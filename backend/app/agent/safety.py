"""Small JSON and secret-echo guards shared by model and tool boundaries."""

import json


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError()
        value[key] = item
    return value


def reject_constant(_):
    raise ValueError()


def load_object(raw, limit):
    if not isinstance(raw, (str, bytes)) or len(raw) > limit:
        raise ValueError()
    if isinstance(raw, str) and len(raw.encode("utf-8")) > limit:
        raise ValueError()
    value = json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant)
    if not isinstance(value, dict):
        raise ValueError()
    return value


def contains_secret(value, secrets):
    if isinstance(value, str):
        return any(secret in value for secret in secrets)
    if isinstance(value, dict):
        return any(
            contains_secret(key, secrets) or contains_secret(item, secrets)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(contains_secret(item, secrets) for item in value)
    return False


def configured_secrets(config):
    return tuple(
        value.get_secret_value()
        for value in (
            config.nebius_api_key,
            config.api_access_token,
            config.n8n_api_key,
            config.vercel_token,
            config.supabase_access_token,
            config.postgres_password,
            config.storage_database_url,
        )
        if value
    )
