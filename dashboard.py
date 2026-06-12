"""Dashboard 聚合(design.md §16)。

把 SQLite 里的会话/能力/纠错聚合成前端需要的指标:练习量、时长、连续打卡、
六维雷达、成长曲线、场景覆盖率、错误分布。
"""
from __future__ import annotations

import json
from pathlib import Path

from db import _conn, USER_ID, DB_PATH, _streak
from scenarios import SCENARIOS
from skills import DIMENSIONS


def get_dashboard(db_path: Path | str = DB_PATH) -> dict:
    with _conn(db_path) as con:
        finished = con.execute(
            "SELECT COUNT(*) n, COALESCE(SUM(duration_sec),0) dur "
            "FROM sessions WHERE user_id=? AND finished_at IS NOT NULL",
            (USER_ID,)).fetchone()

        day_rows = con.execute(
            "SELECT DISTINCT substr(finished_at,1,10) d FROM sessions "
            "WHERE user_id=? AND finished_at IS NOT NULL", (USER_ID,)).fetchall()

        skill_row = con.execute(
            "SELECT profile_json FROM user_skill WHERE user_id=?",
            (USER_ID,)).fetchone()

        growth_rows = con.execute(
            "SELECT created_at, overall, profile_json FROM skill_reports "
            "WHERE user_id=? ORDER BY id", (USER_ID,)).fetchall()

        scen_rows = con.execute(
            "SELECT scenario, count FROM scenario_progress WHERE user_id=?",
            (USER_ID,)).fetchall()

        err_rows = con.execute(
            "SELECT category, COUNT(*) c FROM corrections_log WHERE user_id=? "
            "GROUP BY category ORDER BY c DESC", (USER_ID,)).fetchall()

    current = json.loads(skill_row["profile_json"]) if skill_row else {
        d: None for d in DIMENSIONS}

    growth = [
        {"at": r["created_at"], "overall": r["overall"],
         **{k: json.loads(r["profile_json"]).get(k) for k in DIMENSIONS}}
        for r in growth_rows
    ]

    counts = {r["scenario"]: r["count"] for r in scen_rows}
    coverage = [
        {"key": k, "name": s.name, "count": counts.get(k, 0)}
        for k, s in SCENARIOS.items()
    ]

    return {
        "practice_count": finished["n"],
        "total_minutes": round(finished["dur"] / 60, 1),
        "streak": _streak([r["d"] for r in day_rows]),
        "current_skill": current,
        "growth": growth,
        "scenario_coverage": coverage,
        "covered_scenarios": sum(1 for c in coverage if c["count"] > 0),
        "total_scenarios": len(SCENARIOS),
        "error_stats": [{"category": r["category"], "count": r["c"]}
                        for r in err_rows],
    }
