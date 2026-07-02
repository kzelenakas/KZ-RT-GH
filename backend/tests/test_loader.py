import json

from app.rules import load_ruleset
from tests.conftest import REPO_ROOT

SEED_PATH = REPO_ROOT / "rules" / "seed_rules.json"


def test_load_seed_ruleset():
    rules, version = load_ruleset(SEED_PATH)
    assert [r.rule_id for r in rules] == ["UAD1001", "UAD1002", "UAD1005", "UAD1007"]
    assert version.startswith("H1-seed-phase1-")
    assert len(version.split("-")[-1]) == 12  # sha256 prefix


def test_version_changes_when_content_changes(tmp_path):
    data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    p1 = tmp_path / "a.json"
    p1.write_text(json.dumps(data), encoding="utf-8")
    data["rules"][0]["enabled"] = False
    p2 = tmp_path / "b.json"
    p2.write_text(json.dumps(data), encoding="utf-8")
    _, v1 = load_ruleset(p1)
    _, v2 = load_ruleset(p2)
    assert v1 != v2


def test_unknown_fields_survive_loading(tmp_path):
    data = {"name": "x", "rules": [{
        "rule_id": "R1", "category": "C", "severity": "Advisory",
        "logic": {"type": "field_present", "field": "a"},
        "some_future_key": 42,
    }]}
    p = tmp_path / "r.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    rules, _ = load_ruleset(p)
    assert rules[0].model_dump()["some_future_key"] == 42
