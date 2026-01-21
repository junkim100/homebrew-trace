"""IPC handlers for application settings.

This module registers IPC handlers for settings management, allowing the Electron
frontend to read and modify application settings.
"""

import logging
from typing import Any

from src.core.config import (
    DEFAULT_CONFIG,
    VALID_DAILY_REVISION_HOURS,
    VALID_RETENTION_MONTHS,
    VALID_SUMMARIZATION_INTERVALS,
    VALID_WEEKLY_DIGEST_DAYS,
    get_api_key,
    get_appearance_config,
    get_capture_config,
    get_data_config,
    get_notifications_config,
    get_shortcuts_config,
    load_config,
    save_config,
    set_api_key,
    set_config_value,
    validate_config,
)
from src.core.paths import CACHE_DIR, DATA_ROOT, DB_PATH, NOTES_DIR
from src.trace_app.ipc.server import handler

logger = logging.getLogger(__name__)


@handler("settings.get_all")
def handle_get_all_settings(params: dict[str, Any]) -> dict[str, Any]:
    """Get all application settings.

    Returns:
        Complete settings object with all configuration values and metadata.
    """
    config = load_config()

    return {
        # Full config
        "config": config,
        # Convenience fields
        "appearance": get_appearance_config(),
        "capture": get_capture_config(),
        "notifications": get_notifications_config(),
        "shortcuts": get_shortcuts_config(),
        "data": get_data_config(),
        # API key status (don't expose the actual key)
        "has_api_key": bool(get_api_key()),
        # Paths (read-only info)
        "paths": {
            "data_dir": str(DATA_ROOT),
            "notes_dir": str(NOTES_DIR),
            "db_path": str(DB_PATH),
            "cache_dir": str(CACHE_DIR),
        },
        # Valid options for dropdowns
        "options": {
            "summarization_intervals": VALID_SUMMARIZATION_INTERVALS,
            "daily_revision_hours": VALID_DAILY_REVISION_HOURS,
            "weekly_digest_days": VALID_WEEKLY_DIGEST_DAYS,
            "retention_months": VALID_RETENTION_MONTHS,
        },
        # Defaults for reference
        "defaults": DEFAULT_CONFIG,
    }


@handler("settings.get")
def handle_get_settings(params: dict[str, Any]) -> dict[str, Any]:
    """Get current application settings (legacy endpoint for compatibility).

    Returns:
        Settings dict with api_key status, data directory paths, etc.
    """
    return {
        "data_dir": str(DATA_ROOT),
        "notes_dir": str(NOTES_DIR),
        "db_path": str(DB_PATH),
        "cache_dir": str(CACHE_DIR),
        "has_api_key": bool(get_api_key()),
        # Include new settings
        "appearance": get_appearance_config(),
        "capture": get_capture_config(),
        "notifications": get_notifications_config(),
        "shortcuts": get_shortcuts_config(),
        "data": get_data_config(),
    }


@handler("settings.set")
def handle_set_settings(params: dict[str, Any]) -> dict[str, Any]:
    """Set one or more settings.

    Params:
        settings: Dict of settings to update (can be nested or flat key paths)

    Returns:
        {"success": bool, "errors": list[str]}
    """
    settings = params.get("settings")
    if not settings:
        raise ValueError("settings parameter is required")

    config = load_config()
    errors = []

    # Update config with new values
    for key, value in settings.items():
        if "." in key:
            # Flat key path like "capture.summarization_interval_minutes"
            set_config_value(key, value)
        elif isinstance(value, dict) and key in config:
            # Nested dict like {"capture": {"summarization_interval_minutes": 30}}
            config[key].update(value)
        else:
            config[key] = value

    # Validate
    validation_errors = validate_config(config)
    if validation_errors:
        return {"success": False, "errors": validation_errors}

    # Save
    success = save_config(config)
    return {"success": success, "errors": errors}


@handler("settings.set_value")
def handle_set_value(params: dict[str, Any]) -> dict[str, Any]:
    """Set a single setting value by key path.

    Params:
        key: Dot-separated key path (e.g., "capture.summarization_interval_minutes")
        value: Value to set

    Returns:
        {"success": bool}
    """
    key = params.get("key")
    value = params.get("value")

    if not key:
        raise ValueError("key parameter is required")

    # Validate specific settings
    if key == "capture.summarization_interval_minutes":
        if value not in VALID_SUMMARIZATION_INTERVALS:
            raise ValueError(
                f"Invalid summarization interval: {value}. "
                f"Must be one of {VALID_SUMMARIZATION_INTERVALS}"
            )
    elif key == "capture.daily_revision_hour":
        if value not in VALID_DAILY_REVISION_HOURS:
            raise ValueError(f"Invalid daily revision hour: {value}. Must be 0-23")
    elif key == "notifications.weekly_digest_day":
        if not isinstance(value, str):
            raise ValueError(f"weekly_digest_day must be a string, got {type(value).__name__}")
        if value.lower() not in VALID_WEEKLY_DIGEST_DAYS:
            raise ValueError(
                f"Invalid weekly digest day: {value}. Must be one of {VALID_WEEKLY_DIGEST_DAYS}"
            )
    elif key == "data.retention_months":
        if value not in VALID_RETENTION_MONTHS:
            raise ValueError(
                f"Invalid retention months: {value}. Must be one of {VALID_RETENTION_MONTHS}"
            )

    success = set_config_value(key, value)
    return {"success": success}


