"""Cliente HTTP para la API de Tempo v4."""

from __future__ import annotations

from datetime import date
from typing import Any

import requests


class TempoClient:
    """Cliente para interactuar con Tempo REST API v4."""

    def __init__(self, base_url: str, api_token: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
            }
        )

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def create_worklog(
        self,
        issue_id: int,
        time_spent_seconds: int,
        start_date: date,
        author_account_id: str,
        start_time: str = "09:00:00",
        description: str | None = None,
        attributes: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Crea un worklog en Tempo API v4 usando issueId numérico."""
        payload: dict[str, Any] = {
            "issueId": issue_id,
            "timeSpentSeconds": time_spent_seconds,
            "startDate": start_date.isoformat(),
            "startTime": start_time,
            "authorAccountId": author_account_id,
        }
        if description:
            payload["description"] = description
        if attributes:
            payload["attributes"] = attributes

        response = self.session.post(self._url("/worklogs"), json=payload)
        if not response.ok:
            try:
                detail = response.json()
            except Exception:
                detail = response.text
            raise Exception(f"{response.status_code}: {detail}")
        return response.json()

    def get_issue_account(self, issue_id: int) -> str | None:
        """Obtiene el account (Cliente) asociado a un issue buscando worklogs previos.

        La interfaz gráfica de Tempo auto-completa el campo Cliente basándose
        en la cuenta vinculada al issue. Replicamos esto buscando worklogs
        existentes del issue y extrayendo el valor del atributo _Cliente_.
        """
        response = self.session.get(
            self._url("/worklogs"),
            params={"issueId": issue_id, "limit": 1},
        )
        if not response.ok:
            return None

        results = response.json().get("results", [])
        if not results:
            return None

        for attr in results[0].get("attributes", {}).get("values", []):
            if attr.get("key") == "_Cliente_":
                return attr["value"]
        return None

    def find_account_by_project(
        self, project_issue_ids: list[int], attribute_key: str = "_Cliente_"
    ) -> str | None:
        """Busca el valor del atributo cliente en worklogs previos del proyecto.

        Recibe una lista de issue_ids que pertenecen al mismo proyecto y
        busca en worklogs recientes (de cualquier usuario) el valor del
        atributo ACCOUNT. Retorna el primer valor encontrado, o None.

        Esto permite resolver el cliente para un issue nuevo del proyecto
        aprovechando que otros issues del mismo proyecto ya tienen worklogs.
        """
        for issue_id in project_issue_ids:
            value = self._account_value_from_issue_worklogs(issue_id, attribute_key)
            if value:
                return value
        return None

    def _account_value_from_issue_worklogs(
        self, issue_id: int, attribute_key: str
    ) -> str | None:
        """Extrae el valor de un atributo ACCOUNT del worklog más reciente de un issue."""
        response = self.session.get(
            self._url("/worklogs"),
            params={"issueId": issue_id, "limit": 1},
        )
        if not response.ok:
            return None

        results = response.json().get("results", [])
        if not results:
            return None

        for attr in results[0].get("attributes", {}).get("values", []):
            if attr.get("key") == attribute_key:
                return attr["value"]
        return None

    def get_required_work_attributes(self) -> list[dict[str, Any]]:
        """Obtiene los work attributes obligatorios configurados en Tempo."""
        response = self.session.get(self._url("/work-attributes"))
        if not response.ok:
            return []
        results = response.json().get("results", [])
        return [attr for attr in results if attr.get("required")]

    def get_worklogs(
        self, account_id: str, from_date: date, to_date: date
    ) -> list[dict[str, Any]]:
        """Obtiene worklogs del usuario en un rango de fechas."""
        response = self.session.get(
            self._url(f"/worklogs/user/{account_id}"),
            params={"from": from_date.isoformat(), "to": to_date.isoformat()},
        )
        response.raise_for_status()
        return response.json().get("results", [])

    def delete_worklog(self, worklog_id: int) -> None:
        """Elimina un worklog por ID.

        NOTA: No expuesto en el CLI — requiere permisos que no se otorgan vía token.
        Conservado como método interno por si se necesita en el futuro.
        """
        response = self.session.delete(self._url(f"/worklogs/{worklog_id}"))
        response.raise_for_status()

    def update_worklog(self, worklog_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        """Actualiza un worklog existente."""
        response = self.session.put(self._url(f"/worklogs/{worklog_id}"), json=payload)
        response.raise_for_status()
        return response.json()

    def get_planned_time(
        self, account_id: str, from_date: date, to_date: date
    ) -> list[dict[str, Any]]:
        """Obtiene eventos de calendario detectados por Tempo (planned time)."""
        response = self.session.get(
            self._url(f"/plans/user/{account_id}"),
            params={"from": from_date.isoformat(), "to": to_date.isoformat()},
        )
        response.raise_for_status()
        return response.json().get("results", [])

    def get_all_worklogs(
        self, from_date: date, to_date: date, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Obtiene todos los worklogs (sin filtro de usuario) para extraer issue IDs."""
        results: list[dict[str, Any]] = []
        offset = 0

        while True:
            response = self.session.get(
                self._url("/worklogs"),
                params={
                    "from": from_date.isoformat(),
                    "to": to_date.isoformat(),
                    "limit": limit,
                    "offset": offset,
                },
            )
            response.raise_for_status()
            data = response.json()
            batch = data.get("results", [])
            results.extend(batch)

            metadata = data.get("metadata", {})
            if metadata.get("next"):
                offset += limit
            else:
                break

        return results

    # ═══════════════════════════════════════════════════════════════
    # TIMESHEET APPROVALS
    # ═══════════════════════════════════════════════════════════════

    def get_timesheet_approval(
        self, account_id: str, from_date: date, to_date: date
    ) -> dict[str, Any]:
        """Obtiene el estado de aprobación del timesheet para un periodo.

        Returns dict con campos como:
        - status: OPEN, WAITING_FOR_APPROVAL, APPROVED, REJECTED
        - period: {from, to}
        - workedSeconds, requiredSeconds
        - reviewer, etc.
        """
        response = self.session.get(
            self._url(f"/timesheet-approvals/user/{account_id}"),
            params={"from": from_date.isoformat(), "to": to_date.isoformat()},
        )
        if not response.ok:
            try:
                detail = response.json()
            except Exception:
                detail = response.text
            raise Exception(f"Error al consultar timesheet: {response.status_code} — {detail}")
        return response.json()

    def submit_timesheet(
        self, account_id: str, from_date: date, to_date: date,
        reviewer_account_id: str | None = None, comment: str | None = None
    ) -> dict[str, Any]:
        """Envía el timesheet para aprobación (submit).

        Equivalente al botón "Submit Period" en la UI de Tempo.
        """
        payload: dict[str, Any] = {}
        if reviewer_account_id:
            payload["reviewerAccountId"] = reviewer_account_id
        if comment:
            payload["comment"] = comment

        response = self.session.post(
            self._url(f"/timesheet-approvals/user/{account_id}/submit"),
            params={"from": from_date.isoformat(), "to": to_date.isoformat()},
            json=payload,
        )
        if not response.ok:
            try:
                detail = response.json()
            except Exception:
                detail = response.text
            raise Exception(f"Error al enviar timesheet: {response.status_code} — {detail}")
        return response.json()

    def recall_timesheet(
        self, account_id: str, from_date: date, to_date: date
    ) -> dict[str, Any]:
        """Reabre un timesheet enviado (recall).

        Solo funciona si el timesheet no ha sido aprobado aún.
        """
        response = self.session.post(
            self._url(f"/timesheet-approvals/user/{account_id}/recall"),
            params={"from": from_date.isoformat(), "to": to_date.isoformat()},
            json={},
        )
        if not response.ok:
            try:
                detail = response.json()
            except Exception:
                detail = response.text
            raise Exception(f"Error al reabrir timesheet: {response.status_code} — {detail}")
        return response.json()

    def search_issue_id_from_jira(self, issue_key: str, jira_base_url: str) -> int | None:
        """Intenta obtener el issue ID usando la URL self que Tempo devuelve.

        Tempo incluye en los worklogs un campo issue.self que apunta a Jira.
        Extraemos el ID numérico de esa URL.
        """
        # El self URL tiene formato: https://xxx.atlassian.net/rest/api/2/issue/12345
        # Podemos construirlo directamente
        jira_url = f"{jira_base_url.rstrip('/')}/rest/api/2/issue/{issue_key}"

        # Intentamos buscar este issue en worklogs conocidos
        # No hacemos request a Jira porque no tenemos auth válida
        return None