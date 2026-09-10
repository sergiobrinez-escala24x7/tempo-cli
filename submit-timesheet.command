#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  Tempo CLI — Enviar Timesheet de la semana actual
#  Haz doble click para ver el resumen semanal y enviar a aprobación
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
echo -e "${BOLD}        📋 Tempo CLI — Enviar Timesheet Semanal${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""

# --- Verificar que tempo esté instalado ---
if ! command -v tempo &>/dev/null; then
    echo -e "  ${RED}✗ Tempo CLI no está instalado.${NC}"
    echo -e "  Ejecuta primero ${BOLD}install.command${NC} para instalar."
    echo ""
    echo -e "${YELLOW}  Presiona ENTER para cerrar...${NC}"
    read -r
    exit 1
fi

# --- Verificar día y horas con Python ---
VALIDATION=$("$PYTHON" << 'PYCHECK'
import sys
from datetime import date, timedelta
from tempo_cli.config import load_config, get_hours_per_day
from tempo_cli.client import TempoClient
from tempo_cli.config import get_tempo_base_url, get_tempo_token, get_account_id

today = date.today()
weekday = today.weekday()  # 0=Mon, 6=Sun

config = load_config()
hours_per_day = get_hours_per_day(config)

client = TempoClient(get_tempo_base_url(), get_tempo_token())
account_id = get_account_id()

# Calcular lunes de esta semana
monday = today - timedelta(days=weekday)

# Detectar si la semana actual está esencialmente vacía (ej: lunes temprano)
# y en ese caso ofrecer la semana anterior que es la que se suele enviar.
week_wl = client.get_worklogs(account_id, monday, today)
week_hours = sum(wl.get("timeSpentSeconds", 0) for wl in week_wl) / 3600

# Si estamos en lunes o martes con muy pocas horas, evaluar la semana anterior
use_previous_week = False
if weekday <= 1 and week_hours < hours_per_day - 0.1:
    prev_monday = monday - timedelta(days=7)
    prev_sunday = prev_monday + timedelta(days=6)
    prev_wl = client.get_worklogs(account_id, prev_monday, prev_sunday)
    prev_hours = sum(wl.get("timeSpentSeconds", 0) for wl in prev_wl) / 3600
    if prev_hours > week_hours:
        use_previous_week = True
        monday = prev_monday

# Determinar rango a revisar (lun a vie de la semana objetivo)
today_offset = (today - monday).days
if use_previous_week:
    days_to_check = 5  # semana anterior completa
    query_end = monday + timedelta(days=4)
else:
    days_to_check = min(today_offset + 1, 5)  # hasta hoy o viernes
    query_end = min(today, monday + timedelta(days=4))

worklogs = client.get_worklogs(account_id, monday, query_end)

# Agrupar horas por día
day_names_es = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]
hours_by_day = {}
for d in range(days_to_check):
    day = monday + timedelta(days=d)
    hours_by_day[day.isoformat()] = 0.0

for wl in worklogs:
    d = wl.get("startDate", "")
    seconds = wl.get("timeSpentSeconds", 0)
    if d in hours_by_day:
        hours_by_day[d] += seconds / 3600

# Generar resumen de días (campos internos separados por ~)
day_summary = []
incomplete_days = []
for i, (d_str, hours) in enumerate(sorted(hours_by_day.items())):
    status = "✓" if hours >= hours_per_day - 0.1 else "⚠"
    day_summary.append(f"{day_names_es[i]}~{d_str}~{hours:.2f}~{status}")
    if hours < hours_per_day - 0.1:
        incomplete_days.append(f"{d_str} ({hours:.2f}h/{hours_per_day:.0f}h)")

total_logged = sum(hours_by_day.values())
total_expected = hours_per_day * days_to_check

# Determinar el domingo del periodo (Tempo usa lun-dom)
period_monday = monday.isoformat()
period_sunday = (monday + timedelta(days=6)).isoformat()

# Estado
is_friday_or_later = (not use_previous_week) and weekday >= 4
days_remaining = max(0, 4 - weekday) if not use_previous_week else 0

if use_previous_week:
    status = "PREV_WEEK" if not incomplete_days else "PREV_WEEK_INCOMPLETE"
