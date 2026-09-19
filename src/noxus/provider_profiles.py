from __future__ import annotations

import ipaddress
import json
import os
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

from .api_core import ApiError, ProviderConfig


class ProviderProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_type: Literal["local_openai_compatible", "openai_compatible", "gemini_native"]
    api_key_env: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$", max_length=128)
    base_url: str | None = None
    red_model: str = Field(min_length=1, max_length=200)
    judge_model: str = Field(min_length=1, max_length=200)
    tuning_model: str = Field(min_length=1, max_length=200)


def is_loopback(host: str | None) -> bool:
    try:
        return ipaddress.ip_address(host or "").is_loopback
    except ValueError:
        return False


def manual_keys_enabled() -> bool:
    return os.environ.get("NOXUS_ENABLE_MANUAL_KEYS", "").lower() == "true"


def _validate_endpoint(profile: ProviderProfile) -> None:
    if profile.provider_type == "gemini_native":
        if profile.base_url is not None:
            raise ValueError("Gemini native uses its fixed HTTPS endpoint")
        return
    endpoint = profile.base_url
    if endpoint is None and profile.provider_type == "local_openai_compatible":
        return
    parsed = urlsplit(endpoint or "")
    if (
        not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Invalid provider endpoint")
    local = parsed.hostname == "localhost" or is_loopback(parsed.hostname)
    if parsed.scheme != "https" and not (parsed.scheme == "http" and local):
        raise ValueError("Non-local provider endpoints require HTTPS")


def load_profiles() -> dict[str, ProviderProfile]:
    raw = os.environ.get("NOXUS_PROVIDER_PROFILES", "{}")
    try:
        profiles = json.loads(raw)
        if not isinstance(profiles, dict):
            raise ValueError("Profile configuration must be an object")
        parsed = {}
        for name, value in profiles.items():
            if not isinstance(name, str) or not name or len(name) > 80:
                raise ValueError("Invalid profile name")
            if not all(char.isascii() and (char.isalnum() or char in "-_") for char in name):
                raise ValueError("Invalid profile name")
            profile = ProviderProfile.model_validate(value)
            _validate_endpoint(profile)
            parsed[name] = profile
        return parsed
    except (ValueError, TypeError) as exc:
        raise ApiError(503, "Server provider profiles are not configured correctly.") from exc


def profile_catalog(*, client_host: str | None) -> dict:
    return {
        "profiles": [
            {"name": name, "provider_type": profile.provider_type}
            for name, profile in sorted(load_profiles().items())
        ],
        "manual_keys_enabled": manual_keys_enabled() and is_loopback(client_host),
    }


def resolve_provider_selection(
    profile_name: str | None,
    manual_config: ProviderConfig | None,
    *,
    client_host: str | None,
) -> ProviderConfig:
    if profile_name is not None and manual_config is not None:
        raise ApiError(400, "Choose a provider_profile or local provider_config, not both.")
    if manual_config is not None:
        if not manual_keys_enabled() or not is_loopback(client_host):
            raise ApiError(403, "Manual provider credentials are disabled for this connection.")
        return manual_config
    if not profile_name:
        raise ApiError(400, "Agent-assisted requests require a server provider_profile.")
    profile = load_profiles().get(profile_name)
    if profile is None:
        raise ApiError(400, "Unknown provider profile.")
    api_key = os.environ.get(profile.api_key_env)
    if not api_key or not api_key.strip():
        raise ApiError(503, "The selected provider profile has no configured credential.")
    return ProviderConfig(
        provider_type=profile.provider_type,
        api_key=api_key,
        base_url=profile.base_url,
        red_model=profile.red_model,
        judge_model=profile.judge_model,
        tuning_model=profile.tuning_model,
    )
