# app.py
# SCHELETRO Manager (V2.1.3)
# - Carrito (múltiples líneas)
# - Bodega ÚNICA por venta (interno: Casa/Bodega; UI: nombres desde Config)
# - Ventas_Cabecera + Ventas_Detalle
# - Config (comisiones + TZ) robusto (% o decimal)
# - Activo robusto (columnas con espacios invisibles / variaciones)
# - Transferir stock (funcional, no registra venta)
# - FIX Streamlit reset: evita "st.session_state.cliente cannot be modified..."

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Iterable, cast
import re

import pandas as pd
import streamlit as st
from streamlit_gsheets import GSheetsConnection


# -----------------------------
# Sheets / Tabs (DEBEN coincidir con tus pestañas)
# -----------------------------
SHEET_INVENTARIO = "Inventario"
SHEET_VENTAS_CAB = "Ventas_Cabecera"
SHEET_VENTAS_DET = "Ventas_Detalle"
SHEET_CONFIG = "Config"


# -----------------------------
# Columnas esperadas (sin destruir columnas extra)
# - Cabecera: layout de tu Excel (3).xlsx
# -----------------------------
INV_REQUIRED = [
    "SKU",
    "Drop",
    "Producto",
    "Color",
    "Talla",
    "Stock_Casa",
    "Stock_Bodega",
    "Costo_Unitario",
    "Precio_Lista",
    "Activo",
]

CAB_REQUIRED = [
    "Venta_ID",
    "Fecha",
    "Hora",
    "Cliente",
    "Metodo_Pago",
    "Envio_Cobrado_Total",
    "Costo_Logistica_Total",
    "Comision_Porc",
    "Total_Lineas",
    "Total_Cobrado",
    "Comision_Monto",
    "Monto_A_Recibir",
    "Notas",
    "Estado",
]

DET_REQUIRED = [
    "Venta_ID",
    "Linea",
    "SKU",
    "Producto",
    "Drop",
    "Color",
    "Talla",
    "Bodega_Salida",
    "Cantidad",
    "Precio_Unitario",
    "Descuento_Unitario",
    "Subtotal_Linea",
]


# -----------------------------
# UI helpers (tu estilo card)
# -----------------------------
def money(x: float) -> str:
    try:
        return f"${float(x):,.2f}"
    except Exception:
        return "$0.00"


def normalize_html(html: str) -> str:
    return "\n".join(line.lstrip() for line in html.splitlines()).strip()


@contextmanager
def card():
    with st.container():
        st.markdown('<div class="card-marker"></div>', unsafe_allow_html=True)
        yield


def inject_css() -> None:
    st.markdown(
        """
        <style>
          .block-container { max-width: 560px; padding-top: 1.0rem; padding-bottom: 2.0rem; }
          #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
          .stVerticalBlock { gap: 0.75rem; }

          .card-marker { display:none; }
          div[data-testid="stVerticalBlock"]:has(.card-marker) {
            border: 1px solid rgba(255,255,255,0.08);
            background: rgba(255,255,255,0.03);
            border-radius: 16px;
            padding: 14px 14px;
          }
          div[data-testid="stVerticalBlock"]:has(.card-marker) > div:first-child { margin-top: 0 !important; }

          .card-html {
            border: 1px solid rgba(255,255,255,0.08);
            background: rgba(255,255,255,0.03);
            border-radius: 16px;
            padding: 14px 14px;
          }
          .header-title { font-weight: 800; letter-spacing: 0.6px; font-size: 1.05rem; margin: 0 0 2px 0; }
          .header-sub { opacity: 0.7; font-size: 0.85rem; margin: 0; }

          .muted { opacity: 0.75; font-size: 0.9rem; }

          .summary-grid { display: grid; grid-template-columns: 1fr; gap: 10px; }
          .summary-row { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; }
          .summary-label { opacity: 0.75; }
          .summary-value { font-weight: 800; }

          .gain-ok { color: #38d46a; font-weight: 900; }
          .gain-low { color: #ff4d4d; font-weight: 900; }

          input, textarea { font-size: 16px !important; }
          .small-note { opacity:0.70; font-size: 0.85rem; }
          .pill { display:inline-block; padding:4px 10px; border-radius:999px; border:1px solid rgba(255,255,255,0.10); background:rgba(255,255,255,0.03); }
        </style>
        """,
        unsafe_allow_html=True,
    )


