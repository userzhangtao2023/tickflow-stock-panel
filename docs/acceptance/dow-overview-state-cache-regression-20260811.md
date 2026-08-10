# 道氏监控列表状态缓存回归验收（2026-08-11）

## 需求

- `REQ-DOW-MONITOR-LIGHTWEIGHT-LIST-OVERVIEW-001`
- `REQ-DOW-MONITOR-STARTUP-PERFORMANCE-001`

## 故障语义

生产状态文件 `dow_monitor_states.json` 约 11 MB。回归版本在每次
`list_states()`、`get_state()` 和 `save_states()` 调用时都重新解析完整文件，15 秒自动刷新会与
并发请求叠加，导致 `/api/dow-monitor/list-overview` 超过 30 秒仍未响应，页面停在“加载监控状态”。
这不是行情数据缺失，也不能用页面快照代替存储层验收。

## 修复语义

- `DowMonitorStore` 启动时加载一次状态，并记录文件大小和纳秒级修改时间。
- 文件签名未变时，读操作直接复用进程内不可变状态快照，不再重复解析 11 MB JSON。
- 外部进程改写文件后，下一次读操作必须检测签名变化并仅重载一次。
- 写入和删除在同一锁内先吸收外部变化，再原子写文件并同步缓存签名，避免覆盖外部更新。

## 可执行证据

```text
PYTHONPATH=backend python -m pytest \
  tests/backend/test_dow_monitor_fast_bootstrap.py \
  backend/tests/test_dow_monitor_api.py -q
45 passed in 46.46s
```

新增回归用例先证明旧实现对两个未变化读取执行两次磁盘加载，再验证修复后为零次；外部写入后恰好重载一次，且返回外部的新价格。

## 候选环境证据

- 使用生产根文件系统、生产 11 MB 状态文件和正式数据目录，只替换缓存实现，在 `13019` 启动候选实例。
- 美股列表正常返回 9 只股票并显示价格和指标。
- 冷启动请求为 7.730 秒，随后为 4.973、4.510 秒；缓存稳定后为 2.807 秒，达到稳定态 TTFB 不超过 3 秒的发布门槛。
- 回滚边界仅为 `backend/app/services/dow_monitor_store.py`，不改变行情采集、ClickHouse、Flink、决策或通知语义。

## 生产验收

生产验收须同时满足：`/health` 为当前构建、ClickHouse 能力初始化成功、列表包含 9 只美股、稳定态
`list-overview` TTFB 不超过 3 秒，并且页面数据时间继续推进。端口监听本身不构成完成证据。

2026-08-11 04:32—04:34 的正式验收结果：

- 正式容器内修复文件 SHA-256 为 `cf63c9c11f174353c6dc21d8d1ef52f74f38f2b2acdbedfc386cdc830e991125`。
- 启动日志识别 `custom minute source 'clickhouse'`，报告 `ready; 4 capabilities active` 和 `Application startup complete`。
- 已登录正式浏览器强制刷新后，页面完整返回 9 行美股；单次 `list-overview` 为 766,147 bytes，TTFB 2.105 秒、总耗时 2.107 秒。
- 页面实时价格、WOBI/MLOFI 和内容变化时间可见；RNG.US 指标内容时间推进到 04:29。道氏分钟结果表仍停在 8 月 7 日，作为独立计算产出缺口记录，未用实时行情覆盖或伪装。
- 在实时快车道运行、历史追赶暂停以保护业务延迟后的最终强刷仍为 9 行，`list-overview` 766,145 bytes、TTFB 2.505 秒；本机 `/health` 抽样为 0.104 秒。
