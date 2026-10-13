# LangGraph facts sheet (read 2026-10-12, docs.langchain.com, Python docs)

Convention: each line = fact | source | confidence. "Per docs at time of reading": names/signatures drift; prefer concept names.
Confidence: H = stated on the fetched official page; M = official page via summarizer, wording not verbatim / partially stated; L = third-party or inferred.

Framing (all chapters)
- LangGraph = low-level "runtime" (durable execution, streaming, HITL, thread/cross-thread persistence); LangChain `create_agent` = framework on top of it; Deep Agents = opinionated "harness" (planning, subagents, filesystem, context mgmt) on top of LangGraph. | https://docs.langchain.com/oss/python/concepts/products.md | H
- Workflows follow predetermined code paths; agents define their own process and tool usage. | https://docs.langchain.com/oss/python/langgraph/workflows-agents.md | H
- Docs state a single agent with right tools/prompt can often match multi-agent; multi-agent justified by context management, distributed development, parallelization. | https://docs.langchain.com/oss/python/langchain/multi-agent | H

## 1 Agent Loop / termination / retry / interrupt
- Graph = state + nodes + edges ("nodes do the work, edges tell what to do next"); `StateGraph` must be `.compile()`d (compile validates structure, takes checkpointer/breakpoints). | https://docs.langchain.com/oss/python/langgraph/graph-api | H
- Execution proceeds in discrete super-steps (Pregel-inspired); nodes in the same super-step run in parallel; ends when all nodes inactive and no messages in transit. | graph-api page above | H
- Conditional edges (`add_conditional_edges`) route by a function's return; `Command` combines `update`+`goto` (+`graph` for parent, `resume`); docs advise static edges OR dynamic routing per node, and static edges still run alongside a `Command.goto`. | graph-api | H
- Recursion limit caps super-steps per run; docs state default is 1000 "starting in version 1.0.6"; exceeding raises `GraphRecursionError`; set as top-level `recursion_limit` config key (not inside `configurable`); `RemainingSteps` lets a graph route before hitting it. (Older material says 25 -- outdated per this page.) | graph-api | H
- Agent loop in `create_agent`: model repeatedly calls tools until objective met; page gives no explicit termination condition beyond task completion; retries via `ModelRetryMiddleware`/`ToolRetryMiddleware`. | https://docs.langchain.com/oss/python/langchain/agents.md | M
- Node `RetryPolicy` (via `retry_policy=` on `add_node`): `max_attempts` 3 (incl. first), `initial_interval` 0.5s, `backoff_factor` 2.0, `max_interval` 128s, `jitter` True; default `retry_on` skips ValueError/TypeError/RuntimeError/OSError etc; for requests/httpx only 5xx retried. | https://docs.langchain.com/oss/python/langgraph/fault-tolerance.md | H
- Timeouts: `timeout=` (seconds/timedelta/`TimeoutPolicy` with run_timeout, idle_timeout, refresh_on); only async nodes; raises `NodeTimeoutError`; failed-attempt writes cleared before retry. | fault-tolerance | H
- `error_handler` runs after retries are exhausted, receives `NodeError`, may return a `Command` to update state and route; interrupts bypass error handlers. | fault-tolerance | H
- Graceful shutdown: `RunControl.request_drain()` stops at the next super-step boundary (raises `GraphDrained`), never preempts running work; continue with `invoke(None, config)` same thread_id. | fault-tolerance | H
- Interrupts: `interrupt(value)` pauses inside a node; resume with `Command(resume=...)` on the same `thread_id`; checkpointer required. | https://docs.langchain.com/oss/python/langgraph/interrupts.md | H
- On resume the node restarts from its beginning (code before `interrupt()` re-runs); side effects before it must be idempotent; do not wrap `interrupt()` in bare try/except (it pauses by raising); multiple interrupts in a node matched to resume values by index; avoid `while True` with interrupt inside one node. | interrupts | H
- Parallel branches that interrupt together are resumed in one call with `Command(resume={interrupt_id: value,...})`. | interrupts | H
- `interrupt_before`/`interrupt_after` static breakpoints: debugging, not HITL; resume by passing `None`. | interrupts | H
- Durability modes `exit` / `async` / `sync` (per-call `durability=` argument): exit saves only at run exit; async saves while next step runs (small risk of missed checkpoint on crash); sync saves before next step. Default mode NOT stated on the pages I read. | https://docs.langchain.com/oss/python/langgraph/checkpointers.md | H (modes), default unknown
- Pending writes: if a node fails mid super-step, outputs of nodes that completed in that super-step are stored and not re-run on resume. | checkpointers | H
- Functional API: `@entrypoint` / `@task`; completed task results saved in checkpoint and not re-run on resume (resume = invoke with None + same thread config). | https://docs.langchain.com/oss/python/langgraph/use-functional-api.md | H
- Tasks/side effects: docs advise deterministic + idempotent workflows, side effects in tasks, idempotency keys. | web search summary of durable-execution page (page body itself was thin when fetched) | M/L
- Docs mention a recent `Overwrite` to bypass reducers and `UntrackedValue` (never checkpointed). | graph-api | H

