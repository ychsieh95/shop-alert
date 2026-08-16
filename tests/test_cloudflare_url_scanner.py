import json
from urllib.error import HTTPError


def test_cloudflare_url_scanner_submits_unlisted_scan_and_polls(monkeypatch):
    from app import cloudflare_url_scanner as scanner

    scan_id = "182bd5e5-6e1a-4fe4-a799-aa6d9a6ab26e"
    requests = []
    responses = [
        {"uuid": scan_id},
        HTTPError("https://api.example/result", 404, "pending", {}, None),
        {
            "task": {"success": True},
            "verdicts": {
                "overall": {
                    "malicious": False,
                    "categories": ["Technology"],
                    "tags": [],
                }
            },
        },
    ]

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(self.payload).encode()

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return FakeResponse(response)

    monkeypatch.setattr(scanner, "urlopen", fake_urlopen)
    monkeypatch.setattr(scanner.time, "sleep", lambda _seconds: None)

    verdict = scanner.scan_url(
        "https://example.com/article",
        account_id="account-id",
        api_token="secret-token",
        poll_interval_seconds=10,
    )

    assert verdict.malicious is False
    assert verdict.categories == ("Technology",)
    assert requests[0][0].get_method() == "POST"
    assert json.loads(requests[0][0].data) == {
        "url": "https://example.com/article",
        "visibility": "Unlisted",
    }
    assert requests[0][0].get_header("Authorization") == "Bearer secret-token"
    assert requests[1][0].get_method() == "GET"
