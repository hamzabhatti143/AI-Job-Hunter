"""credential_vault_tool — Encrypt and securely retrieve portal credentials.

Wraps the PortalAccount model.
Passwords are encrypted with Fernet (AES-128-CBC) before storage.
VAULT_SECRET env var must be a 32-byte URL-safe base64 string (generate once).

Generate a key:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
import base64
import json
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, text
from agents import function_tool

from db.database import AsyncSessionLocal
from db.models import PortalAccount

_SECRET_RAW = os.getenv("VAULT_SECRET", "")


def _get_fernet():
    """Return a Fernet instance or raise if VAULT_SECRET is not configured."""
    try:
        from cryptography.fernet import Fernet, InvalidToken
        if not _SECRET_RAW:
            raise EnvironmentError("VAULT_SECRET env var is not set. Run: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\" and add to .env")
        return Fernet(_SECRET_RAW.encode())
    except ImportError:
        raise ImportError("cryptography package is required: pip install cryptography")


def _encrypt(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def _decrypt(ciphertext: str) -> str:
    return _get_fernet().decrypt(ciphertext.encode()).decode()


async def vault_store_impl(
    user_id: str,
    portal_name: str,
    portal_url: str,
    username: str,
    password: str,
) -> str:
    """Encrypt password and store portal credentials."""
    uid = uuid.UUID(user_id)
    try:
        encrypted_pwd = _encrypt(password)

        async with AsyncSessionLocal() as session:
            async with session.begin():
                # Upsert — update if portal already stored for this user
                existing = (await session.execute(
                    select(PortalAccount).where(
                        PortalAccount.user_id == uid,
                        PortalAccount.portal_name == portal_name,
                    )
                )).scalar_one_or_none()

                if existing:
                    existing.username           = username
                    existing.encrypted_password = encrypted_pwd
                    existing.portal_url         = portal_url
                else:
                    session.add(PortalAccount(
                        id=uuid.uuid4(),
                        user_id=uid,
                        portal_name=portal_name,
                        portal_url=portal_url,
                        username=username,
                        encrypted_password=encrypted_pwd,
                    ))

        return json.dumps({"success": True, "portal_name": portal_name, "username": username})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


async def vault_retrieve_impl(user_id: str, portal_name: str) -> str:
    """Decrypt and return stored credentials for a portal."""
    uid = uuid.UUID(user_id)
    try:
        async with AsyncSessionLocal() as session:
            account = (await session.execute(
                select(PortalAccount).where(
                    PortalAccount.user_id == uid,
                    PortalAccount.portal_name == portal_name,
                )
            )).scalar_one_or_none()

        if not account:
            return json.dumps({"success": False, "error": f"No credentials stored for {portal_name}"})

        password = _decrypt(account.encrypted_password)
        return json.dumps({
            "success":     True,
            "portal_name": portal_name,
            "portal_url":  account.portal_url,
            "username":    account.username,
            "password":    password,
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


async def vault_list_impl(user_id: str) -> str:
    """List stored portals (without decrypting passwords)."""
    uid = uuid.UUID(user_id)
    try:
        async with AsyncSessionLocal() as session:
            accounts = (await session.execute(
                select(PortalAccount).where(PortalAccount.user_id == uid)
            )).scalars().all()

        return json.dumps({
            "success": True,
            "portals": [
                {
                    "portal_name": a.portal_name,
                    "portal_url":  a.portal_url,
                    "username":    a.username,
                    "created_at":  a.created_at.isoformat(),
                    "last_used":   a.last_used_at.isoformat() if a.last_used_at else None,
                }
                for a in accounts
            ],
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@function_tool
async def credential_vault_store(
    user_id: str, portal_name: str, portal_url: str, username: str, password: str
) -> str:
    """Encrypt and store portal credentials (username + password) for a user.

    Uses Fernet symmetric encryption. Requires VAULT_SECRET in .env.
    """
    return await vault_store_impl(
        user_id=user_id, portal_name=portal_name,
        portal_url=portal_url, username=username, password=password,
    )


@function_tool
async def credential_vault_retrieve(user_id: str, portal_name: str) -> str:
    """Decrypt and return stored portal credentials for a user.

    Returns username and plaintext password for automation use.
    """
    return await vault_retrieve_impl(user_id=user_id, portal_name=portal_name)
