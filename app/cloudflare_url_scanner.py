from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_ROOT = "https://api.cloudflare.com/client/v4/accounts"


class CloudflareURLScannerError(RuntimeError):
    """Raised when Cloudflare cannot provide a usable URL-scan verdict."""


@dataclass(frozen=True)
class CloudflareURLVerdict:
    scan_id: str
    malicious: bool
    categories: tuple[str, ...]
    tags: tuple[str, ...]


def _unwrap(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise CloudflareURLScannerError("Cloudflare returned an invalid response.")
    if payload.get("success") is False:
        raise CloudflareURLScannerError("Cloudflare rejected the URL Scanner request.")
    result = payload.get("result")
    if isinstance(result, dict):
        return result
    return payload


def _json_request(
    request: Request,
    *,
    timeout_seconds: float,
    allow_pending: bool = False,
) -> dict | None:
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        if allow_pending and error.code == 404:
            return None
        raise CloudflareURLScannerError(
            f"Cloudflare URL Scanner returned HTTP {error.code}."
        ) from error
    except (URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CloudflareURLScannerError(
            "Cloudflare URL Scanner could not be reached."
        ) from error
    return _unwrap(payload)


def scan_url(
    url: str,
    *,
    account_id: str,
    api_token: str,
    request_timeout_seconds: float = 10,
    result_timeout_seconds: float = 40,
    poll_interval_seconds: float = 10,
) -> CloudflareURLVerdict:
    """Submit an unlisted Cloudflare scan and wait for its malicious verdict."""

    account_id = account_id.strip()
    api_token = api_token.strip()
    if not account_id or not api_token:
        raise CloudflareURLScannerError("Cloudflare URL Scanner is not configured.")

    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    scan_endpoint = f"{API_ROOT}/{account_id}/urlscanner/v2/scan"
    submission = _json_request(
        Request(
            scan_endpoint,
            data=json.dumps({"url": url, "visibility": "Unlisted"}).encode("utf-8"),
            headers=headers,
            method="POST",
        ),
        timeout_seconds=request_timeout_seconds,
    )
    scan_id = str((submission or {}).get("uuid", ""))
    try:
        uuid.UUID(scan_id)
    except ValueError as error:
        raise CloudflareURLScannerError(
            "Cloudflare did not return a valid scan identifier."
        ) from error

    result_endpoint = f"{API_ROOT}/{account_id}/urlscanner/v2/result/{scan_id}"
    deadline = time.monotonic() + result_timeout_seconds
    while True:
        result = _json_request(
            Request(result_endpoint, headers=headers, method="GET"),
            timeout_seconds=request_timeout_seconds,
            allow_pending=True,
        )
        if result is not None:
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise CloudflareURLScannerError(
                "Cloudflare URL Scanner did not finish in time."
            )
        time.sleep(min(poll_interval_seconds, remaining))

    task = result.get("task")
    if isinstance(task, dict) and task.get("success") is False:
        raise CloudflareURLScannerError("Cloudflare could not scan this URL.")
    overall = result.get("verdicts", {}).get("overall", {})
    malicious = overall.get("malicious")
    if not isinstance(malicious, bool):
        raise CloudflareURLScannerError(
            "Cloudflare returned an inconclusive URL-scan result."
        )

    categories = overall.get("categories", [])
    tags = overall.get("tags", [])
    return CloudflareURLVerdict(
        scan_id=scan_id,
        malicious=malicious,
        categories=tuple(str(item) for item in categories if isinstance(item, str)),
        tags=tuple(str(item) for item in tags if isinstance(item, str)),
    )
