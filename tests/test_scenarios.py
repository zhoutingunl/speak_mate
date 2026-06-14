"""自定义场景:注册表与持久化单测。"""
import pytest

import db
from scenarios import SCENARIOS, Scenario, get_scenario, register, remove


def test_register_get_remove():
    sc = Scenario(key="custom_t", name="测试场景", role="a tester",
                  goal="practice", opening="hi", custom=True)
    register(sc)
    assert get_scenario("custom_t").custom is True
    remove("custom_t")
    assert "custom_t" not in SCENARIOS


def test_builtin_not_removable():
    with pytest.raises(ValueError):
        remove("interview")


def test_remove_unknown():
    with pytest.raises(ValueError):
        remove("custom_nope")


def test_db_custom_scenarios_roundtrip(tmp_path):
    p = tmp_path / "s.sqlite"
    db.init_db(p)
    db.add_custom_scenario("custom_a", "机场值机", "a check-in agent",
                           "practice check-in", "Hello, your passport please?", p)
    rows = db.get_custom_scenarios(p)
    assert len(rows) == 1 and rows[0]["key"] == "custom_a"
    assert rows[0]["name"] == "机场值机"
    # 可作为 Scenario 还原
    sc = Scenario(custom=True, **rows[0])
    assert "check-in agent" in sc.system_prompt(2)
    db.delete_custom_scenario("custom_a", p)
    assert db.get_custom_scenarios(p) == []
