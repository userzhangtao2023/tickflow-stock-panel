# 01347.HK 道氏实时监控语义验收

日期：2026-07-23
范围：仅 `01347.HK`；未扩展到其他股票。

## 生产实况

- TickFlow 提交：`21f1493`、`072afde`；Longbridge 提交：`1430d0e`。
- 生产镜像：`tickflow-stock-panel-app:dow-monitor-history-alias-20260723-2323`。
- `/health` 返回 `status=ok`；`/api/dow-monitor/status` 返回
  `running=true`、`last_error=null`、`errors={}`。
- WebStock strict 数据为 `LIVE`，缺口列表为空；01347 的严格分钟序列为
  `2026-07-17 09:30` 至 `2026-07-23 16:00`，共 1655 个唯一分钟。
- T-1（2026-07-22）在 ClickHouse 中有 331 个唯一分钟，覆盖
  `09:30` 至 `16:00`。这项下层完整性先于五周期验收通过。

五周期均由同一批最新 WebStock 1m 数据重算并持久化：

| 周期 | 状态 | source timestamp | 最后 K 线 | K 线数 | 当前动作 |
| --- | --- | --- | --- | ---: | --- |
| 5m | LIVE | 2026-07-23 16:00+08:00 | 15:55 | 858 | 观察 |
| 15m | LIVE | 2026-07-23 16:00+08:00 | 15:45 | 286 | 观察 |
| 30m | LIVE | 2026-07-23 16:00+08:00 | 15:30 | 143 | 观察 |
| 60m | LIVE | 2026-07-23 16:00+08:00 | 15:00 | 78 | 观察 |
| 日 K | LIVE | 2026-07-23 16:00+08:00 | 2026-07-23 | 745 | 观察 |

当前生产实况是 `WATCH/观察`，因此当前五个周期没有控制线，也没有伪造新的
交易通知。

## 真实引擎事件样本

使用上述 01347.HK 真实 30 分钟 K 线逐根回放 Longbridge
`/api/dow-state/evaluate`，得到以下真实激活样本：

- 触发 K 线：`2026-07-10 14:30+08:00`
- 完成状态：`FINAL`
- 形态：`二次突破确认`
- 动作：`卖出（平多）`（`CLOSE_LONG`）
- 当前 OHLC：`201.8 / 201.8 / 195.6 / 195.6`
- 控制线：`SUPPORT-MAIN-2`，`MAIN / SUPPORT`
- 锚点一：`2026-07-08 15:00+08:00 @ 183.6`
- 锚点二：`2026-07-09 13:30+08:00 @ 192.3`

Longbridge 返回的 line ID、角色、方向、两个锚点时间和价格均直接作为
TickFlow 的消费字段；TickFlow 没有重新推断锚点或买卖点。

## 受控通知序列

真实引擎身份作为语义基准；通知状态机用隔离存储执行受控序列。生产实况
仍保持 WATCH，受控序列没有写入生产通知：

1. 首次激活只产生一条 `activation_sequence=1` 通知。
2. 连续两个周期保持同一 family/line，不重复通知。
3. 先进入 WATCH 清除激活，再次激活同一 line，产生
   `activation_sequence=2`。
4. 重建 `DowMonitorStore` 和服务后，通知仍存在且不会误增 sequence。
5. WebStock stale/session-gap 时保留最后图表和快照，标为数据延迟，不调用
   引擎且不新增通知。

对应可执行证据：

```text
pytest -q tests/test_dow_monitor_service.py -k
"activation_notifies_once_then_reactivation_uses_next_sequence_and_deepcopy or
stale_webstock_retains_snapshot_and_chart_and_sends_no_notification or
restart_recovers_from_last_reliable_timestamp_without_duplicate_event or
restart_after_first_notification_write_before_any_state_does_not_emit_sequence_two"
4 passed
```

生产通知文件在重启和页面关闭后仍保留两条先前的真实 01347 通知快照；
本次 stale 故障和当前 WATCH 重算没有增加第三条。

## 部署与回滚证据

- 曾发现并发故障镜像
  `tickflow-stock-panel-app:dow-monitor-stock-ai-live-fallback-20260723-2318`
  缺少 `app.api.dow_monitor`；已原子回滚到
  `dow-monitor-20260723-2300` 并恢复 `/health`，故障镜像保留供审计。
- 最终候选基于该已验证镜像分层构建并原子切换。
- Longbridge 回补通过
  `/etc/systemd/system/longbridge-api.service.d/realtime-sinks.conf`
  同时写 PostgreSQL 和 ClickHouse。回滚方式是移除该 drop-in、执行
  `systemctl daemon-reload` 并重启既有 `longbridge-api.service`；没有新增
  systemd timer 或调度服务。

## Chronicle 调度验收

- Chronicle 事件：`tickflow-dow-monitor-health`（ID `emrxo5gnr94`）。
- 事件唯一且已启用；时区为 `Asia/Shanghai`，每小时第
  `0/10/20/30/40/50` 分钟执行。
- Chronicle 调度器状态为启用。
- 2026-07-23 手工触发 Chronicle 实际执行一次：run ID
  `jmrxo5s5095`，`action=job_complete`，`code=0`，耗时 1.242 秒。
- `crontab`、系统级 systemd timer、用户级 systemd timer 中同名健康巡检均为
  0 条，Chronicle 是该巡检的唯一调度入口。
