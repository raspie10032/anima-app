import json
import threading
import urllib.request
from pathlib import Path

from anima_app import __version__
from anima_app.config import AppPaths
from anima_app.defaults import DEFAULT_T2I_CFG, DEFAULT_T2I_HEIGHT, DEFAULT_T2I_STEPS, DEFAULT_T2I_WIDTH
from anima_app.openapi import build_openapi_document
from anima_app.requests import MAX_CFG, MAX_GENERATION_DIMENSION, MAX_PROMPT_CHARACTERS, MAX_SAMPLING_STEPS
from anima_app.server import MAX_QUEUE_DELAY_SECONDS, MAX_QUEUE_JOBS, create_http_server


CORE_AGENT_PATHS = {
    "/api/openapi.json",
    "/api/version",
    "/api/health",
    "/api/readiness",
    "/api/checkpoints",
    "/api/loras",
    "/api/generate",
    "/api/jobs",
    "/api/jobs/{job_id}",
    "/api/jobs/{job_id}/cancel",
    "/api/progress/{progress_id}",
    "/api/manifests/{manifest_name}",
}


def _document(*, default_dry_run=False):
    return build_openapi_document(
        app_version=__version__,
        max_queue_jobs=MAX_QUEUE_JOBS,
        max_queue_delay_seconds=MAX_QUEUE_DELAY_SECONDS,
        default_dry_run=default_dry_run,
    )


def test_openapi_document_describes_core_agent_flow_and_current_limits():
    document = _document()

    assert document["openapi"] == "3.1.0"
    assert document["info"]["version"] == __version__
    assert document["servers"] == [{"url": "/", "description": "Current local Anima APP server"}]
    assert CORE_AGENT_PATHS <= document["paths"].keys()
    assert document["x-anima-agent"]["local_only"] is True
    assert document["x-anima-agent"]["idempotency_supported"] is False

    request_schema = document["components"]["schemas"]["T2IRequest"]
    assert request_schema["additionalProperties"] is False
    assert request_schema["required"] == ["prompt"]
    assert request_schema["properties"]["prompt"]["maxLength"] == MAX_PROMPT_CHARACTERS
    assert request_schema["properties"]["prompt"]["pattern"] == "\\S"
    assert request_schema["properties"]["width"] == {
        "type": "integer",
        "minimum": 8,
        "maximum": MAX_GENERATION_DIMENSION,
        "multipleOf": 8,
        "default": DEFAULT_T2I_WIDTH,
    }
    assert request_schema["properties"]["height"]["default"] == DEFAULT_T2I_HEIGHT
    assert request_schema["properties"]["steps"]["maximum"] == MAX_SAMPLING_STEPS
    assert request_schema["properties"]["steps"]["default"] == DEFAULT_T2I_STEPS
    assert request_schema["properties"]["cfg"]["maximum"] == MAX_CFG
    assert request_schema["properties"]["cfg"]["default"] == DEFAULT_T2I_CFG

    i2i_schema = document["components"]["schemas"]["I2ISettings"]
    assert i2i_schema["required"] == ["enabled"]
    assert i2i_schema["allOf"][0]["then"]["required"] == ["image_path"]
    assert i2i_schema["allOf"][0]["then"]["properties"]["image_path"]["pattern"] == "\\S"
    assert document["components"]["schemas"]["LoraConfig"]["properties"]["path"]["pattern"] == "\\S"

    queue_schema = document["components"]["schemas"]["JobEnqueueRequest"]
    assert queue_schema["properties"]["count"]["maximum"] == MAX_QUEUE_JOBS
    assert queue_schema["properties"]["delay_seconds"]["maximum"] == MAX_QUEUE_DELAY_SECONDS
    assert document["components"]["schemas"]["GenerateResult"]["properties"]["status"]["enum"] == [
        "generated",
        "dry_run",
    ]
    assert "manifest_name" in document["components"]["schemas"]["GenerateResult"]["required"]

    operation_ids = [
        operation["operationId"]
        for path_item in document["paths"].values()
        for method, operation in path_item.items()
        if method in {"get", "post", "delete"}
    ]
    assert len(operation_ids) == len(set(operation_ids))

    enqueue = document["paths"]["/api/jobs"]["post"]
    assert enqueue["requestBody"]["content"]["application/json"]["example"] == {
        "count": 1,
        "seed_mode": "fixed",
        "request": {"prompt": "anime portrait", "dry_run": True},
    }
    assert enqueue["responses"]["429"]["content"]["application/json"]["example"]["error_code"] == "queue_full"
    assert "403" in document["paths"]["/api/manifests/{manifest_name}"]["get"]["responses"]


def test_openapi_document_has_no_broken_local_schema_references():
    document = _document()
    schemas = document["components"]["schemas"]
    pending = [document]
    referenced = set()
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            if "$ref" in value:
                referenced.add(value["$ref"])
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)

    assert referenced
    assert all(reference.startswith("#/components/schemas/") for reference in referenced)
    assert {reference.rsplit("/", 1)[-1] for reference in referenced} <= schemas.keys()


def test_http_server_serves_openapi_json(tmp_path):
    server = create_http_server(
        "127.0.0.1",
        0,
        paths=AppPaths(project_root=tmp_path / "app"),
        default_dry_run=True,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/api/openapi.json"
        with urllib.request.urlopen(url, timeout=5) as response:
            document = json.loads(response.read().decode("utf-8"))

        assert response.status == 200
        assert response.headers["Content-Type"].startswith("application/json")
        assert document["info"]["version"] == __version__
        assert document["paths"]["/api/jobs"]["post"]["operationId"] == "enqueueJobs"
        assert document["components"]["schemas"]["T2IRequest"]["properties"]["dry_run"]["default"] is True

        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/api/generate",
            data=json.dumps({"prompt": "agent contract smoke"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            generated = json.loads(response.read().decode("utf-8"))

        assert generated["status"] == "dry_run"
        assert generated["manifest_name"] == Path(generated["manifest_path"]).name
    finally:
        server.shutdown()
        server.server_close()
