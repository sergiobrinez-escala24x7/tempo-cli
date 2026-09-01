#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  Tempo CLI — Registrar actividades del calendario del DÍA ANTERIOR
#  Haz doble click para registrar automáticamente en Tempo
#  las actividades del día anterior que coincidan con alias configurados.
# ═══════════════════════════════════════════════════════════════

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

export PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH"

# Python del venv donde está instalado tempo-cli
PYTHON="$HOME/Library/Application Support/pipx/venvs/tempo-cli/bin/python"

clear
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}     📅 Tempo CLI — Registrar Calendario (día anterior)${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""

# --- Verificar que tempo esté instalado ---
if ! command -v tempo &>/dev/null; then
    echo -e "  ${RED}✗ Tempo CLI no está instalado.${NC}"
    echo ""
    echo -e "  ${BOLD}¿Qué es Tempo CLI?${NC}"
    echo -e "  Es una herramienta de línea de comandos para registrar tiempo"
    echo -e "  de trabajo en Tempo/Jira directamente desde tu terminal."
    echo ""
    echo -e "  ${BOLD}Para instalar:${NC}"
    echo -e "    Ejecuta ${CYAN}install.command${NC} desde el directorio del proyecto."
    echo ""
    echo -e "${YELLOW}  Presiona ENTER para cerrar...${NC}"
    read -r
    exit 1
fi

# --- Verificar que las credenciales base estén configuradas ---
"$PYTHON" -c "
from tempo_cli.vault import vault_exists
if not vault_exists():
    exit(1)
" 2>/dev/null || {
    echo ""
    echo -e "  ${RED}✗ No hay credenciales configuradas en Tempo CLI.${NC}"
    echo ""
    echo -e "${BLUE}───────────────────────────────────────────────────────────${NC}"
    echo -e "  ${BOLD}¿Qué es Tempo CLI?${NC}"
    echo -e "  Una herramienta de terminal para registrar horas de trabajo"
    echo -e "  en Tempo/Jira. Automatiza la carga del tiempo usando tu"
    echo -e "  calendario de Google como fuente de eventos."
    echo -e "${BLUE}───────────────────────────────────────────────────────────${NC}"
    echo ""
    echo -e "  ${BOLD}Para autenticarte necesitas tener a mano:${NC}"
    echo ""
    echo -e "    ${CYAN}1.${NC} Tempo API Token"
    echo -e "       → Tempo > Settings > API Integration > Crear token"
    echo ""
    echo -e "    ${CYAN}2.${NC} Atlassian Account ID"
    echo -e "       → https://tu-empresa.atlassian.net/rest/api/3/myself"
    echo -e "       → Copia el campo \"accountId\""
    echo ""
    echo -e "    ${CYAN}3.${NC} OAuth Client ID + Secret (Atlassian Developer Console)"
    echo -e "       → developer.atlassian.com > Tu app > Settings"
    echo ""
    echo -e "  ${BOLD}Ejecuta en tu terminal:${NC}"
    echo -e "    ${CYAN}tempo auth setup${NC}"
    echo ""
    echo -e "${BLUE}───────────────────────────────────────────────────────────${NC}"
    echo -e "  ${BOLD}Otras formas de usar Tempo CLI:${NC}"
    echo ""
    echo -e "  • Directamente en terminal (fuera de esta ventana):"
    echo -e "      ${CYAN}tempo log meetings 1 \"Daily standup\" --date yesterday${NC}"
    echo -e "      ${CYAN}tempo status --week${NC}"
    echo ""
    echo -e "  • Con Kiro IDE: en una sesión de chat, pídele a Kiro que"
    echo -e "    aprenda a usar tempo-cli para asistirte con la carga"
    echo -e "    del tiempo. Kiro puede ejecutar comandos de Tempo por ti."
    echo -e "${BLUE}───────────────────────────────────────────────────────────${NC}"
    echo ""
    echo -e "${YELLOW}  Presiona ENTER para cerrar...${NC}"
    read -r
    exit 1
}

