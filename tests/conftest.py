import pytest

from app import create_app
from app.extensions import db


@pytest.fixture()
def app(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
            "LINK_PREVIEW_FOLDER": str(tmp_path / "link-previews"),
            "SECRET_KEY": "test-secret",
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
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def auth(client):
    class AuthActions:
        def signup(
            self,
            email="reporter@example.com",
            password="password123",
            username=None,
        ):
            username = username or email.partition("@")[0].replace(".", "_")
            return client.post(
                "/signup",
                data={
                    "display_name": "Careful Reporter",
                    "username": username,
                    "email": email,
                    "password": password,
                },
                follow_redirects=True,
            )

        def login(
            self,
            email="reporter@example.com",
            password="password123",
            username=None,
        ):
            return client.post(
                "/login",
                data={"identifier": username or email, "password": password},
                follow_redirects=True,
            )

        def logout(self):
            return client.post("/logout", follow_redirects=True)

    return AuthActions()