# -----------------------------
# Data helpers (robustos)
# -----------------------------
def get_conn() -> GSheetsConnection:
    return st.connection("gsheets", type=GSheetsConnection)


def _norm_key(s: str) -> str:
    s = str(s or "").strip().lower()
    s = s.replace("\u00A0", " ")  # nbsp
    return re.sub(r"[^a-z0-9]", "", s)


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).replace("\u00A0", " ").strip() for c in df.columns]
    return df


def _align_required_columns(df: pd.DataFrame, required: list[str]) -> pd.DataFrame:
    df = _normalize_columns(df)

    existing = df.columns.tolist()
    existing_map = {_norm_key(c): c for c in existing}

    rename_map: dict[str, str] = {}
    for req in required:
        k = _norm_key(req)
        if k in existing_map:
            rename_map[existing_map[k]] = req

    df = df.rename(columns=rename_map)

    for req in required:
        if req not in df.columns:
            df[req] = ""

    return df


def _clean_number(x: Any) -> float:
    if x is None:
        return 0.0
    if isinstance(x, float) and pd.isna(x):
        return 0.0
    if isinstance(x, (int, float)):
        return float(x)

    s = str(x).strip()
    if not s:
        return 0.0

    s = s.replace("$", "").replace(",", "").strip()

    if s.endswith("%"):
        try:
            return float(s[:-1].strip()) / 100.0
        except Exception:
            return 0.0

    try:
        return float(s)
    except Exception:
        return 0.0


def _to_numeric(df: pd.DataFrame, cols: Iterable[str]) -> pd.DataFrame:
    df = df.copy()
    for c in cols:
        if c in df.columns:
            df[c] = df[c].apply(_clean_number)
    return df


def _to_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)) and not pd.isna(v):
        return float(v) != 0.0
    s = str(v).strip().lower()
    return s in ["true", "t", "1", "yes", "y", "si", "sí", "verdadero", "activo"]


def load_raw_sheet(conn: GSheetsConnection, worksheet: str) -> pd.DataFrame:
    df = conn.read(worksheet=worksheet, ttl=0)
    if df is None or len(df) == 0:
        return pd.DataFrame()
    return _normalize_columns(df)


def save_sheet(conn: GSheetsConnection, worksheet: str, df: pd.DataFrame) -> None:
    conn.update(worksheet=worksheet, data=df)


def load_config(conn: GSheetsConnection) -> dict[str, Any]:
    df = load_raw_sheet(conn, SHEET_CONFIG)
    if df.empty:
        return {}
    df = _align_required_columns(df, ["Parametro", "Valor", "Notas"])

    out: dict[str, Any] = {}
    for _, row in df.iterrows():
        k = str(row.get("Parametro", "")).strip()
        if not k:
            continue
        out[k] = row.get("Valor", "")
    return out


def load_inventario(conn: GSheetsConnection) -> pd.DataFrame:
    df = load_raw_sheet(conn, SHEET_INVENTARIO)
    if df.empty:
        return _align_required_columns(pd.DataFrame(), INV_REQUIRED)

    df = _align_required_columns(df, INV_REQUIRED)
    df = _to_numeric(df, ["Stock_Casa", "Stock_Bodega", "Costo_Unitario", "Precio_Lista"])

    for c in ["SKU", "Drop", "Producto", "Color", "Talla"]:
        df[c] = df[c].astype(str).fillna("").str.strip()

    df["Activo"] = df["Activo"].apply(_to_bool)
    return df


def load_cabecera(conn: GSheetsConnection) -> pd.DataFrame:
    df = load_raw_sheet(conn, SHEET_VENTAS_CAB)
    if df.empty:
        return _align_required_columns(pd.DataFrame(), CAB_REQUIRED)

    df = _align_required_columns(df, CAB_REQUIRED)
    df = _to_numeric(
        df,
        [
            "Envio_Cobrado_Total",
            "Costo_Logistica_Total",
            "Comision_Porc",
            "Total_Lineas",
            "Total_Cobrado",
            "Comision_Monto",
            "Monto_A_Recibir",
        ],
    )
    for c in ["Venta_ID", "Fecha", "Hora", "Cliente", "Metodo_Pago", "Notas", "Estado"]:
        df[c] = df[c].astype(str).fillna("").str.strip()
    return df


