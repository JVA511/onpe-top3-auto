import requests
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timezone, timedelta
import os
import json

# CONFIGURACIÓN DE LAS APIs (Basado en tu descubrimiento)
BASE_API = "https://resultadoelectoral.onpe.gob.pe/presentacion-backend/resumen-general"
URLS = {
    "TODOS": f"{BASE_API}/totales?idEleccion=10&tipoFiltro=eleccion",
    "PERU": f"{BASE_API}/totales?idAmbitoGeografico=1&idEleccion=10&tipoFiltro=ambito_geografico",
    "EXTRANJERO": f"{BASE_API}/totales?idAmbitoGeografico=2&idEleccion=10&tipoFiltro=ambito_geografico",
    "CANDIDATOS": f"{BASE_API}/participantes-ubicacion-geografica-nombre?idEleccion=10&tipoFiltro=eleccion"
}

SHEET_NAME = "ONPE Top 3"

def obtener_datos_api(url, api_key):
    # Ya NO necesitamos js_render ni wait porque es un JSON directo
    params = {
        'url': url,
        'apikey': api_key,
        'premium_proxy': 'true',
        'proxy_country': 'pe'
    }
    response = requests.get('https://api.zenrows.com/v1/', params=params)
    return response.json() if response.status_code == 200 else None

def conectar_google():
    creds_json = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(creds_json, scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
    return gspread.authorize(creds).open(SHEET_NAME)

def main():
    try:
        api_key = os.environ.get("ZENROWS_API_KEY")
        
        # 1. Obtener porcentajes de avance
        pct_todos = obtener_datos_api(URLS["TODOS"], api_key)['actas']['porcentajeContabilizado']
        pct_peru = obtener_datos_api(URLS["PERU"], api_key)['actas']['porcentajeContabilizado']
        pct_ext = obtener_datos_api(URLS["EXTRANJERO"], api_key)['actas']['porcentajeContabilizado']
        
        # 2. Obtener votos del Top 3 (de la API de participantes)
        data_cands = obtener_datos_api(URLS["CANDIDATOS"], api_key)
        # Asumiendo que vienen ordenados por votos, tomamos los 3 primeros
        top3 = data_cands['rVotacion'][:3] 
        
        # 3. Preparar la fila para Google Sheets
        lima = timezone(timedelta(hours=-5))
        fecha = datetime.now(lima).strftime("%d/%m/%Y %H:%M:%S")
        
        p1, p2, p3 = top3
        # Limpiamos los porcentajes (quitar el % y pasar a float)
        def clean_pct(val): return float(val.replace(',', '.'))

        fila = [
            fecha, 
            p1['nombre_organizacion'], p2['nombre_organizacion'], p3['nombre_organizacion'],
            int(p1['votos_total'].replace(',', '')), int(p2['votos_total'].replace(',', '')), int(p3['votos_total'].replace(',', '')),
            clean_pct(p1['porcentaje_votos_validos']), clean_pct(p2['porcentaje_votos_validos']), clean_pct(p3['porcentaje_votos_validos']),
            int(p2['votos_total'].replace(',', '')) - int(p3['votos_total'].replace(',', '')),
            round(abs(clean_pct(p2['porcentaje_votos_validos']) - clean_pct(p3['porcentaje_votos_validos'])), 3),
            clean_pct(pct_todos), clean_pct(pct_peru), clean_pct(pct_ext)
        ]

        # 4. Guardar en Sheets
        sheet = conectar_google()
        resumen = sheet.worksheet("Resumen")
        historico = sheet.worksheet("Historico")
        
        resumen.update(range_name="A2:O2", values=[fila])
        historico.append_row(fila, value_input_option="USER_ENTERED")
        
        print(f"Éxito Total: {pct_todos} | Perú: {pct_peru} | Ext: {pct_ext}")

    except Exception as e:
        print(f"Error técnico: {e}")

if __name__ == "__main__":
    main()