elif is_friday_or_later:
    status = "OK" if not incomplete_days else "INCOMPLETE"
else:
    status = "NOT_FRIDAY"

# Salida en líneas etiquetadas (una por campo) para evitar colisión de separadores.
# Los días van uno por línea con prefijo DAY:, los incompletos con INC:.
print(f"STATUS={status}")
print(f"WEEKDAY={weekday}")
print(f"DAYS_LEFT={days_remaining}")
print(f"TOTAL={total_logged:.2f}")
print(f"EXPECTED={total_expected:.0f}")
print(f"PERIOD_MONDAY={period_monday}")
print(f"PERIOD_SUNDAY={period_sunday}")
for d in day_summary:
    print(f"DAY={d}")
for inc in incomplete_days:
    print(f"INC={inc}")
PYCHECK
)

# --- Parsear resultado (líneas etiquetadas KEY=valor) ---
get_field() { echo "$VALIDATION" | grep "^$1=" | head -1 | cut -d'=' -f2-; }

STATUS=$(get_field "STATUS")
WEEKDAY_NUM=$(get_field "WEEKDAY")
DAYS_LEFT=$(get_field "DAYS_LEFT")
TOTAL_LOGGED=$(get_field "TOTAL")
TOTAL_EXPECTED=$(get_field "EXPECTED")
PERIOD_MONDAY=$(get_field "PERIOD_MONDAY")
PERIOD_SUNDAY=$(get_field "PERIOD_SUNDAY")

# --- Aviso si se usa la semana anterior ---
if [[ "$STATUS" == "PREV_WEEK" || "$STATUS" == "PREV_WEEK_INCOMPLETE" ]]; then
    echo -e "  ${CYAN}ℹ️  La semana actual apenas comienza. Se preparará el envío de la"
    echo -e "     semana anterior (${PERIOD_MONDAY} → ${PERIOD_SUNDAY}).${NC}"
    echo ""
fi

# --- Mostrar detalle de actividades por día (tabla completa) ---
echo -e "  ${BOLD}📅 Actividades registradas (${PERIOD_MONDAY} → ${PERIOD_SUNDAY}):${NC}"
echo ""
tempo status --from "$PERIOD_MONDAY" --to "$PERIOD_SUNDAY" 2>/dev/null || true
echo ""

# --- Resumen compacto de horas por día ---
echo -e "  ${BOLD}Resumen por día:${NC}"
while IFS= read -r day_line; do
    day_info="${day_line#DAY=}"
    DAY_NAME=$(echo "$day_info" | cut -d'~' -f1)
    DAY_DATE=$(echo "$day_info" | cut -d'~' -f2)
    DAY_HOURS=$(echo "$day_info" | cut -d'~' -f3)
    DAY_STATUS=$(echo "$day_info" | cut -d'~' -f4)

    if [[ "$DAY_STATUS" == "✓" ]]; then
        echo -e "    ${GREEN}✓${NC} ${DAY_NAME} (${DAY_DATE}): ${BOLD}${DAY_HOURS}h${NC}"
    else
        echo -e "    ${YELLOW}⚠${NC} ${DAY_NAME} (${DAY_DATE}): ${YELLOW}${DAY_HOURS}h${NC}"
    fi
done < <(echo "$VALIDATION" | grep "^DAY=")

echo ""
echo -e "  Total: ${BOLD}${TOTAL_LOGGED}h / ${TOTAL_EXPECTED}h${NC}"
echo ""
echo -e "${BLUE}───────────────────────────────────────────────────────────${NC}"
echo ""

# --- Validar día de la semana (solo si es la semana actual) ---
if [[ "$STATUS" == "NOT_FRIDAY" ]]; then
    DAY_NAMES=("lunes" "martes" "miércoles" "jueves" "viernes")
    DAY_NAME="${DAY_NAMES[$WEEKDAY_NUM]}"

    echo -e "  ${YELLOW}⚠️  Hoy es ${BOLD}${DAY_NAME}${NC}${YELLOW}. El timesheet se envía normalmente el viernes.${NC}"
    echo -e "  Faltan ${BOLD}${DAYS_LEFT} día(s) laborales${NC} para completar la semana."
    echo -e "  ${DIM}El envío antes de viernes puede resultar en horas faltantes.${NC}"
    echo ""

    read -p "  ¿Deseas continuar de todas formas? [y/N]: " FORCE_CONTINUE

    if [[ "$FORCE_CONTINUE" != "y" && "$FORCE_CONTINUE" != "Y" ]]; then
        echo ""
        echo -e "  ${GREEN}👍 Mejor espera al viernes para enviar.${NC}"
        echo ""
        echo -e "${YELLOW}  Presiona ENTER para cerrar...${NC}"
        read -r
        exit 0
    fi
    echo ""
