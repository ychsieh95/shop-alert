from __future__ import annotations

import json
import hashlib
import math
import os
import re
import shutil
import tempfile
import time
import uuid
from difflib import SequenceMatcher
from pathlib import Path
from threading import Lock
from urllib.parse import urlparse

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_login import login_required, current_user
from sqlalchemy import or_, update
from werkzeug.utils import secure_filename

from .extensions import db
from .i18n import SUPPORTED_LOCALES, get_locale, translate
from .cloudflare_url_scanner import CloudflareURLScannerError, scan_url
from .link_preview import LinkPreviewError, generate_link_preview, is_public_http_url
from .media_files import make_media_file_readable
from .media_rotation import parse_rotation, rotate_media_file
from .thumbnails import (
    THUMBNAIL_MIME_TYPE,
    ThumbnailError,
    discard_thumbnail,
    ensure_thumbnail,
)
from .models import (
    ProofMedia,
    ReportContact,
    ShopReport,
    User,
    is_valid_username,
    normalize_username,
    utcnow,
)


main_bp = Blueprint("main", __name__)

IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}
VIDEO_EXTENSIONS = {"mp4", "webm", "mov", "m4v"}
MEDIA_UPLOAD_TOKEN_PATTERN = re.compile(r"new:[A-Za-z0-9_-]{1,80}\Z")
SOCIAL_FIELDS = {
    "facebook": "Facebook",
    "instagram": "Instagram",
    "threads": "Threads",
    "tiktok": "TikTok",
    "other": "Other",
}
CONTACT_REASONS = {
    "inaccurate": "Inaccurate or misleading information",
    "privacy": "Personal or private information",
    "copyright": "Copyright or ownership concern",
    "harassment": "Harassment or abusive content",
    "other": "Other concern",
}
MAX_CONTROVERSY_LINKS = 10
MAX_CONTROVERSY_LINK_LENGTH = 2048
MAX_HASHTAGS = 10
MAX_HASHTAG_LENGTH = 30
DEFAULT_HASHTAG_SUGGESTIONS = {
    "en-US": ("service", "pricing", "refund", "quality", "delivery", "support"),
    "zh-TW": ("服務", "價格", "退款", "品質", "配送", "客服"),
}
MAX_POPULAR_HASHTAGS = 6
MAX_RELATED_SHOPS = 10
MAX_RELATED_SHOP_NAME_LENGTH = 180
MAX_RELATED_SHOP_ADDRESS_LENGTH = 500
MAX_RELATED_SHOP_RESULTS = 8
MAX_MEDIA_NAME_LENGTH = 255
# Batches a single home-page render may contain, and the furthest batch the
# scroll-loading endpoint will start from.
MAX_BROWSE_BATCHES = 20
MAX_BROWSE_OFFSET = 100_000
MAX_PROFILE_IMAGE_BYTES = 5 * 1024 * 1024
LINK_PREVIEW_LOCK = Lock()
UPDATE_HISTORY_PATH = Path(__file__).resolve().parent.parent / "data" / "update_history.json"


def _load_update_history() -> list[dict]:
    with UPDATE_HISTORY_PATH.open(encoding="utf-8") as history_file:
        history = json.load(history_file)
    if not isinstance(history, list) or not history:
        raise ValueError("Update history must be a non-empty list.")
    previous_date = "9999-99-99"
    required = {"date", "date_label", "title", "summary", "items"}
    for entry in history:
        if not isinstance(entry, dict) or set(entry) != required:
            raise ValueError("Update history contains an invalid entry.")
        if entry["date"] > previous_date:
            raise ValueError("Update history must be newest first.")
        previous_date = entry["date"]
        for field in ("date_label", "title", "summary", "items"):
            if set(entry[field]) != SUPPORTED_LOCALES:
                raise ValueError(f"Update history has incomplete {field} translations.")
    return history


@main_bp.post("/preferences/language")
def set_language():
    locale = request.form.get("locale", "")
    if locale in SUPPORTED_LOCALES:
        session.permanent = True
        session["locale"] = locale
    destination = request.form.get("next", "")
    if not destination.startswith("/") or destination.startswith("//"):
        destination = url_for("main.home")
    return redirect(destination)


@main_bp.get("/updates")
def updates():
    locale = get_locale()
    entries = [
        {
            "date": entry["date"],
            "date_label": entry["date_label"][locale],
            "title": entry["title"][locale],
            "summary": entry["summary"][locale],
            "items": entry["items"][locale],
        }
        for entry in _load_update_history()
    ]
    return render_template("info/updates.html", update_entries=entries)


@main_bp.get("/licenses")
def licenses():
    return render_template("info/licenses.html")


@main_bp.get("/privacy")
def privacy():
    return render_template(
        "info/privacy.html",
        privacy_contact_email=current_app.config.get("ADMIN_EMAIL", ""),
    )


@main_bp.get("/introduction")
def introduction():
    return render_template("info/introduction.html")


def _float_between(value: str, minimum: float, maximum: float) -> float | None:
    if not value:
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if minimum <= number <= maximum else None


def _valid_url(value: str) -> bool:
    parsed = urlparse(value)
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.netloc)
        and not any(
            character.isspace() or ord(character) < 32 or ord(character) == 127
            for character in value
        )
    )


def _parse_controversy_links(value: str) -> list[str]:
    return list(dict.fromkeys(line.strip() for line in value.splitlines() if line.strip()))


def _validate_controversy_links(links: list[str]) -> list[str]:
    errors = []
    if len(links) > MAX_CONTROVERSY_LINKS:
        errors.append("Add no more than 10 controversy links.")
    if any(
        len(link) > MAX_CONTROVERSY_LINK_LENGTH or not _valid_url(link)
        for link in links
    ):
        errors.append("Use one complete http(s) URL per controversy link.")
    return errors


def _parse_hashtags(value: str) -> list[str]:
    hashtags = []
    seen = set()
    for item in value.replace(",", " ").replace("，", " ").split():
        hashtag = item.lstrip("#＃")
        if not hashtag:
            continue
        normalized = hashtag.casefold()
        if normalized not in seen:
            seen.add(normalized)
            hashtags.append(hashtag)
    return sorted(hashtags, key=str.casefold)


def _validate_hashtags(hashtags: list[str]) -> list[str]:
    errors = []
    if len(hashtags) > MAX_HASHTAGS:
        errors.append("Add no more than 10 hashtags.")
    if any(
        not 1 <= len(hashtag) <= MAX_HASHTAG_LENGTH
        or not all(character.isalnum() or character == "_" for character in hashtag)
        for hashtag in hashtags
    ):
        errors.append("Use 1 to 30 letters, numbers, or underscores per hashtag.")
    return errors


