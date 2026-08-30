from __future__ import annotations

import io
import stat
from pathlib import Path

from PIL import Image

from app.media_rotation import parse_rotation, rotate_media_file


def test_parse_rotation_accepts_only_quarter_turns():
    assert parse_rotation("0") == 0
    assert parse_rotation("90") == 90
    assert parse_rotation(180) == 180
    assert parse_rotation("270") == 270
    assert parse_rotation("360") is None
    assert parse_rotation("left") is None


def test_rotate_image_file_clockwise(tmp_path: Path):
    path = tmp_path / "proof.png"
    image = Image.new("RGB", (3, 2))
    image.putpixel((0, 0), (255, 0, 0))
    image.putpixel((2, 1), (0, 0, 255))
    image.save(path)

    rotate_media_file(path, "image", 90)

    with Image.open(path) as rotated:
        assert rotated.size == (2, 3)
        assert rotated.getpixel((1, 0)) == (255, 0, 0)
        assert rotated.getpixel((0, 2)) == (0, 0, 255)
    assert stat.S_IMODE(path.stat().st_mode) == 0o644


def test_report_upload_applies_submitted_rotation(client, auth, app):
    from app.models import ShopReport

    buffer = io.BytesIO()
    Image.new("RGB", (8, 5), (30, 90, 120)).save(buffer, format="PNG")
    buffer.seek(0)
    auth.signup()

    response = client.post(
        "/reports/new",
        data={
            "name": "Rotated Evidence Shop",
            "address": "100 Community Road, Taipei",
            "controversy": "This report includes enough detail to test rotated evidence uploads.",
            "proof": (buffer, "landscape.png", "image/png"),
            "proof_rotation": "90",
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 302
    with app.app_context():
        media = ShopReport.query.one().media[0]
        stored_path = Path(app.config["UPLOAD_FOLDER"]) / media.stored_name
        with Image.open(stored_path) as rotated:
            assert rotated.size == (5, 8)
        assert stat.S_IMODE(stored_path.stat().st_mode) == 0o644


def test_edit_page_rotates_existing_media_and_discards_its_thumbnail(
    client, auth, app
):
    from app.models import ShopReport

    buffer = io.BytesIO()
    Image.new("RGB", (12, 7), (90, 40, 20)).save(buffer, format="PNG")
    buffer.seek(0)
    auth.signup()
    created = client.post(
        "/reports/new",
        data={
            "name": "Existing Rotation Shop",
            "address": "100 Community Road, Taipei",
            "controversy": "This report includes enough detail to rotate existing evidence.",
            "proof": (buffer, "existing.png", "image/png"),
        },
        content_type="multipart/form-data",
    )
    with app.app_context():
        report = ShopReport.query.one()
        report_url = created.location
        media_id = report.media[0].id
        stored_path = Path(app.config["UPLOAD_FOLDER"]) / report.media[0].stored_name
        thumbnail_folder = Path(app.config["THUMBNAIL_FOLDER"])

    edit_form = client.get(f"{report_url}/edit")
    assert b"data-existing-media-rotate=\"-90\"" in edit_form.data
    assert b"data-media-move=\"-1\"" in edit_form.data
    assert b"data-media-drag-handle" in edit_form.data
    assert b"Drag to reorder" in edit_form.data
    assert f'name="media_rotation_{media_id}"'.encode() in edit_form.data
    client.get(f"/media/{media_id}/thumbnail")
    assert list(thumbnail_folder.glob("*.webp"))

    updated = client.post(
        f"{report_url}/edit",
        data={
            "name": "Existing Rotation Shop",
            "address": "100 Community Road, Taipei",
            "controversy": "This updated report still contains enough detail for rotation.",
            f"media_name_{media_id}": "existing.png",
            f"media_rotation_{media_id}": "90",
        },
        follow_redirects=True,
    )

    assert b"Report updated" in updated.data
    with Image.open(stored_path) as rotated:
        assert rotated.size == (7, 12)
    assert stat.S_IMODE(stored_path.stat().st_mode) == 0o644
    assert list(thumbnail_folder.glob("*.webp")) == []


def test_edit_page_dispatches_existing_video_rotation(client, auth, app, monkeypatch):
    from app.models import ShopReport

    auth.signup()
    created = client.post(
        "/reports/new",
        data={
            "name": "Existing Video Rotation Shop",
            "address": "100 Community Road, Taipei",
            "controversy": "This report includes enough detail to rotate existing video.",
            "proof": (io.BytesIO(b"fake video bytes"), "existing.mp4", "video/mp4"),
        },
        content_type="multipart/form-data",
    )
    with app.app_context():
        media_id = ShopReport.query.one().media[0].id

    calls = []
    monkeypatch.setattr(
        "app.main.rotate_media_file",
        lambda path, media_type, rotation: calls.append((media_type, rotation)),
    )
    updated = client.post(
        f"{created.location}/edit",
        data={
            "name": "Existing Video Rotation Shop",
            "address": "100 Community Road, Taipei",
            "controversy": "This updated report still contains enough detail for rotation.",
            f"media_name_{media_id}": "existing.mp4",
            f"media_rotation_{media_id}": "270",
        },
    )

    assert updated.status_code == 302
    assert calls == [("video", 270)]


def test_failed_edit_restores_existing_media_before_rotation(
    client, auth, app, monkeypatch
):
    from app.main import db
    from app.models import ShopReport

    buffer = io.BytesIO()
    Image.new("RGB", (10, 6), (15, 25, 35)).save(buffer, format="PNG")
    original = buffer.getvalue()
    buffer.seek(0)
    auth.signup()
    created = client.post(
        "/reports/new",
        data={
            "name": "Rotation Rollback Shop",
            "address": "100 Community Road, Taipei",
            "controversy": "This report includes enough detail to test rotation rollback.",
            "proof": (buffer, "rollback.png", "image/png"),
        },
        content_type="multipart/form-data",
    )
    with app.app_context():
        media = ShopReport.query.one().media[0]
        media_id = media.id
        stored_path = Path(app.config["UPLOAD_FOLDER"]) / media.stored_name

    def fail_commit():
        raise RuntimeError("forced commit failure")

    monkeypatch.setattr(db.session, "commit", fail_commit)
    failed = client.post(
        f"{created.location}/edit",
        data={
            "name": "Rotation Rollback Shop",
            "address": "100 Community Road, Taipei",
            "controversy": "This updated report still contains enough detail for rollback.",
            f"media_name_{media_id}": "rollback.png",
            f"media_rotation_{media_id}": "90",
        },
    )

    assert failed.status_code == 200
    assert b"The report could not be updated" in failed.data
    assert stored_path.read_bytes() == original


def test_app_startup_repairs_existing_media_read_permissions(tmp_path: Path):
    from app import create_app

    upload_folder = tmp_path / "uploads"
    thumbnail_folder = tmp_path / "thumbnails"
    upload_folder.mkdir()
    thumbnail_folder.mkdir()
    upload = upload_folder / "old.jpg"
    thumbnail = thumbnail_folder / "old.webp"
    upload.write_bytes(b"old upload")
    thumbnail.write_bytes(b"old thumbnail")
    upload.chmod(0o600)
    thumbnail.chmod(0o600)

    create_app(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'permissions.db'}",
            "UPLOAD_FOLDER": str(upload_folder),
            "THUMBNAIL_FOLDER": str(thumbnail_folder),
            "LINK_PREVIEW_FOLDER": str(tmp_path / "link-previews"),
            "SECRET_KEY": "permission-test-secret",
            "ADMIN_EMAIL": "",
            "ADMIN_PASSWORD": "",
            "ADMIN_USERNAME": "",
            "TURNSTILE_SITE_KEY": "",
            "TURNSTILE_SECRET_KEY": "",
            "TURNSTILE_EXPECTED_HOSTNAME": "",
            "CLOUDFLARE_URL_SCANNER_ACCOUNT_ID": "",
            "CLOUDFLARE_URL_SCANNER_API_TOKEN": "",
        }
    )

    assert stat.S_IMODE(upload.stat().st_mode) & 0o044 == 0o044
    assert stat.S_IMODE(thumbnail.stat().st_mode) & 0o044 == 0o044


