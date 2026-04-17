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

        page.goto(URL, wait_until="domcontentloaded", timeout=60000)

        # Esperar más tiempo para que cargue todo
        page.wait_for_timeout(10000)

        texto = page.locator("body").inner_text()
        browser.close()

    lineas = [x.strip() for x in texto.splitlines() if x.strip()]

    datos = []

    for i, l in enumerate(lineas):
        if "Cantidad de votos:" in l:

            m = re.search(r"([0-9'.,]+)", l)
            if not m:
                continue

            votos = votos_a_int(m.group(1))

            nombre = lineas[i-2] if i >= 2 else ""
            partido = lineas[i-1] if i >= 1 else ""

            pct = None
            for j in range(max(0, i-5), i):
                if "%" in lineas[j]:
                    m_pct = re.search(r"([0-9]+[.,][0-9]+)", lineas[j])
                    if m_pct:
                        pct = pct_a_float(m_pct.group(1))
                        break

            if pct is not None and len(partido) > 2:
                datos.append((partido, votos, pct))

    datos = list(set(datos))
    datos.sort(key=lambda x: x[1], reverse=True)

    if len(datos) < 3:
        raise Exception(f"No se pudo obtener el top 3. Datos encontrados: {datos}")

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

    # Diferencias SOLO 2° vs 3°
    dif_votos = p2[1] - p3[1]
    dif_pct = round(p2[2] - p3[2], 3)

    # Hora Perú
    lima = timezone(timedelta(hours=-5))
    fecha = datetime.now(lima).strftime("%d/%m/%Y %H:%M:%S")

    fila = [
        fecha,
        p1[0], p2[0], p3[0],
        p1[1], p2[1], p3[1],
        p1[2], p2[2], p3[2],
        dif_votos,
        dif_pct
    ]

    # Actualiza resumen
    resumen.update("A2:L2", [fila])

    # Agrega histórico
    historico.append_row(fila, value_input_option="USER_ENTERED")


def main():
    print("Ejecutando script...")
    top3 = obtener_top3()
    print("Top 3:", top3)
    guardar(top3)
    print("Datos guardados correctamente")


if __name__ == "__main__":
    main()