# --- Verificar que Google Calendar esté configurado ---
"$PYTHON" -c "
from tempo_cli.config import gcal_is_configured
if not gcal_is_configured():
    print('NOT_CONFIGURED')
    exit(1)
" 2>/dev/null || {
    echo -e "  ${YELLOW}⚠ Google Calendar no está configurado.${NC}"
    echo ""
    echo -e "  Para vincular tu calendario necesitas:"
    echo -e "    ${CYAN}1.${NC} URL del Web App de Apps Script (desplegado)"
    echo -e "    ${CYAN}2.${NC} API Key configurada en Script Properties"
    echo ""
    echo -e "  ${BOLD}Ejecuta:${NC} ${CYAN}tempo calendar login${NC}"
    echo ""
    echo -e "${YELLOW}  Presiona ENTER para cerrar...${NC}"
    read -r
    exit 1
}

# --- Ejecutar el script principal ---
"$PYTHON" << 'PYTHON_SCRIPT'
"""Registra en Tempo las actividades del calendario del DÍA ANTERIOR que coincidan con alias."""

import sys
from datetime import date, timedelta

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from tempo_cli.config import (
    get_gcal_config,
    load_config,
)
from tempo_cli.gcal_client import GoogleCalendarClient

console = Console()

# ═══════════════════════════════════════════════════════════════
# Eventos a excluir (no laborales)
# ═══════════════════════════════════════════════════════════════

NON_WORK_PATTERNS = [
    "lunch", "almuerzo", "comida", "descanso", "break",
    "gym", "gimnasio", "doctor", "dentista", "personal",
]


def is_non_work_event(title: str) -> bool:
    """Determina si un evento no es laboral basándose en su título."""
    title_lower = title.lower().strip()
    for pattern in NON_WORK_PATTERNS:
        if pattern in title_lower:
            return True
    return False


# ═══════════════════════════════════════════════════════════════
# Mapeo de eventos a alias
# ═══════════════════════════════════════════════════════════════


def find_matching_alias(event_title: str, config: dict) -> tuple[str, str, str] | None:
    """Intenta mapear el título de un evento a un alias configurado.

    Busca coincidencia exacta o parcial (el título del evento contiene el alias
    o el alias contiene el título del evento).

    Returns:
        Tupla (alias, issue_key, description) o None si no hay match.
    """
    title_lower = event_title.lower().strip()
    frequent_issues = config.get("frequent_issues", [])

    # 1. Match exacto por alias
    for issue in frequent_issues:
        alias = issue.get("alias", "")
        if alias.lower() == title_lower:
            return alias, issue["key"], issue.get("description", alias)

    # 2. Match parcial: el título contiene el alias
    for issue in frequent_issues:
        alias = issue.get("alias", "")
        if alias.lower() in title_lower:
            return alias, issue["key"], issue.get("description", alias)

    # 3. Match parcial: el alias contiene el título
    for issue in frequent_issues:
        alias = issue.get("alias", "")
        if title_lower in alias.lower() and len(title_lower) > 3:
            return alias, issue["key"], issue.get("description", alias)

    # 4. Match por key de issue en el título (ej: "INT-83 blah", "algo PRCL-103 algo")
    import re
    # Buscar issue keys en cualquier posición del título (case-insensitive)
    key_matches = re.findall(r'([A-Za-z]+-\d+)', event_title.strip())
    for found_key in key_matches:
        found_key_upper = found_key.upper()
        for issue in frequent_issues:
            if issue.get("key") == found_key_upper:
                return issue.get("alias", found_key_upper), issue["key"], issue.get("description", "")

    # 5. Si el título contiene un issue key que no está en frequent_issues,
    #    devolver el key directamente para que se resuelva vía Jira
    if key_matches:
        return key_matches[0].upper(), key_matches[0].upper(), event_title.strip()

    return None


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════


