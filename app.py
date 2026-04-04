# app.py
# SCHELETRO Manager (V2.1.3)
# - Carrito (múltiples líneas)
# - Bodega ÚNICA por venta
# - Ventas_Cabecera + Ventas_Detalle
# - Config (comisiones + TZ) robusto (% o decimal)
# - Activo robusto (columnas con espacios invisibles / variaciones)
# - Transferir stock Casa <-> Bodega (funcional, no registra venta)
# - FIX: evitar quota 429 (cache ttl + limpiar cache al escribir)
# - FIX: reset sin StreamlitAPIException (flag _reset_sale_pending)
# - FIX: quitar warning amarillo (no mezclar value= con key=)
# - NEW: nombres de bodegas por Config (BODEGA_1_NOMBRE / BODEGA_2_NOMBRE)
# - FIX: scroll estable y layout unificado (barra inferior al final, CSS mejorado)

from __future__ import annotations

from zoneinfo import ZoneInfo

import streamlit as st

from modules.auth.password import require_password
from modules.core.state import init_state, reset_sale_form
from modules.data.helpers import get_conn, load_config, load_inventario
from modules.ui.finanzas_page import render_finanzas_page
from modules.ui.inventario_page import render_inventario_page
from modules.ui.navigation import _scheletro_set_page, init_navigation_state, render_bottom_nav
from modules.ui.styles import inject_css, money
from modules.ui.ventas_page import render_ventas_page
from modules.ui.dashboard_page import render_dashboard_page


# -----------------------------
# App
# -----------------------------
st.set_page_config(page_title="SCHELETRO Manager", page_icon="🦴", layout="centered", initial_sidebar_state="collapsed")

# 🔒 Bloqueo antes de cargar datos
require_password()


inject_css()
init_state()

# ✅ FIX: reset seguro (ANTES de widgets)
if st.session_state.get("_reset_sale_pending", False):
    st.session_state["_reset_sale_pending"] = False
    reset_sale_form()


# Conexión
try:
    conn = get_conn()
except Exception as e:
    st.error("No pude crear la conexión a Google Sheets.")
    st.caption("Revisa `.streamlit/secrets.toml` y que el nombre sea `[connections.gsheets]`.")
    st.exception(e)
    st.stop()

# Config (cache más largo)
try:
    cfg = load_config(conn, ttl_s=180)
except Exception:
    cfg = {}

tz_name = str(cfg.get("TZ", "America/El_Salvador")).strip() or "America/El_Salvador"
APP_TZ = ZoneInfo(tz_name)

# Nombres visibles de bodegas (SIN cambiar columnas Stock_Casa/Stock_Bodega)
BODEGA_NAME = {
    "Casa": (str(cfg.get("BODEGA_1_NOMBRE", "Casa Chiky")).strip() or "Casa Chiky"),
    "Bodega": (str(cfg.get("BODEGA_2_NOMBRE", "Gamaliel")).strip() or "Gamaliel"),
}

# Alias (para usar nombres directos en UI si hace falta)
bodega1_nombre = BODEGA_NAME["Casa"]
bodega2_nombre = BODEGA_NAME["Bodega"]

def fmt_bodega(x: str) -> str:
    return BODEGA_NAME.get(x, x)

# Inventario (cache medio)
inv_df_full = load_inventario(conn, ttl_s=45)

# Navegación (menú inferior)
# NOTA: Solo UI. No altera la lógica interna de Ventas/Inventario/Finanzas ni la conexión a Sheets.
# Motivo del “password se vuelve a pedir”: los <a href> o cambios de URL recargan la app y crean una NUEVA sesión de Streamlit.
# Solución (Opción A): navegación 100% dentro de la MISMA sesión usando st.session_state + st.rerun (sin recargar, sin pestaña nueva).

# --- Estado de navegación en la misma sesión ---
init_navigation_state()
page = st.session_state.scheletro_page


# -----------------------------
# PÁGINA: Dashboard (Coming soon)
# -----------------------------
if page == "Dashboard":
    render_dashboard_page()

# -----------------------------
# TAB: Inventario (vista + transfer stock)
# -----------------------------
elif page == "Inventario":
    render_inventario_page(conn, inv_df_full, fmt_bodega, bodega1_nombre, bodega2_nombre)

# -----------------------------
# TAB: Finanzas (Nivel 1 · 2 · 3)
# -----------------------------
elif page == "Finanzas":
    render_finanzas_page(conn, inv_df_full, APP_TZ, money)

# -----------------------------
# TAB: Ventas (Carrito)
# -----------------------------
elif page == "Ventas":
    render_ventas_page(conn, inv_df_full, cfg, APP_TZ, BODEGA_NAME, fmt_bodega, money)

# -------- BARRA INFERIOR (AHORA AL FINAL, PARA ESTABILIDAD DE SCROLL) ----------
render_bottom_nav(page)