def _parse_related_shops(form) -> list[dict[str, str]]:
    """Read the parallel related-shop form fields into ordered, unique entries."""

    guids = form.getlist("related_shop_guid")
    names = form.getlist("related_shop_name")
    addresses = form.getlist("related_shop_address")
    entries: list[dict[str, str]] = []
    seen = set()
    for index in range(max(len(guids), len(names), len(addresses), 0)):
        guid = guids[index].strip()[:36] if index < len(guids) else ""
        name = names[index].strip() if index < len(names) else ""
        address = addresses[index].strip() if index < len(addresses) else ""
        if guid:
            key = ("report", guid)
            entry = {"guid": guid, "name": "", "address": ""}
        elif name:
            key = ("shop", name.casefold(), address.casefold())
            entry = {"guid": "", "name": name, "address": address}
        else:
            continue
        if key in seen:
            continue
        seen.add(key)
        entries.append(entry)
    return entries


def _validate_related_shops(
    entries: list[dict[str, str]], current_report: ShopReport | None = None
) -> list[str]:
    errors = []
    if len(entries) > MAX_RELATED_SHOPS:
        errors.append("Add no more than 10 related shops.")
    guids = {entry["guid"] for entry in entries if entry["guid"]}
    if current_report is not None and current_report.guid in guids:
        errors.append("A report cannot be listed as its own related shop.")
        guids.discard(current_report.guid)
    if guids:
        known = {
            guid
            for (guid,) in ShopReport.query.filter(
                ShopReport.guid.in_(guids), ShopReport.archived_at.is_(None)
            ).with_entities(ShopReport.guid)
        }
        if known != guids:
            errors.append("A selected related shop report could not be found.")
    manual = [entry for entry in entries if not entry["guid"]]
    if any(
        not 2 <= len(entry["name"]) <= MAX_RELATED_SHOP_NAME_LENGTH for entry in manual
    ):
        errors.append("Related shop names must be between 2 and 180 characters.")
    if any(
        len(entry["address"]) > MAX_RELATED_SHOP_ADDRESS_LENGTH for entry in manual
    ):
        errors.append("Related shop addresses must be 500 characters or fewer.")
    return errors


def _related_shop_details(
    entries: list[dict[str, str]], locale: str
) -> list[dict[str, object]]:
    """Resolve stored entries into display rows, dropping unavailable reports."""

    guids = [entry["guid"] for entry in entries if entry["guid"]]
    linked = {}
    if guids:
        linked = {
            report.guid: report
            for report in ShopReport.query.filter(
                ShopReport.guid.in_(set(guids)), ShopReport.archived_at.is_(None)
            )
        }
    details = []
    for entry in entries:
        if entry["guid"]:
            report = linked.get(entry["guid"])
            if report is None:
                continue
            details.append(
                {
                    "guid": report.guid,
                    "name": report.name,
                    "address": ""
                    if report.is_online
                    else report.localized_address(locale),
                    "is_online": report.is_online,
                    "url": url_for("main.report_detail", report_guid=report.guid),
                }
            )
        else:
            details.append(
                {
                    "guid": "",
                    "name": entry["name"],
                    "address": entry["address"],
                    "is_online": False,
                    "url": "",
                }
            )
    return details


def _hashtag_suggestions(locale: str) -> tuple[list[str], list[str]]:
    counts: dict[str, int] = {}
    labels: dict[str, str] = {}
    rows = (
        ShopReport.query.filter(ShopReport.archived_at.is_(None))
        .with_entities(ShopReport.hashtags_json)
        .order_by(ShopReport.created_at.desc())
        .all()
    )
    for (raw_hashtags,) in rows:
        try:
            hashtags = json.loads(raw_hashtags)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(hashtags, list):
            continue
        for hashtag in hashtags:
            if not isinstance(hashtag, str) or _validate_hashtags([hashtag]):
                continue
            normalized = hashtag.casefold()
            labels.setdefault(normalized, hashtag)
            counts[normalized] = counts.get(normalized, 0) + 1

    ranked = sorted(counts, key=lambda hashtag: (-counts[hashtag], hashtag))
    popular = [labels[hashtag] for hashtag in ranked[:MAX_POPULAR_HASHTAGS]]
    popular_keys = {hashtag.casefold() for hashtag in popular}
    suggested = [
        hashtag
        for hashtag in DEFAULT_HASHTAG_SUGGESTIONS[locale]
        if hashtag.casefold() not in popular_keys
    ]
    return popular, suggested


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _normalized_match_text(value: str | None) -> str:
    return " ".join((value or "").casefold().split())


def _text_match_score(value: str, candidate: str | None) -> float:
    value = _normalized_match_text(value)
    candidate = _normalized_match_text(candidate)
    if not value or not candidate:
        return 0.0
    if value == candidate:
        return 1.0
    score = SequenceMatcher(None, value, candidate).ratio()
    if len(value) >= 3 and value in candidate:
        score = max(score, 0.86 + 0.12 * min(1, len(value) / len(candidate)))
    value_words = set(value.split())
    candidate_words = set(candidate.split())
    if value_words and candidate_words:
        overlap = len(value_words & candidate_words) / len(value_words | candidate_words)
        score = max(score, overlap * 0.9)
    return score


def _similar_report_score(
    report: ShopReport,
    name: str,
    address: str,
    place_id: str,
    latitude: float | None,
    longitude: float | None,
) -> float:
    if place_id and report.google_place_id == place_id:
        return 1.0

    name_score = _text_match_score(name, report.name)
    address_score = max(
        _text_match_score(address, report.address),
        _text_match_score(address, report.address_en_us),
        _text_match_score(address, report.address_zh_tw),
    )
    location_score = 0.0
    if (
        latitude is not None
        and longitude is not None
        and report.latitude is not None
        and report.longitude is not None
    ):
        distance = _distance_km(
            latitude, longitude, report.latitude, report.longitude
        )
        if distance <= 0.1:
            location_score = 1.0
        elif distance <= 1:
            location_score = max(0.55, 1 - distance / 1.25)

    place_score = max(address_score, location_score)
    if name and (address or location_score):
        return name_score * 0.7 + place_score * 0.3
    return name_score if name else place_score


def _validate_media(upload) -> tuple[str, str] | None:
    filename = secure_filename(upload.filename or "")
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    mime = (upload.mimetype or "application/octet-stream").lower()
    if extension in IMAGE_EXTENSIONS and mime.startswith("image/"):
        return "image", extension
    if extension in VIDEO_EXTENSIONS and mime.startswith("video/"):
        return "video", extension
    return None


def _media_display_name(value: str, fallback: str, extension: str) -> str | None:
    name = (value or fallback).strip()
    if (
        not name
        or len(name) > MAX_MEDIA_NAME_LENGTH
        or name in {".", ".."}
        or "/" in name
        or "\\" in name
        or any(ord(character) < 32 or ord(character) == 127 for character in name)
    ):
        return None
    submitted_extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return name if submitted_extension == extension.lower() else None


