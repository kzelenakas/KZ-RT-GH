from app.models import Finding, RuleError, RunResult, Severity, StructuralError
from app.persistence import RunRepository, init_db


def make_repo(tmp_path):
    return RunRepository(init_db(f"sqlite:///{tmp_path / 't.sqlite3'}"))


def sample_result() -> RunResult:
    return RunResult(
        findings=[Finding(
            rule_id="UAD1002", category="Subject Property", severity=Severity.HARD_STOP,
            message_appraiser="a", message_reviewer="r", field_path="subject.CityName",
            xpath=".../CityName", section="Subject Property",
            values={"subject.CityName": None},
            citation="UAD 3.6 Appendix H-1 v1.4, Unique ID 0100.0009, Message ID UAD1002",
        )],
        rule_errors=[RuleError(rule_id="X", error_type="unsupported_logic", detail="d")],
    )


def test_save_and_get_run(tmp_path):
    repo = make_repo(tmp_path)
    run_id = repo.save_run(
        filename="SF1.zip", file_hash="abc123", schema_version="GSE_UAD_3.6.0_v1.3",
        ruleset_version="H1-seed-phase1-deadbeef0000",
        structural_errors=[StructuralError(code="XSD", message="m", location="line 5")],
        result=sample_result(),
    )
    payload = repo.get_run(run_id)
    assert payload["filename"] == "SF1.zip"
    assert payload["counts"] == {"HardStop": 1, "Warning": 0, "Advisory": 0}
    assert payload["structural_errors"][0]["code"] == "XSD"
    assert payload["findings"][0]["rule_id"] == "UAD1002"
    assert payload["findings"][0]["values"] == {"subject.CityName": None}
    assert payload["rule_errors"][0]["error_type"] == "unsupported_logic"
    assert payload["schema_version"] == "GSE_UAD_3.6.0_v1.3"


def test_get_missing_run_returns_none(tmp_path):
    assert make_repo(tmp_path).get_run("nope") is None


def test_list_runs_newest_first(tmp_path):
    repo = make_repo(tmp_path)
    empty = RunResult()
    id1 = repo.save_run("a.zip", "h1", "s", "r", [], empty)
    id2 = repo.save_run("b.zip", "h2", "s", "r", [], empty)
    runs = repo.list_runs()
    assert [r["id"] for r in runs] == [id2, id1]
    assert runs[0]["counts"] == {"HardStop": 0, "Warning": 0, "Advisory": 0}
