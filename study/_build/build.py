import re,sys,io
D='/Users/hulj/cc_wp/fork_billion-context/study/'
CH=[
 (1,'ch1-agent-loop-v3.html','Agent Loop','S'),
 (2,'ch2-tools-permissions.html','工具 · 权限 · 沙箱','T'),
 (3,'ch3-context-compression.html','上下文工程与压缩','K'),
 (4,'ch4-memory-recovery.html','记忆与恢复','M'),
 (5,'ch5-evaluation.html','评估','E'),
 (6,'ch6-cost-cache-economics.html','成本与缓存经济','C'),
 (7,'ch7-security-multitenancy.html','安全与多租户','S'),
 (8,'ch8-langgraph.html','LangGraph 视角','L'),
]
def read(p): return open(D+p,encoding='utf-8').read()
base=read(CH[0][1])
css=re.search(r'<style>(.*?)</style>',base,re.S).group(1)

NEWCSS=r'''
:root{--bg:#f5f4ef;--fg:#1c2321;--mut:#5f6b66;--line:#dedcd2;--card:#fffefb;--acc:#0e6b6f;--accbg:#e3f0ee;--warn:#a85a0c;--warnbg:#fbefdc;--code:#ecebe3;--blue:#2b5fa8;--bluebg:#e5edf8;--purple:#6b4ec2;--purplebg:#eee9fa;--green:#1f7a45;--greenbg:#e2f1e8;--side:#efeee7;--topbar:0px}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#101615;--fg:#e5eae7;--mut:#94a29c;--line:#29342f;--card:#182120;--acc:#52d1c3;--accbg:#17332f;--warn:#f0b360;--warnbg:#35280f;--code:#212b28;--blue:#86aef0;--bluebg:#1a2a42;--purple:#b4a2f5;--purplebg:#2a2347;--green:#6fd09a;--greenbg:#17301f;--side:#131b19;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#101615;--fg:#e5eae7;--mut:#94a29c;--line:#29342f;--card:#182120;--acc:#52d1c3;--accbg:#17332f;--warn:#f0b360;--warnbg:#35280f;--code:#212b28;--blue:#86aef0;--bluebg:#1a2a42;--purple:#b4a2f5;--purplebg:#2a2347;--green:#6fd09a;--greenbg:#17301f;--side:#131b19;color-scheme:dark}
body{padding:0!important;font-size:15.5px}
.shell{display:flex;min-height:100vh}
.side{width:280px;flex:none;background:var(--side);border-right:1px solid var(--line);position:sticky;top:0;height:100vh;height:100dvh;overflow-y:auto;padding:20px 14px 28px;box-sizing:border-box}
.side .brand{font:700 17px/1.3 "Bricolage Grotesque","IBM Plex Sans",sans-serif;margin:0 6px 2px}
.side .bsub{color:var(--mut);font-size:12px;margin:0 6px 16px}
.side .grp{font:600 11px "IBM Plex Mono",monospace;letter-spacing:.08em;color:var(--mut);margin:16px 8px 6px;text-transform:uppercase}
.side button.it{display:flex;gap:8px;width:100%;text-align:left;border:0;background:transparent;padding:7px 8px;border-radius:8px;font-size:14px;line-height:1.4;color:var(--fg)}
.side button.it:hover{background:var(--accbg)}
.side button.it.on{background:var(--accbg);color:var(--acc);font-weight:600}
.side button.it .no{font:600 11px "IBM Plex Mono",monospace;color:var(--mut);padding-top:3px;min-width:18px}
.side button.it.dis{opacity:.5;cursor:default}
.side button.it.dis:hover{background:transparent}
.side .sub2{margin:2px 0 6px 26px;border-left:2px solid var(--line);padding-left:6px}
.side .sub2 button{display:block;width:100%;text-align:left;border:0;background:transparent;padding:4px 8px;border-radius:6px;font-size:13px;color:var(--mut);line-height:1.45}
.side .sub2 button:hover{color:var(--fg);background:var(--accbg)}
.side .sub2 button.on{color:var(--acc);font-weight:600}
.side a.it{display:block;padding:7px 8px;border-radius:8px;font-size:14px;color:var(--fg);text-decoration:none}
.side a.it:hover{background:var(--accbg)}
.stage{flex:1;min-width:0;padding:28px 32px 80px}
.stage main{max-width:860px;margin:0 auto}
.topbar{display:none}
.scrim{display:none;position:fixed;inset:0;background:rgba(0,0,0,.35);z-index:8}
@media (max-width:900px){
 :root{--topbar:48px}
 .shell{display:block}
 .topbar{display:flex;position:sticky;top:env(safe-area-inset-top,0px);height:48px;align-items:center;gap:10px;padding-inline:16px;background:var(--bg);border-bottom:1px solid var(--line);z-index:6}
 .topbar b{font:700 15px "Bricolage Grotesque","IBM Plex Sans",sans-serif}
 .side{position:fixed;left:0;top:0;z-index:9;transform:translateX(-102%);visibility:hidden;transition:transform .2s,visibility 0s .2s;box-shadow:0 0 30px rgba(0,0,0,.25);width:min(300px,86vw)}
 .side.open{transform:none;visibility:visible;transition:transform .2s}
 .scrim.on{display:block}
 .stage{padding:18px 16px 64px}
}
.nav{top:calc(env(safe-area-inset-top,0px) + var(--topbar))!important}
h1{font-size:30px!important}
.sub{font-size:14px}
/* tags by evidence */
.tag{font-weight:600}
.t-code{background:var(--greenbg);color:var(--green)}
.t-inf{background:var(--warnbg);color:var(--warn)}
.t-doc{background:var(--bluebg);color:var(--blue)}
.t-pap{background:var(--purplebg);color:var(--purple)}
/* callouts: Obsidian style */
.callout{--c:var(--acc);border:0!important;border-radius:8px!important;padding:12px 16px 12px!important;margin:12px 0!important;background:color-mix(in srgb,var(--c) 11%,var(--card))!important;color:var(--fg)}
.callout .ct{display:flex;align-items:center;gap:8px;font-weight:700;font-size:14.5px;color:var(--c);margin-bottom:6px}
.callout .ct svg{width:18px;height:18px;flex:none;stroke:currentColor;fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.callout .cb{font-size:15px}
.callout .cb>:first-child{margin-top:0}.callout .cb>:last-child{margin-bottom:0}
.callout.say{--c:var(--acc)}.callout.bridge{--c:var(--warn)}.callout.elev{--c:var(--blue)}.callout.note{--c:var(--purple)}
.row{border-radius:12px!important}
.row h3{margin-top:12px}
.row h3:first-child{margin-top:8px}
.inv>div{border:0!important;border-radius:8px!important;background:color-mix(in srgb,var(--acc) 10%,var(--card))!important}
.inv>div:nth-child(2){background:color-mix(in srgb,var(--blue) 10%,var(--card))!important}
.inv>div:nth-child(3){background:color-mix(in srgb,var(--purple) 10%,var(--card))!important}
.cmp>div{border:0!important;border-radius:8px!important;background:color-mix(in srgb,var(--c,var(--mut)) 10%,var(--card))!important}
.cmp>div b{font-weight:700;color:var(--c,var(--mut))}
.src-pi{--c:var(--purple)}.src-codex{--c:var(--green)}.src-me{--c:var(--acc)}.src-lg{--c:var(--warn)}.src-cc{--c:var(--blue)}
details{border-radius:10px!important}
details[open]{border-color:color-mix(in srgb,var(--acc) 40%,var(--line))}
summary{color:var(--fg)!important}
summary::marker{color:var(--acc)}
table th{background:var(--code);color:var(--mut)}
table tr:nth-child(even) td{background:color-mix(in srgb,var(--code) 45%,transparent)}
.step>h2{border-top:0!important;padding-top:6px!important;font-size:21px!important}
/* home */
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px;margin:12px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px;min-width:0;text-align:left;cursor:pointer;color:var(--fg);display:block}
.card:hover{border-color:var(--acc)}
.card .no{font:600 12px "IBM Plex Mono",monospace;color:var(--acc)}
.card h3{margin:2px 0 4px;color:var(--fg);font-size:16px}
.card p{margin:0;color:var(--mut);font-size:13.5px;line-height:1.55}
.card.dis{opacity:.6;cursor:default}.card.dis:hover{border-color:var(--line)}
.pill{display:inline-block;font:600 11px "IBM Plex Mono",monospace;padding:1px 8px;border-radius:999px;background:var(--code);color:var(--mut);margin-left:6px}
.pill.ok{background:var(--greenbg);color:var(--green)}
.legend{display:flex;flex-wrap:wrap;gap:8px 16px;margin:8px 0}
'''


