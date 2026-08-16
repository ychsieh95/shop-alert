from __future__ import annotations

import ipaddress
import socket
import tempfile
from pathlib import Path
from urllib.parse import urlparse


class LinkPreviewError(RuntimeError):
    pass


def is_public_http_url(url: str, dns_cache: dict[str, bool] | None = None) -> bool:
    """Allow only HTTP(S) hosts whose current DNS answers are all public IPs."""

    parsed = urlparse(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        return False
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        return False
    if port not in {80, 443}:
        return False

    hostname = parsed.hostname.rstrip(".").lower()
    if dns_cache is not None and hostname in dns_cache:
        return dns_cache[hostname]
    try:
        addresses = {
            ipaddress.ip_address(item[4][0])
            for item in socket.getaddrinfo(
                hostname, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
            )
        }
    except (OSError, ValueError):
        allowed = False
    else:
        allowed = bool(addresses) and all(address.is_global for address in addresses)
    if dns_cache is not None:
        dns_cache[hostname] = allowed
    return allowed


def generate_link_preview(
    url: str,
    destination: Path,
    *,
    timeout_ms: int = 15_000,
    settle_ms: int = 1_500,
) -> None:
    """Render a public web page in an isolated browser and atomically cache a PNG."""

    dns_cache: dict[str, bool] = {}
    if not is_public_http_url(url, dns_cache):
        raise LinkPreviewError("The preview URL is not a public HTTP(S) destination.")

    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise LinkPreviewError(
            "Playwright is not installed; link screenshots are unavailable."
        ) from error

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent, prefix="preview-", suffix=".png", delete=False
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
                args=[
                    "--disable-background-networking",
                    "--disable-component-update",
                    "--disable-default-apps",
                    "--disable-sync",
                    "--no-first-run",
                ],
            )
            try:
                context = browser.new_context(
                    viewport={"width": 1365, "height": 768},
                    device_scale_factor=1,
                    java_script_enabled=True,
                    service_workers="block",
                    accept_downloads=False,
                    ignore_https_errors=False,
                    locale="en-US",
                )

                def guard_request(route) -> None:
                    request_url = route.request.url
                    if request_url.startswith(("data:", "blob:", "about:")):
                        route.continue_()
                    elif is_public_http_url(request_url, dns_cache):
                        route.continue_()
                    else:
                        route.abort("blockedbyclient")

                context.route("**/*", guard_request)
                page = context.new_page()
                response = page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=timeout_ms,
                )
                final_url = response.url if response else page.url
                if not is_public_http_url(final_url, dns_cache):
                    raise LinkPreviewError("The page redirected to a blocked destination.")
                if settle_ms:
                    page.wait_for_timeout(settle_ms)
                page.screenshot(
                    path=str(temporary_path),
                    type="png",
                    full_page=False,
                    animations="disabled",
                    timeout=timeout_ms,
                )
                context.close()
            finally:
                browser.close()
        temporary_path.replace(destination)
        temporary_path = None
    except (PlaywrightError, PlaywrightTimeoutError, OSError) as error:
        raise LinkPreviewError("The external page could not be captured.") from error
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
