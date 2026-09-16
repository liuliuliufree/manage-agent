"""Read and validate immutable business-data snapshots."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .errors import BusinessRuleError, DataSourceError, DataSourceNotFoundError


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
class BusinessDataSnapshot:
    directory: Path
    metadata: dict[str, str]
    tables: dict[str, tuple[dict[str, str], ...]]
    baseline: datetime
    rules: dict[str, dict[str, int | float | str]]

    @property
    def data_source_id(self) -> str:
        """Stable identifier exposed to agents and application callers."""
        return self.metadata["scenario_id"]


class BusinessDataRepository:
    """Load versioned business facts without accessing test expectations."""

    def __init__(self, data_root: str | Path) -> None:
        self._root = Path(data_root).resolve()

    def load(self, data_source_id: str) -> BusinessDataSnapshot:
        data_dir = self._find_data_directory(data_source_id)
        source_dir = data_dir / "source"
        tables = {
            filename: tuple(self._read_csv(source_dir / filename))
            for filename in SOURCE_FILES
        }
        metadata_rows = tables["scenario.csv"]
        if len(metadata_rows) != 1:
            raise DataSourceError("scenario.csv must contain exactly one row")
        metadata = metadata_rows[0]
        if metadata.get("scenario_id") != data_source_id:
            raise DataSourceError("data source id does not match the requested snapshot")
        try:
            baseline = datetime.fromisoformat(metadata["baseline_at"])
        except (KeyError, ValueError) as exc:
            raise DataSourceError("scenario baseline_at is invalid") from exc

        self._validate_rows(metadata, tables, baseline)
        rules = self._parse_rules(metadata, tables["calculation_rule.csv"])
        return BusinessDataSnapshot(
            directory=data_dir,
            metadata=dict(metadata),
            tables=tables,
            baseline=baseline,
            rules=rules,
        )

    def _find_data_directory(self, data_source_id: str) -> Path:
        if not self._root.is_dir():
            raise DataSourceNotFoundError(f"Data source root does not exist: {self._root}")
        for candidate in sorted(self._root.iterdir()):
            metadata_file = candidate / "source" / "scenario.csv"
            if not candidate.is_dir() or not metadata_file.is_file():
                continue
            rows = self._read_csv(metadata_file)
            if len(rows) == 1 and rows[0].get("scenario_id") == data_source_id:
                return candidate
        raise DataSourceNotFoundError(f"Unknown data source: {data_source_id}")

    @staticmethod
    def _read_csv(path: Path) -> list[dict[str, str]]:
        if not path.is_file():
            raise DataSourceError(f"Missing source file: {path.name}")
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as file:
                reader = csv.DictReader(file)
                if reader.fieldnames is None:
                    raise DataSourceError(f"Source file has no header: {path.name}")
                return [dict(row) for row in reader]
        except UnicodeError as exc:
            raise DataSourceError(f"Source file is not valid UTF-8: {path.name}") from exc

    @staticmethod
    def _validate_rows(
        metadata: dict[str, str],
        tables: dict[str, tuple[dict[str, str], ...]],
        baseline: datetime,
    ) -> None:
        source_id = metadata["scenario_id"]
        customer_ids = {
            row.get("customer_id", "") for row in tables["customer_profile.csv"]
        }
        if "" in customer_ids or not customer_ids:
            raise DataSourceError("customer profiles must have non-empty customer ids")

        for filename, rows in tables.items():
            if filename != "scenario.csv" and not rows:
                raise DataSourceError(f"Source file is empty: {filename}")
            seen: set[str] = set()
            id_field = IDENTIFIER_FIELDS.get(filename)
            for row in rows:
                if row.get("scenario_id") != source_id:
                    raise DataSourceError(f"Data source mismatch in {filename}")
                if id_field is not None:
                    identifier = row.get(id_field, "")
                    if not identifier or identifier in seen:
                        raise DataSourceError(
                            f"Missing or duplicate {id_field} in {filename}: {identifier}"
                        )
                    seen.add(identifier)
                customer_id = row.get("customer_id")
                if customer_id is not None and customer_id not in customer_ids:
                    raise DataSourceError(
                        f"Unknown customer {customer_id} referenced by {filename}"
                    )
                for field in TIMESTAMP_FIELDS.get(filename, ()):
                    try:
                        value = datetime.fromisoformat(row[field])
                    except (KeyError, ValueError) as exc:
                        raise DataSourceError(
                            f"Invalid {filename}.{field} timestamp"
                        ) from exc
                    if value > baseline:
                        raise DataSourceError(f"{filename}.{field} exceeds baseline")

        authorizations = {
            row["authorization_id"]: row for row in tables["authorization.csv"]
        }
        for fact in tables["family_responsibility_fact.csv"]:
            authorization = authorizations.get(fact["authorization_id"])
            if authorization is None or authorization["customer_id"] != fact["customer_id"]:
                raise DataSourceError(
                    "Family responsibility fact has an invalid authorization reference"
                )

    @staticmethod
    def _parse_rules(
        metadata: dict[str, str],
        rows: tuple[dict[str, str], ...],
    ) -> dict[str, dict[str, int | float | str]]:
        rules: dict[str, dict[str, int | float | str]] = {}
        for row in rows:
            if row["version"] != metadata["rule_version"]:
                raise BusinessRuleError(
                    "Calculation rule version does not match the data source"
                )
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
