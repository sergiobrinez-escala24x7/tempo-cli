"""Cliente HTTP para la API de Google Calendar (Apps Script Web App)."""

from __future__ import annotations

from datetime import date
from typing import Any

import requests


class GoogleCalendarClient:
    """Cliente para consultar eventos de Google Calendar vía Apps Script.

    El endpoint es un Web App de Google Apps Script que expone
    eventos del calendario del usuario en formato JSON.
    """

    def __init__(self, script_url: str, api_key: str):
        self.script_url = script_url.rstrip("/")
        self.api_key = api_key
        self.session = requests.Session()

    def get_events(self, from_date: date, to_date: date) -> list[dict[str, Any]]:
        """Obtiene eventos del calendario en un rango de fechas.

        Args:
            from_date: Fecha inicio (inclusive).
            to_date: Fecha fin (inclusive).

        Returns:
            Lista de eventos con keys: id, title, description,
            start_date, start_time, end_time, duration_hours,
            calendar, is_recurring, organizer.
        """
        response = self.session.get(
            self.script_url,
            params={
                "key": self.api_key,
                "from": from_date.isoformat(),
                "to": to_date.isoformat(),
            },
            allow_redirects=True,
            timeout=30,
        )

        if not response.ok:
            try:
                detail = response.json()
                msg = detail.get("error", response.text[:200])
            except Exception:
                msg = response.text[:200]
            raise Exception(f"Google Calendar API error ({response.status_code}): {msg}")

        data = response.json()

        # Validar que la respuesta tenga la estructura esperada
        if "error" in data:
            raise Exception(f"Google Calendar API: {data['error']}")

        return data.get("events", [])

    def test_connection(self) -> dict[str, Any]:
        """Verifica que la conexión al endpoint funcione.

        Hace una consulta del día actual para validar credenciales.
        Retorna metadata de la respuesta (timezone, count).
        """
        today = date.today()
        response = self.session.get(
            self.script_url,
            params={
                "key": self.api_key,
                "from": today.isoformat(),
                "to": today.isoformat(),
            },
            allow_redirects=True,
            timeout=30,
        )

        if not response.ok:
            raise Exception(
                f"No se pudo conectar al endpoint ({response.status_code}). "
                "Verifica la URL y el API key."
            )

        data = response.json()

        if "error" in data:
            raise Exception(f"Endpoint respondió con error: {data['error']}")

        return {
            "timezone": data.get("timezone", "desconocida"),
            "events_today": data.get("count", 0),
            "from": data.get("from", today.isoformat()),
            "to": data.get("to", today.isoformat()),
        }
