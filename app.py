import streamlit as st
import pandas as pd
import numpy as np
import scipy.stats as stats
import plotly.express as px
import io

# ==============================================================================
# CONFIGURACIÓN DE LA PÁGINA
# ==============================================================================
st.set_page_config(page_title="Dashboard Integral SNC", layout="wide", page_icon="🌲")

def calcular_npv(rate, cashflows):
    return sum([cf / (1 + rate)**i for i, cf in enumerate(cashflows)])

# ==============================================================================
# BARRA LATERAL (CARGA DE DATOS GLOBALES)
# ==============================================================================
st.sidebar.title("🌿 Análisis Integral SNC")
st.sidebar.markdown("Para comenzar, carga tu archivo de parámetros financieros:")

url_plantilla = "https://raw.githubusercontent.com/TU_USUARIO/TU_REPO/main/Plantilla_Risk.xlsx"
st.sidebar.markdown(f"📥 [**Descargar Plantilla Risk.xlsx**]({url_plantilla})")

file_risk = st.sidebar.file_uploader("1. Sube tu archivo Risk.xlsx", type=["xlsx"])
st.sidebar.success("2. La base de datos GDB se carga automáticamente desde el repositorio.")

# Cargamos la GDB localmente (Base de datos maestra)
try:
    df_GDB = pd.read_excel("GDB.xlsx")
    gdb_cargada = True
except Exception as e:
    st.error(f"Error al cargar GDB.xlsx: {e}")
    gdb_cargada = False

