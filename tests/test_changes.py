"""J1: the personal change feed surfaces audit entries affecting a person."""

from server.audit import AuditLog
from server.app import _describe_change


def test_for_person_matches_affected_fields(tmp_path):
    log = AuditLog(data_dir=tmp_path)
    log.log("boss", "assign_cover",
            {"name": "AMY", "date": "2026-07-01", "shift": "day", "covered_by": "BEA"})
    log.log("boss", "decide_vacation", {"person": "AMY", "date": "2026-07-04", "status": "approved"})
    log.log("boss", "assign_cover",
            {"name": "CASS", "date": "2026-07-02", "shift": "night", "covered_by": "DEE"})

    amy = log.for_person("AMY")
    actions = {e["action"] for e in amy}
    assert actions == {"assign_cover", "decide_vacation"}  # not CASS's event
    # BEA appears because she was the cover on AMY's shift
    assert any(e["action"] == "assign_cover" for e in log.for_person("BEA"))


def test_describe_change_first_person():
    cov = {"action": "assign_cover", "actor": "boss",
           "details": {"name": "AMY", "date": "2026-07-01", "shift": "day", "covered_by": "BEA"}}
    assert "covered by BEA" in _describe_change("AMY", cov)
    assert "cover AMY" in _describe_change("BEA", cov)

    vac = {"action": "decide_vacation", "actor": "boss",
           "details": {"person": "AMY", "date": "2026-07-04", "status": "approved"}}
    assert "vacation" in _describe_change("AMY", vac) and "approved" in _describe_change("AMY", vac)
