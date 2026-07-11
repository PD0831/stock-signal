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
<main>
  <section class="hero" aria-labelledby="currentAction">
    <div class="action-panel"><div class="action-label">当前行动</div><h2 id="currentAction">正在加载</h2>
      <p id="actionBasis">正在读取最新预计算快照。</p></div>
    <div class="phase-panel"><div><div class="micro-label">市场阶段</div><div class="phase-row">
      <span id="marketPhase">—</span><span class="badge" id="phaseBadge">等待</span></div></div>
      <div class="fresh-row"><span class="micro-label">快照状态</span><span class="badge" id="freshnessBadge">加载中</span></div></div>
  </section>
  <section class="metrics" aria-label="市场关键指标">
    <article class="metric"><div class="metric-label">Strong</div><div class="metric-value positive" id="strongValue">—</div><div class="metric-note">强势股占比</div></article>
    <article class="metric"><div class="metric-label">Breakdown</div><div class="metric-value negative" id="breakdownValue">—</div><div class="metric-note">破位股占比</div></article>
    <article class="metric"><div class="metric-label">NTSS</div><div class="metric-value" id="ntssValue">—</div><div class="metric-note" id="ntssState">市场中轴</div></article>
    <article class="metric"><div class="metric-label">Momentum</div><div class="metric-value" id="momentumValue">—</div><div class="metric-note">净动量</div></article>
  </section>
  <section class="section" aria-labelledby="targetsTitle">
    <div class="section-head"><div><h2 id="targetsTitle">买入标的</h2><div class="section-sub">NASDAQ 100 与 S&amp;P 500 合并 · 默认按排名、市场、代码排序</div></div><span class="badge" id="targetCount">0 个</span></div>
    <p id="buyTargetMessage">正在加载买入标的…</p>
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
    const riskOff=(phase==="G"||phase==="H"||(ntss!==null&&ntss<0));
    const trailWatch=!riskOff&&breakdown!==null&&breakdown>=35;
    setText("shortRadarTitle",riskOff?"Risk Off · 空头保险":trailWatch?"Trail Exhaustion · 空头雷达":"当前无需主动做空");
    setText("shortRadarText",riskOff?"风险条件已激活，优先控制总仓位并评估对冲。":trailWatch?"Breakdown 已达到观察阈值，等待空头确认。":"继续监测阶段切换；仅在转弱确认后评估对冲。");
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
    const table=document.getElementById("buyTargetTable"); table.hidden=true; const msg=document.getElementById("buyTargetMessage"); msg.hidden=false; msg.textContent="无法读取买入标的。";
    setText("shortRadarTitle","等待有效快照"); setText("shortRadarText","当前不提供空头判断，请等待下一次成功发布。");
    setText("qualityDisclosure","请等待下一次预计算任务成功发布；服务会保留最后一次有效快照。 ");
  }
  function setLoading(){
    setText("currentAction","正在加载"); setText("actionBasis","正在读取最新预计算快照。"); setText("marketPhase","—");
    setText("phaseBadge","等待"); setText("dataTimestamp","数据时间 —"); setText("targetCount","0 个");
    const badge=document.getElementById("freshnessBadge"); badge.className="badge"; badge.textContent="加载中";
    ["strongValue","breakdownValue","ntssValue","momentumValue"].forEach(id=>setText(id,"—"));
    document.getElementById("buyTargetBody").replaceChildren(); document.getElementById("buyTargetTable").hidden=true;
    const message=document.getElementById("buyTargetMessage"); message.hidden=false; message.textContent="正在加载买入标的…";
    setText("shortRadarTitle","正在加载市场风险"); setText("shortRadarText","正在读取 Breakdown、NTSS 与市场阶段。");
    setText("qualityDisclosure","正在检查覆盖率与新鲜度。");
  }
  async function runSignal(){
    const button=document.getElementById("runBtn"); button.disabled=true; setLoading();
    try { const response=await fetch("/api/signals"); const data=await response.json(); if(!response.ok) throw new Error(data.error||"请求失败");
      renderStatus(data); renderQuality(data); renderTargets(data);
    } catch(error) { setUnavailable(error instanceof Error?error.message:"未知错误"); }
    finally { button.disabled=false; }
  }
  document.getElementById("runBtn").addEventListener("click",runSignal); runSignal();