def _media_upload_token(values: list[str], index: int) -> str | None:
    if index >= len(values):
        return f"new:{index}"
    token = values[index].strip()
    return token if MEDIA_UPLOAD_TOKEN_PATTERN.fullmatch(token) else None


def _ordered_media_tokens(value: str, expected_tokens: list[str]) -> list[str] | None:
    """Validate a client order and append any no-JavaScript fallback tokens."""

    if len(expected_tokens) != len(set(expected_tokens)):
        return None
    if not value.strip():
        return expected_tokens
    try:
        submitted_tokens = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None
    if (
        not isinstance(submitted_tokens, list)
        or any(not isinstance(token, str) for token in submitted_tokens)
        or len(submitted_tokens) != len(set(submitted_tokens))
        or any(token not in expected_tokens for token in submitted_tokens)
    ):
        return None
    return submitted_tokens + [
        token for token in expected_tokens if token not in submitted_tokens
    ]


def _is_current_user_admin() -> bool:
    admin_email = current_app.config.get("ADMIN_EMAIL", "")
    return bool(
        admin_email
        and current_user.is_authenticated
        and current_user.email.lower() == admin_email
    )


def _can_view_archived_report(report: ShopReport) -> bool:
    return bool(
        current_user.is_authenticated
        and (current_user.id == report.author_id or _is_current_user_admin())
    )


def _report_by_guid_or_404(report_guid) -> ShopReport:
    report = ShopReport.query.filter_by(guid=str(report_guid)).first_or_404()
    if report.archived_at is not None and not _can_view_archived_report(report):
        abort(404)
    return report


def _browse_filters() -> dict:
    """Read the shared query parameters used by the home listing and its batches."""

    return {
        "q": request.args.get("q", "").strip()[:120],
        "user_lat": _float_between(request.args.get("lat", ""), -90, 90),
        "user_lng": _float_between(request.args.get("lng", ""), -180, 180),
        "radius": _float_between(request.args.get("radius", "10"), 1, 100) or 10,
    }


def _browse_offset(maximum: int) -> int:
    """Read the index of the first report to list, ignoring unusable values."""

    try:
        offset = int(request.args.get("offset", "0"))
    except ValueError:
        return 0
    return max(0, min(offset, maximum))


def _browse_reports(
    *, q: str, user_lat, user_lng, radius: float, start: int, count: int
) -> tuple[list[ShopReport], bool]:
    """Return one listing batch plus whether further reports remain after it."""

    query = ShopReport.query.filter(ShopReport.archived_at.is_(None))
    if q:
        pattern = f"%{q}%"
        hashtag_term = q.lstrip("#＃") or q
        hashtag_pattern = f"%{hashtag_term}%"
        query = query.filter(
            or_(
                ShopReport.name.ilike(pattern),
                ShopReport.address.ilike(pattern),
                ShopReport.address_en_us.ilike(pattern),
                ShopReport.address_zh_tw.ilike(pattern),
                ShopReport.controversy.ilike(pattern),
                ShopReport.hashtags_json.ilike(hashtag_pattern),
            )
        )
    query = query.order_by(ShopReport.created_at.desc(), ShopReport.id.desc())

    if user_lat is not None and user_lng is not None:
        # Distance is computed in Python, so nearby results are ranked in full
        # before the requested batch is sliced out of them.
        matched = []
        for report in query.yield_per(100):
            if report.latitude is None or report.longitude is None:
                continue
            distance = _distance_km(
                user_lat, user_lng, report.latitude, report.longitude
            )
            if distance <= radius:
                report.distance_km = distance
                matched.append(report)
        matched.sort(key=lambda item: item.distance_km)
        return matched[start : start + count], len(matched) > start + count

    window = query.offset(start).limit(count + 1).all()
    return window[:count], len(window) > count


@main_bp.get("/")
def home():
    filters = _browse_filters()
    batch_size = int(current_app.config["HOME_RECENT_REPORTS_COUNT"])
    # A full page render repeats every earlier batch, so visitors without
    # JavaScript keep the reports they already loaded when they ask for more.
    offset = _browse_offset((MAX_BROWSE_BATCHES - 1) * batch_size)
    reports, has_more = _browse_reports(**filters, start=0, count=offset + batch_size)
    nearby_mode = filters["user_lat"] is not None and filters["user_lng"] is not None

    return render_template(
        "home.html",
        reports=reports,
        nearby_mode=nearby_mode,
        # Without a keyword or a location the listing is a recent-activity feed.
        recent_mode=not filters["q"] and not nearby_mode,
        has_more=has_more,
        next_offset=len(reports),
        **filters,
    )


@main_bp.get("/api/reports/page")
def reports_page():
    """Render the next listing batch for the home page's scroll loading."""

    filters = _browse_filters()
    batch_size = int(current_app.config["HOME_RECENT_REPORTS_COUNT"])
    offset = _browse_offset(MAX_BROWSE_OFFSET)
    reports, has_more = _browse_reports(**filters, start=offset, count=batch_size)
    return jsonify(
        {
            "html": "".join(
                render_template("_report_card.html", report=report)
                for report in reports
            ),
            "has_more": has_more,
            "next_offset": offset + len(reports),
        }
    )


@main_bp.get("/my/reports")
@login_required
def my_reports():
    reports = (
        ShopReport.query.filter_by(author_id=current_user.id)
        .order_by(ShopReport.created_at.desc())
        .all()
    )
    return render_template("reports/mine.html", reports=reports)


@main_bp.get("/profile")
@login_required
def profile():
    reports = (
        ShopReport.query.filter_by(author_id=current_user.id)
        .order_by(ShopReport.created_at.desc())
        .all()
    )
    return render_template("profile.html", reports=reports)


@main_bp.post("/profile/username")
@login_required
def change_username():
    username = normalize_username(request.form.get("username", ""))
    if not is_valid_username(username):
        flash(
            "Use 3 to 30 letters, numbers, or underscores for the username.",
            "profile-username-error",
        )
    elif User.query.filter(User.username == username, User.id != current_user.id).first():
        flash("That username is already in use.", "profile-username-error")
    else:
        current_user.username = username
        db.session.commit()
        flash("Username updated.", "profile-username-success")
    return redirect(url_for("main.profile"))


def _upload_size(upload) -> int:
    position = upload.stream.tell()
    upload.stream.seek(0, os.SEEK_END)
    size = upload.stream.tell()
    upload.stream.seek(position)
    return size


