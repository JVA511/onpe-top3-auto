import requests
import gspread
from google.oauth2.service_account import Credentials
import json
import time
import os

SHEET_NAME = "ONPE Top 3"

VISTAS = {
    "peru": "https://resultadosegundavuelta.onpe.gob.pe/presentacion-backend/resumen-general/totales?idEleccion=10&tipoFiltro=ambito_geografico&idAmbitoGeografico=1",
    "extranjero": "https://resultadosegundavuelta.onpe.gob.pe/presentacion-backend/resumen-general/totales?idEleccion=10&tipoFiltro=ambito_geografico&idAmbitoGeografico=2",
    "todos": "https://resultadosegundavuelta.onpe.gob.pe/presentacion-backend/resumen-general/totales?idEleccion=10&tipoFiltro=eleccion"
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
                datos_extraidos[nombre] = [d['actasContabilizadas'], d['contabilizadas'], d['enviadasJee'], d['pendientesJee'], d.get('totalVotosEmitidos', 0), d.get('totalVotosValidos', 0)]
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

    # Ordenamos los 16 valores (Actas + Votos Totales y Segmentados)
    actas_valores = [
        c_float(dt[0]), c_float(dp[0]), c_float(de[0]), 
        c_int(dt[1]), c_int(dt[2]), c_int(dt[3]),       
        c_int(dp[1]), c_int(dp[2]), c_int(dp[3]),       
        c_int(de[1]), c_int(de[2]), c_int(de[3]),
        c_int(dt[4]), c_int(dt[5]),  # V: Emitidos Total, W: Válidos Total
        c_int(dp[4]), c_int(de[4])   # X: Emitidos Perú, Y: Emitidos Extranjero
    ]

# 3. Subida a Sheets
    try:
        sheet = conectar_google()
        resumen = sheet.worksheet("Resumen")
        historico = sheet.worksheet("Historico")
        
        # Actualizamos el resumen (Fijo en J2:Y2)
        resumen.update(range_name="J2:Y2", values=[actas_valores])
        
        # --- EL TRUCO DEL FRANCOTIRADOR ---
        col_a = historico.col_values(1)
        ultima_fila = len(col_a) 
        
        # Inyectamos de la J a la Y en esa fila exacta
        rango_historico = f"J{ultima_fila}:Y{ultima_fila}"
        historico.update(range_name=rango_historico, values=[actas_valores])
        
        print(f"✅ ¡Datos de actas inyectados perfectamente en la Fila {ultima_fila}!")
        
    except Exception as e:
        print(f"⚠️ Error en Sheets: {e}")

if __name__ == "__main__":
    main()
