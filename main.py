import requests
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
import os
import json
import re

# CONFIGURACIÓN
BASE_URL = "https://resultadoelectoral.onpe.gob.pe/main/presidenciales"
SHEET_NAME = "ONPE Top 3"

def votos_a_int(txt: str) -> int:
    return int(txt.replace("'", "").replace("’", "").replace(",", "").replace(".", "").strip())

def pct_a_float(txt: str) -> float:
    # Limpia el texto para dejar solo el número y convertir a float
    num = re.search(r"(\d+[\.,]\d+)", txt)
    if num:
        return float(num.group(1).replace(",", "."))
    return 0.0

def extraer_datos_pagina(html):
    soup = BeautifulSoup(html, "lxml")
    texto = soup.get_text("\n", strip=True)
    lineas = texto.splitlines()

    # 1. Extraer el porcentaje de avance de actas
    avance_actas = 0.0
    for i, linea in enumerate(lineas):
        if "Actas contabilizadas" in linea:
            # Buscamos el porcentaje en las líneas siguientes
            for k in range(1, 5):
                if (i + k) < len(lineas) and "%" in lineas[i + k]:
                    avance_actas = pct_a_float(lineas[i + k])
                    break
            break

    # 2. Extraer candidatos (Solo si es la vista 'TODOS' para el Top 3)
    candidatos = []
    for i, linea in enumerate(lineas):
        if "Cantidad de votos:" in linea:
            votos_texto = linea.replace("Cantidad de votos:", "").strip()
            if not votos_texto and (i + 1) < len(lineas):
                votos_texto = lineas[i + 1].strip()

            try:
                votos = votos_a_int(votos_texto)
            except:
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

    return candidatos, avance_actas

def obtener_todo(api_key):
    vistas = {
        "TODOS": BASE_URL,
        "PERU": f"{BASE_URL}/P",
        "EXTRANJERO": f"{BASE_URL}/E"
    }
    
    resultados = {}
    top3_final = []

    for nombre_vista, url in vistas.items():
        print(f"Consultando vista: {nombre_vista}...")
        params = {
            'url': url,
            'apikey': api_key,
            'js_render': 'true',
            'wait': '15000',
            'premium_proxy': 'true',
            'proxy_country': 'pe'
        }
        
        response = requests.get('https://api.zenrows.com/v1/', params=params)
        if response.status_code == 200:
            cands, avance = extraer_datos_pagina(response.content)
            resultados[nombre_vista] = avance
            if nombre_vista == "TODOS":
                top3_final = cands
        else:
            print(f"Error en {nombre_vista}: {response.status_code}")
            resultados[nombre_vista] = 0.0

    # Limpiar duplicados del Top 3
    unicos = []
    vistos = set()
    for c in top3_final:
        if (c["nombre"], c["partido"]) not in vistos:
            vistos.add((c["nombre"], c["partido"]))
            unicos.append(c)
    unicos.sort(key=lambda x: x["votos"], reverse=True)

    return unicos[:3], resultados

def conectar():
    creds_json = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(creds_json, scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
    return gspread.authorize(creds).open(SHEET_NAME)

def guardar(top3, avances):
    sheet = conectar()
    resumen, historico = sheet.worksheet("Resumen"), sheet.worksheet("Historico")
    
    p1, p2, p3 = top3
    lima = timezone(timedelta(hours=-5))
    fecha = datetime.now(lima).strftime("%d/%m/%Y %H:%M:%S")
    
    # Fila con los nuevos datos de avance al final (Columnas M, N, O)
    fila = [
        fecha, 
        p1["partido"], p2["partido"], p3["partido"], 
        p1["votos"], p2["votos"], p3["votos"], 
        p1["pct"], p2["pct"], p3["pct"], 
        abs(p2["votos"] - p3["votos"]), 
        round(abs(p2["pct"] - p3["pct"]), 3),
        avances.get("TODOS", 0),
        avances.get("PERU", 0),
        avances.get("EXTRANJERO", 0)
    ]
    
    # Actualizamos el rango A2:O2 (ahora son 15 columnas)
    resumen.update("A2:O2", [fila])
    historico.append_row(fila, value_input_option="USER_ENTERED")

def main():
    try:
        api_key = os.environ.get("ZENROWS_API_KEY")
        top3, avances = obtener_todo(api_key)
        if not top3: raise Exception("No se pudo obtener el Top 3.")
        
        guardar(top3, avances)
        print(f"Éxito. Avance Total: {avances['TODOS']}% | Perú: {avances['PERU']}% | Extranjero: {avances['EXTRANJERO']}%")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