@main_bp.post("/profile/picture")
@login_required
def update_profile_picture():
    upload = request.files.get("profile_picture")
    media_info = _validate_media(upload) if upload and upload.filename else None
    if not media_info or media_info[0] != "image":
        flash(
            "Choose a supported JPG, PNG, GIF, or WebP image.",
            "profile-picture-error",
        )
        return redirect(url_for("main.profile"))
    if _upload_size(upload) > MAX_PROFILE_IMAGE_BYTES:
        flash(
            "Profile pictures must be 5 MB or smaller.",
            "profile-picture-error",
        )
        return redirect(url_for("main.profile"))

    extension = media_info[1]
    stored_name = f"profile-{uuid.uuid4().hex}.{extension}"
    destination = Path(current_app.config["UPLOAD_FOLDER"]) / stored_name
    old_name = current_user.profile_image_name
    try:
        upload.save(destination)
        current_user.profile_image_name = stored_name
        current_user.profile_image_mime = upload.mimetype
        db.session.commit()
    except Exception:
        db.session.rollback()
        destination.unlink(missing_ok=True)
        current_app.logger.exception("Could not update profile picture")
        flash(
            "The profile picture could not be saved. Please try again.",
            "profile-picture-error",
        )
        return redirect(url_for("main.profile"))

    if old_name and old_name != stored_name:
        (Path(current_app.config["UPLOAD_FOLDER"]) / old_name).unlink(missing_ok=True)
    flash("Profile picture updated.", "profile-picture-success")
    return redirect(url_for("main.profile"))


@main_bp.post("/profile/picture/remove")
@login_required
def remove_profile_picture():
    old_name = current_user.profile_image_name
    current_user.profile_image_name = None
    current_user.profile_image_mime = None
    db.session.commit()
    if old_name:
        (Path(current_app.config["UPLOAD_FOLDER"]) / old_name).unlink(missing_ok=True)
    flash("Profile picture removed.", "profile-picture-success")
    return redirect(url_for("main.profile"))


@main_bp.post("/profile/password")
@login_required
def change_password():
    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    confirmation = request.form.get("confirm_password", "")
    if not current_user.check_password(current_password):
        message = "Current password is incorrect."
        success = False
    elif len(new_password) < 8:
        message = "Password must contain at least 8 characters."
        success = False
    elif new_password != confirmation:
        message = "New password confirmation does not match."
        success = False
    else:
        current_user.set_password(new_password)
        db.session.commit()
        message = "Password changed."
        success = True

    if request.accept_mimetypes.best == "application/json":
        return jsonify({"ok": success, "message": translate(message)}), (
            200 if success else 400
        )

    flash(
        message,
        "profile-password-success" if success else "profile-password-error",
    )
    return redirect(url_for("main.profile"))


@main_bp.get("/profile-pictures/<int:user_id>")
def profile_picture(user_id: int):
    user = db.get_or_404(User, user_id)
    if not user.profile_image_name or not user.profile_image_mime:
        abort(404)
    return send_from_directory(
        current_app.config["UPLOAD_FOLDER"],
        user.profile_image_name,
        mimetype=user.profile_image_mime,
        conditional=True,
    )


@main_bp.get("/api/reports/similar")
@login_required
def similar_reports():
    name = request.args.get("name", "").strip()[:180]
    address = request.args.get("address", "").strip()[:500]
    place_id = request.args.get("place_id", "").strip()[:255]
    exclude_guid = request.args.get("exclude", "").strip()[:36]
    latitude = _float_between(request.args.get("lat", ""), -90, 90)
    longitude = _float_between(request.args.get("lng", ""), -180, 180)
    if len(name) < 2 and len(address) < 4 and not place_id:
        return jsonify({"reports": [], "searched": False})

    query = ShopReport.query.filter(ShopReport.archived_at.is_(None))
    if exclude_guid:
        query = query.filter(ShopReport.guid != exclude_guid)
    ranked = []
    for report in query.order_by(ShopReport.created_at.desc()).yield_per(100):
        score = _similar_report_score(
            report, name, address, place_id, latitude, longitude
        )
        if score >= 0.58:
            ranked.append((score, report))
    ranked.sort(key=lambda item: (item[0], item[1].created_at), reverse=True)

    locale = get_locale()
    return jsonify(
        {
            "searched": True,
            "reports": [
                {
                    "name": report.name,
                    "address": "" if report.is_online else report.localized_address(locale),
                    "is_online": report.is_online,
                    "reported_at": report.created_at.strftime("%Y-%m-%d"),
                    "url": url_for("main.report_detail", report_guid=report.guid),
                }
                for _, report in ranked[:5]
            ],
        }
    )


@main_bp.get("/api/reports/search")
@login_required
def search_reports():
    """Name/address lookup that powers the related-shop picker."""

    term = request.args.get("q", "").strip()[:180]
    exclude_guid = request.args.get("exclude", "").strip()[:36]
    if len(term) < 2:
        return jsonify({"reports": []})

    pattern = f"%{term}%"
    query = ShopReport.query.filter(ShopReport.archived_at.is_(None)).filter(
        or_(
            ShopReport.name.ilike(pattern),
            ShopReport.address.ilike(pattern),
            ShopReport.address_en_us.ilike(pattern),
            ShopReport.address_zh_tw.ilike(pattern),
        )
    )
    if exclude_guid:
        query = query.filter(ShopReport.guid != exclude_guid)

    locale = get_locale()
    return jsonify(
        {
            "reports": [
                {
                    "guid": report.guid,
                    "name": report.name,
                    "address": "" if report.is_online else report.localized_address(locale),
                    "is_online": report.is_online,
                    "url": url_for("main.report_detail", report_guid=report.guid),
                }
                for report in query.order_by(ShopReport.created_at.desc()).limit(
                    MAX_RELATED_SHOP_RESULTS
                )
            ]
        }
    )


