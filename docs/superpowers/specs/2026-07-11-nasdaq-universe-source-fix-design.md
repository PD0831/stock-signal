# NASDAQ-100 成分股加载修复设计

## 问题

`live_stock_signal_app.py` 当前从 Wikipedia 的 `Nasdaq-100` 介绍页读取成分股。Wikipedia 已将成分股表移至独立的 `List_of_NASDAQ-100_companies` 页面，导致程序找不到 `Ticker` 列、返回空列表，最终由 `compute_signals()` 抛出 `Could not load current universe symbols.`。

## 方案

将 `NASDAQ100_URL` 改为新的独立成分股页面，保留现有的表格解析、内存缓存和本地 CSV 兜底行为。S&P 500 数据源及信号计算逻辑不变。

## 数据流

1. `fetch_current_symbols("nasdaq100")` 请求新的 Wikipedia 页面。
2. `pandas.read_html()` 找到包含 `Ticker` 列的表格。
3. 股票代码经过现有 `normalize_symbol()` 规范化、去重和排序。
4. `compute_signals()` 将成分股列表交给现有 yfinance 行情下载流程。

## 错误处理

网络、HTTP 或 HTML 解析异常仍走现有本地 CSV 兜底。此次修复不改变异常吞吐和 API 错误响应，以控制变更范围。

## 测试与验收

- 添加单元回归测试，用固定 HTML 验证 NASDAQ-100 解析能读取 `Ticker` 列并返回规范化代码，避免测试依赖实时网络。
- 先确认测试在旧 URL/旧行为下因请求地址不符而失败，再修改常量使其通过。
- 运行相关单元测试及项目测试。
- 实际请求新的数据源，确认成分股数量合理；随后调用 `/api/signals` 或等效计算路径，确认不再出现 universe symbols 错误。

## 非目标

- 不切换到 Nasdaq 官方 API。
- 不重构行情下载或缓存架构。
- 不修改选股规则、排名或网页布局。