## 2 Tools / permissions
- HITL middleware: `HumanInTheLoopMiddleware(interrupt_on={tool: policy})`; decisions `approve`/`edit`/`reject`/`respond`; resume `Command(resume={"decisions":[...]})`, one decision per action in order; `when` predicate gates on tool args (needs langchain>=1.3.3); checkpointer required. | https://docs.langchain.com/oss/python/langchain/human-in-the-loop.md | H
- Built-in middleware list includes tool error (exception -> model-visible message), tool retry, model retry, model fallback, tool call limit, model call limit, PII detection, LLM tool selector, provider tool search, context editing, filesystem, shell, subagent, to-do list. | https://docs.langchain.com/oss/python/langchain/middleware/built-in.md | H
- Tool retry defaults: max_retries 2 (3 attempts), backoff_factor 2.0, initial_delay 1.0, max_delay 60, jitter; `on_failure` 'continue' default. | built-in middleware | H
- Handoff tools that update messages must return a matching `ToolMessage` (same tool_call_id) or history is malformed. | https://docs.langchain.com/oss/python/langchain/multi-agent/handoffs.md | H
- Tool-call limit: `thread_limit`/`run_limit`, `exit_behavior` 'continue' (default)/'error'/'end'; thread limit needs a checkpointer. | built-in middleware | H
- No OS-level sandbox / command-permission-policy model in LangGraph core (permissions are middleware/HITL + your own tool code). | inference from absence | L ([推断])

## 3 Context compression / trimming / summarization
- Short-term memory = `messages` in agent state persisted by a checkpointer; trimming via `@before_model` middleware emitting `RemoveMessage(REMOVE_ALL_MESSAGES)` + kept messages; deletion with `RemoveMessage(id)` requires `add_messages` reducer; after trim history must remain provider-valid (tool call must be followed by tool result; some providers need user first). | https://docs.langchain.com/oss/python/langchain/short-term-memory.md | H
- `SummarizationMiddleware`: `model`, `trigger` (fraction/tokens/messages; if omitted never triggers automatically), `keep` default ("messages", 20), `trim_tokens_to_summarize` default 4000; replaces old messages permanently in state with a summary. | built-in middleware + https://docs.langchain.com/oss/python/langchain/context-engineering.md | H
- Context editing middleware: `ClearToolUsesEdit` trigger 100000, keep 3, placeholder "[cleared]". | built-in middleware | H
- Context-engineering model: model context (transient), tool context (persistent), life-cycle context (persistent); `wrap_model_call` changes are transient, state writes persistent. | context-engineering | H
- Summarisation in LangGraph docs is lossy and permanent ("permanently replaced") -- no retrieval-by-reference of originals unless you store them yourself. | context-engineering | H (replacement), [推断] (no retrieval)
- Deep Agents: tool inputs/results >20,000 tokens offloaded to filesystem (agent keeps path + first 10 lines); summarization at 85% of max_input_tokens, keeps 10% recent; fallback 170,000 tokens/6 messages w/o model profile; saves a record of original messages to filesystem; context-overflow error -> immediate summarize + retry. | https://docs.langchain.com/oss/python/deepagents/context-engineering.md | H
- Subagent isolation: subagents run in clean context; parent sees only final message as tool result; Deep Agents `mode: "isolated"` default, `"fork"` inherits parent history. | https://docs.langchain.com/oss/python/langchain/multi-agent/subagents.md ; https://docs.langchain.com/oss/python/deepagents/subagents.md | H
- Prompt-caching-aware design is not a LangGraph core feature; Anthropic prompt-caching middleware exists as provider-specific middleware (params not documented on the page read). | built-in middleware | H (existence)