@main_bp.route("/reports/new", methods=["GET", "POST"])
@login_required
def create_report():
    related_shops: list[dict[str, str]] = []
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        is_online = request.form.get("is_online") == "1"
        address = "" if is_online else request.form.get("address", "").strip()
        google_place_id = (
            None
            if is_online
            else request.form.get("google_place_id", "").strip()[:255] or None
        )
        address_en_us = request.form.get("address_en_us", "").strip() or None
        address_zh_tw = request.form.get("address_zh_tw", "").strip() or None
        if not google_place_id:
            address_en_us = None
            address_zh_tw = None
        controversy = request.form.get("controversy", "").strip()
        hashtags = _parse_hashtags(request.form.get("hashtags", ""))
        controversy_links = _parse_controversy_links(
            request.form.get("controversy_links", "")
        )
        related_shops = _parse_related_shops(request.form)
        latitude = None if is_online else _float_between(request.form.get("latitude", ""), -90, 90)
        longitude = None if is_online else _float_between(request.form.get("longitude", ""), -180, 180)
        uploads = [file for file in request.files.getlist("proof") if file.filename]
        submitted_media_names = request.form.getlist("proof_name")
        submitted_media_rotations = request.form.getlist("proof_rotation")
        submitted_media_tokens = request.form.getlist("proof_token")
        links = {
            key: request.form.get(key, "").strip()
            for key in SOCIAL_FIELDS
            if request.form.get(key, "").strip()
        }
        errors = []

        if not 2 <= len(name) <= 180:
            errors.append("Shop name must be between 2 and 180 characters.")
        if not is_online and not 5 <= len(address) <= 500:
            errors.append("Address must be between 5 and 500 characters.")
        if any(
            localized and not 5 <= len(localized) <= 500
            for localized in (address_en_us, address_zh_tw)
        ):
            errors.append("Address must be between 5 and 500 characters.")
        if not 20 <= len(controversy) <= 5000:
            errors.append("Report details must be between 20 and 5,000 characters.")
        errors.extend(_validate_hashtags(hashtags))
        errors.extend(_validate_controversy_links(controversy_links))
        errors.extend(_validate_related_shops(related_shops))
        if not uploads:
            errors.append("Add at least one image or video as supporting evidence.")
        invalid_links = [SOCIAL_FIELDS[key] for key, value in links.items() if not _valid_url(value)]
        if invalid_links:
            errors.append(f"Use full http(s) links for: {', '.join(invalid_links)}.")

        validated_uploads = []
        for index, upload in enumerate(uploads):
            media_info = _validate_media(upload)
            if not media_info:
                errors.append(
                    f"{upload.filename} is not a supported image or video format."
                )
            else:
                media_type, extension = media_info
                submitted_name = (
                    submitted_media_names[index]
                    if index < len(submitted_media_names)
                    else upload.filename
                )
                display_name = _media_display_name(
                    submitted_name, upload.filename, extension
                )
                rotation = parse_rotation(
                    submitted_media_rotations[index]
                    if index < len(submitted_media_rotations)
                    else 0
                )
                if rotation is None:
                    errors.append("Choose a valid media rotation.")
                upload_token = _media_upload_token(submitted_media_tokens, index)
                if upload_token is None:
                    errors.append("Media order is invalid. Please reorder the files.")
                if display_name is None:
                    errors.append(
                        "Media names must be valid filenames and keep their original extension."
                    )
                else:
                    validated_uploads.append(
                        (
                            upload,
                            media_type,
                            extension,
                            display_name,
                            rotation,
                            upload_token,
                        )
                    )

        upload_tokens = [item[5] for item in validated_uploads]
        media_order = _ordered_media_tokens(
            request.form.get("media_order", ""), upload_tokens
        )
        if media_order is None:
            errors.append("Media order is invalid. Please reorder the files.")

        if not errors:
            submitted_at = utcnow()
            report = ShopReport(
                name=name,
                address=address,
                address_en_us=None if is_online else address_en_us,
                address_zh_tw=None if is_online else address_zh_tw,
                is_online=is_online,
                latitude=latitude,
                longitude=longitude,
                google_place_id=google_place_id,
                controversy=controversy,
                author=current_user,
                created_at=submitted_at,
                updated_at=submitted_at,
            )
            report.social_links = links
            report.hashtags = hashtags
            report.controversy_links = controversy_links
            report.related_shops = related_shops
            db.session.add(report)
            saved_paths = []
            try:
                upload_path = Path(current_app.config["UPLOAD_FOLDER"])
                media_positions = {
                    token: position for position, token in enumerate(media_order)
                }
                for (
                    upload,
                    media_type,
                    extension,
                    display_name,
                    rotation,
                    upload_token,
                ) in validated_uploads:
                    stored_name = f"{uuid.uuid4().hex}.{extension}"
                    destination = upload_path / stored_name
                    upload.save(destination)
                    saved_paths.append(destination)
                    make_media_file_readable(destination)
                    rotate_media_file(destination, media_type, rotation)
                    report.media.append(
                        ProofMedia(
                            stored_name=stored_name,
                            original_name=display_name,
                            media_type=media_type,
                            mime_type=upload.mimetype,
                            position=media_positions[upload_token],
                        )
                    )
                db.session.commit()
            except Exception:
                db.session.rollback()
                for path in saved_paths:
                    path.unlink(missing_ok=True)
                current_app.logger.exception("Could not save report")
                flash("The report could not be saved. Please try again.", "error")
            else:
                flash("Report published. Thank you for documenting it carefully.", "success")
                return redirect(url_for("main.report_detail", report_guid=report.guid))

        for error in errors:
            flash(error, "error")

    locale = get_locale()
    popular_hashtags, suggested_hashtags = _hashtag_suggestions(locale)
    return render_template(
        "reports/new.html",
        report=None,
        edit_mode=False,
        related_shops=_related_shop_details(related_shops, locale),
        social_fields=SOCIAL_FIELDS,
        popular_hashtags=popular_hashtags,
        suggested_hashtags=suggested_hashtags,
        google_maps_api_key=current_app.config["GOOGLE_MAPS_API_KEY"],
    )


@main_bp.get("/reports/<uuid:report_guid>")
def report_detail(report_guid):
    report = _report_by_guid_or_404(report_guid)
    return render_template(
        "reports/detail.html",
        report=report,
        related_shops=_related_shop_details(report.related_shops, get_locale()),
        contact_reasons=CONTACT_REASONS,
    )


