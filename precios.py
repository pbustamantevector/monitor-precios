import os
import logging
import argparse
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests
import yaml
import yfinance as yf

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def load_config(path: str = "config.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def obtener_precio(symbol: str, es_chile: bool = False) -> dict:
    ticker_sym = f"{symbol}.SN" if es_chile else symbol
    resultado = {
        "symbol": symbol,
        "precio": None,
        "cambio_pct": 0.0,
        "moneda": "CLP" if es_chile else "USD",
        "error": False,
    }
    try:
        ticker = yf.Ticker(ticker_sym)

        hist = ticker.history(period="1d", interval="5m")
        if not hist.empty and len(hist) >= 2:
            resultado["precio"] = float(hist["Close"].iloc[-1])
            prev_close = float(hist["Close"].iloc[0])
            resultado["cambio_pct"] = (resultado["precio"] - prev_close) / prev_close * 100
            return resultado

        hist = ticker.history(period="5d", interval="1d")
        if not hist.empty:
            resultado["precio"] = float(hist["Close"].iloc[-1])
            if len(hist) >= 2:
                prev_close = float(hist["Close"].iloc[-2])
                resultado["cambio_pct"] = (resultado["precio"] - prev_close) / prev_close * 100
            return resultado

        resultado["error"] = True
    except Exception as exc:
        logging.error("Error obteniendo %s: %s", symbol, exc)
        resultado["error"] = True
    return resultado


def recopilar_precios(cfg: dict) -> dict:
    secciones = {
        "usa_acciones": (cfg["stocks"]["usa"].get("acciones", []), False),
        "usa_etfs":     (cfg["stocks"]["usa"].get("etfs", []),     False),
        "chile_acciones": (cfg["stocks"]["chile"].get("acciones", []), True),
        "chile_etfs":     (cfg["stocks"]["chile"].get("etfs", []),     True),
    }
    precios = {}
    for clave, (simbolos, es_chile) in secciones.items():
        logging.info("Consultando %s (%d símbolos)...", clave, len(simbolos))
        precios[clave] = [obtener_precio(s, es_chile) for s in simbolos]
    return precios


def _emoji(cambio_pct: float) -> str:
    if cambio_pct > 0.05:
        return "📈"
    if cambio_pct < -0.05:
        return "📉"
    return "➡️"


def _formatear_precio(precio: float, moneda: str, con_simbolo: bool = True) -> str:
    if moneda == "CLP":
        fmt = f"{precio:,.0f}".replace(",", ".")
        return f"${fmt}" if con_simbolo else fmt
    fmt = f"{precio:.2f}"
    return f"${fmt}" if con_simbolo else fmt


def _linea_wa(item: dict) -> str:
    if item["error"] or item["precio"] is None:
        return f"❓ {item['symbol']} — sin datos"
    signo = "+" if item["cambio_pct"] >= 0 else ""
    return (
        f"{_emoji(item['cambio_pct'])} {item['symbol']}  "
        f"{_formatear_precio(item['precio'], item['moneda'], con_simbolo=False)}  "
        f"({signo}{item['cambio_pct']:.2f}%)"
    )


def crear_mensaje_whatsapp(precios: dict) -> str:
    ts = datetime.now().strftime("%d/%m/%Y %H:%M")
    lineas = [f"📊 *Precios — {ts}*", ""]

    secciones = [
        ("🇺🇸 *Acciones USA*",   precios["usa_acciones"]),
        ("🇺🇸 *ETFs USA*",       precios["usa_etfs"]),
        ("🇨🇱 *Acciones Chile*", precios["chile_acciones"]),
        ("🇨🇱 *ETFs Chile*",     precios["chile_etfs"]),
    ]
    for titulo, items in secciones:
        if not items:
            continue
        lineas.append(titulo)
        for item in items:
            lineas.append(_linea_wa(item))
        lineas.append("")

    lineas.append("_Actualizado automáticamente_")
    return "\n".join(lineas)


def _fila_email(item: dict) -> str:
    if item["error"] or item["precio"] is None:
        return f"<tr><td>{item['symbol']}</td><td colspan='2' style='color:#7f8c8d'>Sin datos</td></tr>"
    color = "#27ae60" if item["cambio_pct"] >= 0 else "#e74c3c"
    signo = "+" if item["cambio_pct"] >= 0 else ""
    precio_fmt = _formatear_precio(item["precio"], item["moneda"])
    return (
        f"<tr>"
        f"<td style='padding:5px 14px;font-weight:bold'>{item['symbol']}</td>"
        f"<td style='padding:5px 14px;text-align:right'>{precio_fmt}</td>"
        f"<td style='padding:5px 14px;text-align:right;color:{color};font-weight:bold'>"
        f"{signo}{item['cambio_pct']:.2f}%</td>"
        f"</tr>"
    )


def _seccion_email(titulo: str, items: list) -> str:
    if not items:
        return ""
    filas = "".join(_fila_email(i) for i in items)
    return f"""
    <h3 style='margin-top:28px;margin-bottom:6px;color:#2c3e50'>{titulo}</h3>
    <table style='border-collapse:collapse;min-width:340px;font-size:14px'>
      <thead>
        <tr style='background:#2c3e50;color:white'>
          <th style='padding:6px 14px;text-align:left'>Símbolo</th>
          <th style='padding:6px 14px;text-align:right'>Precio</th>
          <th style='padding:6px 14px;text-align:right'>Variación</th>
        </tr>
      </thead>
      <tbody>{filas}</tbody>
    </table>"""


def crear_cuerpo_email(precios: dict) -> str:
    ts = datetime.now().strftime("%d/%m/%Y %H:%M")
    contenido = (
        _seccion_email("🇺🇸 Acciones USA",   precios["usa_acciones"])
        + _seccion_email("🇺🇸 ETFs USA",       precios["usa_etfs"])
        + _seccion_email("🇨🇱 Acciones Chile", precios["chile_acciones"])
        + _seccion_email("🇨🇱 ETFs Chile",     precios["chile_etfs"])
    )
    return f"""
    <html><body style='font-family:Arial,sans-serif;max-width:620px;margin:auto;padding:24px'>
      <h2 style='color:#2c3e50;border-bottom:2px solid #2c3e50;padding-bottom:8px'>
        📊 Resumen de Precios — {ts}
      </h2>
      {contenido}
      <p style='margin-top:36px;color:#95a5a6;font-size:11px'>
        Generado automáticamente · Monitor Precios · GitHub Actions
      </p>
    </body></html>"""


def enviar_whatsapp(mensaje: str, phone: str, api_key: str) -> bool:
    try:
        resp = requests.get(
            "https://api.callmebot.com/whatsapp.php",
            params={"phone": phone, "text": mensaje, "apikey": api_key},
            timeout=30,
        )
        resp.raise_for_status()
        logging.info("WhatsApp enviado a %s", phone)
        return True
    except Exception as exc:
        logging.error("Error enviando WhatsApp: %s", exc)
        return False


def enviar_email(asunto: str, cuerpo_html: str, cfg_email: dict, password: str) -> bool:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = asunto
    msg["From"] = cfg_email["from_address"]
    msg["To"] = cfg_email["to"]
    msg.attach(MIMEText(cuerpo_html, "html", "utf-8"))
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(cfg_email["from_address"], password)
            server.sendmail(cfg_email["from_address"], cfg_email["to"], msg.as_string())
        logging.info("Email enviado a %s", cfg_email["to"])
        return True
    except Exception as exc:
        logging.error("Error enviando email: %s", exc)
        return False


def main():
    parser = argparse.ArgumentParser(description="Monitor de precios bursátiles")
    parser.add_argument(
        "--modo",
        choices=["reporte", "resumen-final"],
        default="reporte",
        help="reporte: WhatsApp | resumen-final: WhatsApp + email",
    )
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    logging.info("Iniciando modo=%s", args.modo)

    precios = recopilar_precios(cfg)

    api_key = os.environ.get("CALLMEBOT_API_KEY", "")
    if api_key:
        mensaje = crear_mensaje_whatsapp(precios)
        logging.info("Mensaje:\n%s", mensaje)
        enviar_whatsapp(mensaje, cfg["whatsapp"]["phone"], api_key)
    else:
        logging.warning("CALLMEBOT_API_KEY no configurada — WhatsApp omitido")

    if args.modo == "resumen-final":
        gmail_user = os.environ.get("GMAIL_USER", "")
        gmail_pass = os.environ.get("GMAIL_APP_PASSWORD", "")
        if gmail_user and gmail_pass:
            cfg["email"]["from_address"] = gmail_user
            ts = datetime.now().strftime("%d/%m/%Y")
            enviar_email(
                f"📊 Resumen Precios {ts}",
                crear_cuerpo_email(precios),
                cfg["email"],
                gmail_pass,
            )
        else:
            logging.warning("Credenciales Gmail no configuradas — email omitido")

    logging.info("Completado.")


if __name__ == "__main__":
    main()