# ==============================================================================
# FLUJO PRINCIPAL (PANELES INTEGRADOS)
# ==============================================================================
if file_risk and gdb_cargada:
    # 1. Procesamiento de Risk.xlsx
    df_risk_raw = pd.read_excel(file_risk, index_col=0)
    risk = df_risk_raw.T
    
    # Parámetros Fijos del Risk (Fila 4 = índice 3)
    total_area_risk = risk['area_total_proyecto_ha'].iloc[3]
    porcentaje_borde_risk = risk['porcentaje_area_efecto_borde'].iloc[3]
    tasa_descuento = risk['tasa_descuento'].iloc[3]
    anios = int(risk['horizonte_tiempo_anios'].iloc[3])

    # CREAMOS LAS PESTAÑAS (TABS) PARA EL PANEL UNIFICADO
    st.title("Sistema de Modelado - Soluciones Naturales del Clima")
    tab1, tab2, tab3 = st.tabs(["📊 1. Incertidumbre MRV", "☁️ 2. Factor de Emisión", "📈 3. Riesgos y Escalabilidad"])

    # --------------------------------------------------------------------------
    # TAB 1: INCERTIDUMBRE MRV
    # --------------------------------------------------------------------------
    with tab1:
        st.subheader("🗄️ Base de Datos GDB (Vista Interactiva)")
        st.markdown("Interactúa con los datos. Los cambios aquí son temporales y recalculan la tabla inferior.")
        
        df_interactivo = st.data_editor(df_GDB, num_rows="dynamic", use_container_width=True, height=250)
        
        # Botón de Descarga
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_GDB.to_excel(writer, index=False)
            
        st.download_button(label="📥 Descargar Base de Datos GDB Oficial (.xlsx)", data=buffer.getvalue(),
                           file_name="Base_Datos_GDB_MRV.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        
        st.markdown("---")
        st.subheader("📈 Resultados de Incertidumbre por Ecosistema")
        
        # Cálculos de incertidumbre
        df = df_interactivo.dropna(subset=['Valor']).copy()
        df['Valor'] = pd.to_numeric(df['Valor'], errors='coerce')
        df = df.dropna(subset=['Valor'])
        
        resumen = df.groupby(['Ecosistema', 'Medida']).agg(
            n_mediciones=('Valor', 'count'), promedio=('Valor', 'mean'),
            desviacion=('Valor', lambda x: x.std(ddof=1) if len(x) > 1 else 0)
        ).reset_index()
        
        resumen['ee'] = np.where(resumen['n_mediciones'] > 1, resumen['desviacion'] / np.sqrt(resumen['n_mediciones']), np.nan)
        resumen['t_val'] = np.where(resumen['n_mediciones'] > 1, stats.t.ppf(0.95, resumen['n_mediciones'] - 1), np.nan)
        
        condiciones = [(resumen['n_mediciones'] == 1) & (resumen['Medida'] == 'BA'),
                       (resumen['n_mediciones'] == 1) & (resumen['Medida'] == 'COS'),
                       (resumen['n_mediciones'] == 1)]
        resumen['incertidumbre_pct'] = np.where(resumen['n_mediciones'] > 1,
            (resumen['t_val'] * resumen['ee'] / resumen['promedio']) * 100, np.select(condiciones, [80.0, 90.0, 85.0], default=np.nan))
        
        resumen['margen_error'] = resumen['promedio'] * (resumen['incertidumbre_pct'] / 100)
        resumen['Limite_Inferior'] = np.maximum(resumen['promedio'] - resumen['margen_error'], 0)
        
        def status_calidad(row):
            if row['n_mediciones'] == 1: return "🚨 Penalidad (n=1)"
            if row['n_mediciones'] < 3: return "⚠️ Muestra Pequeña (n<3)"
            if row['incertidumbre_pct'] > 20: return "🟠 Alta Variabilidad (>20%)"
            return "✅ Estadísticamente Sólido"
        resumen['Calidad_Estadistica'] = resumen.apply(status_calidad, axis=1)
        
        # Mostrar expanders
        for eco in resumen['Ecosistema'].unique():
            with st.expander(f"🌲 {eco}", expanded=False):
                df_eco = resumen[resumen['Ecosistema'] == eco][['Medida', 'n_mediciones', 'promedio', 'incertidumbre_pct', 'Calidad_Estadistica']]
                df_eco['incertidumbre_pct'] = df_eco['incertidumbre_pct'].round(2).astype(str) + '%'
                df_eco['promedio'] = df_eco['promedio'].round(2)
                st.dataframe(df_eco, use_container_width=True, hide_index=True)

    # --------------------------------------------------------------------------
    # TAB 2: FACTOR DE EMISIÓN
    # --------------------------------------------------------------------------
    with tab2:
        st.subheader("⚙️ Parámetros del Modelo de Carbono")
        st.markdown("Las áreas provienen de tu archivo **Risk**. Los valores biológicos se seleccionan directamente de tu **GDB**.")
        
        # Cálculos de Área usando el Risk.xlsx
        borde_calc = total_area_risk * porcentaje_borde_risk
        nucleo_calc = total_area_risk - borde_calc

        st.info(f"**Área Total (Risk):** {total_area_risk:,.2f} ha | "
                f"**Área Borde ({porcentaje_borde_risk*100}%):** {borde_calc:,.2f} ha | "
                f"**Área Núcleo:** {nucleo_calc:,.2f} ha")

        st.markdown("---")
        st.subheader("🌲 Selección de Variables Biológicas (GDB)")
        
        # Filtramos la GDB para tener solo las filas con valores válidos de BA (Biomasa) y COS (Suelo)
        df_valid = df_GDB.dropna(subset=['Valor'])
        df_BA = df_valid[df_valid['Medida'] == 'BA']
        df_COS = df_valid[df_valid['Medida'] == 'COS']
        
        # Funciones para darle formato visual a las opciones del desplegable
        def format_ba(idx):
            row = df_BA.loc[idx]
            return f"{row.get('Ecosistema', '')} - {row.get('Estado', '')} ({row['Valor']:.2f} tC/ha)"
            
        def format_cos(idx):
            row = df_COS.loc[idx]
            return f"{row.get('Ecosistema', '')} - {row.get('Estado', '')} ({row['Valor']:.2f} tC/ha)"

        # PANELES DESPLEGABLES
        col_b, col_n = st.columns(2)
        with col_b:
            st.markdown("### Sector Borde")
            idx_bt_borde = st.selectbox("Biomasa Total (BT)", options=df_BA.index, format_func=format_ba, index=0, key="bt_b")
            idx_cos_borde = st.selectbox("Carbono Orgánico Suelo (COS)", options=df_COS.index, format_func=format_cos, index=0, key="cos_b")
            
            BT_borde_val = df_BA.loc[idx_bt_borde, 'Valor']
            COS_borde_val = df_COS.loc[idx_cos_borde, 'Valor']
            
        with col_n:
            st.markdown("### Sector Núcleo")
            # Para que por defecto no seleccione el mismo índice que el borde, le sumamos 1 si es posible
            idx_def_bt = 1 if len(df_BA) > 1 else 0
            idx_def_cos = 1 if len(df_COS) > 1 else 0
            
            idx_bt_nucleo = st.selectbox("Biomasa Total (BT)", options=df_BA.index, format_func=format_ba, index=idx_def_bt, key="bt_n")
            idx_cos_nucleo = st.selectbox("Carbono Orgánico Suelo (COS)", options=df_COS.index, format_func=format_cos, index=idx_def_cos, key="cos_n")
            
            BT_nucleo_val = df_BA.loc[idx_bt_nucleo, 'Valor']
            COS_nucleo_val = df_COS.loc[idx_cos_nucleo, 'Valor']

        st.markdown("---")
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        A1 = col_m1.number_input("Área Modelo 1 (A1)", value=25187.94)
        A2 = col_m2.number_input("Área Modelo 2 (A2)", value=12292.83)
        Mt1 = col_m3.number_input("Año Modelo 1 (Mt1)", value=2009)
        Mt2 = col_m4.number_input("Año Modelo 2 (Mt2)", value=2018)

        # Lógica Matemática
        # Borde
        BTe_borde = BT_borde_val * 0.47 * (44/12)
        COSe_borde = (COS_borde_val / 20) * (44/12)
        Fet_borde = (BTe_borde + COSe_borde) * 0.6
        cambio_superficie_borde = abs(((1/(Mt2-Mt1)) * np.log(A2/A1)) * borde_calc)
        CSV_borde = cambio_superficie_borde * (1 - 0.999)
        EAlb_borde = Fet_borde * cambio_superficie_borde
        EAp_borde = Fet_borde * CSV_borde
        REp_borde = (EAlb_borde - EAp_borde)
        Factor_borde = REp_borde / borde_calc

        # Núcleo
        BTe_nucleo = BT_nucleo_val * 0.47 * (44/12)
        COSe_nucleo = (COS_nucleo_val / 20) * (44/12)
        Fet_nucleo = (BTe_nucleo + COSe_nucleo) * 0.6
        cambio_superficie_nucleo = abs(((1/(Mt2-Mt1)) * np.log(A2/A1)) * nucleo_calc)
        CSV_nucleo = cambio_superficie_nucleo * (1 - 0.97)
        EAlb_nucleo = Fet_nucleo * cambio_superficie_nucleo
        EAp_nucleo = Fet_nucleo * CSV_nucleo
        REp_nucleo = (EAlb_nucleo - EAp_nucleo)
        Factor_nucleo = REp_nucleo / nucleo_calc

        st.subheader("✅ Factores de Emisión Finales")
        c_res1, c_res2 = st.columns(2)
        c_res1.metric("Factor Borde", f"{Factor_borde:.4f} tCO2e/ha/año")
        c_res2.metric("Factor Núcleo", f"{Factor_nucleo:.4f} tCO2e/ha/año")

    # --------------------------------------------------------------------------
    # TAB 3: RIESGOS Y ESCALABILIDAD
    # --------------------------------------------------------------------------
    with tab3:
        st.subheader("🔗 1. Tasas Biológicas (Conectadas automáticamente)")
        # Las variables se heredan del Tab 2. Se muestran deshabilitadas para demostrar la interconexión.
        col_b, col_n = st.columns(2)
        tasa_captura_borde = col_b.number_input("Tasa Captura Borde (Heredada del Tab 2)", value=Factor_borde, disabled=True)
        tasa_captura_nucleo = col_n.number_input("Tasa Captura Núcleo (Heredada del Tab 2)", value=Factor_nucleo, disabled=True)
        
        st.subheader("⚙️ 2. Configuración de Escalabilidad")
        c1, c2, c3 = st.columns(3)
        area_minima = c1.number_input("Área Mínima a simular (ha)", value=1000, step=500)
        area_maxima = c2.number_input("Área Máxima a simular (ha)", value=100000, step=5000)
        intervalo_sim = c3.number_input("Intervalo de simulación (ha)", value=500, step=100)
        
        c4, c5, c6, c7 = st.columns(4)
        mult_max = c4.number_input("Tope Máximo Costos (Multiplicador)", value=3.0, step=0.1)
        mult_min = c5.number_input("Tope Mínimo Costos (Multiplicador)", value=0.4, step=0.1)
        eficiencia_base = c6.number_input("Eficiencia Base", value=1.0, step=0.1)
        area_inflexion = c7.number_input("Área de Inflexión (ha)", value=10000, step=1000)
        
        st.markdown("---")
        
        # Preparación de variables a simular
        vars_excluir = ["ingreso_sp", "crecimiento_sp", "horizonte_tiempo_anios", "tasa_descuento"]
        vars_simular = [col for col in risk.columns if col not in vars_excluir]

        def calcular_vpn_iter(v):
            area_total = v["area_total_proyecto_ha"]
            p_borde = v["porcentaje_area_efecto_borde"]
            area_borde = area_total * p_borde
            area_sp = area_total * v["relacion_area_sp_area_snc"]
            tasa_captura_ha = (p_borde * tasa_captura_borde) + ((1 - p_borde) * tasa_captura_nucleo)
            
            capex_snc = v["capex_estudios_habilitantes_snc_usd"] + (v["capex_cercado_perimetral_snc_usd_ha_borde"] * area_borde)
            capex_sp_total = (v["capex_sp_usd_ha"] * area_sp) * v["variabilidad_sistema_productivo"]
            capex_real = capex_snc + capex_sp_total + (v["factor_imprevistos_snc_usd_ha"] * area_total)
            
            opex_snc = (capex_snc * v["opex_mantenimiento_snc"]) + ((v["costo_monitoreo_snc_usd_ha_anio"] + v["factor_salvaguarda_snc_usd_ha_anio"]) * area_total)
            opex_sp = capex_sp_total * v["opex_sp"]
            
            vector_opex = np.zeros(anios + 1)
            vector_opex[1:11] = opex_snc + opex_sp
            vector_opex[11:] = opex_snc
            
            descuento = v["descuento_salvaguarda_tecnica"] + v["descuento_cambio_regulacion"] + v["descuento_variabilidad_climatica"]
            vol_creditos = area_total * tasa_captura_ha * v["eficiencia_snc"] * (1 - descuento)
            
            precios = v["precio_carbono_usd_tco2e"] * (1 + v["crecimiento_precio_carbono"])**np.arange(1, anios + 1)
            ingresos = np.zeros(anios + 1)
            ingresos[1:] = vol_creditos * precios
            
            flujos = ingresos - vector_opex
            flujos = np.where(flujos > 0, flujos * (1 - v["tasa_impuestos"]), flujos)
            flujos[0] = -capex_real
            
            return calcular_npv(tasa_descuento, flujos)

        if st.button("🚀 Ejecutar Simulación Integral", type="primary"):
            with st.spinner('Procesando Flujos y Análisis Sigmoidal...'):
                # Monte Carlo
                simulaciones = {var: np.random.triangular(risk[var].iloc[0], risk[var].iloc[1], risk[var].iloc[2], 10000) for var in vars_simular}
                df_sim = pd.DataFrame(simulaciones)
                vpn_resultados = df_sim.apply(calcular_vpn_iter, axis=1).values
                df_sim['VPN'] = vpn_resultados
                
                st.subheader("📊 3. Análisis de Riesgo Financiero")
                
                fig_hist = px.histogram(df_sim, x="VPN", nbins=50, title="Distribución de la VPN", color_discrete_sequence=['lightgray'])
                fig_hist.update_traces(marker_line_color='white', marker_line_width=1)
                p10, p50, p90 = np.percentile(vpn_resultados, [10, 50, 90])
                fig_hist.add_vline(x=p10, line_dash="dash", line_color="red", annotation_text=f"P10: ${p10:,.0f}")
                fig_hist.add_vline(x=p50, line_width=2, line_color="green", annotation_text=f"P50: ${p50:,.0f}")
                fig_hist.add_vline(x=p90, line_dash="dash", line_color="blue", annotation_text=f"P90: ${p90:,.0f}")
                fig_hist.update_layout(height=500)
                st.plotly_chart(fig_hist, use_container_width=True)

                correlaciones = {var: stats.spearmanr(df_sim[var], df_sim['VPN'])[0] for var in vars_simular if df_sim[var].std() > 0}
                df_corr = pd.DataFrame(list(correlaciones.items()), columns=['Variable', 'Correlacion']).sort_values('Correlacion')
                fig_tornado = px.bar(df_corr, x='Correlacion', y='Variable', orientation='h', title="Sensibilidad de Monte Carlo (Spearman)", color='Correlacion', color_continuous_scale="RdYlGn")
                fig_tornado.update_layout(height=600)
                st.plotly_chart(fig_tornado, use_container_width=True)

                # Escalabilidad
                st.subheader("⚖️ 4. Análisis de Punto de Equilibrio (Curva S)")
                area_base = risk['area_total_proyecto_ha'].iloc[3]
                try:
                    k_steepness = np.log(((mult_max - mult_min) / (eficiencia_base - mult_min)) - 1) / (area_base - area_inflexion)
                except:
                    k_steepness = 0.0005 

                def factor_sigmoidal(area): return mult_min + (mult_max - mult_min) / (1 + np.exp(k_steepness * (area - area_inflexion)))

                v_base = risk.iloc[1].to_dict()
                areas_simuladas = np.arange(area_minima, area_maxima + intervalo_sim, intervalo_sim)
                resultados_escala = []
                
                for ha in areas_simuladas:
                    v_actual = v_base.copy()
                    v_actual["area_total_proyecto_ha"] = ha
                    f_escala = factor_sigmoidal(ha)
                    v_actual["costo_monitoreo_snc_usd_ha_anio"] *= f_escala
                    v_actual["capex_cercado_perimetral_snc_usd_ha_borde"] *= f_escala
                    v_actual["factor_salvaguarda_snc_usd_ha_anio"] *= f_escala
                    v_actual["capex_sp_usd_ha"] *= f_escala
                    resultados_escala.append({"Hectareas": ha, "VPN": calcular_vpn_iter(v_actual), "Factor_Costo": f_escala})
                    
                df_esc = pd.DataFrame(resultados_escala)
                
                df_eq = df_esc[df_esc['VPN'] >= 0]
                pto_eq = df_eq.iloc[0]['Hectareas'] if not df_eq.empty else None
                if pto_eq: st.success(f"✅ **Equilibrio SIGMOIDAL alcanzado a las {pto_eq:,.0f} Hectáreas**")
                else: st.error("❌ El proyecto no logra punto de equilibrio.")
                    
                fig_vpn = px.line(df_esc, x="Hectareas", y="VPN", title="Evolución de VPN vs Área")
                fig_vpn.add_hline(y=0, line_dash="dash", line_color="red", line_width=2)
                if pto_eq: fig_vpn.add_vline(x=pto_eq, line_dash="dot", line_color="green", line_width=2, annotation_text=f"Break-even: {pto_eq:,.0f} ha")
                fig_vpn.update_layout(height=500)
                st.plotly_chart(fig_vpn, use_container_width=True)
                    
                fig_factor = px.line(df_esc, x="Hectareas", y="Factor_Costo", title="Factor de Costo (Curva Sigmoidal)")
                fig_factor.update_traces(line_color="darkorange", line_width=3)
                fig_factor.add_hline(y=eficiencia_base, line_dash="dot", line_color="blue", annotation_text=f"Base ({eficiencia_base})")
                fig_factor.add_hline(y=mult_max, line_dash="dash", line_color="gray")
                fig_factor.add_hline(y=mult_min, line_dash="dash", line_color="gray", annotation_text="Límite Operativo")
                fig_factor.update_layout(height=500)
                st.plotly_chart(fig_factor, use_container_width=True)

else:
    st.info("👈 Por favor, carga tu archivo 'Risk.xlsx' en el menú lateral izquierdo para desplegar el modelo.")
