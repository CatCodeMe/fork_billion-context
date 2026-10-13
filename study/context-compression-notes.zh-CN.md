# billion-context 学习笔记：Agent 上下文压缩的原理与实现

> 用途：面试准备。基于对仓库源码（`kernel/`、`src/`）与自带论文（`paper/`）的通读整理。
> 约定：**[代码]** = 我读过源码确认；**[论文]** = 作者自述数据，未独立验证；**[推断]** = 我的理解，面试时按"我的理解"来讲。
> 诚信提示：这是别人的开源项目（作者 ranxianglei），面试时请讲成"我深入研究/分析了它"，不要说成自己设计的。第 9 节给了让它变成"你自己的东西"的做法。

---

## 0. 三十秒电梯稿

长时间运行的编码 Agent 会把上下文窗口撑爆：工具输出一直累积，主流做法要么滑窗直接丢，要么到阈值后把整段历史一次性总结成一坨、原文丢弃（不可逆，且每轮重复总结，早期信息指数衰减）。

billion-context 是一个夹在 Agent 和模型 API 之间的**压缩代理**，做法是：

1. **让模型自己决定压什么**：内核只负责"何时提醒、推荐哪些区间、怎么记账"，摘要文本由模型写（内核本身**永远不调用模型**）。
2. **只压增量、只压已消费的内容**：每次压缩只折叠"上次压缩以来新增且任务已用完"的区间，而不是重写全部历史。
3. **折叠（fold）布局**：窗口 = 若干可单独恢复的摘要块 + 原文的最近工作区。摘要块还能再被压成二级、三级（像 LSM-tree）。
4. **对 prefix cache 友好**：历史只追加，压缩只替换中段，摘要位置固定，所以 KV cache 前缀基本不失效。

自报结果（单用户生产数据，见第 8 节）：204,800 窗口模型上零越界；重负载会话约 70× 常态压缩比；活跃节奏下 cache 读占比 94.2%。

---

## 1. 问题与已有方案的缺陷

| 方案 | 缺陷 |
|---|---|
| 滑动窗口/截断 | 窗口外的内容永久丢失（保留率 R∞=0） |
| 阈值触发的一次性 compaction（Claude Code `/compact` 类） | 模型无感知、不能拒绝、单一粒度；每轮把"摘要+增量"再总结一遍，早期信息按 ρ^k 衰减（ρ≈0.4–0.6，4 轮后剩 3–13%）；**重写历史 = 整个 prefix cache 失效** |
| 外部记忆（向量库/图） | 写入时就有损，丢过程性上下文（为什么这么修、精确值） |
| 无损递归（LCM） | 保留率 100%，但常驻体积不衰减，窗口更快塞满 |
| 训练式（AgentFold 等） | 每个 Agent 框架要训一个 checkpoint，策略在训练时冻结 |

billion-context 的定位：**免训练**，策略写在可版本化的 prompt（"doctrine"）里；**可逆**（每个块可 decompress）；**增量**（每段内容一生只被折叠一次）。

---

## 2. 整体架构

