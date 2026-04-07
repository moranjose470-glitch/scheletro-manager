from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Iterable
import re
import unicodedata

import pandas as pd
import streamlit as st
from streamlit_gsheets import GSheetsConnection

from modules.core.constants import (
    CAB_REQUIRED,
    CAT_REQUIRED,
    DET_REQUIRED,
    EG_REQUIRED,
    INVEST_REQUIRED,
    INV_REQUIRED,
    SHEET_CATALOGOS,
    SHEET_CATEGORIAS,
    SHEET_CONFIG,
    SHEET_EGRESOS,
    SHEET_INVENTARIO,
    SHEET_INVERSIONES,
    SHEET_VENTAS_CAB,
    SHEET_VENTAS_DET,
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
    return (
        ("code': 429" in s)
        or ('code": 429' in s)
        or ("429" in s and "rate" in s.lower())
        or ("RESOURCE_EXHAUSTED" in s)
        or ("RATE_LIMIT_EXCEEDED" in s)
    )


def _raise_rate_limit_error(action: str, worksheet: str, original_error: Exception) -> None:
    raise RuntimeError(
        f"Google Sheets devolvió rate limit (429) al {action} la hoja '{worksheet}'. "
        f"Reintentá en 60–90 segundos. Detalle original: {original_error}"
    ) from original_error


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
        # Para lecturas cacheadas no reventamos toda la UI.
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
    - En lecturas críticas, si hay 429, SE LANZA EXCEPCIÓN.
    """
    ttl_s = int(ttl_s or 45)

    # Lectura crítica/directa: NO debe fallar silenciosamente
    if ttl_s <= 0:
        try:
            df = conn.read(worksheet=worksheet, ttl=1)
            return _normalize_df(df)
        except Exception as e:
            if _is_rate_limit(e):
                st.error(
                    "⚠️ Google Sheets te limitó por demasiadas solicitudes (error 429) al LEER. "
                    "Esperá 60–90 segundos y reintentá."
                )
                _raise_rate_limit_error("leer", worksheet, e)
            raise

    # Lectura cacheada/no crítica
    if ttl_s <= 60:
        return _cached_read_45(worksheet).copy()
    if ttl_s <= 300:
        return _cached_read_180(worksheet).copy()
    return _cached_read_600(worksheet).copy()


def save_sheet(conn: GSheetsConnection, worksheet: str, df: pd.DataFrame) -> None:
    """
    Escribe un DataFrame a Google Sheets.
    Punto único de escritura.

    IMPORTANTE:
    - Si falla por 429, LANZA EXCEPCIÓN.
    - Ya no hace return silencioso.
    """
    try:
        conn.update(worksheet=worksheet, data=df)
    except Exception as e:
        if _is_rate_limit(e):
            st.error(
                "⚠️ Google Sheets te limitó por demasiadas solicitudes (error 429) al ESCRIBIR. "
                "Esperá 60–90 segundos y reintentá."
            )
            _raise_rate_limit_error("escribir", worksheet, e)
        raise

    # Limpiar cache para que las lecturas posteriores vean el cambio real.
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


def load_egresos(conn: GSheetsConnection, ttl_s: int = 60) -> pd.DataFrame:
    df = load_raw_sheet(conn, SHEET_EGRESOS, ttl_s=ttl_s)
    if df.empty:
        return _align_required_columns(pd.DataFrame(), EG_REQUIRED)
    df = _align_required_columns(df, EG_REQUIRED)
    df = _to_numeric(df, ["Monto"])
    for c in ["Egreso_ID", "Fecha", "Concepto", "Categoria", "Notas", "Drop"]:
        df[c] = df[c].astype(str).fillna("").str.strip()
    return df


def _next_egreso_id(eg_df: pd.DataFrame, tz: str = "America/El_Salvador") -> str:
    now = datetime.now(ZoneInfo(tz))
    year = now.year
    prefix = f"E-{year}-"
    if eg_df is None or eg_df.empty or "Egreso_ID" not in eg_df.columns:
        return f"{prefix}0001"
    nums = []
    for v in eg_df["Egreso_ID"].astype(str).tolist():
        v = v.strip()
        if not v.startswith(prefix):
            continue
        tail = v.replace(prefix, "")
        try:
            nums.append(int(tail))
        except Exception:
            pass
    n = (max(nums) + 1) if nums else 1
    return f"{prefix}{n:04d}"


def load_categorias(conn: GSheetsConnection, ttl_s: int = 300) -> pd.DataFrame:
    """Lee la hoja Categorias (listado maestro de categorías de egresos)."""
    df = load_raw_sheet(conn, SHEET_CATEGORIAS, ttl_s=ttl_s)
    if df.empty:
        return _align_required_columns(pd.DataFrame(), CAT_REQUIRED)
    df = _align_required_columns(df, CAT_REQUIRED)
    df["Categoria"] = df["Categoria"].astype(str).str.strip()
    return df


def load_catalogos(conn: GSheetsConnection, ttl_s: int = 600) -> pd.DataFrame:
    """Lee hoja Catalogos (Drops, Colores, etc.) con cache."""
    df = load_raw_sheet(conn, SHEET_CATALOGOS, ttl_s=ttl_s)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def parse_catalogos(df: pd.DataFrame) -> dict[str, list[dict[str, str]]]:
    """Devuelve dict con listas: drops[{valor,codigo}], colores[{valor,codigo}]."""
    if df is None or df.empty:
        return {"drops": [], "colores": []}

    work = df.copy()

    if "Catalogo" in work.columns:
        work["Catalogo"] = work["Catalogo"].ffill()

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

    segs = sub["SKU"].astype(str).str.split("-", n=3, expand=True)
    if segs.shape[1] < 2:
        return None

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