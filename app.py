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
    st.markdown("Este módulo se conecta a GitHub para calcular la incertidumbre en tiempo real.")
    
    # URL de GitHub (Debe ser la versión "Raw" del archivo)
    url_github = st.text_input("Enlace Raw de GitHub (GDB.xlsx o CSV):", 
                               value="https://raw.githubusercontent.com/TU_USUARIO/TU_REPO/main/GDB.csv")
    
    uploaded_file = st.file_uploader("O sube el archivo GDB temporalmente aquí:", type=["xlsx", "csv"])
    
    if uploaded_file is not None or url_github:
        try:
            if uploaded_file:
                if uploaded_file.name.endswith('.csv'):
                    df_GDB = pd.read_csv(uploaded_file)
                else:
                    df_GDB = pd.read_excel(uploaded_file)
            else:
                # Si usa el link de Github
                df_GDB = pd.read_csv(url_github)
            
            # Filtramos nulos
            df = df_GDB.dropna(subset=['Valor']).copy()
            
            # Agrupación y Estadísticas
            resumen = df.groupby(['Ecosistema', 'Medida']).agg(
                n_mediciones=('Valor', 'count'),
                promedio=('Valor', 'mean'),
                desviacion=('Valor', lambda x: x.std(ddof=1) if len(x) > 1 else 0)
            ).reset_index()
            
            # Lógica matemática
            resumen['ee'] = np.where(resumen['n_mediciones'] > 1, resumen['desviacion'] / np.sqrt(resumen['n_mediciones']), np.nan)
            # t_val al 90% de confianza a dos colas (equivalente a qt(0.95) en R)
            resumen['t_val'] = np.where(resumen['n_mediciones'] > 1, stats.t.ppf(0.95, resumen['n_mediciones'] - 1), np.nan)
            
            # Criterio Experto (Penalidad)
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
            
            # Estatus de Calidad
            def status_calidad(row):
                if row['n_mediciones'] == 1: return "🚨 Penalidad (n=1)"
                if row['n_mediciones'] < 3: return "⚠️ Muestra Pequeña (n<3)"
                if row['incertidumbre_pct'] > 20: return "🟠 Alta Variabilidad (>20%)"
                return "✅ Estadísticamente Sólido"
                
            resumen['Calidad_Estadistica'] = resumen.apply(status_calidad, axis=1)
            
            st.success("Datos procesados correctamente.")
            
            ecosistemas = resumen['Ecosistema'].unique()
            for eco in ecosistemas:
                st.subheader(f"🌲 {eco}")
                df_eco = resumen[resumen['Ecosistema'] == eco][['Medida', 'n_mediciones', 'promedio', 'incertidumbre_pct', 'Calidad_Estadistica']]
                df_eco['incertidumbre_pct'] = df_eco['incertidumbre_pct'].round(2).astype(str) + '%'
                df_eco['promedio'] = df_eco['promedio'].round(2)
                st.dataframe(df_eco, use_container_width=True)
                
        except Exception as e:
            st.warning(f"Esperando datos válidos o revise el formato. Detalle: {e}")

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
    
    file_risk = st.file_uploader("Sube tu archivo Risk.xlsx", type=["xlsx"])
    
    if file_risk:
        df_risk_raw = pd.read_excel(file_risk, index_col=0)
        risk = df_risk_raw.T
        
        # Parámetros Globales (Fila 4 = índice 3)
        tasa_descuento = risk['tasa_descuento'].iloc[3]
        anios = int(risk['horizonte_tiempo_anios'].iloc[3])
        tasa_captura_borde, tasa_captura_nucleo = 21.74, 32.60
        n_iter = 10000
        
        vars_excluir = ["ingreso_sp", "crecimiento_sp", "horizonte_tiempo_anios", "tasa_descuento"]
        vars_simular = [col for col in risk.columns if col not in vars_excluir]

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

        if st.button("Ejecutar Simulación Monte Carlo (10,000 iteraciones)"):
            with st.spinner('Simulando variables triangulares...'):
                # Muestreo Monte Carlo (Numpy vectorizado)
                simulaciones = {}
                for var in vars_simular:
                    min_v = risk[var].iloc[0]
                    mode_v = risk[var].iloc[1]
                    max_v = risk[var].iloc[2]
                    simulaciones[var] = np.random.triangular(min_v, mode_v, max_v, n_iter)
                
                df_sim = pd.DataFrame(simulaciones)
                vpn_resultados = df_sim.apply(calcular_vpn_iter, axis=1).values
                df_sim['VPN'] = vpn_resultados
                
                # Gráfica 1: Histograma interactivo
                st.subheader("1. Distribución de la VPN")
                fig_hist = px.histogram(df_sim, x="VPN", nbins=50, title="Histograma de VPN Simulada", 
                                        color_discrete_sequence=['#4C78A8'])
                p10, p50, p90 = np.percentile(vpn_resultados, [10, 50, 90])
                fig_hist.add_vline(x=p10, line_dash="dash", line_color="red", annotation_text=f"P10: ${p10:,.0f}")
                fig_hist.add_vline(x=p50, line_width=2, line_color="green", annotation_text=f"P50: ${p50:,.0f}")
                fig_hist.add_vline(x=p90, line_dash="dash", line_color="blue", annotation_text=f"P90: ${p90:,.0f}")
                st.plotly_chart(fig_hist, use_container_width=True)

                # Gráfica 2: Tornado Spearman
                st.subheader("2. Sensibilidad (Tornado Spearman)")
                correlaciones = {}
                for var in vars_simular:
                    corr, _ = stats.spearmanr(df_sim[var], df_sim['VPN'])
                    correlaciones[var] = corr
                
                df_corr = pd.DataFrame(list(correlaciones.items()), columns=['Variable', 'Correlacion']).sort_values('Correlacion')
                fig_tornado = px.bar(df_corr, x='Correlacion', y='Variable', orientation='h', 
                                     title="Impacto de las variables sobre la VPN",
                                     color='Correlacion', color_continuous_scale="RdYlGn")
                st.plotly_chart(fig_tornado, use_container_width=True)

        st.markdown("---")
        st.subheader("3. Modelo de Escalabilidad Sigmoidal")
        area_max = st.slider("Área Máxima a Simular (ha)", 10000, 200000, 100000, 5000)
        
        # Parámetros sigmoidal
        mult_max, mult_min, eficiencia_base = 3.0, 0.4, 1.0
        area_base = risk['area_total_proyecto_ha'].iloc[3]
        k_steepness = 0.0005
        area_inflexion = area_base - (np.log(((mult_max - mult_min) / (eficiencia_base - mult_min)) - 1) / k_steepness)

        def factor_sigmoidal(area):
            return mult_min + (mult_max - mult_min) / (1 + np.exp(k_steepness * (area - area_inflexion)))

        areas_simuladas = np.arange(1000, area_max + 500, 500)
        v_base = risk.iloc[1].to_dict() # Escenario Probable

        resultados_escala = []
        for ha in areas_simuladas:
            v_actual = v_base.copy()
            v_actual["area_total_proyecto_ha"] = ha
            f_escala = factor_sigmoidal(ha)
            
            # Aplicar factor
            v_actual["costo_monitoreo_snc_usd_ha_anio"] *= f_escala
            v_actual["capex_cercado_perimetral_snc_usd_ha_borde"] *= f_escala
            v_actual["factor_salvaguarda_snc_usd_ha_anio"] *= f_escala
            v_actual["capex_sp_usd_ha"] *= f_escala
            
            vpn_ha = calcular_vpn_iter(v_actual)
            resultados_escala.append({"Hectareas": ha, "VPN": vpn_ha, "Factor_Costo": f_escala})
            
        df_esc = pd.DataFrame(resultados_escala)
        
        # Encontrar Equilibrio
        df_eq = df_esc[df_esc['VPN'] >= 0]
        if not df_eq.empty:
            pto_eq = df_eq.iloc[0]['Hectareas']
            st.success(f"⚖️ Punto de Equilibrio alcanzado a las **{pto_eq:,.0f} Hectáreas**")
        else:
            st.error("El proyecto no alcanza punto de equilibrio en el rango simulado.")
            pto_eq = None
            
        col_graf1, col_graf2 = st.columns(2)
        
        with col_graf1:
            fig_vpn = px.line(df_esc, x="Hectareas", y="VPN", title="Evolución de VPN vs Área")
            fig_vpn.add_hline(y=0, line_dash="dash", line_color="red")
            if pto_eq:
                fig_vpn.add_vline(x=pto_eq, line_dash="dot", line_color="green", annotation_text="Break-even")
            st.plotly_chart(fig_vpn, use_container_width=True)
            
        with col_graf2:
            fig_factor = px.line(df_esc, x="Hectareas", y="Factor_Costo", title="Curva Sigmoidal (Eficiencia)")
            fig_factor.add_hline(y=1.0, line_dash="dash", line_color="blue", annotation_text="Punto Base (1.0)")
            fig_factor.add_hline(y=0.4, line_dash="dot", line_color="grey")
            st.plotly_chart(fig_factor, use_container_width=True)
