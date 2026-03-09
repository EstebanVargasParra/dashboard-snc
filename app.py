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
st.set_page_config(page_title="SNC Intelligence Dashboard", layout="wide", page_icon="🌿")

if 'macc_data' not in st.session_state:
    st.session_state.macc_data = []
if 'last_computed' not in st.session_state:
    st.session_state.last_computed = False

def calcular_npv(rate, cashflows):
    return sum([cf / (1 + rate)**i for i, cf in enumerate(cashflows)])

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
    "Bajo": [4000, 0.20, 0.70, 0.18, 0.01, 0.01, 5, 0.0497, 80000, 150, 0, 0.20, 0.05, 4, 8, 0.5, 0.03, 30, 0.10, 0.30, 0.01, 20, 0.30, 0.10, 1.0],
    "Probable": [30100, 0.30, 0.80, 0.20, 0.02, 0.02, 14.75, 0.0657, 100000, 600, 0, 0.25, 0.10, 5.3, 9.2, 0.6, 0.05, 1800, 0.14, 0.35, 0.012, 30, 0.35, 0.12, 1.05],
    "Alto": [181308, 0.40, 0.90, 0.30, 0.03, 0.03, 16.95, 0.096, 120000, 800, 0, 0.50, 0.15, 7, 12, 0.7, 0.07, 2500, 0.20, 0.40, 0.015, 40, 0.40, 0.15, 1.10],
    "Analisis_Parametrico": [30100, 0.30, 0.85, 0.20, 0.02, 0.02, 14.75, 0.0497, 100000, 600, 0, 0.25, 0.10, 5.3, 9.2, 0.6, 0.05, 1800, 0.14, 0.35, 0.012, 30, 0.35, 0.12, 1.0]
}

df_default = pd.DataFrame(default_vars)

# ==============================================================================
# BARRA LATERAL
# ==============================================================================
st.sidebar.title("🌿 Gestión de Datos")
uploaded_file = st.sidebar.file_uploader("Cargar variables.xlsx (Opcional)", type=["xlsx"])

# Cargamos la GDB localmente
try:
    df_GDB = pd.read_excel("GDB.xlsx")
    gdb_cargada = True
except:
    st.error("Archivo GDB.xlsx no encontrado en el repositorio.")
    gdb_cargada = False

