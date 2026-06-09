import requests
import gspread
from google.oauth2.service_account import Credentials
import json
import time
import os
import google.generativeai as genai

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

    if len(fila) < 82:
        fila += [''] * (82 - len(fila))

    # --- 1. FUNCIÓN A PRUEBA DE BALAS PARA MILES ---
    def fmt_num(numero):
        if not numero or str(numero) == "Calculando...": return numero
        try:
            val_str = str(numero).strip()
            
            # 1. Si trae decimales de ceros al final, los volamos sin piedad
            if val_str.endswith(".00"): val_str = val_str[:-3]
            if val_str.endswith(",00"): val_str = val_str[:-3]
            if val_str.endswith(".0"): val_str = val_str[:-2]
            if val_str.endswith(",0"): val_str = val_str[:-2]
            
            # 2. Ahora sí, limpiamos cualquier punto o coma de miles que quede
            val_str = val_str.replace(".", "").replace(",", "")
            
            # 3. Lo convertimos a entero real y formateamos con puntos
            return f"{int(val_str):,}".replace(",", ".")
        except:
            return str(numero)

    # --- 2. FUNCIÓN PARA PORCENTAJES (MÁX 3 DECIMALES) ---
    def fmt_pct(valor):
        if not valor or str(valor) in ["...", "Calculando..."]: return str(valor)
        try:
            # Limpiamos el % y cambiamos coma por punto para la matemática
            v_limpio = str(valor).replace('%', '').replace(',', '.').strip()
            # Redondeamos a máximo 3 decimales
            num = round(float(v_limpio), 3)
            # Devolvemos con coma y su %
            return str(num).replace('.', ',') + "%"
        except:
            return str(valor) + "%" if "%" not in str(valor) else str(valor)

    # Extraemos Datos Base (Aplicando el formato)
    partido_1 = fila[1]
    partido_2 = fila[2]
    votos_1 = fmt_num(fila[3])      
    votos_2 = fmt_num(fila[4])
    
    # Porcentajes Principales
    pct_1 = fmt_pct(fila[5])
    pct_2 = fmt_pct(fila[6])      
    dif_votos = fmt_num(fila[7])
    dif_pct = fmt_pct(fila[8])

    pct_total = fmt_pct(fila[9])    
    pct_peru = fmt_pct(fila[10])    
    pct_ext = fmt_pct(fila[11])     

    # Actas con separador de miles
    cont_tot = fmt_num(fila[12])    
    jee_env_tot = fmt_num(fila[13]) 
    jee_pend_tot = fmt_num(fila[14])

    cont_pe = fmt_num(fila[15])     
    jee_env_pe = fmt_num(fila[16])  
    jee_pend_pe = fmt_num(fila[17]) 

    cont_ext = fmt_num(fila[18])    
    jee_env_ext = fmt_num(fila[19]) 
    jee_pend_ext = fmt_num(fila[20])

    # Proyecciones Reales al 100% (Votos)
    proy_real_fp = fmt_num(fila[76]) if fila[76] != '' else "Calculando..."
    proy_real_jp = fmt_num(fila[77]) if fila[77] != '' else "Calculando..."
    dif_real_votos = fmt_num(fila[78]) if fila[78] != '' else "Calculando..."

    # Porcentajes de Proyección
    pct_proy_fp = fmt_pct(fila[79]) if fila[79] != '' else "..."
    pct_proy_jp = fmt_pct(fila[80]) if fila[80] != '' else "..."
    dif_real_pct = fmt_pct(fila[81]) if fila[81] != '' else "..."

    # --- 3. CEREBRO DE LA IA (GEMINI) ---
    def generar_comentario_ia(p1, pc1, p2, pc2, dif):
        try:
            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                return "🤖 *Comentario IA:* (Aviso: Falta agregar la llave GEMINI_API_KEY en GitHub Secrets)"
            
            genai.configure(api_key=api_key)
            
            prompt = f"""
            Eres un analista político y financiero peruano muy sarcástico y dramático. Estás dando un reporte en un grupo de Telegram de traders llamado 'TRADEOS'.
            Acaban de salir los nuevos resultados de la ONPE:
            - Primer lugar: {p1} con {pc1}
            - Segundo lugar: {p2} con {pc2}
            - Diferencia: {dif} votos.

            Genera un comentario corto (máximo 2 líneas) para cerrar el reporte. Reglas estrictas:
            - Usa jerga peruana y términos financieros.
            - Si Juntos por el Perú va ganando por más de 80,000 votos, muestra pánico absoluto, menciona que la Bolsa de Valores se desploma y usa la frase exacta: "Oficialmente estamos cagados. Vayan sacando pasaporte."
            - Si Juntos por el Perú va ganando pero por menos de 80,000 votos, di la frase: "Aún hay esperanza, la brecha es cortita. ¡Pongan a rezar a sus abuelas!"
            - Si Fuerza Popular va ganando, muestra alivio, menciona que salvamos a Julio Velarde, que la Bolsa de Valores sube y termina con la frase exacta: "Lo celebra Fujimori desde la tumba."
            - Sé creativo, chistoso y no uses hashtags.
            """
            
            modelo = genai.GenerativeModel('gemini-1.5-flash')
            respuesta = modelo.generate_content(prompt)
            return f"🤖 *Comentario IA:*\n{respuesta.text.strip()}"
        except Exception as e:
            return f"🤖 *Comentario IA:* (La IA tuvo un lapsus financiero: {e})"

    comentario_final = generar_comentario_ia(partido_1, pct_1, partido_2, pct_2, dif_votos)

    # --- ARMAMOS EL MENSAJE FINAL ---
    texto_alerta = (
        f"🚨 *REPORTE ONPE ACTUALIZADO* 🚨\n\n"
        f"🥇 *{partido_1}*\n"
        f"📊 Porcentaje: {pct_1}\n"
        f"🗳️ Votos: {votos_1}\n\n"
        f"🥈 *{partido_2}*\n"
        f"📊 Porcentaje: {pct_2}\n"
        f"🗳️ Votos: {votos_2}\n\n"
        f"⚖️ *DIF. ACTUAL:* {dif_votos} votos ({dif_pct})\n"
        f"--------------------------------------\n"
        f"📈 *% ACTAS PROCESADAS*\n"
        f"🌍 Total: {pct_total}\n"
        f"🇵🇪 Perú: {pct_peru}\n"
        f"✈️ Extranjero: {pct_ext}\n"
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
        f"🎯 *PROYECCIÓN MATEMÁTICA AL 100%*\n"
        f"🟠 Proy. FP: {proy_real_fp} votos ({pct_proy_fp})\n"
        f"🟢 Proy. JP: {proy_real_jp} votos ({pct_proy_jp})\n"
        f"⚖️ *Dif. Proyectada:* {dif_real_votos} votos ({dif_real_pct})\n"
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
