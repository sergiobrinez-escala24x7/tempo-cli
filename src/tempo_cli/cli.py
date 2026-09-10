"""Definición de comandos Click para Tempo CLI."""

from __future__ import annotations

import getpass
from datetime import date as date_type

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from tempo_cli.config import load_config
from tempo_cli.vault import (
    REQUIRED_FIELDS,
    delete_vault,
    encrypt_credentials,
    vault_exists,
)

console = Console()


def _get_client():
    """Crea un cliente Tempo autenticado."""
    from tempo_cli.client import TempoClient
    from tempo_cli.config import get_tempo_base_url, get_tempo_token

    return TempoClient(get_tempo_base_url(), get_tempo_token())


def _get_account_id() -> str:
    from tempo_cli.config import get_account_id

    return get_account_id()


def _get_jira_client():
    """Crea un cliente Jira usando OAuth 2.0. Renueva el token si expiró.

    Si el refresh_token también expiró pero el client_id y client_secret
    siguen siendo válidos, lanza automáticamente el flujo OAuth (abre navegador)
    para re-autorizar sin necesidad de ejecutar 'tempo auth setup' completo.
    """
    from tempo_cli.config import get_jira_config, save_oauth_tokens
    from tempo_cli.jira_client import JiraClient
    from tempo_cli.oauth import (
        exchange_code_for_tokens,
        get_authorization_code,
        get_cloud_id,
        refresh_access_token,
    )

    jira_cfg = get_jira_config()

    if not jira_cfg.get("access_token") or not jira_cfg.get("cloud_id"):
        raise Exception(
            "OAuth no configurado. Ejecuta 'tempo auth login' para autorizar acceso a Jira."
        )

    # Intentar usar el access_token actual
    client = JiraClient(jira_cfg["cloud_id"], jira_cfg["access_token"])

    # Verificar si funciona con una llamada ligera
    import requests
    test = requests.get(
        f"https://api.atlassian.com/ex/jira/{jira_cfg['cloud_id']}/rest/api/3/myself",
        headers={"Authorization": f"Bearer {jira_cfg['access_token']}"},
    )

    if test.status_code == 401:
        # Token expirado — intentar renovar con refresh_token
        try:
            tokens = refresh_access_token(
                jira_cfg["client_id"],
                jira_cfg["client_secret"],
                jira_cfg["refresh_token"],
            )
            save_oauth_tokens(
                tokens["access_token"],
                tokens["refresh_token"],
                jira_cfg["cloud_id"],
            )
            client = JiraClient(jira_cfg["cloud_id"], tokens["access_token"])
        except Exception:
            # Refresh token también expirado — re-autorizar automáticamente
            # Solo si client_id y client_secret están disponibles
            if not jira_cfg.get("client_id") or not jira_cfg.get("client_secret"):
                raise Exception(
                    "Token OAuth expirado y faltan credenciales OAuth.\n"
                    "Ejecuta 'tempo auth setup' para reconfigurar."
                )

            console.print(
                "[yellow]⚠️  Token de Jira expirado. Re-autorizando automáticamente...[/yellow]"
            )
            console.print("[dim]  Se abrirá el navegador para autorizar acceso a Jira.[/dim]")

            try:
                code = get_authorization_code(jira_cfg["client_id"])
                console.print("  [green]✓[/green] Código de autorización recibido")

                tokens = exchange_code_for_tokens(
                    jira_cfg["client_id"],
                    jira_cfg["client_secret"],
                    code,
                )
                console.print("  [green]✓[/green] Tokens renovados")

                cloud_id = get_cloud_id(tokens["access_token"])
                save_oauth_tokens(tokens["access_token"], tokens["refresh_token"], cloud_id)
                console.print("  [green]✓[/green] Autorización renovada\n")

                client = JiraClient(cloud_id, tokens["access_token"])
            except Exception as e:
                raise Exception(
                    f"No se pudo re-autorizar Jira: {e}\n"
                    "Verifica que el Client ID y Secret sigan vigentes en "
                    "Atlassian Developer Console."
                )

    return client


# Cache de issue_key → issue_id para la sesión
_issue_id_cache: dict[str, int] = {}


def _resolve_issue_id(issue_key: str) -> int:
    """Resuelve un issue key a su ID numérico usando Jira OAuth."""
    if issue_key in _issue_id_cache:
        return _issue_id_cache[issue_key]

    jira = _get_jira_client()
    issue_id = jira.get_issue_id(issue_key)
    _issue_id_cache[issue_key] = issue_id
    return issue_id


def _get_logged_hours(client, account_id: str, target: date_type) -> float:
    """Consulta las horas ya registradas en un día."""
    worklogs = client.get_worklogs(account_id, target, target)
    total_seconds = sum(wl.get("timeSpentSeconds", 0) for wl in worklogs)
    return total_seconds / 3600


def _resolve_project_key(issue_key: str) -> str | None:
    """Obtiene el project key de un issue key (ej. 'PRCL-103' → 'PRCL').

    Primero intenta extraerlo del propio issue key (prefijo antes del '-').
    Si el issue key no tiene ese formato, consulta Jira.
    """
    if "-" in issue_key:
        prefix = issue_key.rsplit("-", 1)[0]
        # Validar que la parte después del '-' sea numérica
        suffix = issue_key.rsplit("-", 1)[1]
        if prefix and suffix.isdigit():
            return prefix

    # Fallback: consultar Jira
    try:
        jira = _get_jira_client()
        return jira.get_project_key(issue_key)
    except Exception:
        return None


