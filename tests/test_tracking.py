"""埋点 + 延迟统计单测(临时 sqlite)。"""
import json

import db
import tracking


def test_add_event_and_counts(tmp_path, monkeypatch):
    p = tmp_path / "e.sqlite"
    db.init_db(p)
    monkeypatch.setattr(db, "DB_PATH", p)
    tracking.track("session_start", {"scenario": "interview"})
    tracking.track("session_start", {"scenario": "restaurant"})
    tracking.track("ai_reply", {})
    counts = db.event_counts(p)
    assert counts["session_start"] == 2 and counts["ai_reply"] == 1


def test_latency_stats(tmp_path, monkeypatch):
    p = tmp_path / "e.sqlite"
    db.init_db(p)
    monkeypatch.setattr(db, "DB_PATH", p)
    for ms in (100, 200, 300, 400, 500):
        tracking.mark("llm_first_token", ms)
    st = db.latency_stats(p)["llm_first_token"]
    assert st["n"] == 5
    assert st["p50"] == 300
    assert 100 <= st["avg"] <= 500
    assert st["p95"] >= st["p50"]


def test_timed_records_latency(tmp_path, monkeypatch):
    p = tmp_path / "e.sqlite"
    db.init_db(p)
    monkeypatch.setattr(db, "DB_PATH", p)
    with tracking.timed("unit_test_metric"):
        pass
    rows = db.latency_stats(p)
    assert "unit_test_metric" in rows and rows["unit_test_metric"]["n"] == 1


def test_track_failure_is_silent(monkeypatch):
    # add_event 抛错时 track 不应向上抛(埋点不影响业务)
    monkeypatch.setattr(db, "add_event",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    tracking.track("ai_reply", {})  # 不抛即通过
