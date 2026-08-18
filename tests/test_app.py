import io
import json
import re
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.extensions import db
from app.models import LoginThrottle, ReportContact, ShopReport, User


def report_payload(**overrides):
    data = {
        "name": "North Star Coffee",
        "address": "100 Community Road, Taipei",
        "latitude": "25.0330",
        "longitude": "121.5654",
        "controversy": "I observed the posted prices differ from the amount charged at checkout.",
        "instagram": "https://instagram.com/northstar",
        "proof": (io.BytesIO(b"fake image bytes"), "receipt.jpg", "image/jpeg"),
    }
    data.update(overrides)
    return data


def test_home_loads(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Know the story" in response.data
    assert b'data-preference-select' not in response.data
    assert response.data.count(b'data-language-select') == 1
    assert response.data.count(b'data-theme-select') == 1
    assert response.data.count(b'data-color-theme-select') == 0
    assert response.data.count(b'data-preference-trigger') == 1
    assert b'<option value="en-US">EN</option>' in response.data
    assert '<option value="coral:light" selected>Coral · Light</option>'.encode() in response.data
    assert '<optgroup label="Purple">'.encode() in response.data
    assert '<option value="purple:dark">Purple · Dark</option>'.encode() in response.data
    assert b"let saved = 'light'" in response.data
    assert b"localStorage.getItem('shopalert-theme') || 'light'" in response.data
    assert b"shopalert-color-theme" in response.data
    header = response.data.split(b'<header class="site-header">', 1)[1].split(b"</header>", 1)[0]
    footer = response.data.split(b'<footer class="site-footer">', 1)[1]
    assert b'data-language-select' not in header
    assert b'data-theme-select' not in header
    assert b'data-preference-trigger' not in header
    assert b'data-language-select' in footer
    assert b'data-theme-select' in footer
    assert b'data-preference-trigger' in footer
    assert b'icons/favicon.svg' in response.data
    assert b'icons/favicon.ico' in response.data
    assert b'icons/apple-touch-icon.png' in response.data
    assert b'icons/site.webmanifest' in response.data

    assert b'href="/assets/css/app.css"' in response.data
    assert b'src="/assets/js/app.js"' in response.data
    assert client.get("/assets/icons/favicon.svg").status_code == 200
    assert client.get("/assets/icons/favicon.ico").status_code == 200
    manifest = client.get("/assets/icons/site.webmanifest")
    assert manifest.status_code == 200
    assert manifest.get_json()["name"] == "ShopAlert"
    assert len(manifest.get_json()["icons"]) == 2


def test_language_preference_persists_and_renders_zh_tw(client):
    response = client.post(
        "/preferences/language",
        data={"locale": "zh-TW", "next": "/login"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert 'lang="zh-TW"'.encode() in response.data
    assert "登入 ShopAlert".encode() in response.data

    response = client.get("/")
    assert "了解店面背後".encode() in response.data
    assert ">語言</label>".encode() in response.data
    assert ">主題</label>".encode() in response.data
    assert ">偏好設定</span>".encode() in response.data
    assert '<optgroup label="黃色">'.encode() in response.data
    assert '<option value="coral:light" selected>珊瑚色 · 淺色</option>'.encode() in response.data
    assert '<option value="yellow">黃色</option>'.encode() not in response.data


def test_ip_country_sets_default_language_until_user_selects_one(client):
    taiwan = client.get("/", headers={"CF-IPCountry": "TW"})
    assert 'lang="zh-TW"'.encode() in taiwan.data
    assert "了解店面背後".encode() in taiwan.data

    hong_kong = client.get("/", headers={"CF-IPCountry": "HK"})
    assert 'lang="zh-TW"'.encode() in hong_kong.data

    client.post(
        "/preferences/language",
        data={"locale": "en-US", "next": "/"},
        headers={"CF-IPCountry": "TW"},
    )
    selected = client.get("/", headers={"CF-IPCountry": "TW"})
    assert b'lang="en-US"' in selected.data
    assert b"Know the story" in selected.data


def test_report_timestamps_use_proxy_timezone_and_include_browser_hooks(
    client, auth, app
):
    auth.signup()
    created = client.post(
        "/reports/new",
        data=report_payload(),
        content_type="multipart/form-data",
    )
    with app.app_context():
        report = ShopReport.query.one()
        report.created_at = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        report.updated_at = datetime(2026, 1, 1, 13, 30, tzinfo=timezone.utc)
        db.session.commit()

    detail = client.get(created.location, headers={"CF-Timezone": "Asia/Taipei"})
    assert b"2026-01-01 20:00" in detail.data
    assert b"2026-01-01 21:30" in detail.data
    assert b"Asia/Taipei" in detail.data
    assert b'datetime="2026-01-01T12:00:00Z"' in detail.data
    assert detail.data.count(b"data-local-time") >= 4

    utc_fallback = client.get(created.location, headers={"CF-Timezone": "invalid"})
    assert b"2026-01-01 12:00" in utc_fallback.data
    assert b"UTC" in utc_fallback.data


def test_invalid_language_and_external_redirect_are_rejected(client):
    response = client.post(
        "/preferences/language",
        data={"locale": "not-valid", "next": "https://example.com"},
    )
    assert response.status_code == 302
    assert response.location == "/"
    response = client.get("/")
    assert b'lang="en-US"' in response.data


def test_information_pages_are_public_and_bilingual(client):
    introduction = client.get("/introduction")
    assert introduction.status_code == 200
    assert b"A clearer community record of shop experiences" in introduction.data
    assert b"A community record, not a verdict" in introduction.data
    assert b'href="/introduction"' in introduction.data
    primary_nav = introduction.data.split(b'<nav id="site-nav"', 1)[1].split(
        b"</nav>", 1
    )[0]
    assert b'href="/introduction"' not in primary_nav

    updates = client.get("/updates")
    assert updates.status_code == 200
    assert "What’s new in ShopAlert".encode() in updates.data
    assert b"Evidence-led shop reports" in updates.data
    assert b"Latest" in updates.data

    licenses = client.get("/licenses")
    assert licenses.status_code == 200
    assert b"DM Sans and Manrope" in licenses.data
    assert b"Python dependencies" in licenses.data
    assert b"Google Maps Platform" in licenses.data
    assert b"Cloudflare Turnstile" in licenses.data
    assert b"Developed with support from OpenAI Codex" in licenses.data

    privacy = client.get("/privacy")
    assert privacy.status_code == 200
    assert b"Privacy policy" in privacy.data
    assert b"Information we collect" in privacy.data
    assert b"Cloudflare URL Scanner" in privacy.data
    assert b"Google Privacy Policy" in privacy.data
    assert b'href="/privacy"' in privacy.data

    client.post(
        "/preferences/language",
        data={"locale": "zh-TW", "next": "/updates"},
    )
    updates = client.get("/updates")
    assert "偏好設定與專案資訊".encode() in updates.data
    assert "更新紀錄".encode() in updates.data
    introduction = client.get("/introduction")
    assert "更清楚記錄社群的店家經驗".encode() in introduction.data
    assert "這是社群紀錄，不是裁決".encode() in introduction.data
    licenses = client.get("/licenses")
    assert "授權資訊與致謝".encode() in licenses.data
    assert "專案授權狀態".encode() in licenses.data
    privacy = client.get("/privacy")
    assert "隱私權政策".encode() in privacy.data
    assert "我們收集的資料".encode() in privacy.data
    assert "位置資料".encode() in privacy.data


def test_signup_login_and_logout(client, auth, app):
    response = auth.signup(username="Careful_User")
    assert b"Your account is ready" in response.data
    with app.app_context():
        assert User.query.count() == 1
        assert User.query.first().password_hash != "password123"
        assert User.query.first().username == "careful_user"
    response = auth.logout()
    assert b"logged out" in response.data
    response = auth.login()
    assert b"Welcome back" in response.data
    auth.logout()
    response = auth.login(username="CAREFUL_USER")
    assert b"Welcome back" in response.data


def test_duplicate_signup_is_rejected(client, auth, app):
    auth.signup()
    auth.logout()
    response = auth.signup()
    assert b"already exists" in response.data
    with app.app_context():
        assert User.query.count() == 1


def test_duplicate_and_invalid_usernames_are_rejected(client, auth, app):
    auth.signup(username="shared_name")
    auth.logout()
    duplicate = auth.signup(email="another@example.com", username="SHARED_NAME")
    assert b"username is already in use" in duplicate.data
    invalid = auth.signup(email="third@example.com", username="not-valid")
    assert b"3 to 30 letters, numbers, or underscores" in invalid.data
    with app.app_context():
        assert User.query.count() == 1


def test_failed_logins_are_limited_and_success_clears_the_lock(client, auth, app):
    app.config.update(
        LOGIN_MAX_ATTEMPTS=3,
        LOGIN_ATTEMPT_WINDOW_MINUTES=15,
        LOGIN_LOCKOUT_MINUTES=10,
    )
    auth.signup()
    auth.logout()

    first = auth.login(username="REPORTER", password="incorrect-password")
    assert first.status_code == 200
    assert b"2 attempts remaining" in first.data
    second = auth.login(password="incorrect-password")
    assert second.status_code == 200
    assert b"1 attempts remaining" in second.data

    locked = auth.login(username="reporter", password="incorrect-password")
    assert locked.status_code == 429
    assert locked.headers["Retry-After"]
    assert b"Too many failed login attempts" in locked.data
    assert auth.login().status_code == 429

    with app.app_context():
        throttle = LoginThrottle.query.one()
        assert len(throttle.key_hash) == 64
        assert "reporter@example.com" not in throttle.key_hash
        throttle.locked_until = int(time.time()) - 1
        db.session.commit()

    retry = auth.login(password="still-incorrect")
    assert retry.status_code == 200
    assert b"2 attempts remaining" in retry.data
    response = auth.login()
    assert response.status_code == 200
    assert b"Welcome back" in response.data
    with app.app_context():
        assert LoginThrottle.query.count() == 0


def test_turnstile_is_required_for_signup_and_login(client, app, monkeypatch):
    from app import auth as auth_module

    app.config.update(
        TURNSTILE_SITE_KEY="public-test-key",
        TURNSTILE_SECRET_KEY="private-test-key",
        TURNSTILE_EXPECTED_HOSTNAME="shopalert.example",
    )
    state = {"valid": False, "actions": []}

    def fake_verify(action):
        state["actions"].append(action)
        return state["valid"]

    monkeypatch.setattr(auth_module, "_verify_turnstile", fake_verify)
    login_page = client.get("/login")
    signup_page = client.get("/signup")
    assert b"public-test-key" in login_page.data
    assert b"private-test-key" not in login_page.data
    assert b'data-action="login"' in login_page.data
    assert b'data-action="signup"' in signup_page.data
    assert b"challenges.cloudflare.com/turnstile/v0/api.js" in signup_page.data

    blocked_signup = client.post(
        "/signup",
        data={
            "display_name": "Captcha User",
            "username": "captcha_user",
            "email": "captcha@example.com",
            "password": "password123",
        },
    )
    assert blocked_signup.status_code == 400
    assert b"Complete the security check" in blocked_signup.data
    with app.app_context():
        assert User.query.count() == 0

    state["valid"] = True
    created = client.post(
        "/signup",
        data={
            "display_name": "Captcha User",
            "username": "captcha_user",
            "email": "captcha@example.com",
            "password": "password123",
        },
    )
    assert created.status_code == 302
    client.post("/logout")

    state["valid"] = False
    blocked_login = client.post(
        "/login", data={"email": "captcha@example.com", "password": "password123"}
    )
    assert blocked_login.status_code == 400
    with app.app_context():
        assert LoginThrottle.query.count() == 0
    assert state["actions"] == ["signup", "signup", "login"]


def test_turnstile_server_validation_checks_action_and_hostname(app, monkeypatch):
    from app import auth as auth_module

    app.config.update(
        TURNSTILE_SITE_KEY="public-test-key",
        TURNSTILE_SECRET_KEY="private-test-key",
        TURNSTILE_EXPECTED_HOSTNAME="shopalert.example",
    )
    result = {
        "success": True,
        "action": "login",
        "hostname": "shopalert.example",
    }
    captured = {}

    def fake_urlopen(verification_request, timeout):
        captured["url"] = verification_request.full_url
        captured["body"] = verification_request.data
        captured["timeout"] = timeout
        return io.BytesIO(json.dumps(result).encode())

    monkeypatch.setattr(auth_module, "urlopen", fake_urlopen)
    with app.test_request_context(
        "/login",
        method="POST",
        data={"cf-turnstile-response": "one-time-token"},
        environ_base={"REMOTE_ADDR": "203.0.113.10"},
    ):
        assert auth_module._verify_turnstile("login") is True
        assert captured["url"].endswith("/turnstile/v0/siteverify")
        assert b"secret=private-test-key" in captured["body"]
        assert b"response=one-time-token" in captured["body"]
        assert captured["timeout"] == 5

        result["action"] = "signup"
        assert auth_module._verify_turnstile("login") is False
        result["action"] = "login"
        result["hostname"] = "attacker.example"
        assert auth_module._verify_turnstile("login") is False


def test_turnstile_keys_must_be_configured_together(tmp_path):
    from app import create_app

    with pytest.raises(RuntimeError, match="must be configured together"):
        create_app(
            {
                "TESTING": True,
                "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
                "UPLOAD_FOLDER": str(tmp_path / "uploads"),
                "TURNSTILE_SITE_KEY": "public-only",
                "TURNSTILE_SECRET_KEY": "",
            }
        )


def test_report_requires_login(client):
    response = client.get("/reports/new")
    assert response.status_code == 302
    assert "/login" in response.location
    response = client.get("/api/reports/similar?name=North+Star")
    assert response.status_code == 302
    assert "/login" in response.location


def test_report_requires_proof(client, auth, app):
    auth.signup()
    data = report_payload()
    data.pop("proof")
    response = client.post("/reports/new", data=data, follow_redirects=True)
    assert b"at least one image or video" in response.data
    with app.app_context():
        assert ShopReport.query.count() == 0


def test_online_shop_does_not_require_address_or_location(client, auth, app):
    auth.signup()
    data = report_payload(
        name="Cloud Cart",
        address="",
        is_online="1",
        latitude="25.0330",
        longitude="121.5654",
        proof=(io.BytesIO(b"online proof"), "order.png", "image/png"),
    )
    response = client.post(
        "/reports/new",
        data=data,
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Report published" in response.data
    assert b"Online shop" in response.data
    with app.app_context():
        report = ShopReport.query.one()
        assert report.is_online is True
        assert report.address == ""
        assert report.latitude is None
        assert report.longitude is None
        assert report.google_place_id is None

    response = client.get("/?q=Cloud+Cart")
    assert b"Cloud Cart" in response.data
    assert b"Online shop" in response.data
    response = client.get("/?lat=25.033&lng=121.5654&radius=100")
    assert b"Cloud Cart" not in response.data


def test_new_report_form_has_online_shop_toggle(client, auth):
    auth.signup()
    response = client.get("/reports/new")
    assert response.status_code == 200
    assert b'data-online-shop' in response.data
    assert b'data-address-dependent' in response.data
    assert b'data-similar-report-check' in response.data
    assert b'data-similar-report-results' in response.data
    assert b'data-similar-report-dialog' in response.data
    assert b'data-similar-report-dialog-open' in response.data
    assert b'data-similar-report-count' in response.data
    assert b'aria-label="Similar report count"' in response.data
    assert b'class="similar-report-icon" data-similar-report-count' in response.data
    assert b'data-similar-report-frame' in response.data
    assert b'sandbox="allow-forms allow-same-origin allow-scripts"' in response.data


def test_similar_report_lookup_by_name_place_and_location(client, auth, app):
    auth.signup()
    created = client.post(
        "/reports/new",
        data=report_payload(
            google_place_id="north-star-place",
            address_en_us="100 Community Road, Taipei",
            address_zh_tw="台北市社區路100號",
        ),
        content_type="multipart/form-data",
    )
    assert created.status_code == 302
    with app.app_context():
        report_guid = ShopReport.query.one().guid

    by_name = client.get(
        "/api/reports/similar",
        query_string={"name": "North Star Coffe", "address": "100 Community Road"},
    ).get_json()
    assert by_name["searched"] is True
    assert [report["name"] for report in by_name["reports"]] == [
        "North Star Coffee"
    ]
    assert by_name["reports"][0]["url"] == created.location

    by_place = client.get(
        "/api/reports/similar",
        query_string={"name": "Different display name", "place_id": "north-star-place"},
    ).get_json()
    assert len(by_place["reports"]) == 1

    by_location = client.get(
        "/api/reports/similar",
        query_string={"lat": "25.0330", "lng": "121.5654", "address": "Taipei"},
    ).get_json()
    assert len(by_location["reports"]) == 1

    excluded = client.get(
        "/api/reports/similar",
        query_string={"name": "North Star Coffee", "exclude": report_guid},
    ).get_json()
    assert excluded["reports"] == []

    unrelated = client.get(
        "/api/reports/similar",
        query_string={"name": "Completely Unrelated Store"},
    ).get_json()
    assert unrelated["reports"] == []


def test_google_places_uses_selected_interface_language(client, auth, app):
    app.config["GOOGLE_MAPS_API_KEY"] = "test-google-key"
    auth.signup()

    english = client.get("/reports/new")
    assert b'data-place-language="en-US"' in english.data
    assert b'data-place-region="us"' in english.data
    assert b'language:"en-US",region:"US"' in english.data

    client.post(
        "/preferences/language",
        data={"locale": "zh-TW", "next": "/reports/new"},
    )
    traditional_chinese = client.get("/reports/new")
    assert b'data-place-language="zh-TW"' in traditional_chinese.data
    assert b'data-place-region="tw"' in traditional_chinese.data
    assert b'language:"zh-TW",region:"TW"' in traditional_chinese.data


def test_report_address_follows_selected_language(client, auth, app):
    auth.signup()
    created = client.post(
        "/reports/new",
        data=report_payload(
            google_place_id="test-place-id",
            address_en_us="No. 112-3, Ziqiang Road, Miaoli County, Taiwan",
            address_zh_tw="351苗栗縣頭份市自強路112-3號",
        ),
        content_type="multipart/form-data",
    )

    english = client.get(created.location)
    assert b"No. 112-3, Ziqiang Road, Miaoli County, Taiwan" in english.data
    assert "351苗栗縣頭份市自強路112-3號".encode() not in english.data
    assert b"No. 112-3, Ziqiang Road, Miaoli County, Taiwan" in client.get("/").data

    client.post(
        "/preferences/language",
        data={"locale": "zh-TW", "next": created.location},
    )
    traditional_chinese = client.get(created.location)
    assert "351苗栗縣頭份市自強路112-3號".encode() in traditional_chinese.data
    assert b"No. 112-3, Ziqiang Road, Miaoli County, Taiwan" not in traditional_chinese.data
    assert "351苗栗縣頭份市自強路112-3號".encode() in client.get("/").data

    with app.app_context():
        report = ShopReport.query.one()
        assert report.address_en_us.startswith("No. 112-3")
        assert report.address_zh_tw.startswith("351")


def test_create_search_detail_and_media(client, auth, app):
    auth.signup()
    response = client.post(
        "/reports/new", data=report_payload(), content_type="multipart/form-data", follow_redirects=True
    )
    assert response.status_code == 200
    assert b"Report published" in response.data
    assert b"North Star Coffee" in response.data
    with app.app_context():
        report = ShopReport.query.one()
        assert len(report.media) == 1
        media_id = report.media[0].id

    response = client.get("/?q=checkout")
    assert b"North Star Coffee" in response.data
    response = client.get("/?q=unrelated")
    assert b"No reports found" in response.data
    response = client.get(f"/media/{media_id}")
    assert response.status_code == 200
    assert response.mimetype == "image/jpeg"


def test_report_content_converts_br_text_without_trusting_other_html(client, auth):
    auth.signup()
    response = client.post(
        "/reports/new",
        data=report_payload(
            controversy=(
                "The first documented point.<br><BR />"
                "The second documented point.<script>alert('unsafe')</script>"
            )
        ),
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"The first documented point.\n\nThe second documented point." in response.data
    assert b"&lt;script&gt;alert(&#39;unsafe&#39;)&lt;/script&gt;" in response.data
    assert b"<script>alert('unsafe')</script>" not in response.data


def test_reports_use_guid_urls_and_legacy_ids_redirect(client, auth, app):
    auth.signup()
    response = client.post(
        "/reports/new",
        data=report_payload(),
        content_type="multipart/form-data",
    )
    assert response.status_code == 302
    assert re.fullmatch(r"/reports/[0-9a-f-]{36}", response.location)
    public_guid = response.location.rsplit("/", 1)[-1]
    assert str(uuid.UUID(public_guid)) == public_guid

    with app.app_context():
        report = ShopReport.query.one()
        assert report.guid == public_guid
        internal_id = report.id

    detail = client.get(response.location)
    assert detail.status_code == 200
    legacy = client.get(f"/reports/{internal_id}")
    assert legacy.status_code == 301
    assert legacy.location == response.location


def test_report_media_uses_stage_and_thumbnail_gallery(client, auth):
    auth.signup()
    data = report_payload()
    data["proof"] = [
        (io.BytesIO(b"first image"), "first.jpg", "image/jpeg"),
        (io.BytesIO(b"video bytes"), "second.mp4", "video/mp4"),
    ]
    response = client.post(
        "/reports/new",
        data=data,
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b'data-evidence-gallery' in response.data
    assert response.data.count(b'data-evidence-slide=') == 2
    assert response.data.count(b'data-evidence-thumbnail=') == 2
    assert b'data-evidence-index' in response.data
    assert b'data-evidence-index-current>1</span>' in response.data
    assert b'aria-label="Media item 1 / 2"' in response.data
    assert b'evidence-gallery-play' in response.data
    assert b'aria-pressed="true"' in response.data
    assert b'aria-pressed="false"' in response.data
    assert b'data-evidence-lightbox' in response.data
    assert b'data-image-lightbox' in response.data
    assert b'data-lightbox-close' in response.data


def test_user_can_list_and_edit_own_reports(client, auth, app):
    auth.signup()
    created = client.post(
        "/reports/new",
        data=report_payload(),
        content_type="multipart/form-data",
    )
    report_url = created.location
    edit_url = f"{report_url}/edit"
    with app.app_context():
        report = ShopReport.query.one()
        assert report.created_at == report.updated_at
        assert report.has_been_updated is False

    listing = client.get("/my/reports")
    assert listing.status_code == 200
    assert b"Reports you created" in listing.data
    assert b"North Star Coffee" in listing.data
    assert edit_url.encode() in listing.data
    assert b"Last updated" not in listing.data

    detail = client.get(report_url)
    assert b"Reported" in detail.data
    assert b"Last updated" not in detail.data

    edit_form = client.get(edit_url)
    assert edit_form.status_code == 200
    assert b"Edit report" in edit_form.data
    assert b"Current evidence" in edit_form.data
    assert b"North Star Coffee" in edit_form.data

    updated = client.post(
        edit_url,
        data={
            "name": "North Star Coffee Updated",
            "address": "200 Revised Road, Taipei",
            "latitude": "25.04",
            "longitude": "121.56",
            "controversy": "This updated description keeps the documented account accurate and clear.",
            "instagram": "https://instagram.com/updated-northstar",
        },
        follow_redirects=True,
    )
    assert updated.status_code == 200
    assert b"Report updated" in updated.data
    assert b"North Star Coffee Updated" in updated.data
    with app.app_context():
        report = ShopReport.query.one()
        assert report.name == "North Star Coffee Updated"
        assert report.address == "200 Revised Road, Taipei"
        assert len(report.media) == 1
        assert report.updated_at > report.created_at
        assert report.has_been_updated is True

    detail = client.get(report_url)
    assert b"Reported" in detail.data
    assert b"Last updated" in detail.data
    assert b"UTC" in detail.data

    listing = client.get("/my/reports")
    assert b"Last updated" in listing.data


def test_user_can_add_and_edit_multiple_controversy_links(client, auth, app):
    auth.signup()
    created = client.post(
        "/reports/new",
        data=report_payload(
            controversy_links=(
                "https://news.example/review\n"
                "https://social.example/post/123\n"
                "https://news.example/review"
            )
        ),
        content_type="multipart/form-data",
    )
    assert created.status_code == 302

    detail = client.get(created.location)
    assert b"Controversy links" in detail.data
    assert b'href="https://news.example/review"' in detail.data
    assert b'href="https://social.example/post/123"' in detail.data
    assert detail.data.count(b'href="https://news.example/review"') == 1
    assert detail.data.count(b"data-controversy-link") == 2
    assert b"data-link-preview-dialog" in detail.data
    assert b"data-link-preview-image" in detail.data
    assert b"data-link-preview-loading" in detail.data
    assert b"data-link-preview-error" in detail.data
    assert b"<iframe" not in detail.data
    assert b"data-link-preview-continue" in detail.data
    assert b"Stay here" in detail.data
    assert b"Go to page" in detail.data
    assert detail.data.index(b"What was documented") < detail.data.index(
        b"Controversy links"
    ) < detail.data.index(b"Supporting media")
    with app.app_context():
        assert ShopReport.query.one().controversy_links == [
            "https://news.example/review",
            "https://social.example/post/123",
        ]

    updated = client.post(
        f"{created.location}/edit",
        data={
            "name": "North Star Coffee",
            "address": "100 Community Road, Taipei",
            "controversy": "This updated report still contains sufficiently detailed information.",
            "controversy_links": "https://updated.example/source",
        },
        follow_redirects=True,
    )
    assert updated.status_code == 200
    assert b'href="https://updated.example/source"' in updated.data
    assert b"https://news.example/review" not in updated.data
    with app.app_context():
        assert ShopReport.query.one().controversy_links == [
            "https://updated.example/source"
        ]


def test_user_can_link_reported_and_manual_related_shops(client, auth, app):
    auth.signup()
    other = client.post(
        "/reports/new",
        data=report_payload(name="Sister Branch Coffee", address="9 Sister Road, Taipei"),
        content_type="multipart/form-data",
    )
    assert other.status_code == 302
    with app.app_context():
        other_guid = ShopReport.query.filter_by(name="Sister Branch Coffee").one().guid

    form = client.get("/reports/new")
    assert b"Related shops" in form.data
    assert b"data-related-shop-editor" in form.data
    assert b"data-related-shop-search" in form.data
    assert b"data-related-shop-manual-name" in form.data
    assert b'data-related-shop-search-url="/api/reports/search"' in form.data

    found = client.get("/api/reports/search", query_string={"q": "sister"}).get_json()
    assert [report["guid"] for report in found["reports"]] == [other_guid]
    assert found["reports"][0]["url"] == other.location
    by_address = client.get(
        "/api/reports/search", query_string={"q": "Sister Road"}
    ).get_json()
    assert len(by_address["reports"]) == 1
    excluded = client.get(
        "/api/reports/search", query_string={"q": "sister", "exclude": other_guid}
    ).get_json()
    assert excluded["reports"] == []
    assert client.get("/api/reports/search", query_string={"q": "s"}).get_json() == {
        "reports": []
    }

    created = client.post(
        "/reports/new",
        data=report_payload(
            **{
                "related_shop_guid": [other_guid, "", ""],
                "related_shop_name": ["", "Unlisted Tea House", ""],
                "related_shop_address": ["", "12 Quiet Lane, Taipei", ""],
            }
        ),
        content_type="multipart/form-data",
    )
    assert created.status_code == 302
    with app.app_context():
        report = ShopReport.query.filter_by(name="North Star Coffee").one()
        assert report.related_shops == [
            {"guid": other_guid, "name": "", "address": ""},
            {
                "guid": "",
                "name": "Unlisted Tea House",
                "address": "12 Quiet Lane, Taipei",
            },
        ]

    detail = client.get(created.location)
    assert b"Related shops" in detail.data
    assert b"Sister Branch Coffee" in detail.data
    assert other.location.encode() in detail.data
    assert b"Unlisted Tea House" in detail.data
    assert b"12 Quiet Lane, Taipei" in detail.data

    edit_form = client.get(f"{created.location}/edit")
    assert f'value="{other_guid}"'.encode() in edit_form.data
    assert b'value="Unlisted Tea House"' in edit_form.data
    # The JSON seed must stay inside a single-quoted attribute: tojson escapes
    # single quotes but leaves the double quotes of JSON keys intact.
    entries = json.loads(
        edit_form.data.decode()
        .split("data-related-shop-entries='", 1)[1]
        .split("'", 1)[0]
    )
    assert [entry["guid"] for entry in entries] == [other_guid, ""]
    assert entries[1]["name"] == "Unlisted Tea House"

    updated = client.post(
        f"{created.location}/edit",
        data={
            "name": "North Star Coffee",
            "address": "100 Community Road, Taipei",
            "controversy": "This updated report still contains sufficiently detailed information.",
            "related_shop_guid": ["", ""],
            "related_shop_name": ["Second Manual Shop", "Second Manual Shop"],
            "related_shop_address": ["", ""],
        },
        follow_redirects=True,
    )
    assert updated.status_code == 200
    assert b"Second Manual Shop" in updated.data
    assert b"Sister Branch Coffee" not in updated.data
    with app.app_context():
        report = ShopReport.query.filter_by(name="North Star Coffee").one()
        assert report.related_shops == [
            {"guid": "", "name": "Second Manual Shop", "address": ""}
        ]


def test_related_shops_reject_self_unknown_and_oversized_entries(client, auth, app):
    auth.signup()
    created = client.post(
        "/reports/new",
        data=report_payload(),
        content_type="multipart/form-data",
    )
    assert created.status_code == 302
    with app.app_context():
        report_guid = ShopReport.query.one().guid

    payload = {
        "name": "North Star Coffee",
        "address": "100 Community Road, Taipei",
        "controversy": "This updated report still contains sufficiently detailed information.",
    }
    itself = client.post(
        f"{created.location}/edit",
        data={**payload, "related_shop_guid": report_guid},
        follow_redirects=True,
    )
    assert b"cannot be listed as its own related shop" in itself.data

    unknown = client.post(
        f"{created.location}/edit",
        data={**payload, "related_shop_guid": str(uuid.uuid4())},
        follow_redirects=True,
    )
    assert b"could not be found" in unknown.data

    too_short = client.post(
        f"{created.location}/edit",
        data={**payload, "related_shop_name": "A"},
        follow_redirects=True,
    )
    assert b"between 2 and 180 characters" in too_short.data

    too_many = client.post(
        f"{created.location}/edit",
        data={
            **payload,
            "related_shop_name": [f"Related Shop {index}" for index in range(11)],
        },
        follow_redirects=True,
    )
    assert b"no more than 10 related shops" in too_many.data

    with app.app_context():
        assert ShopReport.query.one().related_shops == []


def test_archived_related_shop_link_is_hidden_from_the_report(client, auth, app):
    auth.signup()
    other = client.post(
        "/reports/new",
        data=report_payload(name="Sister Branch Coffee", address="9 Sister Road, Taipei"),
        content_type="multipart/form-data",
    )
    with app.app_context():
        other_guid = ShopReport.query.filter_by(name="Sister Branch Coffee").one().guid

    created = client.post(
        "/reports/new",
        data=report_payload(related_shop_guid=other_guid),
        content_type="multipart/form-data",
    )
    assert b"Sister Branch Coffee" in client.get(created.location).data

    with app.app_context():
        archived = ShopReport.query.filter_by(name="Sister Branch Coffee").one()
        archived.archived_at = datetime.now(timezone.utc)
        db.session.commit()

    detail = client.get(created.location)
    assert b"Sister Branch Coffee" not in detail.data
    assert b"Related shops" not in detail.data
    assert client.get("/api/reports/search", query_string={"q": "sister"}).get_json()[
        "reports"
    ] == []
    with app.app_context():
        report = ShopReport.query.filter_by(name="North Star Coffee").one()
        assert report.related_shops == [{"guid": other_guid, "name": "", "address": ""}]


def test_user_can_add_search_and_edit_hashtags(client, auth, app):
    auth.signup()
    form = client.get("/reports/new")
    assert b"data-hashtag-editor" in form.data
    assert b"data-hashtag-chips" in form.data
    assert b"data-hashtag-input" in form.data
    assert b"data-hashtag-value" in form.data
    assert b"Suggested hashtags" in form.data
    assert b'data-hashtag-suggestion="service"' in form.data

    created = client.post(
        "/reports/new",
        data=report_payload(hashtags="#Pricing refund, #退款 pricing"),
        content_type="multipart/form-data",
    )
    assert created.status_code == 302

    detail = client.get(created.location)
    assert b'aria-label="Hashtags"' in detail.data
    assert b"#Pricing" in detail.data
    assert b"#refund" in detail.data
    assert "#退款".encode() in detail.data
    assert detail.data.count(b"#Pricing") == 1
    assert detail.data.index(b"#Pricing") < detail.data.index(b"#refund")
    assert detail.data.index(b"#refund") < detail.data.index("#退款".encode())
    with app.app_context():
        assert ShopReport.query.one().hashtags == ["Pricing", "refund", "退款"]

    next_form = client.get("/reports/new")
    assert b"Popular hashtags" in next_form.data
    assert b'data-hashtag-suggestion="Pricing"' in next_form.data
    assert next_form.data.index(b'data-hashtag-suggestion="Pricing"') < next_form.data.index(
        b'data-hashtag-suggestion="service"'
    )

    by_word = client.get("/?q=pricing")
    assert b"North Star Coffee" in by_word.data
    by_hash = client.get("/?q=%23refund")
    assert b"North Star Coffee" in by_hash.data

    updated = client.post(
        f"{created.location}/edit",
        data={
            "name": "North Star Coffee",
            "address": "100 Community Road, Taipei",
            "controversy": "This updated report still contains sufficiently detailed information.",
            "hashtags": "#service customer_care",
        },
        follow_redirects=True,
    )
    assert updated.status_code == 200
    assert b"#service" in updated.data
    assert b"#customer_care" in updated.data
    assert b"#Pricing" not in updated.data
    assert updated.data.index(b"#customer_care") < updated.data.index(b"#service")
    with app.app_context():
        report = ShopReport.query.one()
        assert report.hashtags == ["customer_care", "service"]
        assert json.loads(report.hashtags_json) == ["customer_care", "service"]


def test_report_form_ranks_hashtags_by_popularity(client, auth):
    auth.signup()
    for index, hashtags in enumerate(("#refund", "#pricing", "#Pricing")):
        created = client.post(
            "/reports/new",
            data=report_payload(
                name=f"Popularity Test Shop {index}",
                hashtags=hashtags,
                proof=(io.BytesIO(b"hashtag proof"), f"proof-{index}.jpg", "image/jpeg"),
            ),
            content_type="multipart/form-data",
        )
        assert created.status_code == 302

    form = client.get("/reports/new")
    assert b"Popular hashtags" in form.data
    assert form.data.index(b'data-hashtag-suggestion="Pricing"') < form.data.index(
        b'data-hashtag-suggestion="refund"'
    )


def test_hashtag_suggestions_follow_interface_language(client, auth):
    auth.signup()
    english = client.get("/reports/new")
    assert b'data-hashtag-suggestion="service"' in english.data
    assert 'data-hashtag-suggestion="服務"'.encode() not in english.data

    client.post(
        "/preferences/language",
        data={"locale": "zh-TW", "next": "/reports/new"},
    )
    traditional_chinese = client.get("/reports/new")
    assert "建議主題標籤".encode() in traditional_chinese.data
    assert 'data-hashtag-suggestion="服務"'.encode() in traditional_chinese.data
    assert 'data-hashtag-suggestion="價格"'.encode() in traditional_chinese.data
    assert b'data-hashtag-suggestion="service"' not in traditional_chinese.data


def test_controversy_link_screenshot_is_generated_and_cached(
    client, auth, app, monkeypatch
):
    from app import main as main_module

    auth.signup()
    created = client.post(
        "/reports/new",
        data=report_payload(controversy_links="https://news.example/source"),
        content_type="multipart/form-data",
    )
    calls = []

    def fake_generate(url, destination, **options):
        calls.append((url, options))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"\x89PNG\r\n\x1a\nserver screenshot")

    monkeypatch.setattr(main_module, "generate_link_preview", fake_generate)
    preview_url = f"{created.location}/link-previews/0.png"
    first = client.get(preview_url)
    second = client.get(preview_url)

    assert first.status_code == 200
    assert first.mimetype == "image/png"
    assert first.data.startswith(b"\x89PNG")
    assert first.headers["X-Content-Type-Options"] == "nosniff"
    assert second.status_code == 200
    assert len(calls) == 1
    assert calls[0][0] == "https://news.example/source"
    assert calls[0][1]["timeout_ms"] == 15_000
    assert client.get(f"{created.location}/link-previews/1.png").status_code == 404


def test_cloudflare_url_scan_allows_clean_link_and_caches_verdict(
    client, auth, app, monkeypatch
):
    from types import SimpleNamespace

    from app import main as main_module

    auth.signup()
    created = client.post(
        "/reports/new",
        data=report_payload(controversy_links="https://news.example/source"),
        content_type="multipart/form-data",
    )
    app.config.update(
        CLOUDFLARE_URL_SCANNER_ACCOUNT_ID="account-id",
        CLOUDFLARE_URL_SCANNER_API_TOKEN="secret-token",
    )
    scan_calls = []
    screenshot_calls = []

    def fake_scan(url, **options):
        scan_calls.append((url, options))
        return SimpleNamespace(
            scan_id="182bd5e5-6e1a-4fe4-a799-aa6d9a6ab26e",
            malicious=False,
            categories=(),
            tags=(),
        )

    def fake_generate(_url, destination, **_options):
        screenshot_calls.append(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"\x89PNG\r\n\x1a\nchecked screenshot")

    monkeypatch.setattr(main_module, "scan_url", fake_scan)
    monkeypatch.setattr(main_module, "is_public_http_url", lambda _url: True)
    monkeypatch.setattr(main_module, "generate_link_preview", fake_generate)
    preview_url = f"{created.location}/link-previews/0.png"

    first = client.get(preview_url)
    second = client.get(preview_url)

    assert first.status_code == 200
    assert first.headers["X-ShopAlert-Link-Check"] == "cloudflare-no-known-threat"
    assert second.status_code == 200
    assert len(scan_calls) == 1
    assert len(screenshot_calls) == 1
    assert scan_calls[0][0] == "https://news.example/source"
    assert scan_calls[0][1]["account_id"] == "account-id"
    assert scan_calls[0][1]["api_token"] == "secret-token"


def test_cloudflare_url_scan_blocks_malicious_link(client, auth, app, monkeypatch):
    from types import SimpleNamespace

    from app import main as main_module

    auth.signup()
    created = client.post(
        "/reports/new",
        data=report_payload(controversy_links="https://malicious.example/source"),
        content_type="multipart/form-data",
    )
    app.config.update(
        CLOUDFLARE_URL_SCANNER_ACCOUNT_ID="account-id",
        CLOUDFLARE_URL_SCANNER_API_TOKEN="secret-token",
    )

    monkeypatch.setattr(
        main_module,
        "scan_url",
        lambda *_args, **_kwargs: SimpleNamespace(
            scan_id="182bd5e5-6e1a-4fe4-a799-aa6d9a6ab26e",
            malicious=True,
            categories=("Phishing",),
            tags=("malicious",),
        ),
    )
    monkeypatch.setattr(main_module, "is_public_http_url", lambda _url: True)
    monkeypatch.setattr(
        main_module,
        "generate_link_preview",
        lambda *_args, **_kwargs: pytest.fail(
            "A malicious URL must not reach the screenshot worker."
        ),
    )

    response = client.get(f"{created.location}/link-previews/0.png")
    assert response.status_code == 403


def test_link_screenshot_blocks_non_public_network_destinations(monkeypatch):
    from app import link_preview

    def public_address(*_args, **_kwargs):
        return [(2, 1, 6, "", ("8.8.8.8", 443))]

    monkeypatch.setattr(link_preview.socket, "getaddrinfo", public_address)
    assert link_preview.is_public_http_url("https://public.example/article") is True
    assert link_preview.is_public_http_url("https://user:pass@public.example") is False
    assert link_preview.is_public_http_url("https://public.example:8443") is False
    assert link_preview.is_public_http_url("file:///etc/passwd") is False

    def private_address(*_args, **_kwargs):
        return [(2, 1, 6, "", ("127.0.0.1", 443))]

    monkeypatch.setattr(link_preview.socket, "getaddrinfo", private_address)
    assert link_preview.is_public_http_url("https://localhost/admin") is False


def test_user_cannot_edit_another_users_report(client, auth, app):
    auth.signup()
    created = client.post(
        "/reports/new",
        data=report_payload(),
        content_type="multipart/form-data",
    )
    edit_url = f"{created.location}/edit"
    auth.logout()
    auth.signup(email="other@example.com")

    response = client.get(edit_url)
    assert response.status_code == 403
    response = client.post(
        edit_url,
        data={
            "name": "Unauthorized change",
            "address": "Different address",
            "controversy": "This unauthorized description should never be accepted by the application.",
        },
    )
    assert response.status_code == 403
    with app.app_context():
        assert ShopReport.query.one().name == "North Star Coffee"


def test_edit_must_keep_evidence_and_can_replace_it(client, auth, app):
    auth.signup()
    created = client.post(
        "/reports/new",
        data=report_payload(),
        content_type="multipart/form-data",
    )
    edit_url = f"{created.location}/edit"
    with app.app_context():
        old_media_id = ShopReport.query.one().media[0].id

    rejected = client.post(
        edit_url,
        data={
            "name": "North Star Coffee",
            "address": "100 Community Road, Taipei",
            "controversy": "This remains a sufficiently detailed description of the documented event.",
            "remove_media": str(old_media_id),
        },
        follow_redirects=True,
    )
    assert b"Keep or add at least one image or video" in rejected.data
    with app.app_context():
        assert len(ShopReport.query.one().media) == 1

    replaced = client.post(
        edit_url,
        data={
            "name": "North Star Coffee",
            "address": "100 Community Road, Taipei",
            "controversy": "This remains a sufficiently detailed description of the documented event.",
            "remove_media": str(old_media_id),
            "proof": (io.BytesIO(b"replacement"), "replacement.webp", "image/webp"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"Report updated" in replaced.data
    with app.app_context():
        media = ShopReport.query.one().media
        assert len(media) == 1
        assert media[0].original_name == "replacement.webp"


def test_user_can_rename_new_and_existing_media(client, auth, app):
    auth.signup()
    created = client.post(
        "/reports/new",
        data=report_payload(proof_name="交易收據.jpg"),
        content_type="multipart/form-data",
    )
    assert created.status_code == 302
    detail = client.get(created.location)
    assert "交易收據.jpg".encode() in detail.data

    with app.app_context():
        media_id = ShopReport.query.one().media[0].id
        assert ShopReport.query.one().media[0].original_name == "交易收據.jpg"

    edit_form = client.get(f"{created.location}/edit")
    assert f'name="media_name_{media_id}"'.encode() in edit_form.data
    assert "交易收據.jpg".encode() in edit_form.data

    renamed = client.post(
        f"{created.location}/edit",
        data={
            "name": "North Star Coffee",
            "address": "100 Community Road, Taipei",
            "controversy": "This remains a sufficiently detailed description of the event.",
            f"media_name_{media_id}": "付款證明.jpg",
        },
        follow_redirects=True,
    )
    assert "付款證明.jpg".encode() in renamed.data
    with app.app_context():
        assert ShopReport.query.one().media[0].original_name == "付款證明.jpg"

    invalid = client.post(
        f"{created.location}/edit",
        data={
            "name": "North Star Coffee",
            "address": "100 Community Road, Taipei",
            "controversy": "This remains a sufficiently detailed description of the event.",
            f"media_name_{media_id}": "misleading.exe",
        },
        follow_redirects=True,
    )
    assert b"keep their original extension" in invalid.data
    with app.app_context():
        assert ShopReport.query.one().media[0].original_name == "付款證明.jpg"


def test_my_reports_requires_login(client):
    response = client.get("/my/reports")
    assert response.status_code == 302
    assert "/login" in response.location


def test_report_contact_modal_and_submission(client, auth, app):
    auth.signup()
    created = client.post(
        "/reports/new",
        data=report_payload(),
        content_type="multipart/form-data",
    )
    report_url = created.location
    detail = client.get(report_url)
    assert b"Report this item" in detail.data
    assert b'data-contact-dialog' in detail.data
    assert b"Contact the administrator" in detail.data

    invalid = client.post(
        f"{report_url}/contact",
        data={"reason": "invalid", "reply_email": "bad", "details": "short"},
        follow_redirects=True,
    )
    assert b"Choose a valid reason" in invalid.data
    assert b"between 20 and 2,000" in invalid.data
    with app.app_context():
        assert ReportContact.query.count() == 0

    submitted = client.post(
        f"{report_url}/contact",
        data={
            "reason": "inaccurate",
            "reply_email": "reporter@example.com",
            "details": "The price information shown in this report needs administrator review.",
        },
        follow_redirects=True,
    )
    assert b"sent to the site administrator" in submitted.data
    with app.app_context():
        contact = ReportContact.query.one()
        assert contact.report.name == "North Star Coffee"
        assert contact.sender.email == "reporter@example.com"
        assert contact.reason == "inaccurate"
        assert contact.is_resolved is False


def test_anonymous_report_contact_prompts_login(client, auth):
    auth.signup()
    created = client.post(
        "/reports/new",
        data=report_payload(),
        content_type="multipart/form-data",
    )
    report_url = created.location
    auth.logout()
    detail = client.get(report_url)
    assert b"Sign in to contact the administrator" in detail.data
    response = client.post(f"{report_url}/contact", data={})
    assert response.status_code == 302
    assert "/login" in response.location


def test_only_configured_admin_can_review_and_resolve_contacts(client, auth, app):
    auth.signup()
    created = client.post(
        "/reports/new",
        data=report_payload(),
        content_type="multipart/form-data",
    )
    client.post(
        f"{created.location}/contact",
        data={
            "reason": "privacy",
            "reply_email": "reporter@example.com",
            "details": "This message identifies private information that should be reviewed promptly.",
        },
    )
    with app.app_context():
        contact_guid = ReportContact.query.one().guid

    assert client.get("/admin/report-contacts").status_code == 403
    app.config["ADMIN_EMAIL"] = "reporter@example.com"
    inbox = client.get("/admin/report-contacts")
    assert inbox.status_code == 200
    assert b"Personal or private information" in inbox.data
    assert b"North Star Coffee" in inbox.data

    resolved = client.post(
        f"/admin/report-contacts/{contact_guid}/resolve",
        follow_redirects=True,
    )
    assert b"Contact status updated" in resolved.data
    with app.app_context():
        assert ReportContact.query.one().is_resolved is True

    auth.logout()
    auth.signup(email="other@example.com")
    assert client.get("/admin/report-contacts").status_code == 403


def test_profile_picture_password_and_own_reports(client, auth, app):
    auth.signup()
    created = client.post(
        "/reports/new",
        data=report_payload(),
        content_type="multipart/form-data",
    )

    profile = client.get("/profile")
    assert profile.status_code == 200
    assert b"My profile" in profile.data
    assert profile.data.count(b"data-language-select") == 2
    assert profile.data.count(b"data-theme-select") == 2
    assert profile.data.count(b"data-preference-trigger") == 1
    assert b"Choose your language, appearance, and color in one place" in profile.data
    assert b"North Star Coffee" in profile.data
    assert created.location.encode() in profile.data
    assert b"@reporter" in profile.data
    assert profile.data.count(b"data-preserve-scroll") == 5
    assert profile.data.count(b"data-password-visibility-toggle") == 3
    assert b"data-new-password-check" in profile.data
    assert b"data-confirm-password-check" in profile.data
    password_card = profile.data.split(
        b'id="profile-password-settings"', 1
    )[1].split(b"</article>", 1)[0]
    assert b'class="button button-coral" type="submit">Change password' in password_card

    username = client.post(
        "/profile/username",
        data={"username": "Updated_User"},
        follow_redirects=True,
    )
    assert b"Username updated" in username.data
    assert username.history[0].location.endswith("/profile")
    username_card = username.data.split(
        b'id="profile-username-settings"', 1
    )[1].split(b"</article>", 1)[0]
    assert b"profile-form-status-success" in username_card
    assert b"Username updated" in username_card
    assert b'<div class="flash-stack"' not in username.data
    with app.app_context():
        assert User.query.one().username == "updated_user"

    picture = client.post(
        "/profile/picture",
        data={
            "profile_picture": (
                io.BytesIO(b"profile image bytes"),
                "portrait.png",
                "image/png",
            )
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"Profile picture updated" in picture.data
    assert picture.history[0].location.endswith("/profile")
    picture_card = picture.data.split(
        b'id="profile-picture-settings"', 1
    )[1].split(b"</article>", 1)[0]
    assert b"profile-form-status-success" in picture_card
    assert b"Profile picture updated" in picture_card
    assert picture.data.count(b"data-preserve-scroll") == 6
    with app.app_context():
        user = User.query.one()
        picture_url = f"/profile-pictures/{user.id}"
        picture_path = Path(app.config["UPLOAD_FOLDER"]) / user.profile_image_name
        assert user.profile_image_mime == "image/png"
        assert picture_path.is_file()
    assert client.get(picture_url).data == b"profile image bytes"

    wrong_password = client.post(
        "/profile/password",
        data={
            "current_password": "incorrect",
            "new_password": "replacement123",
            "confirm_password": "replacement123",
        },
        follow_redirects=True,
    )
    assert b"Current password is incorrect" in wrong_password.data
    assert wrong_password.history[0].location.endswith("/profile")
    password_error_card = wrong_password.data.split(
        b'id="profile-password-settings"', 1
    )[1].split(b"</article>", 1)[0]
    assert b"profile-form-status-error" in password_error_card
    assert b"Current password is incorrect" in password_error_card

    changed = client.post(
        "/profile/password",
        data={
            "current_password": "password123",
            "new_password": "replacement123",
            "confirm_password": "replacement123",
        },
        follow_redirects=True,
    )
    assert b"Password changed" in changed.data
    assert changed.history[0].location.endswith("/profile")
    password_success_card = changed.data.split(
        b'id="profile-password-settings"', 1
    )[1].split(b"</article>", 1)[0]
    assert b"profile-form-status-success" in password_success_card
    assert b"Password changed" in password_success_card
    auth.logout()
    assert b"Email, username, or password is incorrect" in auth.login().data
    assert b"Welcome back" in auth.login(password="replacement123").data
    auth.logout()
    assert b"Welcome back" in auth.login(
        username="UPDATED_USER", password="replacement123"
    ).data

    removed = client.post("/profile/picture/remove", follow_redirects=True)
    assert b"Profile picture removed" in removed.data
    assert removed.history[0].location.endswith("/profile")
    removed_picture_card = removed.data.split(
        b'id="profile-picture-settings"', 1
    )[1].split(b"</article>", 1)[0]
    assert b"profile-form-status-success" in removed_picture_card
    assert b"Profile picture removed" in removed_picture_card
    assert not picture_path.exists()


def test_password_change_supports_in_place_json_status(client, auth):
    auth.signup(password="password123")

    rejected = client.post(
        "/profile/password",
        data={
            "current_password": "incorrect",
            "new_password": "replacement123",
            "confirm_password": "replacement123",
        },
        headers={"Accept": "application/json"},
    )
    assert rejected.status_code == 400
    assert rejected.json == {
        "ok": False,
        "message": "Current password is incorrect.",
    }

    changed = client.post(
        "/profile/password",
        data={
            "current_password": "password123",
            "new_password": "replacement123",
            "confirm_password": "replacement123",
        },
        headers={"Accept": "application/json"},
    )
    assert changed.status_code == 200
    assert changed.json == {"ok": True, "message": "Password changed."}


def test_admin_can_archive_delete_reports_and_manage_users(client, auth, app):
    auth.signup(email="member@example.com", password="member-pass-123")
    created = client.post(
        "/reports/new",
        data=report_payload(),
        content_type="multipart/form-data",
    )
    report_url = created.location
    with app.app_context():
        member = User.query.filter_by(email="member@example.com").one()
        member_id = member.id
        report = ShopReport.query.one()
        report_guid = report.guid
        media_id = report.media[0].id
        media_path = Path(app.config["UPLOAD_FOLDER"]) / report.media[0].stored_name
        assert media_path.is_file()

    auth.logout()
    auth.signup(email="admin@example.com", password="admin-pass-123")
    app.config["ADMIN_EMAIL"] = "admin@example.com"
    dashboard = client.get("/admin")
    assert dashboard.status_code == 200
    assert b"Reports and users" in dashboard.data
    assert b"member@example.com" in dashboard.data

    archived = client.post(
        f"/admin/reports/{report_guid}/archive",
        follow_redirects=True,
    )
    assert b"Report archived" in archived.data
    with app.app_context():
        report = ShopReport.query.one()
        assert report.archived_at is not None
        assert report.updated_at == report.created_at

    auth.logout()
    assert b"Welcome back" in auth.login(
        email="member@example.com", password="member-pass-123"
    ).data
    assert b"North Star Coffee" not in client.get("/").data
    assert client.get(report_url).status_code == 200
    assert b"Archived report" in client.get(report_url).data
    assert client.get(f"{report_url}/edit").status_code == 403
    assert b"Archived" in client.get("/profile").data
    auth.logout()
    assert client.get(report_url).status_code == 404
    assert client.get(f"/media/{media_id}").status_code == 404

    assert b"Welcome back" in auth.login(
        email="admin@example.com", password="admin-pass-123"
    ).data
    banned = client.post(f"/admin/users/{member_id}/ban", follow_redirects=True)
    assert b"User banned" in banned.data
    reset = client.post(
        f"/admin/users/{member_id}/password",
        data={
            "new_password": "member-reset-123",
            "confirm_password": "member-reset-123",
        },
        follow_redirects=True,
    )
    assert b"User password reset" in reset.data
    auth.logout()
    blocked = auth.login(
        email="member@example.com", password="member-reset-123"
    )
    assert blocked.status_code == 403
    assert b"account has been banned" in blocked.data

    assert b"Welcome back" in auth.login(
        email="admin@example.com", password="admin-pass-123"
    ).data
    unbanned = client.post(f"/admin/users/{member_id}/ban", follow_redirects=True)
    assert b"User ban removed" in unbanned.data
    deleted = client.post(
        f"/admin/reports/{report_guid}/delete",
        follow_redirects=True,
    )
    assert b"Report permanently deleted" in deleted.data
    with app.app_context():
        assert ShopReport.query.count() == 0
        assert User.query.filter_by(email="member@example.com").one().is_banned is False
    assert not media_path.exists()

    auth.logout()
    assert b"Welcome back" in auth.login(
        email="member@example.com", password="member-reset-123"
    ).data


def test_existing_sqlite_reports_receive_guids(tmp_path):
    from app import create_app

    database_path = tmp_path / "legacy.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            'CREATE TABLE "user" (id INTEGER PRIMARY KEY, email VARCHAR(255))'
        )
        connection.execute(
            'INSERT INTO "user" (id, email) VALUES (1, "Legacy.User@example.com")'
        )
        connection.execute("CREATE TABLE shop_report (id INTEGER PRIMARY KEY)")
        connection.execute("INSERT INTO shop_report (id) VALUES (1)")

    create_app(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path}",
            "UPLOAD_FOLDER": str(tmp_path / "legacy-uploads"),
            "SECRET_KEY": "migration-test-secret",
            "ADMIN_EMAIL": "",
            "ADMIN_PASSWORD": "",
            "ADMIN_USERNAME": "",
        }
    )

    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(shop_report)")
        }
        user_columns = {
            row[1] for row in connection.execute('PRAGMA table_info("user")')
        }
        migrated_guid = connection.execute(
            "SELECT guid FROM shop_report WHERE id = 1"
        ).fetchone()[0]
        migrated_username = connection.execute(
            'SELECT username FROM "user" WHERE id = 1'
        ).fetchone()[0]
    assert {
        "guid",
        "is_online",
        "updated_at",
        "hashtags_json",
        "controversy_links_json",
        "related_shops_json",
        "address_en_us",
        "address_zh_tw",
        "archived_at",
    }.issubset(columns)
    assert {
        "profile_image_name",
        "profile_image_mime",
        "is_banned",
        "banned_at",
        "username",
    }.issubset(user_columns)
    assert str(uuid.UUID(migrated_guid)) == migrated_guid
    assert migrated_username == "legacy_user"


def test_nearby_search_filters_by_distance(client, auth):
    auth.signup()
    client.post("/reports/new", data=report_payload(), content_type="multipart/form-data")
    far = report_payload(
        name="Far Away Shop",
        address="1 Far Road, Kaohsiung",
        latitude="22.6273",
        longitude="120.3014",
        proof=(io.BytesIO(b"another image"), "proof.png", "image/png"),
    )
    client.post("/reports/new", data=far, content_type="multipart/form-data")
    response = client.get("/?lat=25.033&lng=121.5654&radius=10")
    assert b"North Star Coffee" in response.data
    assert b"Far Away Shop" not in response.data
    assert b"nearest first" in response.data


def create_recent_reports(client, app, count):
    for index in range(count):
        client.post(
            "/reports/new",
            data=report_payload(
                name=f"Recent Shop {index}",
                proof=(io.BytesIO(b"image bytes"), f"proof{index}.jpg", "image/jpeg"),
            ),
            content_type="multipart/form-data",
        )
    with app.app_context():
        for index, report in enumerate(ShopReport.query.order_by(ShopReport.id).all()):
            report.created_at = datetime(2026, 1, index + 1, tzinfo=timezone.utc)
        db.session.commit()


def test_home_lists_one_batch_of_recent_reports(client, auth, app):
    auth.signup()
    create_recent_reports(client, app, 3)

    app.config["HOME_RECENT_REPORTS_COUNT"] = 2
    response = client.get("/")
    assert b"Recent reports" in response.data
    assert b"Recent Shop 2" in response.data
    assert b"Recent Shop 1" in response.data
    assert b"Recent Shop 0" not in response.data
    assert b"Keep scrolling to load more" in response.data
    assert b"data-report-more" in response.data

    searched = client.get("/?q=Recent+Shop+0")
    assert b"Recent Shop 0" in searched.data
    assert b"Reports near you" in searched.data
    assert b"data-report-more" not in searched.data


def test_home_load_more_link_keeps_the_reports_already_listed(client, auth, app):
    auth.signup()
    create_recent_reports(client, app, 3)

    app.config["HOME_RECENT_REPORTS_COUNT"] = 2
    response = client.get("/?offset=2")
    assert b"Recent Shop 2" in response.data
    assert b"Recent Shop 1" in response.data
    assert b"Recent Shop 0" in response.data
    assert b"Showing every report, newest first." in response.data
    assert b"data-report-more" not in response.data


def test_report_batch_endpoint_returns_the_next_cards(client, auth, app):
    auth.signup()
    create_recent_reports(client, app, 3)

    app.config["HOME_RECENT_REPORTS_COUNT"] = 2
    first = client.get("/api/reports/page?offset=0").get_json()
    assert first["has_more"] is True
    assert first["next_offset"] == 2
    assert first["html"].count('<article class="report-card">') == 2
    assert "Recent Shop 2" in first["html"]
    assert "Recent Shop 0" not in first["html"]

    second = client.get("/api/reports/page?offset=2").get_json()
    assert second["has_more"] is False
    assert second["next_offset"] == 3
    assert "Recent Shop 0" in second["html"]

    assert client.get("/api/reports/page?offset=not-a-number").get_json() == first


def png_upload_bytes(size=(1600, 1200)):
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", size, (32, 96, 64)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_media_thumbnail_is_downscaled_cached_and_reused(client, auth, app):
    from PIL import Image

    original = png_upload_bytes()
    auth.signup()
    client.post(
        "/reports/new",
        data=report_payload(proof=(io.BytesIO(original), "evidence.png", "image/png")),
        content_type="multipart/form-data",
    )
    with app.app_context():
        media_id = ShopReport.query.first().media[0].id
        thumbnail_folder = Path(app.config["THUMBNAIL_FOLDER"])

    response = client.get(f"/media/{media_id}/thumbnail")
    assert response.status_code == 200
    assert response.mimetype == "image/webp"
    assert len(response.data) < len(original)
    assert "immutable" in response.headers["Cache-Control"]
    with Image.open(io.BytesIO(response.data)) as thumbnail:
        assert max(thumbnail.size) <= 720
        assert thumbnail.size == (720, 540)

    cached = list(thumbnail_folder.glob("*.webp"))
    assert len(cached) == 1
    # A second request is served from the cache instead of being generated again.
    cached[0].write_bytes(b"cached-thumbnail-marker")
    repeated = client.get(f"/media/{media_id}/thumbnail")
    assert repeated.data == b"cached-thumbnail-marker"
    assert len(list(thumbnail_folder.glob("*.webp"))) == 1

    assert client.get(f"/media/{media_id}").mimetype == "image/png"


def test_media_thumbnail_falls_back_to_the_original_upload(client, auth, app):
    auth.signup()
    client.post("/reports/new", data=report_payload(), content_type="multipart/form-data")
    with app.app_context():
        media_id = ShopReport.query.first().media[0].id

    # The stored file is not a decodable image, so the route serves the upload.
    response = client.get(f"/media/{media_id}/thumbnail")
    assert response.status_code == 200
    assert response.mimetype == "image/jpeg"
    assert response.data == b"fake image bytes"


def test_deleting_a_report_removes_its_cached_thumbnail(client, auth, app):
    auth.signup("admin@example.com", "password123", username="admin")
    app.config["ADMIN_EMAIL"] = "admin@example.com"
    client.post(
        "/reports/new",
        data=report_payload(
            proof=(io.BytesIO(png_upload_bytes((400, 300))), "evidence.png", "image/png")
        ),
        content_type="multipart/form-data",
    )
    with app.app_context():
        report = ShopReport.query.first()
        media_id, report_guid = report.media[0].id, report.guid
        thumbnail_folder = Path(app.config["THUMBNAIL_FOLDER"])

    client.get(f"/media/{media_id}/thumbnail")
    assert len(list(thumbnail_folder.glob("*.webp"))) == 1

    client.post(f"/admin/reports/{report_guid}/delete", follow_redirects=True)
    assert list(thumbnail_folder.glob("*.webp")) == []


def test_invalid_social_url_and_file_are_rejected(client, auth, app):
    auth.signup()
    data = report_payload(
        instagram="not-a-url",
        hashtags=" ".join(f"tag{index}" for index in range(11)) + " invalid-tag",
        controversy_links="\n".join(
            [f"https://example.com/source/{index}" for index in range(11)]
            + ["javascript:alert('not-safe')"]
        ),
        proof=(io.BytesIO(b"not allowed"), "notes.txt", "text/plain"),
    )
    response = client.post("/reports/new", data=data, content_type="multipart/form-data")
    assert b"full http(s) links" in response.data
    assert b"no more than 10 hashtags" in response.data
    assert b"letters, numbers, or underscores" in response.data
    assert b"no more than 10 controversy links" in response.data
    assert b"one complete http(s) URL" in response.data
    assert b"not a supported image or video" in response.data
    with app.app_context():
        assert ShopReport.query.count() == 0


def admin_password_app(tmp_path, database_path, **overrides):
    from app import create_app

    config = {
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path}",
        "UPLOAD_FOLDER": str(tmp_path / "uploads"),
        "LINK_PREVIEW_FOLDER": str(tmp_path / "link-previews"),
        "THUMBNAIL_FOLDER": str(tmp_path / "thumbnails"),
        "SECRET_KEY": "test-secret",
        "TURNSTILE_SITE_KEY": "",
        "TURNSTILE_SECRET_KEY": "",
        "ADMIN_EMAIL": "admin@example.com",
        "ADMIN_PASSWORD": "env-admin-password",
        "ADMIN_USERNAME": "",
    }
    config.update(overrides)
    return create_app(config)


def test_admin_password_creates_admin_account_at_startup(tmp_path):
    app = admin_password_app(tmp_path, tmp_path / "admin.db")
    client = app.test_client()
    response = client.post(
        "/login",
        data={"email": "admin@example.com", "password": "env-admin-password"},
        follow_redirects=True,
    )
    assert b"Welcome back" in response.data
    with app.app_context():
        admin_user = User.query.filter_by(email="admin@example.com").one()
        assert admin_user.username == "admin"


def test_admin_password_resyncs_changed_password_on_restart(tmp_path):
    database_path = tmp_path / "admin.db"
    app = admin_password_app(tmp_path, database_path)
    with app.app_context():
        admin_user = User.query.filter_by(email="admin@example.com").one()
        admin_user.set_password("changed-by-profile")
        db.session.commit()

    restarted = admin_password_app(tmp_path, database_path)
    with restarted.app_context():
        admin_user = User.query.filter_by(email="admin@example.com").one()
        assert admin_user.check_password("env-admin-password")
        assert User.query.count() == 1


def test_admin_password_requires_email_and_minimum_length(tmp_path):
    with pytest.raises(RuntimeError, match="requires ADMIN_EMAIL"):
        admin_password_app(tmp_path, tmp_path / "a.db", ADMIN_EMAIL="")
    with pytest.raises(RuntimeError, match="at least 8 characters"):
        admin_password_app(tmp_path, tmp_path / "b.db", ADMIN_PASSWORD="short")


def test_admin_username_allows_login_with_username_or_email(tmp_path):
    app = admin_password_app(
        tmp_path, tmp_path / "admin.db", ADMIN_USERNAME="chief_admin"
    )
    client = app.test_client()
    for identifier in ("chief_admin", "admin@example.com"):
        response = client.post(
            "/login",
            data={"email": identifier, "password": "env-admin-password"},
            follow_redirects=True,
        )
        assert b"Welcome back" in response.data
        client.post("/logout")
    with app.app_context():
        admin_user = User.query.filter_by(email="admin@example.com").one()
        assert admin_user.username == "chief_admin"


def test_admin_username_renames_existing_account_on_restart(tmp_path):
    database_path = tmp_path / "admin.db"
    admin_password_app(tmp_path, database_path)

    restarted = admin_password_app(
        tmp_path, database_path, ADMIN_USERNAME="chief_admin"
    )
    with restarted.app_context():
        admin_user = User.query.filter_by(email="admin@example.com").one()
        assert admin_user.username == "chief_admin"
        assert User.query.count() == 1


def test_admin_cannot_ban_own_account(client, auth, app):
    auth.signup(email="member@example.com", password="member-pass-123")
    with app.app_context():
        member_id = User.query.filter_by(email="member@example.com").one().id
    auth.logout()

    auth.signup(email="admin@example.com", password="admin-pass-123")
    app.config["ADMIN_EMAIL"] = "admin@example.com"
    with app.app_context():
        admin_id = User.query.filter_by(email="admin@example.com").one().id

    dashboard = client.get("/admin").data.decode()
    admin_card = dashboard.split("admin-user-card")[1:]
    admin_markup = next(card for card in admin_card if "admin@example.com" in card)
    member_markup = next(card for card in admin_card if "member@example.com" in card)
    assert "disabled" in admin_markup
    assert "cannot be banned" in admin_markup
    assert "button-danger" in member_markup

    blocked = client.post(f"/admin/users/{admin_id}/ban", follow_redirects=True)
    assert b"cannot be banned" in blocked.data
    with app.app_context():
        assert db.session.get(User, admin_id).is_banned is False

    banned = client.post(f"/admin/users/{member_id}/ban", follow_redirects=True)
    assert b"User banned" in banned.data
    assert "button-outline" in next(
        card
        for card in client.get("/admin").data.decode().split("admin-user-card")[1:]
        if "member@example.com" in card
    )


def test_admin_username_validation_and_collision(tmp_path):
    with pytest.raises(RuntimeError, match="requires ADMIN_EMAIL"):
        admin_password_app(
            tmp_path,
            tmp_path / "a.db",
            ADMIN_EMAIL="",
            ADMIN_PASSWORD="",
            ADMIN_USERNAME="chief_admin",
        )
    with pytest.raises(RuntimeError, match="letters, numbers, or underscores"):
        admin_password_app(tmp_path, tmp_path / "b.db", ADMIN_USERNAME="no")

    database_path = tmp_path / "admin.db"
    app = admin_password_app(tmp_path, database_path)
    with app.app_context():
        other_user = User(
            display_name="Other Person",
            username="chief_admin",
            email="other@example.com",
        )
        other_user.set_password("password123")
        db.session.add(other_user)
        db.session.commit()
    with pytest.raises(RuntimeError, match="already used by another account"):
        admin_password_app(tmp_path, database_path, ADMIN_USERNAME="chief_admin")
