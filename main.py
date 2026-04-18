import requests
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timezone, timedelta
import os
import json
import time

# Configuración de URLs de la API (Backend de ONPE)
BASE_BACKEND = "https://resultadoelectoral.onpe.gob.pe/presentacion-backend"
URLS = {
    "VOTOS": f"{BASE_BACKEND}/participantes-ubicacion-geografica-nombre?idEleccion=10&tipoFiltro=eleccion",
    "AVANCE_TODOS": f"{BASE_BACKEND}/resumen-general/totales?idEleccion=10&tipoFiltro=eleccion",
    "AVANCE_PERU": f"{BASE_BACKEND}/resumen-general/totales?idAmbitoGeografico=1&idEleccion=10&tipoFiltro=ambito_geografico",
    "AVANCE_EXT": f"{BASE_BACKEND}/resumen-general/totales?idAmbitoGeografico=2&idEleccion=10&tipoFiltro=ambito_geografico"
}

def obtener_json(url, api_key):
    """Consulta la API a través de ZenRows para evitar bloqueos."""
    params = {'url': url, 'apikey': api_key, 'premium_proxy': 'true', 'proxy_country': 'pe'}
    try:
        response = requests.get('https://api.zenrows.com/v1/', params=params, timeout=30)
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None

def conectar_google():
    creds_json = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(creds_json, scopes=[
        "https://www.googleapis.com/auth/spreadsheets", 
        "https://www.googleapis.com/auth/drive"
    ])
    return gspread.authorize(creds).open("ONPE Top 3")

def main():
    api_key = os.environ.get("ZENROWS_API_KEY")
    
    # 1. Descarga de datos
    data_votos = obtener_json(URLS["VOTOS"], api_key)
    time.sleep(1) # Pausa de seguridad
    data_todos = obtener_json(URLS["AVANCE_TODOS"], api_key)
    data_peru = obtener_json(URLS["AVANCE_PERU"], api_key)
    data_ext = obtener_json(URLS["AVANCE_EXT"], api_key)

    if not all([data_votos, data_todos, data_peru, data_ext]):
        print("Error: No se pudo obtener alguna de las fuentes de datos.")
        return

    # 2. Procesamiento de Votos (Top 3)
    # Según la estructura vista en el inspector: data -> rVotacion
    partidos = data_votos['data']['rVotacion'][:3]
    p1, p2, p3 = partidos

    # 3. Procesamiento de Avances
    # Según tus capturas: data -> actasContabilizadas
    avance_t = data_todos['data']['actasContabilizadas']
    avance_p = data_peru['data']['actasContabilizadas']
    avance_e = data_ext['data']['actasContabilizadas']

    # 4. Limpieza y Formateo
    def a_numero(v): return int(str(v).replace(',', '').replace('.', ''))
    def a_decimal(v): return float(str(v).replace(',', '.'))

    fecha_lima = (datetime.now(timezone.utc) - timedelta(hours=5)).strftime("%d/%m/%Y %H:%M:%S")

    fila = [
        fecha_lima,
        p1['nombre_organizacion'], p2['nombre_organizacion'], p3['nombre_organizacion'],
        a_numero(p1['votos_total']), a_numero(p2['votos_total']), a_numero(p3['votos_total']),
        a_decimal(p1['porcentaje_votos_validos']), a_decimal(p2['porcentaje_votos_validos']), a_decimal(p3['porcentaje_votos_validos']),
        a_numero(p2['votos_total']) - a_numero(p3['votos_total']), # Diferencia 2do vs 3ro
        round(abs(a_decimal(p2['porcentaje_votos_validos']) - a_decimal(p3['porcentaje_votos_validos'])), 3),
        a_decimal(avance_t), a_decimal(avance_p), a_decimal(avance_e)
    ]

    # 5. Envío a Google Sheets
    try:
        ss = conectar_google()
        ss.worksheet("Resumen").update(range_name="A2:O2", values=[fila])
        ss.worksheet("Historico").append_row(fila, value_input_option="USER_ENTERED")
        print(f"Sincronización exitosa: {avance_t}% procesado.")
    except Exception as e:
        print(f"Error al guardar en Sheets: {e}")

if __name__ == "__main__":
    main()
