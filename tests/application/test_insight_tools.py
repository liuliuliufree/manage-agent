import hashlib
import json
import shutil
import unittest
from pathlib import Path

from src.application.insight_tools import InsightToolConfig, build_insight_tools


ROOT = Path(__file__).resolve().parents[2]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


class InsightToolsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tools = build_insight_tools(InsightToolConfig.from_repository(ROOT))
        cls.search, cls.read, cls.aggregate = tools

    def test_knowledge_alias_search_and_exact_read(self):
        alias = self.search.handler({"resource_names": ["御享金越年金"], "terms": ["领取方式"], "limit": 10})
        formal = self.search.handler({"resource_names": ["平安御享金越年金保险（分红型）"], "terms": ["领取方式"], "limit": 10})
        self.assertEqual(alias["status"], "ok")
        self.assertEqual([item["doc_id"] for item in alias["data"]["matches"]], [item["doc_id"] for item in formal["data"]["matches"]])
        hit = alias["data"]["matches"][0]
        result = self.read.handler({"doc_id": hit["doc_id"], "document_sha256": hit["document_sha256"], "line_start": hit["line_start"], "line_end": hit["line_end"]})
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"]["text"].splitlines()[0], hit["excerpt"].splitlines()[0])

    def test_knowledge_rejects_unknown_and_changed_sources(self):
        unknown = self.search.handler({"resource_names": ["does-not-exist"], "terms": ["领取"]})
        self.assertEqual(unknown["error"]["code"], "RESOURCE_NOT_FOUND")
        hit = self.search.handler({"terms": ["领取"], "limit": 1})["data"]["matches"][0]
        changed = self.read.handler({"doc_id": hit["doc_id"], "document_sha256": "0" * 64, "line_start": 1, "line_end": 1})
        self.assertEqual(changed["error"]["code"], "SOURCE_CHANGED")

    def test_aggregate_baseline_and_same_event_filters(self):
        result = self.aggregate.handler({
            "source_id": "customer_behaviors",
            "time_range": {"start": "2026-06-24T00:00:00+08:00", "end": "2026-09-22T00:00:00+08:00"},
            "group_by": ["topic_code"], "metrics": ["event_count", "distinct_customers"],
        })
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"]["totals"], {"event_count": 105, "distinct_customers": 40})
        self.assertEqual(sum(row["distinct_customers"] for row in result["data"]["rows"]), 44)

        explicit = self.aggregate.handler({
            "source_id": "customer_behaviors",
            "time_range": {"start": "2026-06-24T00:00:00+08:00", "end": "2026-09-22T00:00:00+08:00"},
            "filters": [{"field": "statement_kind", "op": "eq", "value": "explicit_interest"}],
            "group_by": ["topic_code"], "metrics": ["distinct_customers"],
        })
        self.assertEqual(explicit["data"]["totals"], {"distinct_customers": 15})
        self.assertEqual({row["topic_code"]: row["distinct_customers"] for row in explicit["data"]["rows"]}, {
            "retirement_income": 8, "family_protection": 4, "liquidity_planning": 2, "dividend_understanding": 1,
        })

        same_event = self.aggregate.handler({
            "source_id": "customer_behaviors",
            "time_range": {"start": "2026-06-24T00:00:00+08:00", "end": "2026-09-22T00:00:00+08:00"},
            "filters": [
                {"field": "topic_code", "op": "eq", "value": "retirement_income"},
                {"field": "event_type", "op": "eq", "value": "consultation"},
            ], "metrics": ["distinct_customers"],
        })
        self.assertEqual(same_event["data"]["totals"], {"distinct_customers": 9})

    def test_source_variant_changes_counts_without_changing_tool_code(self):
        directory = ROOT / ".test-insight-variant"
        target = directory / "data"
        if directory.exists():
            shutil.rmtree(directory)
        try:
            shutil.copytree(ROOT / "data", target)
            behavior_path = target / "client" / "behaviors.jsonl"
            rows = [json.loads(line) for line in behavior_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            extra = dict(rows[0])
            extra.update(event_id="VARIANT_EVENT", source_record_id="VARIANT_SOURCE", occurred_at="2026-09-21T10:00:00+08:00")
            rows.append(extra)
            behavior_path.write_text("\n".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) for row in rows) + "\n", encoding="utf-8")
            manifest_path = target / "client" / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["file_sha256"]["client/behaviors.jsonl"] = _sha256(behavior_path)
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            tools = build_insight_tools(InsightToolConfig(target / "client", target / "product"))
            result = tools[2].handler({
                "source_id": "customer_behaviors",
                "time_range": {"start": "2026-06-24T00:00:00+08:00", "end": "2026-09-22T00:00:00+08:00"},
                "metrics": ["event_count", "distinct_customers"],
            })
            self.assertEqual(result["data"]["totals"], {"event_count": 106, "distinct_customers": 40})
        finally:
            if directory.exists():
                shutil.rmtree(directory)

    def test_allowlist_and_denominator_rules(self):
        profiles = self.aggregate.handler({"source_id": "customer_profiles", "group_by": ["age_band"], "metrics": ["distinct_customers"]})
        self.assertEqual({row["age_band"]: row["distinct_customers"] for row in profiles["data"]["rows"]}, {"25-34": 8, "35-44": 12, "45-54": 14, "55-64": 10, "65-74": 6})
        unsupported = self.aggregate.handler({"source_id": "customer_profiles", "filters": [{"field": "topic_code", "op": "eq", "value": "retirement_income"}], "metrics": ["distinct_customers"]})
        self.assertEqual(unsupported["error"]["code"], "UNSUPPORTED_FIELD")
        forbidden = self.search.handler({"terms": ["领取"], "path": "C:\\secret.txt"})
        self.assertEqual(forbidden["error"]["code"], "INVALID_ARGUMENT")


if __name__ == "__main__":
    unittest.main()
