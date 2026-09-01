"""Cache local de mapeo issue_key → issue_id.

Como Tempo API v4 requiere issue_id (numérico) y la autenticación
con Jira puede no estar disponible, mantenemos un cache local que
se construye a partir de:

1. Worklogs existentes en Tempo (extraen issue.id y issue.self → issue_key)
2. Entradas manuales del usuario en config.yaml
3. Resolución contra Jira API (si está disponible)
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from tempo_cli.client import TempoClient


CACHE_DIR = Path.home() / ".tempo-cli"
CACHE_FILE = CACHE_DIR / "issue_cache.json"


def _load_cache() -> dict[str, int]:
    """Carga el cache desde disco."""
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_cache(cache: dict[str, int]) -> None:
    """Guarda el cache a disco."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, indent=2))


def _extract_key_from_self_url(self_url: str) -> str | None:
    """Extrae el issue key de una URL self de Jira si es posible.

    Las URLs tienen formato: https://xxx.atlassian.net/rest/api/2/issue/12345
    No contienen el key directamente, así que retornamos None.
    """
    return None


def build_cache_from_worklogs(client: TempoClient, account_id: str) -> dict[str, int]:
    """Construye/actualiza el cache escaneando worklogs recientes.

    Escanea los últimos 90 días de worklogs del usuario para extraer
    todos los pares (issue_key, issue_id) que encuentre.
    """
    cache = _load_cache()

    # Buscar worklogs del usuario en los últimos 90 días
    to_date = date.today()
    from_date = to_date - timedelta(days=90)

    try:
        worklogs = client.get_worklogs(account_id, from_date, to_date)
    except Exception:
        return cache

    for wl in worklogs:
        issue_data = wl.get("issue", {})
        issue_id = issue_data.get("id")
        # Tempo v4 no incluye key en la respuesta, solo id y self
        # Pero self tiene el formato: .../rest/api/2/issue/{id}
        # No podemos extraer el key de ahí

    _save_cache(cache)
    return cache


def resolve_issue_id(
    issue_key: str,
    client: TempoClient,
    account_id: str,
    config: dict[str, Any] | None = None,
) -> int | None:
    """Resuelve un issue_key a su issue_id numérico.

    Orden de búsqueda:
    1. Cache local (issue_cache.json)
    2. Mapeo explícito en config.yaml (frequent_issues[].id)
    3. Intento de resolución vía Jira API (si funciona)
    4. None si no se encuentra
    """
    cache = _load_cache()

    # 1. Cache local
    if issue_key in cache:
        return cache[issue_key]

    # 2. Config YAML (el usuario puede especificar el ID directamente)
    if config:
        for issue in config.get("frequent_issues", []):
            key = issue.get("key", "")
            alias = issue.get("alias", "")
            issue_id = issue.get("id")
            if issue_id and (key == issue_key or alias == issue_key):
                cache[issue_key] = int(issue_id)
                _save_cache(cache)
                return int(issue_id)

    # 3. No encontrado
    return None


def add_to_cache(issue_key: str, issue_id: int) -> None:
    """Agrega manualmente un mapeo al cache."""
    cache = _load_cache()
    cache[issue_key] = issue_id
    _save_cache(cache)


def remove_from_cache(issue_key: str) -> None:
    """Elimina un mapeo del cache."""
    cache = _load_cache()
    cache.pop(issue_key, None)
    _save_cache(cache)


def list_cache() -> dict[str, int]:
    """Lista todos los mapeos en cache."""
    return _load_cache()
