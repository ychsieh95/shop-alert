from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_guid() -> str:
    return str(uuid.uuid4())


def normalize_username(value: str) -> str:
    return value.strip().casefold()


def is_valid_username(value: str) -> bool:
    return bool(
        3 <= len(value) <= 30
        and value[0].isalnum()
        and all(character.isalnum() or character == "_" for character in value)
    )


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    display_name = db.Column(db.String(80), nullable=False)
    username = db.Column(db.String(30), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    profile_image_name = db.Column(db.String(255), nullable=True)
    profile_image_mime = db.Column(db.String(120), nullable=True)
    is_banned = db.Column(db.Boolean, default=False, nullable=False, index=True)
    banned_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    reports = db.relationship("ShopReport", back_populates="author", lazy=True)
    report_contacts = db.relationship("ReportContact", back_populates="sender", lazy=True)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def is_active(self) -> bool:
        return not self.is_banned


class LoginThrottle(db.Model):
    """Persistent failed-login state for one normalized account identity and IP."""

    id = db.Column(db.Integer, primary_key=True)
    key_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    failed_count = db.Column(db.Integer, default=0, nullable=False)
    window_started_at = db.Column(db.Integer, nullable=False)
    locked_until = db.Column(db.Integer, nullable=True, index=True)
    updated_at = db.Column(db.Integer, nullable=False)


class ShopReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    guid = db.Column(db.String(36), default=new_guid, unique=True, nullable=False, index=True)
    name = db.Column(db.String(180), nullable=False, index=True)
    address = db.Column(db.String(500), nullable=False, index=True)
    address_en_us = db.Column(db.String(500), nullable=True)
    address_zh_tw = db.Column(db.String(500), nullable=True)
    is_online = db.Column(db.Boolean, default=False, nullable=False, index=True)
    latitude = db.Column(db.Float, nullable=True, index=True)
    longitude = db.Column(db.Float, nullable=True, index=True)
    google_place_id = db.Column(db.String(255), nullable=True)
    controversy = db.Column(db.Text, nullable=False)
    hashtags_json = db.Column(db.Text, default="[]", nullable=False)
    controversy_links_json = db.Column(db.Text, default="[]", nullable=False)
    social_links_json = db.Column(db.Text, default="{}", nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    updated_at = db.Column(
        db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
    archived_at = db.Column(db.DateTime(timezone=True), nullable=True, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    author = db.relationship("User", back_populates="reports")
    media = db.relationship(
        "ProofMedia", back_populates="report", cascade="all, delete-orphan", lazy=True
    )
    contacts = db.relationship(
        "ReportContact", back_populates="report", cascade="all, delete-orphan", lazy=True
    )

    @property
    def has_been_updated(self) -> bool:
        if not self.created_at or not self.updated_at:
            return False
        return self.updated_at - self.created_at >= timedelta(milliseconds=1)

    def localized_address(self, locale: str) -> str:
        if locale == "zh-TW":
            return self.address_zh_tw or self.address
        return self.address_en_us or self.address

    @property
    def hashtags(self) -> list[str]:
        try:
            hashtags = json.loads(self.hashtags_json)
        except (TypeError, json.JSONDecodeError):
            return []
        if not isinstance(hashtags, list):
            return []
        return sorted(
            (hashtag for hashtag in hashtags if isinstance(hashtag, str)),
            key=str.casefold,
        )

    @hashtags.setter
    def hashtags(self, hashtags: list[str]) -> None:
        self.hashtags_json = json.dumps(
            sorted(hashtags, key=str.casefold), ensure_ascii=False
        )

    @property
    def social_links(self) -> dict[str, str]:
        try:
            return json.loads(self.social_links_json)
        except (TypeError, json.JSONDecodeError):
            return {}

    @social_links.setter
    def social_links(self, links: dict[str, str]) -> None:
        self.social_links_json = json.dumps(links, ensure_ascii=False)

    @property
    def controversy_links(self) -> list[str]:
        try:
            links = json.loads(self.controversy_links_json)
        except (TypeError, json.JSONDecodeError):
            return []
        if not isinstance(links, list):
            return []
        return [link for link in links if isinstance(link, str)]

    @controversy_links.setter
    def controversy_links(self, links: list[str]) -> None:
        self.controversy_links_json = json.dumps(links, ensure_ascii=False)


class ProofMedia(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    stored_name = db.Column(db.String(255), unique=True, nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    media_type = db.Column(db.String(16), nullable=False)
    mime_type = db.Column(db.String(120), nullable=False)
    report_id = db.Column(db.Integer, db.ForeignKey("shop_report.id"), nullable=False)

    report = db.relationship("ShopReport", back_populates="media")


class ReportContact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    guid = db.Column(db.String(36), default=new_guid, unique=True, nullable=False, index=True)
    reason = db.Column(db.String(32), nullable=False, index=True)
    details = db.Column(db.Text, nullable=False)
    reply_email = db.Column(db.String(255), nullable=False)
    is_resolved = db.Column(db.Boolean, default=False, nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    report_id = db.Column(db.Integer, db.ForeignKey("shop_report.id"), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    report = db.relationship("ShopReport", back_populates="contacts")
    sender = db.relationship("User", back_populates="report_contacts")
