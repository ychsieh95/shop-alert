import hashlib
import json
import math
import time
import uuid
from urllib.error import URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

from flask import (
    Blueprint,
    current_app,
    flash,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_user, logout_user

from .extensions import db
from .models import LoginThrottle, User, is_valid_username, normalize_username


auth_bp = Blueprint("auth", __name__)
TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def _is_safe_redirect(target: str) -> bool:
    host = urlparse(request.host_url)
    destination = urlparse(urljoin(request.host_url, target))
    return destination.scheme in {"http", "https"} and host.netloc == destination.netloc


def _client_ip() -> str:
    # Do not trust X-Forwarded-For unless the deployment explicitly configures ProxyFix.
    return request.remote_addr or "unknown"


def _throttle_key(identity: str) -> str:
    value = f"{identity.strip().casefold()}\0{_client_ip()}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _locked_response(throttle: LoginThrottle, now: int):
    wait_seconds = max(1, (throttle.locked_until or now + 1) - now)
    wait_minutes = max(1, math.ceil(wait_seconds / 60))
    flash(
        f"Too many failed login attempts. Try again in {wait_minutes} minutes.",
        "error",
    )
    response = make_response(render_template("auth/login.html"), 429)
    response.headers["Retry-After"] = str(wait_seconds)
    return response


def _active_throttle(identity: str, now: int) -> LoginThrottle | None:
    throttle = LoginThrottle.query.filter_by(key_hash=_throttle_key(identity)).first()
    if throttle and throttle.locked_until and throttle.locked_until > now:
        return throttle
    return None


def _record_login_failure(identity: str, now: int) -> tuple[LoginThrottle, int]:
    key_hash = _throttle_key(identity)
    throttle = LoginThrottle.query.filter_by(key_hash=key_hash).first()
    window_seconds = int(current_app.config["LOGIN_ATTEMPT_WINDOW_MINUTES"]) * 60
    max_attempts = int(current_app.config["LOGIN_MAX_ATTEMPTS"])

    if throttle is None:
        throttle = LoginThrottle(
            key_hash=key_hash,
            failed_count=0,
            window_started_at=now,
            updated_at=now,
        )
        db.session.add(throttle)
    elif (
        now - throttle.window_started_at >= window_seconds
        or (throttle.locked_until is not None and throttle.locked_until <= now)
    ):
        throttle.failed_count = 0
        throttle.window_started_at = now
        throttle.locked_until = None

    throttle.failed_count += 1
    throttle.updated_at = now
    if throttle.failed_count >= max_attempts:
        throttle.locked_until = now + int(current_app.config["LOGIN_LOCKOUT_MINUTES"]) * 60
    db.session.commit()
    return throttle, max(0, max_attempts - throttle.failed_count)


def _clear_login_failures(identity: str) -> None:
    throttle = LoginThrottle.query.filter_by(key_hash=_throttle_key(identity)).first()
    if throttle:
        db.session.delete(throttle)
        db.session.commit()


def _verify_turnstile(expected_action: str) -> bool:
    secret_key = current_app.config.get("TURNSTILE_SECRET_KEY", "")
    if not secret_key:
        return True

    token = request.form.get("cf-turnstile-response", "")
    if not token or len(token) > 2048:
        return False

    payload = urlencode(
        {
            "secret": secret_key,
            "response": token,
            "remoteip": _client_ip(),
            "idempotency_key": str(uuid.uuid4()),
        }
    ).encode("utf-8")
    verification_request = Request(
        TURNSTILE_VERIFY_URL,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(verification_request, timeout=5) as response:
            result = json.load(response)
    except (OSError, TimeoutError, URLError, ValueError):
        current_app.logger.warning("Cloudflare Turnstile verification was unavailable.")
        return False

    if not isinstance(result, dict):
        return False
    if not result.get("success") or result.get("action") != expected_action:
        return False
    expected_hostname = current_app.config.get("TURNSTILE_EXPECTED_HOSTNAME", "")
    return not expected_hostname or result.get("hostname", "").lower() == expected_hostname


def _captcha_failed():
    flash("Complete the security check and try again.", "error")


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    if request.method == "POST":
        display_name = request.form.get("display_name", "").strip()
        username = normalize_username(request.form.get("username", ""))
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        errors = []

        if not _verify_turnstile("signup"):
            _captcha_failed()
            return render_template("auth/signup.html"), 400

        if len(display_name) < 2 or len(display_name) > 80:
            errors.append("Display name must be between 2 and 80 characters.")
        if not is_valid_username(username):
            errors.append("Use 3 to 30 letters, numbers, or underscores for the username.")
        if "@" not in email or len(email) > 255:
            errors.append("Enter a valid email address.")
        if len(password) < 8:
            errors.append("Password must contain at least 8 characters.")
        if User.query.filter_by(email=email).first():
            errors.append("An account with that email already exists.")
        if User.query.filter_by(username=username).first():
            errors.append("That username is already in use.")

        if not errors:
            user = User(display_name=display_name, username=username, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash("Welcome! Your account is ready.", "success")
            return redirect(url_for("main.home"))

        for error in errors:
            flash(error, "error")

    return render_template("auth/signup.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    if request.method == "POST":
        identifier = request.form.get(
            "identifier", request.form.get("email", "")
        ).strip().casefold()
        password = request.form.get("password", "")
        now = int(time.time())
        user = (
            User.query.filter_by(email=identifier).first()
            if "@" in identifier
            else User.query.filter_by(username=identifier).first()
        )
        throttle_identity = user.email if user else identifier
        throttle = _active_throttle(throttle_identity, now)
        if throttle:
            return _locked_response(throttle, now)

        if not _verify_turnstile("login"):
            _captcha_failed()
            return render_template("auth/login.html"), 400

        password_matches = bool(user and user.check_password(password))
        if password_matches and user.is_banned:
            flash("This account has been banned. Contact the administrator for help.", "error")
            return render_template("auth/login.html"), 403

        if password_matches:
            _clear_login_failures(throttle_identity)
            login_user(user, remember=bool(request.form.get("remember")))
            flash("Welcome back.", "success")
            next_url = request.args.get("next", "")
            if next_url and _is_safe_redirect(next_url):
                return redirect(next_url)
            return redirect(url_for("main.home"))

        throttle, attempts_remaining = _record_login_failure(throttle_identity, now)
        if throttle.locked_until and throttle.locked_until > now:
            return _locked_response(throttle, now)
        flash(
            f"Email, username, or password is incorrect. {attempts_remaining} attempts remaining.",
            "error",
        )

    return render_template("auth/login.html")


@auth_bp.post("/logout")
def logout():
    if current_user.is_authenticated:
        logout_user()
        flash("You have been logged out.", "info")
    return redirect(url_for("main.home"))
