# app.py
# SCHELETRO Manager (V1) - Streamlit + Google Sheets (st-gsheets-connection)

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Iterable
from contextlib import contextmanager

import pandas as pd
import streamlit as st
from streamlit_gsheets import GSheetsConnection


# -----------------------------
# Config
# -----------------------------
APP_TZ = ZoneInfo("America/El_Salvvador") if False else ZoneInfo("America/El_Salvador")

INVENTARIO_SHEET = "Inventario"
VENTAS_SHEET = "Ventas"

INVENTARIO_COLS = [
    "SKU",
    "Producto",
    "Talla",
    "Stock_Casa",
    "Stock_Bodega",
    "Costo_Unitario",
    "Precio_Lista",
]

VENTAS_COLS = [
    "Fecha",
    "Hora",
    "Cliente",
    "Producto",
    "Talla",
    "Bodega_Salida",
    "Metodo_Pago",
    "Precio_Base",
    "Descuento_Aplicado",
    "Envio_Cobrado",
    "Costo_Logistica_Real",
    "Comision_Calc",
    "Total_Cobrado",
    "Ganancia_Neta",
    "Notas",
]


# -----------------------------
# UI helpers
# -----------------------------
def money(x: float) -> str:
    try:
        return f"${float(x):,.2f}"
    except Exception:
        return "$0.00"


def comision_label(metodo_pago: str) -> str:
    m = (metodo_pago or "").strip().lower()
    if m == "tarjeta":
        return "Comisión Tarjeta (2.30%)"
    if m == "contra entrega":
        return "Comisión Contra Entrega (2.99%)"
    return "Comisión (Transferencia/Efectivo)"


def normalize_html(html: str) -> str:
    """
    🔒 Evita que Streamlit/Markdown interprete el HTML como bloque de código.
    Quita sangría al inicio de CADA línea.
    """
    return "\n".join(line.lstrip() for line in html.splitlines()).strip()


def _segmented_like(
    label: str,
    options: list[Any],
    key: str,
    default: Any | None = None,
    help: str | None = None,
) -> Any:
    """
    Mobile-friendly 'pills/segmented' fallback:
    - st.pills (si existe)
    - st.segmented_control (si existe)
    - st.radio(horizontal=True) (fallback universal)
    """
    if default is None and options:
        default = options[0]

    if hasattr(st, "pills"):
        return st.pills(label, options, default=default, key=key, help=help)  # type: ignore[attr-defined]

    if hasattr(st, "segmented_control"):
        return st.segmented_control(label, options, default=default, key=key, help=help)  # type: ignore[attr-defined]

    idx = options.index(default) if default in options else 0
    return st.radio(label, options, index=idx, horizontal=True, key=key, help=help)


@contextmanager
def card():
    """
    ✅ Card REAL sin "div vacío" en el DOM.
    Usa un marker + CSS :has() para estilizar el bloque completo.
    """
    with st.container():
        st.markdown('<div class="card-marker"></div>', unsafe_allow_html=True)
        yield


