import requests
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timezone, timedelta
import os
import json
import time

# URLs que te funcionaron en VS Code
BASE_API = "https://resultadoelectoral.onpe.gob.pe/presentacion-backend"
URLS = {
    "VOTOS": f"{BASE_API}/participantes-ubicacion-geografica-nombre?idEleccion=10&tipoFiltro=eleccion",
    "AVANCE_T": f"{BASE_API}/resumen-general/totales?idEleccion=10&tipoFiltro=eleccion",
    "AVANCE_P": f"{BASE_API}/resumen-general/totales?idAmbitoGeografico=1&idEleccion=10&tipoFiltro=ambito_geografico",
    "AVANCE_E": f"{BASE_API}/resumen-general/totales?idAmbitoGeografico=2&idEleccion=10&tipoFiltro=ambito_geografico"
}

def obtener_json(url, api_key):
    # Usamos la configuración exacta de tu VS Code
    params = {
        'url': url,
        'apikey': api_key,
        'premium_proxy': 'true',
        'proxy_country': 'pe'
    }
    try:
        r = requests.get('https://api.zenrows.com/v1/', params=params, timeout=30)
        if r.status_code == 200:
            return r.json()
        print(f"Fallo en URL: {url} | Status: {r.status_code}")
        return None
    except Exception as e:
        print(f"Error de conexión: {e}")
        return None

def conectar_google():
    creds_json = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(creds_json, scopes=[
        "https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"
    ])
    return gspread.authorize(creds).open("ONPE Top 3")

def main():
    api_key = os.environ.get("ZENROWS_API_KEY")
    
    print("🚀 Iniciando descarga de datos vía API...")
    data_votos = obtener_json(URLS["VOTOS"], api_key)
    time.sleep(2) 
    data_t = obtener_json(URLS["AVANCE_T"], api_key)
    data_p = obtener_json(URLS["AVANCE_P"], api_key)
    data_e = obtener_json(URLS["AVANCE_E"], api_key)

    if not all([data_votos, data_t, data_p, data_e]):
        print("❌ No se pudieron recolectar todos los JSON. Abortando.")
        return

    # Extracción de datos (Rutas de tu exitoso test_api.py)
    top3 = data_votos['data']['rVotacion'][:3]
    p1, p2, p3 = top3
    pct_t = data_t['data']['actasContabilizadas']
    pct_p = data_p['data']['actasContabilizadas']
    pct_e = data_e['data']['actasContabilizadas']

    # Limpieza para que Google Sheets no se maree
    def clean_n(v): return int(str(v).replace(',', '').replace('.', ''))
    def clean_p(v): return float(str(v).replace(',', '.'))

    fecha = (datetime.now(timezone.utc) - timedelta(hours=5)).strftime("%d/%m/%Y %H:%M:%S")

    fila = [
        fecha, 
        p1['nombre_organizacion'], p2['nombre_organizacion'], p3['nombre_organizacion'],
        clean_n(p1['votos_total']), clean_n(p2['votos_total']), clean_n(p3['votos_total']),
        clean_p(p1['porcentaje_votos_validos']), clean_p(p2['porcentaje_votos_validos']), clean_p(p3['porcentaje_votos_validos']),
        clean_n(p2['votos_total']) - clean_n(p3['votos_total']),
        round(abs(clean_p(p2['porcentaje_votos_validos']) - clean_p(p3['porcentaje_votos_validos'])), 3),
        clean_p(pct_t), clean_p(pct_p), clean_p(pct_e)
    ]

    try:
        ss = conectar_google()
        # Solo actualizamos el Histórico para no chocar con el main.py
        ss.worksheet("Historico").append_row(fila, value_input_option="USER_ENTERED")
        print(f"✅ ¡ÉXITO! Datos de la API subidos: {pct_t}%")
    except Exception as e:
        print(f"Error al subir a Sheets: {e}")

if __name__ == "__main__":
    main()
