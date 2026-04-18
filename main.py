import requests
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timezone, timedelta
import os
import json
import time

# Configuración de URLs (Las minas de oro que encontraste)
BASE_API = "https://resultadoelectoral.onpe.gob.pe/presentacion-backend"
URLS = {
    "VOTOS": f"{BASE_API}/participantes-ubicacion-geografica-nombre?idEleccion=10&tipoFiltro=eleccion",
    "AVANCE_T": f"{BASE_API}/resumen-general/totales?idEleccion=10&tipoFiltro=eleccion",
    "AVANCE_P": f"{BASE_API}/resumen-general/totales?idAmbitoGeografico=1&idEleccion=10&tipoFiltro=ambito_geografico",
    "AVANCE_E": f"{BASE_API}/resumen-general/totales?idAmbitoGeografico=2&idEleccion=10&tipoFiltro=ambito_geografico"
}

def obtener_datos(url, api_key):
    params = {'url': url, 'apikey': api_key, 'premium_proxy': 'true', 'proxy_country': 'pe'}
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
    
    # 1. Descarga de los 4 archivos JSON
    data_votos = obtener_datos(URLS["VOTOS"], api_key)
    time.sleep(1) # Pausa técnica
    data_t = obtener_datos(URLS["AVANCE_T"], api_key)
    data_p = obtener_datos(URLS["AVANCE_P"], api_key)
    data_e = obtener_datos(URLS["AVANCE_E"], api_key)

    if not all([data_votos, data_t, data_p, data_e]):
        print("Error: Falló la descarga de datos.")
        return

    # 2. Extracción de datos (Basado en tus pruebas de VS Code)
    # Resultados de candidatos
    top3 = data_votos['data']['rVotacion'][:3]
    p1, p2, p3 = top3

    # Porcentajes de avance
    pct_t = data_t['data']['actasContabilizadas']
    pct_p = data_p['data']['actasContabilizadas']
    pct_e = data_e['data']['actasContabilizadas']

    # 3. Limpieza de formatos (Comas por puntos, etc.)
    def limpio_int(v): return int(str(v).replace(',', '').replace('.', ''))
    def limpio_float(v): return float(str(v).replace(',', '.'))

    fecha = (datetime.now(timezone.utc) - timedelta(hours=5)).strftime("%d/%m/%Y %H:%M:%S")

    # 4. Creación de la fila (Asegúrate que coincida con tus columnas A a O)
    fila = [
        fecha, 
        p1['nombre_organizacion'], p2['nombre_organizacion'], p3['nombre_organizacion'],
        limpio_int(p1['votos_total']), limpio_int(p2['votos_total']), limpio_int(p3['votos_total']),
        limpio_float(p1['porcentaje_votos_validos']), limpio_float(p2['porcentaje_votos_validos']), limpio_float(p3['porcentaje_votos_validos']),
        limpio_int(p2['votos_total']) - limpio_int(p3['votos_total']), # Diferencia
        round(abs(limpio_float(p2['porcentaje_votos_validos']) - limpio_float(p3['porcentaje_votos_validos'])), 3),
        limpio_float(pct_t), limpio_float(pct_p), limpio_float(pct_e)
    ]

    # 5. Envío a Sheets
    ss = conectar_google()
    ss.worksheet("Resumen").update(range_name="A2:O2", values=[fila])
    ss.worksheet("Historico").append_row(fila, value_input_option="USER_ENTERED")
    print(f"✅ Sheets actualizado con éxito: {pct_t}%")

if __name__ == "__main__":
    main()
