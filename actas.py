import requests
import gspread
from google.oauth2.service_account import Credentials
import json
import time
import os

SHEET_NAME = "ONPE Top 3"

VISTAS = {
    "peru": "https://resultadoelectoral.onpe.gob.pe/presentacion-backend/resumen-general/totales?idAmbitoGeografico=1&idEleccion=10&tipoFiltro=ambito_geografico",
    "extranjero": "https://resultadoelectoral.onpe.gob.pe/presentacion-backend/resumen-general/totales?idAmbitoGeografico=2&idEleccion=10&tipoFiltro=ambito_geografico",
    "todos": "https://resultadoelectoral.onpe.gob.pe/presentacion-backend/resumen-general/totales?idEleccion=10&tipoFiltro=eleccion"
}

def conectar_google():
    creds_json = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(
        creds_json, 
        scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    )
    return gspread.authorize(creds).open(SHEET_NAME)

def main():
    zenrows_api_key = os.environ.get("ZENROWS_API_KEY")
    datos_extraidos = {}
    
    for nombre, url in VISTAS.items():
        print(f"📡 Descargando datos de: {nombre.upper()}...")
        params = {'url': url, 'apikey': zenrows_api_key, 'premium_proxy': 'true', 'proxy_country': 'pe', 'antibot': 'true'}
        try:
            response = requests.get('https://api.zenrows.com/v1/', params=params, timeout=45)
            if response.status_code == 200:
                datos = response.json()
                d = datos['data']
                datos_extraidos[nombre] = [d['actasContabilizadas'], d['contabilizadas'], d['enviadasJee'], d['pendientesJee']]
                print(f"✅ Guardado respuesta_{nombre}.json")
            else:
                print(f"❌ Error en {nombre}")
        except Exception as e:
            print(f"💥 Error: {e}")
        time.sleep(1)

    if len(datos_extraidos) < 3:
        print("🛑 Faltan datos. Abortando subida.")
        return

    def c_int(v): return int(str(v).replace(',', '').replace('.', ''))
    def c_float(v): return float(str(v).replace(',', '.'))
    
    dp = datos_extraidos["peru"]
    de = datos_extraidos["extranjero"]
    dt = datos_extraidos["todos"]

    # Ordenamos los 12 valores de Actas
    actas_valores = [
        c_float(dt[0]), c_float(dp[0]), c_float(de[0]), 
        c_int(dt[1]), c_int(dt[2]), c_int(dt[3]),       
        c_int(dp[1]), c_int(dp[2]), c_int(dp[3]),       
        c_int(de[1]), c_int(de[2]), c_int(de[3])        
    ]

    # 3. Subida a Sheets
    try:
        sheet = conectar_google()
        resumen = sheet.worksheet("Resumen")
        historico = sheet.worksheet("Historico")
        
        # Actualizamos el resumen (Fijo en M2:X2)
        resumen.update(range_name="M2:X2", values=[actas_valores])
        
        # --- EL TRUCO DEL FRANCOTIRADOR ---
        # 1. Buscamos cuál fue la última fila que main.py acaba de llenar en la Columna A
        col_a = historico.col_values(1)
        ultima_fila = len(col_a) 
        
        # 2. Inyectamos de la M a la X en esa fila exacta
        rango_historico = f"M{ultima_fila}:X{ultima_fila}"
        historico.update(range_name=rango_historico, values=[actas_valores])
        
        print(f"✅ ¡Datos de actas inyectados perfectamente en la Fila {ultima_fila}!")
        
    # ESTA ES LA PARTE QUE FALTABA
    except Exception as e:
        print(f"⚠️ Error en Sheets: {e}")

if __name__ == "__main__":
    main()
