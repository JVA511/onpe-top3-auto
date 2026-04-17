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


def es_porcentaje(linea: str) -> bool:
    return bool(re.fullmatch(r"\d{1,2}[.,]\d{3}\s*%", linea.strip()))


def limpiar_linea(linea: str) -> str:
    return re.sub(r"\s+", " ", linea).strip()


def es_linea_basura(linea: str) -> bool:
    t = linea.lower().strip()

    basura = [
        "elección de fórmula presidencial",
        "resultado por ubicación geográfica",
        "resultado por organización política",
        "candidatos a la presidencia de la república",
        "nombre del candidato",
        "votos válidos",
        "votos emitidos",
        "cantidad de votos",
        "resumen general",
        "presidencial",
        "senadores",
        "diputados",
        "parlamento andino",
        "participación ciudadana",
        "actas",
        "información",
        "todos",
        "votos en blanco",
        "votos nulos",
        "total de votos",
        "inventario de actas contabilizadas",
    ]

    if any(x in t for x in basura):
        return True

    # Ejes / números sueltos del gráfico
    if re.fullmatch(r"[0-9'.,]+", t):
        return True

    return False


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

        page = browser.new_page(viewport={"width": 1600, "height": 3000})
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)

        # Espera para contenido dinámico
        page.wait_for_timeout(12000)

        # Bajamos un poco para asegurar que la lista esté renderizada
        page.mouse.wheel(0, 1800)
        page.wait_for_timeout(3000)

        texto = page.locator("body").inner_text()
        browser.close()

    lineas = [limpiar_linea(x) for x in texto.splitlines() if limpiar_linea(x)]

    print(f"Total de líneas leídas: {len(lineas)}")

    datos = []

    for i, linea in enumerate(lineas):
        if "Cantidad de votos:" not in linea:
            continue

        m_votos = re.search(r"Cantidad de votos:\s*([0-9'’.,]+)", linea)
        if not m_votos:
            continue

        votos = votos_a_int(m_votos.group(1))

        # Buscar hacia atrás los 2 porcentajes más cercanos
        porcentajes = []
        for j in range(i - 1, max(-1, i - 12), -1):
            if es_porcentaje(lineas[j]):
                porcentajes.append((j, pct_a_float(lineas[j])))
                if len(porcentajes) == 2:
                    break

        # Queremos 2 porcentajes:
        # el más cercano al voto suele ser "votos emitidos"
        # el segundo más cercano suele ser "votos válidos"
        if len(porcentajes) < 2:
            continue

        idx_pct_validos, pct_validos = porcentajes[1]

        # Buscar partido y nombre antes del % de votos válidos
        previas = []
        for k in range(idx_pct_validos - 1, max(-1, idx_pct_validos - 8), -1):
            candidata = lineas[k]

            if es_linea_basura(candidata):
                continue

            if es_porcentaje(candidata):
                continue

            if "Cantidad de votos:" in candidata:
                continue

            previas.append((k, candidata))
            if len(previas) == 2:
                break

        if len(previas) < 2:
            continue

        # previas[0] = partido (más cercano)
        # previas[1] = nombre (siguiente hacia arriba)
        partido = previas[0][1]
        nombre = previas[1][1]

        # Filtros extra
        if len(partido) < 3 or len(nombre) < 3:
            continue

        if es_linea_basura(partido) or es_linea_basura(nombre):
            continue

        datos.append({
            "nombre": nombre,
            "partido": partido,
            "votos": votos,
            "pct": pct_validos
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

    print("Registros detectados:")
    for x in unicos[:10]:
        print(x)

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