ICONS={'say':'<svg viewBox="0 0 24 24"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
'bridge':'<svg viewBox="0 0 24 24"><path d="M5 12h14M13 6l6 6-6 6"/></svg>',
'elev':'<svg viewBox="0 0 24 24"><path d="M13 2L3 14h9l-1 8 10-12h-9z"/></svg>',
'note':'<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/></svg>'}
def callouts(h):
    def mk(kind,title,body):
        return '<div class="callout %s"><div class="ct">%s<span>%s</span></div><div class="cb">%s</div></div>'%(kind,ICONS[kind],title,body)
    def f(kind):
        def g(m):
            return mk(kind,m.group(1).rstrip('：:'),m.group(2))
        return g
    h=re.sub(r'<div class="say"><span class="k">([^<]*)</span>(.*?)</div>',f('say'),h,flags=re.S)
    h=re.sub(r'<div class="bridge"><span class="k">([^<]*)</span>(.*?)</div>',f('bridge'),h,flags=re.S)
    h=re.sub(r'<div class="elev"><b>([^<]*)</b><br>\s*(.*?)</div>',f('elev'),h,flags=re.S)
    return h

def cls_tags(h):
    m={'代码':'t-code','推断':'t-inf','文档':'t-doc','论文':'t-pap'}
    return re.sub(r'<span class="tag">\[(代码|推断|文档|论文)\]</span>',lambda x:'<span class="tag %s">[%s]</span>'%(m[x.group(1)],x.group(1)),h)
