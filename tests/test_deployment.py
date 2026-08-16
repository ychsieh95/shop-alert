from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_supported_dockerfiles_serve_package_static_directory():
    dockerfiles = (
        PROJECT_ROOT / "Dockerfile",
        PROJECT_ROOT / "private" / "Docker" / "Dockerfile",
    )

    for dockerfile in dockerfiles:
        contents = dockerfile.read_text(encoding="utf-8")
        assert "STATIC_PATH=/app/app/static" in contents
        assert "STATIC_URL=/assets" in contents
        assert "ln -s /app/app/static /app/static" in contents
        assert "'/assets/css/app.css'" in contents


def test_supported_dockerfiles_remain_identical():
    public = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
    private = (PROJECT_ROOT / "private" / "Docker" / "Dockerfile").read_text(
        encoding="utf-8"
    )

    assert public == private
