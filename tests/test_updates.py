import urllib.error

from anima_app.updates import (
    APP_REPOSITORY,
    APP_REPOSITORY_URL,
    check_github_update,
    compare_versions,
    version_payload,
)


def test_version_payload_reports_current_app_metadata():
    payload = version_payload()

    assert payload["version"] == "0.2.0"
    assert payload["repository"] == APP_REPOSITORY
    assert payload["repository_url"] == APP_REPOSITORY_URL


def test_compare_versions_handles_v_prefix_and_missing_patch():
    assert compare_versions("0.1.0", "v0.1.1") < 0
    assert compare_versions("v0.2", "0.1.9") > 0
    assert compare_versions("v0.1.0", "0.1.0") == 0


def test_check_github_update_uses_latest_release():
    calls = []

    def fake_fetch(url):
        calls.append(url)
        return {"tag_name": "v0.1.1", "html_url": "https://github.com/raspie10032/anima-app/releases/tag/v0.1.1"}

    payload = check_github_update(current_version="0.1.0", fetch_json=fake_fetch)

    assert payload["status"] == "update_available"
    assert payload["current_version"] == "0.1.0"
    assert payload["latest_version"] == "v0.1.1"
    assert payload["latest_url"] == "https://github.com/raspie10032/anima-app/releases/tag/v0.1.1"
    assert payload["latest_source"] == "release"
    assert calls == ["https://api.github.com/repos/raspie10032/anima-app/releases/latest"]


def test_check_github_update_falls_back_to_tags_when_no_release_exists():
    calls = []

    def fake_fetch(url):
        calls.append(url)
        if url.endswith("/releases/latest"):
            raise urllib.error.HTTPError(url, 404, "Not Found", hdrs=None, fp=None)
        return [{"name": "v0.1.0", "zipball_url": "https://api.github.com/tag.zip"}]

    payload = check_github_update(current_version="0.1.0", fetch_json=fake_fetch)

    assert payload["status"] == "up_to_date"
    assert payload["latest_version"] == "v0.1.0"
    assert payload["latest_url"] == "https://github.com/raspie10032/anima-app/releases/tag/v0.1.0"
    assert payload["latest_source"] == "tag"
    assert calls == [
        "https://api.github.com/repos/raspie10032/anima-app/releases/latest",
        "https://api.github.com/repos/raspie10032/anima-app/tags",
    ]


def test_check_github_update_reports_network_failure_without_raising():
    def fake_fetch(url):
        raise OSError("network down")

    payload = check_github_update(current_version="0.1.0", fetch_json=fake_fetch)

    assert payload["status"] == "update_check_failed"
    assert payload["current_version"] == "0.1.0"
    assert payload["latest_version"] is None
    assert "network down" in payload["error"]
