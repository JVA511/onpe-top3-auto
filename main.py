import requests
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
import os
import json
import re



def enviar_telegram(mensaje):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        print("No hay credenciales de Telegram configuradas.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": mensaje,
        "parse_mode": "Markdown"  # Esto permite usar negritas (*) y cursivas (_)
    }
    try:
        requests.post(url, data=data)
        print("¡Mensaje de Telegram enviado con éxito al grupo!")
    except Exception as e:
        print(f"Error enviando Telegram: {e}")

# CONFIGURACIÓN
url = "https://resultadosegundavuelta.onpe.gob.pe/presentacion-backend/resumen-general/participantes?idEleccion=10&tipoFiltro=eleccion"
SHEET_NAME = "ONPE SEGUNDA VUELTA"

def votos_a_int(txt: str) -> int:
    return int(txt.replace("'", "").replace("’", "").replace(",", "").replace(".", "").strip())

def pct_a_float(txt: str) -> float:
    return float(txt.replace("%", "").replace(",", ".").strip())

def obtener_top3():
    api_key = os.environ.get("ZENROWS_API_KEY")
    if not api_key:
        raise Exception("Falta la API Key de ZenRows en los Secrets.")

    print("Solicitando datos JSON a través de ZenRows...")
    
    # Parámetros optimizados para API: sin esperas largas ni renderizado gráfico
    params = {
        'url': url,
        'apikey': api_key,
        'premium_proxy': 'true',
        'proxy_country': 'pe',
        'antibot': 'true'
    }
    
    response = requests.get('https://api.zenrows.com/v1/', params=params)
    
    if response.status_code != 200:
        raise Exception(f"Error de ZenRows: {response.status_code} - {response.text}")

    # --- LA MAGIA DEL JSON ---
    datos_json = response.json()
    lista_participantes = datos_json["data"]

    candidatos = []
    
    # Recorremos la lista del JSON extrayendo solo lo que necesitamos
    for participante in lista_participantes:
        candidatos.append({
            "nombre": participante["nombreCandidato"],
            "partido": participante["nombreAgrupacionPolitica"],
            "votos": participante["totalVotosValidos"],
            "pct": participante["porcentajeVotosValidos"]
        })

    # Ordenamos de mayor a menor cantidad de votos (para que el Top 1 siempre sea p1)
    candidatos.sort(key=lambda x: x["votos"], reverse=True)
    
    return candidatos[:2]