def cls_src(h):
    pairs=[('pi','src-pi'),('codex','src-codex'),('本项目','src-me'),('LangGraph','src-lg'),('Claude Code','src-cc')]
    for name,c in pairs:
        h=h.replace('<div><b>%s</b>'%name,'<div class="%s"><b>%s</b>'%(c,name))
    return h

chap_html=[];chap_js=[]
for n,f,title,pre in CH:
    s=read(f)
    body=re.search(r'<main>(.*?)</main>',s,re.S).group(1)
    js=re.search(r'<script>(.*?)</script>',s,re.S).group(1)
    ids=set(re.findall(r'id="([\w-]+)"',body))
    for i in ids:
        body=body.replace('id="%s"'%i,'id="%s-c%d"'%(i,n)).replace('url(#%s)'%i,'url(#%s-c%d)'%(i,n))
    body=callouts(cls_src(cls_tags(body)))
    js=js.replace('document.getElementById(','byId(').replace('document.querySelectorAll(','root.querySelectorAll(')
    js=js.replace("document.addEventListener('keydown',function(e){","document.addEventListener('keydown',function(e){if(root.hidden)return;var t=e.target;if(/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)||t.isContentEditable||e.metaKey||e.ctrlKey||e.altKey)return;if(e.key==='Escape'&&document.getElementById('side').classList.contains('open'))return;")
    js=js.replace('function set(n){cur=','function set(n){setTimeout(function(){document.dispatchEvent(new CustomEvent("chstep",{detail:{n:%d,i:cur}}))},0);cur='%n,1)
    js=js.replace('set(0);\n})();','set(0);window.CHAPS=window.CHAPS||{};window.CHAPS[%d]={set:function(i){exitAll();set(i)},titles:steps.map(function(s){return s.querySelector("h2").textContent.split("：")[0]})};\n})();'%n)
    assert 'window.CHAPS' in js,f
    chap_html.append('<div class="chap" id="chap-%d" hidden>%s</div>'%(n,body))
    chap_js.append('(function(){var root=document.getElementById("chap-%d");function byId(i){return document.getElementById(i+"-c%d")}\n%s\n})();'%(n,n,js))

