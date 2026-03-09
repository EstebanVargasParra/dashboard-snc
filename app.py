import streamlit as st
import pandas as pd
import numpy as np
import scipy.stats as stats
import plotly.express as px
import plotly.graph_objects as go
import io
import numpy_financial as npf

# ==============================================================================
# CONFIGURACIÓN Y MEMORIA DE SESIÓN
# ==============================================================================
st.set_page_config(page_title="Dashboard Integral SNC", layout="wide", page_icon="🌿")

if 'macc_data' not in st.session_state:
    st.session_state.macc_data = []
if 'last_computed' not in st.session_state:
    st.session_state.last_computed = False
if 'last_mac' not in st.session_state:
    st.session_state.last_mac = 0.0
if 'last_vol' not in st.session_state:
    st.session_state.last_vol = 0.0

def calcular_npv(rate, cashflows):
    return sum([cf / (1 + rate)**i for i, cf in enumerate(cashflows)])

def parse_mixed_type(val):
    """Convierte los valores visuales (ej. '20%') en flotantes matemáticos (0.20)"""
    if isinstance(val, str):
        val = val.strip()
        if val.endswith('%'):
            return float(val.replace('%', '')) / 100.0
        else:
            return float(val)
    return float(val)

# ==============================================================================
# 1. BASE DE DATOS DE VARIABLES POR DEFECTO 
# ==============================================================================
default_vars = {
    "Variables": [
        "area_total_proyecto_ha", "relacion_area_efecto_borde", "eficiencia_snc",
        "descuento_salvaguarda_tecnica", "descuento_cambio_regulacion", "descuento_variabilidad_climatica",
        "precio_carbono_usd_tco2e", "incremento_precio_carbono", "capex_estudios_habilitantes_snc_usd",
        "capex_snc_usd_ha", "siembra_arboles", "relacion_area_aislamiento_area_snc",
        "operación_relacion_capex_snc", "factor_salvaguarda_snc_usd_ha_anio", "monitoreo_snc_usd_ha_anio",
        "factor_imprevistos_snc_usd_ha", "relacion_area_sp_area_snc", "capex_sp_usd_ha",
        "opex_sp", "ingreso_sp", "crecimiento_sp", "horizonte_tiempo_anios",
        "tasa_impuestos", "tasa_descuento", "variabilidad_sistema_productivo"
    ],
    "Bajo": [4000, "20%", "70%", "18%", "1%", "1%", 5, "4.97%", 80000, 150, 0, "20%", "5%", 4, 8, 0.5, "3%", 30, "10%", "30%", "1.0%", 20, "30%", "10%", "100%"],
    "Probable": [30100, "30%", "80%", "20%", "2%", "2%", 14.75, "6.57%", 100000, 600, 0, "25%", "10%", 5.3, 9.2, 0.6, "5%", 1800, "14%", "35%", "1.2%", 30, "35%", "12%", "105%"],
    "Alto": [181308, "40%", "90%", "30%", "3%", "3%", 16.95, "9.60%", 120000, 800, 0, "50%", "15%", 7, 12, 0.7, "7%", 2500, "20%", "40%", "1.5%", 40, "40%", "15%", "110%"]
}
# Regla estricta: Analisis_Parametrico siempre igual a Probable por defecto
default_vars["Analisis_Parametrico"] = default_vars["Probable"].copy()

# Guardamos en sesión para que los cambios se mantengan
if 'df_risk' not in st.session_state:
    df_inicial = pd.DataFrame(default_vars)
    # Forzamos todo a string para que el editor de Streamlit permita mezclar números y porcentajes sin bloquearse
    for col in ["Bajo", "Probable", "Alto", "Analisis_Parametrico"]:
        df_inicial[col] = df_inicial[col].astype(str)
    st.session_state.df_risk = df_inicial

# ==============================================================================
# BARRA LATERAL LIMPIA
# ==============================================================================
st.sidebar.title("🌿 Análisis Integral SNC")
st.sidebar.info("La plataforma opera de forma autónoma. Puedes modificar todas las variables de proyecto directamente en la **Pestaña 2**.")

# Cargamos la GDB localmente
try:
    df_GDB = pd.read_excel("GDB.xlsx")
    gdb_cargada = True
    st.sidebar.success("✅ Base maestra GDB conectada.")
