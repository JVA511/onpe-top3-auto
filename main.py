import requests
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timezone, timedelta
import os
import json
import time

# URLs de la fuente de la verdad (ONPE Backend)
BASE_API = "https://resultadoelectoral.onpe.gob.pe/presentacion-backend"
URLS = {
    "VOTOS": f"{BASE_API}/participantes-ubicacion-geografica-nombre?idEleccion=10&tipoFiltro=eleccion",
    "AVANCE_T": f"{BASE_API}/resumen-general/totales?idEleccion=10&tipoFiltro=eleccion",
    "AVANCE_P": f"{BASE_API}/resumen-general/totales?idAmbitoGeografico=1&idEleccion=10&tipoFiltro=ambito_geografico",
    "AVANCE_E": f"{BASE_API}/resumen-general/totales?idAmbitoGeografico=2&idEleccion=10&tipoFiltro=ambito_geografico"
}

def obtener_json(url, api_key):
    # Configuración de ZenRows para saltar el bloqueo de la ONPE
    params = {
        'url': url,
        'apikey': api_key,
        'premium_proxy': 'true',
        'proxy_country': 'pe'
    }
    try:
        r = requests.get('https://api.zenrows.com/v1/', params=params, timeout=30)
        return r.json() if r.status_code == 200 else None
    except:
        return None

def conectar_google():
    creds_json = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(creds_json, scopes=[
        "https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"
    ])
    return gspread.authorize(creds).open("ONPE Top 3")

def main():
    api_key = os.environ.get("ZENROWS_API_KEY")
    print("📡 Conectando a la nueva cuenta de ZenRows...")
    
    # Descarga secuencial de datos
    data_votos = obtener_json(URLS["VOTOS"], api_key)
    time.sleep(1) 
    data_t = obtener_json(URLS["AVANCE_T"], api_key)
    data_p = obtener_json(URLS["AVANCE_P"], api_key)
    data_e = obtener_json(URLS["AVANCE_E"], api_key)

    if not all([data_votos, data_t, data_p, data_e]):
        print("❌ Error: No se pudo recolectar la data. Revisa los créditos de la cuenta nueva.")
        return

    # Procesamiento de la información
    top3 = data_votos['data']['rVotacion'][:3]
    p1, p2, p3 = top3
    pct_t = data_t['data']['actasContabilizadas']
    pct_p = data_p['data']['actasContabilizadas']
    pct_e = data_e['data']['actasContabilizadas']

    def c_int(v): return int(str(v).replace(',', '').replace('.', ''))
    def c_float(v): return float(str(v).replace(',', '.'))

    fecha = (datetime.now(timezone.utc) - timedelta(hours=5)).strftime("%d/%m/%Y %H:%M:%S")

    # Fila lista para Google Sheets (Columnas A a O)
    fila = [
        fecha, p1['nombre_organizacion'], p2['nombre_organizacion'], p3['nombre_organizacion'],
        c_int(p1['votos_total']), c_int(p2['votos_total']), c_int(p3['votos_total']),
        c_float(p1['porcentaje_votos_validos']), c_float(p2['porcentaje_votos_validos']), c_float(p3['porcentaje_votos_validos']),
        c_int(p2['votos_total']) - c_int(p3['votos_total']),
        round(abs(c_float(p2['porcentaje_votos_validos']) - c_float(p3['porcentaje_votos_validos'])), 3),
        c_float(pct_t), c_float(pct_p), c_float(pct_e)
    ]

    try:
        ss = conectar_google()
        ss.worksheet("Resumen").update(range_name="A2:O2", values=[fila])
        ss.worksheet("Historico").append_row(fila, value_input_option="USER_ENTERED")
        print(f"✅ ¡Sistema recuperado! Avance: {pct_t}%")
    except Exception as e:
        print(f"Error en Sheets: {e}")

if __name__ == "__main__":
    main()
