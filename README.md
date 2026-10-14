# Stock Signal · Market Vital Sign

美股市场宽度与 NASDAQ-100 目标组合仪表盘。采用 **GitHub Actions 下载和计算 → 成对 JSON 快照 → Render 展示** 的低内存架构。

- [线上市场宽度](https://stock-signal-uaz4.onrender.com/breadth)：SPY／QQQ 涨跌幅、Strong／Breakdown、NTSS 共用美东时间轴，支持 1D / 5D / 20D / 3M。
- [Market Vital Sign](https://stock-signal-uaz4.onrender.com/)：交易账本持仓状态、两腿合并组合、账户权重及数量估算。

## 更新频率与“为什么显示前一天”

**这不是逐笔实时行情。** 宽度使用 Yahoo Finance / yfinance 的 15 分钟行情，股票筛选和组合中的价格使用日线；组合排名按最近完成的月末复核。网页按钮只检查服务器是否有新快照，不会直接下载数百只股票。

| 环节 | 行为 |
| --- | --- |
| 行情计算 | `refresh_dashboard.yml` 在周一至周五 UTC 13–21 点的 07、22、37、52 分尝试运行；由 XNYS 日历判断交易日、夏令时和提前收盘；盘中若已提交的快照生成不足 `MIN_REFRESH_MINUTES`（仓库变量，默认 10）分钟则跳过，避免外部定时器与 GitHub cron 重复计算 |
| 收盘补齐 | 同一美东交易日收盘后最多 6 小时内，若缺少最后一个 15 分钟时段，再下载一次；已有末根数据且快照在收盘后生成才跳过 |
| 页面更新 | 页面可见时每 60 秒检查一次，重新切回页面立即检查；请求和响应均禁止 HTTP 缓存 |
| 发布 | 成对验证并提交 `data/dashboard_snapshot.json` 和 `data/breadth_15m.json`；Render 部署后才会读到新文件 |
| 独立 CSV | `fetch_stock_data.yml` 只更新日线 CSV；它成功并不代表仪表盘快照更新成功 |

GitHub 的 `schedule` 是尽力执行，并不保证 15 分钟准时运行；Yahoo 行情、排队、计算和 Render 部署也会增加延迟。[GitHub 官方说明](https://docs.github.com/en/actions/how-tos/troubleshoot-workflows)。本次排查发现 2026-09-18 宽度任务实际只于 16:54、19:25、21:46 UTC 启动，最后一次被旧的“仅开盘时运行”条件跳过。这会使页面长期停留在旧记录，即使 Actions 总体显示成功。

周末、节假日、开盘前显示上一交易日属于正常；盘中长时间仍停在上一交易日需要按下面流程排查。`generated_at` 是计算批次时间，`data_as_of` 是实际宽度最新行情时间，两者不能混用。盘中快照的实际行情落后生成时间超过 45 分钟也会标为过期。休市状态来自快照生成时的日历判定。

### 需要更准时的盘中更新

配置独立定时器，每 15 分钟调用 GitHub 的手动工作流接口，避开 GitHub cron 触发延迟（Actions 排队仍可能延迟）：

```text
POST https://api.github.com/repos/PD0831/stock-signal/actions/workflows/refresh_dashboard.yml/dispatches
Authorization: Bearer <保存在定时器密钥库中的令牌>
Accept: application/vnd.github+json
Content-Type: application/json

{"ref":"main"}
```

令牌只需该仓库的 Actions 写权限，不要放在网页、README 或 Git 中。外部触发不带参数时同样受 NYSE 日历门禁约束（休市、盘前盘后直接跳过）。**但每次被跳过的运行仍按 1 分钟计费**，私有仓库请把定时器时区设为 America/New_York，只在周一至周五 09–16 点运行，不要全天调用。人工恢复时在 Actions 页面手动运行并勾选 `force`，才会绕过门禁。当前使用 cron-job.org 触发。 若需要可靠的低延迟，应使用常驻生产进程或专用调度服务，不能仅依靠 GitHub cron + Render 免费服务。

## GitHub Actions 分钟额度

私有仓库在免费计划下每月只有 2,000 分钟 Linux 额度，每个 job 至少按 1 分钟计费。用完后所有运行在几秒内失败（job 无步骤），直到账单周期重置。每 15 分钟刷新一次时，一次真实刷新（build + publish）约 4–5 计费分钟，约 27 次/交易日 × 22 天 ≈ 2,600 分钟，即使不算空跑也超过额度。可选方案：

1. 仓库设为 public：标准 runner 不限分钟，可立即恢复。
2. 保持 private：在 GitHub **Settings → Billing → Budgets** 为 Actions 设置预算（Linux 约 $0.008/分钟），超出部分付费。
3. 保持 private 且免费：仓库变量 `MIN_REFRESH_MINUTES=25`（约每 30 分钟刷新），并限制外部定时器只在美东交易时段调用；本月额度用完后仍需等待重置。

## 本地运行

Python 3.12：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/network_guard.py -- uvicorn live_stock_signal_app:app --host 127.0.0.1 --port 8000 --workers 1
```

打开 `http://127.0.0.1:8000/` 或 `/breadth`。默认读取当前目录 `data/`，可用环境变量 `DATA_DIR` 指向其他快照目录。展示进程禁止主动访问外网，避免每个访问请求重新下载市场数据；本地运行不会自动拉取 Git 仓库更新。

手动重新下载和计算（会访问外网，运行在独立生产环境或本机，不在 512MB 展示进程中执行）：

```bash
pip install --require-hashes -r requirements-actions.lock
python scripts/build_dashboard_snapshots.py --output-dir data
python scripts/validate_dashboard_snapshots.py data/dashboard_snapshot.json data/breadth_15m.json
```

快照包含相同 `generation_id`，必须一起发布。计算失败不应删除上次成功数据。持仓来源是 `data/mvs_position_state.json`，不是当前宽度阶段标签。

## Render 部署

使用仓库的 `render.yaml`：Python Web Service、一个 worker、`DATA_DIR=data`。轻量展示依赖在 `requirements.txt`，行情计算依赖锁定在 `requirements-actions.lock`。

1. Render 连接此仓库的 `main` 分支，并启用 **Auto-Deploy / On Commit**。
2. 检查 Build Filters：不要排除 `data/`，否则新快照提交不会更新线上数据。
3. 可选：从 Render 服务 Settings 获取 Deploy Hook URL，在 GitHub 仓库 **Settings → Secrets and variables → Actions** 添加 `RENDER_DEPLOY_HOOK_URL`。发布任务在成功推送 `main` 后调用它。[Render 官方说明](https://render.com/docs/deploy-hooks)。该 URL 是密钥，不要提交进仓库。
4. 自动部署或 Deploy Hook 至少有一种必须正确配置。Deploy Hook 未配置时 Actions 会提示；触发成功只表示 Render 接受部署请求，仍需检查最终部署状态。
5. Render 免费实例可能休眠，首次访问有冷启动；部署期间旧版本仍可能继续服务。不要用放宽“过期”时间冒充新行情。

## 数据落后时的排查顺序

1. 打开 `/api/breadth`，比较 `data_as_of`（或旧版 `records` 最后一条的 `t`）、`generated_at`、`generation_id` 和 `stale`。
2. 检查 GitHub [Refresh MVS dashboard snapshots](https://github.com/PD0831/stock-signal/actions/workflows/refresh_dashboard.yml)：看实际启动时间，以及 **Build snapshots、Upload snapshots、publish** 是否执行；不要只看整条工作流绿色。
3. 若仓库快照也旧：手动 **Run workflow → main**；查看下载、成分股覆盖率、依赖或发布错误。错峰 cron 只能缓解调度延迟，不能保证准时。
4. 若仓库新、线上旧：检查 Render 部署的 commit、Auto-Deploy、Build Filters、Deploy Hook；完成一次最新 `main` 部署。API 返回 `no-store` 不能更新容器里旧的文件。
5. 若行情时间旧但生成时间新：检查行情源是否返回旧数据。页面显示真实行情时间；刷新网页本身不能修复源数据。
6. 若报 generation mismatch：两份 JSON 没有同批次发布，重新生成、验证并一起部署。

## 测试与目录

```bash
pip install --require-hashes -r requirements-actions.lock
pip install -r requirements.txt pytest httpx pyyaml
python3 -m pytest --import-mode=importlib -q
```

JS 合约测试需要 Node.js；服务冒烟测试需要绑定本地端口。`--import-mode=importlib` 避免根目录和 `tests/` 下同名模块的收集冲突。

- `dashboard_html.py`：两页 HTML、SVG 图表和自动检查。
- `live_stock_signal_app.py`：快照校验、文件缓存及 API。
- `scripts/market_snapshot_data.py`：成分股、行情和指标计算。
- `scripts/build_dashboard_snapshots.py`：快照、组合和历史合并。
- `scripts/nyse_market_hours.py`：交易日及收盘补齐门禁。
- [图表口径](docs/BREADTH_CHARTS.md) · [MVS 选股与仓位口径](docs/MVS_SELECTION_AND_SIZING.md)