@main_bp.get("/reports/<uuid:report_guid>/link-previews/<int:link_index>.png")
def controversy_link_preview(report_guid, link_index: int):
    report = _report_by_guid_or_404(report_guid)
    links = report.controversy_links
    if link_index < 0 or link_index >= len(links):
        abort(404)

    target_url = links[link_index]
    cache_name = f"{hashlib.sha256(target_url.encode('utf-8')).hexdigest()}.png"
    preview_folder = Path(current_app.config["LINK_PREVIEW_FOLDER"])
    preview_path = preview_folder / cache_name
    scan_cache_path = preview_folder / f"{cache_name.removesuffix('.png')}.scan.json"
    cache_seconds = int(current_app.config["LINK_PREVIEW_CACHE_HOURS"]) * 3600
    scanner_cache_seconds = (
        int(current_app.config["CLOUDFLARE_URL_SCANNER_CACHE_HOURS"]) * 3600
    )
    scanner_enabled = bool(
        current_app.config["CLOUDFLARE_URL_SCANNER_ACCOUNT_ID"]
        and current_app.config["CLOUDFLARE_URL_SCANNER_API_TOKEN"]
    )

    if scanner_enabled and not is_public_http_url(target_url):
        current_app.logger.warning(
            "Blocked a non-public controversy link for report %s.", report.guid
        )
        abort(403)

    def cache_is_fresh() -> bool:
        return (
            preview_path.is_file()
            and time.time() - preview_path.stat().st_mtime < cache_seconds
        )

    def load_scan_cache() -> dict | None:
        if (
            not scan_cache_path.is_file()
            or time.time() - scan_cache_path.stat().st_mtime >= scanner_cache_seconds
        ):
            return None
        try:
            cached = json.loads(scan_cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(cached, dict) or not isinstance(cached.get("malicious"), bool):
            return None
        return cached

    def save_scan_cache(verdict) -> dict:
        cached = {
            "scan_id": verdict.scan_id,
            "malicious": verdict.malicious,
            "categories": list(verdict.categories),
            "tags": list(verdict.tags),
            "checked_at": int(time.time()),
        }
        preview_folder.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=preview_folder,
                prefix="scan-",
                suffix=".json",
                delete=False,
            ) as temporary_file:
                json.dump(cached, temporary_file, ensure_ascii=False)
                temporary_path = Path(temporary_file.name)
            os.replace(temporary_path, scan_cache_path)
            temporary_path = None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        return cached

    scan_result = load_scan_cache() if scanner_enabled else None
    if scan_result and scan_result["malicious"]:
        current_app.logger.warning(
            "Cloudflare previously flagged a controversy link for report %s as malicious.",
            report.guid,
        )
        abort(403)
    if scan_result is None or not cache_is_fresh():
        with LINK_PREVIEW_LOCK:
            if scanner_enabled and scan_result is None:
                scan_result = load_scan_cache()
                if scan_result is None:
                    try:
                        verdict = scan_url(
                            target_url,
                            account_id=current_app.config[
                                "CLOUDFLARE_URL_SCANNER_ACCOUNT_ID"
                            ],
                            api_token=current_app.config[
                                "CLOUDFLARE_URL_SCANNER_API_TOKEN"
                            ],
                            request_timeout_seconds=int(
                                current_app.config[
                                    "CLOUDFLARE_URL_SCANNER_REQUEST_TIMEOUT_SECONDS"
                                ]
                            ),
                            result_timeout_seconds=int(
                                current_app.config[
                                    "CLOUDFLARE_URL_SCANNER_RESULT_TIMEOUT_SECONDS"
                                ]
                            ),
                            poll_interval_seconds=int(
                                current_app.config[
                                    "CLOUDFLARE_URL_SCANNER_POLL_INTERVAL_SECONDS"
                                ]
                            ),
                        )
                        scan_result = save_scan_cache(verdict)
                    except CloudflareURLScannerError:
                        current_app.logger.warning(
                            "Cloudflare could not check controversy link for report %s.",
                            report.guid,
                        )
                        abort(503)

            if scan_result and scan_result["malicious"]:
                current_app.logger.warning(
                    "Cloudflare flagged a controversy link for report %s as malicious.",
                    report.guid,
                )
                abort(403)

            if not cache_is_fresh():
                try:
                    generate_link_preview(
                        target_url,
                        preview_path,
                        timeout_ms=(
                            int(current_app.config["LINK_PREVIEW_TIMEOUT_SECONDS"])
                            * 1000
                        ),
                        settle_ms=int(current_app.config["LINK_PREVIEW_SETTLE_MS"]),
                    )
                except LinkPreviewError:
                    current_app.logger.warning(
                        "Could not generate controversy-link screenshot for report %s.",
                        report.guid,
                    )
                    if not preview_path.is_file():
                        abort(503)

    response = send_from_directory(
        preview_folder,
        cache_name,
        mimetype="image/png",
        conditional=True,
        max_age=cache_seconds,
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-ShopAlert-Link-Check"] = (
        "cloudflare-no-known-threat" if scanner_enabled else "not-configured"
    )
    return response


@main_bp.post("/reports/<uuid:report_guid>/contact")
@login_required
def contact_report_admin(report_guid):
    report = _report_by_guid_or_404(report_guid)
    reason = request.form.get("reason", "")
    details = request.form.get("details", "").strip()
    reply_email = request.form.get("reply_email", "").strip().lower()
    errors = []

    if reason not in CONTACT_REASONS:
        errors.append("Choose a valid reason for contacting the administrator.")
    if not 20 <= len(details) <= 2000:
        errors.append("Your message must be between 20 and 2,000 characters.")
    if "@" not in reply_email or len(reply_email) > 255:
        errors.append("Enter a valid reply email address.")

    if errors:
        for error in errors:
            flash(error, "error")
        return redirect(
            url_for("main.report_detail", report_guid=report.guid)
            + "#report-contact"
        )

    contact = ReportContact(
        report=report,
        sender=current_user,
        reason=reason,
        details=details,
        reply_email=reply_email,
    )
    db.session.add(contact)
    db.session.commit()
    flash("Your message has been sent to the site administrator.", "success")
    return redirect(url_for("main.report_detail", report_guid=report.guid))


