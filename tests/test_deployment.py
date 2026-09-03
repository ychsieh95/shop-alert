from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_uses_non_root_user_and_checks_static_assets():
    contents = (PROJECT_ROOT / "docker" / "Dockerfile").read_text(encoding="utf-8")

    assert "ARG APP_UID=" in contents
    assert "USER $APP_UID" in contents
    assert "'/assets/css/app.css'" in contents
    assert 'CMD ["gunicorn"' in contents


def test_compose_uses_repository_build_context():
    contents = (PROJECT_ROOT / "docker" / "compose.yaml").read_text(
        encoding="utf-8"
    )

    assert "context: .." in contents
    assert "dockerfile: docker/Dockerfile" in contents
    assert "APP_UID: ${APP_UID:-1654}" in contents
    assert "- ../.env" in contents
