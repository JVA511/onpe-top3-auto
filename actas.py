def main():
    print("Iniciando conexión a Google Sheets...")
    wb = conectar_google()
    cred_sheet = wb.worksheet("Credenciales")
    credenciales = cred_sheet.get_all_values()
    
    datos_extraidos = {}
    
    for nombre, url in VISTAS.items():
        print(f"\n📡 Descargando datos de: {nombre.upper()}...")
        exito = False
        
        # Bucle de rotación de APIs para CADA una de las 3 vistas
        for indice, fila in enumerate(credenciales[1:], start=2):
            api_key = fila[0]
            estado = fila[1]
            
            if estado == "Activa":
                print(f"Probando llave en la fila {indice} para {nombre}...")
                params = {'url': url, 'apikey': api_key, 'premium_proxy': 'true', 'proxy_country': 'pe', 'antibot': 'true'}
                
                try:
                    response = requests.get('https://api.zenrows.com/v1/', params=params, timeout=45)
                    if response.status_code == 200:
                        datos = response.json()
                        d = datos['data']
                        datos_extraidos[nombre] = [d['actasContabilizadas'], d['contabilizadas'], d['enviadasJee'], d['pendientesJee'], d.get('totalVotosEmitidos', 0), d.get('totalVotosValidos', 0)]
                        print(f"✅ Guardado respuesta_{nombre}.json")
                        exito = True
                        break # Rompemos el bucle de APIs y pasamos a la siguiente "VISTA"
                        
                    elif response.status_code in [401, 402, 403]:
                        print(f"❌ Llave de la fila {indice} agotada. Actualizando Sheets a 'Agotada'...")
                        cred_sheet.update_cell(indice, 2, "Agotada")
                        
                    else:
                        print(f"❌ Error {response.status_code} con la llave de la fila {indice} en {nombre}.")
                        cred_sheet.update_cell(indice, 2, "Error")
                except Exception as e:
                    print(f"💥 Error de conexión: {e}")
        
        # Si después de probar todas las APIs de la lista ninguna funcionó para esta vista, cortamos el proceso.
        if not exito:
            print(f"🛑 Faltan datos críticos ({nombre}). Abortando subida.")
            return

        time.sleep(1)

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
        resumen = wb.worksheet("Resumen")
        historico = wb.worksheet("Historico")
        
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
