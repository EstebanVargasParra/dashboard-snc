import streamlit as st
import pandas as pd
import numpy as np
import scipy.stats as stats
import plotly.express as px
import plotly.graph_objects as go
import io
import numpy_financial as npf # NUEVA LIBRERÍA PARA LA TIR

# ==============================================================================
# CONFIGURACIÓN DE LA PÁGINA
# ==============================================================================
st.set_page_config(page_title="Dashboard Integral SNC", layout="wide", page_icon="🌿")

def calcular_npv(rate, cashflows):
    return sum([cf / (1 + rate)**i for i, cf in enumerate(cashflows)])

# ==============================================================================
# BARRA LATERAL (CARGA DE DATOS GLOBALES Y MERCADO)
# ==============================================================================
st.sidebar.title("🌿 Análisis Integral SNC")
st.sidebar.markdown("Para comenzar, carga tu archivo de parámetros financieros:")

url_plantilla = "https://raw.githubusercontent.com/TU_USUARIO/TU_REPO/main/Plantilla_Risk.xlsx"
st.sidebar.markdown(f"📥 [**Descargar Plantilla variables.xlsx**]({url_plantilla})")

# Nota: Cambié el texto para que el usuario sepa que sube 'variables.xlsx'
file_risk = st.sidebar.file_uploader("1. Sube tu archivo de variables (.xlsx)", type=["xlsx"])
st.sidebar.success("2. La base de datos GDB se carga automáticamente.")