</script>
</body></html>
"""

# ── HTML: breadth page ────────────────────────────────────────────────────────
BREADTH_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Market Vital Sign — Breadth Monitor</title>
  <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
  <style>
    *, *::before, *::after { box-sizing:border-box; margin:0; padding:0; }
    body { background:#0d1117; color:#e6edf3;
           font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
           font-size:13px; min-height:100vh; }
    header { background:#161b22; border-bottom:1px solid #30363d;
             padding:10px 20px; display:flex; align-items:center; gap:12px; flex-wrap:wrap; }
    header h1 { font-size:15px; font-weight:600; color:#58a6ff; }
    .header-meta { font-size:11px; color:#8b949e; margin-left:auto; }
    #refreshBtn { background:#21262d; border:1px solid #30363d; color:#c9d1d9;
                  border-radius:6px; padding:4px 12px; font-size:12px; cursor:pointer; }
    #refreshBtn:hover { background:#30363d; }
    .status-bar { display:flex; gap:10px; padding:10px 16px; background:#161b22;
                  border-bottom:1px solid #30363d; flex-wrap:wrap; align-items:center; }
    .card { background:#21262d; border:1px solid #30363d; border-radius:8px;
            padding:7px 14px; min-width:105px; text-align:center; }
    .card .lbl { font-size:10px; color:#8b949e; margin-bottom:2px;
                 text-transform:uppercase; letter-spacing:.4px; }
    .card .val { font-size:20px; font-weight:700; font-variant-numeric:tabular-nums; }
    .card .dlt { font-size:10px; margin-top:2px; }
    .green{color:#3fb950} .red{color:#f85149} .yellow{color:#d29922}
    .blue{color:#58a6ff}  .gray{color:#8b949e}
    .badge { border-radius:20px; padding:3px 12px; font-size:12px; font-weight:600;
             letter-spacing:.4px; white-space:nowrap; }
    .safe    { background:#1a3a1a; color:#3fb950; border:1px solid #3fb950; }
    .caution { background:#2d2200; color:#d29922; border:1px solid #d29922; }
    .panic   { background:#3a1a1a; color:#f85149; border:1px solid #f85149; }
    .allow   { background:#1a3a1a; color:#3fb950; border:1px solid #3fb950; }
    .wait    { background:#21262d; color:#8b949e; border:1px solid #30363d; }
    .controls { display:flex; gap:8px; padding:8px 16px; border-bottom:1px solid #21262d;
                align-items:center; flex-wrap:wrap; }
    .lbl-sm { color:#8b949e; font-size:11px; }
    .btn-grp { display:flex; gap:3px; }
    .btn { background:#21262d; border:1px solid #30363d; color:#c9d1d9;
           border-radius:5px; padding:4px 10px; font-size:11px; cursor:pointer; }
    .btn:hover { background:#30363d; }
    .btn.active { background:#1f6feb; border-color:#388bfd; color:#fff; }
    #chartWrap { padding:4px 8px 12px; }
    #loadMsg { display:flex; flex-direction:column; align-items:center;
               justify-content:center; min-height:60vh; gap:16px;
               color:#8b949e; text-align:center; }
    #loadMsg h2 { color:#58a6ff; }
    .spinner { width:40px; height:40px; border:3px solid #30363d;
               border-top-color:#58a6ff; border-radius:50%;
               animation:spin 0.8s linear infinite; }
    @keyframes spin { to { transform:rotate(360deg); } }
  </style>
</head>
<body>
<header>
  <h1>Market Vital Sign — Breadth Monitor</h1>
  <span style="font-size:11px;color:#8b949e">S&amp;P 500 · Hourly · yfinance</span>
  <div class="header-meta">
    Generated: <span id="genTime">—</span> &nbsp;|&nbsp; <span id="nStocks">—</span> stocks
    &nbsp;&nbsp;
    <button id="refreshBtn" onclick="location.reload()">⟳ Refresh</button>
    <span id="autoReload" style="font-size:11px;color:#484f58;margin-left:8px"></span>
  </div>
</header>
""" + _NAV + r"""
<div class="status-bar" id="statusBar" style="display:none">
  <div class="card">
    <div class="lbl">Strong</div>
    <div class="val green" id="vS">—</div>
    <div class="dlt gray"  id="dS">—</div>
  </div>
  <div class="card">
    <div class="lbl">Breakdown</div>
    <div class="val" id="vBD">—</div>
    <div class="dlt gray" id="dBD">—</div>
  </div>
  <div class="card">
    <div class="lbl">NTSS</div>
    <div class="val blue" id="vMid">—</div>
    <div class="dlt gray" id="dMid">—</div>
  </div>
  <div class="card">
    <div class="lbl">Net Momentum</div>
    <div class="val" id="vMom">—</div>
    <div class="dlt gray" id="dMom">—</div>
  </div>
  <div style="margin-left:auto;display:flex;gap:10px;align-items:center;flex-wrap:wrap">
    <span class="lbl-sm">Phase</span>
    <span class="badge" id="phaseTag">—</span>
    <span class="lbl-sm" style="margin-left:4px">NTSS</span>
    <span class="badge" id="stateTag">—</span>
    <span class="badge" id="stageTag" style="display:none">—</span>
    <span class="lbl-sm" style="margin-left:4px">BL=35</span>
    <span class="badge" id="trigTag">—</span>
    <span style="font-size:10px;color:#484f58;margin-left:8px" id="lastBar">—</span>
  </div>
</div>

<div class="controls" id="ctrlBar" style="display:none">
  <span class="lbl-sm">Show last:</span>
  <div class="btn-grp" id="rangeGrp">
    <button class="btn" onclick="setRange(5)">5D</button>
    <button class="btn active" onclick="setRange(10)">10D</button>
    <button class="btn" onclick="setRange(20)">20D</button>
    <button class="btn" onclick="setRange(30)">30D</button>
    <button class="btn" onclick="setRange(0)">All</button>
  </div>
</div>

<div id="loadMsg">
  <div class="spinner"></div>
  <h2>Loading breadth data…</h2>
  <p id="loadDetail">Fetching from server…</p>
</div>

<div id="chartWrap" style="display:none">
  <div id="chartDiv"></div>
</div>

<script>
let DATA         = null;
let currentRange = 10;

const C = {
  strong:"#3fb950", breakdown:"#f85149",
  midPos:"#58a6ff", midNeg:"#f85149",
  momPos:"#3fb950", momNeg:"#f85149",
  ref:"rgba(139,148,158,0.35)", text:"#8b949e",
};

// ── Fetch with retry on 202 ───────────────────────────────────────────────────
async function loadData() {
  for (let attempt = 0; attempt < 60; attempt++) {
    try {
      const res = await fetch("/api/breadth");
      if (res.status === 202) {
        const j = await res.json();
        const detail = document.getElementById("loadDetail");
        if (j.status === "error") {
          detail.textContent = "Error: " + (j.error || j.message);
          detail.style.color = "#f85149";
        } else {
          detail.textContent = (j.message || "Computing…");
          detail.style.color = "";
        }
        await new Promise(r => setTimeout(r, 15000));
        continue;
      }
      if (!res.ok) throw new Error("HTTP " + res.status);
      DATA = await res.json();
      onDataReady();
      return;
    } catch(e) {
      document.getElementById("loadDetail").textContent = "Network error: " + e.message + " — retrying…";
      await new Promise(r => setTimeout(r, 15000));
    }
  }
  document.getElementById("loadDetail").textContent = "Timed out. Please refresh the page.";
}

function onDataReady() {
  document.getElementById("loadMsg").style.display   = "none";
  document.getElementById("chartWrap").style.display = "block";
  document.getElementById("statusBar").style.display = "flex";
  document.getElementById("ctrlBar").style.display   = "flex";
  document.getElementById("genTime").textContent = DATA.generated_at.replace("T"," ");
  document.getElementById("nStocks").textContent = DATA.n_stocks;
  updateStatus();
  render(currentRange);
  startAutoReload();
}

// ── Status cards ──────────────────────────────────────────────────────────────
function updateStatus() {
  const recs = DATA.records;
  const n    = recs.length - 1;
  if (n < 1) return;
  const daily = DATA.daily_close || {};
  const usingDaily = !!daily.current;
  const cur  = usingDaily ? daily.current : recs[n];
  const prev = usingDaily ? daily.previous : (DATA.previous_day_close || recs[n-1]);
  const deltaLabel = usingDaily ? " vs prior daily close" : (DATA.previous_day_close ? " vs prior day close" : " vs prev");
  const fmt  = (v, d) => v != null ? v.toFixed(d==null?1:d) : "—";
  const sgn  = v => v > 0 ? "+" : "";

  function card(valId, dltId, cv, pv, sfx, posGood) {
    const el = document.getElementById(valId);
    const dl = document.getElementById(dltId);
    const d  = (cv != null && pv != null) ? cv - pv : null;
    el.textContent = fmt(cv) + (sfx||"");
    if      (valId==="vS")   el.className = "val " + (cv >= 35 ? "green" : "red");
    else if (valId==="vBD")  el.className = "val " + (cv >= 50 ? "red" : cv >= 35 ? "yellow" : "green");
    else if (valId==="vMid") el.className = "val " + (cv==null?"gray": cv<0?"red": cv<2?"yellow":"blue");
    else if (valId==="vMom") el.className = "val " + (cv==null?"gray": cv>=0?"green":"red");
    dl.textContent = d!=null ? sgn(d)+fmt(d,2)+(sfx||"")+deltaLabel : "—";
    dl.className   = d!=null ? "dlt "+(posGood?(d>=0?"green":"red"):(d<=0?"green":"red")) : "dlt gray";
  }
  card("vS",  "dS",  cur.s,  prev.s,  "%", true);
  card("vBD", "dBD", cur.bd, prev.bd, "%", false);
  card("vMid","dMid",cur.mid,prev.mid,"",  true);
  card("vMom","dMom",cur.mom,prev.mom,"",  true);

  const st = document.getElementById("stateTag");
  if (cur.mid!=null) {
    if      (cur.mid<0) { st.textContent="PANIC";   st.className="badge panic"; }
    else if (cur.mid<2) { st.textContent="CAUTION"; st.className="badge caution"; }
    else                { st.textContent="SAFE";    st.className="badge safe"; }
  }
  const tr = document.getElementById("trigTag");
  const ok = cur.bd!=null && cur.bd<35;
  tr.textContent = ok ? "BL=35 ✓ ALLOW" : "BL=35 ✗ WAIT";
  tr.className   = "badge " + (ok ? "allow" : "wait");

  const lastBar = document.getElementById("lastBar");
  if (lastBar) {
    lastBar.textContent = usingDaily ? "Daily close: " + cur.t : "Last: " + cur.t + " ET";
  }

  // ── Market phase (Strong × BD) ───────────────────────────────────────────
  const ph = document.getElementById("phaseTag");
  if (ph && cur.s!=null && cur.bd!=null) {
    const s = cur.s, bd = cur.bd, mid = cur.mid;
    let phase, cls;
    if      (s>55 && bd<20)  { phase="A 全面牛市"; cls="safe"; }
    else if (s>40 && bd<30)  { phase="B 强势整固"; cls="safe"; }
    else if (s>35 && bd<45)  { phase="C 牛市回调"; cls="safe"; }
    else if (s>25 && bd<35)  { phase="D 修复中";   cls="safe"; }
    else if (s>20 && bd<50)  { phase="E 震荡整理"; cls="caution"; }
    else if (s<20 && bd<40)  { phase="F 弱势未崩"; cls="caution"; }
    else if (s<30 && bd>50)  { phase="G 宽度承压"; cls="panic"; }
    else                     { phase="H 恐慌出清"; cls="panic"; }
    ph.textContent = phase;
    ph.className   = "badge " + cls;
  }

  // ── NTSS recovery stage (only shown when in panic/bear phase) ────────────
  const sg = document.getElementById("stageTag");
  if (sg && cur.mid!=null) {
    const m = cur.mid, s = cur.s, bd = cur.bd;
    const inPanic = s < 20 && bd > 55;
    if (inPanic) {
      let stage, scls;
      if      (m < -3) { stage="① 极端恐慌";  scls="panic"; }
      else if (m < -1) { stage="② 恐慌中";    scls="panic"; }
      else if (m <  0) { stage="③ 临近0轴";   scls="caution"; }
      else if (m <  1) { stage="④ 刚穿零";    scls="caution"; }
      else if (m <  2) { stage="⑤ 弱确认";    scls="caution"; }
      else             { stage="⑥ 强确认 ★";  scls="safe"; }
      sg.textContent = stage;
      sg.className   = "badge " + scls;
      sg.style.display = "";
    } else {
      sg.style.display = "none";
    }
  }
}

// ── Data slice ────────────────────────────────────────────────────────────────
function sliceRecords(days) {
  const all = DATA.records;
  if (days === 0) return all;
  const dates = [...new Set(all.map(r => r.t.split(" ")[0]))].sort();
  const from  = days >= dates.length ? dates[0] : dates[dates.length - days];
  return all.filter(r => r.t.split(" ")[0] >= from);
}

// ── Buy period shapes ─────────────────────────────────────────────────────────
function buyPeriodShapes(recs) {
  const shapes = [];
  for (const pair of [[50,"rgba(63,185,80,0.07)"],[35,"rgba(63,185,80,0.18)"]]) {
    const limit = pair[0], color = pair[1];
    let start = null;
    for (let i = 0; i < recs.length; i++) {
      const active = recs[i].bd != null && recs[i].bd < limit;
      if (active && start === null) { start = recs[i].t; }
      else if (!active && start !== null) {
        shapes.push({type:"rect",xref:"x",yref:"paper",
          x0:start,x1:recs[i-1].t,y0:0,y1:1,
          fillcolor:color,line:{width:0},layer:"below"});
        start = null;
      }
    }
    if (start !== null)
      shapes.push({type:"rect",xref:"x",yref:"paper",
        x0:start,x1:recs[recs.length-1].t,y0:0,y1:1,
        fillcolor:color,line:{width:0},layer:"below"});
  }
  return shapes;
}

// ── Traces ────────────────────────────────────────────────────────────────────
function makeTraces(recs) {
  const T    = recs.map(r => r.t);
  const S    = recs.map(r => r.s);
  const BD   = recs.map(r => r.bd);
  const MID  = recs.map(r => r.mid);
  const MOM  = recs.map(r => r.mom);
  const A20  = recs.map(r => r.a20);
  const A50  = recs.map(r => r.a50);
  const A200 = recs.map(r => r.a200);
  const midColors = MID.map(v => v!=null && v<0 ? C.midNeg : C.midPos);
  const momColors = MOM.map(v => v!=null && v<0 ? C.momNeg : C.momPos);
  return [
    {x:T,y:S,  name:"Strong",      xaxis:"x",yaxis:"y",  type:"scatter",mode:"lines",
     line:{color:C.strong,width:2},fill:"tozeroy",fillcolor:"rgba(63,185,80,0.10)",
     hovertemplate:"<b>Strong</b>: %{y:.1f}%<extra></extra>"},
    {x:T,y:BD, name:"Breakdown",   xaxis:"x",yaxis:"y",  type:"scatter",mode:"lines",
     line:{color:C.breakdown,width:2,dash:"dot"},fill:"tozeroy",fillcolor:"rgba(248,81,73,0.08)",
     hovertemplate:"<b>Breakdown</b>: %{y:.1f}%<extra></extra>"},
    {x:T,y:A20,name:">20d MA",     xaxis:"x",yaxis:"y2", type:"scatter",mode:"lines",
     line:{color:"#f0a500",width:1.5},hovertemplate:"<b>>20d</b>: %{y:.1f}%<extra></extra>"},
    {x:T,y:A50,name:">50d MA",     xaxis:"x",yaxis:"y2", type:"scatter",mode:"lines",
     line:{color:"#58a6ff",width:1.5},hovertemplate:"<b>>50d</b>: %{y:.1f}%<extra></extra>"},
    {x:T,y:A200,name:">200d MA",   xaxis:"x",yaxis:"y2", type:"scatter",mode:"lines",
     line:{color:"#3fb950",width:1.5},hovertemplate:"<b>>200d</b>: %{y:.1f}%<extra></extra>"},
    {x:T,y:MID,name:"NTSS", xaxis:"x",yaxis:"y3", type:"bar",marker:{color:midColors},
     hovertemplate:"<b>3M-30D</b>: %{y:.2f}<extra></extra>"},
    {x:T,y:MOM,name:"Momentum",    xaxis:"x",yaxis:"y4", type:"bar",marker:{color:momColors},
     hovertemplate:"<b>Mom</b>: %{y:.2f}<extra></extra>"},
  ];
}

// ── Layout ────────────────────────────────────────────────────────────────────
function makeLayout(recs) {
  const grid = "#21262d";
  const rl   = (yr, y0) => ({type:"line",xref:"paper",yref:yr,x0:0,x1:1,y0,y1:y0,
                               line:{color:C.ref,width:1,dash:"dot"}});
  const shapes = [
    ...buyPeriodShapes(recs),
    rl("y",35),rl("y",50),rl("y2",35),rl("y2",50),
    rl("y3",2),rl("y3",1),
    {type:"line",xref:"paper",yref:"y3",x0:0,x1:1,y0:-1,y1:-1,line:{color:"rgba(248,81,73,0.35)",width:1,dash:"dot"}},
    {type:"line",xref:"paper",yref:"y3",x0:0,x1:1,y0:-3,y1:-3,line:{color:"rgba(248,81,73,0.6)",width:1,dash:"dot"}},
    {type:"line",xref:"paper",yref:"y3",x0:0,x1:1,y0:0,y1:0,line:{color:"rgba(139,148,158,0.6)",width:1.5}},
    rl("y4",5),rl("y4",-5),
    {type:"line",xref:"paper",yref:"y4",x0:0,x1:1,y0:0,y1:0,line:{color:"rgba(139,148,158,0.6)",width:1.5}},
  ];
  const lbl  = (yr, txt) => ({xref:"paper",yref:yr,x:0.01,y:1,text:"<b>"+txt+"</b>",
                               showarrow:false,font:{color:"#c9d1d9",size:10},
                               xanchor:"left",yanchor:"top"});
  const rlbl = (yr, y, txt) => ({xref:"paper",yref:yr,x:1.002,y,text:txt,
                                  showarrow:false,font:{color:C.ref,size:9},xanchor:"left"});
  return {
    paper_bgcolor:"#0d1117", plot_bgcolor:"#0d1117",
    font:{color:C.text,size:11},
    margin:{l:52,r:36,t:12,b:36},
    height:Math.max(window.innerHeight-230,480),
    showlegend:true,
    legend:{orientation:"h",x:0,y:-0.04,font:{size:10},bgcolor:"rgba(0,0,0,0)"},
    hovermode:"x unified",
    xaxis:{domain:[0,1],type:"date",gridcolor:grid,linecolor:grid,tickfont:{size:10},showgrid:true,
           rangebreaks:[{bounds:["sat","mon"]},{bounds:[17,9],pattern:"hour"}]},
    yaxis: {domain:[0.77,1.00],range:[0,105],gridcolor:grid,ticksuffix:"%",zeroline:false},
    yaxis2:{domain:[0.52,0.75],range:[0,105],gridcolor:grid,ticksuffix:"%",zeroline:false},
    yaxis3:{domain:[0.27,0.50],gridcolor:grid,zeroline:false},
    yaxis4:{domain:[0.00,0.24],gridcolor:grid,zeroline:false},
    shapes,
    annotations:[
      lbl("y",  "Strong / Breakdown %"),
      lbl("y2", "% above 20d / 50d / 200d daily MA"),
      lbl("y3", "NTSS  [VIX3M−VIX]"),
      lbl("y4", "Net Momentum"),
      rlbl("y",35,"35"),rlbl("y",50,"50"),
      rlbl("y2",35,"35"),rlbl("y2",50,"50"),
      rlbl("y3",2," 2"),rlbl("y3",1," 1"),rlbl("y3",0," 0"),
      rlbl("y3",-1,"-1"),rlbl("y3",-3,"-3"),
      rlbl("y4",5,"+5"),rlbl("y4",-5,"-5"),
    ],
  };
}

// ── Render ────────────────────────────────────────────────────────────────────
function render(days) {
  currentRange = days;
  const recs = sliceRecords(days);
  Plotly.react("chartDiv", makeTraces(recs), makeLayout(recs), {
    responsive:true, displayModeBar:true, displaylogo:false,
    modeBarButtonsToRemove:["select2d","lasso2d","autoScale2d"],
  });
}

function setRange(days) {
  document.querySelectorAll("#rangeGrp .btn").forEach((b,i) => {
    b.classList.toggle("active", [5,10,20,30,0][i] === days);
  });
  if (DATA) render(days);
}

window.addEventListener("resize", () => {
  if (DATA) Plotly.relayout("chartDiv", {height:Math.max(window.innerHeight-230,480)});
});

// ── Auto-reload countdown ─────────────────────────────────────────────────────
function startAutoReload() {
  let rem = 60 * 60 * 1000;
  const el = document.getElementById("autoReload");
  const tick = setInterval(() => {
    rem -= 1000;
    if (rem <= 0) { clearInterval(tick); location.reload(); return; }
    const m = Math.floor(rem/60000);
    const s = Math.floor((rem%60000)/1000);
    if (el) el.textContent = "auto-reload in " + m + ":" + String(s).padStart(2,"0");
  }, 1000);
}

loadData();
</script>
</body>
</html>
"""