## 4 Memory / persistence / checkpointer / Store
- Checkpointer persists graph state per `thread_id` as checkpoints (one per super-step); `StateSnapshot` has values, next, config(thread_id, checkpoint_ns, checkpoint_id), metadata(source, writes, step), created_at, parent_config, tasks. | checkpointers.md | H
- Implementations named: InMemorySaver (lost on restart), SqliteSaver (dev), PostgresSaver/AsyncPostgresSaver (production), also MongoDB, Azure Cosmos DB. thread_id < 255 chars for Postgres; checkpoints accumulate, may need pruning. | https://docs.langchain.com/oss/python/langgraph/persistence ; checkpointers.md | H
- Serialization default `JsonPlusSerializer` (ormsgpack/JSON, optional pickle fallback); optional `EncryptedSerializer` (AES, key from `LANGGRAPH_AES_KEY`). | checkpointers.md | H
- Time travel: `get_state_history` (newest first), replay = `invoke(None, checkpoint.config)` (nodes before checkpoint not re-run, after re-run incl. LLM calls); fork = `update_state` on a past checkpoint creates a branch, original history intact; interrupts always re-trigger on replay. | https://docs.langchain.com/oss/python/langgraph/use-time-travel.md | H
- Store: long-term, cross-thread, namespace tuple + key, JSON docs; `put`/`get`/`search`; semantic search needs embedding index config; `InMemoryStore` dev, `PostgresStore` prod (Redis, MongoDB integrations listed); tools access `runtime.store`. | https://docs.langchain.com/oss/python/langchain/long-term-memory.md | H
- Subgraph checkpointer modes: per-invocation (default, `None`, fresh each call, supports interrupt), per-thread (`True`, accumulates, parallel calls to same subgraph conflict), stateless (`False`, no checkpoint/interrupt/crash recovery). Subgraph state inspect via `get_state(config, subgraphs=True)`; not for subgraphs called inside tool functions. | https://docs.langchain.com/oss/python/langgraph/use-subgraphs.md | H
- Time travel with default (inherited) subgraph checkpointer: whole subgraph is one parent step; fork inside needs `checkpointer=True`. | use-time-travel | H
- Reducers: per-key; default replace; `operator.add` appends; `add_messages` merges by message ID; `MessagesState` prebuilt. | graph-api | H
- Parallel writes to the same key without a reducer -> `InvalidUpdateError` ("INVALID_CONCURRENT_GRAPH_UPDATE"); fix = reducer such as `Annotated[list, operator.add]`. Docs do not specify order of parallel writes. | https://docs.langchain.com/oss/python/langgraph/errors/INVALID_CONCURRENT_GRAPH_UPDATE ; graph-api | H
- Parent/subgraph shared keys need a reducer in the parent when parallel subgraphs write them. | graph-api | H
- Deep Agents has its own Memory page (filesystem/Store-backed); not read in detail. | https://docs.langchain.com/oss/python/deepagents/memory.md | L

## 5 Evaluation / observability
- LangSmith: offline evals on curated datasets with references (pre-deploy); online evals on production traces without references; both in a loop. | https://docs.langchain.com/langsmith/evaluation-concepts (via search excerpt) | M
- Trajectory evaluation: compare actual sequence of steps with expected; docs example records node names/tool calls via LangGraph `debug` streaming and passes a `trajectory` key to the evaluator; tool-name-only matching ignores arguments, so LLM-as-judge over full trajectory suggested. | https://docs.langchain.com/langsmith/evaluate-complex-agent ; https://docs.langchain.com/langsmith/evaluation-approaches | M
- Stream modes: `values`, `updates`, `messages`, `custom`, `checkpoints`, `tasks`, `debug`; `subgraphs=True` adds namespaced output; docs recommend event streaming (LangGraph v1.2+) for new apps. | https://docs.langchain.com/oss/python/langgraph/streaming | H
- Overview lists "Debugging with LangSmith" and mentions LangSmith Engine (detects issues in traces, proposes fixes). | https://docs.langchain.com/oss/python/langgraph/overview | H
- Rubric grading middleware (beta) lets an agent self-grade and iterate. | built-in middleware | H