except Exception as e:
    st.error(f"Error al cargar GDB.xlsx: {e}")
    gdb_cargada = False

# ==============================================================================
# FLUJO PRINCIPAL 
# ==============================================================================
if gdb_cargada:
    
    st.title("Sistema de Modelado - Soluciones Naturales del Clima")
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 1. Incertidumbre MRV", 
        "☁️ 2. Factores y Variables", 
        "💵 3. Análisis Técnico Financiero", 
        "📈 4. Análisis Probabilístico del TEA",
        "📉 5. Curvas MACC"
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
        st.download_button("📥 Descargar GDB Oficial (.xlsx)", data=buffer.getvalue(), file_name="GDB_Oficial.xlsx")
        
        st.markdown("---")
        st.subheader("📈 Resultados de Incertidumbre por Ecosistema")
        
        df = df_interactivo.dropna(subset=['Valor']).copy()
        df['Valor'] = pd.to_numeric(df['Valor'], errors='coerce')
        df = df.dropna(subset=['Valor'])
        
        resumen = df.groupby(['Ecosistema', 'Medida']).agg(n_mediciones=('Valor', 'count'), promedio=('Valor', 'mean'), desviacion=('Valor', lambda x: x.std(ddof=1) if len(x) > 1 else 0)).reset_index()
        resumen['ee'] = np.where(resumen['n_mediciones'] > 1, resumen['desviacion'] / np.sqrt(resumen['n_mediciones']), np.nan)
        resumen['t_val'] = np.where(resumen['n_mediciones'] > 1, stats.t.ppf(0.95, resumen['n_mediciones'] - 1), np.nan)
        
        condiciones = [(resumen['n_mediciones'] == 1) & (resumen['Medida'].isin(['BA', 'BT'])), (resumen['n_mediciones'] == 1) & (resumen['Medida'] == 'COS'), (resumen['n_mediciones'] == 1)]
        resumen['incertidumbre_pct'] = np.where(resumen['n_mediciones'] > 1, (resumen['t_val'] * resumen['ee'] / resumen['promedio']) * 100, np.select(condiciones, [80.0, 90.0, 85.0], default=np.nan))
        
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
    # TAB 2: FACTORES DE EMISIÓN + MATRIZ DE VARIABLES
    # --------------------------------------------------------------------------
    with tab2:
        # PARTE 1: FACTORES DE EMISIÓN
        st.subheader("🌲 Parámetros del Modelo de Carbono")
        
        df_valid = df_GDB.dropna(subset=['Valor'])
        df_BT = df_valid[df_valid['Medida'].isin(['BA', 'BT'])] 
        df_COS = df_valid[df_valid['Medida'] == 'COS']
        
        def format_bt(idx): return f"{df_BT.loc[idx,'Ecosistema']} - {df_BT.loc[idx,'Estado']} | {df_BT.loc[idx,'Medida']}: {df_BT.loc[idx,'Valor']:.2f} tC/ha"
        def format_cos(idx): return f"{df_COS.loc[idx,'Ecosistema']} - {df_COS.loc[idx,'Estado']} | {df_COS.loc[idx,'Medida']}: {df_COS.loc[idx,'Valor']:.2f} tC/ha"

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

        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        A1 = col_m1.number_input("Área Modelo 1 (A1)", value=25187.94)
        A2 = col_m2.number_input("Área Modelo 2 (A2)", value=12292.83)
        Mt1 = col_m3.number_input("Año Modelo 1 (Mt1)", value=2009)
        Mt2 = col_m4.number_input("Año Modelo 2 (Mt2)", value=2018)

        # Cálculo Temporal de Emisión
        # (El área real se calculará en la matriz de variables para mantener sincronía)
        BTe_borde = BT_borde_val * 0.47 * (44/12)
        COSe_borde = (COS_borde_val / 20) * (44/12)
        Fet_borde = (BTe_borde + COSe_borde) * 0.6
        
        BTe_nucleo = BT_nucleo_val * 0.47 * (44/12)
        COSe_nucleo = (COS_nucleo_val / 20) * (44/12)
        Fet_nucleo = (BTe_nucleo + COSe_nucleo) * 0.6
        
        # PARTE 2: MATRIZ DE VARIABLES INTEGRADA
        st.markdown("---")
        st.subheader("📝 Matriz de Variables de Riesgo")
        st.markdown("Haz doble clic en cualquier celda para editar (puedes usar el símbolo `%`). Cuando termines, presiona el botón para guardar los cambios.")
        
        df_edited = st.data_editor(
            st.session_state.df_risk, 
            use_container_width=True, 
            hide_index=True,
            key="variables_editor"
        )
        
        if st.button("✅ Confirmar y Aplicar Variables", type="primary"):
            st.session_state.df_risk = df_edited.copy()
            st.success("¡Variables guardadas con éxito! Los módulos 3, 4 y 5 han sido actualizados.")

        # Procesamiento Matemático del DataFrame Guardado en Sesión
        df_numeric = st.session_state.df_risk.copy()
        for col in ["Bajo", "Probable", "Alto", "Analisis_Parametrico"]:
            df_numeric[col] = df_numeric[col].apply(parse_mixed_type)
        
        df_numeric.set_index("Variables", inplace=True)
        df_numeric.index = df_numeric.index.str.strip().str.lower()
        risk = df_numeric.T
        risk.columns = risk.columns.str.strip().str.lower()

        # Extracción de variables paramétricas globales
        total_area_risk = float(risk['area_total_proyecto_ha'].iloc[3])
        relacion_borde_risk = float(risk['relacion_area_efecto_borde'].iloc[3])
        tasa_descuento = float(risk['tasa_descuento'].iloc[3])
        anios = int(risk['horizonte_tiempo_anios'].iloc[3])
        precio_carbono_input = float(risk['precio_carbono_usd_tco2e'].iloc[3])
        
        borde_calc = total_area_risk * relacion_borde_risk
        nucleo_calc = total_area_risk - borde_calc

        # Terminar Cálculo de Factores
        cambio_superficie_borde = abs(((1/(Mt2-Mt1)) * np.log(A2/A1)) * borde_calc)
        CSV_borde = cambio_superficie_borde * (1 - 0.999)
        Factor_borde = (Fet_borde * cambio_superficie_borde - Fet_borde * CSV_borde) / borde_calc

        cambio_superficie_nucleo = abs(((1/(Mt2-Mt1)) * np.log(A2/A1)) * nucleo_calc)
        CSV_nucleo = cambio_superficie_nucleo * (1 - 0.97)
        Factor_nucleo = (Fet_nucleo * cambio_superficie_nucleo - Fet_nucleo * CSV_nucleo) / nucleo_calc

        st.subheader("✅ Factores de Emisión Finales")
        c_res1, c_res2, c_res3 = st.columns(3)
        c_res1.metric("Factor Borde", f"{Factor_borde:.4f} tCO2e/ha-año")
        c_res2.metric("Factor Núcleo", f"{Factor_nucleo:.4f} tCO2e/ha-año")
        c_res3.metric("Área Total Paramétrica", f"{total_area_risk:,.0f} ha")

    # --------------------------------------------------------------------------
    # TAB 3: ANÁLISIS TÉCNICO ECONÓMICO (FLUJO DE CAJA)
    # --------------------------------------------------------------------------
    with tab3:
        st.subheader("💵 Flujo de Caja y Viabilidad del Proyecto")
        
        c_t1, c_t2 = st.columns(2)
        anio_inicio = c_t1.number_input("Año de Inicio", value=2027, step=1)
        proyeccion = c_t2.number_input("Años de Proyección", value=anios, step=1)
        
        if st.button("Generar Flujo de Caja", type="primary"):
            with st.spinner("Construyendo proyecciones financieras..."):
                anios_arr = np.arange(anio_inicio, anio_inicio + proyeccion + 1)
                df_tec = pd.DataFrame({'Proyecciones': anios_arr})
                
                df_tec['area_borde_proyecto_ha'] = 0.0
                df_tec['area_nucleo_proyecto_ha'] = 0.0
                
                area_borde_calc = total_area_risk * relacion_borde_risk / 2
                area_nucleo_calc = total_area_risk * (1 - relacion_borde_risk) / 2
                
                mask_años = df_tec['Proyecciones'].isin([anio_inicio + 1, anio_inicio + 2])
                df_tec.loc[mask_años, 'area_borde_proyecto_ha'] = area_borde_calc
                df_tec.loc[mask_años, 'area_nucleo_proyecto_ha'] = area_nucleo_calc
                
                df_tec['area_acumulada_borde_anual_ha'] = df_tec['area_borde_proyecto_ha'].cumsum()
                df_tec['area_acumulada_nucleo_anual_ha'] = df_tec['area_nucleo_proyecto_ha'].cumsum()
                df_tec.loc[df_tec['Proyecciones'] < anio_inicio + 1, ['area_acumulada_borde_anual_ha', 'area_acumulada_nucleo_anual_ha']] = 0.0
                
                df_tec['emisiones_evitas_eficiencia_tco2e'] = (df_tec['area_acumulada_borde_anual_ha']*Factor_borde + df_tec['area_acumulada_nucleo_anual_ha']*Factor_nucleo) * float(risk['eficiencia_snc'].iloc[3])
                df_tec['salvaguarda_tecnica_tco2e'] = df_tec['emisiones_evitas_eficiencia_tco2e'] * float(risk['descuento_salvaguarda_tecnica'].iloc[3])
                df_tec['cambio_regulacion_tco2e'] = df_tec['emisiones_evitas_eficiencia_tco2e'] * float(risk['descuento_cambio_regulacion'].iloc[3])
                df_tec['variabilidad_climatica_tco2e'] = df_tec['cambio_regulacion_tco2e']
                
                df_tec['carbono_acreditable_tco2e'] = df_tec['emisiones_evitas_eficiencia_tco2e'] - df_tec['salvaguarda_tecnica_tco2e'] - df_tec['cambio_regulacion_tco2e'] - df_tec['variabilidad_climatica_tco2e']
                
                precios = precio_carbono_input * (1 + float(risk['incremento_precio_carbono'].iloc[3]))**np.arange(0, proyeccion + 1)
                df_tec['precio_carbono_trading_usd_tco2e'] = 0.0
                df_tec.loc[df_tec['Proyecciones'] >= anio_inicio + 1, 'precio_carbono_trading_usd_tco2e'] = precios[:proyeccion]
                df_tec['precio_carbono_ecp_usd_tco2e'] = df_tec['precio_carbono_trading_usd_tco2e']
                
                df_tec['capex_estudios_snc_usd'] = 0.0
                df_tec.loc[0, 'capex_estudios_snc_usd'] = float(risk['capex_estudios_habilitantes_snc_usd'].iloc[3])
                
                fac_aisla = 1.0 if float(risk['relacion_area_aislamiento_area_snc'].iloc[3]) == 0 else float(risk['relacion_area_aislamiento_area_snc'].iloc[3])
                df_tec['capex_conservacion_snc_usd'] = 0.0
                if proyeccion >= 2:
                    df_tec.loc[0, 'capex_conservacion_snc_usd'] = df_tec.loc[1, 'area_borde_proyecto_ha'] * float(risk['capex_snc_usd_ha'].iloc[3]) * fac_aisla + float(risk['siembra_arboles'].iloc[3])
                    df_tec.loc[1, 'capex_conservacion_snc_usd'] = df_tec.loc[2, 'area_borde_proyecto_ha'] * float(risk['capex_snc_usd_ha'].iloc[3]) * fac_aisla + float(risk['siembra_arboles'].iloc[3])
                
                df_tec['opex_mantenimiento_snc_usd'] = 0.0
                if proyeccion >= 2:
                    df_tec.loc[1:2, 'opex_mantenimiento_snc_usd'] = df_tec.loc[1:2, 'area_acumulada_borde_anual_ha'] * float(risk['capex_snc_usd_ha'].iloc[3]) * float(risk['operación_relacion_capex_snc'].iloc[3]) * fac_aisla
                for i in range(3, len(df_tec)):
                    df_tec.loc[i, 'opex_mantenimiento_snc_usd'] = df_tec.loc[i-1, 'opex_mantenimiento_snc_usd'] * 1.03
                
                df_tec['costo_salvaguarda_snc_usd_anio'] = 0.0
                if proyeccion >= 3:
                    val_salv = (df_tec.loc[1, 'area_acumulada_borde_anual_ha'] + df_tec.loc[1, 'area_acumulada_nucleo_anual_ha']) * float(risk['factor_salvaguarda_snc_usd_ha_anio'].iloc[3]) * 2
                    df_tec.loc[1:3, 'costo_salvaguarda_snc_usd_anio'] = val_salv
                
                df_tec['costo_monitoreo_snc_usd'] = float(risk['monitoreo_snc_usd_ha_anio'].iloc[3]) * (df_tec['area_acumulada_borde_anual_ha'] + df_tec['area_acumulada_nucleo_anual_ha'])
                
                df_tec['imprevistos_snc_usd'] = float(risk['factor_imprevistos_snc_usd_ha'].iloc[3]) * (df_tec['area_acumulada_borde_anual_ha'] + df_tec['area_acumulada_nucleo_anual_ha'])
                df_tec.loc[18:, 'imprevistos_snc_usd'] = 0.0
                
                df_tec['costo_transaccion_usd'] = 0.0
                costo_trans_base = (0.06014 * total_area_risk) + 25259
                trans_years = np.arange(anio_inicio + 2, anio_inicio + proyeccion + 1, 3)
                df_tec.loc[df_tec['Proyecciones'].isin(trans_years), 'costo_transaccion_usd'] = costo_trans_base
                
                fac_aisla_sp = 1.0 if float(risk['relacion_area_sp_area_snc'].iloc[3]) == 0 else float(risk['relacion_area_sp_area_snc'].iloc[3])
                df_tec['capex_sistema_productivo_usd'] = 0.0
                df_tec.loc[0, 'capex_sistema_productivo_usd'] = total_area_risk * float(risk['capex_sp_usd_ha'].iloc[3]) * fac_aisla_sp
                
                df_tec['opex_mantenimiento_sp_usd'] = 0.0
                if proyeccion >= 10:
                    df_tec.loc[1:10, 'opex_mantenimiento_sp_usd'] = df_tec.loc[0, 'capex_sistema_productivo_usd'] * float(risk['opex_sp'].iloc[3])
                
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
                
                df_tec['depreciacion_trading_usd'] = 0.0
                if proyeccion >= 1: df_tec.loc[1, 'depreciacion_trading_usd'] = (df_tec.loc[0, 'capex_sistema_productivo_usd']/10) + (df_tec.loc[0, 'capex_conservacion_snc_usd']/20)
                if proyeccion >= 10: df_tec.loc[2:10, 'depreciacion_trading_usd'] = df_tec.loc[1, 'depreciacion_trading_usd'] + (df_tec.loc[1, 'capex_conservacion_snc_usd']/20)
                if proyeccion >= 20: df_tec.loc[11:20, 'depreciacion_trading_usd'] = (df_tec.loc[0, 'capex_conservacion_snc_usd']/20) + (df_tec.loc[1, 'capex_conservacion_snc_usd']/20)
                if proyeccion >= 21: df_tec.loc[21, 'depreciacion_trading_usd'] = df_tec.loc[1, 'capex_conservacion_snc_usd']/20
                
                df_tec['ebit_trading_usd'] = df_tec['ebitda_trading_usd'] - df_tec['depreciacion_trading_usd']
                df_tec['impuestos_trading_usd'] = df_tec['ebit_trading_usd'] * float(risk['tasa_impuestos'].iloc[3])
                df_tec['utilidad_neta_trading_usd'] = df_tec['ebitda_trading_usd'] - df_tec['impuestos_trading_usd']
                
                df_tec['flujo_caja_libre_trading_usd'] = df_tec['utilidad_neta_trading_usd'] - df_tec['capex_sistema_productivo_usd'] - df_tec['capex_conservacion_snc_usd'] - df_tec['capex_estudios_snc_usd']
                
                df_tec['impuestos_comunidad_usd'] = df_tec['ingresos_sp_usd'] * float(risk['tasa_impuestos'].iloc[3])
                df_tec['utilidad_neta_comunidad_usd'] = df_tec['ingresos_sp_usd'] - df_tec['impuestos_comunidad_usd']
                
                flujos_trading = df_tec['flujo_caja_libre_trading_usd'].values
                flujos_comunidad = df_tec['impuestos_comunidad_usd'].values
                
                vpn_precio_usd = sum([cf / (1 + tasa_descuento)**(i + 1) for i, cf in enumerate(flujos_trading)])
                vpn_comunidad_usd = sum([cf / (1 + tasa_descuento)**(i + 1) for i, cf in enumerate(flujos_comunidad[1:])])
                vpn_total = vpn_precio_usd + vpn_comunidad_usd
                
                try:
                    tir_trading = npf.irr(flujos_trading[:-1]) if len(flujos_trading) > 1 else np.nan
                    if np.isnan(tir_trading): tir_trading = 0.0
                except:
                    tir_trading = 0.0
                
                carbono_total = df_tec['carbono_acreditable_tco2e'].sum()
                mac_usd = -(vpn_total / carbono_total) if carbono_total > 0 else np.nan
                
                st.session_state.last_mac = mac_usd
                st.session_state.last_vol = carbono_total
                st.session_state.last_computed = True
                
                st.success("Cálculo completado exitosamente.")
                col_k1, col_k2, col_k3, col_k4 = st.columns(4)
                col_k1.metric("VPN (USD)", f"${vpn_total:,.0f}")
                col_k2.metric("TIR Trading", f"{tir_trading*100:.2f}%")
                col_k3.metric("Carbono Acreditable", f"{carbono_total:,.0f} tCO2e")
                col_k4.metric("Costo Marginal (MAC)", f"${mac_usd:,.2f} USD/tCO2e")
                
                fig_fcl = px.bar(df_tec, x='Proyecciones', y='flujo_caja_libre_trading_usd', 
                                 title="Flujo de Caja Libre (Trading) por Año",
                                 labels={'flujo_caja_libre_trading_usd': 'Flujo (USD)'})
                fig_fcl.update_traces(marker_color=np.where(df_tec["flujo_caja_libre_trading_usd"]<0, 'red', 'green'))
                st.plotly_chart(fig_fcl, use_container_width=True)
                
                with st.expander("Ver Tabla Detallada (Flujo de Caja)"):
                    st.dataframe(df_tec.style.format(precision=2), use_container_width=True)
                    
                buf_flujo = io.BytesIO()
                df_tec.to_excel(buf_flujo, index=False)
                st.download_button("📥 Descargar Análisis Técnico (.xlsx)", buf_flujo.getvalue(), "Analisis_Tecnico.xlsx")

        # LÓGICA DE GUARDADO AL PORTAFOLIO MACC
        if st.session_state.last_computed:
            st.markdown("---")
            st.subheader("💾 Guardar este Escenario para la Curva MACC")
            c_name, c_btn = st.columns([3, 1])
            escenario_name = c_name.text_input("Nombre del Proyecto / Escenario:", value=f"Proyecto {len(st.session_state.macc_data)+1}")
            
            if c_btn.button("➕ Añadir a Curva MACC", type="secondary"):
                st.session_state.macc_data.append({
                    "Proyecto": escenario_name,
                    "MAC (USD/tCO2e)": st.session_state.last_mac,
                    "Volumen (tCO2e)": st.session_state.last_vol
                })
                st.success(f"✅ ¡'{escenario_name}' añadido al portafolio! Ve a la Pestaña 5.")

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
        
        vars_excluir = ["ingreso_sp", "crecimiento_sp", "horizonte_tiempo_anios", "tasa_descuento", "precio_carbono_usd_tco2e"]
        vars_simular = [col for col in risk.columns if col not in vars_excluir]

        def calcular_vpn_iter(v):
            area_total = v["area_total_proyecto_ha"]
            p_borde = v["relacion_area_efecto_borde"] 
            area_borde = area_total * p_borde
            area_nucleo = area_total * (1 - p_borde)
            area_sp = area_total * v["relacion_area_sp_area_snc"]
            tasa_captura_ha = (p_borde * tasa_captura_borde) + ((1 - p_borde) * tasa_captura_nucleo)
            
            fac_aisla = 1.0 if v.get("relacion_area_aislamiento_area_snc", 1.0) == 0 else v.get("relacion_area_aislamiento_area_snc", 1.0)
            siembra = v.get("siembra_arboles", 0.0)
            
            capex_snc = v["capex_estudios_habilitantes_snc_usd"] + (v["capex_snc_usd_ha"] * area_borde * fac_aisla) + siembra
            capex_sp_total = (v["capex_sp_usd_ha"] * area_sp) * v["variabilidad_sistema_productivo"]
            capex_real = capex_snc + capex_sp_total + (v["factor_imprevistos_snc_usd_ha"] * area_total)
            
            opex_snc = (capex_snc * v["operación_relacion_capex_snc"]) + ((v["monitoreo_snc_usd_ha_anio"] + v["factor_salvaguarda_snc_usd_ha_anio"]) * area_total)
            opex_sp = capex_sp_total * v["opex_sp"]
            
            vector_opex = np.zeros(anios + 1)
            vector_opex[1:11] = opex_snc + opex_sp
            vector_opex[11:] = opex_snc
            
            descuento = v["descuento_salvaguarda_tecnica"] + v["descuento_cambio_regulacion"] + v["descuento_variabilidad_climatica"]
            vol_creditos = area_total * tasa_captura_ha * v["eficiencia_snc"] * (1 - descuento)
            
            precios = precio_carbono_input * (1 + v["incremento_precio_carbono"])**np.arange(1, anios + 1)
            ingresos = np.zeros(anios + 1)
            ingresos[1:] = vol_creditos * precios
            
            flujos = ingresos - vector_opex
            flujos = np.where(flujos > 0, flujos * (1 - v["tasa_impuestos"]), flujos)
            flujos[0] = -capex_real
            
            return calcular_npv(tasa_descuento, flujos)

        if st.button("🚀 Ejecutar Simulación Integral de Riesgo", type="primary"):
            with st.spinner('Procesando Simulación Monte Carlo y Escalabilidad...'):
                
                simulaciones = {}
                for var in vars_simular:
                    try:
                        v_min = float(risk[var].iloc[0])
                        v_mode = float(risk[var].iloc[1])
                        v_max = float(risk[var].iloc[2])
                        
                        safe_min = min(v_min, v_max)
                        safe_max = max(v_min, v_max)
                        safe_mode = max(safe_min, min(v_mode, safe_max))
                        
                        if safe_min == safe_max:
                            simulaciones[var] = np.full(10000, safe_min)
                        else:
                            simulaciones[var] = np.random.triangular(safe_min, safe_mode, safe_max, 10000)
                    except Exception as e:
                        st.error(f"Error procesando variable '{var}': {e}")
                        st.stop()
                        
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

    # --------------------------------------------------------------------------
    # TAB 5: CURVAS MACC
    # --------------------------------------------------------------------------
    with tab5:
        st.subheader("📉 Curva de Costos Marginales de Abatimiento (MACC)")
        st.markdown("Genera flujos en la **Pestaña 3** modificando las variables en la **Pestaña 2**, y añádelos aquí para comparar escenarios.")
        
        if not st.session_state.macc_data:
            st.info("💡 Tu portafolio está vacío. Ve a la Pestaña 3 y guarda un escenario.")
        else:
            df_macc = pd.DataFrame(st.session_state.macc_data)
            df_macc = df_macc.sort_values(by="MAC (USD/tCO2e)").reset_index(drop=True)

            df_macc['Volumen Acumulado'] = df_macc['Volumen (tCO2e)'].cumsum()
            df_macc['x_pos'] = df_macc['Volumen Acumulado'] - (df_macc['Volumen (tCO2e)'] / 2)

            colores = np.where(df_macc['MAC (USD/tCO2e)'] < 0, '#2ecc71', 
                               np.where(df_macc['MAC (USD/tCO2e)'] <= 20, '#f39c12', '#e74c3c'))

            fig_macc = go.Figure()
            fig_macc.add_trace(go.Bar(
                x=df_macc['x_pos'],
                y=df_macc['MAC (USD/tCO2e)'],
                width=df_macc['Volumen (tCO2e)'],
                text=df_macc['Proyecto'],
                marker_color=colores,
                hovertemplate="<b>%{text}</b><br>Costo Marginal: $%{y:.2f} / tCO2e<br>Volumen Acreditable: %{width:,.0f} tCO2e<extra></extra>"
            ))

            fig_macc.update_layout(
                title="Curva MACC del Portafolio Climático",
                xaxis_title="Abatimiento Acumulado (tCO2e)",
                yaxis_title="Costo Marginal (USD / tCO2e)",
                bargap=0,
                height=600
            )
            st.plotly_chart(fig_macc, use_container_width=True)

            st.subheader("📋 Resumen del Portafolio")
            st.dataframe(df_macc[['Proyecto', 'MAC (USD/tCO2e)', 'Volumen (tCO2e)']].style.format({
                "MAC (USD/tCO2e)": "${:.2f}",
                "Volumen (tCO2e)": "{:,.0f}"
            }), use_container_width=True)

            if st.button("🗑️ Vaciar Portafolio", type="secondary"):
                st.session_state.macc_data = []
                st.rerun()

else:
    st.info("Cargando sistema de base de datos GDB...")



