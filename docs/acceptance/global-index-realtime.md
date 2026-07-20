# 全球指数实时行情语义验收

- API 行为测试以 HK/US 实时 provider 样本验证字段、百分比单位、请求过滤和 `source=realtime`。
- UI 行为测试验证指数报价查询配置了不高于 10 秒的周期刷新，并保持 market/symbol 查询键隔离。
- 生产验收将 API 返回与同一时间窗口的 Longbridge HK/US 指数报价交叉核对，并确认数据时间持续推进。
