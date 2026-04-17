from playwright.sync_api import sync_playwright
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
import os
import json
import re

URL = "https://resultadoelectoral.onpe.gob.pe/main/presidenciales"
SHEET_NAME = "ONPE Top 3"

def votos_a_int(txt: str) -> int:
    return int(txt.replace("'", "").replace("’", "").replace(",", "").replace(".", "").strip())

def pct_a_float(txt: str) -> float:
    return float(txt.replace("%", "").replace(",", ".").strip())

def obtener_top3():
    with sync_playwright() as p:
        # OJO: Está en False para que veas el navegador en tu laptop.
        # Cuando lo subas a GitHub Actions, DEBES cambiarlo a headless=True
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(
            viewport={"width": 1600, "height": 1000},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="es-PE",
            timezone_id="America/Lima"
        )
        page = context.new_page()

        print("Abriendo página de la ONPE...")
        page.goto(URL, wait_until="networkidle", timeout=60000)
        
        # Scroll suave para que todos los gráficos carguen bien
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(5000)

        html = page.content()
        browser.close()

    soup = BeautifulSoup(html, "lxml")
    texto = soup.get_text("\n", strip=True)
    lineas = texto.splitlines()

    candidatos = []
    
    for i, linea in enumerate(lineas):
        if "Cantidad de votos:" in linea:
            votos_texto = linea.replace("Cantidad de votos:", "").strip()
            
            # Si se quedó vacío, el número saltó a la siguiente línea del HTML
            if not votos_texto and (i + 1) < len(lineas):
                votos_texto = lineas[i + 1].strip()

            try:
                votos = votos_a_int(votos_texto)
            except ValueError:
                continue # Si agarra basura o sigue vacío, lo ignora y avanza

            porcentajes = []
            partido = None
            nombre = None

            # Buscamos hacia arriba con la lógica corregida
            for j in range(i - 1, max(-1, i - 15), -1):
                txt = lineas[j].strip()

                # 1. Ignorar líneas vacías o EJES DEL GRÁFICO
                if not txt or re.fullmatch(r"[0-9\s'’.,]+", txt):
                    continue
                
                # 2. Ignorar textos repetitivos de la web
                if "votos" in txt.lower() or "presidencia" in txt.lower() or "candidatos" in txt.lower():
                    continue

                # 3. Capturar porcentajes
                if "%" in txt:
                    porcentajes.append(pct_a_float(txt))
                    continue

                # 4. Si ya tenemos los 2 %, los siguientes dos textos son Partido y Nombre
                if len(porcentajes) >= 2:
                    if not partido:
                        partido = txt
                        continue
                    if not nombre:
                        nombre = txt
                        break 

            # Validar que encontramos todo y guardar en la lista
            if nombre and partido and len(porcentajes) >= 2:
                # El segundo porcentaje hacia arriba es el de Votos Válidos
                pct_validos = porcentajes[1] 
                
                candidatos.append({
                    "nombre": nombre,
                    "partido": partido,
                    "votos": votos,
                    "pct": pct_validos
                })

    # Quitar duplicados por si Playwright leyó la misma caja dos veces
    unicos = []
    vistos = set()
    for c in candidatos:
        clave = (c["nombre"], c["partido"])
        if clave not in vistos:
            vistos.add(clave)
            unicos.append(c)

    # Ordenar por cantidad de votos de mayor a menor
    unicos.sort(key=lambda x: x["votos"], reverse=True)

    print("\n--- TOP 3 ENCONTRADO ---")
    for x in unicos[:3]:
        print(f"{x['nombre']} | {x['partido']} | Votos: {x['votos']} | Pct: {x['pct']}%")

    if len(unicos) < 3:
        raise Exception("Sigue sin poder leer el top 3 completo.")

    return unicos[:3]

def conectar():
    with open("service_account.json", "r", encoding="utf-8") as f:
        creds_json = json.load(f)

    creds = Credentials.from_service_account_info(
        creds_json,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
    )
    return gspread.authorize(creds).open(SHEET_NAME)

def guardar(top3):
    try:
        sheet = conectar()
        resumen = sheet.worksheet("Resumen")
        historico = sheet.worksheet("Historico")

        p1, p2, p3 = top3
        dif_votos = abs(p2["votos"] - p3["votos"])
        dif_pct = round(abs(p2["pct"] - p3["pct"]), 3)

        lima = timezone(timedelta(hours=-5))
        fecha = datetime.now(lima).strftime("%d/%m/%Y %H:%M:%S")

        fila = [
            fecha,
            p1["partido"], p2["partido"], p3["partido"],
            p1["votos"], p2["votos"], p3["votos"],
            p1["pct"], p2["pct"], p3["pct"],
            dif_votos, dif_pct
        ]

        resumen.update("A2:L2", [fila])
        historico.append_row(fila, value_input_option="USER_ENTERED")
        print("\nDatos subidos a Google Sheets con éxito.")
    except Exception as e:
        print(f"\nError al guardar en Sheets (¿Configuraste el JSON en tu entorno local?): {e}")

def main():
    print("Ejecutando script...")
    top3 = obtener_top3()
    guardar(top3)

if __name__ == "__main__":
    main()