def load_detalle(conn: GSheetsConnection) -> pd.DataFrame:
    df = load_raw_sheet(conn, SHEET_VENTAS_DET)
    if df.empty:
        return _align_required_columns(pd.DataFrame(), DET_REQUIRED)

    df = _align_required_columns(df, DET_REQUIRED)
    df = _to_numeric(df, ["Linea", "Cantidad", "Precio_Unitario", "Descuento_Unitario", "Subtotal_Linea"])
    for c in ["Venta_ID", "SKU", "Producto", "Drop", "Color", "Talla", "Bodega_Salida"]:
        df[c] = df[c].astype(str).fillna("").str.strip()
    return df


# -----------------------------
# Venta_ID secuencial (V-YYYY-0001)
# -----------------------------
def next_venta_id(cab_df: pd.DataFrame, year: int) -> str:
    pat = re.compile(r"^V-(\d{4})-(\d{4})$")
    max_n = 0
    if "Venta_ID" not in cab_df.columns:
        return f"V-{year}-0001"

    for vid in cab_df["Venta_ID"].astype(str).tolist():
        m = pat.match(vid.strip())
        if not m:
            continue
        y = int(m.group(1))
        n = int(m.group(2))
        if y == year and n > max_n:
            max_n = n
    return f"V-{year}-{max_n + 1:04d}"


# -----------------------------
# Comisiones
# -----------------------------
def comision_porcentaje(metodo_pago: str, cfg: dict[str, Any], override_pce: float | None) -> float:
    m = (metodo_pago or "").strip().lower()
    tarjeta = _clean_number(cfg.get("COMISION_TARJETA_PORC", 0.023))
    pce = _clean_number(cfg.get("COMISION_PCE_PORC", 0.0299))

    if m == "tarjeta":
        return float(tarjeta)
    if m == "contra entrega":
        return float(override_pce) if override_pce is not None else float(pce)
    return 0.0


# -----------------------------
# Session defaults
# -----------------------------
def init_state() -> None:
    st.session_state.setdefault("cart", [])  # list[dict]

    st.session_state.setdefault("cliente", "")
    st.session_state.setdefault("notas", "")
    st.session_state.setdefault("metodo_pago", "Transferencia")

    # Interno: siempre "Casa"/"Bodega"
    st.session_state.setdefault("bodega_venta_code", "Casa")

    # UI: se ajusta después de leer Config (por eso aquí ponemos placeholder)
    st.session_state.setdefault("bodega_venta_ui", "Casa")

    st.session_state.setdefault("envio_cliente", 0.0)
    st.session_state.setdefault("costo_courier", 0.0)

    st.session_state.setdefault("pce_mode", "2.99%")
    st.session_state.setdefault("pce_otro", 2.99)

    # Reset diferido
    st.session_state.setdefault("_reset_sale_pending", False)
    st.session_state.setdefault("_last_sale_id", "")


def reset_sale_form(default_bodega_label: str) -> None:
    # OJO: esto se llama SOLO antes de instanciar widgets (por el reset diferido)
    st.session_state["cart"] = []
    st.session_state["cliente"] = ""
    st.session_state["notas"] = ""
    st.session_state["metodo_pago"] = "Transferencia"

    st.session_state["bodega_venta_code"] = "Casa"
    st.session_state["bodega_venta_ui"] = default_bodega_label

    st.session_state["envio_cliente"] = 0.0
    st.session_state["costo_courier"] = 0.0
    st.session_state["pce_mode"] = "2.99%"
    st.session_state["pce_otro"] = 2.99


# -----------------------------
# App
# -----------------------------
st.set_page_config(page_title="SCHELETRO Manager", page_icon="🦴", layout="centered", initial_sidebar_state="collapsed")
inject_css()
init_state()

