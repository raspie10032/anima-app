import json

import pytest


@pytest.fixture
def nai_mock_account(monkeypatch):
    """Existing image/queue mocks also mock the new account preflight explicitly."""
    # Launcher-only CI installs pytest without the optional provider runtime.
    from anima_app.providers.novelai import client

    monkeypatch.setattr(client, "_request_coordinator", client.RequestCoordinator())
    monkeypatch.setattr(client, "_requests_subscription_transport", lambda *_args: json.dumps({
        "active": True, "tier": 3, "usage": {"percent": 100, "isNegative": False},
    }).encode())
