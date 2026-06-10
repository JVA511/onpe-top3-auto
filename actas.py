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
    # Formato HTML estricto para evitar bloqueos de Telegram
    data = {"chat_id": chat_id, "text": mensaje, "parse_mode": "HTML"}
    try:
        respuesta = requests.post(url, data=data)
        if respuesta.status_code == 200:
            print("✅ ¡Mensaje de Telegram enviado con éxito al grupo!")
        else:
            print(f"❌ TELEGRAM RECHAZÓ EL MENSAJE: {respuesta.text}")
    except Exception as e:
        print(f"❌ Error enviando Telegram: {e}")

def disparar_alerta_completa():
    print("Esperando 3 segundos para que Google Sheets calcule las proyecciones...")
    time.sleep(3)
    
    sheet = conectar_google()
    historico = sheet.worksheet("Historico")
    
    ultima_fila = len(historico.col_values(1))
    fila = historico.row_values(ultima_fila)
    
    # --- EL LECTOR DEL PASADO ---
    if ultima_fila > 2:
        fila_ant = historico.row_values(ultima_fila - 1)
    else:
        fila_ant = fila
        
    if len(fila) < 82: fila += [''] * (82 - len(fila))
    if len(fila_ant) < 82: fila_ant += [''] * (82 - len(fila_ant))

    # --- 1. FUNCIÓN A PRUEBA DE BALAS PARA MILES ---
    def fmt_num(numero):
        if not numero or str(numero) == "Calculando...": return numero
        try:
            val_str = str(numero).strip()
            if val_str.endswith(".00"): val_str = val_str[:-3]
            if val_str.endswith(",00"): val_str = val_str[:-3]
            if val_str.endswith(".0"): val_str = val_str[:-2]
            if val_str.endswith(",0"): val_str = val_str[:-2]
            
            val_str = val_str.replace(".", "").replace(",", "")
            return f"{int(val_str):,}".replace(",", ".")
        except:
            return str(numero)

    # --- 2. FUNCIÓN PARA PORCENTAJES (MÁX 3 DECIMALES) ---
    def fmt_pct(valor):
        if not valor or str(valor) in ["...", "Calculando..."]: return str(valor)
        try:
            v_limpio = str(valor).replace('%', '').replace(',', '.').strip()
            num = round(float(v_limpio), 3)
            return str(num).replace('.', ',') + "%"
        except:
            return str(valor) + "%" if "%" not in str(valor) else str(valor)

    # Extraemos Datos Base (Actuales)
    partido_1 = fila[1]
    partido_2 = fila[2]
    votos_1 = fmt_num(fila[3])      
    votos_2 = fmt_num(fila[4])
    
    pct_1 = fmt_pct(fila[5])
    pct_2 = fmt_pct(fila[6])      
    dif_votos = fmt_num(fila[7])
    dif_pct = fmt_pct(fila[8])

    pct_total = fmt_pct(fila[9])    
    pct_peru = fmt_pct(fila[10])    
    pct_ext = fmt_pct(fila[11])     

    cont_tot = fmt_num(fila[12])    
    jee_env_tot = fmt_num(fila[13]) 
    jee_pend_tot = fmt_num(fila[14])

    cont_pe = fmt_num(fila[15])     
    jee_env_pe = fmt_num(fila[16])  
    jee_pend_pe = fmt_num(fila[17]) 

    cont_ext = fmt_num(fila[18])    
    jee_env_ext = fmt_num(fila[19]) 
    jee_pend_ext = fmt_num(fila[20])

    proy_real_fp = fmt_num(fila[76]) if fila[76] != '' else "Calculando..."
    proy_real_jp = fmt_num(fila[77]) if fila[77] != '' else "Calculando..."
    dif_real_votos = fmt_num(fila[78]) if fila[78] != '' else "Calculando..."

    pct_proy_fp = fmt_pct(fila[79]) if fila[79] != '' else "..."
    pct_proy_jp = fmt_pct(fila[80]) if fila[80] != '' else "..."
    dif_real_pct = fmt_pct(fila[81]) if fila[81] != '' else "..."

    # --- 3. NUEVA LÓGICA DE LA ESCALA DE PÁNICO ---
    def generar_comentario_dinamico(ganador_hoy, dif_hoy_txt):
        try:
            # Convertimos la diferencia limpia a entero para la lógica matemática
            dif_hoy = int(str(dif_hoy_txt).replace('.', '').replace(',', ''))
            
            es_jp_hoy = "JUNTOS" in ganador_hoy.upper() or "JP" in ganador_hoy.upper()
            
            if not es_jp_hoy:
                return "🤖 <b>Comentario:</b> ¡FP volteó el partido! Alberto lo celebra desde su tumba en la Diroes y el taper se revaloriza."
            else:
                if dif_hoy > 100000:
                    return f"🤖 <b>Comentario:</b> JP sigue primero y la diferencia ya es de {dif_hoy_txt}. Todo está perdido, que nos conquisten los españoles de nuevo porque este país ya no tiene salvación."
                elif dif_hoy >= 20000:
                    return f"🤖 <b>Comentario:</b> JP sigue primero pero la diferencia está en {dif_hoy_txt}. Estamos cagados, vayan sacando sus pasajes o renovando el pasaporte por si las moscas."
                elif dif_hoy >= 5000:
                    return f"🤖 <b>Comentario:</b> Al fin bajó la diferencia a {dif_hoy_txt}. Seguimos cagados pero confío en que baje más por la ptm."
                else:
                    return f"🤖 <b>Comentario:</b> JP sigue primero, pero la diferencia es de {dif_hoy_txt}. Estamos cagados, pero con un micro-respiro, ¡sí se puede la ptm!"
                    
        except Exception as e:
            return "🤖 <b>Comentario:</b> Qué nervios esta diferencia."

    comentario_final = generar_comentario_dinamico(partido_1, dif_votos)

    # --- ARMAMOS EL MENSAJE FINAL (HTML) ---
    texto_alerta = (
        f"🚨 <b>REPORTE ONPE ACTUALIZADO</b> 🚨\n\n"
        f"🥇 <b>{partido_1}</b>\n"
        f"📊 Porcentaje: {pct_1}\n"
        f"🗳️ Votos: {votos_1}\n\n"
        f"🥈 <b>{partido_2}</b>\n"
        f"📊 Porcentaje: {pct_2}\n"
        f"🗳️ Votos: {votos_2}\n\n"
        f"⚖️ <b>DIF. ACTUAL:</b> {dif_votos} votos ({dif_pct})\n"
        f"--------------------------------------\n"
        f"📈 <b>% ACTAS PROCESADAS</b>\n"
        f"🌍 Total: {pct_total}\n"
        f"🇵🇪 Perú: {pct_peru}\n"
        f"✈️ Extranjero: {pct_ext}\n"
        f"--------------------------------------\n"
        f"📦 <b>ACTAS - TOTAL</b>\n"
        f"✅ Contabilizadas: {cont_tot}\n"
        f"🏛️ Enviadas JEE: {jee_env_tot}\n"
        f"⏳ Pendientes JEE: {jee_pend_tot}\n"
        f"--------------------------------------\n"
        f"🇵🇪 <b>ACTAS - PERÚ</b>\n"
        f"✅ Contabilizadas: {cont_pe}\n"
        f"🏛️ Enviadas JEE: {jee_env_pe}\n"
        f"⏳ Pendientes JEE: {jee_pend_pe}\n"
        f"--------------------------------------\n"
        f"✈️ <b>ACTAS - EXTRANJERO</b>\n"
        f"✅ Contabilizadas: {cont_ext}\n"
        f"🏛️ Enviadas JEE: {jee_env_ext}\n"
        f"⏳ Pendientes JEE: {jee_pend_ext}\n"
        f"--------------------------------------\n"
        f"🎯 <b>PROYECCIÓN MATEMÁTICA AL 100%</b>\n"
        f"🟠 Proy. FP: {proy_real_fp} votos ({pct_proy_fp})\n"
        f"🟢 Proy. JP: {proy_real_jp} votos ({pct_proy_jp})\n"
        f"⚖️ <b>Dif. Proyectada:</b> {dif_real_votos} votos ({dif_real_pct})\n"
        f"--------------------------------------\n"
        f"{comentario_final}\n"
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

    actas_valores = [
        c_float(dt[0]), c_float(dp[0]), c_float(de[0]), 
        c_int(dt[1]), c_int(dt[2]), c_int(dt[3]),       
        c_int(dp[1]), c_int(dp[2]), c_int(dp[3]),       
        c_int(de[1]), c_int(de[2]), c_int(de[3]),
        c_int(dt[4]), c_int(dt[5]),  
        c_int(dp[4]), c_int(de[4])   
    ]

    try:
        sheet = conectar_google()
        resumen = sheet.worksheet("Resumen")
        historico = sheet.worksheet("Historico")
        
        resumen.update(range_name="J2:Y2", values=[actas_valores])
        
        col_a = historico.col_values(1)
        ultima_fila = len(col_a) 
        
        rango_historico = f"J{ultima_fila}:Y{ultima_fila}"
        historico.update(range_name=rango_historico, values=[actas_valores])
        
        print(f"✅ ¡Datos de actas inyectados perfectamente en la Fila {ultima_fila}!")
        
        disparar_alerta_completa()
        
    except Exception as e:
        print(f"⚠️ Error en Sheets: {e}")

if __name__ == "__main__":
    main()
