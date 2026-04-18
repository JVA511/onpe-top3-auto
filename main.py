import requests
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
import os
import json
import re

# CONFIGURACIÓN
URL_ONPE = "https://resultadoelectoral.onpe.gob.pe/main/presidenciales"
SHEET_NAME = "ONPE Top 3"

def votos_a_int(txt: str) -> int:
    return int(txt.replace("'", "").replace("’", "").replace(",", "").replace(".", "").strip())

def pct_a_float(txt: str) -> float:
    return float(txt.replace("%", "").replace(",", ".").strip())

def obtener_top3():
    api_key = os.environ.get("ZENROWS_API_KEY")
    if not api_key:
        raise Exception("Falta la API Key de ZenRows en los Secrets.")

    print("Solicitando datos a través de ZenRows...")
    
    # Parámetros más robustos para evitar el error 422
    params = {
        'url': URL_ONPE,
        'apikey': api_key,
        'js_render': 'true',
        'wait': '15000', # Esperamos 15 segundos exactos a que cargue todo el JS
        'premium_proxy': 'true',
        'proxy_country': 'pe',
        'window_width': '1600',
        'window_height': '1200'
    }
    
    response = requests.get('https://api.zenrows.com/v1/', params=params)
    
    if response.status_code != 200:
        raise Exception(f"Error de ZenRows: {response.status_code} - {response.text}")

    soup = BeautifulSoup(response.content, "lxml")
    texto = soup.get_text("\n", strip=True)
    lineas = texto.splitlines()

    candidatos = []
    for i, linea in enumerate(lineas):
        if "Cantidad de votos:" in linea:
            votos_texto = linea.replace("Cantidad de votos:", "").strip()
            if not votos_texto and (i + 1) < len(lineas):
                votos_texto = lineas[i + 1].strip()

            try:
                votos = votos_a_int(votos_texto)
            except ValueError:
                continue

            porcentajes = []
            partido, nombre = None, None

            for j in range(i - 1, max(-1, i - 15), -1):
                txt = lineas[j].strip()
                if not txt or re.fullmatch(r"[0-9\s'’.,]+", txt): continue
                if "votos" in txt.lower() or "presidencia" in txt.lower(): continue
                
                if "%" in txt:
                    porcentajes.append(pct_a_float(txt))
                    continue

                if len(porcentajes) >= 2:
                    if not partido: partido = txt; continue
                    if not nombre: nombre = txt; break 

            if nombre and partido and len(porcentajes) >= 2:
                candidatos.append({"nombre": nombre, "partido": partido, "votos": votos, "pct": porcentajes[1]})

    unicos = []
    vistos = set()
    for c in candidatos:
        if (c["nombre"], c["partido"]) not in vistos:
            vistos.add((c["nombre"], c["partido"]))
            unicos.append(c)

    unicos.sort(key=lambda x: x["votos"], reverse=True)
    return unicos[:3]

def conectar():
    creds_json = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(creds_json, scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
    return gspread.authorize(creds).open(SHEET_NAME)

def guardar(top3):
    sheet = conectar()
    resumen, historico = sheet.worksheet("Resumen"), sheet.worksheet("Historico")
    p1, p2, p3 = top3
    lima = timezone(timedelta(hours=-5))
    fecha = datetime.now(lima).strftime("%d/%m/%Y %H:%M:%S")
    fila = [fecha, p1["partido"], p2["partido"], p3["partido"], p1["votos"], p2["votos"], p3["votos"], p1["pct"], p2["pct"], p3["pct"], abs(p2["votos"] - p3["votos"]), round(abs(p2["pct"] - p3["pct"]), 3)]
    resumen.update("A2:L2", [fila])
    historico.append_row(fila, value_input_option="USER_ENTERED")

def main():
    print("Ejecutando script...")
    top3 = obtener_top3()
    
    if not top3:
        raise Exception("El script no pudo extraer ningún dato de la página.")
        
    print(f"Top 1 detectado: {top3[0]['nombre']}")
    guardar(top3)
    print("¡Datos guardados correctamente en Sheets!")

if __name__ == "__main__":
    main()
