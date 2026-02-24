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

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Iterable, cast
import re
import unicodedata
from itertools import product as iterproduct

import pandas as pd
import streamlit as st
import hmac
from streamlit_gsheets import GSheetsConnection




# =========================
# Seguridad: Password Gate
# =========================
def require_password() -> None:
    """Bloquea la app con una contraseña guardada en Streamlit Secrets.

    En Streamlit Cloud -> Settings -> Secrets agrega:
    APP_PASSWORD = "TU_CLAVE"
    """
    app_pw = st.secrets.get("APP_PASSWORD", None)
    if not app_pw:
        st.error("No está configurado APP_PASSWORD en Secrets. Ve a Settings → Secrets y agrégalo.")
        st.stop()

    # Invalida sesión si cambia la contraseña (evita sesiones viejas)
    pw_fp = f"len:{len(str(app_pw))}"
    if st.session_state.get("_pw_fp") != pw_fp:
        st.session_state["_pw_fp"] = pw_fp
        st.session_state["_auth_ok"] = False
        st.session_state.pop("_auth_error", None)

    # Estado de auth (NO es widget key)
    if "_auth_ok" not in st.session_state:
        st.session_state["_auth_ok"] = False

    # Key del input del widget (separado)
    if "_auth_pw_input" not in st.session_state:
        st.session_state["_auth_pw_input"] = ""

    # Si ya está autenticado, botón de logout
    if st.session_state.get("_auth_ok", False):
        with st.sidebar:
            if st.button("Cerrar sesión 🔒", use_container_width=True, key="_logout_btn"):
                st.session_state["_auth_ok"] = False
                st.session_state["_auth_pw_input"] = ""
                st.rerun()
        return

    st.title("SCHELETRO Manager 🔒")
    st.markdown("### Acceso restringido")

    # Si se pidió limpiar, limpia ANTES de instanciar el widget (evita StreamlitAPIException)
    if st.session_state.get("_pw_clear_flag", False):
        st.session_state["_auth_pw_input"] = ""
        st.session_state["_pw_clear_flag"] = False
        st.session_state.pop("_auth_error", None)

    with st.form("login_form", clear_on_submit=False):
        pw = st.text_input("Contraseña", type="password", key="_auth_pw_input")

        c1, c2 = st.columns([1, 1])
        submitted = c1.form_submit_button("Entrar", use_container_width=True)
        cleared = c2.form_submit_button("Limpiar", use_container_width=True)

    if cleared:
        # No tocar el key del widget después de instanciado en esta corrida.
        # Marca flag y rerun: en la siguiente corrida se limpia antes del widget.
        st.session_state["_pw_clear_flag"] = True
        st.rerun()

    if submitted:
        if hmac.compare_digest(str(pw), str(app_pw)):
            st.session_state["_auth_ok"] = True
            st.session_state.pop("_auth_error", None)
            st.session_state["_auth_pw_input"] = ""
            st.rerun()
        else:
            st.session_state["_auth_ok"] = False
            st.session_state["_auth_error"] = "Contraseña incorrecta."

    err = st.session_state.get("_auth_error")
    if err:
        st.error(err)

    st.stop()

# -----------------------------
# Sheets / Tabs (DEBEN coincidir con tus pestañas)
# -----------------------------
SHEET_INVENTARIO = "Inventario"
SHEET_VENTAS_CAB = "Ventas_Cabecera"
SHEET_VENTAS_DET = "Ventas_Detalle"
SHEET_CONFIG = "Config"
SHEET_INVERSIONES = "Inversiones"


# -----------------------------
# Columnas esperadas (sin destruir columnas extra)
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

