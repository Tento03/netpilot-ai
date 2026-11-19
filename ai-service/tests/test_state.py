from app.agent import state as st
from app.agent.state import HypStatus


def hyps():
    return st.parse_hypotheses([{"statement": "WiFi lemah"}, "DNS lambat", {"x": 1}, "", 5])


def test_new_state_defaults():
    s = st.new_state("q")
    assert s["iteration"] == 0 and s["tool_calls_used"] == 0 and s["hypotheses"] == []
    assert s["budget"].max_iterations == 6 and s["budget"].max_tool_calls == 12


def test_parse_hypotheses_ignores_malformed_and_caps():
    h = hyps()
    assert [x.id for x in h] == ["h1", "h2"] and all(x.status == HypStatus.OPEN for x in h)
    assert st.parse_hypotheses("bukan list") == []
    assert len(st.parse_hypotheses([f"h{i}" for i in range(20)])) == st.MAX_HYPOTHESES


def test_open_hypotheses_and_budget_left():
    s = st.new_state("q")
    s["hypotheses"] = hyps()
    assert len(st.open_hypotheses(s)) == 2 and st.budget_left(s)
    s["iteration"] = 6
    assert not st.budget_left(s)
    s["iteration"], s["tool_calls_used"] = 0, 12
    assert not st.budget_left(s)


def test_confirm_requires_existing_evidence():
    h = hyps()
    out, notes = st.apply_updates(h, [{"id": "h1", "status": "confirmed", "evidence_refs": []}], {"a"})
    assert out[0].status == HypStatus.OPEN and "tanpa evidence_refs" in notes[0]
    out, notes = st.apply_updates(h, [{"id": "h1", "status": "confirmed", "evidence_refs": ["zzz"]}], {"a"})
    assert out[0].status == HypStatus.OPEN and "tidak ada" in notes[0]
    out, notes = st.apply_updates(h, [{"id": "h1", "status": "rejected", "evidence_refs": ["a"]}], {"a"})
    assert out[0].status == HypStatus.REJECTED and out[0].evidence_refs == ["a"] and notes == []


def test_settled_hypothesis_is_not_changed_again():
    h = hyps()
    h, _ = st.apply_updates(h, [{"id": "h1", "status": "rejected", "evidence_refs": ["a"]}], {"a"})
    out, notes = st.apply_updates(h, [{"id": "h1", "status": "confirmed", "evidence_refs": ["a"]}], {"a"})
    assert out[0].status == HypStatus.REJECTED and "tidak diubah" in notes[0]


def test_bad_updates_are_noted_not_crashing():
    h = hyps()
    out, notes = st.apply_updates(h, [{"id": "h9", "status": "open"}, {"id": "h1", "status": "maybe"},
                                      "x", {"id": "h1", "status": "open", "evidence_refs": "a"}], set())
    assert [x.status for x in out] == [HypStatus.OPEN, HypStatus.OPEN] and len(notes) == 4
    assert st.apply_updates(h, "bukan list", set())[1] == ["updates bukan list"]


def test_apply_updates_does_not_mutate_input():
    h = hyps()
    st.apply_updates(h, [{"id": "h1", "status": "rejected", "evidence_refs": ["a"]}], {"a"})
    assert h[0].status == HypStatus.OPEN


def test_canonical_call_is_order_independent():
    assert st.canonical_call("ping_host", {"host": "a", "count": 3}) == \
        st.canonical_call("ping_host", {"count": 3, "host": "a"})