from playwright.sync_api import sync_playwright
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timezone, timedelta
import os
import json
import re

URL = "https://resultadoelectoral.onpe.gob.pe/main/presidenciales"
SHEET_NAME = "ONPE Top 3"


def votos_a_int(txt: str) -> int:
    return int(txt.replace("'", "").replace(",", "").replace(".", "").strip())


def pct_a_float(txt: str) -> float:
    return float(txt.replace("%", "").replace(",", ".").strip())


def obtener_top3():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        page = browser.new_page(viewport={"width": 1600, "height": 2200})
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)

        # Espera a que aparezca la lista general de candidatos
        page.wait_for_timeout(8000)

        # Esta vista ya muestra % y votos en la lista
        texto = page.locator("body").inner_text()
        browser.close()

    lineas = [x.strip() for x in texto.splitlines() if x.strip()]

    datos = []

    # Patrón esperado en esta vista:
    # [nombre]
    # [partido]
    # [17.069 %]
    # [14.230 %]   <- votos emitidos %, no lo usaremos
    # [Cantidad de votos: 2'683,629]
    #
    # A veces puede variar un poco, así que buscamos hacia atrás.
    for i, linea in enumerate(lineas):
        if "Cantidad de votos:" not in linea:
            continue

        m_votos = re.search(r"Cantidad de votos:\s*([0-9'.,]+)", linea)
        if not m_votos:
            continue

        votos = votos_a_int(m_votos.group(1))

        pct = None
        partido = ""
        nombre = ""

        # Buscar el % de votos válidos hacia atrás
        # Tomamos el porcentaje más cercano entre las 5 líneas previas
        porcentajes_previos = []
        for j in range(max(0, i - 6), i):
            m_pct = re.search(r"([0-9]+[.,][0-9]+)\s*%", lineas[j])
            if m_pct:
                porcentajes_previos.append((j, pct_a_float(m_pct.group(1))))

        if porcentajes_previos:
            # El primero que aparece hacia atrás suele ser el de votos emitidos;
            # el más antiguo de los dos suele ser votos válidos.
            # Para robustez, si hay 2 o más, tomamos el menor índice (más arriba).
            idx_pct, pct = sorted(porcentajes_previos, key=lambda x: x[0])[0]
        else:
            continue

        # Buscar nombre y partido antes del porcentaje
        # Normalmente nombre está 2 líneas arriba del primer % y partido 1 arriba
        # pero lo hacemos tolerante.
        candidatos_previos = lineas[max(0, idx_pct - 4):idx_pct]

        if len(candidatos_previos) >= 2:
            nombre = candidatos_previos[-2]
            partido = candidatos_previos[-1]
        else:
            continue

        # Filtros para evitar basura
        bloque = " ".join([nombre, partido]).lower()
        if any(x in bloque for x in [
            "candidatos a la presidencia",
            "nombre del candidato",
            "votos válidos",
            "votos emitidos",
            "cantidad de votos"
        ]):
            continue

        if len(partido) < 3 or len(nombre) < 3:
            continue

        datos.append({
            "nombre": nombre,
            "partido": partido,
            "votos": votos,
            "pct": pct
        })

    # Quitar duplicados
    unicos = []
    vistos = set()
    for d in datos:
        clave = (d["nombre"], d["partido"], d["votos"], d["pct"])
        if clave not in vistos:
            vistos.add(clave)
            unicos.append(d)

    # Ordenar por votos
    unicos.sort(key=lambda x: x["votos"], reverse=True)

    if len(unicos) < 3:
        raise Exception(f"No se pudo obtener el top 3. Datos encontrados: {unicos}")

    return unicos[:3]


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

    dif_votos = p2["votos"] - p3["votos"]
    dif_pct = round(p2["pct"] - p3["pct"], 3)

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


def main():
    print("Ejecutando script...")
    top3 = obtener_top3()
    print("Top 3:", top3)
    guardar(top3)
    print("Datos guardados correctamente")


if __name__ == "__main__":
    main()
