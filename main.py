from playwright.sync_api import sync_playwright
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timezone, timedelta
import os
import json
import re

URL = "https://resultadoelectoral.onpe.gob.pe/main/presidenciales"
SHEET_NAME = "ONPE Top 3"

def votos_a_int(txt):
    return int(txt.replace("'", "").replace(",", "").replace(".", "").strip())

def pct_a_float(txt):
    return float(txt.replace("%", "").replace(",", ".").strip())

def obtener_top3():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(URL)
        page.get_by_text("Resultado por organización política").click()
        page.wait_for_timeout(3000)

        texto = page.locator("body").inner_text()
        browser.close()

    lineas = [x.strip() for x in texto.splitlines() if x.strip()]

    datos = []
    for i, l in enumerate(lineas):
        if "Cantidad de votos:" in l:
            votos = votos_a_int(re.search(r"([0-9'.,]+)", l).group(1))

            nombre = lineas[i-2]
            partido = lineas[i-1]

            pct = None
            for j in range(i-3, i):
                if "%" in lineas[j]:
                    pct = pct_a_float(lineas[j])
                    break

            if pct:
                datos.append((partido, votos, pct))

    datos = list(set(datos))
    datos.sort(key=lambda x: x[1], reverse=True)

    return datos[:3]

def conectar():
    creds_json = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(
        creds_json,
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return gspread.authorize(creds).open(SHEET_NAME)

def guardar(top3):
    sheet = conectar()
    resumen = sheet.worksheet("Resumen")
    historico = sheet.worksheet("Historico")

    p1, p2, p3 = top3

    dif_votos = p2[1] - p3[1]
    dif_pct = round(p2[2] - p3[2], 3)

    lima = timezone(timedelta(hours=-5))
    fecha = datetime.now(lima).strftime("%d/%m/%Y %H:%M:%S")

    fila = [
        fecha,
        p1[0], p2[0], p3[0],
        p1[1], p2[1], p3[1],
        p1[2], p2[2], p3[2],
        dif_votos, dif_pct
    ]

    resumen.update("A2:L2", [fila])
    historico.append_row(fila)

def main():
    top3 = obtener_top3()
    guardar(top3)

if __name__ == "__main__":
    main()
