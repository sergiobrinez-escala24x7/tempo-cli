"""Carga y validación de configuración.

Credenciales: se leen desde el vault cifrado (~/.tempo-cli/credentials.enc).
              Están atadas al hardware de esta máquina, no requieren contraseña.
Configuración operativa: se lee desde ~/.tempo-cli/config.yaml.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

from tempo_cli.vault import decrypt_credentials, vault_exists


CONFIG_DIR = Path.home() / ".tempo-cli"
CONFIG_FILE = CONFIG_DIR / "config.yaml"

# Cache de credenciales descifradas para la sesión
_credentials_cache: dict[str, str] | None = None


def get_config_path() -> Path:
    """Retorna la ruta al archivo de configuración."""
    return CONFIG_FILE


def load_config() -> dict[str, Any]:
    """Carga la configuración operativa desde el archivo YAML."""
    if not CONFIG_FILE.exists():
        return {}

    with open(CONFIG_FILE, "r") as f:
        config = yaml.safe_load(f) or {}

    return config


def load_credentials() -> dict[str, str]:
    """Carga las credenciales descifradas del vault.

    No requiere contraseña — usa el Machine ID del sistema como clave.
    """
    global _credentials_cache

    if _credentials_cache is not None:
        return _credentials_cache

    if not vault_exists():
        sys.exit(
            "Error: No hay credenciales configuradas.\n"
            "Ejecuta 'tempo auth setup' para configurar la autenticación."
        )

    _credentials_cache = decrypt_credentials()
    return _credentials_cache


def get_tempo_token() -> str:
    """Obtiene el token de Tempo desde el vault."""
    creds = load_credentials()
    token = creds.get("TEMPO_API_TOKEN")
    if not token:
        sys.exit("Error: TEMPO_API_TOKEN no encontrado en el vault. Ejecuta 'tempo auth setup'.")
    return token


def get_tempo_base_url() -> str:
    """Obtiene la base URL de Tempo."""
    creds = load_credentials()
    return creds.get("TEMPO_BASE_URL", "https://api.tempo.io/4")


def get_account_id() -> str:
    """Obtiene el account_id del usuario desde el vault."""
    creds = load_credentials()
    account_id = creds.get("ATLASSIAN_ACCOUNT_ID")
    if not account_id:
        sys.exit("Error: ATLASSIAN_ACCOUNT_ID no encontrado en el vault. Ejecuta 'tempo auth setup'.")
    return account_id


def get_jira_config() -> dict[str, str]:
    """Obtiene configuración de Jira OAuth desde el vault."""
    creds = load_credentials()
    client_id = creds.get("OAUTH_CLIENT_ID")
    client_secret = creds.get("OAUTH_CLIENT_SECRET")

    if not client_id or not client_secret:
        sys.exit("Error: Credenciales OAuth incompletas. Ejecuta 'tempo auth setup'.")

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "access_token": creds.get("OAUTH_ACCESS_TOKEN", ""),
        "refresh_token": creds.get("OAUTH_REFRESH_TOKEN", ""),
        "cloud_id": creds.get("OAUTH_CLOUD_ID", ""),
    }


def save_oauth_tokens(access_token: str, refresh_token: str, cloud_id: str) -> None:
    """Actualiza los tokens OAuth en el vault sin perder los demás campos."""
    creds = load_credentials()
    creds["OAUTH_ACCESS_TOKEN"] = access_token
    creds["OAUTH_REFRESH_TOKEN"] = refresh_token
    creds["OAUTH_CLOUD_ID"] = cloud_id

    from tempo_cli.vault import encrypt_credentials
    encrypt_credentials(creds)

    # Invalidar cache
    global _credentials_cache
    _credentials_cache = None


def resolve_alias(config: dict[str, Any], alias_or_key: str) -> tuple[str, str | None, dict[str, str] | None]:
    """Resuelve un alias a su issue key, descripción default y atributos configurados."""
    for issue in config.get("frequent_issues", []):
        if issue.get("alias") == alias_or_key:
            return issue["key"], issue.get("description"), issue.get("attributes")
    # Si no es alias, buscar por key para obtener atributos
    for issue in config.get("frequent_issues", []):
        if issue.get("key") == alias_or_key:
            return issue["key"], issue.get("description"), issue.get("attributes")
    return alias_or_key, None, None


def get_template(config: dict[str, Any], name: str | None = None) -> list[dict[str, Any]]:
    """Obtiene un template por nombre. Usa 'normal' como default."""
    templates = config.get("templates", {})
    template_name = name or "normal"

    if template_name not in templates:
        sys.exit(f"Error: Template '{template_name}' no encontrado. Disponibles: {list(templates.keys())}")

    return templates[template_name]


def get_hours_per_day(config: dict[str, Any]) -> float:
    """Retorna las horas máximas por día."""
    return float(config.get("defaults", {}).get("hours_per_day", 8))


def get_fill_mode(config: dict[str, Any]) -> str:
    """Retorna el modo de fill (calendar_first, template_only, ask)."""
    return config.get("defaults", {}).get("fill_mode", "calendar_first")


# ═══════════════════════════════════════════════════════════════
# GOOGLE CALENDAR (Apps Script)
# ═══════════════════════════════════════════════════════════════


def gcal_is_configured() -> bool:
    """Verifica si las credenciales de Google Calendar están configuradas."""
    if not vault_exists():
        return False
    creds = load_credentials()
    return bool(creds.get("GCAL_SCRIPT_URL") and creds.get("GCAL_API_KEY"))


def get_gcal_config() -> dict[str, str]:
    """Obtiene la configuración de Google Calendar desde el vault.

    Returns:
        Dict con 'script_url' y 'api_key'.

    Raises:
        SystemExit si no están configuradas.
    """
    creds = load_credentials()
    script_url = creds.get("GCAL_SCRIPT_URL")
    api_key = creds.get("GCAL_API_KEY")

    if not script_url or not api_key:
        sys.exit(
            "Error: Google Calendar no configurado.\n"
            "Ejecuta 'tempo calendar login' para configurar el acceso."
        )

    return {
        "script_url": script_url,
        "api_key": api_key,
    }


def save_gcal_credentials(script_url: str, api_key: str) -> None:
    """Guarda las credenciales de Google Calendar en el vault.

    Preserva las demás credenciales existentes (Tempo, Jira OAuth).
    """
    creds = load_credentials()
    creds["GCAL_SCRIPT_URL"] = script_url
    creds["GCAL_API_KEY"] = api_key

    from tempo_cli.vault import encrypt_credentials
    encrypt_credentials(creds)

    # Invalidar cache
    global _credentials_cache
    _credentials_cache = None


def remove_gcal_credentials() -> None:
    """Elimina las credenciales de Google Calendar del vault.

    Preserva las demás credenciales.
    """
    creds = load_credentials()
    creds.pop("GCAL_SCRIPT_URL", None)
    creds.pop("GCAL_API_KEY", None)

    from tempo_cli.vault import encrypt_credentials
    encrypt_credentials(creds)

    # Invalidar cache
    global _credentials_cache
    _credentials_cache = None
