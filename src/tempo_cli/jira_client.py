"""Cliente HTTP para la API de Jira usando OAuth 2.0 Bearer token."""

from __future__ import annotations

from typing import Any

import requests


class JiraClient:
    """Cliente para interactuar con Jira REST API via OAuth 2.0.

    Usa la API de Atlassian Cloud (api.atlassian.com) con Bearer token.
    """

    def __init__(self, cloud_id: str, access_token: str):
        self.base_url = f"https://api.atlassian.com/ex/jira/{cloud_id}"
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            }
        )

    def get_issue_id(self, issue_key: str) -> int:
        """Obtiene el ID numérico de un issue a partir de su key (ej: INT-45 → 12345)."""
        response = self.session.get(
            f"{self.base_url}/rest/api/3/issue/{issue_key}",
            params={"fields": "summary"},
        )
        if not response.ok:
            try:
                detail = response.json()
                msg = detail.get("errorMessages", [str(detail)])
            except Exception:
                msg = [response.text[:200]]
            raise Exception(f"No se pudo resolver '{issue_key}': {msg}")

        data = response.json()
        return int(data["id"])

    def get_issue_summary(self, issue_key: str) -> str:
        """Obtiene el summary de un issue."""
        response = self.session.get(
            f"{self.base_url}/rest/api/3/issue/{issue_key}",
            params={"fields": "summary"},
        )
        response.raise_for_status()
        return response.json()["fields"]["summary"]

    def get_issue_key_by_id(self, issue_id: int) -> str:
        """Obtiene el key de un issue a partir de su ID numérico (ej: 12345 → INT-45)."""
        response = self.session.get(
            f"{self.base_url}/rest/api/3/issue/{issue_id}",
            params={"fields": "summary"},
        )
        if not response.ok:
            return f"#{issue_id}"

        data = response.json()
        return data.get("key", f"#{issue_id}")

    def get_project_key(self, issue_key_or_id: str | int) -> str | None:
        """Obtiene el project key (ej. 'PRCL') de un issue por su key o id."""
        response = self.session.get(
            f"{self.base_url}/rest/api/3/issue/{issue_key_or_id}",
            params={"fields": "project"},
        )
        if not response.ok:
            return None

        data = response.json()
        return data.get("fields", {}).get("project", {}).get("key")

    def find_issue_ids_in_project(self, project_key: str, max_results: int = 20) -> list[int]:
        """Busca IDs de issues que pertenecen a un proyecto, priorizando los que tienen worklogs.

        Usa JQL para traer issues del proyecto ordenados por actividad reciente.
        Retorna una lista de issue IDs numéricos (útil para buscar el cliente
        en worklogs previos del proyecto, incluyendo los creados por la web).
        """
        jql = f"project = {project_key} AND worklogDate is not EMPTY ORDER BY updated DESC"
        response = self.session.get(
            f"{self.base_url}/rest/api/3/search/jql",
            params={"jql": jql, "fields": "id", "maxResults": max_results},
        )
        if not response.ok:
            # Fallback sin el filtro de worklogDate (algunas instancias no lo soportan en JQL)
            jql_simple = f"project = {project_key} ORDER BY updated DESC"
            response = self.session.get(
                f"{self.base_url}/rest/api/3/search/jql",
                params={"jql": jql_simple, "fields": "id", "maxResults": max_results},
            )
            if not response.ok:
                return []

        issues = response.json().get("issues", [])
        ids = []
        for issue in issues:
            try:
                ids.append(int(issue["id"]))
            except (KeyError, ValueError, TypeError):
                continue
        return ids

    def find_user_by_email(self, email: str) -> dict[str, str]:
        """Busca un usuario en Jira por email y retorna accountId y displayName.

        Usa el endpoint de búsqueda de usuarios de Jira Cloud.
        """
        response = self.session.get(
            f"{self.base_url}/rest/api/3/user/search",
            params={"query": email},
        )
        if not response.ok:
            raise Exception(f"Error al buscar usuario: {response.status_code} — {response.text[:200]}")

        users = response.json()
        if not users:
            raise Exception(f"No se encontró ningún usuario con el email '{email}'.")

        # Retornar el primer match
        user = users[0]
        return {
            "accountId": user["accountId"],
            "displayName": user.get("displayName", email),
        }