def main():
    # DÍA ANTERIOR a la ejecución
    target_day = date.today() - timedelta(days=1)
    config = load_config()

    console.print(f"  Fecha (día anterior): [bold]{target_day.isoformat()}[/bold]")
    console.print(f"  Consultando Google Calendar...\n")

    # Obtener eventos
    gcal_cfg = get_gcal_config()
    gcal = GoogleCalendarClient(gcal_cfg["script_url"], gcal_cfg["api_key"])

    try:
        events = gcal.get_events(target_day, target_day)
    except Exception as e:
        console.print(f"[red]Error al consultar calendario: {e}[/red]")
        sys.exit(1)

    if not events:
        console.print("[yellow]No hay eventos en el calendario para el día anterior.[/yellow]")
        sys.exit(0)

    # Clasificar eventos
    mapped = []       # (evento, alias, issue_key, description)
    unmapped = []     # eventos sin match
    skipped = []      # eventos no laborales

    for ev in events:
        title = ev.get("title", "")

        if is_non_work_event(title):
            skipped.append(ev)
            continue

        match = find_matching_alias(title, config)
        if match:
            alias, issue_key, _ = match
            # Siempre usar el título del evento del calendario como descripción
            mapped.append((ev, alias, issue_key, title.strip()))
        else:
            unmapped.append(ev)

    # ═══════════════════════════════════════════════════════════
    # Validar issue keys detectados vía Jira antes de mostrar
    # ═══════════════════════════════════════════════════════════

    console.print("  Validando issue keys detectados...\n")

    from tempo_cli.config import get_jira_config, save_oauth_tokens
    from tempo_cli.jira_client import JiraClient
    from tempo_cli.oauth import refresh_access_token
    import requests as req

    jira_cfg = get_jira_config()
    jira = JiraClient(jira_cfg["cloud_id"], jira_cfg["access_token"])

    # Verificar token y refrescar si expiró
    test = req.get(
        f"https://api.atlassian.com/ex/jira/{jira_cfg['cloud_id']}/rest/api/3/myself",
        headers={"Authorization": f"Bearer {jira_cfg['access_token']}"},
    )
    if test.status_code == 401:
        try:
            tokens = refresh_access_token(
                jira_cfg["client_id"], jira_cfg["client_secret"], jira_cfg["refresh_token"]
            )
            save_oauth_tokens(tokens["access_token"], tokens["refresh_token"], jira_cfg["cloud_id"])
            jira = JiraClient(jira_cfg["cloud_id"], tokens["access_token"])
        except Exception as e:
            console.print(f"[red]Error al renovar token de Jira: {e}[/red]")
            console.print("[yellow]Ejecuta 'tempo auth login' para re-autorizar.[/yellow]")
            sys.exit(1)

    # Validar cada issue key mapeado
    validated = []
    invalid = []
    for ev, alias, issue_key, description in mapped:
        try:
            jira.get_issue_id(issue_key)
            validated.append((ev, alias, issue_key, description))
        except Exception:
            console.print(f"  [red]✗[/red] Issue '{issue_key}' no accesible — evento \"{ev.get('title', '?')[:30]}\" movido a no mapeados")
            unmapped.append(ev)

    mapped = validated

    # ═══════════════════════════════════════════════════════════
    # Verificar duplicados: no registrar lo que ya existe ese día
    # ═══════════════════════════════════════════════════════════

    from tempo_cli.client import TempoClient
    from tempo_cli.config import get_account_id, get_tempo_base_url, get_tempo_token

    tempo = TempoClient(get_tempo_base_url(), get_tempo_token())
    account_id = get_account_id()

    existing_worklogs = tempo.get_worklogs(account_id, target_day, target_day)

    # Construir set de (issue_id, start_time, seconds) ya registrados
    existing_set = set()
    for wl in existing_worklogs:
        wl_issue_id = wl.get("issue", {}).get("id")
        wl_start = wl.get("startTime", "")[:5]  # HH:MM
        wl_seconds = wl.get("timeSpentSeconds", 0)
        if wl_issue_id:
            existing_set.add((int(wl_issue_id), wl_start, wl_seconds))

    # Filtrar eventos que ya están registrados
    deduplicated = []
    already_logged = []
    for ev, alias, issue_key, description in mapped:
        hours = ev.get("duration_hours", 0)
        start_time = ev.get("start_time", "09:00:00")[:5]
        seconds = int(hours * 3600)

        try:
            issue_id = jira.get_issue_id(issue_key)
        except Exception:
            deduplicated.append((ev, alias, issue_key, description))
            continue

        if (issue_id, start_time, seconds) in existing_set:
            already_logged.append((ev, alias, issue_key, description))
        else:
            deduplicated.append((ev, alias, issue_key, description))

    if already_logged:
        console.print(f"  [dim]Ya registrados ese día (omitidos): {len(already_logged)}[/dim]")
        for ev, alias, issue_key, desc in already_logged:
            hours = ev.get("duration_hours", 0)
            start_time = ev.get("start_time", "—")[:5]
            console.print(f"    [dim]⏭ {issue_key}  {hours:.2f}h  {start_time}  {desc[:30]}[/dim]")
        console.print()

    mapped = deduplicated

    # Filtrar eventos unmapped que ya están registrados (por start_time + duración)
    # Esto cubre eventos que se ingresaron manualmente en ejecuciones anteriores
    unmapped_filtered = []
    for ev in unmapped:
        hours = ev.get("duration_hours", 0)
        start_time = ev.get("start_time", "09:00:00")[:5]
        seconds = int(hours * 3600)

        # Buscar si hay algún worklog con la misma hora de inicio y duración
        already_exists = False
        for wl in existing_worklogs:
            wl_start = wl.get("startTime", "")[:5]
            wl_seconds = wl.get("timeSpentSeconds", 0)
            if wl_start == start_time and wl_seconds == seconds:
                already_exists = True
                break

        if already_exists:
            already_logged.append((ev, "—", "—", ev.get("title", "")))
        else:
            unmapped_filtered.append(ev)

    unmapped = unmapped_filtered

    # ═══════════════════════════════════════════════════════════
    # Mostrar resumen antes de ejecutar
    # ═══════════════════════════════════════════════════════════

    if mapped:
        table = Table(
            title="✅ Actividades a registrar",
            show_header=True,
            header_style="bold green",
        )
        table.add_column("#", justify="right", style="bold")
        table.add_column("Evento")
        table.add_column("Issue")
        table.add_column("Horas", justify="right")
        table.add_column("Inicio")

        total_hours = 0.0
        for i, (ev, alias, issue_key, desc) in enumerate(mapped, 1):
            hours = ev.get("duration_hours", 0)
            total_hours += hours
            table.add_row(
                str(i),
                ev.get("title", "—")[:35],
                issue_key,
                f"{hours:.2f}h",
                ev.get("start_time", "—")[:5],
            )

        console.print(table)
        console.print(f"  Total a registrar: [bold]{total_hours:.2f}h[/bold]\n")

    if unmapped:
        table = Table(
            title="⚠️  No se pudieron mapear",
            show_header=True,
            header_style="bold yellow",
        )
        table.add_column("#", justify="right", style="bold")
        table.add_column("Evento")
        table.add_column("Horas", justify="right")
        table.add_column("Inicio")

        for i, ev in enumerate(unmapped, 1):
            title = ev.get("title", "—")
            hours = ev.get("duration_hours", 0)
            table.add_row(
                str(i),
                title[:35],
                f"{hours:.2f}h",
                ev.get("start_time", "—")[:5],
            )

        console.print(table)
        console.print()

        # Preguntar por cada evento no mapeado
        console.print("[bold cyan]¿Deseas asignar un issue key a los eventos no mapeados?[/bold cyan]")
        console.print("[dim]  Ingresa el issue key (ej: PRCL-103) o un alias del config.[/dim]")
        console.print("[dim]  Deja vacío o escribe 'skip' para omitir un evento.[/dim]\n")

        import click as click_mod
        try:
            tty_input = open("/dev/tty", "r")
            sys.stdin = tty_input
        except OSError:
            pass

        from tempo_cli.config import resolve_alias

        # Preparar cliente Jira para validar issue keys
        from tempo_cli.config import get_jira_config, save_oauth_tokens
        from tempo_cli.jira_client import JiraClient
        from tempo_cli.oauth import refresh_access_token
        import requests as req

        jira_cfg = get_jira_config()
        jira = JiraClient(jira_cfg["cloud_id"], jira_cfg["access_token"])

        # Verificar token y refrescar si expiró
        test = req.get(
            f"https://api.atlassian.com/ex/jira/{jira_cfg['cloud_id']}/rest/api/3/myself",
            headers={"Authorization": f"Bearer {jira_cfg['access_token']}"},
        )
        if test.status_code == 401:
            tokens = refresh_access_token(
                jira_cfg["client_id"], jira_cfg["client_secret"], jira_cfg["refresh_token"]
            )
            save_oauth_tokens(tokens["access_token"], tokens["refresh_token"], jira_cfg["cloud_id"])
            jira = JiraClient(jira_cfg["cloud_id"], tokens["access_token"])

        resolved_unmapped = []
        for i, ev in enumerate(unmapped, 1):
            title = ev.get("title", "—")
            hours = ev.get("duration_hours", 0)
            start_time_str = ev.get("start_time", "—")[:5]

            prompt_text = f"  [{i}] \"{title}\" ({hours:.2f}h, {start_time_str}) → Issue key o alias"
            try:
                user_input = click_mod.prompt(prompt_text, default="skip", show_default=True)
            except (click_mod.exceptions.Abort, EOFError):
                user_input = "skip"

            user_input = user_input.strip()
            if not user_input or user_input.lower() == "skip":
                console.print(f"      [dim]Omitido[/dim]")
                continue

            # Resolver como alias o usar directamente como issue key
            resolved_key, resolved_desc, resolved_attrs = resolve_alias(config, user_input)

            # Si resolve_alias devolvió el mismo input, no encontró alias exacto.
            # Intentar match parcial: buscar alias que contengan el input.
            if resolved_key == user_input:
                input_lower = user_input.lower()
                matches = []
                for issue in config.get("frequent_issues", []):
                    alias_val = issue.get("alias", "")
                    if input_lower in alias_val.lower() or alias_val.lower() in input_lower:
                        matches.append(issue)

                if len(matches) == 1:
                    # Match único — usar directamente
                    resolved_key = matches[0]["key"]
                    resolved_desc = matches[0].get("description", matches[0].get("alias", ""))
                    resolved_attrs = matches[0].get("attributes")
                elif len(matches) > 1:
                    # Múltiples matches — mostrar opciones
                    console.print(f"      [yellow]Múltiples coincidencias para '{user_input}':[/yellow]")
                    for idx, m in enumerate(matches, 1):
                        console.print(f"        {idx}) [{m['key']}] {m.get('alias', '')}")
                    try:
                        choice = click_mod.prompt("      Elige una opción", type=int)
                        if 1 <= choice <= len(matches):
                            selected = matches[choice - 1]
                            resolved_key = selected["key"]
                            resolved_desc = selected.get("description", selected.get("alias", ""))
                            resolved_attrs = selected.get("attributes")
                        else:
                            console.print(f"      [dim]Opción inválida. Omitido.[/dim]")
                            continue
                    except (click_mod.exceptions.Abort, EOFError, ValueError):
                        console.print(f"      [dim]Omitido[/dim]")
                        continue

            description = ev.get("title", "").strip()

            # Validar que el issue key sea accesible vía Jira
            try:
                issue_id = jira.get_issue_id(resolved_key)
                summary = jira.get_issue_summary(resolved_key)
                console.print(f"      [green]✓ {resolved_key} — {summary}[/green]")
                resolved_unmapped.append((ev, user_input, resolved_key, description))
            except Exception as e:
                console.print(f"      [red]✗ No se pudo acceder a '{resolved_key}': {e}[/red]")
                console.print(f"      [dim]Evento omitido. Verifica que el issue exista y tengas acceso.[/dim]")

        sys.stdin = sys.__stdin__
        console.print()

        # Agregar los resueltos manualmente a la lista de mapped
        mapped.extend(resolved_unmapped)

    if skipped:
        console.print(f"  [dim]Eventos no laborales omitidos: {len(skipped)} ({', '.join(e.get('title', '?') for e in skipped)})[/dim]\n")

    if not mapped:
        console.print("[yellow]No hay actividades nuevas para registrar.[/yellow]")

        # Aún así verificar si faltan horas
        hours_per_day = float(config.get("defaults", {}).get("hours_per_day", 8))
        all_worklogs = tempo.get_worklogs(account_id, target_day, target_day)
        total_day = sum(wl.get("timeSpentSeconds", 0) for wl in all_worklogs) / 3600
        remaining = hours_per_day - total_day

        if remaining > 0.1:
            console.print(f"\n[yellow]⚠️  Faltan {remaining:.2f}h para completar las {hours_per_day:.0f}h del día {target_day.isoformat()}.[/yellow]")
            console.print(f"  Total registrado: [bold]{total_day:.2f}h[/bold] / {hours_per_day:.0f}h\n")

            import click as click_end
            try:
                tty_end = open("/dev/tty", "r")
                sys.stdin = tty_end
                launch_kiro = click_end.confirm("  ¿Deseas que Kiro CLI te asista con las horas restantes?", default=True)
            except (OSError, click_end.exceptions.Abort):
                launch_kiro = False
            finally:
                sys.stdin = sys.__stdin__

            if launch_kiro:
                with open("/tmp/tempo_remaining_hours.txt", "w") as f:
                    f.write(f"{remaining:.2f}|{target_day.isoformat()}")
            else:
                console.print(f"  [dim]Puedes completar las horas después con: tempo log <alias> <horas> --date {target_day.isoformat()}[/dim]")
        else:
            console.print(f"\n[green]✓ Día completo: {total_day:.2f}h / {hours_per_day:.0f}h[/green]")

        sys.exit(0)

    # ═══════════════════════════════════════════════════════════
    # Confirmar y registrar
    # ═══════════════════════════════════════════════════════════

    import click
    try:
        # Abrir TTY directamente porque stdin está ocupado por el heredoc
        tty = open("/dev/tty", "r")
        sys.stdin = tty
        proceed = click.confirm("¿Registrar estas actividades en Tempo?", default=True)
    except (OSError, click.exceptions.Abort):
        proceed = False
    finally:
        sys.stdin = sys.__stdin__

    if not proceed:
        console.print("[yellow]Cancelado.[/yellow]")
        sys.exit(0)

    console.print()

    # Registrar worklogs
    from tempo_cli.config import resolve_alias

    success_count = 0
    error_count = 0
    total_registered = 0.0

    for ev, alias, issue_key, description in mapped:
        hours = ev.get("duration_hours", 0)
        start_time = ev.get("start_time", "09:00:00")
        if len(start_time) == 5:
            start_time += ":00"

        # Resolver issue_key → issue_id
        # Usar resolve_alias para obtener los attributes del config
        _, _, config_attributes = resolve_alias(config, alias)

        try:
            # Obtener issue ID vía Jira
            from tempo_cli.config import get_jira_config, save_oauth_tokens
            from tempo_cli.oauth import refresh_access_token

            jira_cfg = get_jira_config()
            jira = JiraClient(jira_cfg["cloud_id"], jira_cfg["access_token"])

            import requests as req
            test = req.get(
                f"https://api.atlassian.com/ex/jira/{jira_cfg['cloud_id']}/rest/api/3/myself",
                headers={"Authorization": f"Bearer {jira_cfg['access_token']}"},
            )
            if test.status_code == 401:
                tokens = refresh_access_token(
                    jira_cfg["client_id"], jira_cfg["client_secret"], jira_cfg["refresh_token"]
                )
                save_oauth_tokens(tokens["access_token"], tokens["refresh_token"], jira_cfg["cloud_id"])
                jira = JiraClient(jira_cfg["cloud_id"], tokens["access_token"])

            issue_id = jira.get_issue_id(issue_key)

            # Resolver atributos obligatorios
            attributes = None
            required_attrs = tempo.get_required_work_attributes()
            if required_attrs:
                attributes = []
                for attr in required_attrs:
                    if attr.get("type") == "ACCOUNT":
                        account_value = tempo.get_issue_account(issue_id)
                        if account_value:
                            attributes.append({"key": attr["key"], "value": account_value})
                        elif config_attributes and attr["key"] in config_attributes:
                            attributes.append({"key": attr["key"], "value": config_attributes[attr["key"]]})
                if not attributes:
                    attributes = None

            # Crear worklog
            tempo.create_worklog(
                issue_id=issue_id,
                time_spent_seconds=int(hours * 3600),
                start_date=target_day,
                author_account_id=account_id,
                start_time=start_time,
                description=description,
                attributes=attributes,
            )
            console.print(
                f"  [green]✓[/green] {issue_key}  {hours:.2f}h  {start_time[:5]}  {description[:40]}"
            )
            success_count += 1
            total_registered += hours

        except Exception as e:
            console.print(f"  [red]✗[/red] {issue_key}  {hours:.2f}h  Error: {e}")
            error_count += 1

    # Resumen final
    console.print()
    if error_count == 0:
        console.print(f"[green]✓ {success_count} worklog(s) registrados exitosamente.[/green]")
    else:
        console.print(
            f"[yellow]Resultado: {success_count} exitosos, {error_count} con error.[/yellow]"
        )

    # Verificar si faltan horas para completar el día
    hours_per_day = float(config.get("defaults", {}).get("hours_per_day", 8))
    # Consultar total real registrado ese día (existentes + recién creados)
    all_worklogs = tempo.get_worklogs(account_id, target_day, target_day)
    total_day = sum(wl.get("timeSpentSeconds", 0) for wl in all_worklogs) / 3600
    remaining = hours_per_day - total_day

    if remaining > 0.1:
        console.print(f"\n[yellow]⚠️  Faltan {remaining:.2f}h para completar las {hours_per_day:.0f}h del día {target_day.isoformat()}.[/yellow]")
        console.print(f"  Total registrado: [bold]{total_day:.2f}h[/bold] / {hours_per_day:.0f}h\n")

        # Preguntar si quiere asistencia de Kiro CLI
        import click as click_final
        try:
            tty_final = open("/dev/tty", "r")
            sys.stdin = tty_final
            launch_kiro = click_final.confirm("  ¿Deseas que Kiro CLI te asista con las horas restantes?", default=True)
        except (OSError, click_final.exceptions.Abort):
            launch_kiro = False
        finally:
            sys.stdin = sys.__stdin__

        if launch_kiro:
            with open("/tmp/tempo_remaining_hours.txt", "w") as f:
                f.write(f"{remaining:.2f}|{target_day.isoformat()}")
        else:
            console.print(f"  [dim]Puedes completar las horas después con: tempo log <alias> <horas> --date {target_day.isoformat()}[/dim]")
    else:
        console.print(f"\n[green]✓ Día completo: {total_day:.2f}h / {hours_per_day:.0f}h[/green]")


