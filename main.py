import requests
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
import os
import json
import re
import time

# --- CONFIGURACIÓN ---
URL_WEB = "https://resultadoelectoral.onpe.gob.pe/main/presidenciales"
SHEET_NAME = "ONPE Top 3"
BASE_API = "https://resultadoelectoral.onpe.gob.pe/presentacion-backend"

VISTAS_API = {
    "peru": f"{BASE_API}/resumen-general/totales?idAmbitoGeografico=1&idEleccion=10&tipoFiltro=ambito_geografico",
    "extranjero": f"{BASE_API}/resumen-general/totales?idAmbitoGeografico=2&idEleccion=10&tipoFiltro=ambito_geografico",
    "todos": f"{BASE_API}/resumen-general/totales?idEleccion=10&tipoFiltro=eleccion"
}

# --- HERRAMIENTAS DE CONVERSIÓN ---
def c_int(v): return int(str(v).replace("'", "").replace("’", "").replace(",", "").replace(".", "").strip())
def c_float(v): return float(str(v).replace("%", "").replace(",", ".").strip())

# --- BLOQUE 1: TOP 3 (PLAYWRIGHT) ---
def obtener_top3():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        print("🌐 Abriendo web para Top 3...")
        page.goto(URL_WEB, wait_until="networkidle", timeout=60000)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(5000)
        html = page.content()
        browser.close()

    soup = BeautifulSoup(html, "lxml")
    lineas = soup.get_text("\n", strip=True).splitlines()
    candidatos = []
    
    for i, linea in enumerate(lineas):
        if "Cantidad de votos:" in linea:
            v_txt = linea.replace("Cantidad de votos:", "").strip() or lineas[i+1].strip()
            votos = c_int(v_txt)
            porcentajes, partido, nombre = [], None, None
            for j in range(i - 1, max(-1, i - 15), -1):
                txt = lineas[j].strip()
                if not txt or re.fullmatch(r"[0-9\s'’.,]+", txt): continue
                if any(x in txt.lower() for x in ["votos", "presidencia"]): continue
                if "%" in txt:
                    porcentajes.append(c_float(txt))
                    continue
                if len(porcentajes) >= 2:
                    if not partido: partido = txt
                    elif not nombre: nombre = txt; break 
            if nombre and partido and len(porcentajes) >= 2:
                candidatos.append({"partido": partido, "votos": votos, "pct": porcentajes[1]})

    candidatos.sort(key=lambda x: x["votos"], reverse=True)
    return candidatos[:3]

# --- BLOQUE 2: ACTAS (ZENROWS API) ---
def obtener_actas(api_key):
    datos_actas = {}
    for nombre, url in VISTAS_API.items():
        print(f"📡 Descargando datos de: {nombre.upper()}...")
        params = {'url': url, 'apikey': api_key, 'premium_proxy': 'true', 'proxy_country': 'pe', 'antibot': 'true'}
        r = requests.get('https://api.zenrows.com/v1/', params=params, timeout=45)
        if r.status_code == 200:
            d = r.json()['data']
            datos_actas[nombre] = [d['actasContabilizadas'], d['contabilizadas'], d['enviadasJee'], d['pendientesJee']]
            print(f"✅ Descarga completada: {nombre}")
        time.sleep(1)
    return datos_actas

# --- EJECUCIÓN PRINCIPAL ---
def main():
    api_key = os.environ.get("ZENROWS_API_KEY")
    print("🚀 Iniciando proceso unificado...\n")
    
    # 1. Ejecutar ambos procesos
    top3 = obtener_top3()
    data_actas = obtener_actas(api_key)

    if not top3 or len(data_actas) < 3:
        print("🛑 Error en la recolección de datos.")
        return

    # 2. Preparar la fila (A hasta X)
    lima = timezone(timedelta(hours=-5))
    fecha = datetime.now(lima).strftime("%d/%m/%Y %H:%M:%S")
    p1, p2, p3 = top3
    dp, de, dt = data_actas["peru"], data_actas["extranjero"], data_actas["todos"]

    fila = [
        fecha, 
        p1["partido"], p2["partido"], p3["partido"],
        p1["votos"], p2["votos"], p3["votos"],
        p1["pct"], p2["pct"], p3["pct"],
        abs(p2["votos"] - p3["votos"]), round(abs(p2["pct"] - p3["pct"]), 3),
        # Columnas M a X (Actas)
        c_float(dt[0]), c_float(dp[0]), c_float(de[0]),
        c_int(dt[1]), c_int(dt[2]), c_int(dt[3]),
        c_int(dp[1]), c_int(dp[2]), c_int(dp[3]),
        c_int(de[1]), c_int(de[2]), c_int(de[3])
    ]

    # 3. Subida única a Sheets
    try:
        creds_json = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
        creds = Credentials.from_service_account_info(creds_json, scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        sheet = gspread.authorize(creds).open(SHEET_NAME)
        
        sheet.worksheet("Resumen").update(range_name="A2:X2", values=[fila])
        sheet.worksheet("Historico").append_row(fila, value_input_option="USER_ENTERED")
        print(f"\n✅ ¡ÉXITO! Fila completa subida (Candidatos + Actas).")
    except Exception as e:
        print(f"⚠️ Error en Sheets: {e}")

if __name__ == "__main__":
    main()
