import requests
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timezone, timedelta
import os
import json
import time

# URLs de la API
BASE_API = "https://resultadoelectoral.onpe.gob.pe/presentacion-backend/resumen-general"
URLS = {
    "TODOS": f"{BASE_API}/totales?idEleccion=10&tipoFiltro=eleccion",
    "PERU": f"{BASE_API}/totales?idAmbitoGeografico=1&idEleccion=10&tipoFiltro=ambito_geografico",
    "EXTRANJERO": f"{BASE_API}/totales?idAmbitoGeografico=2&idEleccion=10&tipoFiltro=ambito_geografico",
    "CANDIDATOS": f"{BASE_API}/participantes-ubicacion-geografica-nombre?idEleccion=10&tipoFiltro=eleccion"
}

SHEET_NAME = "ONPE Top 3"

def obtener_datos_api(url, api_key, nombre):
    print(f"Llamando a {nombre}...")
    params = {
        'url': url,
        'apikey': api_key,
        'premium_proxy': 'true',
        'proxy_country': 'pe'
    }
    # User-agent para parecer un navegador real
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'}
    
    try:
        response = requests.get('https://api.zenrows.com/v1/', params=params, headers=headers, timeout=30)
        if response.status_code != 200:
            print(f"Error {response.status_code} en {nombre}")
            return None
        return response.json()
    except Exception as e:
        print(f"Error crítico al leer JSON de {nombre}: {e}")
        if response: print(f"Respuesta recibida: {response.text[:200]}")
        return None

def conectar_google():
    creds_json = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(creds_json, scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
    return gspread.authorize(creds).open(SHEET_NAME)

def main():
    try:
        api_key = os.environ.get("ZENROWS_API_KEY")
        
        # 1. Capturar datos con pausas de seguridad para no saturar la API
        res_todos = obtener_datos_api(URLS["TODOS"], api_key, "TODOS")
        time.sleep(2)
        res_peru = obtener_datos_api(URLS["PERU"], api_key, "PERU")
        time.sleep(2)
        res_ext = obtener_datos_api(URLS["EXTRANJERO"], api_key, "EXTRANJERO")
        time.sleep(2)
        res_cands = obtener_datos_api(URLS["CANDIDATOS"], api_key, "CANDIDATOS")

        # Verificación de seguridad
        if not all([res_todos, res_peru, res_ext, res_cands]):
            raise Exception("Una o más llamadas a la API fallaron (ver logs arriba).")

        # 2. Extraer datos (usando .get para evitar KeyErrors)
        pct_todos = res_todos['data']['actasContabilizadas']
        pct_peru = res_peru['data']['actasContabilizadas']
        pct_ext = res_ext['data']['actasContabilizadas']
        top3 = res_cands['data']['rVotacion'][:3]
        
        # 3. Preparar fila
        lima = timezone(timedelta(hours=-5))
        fecha = datetime.now(lima).strftime("%d/%m/%Y %H:%M:%S")
        p1, p2, p3 = top3
        
        def clean_num(v): return int(str(v).replace(',', '').replace('.', '').replace("'", ""))
        def clean_pct(v): return float(str(v).replace(',', '.'))

        fila = [
            fecha, p1['nombre_organizacion'], p2['nombre_organizacion'], p3['nombre_organizacion'],
            clean_num(p1['votos_total']), clean_num(p1['votos_total']), clean_num(p1['votos_total']), # Ajustar a p1, p2, p3
            clean_pct(p1['porcentaje_votos_validos']), clean_pct(p2['porcentaje_votos_validos']), clean_pct(p3['porcentaje_votos_validos']),
            clean_num(p2['votos_total']) - clean_num(p3['votos_total']),
            round(abs(clean_pct(p2['porcentaje_votos_validos']) - clean_pct(p3['porcentaje_votos_validos'])), 3),
            clean_pct(pct_todos), clean_pct(pct_peru), clean_pct(pct_ext)
        ]

        # 4. Guardar
        sheet = conectar_google()
        sheet.worksheet("Resumen").update(range_name="A2:O2", values=[fila])
        sheet.worksheet("Historico").append_row(fila, value_input_option="USER_ENTERED")
        
        print(f"¡Éxito! Avance Total: {pct_todos}%")

    except Exception as e:
        print(f"Error técnico: {e}")

if __name__ == "__main__":
    main()