def inject_css() -> None:
    st.markdown(
        """
        <style>
          /* Mobile-first container */
          .block-container {
            max-width: 520px;
            padding-top: 1.0rem;
            padding-bottom: 2.0rem;
          }

          /* Hide Streamlit chrome */
          #MainMenu {visibility: hidden;}
          footer {visibility: hidden;}
          header {visibility: hidden;}

          /* Tighten spacing */
          .stVerticalBlock { gap: 0.75rem; }

          /* =========================================
             ✅ CARDS sin divs vacíos (marker-based)
             ========================================= */
          .card-marker { display:none; }

          /* Estiliza SOLO los bloques que tengan el marker */
          div[data-testid="stVerticalBlock"]:has(.card-marker) {
            border: 1px solid rgba(255,255,255,0.08);
            background: rgba(255,255,255,0.03);
            border-radius: 16px;
            padding: 14px 14px;
          }

          /* Evita que el primer elemento pegue arriba demasiado */
          div[data-testid="stVerticalBlock"]:has(.card-marker) > div:first-child {
            margin-top: 0 !important;
          }

          /* Header card (HTML) */
          .card-html {
            border: 1px solid rgba(255,255,255,0.08);
            background: rgba(255,255,255,0.03);
            border-radius: 16px;
            padding: 14px 14px;
          }

          .header-title {
            font-weight: 800;
            letter-spacing: 0.6px;
            font-size: 1.05rem;
            margin: 0 0 2px 0;
          }
          .header-sub {
            opacity: 0.7;
            font-size: 0.85rem;
            margin: 0;
          }

          .price-big {
            font-size: 2.05rem;
            font-weight: 900;
            line-height: 1.05;
            margin: 6px 0 4px 0;
          }
          .muted {
            opacity: 0.75;
            font-size: 0.9rem;
          }

          .summary-grid {
            display: grid;
            grid-template-columns: 1fr;
            gap: 10px;
          }
          .summary-row {
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            gap: 12px;
          }
          .summary-label { opacity: 0.75; }
          .summary-value { font-weight: 800; }

          .total-big {
            font-size: 1.8rem;
            font-weight: 900;
            line-height: 1.1;
          }

          .gain-ok { color: #38d46a; font-weight: 900; }
          .gain-low { color: #ff4d4d; font-weight: 900; }

          /* Bigger inputs for thumbs */
          input, textarea { font-size: 16px !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


# -----------------------------
# Data layer
# -----------------------------
def get_conn() -> GSheetsConnection:
    return st.connection("gsheets", type=GSheetsConnection)


def _ensure_cols(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    df = df.copy()
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    return df[cols]


def _to_numeric(df: pd.DataFrame, cols: Iterable[str]) -> pd.DataFrame:
    df = df.copy()
    for c in cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    return df


def load_inventario(conn: GSheetsConnection) -> pd.DataFrame:
    df = conn.read(worksheet=INVENTARIO_SHEET, ttl=0)
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=INVENTARIO_COLS)

    df = _ensure_cols(df, INVENTARIO_COLS)
    df = _to_numeric(df, ["Stock_Casa", "Stock_Bodega", "Costo_Unitario", "Precio_Lista"])

    df["SKU"] = df["SKU"].astype(str).str.strip()
    df["Producto"] = df["Producto"].astype(str).str.strip()
    df["Talla"] = df["Talla"].astype(str).str.strip()
    return df


def load_ventas(conn: GSheetsConnection) -> pd.DataFrame:
    df = conn.read(worksheet=VENTAS_SHEET, ttl=0)
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=VENTAS_COLS)

    df = _ensure_cols(df, VENTAS_COLS)
    df = _to_numeric(
        df,
        [
            "Precio_Base",
            "Descuento_Aplicado",
            "Envio_Cobrado",
            "Costo_Logistica_Real",
            "Comision_Calc",
            "Total_Cobrado",
            "Ganancia_Neta",
        ],
    )
    return df


def write_ventas_append(conn: GSheetsConnection, new_row: dict[str, Any]) -> None:
    ventas_df = load_ventas(conn)
    new_df = pd.DataFrame([new_row], columns=VENTAS_COLS)
    out = pd.concat([ventas_df, new_df], ignore_index=True)
    conn.update(worksheet=VENTAS_SHEET, data=out)


def update_inventario_stock(
    conn: GSheetsConnection, sku: str, bodega_salida: str, delta: int
) -> pd.DataFrame:
    inv = load_inventario(conn)
    if inv.empty:
        raise ValueError("Inventario vacío o no encontrado.")

    idx_list = inv.index[inv["SKU"].astype(str) == str(sku)].tolist()
    if not idx_list:
        raise ValueError(f"SKU no encontrado en Inventario: {sku}")

    idx = idx_list[0]
    col = "Stock_Casa" if bodega_salida == "Casa" else "Stock_Bodega"

    current = int(inv.at[idx, col])
    new_val = current + int(delta)
    if new_val < 0:
        raise ValueError("Stock insuficiente (se intentó dejar negativo).")

    inv.loc[idx, col] = new_val
    conn.update(worksheet=INVENTARIO_SHEET, data=inv)
    return inv


# -----------------------------
# Business logic
# -----------------------------
@dataclass(frozen=True)
class FinancialResult:
    precio_base: float
    descuento: float
    envio_cobrado: float
    costo_logistica_real: float
    comision: float
    total_cobrado: float
    ganancia_neta: float


def calc_comision(metodo: str, total_cobrado: float) -> float:
    metodo_norm = (metodo or "").strip().lower()
    if metodo_norm == "tarjeta":
        return total_cobrado * 0.023  # 2.30%
    if metodo_norm == "contra entrega":
        return total_cobrado * 0.0299  # 2.99%
    return 0.0


def calc_financials(
    precio_base: float,
    descuento: float,
    envio_cobrado: float,
    costo_unitario: float,
    costo_logistica_real: float,
    metodo_pago: str,
) -> FinancialResult:
    precio_base = float(precio_base)
    descuento = max(0.0, float(descuento))
    envio_cobrado = max(0.0, float(envio_cobrado))
    costo_unitario = max(0.0, float(costo_unitario))
    costo_logistica_real = max(0.0, float(costo_logistica_real))

    total = precio_base + envio_cobrado - descuento
    total = max(0.0, total)

    comision = calc_comision(metodo_pago, total)

    ganancia = total - (costo_unitario + costo_logistica_real + comision)

    return FinancialResult(
        precio_base=round(precio_base, 2),
        descuento=round(descuento, 2),
        envio_cobrado=round(envio_cobrado, 2),
        costo_logistica_real=round(costo_logistica_real, 2),
        comision=round(comision, 2),
        total_cobrado=round(total, 2),
        ganancia_neta=round(ganancia, 2),
    )


# -----------------------------
# Session defaults
# -----------------------------
def init_state() -> None:
    if "inv_df" not in st.session_state:
        st.session_state.inv_df = pd.DataFrame(columns=INVENTARIO_COLS)

    st.session_state.setdefault("_reset_form_pending", False)

    st.session_state.setdefault("producto", None)
    st.session_state.setdefault("talla", None)
    st.session_state.setdefault("bodega_salida", "Casa")
    st.session_state.setdefault("cliente", "")
    st.session_state.setdefault("notas", "")

    st.session_state.setdefault("add_desc", False)
    st.session_state.setdefault("descuento", 0.0)

    st.session_state.setdefault("envio_choice", "$0.00")
    st.session_state.setdefault("envio_otro", 0.0)

    st.session_state.setdefault("metodo_pago", "Transferencia")

    st.session_state.setdefault("costo_envio_choice", "$0.00")
    st.session_state.setdefault("costo_envio_otro", 0.0)
    st.session_state.setdefault("costo_logistica_real", 0.0)


def reset_form() -> None:
    st.session_state["producto"] = None
    st.session_state["talla"] = None
    st.session_state["bodega_salida"] = "Casa"
    st.session_state["cliente"] = ""
    st.session_state["notas"] = ""
    st.session_state["add_desc"] = False
    st.session_state["descuento"] = 0.0

    st.session_state["envio_choice"] = "$0.00"
    st.session_state["envio_otro"] = 0.0

    st.session_state["metodo_pago"] = "Transferencia"

    st.session_state["costo_envio_choice"] = "$0.00"
    st.session_state["costo_envio_otro"] = 0.0
    st.session_state["costo_logistica_real"] = 0.0


def request_reset_form() -> None:
    st.session_state["_reset_form_pending"] = True


# -----------------------------
# App
# -----------------------------
st.set_page_config(
    page_title="SCHELETRO Manager",
    page_icon="🦴",
    layout="centered",
    initial_sidebar_state="collapsed",
)

inject_css()
init_state()

if st.session_state.get("_reset_form_pending", False):
    st.session_state["_reset_form_pending"] = False
    reset_form()

# Header (HTML card completo en una sola llamada: no genera div vacío)
st.markdown(
    """
    <div class="card-html">
      <div class="header-title">SCHELETRO Manager</div>
      <div class="header-sub">Pedidos + Inventario · V1</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Conexión
try:
    conn = get_conn()
except Exception as e:
    st.error("No pude crear la conexión a Google Sheets.")
    st.caption("Revisa `.streamlit/secrets.toml` y que el nombre de conexión sea `[connections.gsheets]`.")
    st.exception(e)
    st.stop()

# Cargar inventario
if st.session_state.inv_df is None or st.session_state.inv_df.empty:
    try:
        st.session_state.inv_df = load_inventario(conn)
    except Exception as e:
        st.error("No pude cargar el Inventario desde Google Sheets.")
        st.exception(e)
        st.stop()

# Refresh
col_r1, col_r2 = st.columns([1, 1])
with col_r2:
    if st.button("🔄 Refrescar", use_container_width=True):
        try:
            st.session_state.inv_df = load_inventario(conn)
            st.success("Inventario actualizado.")
        except Exception as e:
            st.error("Error al refrescar inventario.")
            st.exception(e)

inv_df: pd.DataFrame = st.session_state.inv_df

if inv_df.empty:
    st.warning("Tu hoja **Inventario** está vacía. Agrega productos para empezar.")
    st.stop()

# -----------------------------
# Selector de Producto
# -----------------------------
with card():
    st.markdown("**Producto**")

    productos = sorted([p for p in inv_df["Producto"].dropna().unique().tolist() if str(p).strip()])
    if st.session_state["producto"] not in productos:
        st.session_state["producto"] = productos[0] if productos else None

    producto_sel = st.selectbox(
        "Producto",
        options=productos,
        index=productos.index(st.session_state["producto"]) if st.session_state["producto"] in productos else 0,
        label_visibility="collapsed",
        key="producto",
    )

    df_prod = inv_df[inv_df["Producto"] == producto_sel].copy()
    is_gorra = "gorra" in str(producto_sel).strip().lower()

    if is_gorra:
        tallas = ["Única"]
    else:
        tallas = sorted([t for t in df_prod["Talla"].dropna().unique().tolist() if str(t).strip()])

    if not tallas:
        tallas = ["Única"] if is_gorra else ["—"]

    if st.session_state["talla"] not in tallas:
        st.session_state["talla"] = tallas[0]

    talla_sel = st.selectbox(
        "Talla",
        options=tallas,
        index=tallas.index(st.session_state["talla"]) if st.session_state["talla"] in tallas else 0,
        label_visibility="collapsed",
        key="talla",
    )

    bodega_sel = st.radio(
        "Bodega de Salida",
        options=["Casa", "Bodega"],
        horizontal=True,
        key="bodega_salida",
    )

# Fila exacta
match = inv_df[(inv_df["Producto"] == producto_sel) & (inv_df["Talla"] == talla_sel)]
if match.empty:
    match = df_prod.head(1)

row = match.iloc[0]
sku = str(row["SKU"])
precio_lista = float(row["Precio_Lista"])
costo_unitario = float(row["Costo_Unitario"])
stock_col = "Stock_Casa" if bodega_sel == "Casa" else "Stock_Bodega"
stock = int(row[stock_col])

stock_ok = stock > 0
if stock <= 0:
    st.error("❌ **AGOTADO** (no se puede registrar venta)")
elif stock <= 2:
    st.warning("⚠️ **Pocas unidades**")

# -----------------------------
# Cliente
# -----------------------------
with card():
    st.markdown("**Cliente**")
    cliente = st.text_input("Nombre", placeholder="Nombre del cliente", label_visibility="collapsed", key="cliente")

# -----------------------------
# Precio y Descuentos
# -----------------------------
with card():
    st.markdown("**Precio**")
    st.markdown(f'<div class="price-big">{money(precio_lista)}</div>', unsafe_allow_html=True)
    st.markdown('<div class="muted">Precio lista</div>', unsafe_allow_html=True)

    add_desc = st.toggle("Añadir descuento", key="add_desc")
    descuento = 0.0
    if add_desc:
        descuento = st.number_input(
            "Monto a descontar ($)",
            min_value=0.0,
            value=float(st.session_state.get("descuento", 0.0)),
            step=0.50,
            format="%.2f",
            key="descuento",
        )
    else:
        st.session_state["descuento"] = 0.0

# -----------------------------
# Envío y Pago
# -----------------------------
with card():
    st.markdown("**Envío y Pago**")

    envio_choice = _segmented_like(
        "Cobro de Envío al Cliente",
        options=["$0.00", "$2.50", "Otro"],
        default=st.session_state.get("envio_choice", "$0.00"),
        key="envio_choice",
    )

    if envio_choice == "Otro":
        envio_cobrado = st.number_input(
            "Envío al cliente ($)",
            min_value=0.0,
            value=float(st.session_state.get("envio_otro", 0.0)),
            step=0.50,
            format="%.2f",
            key="envio_otro",
        )
    elif envio_choice == "$2.50":
        envio_cobrado = 2.50
    else:
        envio_cobrado = 0.0

    metodo_pago = st.selectbox(
        "Método de Pago",
        options=["Transferencia", "Efectivo", "Tarjeta", "Contra Entrega"],
        index=["Transferencia", "Efectivo", "Tarjeta", "Contra Entrega"].index(
            st.session_state.get("metodo_pago", "Transferencia")
        ),
        key="metodo_pago",
    )

    with st.expander("Costos de Envío", expanded=False):
        st.caption("Este costo NO lo ve el cliente. Es lo que tú pagas al courier.")
        costo_envio_choice = _segmented_like(
            "Costo de envío (Courier)",
            options=["$0.00", "$2.50", "Otro"],
            default=st.session_state.get("costo_envio_choice", "$0.00"),
            key="costo_envio_choice",
        )

        if costo_envio_choice == "Otro":
            costo_logistica_real = st.number_input(
                "Costo real del courier ($)",
                min_value=0.0,
                value=float(st.session_state.get("costo_envio_otro", 0.0)),
                step=0.50,
                format="%.2f",
                key="costo_envio_otro",
            )
        elif costo_envio_choice == "$2.50":
            costo_logistica_real = 2.50
        else:
            costo_logistica_real = 0.0

        st.session_state["costo_logistica_real"] = float(costo_logistica_real)

# -----------------------------
# Notas
# -----------------------------
with card():
    st.markdown("**Notas (opcional)**")
    notas = st.text_area(
        "Notas",
        placeholder="Ej: entregar hoy, color, referencia, etc.",
        label_visibility="collapsed",
        key="notas",
    )

# -----------------------------
# Motor financiero + resumen
# -----------------------------
max_desc = max(0.0, precio_lista + float(envio_cobrado))
if descuento > max_desc:
    st.warning("⚠️ El descuento excede el total (precio + envío). Se ajustará automáticamente.")
    descuento = max_desc

fin = calc_financials(
    precio_base=precio_lista,
    descuento=descuento,
    envio_cobrado=float(envio_cobrado),
    costo_unitario=costo_unitario,
    costo_logistica_real=float(st.session_state.get("costo_logistica_real", 0.0)),
    metodo_pago=metodo_pago,
)

monto_recibir = round(fin.total_cobrado - fin.costo_logistica_real - fin.comision, 2)
monto_class = "gain-ok" if monto_recibir >= 0 else "gain-low"

desc_row_html = ""
if fin.descuento > 0:
    desc_row_html = normalize_html(
        f"""
<div class="summary-row">
  <div class="summary-label">(-) Descuento</div>
  <div class="summary-value">{money(fin.descuento)}</div>
</div>
"""
    )

raw_html = f"""
<div class="card-html">
  <div class="summary-grid">
    <div>
      <div class="summary-label">Monto de venta</div>
      <div class="total-big">{money(fin.precio_base)}</div>
    </div>

    <div class="summary-row">
      <div class="summary-label">(+) Envío cliente</div>
      <div class="summary-value">{money(fin.envio_cobrado)}</div>
    </div>

    {desc_row_html}

    <div class="summary-row">
      <div class="summary-label">(-) Costo envío (Courier)</div>
      <div class="summary-value">{money(fin.costo_logistica_real)}</div>
    </div>

    <div class="summary-row">
      <div class="summary-label">(-) {comision_label(metodo_pago)}</div>
      <div class="summary-value">{money(fin.comision)}</div>
    </div>

    <div style="height:1px;background:rgba(255,255,255,0.10);margin:6px 0;"></div>

    <div class="summary-row">
      <div class="summary-label">Monto a Recibir</div>
      <div class="{monto_class}">{money(monto_recibir)}</div>
    </div>
  </div>
</div>
"""
st.markdown(normalize_html(raw_html), unsafe_allow_html=True)

# -----------------------------
# Acción: Registrar venta
# -----------------------------
can_save = True
problems: list[str] = []

if not stock_ok:
    can_save = False
    problems.append("Stock agotado.")
if not str(cliente).strip():
    can_save = False
    problems.append("Cliente vacío.")
if fin.total_cobrado <= 0:
    can_save = False
    problems.append("Total a cobrar debe ser > 0.")

if not can_save:
    st.caption(" • " + " ".join([f"❗{p}" for p in problems]))

btn = st.button("REGISTRAR VENTA", use_container_width=True, disabled=not can_save)

if btn:
    try:
        
        latest_inv = load_inventario(conn)
        latest_match = latest_inv[(latest_inv["SKU"].astype(str) == sku)]
        if latest_match.empty:
            raise ValueError("SKU no encontrado al momento de guardar (inventario cambió).")

        latest_row = latest_match.iloc[0]
        latest_stock = int(latest_row["Stock_Casa" if bodega_sel == "Casa" else "Stock_Bodega"])
        if latest_stock <= 0:
            st.error("❌ AGOTADO (al momento de guardar). Refresca e intenta de nuevo.")
            st.stop()

        now = datetime.now(APP_TZ)
        fecha = now.strftime("%Y-%m-%d")
        hora = now.strftime("%H:%M:%S")

        venta_row = {
            "Fecha": fecha,
            "Hora": hora,
            "Cliente": str(cliente).strip(),
            "Producto": str(producto_sel).strip(),
            "Talla": str(talla_sel).strip(),
            "Bodega_Salida": bodega_sel,
            "Metodo_Pago": metodo_pago,
            "Precio_Base": fin.precio_base,
            "Descuento_Aplicado": fin.descuento,
            "Envio_Cobrado": fin.envio_cobrado,
            "Costo_Logistica_Real": fin.costo_logistica_real,
            "Comision_Calc": fin.comision,
            "Total_Cobrado": fin.total_cobrado,
            "Ganancia_Neta": fin.ganancia_neta,
            "Notas": str(notas).strip(),
        }


        write_ventas_append(conn, venta_row)

    
        updated_inv = update_inventario_stock(conn, sku=sku, bodega_salida=bodega_sel, delta=-1)


        st.session_state.inv_df = updated_inv
        request_reset_form()

        st.success("✅ Venta registrada. Inventario actualizado.")
        st.rerun()

    except Exception as e:
        st.error("Error al registrar la venta.")
        st.exception(e)

