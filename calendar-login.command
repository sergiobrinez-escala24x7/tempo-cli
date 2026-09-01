#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  Tempo CLI — Configuración de Google Calendar
#  Haz doble click en este archivo para configurar la integración
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

clear
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}        📅 Tempo CLI — Google Calendar${NC}"
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

# --- Menú interactivo ---
show_menu() {
    echo -e "  ${BOLD}¿Qué deseas hacer?${NC}"
    echo ""
    echo -e "    ${CYAN}1)${NC} Configurar acceso a Google Calendar"
    echo -e "    ${CYAN}2)${NC} Ver estado de la integración"
    echo -e "    ${CYAN}3)${NC} Ver eventos de hoy"
    echo -e "    ${CYAN}4)${NC} Ver eventos de la semana"
    echo -e "    ${CYAN}5)${NC} Eliminar credenciales de Google Calendar"
    echo -e "    ${CYAN}6)${NC} Ver qué datos necesito"
    echo -e "    ${CYAN}7)${NC} Salir"
    echo ""
    echo -ne "  Opción [1-7]: "
}

show_requirements() {
    clear
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}  📋 Datos necesarios para Google Calendar${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "  ${BOLD}${GREEN}Necesitas 2 datos:${NC}"
    echo ""
    echo -e "  ${BOLD}1. URL del Web App (Apps Script)${NC}"
    echo -e "     Dónde obtenerla:"
    echo -e "     → Abre tu proyecto en ${DIM}script.google.com${NC}"
    echo -e "     → Implementar > Administrar implementaciones"
    echo -e "     → Copia la URL del Web App"
    echo -e "     → Ejemplo: ${DIM}https://script.google.com/macros/s/AKfycb.../exec${NC}"
    echo ""
    echo -e "  ${BOLD}2. API Key${NC}"
    echo -e "     Dónde obtenerla:"
    echo -e "     → En tu proyecto de Apps Script"
    echo -e "     → Configuración del proyecto (⚙️)"
    echo -e "     → Propiedades del script > propiedad ${BOLD}API_KEY${NC}"
    echo -e "     → Es el valor que configuraste ahí"
    echo ""
    echo -e "${BLUE}───────────────────────────────────────────────────────────${NC}"
    echo -e "  ${DIM}Una vez que tengas estos datos, selecciona la opción 1${NC}"
    echo -e "  ${DIM}del menú para configurar el acceso.${NC}"
    echo -e "${BLUE}───────────────────────────────────────────────────────────${NC}"
    echo ""
    echo -e "${YELLOW}  Presiona ENTER para volver al menú...${NC}"
    read -r
}

run_login() {
    clear
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}  🔧 Configurar Google Calendar${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    tempo calendar login
    echo ""
    echo -e "${YELLOW}  Presiona ENTER para volver al menú...${NC}"
    read -r
}

run_status() {
    clear
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}  📊 Estado de Google Calendar${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    tempo calendar status
    echo ""
    echo -e "${YELLOW}  Presiona ENTER para volver al menú...${NC}"
    read -r
}

run_events_today() {
    clear
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}  📅 Eventos de hoy${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    tempo calendar events
    echo ""
    echo -e "${YELLOW}  Presiona ENTER para volver al menú...${NC}"
    read -r
}

run_events_week() {
    clear
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}  📅 Eventos de la semana${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    tempo calendar events --week
    echo ""
    echo -e "${YELLOW}  Presiona ENTER para volver al menú...${NC}"
    read -r
}

run_logout() {
    clear
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}  🗑️  Eliminar credenciales de Google Calendar${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    tempo calendar logout
    echo ""
    echo -e "${YELLOW}  Presiona ENTER para volver al menú...${NC}"
    read -r
}

# --- Loop principal ---
while true; do
    clear
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}        📅 Tempo CLI — Google Calendar${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo ""

    show_menu
    read -r choice

    case $choice in
        1) run_login ;;
        2) run_status ;;
        3) run_events_today ;;
        4) run_events_week ;;
        5) run_logout ;;
        6) show_requirements ;;
        7|q|Q)
            echo ""
            echo -e "  ${GREEN}👋 ¡Hasta luego!${NC}"
            echo ""
            sleep 0.5
            exit 0
            ;;
        *)
            echo -e "  ${RED}Opción no válida. Intenta de nuevo.${NC}"
            sleep 1
            ;;
    esac
done
