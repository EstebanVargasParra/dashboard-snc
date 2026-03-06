import streamlit as st
import pandas as pd
import numpy as np
import scipy.stats as stats
import plotly.express as px
import plotly.graph_objects as go

# Configuración de la página
st.set_page_config(page_title="Dashboard SNC", layout="wide")

# ==============================================================================
# FUNCIÓN AUXILIAR: VPN
# ==============================================================================
def calcular_npv(rate, cashflows):
    """Calcula el Valor Presente Neto (VPN)"""
    return sum([cf / (1 + rate)**i for i, cf in enumerate(cashflows)])

# ==============================================================================
# BARRA LATERAL (NAVEGACIÓN)
# ==============================================================================
st.sidebar.title("🌿 Análisis Integral SNC")
st.sidebar.markdown("---")
modulo = st.sidebar.radio("Seleccione el Módulo:", 
                          ("1. Incertidumbre MRV", 
                           "2. Factor de Emisión", 
                           "3. Riesgo y Escalabilidad"))

# ==============================================================================
# MÓDULO 1: INCERTIDUMBRE MRV
# ==============================================================================
if modulo == "1. Incertidumbre MRV":
    st.title("📊 Módulo de Incertidumbre - MRV")
    st.markdown("Visualiza e interactúa con la base de datos maestra (GDB). Puedes filtrar, ordenar o modificar temporalmente los valores para ver cómo cambia la incertidumbre en tiempo real.")
    
    try:
        # 1. Cargar datos locales del repositorio
        with st.spinner('Cargando base de datos GDB...'):
            df_GDB = pd.read_excel("GDB.xlsx")
            
        # 2. Mostrar la base de datos interactiva al usuario
        st.subheader("🗄️ Base de Datos GDB (Vista Interactiva)")
        
        df_interactivo = st.data_editor(
            df_GDB, 
            num_rows="dynamic",
            use_container_width=True,
            height=300
        )
        
        # --- NUEVO: BOTÓN PARA DESCARGAR LA GDB ---
        # Convertimos el DataFrame original a un formato que Streamlit pueda descargar
        # NOTA: Usamos el df_GDB original para que descargue la base limpia, no la modificada temporalmente
        import io
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_GDB.to_excel(writer, index=False)
        
        st.download_button(
            label="📥 Descargar Base de Datos GDB Completa (.xlsx)",
            data=buffer.getvalue(),
            file_name="Base_Datos_GDB_MRV.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )
        # ------------------------------------------
        
        st.markdown("---")
        st.subheader("📈 Resultados de Incertidumbre por Ecosistema")
        
        # 3. Hacer los cálculos usando la tabla interactiva (df_interactivo)
        df = df_interactivo.dropna(subset=['Valor']).copy()
        
        df['Valor'] = pd.to_numeric(df['Valor'], errors='coerce')
        df = df.dropna(subset=['Valor'])
        
        resumen = df.groupby(['Ecosistema', 'Medida']).agg(
            n_mediciones=('Valor', 'count'),
            promedio=('Valor', 'mean'),
            desviacion=('Valor', lambda x: x.std(ddof=1) if len(x) > 1 else 0)
        ).reset_index()
        
        resumen['ee'] = np.where(resumen['n_mediciones'] > 1, resumen['desviacion'] / np.sqrt(resumen['n_mediciones']), np.nan)
        resumen['t_val'] = np.where(resumen['n_mediciones'] > 1, stats.t.ppf(0.95, resumen['n_mediciones'] - 1), np.nan)
        
        condiciones = [
            (resumen['n_mediciones'] == 1) & (resumen['Medida'] == 'BA'),
            (resumen['n_mediciones'] == 1) & (resumen['Medida'] == 'COS'),
            (resumen['n_mediciones'] == 1)
        ]
        elecciones = [80.0, 90.0, 85.0]
        
        resumen['incertidumbre_pct'] = np.where(
            resumen['n_mediciones'] > 1,
            (resumen['t_val'] * resumen['ee'] / resumen['promedio']) * 100,
            np.select(condiciones, elecciones, default=np.nan)
        )
        
        resumen['margen_error'] = resumen['promedio'] * (resumen['incertidumbre_pct'] / 100)
        resumen['Limite_Inferior'] = np.maximum(resumen['promedio'] - resumen['margen_error'], 0)
        
        def status_calidad(row):
            if row['n_mediciones'] == 1: return "🚨 Penalidad (n=1)"
            if row['n_mediciones'] < 3: return "⚠️ Muestra Pequeña (n<3)"
            if row['incertidumbre_pct'] > 20: return "🟠 Alta Variabilidad (>20%)"
            return "✅ Estadísticamente Sólido"
            
        resumen['Calidad_Estadistica'] = resumen.apply(status_calidad, axis=1)
        
        # 4. Mostrar Tablas de Resultados
        ecosistemas = resumen['Ecosistema'].unique()
        for eco in ecosistemas:
            with st.expander(f"🌲 {eco} (Clic para ver detalles)", expanded=True):
                df_eco = resumen[resumen['Ecosistema'] == eco][['Medida', 'n_mediciones', 'promedio', 'incertidumbre_pct', 'Calidad_Estadistica']]
                df_eco['incertidumbre_pct'] = df_eco['incertidumbre_pct'].round(2).astype(str) + '%'
                df_eco['promedio'] = df_eco['promedio'].round(2)
                st.dataframe(df_eco, use_container_width=True, hide_index=True)
            
    except Exception as e:
        st.error(f"Error al cargar la base de datos GDB.xlsx. Verifique que el archivo exista en la misma carpeta que la app. Detalle: {e}")

# ==============================================================================
# MÓDULO 2: FACTOR DE EMISIÓN
# ==============================================================================
elif modulo == "2. Factor de Emisión":
    st.title("☁️ Cálculo de Factores de Emisión")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        borde = st.number_input("Área borde (ha)", value=1800.0)
        nucleo = st.number_input("Área núcleo (ha)", value=1200.0)
    with col2:
        BT_borde = st.number_input("Biomasa borde (tC/ha)", value=255.4)
        COS_borde = st.number_input("Suelo borde (tC/ha)", value=80.9)
    with col3:
        BT_nucleo = st.number_input("Biomasa núcleo (tC/ha)", value=264.7)
        COS_nucleo = st.number_input("Suelo núcleo (tC/ha)", value=96.5)

    Mt1, Mt2 = 2009, 2018
    A1, A2 = 25187.94, 12292.83
    t1, t2 = 2024, 2025

    if st.button("Calcular Factores"):
        # Cálculos Borde
        BTe_borde = BT_borde * 0.47 * (44/12)
        COSe_borde = (COS_borde / 20) * (44/12)
        Fet_borde = (BTe_borde + COSe_borde) * 0.6
        cambio_sup_borde = abs(((1/(Mt2-Mt1)) * np.log(A2/A1)) * borde)
        DC_borde = 0.999
        CSV_borde = cambio_sup_borde * (1 - DC_borde)
        EAlb_borde = Fet_borde * cambio_sup_borde
        EAp_borde = Fet_borde * CSV_borde
        REp_borde = (t2 - t1) * (EAlb_borde - EAp_borde)
        Factor_borde = REp_borde / borde

        # Cálculos Núcleo
        BTe_nucleo = BT_nucleo * 0.47 * (44/12)
        COSe_nucleo = (COS_nucleo / 20) * (44/12)
        Fet_nucleo = (BTe_nucleo + COSe_nucleo) * 0.6
        cambio_sup_nucleo = abs(((1/(Mt2-Mt1)) * np.log(A2/A1)) * nucleo)
        DC_nucleo = 0.97
        CSV_nucleo = cambio_sup_nucleo * (1 - DC_nucleo)
        EAlb_nucleo = Fet_nucleo * cambio_sup_nucleo
        EAp_nucleo = Fet_nucleo * CSV_nucleo
        REp_nucleo = (t2 - t1) * (EAlb_nucleo - EAp_nucleo)
        Factor_nucleo = REp_nucleo / nucleo

        col_res1, col_res2 = st.columns(2)
        col_res1.metric("Factor Emisión BORDE", f"{Factor_borde:.2f} tCO2e/ha")
        col_res2.metric("Factor Emisión NÚCLEO", f"{Factor_nucleo:.2f} tCO2e/ha")

# ==============================================================================
# MÓDULO 3: RIESGO Y ESCALABILIDAD
# ==============================================================================
elif modulo == "3. Riesgo y Escalabilidad":
    st.title("📈 Motor Financiero y Monte Carlo")
    
    # ⚠️ IMPORTANTE: Enlace a tu plantilla de Excel para los usuarios
    url_plantilla = "https://raw.githubusercontent.com/TU_USUARIO/TU_REPO/main/Plantilla_Risk.xlsx"
    st.markdown(f"📥 [**Descargar Plantilla de Riesgo (Excel)**]({url_plantilla})")
    
    file_risk = st.file_uploader("Sube tu archivo Risk.xlsx completado", type=["xlsx"])
    
    if file_risk:
        df_risk_raw = pd.read_excel(file_risk, index_col=0)
        risk = df_risk_raw.T
        
        st.markdown("---")
        # --- PANEL DE TASAS BIOLÓGICAS ---
        st.subheader("🌱 1. Parámetros Biológicos de Captura")
        col_b, col_n = st.columns(2)
        tasa_captura_borde = col_b.number_input("Tasa Captura Borde (tCO2e/ha/año)", value=21.74, step=1.0)
        tasa_captura_nucleo = col_n.number_input("Tasa Captura Núcleo (tCO2e/ha/año)", value=32.60, step=1.0)
        
        # --- PANEL DE ESCALABILIDAD ---
        st.subheader("⚙️ 2. Configuración de Escalabilidad")
        
        c1, c2, c3 = st.columns(3)
        area_minima = c1.number_input("Área Mínima a simular (ha)", value=1000, step=500)
        area_maxima = c2.number_input("Área Máxima a simular (ha)", value=100000, step=5000)
        intervalo_sim = c3.number_input("Intervalos de simulación (ha)", value=500, step=100)
        
        c4, c5, c6, c7 = st.columns(4)
        mult_max = c4.number_input("Tope Máximo Costos (Multiplicador)", value=3.0, step=0.1)
        mult_min = c5.number_input("Tope Mínimo Costos (Multiplicador)", value=0.4, step=0.1)
        eficiencia_base = c6.number_input("Eficiencia Base", value=1.0, step=0.1)
        area_inflexion = c7.number_input("Área de Inflexión (ha)", value=10000, step=1000)
        
        st.markdown("---")
        
        # Parámetros Globales Fijos del Excel
        tasa_descuento = risk['tasa_descuento'].iloc[3]
        anios = int(risk['horizonte_tiempo_anios'].iloc[3])
        n_iter = 10000
        
        vars_excluir = ["ingreso_sp", "crecimiento_sp", "horizonte_tiempo_anios", "tasa_descuento"]
        vars_simular = [col for col in risk.columns if col not in vars_excluir]

        # Función del Motor Financiero
        def calcular_vpn_iter(v):
            area_total = v["area_total_proyecto_ha"]
            p_borde = v["porcentaje_area_efecto_borde"]
            area_borde = area_total * p_borde
            area_nucleo = area_total * (1 - p_borde)
            tasa_captura_ha = (p_borde * tasa_captura_borde) + ((1 - p_borde) * tasa_captura_nucleo)
            area_sp = area_total * v["relacion_area_sp_area_snc"]
            
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

        # SIMULACIÓN MONTE CARLO
        if st.button("Ejecutar Simulación Monte Carlo", type="primary"):
            with st.spinner('Simulando 10,000 escenarios...'):
                simulaciones = {}
                for var in vars_simular:
                    min_v = risk[var].iloc[0]
                    mode_v = risk[var].iloc[1]
                    max_v = risk[var].iloc[2]
                    simulaciones[var] = np.random.triangular(min_v, mode_v, max_v, n_iter)
                
                df_sim = pd.DataFrame(simulaciones)
                vpn_resultados = df_sim.apply(calcular_vpn_iter, axis=1).values
                df_sim['VPN'] = vpn_resultados
                
                st.subheader("📊 3. Análisis de Riesgo")
                
                # Gráfica 1: Histograma (AHORA MÁS GRANDE)
                fig_hist = px.histogram(df_sim, x="VPN", nbins=50, title="Distribución de la VPN (Análisis de Riesgo SNC)", color_discrete_sequence=['#lightgray'])
                fig_hist.update_traces(marker_line_color='white', marker_line_width=1, opacity=0.8)
                p10, p50, p90 = np.percentile(vpn_resultados, [10, 50, 90])
                fig_hist.add_vline(x=p10, line_dash="dash", line_color="red", annotation_text=f"P10: ${p10:,.0f}")
                fig_hist.add_vline(x=p50, line_width=2, line_color="green", annotation_text=f"P50: ${p50:,.0f}")
                fig_hist.add_vline(x=p90, line_dash="dash", line_color="blue", annotation_text=f"P90: ${p90:,.0f}")
                fig_hist.update_layout(height=500) # Forzamos mayor altura
                st.plotly_chart(fig_hist, use_container_width=True)

                # Gráfica 2: Tornado Spearman (AHORA MÁS GRANDE Y CORREGIDO)
                correlaciones = {}
                for var in vars_simular:
                    # Filtro anti-bugs: Solo calcula si la variable no es constante en el Excel
                    if df_sim[var].std() > 0: 
                        corr, _ = stats.spearmanr(df_sim[var], df_sim['VPN'])
                        correlaciones[var] = corr
                        
                df_corr = pd.DataFrame(list(correlaciones.items()), columns=['Variable', 'Correlacion']).sort_values('Correlacion')
                fig_tornado = px.bar(df_corr, x='Correlacion', y='Variable', orientation='h', 
                                     title="Sensibilidad de Monte Carlo (Spearman)", 
                                     color='Correlacion', color_continuous_scale="RdYlGn")
                fig_tornado.update_layout(height=600) # Mayor altura para que los nombres no se corten
                st.plotly_chart(fig_tornado, use_container_width=True)

        # ANÁLISIS DE ESCALABILIDAD
        st.subheader("⚖️ 4. Análisis de Punto de Equilibrio y Escalabilidad")
        
        # MATEMÁTICA EXACTA AL SCRIPT R
        area_base = risk['area_total_proyecto_ha'].iloc[3]
        try:
            # Cálculo de la pendiente (k_steepness) idéntico a R
            k_steepness = np.log(((mult_max - mult_min) / (eficiencia_base - mult_min)) - 1) / (area_base - area_inflexion)
        except Exception:
            st.warning("Advertencia: Configuración de escalabilidad inválida. Revisa los multiplicadores.")
            k_steepness = 0.0005 

        def factor_sigmoidal(area):
            # Fórmula sigmoidal idéntica a R
            return mult_min + (mult_max - mult_min) / (1 + np.exp(k_steepness * (area - area_inflexion)))

        areas_simuladas = np.arange(area_minima, area_maxima + intervalo_sim, intervalo_sim)
        v_base = risk.iloc[1].to_dict() # Escenario "Probable"

        resultados_escala = []
        for ha in areas_simuladas:
            v_actual = v_base.copy()
            v_actual["area_total_proyecto_ha"] = ha
            f_escala = factor_sigmoidal(ha)
            
            # Aplicar factor de escala solo a las variables que indicaste en R
            v_actual["costo_monitoreo_snc_usd_ha_anio"] *= f_escala
            v_actual["capex_cercado_perimetral_snc_usd_ha_borde"] *= f_escala
            v_actual["factor_salvaguarda_snc_usd_ha_anio"] *= f_escala
            v_actual["capex_sp_usd_ha"] *= f_escala
            
            vpn_ha = calcular_vpn_iter(v_actual)
            resultados_escala.append({"Hectareas": ha, "VPN": vpn_ha, "Factor_Costo": f_escala})
            
        df_esc = pd.DataFrame(resultados_escala)
        
        # Encontrar Punto de Equilibrio
        df_eq = df_esc[df_esc['VPN'] >= 0]
        if not df_eq.empty:
            pto_eq = df_eq.iloc[0]['Hectareas']
            st.success(f"✅ **Equilibrio SIGMOIDAL alcanzado a las {pto_eq:,.0f} Hectáreas**")
        else:
            st.error("❌ El proyecto no logra punto de equilibrio ni con máxima escala.")
            pto_eq = None
            
        # Gráfica 3: VPN vs Área (GRANDE)
        fig_vpn = px.line(df_esc, x="Hectareas", y="VPN", title="Punto de Equilibrio: Modelo Sigmoidal")
        fig_vpn.add_hline(y=0, line_dash="dash", line_color="red", line_width=2)
        if pto_eq:
            fig_vpn.add_vline(x=pto_eq, line_dash="dot", line_color="green", line_width=2, annotation_text=f"Break-even: {pto_eq:,.0f} ha")
        fig_vpn.update_layout(height=500)
        st.plotly_chart(fig_vpn, use_container_width=True)
            
        # Gráfica 4: Curva Sigmoidal (GRANDE)
        fig_factor = px.line(df_esc, x="Hectareas", y="Factor_Costo", title="Comportamiento del Factor de Costo (Curva Sigmoidal)")
        fig_factor.update_traces(line_color="darkorange", line_width=3)
        fig_factor.add_hline(y=eficiencia_base, line_dash="dot", line_color="blue", annotation_text=f"Multiplicador de Costo ({eficiencia_base} = Base)")
        fig_factor.add_hline(y=mult_max, line_dash="dash", line_color="gray")
        fig_factor.add_hline(y=mult_min, line_dash="dash", line_color="gray", annotation_text="Tope Mínimo (40%)")
        fig_factor.update_layout(height=500)
        st.plotly_chart(fig_factor, use_container_width=True)
