"""Read and validate immutable synthetic scenario source snapshots."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .errors import BusinessRuleError, ScenarioDataError, ScenarioNotFoundError


SOURCE_FILES = (
    "scenario.csv",
    "business_request.csv",
    "customer_profile.csv",
    "family_responsibility_fact.csv",
    "policy_coverage.csv",
    "authorization.csv",
    "behavior_event.csv",
    "contact_event.csv",
    "sensitive_status.csv",
    "suitability_fact.csv",
    "opportunity_definition.csv",
    "calculation_rule.csv",
)

IDENTIFIER_FIELDS = {
    "business_request.csv": "request_id",
    "customer_profile.csv": "customer_id",
    "family_responsibility_fact.csv": "fact_id",
    "policy_coverage.csv": "policy_id",
    "authorization.csv": "authorization_id",
    "behavior_event.csv": "event_id",
    "contact_event.csv": "event_id",
    "sensitive_status.csv": "status_id",
    "suitability_fact.csv": "fact_id",
    "opportunity_definition.csv": "opportunity_id",
    "calculation_rule.csv": "rule_id",
}

TIMESTAMP_FIELDS = {
    "business_request.csv": ("requested_at",),
    "customer_profile.csv": ("profile_updated_at",),
    "family_responsibility_fact.csv": ("occurred_at",),
    "policy_coverage.csv": ("effective_at",),
    "authorization.csv": ("effective_at",),
    "behavior_event.csv": ("occurred_at",),
    "contact_event.csv": ("occurred_at",),
    "sensitive_status.csv": ("started_at",),
    "suitability_fact.csv": ("evaluated_at",),
    "calculation_rule.csv": ("effective_at",),
}


@dataclass(frozen=True, slots=True)
class ScenarioSnapshot:
    directory: Path
    scenario: dict[str, str]
    tables: dict[str, tuple[dict[str, str], ...]]
    baseline: datetime
    rules: dict[str, dict[str, int | float | str]]

    @property
    def scenario_id(self) -> str:
        return self.scenario["scenario_id"]


class ScenarioRepository:
    """Load scenario source facts without accessing test expectations."""

    def __init__(self, scenarios_root: str | Path) -> None:
        self._root = Path(scenarios_root).resolve()

    def load(self, scenario_id: str) -> ScenarioSnapshot:
        scenario_dir = self._find_scenario_directory(scenario_id)
        source_dir = scenario_dir / "source"
        tables = {
            filename: tuple(self._read_csv(source_dir / filename))
            for filename in SOURCE_FILES
        }
        scenario_rows = tables["scenario.csv"]
        if len(scenario_rows) != 1:
            raise ScenarioDataError("scenario.csv must contain exactly one row")
        scenario = scenario_rows[0]
        if scenario.get("scenario_id") != scenario_id:
            raise ScenarioDataError("scenario id does not match the requested scenario")
        try:
            baseline = datetime.fromisoformat(scenario["baseline_at"])
        except (KeyError, ValueError) as exc:
            raise ScenarioDataError("scenario baseline_at is invalid") from exc

        self._validate_rows(scenario, tables, baseline)
        rules = self._parse_rules(scenario, tables["calculation_rule.csv"])
        return ScenarioSnapshot(
            directory=scenario_dir,
            scenario=dict(scenario),
            tables=tables,
            baseline=baseline,
            rules=rules,
        )

    def _find_scenario_directory(self, scenario_id: str) -> Path:
        if not self._root.is_dir():
            raise ScenarioNotFoundError(f"Scenario root does not exist: {self._root}")
        for candidate in sorted(self._root.iterdir()):
            scenario_file = candidate / "source" / "scenario.csv"
            if not candidate.is_dir() or not scenario_file.is_file():
                continue
            rows = self._read_csv(scenario_file)
            if len(rows) == 1 and rows[0].get("scenario_id") == scenario_id:
                return candidate
        raise ScenarioNotFoundError(f"Unknown scenario: {scenario_id}")

    @staticmethod
    def _read_csv(path: Path) -> list[dict[str, str]]:
        if not path.is_file():
            raise ScenarioDataError(f"Missing scenario source file: {path.name}")
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as file:
                reader = csv.DictReader(file)
                if reader.fieldnames is None:
                    raise ScenarioDataError(f"Scenario source has no header: {path.name}")
                return [dict(row) for row in reader]
        except UnicodeError as exc:
            raise ScenarioDataError(f"Scenario source is not valid UTF-8: {path.name}") from exc

    @staticmethod
    def _validate_rows(
        scenario: dict[str, str],
        tables: dict[str, tuple[dict[str, str], ...]],
        baseline: datetime,
    ) -> None:
        scenario_id = scenario["scenario_id"]
        customer_ids = {
            row.get("customer_id", "") for row in tables["customer_profile.csv"]
        }
        if "" in customer_ids or not customer_ids:
            raise ScenarioDataError("customer profiles must have non-empty customer ids")

        for filename, rows in tables.items():
            if filename != "scenario.csv" and not rows:
                raise ScenarioDataError(f"Scenario source is empty: {filename}")
            seen: set[str] = set()
            id_field = IDENTIFIER_FIELDS.get(filename)
            for row in rows:
                if row.get("scenario_id") != scenario_id:
                    raise ScenarioDataError(f"Scenario mismatch in {filename}")
                if id_field is not None:
                    identifier = row.get(id_field, "")
                    if not identifier or identifier in seen:
                        raise ScenarioDataError(
                            f"Missing or duplicate {id_field} in {filename}: {identifier}"
                        )
                    seen.add(identifier)
                customer_id = row.get("customer_id")
                if customer_id is not None and customer_id not in customer_ids:
                    raise ScenarioDataError(
                        f"Unknown customer {customer_id} referenced by {filename}"
                    )
                for field in TIMESTAMP_FIELDS.get(filename, ()):
                    try:
                        value = datetime.fromisoformat(row[field])
                    except (KeyError, ValueError) as exc:
                        raise ScenarioDataError(
                            f"Invalid {filename}.{field} timestamp"
                        ) from exc
                    if value > baseline:
                        raise ScenarioDataError(f"{filename}.{field} exceeds baseline")

        authorizations = {
            row["authorization_id"]: row for row in tables["authorization.csv"]
        }
        for fact in tables["family_responsibility_fact.csv"]:
            authorization = authorizations.get(fact["authorization_id"])
            if authorization is None or authorization["customer_id"] != fact["customer_id"]:
                raise ScenarioDataError(
                    "Family responsibility fact has an invalid authorization reference"
                )

    @staticmethod
    def _parse_rules(
        scenario: dict[str, str],
        rows: tuple[dict[str, str], ...],
    ) -> dict[str, dict[str, int | float | str]]:
        rules: dict[str, dict[str, int | float | str]] = {}
        for row in rows:
            if row["version"] != scenario["rule_version"]:
                raise BusinessRuleError("Calculation rule version does not match scenario")
            group = row["rule_group"]
            name = row["parameter_name"]
            if name in rules.setdefault(group, {}):
                raise BusinessRuleError(f"Duplicate rule parameter: {group}.{name}")
            raw_value = row["parameter_value"]
            value_type = row["value_type"]
            try:
                if value_type == "integer":
                    value: int | float | str = int(raw_value)
                elif value_type == "decimal":
                    value = float(raw_value)
                elif value_type == "string":
                    value = raw_value
                else:
                    raise BusinessRuleError(
                        f"Unsupported rule value type: {value_type}"
                    )
            except ValueError as exc:
                raise BusinessRuleError(
                    f"Invalid rule value: {group}.{name}={raw_value}"
                ) from exc
            rules[group][name] = value
        return rules
