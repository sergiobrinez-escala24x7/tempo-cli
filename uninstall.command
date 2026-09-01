#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  Tempo CLI — Desinstalador
#  Haz doble click en este archivo para desinstalar Tempo CLI
# ═══════════════════════════════════════════════════════════════

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

clear
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}        🕐 Tempo CLI — Desinstalador${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  Esto va a:"
echo -e "    1. Desinstalar el comando 'tempo'"
echo -e "    2. Eliminar credenciales cifradas y configuración"
echo ""
echo -e "${RED}  ⚠️  Esta acción es irreversible.${NC}"
echo ""
echo -e "${YELLOW}  Presiona ENTER para continuar o Ctrl+C para cancelar...${NC}"
read -r

# --- Desinstalar con pipx ---
echo ""
echo -e "${BOLD}[1/2] Desinstalando Tempo CLI...${NC}"

if command -v pipx &>/dev/null; then
    if pipx list 2>/dev/null | grep -q "tempo-cli"; then
        pipx uninstall tempo-cli 2>&1 | tail -1
        echo -e "  ${GREEN}✓${NC} Comando 'tempo' eliminado"
    else
        echo -e "  ${YELLOW}→${NC} Tempo CLI no estaba instalado con pipx"
    fi
else
    echo -e "  ${YELLOW}→${NC} pipx no encontrado, intentando con pip..."
    pip3 uninstall tempo-cli -y 2>/dev/null || true
fi

# --- Eliminar configuración ---
echo ""
echo -e "${BOLD}[2/2] Eliminando configuración...${NC}"

CONFIG_DIR="$HOME/.tempo-cli"
if [ -d "$CONFIG_DIR" ]; then
    echo -e "  ${YELLOW}→${NC} Se encontró: ~/.tempo-cli/"
    echo -ne "  ¿Eliminar configuración y credenciales? [s/N]: "
    read -r answer
    if [[ "$answer" =~ ^[sSyY]$ ]]; then
        rm -rf "$CONFIG_DIR"
        echo -e "  ${GREEN}✓${NC} Eliminado: ~/.tempo-cli/"
    else
        echo -e "  ${YELLOW}→${NC} Conservado: ~/.tempo-cli/"
    fi
else
    echo -e "  ${GREEN}✓${NC} No hay configuración que eliminar"
fi

# --- Resumen ---
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}  ✅ Desinstalación completada${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}  Presiona ENTER para cerrar...${NC}"
read -r
