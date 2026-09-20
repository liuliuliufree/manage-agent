import unittest
from types import SimpleNamespace
from typing import cast

from src.application import CAPABILITY_CATALOG, validate_plan
from src.domain import Plan, PlanStep


def plan_with_steps(*steps: PlanStep) -> Plan:
    """Build a plan-shaped test fixture without triggering Plan validation first."""

    return cast(Plan, SimpleNamespace(steps=steps))


class PlanValidationTests(unittest.TestCase):
    def test_unknown_capability_fails(self) -> None:
        plan = plan_with_steps(PlanStep("unknown", "invented_capability"))

        with self.assertRaisesRegex(ValueError, "unknown capability"):
            validate_plan(plan, CAPABILITY_CATALOG)

    def test_duplicate_step_id_fails(self) -> None:
        plan = plan_with_steps(
            PlanStep("duplicate", "directional_insight"),
            PlanStep("duplicate", "customer_targeting"),
        )

        with self.assertRaisesRegex(ValueError, "step_id values must be unique"):
            validate_plan(plan, CAPABILITY_CATALOG)

    def test_unknown_dependency_fails(self) -> None:
        plan = plan_with_steps(
            PlanStep(
                "find_customers",
                "customer_targeting",
                depends_on=("missing_insight",),
            )
        )

        with self.assertRaisesRegex(ValueError, "depends on unknown step"):
            validate_plan(plan, CAPABILITY_CATALOG)

    def test_dependency_cycle_fails(self) -> None:
        plan = plan_with_steps(
            PlanStep(
                "inspect",
                "directional_insight",
                depends_on=("target",),
            ),
            PlanStep(
                "target",
                "customer_targeting",
                depends_on=("inspect",),
            ),
        )

        with self.assertRaisesRegex(ValueError, "dependency cycle"):
            validate_plan(plan, CAPABILITY_CATALOG)


if __name__ == "__main__":
    unittest.main()
