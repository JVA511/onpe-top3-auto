import requests
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
import os
import json
import re

# CONFIGURACIÓN
url = "https://resultadosegundavuelta.onpe.gob.pe/presentacion-backend/resumen-general/participantes?idEleccion=10&tipoFiltro=eleccion"
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
    return unicos[:2]

def conectar():
    creds_json = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(creds_json, scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
    return gspread.authorize(creds).open(SHEET_NAME)

def guardar(top2):
    sheet = conectar()
    resumen = sheet.worksheet("Resumen")
    historico = sheet.worksheet("Historico")
    
    # Solo desempaquetamos a los 2 candidatos
    p1, p2 = top2 
    lima = timezone(timedelta(hours=-5))
    fecha = datetime.now(lima).strftime("%d/%m/%Y %H:%M:%S")
    
    # LA NUEVA MATEMÁTICA: p1 vs p2 (Ocupa exactamente 9 elementos)
    fila = [
        fecha, 
        p1["partido"], p2["partido"], 
        p1["votos"], p2["votos"], 
        p1["pct"], p2["pct"], 
        abs(p1["votos"] - p2["votos"]), 
        round(abs(p1["pct"] - p2["pct"]), 3)
    ]

    # Actualiza el Resumen (A2:I2)
    resumen.update(range_name="A2:I2", values=[fila])
    
    # --- EL TRUCO DEL FRANCOTIRADOR ---
    col_a = historico.col_values(1)
    siguiente_fila = len(col_a) + 1 
    
    # Inyectamos a la fuerza desde la A hasta la I
    rango_historico = f"A{siguiente_fila}:I{siguiente_fila}"
    historico.update(range_name=rango_historico, values=[fila])
    
    print(f"\nDatos subidos a la Fila {siguiente_fila} con éxito.")

def main():
    print("Ejecutando script...")
    top2 = obtener_top3() # Sigue usando el mismo nombre de función, pero trae 2
    
    if not top2 or len(top2) < 2:
        raise Exception("El script no pudo extraer los 2 candidatos.")
        
    print(f"Top 1 detectado: {top2[0]['nombre']}")
    guardar(top2)
    print("¡Datos guardados correctamente en Sheets!")

if __name__ == "__main__":
    main()
