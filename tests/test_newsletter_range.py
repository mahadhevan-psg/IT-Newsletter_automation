"""The studio's date range: only entries dated inside the chosen range are listed and used for the newsletter."""
import os
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend import app as studio  # noqa: E402
from database import db_manager  # noqa: E402


def test_dates_are_read_whatever_way_the_form_wrote_them():
    d = db_manager.entry_date
    assert d({"event_date": "2026-03-15"}) == "2026-03-15" and d({"event_date": "15/03/2026"}) == "2026-03-15"
    assert d({"event_date": "March 2026"}) == "2026-03-01" and d({"event_date": ""}) is None and d({"event_date": "soon"}) is None


def test_range_includes_both_ends_and_drops_undated_entries_only_when_a_range_is_set():
    r = db_manager.in_date_range
    e = {"event_date": "2026-03-15"}
    assert r(e, None, None) and r({"event_date": ""}, None, None)                       # no range: everything counts
    assert r(e, "2026-03-15", "2026-03-15") and r(e, "2026-03-01", None) and r(e, None, "2026-03-31")
    assert not r(e, "2026-03-16", None) and not r(e, None, "2026-03-14") and not r({"event_date": ""}, "2026-01-01", None)


def test_entries_and_documents_use_only_the_chosen_range(tmp_path, monkeypatch):
    monkeypatch.setattr(db_manager, "DB_PATH", str(tmp_path / "news.db"))
    db_manager.init_db()
    issue = db_manager.get_all_issues()[0]["issue_id"]
    sec = db_manager.get_sections_and_categories()[0]
    mk = lambda title, date: db_manager.create_canonical_entry({
        "issue_id": issue, "section_id": sec["section_id"], "category_id": (sec.get("subcategories") or [{}])[0].get("category_id"), "title": title, "event_date": date,
        "author_or_person": "A", "organization_or_venue": "V", "description": "d", "approval_status": "Approved"})
    for t, d in (("Jan", "2026-01-10"), ("Mar", "15/03/2026"), ("May", "2026-05-20"), ("None", "")):
        mk(t, d)
    titles = lambda **kw: sorted(e["title"] for e in db_manager.get_entries(issue_id=issue, **kw))
    assert titles() == ["Jan", "Mar", "May", "None"]
    assert titles(date_from="2026-02-01", date_to="2026-04-30") == ["Mar"]
    assert titles(date_from="2026-03-01") == ["Mar", "May"] and titles(date_to="2026-03-31") == ["Jan", "Mar"]
    # the list the studio pages get carries each entry's date in one format
    assert {e["title"]: e["date_iso"] for e in studio.list_entries(issue_id=issue)} == {"Jan": "2026-01-10", "Mar": "2026-03-15", "May": "2026-05-20", "None": None}
    assert [e["title"] for e in studio.list_entries(issue_id=issue, date_from="2026-05-01", date_to="2026-05-31")] == ["May"]


def test_a_bad_range_is_refused():
    for a, b in (("2026-05-01", "2026-01-01"), ("1/2/2026", None), (None, "tomorrow")):
        with pytest.raises(HTTPException) as e:
            studio._check_range(a, b)
        assert e.value.status_code == 400
    studio._check_range(None, None)
    studio._check_range("2026-01-01", "2026-01-01")


def test_entries_are_approved_by_default_and_only_a_rejection_keeps_them_out(tmp_path, monkeypatch):
    monkeypatch.setattr(db_manager, "DB_PATH", str(tmp_path / "news.db"))
    db_manager.init_db()
    issue = db_manager.get_all_issues()[0]["issue_id"]
    sec = db_manager.get_sections_and_categories()[0]
    base = {"issue_id": issue, "section_id": sec["section_id"], "category_id": (sec.get("subcategories") or [{}])[0].get("category_id"), "title": "T", "event_date": "2026-03-15", "author_or_person": "A", "organization_or_venue": "V", "description": "d"}
    new = db_manager.create_canonical_entry(dict(base))                                   # nothing said about approval: it is in
    assert [e["approval_status"] for e in db_manager.get_entries(issue_id=issue)] == ["Approved"]
    db_manager.update_entry_status(new, "Rejected", rejection_reason="Not this time")
    assert db_manager.get_entries(issue_id=issue, approval_status="Approved") == []
    db_manager.update_entry_status(new, "Approved")
    assert len(db_manager.get_entries(issue_id=issue, approval_status="Approved")) == 1
    # entries left as Draft / Reviewed by the old workflow count as approved after start-up; rejected ones stay rejected
    a = db_manager.create_canonical_entry({**base, "approval_status": "Draft"})
    b = db_manager.create_canonical_entry({**base, "approval_status": "Reviewed"})
    c = db_manager.create_canonical_entry({**base, "approval_status": "Rejected"})
    db_manager.init_db()
    status = {e["entry_id"]: e["approval_status"] for e in db_manager.get_entries(issue_id=issue)}
    assert status[a] == status[b] == "Approved" and status[c] == "Rejected"
