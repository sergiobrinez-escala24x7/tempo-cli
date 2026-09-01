#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  Tempo CLI — Instalador
#  Haz doble click en este archivo para instalar Tempo CLI
# ═══════════════════════════════════════════════════════════════

set -e

# Colores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

clear
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}        🕐 Tempo CLI — Instalador${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  Este instalador va a:"
echo -e "    1. Verificar que Python 3.9+ esté disponible"
echo -e "    2. Instalar pipx (si no está instalado)"
echo -e "    3. Instalar Tempo CLI globalmente"
echo -e "    4. Crear el directorio de configuración"
echo -e "    5. Crear acceso directo (app) en ~/Applications"
echo ""
echo -e "${YELLOW}  Presiona ENTER para continuar o Ctrl+C para cancelar...${NC}"
read -r

# --- Detectar directorio del script ---
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# --- Verificar Python ---
echo ""
echo -e "${BOLD}[1/4] Verificando Python...${NC}"

PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        version=$("$cmd" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 9 ]; then
            PYTHON="$cmd"
            echo -e "  ${GREEN}✓${NC} Encontrado: $($cmd --version)"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo -e "  ${RED}✗ Python 3.9+ no encontrado.${NC}"
    echo ""
    echo -e "  Instala Python desde: ${BOLD}https://www.python.org/downloads/${NC}"
    echo -e "  O con Homebrew: ${BOLD}brew install python${NC}"
    echo ""
    echo -e "  Presiona ENTER para cerrar..."
    read -r
    exit 1
fi

# --- Verificar/Instalar pipx ---
echo ""
echo -e "${BOLD}[2/4] Verificando pipx...${NC}"

if command -v pipx &>/dev/null; then
    echo -e "  ${GREEN}✓${NC} pipx ya está instalado: $(pipx --version)"
else
    echo -e "  ${YELLOW}→${NC} pipx no encontrado. Instalando..."

    if command -v brew &>/dev/null; then
        brew install pipx 2>&1 | tail -1
        pipx ensurepath 2>/dev/null || true
    else
        "$PYTHON" -m pip install --user pipx 2>&1 | tail -1
        "$PYTHON" -m pipx ensurepath 2>/dev/null || true
    fi

    # Recargar PATH
    export PATH="$HOME/.local/bin:$PATH"
    export PATH="/opt/homebrew/bin:$PATH"

    if command -v pipx &>/dev/null; then
        echo -e "  ${GREEN}✓${NC} pipx instalado correctamente"
    else
        echo -e "  ${RED}✗ No se pudo instalar pipx.${NC}"
        echo -e "  Intenta manualmente: ${BOLD}brew install pipx${NC}"
        echo ""
        echo -e "  Presiona ENTER para cerrar..."
        read -r
        exit 1
    fi
fi

# --- Instalar Tempo CLI ---
echo ""
echo -e "${BOLD}[3/4] Instalando Tempo CLI...${NC}"

if pipx list 2>/dev/null | grep -q "tempo-cli"; then
    echo -e "  ${YELLOW}→${NC} Tempo CLI ya está instalado. Reinstalando..."
    pipx install -e "$SCRIPT_DIR" --force 2>&1 | grep -E "(installed|done)" | head -2
else
    pipx install -e "$SCRIPT_DIR" 2>&1 | grep -E "(installed|done)" | head -2
fi

# Verificar instalación
export PATH="$HOME/.local/bin:$PATH"
if command -v tempo &>/dev/null; then
    echo -e "  ${GREEN}✓${NC} Comando 'tempo' disponible"
else
    echo -e "  ${YELLOW}⚠${NC}  Instalado pero puede requerir reiniciar la terminal"
fi

# --- Crear directorio de configuración ---
echo ""
echo -e "${BOLD}[4/4] Preparando configuración...${NC}"

CONFIG_DIR="$HOME/.tempo-cli"
if [ ! -d "$CONFIG_DIR" ]; then
    mkdir -p "$CONFIG_DIR"
    chmod 700 "$CONFIG_DIR"
    echo -e "  ${GREEN}✓${NC} Directorio creado: ~/.tempo-cli/"
else
    echo -e "  ${GREEN}✓${NC} Directorio ya existe: ~/.tempo-cli/"
fi

# Copiar config de ejemplo si no existe
if [ ! -f "$CONFIG_DIR/config.yaml" ]; then
    cp "$SCRIPT_DIR/config/example.yaml" "$CONFIG_DIR/config.yaml"
    echo -e "  ${GREEN}✓${NC} Configuración de ejemplo copiada"
else
    echo -e "  ${GREEN}✓${NC} Configuración existente conservada"
fi

# --- Crear accesos directos (apps) ---
echo ""
echo -e "${BOLD}[5/5] Creando accesos directos (apps)...${NC}"

PYTHON_VENV="$HOME/Library/Application Support/pipx/venvs/tempo-cli/bin/python"

# --- App 1: Tempo Log Calendar ---
APP_DIR="$HOME/Applications/Tempo Log Calendar.app"
APP_CONTENTS="$APP_DIR/Contents"
APP_MACOS="$APP_CONTENTS/MacOS"
APP_RESOURCES="$APP_CONTENTS/Resources"

mkdir -p "$APP_MACOS"
mkdir -p "$APP_RESOURCES"

cat > "$APP_MACOS/run.sh" << APPSCRIPT
#!/bin/bash
open -a Terminal "$SCRIPT_DIR/log-calendar.command"
APPSCRIPT
chmod +x "$APP_MACOS/run.sh"

cat > "$APP_CONTENTS/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>run.sh</string>
    <key>CFBundleName</key>
    <string>Tempo Log Calendar</string>
    <key>CFBundleDisplayName</key>
    <string>Tempo Log Calendar</string>
    <key>CFBundleIdentifier</key>
    <string>com.tempo-cli.log-calendar</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.15</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
PLIST

# --- App 2: Tempo Submit Timesheet ---
APP2_DIR="$HOME/Applications/Tempo Submit Timesheet.app"
APP2_CONTENTS="$APP2_DIR/Contents"
APP2_MACOS="$APP2_CONTENTS/MacOS"
APP2_RESOURCES="$APP2_CONTENTS/Resources"

mkdir -p "$APP2_MACOS"
mkdir -p "$APP2_RESOURCES"

cat > "$APP2_MACOS/run.sh" << APPSCRIPT2
#!/bin/bash
open -a Terminal "$SCRIPT_DIR/submit-timesheet.command"
APPSCRIPT2
chmod +x "$APP2_MACOS/run.sh"

cat > "$APP2_CONTENTS/Info.plist" << 'PLIST2'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>run.sh</string>
    <key>CFBundleName</key>
    <string>Tempo Submit Timesheet</string>
    <key>CFBundleDisplayName</key>
    <string>Tempo Submit Timesheet</string>
    <key>CFBundleIdentifier</key>
    <string>com.tempo-cli.submit-timesheet</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.15</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
PLIST2

# --- Generar íconos para ambas apps ---
if [ -f "$PYTHON_VENV" ]; then
    "$PYTHON_VENV" << 'ICONSCRIPT'
import subprocess, os, shutil

def create_icon(svg_content, app_name):
    """Genera un .icns a partir de SVG y lo copia a la app."""
    svg_path = f'/tmp/tempo_{app_name}_icon.svg'
    png_path = f'/tmp/tempo_{app_name}_icon.png'

    with open(svg_path, 'w') as f:
        f.write(svg_content)

    converted = False
    try:
        subprocess.run(['rsvg-convert', '-w', '512', '-h', '512', svg_path, '-o', png_path],
                       check=True, capture_output=True)
        converted = True
    except (FileNotFoundError, subprocess.CalledProcessError):
        try:
            subprocess.run(['qlmanage', '-t', '-s', '512', '-o', '/tmp', svg_path],
                           check=True, capture_output=True)
            ql_output = svg_path + '.png'
            if os.path.exists(ql_output):
                os.rename(ql_output, png_path)
                converted = True
        except Exception:
            pass

    if not converted or not os.path.exists(png_path):
        return False

    iconset_path = f'/tmp/{app_name}.iconset'
    os.makedirs(iconset_path, exist_ok=True)

    sizes = [16, 32, 64, 128, 256, 512]
    for size in sizes:
        out = f'{iconset_path}/icon_{size}x{size}.png'
        subprocess.run(['sips', '-z', str(size), str(size), png_path, '--out', out],
                       capture_output=True)
        if size <= 256:
            out_2x = f'{iconset_path}/icon_{size}x{size}@2x.png'
            subprocess.run(['sips', '-z', str(size*2), str(size*2), png_path, '--out', out_2x],
                           capture_output=True)

    icns_path = f'/tmp/{app_name}.icns'
    result = subprocess.run(['iconutil', '-c', 'icns', iconset_path, '-o', icns_path],
                           capture_output=True)

    success = result.returncode == 0 and os.path.exists(icns_path)

    # Cleanup
    for f in [svg_path, png_path]:
        if os.path.exists(f):
            os.remove(f)
    if os.path.exists(iconset_path):
        shutil.rmtree(iconset_path)

    return icns_path if success else None


# Icono 1: Calendario azul con reloj (Log Calendar)
svg_calendar = '''<?xml version="1.0" encoding="UTF-8"?>
<svg width="512" height="512" viewBox="0 0 512 512" xmlns="http://www.w3.org/2000/svg">
  <rect x="40" y="80" width="432" height="392" rx="40" fill="#2563EB"/>
  <rect x="40" y="80" width="432" height="100" rx="40" fill="#1D4ED8"/>
  <rect x="40" y="140" width="432" height="40" fill="#1D4ED8"/>
  <rect x="140" y="50" width="24" height="70" rx="12" fill="#374151"/>
  <rect x="348" y="50" width="24" height="70" rx="12" fill="#374151"/>
  <circle cx="256" cy="320" r="100" fill="none" stroke="white" stroke-width="16"/>
  <line x1="256" y1="320" x2="256" y2="250" stroke="white" stroke-width="14" stroke-linecap="round"/>
  <line x1="256" y1="320" x2="310" y2="340" stroke="white" stroke-width="14" stroke-linecap="round"/>
  <path d="M 370 400 L 400 430 L 450 370" fill="none" stroke="#34D399" stroke-width="20" stroke-linecap="round" stroke-linejoin="round"/>
</svg>'''

# Icono 2: Calendario verde con checkmark (Submit Timesheet)
svg_submit = '''<?xml version="1.0" encoding="UTF-8"?>
<svg width="512" height="512" viewBox="0 0 512 512" xmlns="http://www.w3.org/2000/svg">
  <rect x="40" y="80" width="432" height="392" rx="40" fill="#059669"/>
  <rect x="40" y="80" width="432" height="100" rx="40" fill="#047857"/>
  <rect x="40" y="140" width="432" height="40" fill="#047857"/>
  <rect x="140" y="50" width="24" height="70" rx="12" fill="#374151"/>
  <rect x="348" y="50" width="24" height="70" rx="12" fill="#374151"/>
  <path d="M 180 300 L 230 350 L 340 240" fill="none" stroke="white" stroke-width="32" stroke-linecap="round" stroke-linejoin="round"/>
  <rect x="160" y="390" width="192" height="40" rx="8" fill="white" opacity="0.3"/>
</svg>'''

# Generar icono 1
icns = create_icon(svg_calendar, "log_calendar")
if icns:
    dest = os.path.expanduser('~/Applications/Tempo Log Calendar.app/Contents/Resources/AppIcon.icns')
    shutil.copy(icns, dest)
    os.remove(icns)

# Generar icono 2
icns = create_icon(svg_submit, "submit_timesheet")
if icns:
    dest = os.path.expanduser('~/Applications/Tempo Submit Timesheet.app/Contents/Resources/AppIcon.icns')
    shutil.copy(icns, dest)
    os.remove(icns)
ICONSCRIPT
fi

# Registrar con Launch Services
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP_DIR" 2>/dev/null || true
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP2_DIR" 2>/dev/null || true

touch "$APP_DIR"
touch "$APP2_DIR"

echo -e "  ${GREEN}✓${NC} Tempo Log Calendar.app creada"
echo -e "  ${GREEN}✓${NC} Tempo Submit Timesheet.app creada"
echo -e "  ${GREEN}✓${NC} Búscalas en Spotlight o arrástralas al Dock"

# --- Resumen ---
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}  ✅ Instalación completada${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${BOLD}Siguiente paso:${NC} Abre una terminal y ejecuta:"
echo ""
echo -e "    ${BOLD}tempo auth setup${NC}"
echo ""
echo -e "  Datos que necesitas tener listos:"
echo -e "    • Tempo API Token (Tempo > Settings > API Integration)"
echo -e "    • Atlassian Account ID (desde /rest/api/3/myself)"
echo ""
echo -e "  Comandos útiles:"
echo -e "    tempo --help          Ver todos los comandos"
echo -e "    tempo auth --help     Ver datos necesarios para autenticación"
echo -e "    tempo status          Ver worklogs del día"
echo ""
echo -e "${YELLOW}  Presiona ENTER para cerrar...${NC}"
read -r