def conectar():
    creds_json = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(creds_json, scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
    return gspread.authorize(creds).open(SHEET_NAME)

def guardar(top2):
    sheet = conectar()
    resumen = sheet.worksheet("Resumen")
    historico = sheet.worksheet("Historico")
    
    # Solo desempaquetamos a los 2 candidatos
    p1, p2 = top2 
    lima = timezone(timedelta(hours=-5))
    fecha = datetime.now(lima).strftime("%d/%m/%Y %H:%M:%S")
    
    # LA NUEVA MATEMÁTICA: p1 vs p2 (Ocupa exactamente 9 elementos)
    fila = [
        fecha, 
        p1["partido"], p2["partido"], 
        p1["votos"], p2["votos"], 
        p1["pct"], p2["pct"], 
        abs(p1["votos"] - p2["votos"]), 
        round(abs(p1["pct"] - p2["pct"]), 3)
    ]

    # Actualiza el Resumen (A2:I2)
    resumen.update(range_name="A2:I2", values=[fila])
    
    # --- EL TRUCO DEL FRANCOTIRADOR ---
    col_a = historico.col_values(1)
    siguiente_fila = len(col_a) + 1 
    
    # Inyectamos a la fuerza desde la A hasta la I
    rango_historico = f"A{siguiente_fila}:I{siguiente_fila}"
    historico.update(range_name=rango_historico, values=[fila])
    
    print(f"\nDatos subidos a la Fila {siguiente_fila} con éxito.")

def main():
    print("Ejecutando script...")
    top2 = obtener_top3() # Sigue usando el mismo nombre de función, pero trae 2
    
    if not top2 or len(top2) < 2:
        raise Exception("El script no pudo extraer los 2 candidatos.")
        
    print(f"Top 1 detectado: {top2[0]['nombre']}")
    guardar(top2)
    print("¡Datos guardados correctamente en Sheets!")

    # --- AQUÍ EMPIEZA EL PASO 3 (ALERTA DE TELEGRAM CON PROYECCIONES) ---
    candidato_1 = top2[0]
    candidato_2 = top2[1]

    # 1. Nos conectamos al Excel y buscamos la hoja Histórico
    sheet = conectar()
    historico = sheet.worksheet("Historico")
    
    # Obtenemos la última fila que se acaba de guardar para tener los datos más frescos
    ultima_fila = len(historico.col_values(1))
    fila = historico.row_values(ultima_fila)

    # Truco de seguridad: Rellenamos la lista con vacíos por si Google recorta celdas sin datos
    if len(fila) < 76:
        fila += [''] * (76 - len(fila))

    # 2. Extraemos los valores por índice (A=0, B=1, ... BV=73)
    
    # Votos y Diferencia Actual (Columnas D, E, H)
    votos_1 = fila[3]      
    votos_2 = fila[4]      
    dif_votos = fila[7]    

    # % Actas (Columnas J, K, L)
    pct_total = fila[9]    
    pct_peru = fila[10]    
    pct_ext = fila[11]     

    # Actas Totales (Columnas M, N, O)
    cont_tot = fila[12]    
    jee_env_tot = fila[13] 
    jee_pend_tot = fila[14]

    # Actas Perú (Columnas P, Q, R)
    cont_pe = fila[15]     
    jee_env_pe = fila[16]  
    jee_pend_pe = fila[17] 

    # Actas Extranjero (Columnas S, T, U)
    cont_ext = fila[18]    
    jee_env_ext = fila[19] 
    jee_pend_ext = fila[20]

    # Proyecciones (Columnas BV, BW, BX)
    proy_fp = fila[73]
    proy_jp = fila[74]
    dif_proy = fila[75]

    # 3. Armamos el mega mensaje con formato, negritas (*) y emojis
    texto_alerta = (
        f"🚨 *REPORTE ONPE ACTUALIZADO* 🚨\n\n"
        
        f"🥇 *{candidato_1['partido']}*\n"
        f"📊 Porcentaje: {candidato_1['pct']}%\n"
        f"🗳️ Votos: {votos_1}\n\n"
        
        f"🥈 *{candidato_2['partido']}*\n"
        f"📊 Porcentaje: {candidato_2['pct']}%\n"
        f"🗳️ Votos: {votos_2}\n\n"
        
        f"⚖️ *DIFERENCIA ACTUAL:* {dif_votos} votos\n"
        f"------------------------------------\n"
        f"📈 *% ACTAS PROCESADAS*\n"
        f"🌍 Total: {pct_total}%\n"
        f"🇵🇪 Perú: {pct_peru}%\n"
        f"✈️ Extranjero: {pct_ext}%\n"
        f"------------------------------------\n"
        f"📦 *ACTAS - TOTAL*\n"
        f"✅ Contabilizadas: {cont_tot}\n"
        f"🏛️ Enviadas JEE: {jee_env_tot}\n"
        f"⏳ Pendientes JEE: {jee_pend_tot}\n"
        f"------------------------------------\n"
        f"🇵🇪 *ACTAS - PERÚ*\n"
        f"✅ Contabilizadas: {cont_pe}\n"
        f"🏛️ Enviadas JEE: {jee_env_pe}\n"
        f"⏳ Pendientes JEE: {jee_pend_pe}\n"
        f"------------------------------------\n"
        f"✈️ *ACTAS - EXTRANJERO*\n"
        f"✅ Contabilizadas: {cont_ext}\n"
        f"🏛️ Enviadas JEE: {jee_env_ext}\n"
        f"⏳ Pendientes JEE: {jee_pend_ext}\n"
        f"------------------------------------\n"
        f"🔮 *PROYECCIÓN AL 100%*\n"
        f"🟠 Proy. FP: {proy_fp}\n"
        f"🟢 Proy. JP: {proy_jp}\n"
        f"⚖️ *Dif. Proyectada:* {dif_proy}\n"
    )

    # Disparamos el mensaje al grupo
    enviar_telegram(texto_alerta)
if __name__ == "__main__":
    main()
