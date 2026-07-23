# 道氏实时监控独立需求证据复核

日期：2026-07-23
复核结论：十项需求均有实现、可执行测试和 01347.HK 语义证据；未发现
TickFlow 本地重算道氏锚点/信号、静默实时源回退或新增 systemd 调度任务。

| 需求 | 实现与测试复核 | 独立结论 |
| --- | --- | --- |
| REQ-DOW-WATCH-UI-001 | `DowMonitor.tsx`、卡片/迷你图；`DowMonitor.test.tsx` | 紧凑多卡片和五周期摘要由服务状态驱动。 |
| REQ-DOW-WATCH-DETAIL-001 | `DowMonitorDetailDialog.tsx` 及其测试 | 详情复用现有 K 线控件，不建立第二套指标语义。 |
| REQ-DOW-WATCH-FILTER-001 | 页面与 hook 测试 | 市场/信号筛选只改变视图，不修改启用状态。 |
| REQ-DOW-WATCH-DATA-001 | strict ClickHouse provider/data tests | 01347 strict 1655 唯一分钟、无缺口；未走 HTTP 行情回退。 |
| REQ-DOW-WATCH-MTF-001 | bars/service tests | 五周期统一 source timestamp，均持久化 LIVE。 |
| REQ-DOW-WATCH-SIGNAL-001 | typed Longbridge client/service tests | 真实 CLOSE_LONG 样本的 line/role/anchors 与 Longbridge 完全一致。 |
| REQ-DOW-WATCH-NOTIFY-001 | service/store tests | 首次、维持、清除、再激活和不可变快照均有端到端证据。 |
| REQ-DOW-WATCH-BACKGROUND-001 | app lifecycle/API/health tests | 页面关闭不控制后端循环；健康探针只检查服务状态。 |
| REQ-DOW-WATCH-STALE-001 | data/service tests及生产故障恢复 | SESSION_GAP 阶段保持旧状态并阻断通知；补齐后恢复 LIVE。 |
| REQ-DOW-WATCH-MARKET-001 | session/bar tests | A/HK/US 规则均有测试；本次只做 HK 01347 语义验收。 |

## 下层优先复核

先验证 T-1 完整分钟数据，再验证五周期聚合与通知。最初只有 PostgreSQL
回补而 ClickHouse 未启用写入时，验收明确失败；启用 ClickHouse sink 后，
T-1 达到 331 唯一分钟。随后又发现 `lb_intraday_lines` SQL 分支遗漏
`1347.HK` 别名，测试先 RED，再以提交 `072afde` 修复并达到 115 项相关测试
通过。没有用截图、黄金文件或下游通知替代这些下层语义门槛。

## 身份与持久化复核

真实 30m 样本控制线为 `SUPPORT-MAIN-2`：

- role/side：`MAIN / SUPPORT`
- anchors：`2026-07-08 15:00 @ 183.6`、
  `2026-07-09 13:30 @ 192.3`

这些字段来自 Longbridge 响应，并进入不可变通知快照。受控四项通知测试
共 `4 passed`；生产当前为 WATCH，未伪造激活信号。

## 调度复核

应用只保留既有 `longbridge-api.service`。没有新增 timer、crontab 或
systemd 调度单元。独立复核确认 Chronicle 仅有一个
`tickflow-dow-monitor-health` 事件，已启用并按 10 分钟周期运行；实际
run `jmrxo5s5095` 以 `job_complete/code=0` 完成。crontab、系统级 timer 和
用户级 timer 的重复项均为 0。
