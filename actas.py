import requests
import gspread
from google.oauth2.service_account import Credentials
import json
import time
import os

SHEET_NAME = "ONPE SEGUNDA VUELTA"

VISTAS = {
    "peru": "https://resultadosegundavuelta.onpe.gob.pe/presentacion-backend/resumen-general/totales?idEleccion=10&tipoFiltro=ambito_geografico&idAmbitoGeografico=1",
    "extranjero": "https://resultadosegundavuelta.onpe.gob.pe/presentacion-backend/resumen-general/totales?idEleccion=10&tipoFiltro=ambito_geografico&idAmbitoGeografico=2",
    "todos": "https://resultadosegundavuelta.onpe.gob.pe/presentacion-backend/resumen-general/totales?idEleccion=10&tipoFiltro=eleccion"
}

# --- FUNCIONES DE TELEGRAM ---
def enviar_telegram(mensaje):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        print("❌ No hay credenciales de Telegram configuradas.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {"chat_id": chat_id, "text": mensaje, "parse_mode": "Markdown"}
    try:
        requests.post(url, data=data)
        print("✅ ¡Mensaje de Telegram enviado con éxito al grupo!")
    except Exception as e:
        print(f"❌ Error enviando Telegram: {e}")

def disparar_alerta_completa():
    print("Esperando 3 segundos para que Google Sheets calcule las proyecciones...")
    time.sleep(3)
    
    # Nos conectamos al Excel usando tu función
    sheet = conectar_google()
    historico = sheet.worksheet("Historico")
    
    # Obtenemos la última fila ya terminada
    ultima_fila = len(historico.col_values(1))
    fila = historico.row_values(ultima_fila)

    if len(fila) < 76:
        fila += [''] * (76 - len(fila))

    # Extraemos TODO desde la fila
    partido_1 = fila[1]
    partido_2 = fila[2]
    votos_1 = fila[3]      
    votos_2 = fila[4]
    pct_1 = fila[5]
    pct_2 = fila[6]      
    dif_votos = fila[7]    

    pct_total = fila[9]    
    pct_peru = fila[10]    
    pct_ext = fila[11]     

    cont_tot = fila[12]    
    jee_env_tot = fila[13] 
    jee_pend_tot = fila[14]

    cont_pe = fila[15]     
    jee_env_pe = fila[16]  
    jee_pend_pe = fila[17] 

    cont_ext = fila[18]    
    jee_env_ext = fila[19] 
    jee_pend_ext = fila[20]

    proy_fp = fila[73]
    proy_jp = fila[74]
    dif_proy = fila[75]

    texto_alerta = (
        f"🚨 *REPORTE ONPE ACTUALIZADO* 🚨\n\n"
        f"🥇 *{partido_1}*\n"
        f"📊 Porcentaje: {pct_1}%\n"
        f"🗳️ Votos: {votos_1}\n\n"
        f"🥈 *{partido_2}*\n"
        f"📊 Porcentaje: {pct_2}%\n"
        f"🗳️ Votos: {votos_2}\n\n"
        f"⚖️ *DIFERENCIA ACTUAL:* {dif_votos} votos\n"
        f"--------------------------------------\n"
        f"📈 *% ACTAS PROCESADAS*\n"
        f"🌍 Total: {pct_total}%\n"
        f"🇵🇪 Perú: {pct_peru}%\n"
        f"✈️ Extranjero: {pct_ext}%\n"
        f"--------------------------------------\n"
        f"📦 *ACTAS - TOTAL*\n"
        f"✅ Contabilizadas: {cont_tot}\n"
        f"🏛️ Enviadas JEE: {jee_env_tot}\n"
        f"⏳ Pendientes JEE: {jee_pend_tot}\n"
        f"--------------------------------------\n"
        f"🇵🇪 *ACTAS - PERÚ*\n"
        f"✅ Contabilizadas: {cont_pe}\n"
        f"🏛️ Enviadas JEE: {jee_env_pe}\n"
        f"⏳ Pendientes JEE: {jee_pend_pe}\n"
        f"--------------------------------------\n"
        f"✈️ *ACTAS - EXTRANJERO*\n"
        f"✅ Contabilizadas: {cont_ext}\n"
        f"🏛️ Enviadas JEE: {jee_env_ext}\n"
        f"⏳ Pendientes JEE: {jee_pend_ext}\n"
        f"--------------------------------------\n"
        f"🔮 *PROYECCIÓN AL 100%*\n"
        f"🟠 Proy. FP: {proy_fp}\n"
        f"🟢 Proy. JP: {proy_jp}\n"
        f"⚖️ *Dif. Proyectada:* {dif_proy}\n"
    )

    enviar_telegram(texto_alerta)
# -----------------------------

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
        
        # --- AQUÍ DISPARAMOS LA ALERTA DE TELEGRAM ---
        disparar_alerta_completa()
        
    except Exception as e:
        print(f"⚠️ Error en Sheets: {e}")

if __name__ == "__main__":
    main()