st.markdown(
    """
    <div class="card-html">
      <div class="header-title">SCHELETRO Manager</div>
      <div class="header-sub">Ventas (Carrito) · V2.1.3</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Conexión + Config
try:
    conn = get_conn()
except Exception as e:
    st.error("No pude crear la conexión a Google Sheets.")
    st.caption("Revisa `.streamlit/secrets.toml` y que el nombre sea `[connections.gsheets]`.")
    st.exception(e)
    st.stop()

try:
    cfg = load_config(conn)
except Exception:
    cfg = {}

tz_name = str(cfg.get("TZ", "America/El_Salvador")).strip() or "America/El_Salvador"
APP_TZ = ZoneInfo(tz_name)

# -----------------------------
# Nombres de bodegas (UI) desde Config
# Interno: "Casa"/"Bodega" (para Stock_Casa / Stock_Bodega)
# -----------------------------
BODEGA_1_LABEL = str(cfg.get("BODEGA_1_NOMBRE", "Casa")).strip() or "Casa"
BODEGA_2_LABEL = str(cfg.get("BODEGA_2_NOMBRE", "Bodega")).strip() or "Bodega"

LABEL_TO_CODE = {
    BODEGA_1_LABEL: "Casa",
    BODEGA_2_LABEL: "Bodega",
}
CODE_TO_LABEL = {
    "Casa": BODEGA_1_LABEL,
    "Bodega": BODEGA_2_LABEL,
}

# Asegurar que el estado UI tenga un valor válido ANTES de crear widgets
if st.session_state.get("bodega_venta_code") not in ["Casa", "Bodega"]:
    st.session_state["bodega_venta_code"] = "Casa"

desired_label = CODE_TO_LABEL.get(st.session_state["bodega_venta_code"], BODEGA_1_LABEL)
if st.session_state.get("bodega_venta_ui") not in [BODEGA_1_LABEL, BODEGA_2_LABEL]:
    st.session_state["bodega_venta_ui"] = desired_label

# -----------------------------
# FIX reset diferido (antes de instanciar widgets)
# -----------------------------
if st.session_state.get("_reset_sale_pending", False):
    st.session_state["_reset_sale_pending"] = False
    reset_sale_form(default_bodega_label=BODEGA_1_LABEL)

# Tabs
tab_ventas, tab_inventario, tab_finanzas = st.tabs(["🧾 Ventas", "📦 Inventario", "📈 Finanzas"])


# -----------------------------
# TAB: Inventario (vista + transfer stock)
# -----------------------------
with tab_inventario:
    with card():
        c1, c2 = st.columns([3, 2])
        with c1:
            st.markdown("**Inventario**")
            st.caption("Vista rápida del inventario conectado a tu Google Sheet.")
        with c2:
            if st.button("🔄 Refrescar Inventario", use_container_width=True):
                st.rerun()

        try:
            inv_df_full = load_inventario(conn)
            st.dataframe(inv_df_full, use_container_width=True, hide_index=True)
        except Exception as e:
            st.error("No pude cargar Inventario.")
            st.exception(e)
            inv_df_full = pd.DataFrame()

    with card():
        st.markdown(f"**Transferir stock ({BODEGA_1_LABEL} ↔ {BODEGA_2_LABEL})**")
        st.caption("Esto NO registra una venta. Solo mueve unidades entre bodegas.")

        if inv_df_full is None or inv_df_full.empty:
            st.warning("Inventario vacío.")
        else:
            activos = inv_df_full[inv_df_full["Activo"] == True].copy()
            if activos.empty:
                st.warning("No detecté SKUs activos por el campo 'Activo'. Voy a mostrarte TODOS para que no te bloquee.")
                activos = inv_df_full.copy()

            activos["Label"] = (
                activos["SKU"].astype(str).str.strip()
                + " · "
                + activos["Producto"].astype(str).str.strip()
                + " · "
                + activos["Color"].astype(str).str.strip()
                + " · "
                + activos["Talla"].astype(str).str.strip()
            )
            sku_map = dict(zip(activos["Label"], activos["SKU"]))

            label_sel = st.selectbox("SKU a mover", options=list(sku_map.keys()))
            sku_sel = sku_map[label_sel]

            row = activos[activos["SKU"].astype(str).str.strip() == str(sku_sel).strip()].iloc[0]
            stock_casa = int(_clean_number(row.get("Stock_Casa", 0)))
            stock_bodega = int(_clean_number(row.get("Stock_Bodega", 0)))

            st.markdown(
                f"<div class='small-note'>Stock {BODEGA_1_LABEL}: <b>{stock_casa}</b> · Stock {BODEGA_2_LABEL}: <b>{stock_bodega}</b></div>",
                unsafe_allow_html=True,
            )

            direction = st.radio(
                "Dirección",
                [f"{BODEGA_1_LABEL} ➜ {BODEGA_2_LABEL}", f"{BODEGA_2_LABEL} ➜ {BODEGA_1_LABEL}"],
                horizontal=True,
            )

            from_code = "Casa" if direction.startswith(BODEGA_1_LABEL) else "Bodega"
            max_qty = stock_casa if from_code == "Casa" else stock_bodega

            qty = st.number_input("Cantidad a mover", min_value=1, max_value=max(1, int(max_qty)), value=1, step=1)

            can_move = max_qty >= int(qty)
            if not can_move:
                st.error("Stock insuficiente para mover esa cantidad.")

            move_btn = st.button("✅ Transferir", use_container_width=True, disabled=not can_move)
            if move_btn:
                try:
                    inv_latest = load_inventario(conn)

                    mask = inv_latest["SKU"].astype(str).str.strip() == str(sku_sel).strip()
                    if not mask.any():
                        raise ValueError(f"SKU no encontrado: {sku_sel}")

                    ix = inv_latest.index[mask].tolist()[0]
                    q = int(qty)

                    if from_code == "Casa":
                        if int(_clean_number(inv_latest.loc[ix, "Stock_Casa"])) < q:
                            raise ValueError(f"Stock {BODEGA_1_LABEL} insuficiente.")
                        inv_latest.loc[ix, "Stock_Casa"] = int(_clean_number(inv_latest.loc[ix, "Stock_Casa"])) - q
                        inv_latest.loc[ix, "Stock_Bodega"] = int(_clean_number(inv_latest.loc[ix, "Stock_Bodega"])) + q
                    else:
                        if int(_clean_number(inv_latest.loc[ix, "Stock_Bodega"])) < q:
                            raise ValueError(f"Stock {BODEGA_2_LABEL} insuficiente.")
                        inv_latest.loc[ix, "Stock_Bodega"] = int(_clean_number(inv_latest.loc[ix, "Stock_Bodega"])) - q
                        inv_latest.loc[ix, "Stock_Casa"] = int(_clean_number(inv_latest.loc[ix, "Stock_Casa"])) + q

                    save_sheet(conn, SHEET_INVENTARIO, inv_latest)
                    st.success("✅ Transferencia realizada.")
                    st.rerun()

                except Exception as e:
                    st.error("Error al transferir stock.")
                    st.exception(e)


# -----------------------------
# TAB: Finanzas (placeholder)
# -----------------------------
with tab_finanzas:
    with card():
        st.markdown("**Finanzas (próximamente)**")
        st.caption("Aquí haremos: totales por mes, por drop, top productos, etc. Primero dejamos ventas (carrito) perfecto.")


# -----------------------------
# TAB: Ventas (Carrito)
# -----------------------------
with tab_ventas:
    # Mensaje de éxito (después de rerun)
    last_sale = str(st.session_state.get("_last_sale_id", "")).strip()
    if last_sale:
        st.success(f"✅ Venta registrada: {last_sale}")
        st.session_state["_last_sale_id"] = ""

    # Cargar inventario
    try:
        inv_df = load_inventario(conn)
    except Exception as e:
        st.error("No pude cargar el Inventario desde Google Sheets.")
        st.exception(e)
        st.stop()

    if inv_df.empty:
        st.warning("Tu Inventario está vacío.")
        st.stop()

    inv_activo = inv_df[inv_df["Activo"] == True].copy()
    if inv_activo.empty and len(inv_df) > 0:
        with card():
            st.warning("Tu inventario tiene filas, pero el filtro 'Activo' quedó en 0. Voy a permitir ventas usando TODOS los SKUs para no bloquearte.")
            st.caption("Luego revisamos si el header 'Activo' trae espacios invisibles o si Sheets lo está enviando diferente.")
        inv_activo = inv_df.copy()

    if inv_activo.empty:
        st.warning("Tu Inventario está vacío o todo está inactivo.")
        st.stop()

    # -----------------------------
    # Bodega única por venta (UI con nombres desde Config)
    # -----------------------------
    with card():
        st.markdown("**Bodega de salida (toda la venta)**")

        # Radio UI (label)
        selected_label = st.radio(
            "Bodega",
            options=[BODEGA_1_LABEL, BODEGA_2_LABEL],
            horizontal=True,
            key="bodega_venta_ui",
        )

        # Convertir label -> code (interno)
        bodega_venta_code = LABEL_TO_CODE.get(selected_label, "Casa")
        st.session_state["bodega_venta_code"] = bodega_venta_code

        cart_now = cast(list[dict[str, Any]], st.session_state["cart"])
        if cart_now:
            st.caption(f"Carrito actual tiene {len(cart_now)} línea(s). (Bodega actual: {selected_label})")

    # -----------------------------
    # Agregar línea al carrito
    # -----------------------------
    with card():
        st.markdown("**Agregar producto**")

        productos = sorted([p for p in inv_activo["Producto"].dropna().unique().tolist() if str(p).strip()])
        producto_sel = st.selectbox("Producto", productos, index=0)

        df_p = inv_activo[inv_activo["Producto"] == producto_sel].copy()
        colores = sorted([c for c in df_p["Color"].dropna().unique().tolist() if str(c).strip()])
        color_sel = st.selectbox("Color", colores, index=0)

        df_pc = df_p[df_p["Color"] == color_sel].copy()
        tallas = sorted([t for t in df_pc["Talla"].dropna().unique().tolist() if str(t).strip()])
        talla_sel = st.selectbox("Talla", tallas, index=0)

        df_pct = df_pc[df_pc["Talla"] == talla_sel].copy()
        if df_pct.empty:
            st.error("No encontré esa variante en inventario.")
            st.stop()

        row = df_pct.iloc[0]
        sku = str(row["SKU"]).strip()
        drop = str(row["Drop"]).strip()
        precio_unit = float(_clean_number(row["Precio_Lista"]))

        stock_casa = int(_clean_number(row["Stock_Casa"]))
        stock_bodega = int(_clean_number(row["Stock_Bodega"]))

        col_stock = "Stock_Casa" if bodega_venta_code == "Casa" else "Stock_Bodega"
        stock_disp = stock_casa if col_stock == "Stock_Casa" else stock_bodega

        if stock_disp <= 0:
            st.error(f"❌ AGOTADO en {selected_label}.")
        elif stock_disp <= 2:
            st.warning(f"⚠️ Pocas unidades en {selected_label}.")

        cols = st.columns([1, 1])
        with cols[0]:
            qty = st.number_input("Cantidad", min_value=1, max_value=max(1, stock_disp), value=1, step=1)
        with cols[1]:
            desc_u = st.number_input("Descuento unitario ($)", min_value=0.0, value=0.0, step=0.50, format="%.2f")

        if desc_u > precio_unit:
            st.warning("⚠️ El descuento unitario no puede ser mayor al precio unitario. Se ajustará.")
            desc_u = precio_unit

        subtotal_linea = round((precio_unit - desc_u) * int(qty), 2)

        st.markdown(
            f"<div class='small-note'>SKU: <b>{sku}</b> · Precio: <b>{money(precio_unit)}</b> · "
            f"Bodega: <span class='pill'><b>{selected_label}</b></span> · Subtotal: <b>{money(subtotal_linea)}</b></div>",
            unsafe_allow_html=True,
        )

        add_btn = st.button("➕ Añadir al carrito", use_container_width=True, disabled=(stock_disp <= 0))
        if add_btn:
            cart = cast(list[dict[str, Any]], st.session_state["cart"])
            cart.append(
                {
                    "SKU": sku,
                    "Drop": drop,
                    "Producto": producto_sel,
                    "Color": color_sel,
                    "Talla": talla_sel,
                    # Guardamos label en la línea (para que se vea lindo)
                    # La lógica de stock SIEMPRE usa bodega_venta_code
                    "Bodega_Salida": selected_label,
                    "Cantidad": int(qty),
                    "Precio_Unitario": float(precio_unit),
                    "Descuento_Unitario": float(desc_u),
                    "Subtotal_Linea": float(subtotal_linea),
                }
            )
            st.session_state["cart"] = cart
            st.success("Agregado al carrito.")

    # -----------------------------
    # Mostrar carrito + remover
    # -----------------------------
    cart = cast(list[dict[str, Any]], st.session_state["cart"])

    with card():
        st.markdown("**Carrito**")
        if not cart:
            st.caption("Aún no has agregado productos.")
        else:
            for i, item in enumerate(cart, start=1):
                c1, c2 = st.columns([6, 2])
                with c1:
                    st.markdown(
                        f"**{i}. {item['Producto']}** · {item['Color']} · {item['Talla']}  \n"
                        f"SKU: `{item['SKU']}` · Bodega: **{item['Bodega_Salida']}**"
                    )
                    st.caption(
                        f"Qty: {item['Cantidad']} · Precio: {money(item['Precio_Unitario'])} · "
                        f"Desc/U: {money(item['Descuento_Unitario'])} · Subtotal: {money(item['Subtotal_Linea'])}"
                    )
                with c2:
                    if st.button("🗑️ Quitar", key=f"rm_{i}_{item['SKU']}"):
                        cart.pop(i - 1)
                        st.session_state["cart"] = cart
                        st.rerun()

            if st.button("🧹 Vaciar carrito", use_container_width=True):
                st.session_state["cart"] = []
                st.rerun()

    # -----------------------------
    # Datos de venta (cabecera)
    # -----------------------------
    with card():
        st.markdown("**Datos de venta**")
        cliente = st.text_input("Cliente", placeholder="Nombre del cliente", key="cliente")
        notas = st.text_area("Notas (opcional)", placeholder="Ej: entregar hoy, referencia, etc.", key="notas")

        metodo_pago = st.selectbox(
            "Método de pago",
            options=["Transferencia", "Efectivo", "Tarjeta", "Contra Entrega"],
            index=["Transferencia", "Efectivo", "Tarjeta", "Contra Entrega"].index(
                st.session_state.get("metodo_pago", "Transferencia")
            ),
            key="metodo_pago",
        )

        envio_cliente = st.number_input(
            "Envío cobrado al cliente ($)",
            min_value=0.0,
            value=float(st.session_state.get("envio_cliente", 0.0)),
            step=0.50,
            format="%.2f",
            key="envio_cliente",
        )
        costo_courier = st.number_input(
            "Costo real courier ($)",
            min_value=0.0,
            value=float(st.session_state.get("costo_courier", 0.0)),
            step=0.50,
            format="%.2f",
            key="costo_courier",
        )

        override_pce: float | None = None
        if metodo_pago == "Contra Entrega":
            st.markdown("**Comisión PCE (Contra Entrega)**")
            pce_mode = st.radio("Comisión", ["2.99%", "Otro"], horizontal=True, key="pce_mode")
            if pce_mode == "Otro":
                p = st.number_input(
                    "Porcentaje PCE (%)",
                    min_value=0.0,
                    value=float(st.session_state.get("pce_otro", 2.99)),
                    step=0.10,
                    format="%.2f",
                    key="pce_otro",
                )
                override_pce = float(p) / 100.0
            else:
                override_pce = None

    # -----------------------------
    # Totales
    # -----------------------------
    total_lineas = round(sum(float(x["Subtotal_Linea"]) for x in cart), 2) if cart else 0.0
    total_cobrado = round(total_lineas + float(envio_cliente), 2)

    com_porc = comision_porcentaje(metodo_pago, cfg, override_pce)
    com_monto = round(total_cobrado * float(com_porc), 2)

    monto_a_recibir = round(total_cobrado - float(costo_courier) - com_monto, 2)
    monto_class = "gain-ok" if monto_a_recibir >= 0 else "gain-low"

    with card():
        st.markdown("**Resumen**")
        raw_html = f"""
        <div class="card-html">
          <div class="summary-grid">
            <div class="summary-row">
              <div class="summary-label">Subtotal productos</div>
              <div class="summary-value">{money(total_lineas)}</div>
            </div>

            <div class="summary-row">
              <div class="summary-label">(+) Envío cobrado</div>
              <div class="summary-value">{money(envio_cliente)}</div>
            </div>

            <div class="summary-row">
              <div class="summary-label">Total cobrado</div>
              <div class="summary-value">{money(total_cobrado)}</div>
            </div>

            <div class="summary-row">
              <div class="summary-label">(-) Costo courier</div>
              <div class="summary-value">{money(costo_courier)}</div>
            </div>

            <div class="summary-row">
              <div class="summary-label">(-) Comisión ({com_porc*100:.2f}%)</div>
              <div class="summary-value">{money(com_monto)}</div>
            </div>

            <div style="height:1px;background:rgba(255,255,255,0.10);margin:6px 0;"></div>

            <div class="summary-row">
              <div class="summary-label">Monto a recibir</div>
              <div class="{monto_class}">{money(monto_a_recibir)}</div>
            </div>
          </div>
        </div>
        """
        st.markdown(normalize_html(raw_html), unsafe_allow_html=True)

    # -----------------------------
    # Guardar venta + descontar stock
    # -----------------------------
    problems: list[str] = []
    can_save = True

    if not cart:
        can_save = False
        problems.append("Carrito vacío.")
    if not str(cliente).strip():
        can_save = False
        problems.append("Cliente vacío.")
    if total_cobrado <= 0:
        can_save = False
        problems.append("Total cobrado debe ser > 0.")

    if not can_save:
        st.caption(" • " + " ".join([f"❗{p}" for p in problems]))

    save_btn = st.button("✅ REGISTRAR VENTA", use_container_width=True, disabled=not can_save)

    if save_btn:
        try:
            latest_inv = load_inventario(conn)

            col_stock = "Stock_Casa" if bodega_venta_code == "Casa" else "Stock_Bodega"

            # validar stock
            for item in cart:
                sku_i = str(item["SKU"]).strip()
                qty_i = int(item["Cantidad"])

                match = latest_inv[latest_inv["SKU"].astype(str).str.strip() == sku_i]
                if match.empty:
                    raise ValueError(f"SKU no encontrado: {sku_i}")

                r = match.iloc[0]
                available = int(_clean_number(r.get(col_stock, 0)))
                if available < qty_i:
                    raise ValueError(
                        f"Stock insuficiente para {sku_i} en {selected_label}. Disponible={available}, Pedido={qty_i}"
                    )

            cab_df = load_cabecera(conn)

            now = datetime.now(APP_TZ)
            year = int(now.strftime("%Y"))
            venta_id = next_venta_id(cab_df, year)

            fecha = now.strftime("%Y-%m-%d")
            hora = now.strftime("%H:%M:%S")

            cab_row = {
                "Venta_ID": venta_id,
                "Fecha": fecha,
                "Hora": hora,
                "Cliente": str(cliente).strip(),
                "Metodo_Pago": metodo_pago,
                "Envio_Cobrado_Total": float(envio_cliente),
                "Costo_Logistica_Total": float(costo_courier),
                "Comision_Porc": float(com_porc),
                "Total_Lineas": float(total_lineas),
                "Total_Cobrado": float(total_cobrado),
                "Comision_Monto": float(com_monto),
                "Monto_A_Recibir": float(monto_a_recibir),
                "Notas": str(notas).strip(),
                "Estado": "COMPLETADA",
            }

            det_df = load_detalle(conn)
            det_rows: list[dict[str, Any]] = []
            for idx, item in enumerate(cart, start=1):
                det_rows.append(
                    {
                        "Venta_ID": venta_id,
                        "Linea": idx,
                        "SKU": str(item["SKU"]).strip(),
                        "Producto": str(item["Producto"]).strip(),
                        "Drop": str(item["Drop"]).strip(),
                        "Color": str(item["Color"]).strip(),
                        "Talla": str(item["Talla"]).strip(),
                        "Bodega_Salida": selected_label,  # guardamos label en sheet
                        "Cantidad": int(item["Cantidad"]),
                        "Precio_Unitario": float(item["Precio_Unitario"]),
                        "Descuento_Unitario": float(item["Descuento_Unitario"]),
                        "Subtotal_Linea": float(item["Subtotal_Linea"]),
                    }
                )

            cab_df = _align_required_columns(cab_df, CAB_REQUIRED)
            cab_out = pd.concat([cab_df, pd.DataFrame([cab_row])], ignore_index=True)
            cab_out = _align_required_columns(cab_out, CAB_REQUIRED)
            save_sheet(conn, SHEET_VENTAS_CAB, cab_out)

            det_df = _align_required_columns(det_df, DET_REQUIRED)
            det_out = pd.concat([det_df, pd.DataFrame(det_rows)], ignore_index=True)
            det_out = _align_required_columns(det_out, DET_REQUIRED)
            save_sheet(conn, SHEET_VENTAS_DET, det_out)

            # descontar stock en inventario (usa code)
            inv_updated = latest_inv.copy()
            for item in cart:
                sku_i = str(item["SKU"]).strip()
                qty_i = int(item["Cantidad"])

                mask = inv_updated["SKU"].astype(str).str.strip() == sku_i
                if not mask.any():
                    raise ValueError(f"SKU no encontrado al descontar: {sku_i}")
                ix = inv_updated.index[mask].tolist()[0]

                inv_updated.loc[ix, col_stock] = int(_clean_number(inv_updated.loc[ix, col_stock])) - qty_i

            save_sheet(conn, SHEET_INVENTARIO, inv_updated)

            # Guardar mensaje de éxito y reset diferido (NO tocamos widgets aquí)
            st.session_state["_last_sale_id"] = venta_id
            st.session_state["_reset_sale_pending"] = True
            st.rerun()

        except Exception as e:
            st.error("Error al registrar la venta.")
            st.exception(e)