INVEST_REQUIRED = [
    "Tipo",
    "Referencia",
    "Monto_Invertido",
    "Notas",
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
          .total-big { font-size: 1.8rem; font-weight: 900; line-height: 1.1; }

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


def _is_rate_limit(e: Exception) -> bool:
    s = str(e)
    return ("code': 429" in s) or ("RESOURCE_EXHAUSTED" in s) or ("RATE_LIMIT_EXCEEDED" in s)


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Limpia nombres de columnas y garantiza DataFrame."""
    if df is None or not isinstance(df, pd.DataFrame):
        return pd.DataFrame()
    out = df.copy()
    out.columns = [str(c).strip() for c in out.columns]
    return out


@st.cache_data(ttl=45, show_spinner=False)
def _cached_read_45(worksheet: str) -> pd.DataFrame:
    try:
        _conn = st.connection("gsheets", type=GSheetsConnection)
        df = _conn.read(worksheet=worksheet, ttl=45)
        return _normalize_df(df)
    except Exception as e:
        # No cachear un estado "malo" indefinidamente: devolvemos DF vacío para evitar romper UI.
        if _is_rate_limit(e):
            st.warning("Google Sheets está rate-limited (429). Usando cache/local vacío temporalmente.")
        else:
            st.warning(f"No se pudo leer '{worksheet}': {e}")
        return pd.DataFrame()


@st.cache_data(ttl=180, show_spinner=False)
def _cached_read_180(worksheet: str) -> pd.DataFrame:
    try:
        _conn = st.connection("gsheets", type=GSheetsConnection)
        df = _conn.read(worksheet=worksheet, ttl=180)
        return _normalize_df(df)
    except Exception as e:
        if _is_rate_limit(e):
            st.warning("Google Sheets está rate-limited (429). Usando cache/local vacío temporalmente.")
        else:
            st.warning(f"No se pudo leer '{worksheet}': {e}")
        return pd.DataFrame()


@st.cache_data(ttl=600, show_spinner=False)
def _cached_read_600(worksheet: str) -> pd.DataFrame:
    try:
        _conn = st.connection("gsheets", type=GSheetsConnection)
        df = _conn.read(worksheet=worksheet, ttl=600)
        return _normalize_df(df)
    except Exception as e:
        if _is_rate_limit(e):
            st.warning("Google Sheets está rate-limited (429). Usando cache/local vacío temporalmente.")
        else:
            st.warning(f"No se pudo leer '{worksheet}': {e}")
        return pd.DataFrame()


def load_raw_sheet(conn: GSheetsConnection, worksheet: str, ttl_s: int = 45) -> pd.DataFrame:
    """
    Lectura con cache (anti-429):
    - Usa cache_data para evitar lecturas repetidas en cada rerun.
    - ttl_s <= 0 fuerza lectura directa (sin cache_data) para operaciones críticas.
    """
    ttl_s = int(ttl_s or 45)

    # Forzar lectura directa (para guardados / validaciones críticas)
    if ttl_s <= 0:
        try:
            df = conn.read(worksheet=worksheet, ttl=1)
            return _normalize_df(df)
        except Exception as e:
            if _is_rate_limit(e):
                st.error("Google Sheets está rate-limited (429). Esperá un momento y reintentá.")
                return pd.DataFrame()
            raise

    # Ruteo por TTL (mantiene el espíritu de los ttl_s del código)
    if ttl_s <= 60:
        return _cached_read_45(worksheet).copy()
    if ttl_s <= 300:
        return _cached_read_180(worksheet).copy()
    return _cached_read_600(worksheet).copy()



def save_sheet(conn: GSheetsConnection, worksheet: str, df: pd.DataFrame) -> None:
    """Escribe un DataFrame a Google Sheets. (ÚNICO punto de escritura)"""
    try:
        conn.update(worksheet=worksheet, data=df)
    except Exception as e:
        if _is_rate_limit(e):
            st.error(
                "⚠️ Google Sheets te limitó por demasiadas solicitudes (error 429) al ESCRIBIR. "
                "Esperá 60–90 segundos y reintentá."
            )
            return
        raise

    # Importante: limpiamos cache para que las lecturas posteriores vean el cambio.
    try:
        st.cache_data.clear()
    except Exception:
        pass

def load_config(conn: GSheetsConnection, ttl_s: int = 120) -> dict[str, Any]:
    df = load_raw_sheet(conn, SHEET_CONFIG, ttl_s=ttl_s)
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


def load_inventario(conn: GSheetsConnection, ttl_s: int = 45) -> pd.DataFrame:
    df = load_raw_sheet(conn, SHEET_INVENTARIO, ttl_s=ttl_s)
    if df.empty:
        return _align_required_columns(pd.DataFrame(), INV_REQUIRED)

    df = _align_required_columns(df, INV_REQUIRED)
    df = _to_numeric(df, ["Stock_Casa", "Stock_Bodega", "Costo_Unitario", "Precio_Lista"])

    for c in ["SKU", "Drop", "Producto", "Color", "Talla"]:
        df[c] = df[c].astype(str).fillna("").str.strip()

    df["Activo"] = df["Activo"].apply(_to_bool)
    return df


# -----------------------------
# Catálogos (Drops / Colores) + generación de SKU

SHEET_CATALOGOS = "Catalogos"

def load_catalogos(conn: GSheetsConnection, ttl_s: int = 600) -> pd.DataFrame:
    """Lee hoja Catalogos (Drops, Colores, etc.) con cache."""
    df = load_raw_sheet(conn, SHEET_CATALOGOS, ttl_s=ttl_s)
    # Normaliza encabezados por si vienen con espacios
    df.columns = [str(c).strip() for c in df.columns]
    return df

def parse_catalogos(df: pd.DataFrame) -> dict[str, list[dict[str, str]]]:
    """Devuelve dict con listas: drops[{valor,codigo}], colores[{valor,codigo}]."""
    if df is None or df.empty:
        return {"drops": [], "colores": []}

    work = df.copy()
    # En tu sheet, a veces puede quedar una celda vacía en 'Catalogo' (ej: A21).
    # Para que no se rompa, heredamos el último valor válido.
    if "Catalogo" in work.columns:
        work["Catalogo"] = work["Catalogo"].ffill()

    # Limpieza básica
    for col in ["Catalogo", "Valor", "Codigo"]:
        if col in work.columns:
            work[col] = work[col].astype(str).str.strip()

    def _pick(cat: str) -> list[dict[str, str]]:
        sub = work[work.get("Catalogo", "").str.upper() == cat.upper()].copy()
        if sub.empty:
            return []
        out = []
        for _, r in sub.iterrows():
            valor = (r.get("Valor") or "").strip()
            codigo = (r.get("Codigo") or "").strip()
            if not valor:
                continue
            if not codigo or codigo.lower() == "nan":
                # fallback: código = valor (sanitizado)
                codigo = re.sub(r"\s+", "", valor).upper()
            out.append({"valor": valor, "codigo": codigo})
        return out

    return {"drops": _pick("DROP"), "colores": _pick("COLOR")}

def _strip_accents(s: str) -> str:
    s = str(s or "")
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch)
    )

def _slug_upper(s: str) -> str:
    s = _strip_accents(s).upper().strip()
    s = re.sub(r"[^A-Z0-9\s\-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def suggest_product_code(product_name: str) -> str:
    """Sugiere un código de 3 letras tipo PSY / BSC."""
    s = _slug_upper(product_name)
    if not s:
        return "PRD"
    # Quita palabras ultra genéricas (pero deja 'HAT' y 'LONGSLEEVE' porque a veces son parte del estilo)
    stop = {"T-SHIRT", "TSHIRT", "TEE", "SHIRT"}
    words = [w for w in s.replace("-", " ").split() if w and w not in stop]
    if not words:
        words = s.replace("-", " ").split()

    consonants = "BCDFGHJKLMNPQRSTVWXYZ0123456789"
    code = ""
    for w in words:
        for ch in w:
            if ch in consonants:
                code += ch
            if len(code) >= 3:
                break
        if len(code) >= 3:
            break

    code = (code + "XXX")[:3]
    return code

def build_sku(drop_code: str, prod_code: str, color_code: str, size_code: str) -> str:
    return f"{drop_code}-{prod_code}-{color_code}-{size_code}".upper()

def get_existing_product_code(inv_df: pd.DataFrame, product_name: str) -> str | None:
    """Si el producto ya existe, intenta respetar su código (2do segmento del SKU)."""
    if inv_df is None or inv_df.empty:
        return None
    sub = inv_df[inv_df.get("Producto", "") == product_name]
    if sub.empty:
        return None
    # SKU esperado: DROP-PROD-COLOR-TALLA
    segs = sub["SKU"].astype(str).str.split("-", n=3, expand=True)
    if segs.shape[1] < 2:
        return None
    # toma el más común
    prod_codes = segs[1].dropna().astype(str).str.strip()
    if prod_codes.empty:
        return None
    return prod_codes.value_counts().index[0]

def ensure_unique_skus(new_skus: list[str], existing: set[str]) -> tuple[bool, list[str]]:
    dups = [s for s in new_skus if s in existing]
    return (len(dups) == 0, dups)

def size_sort_key(s: str) -> int:
    order = ["XS", "S", "M", "L", "XL", "XXL", "XXXL", "OS"]
    s = str(s or "").upper().strip()
    return order.index(s) if s in order else 999



def load_cabecera(conn: GSheetsConnection, ttl_s: int = 60) -> pd.DataFrame:
    df = load_raw_sheet(conn, SHEET_VENTAS_CAB, ttl_s=ttl_s)
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


def load_detalle(conn: GSheetsConnection, ttl_s: int = 60) -> pd.DataFrame:
    df = load_raw_sheet(conn, SHEET_VENTAS_DET, ttl_s=ttl_s)
    if df.empty:
        return _align_required_columns(pd.DataFrame(), DET_REQUIRED)

    df = _align_required_columns(df, DET_REQUIRED)
    df = _to_numeric(df, ["Linea", "Cantidad", "Precio_Unitario", "Descuento_Unitario", "Subtotal_Linea"])
    for c in ["Venta_ID", "SKU", "Producto", "Drop", "Color", "Talla", "Bodega_Salida"]:
        df[c] = df[c].astype(str).fillna("").str.strip()
    return df

def load_inversiones(conn: GSheetsConnection, ttl_s: int = 180) -> pd.DataFrame:
    df = load_raw_sheet(conn, SHEET_INVERSIONES, ttl_s=ttl_s)
    if df.empty:
        return _align_required_columns(pd.DataFrame(), INVEST_REQUIRED)

    df = _align_required_columns(df, INVEST_REQUIRED)
    df = _to_numeric(df, ["Monto_Invertido"])
    for c in ["Tipo", "Referencia", "Notas"]:
        df[c] = df[c].astype(str).fillna("").str.strip()

    df["Tipo"] = df["Tipo"].str.upper()
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

    st.session_state.setdefault("bodega_venta", "Casa")  # interno: Casa/Bodega
    st.session_state.setdefault("envio_cliente", 0.0)
    st.session_state.setdefault("costo_courier", 0.0)

    st.session_state.setdefault("pce_mode", "2.99%")
    st.session_state.setdefault("pce_otro", 2.99)

    st.session_state.setdefault("_reset_sale_pending", False)


def reset_sale_form() -> None:
    st.session_state["cart"] = []
    st.session_state["cliente"] = ""
    st.session_state["notas"] = ""
    st.session_state["metodo_pago"] = "Transferencia"
    st.session_state["bodega_venta"] = "Casa"
    st.session_state["envio_cliente"] = 0.0
    st.session_state["costo_courier"] = 0.0
    st.session_state["pce_mode"] = "2.99%"
    st.session_state["pce_otro"] = 2.99


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

def render_app_header(sub: str) -> None:
    st.markdown(
        f"""
        <div class=\"card-html\">
          <div class=\"header-title\">SCHELETRO Manager</div>
          <div class=\"header-sub\">{sub}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

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

# Tabs

# -----------------------------
# Egresos (nuevo)
# -----------------------------
SHEET_EGRESOS = "Egresos"

EGRESOS_REQUIRED = [
    "Egreso_ID",
    "Fecha",
    "Concepto",
    "Categoria",
    "Monto",
    "Notas",
    "Drop",
]

def load_egresos(conn: GSheetsConnection, ttl_s: int = 60) -> pd.DataFrame:
    df = load_raw_sheet(conn, SHEET_EGRESOS, ttl_s=ttl_s)
    if df.empty:
        return _align_required_columns(pd.DataFrame(), EGRESOS_REQUIRED)

    df = _align_required_columns(df, EGRESOS_REQUIRED)
    df = _to_numeric(df, ["Monto"])
    for c in ["Egreso_ID", "Fecha", "Concepto", "Categoria", "Notas", "Drop"]:
        df[c] = df[c].astype(str).fillna("").str.strip()
    return df

def next_egreso_id(eg_df: pd.DataFrame, year: int) -> str:
    pat = re.compile(r"^E-(\d{4})-(\d{4})$")
    max_n = 0
    if "Egreso_ID" not in eg_df.columns:
        return f"E-{year}-0001"

    for eid in eg_df["Egreso_ID"].astype(str).tolist():
        m = pat.match(eid.strip())
        if not m:
            continue
        y = int(m.group(1))
        n = int(m.group(2))
        if y == year and n > max_n:
            max_n = n
    return f"E-{year}-{max_n + 1:04d}"

# -----------------------------
# Navegación tipo app (BottomNav)
# -----------------------------
def inject_nav_css() -> None:
    st.markdown(
        '''
        <style>
          .bottom-nav-marker { display:none; }

          div[data-testid="stVerticalBlock"]:has(.bottom-nav-marker) {
            position: fixed;
            left: 0;
            right: 0;
            bottom: 0;
            z-index: 999;
            padding: 10px 12px calc(10px + env(safe-area-inset-bottom));
            background: rgba(15,15,18,0.88);
            backdrop-filter: blur(10px);
            border-top: 1px solid rgba(255,255,255,0.08);
          }

          /* deja espacio para el nav */
          .block-container { padding-bottom: 96px; }

          .nav-pill {
            border: 1px solid rgba(255,255,255,0.10);
            background: rgba(255,255,255,0.03);
            border-radius: 999px;
            padding: 8px 10px;
            text-align: center;
            font-weight: 800;
            letter-spacing: 0.2px;
          }
          .nav-pill.active {
            border-color: rgba(255,255,255,0.22);
            background: rgba(255,255,255,0.08);
          }
        </style>
        ''',
        unsafe_allow_html=True,
    )

def nav_state_init() -> None:
    st.session_state.setdefault("screen", "Dashboard")
    st.session_state.setdefault("ventas_sub", "Ventas")
    st.session_state.setdefault("inventario_sub", "Inventario")

def set_screen(name: str) -> None:
    st.session_state["screen"] = name

def bottom_nav() -> None:
    # se dibuja al final para quedar encima de todo
    with st.container():
        st.markdown('<div class="bottom-nav-marker"></div>', unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns(4)
        screens = [
            ("Dashboard", "🏠"),
            ("Inventario", "📦"),
            ("Ventas", "🧾"),
            ("Finanzas", "📈"),
        ]
        cols = [c1, c2, c3, c4]
        for col, (name, icon) in zip(cols, screens):
            with col:
                active = (st.session_state.get("screen") == name)
                btn_type = "primary" if active else "secondary"
                if st.button(f"{icon}\n{name}", use_container_width=True, type=btn_type, key=f"nav_{name}"):
                    set_screen(name)
                    st.rerun()


def _month_range(now: datetime) -> tuple[pd.Timestamp, pd.Timestamp]:
    start = pd.Timestamp(year=now.year, month=now.month, day=1)
    if now.month == 12:
        end = pd.Timestamp(year=now.year + 1, month=1, day=1)
    else:
        end = pd.Timestamp(year=now.year, month=now.month + 1, day=1)
    return start, end

def render_dashboard_screen(conn: GSheetsConnection, inv_df_full: pd.DataFrame, APP_TZ: ZoneInfo) -> None:
    render_app_header("🏠 Dashboard")

    now = datetime.now(APP_TZ)
    m_start, m_end = _month_range(now)

    cab_df = load_cabecera(conn, ttl_s=60)
    eg_df = load_egresos(conn, ttl_s=60)

    ingresos_mes = 0.0
    if not cab_df.empty:
        cab_df["_Fecha_dt"] = pd.to_datetime(cab_df["Fecha"], errors="coerce", dayfirst=True)
        cab_m = cab_df[(cab_df["_Fecha_dt"] >= m_start) & (cab_df["_Fecha_dt"] < m_end)].copy()
        cab_m["Total_Cobrado"] = pd.to_numeric(cab_m["Total_Cobrado"], errors="coerce").fillna(0.0)
        ingresos_mes = float(cab_m["Total_Cobrado"].sum())

    egresos_mes = 0.0
    if not eg_df.empty:
        eg_df["_Fecha_dt"] = pd.to_datetime(eg_df["Fecha"], errors="coerce", dayfirst=True)
        eg_m = eg_df[(eg_df["_Fecha_dt"] >= m_start) & (eg_df["_Fecha_dt"] < m_end)].copy()
        eg_m["Monto"] = pd.to_numeric(eg_m["Monto"], errors="coerce").fillna(0.0)
        egresos_mes = float(eg_m["Monto"].sum())

    balance = ingresos_mes - egresos_mes

    # KPIs
    with card():
        st.markdown("### Resumen del mes")
        st.caption(now.strftime("%B %Y"))
        r1 = st.columns(3)
        r1[0].markdown(f"**Ingresos (mes):**  {money(ingresos_mes)}")
        r1[1].markdown(f"**Egresos (mes):**  {money(egresos_mes)}")
        r1[2].markdown(f"**Balance:**  {money(balance)}")

    # Alertas inventario
    with card():
        st.markdown("### Alertas de inventario")
        inv = inv_df_full.copy()
        if inv.empty:
            st.info("No hay inventario para analizar.")
        else:
            inv["Stock_Casa"] = pd.to_numeric(inv["Stock_Casa"], errors="coerce").fillna(0).astype(int)
            inv["Stock_Bodega"] = pd.to_numeric(inv["Stock_Bodega"], errors="coerce").fillna(0).astype(int)
            inv["Total_Stock"] = inv["Stock_Casa"] + inv["Stock_Bodega"]
            if "Activo" in inv.columns:
                inv = inv[inv["Activo"].fillna(True) == True].copy()

            by_prod = inv.groupby("Producto", as_index=False)["Total_Stock"].sum().sort_values("Total_Stock")
            low = by_prod[by_prod["Total_Stock"] <= 2].head(12)
            mid = by_prod[(by_prod["Total_Stock"] >= 3) & (by_prod["Total_Stock"] <= 6)].head(12)

            if low.empty and mid.empty:
                st.success("Todo bien: no hay productos en stock bajo/medio.")
            else:
                if not low.empty:
                    st.markdown("**🟥 Bajo (≤ 2):**")
                    for _, r in low.iterrows():
                        st.write(f"• {r['Producto']}: {int(r['Total_Stock'])} u.")
                if not mid.empty:
                    st.markdown("**🟨 Medio (3–6):**")
                    for _, r in mid.iterrows():
                        st.write(f"• {r['Producto']}: {int(r['Total_Stock'])} u.")

    # Actividad reciente (ventas + egresos)
    with card():
        st.markdown("### Actividad reciente")
        events = []

        if not cab_df.empty:
            c = cab_df.copy()
            c["_Fecha_dt"] = pd.to_datetime(c["Fecha"], errors="coerce", dayfirst=True)
            # arma datetime con hora si existe
            def _dt(row):
                d = row.get("_Fecha_dt")
                if pd.isna(d):
                    return pd.NaT
                h = str(row.get("Hora","")).strip()
                try:
                    if h:
                        hh, mm, ss = (h.split(":") + ["0","0"])[:3]
                        return pd.Timestamp(d.year, d.month, d.day, int(hh), int(mm), int(float(ss)))
                except Exception:
                    pass
                return pd.Timestamp(d.year, d.month, d.day)
            c["_DT"] = c.apply(_dt, axis=1)
            c["Total_Cobrado"] = pd.to_numeric(c["Total_Cobrado"], errors="coerce").fillna(0.0)
            for _, r in c.sort_values("_DT", ascending=False).head(25).iterrows():
                events.append({
                    "DT": r.get("_DT"),
                    "Tipo": "Venta",
                    "Detalle": f"{r.get('Venta_ID','')} · {r.get('Cliente','')}",
                    "Monto": float(r.get("Total_Cobrado", 0.0)),
                })

        if not eg_df.empty:
            e = eg_df.copy()
            e["_DT"] = pd.to_datetime(e["Fecha"], errors="coerce", dayfirst=True)
            e["Monto"] = pd.to_numeric(e["Monto"], errors="coerce").fillna(0.0)
            for _, r in e.sort_values("_DT", ascending=False).head(25).iterrows():
                events.append({
                    "DT": r.get("_DT"),
                    "Tipo": "Egreso",
                    "Detalle": f"{r.get('Categoria','')} · {r.get('Concepto','')}",
                    "Monto": -float(r.get("Monto", 0.0)),
                })

        if not events:
            st.info("Aún no hay actividad.")
        else:
            ev = pd.DataFrame(events)
            ev = ev.sort_values("DT", ascending=False).head(15)
            for _, r in ev.iterrows():
                dt = r.get("DT")
                when = dt.strftime("%d/%m %H:%M") if hasattr(dt, "strftime") and not pd.isna(dt) else ""
                monto = float(r.get("Monto",0.0))
                tag = "🟢" if monto >= 0 else "🔴"
                st.write(f"{tag} **{r.get('Tipo','')}** · {when} · {r.get('Detalle','')} · **{money(abs(monto))}**")


def render_inventario_screen(conn: GSheetsConnection, inv_df_full: pd.DataFrame) -> None:
    render_app_header("📦 Inventario")
    st.markdown("<div class='small-note'>Subsecciones: Inventario · Transferir · Nuevo</div>", unsafe_allow_html=True)

    # Subnav (sin tocar lógica, solo reubicar)
    sub = st.radio(
        "Sección",
        ["Inventario", "Transferir", "Nuevo"],
        horizontal=True,
        key="inventario_sub",
        label_visibility="collapsed",
    )

    # =========================================================
    # Inventario (UX v2: acordeones + detalle por color/talla)
    # =========================================================

    # Auto-carga estable: cache TTL + refresco forzado por botón
    inv_df = inv_df_full.copy()
    if "Activo" in inv_df.columns:
        inv_df = inv_df[inv_df["Activo"].fillna(True) == True].copy()

    # Cargamos catálogos (Drops/Colores) con cache largo
    cat_df = load_catalogos(conn, ttl_s=600)
    cat = parse_catalogos(cat_df)
    colores_catalogo = cat.get("colores", [])

    # Mapas útiles
    color_to_code = {c["valor"]: c["codigo"] for c in colores_catalogo}
    # Fallbacks fijos para tus defaults
    color_to_code.setdefault("Standard", "STD")
    color_to_code.setdefault("STANDARD", "STD")

    # -----------------------------
    # Sección 1: Inventario (plegable)
    # -----------------------------

    if sub == "Inventario":
        with st.expander("Inventario", expanded=True):
            top_l, top_r = st.columns([1, 1])
            with top_r:
                if st.button("🔄 Refrescar Inventario", use_container_width=True):
                    st.cache_data.clear()
                    st.rerun()

            st.caption("Vista rápida del inventario conectado a tu Google Sheet.")

            if inv_df.empty:
                st.info("No hay filas en Inventario todavía.")
            else:
                # Lista de productos (cada uno desplegable)
                productos = sorted(inv_df["Producto"].dropna().astype(str).unique().tolist())
                for producto in productos:
                    p_df = inv_df[inv_df["Producto"] == producto].copy()

                    casa_total = int(p_df.get("Stock_Casa", 0).fillna(0).sum())
                    bod_total = int(p_df.get("Stock_Bodega", 0).fillna(0).sum())
                    total = casa_total + bod_total

                    with st.expander(f"{producto}   ·   Stock Total: {total}", expanded=False):
                        chips = st.columns(2)
                        chips[0].markdown(f"**🏠 {fmt_bodega('Casa')}:** {casa_total}")
                        chips[1].markdown(f"**🏭 {fmt_bodega('Bodega')}:** {bod_total}")

                        # Colores: si hay más de 1 color y no es solo Standard
                        colors = (
                            p_df.get("Color", pd.Series([], dtype=str))
                            .fillna("Standard")
                            .astype(str)
                            .str.strip()
                            .unique()
                            .tolist()
                        )
                        colors = [c for c in colors if c and c.lower() != "nan"]
                        has_real_colors = any(c.lower() != "standard" for c in colors)

                        selected_color = None
                        show_df = p_df

                        if has_real_colors:
                            st.markdown("**Color:**")
                            # Ordena para mostrar Standard al final si apareciera
                            colors_sorted = sorted(colors, key=lambda x: (x.lower() == "standard", x))
                            selected_color = st.radio(
                                label="Color",
                                options=colors_sorted,
                                horizontal=True,
                                label_visibility="collapsed",
                                key=f"inv_color_{producto}",
                            )
                            show_df = p_df[p_df["Color"].fillna("Standard").astype(str).str.strip() == selected_color].copy()

                        # Tallas
                        sizes = (
                            show_df.get("Talla", pd.Series([], dtype=str))
                            .fillna("OS")
                            .astype(str)
                            .str.strip()
                            .unique()
                            .tolist()
                        )
                        sizes = [s for s in sizes if s and s.lower() != "nan"]

                        # Si solo existe OS, lo tratamos como “sin tallas”
                        has_sizes = not (len(sizes) == 1 and sizes[0].upper() == "OS")

                        if not has_sizes:
                            # No hay tallas (solo OS) -> mostramos barras por bodega igual que en el resto
                            st.markdown("**Stock (OS):**")
                            casa = int(show_df.get("Stock_Casa", 0).fillna(0).sum())
                            bod = int(show_df.get("Stock_Bodega", 0).fillna(0).sum())
                            mx = max(casa, bod, 1)
                            c1, c2 = st.columns(2)
                            with c1:
                                st.write(f"🏠 **{bodega1_nombre}:** {casa} u.")
                                st.progress(int((casa / mx) * 100))
                            with c2:
                                st.write(f"🏭 **{bodega2_nombre}:** {bod} u.")
                                st.progress(int((bod / mx) * 100))
                        else:
                            st.markdown("**Stock por talla:**")
                            sizes_sorted = sorted(sizes, key=size_sort_key)

                            for talla in sizes_sorted:
                                row = show_df[show_df["Talla"].fillna("OS").astype(str).str.strip().str.upper() == str(talla).upper()]
                                casa = int(row.get("Stock_Casa", 0).fillna(0).sum())
                                bod = int(row.get("Stock_Bodega", 0).fillna(0).sum())
                                # Barra simple (normaliza al máximo de ambos para esa talla)
                                mx = max(casa, bod, 1)

                                st.markdown(f"**Talla {talla}**")
                                c1, c2 = st.columns(2)
                                with c1:
                                    st.caption(f"🏠 {fmt_bodega('Casa')}: {casa} u.")
                                    st.progress(int((casa / mx) * 100))
                                with c2:
                                    st.caption(f"🏭 {fmt_bodega('Bodega')}: {bod} u.")
                                    st.progress(int((bod / mx) * 100))


        st.divider()

        # -----------------------------
        # Sección 2: Transferir stock (plegable) (misma lógica, solo UI)
        # -----------------------------
    elif sub == "Transferir":
        with st.expander("Transferir stock (Casa ↔ Bodega)", expanded=False):
            st.caption("Esto NO registra una venta. Solo mueve unidades entre bodegas.")
            inv_latest = load_inventario(conn, ttl_s=45)
            if "Activo" in inv_latest.columns:
                inv_latest = inv_latest[inv_latest["Activo"].fillna(True) == True].copy()

            if inv_latest.empty:
                st.warning("No hay SKUs en Inventario.")
            else:
                # SKU selector con etiqueta bonita
                inv_latest["__label"] = (
                    inv_latest["SKU"].astype(str)
                    + " · "
                    + inv_latest["Producto"].astype(str)
                    + " · "
                    + inv_latest["Color"].fillna("Standard").astype(str)
                    + " · "
                    + inv_latest["Talla"].fillna("OS").astype(str)
                )

                sku_options = inv_latest["__label"].tolist()
                label_sel = st.selectbox("SKU a mover", sku_options, key="transfer_sku_label")

                sel_row = inv_latest[inv_latest["__label"] == label_sel].iloc[0]
                sku = str(sel_row["SKU"])

                casa_stock = int(sel_row.get("Stock_Casa", 0) or 0)
                bod_stock = int(sel_row.get("Stock_Bodega", 0) or 0)

                st.caption(f"Stock {fmt_bodega('Casa')}: {casa_stock} · Stock {fmt_bodega('Bodega')}: {bod_stock}")

                direction = st.radio(
                    "Dirección",
                    options=[
                        f"{fmt_bodega('Casa')} ➜ {fmt_bodega('Bodega')}",
                        f"{fmt_bodega('Bodega')} ➜ {fmt_bodega('Casa')}",
                    ],
                    horizontal=True,
                    key="transfer_dir",
                )

                qty = st.number_input("Cantidad a mover", min_value=1, step=1, value=1, key="transfer_qty")

                def _can_move() -> tuple[bool, str]:
                    if direction.startswith(fmt_bodega("Casa")):
                        if qty > casa_stock:
                            return False, f"No hay suficiente stock en {fmt_bodega('Casa')}."
                    else:
                        if qty > bod_stock:
                            return False, f"No hay suficiente stock en {fmt_bodega('Bodega')}."
                    return True, ""

                ok, msg = _can_move()
                if not ok:
                    st.error(msg)

                if st.button("✅ Transferir", use_container_width=True, disabled=not ok):
                    # Forzamos lectura fresca SOLO en este momento (sin poner ttl=0 siempre)
                    st.cache_data.clear()
                    inv_fresh = load_inventario(conn, ttl_s=45)
                    if "Activo" in inv_fresh.columns:
                        inv_fresh = inv_fresh[inv_fresh["Activo"].fillna(True) == True].copy()

                    idx = inv_fresh.index[inv_fresh["SKU"].astype(str) == sku]
                    if idx.empty:
                        st.error("SKU no encontrado en Inventario (refrescá e intentá otra vez).")
                        st.stop()

                    i0 = idx[0]
                    if direction.startswith(fmt_bodega("Casa")):
                        inv_fresh.at[i0, "Stock_Casa"] = int(inv_fresh.at[i0, "Stock_Casa"] or 0) - int(qty)
                        inv_fresh.at[i0, "Stock_Bodega"] = int(inv_fresh.at[i0, "Stock_Bodega"] or 0) + int(qty)
                    else:
                        inv_fresh.at[i0, "Stock_Bodega"] = int(inv_fresh.at[i0, "Stock_Bodega"] or 0) - int(qty)
                        inv_fresh.at[i0, "Stock_Casa"] = int(inv_fresh.at[i0, "Stock_Casa"] or 0) + int(qty)

                    save_sheet(conn, SHEET_INVENTARIO, inv_fresh)

                    st.success("Transferencia realizada.")
                    st.cache_data.clear()
                    st.rerun()

        st.divider()

            # -----------------------------
        # Sección 3: Ingreso de producto (nuevo)
        # -----------------------------
    else:
        with st.expander("Ingreso de producto", expanded=False):
            st.caption(
                "Crea un producto nuevo y lo registra en tu hoja de Inventario. "
                "Importante: **NO** se escribe nada en Google Sheets hasta que presionés **Guardar producto**."
            )

            # -------------------------------------------------
            # Estado interno (para que NO se borre lo escrito)
            # -------------------------------------------------
            def _np_init_state() -> None:
                ss = st.session_state
                ss.setdefault("np_stage", "define")  # define | stock
                ss.setdefault("np_tiene_tallas", True)
                ss.setdefault("np_tiene_colores", True)

                ss.setdefault("np_nombre", "")
                ss.setdefault("np_drop_sel", "")
                ss.setdefault("np_add_drop", False)
                ss.setdefault("np_new_drop", "")
                ss.setdefault("np_new_drop_code", "")

                ss.setdefault("np_costo", 0.0)
                ss.setdefault("np_precio", 0.0)
                ss.setdefault("np_almacen", "Casa")  # interno: Casa/Bodega

                ss.setdefault("np_prod_code", "")
                ss.setdefault("np_allow_stock0", False)

                ss.setdefault("np_colores_sel", ["Standard"])
                ss.setdefault("np_tallas_sel", ["S", "M", "L", "XL"])

                ss.setdefault("np_variants", {"colores": ["Standard"], "tallas": ["OS"]})

            def _np_clear_stock_keys() -> None:
                # Elimina inputs dinámicos de stock para que no queden residuos entre combinaciones.
                kill = [k for k in st.session_state.keys() if str(k).startswith("np_stock_")]
                for k in kill:
                    try:
                        del st.session_state[k]
                    except Exception:
                        pass

            def _np_unlock_variants() -> None:
                # Volver a editar (NO toca nombre/costo/precio/drop/almacen)
                st.session_state["np_stage"] = "define"
                _np_clear_stock_keys()

            def _np_lock_variants() -> None:
                # Congela la selección de tallas/colores y abre la sección de stock (sin borrar lo escrito)
                tiene_tallas = bool(st.session_state.get("np_tiene_tallas", True))
                tiene_colores = bool(st.session_state.get("np_tiene_colores", True))

                tallas = st.session_state.get("np_tallas_sel", []) or []
                colores = st.session_state.get("np_colores_sel", []) or []

                if not tiene_tallas:
                    tallas = ["OS"]
                else:
                    tallas = [str(s).strip().upper() for s in tallas if str(s).strip()]
                    if not tallas:
                        tallas = ["S"]

                if not tiene_colores:
                    colores = ["Standard"]
                else:
                    colores = [str(c).strip() for c in colores if str(c).strip()]
                    if not colores:
                        colores = ["Standard"]

                st.session_state["np_variants"] = {"colores": colores, "tallas": tallas}
                st.session_state["np_stage"] = "stock"
                _np_clear_stock_keys()

            def _np_reset_all() -> None:
                # Limpia TODO el flujo de ingreso
                keys = [
                    "np_stage",
                    "np_tiene_tallas",
                    "np_tiene_colores",
                    "np_nombre",
                    "np_drop_sel",
                    "np_add_drop",
                    "np_new_drop",
                    "np_new_drop_code",
                    "np_costo",
                    "np_precio",
                    "np_almacen",
                    "np_prod_code",
                    "np_allow_stock0",
                    "np_colores_sel",
                    "np_tallas_sel",
                    "np_variants",
                ]
                for k in keys:
                    if k in st.session_state:
                        del st.session_state[k]
                _np_clear_stock_keys()
                _np_init_state()

            _np_init_state()

            stage = str(st.session_state.get("np_stage", "define"))
            locked = stage == "stock"

            # -------------------------------------------------
            # Catálogos (cacheado con TTL en conn.read)
            # -------------------------------------------------
            cat_df = load_catalogos(conn, ttl_s=600)
            cat = parse_catalogos(cat_df)
            drops = cat.get("drops", [])
            colores_cat = cat.get("colores", [])

            drop_vals = [d.get("valor", "") for d in drops if str(d.get("valor", "")).strip()] or []
            color_vals = [c.get("valor", "") for c in colores_cat if str(c.get("valor", "")).strip()] or []

            # Mapas de códigos (para SKU)
            color_to_code = {c.get("valor", ""): c.get("codigo", "") for c in colores_cat}
            color_to_code.setdefault("Standard", "STD")
            color_to_code.setdefault("STANDARD", "STD")

            # Si no hay drops en catálogo, igual dejamos un fallback
            if not drop_vals:
                drop_vals = ["(sin drops en Catalogos)"]

            # Asegura que el selectbox no quede en un valor inválido
            if st.session_state.get("np_drop_sel") not in drop_vals:
                st.session_state["np_drop_sel"] = drop_vals[0]

            # Autollenado del código producto (solo si está vacío)
            if not str(st.session_state.get("np_prod_code", "")).strip() and str(st.session_state.get("np_nombre", "")).strip():
                st.session_state["np_prod_code"] = suggest_product_code(str(st.session_state.get("np_nombre", "")))

            # -------------------------------------------------
            # UI: switches de variantes (estos son los únicos que "cambian" la vista)
            # -------------------------------------------------
            sw1, sw2 = st.columns(2)
            with sw1:
                st.toggle(
                    "Tiene tallas",
                    key="np_tiene_tallas",
                    disabled=locked,
                    on_change=_np_unlock_variants,
                )
            with sw2:
                st.toggle(
                    "Tiene variante de color",
                    key="np_tiene_colores",
                    disabled=locked,
                    on_change=_np_unlock_variants,
                )

            # -------------------------------------------------
            # UI: datos base (SIEMPRE visibles, solo se deshabilitan cuando las variantes están aplicadas)
            # -------------------------------------------------
            with st.container():
                st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

                st.text_input("Nombre del producto", key="np_nombre", disabled=locked, on_change=_np_unlock_variants)

                # Drop (solo lectura visual; no hace writes hasta Guardar)
                st.selectbox("Drop", options=drop_vals, key="np_drop_sel", disabled=locked, on_change=_np_unlock_variants)

                with st.expander("Agregar drop nuevo (opcional)", expanded=False):
                    st.checkbox("Agregar drop nuevo", key="np_add_drop", disabled=locked)
                    if st.session_state.get("np_add_drop", False):
                        st.text_input("Nuevo drop (ej: D005)", key="np_new_drop", disabled=locked)
                        st.text_input("Código drop (si no, igual al valor)", key="np_new_drop_code", disabled=locked)

                c1, c2 = st.columns(2)
                with c1:
                    st.number_input(
                        "Costo del producto ($)",
                        min_value=0.0,
                        step=0.50,
                        format="%.2f",
                        key="np_costo",
                        disabled=locked,
                        on_change=_np_unlock_variants,
                    )
                with c2:
                    st.number_input(
                        "Precio de venta ($)",
                        min_value=0.0,
                        step=0.50,
                        format="%.2f",
                        key="np_precio",
                        disabled=locked,
                        on_change=_np_unlock_variants,
                    )

                st.radio(
                    "Almacén inicial",
                    options=["Casa", "Bodega"],
                    horizontal=True,
                    key="np_almacen",
                    format_func=fmt_bodega,
                    disabled=locked,
                    on_change=_np_unlock_variants,
                )

                # Código producto (3 letras)
                st.text_input(
                    "Código producto (3 letras) (auto sugerido)",
                    key="np_prod_code",
                    disabled=locked,
                    help="Se usa como 2do segmento del SKU: DROP-PROD-COLOR-TALLA",
                    on_change=_np_unlock_variants,
                )

                st.toggle("Permitir guardar con stock 0", key="np_allow_stock0", disabled=locked)


            # -------------------------------------------------
            # UI: selección de variantes (solo si NO está bloqueado)
            # -------------------------------------------------
            tiene_tallas = bool(st.session_state.get("np_tiene_tallas", True))
            tiene_colores = bool(st.session_state.get("np_tiene_colores", True))

            if not locked:
                if tiene_tallas:
                    all_sizes = ["XS", "S", "M", "L", "XL", "XXL", "XXXL", "OS"]
                    default_sizes = ["S", "M", "L", "XL"]
                    # ⚠️ Streamlit: este widget ya está controlado por `key=`.
                    # Si también pasamos `default=`, Streamlit muestra el warning:
                    # "created with a default value but also had its value set via Session State".
                    # Por eso, dejamos que el valor venga SOLO de `st.session_state`.
                    st.multiselect(
                        "Tallas",
                        options=all_sizes,
                        key="np_tallas_sel",
                    )
                else:
                    st.session_state["np_tallas_sel"] = ["OS"]

                if tiene_colores:
                    if not color_vals:
                        st.info("No hay colores en Catalogos. Se usará 'Standard'.")
                        st.session_state["np_colores_sel"] = ["Standard"]
                    else:
                        st.multiselect(
                            "Colores",
                            options=color_vals,
                            key="np_colores_sel",
                        )
                else:
                    st.session_state["np_colores_sel"] = ["Standard"]

                # Botones de acción (sin escribir nada)
                b1, b2 = st.columns(2)
                with b1:
                    if st.button("✅ Aplicar variantes", use_container_width=True):
                        _np_lock_variants()
                        st.rerun()
                with b2:
                    if st.button("🧹 Limpiar formulario", use_container_width=True):
                        _np_reset_all()
                        st.rerun()

            # -------------------------------------------------
            # UI: stock por variante (cuando ya aplicaste variantes)
            # -------------------------------------------------
            if locked:
                v = st.session_state.get("np_variants", {}) or {}
                v_colors = [str(x) for x in (v.get("colores") or ["Standard"]) if str(x).strip()]
                v_sizes = [str(x).upper() for x in (v.get("tallas") or ["OS"]) if str(x).strip()]

                st.markdown(
                    f"**Variantes aplicadas:** {len(v_colors)} color(es) × {len(v_sizes)} talla(s) = **{len(v_colors)*len(v_sizes)} SKU(s)**"
                )

                top_l, top_r = st.columns([1, 1])
                with top_l:
                    if st.button("↩️ Editar variantes", use_container_width=True):
                        _np_unlock_variants()
                        st.rerun()
                with top_r:
                    if st.button("🧹 Limpiar formulario", use_container_width=True):
                        _np_reset_all()
                        st.rerun()

                st.markdown("## Stock inicial (unidades)")

                # Inputs dinámicos por color x talla (sin forms para que no se pierda nada)
                total_units = 0
                stock_map: dict[tuple[str, str], int] = {}

                def _stk_key(color: str, talla: str) -> str:
                    # key estable y segura
                    c = re.sub(r"[^A-Za-z0-9]", "", str(color)).upper()[:12] or "STD"
                    t = re.sub(r"[^A-Za-z0-9]", "", str(talla)).upper()[:6] or "OS"
                    return f"np_stock_{c}_{t}"

                # Render
                for color in v_colors:
                    st.markdown(f"**Color:** {color}")
                    cols = st.columns(len(v_sizes)) if len(v_sizes) <= 5 else None

                    row_vals = []
                    for j, talla in enumerate(v_sizes):
                        key = _stk_key(color, talla)
                        if cols is None:
                            val = int(st.number_input(f"{talla}", min_value=0, step=1, value=0, key=key))
                        else:
                            with cols[j]:
                                val = int(st.number_input(f"{talla}", min_value=0, step=1, value=0, key=key))
                        stock_map[(color, talla)] = val
                        row_vals.append(val)

                    subtotal = int(sum(row_vals))
                    total_units += subtotal
                    st.caption(f"Total {color}: {subtotal} u.")
                    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

                st.caption(f"**Total de unidades:** {int(total_units)}")

                # Guardar (único momento donde se escribe en Sheets)
                can_save = True
                errors: list[str] = []

                nombre = str(st.session_state.get("np_nombre", "")).strip()
                if not nombre:
                    can_save = False
                    errors.append("Escribí el Nombre del producto.")

                if not st.session_state.get("np_allow_stock0", False) and int(total_units) <= 0:
                    can_save = False
                    errors.append("El stock total es 0 (activá 'Permitir guardar con stock 0' si querés igual).")

                if errors:
                    st.error("\n".join(errors))

                if st.button("💾 Guardar producto", use_container_width=True, disabled=not can_save):
                    # -----------------------------
                    # Guardado real (con pocas lecturas y cache)
                    # -----------------------------
                    try:
                        # 1) (Opcional) agregar drop a Catalogos
                        if bool(st.session_state.get("np_add_drop", False)) and str(st.session_state.get("np_new_drop", "")).strip():
                            nd = str(st.session_state.get("np_new_drop", "")).strip().upper()
                            nd_code = str(st.session_state.get("np_new_drop_code", "")).strip().upper() or nd

                            cat_write = load_catalogos(conn, ttl_s=600).copy()
                            cat_write.columns = [str(c).strip() for c in cat_write.columns]
                            if "Catalogo" in cat_write.columns:
                                cat_write["Catalogo"] = cat_write["Catalogo"].ffill()

                            already = (
                                (cat_write.get("Catalogo", "").astype(str).str.upper() == "DROP")
                                & (cat_write.get("Valor", "").astype(str).str.upper() == nd)
                            )
                            if not already.any():
                                new_row = {"Catalogo": "DROP", "Valor": nd, "Codigo": nd_code}
                                cat_write = pd.concat([cat_write, pd.DataFrame([new_row])], ignore_index=True)
                                save_sheet(conn, SHEET_CATALOGOS, cat_write)

                        # 2) Determina códigos (drop/product/color)
                        drop_sel = str(st.session_state.get("np_drop_sel", "")).strip()
                        drop_code = None
                        for d in drops:
                            if str(d.get("valor", "")).strip() == drop_sel:
                                drop_code = str(d.get("codigo", "")).strip()
                                break
                        if not drop_code or str(drop_code).lower() == "nan":
                            drop_code = drop_sel.strip().upper()

                        raw_pc = str(st.session_state.get("np_prod_code", "")).strip()
                        raw_pc = re.sub(r"[^A-Za-z0-9]", "", raw_pc).upper()[:3]
                        if not raw_pc:
                            raw_pc = "PRD"
                        if len(raw_pc) < 3:
                            raw_pc = (raw_pc + "XXX")[:3]
                        prod_code = raw_pc
                        if len(prod_code) < 3:
                            prod_code = (prod_code + "XXX")[:3]

                        costo = float(st.session_state.get("np_costo", 0.0) or 0.0)
                        precio = float(st.session_state.get("np_precio", 0.0) or 0.0)

                        almacen = str(st.session_state.get("np_almacen", "Casa"))

                        # 3) Respeta código existente si el producto ya existe exacto
                        existing_code = get_existing_product_code(inv_df, nombre)
                        if existing_code:
                            prod_code = str(existing_code).strip().upper()[:3]

                        # 4) Construye filas nuevas
                        inv_now = load_inventario(conn, ttl_s=45).copy()
                        existing_skus = set(inv_now["SKU"].astype(str).str.strip().tolist())

                        rows = []
                        for col in v_colors:
                            col_label = str(col).strip() if tiene_colores else "Standard"
                            col_code = color_to_code.get(col_label) or color_to_code.get(col_label.title())
                            if not col_code:
                                col_code = re.sub(r"\s+", "", col_label).upper()[:3] or "STD"

                            for talla in v_sizes:
                                talla_label = str(talla).strip().upper() if tiene_tallas else "OS"
                                sku = build_sku(drop_code, prod_code, col_code, talla_label)

                                qty = int(stock_map.get((col, talla), 0) or 0)
                                stock_casa = qty if almacen == "Casa" else 0
                                stock_bod = qty if almacen == "Bodega" else 0

                                rows.append(
                                    {
                                        "SKU": sku,
                                        "Drop": drop_code,
                                        "Producto": nombre,
                                        "Color": col_label,
                                        "Talla": talla_label,
                                        "Stock_Casa": stock_casa,
                                        "Stock_Bodega": stock_bod,
                                        "Costo_Unitario": float(costo),
                                        "Precio_Lista": float(precio),
                                        "Activo": True,
                                    }
                                )

                        new_skus = [r["SKU"] for r in rows]
                        ok_unique, dups = ensure_unique_skus(new_skus, existing_skus)
                        if not ok_unique:
                            st.error("Estos SKUs ya existen en Inventario: " + ", ".join(dups))
                            st.stop()

                        # 5) Append y guardar
                        inv_out = inv_now.copy()
                        for col in INV_REQUIRED:
                            if col not in inv_out.columns:
                                inv_out[col] = None

                        inv_out = pd.concat([inv_out, pd.DataFrame(rows)], ignore_index=True)
                        save_sheet(conn, SHEET_INVENTARIO, inv_out)

                        st.success(f"Producto creado: {nombre} ({len(rows)} SKU(s))")

                        # Limpia cache SOLO al escribir
                        st.cache_data.clear()
                        _np_reset_all()
                        st.rerun()

                    except Exception as e:
                        st.error("Error al guardar el producto.")
                        st.exception(e)
        # -----------------------------
        # TAB: Finanzas (Nivel 1 · 2 · 3)
        # -----------------------------


def render_ventas_screen(conn: GSheetsConnection, inv_df_full: pd.DataFrame, cfg: dict[str, Any], APP_TZ: ZoneInfo) -> None:
    render_app_header("🧾 Ventas")
    sub = st.radio(
        "Sección",
        ["Ventas", "Egresos"],
        horizontal=True,
        key="ventas_sub",
        label_visibility="collapsed",
    )

    if sub == "Ventas":
        inv_df = inv_df_full

        if inv_df is None or inv_df.empty:
            st.warning("No pude cargar el Inventario desde Google Sheets (si viste 429, esperá 60–90s).")
            st.stop()

        inv_activo = inv_df[inv_df["Activo"] == True].copy()
        if inv_activo.empty and len(inv_df) > 0:
            with card():
                st.warning("Tu inventario tiene filas, pero el filtro 'Activo' quedó en 0. Permito ventas usando TODOS los SKUs para no bloquearte.")
            inv_activo = inv_df.copy()

        if inv_activo.empty:
            st.warning("Tu Inventario está vacío o todo está inactivo.")
            st.stop()

        # Bodega única por venta
        with card():
            st.markdown("**Bodega de salida (toda la venta)**")
            bodega_venta = st.radio(
                "Bodega",
                ["Casa", "Bodega"],
                horizontal=True,
                key="bodega_venta",
                format_func=fmt_bodega,
            )

            cart_now = cast(list[dict[str, Any]], st.session_state["cart"])
            if cart_now:
                st.caption(f"Carrito actual tiene {len(cart_now)} línea(s). (Bodega actual: {fmt_bodega(bodega_venta)})")

        # Agregar línea al carrito
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
            stock_disp = stock_casa if bodega_venta == "Casa" else stock_bodega

            if stock_disp <= 0:
                st.error(f"❌ AGOTADO en {fmt_bodega(bodega_venta)}.")
            elif stock_disp <= 2:
                st.warning(f"⚠️ Pocas unidades en {fmt_bodega(bodega_venta)}.")

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
                f"Bodega: <span class='pill'><b>{fmt_bodega(bodega_venta)}</b></span> · Subtotal: <b>{money(subtotal_linea)}</b></div>",
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
                        "Bodega_Salida": bodega_venta,  # interno
                        "Cantidad": int(qty),
                        "Precio_Unitario": float(precio_unit),
                        "Descuento_Unitario": float(desc_u),
                        "Subtotal_Linea": float(subtotal_linea),
                    }
                )
                st.session_state["cart"] = cart
                st.success("Agregado al carrito.")

        # Mostrar carrito + remover
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
                            f"SKU: `{item['SKU']}` · Bodega: **{fmt_bodega(str(item['Bodega_Salida']))}**"
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

        # Datos de venta (cabecera)
        with card():
            st.markdown("**Datos de venta**")
            cliente = st.text_input("Cliente", placeholder="Nombre del cliente", key="cliente")
            notas = st.text_area("Notas (opcional)", placeholder="Ej: entregar hoy, referencia, etc.", key="notas")

            metodo_pago = st.selectbox(
                "Método de pago",
                options=["Transferencia", "Efectivo", "Tarjeta", "Contra Entrega"],
                key="metodo_pago",
            )

            # ✅ FIX warning: no pasar value= si ya usas key y session_state
            envio_cliente = st.number_input(
                "Envío cobrado al cliente ($)",
                min_value=0.0,
                step=0.50,
                format="%.2f",
                key="envio_cliente",
            )
            costo_courier = st.number_input(
                "Costo real courier ($)",
                min_value=0.0,
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
                        step=0.10,
                        format="%.2f",
                        key="pce_otro",
                    )
                    override_pce = float(p) / 100.0
                else:
                    override_pce = None

        # Totales
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

        # Guardar venta
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
                # Lecturas FRESCAS solo aquí (acción)
                latest_inv = load_inventario(conn, ttl_s=0)

                col_stock = "Stock_Casa" if bodega_venta == "Casa" else "Stock_Bodega"
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
                            f"Stock insuficiente para {sku_i} en {fmt_bodega(bodega_venta)}. Disponible={available}, Pedido={qty_i}"
                        )

                cab_df = load_cabecera(conn, ttl_s=0)
                det_df = load_detalle(conn, ttl_s=0)

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

                det_rows: list[dict[str, Any]] = []
                bodega_label = fmt_bodega(bodega_venta)  # guardamos nombre visible en el sheet
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
                            "Bodega_Salida": bodega_label,
                            "Cantidad": int(item["Cantidad"]),
                            "Precio_Unitario": float(item["Precio_Unitario"]),
                            "Descuento_Unitario": float(item["Descuento_Unitario"]),
                            "Subtotal_Linea": float(item["Subtotal_Linea"]),
                        }
                    )

                # 1) Cabecera
                cab_df = _align_required_columns(cab_df, CAB_REQUIRED)
                cab_out = pd.concat([cab_df, pd.DataFrame([cab_row])], ignore_index=True)
                cab_out = _align_required_columns(cab_out, CAB_REQUIRED)
                save_sheet(conn, SHEET_VENTAS_CAB, cab_out)

                # 2) Detalle
                det_df = _align_required_columns(det_df, DET_REQUIRED)
                det_out = pd.concat([det_df, pd.DataFrame(det_rows)], ignore_index=True)
                det_out = _align_required_columns(det_out, DET_REQUIRED)
                save_sheet(conn, SHEET_VENTAS_DET, det_out)

                # 3) Descontar stock
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

                st.success(f"✅ Venta registrada: {venta_id}")

                # ✅ FIX reset sin tocar session_state después del widget
                st.cache_data.clear()
                st.session_state["_reset_sale_pending"] = True
                st.rerun()

            except Exception as e:
                st.error("Error al registrar la venta.")
                st.exception(e)
    else:
        # -----------------------------
        # EGRESOS (nuevo)
        # -----------------------------
        with card():
            st.markdown("**Registrar egreso**")
            eg_df = load_egresos(conn, ttl_s=60)

            now = datetime.now(APP_TZ)
            default_date = now.date()

            with st.form("egreso_form", clear_on_submit=True):
                concepto = st.text_input("Concepto", value="")
                categoria = st.text_input("Categoría", value="")
                monto = st.number_input("Monto ($)", min_value=0.0, step=0.50, format="%.2f")
                fecha = st.date_input("Fecha", value=default_date)
                drop = st.text_input("Drop (opcional)", value="")
                notas = st.text_area("Notas (opcional)", value="")

                submit = st.form_submit_button("💾 Guardar egreso", use_container_width=True)

            if submit:
                concepto_s = str(concepto).strip()
                categoria_s = str(categoria).strip()
                if not concepto_s or not categoria_s or float(monto) <= 0:
                    st.error("Completa Concepto, Categoría y un Monto mayor a 0.")
                else:
                    year = int(fecha.year)
                    eg_id = next_egreso_id(eg_df, year)

                    new_row = {
                        "Egreso_ID": eg_id,
                        "Fecha": fecha.strftime("%d/%m/%Y"),
                        "Concepto": concepto_s,
                        "Categoria": categoria_s,
                        "Monto": float(monto),
                        "Notas": str(notas).strip(),
                        "Drop": str(drop).strip(),
                    }

                    out = eg_df.copy()
                    for col in EGRESOS_REQUIRED:
                        if col not in out.columns:
                            out[col] = ""

                    out = pd.concat([out, pd.DataFrame([new_row])], ignore_index=True)
                    save_sheet(conn, SHEET_EGRESOS, out)
                    st.success(f"Egreso guardado: {eg_id}")
                    st.cache_data.clear()
                    st.rerun()

        with card():
            st.markdown("**Últimos movimientos (Egresos)**")
            eg_df = load_egresos(conn, ttl_s=60)
            if eg_df.empty:
                st.info("Aún no hay egresos.")
            else:
                eg_df["_Fecha_dt"] = pd.to_datetime(eg_df["Fecha"], errors="coerce", dayfirst=True)
                show = eg_df.sort_values("_Fecha_dt", ascending=False).head(25).copy()
                show["Monto"] = pd.to_numeric(show["Monto"], errors="coerce").fillna(0.0)
                for _, r in show.iterrows():
                    with st.expander(f"{r.get('Fecha','')} · {r.get('Categoria','')} · {money(float(r.get('Monto',0)))}", expanded=False):
                        st.markdown(f"**Concepto:** {r.get('Concepto','')}")
                        if str(r.get("Drop","")).strip():
                            st.caption(f"Drop: {r.get('Drop','')}")
                        if str(r.get("Notas","")).strip():
                            st.caption(str(r.get("Notas","")))


