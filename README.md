# Tempo CLI

CLI local para registrar worklogs en Tempo/Jira desde la terminal.

## Instalación

### Opción A — Doble click (recomendado para usuarios no técnicos)

1. Abre la carpeta del proyecto en Finder
2. Haz doble click en **`install.command`** para instalar
3. Haz doble click en **`auth.command`** para configurar credenciales
4. Listo — abre una terminal y usa `tempo`

### Opción B — Desde terminal

```bash
pipx install -e .
```

El comando `tempo` queda disponible globalmente.

## Configuración inicial

### 1. Autenticación

```bash
tempo auth setup
```

Te pide los tokens de forma interactiva. Las credenciales se cifran y quedan **atadas a tu máquina**: no se pueden recuperar, exportar ni usar en otro equipo.

```
🔐 Tempo Auth Setup
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Campos requeridos:
  Tempo API Token: ****
  Tempo Base URL [https://api.tempo.io/4]:
  Atlassian Account ID: abc123

Campos opcionales (Jira):
  ¿Configurar integración con Jira? [y/n]: n

✅ Credenciales cifradas y almacenadas.
   Los valores no se pueden recuperar en texto plano.
```

No hay contraseña maestra. La clave de cifrado se deriva del identificador de hardware de tu Mac, así que los tokens solo son descifrables en esta máquina.

### 2. Configuración operativa

```bash
mkdir -p ~/.tempo-cli
cp config/example.yaml ~/.tempo-cli/config.yaml
```

Edita `config.yaml` con tus alias, templates y preferencias.

## Uso

```bash
# No pide contraseña — descifra automáticamente
tempo log pipeline 4h "Desarrollo de feature"
tempo fill --week
tempo status
```

## Comandos

| Comando | Descripción |
|---------|-------------|
| `tempo auth setup` | Configura credenciales (una sola vez) |
| `tempo auth status` | Verifica estado de autenticación |
| `tempo auth reset` | Elimina credenciales (irreversible) |
| `tempo log <issue> <hours> [desc]` | Registra tiempo en un ticket |
| `tempo fill` | Aplica template para llenar el día |
| `tempo status` | Muestra worklogs del día |
| `tempo calendar` | Muestra eventos de calendario |
| `tempo delete <id>` | Elimina un worklog |
| `tempo timesheet status` | Estado de aprobación del periodo |
| `tempo timesheet submit` | Envía timesheet para aprobación |
| `tempo timesheet recall` | Reabre un timesheet enviado |
| `tempo config show` | Muestra configuración operativa |
| `tempo config clientes` | Muestra/limpia el cache de clientes aprendido |

## Resolución automática del cliente

En instancias de Tempo con un atributo obligatorio de tipo cuenta (ej. "Cliente"),
la app web lo auto-completa al reconocer el issue. La CLI replica esto sin necesitar
permisos adicionales sobre las cuentas de Tempo, resolviendo el valor en este orden:

1. **Worklog previo del mismo issue** — reutiliza el valor ya usado antes
   (incluye worklogs creados por la app web).
2. **Cache local de proyecto** — aprendido de registros anteriores hechos por la
   CLI. Instantáneo, sin llamadas de red.
3. **Worklogs del proyecto en Tempo** — si el cache local no lo tiene, consulta
   Tempo buscando el cliente en otros issues del mismo proyecto (incluyendo los
   registrados por la web). Cubre issues nuevos en proyectos con actividad previa
   aunque nunca hayas registrado en ellos vía CLI.
4. **Config** — valor manual en `frequent_issues[].attributes` como último recurso.

Cada vez que se resuelve el cliente (por cualquier nivel), se guarda en el cache
local `~/.tempo-cli/client_cache.json`, de modo que las ejecuciones futuras del
mismo proyecto se resuelven al instante sin volver a consultar Tempo/Jira.

```bash
# Ver clientes aprendidos por proyecto
tempo config clientes

# Vaciar el cache
tempo config clientes --clear
```

### Timesheet (envío de periodos)

```bash
# Ver estado de aprobación de la semana actual
tempo timesheet status --week

# Ver estado de un periodo específico
tempo timesheet status --from 2026-08-01 --to 2026-08-15

# Enviar semana actual para aprobación
tempo timesheet submit --week

# Enviar periodo con comentario
tempo timesheet submit --from 2026-08-01 --to 2026-08-15 -c "Periodo completo"

# Enviar sin confirmación (--yes)
tempo timesheet submit --week -y

# Reabrir un timesheet enviado (solo si no fue aprobado)
tempo timesheet recall --week
```

## Seguridad

- Cifrado **Fernet** (AES-128-CBC + HMAC-SHA256)
- Clave derivada del **Machine ID** del hardware con PBKDF2 (480K iteraciones)
- Las credenciales **no son portables** — solo funcionan en esta máquina
- Los tokens **no se pueden recuperar** en texto plano
- Archivo cifrado con permisos `600`, directorio con `700`
- Sin contraseña maestra, sin `.env`, sin texto plano en ningún lado

## Desinstalación

### Opción A — Doble click

Haz doble click en **`uninstall.command`**

### Opción B — Desde terminal

```bash
pipx uninstall tempo-cli
rm -rf ~/.tempo-cli
```
