"""Flujo OAuth 2.0 (3LO) con Atlassian para acceso a Jira."""

from __future__ import annotations

import http.server
import threading
import time
import urllib.parse
import webbrowser
from typing import Any

import requests


ATLASSIAN_AUTH_URL = "https://auth.atlassian.com/authorize"
ATLASSIAN_TOKEN_URL = "https://auth.atlassian.com/oauth/token"
ATLASSIAN_RESOURCES_URL = "https://api.atlassian.com/oauth/token/accessible-resources"
CALLBACK_PORT = 8976
CALLBACK_PATH = "/callback"
REDIRECT_URI = f"http://localhost:{CALLBACK_PORT}{CALLBACK_PATH}"
SCOPES = "read:jira-work offline_access"


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """Handler HTTP que captura el authorization code del redirect."""

    authorization_code: str | None = None
    error: str | None = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if parsed.path == CALLBACK_PATH:
            if "code" in params:
                _CallbackHandler.authorization_code = params["code"][0]
                self._respond(
                    "<html><body><h2>✅ Autorización exitosa</h2>"
                    "<p>Puedes cerrar esta pestaña y volver a la terminal.</p>"
                    "</body></html>"
                )
            elif "error" in params:
                _CallbackHandler.error = params.get("error_description", params["error"])[0]
                self._respond(
                    f"<html><body><h2>❌ Error</h2><p>{_CallbackHandler.error}</p></body></html>"
                )
            else:
                self._respond("<html><body><h2>❌ Respuesta inesperada</h2></body></html>")
        else:
            self.send_response(404)
            self.end_headers()

    def _respond(self, html: str):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

    def log_message(self, format, *args):
        # Silenciar logs del servidor HTTP
        pass


def get_authorization_code(client_id: str) -> str:
    """Abre el navegador para el consent y captura el authorization code.

    Levanta un servidor local temporal en localhost:8976 para recibir el callback.
    """
    # Construir URL de autorización
    params = {
        "audience": "api.atlassian.com",
        "client_id": client_id,
        "scope": SCOPES,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "prompt": "consent",
    }
    auth_url = f"{ATLASSIAN_AUTH_URL}?{urllib.parse.urlencode(params)}"

    # Reset estado
    _CallbackHandler.authorization_code = None
    _CallbackHandler.error = None

    # Levantar servidor local
    server = http.server.HTTPServer(("localhost", CALLBACK_PORT), _CallbackHandler)
    server_thread = threading.Thread(target=server.handle_request, daemon=True)
    server_thread.start()

    # Abrir navegador
    webbrowser.open(auth_url)

    # Esperar a que llegue el callback (timeout 120s)
    timeout = 120
    start = time.time()
    while (
        _CallbackHandler.authorization_code is None
        and _CallbackHandler.error is None
        and time.time() - start < timeout
    ):
        time.sleep(0.5)

    server.server_close()

    if _CallbackHandler.error:
        raise Exception(f"Error de autorización: {_CallbackHandler.error}")

    if _CallbackHandler.authorization_code is None:
        raise Exception("Timeout: no se recibió respuesta de autorización en 120 segundos.")

    return _CallbackHandler.authorization_code


def exchange_code_for_tokens(client_id: str, client_secret: str, code: str) -> dict[str, str]:
    """Intercambia el authorization code por access_token y refresh_token."""
    response = requests.post(
        ATLASSIAN_TOKEN_URL,
        json={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": REDIRECT_URI,
        },
        headers={"Content-Type": "application/json"},
    )

    if not response.ok:
        try:
            detail = response.json()
        except Exception:
            detail = response.text
        raise Exception(f"Error al obtener tokens: {response.status_code} — {detail}")

    data = response.json()
    return {
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
        "expires_in": str(data.get("expires_in", 3600)),
    }


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> dict[str, str]:
    """Renueva el access_token usando el refresh_token."""
    response = requests.post(
        ATLASSIAN_TOKEN_URL,
        json={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        },
        headers={"Content-Type": "application/json"},
    )

    if not response.ok:
        try:
            detail = response.json()
        except Exception:
            detail = response.text
        raise Exception(f"Error al renovar token: {response.status_code} — {detail}")

    data = response.json()
    return {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token", refresh_token),
        "expires_in": str(data.get("expires_in", 3600)),
    }


def get_cloud_id(access_token: str) -> str:
    """Obtiene el cloud ID de la instancia de Jira accesible."""
    response = requests.get(
        ATLASSIAN_RESOURCES_URL,
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
    )
    response.raise_for_status()

    resources = response.json()
    if not resources:
        raise Exception("No se encontraron sitios de Atlassian accesibles con este token.")

    # Retornar el primero (normalmente solo hay uno)
    return resources[0]["id"]
