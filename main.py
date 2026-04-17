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
    return int(
        txt.replace("'", "")
           .replace("’", "")
           .replace(",", "")
           .replace(".", "")
           .strip()
    )


def pct_a_float(txt: str) -> float:
    return float(
        txt.replace("%", "")
           .replace(",", ".")
           .strip()
    )


def limpiar_linea(linea: str) -> str:
    return re.sub(r"\s+", " ", linea).strip()


def es_pct(linea: str) -> bool:
    return bool(re.fullmatch(r"\d{1,2}[.,]\d{3}\s*%", linea.strip()))


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

        context = browser.new_context(
            viewport={"width": 1600, "height": 3200},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/135.0.0.0 Safari/537.36"
            ),
            locale="es-PE",
            timezone_id="America/Lima",
        )

        page = context.new_page()

        print("Abriendo página...")
        page.goto(URL, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(10000)

        # Forzar render de la tabla inferior
        page.mouse.wheel(0, 2500)
        page.wait_for_timeout(3000)
        page.mouse.wheel(0, 2500)
        page.wait_for_timeout(3000)
        page.mouse.wheel(0, 1500)
        page.wait_for_timeout(3000)

        # screenshot para depuración
        page.screenshot(path="debug_page.png", full_page=True)

        body_text = page.locator("body").inner_text()
        browser.close()

    print("Longitud body_text:", len(body_text))

    if not body_text.strip():
        raise Exception("El body llegó vacío.")

    lineas = [limpiar_linea(x) for x in body_text.splitlines() if limpiar_linea(x)]

    print(f"Total de líneas leídas: {len(lineas)}")
    print("Primeras 80 líneas:")
    for x in lineas[:80]:
        print(x)

    # ---- quedarnos solo con la tabla/lista de candidatos ----
    ini = None
    fin = None

    for idx, l in enumerate(lineas):
        if "Candidatos a la Presidencia de la República" in l:
            ini = idx
            break

    for idx, l in enumerate(lineas):
        if "VOTOS EN BLANCO" in l:
            fin = idx
            break

    if ini is None or fin is None or fin <= ini:
        raise Exception("No se pudo ubicar la sección de la tabla de candidatos.")

    tabla = lineas[ini:fin]

    print(f"Líneas dentro de la tabla: {len(tabla)}")
    print("Primeras 60 líneas de la tabla:")
    for x in tabla[:60]:
        print(x)

    datos = []

    # Patrón esperado en tabla:
    # NOMBRE
    # PARTIDO
    # % validos
    # % emitidos
    # Cantidad de votos: X
    #
    # A veces puede haber variaciones, así que buscamos por 'Cantidad de votos:'
    for i, l in enumerate(tabla):
        if "Cantidad de votos:" not in l:
            continue

        m_votos = re.search(r"Cantidad de votos:\s*([0-9'’.,]+)", l)
        if not m_votos:
            continue

        votos = votos_a_int(m_votos.group(1))

        # Buscar hacia atrás dos porcentajes: el más lejano es votos válidos
        pcts = []
        for j in range(i - 1, max(-1, i - 10), -1):
            if es_pct(tabla[j]):
                pcts.append((j, pct_a_float(tabla[j])))
                if len(pcts) == 2:
                    break

        if len(pcts) < 2:
            continue

        idx_pct_validos, pct_validos = pcts[1]

        # Buscar partido y nombre antes del % válido
        previas = []
        for k in range(idx_pct_validos - 1, max(-1, idx_pct_validos - 8), -1):
            t = tabla[k]

            if es_pct(t):
                continue
            if "Cantidad de votos:" in t:
                continue
            if "Votos válidos" in t or "Votos emitidos" in t:
                continue
            if "Nombre del candidato" in t:
                continue
            if re.fullmatch(r"[0-9'’.,]+", t):
                continue

            previas.append(t)
            if len(previas) == 2:
                break

        if len(previas) < 2:
            continue

        partido = previas[0]
        nombre = previas[1]

        datos.append({
            "nombre": nombre,
            "partido": partido,
            "votos": votos,
            "pct": pct_validos
        })

    # quitar duplicados
    unicos = []
    vistos = set()
    for d in datos:
        clave = (d["nombre"], d["partido"], d["votos"], d["pct"])
        if clave not in vistos:
            vistos.add(clave)
            unicos.append(d)

    unicos.sort(key=lambda x: x["votos"], reverse=True)

    print("Registros detectados:")
    for x in unicos[:15]:
        print(x)

    if len(unicos) < 3:
        raise Exception(f"No se pudo obtener el top 3. Datos encontrados: {unicos}")

    return unicos[:3]


def conectar():
    creds_json = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(
        creds_json,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
    )
    return gspread.authorize(creds).open(SHEET_NAME)


def guardar(top3):
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

    print("Fila a guardar:", fila)

    resumen.update("A2:L2", [fila])
    historico.append_row(fila, value_input_option="USER_ENTERED")


def main():
    print("Ejecutando script...")
    top3 = obtener_top3()
    print("Top 3 final:", top3)
    guardar(top3)
    print("Datos guardados correctamente")


if __name__ == "__main__":
    main()