@handler("settings.set_api_key")
def handle_set_api_key(params: dict[str, Any]) -> dict[str, Any]:
    """Set the OpenAI API key.

    Params:
        api_key: The API key to set

    Returns:
        {"success": bool}
    """
    api_key = params.get("api_key")
    if not api_key:
        raise ValueError("api_key parameter is required")

    if not isinstance(api_key, str):
        raise ValueError("api_key must be a string")

    api_key = api_key.strip()

    try:
        success = set_api_key(api_key)
        # Reset chat API to use new key
        from src.trace_app.ipc.chat_handlers import reset_chat_api

        reset_chat_api()
        return {"success": success}
    except ValueError as e:
        raise ValueError(str(e)) from e


@handler("settings.get_appearance")
def handle_get_appearance(params: dict[str, Any]) -> dict[str, Any]:
    """Get appearance settings.

    Returns:
        {"show_in_dock": bool, "launch_at_login": bool}
    """
    return get_appearance_config()


@handler("settings.set_appearance")
def handle_set_appearance(params: dict[str, Any]) -> dict[str, Any]:
    """Set appearance settings.

    Params:
        show_in_dock: bool (optional)
        launch_at_login: bool (optional)

    Returns:
        {"success": bool}
    """
    config = load_config()

    if "show_in_dock" in params:
        config["appearance"]["show_in_dock"] = bool(params["show_in_dock"])
    if "launch_at_login" in params:
        config["appearance"]["launch_at_login"] = bool(params["launch_at_login"])

    success = save_config(config)
    return {"success": success}


@handler("settings.get_capture")
def handle_get_capture(params: dict[str, Any]) -> dict[str, Any]:
    """Get capture settings.

    Returns:
        Capture configuration dict
    """
    return get_capture_config()


@handler("settings.set_capture")
def handle_set_capture(params: dict[str, Any]) -> dict[str, Any]:
    """Set capture settings.

    Params:
        summarization_interval_minutes: int (optional)
        daily_revision_hour: int (optional)
        blocked_apps: list[str] (optional)
        blocked_domains: list[str] (optional)

    Returns:
        {"success": bool}
    """
    config = load_config()

    if "summarization_interval_minutes" in params:
        interval = params["summarization_interval_minutes"]
        if interval not in VALID_SUMMARIZATION_INTERVALS:
            raise ValueError(
                f"Invalid interval: {interval}. Must be one of {VALID_SUMMARIZATION_INTERVALS}"
            )
        config["capture"]["summarization_interval_minutes"] = interval

    if "daily_revision_hour" in params:
        hour = params["daily_revision_hour"]
        if hour not in VALID_DAILY_REVISION_HOURS:
            raise ValueError(f"Invalid hour: {hour}. Must be 0-23")
        config["capture"]["daily_revision_hour"] = hour

    if "blocked_apps" in params:
        blocked_apps = params["blocked_apps"]
        if not isinstance(blocked_apps, (list, tuple)):
            raise ValueError("blocked_apps must be a list")
        if not all(isinstance(app, str) for app in blocked_apps):
            raise ValueError("All blocked_apps entries must be strings")
        config["capture"]["blocked_apps"] = list(blocked_apps)

    if "blocked_domains" in params:
        blocked_domains = params["blocked_domains"]
        if not isinstance(blocked_domains, (list, tuple)):
            raise ValueError("blocked_domains must be a list")
        if not all(isinstance(domain, str) for domain in blocked_domains):
            raise ValueError("All blocked_domains entries must be strings")
        config["capture"]["blocked_domains"] = list(blocked_domains)

    success = save_config(config)
    return {"success": success}


@handler("settings.get_notifications")
def handle_get_notifications(params: dict[str, Any]) -> dict[str, Any]:
    """Get notification settings.

    Returns:
        Notification configuration dict
    """
    return get_notifications_config()