def _resolve_work_attributes(
    client,
    issue_id: int,
    config_attributes: dict[str, str] | None = None,
    issue_key: str | None = None,
) -> list[dict[str, str]] | None:
    """Auto-resuelve los work attributes obligatorios (ej: _Cliente_).

    Replica el comportamiento de la UI de Tempo que auto-llena el campo
    Cliente al reconocer el issue. Orden de resolución:

    1. Worklog previo del mismo issue (valor exacto ya usado antes).
    2. Cache local proyecto → cliente (aprendido de registros anteriores
       en cualquier issue del mismo proyecto).
    3. Atributos configurados en frequent_issues (fallback manual).

    Cada valor resuelto se guarda en el cache de proyecto, de modo que
    los siguientes issues del mismo proyecto se resuelven automáticamente.
    """
    from tempo_cli import client_cache

    required_attrs = client.get_required_work_attributes()
    if not required_attrs:
        return None

    project_key = _resolve_project_key(issue_key) if issue_key else None

    attributes = []
    for attr in required_attrs:
        if attr.get("type") != "ACCOUNT":
            continue

        account_value = None
        source = None
        from_local_cache = False

        # 1. Worklog previo del mismo issue (incluye los creados por la web)
        account_value = client.get_issue_account(issue_id)
        if account_value:
            source = "worklog del issue"

        # 2. Cache local proyecto → cliente (aprendido en ejecuciones previas del CLI)
        if not account_value and project_key:
            cached = client_cache.get_client_for_project(project_key)
            if cached:
                account_value = cached
                source = "cache local del proyecto"
                from_local_cache = True

        # 3. Consultar Tempo directamente: worklogs de otros issues del mismo
        #    proyecto (incluye los registrados por la web). Cubre issues nuevos
        #    en proyectos que ya tienen actividad aunque no vía CLI.
        if not account_value and project_key:
            resolved = _resolve_client_from_project_worklogs(client, project_key, attr["key"])
            if resolved:
                account_value = resolved
                source = "worklogs del proyecto en Tempo"

        # 4. Fallback: atributos del config
        if not account_value and config_attributes and attr["key"] in config_attributes:
            account_value = config_attributes[attr["key"]]
            source = "config"

        if account_value:
            attributes.append({"key": attr["key"], "value": account_value})
            # Aprender: persistir en cache local para ejecuciones futuras,
            # sin importar de qué fuente se resolvió (excepto si ya venía del cache).
            if project_key and not from_local_cache:
                client_cache.set_client_for_project(project_key, account_value)
            if source and not from_local_cache:
                console.print(f"  [dim]Cliente '{account_value}' resuelto desde {source}[/dim]")
        else:
            console.print(
                f"[yellow]⚠️  No se pudo auto-resolver el atributo '{attr['name']}' para este issue.[/yellow]\n"
                f"  No hay worklogs previos (ni en el issue ni en el proyecto) ni cache local.\n"
                f"  Puedes definirlo en 'frequent_issues[].attributes' del config.yaml."
            )

    return attributes if attributes else None


def _resolve_client_from_project_worklogs(client, project_key: str, attribute_key: str) -> str | None:
    """Busca el valor del cliente en worklogs de cualquier issue del proyecto.

    Usa Jira para descubrir issue_ids del proyecto que tienen worklogs, luego
    consulta Tempo para extraer el valor del atributo ACCOUNT. Esto captura los
    registros hechos por la web, no solo por la CLI.
    """
    try:
        jira = _get_jira_client()
        issue_ids = jira.find_issue_ids_in_project(project_key)
    except Exception:
        return None

    if not issue_ids:
        return None

    try:
        return client.find_account_by_project(issue_ids, attribute_key)
    except Exception:
        return None


@click.group()
@click.pass_context
def main(ctx):
    """Tempo CLI — Registra tiempo en Tempo/Jira desde la terminal."""
    ctx.ensure_object(dict)
    ctx.obj["config"] = load_config()


# ═══════════════════════════════════════════════════════════════
# AUTH
# ═══════════════════════════════════════════════════════════════


