# 全球指数实时行情独立审查

状态：待实现后审查。

审查顺序：先确认 Longbridge → ClickHouse 当日指数快照语义，再确认 TickFlow API 字段与来源标记，最后确认 UI 自动刷新。页面显示、SSE 或前端测试不得替代下层数据验收。
