"""持久化 + Dashboard 聚合单测(用临时 sqlite,不碰真实库)。"""
import pytest

import db as dbmod
from dashboard import get_dashboard
from db import (create_session, finish_session, get_user_skill, init_db, _streak)


@pytest.fixture
def tmpdb(tmp_path):
    return tmp_path / "t.sqlite"


def _finish(path, sid, scenario, raw, profile, overall, cats):
    create_session(sid, scenario, 2, db_path=path)
    finish_session(sid, turns=4, raw_skills=raw, profile=profile,
                   overall=overall, correction_categories=cats, db_path=path)


def test_persist_and_aggregate(tmpdb):
    init_db(tmpdb)
    _finish(tmpdb, "s1", "interview",
            {"grammar": 80}, {"grammar": 80, "vocabulary": 70, "fluency": None},
            75.0, ["grammar", "expression", "grammar"])
    _finish(tmpdb, "s2", "restaurant",
            {"grammar": 90}, {"grammar": 86, "vocabulary": 74}, 80.0, ["tense"])

    d = get_dashboard(tmpdb)
    assert d["practice_count"] == 2
    assert d["covered_scenarios"] == 2
    assert d["current_skill"]["grammar"] == 86  # 最近一次写入的累计画像
    assert len(d["growth"]) == 2
    assert d["growth"][-1]["overall"] == 80.0
    # 错误分布:grammar 出现 2 次
    errs = {e["category"]: e["count"] for e in d["error_stats"]}
    assert errs["grammar"] == 2 and errs["tense"] == 1


def test_user_skill_roundtrip(tmpdb):
    init_db(tmpdb)
    assert get_user_skill(tmpdb) is None
    _finish(tmpdb, "s1", "interview", {"grammar": 80},
            {"grammar": 80}, 80.0, [])
    assert get_user_skill(tmpdb)["grammar"] == 80


def test_scenario_coverage_lists_all(tmpdb):
    init_db(tmpdb)
    _finish(tmpdb, "s1", "interview", {}, {"grammar": 80}, 80.0, [])
    d = get_dashboard(tmpdb)
    keys = {c["key"]: c["count"] for c in d["scenario_coverage"]}
    assert keys["interview"] == 1
    assert keys["restaurant"] == 0  # 未练的场景也列出,count=0


def test_empty_dashboard(tmpdb):
    init_db(tmpdb)
    d = get_dashboard(tmpdb)
    assert d["practice_count"] == 0
    assert d["growth"] == []
    assert all(v is None for v in d["current_skill"].values())


def test_streak():
    from datetime import date, timedelta
    today = date.today().isoformat()
    yest = (date.today() - timedelta(days=1)).isoformat()
    gap = (date.today() - timedelta(days=5)).isoformat()
    assert _streak([today, yest]) == 2
    assert _streak([yest]) == 1            # 昨天起算不归零
    assert _streak([gap]) == 0
    assert _streak([]) == 0