home=callouts('''<div class="chap" id="chap-home"><h1>Agent 设计 · 专家面试手册</h1>
<p class="sub">以 billion-context（上下文压缩代理）为入口，系统学习 Agent runtime 的关键设计，并整理成能在专家面试里讲出来的结论。对标对象：<b>pi</b>、<b>codex</b>，并结合你做过的 <b>LangGraph</b> 招聘 Agent 经验；Claude Code 只引用公开行为。</p>
<div class="elev"><b>怎么用这份手册</b><br>每章是一条“演进主线”：从最朴素的实现出发，<b>遇到现实问题 → 加一个补丁 → 补丁带来新代价 → 引出下一步</b>。面试时照这条线讲，每步末尾的<b>过渡句</b>就是自然的衔接；被追问时展开折叠的“追问”。左侧目录可跳到任意章与任意步。</div>
<h2>章节</h2>
<div class="cards" id="cards"></div>
<h2>证据标签（诚实陈述证据强度本身就是专家信号）</h2>
<div class="legend"><span class="tag t-code">[代码]</span> 读过源码，可指到文件 <span class="tag t-inf">[推断]</span> 我的判断，未逐行验证 <span class="tag t-doc">[文档]</span> 公开文档描述的行为 <span class="tag t-pap">[论文]</span> 作者自报数据，非对照实验</div>
<h2>面试里“带着面试官走”的三招</h2>
<div class="inv"><div><p><b>① 先画图锚定</b><br>开口先画本章的演进图，之后所有问题落在图上的某个部件。</p></div><div><p><b>② 用过渡句埋钩子</b><br>每步结尾那句“代价 → 下一步”，自然把话题引到你准备最深的地方。</p></div><div><p><b>③ 给面试官选项</b><br>“这块我可以从成本讲，也可以从正确性讲，你更关心哪个？”</p></div></div>
<h2>对标对象的层级</h2>
<div class="cmp"><div class="src-pi"><b>pi</b>具体的 agent runtime（loop、compaction、session、扩展 hook），偏 coding agent。</div><div class="src-codex"><b>codex</b>Rust 实现的 coding agent，强在审批、沙箱、compaction 的工程化。</div><div class="src-lg"><b>LangGraph</b>通用状态图编排框架；pi 的 loop 约等于其中的 ReAct 子图。我没读过其源码，对照为公开文档层面的推断。</div><div class="src-cc"><b>Claude Code</b>闭源，仅引用公开文档描述的行为。</div></div>
</div>''')

