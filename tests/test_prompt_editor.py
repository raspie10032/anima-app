import copy
import http.client
import json
import threading

import pytest

from anima_app.config import AppPaths
from anima_app.prompt_routing import adapt_editor, route_text
from anima_app.server import create_http_server


def test_editor_converts_every_field_and_submission_does_not_double_weights():
    payload = {"source": "auto", "target": "naiv4", "texts": [
        r"(no lineart:2), (@alpha, artist:beta:0.85), (@alt \(example\):0.95)",
        "(blur:1.2)", "(blue eyes:1.3)", "(red eyes:0.8)", "(@gamma:0.7)", "",
    ]}
    original = copy.deepcopy(payload)
    result = adapt_editor(payload)
    assert payload == original
    assert result["texts"] == [
        "2::no lineart ::, 0.85::artist:alpha, artist:beta ::, 0.95::artist:alt (example) ::",
        "1.2::blur ::", "1.3::blue eyes ::", "0.8::red eyes ::", "0.7::artist:gamma ::", "",
    ]
    assert all(route_text(text, result["source"], "naiv4")[0] == text for text in result["texts"])
    back = adapt_editor({
        "source": result["source"], "target": "comfyui", "texts": result["texts"]})
    assert "(@alt \\(example\\):0.95)" in back["texts"][0]
    assert back["texts"][2] == "(blue eyes:1.3)"


@pytest.mark.parametrize("source,text", [
    ("native", "(artist:alpha:1.2)"),
    ("comfyui", "(@alpha:1.2), {red coat|blue coat}"),
    ("auto", "(portrait:1.2), __outfit__"),
])
def test_native_and_unexpanded_templates_preserve_source(source, text):
    result = adapt_editor({"source": source, "target": "naiv4", "texts": [text, "(blur:1.1)"]})
    assert result["texts"] == [text, "(blur:1.1)"]
    assert result["source"] == source


def test_legacy_nai_approximates_with_notice_but_rejects_lost_weights():
    result = adapt_editor({"source": "auto", "target": "oldnai", "texts": ["(@alpha:1.2)", ""]})
    assert result["texts"][0] == "{{{{artist:alpha}}}}"
    assert result["warnings"]
    with pytest.raises(ValueError):
        adapt_editor({"source": "auto", "target": "oldnai", "texts": ["(portrait:0)", ""]})


@pytest.mark.parametrize("change", [
    {"texts": "bad"}, {"texts": ["a"]}, {"texts": ["a"] * 48},
    {"texts": [None, ""]}, {"texts": ["x" * 32769, ""]}, {"source": "invalid"},
    {"target": "invalid"}, {"token": "secret"}, {"texts": ["(portrait:8)", ""]},
    {"texts": ["(portrait:1.2), 1.1::hat::", ""]},
])
def test_editor_rejects_invalid_or_lossy_input(change):
    with pytest.raises(ValueError):
        adapt_editor({"source": "auto", "target": "naiv4", "texts": ["a", ""], **change})


def test_editor_http_is_local_only_and_requires_no_generation_settings(tmp_path):
    server = create_http_server("127.0.0.1", 0, paths=AppPaths(tmp_path), default_dry_run=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        client = http.client.HTTPConnection(*server.server_address)
        body = json.dumps({"source": "auto", "target": "naiv4", "texts": ["(@alpha:1.2)", ""]})
        client.request("POST", "/api/prompts/adapt-editor", body, {"Content-Type": "application/json"})
        response = client.getresponse()
        assert response.status == 200
        assert json.loads(response.read())["texts"][0] == "1.2::artist:alpha ::"
        client.request("POST", "/api/prompts/adapt-editor", body,
                       {"Content-Type": "application/json", "Origin": "https://untrusted.invalid"})
        response = client.getresponse()
        assert response.status == 403
        response.read()
        client.close()
    finally:
        server.shutdown()
        server.server_close()