if __name__ == "__main__":
    main()
PYTHON_SCRIPT

# --- Resultado final ---
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""

# --- Si faltan horas, lanzar kiro-cli con agente tempo ---
if [ -f /tmp/tempo_remaining_hours.txt ]; then
    REMAINING=$(cat /tmp/tempo_remaining_hours.txt | cut -d'|' -f1)
    TARGET_DATE=$(cat /tmp/tempo_remaining_hours.txt | cut -d'|' -f2)
    rm -f /tmp/tempo_remaining_hours.txt

    echo -e "${CYAN}  Iniciando Kiro CLI (agente tempo) para completar ${REMAINING}h restantes del ${TARGET_DATE}...${NC}"
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo ""

    kiro-cli chat --agent tempo "El día de trabajo a completar es ${TARGET_DATE} (día anterior a hoy). Ya registré actividades del calendario pero faltan ${REMAINING}h para completar 8h en esa fecha. Ayúdame a decidir qué registrar en las horas restantes. Primero muestra el status con 'tempo status --date ${TARGET_DATE}' y luego sugiere opciones basándote en los alias disponibles. Usa --date ${TARGET_DATE} en los comandos tempo log."
else
    echo -e "${YELLOW}  Presiona ENTER para cerrar...${NC}"
    read -r
fi
