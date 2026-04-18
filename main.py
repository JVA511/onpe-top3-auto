import requests
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timezone, timedelta
import os
import json

# URLs de la API (Tus descubrimientos)
BASE_API = "https://resultadoelectoral.onpe.gob.pe/presentacion-backend/resumen-general"
URLS = {
    "TODOS": f"{BASE_API}/totales?idEleccion=10&tipoFiltro=eleccion",
    "PERU": f"{BASE_API}/totales?idAmbitoGeografico=1&idEleccion=10&tipoFiltro=ambito_geografico",
    "EXTRANJERO": f"{BASE_API}/totales?idAmbitoGeografico=2&idEleccion=10&tipoFiltro=ambito_geografico",
    "CANDIDATOS": f"{BASE_API}/participantes-ubicacion-geografica-nombre?idEleccion=10&tipoFiltro=eleccion"
}

SHEET_NAME = "ONPE Top 3"

def obtener_datos_api(url, api_key):
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
        
        # 1. Capturar JSONs
        res_todos = obtener_datos_api(URLS["TODOS"], api_key)
        res_peru = obtener_datos_api(URLS["PERU"], api_key)
        res_ext = obtener_datos_api(URLS["EXTRANJERO"], api_key)
        res_cands = obtener_datos_api(URLS["CANDIDATOS"], api_key)

        # 2. Extraer porcentajes usando la ruta de tus capturas: data -> actasContabilizadas
        pct_todos = res_todos['data']['actasContabilizadas']
        pct_peru = res_peru['data']['actasContabilizadas']
        pct_ext = res_ext['data']['actasContabilizadas']
        
        # 3. Extraer candidatos (asumiendo que siguen en 'data' -> 'rVotacion')
        # Si esto falla, revisa el JSON de candidatos igual que hiciste con estos
        top3 = res_cands['data']['rVotacion'][:3]
        
        # 4. Preparar fila
        lima = timezone(timedelta(hours=-5))
        fecha = datetime.now(lima).strftime("%d/%m/%Y %H:%M:%S")
        p1, p2, p3 = top3
        
        def clean_num(v): return int(str(v).replace(',', '').replace('.', ''))
        def clean_pct(v): return float(str(v).replace(',', '.'))

        fila = [
            fecha, p1['nombre_organizacion'], p2['nombre_organizacion'], p3['nombre_organizacion'],
            clean_num(p1['votos_total']), clean_num(p2['votos_total']), clean_num(p3['votos_total']),
            clean_pct(p1['porcentaje_votos_validos']), clean_pct(p2['porcentaje_votos_validos']), clean_pct(p3['porcentaje_votos_validos']),
            clean_num(p2['votos_total']) - clean_num(p3['votos_total']),
            round(abs(clean_pct(p2['porcentaje_votos_validos']) - clean_pct(p3['porcentaje_votos_validos'])), 3),
            clean_pct(pct_todos), clean_pct(pct_peru), clean_pct(pct_ext)
        ]

        # 5. Guardar
        sheet = conectar_google()
        sheet.worksheet("Resumen").update(range_name="A2:O2", values=[fila])
        sheet.worksheet("Historico").append_row(fila, value_input_option="USER_ENTERED")
        
        print(f"¡Éxito! Avance Total: {pct_todos}%")

    except Exception as e:
        print(f"Error técnico: {e}")
        # Si falla, imprimimos el JSON para ver qué pasó
        if 'res_todos' in locals(): print(f"JSON recibido: {res_todos}")

if __name__ == "__main__":
    main()
