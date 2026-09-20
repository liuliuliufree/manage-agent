"""Capabilities available to the M2-Lite planner.

The mapping is a catalog of independent capability categories. Its iteration
order has no workflow meaning: a planner may select, skip, repeat, or reorder
capabilities according to the current goal and context.
"""

from typing import Final


CAPABILITY_CATALOG: Final[dict[str, dict[str, str]]] = {
    "directional_insight": {
        "description": "识别与当前经营目标相关的经营机会",
    },
    "customer_targeting": {
        "description": "围绕明确经营机会寻找候选客户",
    },
    "strategy_generation": {
        "description": "针对明确客户形成经营策略",
    },
    "validation_distribution": {
        "description": "进行必要校验并支持后续分发",
    },
    "tracking_iteration": {
        "description": "查看经营任务进展和反馈",
    },
}
