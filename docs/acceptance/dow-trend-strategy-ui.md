# 道氏趋势策略入口验收

状态：通过（2026-07-24）

- `dow_trend` 继续作为股票内置策略显示，使用专用的多市场、多周期手工执行控制区。
- `StrategyEngine` 从 `backend/app/strategy/builtin/dow_trend.py` 正式加载 `dow_trend`，策略来源为 `builtin`、执行后端为 `external`；列表和详情接口读取同一注册项，不再由 API 临时追加元数据。
- 打开策略或切换市场只清空结果，不发送 `/api/dow-strategy/runs` 请求。
- 控制区明确提示“点击‘执行选股’开始扫描”；只有用户点击按钮后才启动当前市场任务。
- 运行中显示完成数、总数和当前股票；完成后显示命中数量或空结果。
- 道氏返回值会转换为统一筛选行，股票只在共享 `ScreenerTable` / `StockDataTable` 中展示，不再生成横向候选卡片。
- 共享列表保留策略标签、评分以及“局部/长期”命中周期摘要，并沿用现有排序、筛选、列配置、加自选和详情入口。
- 注册行为测试先观察到 `StrategyEngine.get("dow_trend")` 报 `unknown strategy`，再由正式内置注册修复；后端策略注册、ETF 隔离和代理路由回归测试共21项通过。
- 组件及路由测试共5项通过，强制 TypeScript 检查和前端生产构建通过。