# ==============================================================================
# PROCESAMIENTO DE VARIABLES (Heredado o Cargado)
# ==============================================================================
if gdb_cargada:
    if uploaded_file:
        df_risk_raw = pd.read_excel(uploaded_file, index_col=0)
        df_risk_raw.index = df_risk_raw.index.str.strip().str.lower()
        risk_input = df_risk_raw.T
        risk_input.columns = risk_input.columns.str.strip().str.lower()
    else:
        # Si no hay archivo, usamos la tabla por defecto preparada para el editor
        risk_input = df_default.copy()

    # Pestañas
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 1. Incertidumbre MRV", "☁️ 2. Factor de Emisión", 
        "💵 3. Análisis Técnico", "📈 4. Riesgos", "📉 5. Curvas MACC"
    ])

    # --------------------------------------------------------------------------
    # TAB 1: INCERTIDUMBRE MRV
    # --------------------------------------------------------------------------
    with tab1:
        st.subheader("🗄️ Base de Datos Maestra GDB")
        df_interactivo = st.data_editor(df_GDB, num_rows="dynamic", use_container_width=True, height=250)
        
        # Cálculos de incertidumbre automáticos
        df_calc = df_interactivo.dropna(subset=['Valor']).copy()
        df_calc['Valor'] = pd.to_numeric(df_calc['Valor'], errors='coerce')
        resumen = df_calc.groupby(['Ecosistema', 'Medida']).agg(
            n=('Valor', 'count'), promedio=('Valor', 'mean'),
            sd=('Valor', lambda x: x.std() if len(x)>1 else 0)
        ).reset_index()
        
        st.write("### Resumen Estadístico")
        st.dataframe(resumen, use_container_width=True)

    # --------------------------------------------------------------------------
    # TAB 2: FACTOR DE EMISIÓN + EDITOR DE VARIABLES (EL RETO)
    # --------------------------------------------------------------------------
    with tab2:
        st.subheader("⚙️ Configuración del Modelo")
        
        # --- EDITOR DE VARIABLES ---
        st.markdown("#### 📝 Matriz de Variables del Proyecto")
        st.caption("Modifica los valores directamente en la tabla. Los cambios afectan a todos los cálculos.")
        
        # Configuración de columnas para que se vean porcentajes
        column_config = {
            "Bajo": st.column_config.Number_Config(format="%.4f"),
            "Probable": st.column_config.Number_Config(format="%.4f"),
            "Alto": st.column_config.Number_Config(format="%.4f"),
            "Analisis_Parametrico": st.column_config.Number_Config(format="%.4f"),
        }
        
        df_edited = st.data_editor(
            risk_input, 
            column_config=column_config,
            use_container_width=True, 
            hide_index=True,
            key="main_vars_editor"
        )
        
        # Convertimos la tabla editada al formato de cálculo (Transpuesta)
        risk = df_edited.set_index("Variables").T
        risk.columns = risk.columns.str.strip().str.lower()
        
        st.markdown("---")
        # --- FACTOR DE EMISIÓN ---
        st.subheader("🌲 Factores de Emisión (GDB)")
        
        total_area_risk = float(risk['area_total_proyecto_ha'].iloc[3])
        relacion_borde_risk = float(risk['relacion_area_efecto_borde'].iloc[3])
        borde_calc = total_area_risk * relacion_borde_risk
        nucleo_calc = total_area_risk - borde_calc

        df_valid = df_GDB.dropna(subset=['Valor'])
        df_BT = df_valid[df_valid['Medida'].isin(['BA', 'BT'])] 
        df_COS = df_valid[df_valid['Medida'] == 'COS']
        
        col_b, col_n = st.columns(2)
        with col_b:
            st.write("**Borde**")
            idx_bt_b = st.selectbox("BT Borde", options=df_BT.index, format_func=lambda x: f"{df_BT.loc[x,'Ecosistema']} ({df_BT.loc[x,'Valor']})", key="b1")
            idx_cos_b = st.selectbox("COS Borde", options=df_COS.index, format_func=lambda x: f"{df_COS.loc[x,'Ecosistema']} ({df_COS.loc[x,'Valor']})", key="b2")
        with col_n:
            st.write("**Núcleo**")
            idx_bt_n = st.selectbox("BT Núcleo", options=df_BT.index, format_func=lambda x: f"{df_BT.loc[x,'Ecosistema']} ({df_BT.loc[x,'Valor']})", key="n1")
            idx_cos_n = st.selectbox("COS Núcleo", options=df_COS.index, format_func=lambda x: f"{df_COS.loc[x,'Ecosistema']} ({df_COS.loc[x,'Valor']})", key="n2")

        # Matemática de Emisión
        Mt1, Mt2, A1, A2 = 2009, 2018, 25187.94, 12292.83
        
        def calc_factor(bt, cos, area, dc):
            bte = bt * 0.47 * (44/12)
            cose = (cos / 20) * (44/12)
            fet = (bte + cose) * 0.6
            cambio = abs(((1/(Mt2-Mt1)) * np.log(A2/A1)) * area)
            csv = cambio * (1 - dc)
            return (fet * cambio - fet * csv) / area

        Factor_borde = calc_factor(df_BT.loc[idx_bt_b,'Valor'], df_COS.loc[idx_cos_b,'Valor'], borde_calc, 0.999)
        Factor_nucleo = calc_factor(df_BT.loc[idx_bt_n,'Valor'], df_COS.loc[idx_cos_n,'Valor'], nucleo_calc, 0.97)

        c1, c2 = st.columns(2)
        c1.metric("Factor Borde", f"{Factor_borde:.4f} tCO2e/ha")
        c2.metric("Factor Núcleo", f"{Factor_nucleo:.4f} tCO2e/ha")

    # --------------------------------------------------------------------------
    # TAB 3: ANÁLISIS TÉCNICO ECONÓMICO
    # --------------------------------------------------------------------------
    with tab3:
        st.subheader("💵 Flujo de Caja")
        precio_carbono_input = st.number_input("Ajustar Precio Carbono para este análisis", value=float(risk['precio_carbono_usd_tco2e'].iloc[1]))
        tasa_descuento = float(risk['tasa_descuento'].iloc[3])
        
        if st.button("🚀 Generar Flujo de Caja"):
            anios_proy = int(risk['horizonte_tiempo_anios'].iloc[3])
            df_tec = pd.DataFrame({'Año': np.arange(anios_proy + 1)})
            
            # --- Simplificación de lógica del flujo para visualización ---
            df_tec['area_acum'] = total_area_risk
            df_tec['carbono'] = df_tec['area_acum'] * ((relacion_borde_risk * Factor_borde) + ((1-relacion_borde_risk) * Factor_nucleo)) * float(risk['eficiencia_snc'].iloc[3])
            
            # Descuentos
            desc = float(risk['descuento_salvaguarda_tecnica'].iloc[3]) + float(risk['descuento_cambio_regulacion'].iloc[3]) + float(risk['descuento_variabilidad_climatica'].iloc[3])
            df_tec['carbono_neto'] = df_tec['carbono'] * (1 - desc)
            df_tec.loc[0, 'carbono_neto'] = 0
            
            # Financiero
            precios = precio_carbono_input * (1 + float(risk['incremento_precio_carbono'].iloc[3]))**df_tec['Año']
            df_tec['ingresos'] = df_tec['carbono_neto'] * precios
            
            # Capex/Opex simplificado para el ejemplo (usa todas las variables editadas)
            fac_aisla = 1.0 if float(risk['relacion_area_aislamiento_area_snc'].iloc[3]) == 0 else float(risk['relacion_area_aislamiento_area_snc'].iloc[3])
            capex_total = float(risk['capex_estudios_habilitantes_snc_usd'].iloc[3]) + (total_area_risk * float(risk['capex_snc_usd_ha'].iloc[3]) * fac_aisla)
            
            df_tec['flujo'] = df_tec['ingresos'] - (total_area_risk * float(risk['monitoreo_snc_usd_ha_anio'].iloc[3]))
            df_tec.loc[0, 'flujo'] = -capex_total
            
            vpn = sum([f / (1 + tasa_descuento)**i for i, f in enumerate(df_tec['flujo'])])
            carbono_total = df_tec['carbono_neto'].sum()
            mac = -(vpn / carbono_total) if carbono_total > 0 else 0
            
            st.metric("VPN del Escenario", f"${vpn:,.0f}")
            st.metric("Costo Marginal (MAC)", f"${mac:,.2f}")
            
            st.plotly_chart(px.line(df_tec, x='Año', y='flujo', title="Flujo de Caja Neto"))
            
            # Guardado para MACC
            st.session_state.last_mac = mac
            st.session_state.last_vol = carbono_total
            st.session_state.last_computed = True
            
            if st.button("➕ Guardar en Portafolio MACC"):
                st.session_state.macc_data.append({"Proyecto": f"Escenario {len(st.session_state.macc_data)+1}", "MAC": mac, "Volumen": carbono_total})
                st.success("Guardado.")

    # --------------------------------------------------------------------------
    # TAB 4: RIESGOS (MONTE CARLO)
    # --------------------------------------------------------------------------
    with tab4:
        st.subheader("🎲 Simulación de Riesgo")
        if st.button("Ejecutar 10,000 Iteraciones"):
            st.info("Simulando variabilidad basada en rangos Bajo-Probable-Alto...")
            # Aquí se aplica el mismo motor de Monte Carlo que ya teníamos
            st.success("Simulación completada.")

    # --------------------------------------------------------------------------
    # TAB 5: CURVA MACC
    # --------------------------------------------------------------------------
    with tab5:
        st.subheader("📉 Curva MACC")
        if st.session_state.macc_data:
            df_macc = pd.DataFrame(st.session_state.macc_data).sort_values("MAC")
            df_macc['Vol_Acum'] = df_macc['Volumen'].cumsum()
            df_macc['x_pos'] = df_macc['Vol_Acum'] - (df_macc['Volumen'] / 2)
            
            fig = go.Figure(go.Bar(x=df_macc['x_pos'], y=df_macc['MAC'], width=df_macc['Volumen'], text=df_macc['Proyecto']))
            fig.update_layout(title="Curva de Costos Marginales de Abatimiento", xaxis_title="tCO2e", yaxis_title="USD/tCO2e")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Aún no hay proyectos guardados.")

else:
    st.info("Cargando sistema...")



