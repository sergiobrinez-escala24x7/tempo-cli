#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  Tempo CLI — Configuración de Autenticación
#  Haz doble click en este archivo para gestionar tus credenciales
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
echo -e "${BOLD}        🔐 Tempo CLI — Autenticación${NC}"
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
    echo -e "    ${CYAN}1)${NC} Configurar credenciales (primera vez o reconfigurar)"
    echo -e "    ${CYAN}2)${NC} Ver estado de autenticación"
    echo -e "    ${CYAN}3)${NC} Eliminar credenciales"
    echo -e "    ${CYAN}4)${NC} Ver qué datos necesito antes de configurar"
    echo -e "    ${CYAN}5)${NC} Salir"
    echo ""
    echo -ne "  Opción [1-5]: "
}

show_requirements() {
    clear
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}  📋 Datos necesarios para autenticación${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "  ${BOLD}${GREEN}Todos los datos son obligatorios:${NC}"
    echo ""
    echo -e "  ${BOLD}1. Tempo API Token${NC}"
    echo -e "     Dónde obtenerlo:"
    echo -e "     → Ingresa a Tempo (desde Jira)"
    echo -e "     → Settings > API Integration"
    echo -e "     → Crear nuevo token con permiso ${BOLD}\"Manage Worklogs\"${NC}"
    echo -e "     → Copia el token generado"
    echo ""
    echo -e "  ${BOLD}2. Atlassian Account ID${NC}"
    echo -e "     Dónde obtenerlo:"
    echo -e "     → Abre en tu navegador:"
    echo -e "       ${DIM}https://tu-empresa.atlassian.net/rest/api/3/myself${NC}"
    echo -e "     → Busca el campo ${BOLD}\"accountId\"${NC}"
    echo -e "     → Es una cadena tipo: ${DIM}5a1234bc5678de9012f34567${NC}"
    echo ""
    echo -e "  ${BOLD}3. Jira Base URL${NC}"
    echo -e "     La URL de tu instancia de Jira"
    echo -e "     Ejemplo: ${DIM}https://tu-empresa.atlassian.net${NC}"
    echo ""
    echo -e "  ${BOLD}4. Jira Email${NC}"
    echo -e "     Tu email corporativo con el que accedes a Jira"
    echo ""
    echo -e "  ${BOLD}5. Jira API Token${NC}"
    echo -e "     Dónde obtenerlo:"
    echo -e "     → Ir a: ${DIM}https://id.atlassian.com/manage-profile/security/api-tokens${NC}"
    echo -e "     → Crear nuevo token y copiarlo"
    echo ""
    echo -e "${BLUE}───────────────────────────────────────────────────────────${NC}"
    echo -e "  ${DIM}Una vez que tengas estos datos, selecciona la opción 1${NC}"
    echo -e "  ${DIM}del menú para configurar las credenciales.${NC}"
    echo -e "${BLUE}───────────────────────────────────────────────────────────${NC}"
    echo ""
    echo -e "${YELLOW}  Presiona ENTER para volver al menú...${NC}"
    read -r
}

run_setup() {
    clear
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}  🔧 Configurar credenciales${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    tempo auth setup
    echo ""
    echo -e "${YELLOW}  Presiona ENTER para volver al menú...${NC}"
    read -r
}

run_status() {
    clear
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}  📊 Estado de autenticación${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    tempo auth status
    echo ""
    echo -e "${YELLOW}  Presiona ENTER para volver al menú...${NC}"
    read -r
}

run_reset() {
    clear
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}  🗑️  Eliminar credenciales${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    tempo auth reset
    echo ""
    echo -e "${YELLOW}  Presiona ENTER para volver al menú...${NC}"
    read -r
}

# --- Loop principal ---
while true; do
    clear
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}        🔐 Tempo CLI — Autenticación${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo ""

    show_menu
    read -r choice

    case $choice in
        1) run_setup ;;
        2) run_status ;;
        3) run_reset ;;
        4) show_requirements ;;
        5|q|Q)
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
