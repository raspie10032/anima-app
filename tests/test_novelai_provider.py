import io
import json
import urllib.error
import zipfile

import pytest
from PIL import Image

from anima_app.config import AppPaths
from anima_app.providers import novelai

pytestmark = pytest.mark.usefixtures("nai_mock_account")


def _png_zip(size=(512, 768)) -> bytes:
    png = io.BytesIO()
    Image.new("RGB", size, "purple").save(png, format="PNG")
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("image_0.png", png.getvalue())
    return archive.getvalue()


def test_token_status_never_returns_token_value():
    status = novelai.token_status({"NAI_ACCESS_TOKEN": "top-secret"})

    assert status == {"configured": True, "source": "environment", "variable": "NAI_ACCESS_TOKEN"}
    assert "top-secret" not in json.dumps(status)


def test_primary_token_variable_wins_over_compatibility_fallback():
    environ = {"NAI_ACCESS_TOKEN": "primary", "NAI_API_TOKEN": "fallback"}

    assert novelai.get_token(environ) == "primary"
    assert novelai.token_status(environ)["variable"] == "NAI_ACCESS_TOKEN"


def test_v5_payload_uses_v4_conditioning_and_opus_limits():
    request = novelai.NovelAIRequest(prompt="1girl", width=2048, height=2048, steps=50)

    applied, payload = novelai.build_payload(request)

    assert applied.width * applied.height <= 1024 * 1024
    assert applied.steps == 28
    assert payload["model"] == "nai-diffusion-5-curated"
    assert payload["parameters"]["params_version"] == 4
    assert payload["parameters"]["v4_prompt"]["caption"]["base_caption"] == "1girl"
    assert payload["parameters"]["n_samples"] == 1


def test_generate_sends_bearer_token_and_writes_png_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("NAI_ACCESS_TOKEN", "top-secret")
    captured = {}

    def transport(url, headers, body, timeout):
        captured.update(url=url, headers=headers, payload=json.loads(body), timeout=timeout)
        return _png_zip()

    result = novelai.generate(
        novelai.NovelAIRequest(prompt="1girl", width=512, height=768, seed=7),
        paths=AppPaths(project_root=tmp_path),
        transport=transport,
    )
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))

    assert captured["headers"]["Authorization"] == "Bearer top-secret"
    assert captured["payload"]["action"] == "generate"
    assert result.output_path.is_file()
    assert manifest["provider"] == "novelai"
    assert manifest["provenance"]["provider"] == "novelai"
    assert "top-secret" not in result.manifest_path.read_text(encoding="utf-8")


def test_generate_preserves_novelai_png_bytes(tmp_path, monkeypatch):
    monkeypatch.setenv("NAI_ACCESS_TOKEN", "token")
    archive = _png_zip((512, 512))
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        expected = zipped.read("image_0.png")

    result = novelai.generate(
        novelai.NovelAIRequest(prompt="preserve bytes", width=512, height=512),
        paths=AppPaths(project_root=tmp_path),
        transport=lambda *_args: archive,
    )

    assert result.output_path.read_bytes() == expected


def test_generate_rejects_invalid_response_archive(tmp_path, monkeypatch):
    monkeypatch.setenv("NAI_ACCESS_TOKEN", "token")

    with pytest.raises(ValueError, match="valid PNG archive"):
        novelai.generate(
            novelai.NovelAIRequest(prompt="invalid archive", width=512, height=512),
            paths=AppPaths(project_root=tmp_path),
            transport=lambda *_args: b"not a zip",
        )


def test_429_retry_is_bounded_and_honors_clamped_retry_after(tmp_path, monkeypatch):
    monkeypatch.setenv("NAI_ACCESS_TOKEN", "token")
    calls = []
    delays = []
    now = [100.0]
    monkeypatch.setattr(novelai.client, "_request_coordinator", novelai.client.RequestCoordinator(lambda: now[0]))

    def sleep(delay):
        delays.append(delay)
        now[0] += delay

    def transport(url, headers, body, timeout):
        calls.append(url)
        if len(calls) == 1:
            raise urllib.error.HTTPError(url, 429, "rate limited", {"Retry-After": "999"}, None)
        return _png_zip((512, 512))

    novelai.generate(
        novelai.NovelAIRequest(prompt="retry", width=512, height=512),
        paths=AppPaths(project_root=tmp_path),
        transport=transport,
        sleep=sleep,
    )

    assert len(calls) == 2
    assert sum(delays) == pytest.approx(60.0)
    assert max(delays) <= .1


def test_dry_run_does_not_require_token(tmp_path, monkeypatch):
    monkeypatch.delenv("NAI_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("NAI_API_TOKEN", raising=False)

    result = novelai.generate(
        novelai.NovelAIRequest(prompt="dry run", width=512, height=512),
        paths=AppPaths(project_root=tmp_path),
        dry_run=True,
    )

    assert result.status == "dry_run"
    assert result.output_path is None
    assert result.manifest_path.is_file()
