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
SIGNALS_HTML = r"""<!doctype html>
<html lang="zh">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Market Vital Sign</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: #0d1117;
      color: #e6edf3;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 13px;
      min-height: 100vh;
    }
    header {
      background: #161b22;
      border-bottom: 1px solid #30363d;
      padding: 14px 24px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
    }
    .hd-title { font-size: 16px; font-weight: 700; letter-spacing: -.01em; }
    .hd-sub   { font-size: 11px; color: #8b949e; margin-top: 3px; }
    .hd-right { display: flex; align-items: center; gap: 10px; }
    #clock { font-size: 12px; color: #8b949e; font-variant-numeric: tabular-nums; }
    #runBtn {
      height: 30px; padding: 0 12px;
      background: #21262d; border: 1px solid #30363d;
      color: #c9d1d9; border-radius: 6px;
      font-size: 12px; font-weight: 600; cursor: pointer;
    }
    #runBtn:hover { background: #30363d; border-color: #484f58; }
    #runBtn:disabled { opacity: .5; cursor: wait; }

    main { max-width: 1280px; margin: 0 auto; padding: 20px 16px; display: grid; gap: 32px; }

    .sec-hd {
      display: flex; align-items: baseline;
      justify-content: space-between;
      padding-bottom: 10px;
      border-bottom: 1px solid #21262d;
      margin-bottom: 14px;
    }
    .sec-title { font-size: 15px; font-weight: 700; }
    .sec-meta  { font-size: 11px; color: #8b949e; }

    .cards { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
    .cards.three { grid-template-columns: 1fr 1fr 1fr; }

    .status-panel {
      background: #161b22;
      border: 1px solid #30363d;
      border-radius: 8px;
      padding: 13px 15px;
      display: grid;
      grid-template-columns: 1.1fr 1.6fr;
      gap: 12px;
      align-items: center;
    }
    .status-main { display: flex; align-items: center; gap: 9px; flex-wrap: wrap; }
    .badge {
      display: inline-flex; align-items: center;
      border-radius: 999px; padding: 3px 10px;
      font-size: 11px; font-weight: 800;
      border: 1px solid #30363d;
    }
    .badge.safe { color: #3fb950; border-color: #238636; background: rgba(46,160,67,.12); }
    .badge.caution { color: #d29922; border-color: #9e6a03; background: rgba(187,128,9,.12); }
    .badge.panic { color: #f85149; border-color: #da3633; background: rgba(248,81,73,.10); }
    .badge.wait { color: #8b949e; background: #21262d; }
    .status-title { font-size: 14px; font-weight: 800; }
    .status-detail { color: #8b949e; font-size: 12px; line-height: 1.45; }

    .card {
      background: #161b22;
      border: 1px solid #30363d;
      border-radius: 10px;
      overflow: hidden;
    }
    .card-hd {
      padding: 11px 15px 11px 13px;
      border-bottom: 1px solid #30363d;
      display: flex; justify-content: space-between; align-items: center;
    }
    .card-hd.stable { border-left: 3px solid #3fb950; }
    .card-hd.offens { border-left: 3px solid #d29922; }
    .card-hd.short  { border-left: 3px solid #f85149; }
    .card-title { font-size: 13px; font-weight: 700; }
    .card-title.stable { color: #3fb950; }
    .card-title.offens { color: #d29922; }
    .card-title.short  { color: #f85149; }
    .card-perf { font-size: 11px; color: #484f58; }
    .card-note {
      padding: 7px 15px;
      font-size: 11px; color: #484f58;
      background: #0d1117;
      border-top: 1px solid #21262d;
    }

    .msg-row { padding: 16px 15px; color: #8b949e; font-size: 13px; }
    .msg-row.err { color: #f85149; }

    table { width: 100%; border-collapse: collapse; }
    th, td {
      padding: 9px 15px;
      text-align: right;
      white-space: nowrap;
      border-bottom: 1px solid #21262d;
    }
    th:first-child, td:first-child { text-align: left; }
    th {
      font-size: 10px; font-weight: 700;
      color: #484f58; text-transform: uppercase; letter-spacing: .05em;
      background: #0d1117;
    }
    tbody tr { transition: background .1s; }
    tbody tr:hover { background: rgba(139,148,158,.05); }
    tbody tr:last-child td { border-bottom: none; }

    .sym { font-size: 14px; font-weight: 800; color: #58a6ff; letter-spacing: -.02em; }
    .rk {
      display: inline-flex; align-items: center; justify-content: center;
      width: 22px; height: 22px; border-radius: 50%;
      font-size: 11px; font-weight: 800;
    }
    .rk.s-hi  { background: #3fb950; color: #0d1117; }
    .rk.s-lo  { background: #21262d; color: #8b949e; }
    .rk.o-hi  { background: #d29922; color: #0d1117; }
    .rk.x-hi  { background: #f85149; color: #0d1117; }
    .pos { color: #3fb950; font-weight: 600; font-variant-numeric: tabular-nums; }
    .neg { color: #f85149; font-weight: 600; font-variant-numeric: tabular-nums; }
    .na  { color: #484f58; }
    .num { color: #c9d1d9; font-variant-numeric: tabular-nums; }

    @media (max-width: 760px) {
      .cards, .cards.three  { grid-template-columns: 1fr; }
      .status-panel { grid-template-columns: 1fr; }
      header  { flex-direction: column; align-items: flex-start; }
      main    { padding: 12px; gap: 20px; }
    }
  </style>
</head>
<body>
<header>
  <div>
    <div class="hd-title">Market Vital Sign</div>
    <div class="hd-sub">信号激活时参考 · 数据来自 Yahoo Finance</div>
  </div>
  <div class="hd-right">
    <span id="clock">—</span>
    <button id="runBtn">⟳ 刷新</button>
  </div>
</header>
""" + _NAV + r"""
<main>
  <div class="status-panel">
    <div class="status-main">
      <span class="badge wait" id="signalBadge">状态加载中</span>
      <span class="status-title" id="statusTitle">等待市场宽度数据</span>
    </div>
    <div class="status-detail" id="statusDetail">正在读取最新 Strong / Breakdown / NTSS。</div>
  </div>
  <div>
    <div class="sec-hd">
      <span class="sec-title">NASDAQ 100 / QQQ</span>
      <span class="sec-meta" id="nasdaqMeta">—</span>
    </div>
    <div class="cards three">
      <div class="card">
        <div class="card-hd stable">
          <span class="card-title stable">稳健核心 · ADV Top5</span>
          <span class="card-perf">CAGR 44–49% · MaxDD ~22%</span>
        </div>
        <div class="msg-row" id="nasdaqAdvMsg">正在加载…</div>
        <table id="nasdaqAdvTbl" style="display:none">
          <thead><tr><th>股票</th><th>#</th><th>收盘价</th><th>距 MA200</th><th>63日均量</th></tr></thead>
          <tbody id="nasdaqAdvBody"></tbody>
        </table>
        <div class="card-note">深绿 Top3 建议买入 · 浅色 4–5 为可选扩展</div>
      </div>
      <div class="card">
        <div class="card-hd offens">
          <span class="card-title offens">进攻首选 · ADV Top10 → MA200 Top3</span>
          <span class="card-perf">CAGR 52% · MaxDD ~32%</span>
        </div>
        <div class="msg-row" id="nasdaqMaMsg">正在加载…</div>
        <table id="nasdaqMaTbl" style="display:none">
          <thead><tr><th>股票</th><th>#</th><th>收盘价</th><th>MA200</th><th>超出幅度 ↑</th><th>63日均量</th></tr></thead>
          <tbody id="nasdaqMaBody"></tbody>
        </table>
        <div class="card-note">ADV Top10 中选距 MA200 最远的 3 只 · 动量最强但回撤更大</div>
      </div>
      <div class="card">
        <div class="card-hd short">
          <span class="card-title short">空头保险 · QQQ 70% + 弱股 30%</span>
          <span class="card-perf" id="nasdaqShortType">Gap Short</span>
        </div>
        <div class="msg-row" id="nasdaqShortMsg">正在加载…</div>
        <table id="nasdaqShortTbl" style="display:none">
          <thead><tr><th>标的</th><th>权重</th><th>收盘价</th><th>MA200</th><th>距 MA200 ↓</th></tr></thead>
          <tbody id="nasdaqShortBody"></tbody>
        </table>
        <div class="card-note">仅在空仓期满足 Gap Short 时参考 · 弱股来自 ADV Top30 中 MA200 最弱 Top1</div>
      </div>
    </div>
  </div>
  <div>
    <div class="sec-hd">
      <span class="sec-title">S&amp;P 500 / SPY</span>
      <span class="sec-meta" id="sp500Meta">—</span>
    </div>
    <div class="cards three">
      <div class="card">
        <div class="card-hd stable">
          <span class="card-title stable">稳健核心 · ADV Top5</span>
          <span class="card-perf">流动性加权 · 等权买入</span>
        </div>
        <div class="msg-row" id="sp500AdvMsg">正在加载…</div>
        <table id="sp500AdvTbl" style="display:none">
          <thead><tr><th>股票</th><th>#</th><th>收盘价</th><th>距 MA200</th><th>63日均量</th></tr></thead>
          <tbody id="sp500AdvBody"></tbody>
        </table>
        <div class="card-note">深绿 Top3 · 同公司双重股权已去重</div>
      </div>
      <div class="card">
        <div class="card-hd offens">
          <span class="card-title offens">进攻首选 · ADV Top10 → MA200 Top3</span>
          <span class="card-perf">动量最强 3 只</span>
        </div>
        <div class="msg-row" id="sp500MaMsg">正在加载…</div>
        <table id="sp500MaTbl" style="display:none">
          <thead><tr><th>股票</th><th>#</th><th>收盘价</th><th>MA200</th><th>超出幅度 ↑</th><th>63日均量</th></tr></thead>
          <tbody id="sp500MaBody"></tbody>
        </table>
        <div class="card-note">ADV Top10 池内按 MA200 距离排序，取前 3</div>
      </div>
      <div class="card">
        <div class="card-hd short">
          <span class="card-title short">空头保险 · SPY 70% + 弱股 30%</span>
          <span class="card-perf" id="sp500ShortType">Gap Short</span>
        </div>
        <div class="msg-row" id="sp500ShortMsg">正在加载…</div>
        <table id="sp500ShortTbl" style="display:none">
          <thead><tr><th>标的</th><th>权重</th><th>收盘价</th><th>MA200</th><th>距 MA200 ↓</th></tr></thead>
          <tbody id="sp500ShortBody"></tbody>
        </table>
        <div class="card-note">仅在空仓期满足 Gap Short 时参考 · 弱股来自 ADV Top30 中 MA200 最弱 Top1</div>
      </div>
    </div>
  </div>
</main>
<script>
  const P2 = new Intl.NumberFormat("en-US", { minimumFractionDigits:2, maximumFractionDigits:2 });
  const P1 = new Intl.NumberFormat("en-US", { minimumFractionDigits:1, maximumFractionDigits:1 });
  const P0 = new Intl.NumberFormat("en-US", { maximumFractionDigits:0 });
  function money(v) {
    if (v >= 1e9) return "$" + P2.format(v/1e9) + "B";
    if (v >= 1e6) return "$" + P2.format(v/1e6) + "M";
    return "$" + P0.format(v);
  }
  function distCell(pct) {
    if (pct == null) return '<span class="na">N/A</span>';
    const cls = pct >= 0 ? "pos" : "neg";
    const sgn = pct >= 0 ? "+" : "";
    return '<span class="' + cls + '">' + sgn + P1.format(pct) + "%</span>";
  }
  function advRow(r) {
    const rc = r.rank <= 3 ? "s-hi" : "s-lo";
    return "<tr>"
      + "<td><span class='sym'>" + r.symbol + "</span></td>"
      + "<td><span class='rk " + rc + "'>" + r.rank + "</span></td>"
      + "<td class='num'>$" + P2.format(r.close) + "</td>"
      + "<td>" + distCell(r.distance_pct) + "</td>"
      + "<td class='num'>" + money(r.adv63) + "</td>"
      + "</tr>";
  }
  function maRow(r) {
    const ma = r.ma200 != null
      ? "<span class='num'>$" + P2.format(r.ma200) + "</span>"
      : '<span class="na">N/A</span>';
    return "<tr>"
      + "<td><span class='sym'>" + r.symbol + "</span></td>"
      + "<td><span class='rk o-hi'>" + r.rank + "</span></td>"
      + "<td class='num'>$" + P2.format(r.close) + "</td>"
      + "<td>" + ma + "</td>"
      + "<td>" + distCell(r.distance_pct) + "</td>"
      + "<td class='num'>" + money(r.adv63) + "</td>"
      + "</tr>";
  }
  function shortRows(data) {
    const rows = [];
    rows.push("<tr>"
      + "<td><span class='sym'>" + data.short_proxy + "</span></td>"
      + "<td><span class='rk x-hi'>" + data.short_allocation.proxy_pct + "%</span></td>"
      + "<td class='na'>指数</td><td class='na'>—</td><td class='na'>—</td>"
      + "</tr>");
    data.short_selected.forEach(r => {
      const ma = r.ma200 != null
        ? "<span class='num'>$" + P2.format(r.ma200) + "</span>"
        : '<span class="na">N/A</span>';
      rows.push("<tr>"
        + "<td><span class='sym'>" + r.symbol + "</span></td>"
        + "<td><span class='rk x-hi'>" + data.short_allocation.weak_stock_pct + "%</span></td>"
        + "<td class='num'>$" + P2.format(r.close) + "</td>"
        + "<td>" + ma + "</td>"
        + "<td>" + distCell(r.distance_pct) + "</td>"
        + "</tr>");
    });
    return rows.join("");
  }
  function show(tblId, msgId, rows, renderFn) {
    document.getElementById(tblId.replace("Tbl","Body")).innerHTML = rows.map(renderFn).join("");
    document.getElementById(msgId).style.display = "none";
    document.getElementById(tblId).style.display = "";
  }
  function showShort(prefix, data, status) {
    document.getElementById(prefix+"ShortBody").innerHTML = shortRows(data);
    document.getElementById(prefix+"ShortMsg").style.display = "none";
    document.getElementById(prefix+"ShortTbl").style.display = "";
    document.getElementById(prefix+"ShortType").textContent =
      status && status.short_type ? status.short_type : "Gap Short";
  }
  function renderUniverse(data, prefix) {
    show(prefix+"AdvTbl", prefix+"AdvMsg", data.adv_selected,  advRow);
    show(prefix+"MaTbl",  prefix+"MaMsg",  data.ma200_selected, maRow);
    showShort(prefix, data, window.MARKET_STATUS);
    document.getElementById(prefix+"Meta").textContent =
      "截至 " + data.as_of + " · " + data.valid_count + "/" + data.universe_count + " 有效";
  }
  function renderMarketStatus(status) {
    window.MARKET_STATUS = status || {};
    const badge = document.getElementById("signalBadge");
    const title = document.getElementById("statusTitle");
    const detail = document.getElementById("statusDetail");
    const cls = status.phase_class || "wait";
    badge.className = "badge " + cls;
    badge.textContent = status.label || "状态未知";
    title.textContent = (status.phase_code ? status.phase_code + " · " : "") + (status.phase || "等待宽度数据");
    const bits = [];
    if (status.strong != null) bits.push("Strong " + P1.format(status.strong) + "%");
    if (status.breakdown != null) bits.push("BD " + P1.format(status.breakdown) + "%");
    if (status.ntss != null) bits.push("NTSS " + P2.format(status.ntss));
    if (status.ntss_state) bits.push(status.ntss_state);
    detail.textContent = bits.join(" · ") + (bits.length ? " · " : "") + (status.action || status.basis || "");
  }
  function setLoading() {
    renderMarketStatus({label:"状态加载中", phase:"等待市场宽度数据", phase_class:"wait",
                        action:"正在读取最新 Strong / Breakdown / NTSS。"});
    ["nasdaq","sp500"].forEach(p => {
      ["AdvMsg","MaMsg","ShortMsg"].forEach(s => {
        const el = document.getElementById(p+s);
        el.textContent = "正在抓取并计算…"; el.className = "msg-row"; el.style.display = "";
      });
      ["AdvTbl","MaTbl","ShortTbl"].forEach(s => { document.getElementById(p+s).style.display = "none"; });
      document.getElementById(p+"Meta").textContent = "—";
    });
  }
  function setError(msg) {
    ["nasdaq","sp500"].forEach(p =>
      ["AdvMsg","MaMsg","ShortMsg"].forEach(s => {
        const el = document.getElementById(p+s);
        el.textContent = "错误: " + msg; el.className = "msg-row err";
      })
    );
  }
  async function runSignal() {
    const btn = document.getElementById("runBtn");
    btn.disabled = true; setLoading();
    try {
      const res  = await fetch("/api/signals");
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "请求失败");
      document.getElementById("clock").textContent = data.generated_at.replace("T"," ");
      renderMarketStatus(data.market_status);
      renderUniverse(data.nasdaq100, "nasdaq");
      renderUniverse(data.sp500,     "sp500");
    } catch(err) { setError(err.message); }
    finally { btn.disabled = false; }
  }
  document.getElementById("runBtn").addEventListener("click", runSignal);
  runSignal();
</script>
</body>
</html>
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