@main.group(invoke_without_command=True)
@click.pass_context
def auth(ctx):
    """Gestiona la autenticación y credenciales.

    \b
    Datos requeridos para 'tempo auth setup':
    ──────────────────────────────────────────
      • Tempo API Token
        → Tempo > Settings > API Integration > Crear token con permiso "Manage Worklogs"
      • Atlassian Account ID
        → Visita https://<tu-empresa>.atlassian.net/rest/api/3/myself
        → Copia el campo "accountId"
      • OAuth Client ID
        → Atlassian Developer Console > Tu app > Settings
      • OAuth Client Secret
        → Atlassian Developer Console > Tu app > Settings

    \b
    Después del setup, se abre el navegador para autorizar acceso a Jira.
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@auth.command()
def setup():
    """Configura las credenciales de forma interactiva."""
    from tempo_cli.oauth import (
        exchange_code_for_tokens,
        get_authorization_code,
        get_cloud_id,
    )

    console.print(
        Panel(
            "[bold]Configuración de autenticación[/bold]\n\n"
            "Se configurarán credenciales de Tempo y acceso a Jira (OAuth 2.0).\n"
            "Todo se cifra y queda atado a este equipo.",
            title="🔐 Tempo Auth Setup",
            border_style="blue",
        )
    )

    if vault_exists():
        overwrite = click.confirm("\n⚠️  Ya existen credenciales configuradas. ¿Sobreescribir?", default=False)
        if not overwrite:
            console.print("[yellow]Cancelado.[/yellow]")
            return

    credentials: dict[str, str] = {}

    # Credenciales de Tempo
    console.print("\n[bold cyan]1. Credenciales de Tempo:[/bold cyan]")
    for key, label in REQUIRED_FIELDS:
        if key == "TEMPO_BASE_URL":
            value = click.prompt(f"  {label}", default="https://api.tempo.io/4")
        elif "secret" in key.lower() or "token" in key.lower():
            value = getpass.getpass(f"  {label}: ")
        else:
            value = click.prompt(f"  {label}")

        if value:
            credentials[key] = value

    # Flujo OAuth con Jira
    console.print("\n[bold cyan]2. Autorización con Jira (OAuth 2.0):[/bold cyan]")
    console.print("  Se abrirá tu navegador para autorizar acceso de solo lectura a Jira.")
    console.print("  [dim]Scope: read:jira-work (solo leer issues, no puede modificar nada)[/dim]")

    proceed = click.confirm("\n  ¿Continuar con la autorización?", default=True)
    if not proceed:
        # Guardar sin OAuth
        encrypt_credentials(credentials)
        console.print("[yellow]⚠️  OAuth no configurado. No podrás crear worklogs.[/yellow]")
        return

    console.print("\n  Abriendo navegador...")

    try:
        code = get_authorization_code(credentials["OAUTH_CLIENT_ID"])
        console.print("  [green]✓[/green] Código de autorización recibido")

        tokens = exchange_code_for_tokens(
            credentials["OAUTH_CLIENT_ID"],
            credentials["OAUTH_CLIENT_SECRET"],
            code,
        )
        console.print("  [green]✓[/green] Tokens obtenidos")

        cloud_id = get_cloud_id(tokens["access_token"])
        console.print(f"  [green]✓[/green] Cloud ID: {cloud_id[:8]}...")

        # Guardar tokens OAuth junto con el resto
        credentials["OAUTH_ACCESS_TOKEN"] = tokens["access_token"]
        credentials["OAUTH_REFRESH_TOKEN"] = tokens["refresh_token"]
        credentials["OAUTH_CLOUD_ID"] = cloud_id

    except Exception as e:
        console.print(f"  [red]✗ Error en OAuth: {e}[/red]")
        console.print("  [yellow]Guardando credenciales sin OAuth. Podrás reintentar con 'tempo auth login'.[/yellow]")

    # Cifrar todo
    encrypt_credentials(credentials)

    console.print(
        Panel(
            "[bold green]✓ Credenciales cifradas y almacenadas.[/bold green]\n\n"
            f"Archivo: ~/.tempo-cli/credentials.enc\n"
            f"Campos guardados: {len(credentials)}\n\n"
            "[dim]Las credenciales solo funcionan en este equipo.[/dim]",
            title="✅ Configuración completa",
            border_style="green",
        )
    )


@auth.command(name="status")
def auth_status():
    """Muestra el estado de la autenticación."""
    if not vault_exists():
        console.print("[red]✗ No hay credenciales configuradas.[/red]")
        console.print("  Ejecuta: [bold]tempo auth setup[/bold]")
        return

    console.print("[green]✓ Vault de credenciales encontrado.[/green]")
    console.print("  Ubicación: ~/.tempo-cli/credentials.enc")

    try:
        from tempo_cli.config import load_credentials

        creds = load_credentials()
        console.print(f"  Campos almacenados: {len(creds)}")
        for key in creds:
            masked = creds[key][:3] + "•" * 8 if len(creds[key]) > 3 else "•" * 8
            console.print(f"    {key}: {masked}")
    except SystemExit as e:
        console.print(f"  [yellow]{e}[/yellow]")


@auth.command()
def reset():
    """Elimina las credenciales almacenadas (irreversible)."""
    if not vault_exists():
        console.print("[yellow]No hay credenciales que eliminar.[/yellow]")
        return

    confirm = click.confirm("⚠️  ¿Eliminar las credenciales?", default=False)
    if confirm:
        delete_vault()
        console.print("[green]✓ Credenciales eliminadas.[/green]")
    else:
        console.print("[yellow]Cancelado.[/yellow]")


@auth.command()
def login():
    """Re-autoriza el acceso a Jira (renueva tokens OAuth)."""
    from tempo_cli.config import get_jira_config, save_oauth_tokens
    from tempo_cli.oauth import exchange_code_for_tokens, get_authorization_code, get_cloud_id

    if not vault_exists():
        console.print("[red]Ejecuta 'tempo auth setup' primero.[/red]")
        return

    jira_cfg = get_jira_config()
    client_id = jira_cfg["client_id"]
    client_secret = jira_cfg["client_secret"]

    console.print("Abriendo navegador para autorizar acceso a Jira...")

    try:
        code = get_authorization_code(client_id)
        console.print("[green]✓[/green] Código recibido")

        tokens = exchange_code_for_tokens(client_id, client_secret, code)
        console.print("[green]✓[/green] Tokens obtenidos")

        cloud_id = get_cloud_id(tokens["access_token"])
        console.print(f"[green]✓[/green] Cloud ID: {cloud_id[:8]}...")

        save_oauth_tokens(tokens["access_token"], tokens["refresh_token"], cloud_id)
        console.print("[green]✓ Autorización renovada correctamente.[/green]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


# ═══════════════════════════════════════════════════════════════
# LOG
# ═══════════════════════════════════════════════════════════════


@main.command()
@click.argument("issue")
@click.argument("hours")
@click.argument("description", required=False, default=None)
@click.option("--date", "-d", default=None, help="Fecha (YYYY-MM-DD, yesterday, monday...)")
@click.option("--start", "-s", default=None, help="Hora de inicio (HH:MM)")
@click.option("--force", is_flag=True, help="Ignorar límite de horas diarias")
@click.option("--dry-run", is_flag=True, help="Mostrar qué haría sin ejecutar")
@click.pass_context
def log(ctx, issue, hours, description, date, start, force, dry_run):
    """Registra tiempo en un ticket. Soporta alias e issue keys."""
    from tempo_cli.config import get_hours_per_day, resolve_alias
    from tempo_cli.utils import day_name, is_weekend, parse_date, parse_hours

    config = ctx.obj["config"]

    # Resolver alias → issue key
    issue_key, default_desc, config_attributes = resolve_alias(config, issue)
    if description is None:
        description = default_desc

    # Parsear horas y fecha
    try:
        hours_val = parse_hours(hours)
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        return

    try:
        target_date = parse_date(date)
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        return

    # Advertir si es fin de semana
    if is_weekend(target_date) and not force:
        console.print(
            f"[yellow]⚠️  {target_date.isoformat()} es [bold]{day_name(target_date)}[/bold] (fin de semana).[/yellow]"
        )
        if not click.confirm("  ¿Seguro que quieres registrar aquí?", default=False):
            console.print("[yellow]Cancelado.[/yellow]")
            return

    # Hora de inicio
    start_time = f"{start}:00" if start else config.get("defaults", {}).get("start_time", "09:00:00")
    if len(start_time) == 5:
        start_time += ":00"

    # Validar límite de horas
    hours_per_day = get_hours_per_day(config)
    client = _get_client()
    account_id = _get_account_id()

    from tempo_cli.utils import fmt_hours

    logged = _get_logged_hours(client, account_id, target_date)
    if logged + hours_val > hours_per_day and not force:
        console.print(
            f"[red]⚠️  No se puede registrar: ya hay {fmt_hours(logged)}h registradas en {target_date.isoformat()}.[/red]\n"
            f"  Disponible: {fmt_hours(hours_per_day - logged)}h. Usa [bold]--force[/bold] para ignorar el límite."
        )
        return

    # Resolver issue key → issue id vía Jira OAuth
    try:
        issue_id = _resolve_issue_id(issue_key)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return

    # Dry run
    if dry_run:
        console.print(
            Panel(
                f"Issue: [bold]{issue_key}[/bold] (id: {issue_id})\n"
                f"Horas: {fmt_hours(hours_val)}h ({int(hours_val * 3600)}s)\n"
                f"Fecha: {target_date.isoformat()}\n"
                f"Inicio: {start_time[:5]}\n"
                f"Descripción: {description or '—'}",
                title="🔍 Dry run — no se ejecuta",
                border_style="yellow",
            )
        )
        return

    # Auto-resolver atributos obligatorios (ej: _Cliente_)
    attributes = _resolve_work_attributes(client, issue_id, config_attributes, issue_key)

    # Crear worklog con Tempo API v4
    try:
        client.create_worklog(
            issue_id=issue_id,
            time_spent_seconds=int(hours_val * 3600),
            start_date=target_date,
            author_account_id=account_id,
            start_time=start_time,
            description=description,
            attributes=attributes,
        )
        console.print(
            f"[green]✓[/green] {issue_key}  {fmt_hours(hours_val)}h  {start_time[:5]}  {description or '—'}"
        )
        new_total = logged + hours_val
        if new_total >= hours_per_day:
            console.print(f"  Total del día: {fmt_hours(new_total)}h / {hours_per_day:.0f}h [green]✓[/green]")
        else:
            console.print(f"  Total del día: {fmt_hours(new_total)}h / {hours_per_day:.0f}h (faltan {fmt_hours(hours_per_day - new_total)}h)")
    except Exception as e:
        console.print(f"[red]Error al crear worklog: {e}[/red]")


# ═══════════════════════════════════════════════════════════════
# FILL
# ═══════════════════════════════════════════════════════════════


@main.command()
@click.option("--date", "-d", default=None, help="Fecha específica (YYYY-MM-DD)")
@click.option("--template", "-t", default=None, help="Nombre del template a usar")
@click.option("--from", "from_date", default=None, help="Fecha inicio del rango")
@click.option("--to", "to_date", default=None, help="Fecha fin del rango")
@click.option("--week", "-w", is_flag=True, help="Llenar semana actual (lun-vie)")
@click.option("--force", is_flag=True, help="Ignorar límite de horas diarias")
@click.option("--dry-run", is_flag=True, help="Mostrar qué haría sin ejecutar")
@click.pass_context
def fill(ctx, date, template, from_date, to_date, week, force, dry_run):
    """Aplica una plantilla para llenar un día o rango de fechas."""
    from datetime import timedelta

    from tempo_cli.config import get_hours_per_day, get_template, resolve_alias
    from tempo_cli.utils import fmt_hours, get_week_range, parse_date

    config = ctx.obj["config"]
    hours_per_day = get_hours_per_day(config)

    # Resolver template
    try:
        tmpl = get_template(config, template)
    except SystemExit:
        return

    # Resolver rango de fechas
    if week:
        start, end = get_week_range()
    elif from_date and to_date:
        try:
            start = parse_date(from_date)
            end = parse_date(to_date)
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            return
    else:
        try:
            target = parse_date(date)
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            return
        start = target
        end = target

    client = _get_client()
    account_id = _get_account_id()
    default_start_time = config.get("defaults", {}).get("start_time", "09:00:00")

    # Iterar por cada día del rango
    current = start
    total_created = 0
    while current <= end:
        # Saltar fines de semana
        if current.weekday() >= 5:
            current += timedelta(days=1)
            continue

        logged = _get_logged_hours(client, account_id, current)
        available = hours_per_day - logged

        if available <= 0 and not force:
            console.print(f"[yellow]⏭  {current.isoformat()} — ya tiene {fmt_hours(logged)}h registradas, omitido[/yellow]")
            current += timedelta(days=1)
            continue

        # Calcular horas del template
        template_total = sum(entry.get("hours", 0) for entry in tmpl)

        # Si no cabe, ajustar proporcionalmente
        if template_total > available and not force:
            ratio = available / template_total
            console.print(
                f"[yellow]⚠️  {current.isoformat()} — disponible {fmt_hours(available)}h, "
                f"template suma {template_total:.0f}h. Ajustando proporcionalmente.[/yellow]"
            )
        else:
            ratio = 1.0

        # Calcular hora de inicio para cada entry
        # Empezamos después de las horas ya registradas
        hour_offset = logged
        base_hour = int(default_start_time[:2])
        base_min = int(default_start_time[3:5])

        console.print(f"\n[bold]📅 {current.isoformat()}[/bold]")

        for entry in tmpl:
            issue_alias = entry.get("issue", "")
            entry_hours = entry.get("hours", 0) * ratio
            entry_desc = entry.get("description", "")

            if entry_hours <= 0:
                continue

            issue_key, _, fill_config_attributes = resolve_alias(config, issue_alias)

            # Calcular hora de inicio
            total_minutes = (base_hour * 60 + base_min) + int(hour_offset * 60)
            h = total_minutes // 60
            m = total_minutes % 60
            start_time = f"{h:02d}:{m:02d}:00"

            if dry_run:
                console.print(
                    f"  [dim](dry)[/dim] {issue_key}  {fmt_hours(entry_hours)}h  {start_time[:5]}  {entry_desc}"
                )
            else:
                try:
                    issue_id = _resolve_issue_id(issue_key)
                    attributes = _resolve_work_attributes(client, issue_id, fill_config_attributes, issue_key)
                    client.create_worklog(
                        issue_id=issue_id,
                        time_spent_seconds=int(entry_hours * 3600),
                        start_date=current,
                        author_account_id=account_id,
                        start_time=start_time,
                        description=entry_desc,
                        attributes=attributes,
                    )
                    console.print(
                        f"  [green]✓[/green] {issue_key}  {fmt_hours(entry_hours)}h  {start_time[:5]}  {entry_desc}"
                    )
                    total_created += 1
                except Exception as e:
                    console.print(f"  [red]✗ {issue_key}: {e}[/red]")

            hour_offset += entry_hours

        current += timedelta(days=1)

    if dry_run:
        console.print(f"\n[yellow]Dry run completado. No se crearon worklogs.[/yellow]")
    else:
        console.print(f"\n[green]✓ {total_created} worklog(s) creados.[/green]")


# ═══════════════════════════════════════════════════════════════
# STATUS
# ═══════════════════════════════════════════════════════════════


@main.command(name="status")
@click.option("--date", "-d", default=None, help="Fecha específica (YYYY-MM-DD)")
@click.option("--week", "-w", is_flag=True, help="Mostrar semana actual")
@click.option("--from", "from_date_opt", default=None, help="Fecha inicio del rango (YYYY-MM-DD)")
@click.option("--to", "to_date_opt", default=None, help="Fecha fin del rango (YYYY-MM-DD)")
@click.pass_context
def status_cmd(ctx, date, week, from_date_opt, to_date_opt):
    """Muestra worklogs registrados y estado del día."""
    from tempo_cli.config import get_hours_per_day
    from tempo_cli.utils import fmt_hours, get_week_range, parse_date

    config = ctx.obj["config"]
    hours_per_day = get_hours_per_day(config)

    if from_date_opt and to_date_opt:
        try:
            from_date = parse_date(from_date_opt)
            to_date = parse_date(to_date_opt)
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            return
    elif week:
        from_date, to_date = get_week_range()
    else:
        try:
            target = parse_date(date)
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            return
        from_date = target
        to_date = target

    client = _get_client()
    account_id = _get_account_id()

    try:
        worklogs = client.get_worklogs(account_id, from_date, to_date)
    except Exception as e:
        console.print(f"[red]Error al consultar Tempo: {e}[/red]")
        return

    if not worklogs:
        from tempo_cli.utils import day_name as _day_name
        if from_date == to_date:
            label = f"{from_date.isoformat()} ({_day_name(from_date)})"
        else:
            label = f"{from_date.isoformat()} a {to_date.isoformat()}"
        console.print(f"\n[yellow]No hay worklogs registrados para {label}[/yellow]")
        console.print(f"  Total: 0h / {hours_per_day:.0f}h ✗")
        return

    # Resolver issue IDs → keys vía Jira
    issue_id_to_key: dict[int, str] = {}
    try:
        jira = _get_jira_client()
        unique_ids = {wl.get("issue", {}).get("id") for wl in worklogs if wl.get("issue", {}).get("id")}
        for issue_id in unique_ids:
            if issue_id:
                issue_id_to_key[issue_id] = jira.get_issue_key_by_id(issue_id)
    except Exception:
        pass  # Si falla Jira, se muestra "???" como fallback

    # Agrupar por fecha
    dates: dict[str, list] = {}
    for wl in worklogs:
        d = wl.get("startDate", "")
        dates.setdefault(d, []).append(wl)

    grand_total = 0.0
    for day_str in sorted(dates.keys()):
        day_worklogs = dates[day_str]

        # Calcular nombre del día
        from tempo_cli.utils import day_name as _day_name
        try:
            day_date = date_type.fromisoformat(day_str)
            day_label = f"📅 {day_str} ({_day_name(day_date)})"
        except ValueError:
            day_label = f"📅 {day_str}"

        table = Table(title=day_label, show_header=True, header_style="bold cyan")
        table.add_column("Issue", style="bold")
        table.add_column("Horas", justify="right")
        table.add_column("Inicio")
        table.add_column("Descripción")

        total_seconds = 0
        for wl in day_worklogs:
            issue_id = wl.get("issue", {}).get("id")
            issue_key = issue_id_to_key.get(issue_id, wl.get("issue", {}).get("key", "???"))
            seconds = wl.get("timeSpentSeconds", 0)
            total_seconds += seconds
            hours_val = seconds / 3600
            start_time = wl.get("startTime", "—")
            desc = wl.get("description") or "—"

            table.add_row(
                issue_key,
                f"{fmt_hours(hours_val)}h",
                start_time[:5] if start_time and start_time != "—" else "—",
                desc[:50],
            )

        console.print(table)

        total_hours = total_seconds / 3600
        grand_total += total_hours

        if total_hours >= hours_per_day:
            console.print(f"  Total: {fmt_hours(total_hours)}h / {hours_per_day:.0f}h [green]✓[/green]\n")
        elif total_hours > 0:
            console.print(f"  Total: {fmt_hours(total_hours)}h / {hours_per_day:.0f}h [yellow]⚠️  (faltan {fmt_hours(hours_per_day - total_hours)}h)[/yellow]\n")
        else:
            console.print(f"  Total: 0h / {hours_per_day:.0f}h [red]✗[/red]\n")

    if week and len(dates) > 1:
        expected = len([d for d in dates]) * hours_per_day
        console.print(f"[bold]Semana: {fmt_hours(grand_total)}h / {expected:.0f}h[/bold]")


# ═══════════════════════════════════════════════════════════════
# CALENDAR (grupo: Tempo Plans + Google Calendar)
# ═══════════════════════════════════════════════════════════════


@main.group(invoke_without_command=True)
@click.option("--date", "-d", default=None, help="Fecha específica (YYYY-MM-DD)")
@click.pass_context
def calendar(ctx, date):
    """Gestiona calendario: muestra planes de Tempo o eventos de Google Calendar.

    \b
    Sin subcomando muestra los planes de Tempo del día.
    Subcomandos disponibles:
      login   — Configura acceso a Google Calendar (Apps Script)
      logout  — Elimina credenciales de Google Calendar
      status  — Muestra estado de la integración con Google Calendar
      events  — Muestra eventos de Google Calendar
    """
    if ctx.invoked_subcommand is not None:
        return

    # Comportamiento default: mostrar planes de Tempo (backwards-compatible)
    from tempo_cli.utils import parse_date

    try:
        target = parse_date(date)
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        return

    client = _get_client()
    account_id = _get_account_id()

    try:
        plans = client.get_planned_time(account_id, target, target)
    except Exception as e:
        console.print(f"[red]Error al consultar planes en Tempo: {e}[/red]")
        return

    if not plans:
        console.print(f"\n[yellow]No hay eventos planificados para {target.isoformat()}[/yellow]")
        return

    table = Table(title=f"📅 Planes — {target.isoformat()}", show_header=True, header_style="bold cyan")
    table.add_column("#", justify="right", style="bold")
    table.add_column("Descripción")
    table.add_column("Horas", justify="right")
    table.add_column("Issue", style="bold")

    from tempo_cli.utils import fmt_hours

    total_hours = 0.0
    for i, plan in enumerate(plans, 1):
        desc = plan.get("description") or plan.get("name") or "—"
        seconds = plan.get("secondsPerDay", 0) or plan.get("totalPlannedSecondsInScope", 0)
        hours_val = seconds / 3600 if seconds else 0
        total_hours += hours_val
        issue = plan.get("planItem", {}).get("key", "") or plan.get("issueKey", "—")

        table.add_row(str(i), desc[:40], f"{fmt_hours(hours_val)}h", issue)

    console.print(table)
    console.print(f"\n  Total planificado: {fmt_hours(total_hours)}h")


@calendar.command(name="login")
def calendar_login():
    """Configura el acceso a Google Calendar (Apps Script).

    \b
    Requiere:
      • URL del Web App de Apps Script (desplegado)
      • API Key configurada en las Script Properties

    \b
    Estas credenciales se almacenan cifradas en el vault (~/.tempo-cli/credentials.enc)
    junto con las demás credenciales de Tempo/Jira.
    """
    from tempo_cli.config import gcal_is_configured, save_gcal_credentials

    console.print(
        Panel(
            "[bold]Configuración de Google Calendar[/bold]\n\n"
            "Se configurará el acceso a tu API de Google Calendar (Apps Script).\n"
            "Necesitas la URL del Web App desplegado y el API Key.\n\n"
            "[dim]Las credenciales se cifran y quedan atadas a este equipo.[/dim]",
            title="📅 Google Calendar Setup",
            border_style="blue",
        )
    )

    if not vault_exists():
        console.print("[red]⚠️  No hay vault configurado. Ejecuta 'tempo auth setup' primero.[/red]")
        return

    if gcal_is_configured():
        overwrite = click.confirm("\n⚠️  Ya hay credenciales de Google Calendar. ¿Sobreescribir?", default=False)
        if not overwrite:
            console.print("[yellow]Cancelado.[/yellow]")
            return

    console.print("\n[bold cyan]Credenciales de Google Calendar:[/bold cyan]")

    script_url = click.prompt("  URL del Web App (Apps Script)")
    api_key = getpass.getpass("  API Key: ")

    if not script_url.startswith("https://"):
        console.print("[red]Error: La URL debe comenzar con https://[/red]")
        return

    if not api_key:
        console.print("[red]Error: El API Key no puede estar vacío.[/red]")
        return

    # Verificar conexión antes de guardar
    console.print("\n  Verificando conexión...")
    try:
        from tempo_cli.gcal_client import GoogleCalendarClient

        client = GoogleCalendarClient(script_url, api_key)
        info = client.test_connection()
        console.print(f"  [green]✓[/green] Conexión exitosa")
        console.print(f"    Timezone: {info['timezone']}")
        console.print(f"    Eventos hoy: {info['events_today']}")
    except Exception as e:
        console.print(f"  [red]✗ Error de conexión: {e}[/red]")
        save_anyway = click.confirm("\n  ¿Guardar credenciales de todas formas?", default=False)
        if not save_anyway:
            console.print("[yellow]Cancelado.[/yellow]")
            return

    # Guardar
    save_gcal_credentials(script_url, api_key)
    console.print(
        Panel(
            "[bold green]✓ Google Calendar configurado.[/bold green]\n\n"
            "Ahora puedes usar:\n"
            "  • [bold]tempo calendar events[/bold] — Ver eventos del calendario\n"
            "  • [bold]tempo calendar status[/bold] — Verificar la integración",
            title="✅ Configuración completa",
            border_style="green",
        )
    )


@calendar.command(name="status")
def calendar_status():
    """Muestra el estado de la integración con Google Calendar."""
    from tempo_cli.config import gcal_is_configured

    if not gcal_is_configured():
        console.print("[yellow]Google Calendar no configurado.[/yellow]")
        console.print("  Ejecuta: [bold]tempo calendar login[/bold]")
        return

    console.print("[green]✓ Google Calendar configurado.[/green]")

    # Intentar verificar conexión
    console.print("  Verificando conexión...")
    try:
        from tempo_cli.config import get_gcal_config
        from tempo_cli.gcal_client import GoogleCalendarClient

        gcal_cfg = get_gcal_config()
        client = GoogleCalendarClient(gcal_cfg["script_url"], gcal_cfg["api_key"])
        info = client.test_connection()
        console.print(f"  [green]✓[/green] Endpoint accesible")
        console.print(f"    URL: {gcal_cfg['script_url'][:50]}...")
        console.print(f"    Timezone: {info['timezone']}")
        console.print(f"    Eventos hoy: {info['events_today']}")
    except Exception as e:
        console.print(f"  [red]✗ Error de conexión: {e}[/red]")
        console.print("  Verifica tu endpoint o ejecuta [bold]tempo calendar login[/bold] para reconfigurar.")


@calendar.command(name="events")
@click.option("--date", "-d", default=None, help="Fecha específica (YYYY-MM-DD)")
@click.option("--week", "-w", is_flag=True, help="Mostrar semana actual")
@click.pass_context
def calendar_events(ctx, date, week):
    """Muestra eventos de Google Calendar para el día o semana."""
    from tempo_cli.config import gcal_is_configured, get_gcal_config
    from tempo_cli.utils import fmt_hours
    from tempo_cli.gcal_client import GoogleCalendarClient
    from tempo_cli.utils import parse_date

    if not gcal_is_configured():
        console.print("[yellow]Google Calendar no configurado.[/yellow]")
        console.print("  Ejecuta: [bold]tempo calendar login[/bold]")
        return

    if week:
        from tempo_cli.utils import get_week_range
        from_date, to_date = get_week_range()
    else:
        try:
            target = parse_date(date)
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            return
        from_date = target
        to_date = target

    gcal_cfg = get_gcal_config()
    client = GoogleCalendarClient(gcal_cfg["script_url"], gcal_cfg["api_key"])

    try:
        events = client.get_events(from_date, to_date)
    except Exception as e:
        console.print(f"[red]Error al consultar Google Calendar: {e}[/red]")
        return

    if not events:
        label = (
            f"{from_date.isoformat()} a {to_date.isoformat()}"
            if from_date != to_date
            else from_date.isoformat()
        )
        console.print(f"\n[yellow]No hay eventos en Google Calendar para {label}[/yellow]")
        return

    # Agrupar por fecha
    by_date: dict[str, list] = {}
    for ev in events:
        d = ev.get("start_date", "")
        by_date.setdefault(d, []).append(ev)

    grand_total = 0.0
    for day_str in sorted(by_date.keys()):
        day_events = by_date[day_str]

        table = Table(
            title=f"📅 Google Calendar — {day_str}",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("#", justify="right", style="bold")
        table.add_column("Título")
        table.add_column("Inicio")
        table.add_column("Fin")
        table.add_column("Duración", justify="right")
        table.add_column("Calendario", style="dim")

        day_total = 0.0
        for i, ev in enumerate(day_events, 1):
            title = ev.get("title", "—")[:35]
            start_time = ev.get("start_time", "—")[:5]
            end_time = ev.get("end_time", "—")[:5]
            duration = ev.get("duration_hours", 0)
            cal_name = ev.get("calendar", "—")
            day_total += duration

            table.add_row(
                str(i), title, start_time, end_time, f"{duration:.2f}h", cal_name
            )

        console.print(table)
        console.print(f"  Total del día: {fmt_hours(day_total)}h\n")
        grand_total += day_total

    if from_date != to_date:
        console.print(f"[bold]Total periodo: {fmt_hours(grand_total)}h[/bold]")


@calendar.command(name="logout")
def calendar_logout():
    """Elimina las credenciales de Google Calendar."""
    from tempo_cli.config import gcal_is_configured, remove_gcal_credentials

    if not gcal_is_configured():
        console.print("[yellow]No hay credenciales de Google Calendar que eliminar.[/yellow]")
        return

    confirm = click.confirm("⚠️  ¿Eliminar credenciales de Google Calendar?", default=False)
    if confirm:
        remove_gcal_credentials()
        console.print("[green]✓ Credenciales de Google Calendar eliminadas.[/green]")
    else:
        console.print("[yellow]Cancelado.[/yellow]")


# ═══════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════


@main.group()
@click.pass_context
def config(ctx):
    """Gestiona la configuración operativa de Tempo CLI."""
    pass


@config.command()
@click.pass_context
def show(ctx):
    """Muestra la configuración actual (alias, templates, defaults)."""
    from tempo_cli.config import get_config_path

    cfg = ctx.obj["config"]
    config_path = get_config_path()

    if not cfg:
        console.print(f"[yellow]No hay configuración en {config_path}[/yellow]")
        console.print("  Ejecuta: [bold]tempo config init[/bold]")
        return

    console.print(f"[dim]Archivo: {config_path}[/dim]\n")

    # Defaults
    defaults = cfg.get("defaults", {})
    if defaults:
        console.print("[bold cyan]Defaults:[/bold cyan]")
        for k, v in defaults.items():
            console.print(f"  {k}: {v}")
        console.print()

    # Alias
    issues = cfg.get("frequent_issues", [])
    if issues:
        table = Table(title="Alias", show_header=True, header_style="bold cyan")
        table.add_column("Alias", style="bold")
        table.add_column("Issue Key")
        table.add_column("Descripción")
        table.add_column("Horas default", justify="right")

        for issue in issues:
            table.add_row(
                issue.get("alias", "—"),
                issue.get("key", "—"),
                issue.get("description", "—")[:30],
                str(issue.get("default_hours", "—")),
            )
        console.print(table)
        console.print()

    # Templates
    templates = cfg.get("templates", {})
    if templates:
        console.print("[bold cyan]Templates:[/bold cyan]")
        for name, entries in templates.items():
            total = sum(e.get("hours", 0) for e in entries)
            items = ", ".join(f"{e.get('issue')}:{e.get('hours')}h" for e in entries)
            console.print(f"  [bold]{name}[/bold] ({total:.0f}h) → {items}")


@config.command()
@click.pass_context
def init(ctx):
    """Inicializa la configuración operativa copiando el ejemplo."""
    import shutil
    from pathlib import Path

    from tempo_cli.config import CONFIG_DIR, CONFIG_FILE

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    if CONFIG_FILE.exists():
        overwrite = click.confirm(f"⚠️  Ya existe {CONFIG_FILE}. ¿Sobreescribir?", default=False)
        if not overwrite:
            console.print("[yellow]Cancelado.[/yellow]")
            return

    # Buscar el example.yaml en el paquete
    example = Path(__file__).parent.parent.parent / "config" / "example.yaml"
    if not example.exists():
        console.print("[red]No se encontró config/example.yaml en el proyecto.[/red]")
        return

    shutil.copy(example, CONFIG_FILE)
    console.print(f"[green]✓ Configuración creada en {CONFIG_FILE}[/green]")
    console.print("  Edítala con tus alias y templates.")


@config.command(name="clientes")
@click.option("--clear", is_flag=True, help="Vaciar el cache de clientes")
@click.pass_context
def config_clientes(ctx, clear):
    """Muestra o limpia el cache de proyecto → cliente aprendido."""
    from tempo_cli import client_cache

    if clear:
        cache = client_cache.list_cache()
        for project in list(cache.keys()):
            client_cache.remove_project(project)
        console.print("[green]✓ Cache de clientes vaciado.[/green]")
        return

    cache = client_cache.list_cache()
    if not cache:
        console.print("[yellow]No hay clientes cacheados todavía.[/yellow]")
        console.print("  Se aprenden automáticamente al registrar tiempo en cada proyecto.")
        return

    table = Table(title="Cache proyecto → cliente", show_header=True, header_style="bold cyan")
    table.add_column("Proyecto", style="bold")
    table.add_column("Cliente (account key)")
    for project, client_value in sorted(cache.items()):
        table.add_row(project, client_value)
    console.print(table)


main.add_command(config)


# ═══════════════════════════════════════════════════════════════
# TIMESHEET (submit / recall / approval status)
# ═══════════════════════════════════════════════════════════════


@main.group()
@click.pass_context
def timesheet(ctx):
    """Gestiona el envío y estado de aprobación de timesheets."""
    pass


def _resolve_period(from_date: str | None, to_date: str | None, week: bool) -> tuple[date_type, date_type]:
    """Resuelve el periodo de fechas para operaciones de timesheet.

    Tempo usa períodos lunes-domingo para timesheets.
    """
    from tempo_cli.utils import get_timesheet_period, parse_date

    if week:
        return get_timesheet_period()
    elif from_date and to_date:
        return parse_date(from_date), parse_date(to_date)
    elif from_date:
        # Si solo dan from, asumimos hasta hoy
        return parse_date(from_date), date_type.today()
    else:
        # Default: semana actual (lun-dom)
        return get_timesheet_period()


def _resolve_reviewer(config: dict, reviewer_input: str) -> dict[str, str] | None:
    """Resuelve un alias de reviewer a su account_id y nombre.

    Busca en la sección 'reviewers' del config por alias o account_id directo.
    Retorna dict con 'account_id' y 'name', o None si no lo encuentra.
    """
    reviewers = config.get("reviewers", [])

    # Buscar por alias
    for r in reviewers:
        if r.get("alias", "").lower() == reviewer_input.lower():
            return {"account_id": r["account_id"], "name": r.get("name", r["alias"])}

    # Buscar por account_id exacto
    for r in reviewers:
        if r.get("account_id", "") == reviewer_input:
            return {"account_id": r["account_id"], "name": r.get("name", reviewer_input)}

    # Si parece un account_id (contiene ':'), usarlo directamente
    if ":" in reviewer_input:
        return {"account_id": reviewer_input, "name": reviewer_input}

    return None


@timesheet.command(name="status")
@click.option("--from", "from_date", default=None, help="Fecha inicio del periodo (YYYY-MM-DD)")
@click.option("--to", "to_date", default=None, help="Fecha fin del periodo (YYYY-MM-DD)")
@click.option("--week", "-w", is_flag=True, help="Usar semana actual")
@click.pass_context
def timesheet_status(ctx, from_date, to_date, week):
    """Muestra el estado de aprobación del timesheet para un periodo."""
    from tempo_cli.utils import fmt_hours
    try:
        start, end = _resolve_period(from_date, to_date, week)
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        return

    client = _get_client()
    account_id = _get_account_id()

    try:
        approval = client.get_timesheet_approval(account_id, start, end)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return

    # Mostrar resultado
    period = approval.get("period", {})
    status_val = approval.get("status", {}).get("key", "UNKNOWN")
    worked_seconds = approval.get("timeSpentSeconds", 0)
    required_seconds = approval.get("requiredSeconds", 0)
    reviewer = approval.get("reviewer", {})
    reviewer_name = reviewer.get("displayName", "—") if reviewer else "—"

    status_colors = {
        "OPEN": "yellow",
        "WAITING_FOR_APPROVAL": "blue",
        "APPROVED": "green",
        "REJECTED": "red",
    }
    status_labels = {
        "OPEN": "Abierto",
        "WAITING_FOR_APPROVAL": "Enviado (esperando aprobación)",
        "APPROVED": "Aprobado",
        "REJECTED": "Rechazado",
    }

    color = status_colors.get(status_val, "white")
    label = status_labels.get(status_val, status_val)

    period_from = period.get("from", start.isoformat())
    period_to = period.get("to", end.isoformat())

    console.print(
        Panel(
            f"[bold]Periodo:[/bold] {period_from} → {period_to}\n"
            f"[bold]Estado:[/bold] [{color}]{label}[/{color}]\n"
            f"[bold]Horas trabajadas:[/bold] {fmt_hours(worked_seconds / 3600)}h\n"
            f"[bold]Horas requeridas:[/bold] {fmt_hours(required_seconds / 3600)}h\n"
            f"[bold]Revisor:[/bold] {reviewer_name}",
            title="📋 Timesheet",
            border_style=color,
        )
    )


@timesheet.command(name="submit")
@click.option("--from", "from_date", default=None, help="Fecha inicio del periodo (YYYY-MM-DD)")
@click.option("--to", "to_date", default=None, help="Fecha fin del periodo (YYYY-MM-DD)")
@click.option("--week", "-w", is_flag=True, help="Enviar semana actual")
@click.option("--reviewer", "-r", default=None, help="Alias o Account ID del revisor")
@click.option("--comment", "-c", default=None, help="Comentario para el revisor")
@click.option("--yes", "-y", is_flag=True, help="Confirmar sin preguntar")
@click.pass_context
def timesheet_submit(ctx, from_date, to_date, week, reviewer, comment, yes):
    """Envía el timesheet para aprobación (submit period).

    El revisor se puede especificar por alias (configurado en config.yaml)
    o directamente por email. Si no se indica, se usa el default_reviewer del config.
    """
    from tempo_cli.utils import fmt_hours
    try:
        start, end = _resolve_period(from_date, to_date, week)
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        return

    client = _get_client()
    account_id = _get_account_id()
    config = ctx.obj.get("config", {})

    # Resolver reviewer: argumento > default del config
    reviewer_input = reviewer or config.get("defaults", {}).get("default_reviewer")

    if not reviewer_input:
        console.print("[yellow]⚠️  No se especificó un revisor.[/yellow]")
        console.print("  Usa: [bold]--reviewer alias_o_account_id[/bold]")
        console.print("  O configura 'default_reviewer' en defaults del config.yaml.")
        return

    # Resolver alias → account_id
    reviewer_info = _resolve_reviewer(config, reviewer_input)
    if not reviewer_info:
        console.print(f"[red]No se encontró el revisor '{reviewer_input}'.[/red]")
        console.print("  Verifica los alias en la sección 'reviewers' de config.yaml,")
        console.print("  o usa un account_id directamente: --reviewer 712020:xxxx-xxxx")
        return

    reviewer_account_id = reviewer_info["account_id"]
    console.print(f"  Revisor: [bold]{reviewer_info['name']}[/bold]")

    # Mostrar resumen antes de enviar
    try:
        approval = client.get_timesheet_approval(account_id, start, end)
        current_status = approval.get("status", {}).get("key", "UNKNOWN")
        worked_seconds = approval.get("timeSpentSeconds", 0)
        required_seconds = approval.get("requiredSeconds", 0)
    except Exception:
        current_status = "UNKNOWN"
        worked_seconds = 0
        required_seconds = 0

    if current_status == "WAITING_FOR_APPROVAL":
        console.print(f"[yellow]⚠️  Este periodo ya fue enviado y está esperando aprobación.[/yellow]")
        return

    if current_status == "APPROVED":
        console.print(f"[green]✓ Este periodo ya está aprobado.[/green]")
        return

    console.print(f"\n[bold]Periodo:[/bold] {start.isoformat()} → {end.isoformat()}")
    console.print(f"[bold]Horas:[/bold] {fmt_hours(worked_seconds / 3600)}h / {fmt_hours(required_seconds / 3600)}h requeridas")

    if worked_seconds < required_seconds and not yes:
        console.print(
            f"[yellow]⚠️  Faltan {fmt_hours((required_seconds - worked_seconds) / 3600)}h para completar el periodo.[/yellow]"
        )

    if not yes:
        confirm = click.confirm("\n¿Enviar timesheet para aprobación?", default=True)
        if not confirm:
            console.print("[yellow]Cancelado.[/yellow]")
            return

    try:
        result = client.submit_timesheet(account_id, start, end, reviewer_account_id, comment)
        console.print(f"\n[green]✓ Timesheet enviado para aprobación.[/green]")
        console.print(f"  Periodo: {start.isoformat()} → {end.isoformat()}")
        if comment:
            console.print(f"  Comentario: {comment}")
    except Exception as e:
        console.print(f"[red]Error al enviar timesheet: {e}[/red]")


@timesheet.command(name="recall")
@click.option("--from", "from_date", default=None, help="Fecha inicio del periodo (YYYY-MM-DD)")
@click.option("--to", "to_date", default=None, help="Fecha fin del periodo (YYYY-MM-DD)")
@click.option("--week", "-w", is_flag=True, help="Semana actual")
@click.option("--yes", "-y", is_flag=True, help="Confirmar sin preguntar")
@click.pass_context
def timesheet_recall(ctx, from_date, to_date, week, yes):
    """Reabre un timesheet enviado (recall). Solo si no ha sido aprobado."""
    try:
        start, end = _resolve_period(from_date, to_date, week)
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        return

    client = _get_client()
    account_id = _get_account_id()

    # Verificar estado actual
    try:
        approval = client.get_timesheet_approval(account_id, start, end)
        current_status = approval.get("status", {}).get("key", "UNKNOWN")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return

    if current_status == "OPEN":
        console.print("[yellow]Este periodo ya está abierto, no necesita recall.[/yellow]")
        return

    if current_status == "APPROVED":
        console.print("[red]⚠️  Este periodo ya fue aprobado. No se puede reabrir.[/red]")
        return

    console.print(f"\n[bold]Periodo:[/bold] {start.isoformat()} → {end.isoformat()}")
    console.print(f"[bold]Estado actual:[/bold] {current_status}")

    if not yes:
        confirm = click.confirm("\n¿Reabrir (recall) este timesheet?", default=False)
        if not confirm:
            console.print("[yellow]Cancelado.[/yellow]")
            return

    try:
        client.recall_timesheet(account_id, start, end)
        console.print(f"\n[green]✓ Timesheet reabierto.[/green]")
        console.print(f"  Periodo: {start.isoformat()} → {end.isoformat()}")
        console.print("  Ahora puedes editar worklogs y volver a enviarlo.")
    except Exception as e:
        console.print(f"[red]Error al reabrir timesheet: {e}[/red]")


main.add_command(timesheet)


if __name__ == "__main__":
    main()
