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
weekday = today.weekday()  # 0=Mon, 4=Fri

config = load_config()
hours_per_day = get_hours_per_day(config)

# Calcular lunes de esta semana
monday = today - timedelta(days=weekday)

# Consultar worklogs de lun a hoy (no días futuros)
client = TempoClient(get_tempo_base_url(), get_tempo_token())
account_id = get_account_id()

query_end = today if weekday < 4 else monday + timedelta(days=4)
worklogs = client.get_worklogs(account_id, monday, query_end)

# Agrupar horas por día
day_names_es = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]
days_to_check = min(weekday + 1, 5)  # hasta hoy o viernes

hours_by_day = {}
for d in range(days_to_check):
    day = monday + timedelta(days=d)
    hours_by_day[day.isoformat()] = 0.0

for wl in worklogs:
    d = wl.get("startDate", "")
    seconds = wl.get("timeSpentSeconds", 0)
    if d in hours_by_day:
        hours_by_day[d] += seconds / 3600

# Generar resumen de días
day_summary = []
incomplete_days = []
for i, (d_str, hours) in enumerate(sorted(hours_by_day.items())):
    status = "✓" if hours >= hours_per_day - 0.1 else "⚠"
    day_summary.append(f"{day_names_es[i]}|{d_str}|{hours:.1f}|{status}")
    if hours < hours_per_day - 0.1:
        incomplete_days.append(f"{d_str} ({hours:.1f}h/{hours_per_day:.0f}h)")

total_logged = sum(hours_by_day.values())
total_expected = hours_per_day * days_to_check

# Output format: STATUS|weekday|days_remaining|total_logged|total_expected|day1;day2;...|incomplete1;incomplete2;...
is_friday = weekday >= 4
days_remaining = max(0, 4 - weekday)

status = "OK" if (is_friday and not incomplete_days) else ("NOT_FRIDAY" if not is_friday else "INCOMPLETE")

days_str = ";;".join(day_summary)
incomplete_str = ";;".join(incomplete_days) if incomplete_days else "NONE"

print(f"{status}|{weekday}|{days_remaining}|{total_logged:.1f}|{total_expected:.0f}|{days_str}|{incomplete_str}")
PYCHECK
)

# --- Parsear resultado ---
STATUS=$(echo "$VALIDATION" | cut -d'|' -f1)
WEEKDAY_NUM=$(echo "$VALIDATION" | cut -d'|' -f2)
DAYS_LEFT=$(echo "$VALIDATION" | cut -d'|' -f3)
TOTAL_LOGGED=$(echo "$VALIDATION" | cut -d'|' -f4)
TOTAL_EXPECTED=$(echo "$VALIDATION" | cut -d'|' -f5)
DAYS_SUMMARY=$(echo "$VALIDATION" | cut -d'|' -f6)
INCOMPLETE_DAYS=$(echo "$VALIDATION" | cut -d'|' -f7)

# --- Mostrar resumen de días registrados ---
echo -e "  ${BOLD}📅 Horas registradas esta semana:${NC}"
echo ""

# Usar tempo status para mostrar detalle por día (lun a hoy)
tempo status --week 2>/dev/null || true

echo ""
echo -e "  Total semana: ${BOLD}${TOTAL_LOGGED}h / ${TOTAL_EXPECTED}h${NC}"
echo ""
echo -e "${BLUE}───────────────────────────────────────────────────────────${NC}"
echo ""

# --- Validar día de la semana ---
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
if [[ "$INCOMPLETE_DAYS" != "NONE" ]]; then
    echo -e "  ${RED}⚠️  Hay días con horas incompletas:${NC}"
    echo ""

    IFS=';;' read -ra INC_DAYS <<< "$INCOMPLETE_DAYS"
    for day in "${INC_DAYS[@]}"; do
        echo -e "    ${YELLOW}• ${day}${NC}"
    done

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

# --- Mostrar estado del timesheet antes de enviar ---
echo -e "  ${BOLD}📋 Estado del timesheet:${NC}"
echo ""
tempo timesheet status --week
echo ""
echo -e "${BLUE}───────────────────────────────────────────────────────────${NC}"
echo ""

# --- Confirmar y enviar ---
echo -e "${BOLD}  ¿Enviar timesheet para aprobación?${NC}"
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
tempo timesheet submit --week --yes
echo ""

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}  Presiona ENTER para cerrar...${NC}"
read -r
