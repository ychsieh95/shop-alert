import os
import re
import uuid
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, render_template
from flask_login import current_user
from sqlalchemy import inspect, text

from .extensions import csrf, db, login_manager
from .i18n import (
    datetime_iso_utc,
    format_local_datetime,
    get_locale,
    get_timezone_name,
    translate,
)
from .media_files import repair_media_folder_permissions
from .models import User, is_valid_username, normalize_username


BR_TAG_PATTERN = re.compile(r"<br\s*/?>", re.IGNORECASE)


def normalize_line_breaks(value: object) -> str:
    """Treat user-entered HTML break markers as text newlines, not trusted HTML."""

    return BR_TAG_PATTERN.sub("\n", str(value or ""))


def create_app(test_config: dict | None = None) -> Flask:
    load_dotenv()
    app = Flask(
        __name__,
        instance_relative_config=True,
        static_url_path="/assets",
    )

    upload_dir = Path(app.instance_path) / "uploads"
    link_preview_dir = Path(app.instance_path) / "link_previews"
    thumbnail_dir = Path(app.instance_path) / "thumbnails"
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY", "dev-only-change-me"),
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL", "sqlite:///shop_alert.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MAX_CONTENT_LENGTH=int(os.getenv("MAX_CONTENT_LENGTH_MB", "50")) * 1024 * 1024,
        UPLOAD_FOLDER=str(upload_dir),
        LINK_PREVIEW_FOLDER=str(link_preview_dir),
        THUMBNAIL_FOLDER=str(thumbnail_dir),
        LINK_PREVIEW_TIMEOUT_SECONDS=int(
            os.getenv("LINK_PREVIEW_TIMEOUT_SECONDS", "15")
        ),
        LINK_PREVIEW_SETTLE_MS=int(os.getenv("LINK_PREVIEW_SETTLE_MS", "1500")),
        LINK_PREVIEW_CACHE_HOURS=int(os.getenv("LINK_PREVIEW_CACHE_HOURS", "24")),
        CLOUDFLARE_URL_SCANNER_ACCOUNT_ID=os.getenv(
            "CLOUDFLARE_URL_SCANNER_ACCOUNT_ID", ""
        ).strip(),
        CLOUDFLARE_URL_SCANNER_API_TOKEN=os.getenv(
            "CLOUDFLARE_URL_SCANNER_API_TOKEN", ""
        ).strip(),
        CLOUDFLARE_URL_SCANNER_REQUEST_TIMEOUT_SECONDS=int(
            os.getenv("CLOUDFLARE_URL_SCANNER_REQUEST_TIMEOUT_SECONDS", "10")
        ),
        CLOUDFLARE_URL_SCANNER_RESULT_TIMEOUT_SECONDS=int(
            os.getenv("CLOUDFLARE_URL_SCANNER_RESULT_TIMEOUT_SECONDS", "40")
        ),
        CLOUDFLARE_URL_SCANNER_POLL_INTERVAL_SECONDS=int(
            os.getenv("CLOUDFLARE_URL_SCANNER_POLL_INTERVAL_SECONDS", "10")
        ),
        CLOUDFLARE_URL_SCANNER_CACHE_HOURS=int(
            os.getenv("CLOUDFLARE_URL_SCANNER_CACHE_HOURS", "24")
        ),
        HOME_RECENT_REPORTS_COUNT=int(os.getenv("HOME_RECENT_REPORTS_COUNT", "9")),
        GOOGLE_MAPS_API_KEY=os.getenv("GOOGLE_MAPS_API_KEY", ""),
        ADMIN_EMAIL=os.getenv("ADMIN_EMAIL", "").strip().lower(),
        ADMIN_PASSWORD=os.getenv("ADMIN_PASSWORD", ""),
        ADMIN_USERNAME=normalize_username(os.getenv("ADMIN_USERNAME", "")),
        LOGIN_MAX_ATTEMPTS=int(os.getenv("LOGIN_MAX_ATTEMPTS", "5")),
        LOGIN_ATTEMPT_WINDOW_MINUTES=int(
            os.getenv("LOGIN_ATTEMPT_WINDOW_MINUTES", "15")
        ),
        LOGIN_LOCKOUT_MINUTES=int(os.getenv("LOGIN_LOCKOUT_MINUTES", "15")),
        TURNSTILE_SITE_KEY=os.getenv("TURNSTILE_SITE_KEY", "").strip(),
        TURNSTILE_SECRET_KEY=os.getenv("TURNSTILE_SECRET_KEY", "").strip(),
        TURNSTILE_EXPECTED_HOSTNAME=os.getenv(
            "TURNSTILE_EXPECTED_HOSTNAME", ""
        ).strip().lower(),
    )
    if test_config:
        app.config.update(test_config)

    app.jinja_env.filters["normalize_line_breaks"] = normalize_line_breaks
    app.jinja_env.filters["datetime_iso_utc"] = datetime_iso_utc
    app.jinja_env.filters["format_local_datetime"] = format_local_datetime

    throttle_settings = (
        "LOGIN_MAX_ATTEMPTS",
        "LOGIN_ATTEMPT_WINDOW_MINUTES",
        "LOGIN_LOCKOUT_MINUTES",
    )
    if any(int(app.config[name]) < 1 for name in throttle_settings):
        raise RuntimeError("Login throttle settings must be positive integers.")
    if (
        int(app.config["LINK_PREVIEW_TIMEOUT_SECONDS"]) < 1
        or int(app.config["LINK_PREVIEW_SETTLE_MS"]) < 0
        or int(app.config["LINK_PREVIEW_CACHE_HOURS"]) < 1
    ):
        raise RuntimeError("Link preview timing and cache settings are invalid.")
    if int(app.config["HOME_RECENT_REPORTS_COUNT"]) < 1:
        raise RuntimeError("HOME_RECENT_REPORTS_COUNT must be a positive integer.")
    if bool(app.config["TURNSTILE_SITE_KEY"]) != bool(
        app.config["TURNSTILE_SECRET_KEY"]
    ):
        raise RuntimeError(
            "TURNSTILE_SITE_KEY and TURNSTILE_SECRET_KEY must be configured together."
        )
    if bool(app.config["CLOUDFLARE_URL_SCANNER_ACCOUNT_ID"]) != bool(
        app.config["CLOUDFLARE_URL_SCANNER_API_TOKEN"]
    ):
        raise RuntimeError(
            "CLOUDFLARE_URL_SCANNER_ACCOUNT_ID and "
            "CLOUDFLARE_URL_SCANNER_API_TOKEN must be configured together."
        )
    scanner_timing_settings = (
        "CLOUDFLARE_URL_SCANNER_REQUEST_TIMEOUT_SECONDS",
        "CLOUDFLARE_URL_SCANNER_RESULT_TIMEOUT_SECONDS",
        "CLOUDFLARE_URL_SCANNER_POLL_INTERVAL_SECONDS",
        "CLOUDFLARE_URL_SCANNER_CACHE_HOURS",
    )
    if any(int(app.config[name]) < 1 for name in scanner_timing_settings):
        raise RuntimeError("Cloudflare URL Scanner settings must be positive integers.")
    if app.config["ADMIN_PASSWORD"]:
        if not app.config["ADMIN_EMAIL"]:
            raise RuntimeError("ADMIN_PASSWORD requires ADMIN_EMAIL to be configured.")
        if len(app.config["ADMIN_PASSWORD"]) < 8:
            raise RuntimeError("ADMIN_PASSWORD must contain at least 8 characters.")
    if app.config["ADMIN_USERNAME"]:
        if not app.config["ADMIN_EMAIL"]:
            raise RuntimeError("ADMIN_USERNAME requires ADMIN_EMAIL to be configured.")
        if not is_valid_username(app.config["ADMIN_USERNAME"]):
            raise RuntimeError(
                "ADMIN_USERNAME must contain 3 to 30 letters, numbers, or underscores."
            )

    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["LINK_PREVIEW_FOLDER"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["THUMBNAIL_FOLDER"]).mkdir(parents=True, exist_ok=True)
    for media_folder_name in ("UPLOAD_FOLDER", "THUMBNAIL_FOLDER"):
        for failed_path in repair_media_folder_permissions(
            Path(app.config[media_folder_name])
        ):
            app.logger.warning(
                "Could not repair media file permissions for %s", failed_path
            )
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to share a report."
    login_manager.login_message_category = "info"

    @app.context_processor
    def inject_preferences():
        admin_email = app.config.get("ADMIN_EMAIL", "")
        is_admin = bool(
            admin_email
            and current_user.is_authenticated
            and current_user.email.lower() == admin_email
        )
        return {
            "locale": get_locale(),
            "timezone_name": get_timezone_name(),
            "t": translate,
            "is_admin": is_admin,
            "turnstile_enabled": bool(app.config["TURNSTILE_SITE_KEY"]),
            "turnstile_site_key": app.config["TURNSTILE_SITE_KEY"],
        }

    @login_manager.user_loader
    def load_user(user_id: str) -> User | None:
        user = db.session.get(User, int(user_id))
        return None if user is not None and user.is_banned else user

    from .auth import auth_bp
    from .main import main_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("404.html"), 404

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("403.html"), 403

    @app.errorhandler(413)
    def too_large(_error):
        return render_template("413.html"), 413

    with app.app_context():
        db.create_all()
        user_columns = {
            column["name"] for column in inspect(db.engine).get_columns("user")
        }
        if "username" not in user_columns:
            db.session.execute(
                text("ALTER TABLE user ADD COLUMN username VARCHAR(30)")
            )
            db.session.commit()
            user_columns.add("username")

        username_rows = db.session.execute(
            text(
                "SELECT id, email, username FROM user ORDER BY id"
                if "email" in user_columns
                else "SELECT id, '' AS email, username FROM user ORDER BY id"
            )
        ).mappings().all()
        used_usernames = {
            normalize_username(username)
            for (username,) in db.session.execute(
                text("SELECT username FROM user WHERE username IS NOT NULL")
            )
            if username
        }
        for row in username_rows:
            if row["username"]:
                continue
            email_prefix = row["email"].partition("@")[0]
            base = "".join(
                character if character.isalnum() or character == "_" else "_"
                for character in normalize_username(email_prefix)
            ).strip("_")[:30]
            if not is_valid_username(base):
                base = f"user_{row['id']}"
            candidate = base
            suffix_number = 1
            while candidate in used_usernames:
                suffix = f"_{suffix_number}"
                candidate = f"{base[: 30 - len(suffix)]}{suffix}"
                suffix_number += 1
            db.session.execute(
                text("UPDATE user SET username = :username WHERE id = :user_id"),
                {"username": candidate, "user_id": row["id"]},
            )
            used_usernames.add(candidate)
        db.session.commit()

        user_indexes = inspect(db.engine).get_indexes("user")
        if not any(index.get("column_names") == ["username"] for index in user_indexes):
            db.session.execute(
                text("CREATE UNIQUE INDEX ix_user_username ON user (username)")
            )
            db.session.commit()

        if "profile_image_name" not in user_columns:
            db.session.execute(
                text("ALTER TABLE user ADD COLUMN profile_image_name VARCHAR(255)")
            )
            db.session.commit()
        if "profile_image_mime" not in user_columns:
            db.session.execute(
                text("ALTER TABLE user ADD COLUMN profile_image_mime VARCHAR(120)")
            )
            db.session.commit()
        if "is_banned" not in user_columns:
            db.session.execute(
                text(
                    "ALTER TABLE user ADD COLUMN "
                    "is_banned BOOLEAN NOT NULL DEFAULT FALSE"
                )
            )
            db.session.commit()
        if "banned_at" not in user_columns:
            db.session.execute(text("ALTER TABLE user ADD COLUMN banned_at DATETIME"))
            db.session.commit()

        report_columns = {
            column["name"] for column in inspect(db.engine).get_columns("shop_report")
        }
        if "is_online" not in report_columns:
            db.session.execute(
                text(
                    "ALTER TABLE shop_report "
                    "ADD COLUMN is_online BOOLEAN NOT NULL DEFAULT FALSE"
                )
            )
            db.session.commit()
        if "guid" not in report_columns:
            db.session.execute(
                text("ALTER TABLE shop_report ADD COLUMN guid VARCHAR(36)")
            )
            db.session.commit()
        if "updated_at" not in report_columns:
            db.session.execute(
                text("ALTER TABLE shop_report ADD COLUMN updated_at DATETIME")
            )
            if "created_at" in report_columns:
                db.session.execute(
                    text(
                        "UPDATE shop_report SET updated_at = created_at "
                        "WHERE updated_at IS NULL"
                    )
                )
            else:
                db.session.execute(
                    text(
                        "UPDATE shop_report SET updated_at = CURRENT_TIMESTAMP "
                        "WHERE updated_at IS NULL"
                    )
                )
            db.session.commit()

        if "archived_at" not in report_columns:
            db.session.execute(
                text("ALTER TABLE shop_report ADD COLUMN archived_at DATETIME")
            )
            db.session.commit()

        if "controversy_links_json" not in report_columns:
            db.session.execute(
                text(
                    "ALTER TABLE shop_report ADD COLUMN "
                    "controversy_links_json TEXT NOT NULL DEFAULT '[]'"
                )
            )
            db.session.commit()
        if "related_shops_json" not in report_columns:
            db.session.execute(
                text(
                    "ALTER TABLE shop_report ADD COLUMN "
                    "related_shops_json TEXT NOT NULL DEFAULT '[]'"
                )
            )
            db.session.commit()
        if "hashtags_json" not in report_columns:
            db.session.execute(
                text(
                    "ALTER TABLE shop_report ADD COLUMN "
                    "hashtags_json TEXT NOT NULL DEFAULT '[]'"
                )
            )
            db.session.commit()
        if "address_en_us" not in report_columns:
            db.session.execute(
                text("ALTER TABLE shop_report ADD COLUMN address_en_us VARCHAR(500)")
            )
            db.session.commit()
        if "address_zh_tw" not in report_columns:
            db.session.execute(
                text("ALTER TABLE shop_report ADD COLUMN address_zh_tw VARCHAR(500)")
            )
            db.session.commit()

        media_columns = {
            column["name"] for column in inspect(db.engine).get_columns("proof_media")
        }
        if "position" not in media_columns:
            db.session.execute(
                text(
                    "ALTER TABLE proof_media ADD COLUMN "
                    "position INTEGER NOT NULL DEFAULT 0"
                )
            )
            media_rows = db.session.execute(
                text("SELECT id, report_id FROM proof_media ORDER BY report_id, id")
            ).mappings()
            current_report_id = None
            position = 0
            for media_row in media_rows:
                if media_row["report_id"] != current_report_id:
                    current_report_id = media_row["report_id"]
                    position = 0
                db.session.execute(
                    text(
                        "UPDATE proof_media SET position = :position "
                        "WHERE id = :media_id"
                    ),
                    {"position": position, "media_id": media_row["id"]},
                )
                position += 1
            db.session.commit()

        missing_guids = db.session.execute(
            text("SELECT id FROM shop_report WHERE guid IS NULL OR guid = ''")
        ).scalars()
        for report_id in missing_guids:
            db.session.execute(
                text("UPDATE shop_report SET guid = :guid WHERE id = :report_id"),
                {"guid": str(uuid.uuid4()), "report_id": report_id},
            )
        db.session.commit()

        report_indexes = inspect(db.engine).get_indexes("shop_report")
        if not any(index.get("column_names") == ["guid"] for index in report_indexes):
            db.session.execute(
                text("CREATE UNIQUE INDEX ix_shop_report_guid ON shop_report (guid)")
            )
            db.session.commit()

        admin_email = app.config["ADMIN_EMAIL"]
        admin_password = app.config["ADMIN_PASSWORD"]
        admin_username = app.config["ADMIN_USERNAME"]
        if admin_email and (admin_password or admin_username):
            admin_user = User.query.filter_by(email=admin_email).first()
            if admin_username:
                username_owner = User.query.filter_by(username=admin_username).first()
                if username_owner is not None and username_owner.email != admin_email:
                    raise RuntimeError(
                        "ADMIN_USERNAME is already used by another account."
                    )
            if admin_user is None and admin_password:
                email_prefix = admin_email.partition("@")[0]
                if admin_username:
                    candidate = admin_username
                else:
                    base = "".join(
                        character if character.isalnum() or character == "_" else "_"
                        for character in normalize_username(email_prefix)
                    ).strip("_")[:30]
                    if not is_valid_username(base):
                        base = "admin"
                    candidate = base
                    suffix_number = 1
                    while User.query.filter_by(username=candidate).first() is not None:
                        suffix = f"_{suffix_number}"
                        candidate = f"{base[: 30 - len(suffix)]}{suffix}"
                        suffix_number += 1
                display_name = email_prefix[:80]
                if len(display_name) < 2:
                    display_name = "Administrator"
                admin_user = User(
                    display_name=display_name,
                    username=candidate,
                    email=admin_email,
                )
                admin_user.set_password(admin_password)
                db.session.add(admin_user)
                db.session.commit()
            elif admin_user is not None:
                admin_changed = False
                if admin_password and not admin_user.check_password(admin_password):
                    admin_user.set_password(admin_password)
                    admin_changed = True
                if admin_username and admin_user.username != admin_username:
                    admin_user.username = admin_username
                    admin_changed = True
                if admin_changed:
                    db.session.commit()

    return app
