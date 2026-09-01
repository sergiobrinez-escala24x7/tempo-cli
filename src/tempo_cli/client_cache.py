"""Cache local de mapeo proyecto → cliente (account key).

El atributo obligatorio "_Cliente_" (tipo ACCOUNT) de Tempo requiere el
*key* del account (ej. "PRINCIPALG"), no su id numérico. La app web lo
resuelve automáticamente porque tiene acceso completo a Tempo Accounts.

Con el token estándar de la CLI (sin scope accounts:view) no podemos
traducir el account id → key directamente. Pero sí podemos aprender el
key a partir de worklogs previos: cada worklog ya creado guarda el valor
del atributo _Cliente_ como key.

Este módulo mantiene un cache local que asocia:

    project_key (ej. "PRCL") → cliente/account key (ej. "PRINCIPALG")

Así, una vez que se ha registrado tiempo en cualquier issue de un
proyecto, el cliente se auto-resuelve para todos los demás issues del
mismo proyecto — sin necesitar scope adicional ni configuración manual.
"""

from __future__ import annotations

import json
from pathlib import Path


CACHE_DIR = Path.home() / ".tempo-cli"
CACHE_FILE = CACHE_DIR / "client_cache.json"


def _load() -> dict[str, str]:
    """Carga el cache de proyecto → cliente desde disco."""
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save(cache: dict[str, str]) -> None:
    """Guarda el cache a disco."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, indent=2))


def get_client_for_project(project_key: str) -> str | None:
    """Retorna el cliente (account key) cacheado para un proyecto, o None."""
    return _load().get(project_key)


def set_client_for_project(project_key: str, client_value: str) -> None:
    """Guarda el mapeo proyecto → cliente en el cache."""
    cache = _load()
    if cache.get(project_key) != client_value:
        cache[project_key] = client_value
        _save(cache)


def list_cache() -> dict[str, str]:
    """Lista todos los mapeos proyecto → cliente."""
    return _load()


def remove_project(project_key: str) -> None:
    """Elimina un mapeo del cache."""
    cache = _load()
    if cache.pop(project_key, None) is not None:
        _save(cache)
