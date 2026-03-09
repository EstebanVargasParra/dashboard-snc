def calcular_vpn_iter(v):
            area_total = v["area_total_proyecto_ha"]
            p_borde = v["relacion_area_efecto_borde"]
            area_borde = area_total * p_borde
            area_nucleo = area_total * (1 - p_borde)
            area_sp = area_total * v["relacion_area_sp_area_snc"]
            tasa_captura_ha = (p_borde * tasa_captura_borde) + ((1 - p_borde) * tasa_captura_nucleo)
            
            # 1. Aplicamos las nuevas variables de aislamiento y siembra al Monte Carlo
            fac_aisla = 1.0 if v["relacion_area_aislamiento_area_snc"] == 0 else v["relacion_area_aislamiento_area_snc"]
            
            # Capex con nuevas variables
            capex_snc = v["capex_estudios_habilitantes_snc_usd"] + (v["capex_snc_usd_ha"] * area_borde * fac_aisla) + v["siembra_arboles"]
            capex_sp_total = (v["capex_sp_usd_ha"] * area_sp) * v["variabilidad_sistema_productivo"]
            capex_real = capex_snc + capex_sp_total + (v["factor_imprevistos_snc_usd_ha"] * area_total)
            
            # Opex con nuevas variables
            opex_snc = (capex_snc * v["operación_relacion_capex_snc"]) + ((v["monitoreo_snc_usd_ha_anio"] + v["factor_salvaguarda_snc_usd_ha_anio"]) * area_total)
            opex_sp = capex_sp_total * v["opex_sp"]
            
            vector_opex = np.zeros(anios + 1)
            vector_opex[1:11] = opex_snc + opex_sp
            vector_opex[11:] = opex_snc
            
            descuento = v["descuento_salvaguarda_tecnica"] + v["descuento_cambio_regulacion"] + v["descuento_variabilidad_climatica"]
            vol_creditos = area_total * tasa_captura_ha * v["eficiencia_snc"] * (1 - descuento)
            
            # Precios controlados globalmente por el panel lateral
            precios = precio_carbono_input * (1 + v["incremento_precio_carbono"])**np.arange(1, anios + 1)
            ingresos = np.zeros(anios + 1)
            ingresos[1:] = vol_creditos * precios
            
            flujos = ingresos - vector_opex
            flujos = np.where(flujos > 0, flujos * (1 - v["tasa_impuestos"]), flujos)
            flujos[0] = -capex_real
            
            return calcular_npv(tasa_descuento, flujos)


