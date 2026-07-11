_NAV = r"""
<style>
  .nav-bar { background:#161b22; border-bottom:1px solid #30363d; padding:0 24px; display:flex; gap:0; }
  .nav-link { display:block; padding:9px 16px; font-size:13px; font-weight:600;
              text-decoration:none; color:#8b949e;
              border-bottom:2px solid transparent; transition:color .15s; }
  .nav-link:hover { color:#c9d1d9; }
  .nav-link.active { color:#58a6ff; border-bottom-color:#58a6ff; }
</style>
<nav class="nav-bar">
  <a id="nav-signals" class="nav-link" href="/">Market Vital Sign</a>
  <a id="nav-breadth" class="nav-link" href="/breadth">市场宽度</a>
</nav>
<script>
  (function(){
    var id = location.pathname.startsWith("/breadth") ? "nav-breadth" : "nav-signals";
    document.getElementById(id).classList.add("active");
  })();
</script>
"""

# ── HTML: signals page ────────────────────────────────────────────────────────
# Action-first signals dashboard.  Kept next to the breadth page so the
# display-only server can continue importing one dependency-free module.
SIGNALS_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Market Vital Sign · 决策台</title>
  <style>
    :root { color-scheme:dark; --bg:#090d13; --panel:#111821; --line:#263140;
      --muted:#8b98a9; --text:#eef3f8; --blue:#5ba7ff; --green:#41d17d;
      --red:#ff6574; --amber:#f5c451; }
    *,*::before,*::after { box-sizing:border-box; }
    body { margin:0; min-height:100vh; background:var(--bg); color:var(--text);
      font:13px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
    header { display:flex; align-items:center; justify-content:space-between; gap:18px;
      padding:18px max(18px,calc((100vw - 1320px)/2)); border-bottom:1px solid var(--line);
      background:#0d131b; }
    h1,h2,p { margin:0; } h1 { font-size:18px; } h2 { font-size:15px; }
    .eyebrow { color:var(--blue); font-size:10px; font-weight:800; letter-spacing:.16em;
      text-transform:uppercase; margin-bottom:3px; }
    .header-actions { display:flex; align-items:center; gap:12px; color:var(--muted); }
    button { border:1px solid #354458; background:#172130; color:var(--text); border-radius:7px;
      padding:7px 12px; font-weight:700; cursor:pointer; }
    button:disabled { opacity:.55; cursor:wait; }
    main { width:min(1320px,calc(100% - 32px)); margin:22px auto 48px; display:grid; gap:18px; }
    .hero { display:grid; grid-template-columns:minmax(0,2fr) minmax(250px,.8fr); gap:14px; }
    .action-panel,.phase-panel,.metric,.section,.radar { border:1px solid var(--line);
      background:linear-gradient(145deg,#131c27,#0e151e); border-radius:12px; }
    .action-panel { padding:24px; border-left:4px solid var(--blue); }
    .action-label,.metric-label,.micro-label { color:var(--muted); text-transform:uppercase;
      letter-spacing:.1em; font-size:10px; font-weight:800; }
    #currentAction { font-size:clamp(24px,4vw,42px); line-height:1.1; margin:8px 0 10px; }
    #actionBasis { color:#b6c2cf; max-width:760px; }
    .phase-panel { padding:20px; display:flex; flex-direction:column; justify-content:space-between; gap:18px; }
    .phase-row,.fresh-row,.section-head { display:flex; justify-content:space-between; align-items:center; gap:12px; }
    #marketPhase { font-size:22px; font-weight:800; }
    .badge { display:inline-flex; align-items:center; border:1px solid #43536a; border-radius:999px;
      padding:4px 9px; font-size:11px; font-weight:800; color:#c7d2df; }
    .badge.fresh { border-color:#267a4c; color:var(--green); background:#10291d; }
    .badge.stale { border-color:#926f19; color:var(--amber); background:#2a210c; }
    .badge.unavailable { border-color:#963b48; color:var(--red); background:#2a1218; }
    #dataTimestamp { color:var(--muted); font-variant-numeric:tabular-nums; font-size:11px; }
    .metrics { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }
    .metric { padding:16px; min-height:112px; }
    .metric-value { margin-top:8px; font-size:28px; font-weight:850; font-variant-numeric:tabular-nums; }
    .metric-note { margin-top:5px; color:var(--muted); font-size:11px; }
    .section { overflow:hidden; }
    .section-head { padding:16px 18px; border-bottom:1px solid var(--line); }
    .section-sub { color:var(--muted); font-size:11px; }
    #buyTargetMessage { padding:24px 18px; color:var(--muted); }
    .table-scroll { overflow-x: auto; -webkit-overflow-scrolling:touch; }
    table { width:100%; min-width:940px; border-collapse:collapse; font-variant-numeric:tabular-nums; }
    th,td { padding:11px 14px; border-bottom:1px solid #202a37; text-align:right; white-space:nowrap; }
    th { color:var(--muted); background:#0d141d; font-size:10px; text-transform:uppercase;
      letter-spacing:.06em; position:sticky; top:0; }
    th:nth-child(2),td:nth-child(2),th:nth-child(3),td:nth-child(3) { text-align:left; }
    tbody tr:hover { background:#151f2b; }
    .rank { color:var(--muted); font-weight:800; } .symbol { color:var(--blue); font-weight:850; font-size:14px; }
    .universe { color:#bac6d3; } .positive { color:var(--green); } .negative { color:var(--red); }
    .weight { color:var(--amber); font-weight:800; }
    .below { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
    .radar { padding:17px; }
    .radar p { margin-top:7px; color:#b4c0cd; }
    details { margin-top:12px; border-top:1px solid var(--line); padding-top:11px; color:var(--muted); }
    summary { color:#c8d3df; cursor:pointer; font-weight:700; }
    #qualityDisclosure { margin-top:8px; }
    @media (max-width:800px) {
      header { align-items:flex-start; padding:14px 16px; } .header-actions { flex-direction:column; align-items:flex-end; }
      main { width:min(100% - 20px,1320px); margin-top:12px; } .hero,.below { grid-template-columns:1fr; }
      .metrics { grid-template-columns:1fr 1fr; } .action-panel { padding:18px; }
      th,td { padding:10px 11px; }
      th:nth-child(n+4),td:nth-child(n+4) { font-size:11px; }
    }
    @media (max-width:440px) { .metrics { grid-template-columns:1fr 1fr; gap:8px; }
      .metric { min-height:96px; padding:13px; } .metric-value { font-size:22px; }
      #currentAction { font-size:26px; } }
    @media (max-width:640px) {
      #buyTargetTable { min-width:100%; }
      #buyTargetTable th:nth-child(3),#buyTargetTable td:nth-child(3),
      #buyTargetTable th:nth-child(4),#buyTargetTable td:nth-child(4),
      #buyTargetTable th:nth-child(6),#buyTargetTable td:nth-child(6),
      #buyTargetTable th:nth-child(7),#buyTargetTable td:nth-child(7),
      #buyTargetTable th:nth-child(8),#buyTargetTable td:nth-child(8) { display:none; }
      #buyTargetTable th:nth-child(1),#buyTargetTable td:nth-child(1),
      #buyTargetTable th:nth-child(2),#buyTargetTable td:nth-child(2),
      #buyTargetTable th:nth-child(5),#buyTargetTable td:nth-child(5) { display:table-cell; }
    }
  </style>
</head>
<body>
<header>
  <div><div class="eyebrow">15 Minute Snapshot</div><h1>Market Vital Sign 决策台</h1></div>
  <div class="header-actions"><span id="dataTimestamp">数据时间 —</span><button id="runBtn" type="button">刷新快照</button></div>
</header>
""" + _NAV + r"""
<main id="dashboard" aria-busy="false">
  <section class="hero" aria-labelledby="currentAction">
    <div class="action-panel" role="status" aria-live="polite"><div class="action-label">当前行动</div><h2 id="currentAction">正在加载</h2>
      <p id="actionBasis">正在读取最新预计算快照。</p></div>
    <div class="phase-panel"><div><div class="micro-label">市场阶段</div><div class="phase-row">
      <span id="marketPhase">—</span><span class="badge" id="phaseBadge">等待</span></div></div>
      <div class="fresh-row"><span class="micro-label">快照状态</span><span class="badge" id="freshnessBadge" role="status" aria-live="polite">加载中</span></div></div>
  </section>
  <section class="metrics" aria-label="市场关键指标">
    <article class="metric"><div class="metric-label">Strong</div><div class="metric-value positive" id="strongValue">—</div><div class="metric-note">强势股占比</div></article>
    <article class="metric"><div class="metric-label">Breakdown</div><div class="metric-value negative" id="breakdownValue">—</div><div class="metric-note">破位股占比</div></article>
    <article class="metric"><div class="metric-label">NTSS</div><div class="metric-value" id="ntssValue">—</div><div class="metric-note" id="ntssState">市场中轴</div></article>
    <article class="metric"><div class="metric-label">Momentum</div><div class="metric-value" id="momentumValue">—</div><div class="metric-note">净动量</div></article>
  </section>
  <section class="section" aria-labelledby="targetsTitle">
    <div class="section-head"><div><h2 id="targetsTitle">买入标的</h2><div class="section-sub">NASDAQ 100 与 S&amp;P 500 合并 · 默认按排名、市场、代码排序</div></div><span class="badge" id="targetCount" role="status" aria-live="polite">0 个</span></div>
    <p id="buyTargetMessage" role="status" aria-live="polite">正在加载买入标的…</p>
    <div class="table-scroll"><table id="buyTargetTable" aria-label="买入标的专业表格" hidden>
      <thead><tr><th scope="col">排名</th><th scope="col">标的</th><th scope="col">市场</th><th scope="col">MA200 距离</th>
        <th scope="col">目标权重</th><th scope="col">最新价</th><th scope="col">ADV 排名</th><th scope="col">数据时间</th></tr></thead>
      <tbody id="buyTargetBody"></tbody></table></div>
  </section>
  <section class="below">
    <article class="radar" id="shortRadar"><div class="micro-label">空头雷达</div><h2 id="shortRadarTitle">等待市场状态</h2><p id="shortRadarText">只有在市场阶段转弱时才评估对冲；本页不自动生成交易。</p></article>
    <article class="radar"><div class="micro-label">数据质量</div><h2>预计算快照</h2><p id="qualityDisclosure">正在检查覆盖率与新鲜度。</p>
      <details><summary>方法说明</summary><p>候选股先按 63 日平均成交额筛选，再在流动性池中按距离 MA200 排名；目标权重为 60% / 20% / 20%。指标缺失时显示“—”，不会用旧值补齐。</p></details></article>
  </section>
</main>
<script>
  const F1 = new Intl.NumberFormat("zh-CN",{minimumFractionDigits:1,maximumFractionDigits:1});
  const F2 = new Intl.NumberFormat("zh-CN",{minimumFractionDigits:2,maximumFractionDigits:2});
  function finite(value){ return typeof value === "number" && Number.isFinite(value); }
  function valueFrom(status,names){ for(const name of names){ if(finite(status[name])) return status[name]; } return null; }
  function setText(id,value){ document.getElementById(id).textContent=String(value); }
  function setDashboardBusy(busy){ document.getElementById("dashboard").setAttribute("aria-busy",busy?"true":"false"); }
  function cell(value,className){ const td=document.createElement("td"); td.textContent=String(value); if(className) td.className=className; return td; }
  function universeName(value){ return value === "nasdaq100" ? "NASDAQ 100" : value === "sp500" ? "S&P 500" : "—"; }
  function targetRow(target){
    const tr=document.createElement("tr");
    const distance=finite(target.distance_pct)?F1.format(target.distance_pct)+"%":"—";
    const price=finite(target.close)?"$"+F2.format(target.close):"—";
    const adv=Number.isInteger(target.adv_rank)?"#"+target.adv_rank:"—";
    const weight=finite(target.target_weight_pct)?F1.format(target.target_weight_pct)+"%":"—";
    tr.append(cell(target.rank,"rank"),cell(target.symbol,"symbol"),cell(universeName(target.universe),"universe"),
      cell(distance,finite(target.distance_pct)?(target.distance_pct>=0?"positive":"negative"):""),cell(weight,"weight"),
      cell(price),cell(adv),cell(target.last_date||"—"));
    return tr;
  }
  function sortedTargets(targets){ return [...targets].sort((a,b)=>a.rank-b.rank || a.universe.localeCompare(b.universe) || a.symbol.localeCompare(b.symbol)); }
  function renderTargets(data){
    const rows=sortedTargets(Array.isArray(data.buy_targets)?data.buy_targets:[]);
    const table=document.getElementById("buyTargetTable"), message=document.getElementById("buyTargetMessage");
    document.getElementById("buyTargetBody").replaceChildren(...rows.map(targetRow));
    message.setAttribute("role","status");
    setText("targetCount",rows.length+" 个"); table.hidden=rows.length===0; message.hidden=rows.length>0;
    if(!rows.length) message.textContent="当前快照没有可执行买入标的。";
  }
  function renderStatus(data){
    const status=data.market_status||{}, phase=String(status.phase_code||status.phase||"—");
    const strong=finite(status.strong)?status.strong:valueFrom(status,["s"]);
    const breakdown=finite(status.breakdown)?status.breakdown:valueFrom(status,["bd"]);
    const ntss=finite(status.ntss)?status.ntss:valueFrom(status,["mid"]);
    const momentum=finite(status.momentum)?status.momentum:valueFrom(status,["mom"]);
    setText("marketPhase",phase==="—"?"—":phase+" "+(status.phase||"")); setText("phaseBadge",status.label||"未知");
    setText("strongValue",strong===null?"—":F1.format(strong)+"%"); setText("breakdownValue",breakdown===null?"—":F1.format(breakdown)+"%");
    setText("ntssValue",ntss===null?"—":F2.format(ntss)); setText("momentumValue",momentum===null?"—":F2.format(momentum));
    setText("ntssState",status.ntss_state||"市场中轴");
    setText("currentAction",status.label||"等待市场确认"); setText("actionBasis",status.action||status.basis||"依据最新市场阶段与预计算候选股执行。");
    const riskOff=status.signal==="short";
    const trailWatch=status.signal==="short_watch";
    const radarKind=status.short_type?status.short_type+" · ":"";
    setText("shortRadarTitle",riskOff||trailWatch?radarKind+(status.label||"空头雷达"):(status.label||"观察")+" · 空头雷达关闭");
    setText("shortRadarText",status.action||"等待生产者发布最新市场行动。");
  }
  function renderQuality(data){
    const quality=data.quality||{}, badge=document.getElementById("freshnessBadge");
    badge.className="badge "+(data.stale?"stale":"fresh"); badge.textContent=data.stale?"数据已过期":"数据正常";
    setText("dataTimestamp","数据时间 "+String(data.generated_at||"—").replace("T"," "));
    const parts=[]; ["nasdaq100","sp500"].forEach(key=>{ const q=quality[key]; if(!q) return;
      const market=universeName(key); if(finite(q.valid_count)) parts.push(market+" 有效 "+q.valid_count);
      if(finite(q.failed_count)) parts.push(market+" 失败 "+q.failed_count);
      if(q.universe_source) parts.push(market+" 来源 "+q.universe_source);
      if(q.universe_warning) parts.push(market+" 警告 "+q.universe_warning);
      if(q.universe_error) parts.push(market+" 错误 "+q.universe_error);
      const candidateCount=Array.isArray(data.buy_targets)?data.buy_targets.filter(target=>target.universe===key).length:0;
      if(candidateCount<3) parts.push(market+" 候选不足 "+candidateCount+"/3");
    });
    if(quality.session_status) parts.push(quality.session_status==="open"?"交易时段":"非交易时段");
    if(data.stale) parts.push("页面继续展示上次成功快照");
    setText("qualityDisclosure",parts.length?parts.join(" · "):"覆盖率未提供；页面仅展示已验证快照字段。");
  }
  function setUnavailable(message){
    setText("currentAction","暂缓交易"); setText("actionBasis","快照不可用："+message); setText("marketPhase","—");
    setText("phaseBadge","未知"); setText("dataTimestamp","数据时间 —"); setText("targetCount","0 个");
    const badge=document.getElementById("freshnessBadge"); badge.className="badge unavailable"; badge.textContent="不可用";
    ["strongValue","breakdownValue","ntssValue","momentumValue"].forEach(id=>setText(id,"—"));
    setText("ntssState","—");
    const table=document.getElementById("buyTargetTable"); table.hidden=true; const msg=document.getElementById("buyTargetMessage"); msg.hidden=false; msg.textContent="无法读取买入标的。"; msg.setAttribute("role","alert");
    setText("shortRadarTitle","等待有效快照"); setText("shortRadarText","当前不提供空头判断，请等待下一次成功发布。");
    setText("qualityDisclosure","请等待下一次预计算任务成功发布；服务会保留最后一次有效快照。 ");
    setDashboardBusy(false);
  }
  function setLoading(){
    setText("currentAction","正在加载"); setText("actionBasis","正在读取最新预计算快照。"); setText("marketPhase","—");
    setText("phaseBadge","等待"); setText("dataTimestamp","数据时间 —"); setText("targetCount","0 个");
    const badge=document.getElementById("freshnessBadge"); badge.className="badge"; badge.textContent="加载中";
    ["strongValue","breakdownValue","ntssValue","momentumValue"].forEach(id=>setText(id,"—"));
    setText("ntssState","等待");
    document.getElementById("buyTargetBody").replaceChildren(); document.getElementById("buyTargetTable").hidden=true;
    const message=document.getElementById("buyTargetMessage"); message.hidden=false; message.textContent="正在加载买入标的…"; message.setAttribute("role","status");
    setText("shortRadarTitle","正在加载市场风险"); setText("shortRadarText","正在读取 Breakdown、NTSS 与市场阶段。");
    setText("qualityDisclosure","正在检查覆盖率与新鲜度。");
    setDashboardBusy(true);
  }
  async function runSignal(){
    const button=document.getElementById("runBtn"); button.disabled=true; setLoading();
    try { const response=await fetch("/api/signals"); const data=await response.json(); if(!response.ok) throw new Error(data.error||"请求失败");
      renderStatus(data); renderQuality(data); renderTargets(data); setDashboardBusy(false);
    } catch(error) { setUnavailable(error instanceof Error?error.message:"未知错误"); }
    finally { button.disabled=false; }
  }
  document.getElementById("runBtn").addEventListener("click",runSignal); runSignal();
</script>
</body></html>
"""

# ── HTML: breadth page ────────────────────────────────────────────────────────
BREADTH_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Market Vital Sign · 15 分钟盘中雷达</title>
  <style>
    :root{color-scheme:dark;--bg:#090d13;--panel:#111821;--line:#263140;--muted:#8b98a9;
      --text:#eef3f8;--blue:#5ba7ff;--green:#41d17d;--red:#ff6574;--amber:#f5c451}
    *,*::before,*::after{box-sizing:border-box}body{margin:0;min-height:100vh;background:var(--bg);
      color:var(--text);font:13px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
    header{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:17px max(16px,calc((100vw - 1180px)/2));
      border-bottom:1px solid var(--line);background:#0d131b}h1,h2,p{margin:0}h1{font-size:18px}.eyebrow,.label{
      color:var(--muted);font-size:10px;font-weight:800;letter-spacing:.12em;text-transform:uppercase}
    .eyebrow{color:var(--blue)}button{border:1px solid #354458;background:#172130;color:var(--text);border-radius:7px;
      padding:7px 12px;font-weight:700;cursor:pointer}button:disabled{opacity:.55;cursor:wait}
    main{width:min(1180px,calc(100% - 28px));margin:20px auto 45px;display:grid;gap:15px}
    .hero,.metric,.panel{border:1px solid var(--line);background:linear-gradient(145deg,#131c27,#0e151e);border-radius:12px}
    .hero{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(260px,.7fr);overflow:hidden}.hero-main{padding:22px;border-left:4px solid var(--blue)}
    #breadthAction{font-size:clamp(22px,3.7vw,38px);margin:7px 0}.hero-side{padding:19px;border-left:1px solid var(--line);display:grid;gap:13px}
    .row{display:flex;justify-content:space-between;align-items:center;gap:12px}.badge{display:inline-flex;border:1px solid #43536a;
      border-radius:999px;padding:4px 9px;font-size:11px;font-weight:800}.fresh{color:var(--green);border-color:#267a4c;background:#10291d}
    .stale{color:var(--amber);border-color:#926f19;background:#2a210c}.unavailable{color:var(--red);border-color:#963b48;background:#2a1218}
    #breadthPhase{font-size:22px;font-weight:850}.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.metric{padding:17px}.value{font-size:30px;
      font-weight:850;font-variant-numeric:tabular-nums;margin-top:7px}.delta{font-size:11px;color:var(--muted);margin-top:5px}.positive{color:var(--green)}.negative{color:var(--red)}
    .panel{padding:18px}.panel-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:13px}.sub{font-size:11px;color:var(--muted)}
    #intradayChart{width:100%;height:auto;min-height:230px;background:#0b1119;border-radius:8px;border:1px solid #202a37}.legend{display:flex;gap:15px;color:var(--muted);font-size:11px}
    .dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px}.transition{border-left:3px solid var(--amber);padding:12px 14px;background:#141b24;border-radius:6px}
    details{border:1px solid var(--line);border-radius:10px;background:#0e151e}summary{cursor:pointer;padding:15px 17px;font-weight:800}.research{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:var(--line);border-top:1px solid var(--line)}
    .research>div{background:#111821;padding:15px}.research .value{font-size:22px}#qualityDetails{padding:14px 17px;color:var(--muted);border-top:1px solid var(--line)}
    .visually-hidden{position:absolute!important;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
    @media(max-width:720px){header{align-items:flex-start}.hero{grid-template-columns:1fr}.hero-side{border-left:0;border-top:1px solid var(--line)}.metrics{grid-template-columns:1fr}.research{grid-template-columns:1fr 1fr}.panel{padding:12px}}
  </style>
</head><body>
<header><div><div class="eyebrow">Intraday Radar</div><h1>15 分钟市场宽度</h1></div><button id="refreshBtn" type="button">刷新快照</button></header>
""" + _NAV + r"""
<main id="breadthDashboard" aria-busy="true">
  <section class="hero"><div class="hero-main" role="status" aria-live="polite"><div class="label">当前行动</div><h2 id="breadthAction">正在加载</h2><p class="sub" id="latestBar">正在读取预计算快照。</p></div>
    <div class="hero-side"><div><div class="label">当前阶段</div><div class="row"><span id="breadthPhase">—</span><span class="badge" id="phaseBadge">等待</span></div></div>
      <div class="row"><span class="label">快照状态</span><span class="badge" id="breadthFreshness" role="status" aria-live="polite">加载中</span></div>
      <div class="sub" id="breadthTimestamp">数据时间 —</div></div></section>
  <section class="metrics" aria-label="盘中核心指标">
    <article class="metric"><div class="label">Strong</div><div class="value positive" id="strongValue">—</div><div class="delta" id="strongDelta">—</div></article>
    <article class="metric"><div class="label">Breakdown</div><div class="value negative" id="breakdownValue">—</div><div class="delta" id="breakdownDelta">—</div></article>
    <article class="metric"><div class="label">NTSS</div><div class="value" id="ntssValue">—</div><div class="delta" id="ntssDelta">—</div></article>
  </section>
  <section class="panel"><div class="panel-head"><div><h2>今日轨迹</h2><div class="sub">仅绘制当前交易日的 15 分钟聚合记录</div></div><div class="legend"><span><i class="dot" style="background:var(--green)"></i>Strong</span><span><i class="dot" style="background:var(--red)"></i>Breakdown</span></div></div>
    <svg id="intradayChart" viewBox="0 0 900 260" role="img" aria-labelledby="chartTitle chartDescription"></svg><p id="chartEmpty" class="sub" hidden>当前交易日暂无足够记录。</p></section>
  <section class="transition"><div class="label">最近阶段切换</div><strong id="latestTransition">暂无阶段切换记录</strong></section>
  <details><summary>研究详情</summary><div class="research">
    <div><div class="label">MA20 宽度</div><div class="value" id="ma20Value">—</div></div><div><div class="label">MA50 宽度</div><div class="value" id="ma50Value">—</div></div>
    <div><div class="label">MA200 宽度</div><div class="value" id="ma200Value">—</div></div><div><div class="label">Momentum</div><div class="value" id="momentumValue">—</div></div></div>
    <p id="qualityDetails">正在检查覆盖率和有效成分股数。</p><p id="seriesSummary" class="visually-hidden">今日轨迹尚未载入。</p></details>
</main>
<script>
const P1=new Intl.NumberFormat("zh-CN",{minimumFractionDigits:1,maximumFractionDigits:1});
const P2=new Intl.NumberFormat("zh-CN",{minimumFractionDigits:2,maximumFractionDigits:2});
function finite(v){return typeof v==="number"&&Number.isFinite(v)}
function text(id,v){document.getElementById(id).textContent=String(v)}
function busy(v){document.getElementById("breadthDashboard").setAttribute("aria-busy",v?"true":"false")}
function resetValues(emptyText){["strongValue","strongDelta","breakdownValue","breakdownDelta","ntssValue","ntssDelta","ma20Value","ma50Value","ma200Value","momentumValue"].forEach(id=>text(id,"—"));document.getElementById("intradayChart").replaceChildren();const empty=document.getElementById("chartEmpty");empty.hidden=false;empty.textContent=emptyText;text("seriesSummary",emptyText)}
function setLoading(){resetValues("正在加载今日轨迹。");text("breadthAction","正在加载");text("latestBar","正在读取预计算快照。");text("breadthPhase","—");text("phaseBadge","等待");text("breadthTimestamp","数据时间 —");text("latestTransition","暂无阶段切换记录");text("qualityDetails","正在检查覆盖率和有效成分股数。");const b=document.getElementById("breadthFreshness");b.className="badge";b.textContent="加载中";b.setAttribute("role","status");busy(true)}
function setUnavailable(message){resetValues("轨迹不可用。");text("breadthAction","暂缓判断："+message);text("latestBar","等待下一次成功发布。");text("breadthPhase","—");text("phaseBadge","未知");text("breadthTimestamp","数据时间 —");text("latestTransition","无可用阶段切换");text("qualityDetails","快照不可用，研究指标已清空。");const b=document.getElementById("breadthFreshness");b.className="badge unavailable";b.textContent="不可用";b.setAttribute("role","alert");busy(false)}
function phaseMeta(record){const code=String(record.phase_code||record.phase||"—"),label=record.phase_label||record.phase_name||"";return {code,label:label?code+" "+label:code,action:record.action||record.action_label||"等待生产端发布行动建议。"}}
function metric(value,previous,digits,suffix,elapsed){const val=finite(value)?(digits===2?P2:P1).format(value)+(suffix||""):"—";let delta="—";if(finite(value)&&finite(previous)&&finite(elapsed)&&elapsed>0&&elapsed<=180){const d=value-previous,mins=Math.round(elapsed);delta=(d>0?"+":d<0?"−":"")+(digits===2?P2:P1).format(Math.abs(d))+(suffix||"")+" vs "+mins+" 分钟前"}return [val,delta]}
function dayKey(t){const s=String(t||"");return s.includes("T")?s.split("T")[0]:s.split(" ")[0]}
function normalizeRecords(records){const unique=new Map();(Array.isArray(records)?records:[]).forEach(record=>{const ms=Date.parse(record&&record.t);if(Number.isFinite(ms))unique.set(ms,{...record,_ms:ms})});return [...unique.values()].sort((a,b)=>a._ms-b._ms)}
function svg(tag,attrs){const node=document.createElementNS("http://www.w3.org/2000/svg",tag);Object.entries(attrs||{}).forEach(([k,v])=>node.setAttribute(k,String(v)));return node}
function intradayRecords(records){const sorted=normalizeRecords(records);if(!sorted.length)return [];const latestDay=dayKey(sorted[sorted.length-1].t);return sorted.filter(r=>dayKey(r.t)===latestDay)}
function renderChart(records,transition){const chart=document.getElementById("intradayChart"),empty=document.getElementById("chartEmpty"),today=intradayRecords(records),recs=today.filter(r=>finite(r.s)&&finite(r.bd));chart.replaceChildren();empty.hidden=recs.length>=2;if(recs.length<2){empty.textContent="当前交易日有效轨迹点不足（需要 Strong 与 Breakdown 均有效的至少 2 个点）。";text("seriesSummary",empty.textContent);return}const first=recs[0],lastRec=recs[recs.length-1],strong=recs.map(r=>r.s),breakdown=recs.map(r=>r.bd),date=dayKey(lastRec.t);const title=svg("title",{id:"chartTitle"});title.textContent=date+" 市场宽度轨迹";const desc=svg("desc",{id:"chartDescription"});desc.textContent=recs.length+" 个有效点；Strong "+P1.format(first.s)+"% 到 "+P1.format(lastRec.s)+"%，范围 "+P1.format(Math.min(...strong))+"%–"+P1.format(Math.max(...strong))+"%；Breakdown "+P1.format(first.bd)+"% 到 "+P1.format(lastRec.bd)+"%，范围 "+P1.format(Math.min(...breakdown))+"%–"+P1.format(Math.max(...breakdown))+"%。";chart.appendChild(title);chart.appendChild(desc);text("seriesSummary","今日 "+date+"，共 "+recs.length+" 个有效点。Strong "+P1.format(first.s)+"% → "+P1.format(lastRec.s)+"%；Breakdown "+P1.format(first.bd)+"% → "+P1.format(lastRec.bd)+"%。");const left=45,right=875,top=18,bottom=225,x=i=>left+(right-left)*i/(recs.length-1),y=v=>bottom-(bottom-top)*Math.max(0,Math.min(100,v))/100;
  [0,25,50,75,100].forEach(v=>{chart.appendChild(svg("line",{x1:left,y1:y(v),x2:right,y2:y(v),stroke:"#263140"}));const l=svg("text",{x:8,y:y(v)+4,fill:"#8b98a9","font-size":10});l.textContent=v+"%";chart.appendChild(l)});
  [["s","#41d17d"],["bd","#ff6574"]].forEach(([key,color])=>{const points=recs.map((r,i)=>x(i)+","+y(r[key])).join(" ");chart.appendChild(svg("polyline",{points,fill:"none",stroke:color,"stroke-width":3,"stroke-linejoin":"round"}));const last=recs.length-1;chart.appendChild(svg("circle",{cx:x(last),cy:y(recs[last][key]),r:4,fill:color}))});
  if(transition){const i=recs.findIndex(r=>String(r.t)===String(transition.at));if(i>=0){chart.appendChild(svg("line",{x1:x(i),y1:top,x2:x(i),y2:bottom,stroke:"#f5c451","stroke-dasharray":"4 4"}));const note=svg("text",{x:Math.min(x(i)+6,right-85),y:top+13,fill:"#f5c451","font-size":11});note.textContent=String(transition.to||"—")+(transition.to_label?" "+transition.to_label:"");chart.appendChild(note)}}
}
function qualityText(data,cur){const q=data.quality||{},parts=[];if(finite(q.valid_count))parts.push("有效 "+q.valid_count);if(finite(q.failed_count))parts.push("失败 "+q.failed_count);[["MA20","a20_n", "valid_20_n"],["MA50","a50_n","valid_50_n"],["MA200","a200_n","valid_200_n"]].forEach(([name,a,b])=>{const n=finite(cur[a])?cur[a]:cur[b];if(finite(n))parts.push(name+" 有效 "+n)});if(q.session_status)parts.push(q.session_status==="open"?"交易时段":"市场已收盘");if(data.stale)parts.push("继续展示上次成功快照");return parts.length?parts.join(" · "):"覆盖率未提供。"}
function renderBreadth(data){const all=normalizeRecords(data.records),recs=intradayRecords(all);if(!recs.length){setUnavailable("当前交易日暂无记录");return}const cur=recs[recs.length-1],complete=recs.filter(r=>finite(r.s)&&finite(r.bd)),curComplete=finite(cur.s)&&finite(cur.bd),prev=curComplete?complete[complete.length-2]||null:null,elapsed=prev?(cur._ms-prev._ms)/60000:null,phase=phaseMeta(cur);text("breadthPhase",phase.label);text("phaseBadge",phase.code);text("breadthAction",phase.action);text("latestBar","最新记录 "+String(cur.t||"—"));text("breadthTimestamp","数据时间 "+String(data.generated_at||"—").replace("T"," "));
  [["strongValue","strongDelta",cur.s,prev&&prev.s,1,"%"],["breakdownValue","breakdownDelta",cur.bd,prev&&prev.bd,1,"%"],["ntssValue","ntssDelta",cur.mid,prev&&prev.mid,2,""]].forEach(v=>{const out=metric(v[2],v[3],v[4],v[5],elapsed);text(v[0],out[0]);text(v[1],out[1])});
  [["ma20Value",cur.a20,1,"%"],["ma50Value",cur.a50,1,"%"],["ma200Value",cur.a200,1,"%"],["momentumValue",cur.mom,2,""]].forEach(v=>text(v[0],finite(v[1])?(v[2]===2?P2:P1).format(v[1])+v[3]:"—"));
  const tr=data.latest_transition,from=tr?String(tr.from||"—")+(tr.from_label?" "+tr.from_label:""):"",to=tr?String(tr.to||"—")+(tr.to_label?" "+tr.to_label:""):"";text("latestTransition",tr?from+" → "+to+" · "+String(tr.at||"—").replace("T"," "):"暂无阶段切换记录");renderChart(all,tr);text("qualityDetails",qualityText(data,cur));const b=document.getElementById("breadthFreshness");b.className="badge "+(data.stale?"stale":"fresh");b.textContent=data.stale?"数据已过期":((data.quality||{}).session_status==="closed"?"市场已收盘":"数据正常");b.setAttribute("role","status");busy(false)}
async function loadBreadth(){const button=document.getElementById("refreshBtn");button.disabled=true;setLoading();try{const response=await fetch("/api/breadth");const data=await response.json();if(!response.ok)throw new Error(data.error||"请求失败");renderBreadth(data)}catch(error){setUnavailable(error instanceof Error?error.message:"未知错误")}finally{button.disabled=false}}
document.getElementById("refreshBtn").addEventListener("click",loadBreadth);loadBreadth();
</script></body></html>
"""
