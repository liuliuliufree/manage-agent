import unittest

from src.application import CAPABILITY_CATALOG


class CapabilityCatalogTests(unittest.TestCase):
    def test_catalog_contains_the_five_configured_capabilities(self) -> None:
        self.assertEqual(
            CAPABILITY_CATALOG,
            {
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
            },
        )

    def test_catalog_does_not_encode_a_fixed_workflow(self) -> None:
        forbidden_fields = {
            "order",
            "step_number",
            "previous_capability",
            "next_capability",
        }

        for definition in CAPABILITY_CATALOG.values():
            self.assertTrue(forbidden_fields.isdisjoint(definition))


if __name__ == "__main__":
    unittest.main()
