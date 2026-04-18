import requests
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timezone, timedelta
import os
import json
import time

# URLs ABSOLUTAS (Para evitar errores de rutas)
URLS = {
    "TODOS": "https://resultadoelectoral.onpe.gob.pe/presentacion-backend/resumen-general/totales?idEleccion=10&tipoFiltro=eleccion",
    "PERU": "https://resultadoelectoral.onpe.gob.pe/presentacion-backend/resumen-general/totales?idAmbitoGeografico=1&idEleccion=10&tipoFiltro=ambito_geografico",
    "EXTRANJERO": "https://resultadoelectoral.onpe.gob.pe/presentacion-backend/resumen-general/totales?idAmbitoGeografico=2&idEleccion=10&tipoFiltro=ambito_geografico",
    # He quitado '/resumen-general/' de aquí, que es lo más probable que esté fallando
    "CANDIDATOS": "https://resultadoelectoral.onpe.gob.pe/presentacion-backend/participantes-ubicacion-geografica-nombre?idEleccion=10&tipoFiltro=eleccion"
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
    try:
        response = requests.get('https://api.zenrows.com/v1/', params=params, timeout=30)
        if response.status_code != 200:
            return None
        return response.json()
    except Exception as e:
        print(f"Error en {nombre}: {e}")
        return None

def conectar_google():
    creds_json = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(creds_json, scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
    return gspread.authorize(creds).open(SHEET_NAME)

def main():
    try:
        api_key = os.environ.get("ZENROWS_API_KEY")
        
        # 1. Capturar datos
        res_todos = obtener_datos_api(URLS["TODOS"], api_key, "TODOS")
        time.sleep(1) # Pausa para no saturar
        res_peru = obtener_datos_api(URLS["PERU"], api_key, "PERU")
        time.sleep(1)
        res_ext = obtener_datos_api(URLS["EXTRANJERO"], api_key, "EXTRANJERO")
        time.sleep(1)
        res_cands = obtener_datos_api(URLS["CANDIDATOS"], api_key, "CANDIDATOS")

        if not all([res_todos, res_peru, res_ext, res_cands]):
            raise Exception("Una de las APIs devolvió HTML o error. Revisa las URLs.")

        # 2. Extraer datos (basado en tus capturas de JSON)
        pct_todos = res_todos['data']['actasContabilizadas']
        pct_peru = res_peru['data']['actasContabilizadas']
        pct_ext = res_ext['data']['actasContabilizadas']
        top3 = res_cands['data']['rVotacion'][:3]
        
        # 3. Preparar fila
        lima = timezone(timedelta(hours=-5))
        fecha = datetime.now(lima).strftime("%d/%m/%Y %H:%M:%S")
        
        p1, p2, p3 = top3
        
        # Limpieza de números (maneja si vienen como int o str)
        def clean_num(v): return int(str(v).replace(',', '').replace('.', ''))
        def clean_pct(v): return float(str(v).replace(',', '.'))

        fila = [
            fecha, 
            p1['nombre_organizacion'], p2['nombre_organizacion'], p3['nombre_organizacion'],
            clean_num(p1['votos_total']), clean_num(p2['votos_total']), clean_num(p3['votos_total']),
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