# Cargamos la GDB localmente
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
    # 1. Procesamiento de variables.xlsx (Risk)
    df_risk_raw = pd.read_excel(file_risk, index_col=0)
    risk = df_risk_raw.T
    
    # Parámetros Fijos
    total_area_risk = float(risk['area_total_proyecto_ha'].iloc[3])
    relacion_borde_risk = float(risk['relacion_area_efecto_borde'].iloc[3])
    tasa_descuento = float(risk['tasa_descuento'].iloc[3])
    anios = int(risk['horizonte_tiempo_anios'].iloc[3])
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("💰 Variable de Mercado")
    precio_carbono_base = float(risk['precio_carbono_usd_tco2e'].iloc[1])
    precio_carbono_input = st.sidebar.number_input("Precio del Carbono (USD/tCO2e)", value=precio_carbono_base, step=0.5)

    st.title("Sistema de Modelado - Soluciones Naturales del Clima")
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 1. Incertidumbre MRV", 
        "☁️ 2. Factor de Emisión", 
        "💵 3. Análisis Técnico Económico", 
        "📈 4. Riesgos y Escalabilidad"
    ])

    # --------------------------------------------------------------------------
    # TAB 1: INCERTIDUMBRE MRV
    # --------------------------------------------------------------------------
    with tab1:
        st.subheader("🗄️ Base de Datos GDB (Vista Interactiva)")
        df_interactivo = st.data_editor(df_GDB, num_rows="dynamic", use_container_width=True, height=250)
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_GDB.to_excel(writer, index=False)
        st.download_button(label="📥 Descargar GDB Oficial (.xlsx)", data=buffer.getvalue(), file_name="GDB_Oficial.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        
        st.markdown("---")
        st.subheader("📈 Resultados de Incertidumbre por Ecosistema")
        
        df = df_interactivo.dropna(subset=['Valor']).copy()
        df['Valor'] = pd.to_numeric(df['Valor'], errors='coerce')
        df = df.dropna(subset=['Valor'])
        
        resumen = df.groupby(['Ecosistema', 'Medida']).agg(
            n_mediciones=('Valor', 'count'), promedio=('Valor', 'mean'),
            desviacion=('Valor', lambda x: x.std(ddof=1) if len(x) > 1 else 0)
        ).reset_index()
        
        resumen['ee'] = np.where(resumen['n_mediciones'] > 1, resumen['desviacion'] / np.sqrt(resumen['n_mediciones']), np.nan)
        resumen['t_val'] = np.where(resumen['n_mediciones'] > 1, stats.t.ppf(0.95, resumen['n_mediciones'] - 1), np.nan)
        
        condiciones = [(resumen['n_mediciones'] == 1) & (resumen['Medida'].isin(['BA', 'BT'])),
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
        borde_calc = total_area_risk * relacion_borde_risk
        nucleo_calc = total_area_risk - borde_calc

        st.info(f"**Área Total (Risk):** {total_area_risk:,.2f} ha | **Área Borde ({relacion_borde_risk*100}%):** {borde_calc:,.2f} ha | **Área Núcleo:** {nucleo_calc:,.2f} ha")

        st.markdown("---")
        df_valid = df_GDB.dropna(subset=['Valor'])
        df_BT = df_valid[df_valid['Medida'].isin(['BA', 'BT'])] 
        df_COS = df_valid[df_valid['Medida'] == 'COS']
        
        def format_bt(idx):
            row = df_BT.loc[idx]
            return f"{row.get('Ecosistema', '')} - {row.get('Estado', '')} | {row.get('Medida', '')}: {row['Valor']:.2f} tC/ha"
        def format_cos(idx):
            row = df_COS.loc[idx]
            return f"{row.get('Ecosistema', '')} - {row.get('Estado', '')} | {row.get('Medida', '')}: {row['Valor']:.2f} tC/ha"

        col_b, col_n = st.columns(2)
        with col_b:
            st.markdown("### Sector Borde")
            idx_bt_borde = st.selectbox("Biomasa Total (BT/BA)", options=df_BT.index, format_func=format_bt, index=0, key="bt_b")
            idx_cos_borde = st.selectbox("Carbono Orgánico Suelo (COS)", options=df_COS.index, format_func=format_cos, index=0, key="cos_b")
            BT_borde_val = float(df_BT.loc[idx_bt_borde, 'Valor'])
            COS_borde_val = float(df_COS.loc[idx_cos_borde, 'Valor'])
            
        with col_n:
            st.markdown("### Sector Núcleo")
            idx_def_bt = 1 if len(df_BT) > 1 else 0
            idx_def_cos = 1 if len(df_COS) > 1 else 0
            idx_bt_nucleo = st.selectbox("Biomasa Total (BT/BA)", options=df_BT.index, format_func=format_bt, index=idx_def_bt, key="bt_n")
            idx_cos_nucleo = st.selectbox("Carbono Orgánico Suelo (COS)", options=df_COS.index, format_func=format_cos, index=idx_def_cos, key="cos_n")
            BT_nucleo_val = float(df_BT.loc[idx_bt_nucleo, 'Valor'])
            COS_nucleo_val = float(df_COS.loc[idx_cos_nucleo, 'Valor'])

        st.markdown("---")
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        A1 = col_m1.number_input("Área Modelo 1 (A1)", value=25187.94)
        A2 = col_m2.number_input("Área Modelo 2 (A2)", value=12292.83)
        Mt1 = col_m3.number_input("Año Modelo 1 (Mt1)", value=2009)
        Mt2 = col_m4.number_input("Año Modelo 2 (Mt2)", value=2018)

        # Cálculos de Emisión
        BTe_borde = BT_borde_val * 0.47 * (44/12)
        COSe_borde = (COS_borde_val / 20) * (44/12)
        Fet_borde = (BTe_borde + COSe_borde) * 0.6
        cambio_superficie_borde = abs(((1/(Mt2-Mt1)) * np.log(A2/A1)) * borde_calc)
        CSV_borde = cambio_superficie_borde * (1 - 0.999)
        EAlb_borde = Fet_borde * cambio_superficie_borde
        EAp_borde = Fet_borde * CSV_borde
        Factor_borde = (EAlb_borde - EAp_borde) / borde_calc

        BTe_nucleo = BT_nucleo_val * 0.47 * (44/12)
        COSe_nucleo = (COS_nucleo_val / 20) * (44/12)
        Fet_nucleo = (BTe_nucleo + COSe_nucleo) * 0.6
        cambio_superficie_nucleo = abs(((1/(Mt2-Mt1)) * np.log(A2/A1)) * nucleo_calc)
        CSV_nucleo = cambio_superficie_nucleo * (1 - 0.97)
        EAlb_nucleo = Fet_nucleo * cambio_superficie_nucleo
        EAp_nucleo = Fet_nucleo * CSV_nucleo
        Factor_nucleo = (EAlb_nucleo - EAp_nucleo) / nucleo_calc

        st.subheader("✅ Factores de Emisión Finales")
        c_res1, c_res2 = st.columns(2)
        c_res1.metric("Factor Borde", f"{Factor_borde:.4f} tCO2e/ha/año")
        c_res2.metric("Factor Núcleo", f"{Factor_nucleo:.4f} tCO2e/ha/año")

    # --------------------------------------------------------------------------
    # TAB 3: ANÁLISIS TÉCNICO ECONÓMICO (NUEVO MÓDULO)
    # --------------------------------------------------------------------------
    with tab3:
        st.subheader("💵 Flujo de Caja y Viabilidad del Proyecto")
        
        c_t1, c_t2 = st.columns(2)
        anio_inicio = c_t1.number_input("Año de Inicio", value=2027, step=1)
        proyeccion = c_t2.number_input("Años de Proyección", value=30, step=1)
        
        if st.button("Generar Flujo de Caja", type="primary"):
            with st.spinner("Construyendo proyecciones financieras..."):
                # Creación del DataFrame equivalente a tu script de R
                anios_arr = np.arange(anio_inicio, anio_inicio + proyeccion + 1)
                df_tec = pd.DataFrame({'Proyecciones': anios_arr})
                
                # 1. Áreas
                df_tec['area_borde_proyecto_ha'] = 0.0
                df_tec['area_nucleo_proyecto_ha'] = 0.0
                if proyeccion >= 2:
                    df_tec.loc[1:2, 'area_borde_proyecto_ha'] = total_area_risk * relacion_borde_risk / 2
                    df_tec.loc[1:2, 'area_nucleo_proyecto_ha'] = total_area_risk * (1 - relacion_borde_risk) / 2
                
                df_tec['area_acumulada_borde_anual_ha'] = df_tec['area_borde_proyecto_ha'].cumsum()
                df_tec.loc[0, 'area_acumulada_borde_anual_ha'] = 0.0
                df_tec['area_acumulada_nucleo_anual_ha'] = df_tec['area_nucleo_proyecto_ha'].cumsum()
                df_tec.loc[0, 'area_acumulada_nucleo_anual_ha'] = 0.0
                
                # 2. Carbono
                df_tec['emisiones_evitas_eficiencia_tco2e'] = (df_tec['area_acumulada_borde_anual_ha']*Factor_borde + df_tec['area_acumulada_nucleo_anual_ha']*Factor_nucleo) * float(risk['eficiencia_snc'].iloc[3])
                df_tec['salvaguarda_tecnica_tco2e'] = df_tec['emisiones_evitas_eficiencia_tco2e'] * float(risk['descuento_salvaguarda_tecnica'].iloc[3])
                df_tec['cambio_regulacion_tco2e'] = df_tec['emisiones_evitas_eficiencia_tco2e'] * float(risk['descuento_cambio_regulacion'].iloc[3])
                df_tec['variabilidad_climatica_tco2e'] = df_tec['cambio_regulacion_tco2e']
                df_tec['carbono_acreditable_tco2e'] = df_tec['emisiones_evitas_eficiencia_tco2e'] - df_tec['salvaguarda_tecnica_tco2e'] - df_tec['cambio_regulacion_tco2e'] - df_tec['variabilidad_climatica_tco2e']
                
                # 3. Precios
                precios = precio_carbono_input * (1 + float(risk['incremento_precio_carbono'].iloc[3]))**np.arange(0, proyeccion + 1)
                df_tec['precio_carbono_trading_usd_tco2e'] = 0.0
                df_tec.loc[1:, 'precio_carbono_trading_usd_tco2e'] = precios[:-1] # Desfase equivalente al R
                df_tec['precio_carbono_ecp_usd_tco2e'] = df_tec['precio_carbono_trading_usd_tco2e']
                
                # 4. CAPEX
                df_tec['capex_estudios_snc_usd'] = 0.0
                df_tec.loc[0, 'capex_estudios_snc_usd'] = float(risk['capex_estudios_habilitantes_snc_usd'].iloc[3])
                
                fac_aisla = 1.0 if float(risk['relacion_area_aislamiento_area_snc'].iloc[3]) == 0 else float(risk['relacion_area_aislamiento_area_snc'].iloc[3])
                df_tec['capex_conservacion_snc_usd'] = 0.0
                if proyeccion >= 2:
                    df_tec.loc[1, 'capex_conservacion_snc_usd'] = df_tec.loc[1, 'area_borde_proyecto_ha'] * float(risk['capex_snc_usd_ha'].iloc[3]) * fac_aisla + float(risk['siembra_arboles'].iloc[3])
                    df_tec.loc[2, 'capex_conservacion_snc_usd'] = df_tec.loc[2, 'area_borde_proyecto_ha'] * float(risk['capex_snc_usd_ha'].iloc[3]) * fac_aisla + float(risk['siembra_arboles'].iloc[3])
                
                # 5. OPEX SNC
                df_tec['opex_mantenimiento_snc_usd'] = 0.0
                if proyeccion >= 2:
                    df_tec.loc[1:2, 'opex_mantenimiento_snc_usd'] = df_tec.loc[1:2, 'area_acumulada_borde_anual_ha'] * float(risk['capex_snc_usd_ha'].iloc[3]) * float(risk['operación_relacion_capex_snc'].iloc[3]) * fac_aisla
                for i in range(3, len(df_tec)):
                    df_tec.loc[i, 'opex_mantenimiento_snc_usd'] = df_tec.loc[i-1, 'opex_mantenimiento_snc_usd'] * 1.03
                
                df_tec['costo_salvaguarda_snc_usd_anio'] = 0.0
                if proyeccion >= 3:
                    df_tec.loc[1:3, 'costo_salvaguarda_snc_usd_anio'] = (df_tec.loc[1:3, 'area_acumulada_borde_anual_ha'] + df_tec.loc[1:3, 'area_acumulada_nucleo_anual_ha']) * float(risk['factor_salvaguarda_snc_usd_ha_anio'].iloc[3]) * 2
                
                df_tec['costo_monitoreo_snc_usd'] = float(risk['monitoreo_snc_usd_ha_anio'].iloc[3]) * (df_tec['area_acumulada_borde_anual_ha'] + df_tec['area_acumulada_nucleo_anual_ha'])
                
                df_tec['imprevistos_snc_usd'] = float(risk['factor_imprevistos_snc_usd_ha'].iloc[3]) * (df_tec['area_acumulada_borde_anual_ha'] + df_tec['area_acumulada_nucleo_anual_ha'])
                df_tec.loc[18:, 'imprevistos_snc_usd'] = 0.0
                
                df_tec['costo_transaccion_usd'] = 0.0
                costo_trans_base = (0.06014 * total_area_risk) + 25259
                trans_years = np.arange(anio_inicio + 2, anio_inicio + proyeccion + 1, 3)
                df_tec.loc[df_tec['Proyecciones'].isin(trans_years), 'costo_transaccion_usd'] = costo_trans_base
                
                # 6. Sistema Productivo (SP)
                fac_aisla_sp = 1.0 if float(risk['relacion_area_sp_area_snc'].iloc[3]) == 0 else float(risk['relacion_area_sp_area_snc'].iloc[3])
                df_tec['capex_sistema_productivo_usd'] = 0.0
                df_tec.loc[0, 'capex_sistema_productivo_usd'] = total_area_risk * float(risk['capex_sp_usd_ha'].iloc[3]) * fac_aisla_sp
                
                df_tec['opex_mantenimiento_sp_usd'] = 0.0
                if proyeccion >= 10:
                    df_tec.loc[1:10, 'opex_mantenimiento_sp_usd'] = df_tec.loc[0, 'capex_sistema_productivo_usd'] * float(risk['opex_sp'].iloc[3])
                
                # 7. Totales OPEX e Ingresos
                cols_opex = ['opex_mantenimiento_snc_usd', 'costo_salvaguarda_snc_usd_anio', 'costo_monitoreo_snc_usd', 'imprevistos_snc_usd', 'costo_transaccion_usd', 'capex_sistema_productivo_usd', 'opex_mantenimiento_sp_usd']
                df_tec['egresos_opex_totales_usd'] = df_tec[cols_opex].sum(axis=1)
                df_tec.loc[0, 'egresos_opex_totales_usd'] = 0.0
                
                df_tec['ingresos_carbono_trading_usd'] = df_tec['carbono_acreditable_tco2e'] * df_tec['precio_carbono_trading_usd_tco2e']
                df_tec['ingresos_sp_usd'] = 0.0
                if proyeccion >= 1:
                    df_tec.loc[1, 'ingresos_sp_usd'] = df_tec.loc[0, 'capex_sistema_productivo_usd'] * float(risk['ingreso_sp'].iloc[3])
                for i in range(2, len(df_tec)):
                    df_tec.loc[i, 'ingresos_sp_usd'] = df_tec.loc[i-1, 'ingresos_sp_usd'] * (1 + float(risk['crecimiento_sp'].iloc[3]))
                
                df_tec['ebitda_trading_usd'] = df_tec['ingresos_carbono_trading_usd'] - df_tec['egresos_opex_totales_usd']
                
                # 8. Depreciación y Financieros
                df_tec['depreciacion_trading_usd'] = 0.0
                if proyeccion >= 1: df_tec.loc[1, 'depreciacion_trading_usd'] = (df_tec.loc[0, 'capex_sistema_productivo_usd']/10) + (df_tec.loc[1, 'capex_conservacion_snc_usd']/20)
                if proyeccion >= 10: df_tec.loc[2:10, 'depreciacion_trading_usd'] = df_tec.loc[1, 'depreciacion_trading_usd'] + (df_tec.loc[2, 'capex_conservacion_snc_usd']/20)
                if proyeccion >= 20: df_tec.loc[11:20, 'depreciacion_trading_usd'] = (df_tec.loc[1, 'capex_conservacion_snc_usd']/20) + (df_tec.loc[2, 'capex_conservacion_snc_usd']/20)
                if proyeccion >= 21: df_tec.loc[21, 'depreciacion_trading_usd'] = df_tec.loc[2, 'capex_conservacion_snc_usd']/20
                
                df_tec['ebit_trading_usd'] = df_tec['ebitda_trading_usd'] - df_tec['depreciacion_trading_usd']
                df_tec['impuestos_trading_usd'] = df_tec['ebit_trading_usd'] * float(risk['tasa_impuestos'].iloc[3])
                df_tec['utilidad_neta_trading_usd'] = df_tec['ebitda_trading_usd'] - df_tec['impuestos_trading_usd']
                
                df_tec['flujo_caja_libre_trading_usd'] = df_tec['utilidad_neta_trading_usd'] - df_tec['capex_sistema_productivo_usd'] - df_tec['capex_conservacion_snc_usd'] - df_tec['capex_estudios_snc_usd']
                
                df_tec['impuestos_comunidad_usd'] = df_tec['ingresos_sp_usd'] * float(risk['tasa_impuestos'].iloc[3])
                df_tec['utilidad_neta_comunidad_usd'] = df_tec['ingresos_sp_usd'] - df_tec['impuestos_comunidad_usd']
                
                # 9. Cálculo de VPN, TIR y MAC
                flujos_trading = df_tec['flujo_caja_libre_trading_usd'].values
                flujos_comunidad = df_tec['impuestos_comunidad_usd'].values
                
                vpn_precio_usd = calcular_npv(tasa_descuento, flujos_trading)
                vpn_comunidad_usd = calcular_npv(tasa_descuento, flujos_comunidad)
                vpn_total = vpn_precio_usd + vpn_comunidad_usd
                
                # TIR con Numpy Financial
                tir_trading = npf.irr(flujos_trading[:-1]) if len(flujos_trading) > 1 else np.nan
                
                carbono_total = df_tec['carbono_acreditable_tco2e'].sum()
                mac_usd = -(vpn_total / carbono_total) if carbono_total > 0 else np.nan
                
                # 10. Visualización de Resultados
                st.success("Cálculo completado exitosamente.")
                col_k1, col_k2, col_k3, col_k4 = st.columns(4)
                col_k1.metric("VPN Trading + Comunidad", f"${vpn_total:,.0f}")
                col_k2.metric("TIR Trading", f"{tir_trading*100:.2f}%" if not np.isnan(tir_trading) else "N/A")
                col_k3.metric("Carbono Acreditable", f"{carbono_total:,.0f} tCO2e")
                col_k4.metric("Costo Marginal (MAC)", f"${mac_usd:,.2f} /tCO2e")
                
                # Gráfica de Cascada Flujo de Caja
                fig_fcl = px.bar(df_tec, x='Proyecciones', y='flujo_caja_libre_trading_usd', 
                                 title="Flujo de Caja Libre (Trading) por Año",
                                 labels={'flujo_caja_libre_trading_usd': 'Flujo (USD)'})
                fig_fcl.update_traces(marker_color=np.where(df_tec["flujo_caja_libre_trading_usd"]<0, 'red', 'green'))
                st.plotly_chart(fig_fcl, use_container_width=True)
                
                with st.expander("Ver Tabla Detallada (Flujo de Caja)"):
                    st.dataframe(df_tec.style.format(precision=2), use_container_width=True)
                    
                # Botón Descarga Flujo
                buf_flujo = io.BytesIO()
                df_tec.to_excel(buf_flujo, index=False)
                st.download_button("📥 Descargar Análisis Técnico (.xlsx)", buf_flujo.getvalue(), "Analisis_Tecnico.xlsx")

    # --------------------------------------------------------------------------
    # TAB 4: RIESGOS Y ESCALABILIDAD
    # --------------------------------------------------------------------------
    with tab4:
        st.subheader("🔗 1. Tasas Biológicas (Heredadas de Pestaña 2)")
        col_b, col_n = st.columns(2)
        tasa_captura_borde = col_b.number_input("Tasa Captura Borde", value=Factor_borde, disabled=True)
        tasa_captura_nucleo = col_n.number_input("Tasa Captura Núcleo", value=Factor_nucleo, disabled=True)
        
        st.subheader("⚙️ 2. Configuración de Escalabilidad")
        c1, c2, c3 = st.columns(3)
        area_minima = c1.number_input("Área Mínima a simular (ha)", value=1000, step=500)
        area_maxima = c2.number_input("Área Máxima a simular (ha)", value=100000, step=5000)
        intervalo_sim = c3.number_input("Intervalo de simulación (ha)", value=500, step=100)
        
        c4, c5, c6, c7 = st.columns(4)
        mult_max = c4.number_input("Tope Máximo Costos", value=3.0, step=0.1)
        mult_min = c5.number_input("Tope Mínimo Costos", value=0.4, step=0.1)
        eficiencia_base = c6.number_input("Eficiencia Base", value=1.0, step=0.1)
        area_inflexion = c7.number_input("Área de Inflexión (ha)", value=10000, step=1000)
        
        st.markdown("---")
        
        # ⚠️ Exclusiones actualizadas con tus nuevas variables
        vars_excluir = ["ingreso_sp", "crecimiento_sp", "horizonte_tiempo_anios", "tasa_descuento", "precio_carbono_usd_tco2e"]
        vars_simular = [col for col in risk.columns if col not in vars_excluir]

        def calcular_vpn_iter(v):
            area_total = v["area_total_proyecto_ha"]
            p_borde = v["relacion_area_efecto_borde"] # Actualizado a tu nuevo nombre
            area_borde = area_total * p_borde
            area_nucleo = area_total * (1 - p_borde)
            area_sp = area_total * v["relacion_area_sp_area_snc"]
            tasa_captura_ha = (p_borde * tasa_captura_borde) + ((1 - p_borde) * tasa_captura_nucleo)
            
            # Capex con nuevas variables
            capex_snc = v["capex_estudios_habilitantes_snc_usd"] + (v["capex_snc_usd_ha"] * area_borde)
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
            
            # Precios controlados globalmente por el panel lateral y variable de incremento
            precios = precio_carbono_input * (1 + v["incremento_precio_carbono"])**np.arange(1, anios + 1)
            ingresos = np.zeros(anios + 1)
            ingresos[1:] = vol_creditos * precios
            
            flujos = ingresos - vector_opex
            flujos = np.where(flujos > 0, flujos * (1 - v["tasa_impuestos"]), flujos)
            flujos[0] = -capex_real
            
            return calcular_npv(tasa_descuento, flujos)

        if st.button("🚀 Ejecutar Simulación Integral de Riesgo", type="primary"):
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
                try:
                    k_steepness = np.log(((mult_max - mult_min) / (eficiencia_base - mult_min)) - 1) / (total_area_risk - area_inflexion)
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
                    
                    # Nuevas variables de opex para el escalado
                    v_actual["monitoreo_snc_usd_ha_anio"] *= f_escala
                    v_actual["capex_snc_usd_ha"] *= f_escala
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
    st.info("👈 Por favor, carga tu archivo 'variables.xlsx' en el menú lateral izquierdo para desplegar el modelo.")