fi

# --- Validar horas incompletas ---
# Nota: grep -c retorna exit 1 si no hay coincidencias; || true evita que set -e corte el script
INCOMPLETE_COUNT=$(echo "$VALIDATION" | grep -c "^INC=" || true)
if [[ "$INCOMPLETE_COUNT" -gt 0 ]]; then
    echo -e "  ${RED}⚠️  Hay días con horas incompletas:${NC}"
    echo ""

    while IFS= read -r inc_line; do
        echo -e "    ${YELLOW}• ${inc_line#INC=}${NC}"
    done < <(echo "$VALIDATION" | grep "^INC=")

    echo ""
    read -p "  ¿Deseas enviar el timesheet con horas incompletas? [y/N]: " FORCE_SUBMIT

    if [[ "$FORCE_SUBMIT" != "y" && "$FORCE_SUBMIT" != "Y" ]]; then
        echo ""
        echo -e "  ${YELLOW}Cancelado. Completa las horas faltantes primero.${NC}"
        echo -e "  ${DIM}Usa: tempo log <alias> <horas> --date <fecha>${NC}"
        echo ""
        echo -e "${YELLOW}  Presiona ENTER para cerrar...${NC}"
        read -r
        exit 0
    fi
    echo ""
fi

# --- Mostrar estado del timesheet antes de enviar (usando período lun-dom) ---
echo -e "  ${BOLD}📋 Estado del timesheet:${NC}"
echo ""
tempo timesheet status --from "$PERIOD_MONDAY" --to "$PERIOD_SUNDAY"
echo ""

# --- Mostrar el revisor configurado (default_reviewer) ---
REVIEWER_INFO=$("$PYTHON" -c "
from tempo_cli.config import load_config
cfg = load_config()
default = cfg.get('defaults', {}).get('default_reviewer')
if not default:
    print('NONE')
else:
    # Resolver alias a nombre
    name = default
    for r in cfg.get('reviewers', []):
        if r.get('alias', '').lower() == default.lower():
            name = r.get('name', default)
            break
    print(f'{default}|{name}')
" 2>/dev/null || echo "NONE")

if [[ "$REVIEWER_INFO" == "NONE" ]]; then
    echo -e "  ${YELLOW}⚠️  No hay revisor configurado (default_reviewer).${NC}"
    echo -e "  ${DIM}El envío puede fallar. Configura 'default_reviewer' en config.yaml.${NC}"
else
    REVIEWER_ALIAS=$(echo "$REVIEWER_INFO" | cut -d'|' -f1)
    REVIEWER_NAME=$(echo "$REVIEWER_INFO" | cut -d'|' -f2)
    echo -e "  ${BOLD}👤 Revisor asignado:${NC} ${REVIEWER_NAME} ${DIM}(${REVIEWER_ALIAS})${NC}"
fi
echo ""
echo -e "${BLUE}───────────────────────────────────────────────────────────${NC}"
echo ""

# --- Confirmar y enviar ---
echo -e "${BOLD}  ¿Enviar timesheet para aprobación (${PERIOD_MONDAY} → ${PERIOD_SUNDAY})?${NC}"
echo ""
read -p "  Confirmar [y/N]: " CONFIRM

if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
    echo ""
    echo -e "  ${YELLOW}Cancelado.${NC}"
    echo ""
    echo -e "${YELLOW}  Presiona ENTER para cerrar...${NC}"
    read -r
    exit 0
fi

echo ""
tempo timesheet submit --from "$PERIOD_MONDAY" --to "$PERIOD_SUNDAY" --yes
echo ""

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}  Presiona ENTER para cerrar...${NC}"
read -r
