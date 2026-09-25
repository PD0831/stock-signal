_AUTO_REFRESH = r"""function startSnapshotPolling(refresh){
  if(typeof window==="undefined"||typeof document.addEventListener!=="function")return;
  let pending=false;
  async function check(){if(document.hidden||pending)return;pending=true;try{await refresh()}catch(_error){}finally{pending=false}}
  window.setInterval(check,60000);
  document.addEventListener("visibilitychange",check);
}
"""

_NAV = r"""
<style>
  .nav-bar { background:#161b22; border-bottom:1px solid #30363d; padding:0 24px; display:flex; gap:0; }
  .nav-link { display:block; padding:9px 16px; font-size:13px; font-weight:600;
              text-decoration:none; color:#8b949e;
              border-bottom:2px solid transparent; transition:color .15s; }
  .nav-link:hover { color:#c9d1d9; }
  .nav-link.active { color:#58a6ff; border-bottom-color:#58a6ff; }

  body { background:radial-gradient(ellipse at 80% 0%,#172637 0,transparent 42%),#0b1017; }
  header { background:transparent; border-bottom:0; padding-top:30px; padding-bottom:22px; }
  header h1 { font-size:23px; font-weight:650; letter-spacing:-.035em; }
  header .eyebrow { color:#92a7bc; font-size:10px; letter-spacing:.19em; margin-bottom:8px; }
  .nav-bar { padding:0 max(20px,calc((100vw - 1320px)/2)); gap:8px; align-items:center; background:#101720; border-color:#26313e; }
  .brand { color:#edf3fa; text-decoration:none; font-size:19px; font-weight:800; letter-spacing:-1px; margin-right:auto; white-space:nowrap; }
  .brand>span { color:#72b6c9; }.brand .brand-caption { color:#7f90a3; font-size:9px; letter-spacing:.14em; margin-left:16px; font-weight:500; }
  .nav-link { padding:16px 18px; font-size:12px; }.nav-link.active { color:#91c9d8; border-color:#91c9d8; }
  main { margin-top:24px; gap:18px; } .hero,.action-panel,.phase-panel,.metric,.panel,.section,.radar { background:#111a25; border-color:#273442; border-radius:14px; }
  .action-panel,.hero-main { border-left:0; }.action-panel { padding:22px 24px; }
  #currentAction,#breadthAction { font-size:21px; line-height:1.45; font-weight:650; letter-spacing:-.02em; }
  .metric { position:relative; padding:20px; }.metric-label,.label,.micro-label,.action-label { font-weight:600; letter-spacing:.09em; color:#91a1b5; }
  .metric-value,.value { font-size:30px; letter-spacing:-.045em; font-weight:600; }.metric-note,.delta { margin-top:8px; color:#94a3b5; }
  button { border-radius:8px; background:#1a2634; border-color:#354656; padding:9px 14px; font-size:12px; }
  button:hover:not(:disabled) { background:#25364a; } button:focus-visible,a:focus-visible,summary:focus-visible,input:focus-visible,svg:focus-visible { outline:2px solid #91c9d8; outline-offset:3px; }
  .section-head { padding:20px; } h2 { font-weight:650; } .badge { font-weight:600; } th { padding-top:14px; padding-bottom:14px; } td { padding-top:14px; padding-bottom:14px; }
  @media(max-width:720px) { header { padding:22px 16px 18px; } header h1 { font-size:19px; } header { flex-wrap:wrap; } .header-actions { flex-direction:row; align-items:center; justify-content:space-between; width:100%; } .section-head { flex-direction:column; align-items:stretch; } .strategy-controls { justify-content:flex-start; } .nav-bar { padding:0 14px; }.nav-link { padding:14px 9px; font-size:11px; }.brand .brand-caption { display:none; } #currentAction,#breadthAction { font-size:19px; } }
</style>
<nav class="nav-bar" aria-label="主导航"><a class="brand" href="/">M<span> / </span>VS<span class="brand-caption">MARKET OBSERVATORY</span></a>
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
    .strategy-controls { display:flex; align-items:center; justify-content:flex-end; gap:10px; flex-wrap:wrap; }
    .strategy-meta { color:var(--muted); font-size:11px; }
    .account-label { color:var(--muted); font-size:11px; font-weight:700; }
    #accountEquity { width:132px; margin-left:6px; border:1px solid #354458; background:#0d141d;
      color:var(--text); border-radius:7px; padding:7px 9px; font-variant-numeric:tabular-nums; }
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
    table { width:100%; min-width:1180px; border-collapse:collapse; font-variant-numeric:tabular-nums; }
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
      #buyTargetTable th:nth-child(8),#buyTargetTable td:nth-child(8),
      #buyTargetTable th:nth-child(9),#buyTargetTable td:nth-child(9),
      #buyTargetTable th:nth-child(10),#buyTargetTable td:nth-child(10),
      #buyTargetTable th:nth-child(11),#buyTargetTable td:nth-child(11) { display:none; }
      #buyTargetTable th:nth-child(1),#buyTargetTable td:nth-child(1),
      #buyTargetTable th:nth-child(2),#buyTargetTable td:nth-child(2),
      #buyTargetTable th:nth-child(5),#buyTargetTable td:nth-child(5),
      #buyTargetTable th:nth-child(6),#buyTargetTable td:nth-child(6),
      #buyTargetTable th:nth-child(7),#buyTargetTable td:nth-child(7) { display:table-cell; }
    }
  </style>
</head>
<body>
<header>
  <div><div class="eyebrow">15 Minute Snapshot</div><h1>Market Vital Sign 决策台</h1></div>
  <div class="header-actions"><span id="dataTimestamp">数据时间 —</span><button id="runBtn" type="button">检查更新</button></div>
</header>
""" + _NAV + r"""
<main id="dashboard" aria-busy="false"><p class="section-sub">每分钟自动检查新快照 · 行情由后台定时下载，非逐笔实时</p>
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
    <div class="section-head"><div><h2 id="targetsTitle">MVS 目标组合</h2><div class="section-sub">NASDAQ 100 · 两腿合并后的账户级买入清单</div></div>
      <div class="strategy-controls"><span class="strategy-meta"><span id="strategyMode">—</span> · 总暴露 <span id="grossExposure">—</span></span>
        <label class="account-label" for="accountEquity">账户净值 USD<input id="accountEquity" type="number" min="1000" step="1000" value="100000" inputmode="decimal"></label>
        <span class="badge" id="targetCount" role="status" aria-live="polite">0 个</span></div></div>
    <p id="buyTargetMessage" role="status" aria-live="polite">正在加载买入标的…</p>
    <div class="table-scroll"><table id="buyTargetTable" aria-label="买入标的专业表格" hidden>
      <thead><tr><th scope="col">排名</th><th scope="col">标的</th><th scope="col">流动性腿</th><th scope="col">趋势/Dip腿</th>
        <th scope="col">账户权重</th><th scope="col">计划金额</th><th scope="col">整股数量</th><th scope="col">最新价</th>
        <th scope="col">EMA200 距离</th><th scope="col">ADV 排名</th><th scope="col">复核日</th></tr></thead>
      <tbody id="buyTargetBody"></tbody></table></div>
  </section>
  <section class="below">
    <article class="radar" id="shortRadar"><div class="micro-label">空头雷达</div><h2 id="shortRadarTitle">等待市场状态</h2><p id="shortRadarText">只有在市场阶段转弱时才评估对冲；本页不自动生成交易。</p></article>
    <article class="radar"><div class="micro-label">数据质量</div><h2>预计算快照</h2><p id="qualityDisclosure">正在检查覆盖率与新鲜度。</p>
      <details><summary>方法说明</summary><p>交易账本决定持仓；观察标签不会自动平仓。持仓期间每月底复核：流动性腿持有 ADV Top3 等权；普通 Long 的第二腿从 ADV Top15 中按 EMA200 距离选 Top3，按 60% / 20% / 20%；Dip Long 的第二腿改持 ADV Top10 等权。重复股票合并显示。1.15× 属 development 候选，尚未通过真正新样本验收。</p></details></article>
  </section>
</main>
<script>
  const F1 = new Intl.NumberFormat("zh-CN",{minimumFractionDigits:1,maximumFractionDigits:1});
  const F2 = new Intl.NumberFormat("zh-CN",{minimumFractionDigits:2,maximumFractionDigits:2});
  const F0 = new Intl.NumberFormat("zh-CN",{maximumFractionDigits:0});
  let lastSignalData=null;
  function finite(value){ return typeof value === "number" && Number.isFinite(value); }
  function valueFrom(status,names){ for(const name of names){ if(finite(status[name])) return status[name]; } return null; }
  function setText(id,value){ document.getElementById(id).textContent=String(value); }
  function setDashboardBusy(busy){ document.getElementById("dashboard").setAttribute("aria-busy",busy?"true":"false"); }
  function cell(value,className){ const td=document.createElement("td"); td.textContent=String(value); if(className) td.className=className; return td; }
  function universeName(value){ return value === "nasdaq100" ? "NASDAQ 100" : value === "sp500" ? "S&P 500" : "—"; }
  function accountValue(){ const raw=Number(document.getElementById("accountEquity").value); return Number.isFinite(raw)&&raw>0?raw:100000; }
  function targetRow(target,equity){
    const tr=document.createElement("tr");
    const distance=finite(target.distance_pct)?F1.format(target.distance_pct)+"%":"—";
    const price=finite(target.close)?"$"+F2.format(target.close):"—";
    const adv=Number.isInteger(target.adv_rank)?"#"+target.adv_rank:"—";
    const weight=finite(target.target_weight_pct)?F1.format(target.target_weight_pct)+"%":"—";
    const liquidity=finite(target.liquidity_leg_weight_pct)?F1.format(target.liquidity_leg_weight_pct)+"%":"—";
    const trend=finite(target.trend_leg_weight_pct)?F1.format(target.trend_leg_weight_pct)+"%":"—";
    const dollars=finite(target.target_weight_pct)?equity*target.target_weight_pct/100:null;
    const shares=dollars!==null&&finite(target.close)&&target.close>0?Math.floor(dollars/target.close):null;
    tr.append(cell(target.rank,"rank"),cell(target.symbol,"symbol"),cell(liquidity),cell(trend),cell(weight,"weight"),
      cell(dollars===null?"—":"$"+F0.format(dollars)),cell(shares===null?"—":F0.format(shares)),cell(price),
      cell(distance,finite(target.distance_pct)?(target.distance_pct>=0?"positive":"negative"):""),cell(adv),cell(target.selection_date||target.last_date||"—"));
    return tr;
  }
  function sortedTargets(targets){ return [...targets].sort((a,b)=>a.rank-b.rank || a.universe.localeCompare(b.universe) || a.symbol.localeCompare(b.symbol)); }
  function renderTargets(data){
    const rows=sortedTargets(Array.isArray(data.buy_targets)?data.buy_targets:[]);
    const table=document.getElementById("buyTargetTable"), message=document.getElementById("buyTargetMessage");
    document.getElementById("buyTargetBody").replaceChildren(...rows.map(target=>targetRow(target,accountValue())));
    message.setAttribute("role","status");
    setText("targetCount",rows.length+" 个"); table.hidden=rows.length===0; message.hidden=rows.length>0;
    if(!rows.length) message.textContent=data.strategy&&data.strategy.selection_mode==="cash"?"当前状态为空仓：不买股票，账户净值 100% 保留现金。":"当前快照没有可执行买入标的。";
  }
  function renderStrategy(data){ const strategy=data.strategy||{}; const names={regular_long:"普通 Long",dip_long_proxy:"Phase C · Dip代理",regular_long_hold:"普通 Long · 持仓中",dip_long_hold:"Dip Long · 持仓中",cash:"空仓"};
    setText("strategyMode",names[strategy.selection_mode]||"—"); setText("grossExposure",finite(strategy.gross_exposure_pct)?F1.format(strategy.gross_exposure_pct)+"%":"—"); }
  function renderStatus(data){
    const status=data.market_status||{}, strategy=data.strategy||{}, phase=String(status.phase_code||status.phase||"—");
    const strong=finite(status.strong)?status.strong:valueFrom(status,["s"]);
    const breakdown=finite(status.breakdown)?status.breakdown:valueFrom(status,["bd"]);
    const ntss=finite(status.ntss)?status.ntss:valueFrom(status,["mid"]);
    const momentum=finite(status.momentum)?status.momentum:valueFrom(status,["mom"]);
    setText("marketPhase",phase==="—"?"—":phase+" "+(status.phase||"")); setText("phaseBadge",status.label||"未知");
    setText("strongValue",strong===null?"—":F1.format(strong)+"%"); setText("breakdownValue",breakdown===null?"—":F1.format(breakdown)+"%");
    setText("ntssValue",ntss===null?"—":F2.format(ntss)); setText("momentumValue",momentum===null?"—":F2.format(momentum));
    setText("ntssState",status.ntss_state||"市场中轴");
    setText("currentAction",strategy.action_label||status.label||"等待市场确认"); setText("actionBasis",strategy.action||status.action||status.basis||"依据最新市场阶段与预计算候选股执行。");
    const riskOff=status.signal==="short";
    const trailWatch=status.signal==="short_watch";
    const radarKind=status.short_type?status.short_type+" · ":"";
    setText("shortRadarTitle",riskOff||trailWatch?radarKind+(status.label||"空头雷达"):(status.label||"观察")+" · 空头雷达关闭");
    setText("shortRadarText",status.action||"等待生产者发布最新市场行动。");
  }
  function renderQuality(data){
    const quality=data.quality||{}, badge=document.getElementById("freshnessBadge");
    badge.className="badge "+(data.stale?"stale":"fresh"); badge.textContent=data.stale?"数据已过期":"数据正常";
    setText("dataTimestamp","行情 "+String(data.data_as_of||data.generated_at||"—").replace("T"," "));
    const parts=[]; ["nasdaq100","sp500"].forEach(key=>{ const q=quality[key]; if(!q) return;
      const market=universeName(key); if(finite(q.valid_count)) parts.push(market+" 有效 "+q.valid_count);
      if(finite(q.failed_count)) parts.push(market+" 失败 "+q.failed_count);
      if(q.universe_source) parts.push(market+" 来源 "+q.universe_source);
      if(q.universe_warning) parts.push(market+" 警告 "+q.universe_warning);
      if(q.universe_error) parts.push(market+" 错误 "+q.universe_error);
      if(key==="nasdaq100"&&data.strategy&&data.strategy.selection_mode!=="cash"){
        const candidateCount=Array.isArray(data.buy_targets)?data.buy_targets.filter(target=>target.universe===key).length:0;
        const expected=["dip_long_proxy","dip_long_hold"].includes(data.strategy.selection_mode)?10:3;
        if(candidateCount<expected) parts.push(market+" 候选不足 "+candidateCount+"/"+expected);
      }
    });
    if(quality.session_status) parts.push(quality.session_status==="open"?"交易时段":"非交易时段");
    if(data.stale) parts.push("页面继续展示上次成功快照");
    setText("qualityDisclosure",parts.length?parts.join(" · "):"覆盖率未提供；页面仅展示已验证快照字段。");
  }
  function setUnavailable(message){
    setText("currentAction","暂缓交易"); setText("actionBasis","快照不可用："+message); setText("marketPhase","—");
    setText("phaseBadge","未知"); setText("dataTimestamp","数据时间 —"); setText("targetCount","0 个"); setText("strategyMode","—"); setText("grossExposure","—");
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
    setText("phaseBadge","等待"); setText("dataTimestamp","数据时间 —"); setText("targetCount","0 个"); setText("strategyMode","—"); setText("grossExposure","—");
    const badge=document.getElementById("freshnessBadge"); badge.className="badge"; badge.textContent="加载中";
    ["strongValue","breakdownValue","ntssValue","momentumValue"].forEach(id=>setText(id,"—"));
    setText("ntssState","等待");
    document.getElementById("buyTargetBody").replaceChildren(); document.getElementById("buyTargetTable").hidden=true;
    const message=document.getElementById("buyTargetMessage"); message.hidden=false; message.textContent="正在加载买入标的…"; message.setAttribute("role","status");
    setText("shortRadarTitle","正在加载市场风险"); setText("shortRadarText","正在读取 Breakdown、NTSS 与市场阶段。");
    setText("qualityDisclosure","正在检查覆盖率与新鲜度。");
    setDashboardBusy(true);
  }
  async function runSignal(background=false){
    const button=document.getElementById("runBtn"); if(button.disabled)return;button.disabled=true; if(!background)setLoading();
    try { const response=await fetch("/api/signals",{cache:"no-store",signal:AbortSignal.timeout(45000)}); const data=await response.json(); if(!response.ok) throw new Error(data.error||"请求失败");
      lastSignalData=data; renderStatus(data); renderQuality(data); renderStrategy(data); renderTargets(data); setDashboardBusy(false);
    } catch(error) { setUnavailable(error instanceof Error?error.message:"未知错误"); }
    finally { button.disabled=false; }
  }
  document.getElementById("runBtn").addEventListener("click",()=>runSignal());
  const accountEquity=document.getElementById("accountEquity"); accountEquity.addEventListener("input",()=>{if(lastSignalData)renderTargets(lastSignalData)}); runSignal();
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
      border-radius:999px;padding:4px 9px;font-size:11px;font-weight:800}    .fresh{color:var(--green);border-color:#267a4c;background:#10291d}
    .stale{color:var(--amber);border-color:#926f19;background:#2a210c}.unavailable{color:var(--red);border-color:#963b48;background:#2a1218}
    .badge.safe{color:var(--green);border-color:#267a4c;background:#10291d}.badge.caution{color:var(--amber);border-color:#926f19;background:#2a210c}.badge.panic{color:var(--red);border-color:#963b48;background:#2a1218}
    #breadthPhase{font-size:22px;font-weight:850}.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.metric{padding:17px}.value{font-size:30px;
      font-weight:850;font-variant-numeric:tabular-nums;margin-top:7px}.delta{font-size:11px;color:var(--muted);margin-top:5px}.positive{color:var(--green)}.negative{color:var(--red)}
    .panel{padding:18px}.panel-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:13px}.sub{font-size:11px;color:var(--muted)}
    .range-bar{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}.range-options{display:flex;gap:6px;overflow-x:auto;padding:2px}
    .range-options button[aria-pressed="true"]{color:#07111d;background:var(--blue);border-color:var(--blue)}#coverageLabel{color:var(--muted);font-size:11px}
    .chart-stack{display:grid;gap:10px}.chart-wrap{position:relative}.chart-label{margin:0 0 6px;color:var(--muted);font-size:11px;font-weight:800}
    #intradayChart,#ntssChart{width:100%;height:auto;background:#0b1119;border-radius:8px;border:1px solid #202a37;outline:none}
    #intradayChart{min-height:220px}#ntssChart{min-height:150px}.legend{display:flex;gap:15px;color:var(--muted);font-size:11px}
    .dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px}.transition{border-left:3px solid var(--amber);padding:12px 14px;background:#141b24;border-radius:6px}
    details{border:1px solid var(--line);border-radius:10px;background:#0e151e}summary{cursor:pointer;padding:15px 17px;font-weight:800}.research{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:var(--line);border-top:1px solid var(--line)}
    .research>div{background:#111821;padding:15px}.research .value{font-size:22px}#qualityDetails{padding:14px 17px;color:var(--muted);border-top:1px solid var(--line)}
    .visually-hidden{position:absolute!important;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
    @media(max-width:720px){header{align-items:flex-start}.hero{grid-template-columns:1fr}.hero-side{border-left:0;border-top:1px solid var(--line)}.metrics{grid-template-columns:1fr}.research{grid-template-columns:1fr 1fr}.panel{padding:12px}.range-bar{align-items:flex-start}.range-options{width:100%}#intradayChart{min-height:190px}#ntssChart{min-height:130px}}
    main{width:min(1320px,calc(100% - 40px))}.hero{grid-template-columns:minmax(0,1fr) 300px}.hero-main{padding:22px 24px}.hero-side{padding:18px 24px}.panel{padding:24px}.panel-head h2{font-size:18px;margin-bottom:5px}.range-bar{padding:12px 0 20px}.range-options{padding:4px;background:#0c131d;border:1px solid #273442;border-radius:10px}.range-options button{border:0;background:transparent;min-width:48px;padding:7px 12px}.range-options button[aria-pressed="true"]{color:#dceef5;background:#294354}.chart-stack{gap:20px}.chart-label{font-weight:600;font-size:12px;margin-bottom:10px;color:#c1ccd9}.chart-index{display:inline-block;color:#75899e;font-size:10px;margin-right:10px}.chart-heading{display:flex;justify-content:space-between;gap:12px}.chart-wrap{min-width:0}#priceChart,#intradayChart,#ntssChart{display:block;width:100%;height:auto;min-height:0;background:#0d151f;border:1px solid #22313f;border-radius:10px;touch-action:pan-y}#benchmarkCoverage{margin:0 0 9px}#cursorDetails{margin-top:18px;padding:12px 14px;min-height:44px;background:#182431;border:1px solid #2a3b4b;border-radius:8px;color:#c7d6e5;font-variant-numeric:tabular-nums;line-height:1.8}.research>div{background:#111a25}
    #analogPanel{min-width:0}.analog-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1px;background:var(--line);border:1px solid var(--line);border-radius:10px;overflow:hidden;margin-bottom:16px}.analog-summary>div{background:#111a25;padding:13px 15px}.analog-summary .value{font-size:20px;margin-top:4px}
    .table-scroll{overflow-x:auto;border:1px solid var(--line);border-radius:10px}.analog-table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums;min-width:760px}.analog-table th,.analog-table td{padding:10px 12px;text-align:right;border-bottom:1px solid #1d2835;white-space:nowrap}.analog-table th:first-child,.analog-table td:first-child{text-align:left;white-space:normal;min-width:190px}.analog-table thead th{color:var(--muted);font-size:10px;font-weight:800;letter-spacing:.06em;background:#0d151f}.analog-table tbody tr:last-child td{border-bottom:0}.analog-table .cond{display:block;color:var(--muted);font-size:11px;font-weight:400;margin-top:2px}.analog-table tr.thin td{color:#9aa7b7}.thin-tag{display:inline-block;margin-left:6px;padding:1px 6px;border:1px solid #926f19;border-radius:999px;color:var(--amber);font-size:10px;font-weight:800}.analog-table .episodes td{text-align:left;color:var(--muted);font-size:11px;white-space:normal;background:#0d151f}
    .riskoff-box{margin-top:16px;padding:13px 15px;border-left:3px solid var(--amber);background:#141b24;border-radius:6px;line-height:1.7}.riskoff-box.clear{border-left-color:#267a4c}
    @media(max-width:720px){.analog-summary{grid-template-columns:1fr 1fr}}
    @media(max-width:720px){main{width:calc(100% - 24px)}.hero{grid-template-columns:1fr}.hero-side{grid-template-columns:1fr 1fr;gap:10px}.hero-side .sub{grid-column:1/-1}.metrics{grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.metric{padding:13px}.value{font-size:24px}.delta{font-size:10px}.panel{padding:14px}.panel-head{flex-direction:column}.chart-stack{gap:18px}.chart-label .sub{display:none}.legend{gap:10px}.range-options{width:auto}.range-bar{gap:10px}#coverageLabel{font-size:10px}}
  </style>
</head><body>
<header><div><div class="eyebrow">Market breadth / 15 min</div><h1>15 分钟市场宽度</h1></div><button id="refreshBtn" type="button">检查更新</button></header>
""" + _NAV + r"""
<main id="breadthDashboard" aria-busy="true"><p class="sub">每分钟自动检查新快照 · 行情由后台定时下载，非逐笔实时</p>
  <section class="hero"><div class="hero-main" role="status" aria-live="polite"><div class="label">当前行动</div><h2 id="breadthAction">正在加载</h2><p class="sub" id="latestBar">正在读取预计算快照。</p></div>
    <div class="hero-side">
      <div class="row"><span class="label">NTSS 状态</span><span class="badge" id="ntssStateBadge">—</span></div>
      <div class="row"><span class="label">快照状态</span><span class="badge" id="breadthFreshness" role="status" aria-live="polite">加载中</span></div>
      <div class="sub" id="breadthTimestamp">数据时间 —</div></div></section>
  <section class="metrics" aria-label="盘中核心指标">
    <article class="metric"><div class="label">Strong</div><div class="value positive" id="strongValue">—</div><div class="delta" id="strongDelta">—</div></article>
    <article class="metric"><div class="label">Breakdown</div><div class="value negative" id="breakdownValue">—</div><div class="delta" id="breakdownDelta">—</div></article>
    <article class="metric"><div class="label">NTSS</div><div class="value" id="ntssValue">—</div><div class="delta" id="ntssDelta">—</div></article>
  </section>
  <section class="panel"><div class="panel-head"><div><h2>价格 × 市场宽度</h2><div class="sub">对照指数走势与市场参与度 · 美东时间 ET · 非交易时段压缩</div></div><div class="legend"><span><i class="dot" style="background:var(--green)"></i>Strong</span><span><i class="dot" style="background:var(--red)"></i>Breakdown</span><span><i class="dot" style="background:var(--blue)"></i>NTSS</span></div></div>
    <div class="range-bar"><div id="rangeOptions" class="range-options" role="group" aria-label="历史范围">
      <button type="button" data-range="1D" aria-pressed="false">1D</button><button type="button" data-range="5D" aria-pressed="true">5D</button><button type="button" data-range="20D" aria-pressed="false">20D</button><button type="button" data-range="3M" aria-pressed="false">3M</button>
    </div><div id="coverageLabel" role="status" aria-live="polite">正在计算实际覆盖范围</div></div>
    <div class="chart-stack"><div class="chart-wrap"><div class="chart-heading"><p class="chart-label"><span class="chart-index">01</span> 指数走势 <span class="sub">共同起点涨跌幅 %</span></p><div class="legend"><span><i class="dot" style="background:#b5a1f5"></i>SPY</span><span><i class="dot" style="background:#f2c47b"></i>QQQ</span></div></div><p id="benchmarkCoverage" class="sub">正在读取指数行情</p><svg id="priceChart" viewBox="0 0 900 220" role="img" tabindex="0" aria-labelledby="priceChartTitle priceChartDescription"></svg></div><div class="chart-wrap"><p class="chart-label"><span class="chart-index">02</span> Strong / Breakdown <span class="sub">强势与破位股占比 %</span></p><svg id="intradayChart" viewBox="0 0 900 250" role="img" tabindex="0" aria-labelledby="chartTitle chartDescription"></svg></div>
      <div class="chart-wrap"><p class="chart-label"><span class="chart-index">03</span> NTSS <span class="sub">独立刻度 · 零轴参考</span></p><svg id="ntssChart" viewBox="0 0 900 190" role="img" tabindex="0" aria-labelledby="ntssChartTitle ntssChartDescription"></svg></div></div>
    <p id="cursorDetails" class="sub" role="status" aria-live="polite">使用鼠标或方向键查看记录。</p><p id="chartEmpty" class="sub" hidden>暂无足够记录。</p></section>
  <section class="panel" id="analogPanel" aria-labelledby="analogTitle"><div class="panel-head"><div><h2 id="analogTitle">当前数值的历史统计</h2><div class="sub" id="analogMeta">正在读取历史对照。</div></div></div>
    <div class="analog-summary" id="analogSummary"></div>
    <div class="table-scroll"><table class="analog-table"><thead><tr><th scope="col">历史同类状态</th><th scope="col">独立事件</th><th scope="col">样本日</th><th scope="col">之后 20 天均值</th><th scope="col">之后 60 天均值</th><th scope="col">60 天中位</th><th scope="col">60 天收跌比例</th><th scope="col">60 天内回撤中位</th><th scope="col">回撤超过 10% 比例</th></tr></thead><tbody id="analogRows"><tr><td colspan="9">加载中</td></tr></tbody></table></div>
    <div class="riskoff-box" id="riskOffBox" hidden></div>
    <p class="sub" id="analogMethod" style="margin-top:12px"></p></section>
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
function resetValues(emptyText){["strongValue","strongDelta","breakdownValue","breakdownDelta","ntssValue","ntssDelta","ma20Value","ma50Value","ma200Value","momentumValue"].forEach(id=>text(id,"—"));document.getElementById("intradayChart").replaceChildren();document.getElementById("ntssChart").replaceChildren();document.getElementById("priceChart").replaceChildren();visibleRecords=[];selectedRecordIndex=-1;lastBreadthData=null;text("benchmarkCoverage","暂无指数行情");const empty=document.getElementById("chartEmpty");empty.hidden=false;empty.textContent=emptyText;text("seriesSummary",emptyText);text("cursorDetails","使用鼠标或方向键查看记录。");text("coverageLabel","暂无覆盖范围")}
function setLoading(){resetValues("正在加载历史轨迹。");text("breadthAction","正在加载");text("latestBar","正在读取预计算快照。");text("breadthTimestamp","数据时间 —");text("qualityDetails","正在检查覆盖率和有效成分股数。");const b=document.getElementById("breadthFreshness");b.className="badge";b.textContent="加载中";b.setAttribute("role","status");busy(true)}
function setUnavailable(message){resetValues("轨迹不可用。");text("breadthAction","暂缓判断："+message);text("latestBar","等待下一次成功发布。");text("breadthTimestamp","数据时间 —");text("qualityDetails","快照不可用，研究指标已清空。");renderAnalogs(null);const b=document.getElementById("breadthFreshness");b.className="badge unavailable";b.textContent="不可用";b.setAttribute("role","alert");busy(false)}
function metric(value,previous,digits,suffix,elapsed){const val=finite(value)?(digits===2?P2:P1).format(value)+(suffix||""):"—";let delta="—";if(finite(value)&&finite(previous)&&finite(elapsed)&&elapsed>0&&elapsed<=180){const d=value-previous,mins=Math.round(elapsed);delta=(d>0?"+":d<0?"−":"")+(digits===2?P2:P1).format(Math.abs(d))+(suffix||"")+" vs "+mins+" 分钟前"}return [val,delta]}
function dayKey(t){return ET_DATE.format(new Date(t))}
function normalizeRecords(records){const unique=new Map();(Array.isArray(records)?records:[]).forEach(record=>{const ms=Date.parse(record&&record.t);if(Number.isFinite(ms))unique.set(ms,{...record,_ms:ms})});return [...unique.values()].sort((a,b)=>a._ms-b._ms)}
function svg(tag,attrs){const node=document.createElementNS("http://www.w3.org/2000/svg",tag);Object.entries(attrs||{}).forEach(([k,v])=>node.setAttribute(k,String(v)));return node}
const VALID_RANGES=new Set(["1D","5D","20D","3M"]);let activeRange="5D",lastBreadthData=null,visibleRecords=[],selectedRecordIndex=-1;
try{const saved=localStorage.getItem("mvsBreadthRange");if(VALID_RANGES.has(saved))activeRange=saved}catch(_error){}
function intradayRecords(records){return normalizeRecords(records)}
function subtractMonths(ms,months){const d=new Date(ms),day=d.getUTCDate();d.setUTCDate(1);d.setUTCMonth(d.getUTCMonth()-months);const days=new Date(Date.UTC(d.getUTCFullYear(),d.getUTCMonth()+1,0)).getUTCDate();d.setUTCDate(Math.min(day,days));d.setUTCHours(0,0,0,0);return d.getTime()}
function filterRange(records,range){const sorted=normalizeRecords(records);if(!sorted.length)return[];if(range==="3M"){const cutoff=subtractMonths(sorted[sorted.length-1]._ms,3);return sorted.filter(r=>r._ms>=cutoff)}const count=range==="1D"?1:range==="20D"?20:5,days=[...new Set(sorted.map(r=>dayKey(r.t)))],allowed=new Set(days.slice(-count));return sorted.filter(r=>allowed.has(dayKey(r.t)))}
function coverage(records){if(!records.length)return"暂无覆盖范围";return "实际覆盖 "+dayKey(records[0].t)+" 至 "+dayKey(records[records.length-1].t)+" · "+records.length+" 根"}
function updateRangeButtons(){const root=document.getElementById("rangeOptions");if(!root||!root.querySelectorAll)return;root.querySelectorAll("button[data-range]").forEach(button=>button.setAttribute("aria-pressed",String(button.getAttribute("data-range")===activeRange)))}
function setRange(range){activeRange=VALID_RANGES.has(range)?range:"5D";try{localStorage.setItem("mvsBreadthRange",activeRange)}catch(_error){}updateRangeButtons();if(lastBreadthData)renderBreadth(lastBreadthData)}
function seriesSegments(records,key,x,y){const groups=[];let current=[];records.forEach((record,index)=>{if(finite(record[key]))current.push(x(index)+","+y(record[key]));else if(current.length){groups.push(current);current=[]}});if(current.length)groups.push(current);return groups}
function appendSeries(chart,records,key,color,x,y){seriesSegments(records,key,x,y).forEach(points=>{if(points.length>=2)chart.appendChild(svg("polyline",{points:points.join(" "),fill:"none",stroke:color,"stroke-width":3,"stroke-linejoin":"round"}))})}
let chartWidth=900;
const ET_DATE=new Intl.DateTimeFormat("en-CA",{timeZone:"America/New_York",year:"numeric",month:"2-digit",day:"2-digit"});
const ET_TIME=new Intl.DateTimeFormat("en-GB",{timeZone:"America/New_York",hour:"2-digit",minute:"2-digit",hourCycle:"h23"});
function timeLabel(t){const d=new Date(t);return ET_DATE.format(d)+" "+ET_TIME.format(d)+" ET"}
function benchmarkSeries(records){
  const valid=v=>finite(v)&&v>0,hasSpy=records.some(r=>valid(r.spy)),hasQqq=records.some(r=>valid(r.qqq));
  const base=records.findIndex(r=>(!hasSpy||valid(r.spy))&&(!hasQqq||valid(r.qqq))&&(hasSpy||hasQqq));
  return records.map((r,i)=>({...r,spyReturn:base>=0&&i>=base&&valid(r.spy)&&valid(records[base].spy)?(r.spy/records[base].spy-1)*100:null,qqqReturn:base>=0&&i>=base&&valid(r.qqq)&&valid(records[base].qqq)?(r.qqq/records[base].qqq-1)*100:null}));
}
function chartText(chart,label,x,y,anchor="start",color="#8b98a9"){const node=svg("text",{x,y,fill:color,"font-size":11,"text-anchor":anchor});node.textContent=label;chart.appendChild(node)}
function axisTicks(chart,recs,bottom){
  const count=Math.min(chartWidth<600?3:5,recs.length),indices=[...new Set(Array.from({length:count},(_,i)=>Math.round(i*(recs.length-1)/(count-1))))];
  indices.forEach(i=>{const x=45+(chartWidth-70)*i/(recs.length-1),anchor=i===0?"start":i===recs.length-1?"end":"middle";
    chart.appendChild(svg("line",{x1:x,y1:15,x2:x,y2:bottom,stroke:"#263140","stroke-dasharray":"2 5"}));
    const d=new Date(recs[i].t);chartText(chart,ET_DATE.format(d).slice(5)+" "+ET_TIME.format(d),x,bottom+21,anchor);
  });
}
function titleChart(chart,id,title,description){const t=svg("title",{id:id+"Title"});t.textContent=title;chart.appendChild(t);const d=svg("desc",{id:id+"Description"});d.textContent=description;chart.appendChild(d)}
function renderCursor(index){
  if(!visibleRecords.length)return;selectedRecordIndex=Math.max(0,Math.min(index,visibleRecords.length-1));
  const record=visibleRecords[selectedRecordIndex],x=45+(chartWidth-70)*(visibleRecords.length===1?0:selectedRecordIndex/(visibleRecords.length-1));
  [["priceChart",185],["intradayChart",220],["ntssChart",155]].forEach(([id,bottom])=>{const chart=document.getElementById(id);if(chart.querySelectorAll)chart.querySelectorAll('[data-cursor="true"]').forEach(node=>node.remove());chart.appendChild(svg("line",{x1:x,y1:12,x2:x,y2:bottom,stroke:"#8b98a9","stroke-dasharray":"2 3","data-cursor":"true"}))});
  const price=key=>{const value=record[key+"Return"];return key.toUpperCase()+" "+(finite(record[key])&&record[key]>0?"$"+P2.format(record[key]):"—")+" / "+(finite(value)?(value>0?"+":"")+P2.format(value)+"%":"—")};
  text("cursorDetails",timeLabel(record.t)+" · "+price("spy")+" · "+price("qqq")+" · Strong "+(finite(record.s)?P1.format(record.s)+"%":"—")+" · Breakdown "+(finite(record.bd)?P1.format(record.bd)+"%":"—")+" · NTSS "+(finite(record.mid)?P2.format(record.mid):"—"));
}
function renderChart(records){
  const chart=document.getElementById("intradayChart"),ntssChart=document.getElementById("ntssChart"),priceChart=document.getElementById("priceChart"),empty=document.getElementById("chartEmpty"),recs=benchmarkSeries(normalizeRecords(records));
  chartWidth=Math.max(320,Math.min(1200,chart.clientWidth||900));
  [[chart,250],[ntssChart,190],[priceChart,220]].forEach(([c,height])=>{c.replaceChildren();c.setAttribute("viewBox","0 0 "+chartWidth+" "+height)});visibleRecords=recs;selectedRecordIndex=-1;
  const ntssValues=recs.filter(r=>finite(r.mid)).map(r=>r.mid),prices=recs.flatMap(r=>[r.spyReturn,r.qqqReturn]).filter(finite),base=recs.find(r=>finite(r.spyReturn)||finite(r.qqqReturn));
  const hasSpy=recs.some(r=>finite(r.spyReturn)),hasQqq=recs.some(r=>finite(r.qqqReturn));
  text("benchmarkCoverage",base?"基准 "+timeLabel(base.t)+" · 15 分钟收盘价 · "+(!hasSpy?"SPY 暂无数据 · ":!hasQqq?"QQQ 暂无数据 · ":"")+"缺失区间留空":"暂无可对齐的 SPY / QQQ 行情，等待含指数价格的新快照。");
  empty.hidden=recs.filter(r=>finite(r.s)||finite(r.bd)).length>=2||ntssValues.length>=2||prices.length>=2;
  if(recs.length<2){empty.hidden=false;empty.textContent="所选范围有效记录不足。";text("seriesSummary",empty.textContent);return}
  const left=45,right=chartWidth-25,x=i=>left+(right-left)*i/(recs.length-1),top=18,bottom=220,y=v=>bottom-(bottom-top)*Math.max(0,Math.min(100,v))/100;
  titleChart(chart,"chart","Strong 与 Breakdown · "+activeRange,"所选范围 "+coverage(recs)+"。时间为美东时间 ET。");
  [0,25,50,75,100].forEach(v=>{chart.appendChild(svg("line",{x1:left,y1:y(v),x2:right,y2:y(v),stroke:"#263140"}));chartText(chart,v+"%",8,y(v)+4)});
  axisTicks(chart,recs,220);appendSeries(chart,recs,"s","#41d17d",x,y);appendSeries(chart,recs,"bd","#ff6574",x,y);
  titleChart(ntssChart,"ntssChart","NTSS · "+activeRange,"NTSS 独立刻度，零轴参考。美东时间 ET。");
  let min=Math.min(0,...ntssValues),max=Math.max(0,...ntssValues);if(min===max){min-=1;max+=1}const pad=Math.max((max-min)*.1,.25);min-=pad;max+=pad;
  const ny=v=>155-140*(v-min)/(max-min),zero=ny(0);
  ntssChart.appendChild(svg("rect",{x:left,y:15,width:right-left,height:Math.max(0,zero-15),fill:"#10291d",opacity:.35}));
  ntssChart.appendChild(svg("rect",{x:left,y:zero,width:right-left,height:Math.max(0,155-zero),fill:"#2a1218",opacity:.35}));
  ntssChart.appendChild(svg("line",{x1:left,y1:zero,x2:right,y2:zero,stroke:"#8b98a9","stroke-width":1.5}));
  [max,0,min].forEach(v=>chartText(ntssChart,P2.format(v),8,ny(v)+4));axisTicks(ntssChart,recs,155);appendSeries(ntssChart,recs,"mid","#5ba7ff",x,ny);
  titleChart(priceChart,"priceChart","SPY / QQQ · "+activeRange,"相同起点的区间价格变化，不含分红。"+document.getElementById("benchmarkCoverage").textContent);
  let pmin=Math.min(0,...prices),pmax=Math.max(0,...prices);const ppad=Math.max((pmax-pmin)*.15,.1);pmin-=ppad;pmax+=ppad;
  const py=v=>185-167*(v-pmin)/(pmax-pmin);
  [pmax,0,pmin].forEach(v=>{priceChart.appendChild(svg("line",{x1:left,y1:py(v),x2:right,y2:py(v),stroke:v===0?"#576779":"#263140","stroke-dasharray":v===0?"4 4":"none"}));chartText(priceChart,P1.format(v)+"%",3,py(v)+4)});
  axisTicks(priceChart,recs,185);appendSeries(priceChart,recs,"spyReturn","#b5a1f5",x,py);appendSeries(priceChart,recs,"qqqReturn","#f2c47b",x,py);
  if(!prices.length)chartText(priceChart,"暂无指数行情",chartWidth/2,100,"middle");
  if(!ntssValues.length)chartText(ntssChart,"暂无 NTSS 数据",chartWidth/2,80,"middle");
  text("seriesSummary",coverage(recs)+"。SPY、QQQ、Strong、Breakdown 与 NTSS 使用共享时间轴，美东时间 ET。");renderCursor(recs.length-1);
}
function pctText(v,signed){if(!finite(v))return"—";return(signed&&v>0?"+":"")+P1.format(v)+"%"}
function hnode(tag,cls,content){const n=document.createElementNS("http://www.w3.org/1999/xhtml",tag);if(cls)n.className=cls;if(content!==undefined)n.textContent=String(content);return n}
function statCell(value,signed){const c=signed&&finite(value)?(value>0?"positive":value<0?"negative":""):"";return hnode("td",c,pctText(value,signed))}
function wideRow(cls,content){const tr=hnode("tr",cls),td=hnode("td","",content);td.setAttribute("colspan","9");tr.appendChild(td);return tr}
function summaryTile(label,value,note){const d=hnode("div");d.appendChild(hnode("div","label",label));d.appendChild(hnode("div","value",value));d.appendChild(hnode("div","delta",note));return d}
function episodeText(e){return e.date+"（Strong "+(finite(e.strong)?P1.format(e.strong):"—")+" / Breakdown "+(finite(e.breakdown)?P1.format(e.breakdown):"—")+" / NTSS "+(finite(e.mid)?P2.format(e.mid):"—")+" → 60 天 "+(finite(e.f60)?pctText(e.f60,true):"进行中")+"，回撤 "+(finite(e.mdd60)?pctText(e.mdd60,true):"—")+"）"}
function riskOffText(ro){const nm=finite(ro.net_momentum)?P2.format(ro.net_momentum):"—";if(!ro.zone)return"Risk Off 条件未就绪：Breakdown > 50 "+(ro.breakdown_gt_50?"✓":"✗")+" · Breakdown > Strong "+(ro.breakdown_gt_strong?"✓":"✗")+" · 净动量 "+nm+"。";
  return"Risk Off 条件：Breakdown > 50 ✓ · Breakdown > Strong ✓ · 净动量（Pine 口径，今日对昨日收盘）"+nm+"，需 ≤ "+P1.format(ro.momentum_trigger)+"。历史上处于同样等待状态的 "+ro.history_waiting_days+" 天里，5 / 10 / 20 个交易日内触发的比例为 "+pctText(ro.triggered_within_5d_pct)+" / "+pctText(ro.triggered_within_10d_pct)+" / "+pctText(ro.triggered_within_20d_pct)+"。"}
function renderAnalogs(a){const rows=document.getElementById("analogRows"),summary=document.getElementById("analogSummary"),box=document.getElementById("riskOffBox");rows.replaceChildren();summary.replaceChildren();
  if(!a||!Array.isArray(a.rows)){text("analogMeta","历史对照暂不可用。");rows.appendChild(wideRow("","暂无数据"));box.hidden=true;text("analogMethod","");return}
  const c=a.current||{};text("analogMeta","当前日线读数与 "+a.history_start+" 至 "+a.history_end+" 的历史比较 · 之后收益按 QQQ");
  [["Breakdown",c.breakdown,c.breakdown_percentile,P1],["Strong",c.strong,c.strong_percentile,P1],["NTSS",c.mid,c.mid_percentile,P2]].forEach(([name,v,p,fmt])=>summary.appendChild(summaryTile(name,finite(v)?fmt.format(v):"—",finite(p)?"历史分位 "+P1.format(p)+"%":"—")));
  summary.appendChild(summaryTile("QQQ 位置",pctText(c.qqq_drawdown_pct,true),"距 52 周高点 · "+(c.above_ma200?"MA200 之上":"MA200 之下")));
  a.rows.forEach(r=>{const tr=hnode("tr",r.thin?"thin":""),head=hnode("td","",r.label);if(r.thin)head.appendChild(hnode("span","thin-tag","样本不足"));head.appendChild(hnode("span","cond",r.condition||""));tr.appendChild(head);
    tr.appendChild(hnode("td","",finite(r.n_events)?r.n_events:"—"));tr.appendChild(hnode("td","",finite(r.n_days)?r.n_days:"—"));
    [[r.f20_mean,true],[r.f60_mean,true],[r.f60_median,true],[r.f60_neg_pct,false],[r.mdd60_median,true],[r.mdd60_le10_pct,false]].forEach(([v,signed])=>tr.appendChild(statCell(v,signed)));rows.appendChild(tr);
    if(Array.isArray(r.episodes)&&r.episodes.length)rows.appendChild(wideRow("episodes","历史日期："+r.episodes.map(episodeText).join("；")))});
  if(a.risk_off){box.hidden=false;box.className="riskoff-box"+(a.risk_off.zone?"":" clear");box.textContent=riskOffText(a.risk_off)}else box.hidden=true;
  text("analogMethod",a.method||"")}
function qualityText(data,cur){const q=data.quality||{},parts=[];if(finite(q.valid_count))parts.push("有效 "+q.valid_count);if(finite(q.failed_count))parts.push("失败 "+q.failed_count);[["MA20","a20_n", "valid_20_n"],["MA50","a50_n","valid_50_n"],["MA200","a200_n","valid_200_n"]].forEach(([name,a,b])=>{const n=finite(cur[a])?cur[a]:cur[b];if(finite(n))parts.push(name+" 有效 "+n)});if(q.session_status)parts.push(q.session_status==="open"?"交易时段":"市场已收盘");if(data.stale)parts.push("继续展示上次成功快照");return parts.length?parts.join(" · "):"覆盖率未提供。"}
function renderBreadth(data){lastBreadthData=data;updateRangeButtons();const all=normalizeRecords(data.records),recs=filterRange(all,activeRange);if(!recs.length){setUnavailable("暂无可用记录");return}text("coverageLabel",coverage(recs));const cur=recs[recs.length-1],complete=recs.filter(r=>finite(r.s)&&finite(r.bd)),curComplete=finite(cur.s)&&finite(cur.bd),prev=curComplete?complete[complete.length-2]||null:null,elapsed=prev?(cur._ms-prev._ms)/60000:null;const midVal=finite(cur.mid)?cur.mid:null;const nsb=document.getElementById("ntssStateBadge");if(midVal===null){nsb.textContent="—";nsb.className="badge"}else if(midVal<0){nsb.textContent="PANIC";nsb.className="badge panic"}else if(midVal<2){nsb.textContent="CAUTION";nsb.className="badge caution"}else{nsb.textContent="SAFE";nsb.className="badge safe"}text("breadthAction",cur.action||cur.action_label||"等待生产端发布行动建议。");text("latestBar","最新记录 "+timeLabel(cur.t));text("breadthTimestamp","数据时间 "+(Number.isFinite(Date.parse(data.generated_at))?timeLabel(data.generated_at):"—"));
  [["strongValue","strongDelta",cur.s,prev&&prev.s,1,"%"],["breakdownValue","breakdownDelta",cur.bd,prev&&prev.bd,1,"%"],["ntssValue","ntssDelta",cur.mid,prev&&prev.mid,2,""]].forEach(v=>{const out=metric(v[2],v[3],v[4],v[5],elapsed);text(v[0],out[0]);text(v[1],out[1])});
  [["ma20Value",cur.a20,1,"%"],["ma50Value",cur.a50,1,"%"],["ma200Value",cur.a200,1,"%"],["momentumValue",cur.mom,2,""]].forEach(v=>text(v[0],finite(v[1])?(v[2]===2?P2:P1).format(v[1])+v[3]:"—"));
  renderChart(recs);renderAnalogs(data.analogs);text("qualityDetails",qualityText(data,cur));const b=document.getElementById("breadthFreshness");b.className="badge "+(data.stale?"stale":"fresh");b.textContent=data.stale?"数据已过期":((data.quality||{}).session_status==="closed"?"市场已收盘":"数据正常");b.setAttribute("role","status");busy(false)}
async function loadBreadth(background=false){const button=document.getElementById("refreshBtn");if(button.disabled)return;button.disabled=true;if(!background)setLoading();try{const response=await fetch("/api/breadth",{cache:"no-store",signal:AbortSignal.timeout(45000)});const data=await response.json();if(!response.ok)throw new Error(data.error||"请求失败");renderBreadth(data)}catch(error){setUnavailable(error instanceof Error?error.message:"未知错误")}finally{button.disabled=false}}
document.getElementById("refreshBtn").addEventListener("click",()=>loadBreadth());
const rangeRoot=document.getElementById("rangeOptions");if(rangeRoot&&rangeRoot.querySelectorAll)rangeRoot.querySelectorAll("button[data-range]").forEach(button=>button.addEventListener("click",()=>setRange(button.getAttribute("data-range"))));
function inspectChart(event){if(!visibleRecords.length)return;if(event&&event.key){if(!["ArrowLeft","ArrowRight","Home","End"].includes(event.key))return;if(event.preventDefault)event.preventDefault();const next=event.key==="Home"?0:event.key==="End"?visibleRecords.length-1:event.key==="ArrowLeft"?Math.max(0,selectedRecordIndex-1):Math.min(visibleRecords.length-1,selectedRecordIndex+1);renderCursor(next);return}const chart=event.currentTarget,box=chart.getBoundingClientRect(),vb=chart.viewBox.baseVal,scale=Math.min(box.width/vb.width,box.height/vb.height),offset=(box.width-vb.width*scale)/2,px=(event.clientX-box.left-offset)/scale,ratio=Math.max(0,Math.min(1,(px-45)/(vb.width-70)));renderCursor(Math.round(ratio*(visibleRecords.length-1)))}
["priceChart","intradayChart","ntssChart"].forEach(id=>{const chart=document.getElementById(id);chart.addEventListener("click",inspectChart);chart.addEventListener("pointermove",inspectChart);chart.addEventListener("keydown",inspectChart)});
if(typeof ResizeObserver!=="undefined"){let resizeFrame;new ResizeObserver(()=>{cancelAnimationFrame(resizeFrame);resizeFrame=requestAnimationFrame(()=>{const width=Math.max(320,Math.min(1200,document.getElementById("intradayChart").clientWidth||900));if(width!==chartWidth&&lastBreadthData)renderChart(filterRange(lastBreadthData.records,activeRange))})}).observe(document.getElementById("intradayChart"))}
updateRangeButtons();loadBreadth();
</script></body></html>
"""

# Keep polling in each page's main script, including standalone JS contract tests.
SIGNALS_HTML = SIGNALS_HTML.replace('  async function runSignal', _AUTO_REFRESH + '  async function runSignal').replace('}); runSignal();', '}); runSignal();startSnapshotPolling(()=>runSignal(true));')
BREADTH_HTML = BREADTH_HTML.replace('async function loadBreadth', _AUTO_REFRESH + 'async function loadBreadth').replace('updateRangeButtons();loadBreadth();', 'updateRangeButtons();loadBreadth();startSnapshotPolling(()=>loadBreadth(true));')
