"""SQLite 持久化层(design.md §20)。

单用户 demo:所有数据归到 user_id=1。连接按操作开闭,简单且线程安全
(Flask threaded=True 下 sqlite 连接不可跨线程共享)。
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, date
from pathlib import Path

DB_PATH = Path(__file__).with_name("data") / "speakmate.sqlite"
USER_ID = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL DEFAULT 1,
  scenario TEXT NOT NULL,
  difficulty INTEGER NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  duration_sec INTEGER DEFAULT 0,
  turns INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS skill_reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  user_id INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  raw_json TEXT NOT NULL,
  profile_json TEXT NOT NULL,
  overall REAL
);
CREATE TABLE IF NOT EXISTS user_skill (
  user_id INTEGER PRIMARY KEY,
  profile_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scenario_progress (
  user_id INTEGER NOT NULL,
  scenario TEXT NOT NULL,
  count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (user_id, scenario)
);
CREATE TABLE IF NOT EXISTS corrections_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL DEFAULT 1,
  session_id TEXT,
  category TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS app_settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS custom_scenarios (
  key TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  role TEXT NOT NULL,
  goal TEXT NOT NULL,
  opening TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event TEXT NOT NULL,
  payload TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
"""


@contextmanager
def _conn(db_path: Path | str = DB_PATH):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db(db_path: Path | str = DB_PATH) -> None:
    with _conn(db_path) as con:
        con.executescript(_SCHEMA)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ---------- 写入 ----------
def create_session(session_id: str, scenario: str, difficulty: int,
                   db_path: Path | str = DB_PATH) -> None:
    with _conn(db_path) as con:
        con.execute(
            "INSERT OR REPLACE INTO sessions"
            "(id, user_id, scenario, difficulty, started_at) VALUES (?,?,?,?,?)",
            (session_id, USER_ID, scenario, difficulty, _now()))


def finish_session(session_id: str, *, turns: int, raw_skills: dict,
                   profile: dict, overall: float | None,
                   correction_categories: list[str],
                   db_path: Path | str = DB_PATH) -> None:
    """会话结束:落盘 skill_report、更新 user_skill / scenario_progress / 时长。"""
    now = _now()
    with _conn(db_path) as con:
        row = con.execute(
            "SELECT started_at, scenario FROM sessions WHERE id=?",
            (session_id,)).fetchone()
        if row is None:
            return
        dur = _duration(row["started_at"], now)
        con.execute(
            "UPDATE sessions SET finished_at=?, duration_sec=?, turns=? WHERE id=?",
            (now, dur, turns, session_id))
        con.execute(
            "INSERT INTO skill_reports"
            "(session_id, user_id, created_at, raw_json, profile_json, overall)"
            " VALUES (?,?,?,?,?,?)",
            (session_id, USER_ID, now, json.dumps(raw_skills),
             json.dumps(profile), overall))
        con.execute(
            "INSERT INTO user_skill(user_id, profile_json, updated_at)"
            " VALUES (?,?,?) ON CONFLICT(user_id) DO UPDATE SET"
            " profile_json=excluded.profile_json, updated_at=excluded.updated_at",
            (USER_ID, json.dumps(profile), now))
        con.execute(
            "INSERT INTO scenario_progress(user_id, scenario, count)"
            " VALUES (?,?,1) ON CONFLICT(user_id, scenario) DO UPDATE SET"
            " count = count + 1", (USER_ID, row["scenario"]))
        con.executemany(
            "INSERT INTO corrections_log(user_id, session_id, category, created_at)"
            " VALUES (?,?,?,?)",
            [(USER_ID, session_id, c, now) for c in correction_categories])


# ---------- 埋点事件 ----------
def add_event(event: str, payload: dict | None = None,
              db_path: Path | str | None = None) -> None:
    # 调用时解析 DB_PATH(默认参数会绑定旧值,测试用 monkeypatch 改 DB_PATH 才生效)
    with _conn(db_path or DB_PATH) as con:
        con.execute(
            "INSERT INTO events(event, payload, created_at) VALUES (?,?,?)",
            (event, json.dumps(payload or {}, ensure_ascii=False), _now()))


def event_counts(db_path: Path | str = DB_PATH) -> dict[str, int]:
    with _conn(db_path) as con:
        try:
            rows = con.execute(
                "SELECT event, COUNT(*) c FROM events GROUP BY event").fetchall()
        except sqlite3.OperationalError:
            return {}
        return {r["event"]: r["c"] for r in rows}


