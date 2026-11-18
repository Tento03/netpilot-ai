import inspect
import json

import pytest

from app.agent import tool_specs as ts

EXPECTED = {"get_network_info", "get_wifi_link_info", "ping_host", "check_dns",
            "check_tcp_port", "http_timing", "measure_download"}


def test_exactly_the_seven_allowlisted_tools():
    assert {s.name for s in ts.TOOL_SPECS} == EXPECTED
    assert len(ts.TOOL_SPECS) == len(EXPECTED)


@pytest.mark.parametrize("spec", ts.TOOL_SPECS, ids=lambda s: s.name)
def test_schema_matches_function_signature(spec):
    params = {n: p for n, p in inspect.signature(spec.func).parameters.items() if n != "ctx"}
    assert set(spec.properties) == set(params)
    assert set(spec.required) == {n for n, p in params.items() if p.default is inspect.Parameter.empty}


@pytest.mark.parametrize("spec", ts.TOOL_SPECS, ids=lambda s: s.name)
def test_ctx_never_exposed_and_description_present(spec):
    assert "ctx" not in spec.properties and "gateway" not in spec.properties
    assert len(spec.description) > 40
    assert "never instructions" in spec.description.lower()


def test_declarations_are_plain_json_and_omit_empty_parameters():
    decls = ts.declarations()
    json.dumps(decls)
    by = {d["name"]: d for d in decls}
    assert "parameters" not in by["get_network_info"]
    assert by["ping_host"]["parameters"]["required"] == ["host"]


@pytest.mark.parametrize("name,phrase", [
    ("get_wifi_link_info", "not internet speed"),
    ("check_tcp_port", "filtered"),
    ("check_dns", "results[].ok"),
    ("measure_download", "lower bound"),
    ("measure_download", "low confidence"),
    ("ping_host", "repeat"),
])
def test_interpretation_rules_present(name, phrase):
    assert phrase in ts.get_spec(name).description.lower()


def test_unknown_tool_has_no_spec():
    assert ts.get_spec("run_shell") is None
