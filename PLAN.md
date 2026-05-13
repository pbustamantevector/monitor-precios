# Plan: Migrar precios.ipynb → precios.py con GitHub Actions

## Contexto

El notebook `precios.ipynb` monitorea precios de acciones chilenas y estadounidenses y envía mensajes de WhatsApp vía PyWhatKit (requiere Chrome abierto). Este plan migra el sistema a una arquitectura moderna que:
- Corre en la **nube (GitHub Actions)** — funciona con el PC apagado
- Usa **CallMeBot** para WhatsApp (sin browser, sin Chrome)
- Agrega **resumen por email** al cierre del mercado
- Hace las acciones/ETFs **configurables via `config.yaml`**

---

## Archivos a crear

```
95. Precios informar/
├── precios.py                          # Script principal (reemplaza notebook)
├── config.yaml                         # Acciones/ETFs configurables
├── requirements.txt                    # Dependencias Python
├── .gitignore                          # Excluir archivos sensibles
├── PLAN.md                             # Este archivo
└── .github/
    └── workflows/
        └── precios.yml                 # Workflow de GitHub Actions
```

---

## 1. `config.yaml`

Configuración centralizada. Editar aquí para agregar/quitar símbolos sin tocar el código.

```yaml
whatsapp:
  phone: "+56995959596"

email:
  to: "bustamante.pablo@uc.cl"
  from_address: ""   # Gmail del remitente (configurar en GitHub Secrets)

stocks:
  usa:
    acciones:
      - AAPL
      - MSFT
      - GOOGL
      - AMZN
      - TSLA
      - NVDA
      - NBIS
      - AMD
    etfs:
      - SPY
      - QQQ
      - IWM
  chile:
    acciones:
      - SQM-B
      - COPEC
      - CHILE
      - FALABELLA
      - CENCOSUD
      - BCI
      - BSANTANDER
      - CAP
      - CMPC
      - LTM
      - COLBUN
      - ENELAM
      - CCU
    etfs:
      - CFIETFIPSA
      - CFINASDAQ

mercado:
  horario_inicio: "09:00"
  horario_fin: "16:00"
  timezone: "America/Santiago"
```

---

## 2. `precios.py` — estructura

### Imports y carga de config
- `yfinance`, `requests`, `smtplib`, `yaml`, `argparse`, `logging`
- `load_config(path)` — carga `config.yaml`
- Logging con formato timestamp

### Funciones de datos
- `obtener_precio(symbol, es_chile=False)` — retorna `{precio, cambio_pct, moneda, error}`
  - Acciones chilenas usan sufijo `.SN` automáticamente
  - Fallback: intenta datos 5m → diarios

### Funciones de mensaje
- `crear_mensaje_whatsapp(config, precios)` — formatea con emojis (📈📉➡️), secciones: USA acciones, USA ETFs, Chile acciones, Chile ETFs
- `crear_cuerpo_email(config, precios)` — HTML con tabla de precios, variaciones coloreadas (verde/rojo), timestamp

### Funciones de envío
- `enviar_whatsapp(mensaje, phone, api_key)` — `requests.get` a `api.callmebot.com`
- `enviar_email(asunto, cuerpo_html, cfg_email, password)` — `smtplib.SMTP` con Gmail App Password

### `main()`
```
--modo reporte        → obtener precios + enviar WhatsApp
--modo resumen-final  → obtener precios + enviar WhatsApp + enviar email
```

Credenciales desde variables de entorno (nunca en el código):
- `CALLMEBOT_API_KEY`
- `GMAIL_USER`
- `GMAIL_APP_PASSWORD`

---

## 3. `.github/workflows/precios.yml`

```yaml
name: Monitor Precios

on:
  schedule:
    # Cada 30 min, 9:00-16:00 CLT (UTC-4 en invierno = 13:00-20:00 UTC)
    - cron: '0,30 13-19 * * 1-5'
    - cron: '0 20 * * 1-5'        # 16:00 CLT = resumen final
  workflow_dispatch:                # ejecución manual desde GitHub

jobs:
  monitor:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - name: Determinar modo
        id: modo
        run: |
          HORA=$(date -u +%H:%M)
          if [[ "$HORA" == "20:00" ]]; then
            echo "modo=resumen-final" >> $GITHUB_OUTPUT
          else
            echo "modo=reporte" >> $GITHUB_OUTPUT
          fi
      - name: Ejecutar script
        run: python precios.py --modo ${{ steps.modo.outputs.modo }}
        env:
          CALLMEBOT_API_KEY: ${{ secrets.CALLMEBOT_API_KEY }}
          GMAIL_USER: ${{ secrets.GMAIL_USER }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
```

---

## 4. `requirements.txt`

```
yfinance>=0.2.40
requests>=2.31.0
pyyaml>=6.0
pandas>=2.0.0
```

---

## Mejoras respecto al notebook

| Aspecto | Notebook (antes) | Script (después) |
|---|---|---|
| WhatsApp | PyWhatKit + Chrome | CallMeBot HTTP API |
| Configuración | Hardcodeada en celdas | `config.yaml` editable |
| Ejecución | Loop infinito manual | GitHub Actions (cloud) |
| Email | No había | Resumen HTML al cierre |
| ETFs | Mezclados con acciones | Sección separada |
| Dependencias | pywhatkit, beautifulsoup4, schedule | Solo yfinance, requests, pyyaml |
| Logs | print() | logging con timestamp |

---

## Setup manual (una sola vez)

### 1. CallMeBot (WhatsApp)
1. Agregar `+34 644 88 29 98` a tus contactos de WhatsApp
2. Enviarle el mensaje: `I allow callmebot to send me messages`
3. Recibirás una API key por WhatsApp — guardarla

### 2. Gmail App Password
1. Ir a tu cuenta Gmail → Seguridad → Verificación en 2 pasos (activar si no está)
2. Seguridad → Contraseñas de aplicación → Crear una para "Monitor Precios"
3. Guardar la contraseña generada (16 caracteres)

### 3. GitHub
1. Crear repositorio **privado** en github.com
2. Subir todos los archivos (`git push`)
3. Ir a Settings → Secrets and variables → Actions → New repository secret:
   - `CALLMEBOT_API_KEY` — la API key de CallMeBot
   - `GMAIL_USER` — tu dirección Gmail (ej: nombre@gmail.com)
   - `GMAIL_APP_PASSWORD` — la contraseña de aplicación generada

---

## Verificación

```bash
# Test local (definir variables de entorno primero)
set CALLMEBOT_API_KEY=tu_key
set GMAIL_USER=tu@gmail.com
set GMAIL_APP_PASSWORD=tu_app_password

python precios.py --modo reporte          # WhatsApp llega en ~30 segundos
python precios.py --modo resumen-final    # WhatsApp + email a bustamante.pablo@uc.cl
```

En GitHub Actions: ir a Actions → Monitor Precios → Run workflow para forzar ejecución y ver logs en tiempo real.
