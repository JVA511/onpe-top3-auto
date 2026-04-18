import requests
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timezone, timedelta
import json
import time
import os

# --- CONFIGURACIÓN DE GITHUB ---
SHEET_NAME = "ONPE Top 3"

VISTAS = {
    "peru": "https://resultadoelectoral.onpe.gob.pe/presentacion-backend/resumen-general/totales?idAmbitoGeografico=1&idEleccion=10&tipoFiltro=ambito_geografico",
    "extranjero": "https://resultadoelectoral.onpe.gob.pe/presentacion-backend/resumen-general/totales?idAmbitoGeografico=2&idEleccion=10&tipoFiltro=ambito_geografico",
    "todos": "https://resultadoelectoral.onpe.gob.pe/presentacion-backend/resumen-general/totales?idEleccion=10&tipoFiltro=eleccion"
}

def conectar_google():
    # En GitHub, leemos el JSON de Google desde las variables secretas
    creds_json = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(
        creds_json, 
        scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    )
    return gspread.authorize(creds).open(SHEET_NAME)

def main():
    # En GitHub, leemos la llave de ZenRows desde las variables secretas
    zenrows_api_key = os.environ.get("ZENROWS_API_KEY")
    if not zenrows_api_key:
        print("🚨 Error: No se encontró ZENROWS_API_KEY en los Secrets de GitHub.")
        return

    datos_extraidos = {}
    
    for nombre, url in VISTAS.items():
        print(f"📡 Descargando datos de: {nombre.upper()}...")
        
        params = {
            'url': url,
            'apikey': zenrows_api_key,
            'premium_proxy': 'true',
            'proxy_country': 'pe',
            'antibot': 'true'
        }
        
        try:
            response = requests.get('https://api.zenrows.com/v1/', params=params, timeout=45)
            
            if response.status_code == 200:
                datos = response.json()
                
                avance = datos['data']['actasContabilizadas']
                contabilizadas = datos['data']['contabilizadas']
                enviadas_jee = datos['data']['enviadasJee']
                pendientes_jee = datos['data']['pendientesJee']
                
                datos_extraidos[nombre] = [avance, contabilizadas, enviadas_jee, pendientes_jee]
                
                print(f"✅ Descarga completada: {nombre}")
                print(f"   ▶ Avance: {avance}%")
                print(f"   ▶ Actas Contabilizadas: {contabilizadas}")
                print(f"   ▶ Enviadas al JEE: {enviadas_jee}")
                print(f"   ▶ Pendientes JEE: {pendientes_jee}\n")
            else:
                print(f"❌ Error en {nombre}: {response.status_code}\n")
                
        except Exception as e:
            print(f"💥 Error de red con {nombre}: {e}\n")
            
        time.sleep(1)

    if len(datos_extraidos) < 3:
        print("🛑 No se pudieron descargar todos los datos. Abortando subida a Sheets.")
        return

    print("📊 Preparando envío a Google Sheets...")
    
    def c_int(v): return int(str(v).replace(',', '').replace('.', ''))
    def c_float(v): return float(str(v).replace(',', '.'))
    
    lima = timezone(timedelta(hours=-5))
    fecha = datetime.now(lima).strftime("%d/%m/%Y %H:%M:%S")

    dp = datos_extraidos["peru"]
    de = datos_extraidos["extranjero"]
    dt = datos_extraidos["todos"]

    actas_valores = [
        c_float(dt[0]), c_float(dp[0]), c_float(de[0]), 
        c_int(dt[1]), c_int(dt[2]), c_int(dt[3]),       
        c_int(dp[1]), c_int(dp[2]), c_int(dp[3]),       
        c_int(de[1]), c_int(de[2]), c_int(de[3])        
    ]

    fila_historico = [fecha] + [""] * 11 + actas_valores

    try:
        sheet = conectar_google()
        resumen = sheet.worksheet("Resumen")
        historico = sheet.worksheet("Historico")
        
        resumen.update(range_name="A2", values=[[fecha]])
        resumen.update(range_name="M2:X2", values=[actas_valores])
        historico.append_row(fila_historico, value_input_option="USER_ENTERED")
        print("✅ ¡Datos de actas subidos a Google Sheets (A partir de la columna M)!")
    except Exception as e:
        print(f"⚠️ Error al guardar en Sheets: {e}")

if __name__ == "__main__":
    main()
