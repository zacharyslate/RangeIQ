from pathlib import Path

import pytest

from ranch_ai.services.auth_service import AuthError, AuthService


def test_auth_service_can_create_and_authenticate_user(tmp_path: Path):
    service = AuthService(tmp_path / "rangeiq_auth.sqlite")
    created = service.create_user(
        email="rancher@example.com",
        password="supersecure",
        full_name="Ranch Owner",
        ranch_name="Caja Caliente",
        ranch_address="711 N Scotty Road, Alpine, TX 79830",
        ranch_latitude=29.606333,
        ranch_longitude=-103.50975,
    )

    assert created.email == "rancher@example.com"
    assert created.workspace_id.startswith("user-rancher-")

    authenticated = service.authenticate_user(email="rancher@example.com", password="supersecure")
    assert authenticated.user_id == created.user_id
    assert authenticated.last_login_at is not None


def test_auth_service_rejects_duplicate_email(tmp_path: Path):
    service = AuthService(tmp_path / "rangeiq_auth.sqlite")
    payload = {
        "email": "duplicate@example.com",
        "password": "supersecure",
        "full_name": "Owner",
        "ranch_name": "Caja Caliente",
        "ranch_address": "711 N Scotty Road, Alpine, TX 79830",
    }
    service.create_user(**payload)

    with pytest.raises(AuthError, match="already exists"):
        service.create_user(**payload)


def test_auth_service_updates_profile(tmp_path: Path):
    service = AuthService(tmp_path / "rangeiq_auth.sqlite")
    user = service.create_user(
        email="profile@example.com",
        password="supersecure",
        full_name="Original Name",
        ranch_name="Original Ranch",
        ranch_address="Old Address",
    )

    updated = service.update_user_profile(
        user.user_id,
        full_name="Updated Name",
        ranch_name="Updated Ranch",
        ranch_address="New Address",
        ranch_latitude=29.6,
        ranch_longitude=-103.5,
    )

    assert updated.full_name == "Updated Name"
    assert updated.ranch_name == "Updated Ranch"
    assert updated.ranch_address == "New Address"
    assert updated.ranch_latitude == pytest.approx(29.6)
    assert updated.ranch_longitude == pytest.approx(-103.5)


def test_auth_service_rejects_bad_password(tmp_path: Path):
    service = AuthService(tmp_path / "rangeiq_auth.sqlite")
    service.create_user(
        email="login@example.com",
        password="supersecure",
        full_name="Login Name",
        ranch_name="Caja Caliente",
        ranch_address="711 N Scotty Road, Alpine, TX 79830",
    )

    with pytest.raises(AuthError, match="Incorrect password"):
        service.authenticate_user(email="login@example.com", password="wrongpass")