## 6 Cost / caching
- LangSmith auto-records token usage and cost for major providers; breakdown input/output/other; trace tree, project stats, dashboards; usage fields include cache read and reasoning tokens; custom LLM calls need run_type llm + provider/model metadata + token counts; open-weight hosted models are estimated. | https://docs.langchain.com/langsmith/cost-tracking | M (search excerpt)
- Cost-limiting middleware: model call limit (run/thread), tool call limit; `exit_behavior` configurable. | built-in middleware | H
- Multi-agent cost table in docs (model calls / tokens): Subagents 4 calls one-shot, 8 repeat, multi-domain 5 calls ~9K; Handoffs 3 / 5 / 7+ calls ~14K+; Skills 3 / 5 / 3 calls ~15K; Router 3 / 6 / 5 calls ~9K. Illustrative figures from the docs' example scenarios, not general benchmarks. | https://docs.langchain.com/oss/python/langchain/multi-agent | H
- `langgraph-supervisor` `create_forward_message_tool` forwards a worker's last message to output to save supervisor tokens and avoid paraphrasing. | https://pypi.org/project/langgraph-supervisor/ | H
- Node-level `cache_policy` and `set_node_defaults()` exist (node result caching, distinct from provider prompt caching). | fault-tolerance page | H (existence)

## 7 Security / multi-tenancy / auth
- Agent Server (LangSmith Deployment) custom auth: `@auth.authenticate` returns user; `@auth.on` handlers (global / resource / action level, narrower wins) stamp `owner` metadata on create and return filters on read/search or raise to deny; separate `@auth.on.store()` for Store namespaces (convention: first namespace element = user id). | https://docs.langchain.com/langsmith/auth ; https://docs.langchain.com/langsmith/resource-auth (search excerpt) | M
- Changelog notes: thread-creation auth gap fixed in v0.13 (Postgres); namespaces from custom auth validated (v0.15/0.16); fields used by authz filters must not be encrypted. | https://docs.langchain.com/langgraph-platform/langgraph-server-changelog (search excerpt) | M
- Open-source LangGraph itself has no auth: tenant isolation in OSS = your own thread_id/namespace discipline (`context_schema` carries user id). | inference + long-term-memory page | [推断]
- Checkpoint encryption at rest is opt-in (`EncryptedSerializer`). | checkpointers.md | H
- PII detection middleware exists. | built-in middleware | H

## Multi-agent specifics (chapter 8)
- Patterns named in LangChain docs: Subagents (agents as tools; stateless, strong context isolation), Handoffs (tool updates a state variable / `Command`; stateful), Skills, Router, Custom workflow (LangGraph). | https://docs.langchain.com/oss/python/langchain/multi-agent | H
- Subagent returns its final message as tool result; supervisor sees only that; parallel by calling multiple subagents in one turn; async variant = start/check/get-result tools. | subagents.md | H
- Handoffs: recommended implementation for most cases = single agent + middleware switching prompt/tools by `current_step`; multi-subgraph variant uses `Command(goto=..., graph=Command.PARENT)`; subgraph handoff documented to pass only the triggering AIMessage + ToolMessage, not full history. | handoffs.md | H
- `langgraph-supervisor`: maintainers now recommend implementing the supervisor pattern directly via tools for most cases (more control over context engineering); `output_mode` "full_history" vs "last_message"; hierarchical teams by nesting compiled supervisors. | https://pypi.org/project/langgraph-supervisor/ | H
- `langgraph-swarm`: `create_swarm`, tracks `active_agent`; always compile with checkpointer for multi-turn or active agent is forgotten; default handoff passes full history + tool message. | https://pypi.org/project/langgraph-swarm/ | H
- Orchestrator-worker: `Send` creates a worker per subtask at runtime; worker outputs accumulate in a shared state key (reducer). | workflows-agents.md ; graph-api | H
- Deep Agents: `task` tool, subagent config (name, description, system_prompt, tools, model, middleware, interrupt_on, skills, response_format, permissions, mode); auto `general-purpose` subagent; also dynamic and async subagents pages exist. | deepagents/subagents.md ; page index | H / M
- Docs index (as of reading) shows Functional API, Deep Agents, fault-tolerance, event streaming v3 -- these are the "newer" concepts verified.

## Items contradicting common belief
- Recursion limit default is 1000 (since 1.0.6), not 25.
- Supervisor library is no longer the recommended path; tool-based supervisor preferred.
- Resume re-runs the whole node from its start, not from the interrupt line.
- Docs' "default" durability mode not stated on pages read.
- Docs don't specify order of parallel writes to same key.
