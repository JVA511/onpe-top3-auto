import requests
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timezone, timedelta
import os
import json

# CONFIGURACIÓN
url = "https://resultadosegundavuelta.onpe.gob.pe/presentacion-backend/resumen-general/participantes?idEleccion=10&tipoFiltro=eleccion"
SHEET_NAME = "ONPE SEGUNDA VUELTA"

def votos_a_int(txt: str) -> int:
    return int(txt.replace("'", "").replace("’", "").replace(",", "").replace(".", "").strip())

def pct_a_float(txt: str) -> float:
    return float(txt.replace("%", "").replace(",", ".").strip())

def conectar():
    creds_json = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(
        creds_json, 
        scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    )
    return gspread.authorize(creds).open(SHEET_NAME)

def obtener_top3(wb):
    print("Solicitando datos JSON a través de ZenRows con rotación de APIs...")
    cred_sheet = wb.worksheet("Credenciales")
    credenciales = cred_sheet.get_all_values()
    
    datos_json = None
    
    # Bucle de rotación: lee desde la fila 2 hacia abajo
    for indice, fila in enumerate(credenciales[1:], start=2):
        api_key = fila[0]
        estado = fila[1]
        
        if estado == "Activa":
            print(f"Probando llave en la fila {indice}...")
            params = {
                'url': url,
                'apikey': api_key,
                'premium_proxy': 'true',
                'proxy_country': 'pe',
                'antibot': 'true'
            }
            
            try:
                response = requests.get('https://api.zenrows.com/v1/', params=params)
                
                if response.status_code == 200:
                    print(f"¡Éxito con la llave de la fila {indice}!")
                    datos_json = response.json()
                    break  # Rompemos el ciclo porque la extracción fue exitosa
                
                elif response.status_code in [401, 402, 403]:
                    print(f"Llave de la fila {indice} agotada o bloqueada. Actualizando Sheets a 'Agotada'...")
                    cred_sheet.update_cell(indice, 2, "Agotada")
                
                else:
                    print(f"Error {response.status_code} con la llave de la fila {indice}.")
                    cred_sheet.update_cell(indice, 2, "Error")
            except Exception as e:
                print(f"Hubo un fallo de conexión: {e}")

    if not datos_json:
        raise Exception("ALERTA CRÍTICA: Ninguna API Key activa funcionó. Todas están agotadas o en error.")

    # --- LA MAGIA DEL JSON ---
    lista_participantes = datos_json["data"]
    candidatos = []
    
    for participante in lista_participantes:
        candidatos.append({
            "nombre": participante["nombreCandidato"],
            "partido": participante["nombreAgrupacionPolitica"],
            "votos": participante["totalVotosValidos"],
            "pct": participante["porcentajeVotosValidos"]
        })

    candidatos.sort(key=lambda x: x["votos"], reverse=True)
    return candidatos[:2]

def guardar(wb, top2):
    resumen = wb.worksheet("Resumen")
    historico = wb.worksheet("Historico")
    
    p1, p2 = top2 
    lima = timezone(timedelta(hours=-5))
    fecha = datetime.now(lima).strftime("%d/%m/%Y %H:%M:%S")
    
    fila = [
        fecha, 
        p1["partido"], p2["partido"], 
        p1["votos"], p2["votos"], 
        p1["pct"], p2["pct"], 
        abs(p1["votos"] - p2["votos"]), 
        round(abs(p1["pct"] - p2["pct"]), 3)
    ]

    resumen.update(range_name="A2:I2", values=[fila])
    
    col_a = historico.col_values(1)
    siguiente_fila = len(col_a) + 1 
    
    rango_historico = f"A{siguiente_fila}:I{siguiente_fila}"
    historico.update(range_name=rango_historico, values=[fila])
    
    print(f"\nDatos subidos a la Fila {siguiente_fila} con éxito.")

def main():
    print("Ejecutando script...")
    wb = conectar() # Conectamos a Google Sheets una sola vez al inicio
    top2 = obtener_top3(wb)
    
    if not top2 or len(top2) < 2:
        raise Exception("El script no pudo extraer los 2 candidatos.")
        
    print(f"Top 1 detectado: {top2[0]['nombre']}")
    guardar(wb, top2)
    print("¡Datos guardados correctamente en Sheets! Terminando main.py...")

if __name__ == "__main__":
    main()
