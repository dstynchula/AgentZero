"""Tests for Google sync prune planning."""

from agentzero.google.sync import PrunePlan


def test_prune_plan_dataclass():
    plan = PrunePlan(
        spreadsheet_title="Jobs",
        sheet_job_count=2,
        db_job_count=5,
        to_delete=["a", "b", "c"],
        missing_in_db=["x"],
    )
    assert len(plan.to_delete) == 3
    assert plan.missing_in_db == ["x"]
