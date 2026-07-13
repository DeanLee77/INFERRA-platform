from __future__ import annotations

from dataclasses import dataclass
import re

from cryptography.fernet import Fernet, InvalidToken

from src.infrastructure.secrets import read_secret


ENCRYPTED_SECRET_PREFIX = "enc:v1:"
PRIMARY_KEY_SECRET = "AEGIS_LLM_API_KEY_ENCRYPTION_KEY"
PREVIOUS_KEYS_SECRET = "AEGIS_LLM_API_KEY_ENCRYPTION_PREVIOUS_KEYS"


class LLMSecretEncryptionError(ValueError):
    """Raised when stored LLM secrets cannot be encrypted or decrypted safely."""


@dataclass(frozen=True)
class DecryptedLLMSecret:
    value: str | None
    needs_rotation: bool = False


def encrypt_llm_api_key(value: str | None) -> str | None:
    if value is None:
        return None
    primary_key = _primary_key()
    if primary_key is None:
        raise LLMSecretEncryptionError(
            f"{PRIMARY_KEY_SECRET} or {PRIMARY_KEY_SECRET}_FILE must be set "
            "before storing editable AEGIS LLM API keys"
        )
    token = _fernet(primary_key).encrypt(value.encode("utf-8")).decode("ascii")
    return f"{ENCRYPTED_SECRET_PREFIX}{token}"


def decrypt_llm_api_key(stored_value: str | None) -> DecryptedLLMSecret:
    if stored_value is None:
        return DecryptedLLMSecret(value=None)
    normalized = stored_value.strip()
    if not normalized:
        return DecryptedLLMSecret(value=None)

    primary_key = _primary_key()
    if not normalized.startswith(ENCRYPTED_SECRET_PREFIX):
        return DecryptedLLMSecret(
            value=normalized,
            needs_rotation=primary_key is not None,
        )

    token = normalized.removeprefix(ENCRYPTED_SECRET_PREFIX).encode("ascii")
    for key in _configured_keys(primary_key):
        try:
            decrypted = _fernet(key).decrypt(token).decode("utf-8")
        except InvalidToken:
            continue
        return DecryptedLLMSecret(
            value=decrypted,
            needs_rotation=primary_key is not None and key != primary_key,
        )

    raise LLMSecretEncryptionError(
        "Stored AEGIS LLM API key cannot be decrypted with the configured keys"
    )


def _configured_keys(primary_key: str | None) -> list[str]:
    keys: list[str] = []
    if primary_key:
        keys.append(primary_key)
    for key in _previous_keys():
        if key not in keys:
            keys.append(key)
    return keys


def _primary_key() -> str | None:
    value = read_secret(PRIMARY_KEY_SECRET)
    return value.strip() if value and value.strip() else None


def _previous_keys() -> list[str]:
    value = read_secret(PREVIOUS_KEYS_SECRET)
    if not value:
        return []
    return [key for key in re.split(r"[\s,]+", value.strip()) if key]


def _fernet(key: str) -> Fernet:
    try:
        return Fernet(key.encode("ascii"))
    except Exception as exc:
        raise LLMSecretEncryptionError(
            f"{PRIMARY_KEY_SECRET} values must be Fernet-compatible 32-byte keys"
        ) from exc
