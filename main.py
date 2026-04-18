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
    num = re.search(r"(\d+[\.,]\d+)", txt)
    return float(num.group(1).replace(",", ".")) if num else 0.0

def extraer_datos_pagina(html):
    soup = BeautifulSoup(html, "lxml")
    texto = soup.get_text("\n", strip=True)
    lineas = texto.splitlines()

    avance_actas = 0.0
    for i, linea in enumerate(lineas):
        if "Actas contabilizadas" in linea:
            for k in range(1, 5):
                if (i + k) < len(lineas) and "%" in lineas[i + k]:
                    avance_actas = pct_a_float(lineas[i + k])
                    break
            break

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
    # Usamos selectores mucho más potentes y específicos
    vistas_config = {
        "TODOS": None,
        "PERU": [
            {"click": "button.dropdown-toggle:has-text('TODOS')"}, # Clic al botón que marcaste en rojo
            {"wait": 3000}, # Esperamos a que el menú se abra
            {"click": "ul.dropdown-menu a:has-text('PERÚ')"}, # Clic al link exacto de Perú
            {"wait": 8000} # Espera larga para que los números cambien
        ],
        "EXTRANJERO": [
            {"click": "button.dropdown-toggle:has-text('TODOS')"},
            {"wait": 3000},
            {"click": "ul.dropdown-menu a:has-text('EXTRANJERO')"},
            {"wait": 8000}
        ]
    }
    
    resultados = {}
    top3_final = []

    for nombre_vista, pasos in vistas_config.items():
        print(f"Iniciando captura de {nombre_vista}...")
        
        params = {
            'url': URL_ONPE,
            'apikey': api_key,
            'js_render': 'true',
            'premium_proxy': 'true',
            'proxy_country': 'pe',
            'wait': '10000'
        }
        
        if pasos:
            params['js_instructions'] = json.dumps(pasos)
        
        response = requests.get('https://api.zenrows.com/v1/', params=params)
        
        if response.status_code == 200:
            cands, avance = extraer_datos_pagina(response.content)
            resultados[nombre_vista] = avance
            if nombre_vista == "TODOS":
                top3_final = cands
            print(f"Dato obtenido para {nombre_vista}: {avance}%")
        else:
            print(f"Fallo en {nombre_vista}. Status: {response.status_code}")
            resultados[nombre_vista] = 0.0

    # Limpieza de duplicados
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
    
    fila = [
        fecha, p1["partido"], p2["partido"], p3["partido"], 
        p1["votos"], p2["votos"], p3["votos"], 
        p1["pct"], p2["pct"], p3["pct"], 
        abs(p2["votos"] - p3["votos"]), round(abs(p2["pct"] - p3["pct"]), 3),
        avances.get("TODOS", 0), avances.get("PERU", 0), avances.get("EXTRANJERO", 0)
    ]
    
    # Arreglo del orden de argumentos para evitar el DeprecationWarning
    resumen.update(range_name="A2:O2", values=[fila])
    historico.append_row(fila, value_input_option="USER_ENTERED")

def main():
    try:
        api_key = os.environ.get("ZENROWS_API_KEY")
        top3, avances = obtener_todo(api_key)
        if not top3: raise Exception("Datos incompletos.")
        guardar(top3, avances)
        print(f"OK. T: {avances['TODOS']}% | P: {avances['PERU']}% | E: {avances['EXTRANJERO']}%")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