@main_bp.route("/reports/<uuid:report_guid>/edit", methods=["GET", "POST"])
@login_required
def edit_report(report_guid):
    report = _report_by_guid_or_404(report_guid)
    if report.author_id != current_user.id:
        abort(403)
    if report.archived_at is not None:
        abort(403)

    related_shops = report.related_shops
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        is_online = request.form.get("is_online") == "1"
        address = "" if is_online else request.form.get("address", "").strip()
        google_place_id = (
            None
            if is_online
            else request.form.get("google_place_id", "").strip()[:255] or None
        )
        address_en_us = request.form.get("address_en_us", "").strip() or None
        address_zh_tw = request.form.get("address_zh_tw", "").strip() or None
        if not google_place_id:
            address_en_us = None
            address_zh_tw = None
        controversy = request.form.get("controversy", "").strip()
        hashtags = _parse_hashtags(request.form.get("hashtags", ""))
        controversy_links = _parse_controversy_links(
            request.form.get("controversy_links", "")
        )
        related_shops = _parse_related_shops(request.form)
        latitude = (
            None
            if is_online
            else _float_between(request.form.get("latitude", ""), -90, 90)
        )
        longitude = (
            None
            if is_online
            else _float_between(request.form.get("longitude", ""), -180, 180)
        )
        uploads = [file for file in request.files.getlist("proof") if file.filename]
        submitted_media_names = request.form.getlist("proof_name")
        submitted_media_rotations = request.form.getlist("proof_rotation")
        submitted_media_tokens = request.form.getlist("proof_token")
        links = {
            key: request.form.get(key, "").strip()
            for key in SOCIAL_FIELDS
            if request.form.get(key, "").strip()
        }
        requested_removals = {
            value for value in request.form.getlist("remove_media") if value.isdigit()
        }
        media_to_remove = [
            media for media in report.media if str(media.id) in requested_removals
        ]
        media_to_keep = [media for media in report.media if media not in media_to_remove]
        renamed_media = {}
        existing_media_rotations = {}
        errors = []

        if not 2 <= len(name) <= 180:
            errors.append("Shop name must be between 2 and 180 characters.")
        if not is_online and not 5 <= len(address) <= 500:
            errors.append("Address must be between 5 and 500 characters.")
        if any(
            localized and not 5 <= len(localized) <= 500
            for localized in (address_en_us, address_zh_tw)
        ):
            errors.append("Address must be between 5 and 500 characters.")
        if not 20 <= len(controversy) <= 5000:
            errors.append("Report details must be between 20 and 5,000 characters.")
        errors.extend(_validate_hashtags(hashtags))
        errors.extend(_validate_controversy_links(controversy_links))
        errors.extend(_validate_related_shops(related_shops, report))
        invalid_links = [
            SOCIAL_FIELDS[key] for key, value in links.items() if not _valid_url(value)
        ]
        if invalid_links:
            errors.append(f"Use full http(s) links for: {', '.join(invalid_links)}.")

        for media in media_to_keep:
            extension = (
                media.original_name.rsplit(".", 1)[-1].lower()
                if "." in media.original_name
                else media.stored_name.rsplit(".", 1)[-1].lower()
            )
            display_name = _media_display_name(
                request.form.get(f"media_name_{media.id}", ""),
                media.original_name,
                extension,
            )
            if display_name is None:
                errors.append(
                    "Media names must be valid filenames and keep their original extension."
                )
            else:
                renamed_media[media.id] = display_name
            rotation = parse_rotation(
                request.form.get(f"media_rotation_{media.id}", "0")
            )
            if rotation is None:
                errors.append("Choose a valid media rotation.")
            else:
                existing_media_rotations[media.id] = rotation

        validated_uploads = []
        for index, upload in enumerate(uploads):
            media_info = _validate_media(upload)
            if not media_info:
                errors.append(
                    f"{upload.filename} is not a supported image or video format."
                )
            else:
                media_type, extension = media_info
                submitted_name = (
                    submitted_media_names[index]
                    if index < len(submitted_media_names)
                    else upload.filename
                )
                display_name = _media_display_name(
                    submitted_name, upload.filename, extension
                )
                rotation = parse_rotation(
                    submitted_media_rotations[index]
                    if index < len(submitted_media_rotations)
                    else 0
                )
                if rotation is None:
                    errors.append("Choose a valid media rotation.")
                upload_token = _media_upload_token(submitted_media_tokens, index)
                if upload_token is None:
                    errors.append("Media order is invalid. Please reorder the files.")
                if display_name is None:
                    errors.append(
                        "Media names must be valid filenames and keep their original extension."
                    )
                else:
                    validated_uploads.append(
                        (
                            upload,
                            media_type,
                            extension,
                            display_name,
                            rotation,
                            upload_token,
                        )
                    )

        expected_media_tokens = [
            *(f"existing:{media.id}" for media in report.media),
            *(item[5] for item in validated_uploads),
        ]
        media_order = _ordered_media_tokens(
            request.form.get("media_order", ""), expected_media_tokens
        )
        if media_order is None:
            errors.append("Media order is invalid. Please reorder the files.")

        remaining_media = len(report.media) - len(media_to_remove) + len(validated_uploads)
        if remaining_media < 1:
            errors.append("Keep or add at least one image or video as supporting evidence.")

        if not errors:
            report.name = name
            report.is_online = is_online
            report.address = address
            report.address_en_us = None if is_online else address_en_us
            report.address_zh_tw = None if is_online else address_zh_tw
            report.latitude = latitude
            report.longitude = longitude
            report.google_place_id = google_place_id
            report.controversy = controversy
            report.hashtags = hashtags
            report.controversy_links = controversy_links
            report.related_shops = related_shops
            report.social_links = links
            report.updated_at = utcnow()
            removed_tokens = {
                f"existing:{media.id}" for media in media_to_remove
            }
            effective_media_order = [
                token for token in media_order if token not in removed_tokens
            ]
            media_positions = {
                token: position for position, token in enumerate(effective_media_order)
            }
            for media in media_to_keep:
                media.original_name = renamed_media[media.id]
                media.position = media_positions[f"existing:{media.id}"]
            saved_paths = []
            rotation_backups = []
            rotated_media = []
            removed_paths = [
                Path(current_app.config["UPLOAD_FOLDER"]) / media.stored_name
                for media in media_to_remove
            ]
            try:
                upload_path = Path(current_app.config["UPLOAD_FOLDER"])
                for media in media_to_remove:
                    db.session.delete(media)
                for media in media_to_keep:
                    rotation = existing_media_rotations[media.id]
                    if rotation == 0:
                        continue
                    source = upload_path / media.stored_name
                    backup_handle, backup_name = tempfile.mkstemp(
                        dir=upload_path,
                        prefix=f".{source.stem}-rotation-backup-",
                        suffix=source.suffix,
                    )
                    os.close(backup_handle)
                    backup = Path(backup_name)
                    try:
                        shutil.copy2(source, backup)
                    except Exception:
                        backup.unlink(missing_ok=True)
                        raise
                    rotation_backups.append((source, backup))
                    rotate_media_file(source, media.media_type, rotation)
                    rotated_media.append(media)
                for (
                    upload,
                    media_type,
                    extension,
                    display_name,
                    rotation,
                    upload_token,
                ) in validated_uploads:
                    stored_name = f"{uuid.uuid4().hex}.{extension}"
                    destination = upload_path / stored_name
                    upload.save(destination)
                    saved_paths.append(destination)
                    make_media_file_readable(destination)
                    rotate_media_file(destination, media_type, rotation)
                    report.media.append(
                        ProofMedia(
                            stored_name=stored_name,
                            original_name=display_name,
                            media_type=media_type,
                            mime_type=upload.mimetype,
                            position=media_positions[upload_token],
                        )
                    )
                db.session.commit()
            except Exception:
                db.session.rollback()
                for path in saved_paths:
                    path.unlink(missing_ok=True)
                for source, backup in rotation_backups:
                    try:
                        os.replace(backup, source)
                        make_media_file_readable(source)
                    except OSError:
                        current_app.logger.exception(
                            "Could not restore media after a failed rotation"
                        )
                current_app.logger.exception("Could not update report")
                flash("The report could not be updated. Please try again.", "error")
            else:
                for _source, backup in rotation_backups:
                    backup.unlink(missing_ok=True)
                for media in rotated_media:
                    discard_thumbnail(media.stored_name)
                for path in removed_paths:
                    path.unlink(missing_ok=True)
                    discard_thumbnail(path.name)
                flash("Report updated.", "success")
                return redirect(
                    url_for("main.report_detail", report_guid=report.guid)
                )

        for error in errors:
            flash(error, "error")

    locale = get_locale()
    popular_hashtags, suggested_hashtags = _hashtag_suggestions(locale)
    return render_template(
        "reports/new.html",
        report=report,
        edit_mode=True,
        related_shops=_related_shop_details(related_shops, locale),
        social_fields=SOCIAL_FIELDS,
        popular_hashtags=popular_hashtags,
        suggested_hashtags=suggested_hashtags,
        google_maps_api_key=current_app.config["GOOGLE_MAPS_API_KEY"],
    )


