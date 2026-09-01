"""Almacenamiento cifrado de credenciales.

Las credenciales se cifran con Fernet (AES-128-CBC + HMAC-SHA256)
usando una clave derivada del Machine ID del sistema operativo.

Esto garantiza que:
- Solo pueden ser descifradas en esta máquina específica
- No requieren contraseña maestra
- No son portables a otro equipo (ni útiles si alguien copia el archivo)
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


VAULT_DIR = Path.home() / ".tempo-cli"
VAULT_FILE = VAULT_DIR / "credentials.enc"
SALT_FILE = VAULT_DIR / ".salt"

# Campos requeridos para autenticación
REQUIRED_FIELDS = [
    ("TEMPO_API_TOKEN", "Tempo API Token"),
    ("TEMPO_BASE_URL", "Tempo Base URL (default: https://api.tempo.io/4)"),
    ("ATLASSIAN_ACCOUNT_ID", "Atlassian Account ID"),
    ("OAUTH_CLIENT_ID", "OAuth Client ID (de Atlassian Developer Console)"),
    ("OAUTH_CLIENT_SECRET", "OAuth Client Secret"),
]

OPTIONAL_FIELDS: list[tuple[str, str]] = []


def _get_machine_id() -> str:
    """Obtiene un identificador único de la máquina.

    En macOS usa el IOPlatformUUID del hardware.
    Este valor es estable entre reinicios pero único por máquina.
    """
    system = platform.system()

    if system == "Darwin":
        try:
            result = subprocess.run(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                capture_output=True,
                text=True,
            )
            for line in result.stdout.splitlines():
                if "IOPlatformUUID" in line:
                    # Extrae el UUID entre comillas
                    uuid = line.split('"')[-2]
                    return uuid
        except (subprocess.SubprocessError, IndexError):
            pass

    elif system == "Linux":
        # /etc/machine-id es estándar en systemd
        machine_id_path = Path("/etc/machine-id")
        if machine_id_path.exists():
            return machine_id_path.read_text().strip()

    # Fallback: hostname + username (menos seguro pero funcional)
    fallback = f"{platform.node()}-{os.getlogin()}"
    return hashlib.sha256(fallback.encode()).hexdigest()


def _ensure_vault_dir() -> None:
    """Crea el directorio del vault si no existe."""
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(VAULT_DIR, 0o700)


def _get_or_create_salt() -> bytes:
    """Obtiene o genera el salt para derivar la clave."""
    _ensure_vault_dir()
    if SALT_FILE.exists():
        return SALT_FILE.read_bytes()

    salt = os.urandom(16)
    SALT_FILE.write_bytes(salt)
    os.chmod(SALT_FILE, 0o600)
    return salt


def _derive_key(salt: bytes) -> bytes:
    """Deriva una clave Fernet a partir del Machine ID del sistema."""
    machine_id = _get_machine_id()

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480_000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(machine_id.encode()))
    return key


def encrypt_credentials(credentials: dict[str, str]) -> None:
    """Cifra y guarda las credenciales en disco, atadas a esta máquina."""
    _ensure_vault_dir()
    salt = _get_or_create_salt()
    key = _derive_key(salt)
    fernet = Fernet(key)

    data = json.dumps(credentials).encode()
    encrypted = fernet.encrypt(data)

    VAULT_FILE.write_bytes(encrypted)
    os.chmod(VAULT_FILE, 0o600)


def decrypt_credentials() -> dict[str, str]:
    """Descifra y retorna las credenciales almacenadas.

    Solo funciona en la misma máquina donde se cifraron.
    """
    if not VAULT_FILE.exists():
        sys.exit(
            "Error: No hay credenciales configuradas.\n"
            "Ejecuta 'tempo auth setup' para configurar la autenticación."
        )

    salt = _get_or_create_salt()
    key = _derive_key(salt)
    fernet = Fernet(key)

    try:
        encrypted = VAULT_FILE.read_bytes()
        decrypted = fernet.decrypt(encrypted)
        return json.loads(decrypted.decode())
    except InvalidToken:
        sys.exit(
            "Error: No se pudieron descifrar las credenciales.\n"
            "Esto puede ocurrir si el archivo fue movido desde otra máquina.\n"
            "Ejecuta 'tempo auth reset' y luego 'tempo auth setup' para reconfigurar."
        )


def vault_exists() -> bool:
    """Verifica si ya existe un vault configurado."""
    return VAULT_FILE.exists()


def delete_vault() -> None:
    """Elimina el vault y el salt."""
    if VAULT_FILE.exists():
        VAULT_FILE.unlink()
    if SALT_FILE.exists():
        SALT_FILE.unlink()