shell='''<title>Agent 设计手册</title>
<style>%s
%s</style>
<div class="topbar"><button id="menu" aria-expanded="false" aria-controls="side">☰ 目录</button><b id="tbt">Agent 设计手册</b></div>
<div class="shell">
<div class="scrim" id="scrim"></div>
<nav class="side" id="side" aria-label="目录"></nav>
<div class="stage"><main id="stage">
%s
%s
</main></div></div>
<script>
%s
(function(){
var CHS=[
 {n:1,t:"Agent Loop",d:"停止条件、工具往返、打断、重试，与 compaction 的交互。",ready:1},
 {n:2,t:"工具 · 权限 · 沙箱",d:"工具契约、输出治理、审批策略、沙箱与升级路径、间接注入。",ready:1},
 {n:3,t:"上下文工程与压缩",d:"本仓库核心：折叠、缓存稳定、CCR/crush、身份对账。",ready:1},
 {n:4,t:"记忆与恢复",d:"会话持久化、崩溃恢复、长期记忆。",ready:1},
 {n:5,t:"评估",d:"不变量测试、契约测试、效果对照。",ready:1},
 {n:6,t:"成本与缓存经济",d:"前缀稳定、折叠收益门、定价影响。",ready:1},
 {n:7,t:"安全与多租户",d:"注入、凭据、隔离。",ready:1},
 {n:8,t:"LangGraph 视角",d:"状态图、持久化、HITL、多 Agent 聚合，以及与前七章的映射。",ready:1}];
var side=document.getElementById("side"),cur="home",curStep=0;
function el(t,c,h){var e=document.createElement(t);if(c)e.className=c;if(h!=null)e.innerHTML=h;return e}
function renderSide(){side.innerHTML="";
side.appendChild(el("div","brand","Agent 设计手册"));side.appendChild(el("div","bsub","专家面试 · 演进讲法"));
var h=el("button","it"+(cur==="home"?" on":""),'<span class="no">◎</span><span>总览</span>');h.onclick=function(){show("home")};side.appendChild(h);
side.appendChild(el("div","grp","章节"));
CHS.forEach(function(c){var b=el("button","it"+(cur===c.n?" on":"")+(c.ready?"":" dis"),'<span class="no">'+c.n+'</span><span>'+c.t+(c.ready?"":'<span class="pill">待写</span>')+'</span>');
if(c.ready)b.onclick=function(){show(c.n,0)};side.appendChild(b);
if(cur===c.n&&window.CHAPS&&window.CHAPS[c.n]){var sub=el("div","sub2");window.CHAPS[c.n].titles.forEach(function(t,i){var sb=el("button",i===curStep?"on":"",t);sb.onclick=function(){show(c.n,i)};sub.appendChild(sb)});side.appendChild(sub)}});
side.appendChild(el("div","grp","附录"));
side.appendChild(el("a","it",'上下文折叠手册（v1，可交互模拟器）↗')).href="https://claude.ai/artifact/BVwGBV7dZVv3A89NpTi2t6";
side.lastChild.target="_blank";side.lastChild.rel="noopener noreferrer";
}
function setHash(h){try{history.replaceState(null,"","#"+h)}catch(e){}}
function closeSide(){side.classList.remove("open");document.getElementById("scrim").classList.remove("on");document.getElementById("menu").setAttribute("aria-expanded","false")}
function show(v,step){var fromSide=side.contains(document.activeElement);cur=v;curStep=step||0;
document.querySelectorAll(".chap").forEach(function(c){c.hidden=c.id!=="chap-"+v});
if(v!=="home"&&window.CHAPS&&window.CHAPS[v])window.CHAPS[v].set(curStep);
renderSide();closeSide();if(fromSide){var a=side.querySelector(".sub2 button.on")||side.querySelector("button.it.on");if(a)a.focus()}
var c=CHS.filter(function(x){return x.n===v})[0];document.getElementById("tbt").textContent=c?c.t:"Agent 设计手册";
setHash(v==="home"?"home":"ch"+v+"-s"+curStep);
window.scrollTo(0,0)}
document.addEventListener("chstep",function(e){if(e.detail.n===cur&&e.detail.i!==curStep){curStep=e.detail.i;var fs=side.contains(document.activeElement);renderSide();if(fs){var b=side.querySelector(".sub2 button.on");if(b)b.focus()}setHash("ch"+cur+"-s"+curStep)}});
var cards=document.getElementById("cards");
CHS.forEach(function(c){var b=el("button","card"+(c.ready?"":" dis"),'<span class="no">CH '+c.n+'</span><span class="pill'+(c.ready?' ok':'')+'">'+(c.ready?"已完成":"待写")+'</span><h3>'+c.t+'</h3><p>'+c.d+'</p>');if(c.ready)b.onclick=function(){show(c.n,0)};cards.appendChild(b)});
document.getElementById("menu").onclick=function(){var o=side.classList.toggle("open");document.getElementById("scrim").classList.toggle("on",o);this.setAttribute("aria-expanded",o)};
document.getElementById("scrim").onclick=closeSide;
document.addEventListener("keydown",function(e){if(e.key==="Escape"&&side.classList.contains("open"))closeSide()});
function route(){var m=/^#ch(\\d+)(?:-s(\\d+))?$/.exec(location.hash||"");
if(m&&CHS[+m[1]-1]&&CHS[+m[1]-1].ready)show(+m[1],+(m[2]||0));else show("home")}
window.addEventListener("hashchange",route);route();
})();
</script>
'''%(css,NEWCSS,home,'\n'.join(chap_html),'\n'.join(chap_js))
open(D+'handbook.html','w',encoding='utf-8').write(shell)
print(len(shell))
