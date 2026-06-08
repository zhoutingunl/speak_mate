"""六维能力模型单测(design.md §14)。"""
from skills import SkillProfile, update_profile, derive_raw_skills, DIMENSIONS


def test_cold_start_takes_raw():
    prev = SkillProfile()  # 全 None
    raw = SkillProfile(grammar=80, vocabulary=70)
    out = update_profile(prev, raw)
    assert out.grammar == 80
    assert out.vocabulary == 70
    assert out.pronunciation is None  # raw 也无 → 保持 None


def test_ewma_blends():
    prev = SkillProfile(grammar=60)
    raw = SkillProfile(grammar=100)
    out = update_profile(prev, raw, alpha=0.3)
    assert out.grammar == round(0.3 * 100 + 0.7 * 60, 1)  # 72.0


def test_none_raw_keeps_prev():
    prev = SkillProfile(grammar=90, pronunciation=85)
    raw = SkillProfile(grammar=50)  # pronunciation None
    out = update_profile(prev, raw)
    assert out.pronunciation == 85  # 本次无声学数据,保留历史
    assert out.grammar != 90


def test_derive_leaves_acoustic_dims_none():
    raw = derive_raw_skills(["I really enjoyed the trip to Japan last summer."],
                            correction_count=0, expression_issue_count=0,
                            completed=True)
    assert raw.pronunciation is None and raw.fluency is None
    assert raw.grammar is not None and raw.vocabulary is not None


def test_more_errors_lower_grammar():
    utts = ["a b c d e", "f g h i j"]
    clean = derive_raw_skills(utts, correction_count=0,
                              expression_issue_count=0, completed=True)
    noisy = derive_raw_skills(utts, correction_count=6,
                              expression_issue_count=0, completed=True)
    assert noisy.grammar < clean.grammar


def test_empty_utterances():
    raw = derive_raw_skills([], correction_count=0,
                            expression_issue_count=0, completed=False)
    assert all(getattr(raw, d) is None for d in DIMENSIONS)


def test_scores_in_range():
    raw = derive_raw_skills(["hello world"] * 5, correction_count=2,
                            expression_issue_count=1, completed=True)
    for d in ("grammar", "vocabulary", "expression", "communication"):
        v = getattr(raw, d)
        assert 0 <= v <= 100