def test_report_rejects_invalid_rotation(client, auth, app):
    from app.models import ShopReport

    auth.signup()
    response = client.post(
        "/reports/new",
        data={
            "name": "Invalid Rotation Shop",
            "address": "100 Community Road, Taipei",
            "controversy": "This report includes enough detail to test invalid rotation input.",
            "proof": (io.BytesIO(b"fake image bytes"), "proof.jpg", "image/jpeg"),
            "proof_rotation": "45",
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert b"Choose a valid media rotation." in response.data
    with app.app_context():
        assert ShopReport.query.count() == 0


def test_report_dispatches_video_rotation(client, auth, monkeypatch):
    calls = []

    def record_rotation(path, media_type, rotation):
        calls.append((path, media_type, rotation))

    monkeypatch.setattr("app.main.rotate_media_file", record_rotation)
    auth.signup()
    response = client.post(
        "/reports/new",
        data={
            "name": "Rotated Video Shop",
            "address": "100 Community Road, Taipei",
            "controversy": "This report includes enough detail to test rotated video uploads.",
            "proof": (io.BytesIO(b"fake video bytes"), "proof.mp4", "video/mp4"),
            "proof_rotation": "270",
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 302
    assert len(calls) == 1
    assert calls[0][1:] == ("video", 270)