@main_bp.get("/reports/<int:report_id>")
def legacy_report_detail(report_id: int):
    report = db.get_or_404(ShopReport, report_id)
    if report.archived_at is not None and not _can_view_archived_report(report):
        abort(404)
    return redirect(
        url_for("main.report_detail", report_guid=report.guid),
        code=301,
    )


@main_bp.get("/admin/report-contacts")
@login_required
def admin_report_contacts():
    if not _is_current_user_admin():
        abort(403)
    contacts = ReportContact.query.order_by(
        ReportContact.is_resolved.asc(), ReportContact.created_at.desc()
    ).all()
    return render_template(
        "admin/report_contacts.html",
        contacts=contacts,
        contact_reasons=CONTACT_REASONS,
    )


@main_bp.get("/admin")
@login_required
def admin_dashboard():
    if not _is_current_user_admin():
        abort(403)
    reports = ShopReport.query.order_by(ShopReport.created_at.desc()).all()
    users = User.query.order_by(User.created_at.desc()).all()
    open_contact_count = ReportContact.query.filter_by(is_resolved=False).count()
    return render_template(
        "admin/dashboard.html",
        reports=reports,
        users=users,
        open_contact_count=open_contact_count,
        admin_email=current_app.config.get("ADMIN_EMAIL", ""),
    )


@main_bp.post("/admin/reports/<uuid:report_guid>/archive")
@login_required
def admin_archive_report(report_guid):
    if not _is_current_user_admin():
        abort(403)
    report = ShopReport.query.filter_by(guid=str(report_guid)).first_or_404()
    content_updated_at = report.updated_at
    if report.archived_at is None:
        archived_at = utcnow()
        message = "Report archived."
    else:
        archived_at = None
        message = "Report restored."
    db.session.execute(
        update(ShopReport)
        .where(ShopReport.id == report.id)
        .values(archived_at=archived_at, updated_at=content_updated_at)
    )
    db.session.commit()
    flash(message, "success")
    return redirect(url_for("main.admin_dashboard") + "#reports")


@main_bp.post("/admin/reports/<uuid:report_guid>/delete")
@login_required
def admin_delete_report(report_guid):
    if not _is_current_user_admin():
        abort(403)
    report = ShopReport.query.filter_by(guid=str(report_guid)).first_or_404()
    upload_folder = Path(current_app.config["UPLOAD_FOLDER"])
    preview_folder = Path(current_app.config["LINK_PREVIEW_FOLDER"])
    media_paths = [upload_folder / media.stored_name for media in report.media]
    thumbnail_names = [media.stored_name for media in report.media]
    preview_paths = []
    for link in report.controversy_links:
        cache_key = hashlib.sha256(link.encode("utf-8")).hexdigest()
        preview_paths.extend(
            [preview_folder / f"{cache_key}.png", preview_folder / f"{cache_key}.scan.json"]
        )
    db.session.delete(report)
    db.session.commit()
    for path in media_paths + preview_paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            current_app.logger.warning("Could not remove deleted report file %s", path)
    for stored_name in thumbnail_names:
        discard_thumbnail(stored_name)
    flash("Report permanently deleted.", "success")
    return redirect(url_for("main.admin_dashboard") + "#reports")


@main_bp.post("/admin/users/<int:user_id>/ban")
@login_required
def admin_ban_user(user_id: int):
    if not _is_current_user_admin():
        abort(403)
    user = db.get_or_404(User, user_id)
    if user.email.lower() == current_app.config.get("ADMIN_EMAIL", ""):
        flash("The configured administrator account cannot be banned.", "error")
        return redirect(url_for("main.admin_dashboard") + "#users")
    user.is_banned = not user.is_banned
    user.banned_at = utcnow() if user.is_banned else None
    db.session.commit()
    flash("User banned." if user.is_banned else "User ban removed.", "success")
    return redirect(url_for("main.admin_dashboard") + "#users")


@main_bp.post("/admin/users/<int:user_id>/password")
@login_required
def admin_reset_user_password(user_id: int):
    if not _is_current_user_admin():
        abort(403)
    user = db.get_or_404(User, user_id)
    new_password = request.form.get("new_password", "")
    confirmation = request.form.get("confirm_password", "")
    if len(new_password) < 8:
        flash("Password must contain at least 8 characters.", "error")
    elif new_password != confirmation:
        flash("New password confirmation does not match.", "error")
    else:
        user.set_password(new_password)
        db.session.commit()
        flash("User password reset.", "success")
    return redirect(url_for("main.admin_dashboard") + "#users")


@main_bp.post("/admin/report-contacts/<uuid:contact_guid>/resolve")
@login_required
def resolve_report_contact(contact_guid):
    if not _is_current_user_admin():
        abort(403)
    contact = ReportContact.query.filter_by(guid=str(contact_guid)).first_or_404()
    contact.is_resolved = not contact.is_resolved
    db.session.commit()
    flash("Contact status updated.", "success")
    return redirect(url_for("main.admin_report_contacts"))


@main_bp.get("/media/<int:media_id>")
def proof_media(media_id: int):
    media = db.get_or_404(ProofMedia, media_id)
    if media.report.archived_at is not None and not _can_view_archived_report(media.report):
        abort(404)
    return send_from_directory(
        current_app.config["UPLOAD_FOLDER"],
        media.stored_name,
        mimetype=media.mime_type,
        conditional=True,
    )


@main_bp.get("/media/<int:media_id>/thumbnail")
def proof_thumbnail(media_id: int):
    """Serve a small cached copy of an image for listings and gallery rails."""

    media = db.get_or_404(ProofMedia, media_id)
    if media.report.archived_at is not None and not _can_view_archived_report(media.report):
        abort(404)
    if media.media_type == "image":
        try:
            thumbnail = ensure_thumbnail(media.stored_name)
        except ThumbnailError:
            current_app.logger.warning(
                "Serving the original upload for media %s: no thumbnail", media_id
            )
        else:
            response = send_from_directory(
                thumbnail.parent,
                thumbnail.name,
                mimetype=THUMBNAIL_MIME_TYPE,
                conditional=True,
                # Uploads never change under a stored name, so the thumbnail
                # generated from one can be cached for as long as the browser
                # is willing to keep it.
                max_age=31_536_000,
            )
            response.headers["Cache-Control"] += ", immutable"
            return response
    return proof_media(media_id)