def latency_stats(db_path: Path | str = DB_PATH) -> dict[str, dict]:
    """按 metric 聚合 'latency' 事件的 p50/p95/avg/n(真实运行 QoS)。"""
    with _conn(db_path) as con:
        try:
            rows = con.execute(
                "SELECT payload FROM events WHERE event='latency'").fetchall()
        except sqlite3.OperationalError:
            return {}
    buckets: dict[str, list[float]] = {}
    for r in rows:
        try:
            p = json.loads(r["payload"])
            buckets.setdefault(p["metric"], []).append(float(p["ms"]))
        except (ValueError, KeyError):
            continue
    out = {}
    for metric, vals in buckets.items():
        vals.sort()
        out[metric] = {
            "n": len(vals),
            "p50": _pct(vals, 50),
            "p95": _pct(vals, 95),
            "avg": round(sum(vals) / len(vals), 1),
        }
    return out


def _pct(sorted_vals: list[float], p: int) -> float:
    if not sorted_vals:
        return 0.0
    idx = min(len(sorted_vals) - 1, int(round((p / 100) * (len(sorted_vals) - 1))))
    return round(sorted_vals[idx], 1)


# ---------- 自定义场景 ----------
def add_custom_scenario(key: str, name: str, role: str, goal: str,
                        opening: str, db_path: Path | str = DB_PATH) -> None:
    with _conn(db_path) as con:
        con.execute(
            "INSERT OR REPLACE INTO custom_scenarios"
            "(key, name, role, goal, opening, created_at) VALUES (?,?,?,?,?,?)",
            (key, name, role, goal, opening, _now()))


def get_custom_scenarios(db_path: Path | str = DB_PATH) -> list[dict]:
    with _conn(db_path) as con:
        try:
            rows = con.execute(
                "SELECT key, name, role, goal, opening FROM custom_scenarios "
                "ORDER BY created_at").fetchall()
        except sqlite3.OperationalError:
            return []
        return [dict(r) for r in rows]


def delete_custom_scenario(key: str, db_path: Path | str = DB_PATH) -> None:
    with _conn(db_path) as con:
        con.execute("DELETE FROM custom_scenarios WHERE key=?", (key,))


# ---------- 设置(用户在 UI 配置的 Key 等)----------
def get_all_settings(db_path: Path | str = DB_PATH) -> dict[str, str]:
    with _conn(db_path) as con:
        try:
            rows = con.execute("SELECT key, value FROM app_settings").fetchall()
        except sqlite3.OperationalError:
            return {}
        return {r["key"]: r["value"] for r in rows}


def save_settings(values: dict[str, str], db_path: Path | str = DB_PATH) -> None:
    """非空写入/更新;空字符串表示清除该项(删除行,回落到环境变量)。"""
    now = _now()
    with _conn(db_path) as con:
        for key, val in values.items():
            if val:
                con.execute(
                    "INSERT INTO app_settings(key, value, updated_at) VALUES (?,?,?)"
                    " ON CONFLICT(key) DO UPDATE SET value=excluded.value,"
                    " updated_at=excluded.updated_at", (key, val, now))
            else:
                con.execute("DELETE FROM app_settings WHERE key=?", (key,))


def get_user_skill(db_path: Path | str = DB_PATH) -> dict | None:
    with _conn(db_path) as con:
        row = con.execute(
            "SELECT profile_json FROM user_skill WHERE user_id=?",
            (USER_ID,)).fetchone()
        return json.loads(row["profile_json"]) if row else None


def _duration(start_iso: str, end_iso: str) -> int:
    try:
        return max(0, int((datetime.fromisoformat(end_iso)
                           - datetime.fromisoformat(start_iso)).total_seconds()))
    except ValueError:
        return 0


def _streak(days: list[str]) -> int:
    """连续打卡天数:从今天往回数有训练记录的连续天数。"""
    s = {date.fromisoformat(d) for d in days if d}
    if not s:
        return 0
    today = date.today()
    # 允许从今天或昨天起算(今天还没练也不归零)
    cur = today if today in s else today.fromordinal(today.toordinal() - 1)
    if cur not in s:
        return 0
    n = 0
    while cur in s:
        n += 1
        cur = cur.fromordinal(cur.toordinal() - 1)
    return n