def render_finanzas_screen(conn: GSheetsConnection, inv_df_full: pd.DataFrame) -> None:
    render_app_header("📈 Finanzas")
    # Carga de datos (solo lectura)
    cab_df = load_cabecera(conn, ttl_s=60)
    det_df = load_detalle(conn, ttl_s=60)
    inv_df = inv_df_full.copy()
    invst_df = load_inversiones(conn, ttl_s=180)

    # Normalizaciones
    if not cab_df.empty:
        cab_df["_Fecha_dt"] = pd.to_datetime(cab_df["Fecha"], errors="coerce", dayfirst=True)
    else:
        cab_df["_Fecha_dt"] = pd.NaT

    if not det_df.empty:
        det_df["Subtotal_Linea"] = pd.to_numeric(det_df["Subtotal_Linea"], errors="coerce").fillna(0.0)
        det_df["Cantidad"] = pd.to_numeric(det_df["Cantidad"], errors="coerce").fillna(0).astype(int)
    else:
        det_df["Subtotal_Linea"] = 0.0
        det_df["Cantidad"] = 0

    # Merge de costos unitarios (por SKU)
    sku_cost = (
        inv_df[["SKU", "Costo_Unitario"]].copy()
        if (not inv_df.empty and "SKU" in inv_df.columns)
        else pd.DataFrame(columns=["SKU", "Costo_Unitario"])
    )
    if not sku_cost.empty:
        sku_cost["SKU"] = sku_cost["SKU"].astype(str).str.strip()
        sku_cost["Costo_Unitario"] = pd.to_numeric(sku_cost["Costo_Unitario"], errors="coerce").fillna(0.0)

    # Base de líneas enriquecida
    lines = det_df.merge(sku_cost, on="SKU", how="left")
    lines["Costo_Unitario"] = pd.to_numeric(lines.get("Costo_Unitario", 0.0), errors="coerce").fillna(0.0)
    lines["COGS_Linea"] = (lines["Costo_Unitario"] * lines["Cantidad"]).round(2)

    # Totales por venta (para asignar Monto_A_Recibir por línea)
    sale_line_tot = (
        lines.groupby("Venta_ID", as_index=False)["Subtotal_Linea"]
        .sum()
        .rename(columns={"Subtotal_Linea": "_Venta_Subtotal_Lineas"})
    )

    cab = cab_df[["Venta_ID", "Total_Cobrado", "Monto_A_Recibir", "Costo_Logistica_Total", "Comision_Monto", "_Fecha_dt"]].copy()
    cab["Total_Cobrado"] = pd.to_numeric(cab["Total_Cobrado"], errors="coerce").fillna(0.0)
    cab["Monto_A_Recibir"] = pd.to_numeric(cab["Monto_A_Recibir"], errors="coerce").fillna(0.0)
    cab["Costo_Logistica_Total"] = pd.to_numeric(cab["Costo_Logistica_Total"], errors="coerce").fillna(0.0)
    cab["Comision_Monto"] = pd.to_numeric(cab["Comision_Monto"], errors="coerce").fillna(0.0)

    lines = lines.merge(sale_line_tot, on="Venta_ID", how="left").merge(cab, on="Venta_ID", how="left")
    lines["_Venta_Subtotal_Lineas"] = pd.to_numeric(lines["_Venta_Subtotal_Lineas"], errors="coerce").fillna(0.0)
    lines["_Share"] = 0.0
    nz = lines["_Venta_Subtotal_Lineas"] > 0
    lines.loc[nz, "_Share"] = (lines.loc[nz, "Subtotal_Linea"] / lines.loc[nz, "_Venta_Subtotal_Lineas"]).fillna(0.0)

    lines["_Monto_Asignado"] = (lines["_Share"] * pd.to_numeric(lines["Monto_A_Recibir"], errors="coerce").fillna(0.0)).round(2)
    lines["_Cobrado_Asignado"] = (lines["_Share"] * pd.to_numeric(lines["Total_Cobrado"], errors="coerce").fillna(0.0)).round(2)
    lines["_Ganancia_Neta_Linea"] = (lines["_Monto_Asignado"] - lines["COGS_Linea"]).round(2)

    # -----------------------------------
    # Filtros (Todo / Por Drop / Este mes)
    # -----------------------------------
    # Drops disponibles
    drops_in_data = sorted(
        [d for d in lines.get("Drop", pd.Series(dtype=str)).dropna().astype(str).str.strip().unique().tolist() if d]
    )
    # fallback: drops desde inventario
    if not drops_in_data and (not inv_df.empty):
        drops_in_data = sorted([d for d in inv_df["Drop"].dropna().astype(str).str.strip().unique().tolist() if d])

    now = datetime.now(APP_TZ)
    this_month = now.strftime("%Y-%m")

    # Control de filtro (simple y móvil-friendly)
    options = ["Todo"] + [f"Drop {d}" for d in drops_in_data] + ["Este mes"]
    if "fin_filter" not in st.session_state:
        st.session_state.fin_filter = "Todo"

    with card():
        header_cols = st.columns([1, 1])
        with header_cols[0]:
            st.markdown("### Finanzas")
        with header_cols[1]:
            if st.button("🔄 Refrescar", use_container_width=True):
                st.cache_data.clear()
                st.rerun()

        sel = st.radio("Filtro", options, index=options.index(st.session_state.fin_filter) if st.session_state.fin_filter in options else 0, horizontal=True, label_visibility="collapsed")
        st.session_state.fin_filter = sel

        # Determinar subconjunto por fecha
        cab_f = cab_df.copy()
        if not cab_f.empty:
            cab_f["_Fecha_dt"] = pd.to_datetime(cab_f["Fecha"], errors="coerce", dayfirst=True)
        if sel == "Este mes" and not cab_f.empty:
            cab_f = cab_f[cab_f["_Fecha_dt"].dt.strftime("%Y-%m") == this_month].copy()

        # Para líneas usamos el mismo filtro por fecha (vía Venta_ID)
        if sel == "Este mes" and not cab_f.empty:
            vids = set(cab_f["Venta_ID"].astype(str).tolist())
            lines_f = lines[lines["Venta_ID"].astype(str).isin(vids)].copy()
        else:
            lines_f = lines.copy()

        # Si es Drop, filtramos por drop (y trabajamos con asignación proporcional ya calculada)
        active_drop = None
        if sel.startswith("Drop "):
            active_drop = sel.replace("Drop ", "").strip()
            lines_f = lines_f[lines_f["Drop"].astype(str).str.strip() == active_drop].copy()

        # Totales principales
        total_cobrado = float(pd.to_numeric(lines_f["_Cobrado_Asignado"], errors="coerce").fillna(0.0).sum())
        neto_recibido = float(pd.to_numeric(lines_f["_Monto_Asignado"], errors="coerce").fillna(0.0).sum())
        unidades = int(pd.to_numeric(lines_f["Cantidad"], errors="coerce").fillna(0).sum())
        ingreso_productos = float(pd.to_numeric(lines_f["Subtotal_Linea"], errors="coerce").fillna(0.0).sum())
        ganancia_neta = float(pd.to_numeric(lines_f["_Ganancia_Neta_Linea"], errors="coerce").fillna(0.0).sum())

        st.markdown(
            f"<div style='font-size: 40px; font-weight: 800; line-height: 1.0;'>"
            f"{money(total_cobrado)} <span style='font-size: 22px; font-weight: 700; opacity: .85;'>Ventas Totales</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
        mini = st.columns(4)
        mini[0].markdown(f"**Neto recibido:** {money(neto_recibido)}")
        mini[1].markdown(f"**Ingreso productos:** {money(ingreso_productos)}")
        mini[2].markdown(f"**Unidades:** {unidades}")
        mini[3].markdown(f"**Ganancia neta:** {money(ganancia_neta)}")

    # -----------------------------------
    # Nivel 1: Punto de equilibrio global
    # -----------------------------------
    def _inv_amount_for_scope(drop_name: str | None, lines_scope: pd.DataFrame) -> float:
        if invst_df.empty:
            return 0.0

        df = invst_df.copy()
        df["Tipo"] = df["Tipo"].astype(str).str.upper().str.strip()
        df["Referencia"] = df["Referencia"].astype(str).str.strip()
        df["Monto_Invertido"] = pd.to_numeric(df["Monto_Invertido"], errors="coerce").fillna(0.0)

        if drop_name:
            # 1) Drop directo
            m = df[(df["Tipo"] == "DROP") & (df["Referencia"] == drop_name)]
            if not m.empty:
                return float(m["Monto_Invertido"].sum())

            # 2) Suma por producto dentro del drop (si no hay DROP)
            prods = sorted([p for p in lines_scope["Producto"].dropna().astype(str).str.strip().unique().tolist() if p])
            m2 = df[(df["Tipo"] == "PRODUCTO") & (df["Referencia"].isin(prods))]
            return float(m2["Monto_Invertido"].sum())

        # Scope global
        # Preferimos inversiones por DROP si existen
        drops_scope = sorted([d for d in lines_scope["Drop"].dropna().astype(str).str.strip().unique().tolist() if d])
        m_drop = df[(df["Tipo"] == "DROP") & (df["Referencia"].isin(drops_scope))]
        if not m_drop.empty:
            return float(m_drop["Monto_Invertido"].sum())

        # Si no hay drops, sumamos por producto
        prods = sorted([p for p in lines_scope["Producto"].dropna().astype(str).str.strip().unique().tolist() if p])
        m_prod = df[(df["Tipo"] == "PRODUCTO") & (df["Referencia"].isin(prods))]
        return float(m_prod["Monto_Invertido"].sum())

    inv_total = _inv_amount_for_scope(active_drop, lines_f)
    with card():
        title = "Punto de Equilibrio Global"
        if active_drop:
            title += f" ({active_drop})"
        elif sel == "Este mes":
            title += f" ({this_month})"
        st.markdown(f"### {title}")

        if inv_total <= 0:
            st.warning("No hay inversión registrada para este filtro. Agregá montos en la hoja **Inversiones**.")
        else:
            pct = 0 if inv_total <= 0 else max(0.0, min(1.0, neto_recibido / inv_total))
            st.progress(int(round(pct * 100)))
            falta = max(0.0, inv_total - neto_recibido)
            st.caption(f"Has recuperado {money(neto_recibido)} de {money(inv_total)}. Te faltan {money(falta)} para recuperar tu inversión.")

    # -----------------------------------
    # Nivel 1.5: Producto estrella (ganancia neta)
    # -----------------------------------
    with card():
        st.markdown("### PRODUCTO ESTRELLA (Ganancia neta)")
        if lines_f.empty:
            st.info("Aún no hay ventas para mostrar.")
        else:
            star = (
                lines_f.groupby("Producto", as_index=False)["_Ganancia_Neta_Linea"]
                .sum()
                .rename(columns={"_Ganancia_Neta_Linea": "Ganancia_Neta"})
                .sort_values("Ganancia_Neta", ascending=False)
            )
            top = star.head(3).copy()
            cols = st.columns(3)
            medals = ["🥇", "🥈", "🥉"]
            for i in range(3):
                with cols[i]:
                    if i < len(top):
                        r = top.iloc[i]
                        st.markdown(f"**{i+1}. {r['Producto']}**")
                        st.markdown(f"{medals[i]}  **{money(float(r['Ganancia_Neta']))}**")
                    else:
                        st.markdown("—")

    # -----------------------------------
    # Nivel 2: Progreso por producto (recuperación)
    # -----------------------------------
    with card():
        st.markdown("### Progreso por Producto (Recuperación de Inversión)")

        if lines_f.empty:
            st.info("Aún no hay ventas para mostrar.")
        else:
            # Nota: esta sección muestra TODOS los productos con ventas en el filtro actual.
            # Si un producto no tiene inversión asignada (Tipo=PRODUCTO en la hoja Inversiones),
            # se mostrará como "Inversión no definida" en lugar de ocultarse.
            inv_prod = pd.DataFrame(columns=["Tipo", "Referencia", "Monto_Invertido"])
            if not invst_df.empty:
                inv_prod = invst_df.copy()
                inv_prod["Tipo"] = inv_prod["Tipo"].astype(str).str.upper().str.strip()
                inv_prod["Referencia"] = inv_prod["Referencia"].astype(str).str.strip()
                inv_prod["Monto_Invertido"] = pd.to_numeric(inv_prod["Monto_Invertido"], errors="coerce").fillna(0.0)
                inv_prod = inv_prod[inv_prod["Tipo"] == "PRODUCTO"].copy()

                if active_drop:
                    # restringe a productos vendidos en este filtro
                    prods_in_drop = sorted(
                        [
                            p
                            for p in lines_f["Producto"].dropna().astype(str).str.strip().unique().tolist()
                            if p
                        ]
                    )
                    inv_prod = inv_prod[inv_prod["Referencia"].isin(prods_in_drop)].copy()
            else:
                st.warning("No hay inversiones registradas. Hoja: **Inversiones**. Se mostrará progreso sin inversión asignada.")

            # Cálculos por producto (basado en el filtro actual)
            g = lines_f.groupby("Producto", as_index=False).agg(
                Unidades=("Cantidad", "sum"),
                Ingreso=("Subtotal_Linea", "sum"),
                Neto=("_Monto_Asignado", "sum"),
            )

            # merge inversión (si existe)
            if not inv_prod.empty:
                inv_map = inv_prod.groupby("Referencia", as_index=False)["Monto_Invertido"].sum()
                g = g.merge(inv_map, left_on="Producto", right_on="Referencia", how="left")
                g["Monto_Invertido"] = pd.to_numeric(g["Monto_Invertido"], errors="coerce").fillna(0.0)
            else:
                g["Monto_Invertido"] = 0.0

            # precio efectivo promedio y costo unitario promedio
            avg_price = (
                lines_f.groupby("Producto")
                .apply(lambda d: (d["Subtotal_Linea"].sum() / max(1, d["Cantidad"].sum())))
                .rename("Precio_Prom")
                .reset_index()
            )
            avg_cost = (
                lines_f.groupby("Producto")
                .apply(lambda d: (d["COGS_Linea"].sum() / max(1, d["Cantidad"].sum())))
                .rename("Costo_Prom")
                .reset_index()
            )
            g = g.merge(avg_price, on="Producto", how="left").merge(avg_cost, on="Producto", how="left")
            g["Precio_Prom"] = pd.to_numeric(g["Precio_Prom"], errors="coerce").fillna(0.0)
            g["Costo_Prom"] = pd.to_numeric(g["Costo_Prom"], errors="coerce").fillna(0.0)

            # Orden: primero los que tienen inversión (por %), luego los sin inversión (por neto)
            def _pct_rec(row: pd.Series) -> float:
                invv = float(row.get("Monto_Invertido", 0.0) or 0.0)
                neto = float(row.get("Neto", 0.0) or 0.0)
                if invv > 0:
                    return neto / invv
                return -1.0

            g["Pct_Rec"] = g.apply(_pct_rec, axis=1)
            g = g.sort_values(["Pct_Rec", "Neto"], ascending=[False, False])

            missing_inv = int((g["Monto_Invertido"] <= 0).sum())
            if missing_inv > 0:
                st.caption(
                    f"⚠️ {missing_inv} producto(s) no tienen inversión asignada (Tipo=PRODUCTO en **Inversiones**). "
                    "Aún así se muestran para que veas ventas/recuperado."
                )

            for _, r in g.iterrows():
                prod = str(r["Producto"])
                invv = float(r["Monto_Invertido"])
                neto = float(r["Neto"])
                unidades_sold = int(r["Unidades"])
                precio_prom = float(r["Precio_Prom"])
                costo_prom = float(r["Costo_Prom"])

                with st.expander(f"{prod}", expanded=False):
                    if invv > 0:
                        pct = max(0.0, min(1.0, neto / invv))
                        st.progress(int(round(pct * 100)))

                        falta = max(0.0, invv - neto)
                        st.caption(f"Has recuperado {money(neto)} de {money(invv)}. Te faltan {money(falta)}.")

                        # Unidades estimadas para recuperar (basado en neto promedio por unidad)
                        if unidades_sold > 0:
                            neto_unit = neto / max(1, unidades_sold)
                            unidades_target = int((invv / max(0.01, neto_unit)) + 0.999)
                            if unidades_target > 0:
                                st.caption(f"Unidades vendidas: {unidades_sold} de {unidades_target} (estimado).")

                        if pct >= 1.0:
                            util_unit = max(0.0, precio_prom - costo_prom)
                            st.success(
                                f"¡Recuperado! Cada venta ahora aporta aprox. {money(util_unit)} de margen bruto por unidad."
                            )
                    else:
                        # No ocultar el producto: mostrarlo como pendiente de inversión
                        st.progress(0)
                        st.warning("Inversión no definida para este producto.")
                        st.caption(f"Recuperado (neto asignado en el periodo): {money(neto)}.")
                        st.caption(f"Unidades vendidas: {unidades_sold}.")
                        st.caption(
                            "Para activar recuperación, agrega una fila en **Inversiones** con "
                            "**Tipo=PRODUCTO** y **Referencia** exactamente igual al nombre del producto."
                        )

                    st.caption(f"Precio promedio: {money(precio_prom)}  |  Costo promedio: {money(costo_prom)}")


        # -----------------------------------
        # Nivel 3: Producto por producto (finanzas empresa)
        # -----------------------------------
        with card():
            st.markdown("### Producto por producto (Finanzas empresa)")
            if lines_f.empty:
                st.info("Aún no hay ventas para mostrar.")
            else:
                total_profit = float(pd.to_numeric(lines_f["_Ganancia_Neta_Linea"], errors="coerce").fillna(0.0).sum())
                p = lines_f.groupby("Producto", as_index=False).agg(
                    Unidades=("Cantidad", "sum"),
                    Ingreso=("Subtotal_Linea", "sum"),
                    Neto=("_Monto_Asignado", "sum"),
                    COGS=("COGS_Linea", "sum"),
                    Ganancia=("_Ganancia_Neta_Linea", "sum"),
                )

                # arreglar columnas por nombre raro si aplica
                if "Neto" not in p.columns:
                    p["Neto"] = lines_f.groupby("Producto")["_Monto_Asignado"].sum().values
                if "Ganancia" not in p.columns:
                    p["Ganancia"] = lines_f.groupby("Producto")["_Ganancia_Neta_Linea"].sum().values

                p["Ingreso"] = pd.to_numeric(p["Ingreso"], errors="coerce").fillna(0.0)
                p["Neto"] = pd.to_numeric(p["Neto"], errors="coerce").fillna(0.0)
                p["COGS"] = pd.to_numeric(p["COGS"], errors="coerce").fillna(0.0)
                p["Ganancia"] = pd.to_numeric(p["Ganancia"], errors="coerce").fillna(0.0)
                p["Margen_%"] = p.apply(lambda r: (r["Ganancia"] / r["Ingreso"] * 100) if r["Ingreso"] > 0 else 0.0, axis=1)
                p["Precio_Prom"] = p.apply(lambda r: (r["Ingreso"] / r["Unidades"]) if r["Unidades"] > 0 else 0.0, axis=1)
                p["Costo_Prom"] = p.apply(lambda r: (r["COGS"] / r["Unidades"]) if r["Unidades"] > 0 else 0.0, axis=1)
                p["Ganancia_U"] = p.apply(lambda r: (r["Ganancia"] / r["Unidades"]) if r["Unidades"] > 0 else 0.0, axis=1)
                p = p.sort_values("Ganancia", ascending=False)

                for _, r in p.iterrows():
                    prod = str(r["Producto"])
                    with st.expander(f"{prod}", expanded=False):
                        cols = st.columns(3)
                        cols[0].markdown(f"**Unidades:** {int(r['Unidades'])}")
                        cols[1].markdown(f"**Ingreso:** {money(float(r['Ingreso']))}")
                        cols[2].markdown(f"**Neto recibido:** {money(float(r['Neto']))}")

                        cols2 = st.columns(3)
                        cols2[0].markdown(f"**COGS:** {money(float(r['COGS']))}")
                        cols2[1].markdown(f"**Ganancia neta:** {money(float(r['Ganancia']))}")
                        cols2[2].markdown(f"**Margen:** {float(r['Margen_%']):.1f}%")

                        cols3 = st.columns(3)
                        cols3[0].markdown(f"**Precio prom.:** {money(float(r['Precio_Prom']))}")
                        cols3[1].markdown(f"**Costo prom.:** {money(float(r['Costo_Prom']))}")
                        cols3[2].markdown(f"**Ganancia/unidad:** {money(float(r['Ganancia_U']))}")

                        contrib = (float(r["Ganancia"]) / total_profit * 100) if total_profit != 0 else 0.0
                        st.caption(f"Contribución a la ganancia total: {contrib:.1f}%")
    # -----------------------------
    # TAB: Ventas (Carrito)
    # -----------------------------


# -----------------------------
# Navegación principal
# -----------------------------
nav_state_init()
inject_nav_css()

screen = str(st.session_state.get("screen", "Dashboard"))

if screen == "Dashboard":
    render_dashboard_screen(conn, inv_df_full, APP_TZ)
elif screen == "Inventario":
    render_inventario_screen(conn, inv_df_full)
elif screen == "Ventas":
    render_ventas_screen(conn, inv_df_full, cfg, APP_TZ)
else:
    render_finanzas_screen(conn, inv_df_full)

bottom_nav()
