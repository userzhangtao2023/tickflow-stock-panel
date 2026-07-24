"""道氏多周期策略的内置注册入口。

实际扫描由专用的多市场、多周期服务执行；本模块只负责把该能力注册进
统一策略引擎，使策略池、详情和来源标识使用同一份内置策略元数据。
"""

META = {
    "id": "dow_trend",
    "name": "道氏趋势 · 多周期",
    "description": "5分钟、15分钟、30分钟、60分钟和日线任一已完成周期出现 OPEN_LONG 即入选",
    "tags": ["道氏", "多周期", "实时"],
    "strategy_role": "buy",
    "execution_backend": "external",
    "asset_types": ["stock"],
    "timeframes": ["1d"],
    "version": "1.0.0",
    "basic_filter": {},
    "params": [],
    "scoring": {},
    "entry_signals": ["OPEN_LONG"],
    "exit_signals": ["CLOSE_LONG"],
    "order_by": "strategyScore",
    "descending": True,
    "limit": 80,
}

EXECUTION_BACKEND = "external"
ENTRY_SIGNALS = ["OPEN_LONG"]
EXIT_SIGNALS = ["CLOSE_LONG"]
ALERTS = []