```
Agent 客户端 (Claude Code / Codex / OpenCode / pi ...)
        │  改 base URL 指向代理（或装原生插件）
        ▼
┌──────────────────────────── billion-context（src/，宿主/适配层）───────────────────────────┐
│ server.ts / server/handle.ts   HTTP 代理、路由、会话识别                                   │
│ server/prepare-{openai,anthropic,responses,google}.ts   每种 wire 协议的请求预处理         │
│        └─ 调内核 processTurn → 重建请求 → 注入 nudge / 压缩工具 / 系统提示                 │
│ loop/core.ts  runCompressLoop   代理侧执行 compress 工具调用并重新请求上游（代理模式）    │
│ preflight.ts  转发前预压缩（输入已超窗口时）                                              │
│ session.ts / persist.ts / session-id.ts   会话状态、落盘、会话身份                         │
│ fold-reconcile.ts / prefix-affinity.ts    客户端重写历史后的"折叠状态修复"、无 ID 会话归属 │
│ cache-ledger.ts   prompt cache 命中与节省的记账                                            │
└──────────────┬──────────────────────────────────────────────────────────────────────────┘
               │ 纯函数调用（状态显式传入传出，无 I/O，不调用模型）
┌──────────────▼──────────────── acp-kernel（kernel/，纯 TS，零运行时依赖）────────────────┐
│ processTurn / applyCompression / decompress / search / status / retrieve                   │
│ 节点式流水线：见第 4 节                                                                    │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

关键边界（`kernel/DESIGN.md` §1-2）[代码]：
- **模型写摘要，库负责编排**。摘要文本是 `applyCompression` 的**入参**，内核不联网、不调模型。
- **内核无状态**：`CompressionState` 由宿主持有并持久化，每次调用传入传出（`zip(data)→data` 的思路）。
- 内核消费统一的 `CoreMessage[]`（id/role/contentType/text/toolName/toolCallId），宿主适配器负责 Anthropic/OpenAI/Responses/Gemini ⇄ CoreMessage 的双向转换（`kernel/src/wire/*`）。
- 构建上 `kernel/` 作为 `file:` 依赖被 tsup **内联**进 `dist`；改内核必须 bump 内核版本、人工评审（`AGENTS.md` Kernel Boundary）。

仓库规模参考：`kernel/src` 约 2.1 万行；`src/server.ts` 3057 行、`src/preflight.ts` 2361 行、`src/loop/core.ts` 1458 行。

---

## 3. 核心数据模型（`kernel/src/types.ts`、`DESIGN.md` §3）

### 3.1 消息引用（ref）
- 每条消息按**内容哈希**得到 raw id，再分配稳定短号 `m00001, m00002 …`（`refs.ts`，`assignRefsNode` 是 ref 表**唯一的写入者**）。
- 渲染时在文本里注入标签（XML 形态，`render-refs.ts`），让模型能引用 `m00420–m00520` 指定压缩范围。源码里这类尖括号必须写成 `\x3c \x3e` 十六进制转义（避免工具链吞标签）。
- **不变量：ref 编号永不复用、不重复**（即使消息被删/折叠）。因为摘要里会引用旧编号，复用会让 decompress 静默张冠李戴。游标算法 `highestUsedIndex(map)+1`，所以宿主绝不能收缩 `messageRefs` 表。
- 被保护或含"无法恢复的媒体"（远程 URL 无字节）的消息得到 `BLOCKED` ref，永不展示、永不折叠。

### 3.2 压缩块 `CompressionBlock`
`blockId(b0,b1…)`、`tier ∈ {1,2,3}`、`topic`、`summary`（模型写的）、`directMessageIds`（本次直接折叠的）、`effectiveMessageIds`（传递闭包：含被它吞并的旧块所覆盖的全部原消息）、`directBlockIds`（被吞并的旧块）、`active`、`survivedCount`、`generation(young/old)`。

### 3.3 三级金字塔（"LSM tree over prose"）
- **T1**：对一段**消息区间**的摘要（范围用 `mNNNNN`）。
- **T2**：蒸馏若干 T1 **块**（范围用 `bN..bM`，`outputTier = min(3, targetTier+1)`）。
- **T3**：把 T2 再浓缩成"事实索引"（每块 30–60 token）。
- 每级体积都远小于下一级 → 摘要总量增长逐级衰减（论文的"pagoda effect"）。

### 3.4 状态
`CompressionState` = `blocks` + `messageRefs{byRaw,byRef}` + `nudge{基线/上次展示 token/分级节奏}` + `stats` + `deadRefs`（墓碑）+ `lastPassIds` 等。

---

## 4. 每一轮发生了什么：`processTurn` 流水线

代码：`kernel/src/compress.ts` `buildNodes`（约 859 行）+ 各节点实现 [代码]。顺序：

```
reconcile-live-ids  → 把客户端回放的"已被折叠的旧 id"重新对上（echo 连续性）
assign-refs         → 给新消息分配 mNNNNN（唯一写 ref 表的节点）
sync-blocks         → 同步块的激活状态；advanceSurvival 做 young→old 晋升
prune               → 重建可见视图：删掉被块覆盖的消息，在锚点插入摘要
ccr-store           → 超大工具结果入库，原位换成确定性占位符
absorb-hide         → 隐藏已被"吸收蒸馏"的消息（可选特性）
crush               → 确定性机械压缩（json-fold / code-trim / log-select）
absorb-prompt       → 可选的强制蒸馏提示
filter              → 按角色/类型的可见性规则
hide-compress-calls → 隐藏已被消费的 compress 工具调用噪声
recommend           → 计算"受保护区"与"可压缩区间"推荐列表（带真实 token 数）
nudge-inject        → decideNudge：这一轮要不要提醒模型压缩
emergency-truncate  → 最后一道保险：使用率≥95% 时截断大工具输出
render-refs         → 注入 ref 标签
```

注意：论文/`DESIGN.md` 里写的 `merge-blocks` 节点，在当前 `buildNodes` 中**不存在**（文档有漂移，面试时以"论文描述 + 实际代码略有演进"回答更稳）。

节点接口极简（`kernel/src/pipeline.ts`）：`{ name, run(io, ctx) → io, enabled? }`，`io = {messages, state, effects}`；`runPipeline` 顺序执行。每个节点只管一件事，纯函数、可单测。

---

## 5. 关键机制详解

### 5.1 谁来触发：growth-gated nudge（`decideNudge`，`compress.ts` ≈ 1791）

内核**不自己压**，只决定"这一轮要不要往提示里塞一段 nudge，让模型自己调用 `compress`"。我读到的逻辑 [代码]：

默认参数（`kernel/src/config.ts`）：
- `growthFloor = growthCap = 50000`（**窗口大小无关的固定 50K 增长步长**，AGENTS.md KDD#8 明确"不要按窗口百分比缩放"）
- `minGrowthFloor=20000, minGrowthRatio=0.45` → 实际增长门槛 `max(20000, 0.45×50000)=22,500`
- `maxContextLimitPct=0.75`（高压带）、`emergencyThresholdPct=0.95`、`minContextLimitPct=0.45`
- `minCompressRange=5000`（字符）、`maxSummaryLength=20000`、`preserveRecentMessages=5`、`preserveRecentTokens=5000`

判定流程：
1. **高压带**（使用率 ≥ 75%）：绕过增长门，选"可回收量最大"的层级（T1/T2/T3），但要求可回收量 ≥ `minPressureBenefit = max(5000, 1%窗口)`，避免"越压越小、每轮都触发"的零收益死循环（#198）。≥95% 标记为 EMERGENCY，只改措辞。
2. **常态**：必须 `growthSinceReference ≥ 22.5K`（相对"上次展示 nudge 的 token 数"或基线）。然后：T1 有效可压量 ≥ 50K → 发 T1；否则看 T2/T3（块数量触发默认关闭：1000/2000；或 token 质量阈值 1.5× 且大于下层）。T2/T3 还有各自的节奏门（距上次同层展示 ≥ 增长下限）。
3. **First-sight mass bypass**：会话"带着一大坨历史进来"（无基线、使用率 ≥45%、可压量 ≥50K）时，不必先等一整个增长步长，否则会一直闲置直到爆（#194/#351）。
4. nudge 之后的状态：展示后记 `lastNudgeShownTokens`；成功压缩会重置基线；token 大幅下降（宿主 compaction）则重置节奏。

> 论文称"三个门取合取（使用率下限 × 增长 × 最小区间）"。我在代码里看到的是：45% 使用率下限主要出现在 first-sight 分支，常态主要靠"增长≥22.5K + 有效可压量≥阈值"。论文是 v0.2 描述，代码已演进，面试时可以说"我对照过实现"。

**设计哲学 [论文 §4]（面试高频）**：
- *只压已消费的内容*：判据是"当前任务步骤是否还需要这段"，不是"旧/大"。
- *不告诉模型上下文占比*：只给指令 + 可压区间列表。否则模型看到"20% 已用"就拒绝压缩。
- *模型有权拒绝*（nudge 被措辞为"效率提示而非溢出警告"），可在调试中途晚点再压。
- *推荐列表带真实尺寸*（token 数/消息数/工具占比）：没有尺寸时模型会乱选零散低价值区间。
- *压缩时模型看到完整原文*，压完原文离开工作集；nudge 与 compress 调用事后被隐藏（`hide-compress-calls`），不在上下文留痕。

### 5.2 压缩怎么落地：`applyCompression`（`compress.ts` ≈ 349）

输入：模型给的 `ranges[{startRef,endRef,summary,topic}]` + 当前消息 + 状态。主要步骤 [代码]：
1. **清洗摘要**：去掉孤立 surrogate（模型把 `\uXXXX` 抄进摘要会毒化之后每次请求体，#816）。
2. **解析边界** `resolveBoundaries`：ref → 索引；区分 `unknown`（从未存在/别的会话）与 `consumed`（已被某块吞并）。
3. **死 ref 墓碑** `deadRefs`（#2362）：ref 存在但已无任何可见/已折叠消息（客户端改写或丢弃了），记死，后续回执明确告知"不要再重试"，避免模型陷入自我放大的失败循环。
4. **最小范围门**：总字符 < `minCompressRange` 拒绝（"太小，合并更多消息"）；纯 refold 例外。
5. **区间重叠**：重叠的范围警告并跳过（先到先得），不整批失败。
6. **配对修正** `tool-pairs.ts` / `reasoning-pairs.ts`：把落在区间外的 tool_call/tool_result 另一半**拉进来**一起压，保证不产生孤儿。
7. **保护区软排除**：最近 N 条 / 最近 token / 最近一条用户消息 / 受保护工具（`compress`、`acp_rule` 永远受保护）从区间里剔除并给 warning；剔光才报错。
8. **回合完整性闸门** `turn-integrity.ts`（#684）：保留侧有 tool-call 而推理块被折叠、或 call/result 被拆到两侧时，整回合撤回——严格后端（DeepSeek thinking 模式等）会拒绝。
9. **分层**：消息区间 → T1；块区间 `bN..bM` → 目标层 +1，并把被吞并的块置为非 active（`directBlockIds`），保留血缘。
10. 生成新块，更新 `effectiveMessageIds` / `stats` / 重置 nudge 基线（避免反馈环）。
11. **Refold in place**（#398/#400）：对已折叠区间再次压缩可原地更新，不新建块。

### 5.3 视图怎么重建：`prune`（`prune.ts`）
- 被激活块覆盖的消息从可见列表里删除；每个块的摘要渲染成一条 `[Compressed conversation section] — topic` 消息（id=`acp_summary_bN`，内核渲染成 role=system），插在块**直接覆盖范围**里最早消息的位置。
- **锚点必须"配对安全"**（`pairSafeAnchorIndex`）：摘要不能落在 `assistant tool_calls` 与其 `tool` 结果之间（OpenAI 严格后端会 400）；也不能切开同一轮 assistant 的 reasoning+text+tool_calls（DeepSeek 要求原样回传）。
- **首条用户消息钉住（pin）**：永远保留，即使被块覆盖。因为 Anthropic 等要求对话以 user 开头；顺序是"先判 pin 再判 covered"，是契约。
- **#2733 关键修复**：摘要**永远不能排在首条用户消息之前**；锚点按块的"直接范围"而不是合并后的有效范围计算——否则每次再折叠都会把摘要移回很早的位置，改写 provider 已缓存的字节，prefix match 塌回几 K。
- 防御式清理：`stripOrphanedToolCalls/Results/Reasoning` 兜底去掉孤儿，宁可丢孤儿也不发会 400 的请求。

### 5.4 恢复：`decompress` / `search_context` / `acp_status`
- `decompress(blockId)`：重新激活源消息、关闭该块；还支持 **decompress-to-file**（把原文写到文件让模型用读文件工具读，**不改变上下文前缀**，保护 cache）。
- `search_context`：对块的 topic/summary 做关键词相关度打分（topic 命中权重大于 summary 命中）。
- `acp_status`：给出各类内容占比与当前可压区间，模型可据此校准。
- 论文坦言（§8.1）：这个规模的模型**不会主动**去恢复，需要明确指示——这是"doctrine→权重"的动机。

### 5.5 摘要质量的"宪法"：compression doctrine（`kernel/src/compression-rules.ts`）
KEEP 原文不改：带行号的完整路径、签名与关键代码行、报错原文、**决策及其"因为"**、约束、精确值、用户意图与目标演进、**Open objectives（未完成目标）带 ref**、开放问题、关键消息 ref。
DROP：冗长日志（留错误行）、重复读文件、已消费的探索、死路（但留一行教训）、来回讨论的过程。
优先级：目标/意图 > 决策+理由 > 精确产物 > 结论 > 教训。
安全细节：
- 引用用户原话**必须带 ref**，否则只能转述并标注（曾出现摘要里伪造"user verbatim"导致任务回归，2026-09-06 修订）。
- 记录的任务状态要写成"TASK AS OF THIS BLOCK"（历史），防止后读者把它当成现行指令重新执行。
- T2 蒸馏：每源块 50–150 token，强制保留 Open objectives；T3：`[PR/版本] — ≤8 词结果`。
- 覆盖这些规则需要显式 `acknowledgeRisk: true`（`prompts.ts`）。

### 5.6 无损/确定性的"前置减重"手段
- **CCR（content-cached retrieval，`ccr.ts`）**：工具结果 ≥ 4000 token 在**到达时**入库，可见处替换为两行确定性占位符：`📦 [acp-stored #m00423 · shell output · 12,345 tok] \`cmd\`` + `→ acp_retrieve("m00423") returns the full text`。**replace-once-at-arrival**：之后字节永不变化 → prefix-cache 稳定；客户端重发原文时也重新投影成占位符（#1460）。找回时原文走 tool result 本身（最低信任层级）；更大的导出成文件让模型分页读。用严格语法解析占位符，而非子串扫描（#1456，防文档中提到该标记被误判）。
- **crush（`crush.ts`）**：json-fold（字段方差折叠，**构造上无损**，如 `{"__acp_crush":"rows",...}`）、code-trim（去注释/docstring，有损）、log-select（构建/测试日志，有损，但内核强制"所有 ERROR/FAIL 行必须原样保留"否则整个结果被拒绝）。**fail-open**：任何异常都原样放行；刻意不做 query 感知（否则每轮结果变化会让 cache 抖动）。
- **图片压缩**、**absorb**（强制模型蒸馏大工具结果，有损，默认关）也属此类。
- **emergency-truncate**：使用率 ≥95% 且无可压内容时截大工具输出（保留前后各 2000 字符）；连续 3 次"卡死"（无可行压缩 + 截不动）发出 `terminalEscape` 信号：建议新开会话/原生 compaction。

### 5.7 为什么 prefix cache 不会被破坏（**面试核心卖点**）
1. 历史**只追加**，压缩只把中段的一个区间换成一条摘要；前面的字节不变。
2. 摘要锚点稳定：用"直接范围"+ pin 之后，不会回跳到很早的位置（#2733）。
3. nudge/系统提示注入位置固定、不因轮次增删（见 `prepare-openai.ts` 里对 title-gen 请求的处理注释：不能因 message 数变化翻转是否注入，否则系统提示字节变化会打断每一轮的 cache）。
4. CCR 占位符 replace-once、crush 与 query 无关 → 同一消息每轮字节一致。
5. 摘要消息在代理模式下"重新配音"为 `user`（`systemToUser`），保持首条 system 字节稳定，且满足 SGLang"只能有一条 system 且在首位"的限制（#377）。
6. 对比：重写式 compaction 每次压缩都使整个前缀失效。
自报：活跃节奏（间隔<2 分钟，占 89% 流量）下 cache 读占比 **94.2%**；仅 16% 的 miss 能由"新增后缀"解释，其余是 provider 侧过期/驱逐 [论文，需独立验证]。

---

## 6. 宿主侧（代理）实现要点

### 6.1 两种压缩模式（AGENTS.md KDD#7，TECHNICAL-NOTES）—— 极易被追问
| | 插件模式（`x-bili-plugin`，如 `bili pi`） | 代理模式（普通客户端） |
|---|---|---|
| 谁执行 `compress` | Agent 自己（本地执行） | **代理**（服务端循环） |
| compress 调用在客户端历史里？ | 在 | 不在（临时） |
| 摘要载体 | **tool call 本身** | **`acp_summary` 消息**（重新配音为 `user`） |
| nudge | 代理注入（Agent 没有这个通道） | 代理注入 |
设计原则：任何涉及 wire 的改动**必须在两种模式下都推演**；#377 就是只在代理模式出现的 bug。模式按请求判定、按会话"粘性"绑定，只升不降。

为什么摘要用 `user` 而非 `system` 或伪造 tool call：mid-stream 的 system 被严格后端拒绝；伪造 tool_calls/tool_result 配对太侵入（要造 id、声明工具、还要处理没有真实调用的 preflight 块）；`user` 消息可出现在任意位置，改动最小，代价是语义上"摘要变成了用户说的话"，但有明确前缀标记，模型能容忍。

### 6.2 `runCompressLoop`（`src/loop/core.ts`）
代理模式下，上游流式响应里模型发出 `compress` 工具调用 → 代理**拦截**、本地调用内核 `applyCompression`、更新会话状态、把结果作为 tool result **再次请求上游**（最多 `MAX_LOOP_ROUNDS=10` 轮），客户端只看到连续的文本流和一条可见性标记（`📦 [ACP] Compressed …`）。还处理：SSE 流中断后的"续写式重试"（引用已转发尾部让模型无缝接着写）、退化响应（空/截断）重试、上游 524/504 网关死亡（学到"改用流式摘要"）、`thinking` 签名相关 400（见 6.5）。
注意：模型曾**自己伪造**"📦 Compressed"标记而没真调工具（#717），所以代理会剥掉模型自写的标记行并告警，验证压缩是否落地要看 `acp_status`。

### 6.3 Preflight（`src/preflight.ts`，#247）
场景：用户从 1M 窗口模型切到 260K 模型，请求本身就超窗口，上游直接拒绝，模型永远看不到 nudge → 会话卡死。解法：**转发前**由代理发起独立的摘要调用，先把最老的可压区间压掉。要点 [代码]：
- 每次摘要块大小约窗口的 60%（`CHUNK_FRACTION`），最多 16 轮；摘要调用次数有上限（#574）。
- **净收缩验收**：候选摘要必须比所覆盖区间小（容忍 1.05×），防止弱摘要模型"越压越大"（#1819）。
- 空摘要区分瞬时（content_filter→同区间重试≤2 次）与尺寸驱动（二分重试）与确定性空答复（连续 3 次→会话级"死探针"）。
- **超大溢出**（如 dsh 一次重放 509 万 token 到 24 万窗口，需 ~45 次折叠、客户端 300s 就断连）：不调模型，改用 CPU-only 的**确定性结构化摘要**（`deterministicDigest`），原文仍可 decompress（#2383）。
- 支持"外部摘要器"（独立模型、有序故障转移、并发池）。

### 6.4 会话身份与折叠状态修复
- **内容哈希身份是脆弱的**：客户端重序列化历史（重启/恢复、tool_result 重编码、空白变化）会让所有 id 变化，折叠覆盖失效，原文重新涌回 → "death spiral"（#1908）。`fold-reconcile.ts` 逐级对齐修复：①前后缀精确 id 锚定 → ②按协议稳定的 toolCallId 认领 → ③NFC+空白规整后文本相等（同重复序号）→ ④位置身份 `foldPositions`（自存储的规范指纹，用位置做所有权证据，指纹仅作置信度比较）→ ⑤assistant 回合键、图片能力变体……**坚持保守：只有协议唯一 id 或完整规整文本相等才认领，绝不做模糊相似**，因为误归属代价极高（MESSAGE-IDENTITY.md）。
- **前缀亲和 `prefix-affinity.ts`**：无会话 id 的客户端每次全量回放历史，把历史做成追加链 `h_i = sha256(h_{i-1} ‖ msg_i)`，找存储链中**最长严格前缀**匹配的会话——类比 vLLM/SGLang 的 radix prefix cache，但用在身份层；只做头部锚定，分叉自动 fork 成新会话。
- 特殊：dsh 等"同一 id、多种人格"的宿主，用 `subagentNamespace(id, systemText)` 把辅助人格分叉到 `<id>|sub:<fp>`，防止覆盖主会话基线；这是**证据白名单**，不是全局开启。

### 6.5 绝不能碰的东西：signed thinking（KDD#10）
Anthropic `thinking/redacted_thinking`、Gemini `thoughtSignature` 回放时按字节验签。代理转发的字节会成为客户端持久历史、也是重请求的基础，**任何改写（去标签、去重、重排、丢空段）都会让会话永久 400**（#1882 的真实事故）。所以：思考通道字节级原样；工具调用**参数**也字节级原样（#1039：任何过滤都会破坏用户要执行/写入的数据）；标签回显过滤只作用于模型**文本散文**。
这也是"根因 vs 掩盖症状（疏不堵）"原则的教科书案例（#933→#1039）。

### 6.6 其它工程细节
- 日志统一走 `loggerLog`，自更新（`update.ts`）改动要先发"空转验证版本"。
- 配置面是"所有者设计领地"，新增字段需要写明与现有机制的映射；env 变量是稀缺资源。
- 上下文窗口解析优先级链：`anthropic-beta` 协商 > 插件头 > runtime-info > launcher env > 路由配置 > models.dev > 内置表（静态源永远输给更新鲜的权威源）。
- 测试：node 内置 test runner；真实客户端 e2e（codex CLI 走完 warmup→增长→ACP 压缩→纯度→native-compact）；"wire 约束账本只增不减"（上游拒绝过的形状永久写进测试）；黄金文件锁住内核行为常量。

---

## 7. 数据流走一遍（代理模式，OpenAI chat 为例）

```
客户端 POST /bili/<upstream>/chat/completions  (全量历史)
 ① 会话识别（客户端 id / prefix-affinity / system-hash fork）
 ② preflight：输入 > 窗口？是 → 先独立摘要调用，把最老区间压掉
 ③ prepareOpenai：openaiToCore → core.processTurn（上节流水线）
        ├─ 得到：压缩后视图 + NudgeDecision(+可压区间推荐)
        └─ coreToOpenai；必要时注入 compress/decompress/search/status 工具 + 系统提示 + nudge 文本
 ④ 转发上游（流式）
 ⑤ runCompressLoop：模型若调用 compress → 代理本地 applyCompression → 重新请求上游
    （最多 10 轮），客户端只看到最终文本；状态落盘 (persist.ts)
 ⑥ 下一次请求：客户端带着自己的全量历史回来，processTurn 用保存的 state 把已折叠区间再次替换为摘要
```
关键点 [推断]：**客户端永远持有未压缩的完整历史**，压缩是在代理里"每次请求现算的视图"，这也是为什么需要 fold-reconcile（客户端回放的历史和代理保存的折叠状态要能对上）。

---

## 8. 数字与证据（全部为作者自报，单用户，非随机对照）

- 部署：4.5 个月、3 个宿主、174,327 次调用、累计输入 ~18.76B（全宿主 ~24.7B token）。
- 204,800 窗口模型：**0 次越界**（峰值 198,628）；1M 窗口马拉松会话 8,584–12,049 次调用。
- 单次压缩：被压区间中位 2.6K token → 摘要中位 **185 token**，97.5% ≤2K；整体压缩比中位 7.9×，工具为主的块中位 24×、p75 45×；重负载会话常态约 **70×**。
- T2 块仅占 3.5%（60/1711）——级联蒸馏是安全阀而非常规路径。
- 保留率模型：传统阈值压缩 R(k)≈ρ^k→0；fold 每段内容只折叠一次，保留率稳定在 ~1/8，R∞>0。
- Cache：混合读占比 90.7%/88.3%；<2 分钟间隔 94.2%；>60 分钟 9.1%（provider TTL 过期，不是布局问题）。
- 受控试验（qwen3.8-27b，temperature 0，65K 窗口）：计费 token 比保留基线少 **31–54%**；重读调用减少 63%（2.7×）；探针召回持平。**归因**：2.7× 主要来自"doctrine+消息标签"整体，而非压缩机制本身（静默对照组几乎复现全部效果）。
- 容量外推（模拟，非实测）：1M 窗口理论上可支撑 ~28.6B token / 106 天单会话。
- 作者自述的局限：单用户、观察性、基准 RQ 待做、探针饱和（85–95%）、doctrine 偏英文、受控试验单模型、小窗口（16K）doctrine 本身有 ~25% 固定开销。

**面试时怎么处理这些数字**：说"作者自报的生产数据"，主动指出它是单用户观察数据而非对照实验；你能展示批判性比背数字更加分。

---

## 9. 让它成为"你自己的"：建议的落地动作

1. **写一个 ~300 行的 mini 版（强烈建议）**：只实现 `CoreMessage → ref → block → prune → nudge` 的最小闭环 + 一个假的"摘要函数"，配上单测。你能现场手画并解释每一步，说服力远大于复述。
2. **跑起来看真实流量**：`npm run build && bili start`，用 `ACP_DUMP`/body dump 对比压缩前后的请求体，截图 `/acp` 面板的 cache 报告。
3. **做一个小而真实的贡献/实验**：例如写一个对比实验（阈值 compaction vs fold 在你自己的长会话回放上的 token/重读次数）；或者给 `crush` 加一种新的无损策略并附 fail-open 测试；或者为 `decideNudge` 补一份"各分支触发条件"的表驱动测试。
4. 记录你读代码时发现的**文档与代码漂移**（如 `merge-blocks`、nudge 的使用率门），这是很好的"我真的读过"证据。

---

## 10. 面试 Q&A 预演

**Q1. 为什么让模型决定压缩，而不是按阈值自动压？**
阈值方案三个缺陷同源——决策者看不到任务状态：模型无感知、不能拒绝、只能单一粒度。让模型决策可以按"任务是否还需要"选区间，并可在调试中途延后。论文数据：22% 的有效压缩发生在引擎没发 nudge 的回合（模型自发）。对照试验里"固定节奏"在重复负载上更便宜，但在有阶段结构的负载上输给默认配置，说明可泛化的是"时机和范围判断"。

**Q2. 压缩会不会丢信息？怎么兜底？**
三层：①doctrine 的 KEEP 规则（决策+理由、路径行号、报错原文、未完成目标）；②每个块可 decompress / decompress-to-file，血缘（`directBlockIds`/`effectiveMessageIds`）保证再压缩后仍能追溯；③大工具结果走 CCR 无损入库 + 可检索。诚实的局限：模型不会主动恢复；"逐字历史"类任务（审计/合规）不适用。

**Q3. 怎么保证 prefix cache 不被破坏？**
见 5.7：只追加、摘要锚点稳定且不早于首条用户消息、nudge 注入字节稳定、CCR replace-once、crush 与 query 无关、摘要重新配音为 user 以保持首条 system 字节稳定。

**Q4. 多级压缩（T1/T2/T3）有什么用？**
摘要本身也会累积。T2 蒸馏 T1 块、T3 再浓缩，使摘要质量随层级衰减，常驻体积按金字塔收敛，才能支撑超长会话；实际 T2 占比仅 3.5%，是安全阀。

**Q5. tool_call/tool_result 配对怎么处理？**
三处防线：压缩时把区间外的另一半拉进区间；回合完整性闸门整回合撤回被保护区切开的回合；prune 时摘要锚点避开 call/result 之间与同一 assistant 回合内部，最后还有孤儿清理兜底。目的是永不向严格后端发送会 400 的结构。

**Q6. ref 编号为什么永不复用？**
摘要里引用旧编号；复用会让 decompress 静默指向别的消息。所以 ref 表只增不减，游标由已用最大值 +1 得到，宿主不得收缩该表。

**Q7. 客户端改写/重放历史，折叠状态怎么办？**
内容哈希身份对重序列化脆弱 → fold-reconcile 分级保守对齐（toolCallId → 规整文本 → 位置指纹…）；对齐不了的老老实实"重新涌回未折叠"，并有僵尸块回收（#2695）。不做模糊匹配，因为误归属比漏匹配代价高。

**Q8. 代理模式和插件模式有什么区别？为什么重要？**
见 6.1。核心是"谁执行 compress → 摘要靠什么载体上线"。改任何 wire 相关逻辑都要两种模式都推演。

**Q9. 你会怎么评估压缩质量？**
作者用：召回探针（含深度召回）、重读调用数（交互成本）、计费 token、cache 命中率；语料分析（块里 KEEP 类标记出现率：精确值 93%、ref 47%、路径行号 39%）。我会补：与 Claude Code `/compact` 在同一回放上的对照、不同模型迁移、摘要的人评或 LLM-judge、恢复延迟。

**Q10. 这个方案的风险/缺点？**
- 依赖模型的判断力与守约（会自己伪造压缩标记、会不去恢复）。
- 摘要有损且不可验证；T2/T3 逐级丢细节。
- 系统复杂度大：多协议 wire、会话身份、折叠对齐，边界 case 极多（仓库里大量 `#NNNN` 修复即是证据）。
- 论文证据为单用户观察数据。
- 小窗口下 doctrine 固定开销显著。

**Q11. 如果让你改进？**
nudge 限频（论文承认 extreme 配置会 over-fire 打断任务）；把 doctrine 蒸馏进权重省掉提示 token；摘要的自动一致性校验（如检查 Open objectives 是否被丢）；和外部检索结合处理"逐字历史"任务。

---

## 11. 速查：关键文件

| 主题 | 文件 |
|---|---|
| 内核设计契约 | `kernel/DESIGN.md`、`kernel/DESIGN-prompts.md` |
| 流水线 | `kernel/src/pipeline.ts`、`kernel/src/compress.ts`（`buildNodes`≈859、`applyCompression`≈349、`decideNudge`≈1791） |
| prune/锚点/pin | `kernel/src/prune.ts`、`kernel/src/sync.ts`、`kernel/src/boundaries.ts` |
| 推荐/保护区 | `kernel/src/recommend.ts`、`kernel/src/protected.ts`、`kernel/src/turn-integrity.ts`、`tool-pairs.ts`、`reasoning-pairs.ts` |
| 提示词 | `kernel/src/compression-rules.ts`、`prompts.ts`、`nudge-text.ts` |
| 无损/确定性减重 | `kernel/src/ccr.ts`、`content-store.ts`、`crush.ts`、`truncate-tools.ts`、`image-compress.ts` |
| 协议编解码 | `kernel/src/wire/{openai,anthropic,responses,google}.ts` |
| 代理主流程 | `src/server.ts`、`src/server/prepare-*.ts`、`src/server/handle.ts` |
| 压缩循环 | `src/loop/core.ts`、`src/loop/adapter-*.ts` |
| 预压缩 | `src/preflight.ts` |
| 身份/对齐 | `src/session-id.ts`、`src/fold-reconcile.ts`、`src/prefix-affinity.ts`、`MESSAGE-IDENTITY.md`、`SESSION-IDENTITY.md` |
| 缓存记账 | `src/cache-ledger.ts` |
| 论文 | `paper/model-driven-…-agents.md`（中文版 `paper/模型驱动的分层增量压缩-免训练多代上下文管理.md`） |
| 模式/规则 | `TECHNICAL-NOTES.md`、`AGENTS.md` |

---

## 12. 我没有验证的部分（避免面试被问穿）

- 未实际运行 `bili`、未跑测试与 e2e，所以没有自己的性能/命中率数据。
- `applyCompression` 在"生成新块、更新 stats"之后的尾段（约 1520 行之后）、`decompress` 的完整实现、`absorb`、`rules`、`output-steering`、`cache-ledger` 的细节只做了浏览。
- 论文中的生产数据、受控试验、容量外推均未复现。
- `src/server.ts` 与 `handle.ts` 的完整路由/会话绑定逻辑只读了入口与关键注释。