@handler("settings.set_notifications")
def handle_set_notifications(params: dict[str, Any]) -> dict[str, Any]:
    """Set notification settings.

    Params:
        weekly_digest_enabled: bool (optional)
        weekly_digest_day: str (optional)

    Returns:
        {"success": bool}
    """
    config = load_config()

    if "weekly_digest_enabled" in params:
        config["notifications"]["weekly_digest_enabled"] = bool(params["weekly_digest_enabled"])

    if "weekly_digest_day" in params:
        day_value = params["weekly_digest_day"]
        if not isinstance(day_value, str):
            raise ValueError(f"weekly_digest_day must be a string, got {type(day_value).__name__}")
        day = day_value.lower()
        if day not in VALID_WEEKLY_DIGEST_DAYS:
            raise ValueError(f"Invalid day: {day}. Must be one of {VALID_WEEKLY_DIGEST_DAYS}")
        config["notifications"]["weekly_digest_day"] = day

    success = save_config(config)
    return {"success": success}


@handler("settings.get_shortcuts")
def handle_get_shortcuts(params: dict[str, Any]) -> dict[str, Any]:
    """Get keyboard shortcut settings.

    Returns:
        Shortcuts configuration dict
    """
    return get_shortcuts_config()


@handler("settings.set_shortcuts")
def handle_set_shortcuts(params: dict[str, Any]) -> dict[str, Any]:
    """Set keyboard shortcut settings.

    Params:
        open_trace: str (optional) - Electron accelerator format

    Returns:
        {"success": bool}
    """
    config = load_config()

    if "open_trace" in params:
        shortcut = params["open_trace"]
        if not isinstance(shortcut, str):
            raise ValueError(f"open_trace must be a string, got {type(shortcut).__name__}")
        # Basic validation of accelerator format (should contain at least one modifier + key)
        if not shortcut or len(shortcut) < 3:
            raise ValueError("Invalid shortcut format")
        config["shortcuts"]["open_trace"] = shortcut

    success = save_config(config)
    return {"success": success}


@handler("settings.get_data")
def handle_get_data(params: dict[str, Any]) -> dict[str, Any]:
    """Get data management settings.

    Returns:
        Data configuration dict
    """
    return get_data_config()


@handler("settings.set_data")
def handle_set_data(params: dict[str, Any]) -> dict[str, Any]:
    """Set data management settings.

    Params:
        retention_months: int | None (optional)

    Returns:
        {"success": bool}
    """
    config = load_config()

    if "retention_months" in params:
        retention = params["retention_months"]
        if retention not in VALID_RETENTION_MONTHS:
            raise ValueError(
                f"Invalid retention: {retention}. Must be one of {VALID_RETENTION_MONTHS}"
            )
        config["data"]["retention_months"] = retention

    success = save_config(config)
    return {"success": success}


@handler("settings.reset")
def handle_reset_settings(params: dict[str, Any]) -> dict[str, Any]:
    """Reset all settings to defaults.

    Returns:
        {"success": bool}
    """
    from src.core.config import reset_to_defaults

    success = reset_to_defaults()
    return {"success": success}


@handler("settings.validate_api_key")
def handle_validate_api_key(params: dict[str, Any]) -> dict[str, Any]:
    """Validate an OpenAI API key by making a test API call.

    Params:
        api_key: The API key to validate (optional, uses stored key if not provided)

    Returns:
        {"valid": bool, "error": str | None}
    """
    import httpx

    api_key = params.get("api_key")

    # If no key provided, use stored key
    if not api_key:
        api_key = get_api_key()

    if not api_key:
        return {"valid": False, "error": "No API key provided"}

    # Basic format validation
    if not api_key.startswith("sk-"):
        return {"valid": False, "error": "Invalid API key format. Key should start with 'sk-'"}

    # Test the API key with a minimal API call (list models)
    try:
        response = httpx.get(
            "https://api.openai.com/v1/models",
            headers={
                "Authorization": f"Bearer {api_key}",
            },
            timeout=10.0,
        )

        if response.status_code == 200:
            return {"valid": True, "error": None}
        elif response.status_code == 401:
            return {
                "valid": False,
                "error": "Invalid API key. Please check your key and try again.",
            }
        elif response.status_code == 429:
            return {"valid": False, "error": "Rate limited. Please try again later."}
        else:
            return {"valid": False, "error": f"API error: {response.status_code}"}

    except httpx.TimeoutException:
        return {
            "valid": False,
            "error": "Connection timeout. Please check your internet connection.",
        }
    except httpx.RequestError as e:
        return {"valid": False, "error": f"Connection error: {str(e)}"}
    except Exception as e:
        logger.exception("Failed to validate API key")
        return {"valid": False, "error": f"Validation failed: {str(e)}"}
