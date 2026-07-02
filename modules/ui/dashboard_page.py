from __future__ import annotations

import html
import re
from datetime import datetime

import pandas as pd
import streamlit as st

from modules.data.helpers import load_cabecera, load_detalle, load_egresos, load_inversiones


def _esc(v: object) -> str:
    return html.escape(str(v))


def _inject_dash_css() -> None:
    st.markdown("""
    <style>
      .dash-header {
        font-size: 2rem;
        font-weight: 900;
        color: #dae2fd;
        margin-bottom: 4px;
      }
      /* ── KPI grid ── */
      .dash-kpi-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 10px;
        margin-bottom: 14px;
      }
      .dash-kpi-tile {
        background: rgba(20, 20, 20, 0.72);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 18px;
        padding: 18px 16px;
        backdrop-filter: blur(8px);
      }
      .dash-kpi-label {
        font-size: 0.56rem;
        text-transform: uppercase;
        font-weight: 700;
        letter-spacing: 0.07em;
        color: #888;
        display: block;
        margin-bottom: 6px;
      }
      .dash-kpi-value {
        font-size: 1.42rem;
        font-weight: 900;
        color: #ffffff;
        line-height: 1.1;
      }
      .dash-kpi-value.green { color: #3fff8b; }
      .dash-kpi-value.red   { color: #ff6b6b; }
      .dash-kpi-sub {
        font-size: 0.58rem;
        color: #555;
        margin-top: 4px;
        display: block;
      }
      /* ── Mes highlight ── */
      .dash-mes-card {
        background: rgba(63,255,139,0.04);
        border: 1px solid rgba(63,255,139,0.15);
        border-radius: 18px;
        padding: 16px;
        margin-bottom: 14px;
      }
      /* ── Section title ── */
      .dash-section {
        font-size: 0.68rem;
        font-weight: 800;
        color: #888;
        margin: 20px 0 10px 0;
        text-transform: uppercase;
        letter-spacing: 0.1em;
      }
      /* ── Generic card ── */
      .dash-card {
        background: rgba(20,20,20,0.72);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 18px;
        padding: 18px;
        margin-bottom: 12px;
        backdrop-filter: blur(8px);
      }
      /* ── Monthly bar chart ── */
      .dash-bar-row { margin-bottom: 12px; }
      .dash-bar-row:last-child { margin-bottom: 0; }
      .dash-bar-header {
        display: flex;
        justify-content: space-between;
        font-size: 0.72rem;
        font-weight: 600;
        color: #cccccc;
        margin-bottom: 5px;
      }
      .dash-bar-track {
        height: 7px;
        background: rgba(255,255,255,0.07);
        border-radius: 999px;
        overflow: hidden;
      }
      .dash-bar-fill {
        height: 100%;
        background: linear-gradient(90deg, #3fff8b, #00d4aa);
        border-radius: 999px;
      }
      /* ── Product ranking ── */
      .dash-prod-list {
        background: rgba(20,20,20,0.72);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 18px;
        overflow: hidden;
        margin-bottom: 12px;
      }
      .dash-prod-item {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 13px 18px;
        border-bottom: 1px solid rgba(255,255,255,0.06);
      }
      .dash-prod-item:last-child { border-bottom: none; }
      .dash-prod-rank {
        font-size: 0.75rem;
        font-weight: 800;
        color: #555;
        min-width: 22px;
      }
      .dash-prod-name {
        font-size: 0.86rem;
        font-weight: 600;
        color: #ffffff;
        flex: 1;
        margin-left: 10px;
      }
      .dash-prod-units {
        font-size: 0.68rem;
        color: #555;
        margin-right: 12px;
      }
      .dash-prod-revenue {
        font-size: 0.86rem;
        font-weight: 800;
        color: #3fff8b;
      }
      /* ── Payment methods ── */
      .dash-pay-row { margin-bottom: 12px; }
      .dash-pay-row:last-child { margin-bottom: 0; }
      .dash-pay-header {
        display: flex;
        justify-content: space-between;
        font-size: 0.75rem;
        font-weight: 600;
        color: #ffffff;
        margin-bottom: 5px;
      }
      .dash-pay-pct { color: #666; }
      .dash-pay-track {
        height: 5px;
        background: rgba(255,255,255,0.07);
        border-radius: 999px;
        overflow: hidden;
      }
      .dash-pay-fill {
        height: 100%;
        border-radius: 999px;
      }
      /* ── Investment recovery ── */
      .dash-inv-row { margin-bottom: 16px; }
      .dash-inv-row:last-child { margin-bottom: 0; }
      .dash-inv-header {
        display: flex;
        justify-content: space-between;
        margin-bottom: 5px;
      }
      .dash-inv-drop {
        font-size: 0.82rem;
        font-weight: 700;
        color: #ffffff;
      }
      .dash-inv-pct {
        font-size: 0.82rem;
        font-weight: 800;
      }
      .dash-inv-track {
        height: 8px;
        background: rgba(255,255,255,0.07);
        border-radius: 999px;
        overflow: hidden;
        margin-bottom: 5px;
      }
      .dash-inv-fill {
        height: 100%;
        border-radius: 999px;
      }
      .dash-inv-footer {
        display: flex;
        justify-content: space-between;
        font-size: 0.62rem;
        color: #666;
      }
      /* ── Stock grid ── */
      .dash-stock-grid {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 8px;
        margin-bottom: 10px;
      }
      .dash-stock-tile {
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 12px;
        padding: 12px;
        text-align: center;
      }
      .dash-stock-drop {
        font-size: 0.55rem;
        text-transform: uppercase;
        font-weight: 700;
        color: #666;
        display: block;
        margin-bottom: 4px;
      }
      .dash-stock-num {
        font-size: 1.4rem;
        font-weight: 900;
        color: #3fff8b;
      }
      .dash-stock-label {
        font-size: 0.52rem;
        color: #555;
        display: block;
        margin-top: 2px;
      }
      /* ── Egreso categories ── */
      .dash-egr-item {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 10px 0;
        border-bottom: 1px solid rgba(255,255,255,0.06);
      }
      .dash-egr-item:last-child { border-bottom: none; }
      .dash-egr-cat {
        font-size: 0.82rem;
        font-weight: 600;
        color: #ffffff;
      }
      .dash-egr-amount {
        font-size: 0.82rem;
        font-weight: 800;
        color: #ff6b6b;
      }
      /* ── Últimas órdenes ── */
      .dash-order-list {
        background: rgba(20,20,20,0.72);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 18px;
        overflow: hidden;
        margin-bottom: 4px;
      }
      .dash-order-item {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        padding: 13px 18px;
        border-bottom: 1px solid rgba(255,255,255,0.06);
        gap: 10px;
      }
      .dash-order-item:last-child { border-bottom: none; }
      .dash-order-left { flex: 1; min-width: 0; }
      .dash-order-topline {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 3px;
      }
      .dash-order-id {
        font-size: 0.72rem;
        font-weight: 800;
        color: #ffffff;
      }
      .dash-order-badge {
        font-size: 0.52rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        padding: 2px 8px;
        border-radius: 999px;
        white-space: nowrap;
      }
      .dash-order-client {
        font-size: 0.82rem;
        font-weight: 600;
        color: #dddddd;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .dash-order-products {
        font-size: 0.68rem;
        color: #888;
        margin-top: 3px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .dash-order-meta {
        font-size: 0.6rem;
        color: #555;
        margin-top: 4px;
      }
      .dash-order-right {
        flex-shrink: 0;
        text-align: right;
        display: flex;
        flex-direction: column;
        align-items: flex-end;
      }
      .dash-order-total {
        font-size: 0.92rem;
        font-weight: 900;
        color: #3fff8b;
      }
      .dash-order-net {
        font-size: 0.58rem;
        color: #555;
        margin-top: 2px;
      }
    </style>
    """, unsafe_allow_html=True)


def _money(x: float) -> str:
    try:
        return f"${float(x):,.2f}"
    except Exception:
        return "$0.00"


_VENTA_ID_RE = re.compile(r"^V-(\d{4})-(\d+)$")


def _order_sort_key(venta_id: str) -> tuple[int, int]:
    """
    Ordena por año y correlativo del Venta_ID (V-YYYY-NNNN), que refleja
    el orden real de REGISTRO (no depende de que 'Fecha' esté bien tipeada).
    Si el ID no matchea el patrón, cae al final.
    """
    m = _VENTA_ID_RE.match(str(venta_id).strip())
    if not m:
        return (0, 0)
    return (int(m.group(1)), int(m.group(2)))


def _order_products_summary(det_df: pd.DataFrame, venta_id: str, max_items: int = 3) -> str:
    """Arma un resumen corto '2× Producto (Color/Talla), 1× Otro Producto +N más'."""
    if det_df is None or det_df.empty or "Venta_ID" not in det_df.columns:
        return "—"

    lines = det_df[det_df["Venta_ID"] == venta_id]
    if lines.empty:
        return "—"

    parts: list[str] = []
    for _, r in lines.iterrows():
        qty   = int(pd.to_numeric(r.get("Cantidad", 0), errors="coerce") or 0)
        prod  = str(r.get("Producto", "")).strip() or "Producto"
        color = str(r.get("Color", "")).strip()
        talla = str(r.get("Talla", "")).strip()

        detail = f"{qty}× {prod}"
        extras = [x for x in [color, talla] if x and x.upper() not in ("STANDARD", "OS", "N/A", "")]
        if extras:
            detail += f" ({'/'.join(extras)})"
        parts.append(detail)

    if len(parts) > max_items:
        return ", ".join(parts[:max_items]) + f" +{len(parts) - max_items} más"
    return ", ".join(parts)


def render_dashboard_page(conn, inv_df_full, APP_TZ) -> None:
    _inject_dash_css()

    # ── Load data ────────────────────────────────────────────────────────────
    cab_df   = load_cabecera(conn, ttl_s=60)
    det_df   = load_detalle(conn, ttl_s=60)
    egr_df   = load_egresos(conn, ttl_s=60)
    invst_df = load_inversiones(conn, ttl_s=180)
    inv_df   = inv_df_full.copy()

    # ── Coerce numerics ──────────────────────────────────────────────────────
    for col in ["Total_Cobrado", "Monto_A_Recibir", "Costo_Logistica_Total", "Comision_Monto"]:
        if not cab_df.empty and col in cab_df.columns:
            cab_df[col] = pd.to_numeric(cab_df[col], errors="coerce").fillna(0.0)

    if not det_df.empty:
        for col in ["Cantidad", "Subtotal_Linea", "Precio_Unitario", "Descuento_Unitario"]:
            if col in det_df.columns:
                det_df[col] = pd.to_numeric(det_df[col], errors="coerce").fillna(0.0)

    if not egr_df.empty and "Monto" in egr_df.columns:
        egr_df["Monto"] = pd.to_numeric(egr_df["Monto"], errors="coerce").fillna(0.0)

    if not inv_df.empty:
        for col in ["Stock_Casa", "Stock_Bodega", "Costo_Unitario", "Precio_Lista"]:
            if col in inv_df.columns:
                inv_df[col] = pd.to_numeric(inv_df[col], errors="coerce").fillna(0.0)

    if not invst_df.empty:
        invst_df["Monto_Invertido"] = pd.to_numeric(invst_df["Monto_Invertido"], errors="coerce").fillna(0.0)

    if not cab_df.empty:
        cab_df["_Fecha_dt"] = pd.to_datetime(cab_df["Fecha"], errors="coerce", dayfirst=True)

    now          = datetime.now(APP_TZ)
    this_month   = now.strftime("%Y-%m")
    this_month_l = now.strftime("%B %Y")

    # ── Global KPIs ──────────────────────────────────────────────────────────
    total_cobrado = float(cab_df["Total_Cobrado"].sum())  if not cab_df.empty else 0.0
    neto_recibido = float(cab_df["Monto_A_Recibir"].sum()) if not cab_df.empty else 0.0
    total_egresos = float(egr_df["Monto"].sum())           if not egr_df.empty else 0.0
    balance       = neto_recibido - total_egresos
    n_ventas      = len(cab_df) if not cab_df.empty else 0
    total_uds     = int(det_df["Cantidad"].sum()) if not det_df.empty else 0

    # Este mes
    if not cab_df.empty and "_Fecha_dt" in cab_df.columns:
        cab_mes     = cab_df[cab_df["_Fecha_dt"].dt.strftime("%Y-%m") == this_month]
        ventas_mes  = float(cab_mes["Total_Cobrado"].sum())
        neto_mes    = float(cab_mes["Monto_A_Recibir"].sum())
        n_ventas_mes = len(cab_mes)
    else:
        ventas_mes = neto_mes = 0.0
        n_ventas_mes = 0

    # ── Header ───────────────────────────────────────────────────────────────
    h1, h2 = st.columns([3, 1])
    with h1:
        st.markdown('<div class="dash-header">📊 Dashboard</div>', unsafe_allow_html=True)
    with h2:
        if st.button("🔄 Refrescar", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # ── KPI tiles ────────────────────────────────────────────────────────────
    bal_cls = "green" if balance >= 0 else "red"
    st.markdown(f"""
    <div class="dash-kpi-grid">
      <div class="dash-kpi-tile">
        <span class="dash-kpi-label">💰 Total Cobrado</span>
        <span class="dash-kpi-value">{_money(total_cobrado)}</span>
        <span class="dash-kpi-sub">{n_ventas} ventas · {total_uds} unidades</span>
      </div>
      <div class="dash-kpi-tile">
        <span class="dash-kpi-label">✅ Neto Recibido</span>
        <span class="dash-kpi-value green">{_money(neto_recibido)}</span>
        <span class="dash-kpi-sub">Después de comisiones y envíos</span>
      </div>
      <div class="dash-kpi-tile">
        <span class="dash-kpi-label">📤 Total Egresos</span>
        <span class="dash-kpi-value red">{_money(total_egresos)}</span>
        <span class="dash-kpi-sub">{len(egr_df) if not egr_df.empty else 0} registros</span>
      </div>
      <div class="dash-kpi-tile">
        <span class="dash-kpi-label">⚖️ Balance</span>
        <span class="dash-kpi-value {bal_cls}">{_money(balance)}</span>
        <span class="dash-kpi-sub">Neto − Egresos</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Este mes highlight ────────────────────────────────────────────────────
    if n_ventas_mes > 0:
        st.markdown(f"""
        <div class="dash-mes-card">
          <span class="dash-kpi-label" style="color:#3fff8b">📅 {_esc(this_month_l)}</span>
          <div style="display:flex;justify-content:space-between;align-items:center;margin-top:6px">
            <div>
              <div style="font-size:1.5rem;font-weight:900;color:#fff">{_money(ventas_mes)}</div>
              <div style="font-size:0.6rem;color:#666;margin-top:2px">Neto: {_money(neto_mes)}</div>
            </div>
            <div style="text-align:right">
              <div style="font-size:1.5rem;font-weight:900;color:#3fff8b">{n_ventas_mes}</div>
              <div style="font-size:0.6rem;color:#666;margin-top:2px">ventas</div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    # ── Últimas Órdenes ───────────────────────────────────────────────────────
    if not cab_df.empty:
        st.markdown('<div class="dash-section">🧾 Últimas Órdenes</div>', unsafe_allow_html=True)

        N_SHOW = 10  # <- cambiá este número si querés mostrar más/menos

        cab_sorted = cab_df.copy()
        cab_sorted["_SortKey"] = cab_sorted["Venta_ID"].apply(_order_sort_key)
        cab_sorted = cab_sorted.sort_values("_SortKey", ascending=False)
        last_orders = cab_sorted.head(N_SHOW)

        pay_colors = {
            "efectivo": "#3fff8b",
            "transferencia": "#60b4ff",
            "tarjeta": "#c084fc",
            "contra entrega": "#ffd166",
        }
        estado_colors = {
            "completada": "#3fff8b",
            "completado": "#3fff8b",
            "pendiente": "#ffd166",
            "pending": "#ffd166",
            "cancelada": "#ff6b6b",
            "cancelado": "#ff6b6b",
        }

        order_rows = ""
        for _, o in last_orders.iterrows():
            vid     = str(o.get("Venta_ID", ""))
            fecha   = str(o.get("Fecha", "")).strip()
            hora    = str(o.get("Hora", "")).strip()
            cliente = str(o.get("Cliente", "")).strip() or "—"
            metodo  = str(o.get("Metodo_Pago", "")).strip()
            estado  = str(o.get("Estado", "")).strip() or "COMPLETADA"
            total   = float(pd.to_numeric(o.get("Total_Cobrado", 0), errors="coerce") or 0)
            neto    = float(pd.to_numeric(o.get("Monto_A_Recibir", 0), errors="coerce") or 0)

            pay_color = pay_colors.get(metodo.lower(), "#a0a0a0")
            est_color = estado_colors.get(estado.lower(), "#a0a0a0")

            products_str = _order_products_summary(det_df, vid)
            meta_str = " · ".join(x for x in [fecha, hora] if x)

            order_rows += f"""
            <div class="dash-order-item">
              <div class="dash-order-left">
                <div class="dash-order-topline">
                  <span class="dash-order-id">{_esc(vid)}</span>
                  <span class="dash-order-badge" style="background:{est_color}22;color:{est_color}">{_esc(estado)}</span>
                </div>
                <div class="dash-order-client">{_esc(cliente)}</div>
                <div class="dash-order-products">{_esc(products_str)}</div>
                <div class="dash-order-meta">{_esc(meta_str)} &nbsp;·&nbsp; <span style="color:{pay_color}">{_esc(metodo)}</span></div>
              </div>
              <div class="dash-order-right">
                <span class="dash-order-total">{_money(total)}</span>
                <span class="dash-order-net">Neto: {_money(neto)}</span>
              </div>
            </div>"""

        st.markdown(f'<div class="dash-order-list">{order_rows}</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div style="font-size:0.62rem;color:#555;margin-top:6px;margin-bottom:4px">'
            f'Mostrando {len(last_orders)} de {len(cab_df)} órdenes registradas</div>',
            unsafe_allow_html=True,
        )

    # ── Monthly sales chart ───────────────────────────────────────────────────
    if not cab_df.empty and "_Fecha_dt" in cab_df.columns:
        st.markdown('<div class="dash-section">Ventas Mensuales</div>', unsafe_allow_html=True)

        cab_df["_Month"] = cab_df["_Fecha_dt"].dt.to_period("M").astype(str)
        monthly = (
            cab_df.groupby("_Month", as_index=False)
            .agg(Total=("Total_Cobrado", "sum"), N=("Venta_ID", "count"))
            .sort_values("_Month")
        )

        month_es = {
            "2026-01": "Enero 2026",   "2026-02": "Febrero 2026",
            "2026-03": "Marzo 2026",   "2026-04": "Abril 2026",
            "2026-05": "Mayo 2026",    "2026-06": "Junio 2026",
        }
        max_t = float(monthly["Total"].max()) if not monthly.empty else 1.0
        bars  = ""
        for _, row in monthly.iterrows():
            pct   = (float(row["Total"]) / max_t * 100) if max_t > 0 else 0
            label = month_es.get(str(row["_Month"]), str(row["_Month"]))
            bars += f"""
            <div class="dash-bar-row">
              <div class="dash-bar-header">
                <span>{_esc(label)}</span>
                <span>{_money(float(row["Total"]))} &nbsp;·&nbsp; {int(row["N"])} vtas</span>
              </div>
              <div class="dash-bar-track">
                <div class="dash-bar-fill" style="width:{pct:.1f}%"></div>
              </div>
            </div>"""

        st.markdown(f'<div class="dash-card">{bars}</div>', unsafe_allow_html=True)

    # ── Top productos ─────────────────────────────────────────────────────────
    if not det_df.empty:
        st.markdown('<div class="dash-section">Top Productos por Ingresos</div>', unsafe_allow_html=True)

        sku_cost = (
            inv_df[["SKU", "Costo_Unitario"]].copy()
            if not inv_df.empty and "SKU" in inv_df.columns
            else pd.DataFrame(columns=["SKU", "Costo_Unitario"])
        )
        lines = det_df.merge(sku_cost, on="SKU", how="left")
        lines["Costo_Unitario"] = pd.to_numeric(lines.get("Costo_Unitario", 0), errors="coerce").fillna(0.0)
        lines["COGS"] = lines["Costo_Unitario"] * lines["Cantidad"]

        top = (
            lines.groupby("Producto", as_index=False)
            .agg(Ingresos=("Subtotal_Linea", "sum"), Uds=("Cantidad", "sum"), COGS=("COGS", "sum"))
            .sort_values("Ingresos", ascending=False)
            .head(5)
        )
        top["Margen"] = top.apply(
            lambda r: f"{(r['Ingresos']-r['COGS'])/r['Ingresos']*100:.0f}%" if r["Ingresos"] > 0 else "—",
            axis=1,
        )

        items = ""
        for i, (_, r) in enumerate(top.iterrows(), 1):
            items += f"""
            <div class="dash-prod-item">
              <span class="dash-prod-rank">{i:02d}</span>
              <span class="dash-prod-name">{_esc(r["Producto"])}</span>
              <span class="dash-prod-units">{int(r["Uds"])} uds&nbsp;·&nbsp;{r["Margen"]}</span>
              <span class="dash-prod-revenue">{_money(float(r["Ingresos"]))}</span>
            </div>"""

        st.markdown(f'<div class="dash-prod-list">{items}</div>', unsafe_allow_html=True)

    # ── Inventario snapshot ───────────────────────────────────────────────────
    if not inv_df.empty:
        st.markdown('<div class="dash-section">Inventario</div>', unsafe_allow_html=True)
        inv_df["Stock_Total"] = inv_df["Stock_Casa"] + inv_df["Stock_Bodega"]
        stock_total = int(inv_df["Stock_Total"].sum())
        stock_valor = float((inv_df["Stock_Total"] * inv_df["Costo_Unitario"]).sum())
        agotados    = int((inv_df["Stock_Total"] == 0).sum())

        drops = inv_df.groupby("Drop", as_index=False)["Stock_Total"].sum().sort_values("Drop")
        drop_tiles = "".join(
            f"""<div class="dash-stock-tile">
              <span class="dash-stock-drop">{_esc(row["Drop"])}</span>
              <span class="dash-stock-num">{int(row["Stock_Total"])}</span>
              <span class="dash-stock-label">uds</span>
            </div>"""
            for _, row in drops.iterrows()
        )

        agotados_color = "#ff6b6b" if agotados > 0 else "#3fff8b"
        st.markdown(f"""
        <div class="dash-card">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
            <div>
              <div style="font-size:0.56rem;text-transform:uppercase;font-weight:700;color:#888;margin-bottom:4px">Stock Total</div>
              <div style="font-size:2rem;font-weight:900;color:#fff">{stock_total}
                <span style="font-size:0.85rem;color:#555">unidades</span>
              </div>
            </div>
            <div style="text-align:right">
              <div style="font-size:0.56rem;text-transform:uppercase;font-weight:700;color:#888;margin-bottom:4px">Valor en Costo</div>
              <div style="font-size:1.25rem;font-weight:900;color:#fff">{_money(stock_valor)}</div>
            </div>
          </div>
          <div class="dash-stock-grid">{drop_tiles}</div>
          <div style="font-size:0.68rem;color:{agotados_color};margin-top:6px">
            {'⚠️' if agotados > 0 else '✅'} {agotados} SKUs agotados (stock 0)
          </div>
        </div>
        """, unsafe_allow_html=True)

    # ── Inversión por Drop ────────────────────────────────────────────────────
    if not invst_df.empty and not det_df.empty and not cab_df.empty:
        st.markdown('<div class="dash-section">Recuperación de Inversión</div>', unsafe_allow_html=True)

        # Allocate neto to lines proportionally
        lt = det_df.groupby("Venta_ID", as_index=False)["Subtotal_Linea"].sum().rename(columns={"Subtotal_Linea": "_VT"})
        l2 = det_df.merge(lt, on="Venta_ID", how="left").merge(
            cab_df[["Venta_ID", "Monto_A_Recibir"]], on="Venta_ID", how="left"
        )
        l2["Monto_A_Recibir"] = pd.to_numeric(l2["Monto_A_Recibir"], errors="coerce").fillna(0.0)
        l2["_VT"]             = pd.to_numeric(l2["_VT"], errors="coerce").fillna(0.0)
        nz = l2["_VT"] > 0
        l2["_Share"] = 0.0
        l2.loc[nz, "_Share"] = l2.loc[nz, "Subtotal_Linea"] / l2.loc[nz, "_VT"]
        l2["_Neto"] = (l2["_Share"] * l2["Monto_A_Recibir"]).round(2)

        drop_neto = l2.groupby("Drop")["_Neto"].sum()

        inv_drops = invst_df[invst_df["Tipo"].astype(str).str.upper().str.strip() == "DROP"].copy()

        inv_rows = ""
        for _, row in inv_drops.iterrows():
            dr       = str(row["Referencia"]).strip()
            inversion = float(row["Monto_Invertido"])
            neto_dr  = float(drop_neto.get(dr, 0.0))
            pct      = min(100.0, (neto_dr / inversion * 100)) if inversion > 0 else 0.0
            faltante = max(0.0, inversion - neto_dr)
            color    = "#3fff8b" if pct >= 100 else "#a0a0a0" if pct >= 50 else "#ff6b6b"
            nota     = (
                f'<div style="font-size:0.6rem;color:#3fff8b;margin-top:3px">✓ ¡Inversión recuperada!</div>'
                if faltante <= 0
                else f'<div style="font-size:0.6rem;color:#666;margin-top:3px">Faltante: {_money(faltante)}</div>'
            )
            inv_rows += f"""
            <div class="dash-inv-row">
              <div class="dash-inv-header">
                <span class="dash-inv-drop">Drop {_esc(dr)}</span>
                <span class="dash-inv-pct" style="color:{color}">{pct:.1f}%</span>
              </div>
              <div class="dash-inv-track">
                <div class="dash-inv-fill" style="width:{pct:.1f}%;background:{color}"></div>
              </div>
              <div class="dash-inv-footer">
                <span>Recuperado: {_money(neto_dr)}</span>
                <span>Inversión: {_money(inversion)}</span>
              </div>
              {nota}
            </div>"""

        if inv_rows:
            st.markdown(f'<div class="dash-card">{inv_rows}</div>', unsafe_allow_html=True)

    # ── Métodos de pago ───────────────────────────────────────────────────────
    if not cab_df.empty and "Metodo_Pago" in cab_df.columns:
        st.markdown('<div class="dash-section">Métodos de Pago</div>', unsafe_allow_html=True)
        pay = (
            cab_df.groupby("Metodo_Pago", as_index=False)["Total_Cobrado"]
            .sum()
            .sort_values("Total_Cobrado", ascending=False)
        )
        pay_total = float(pay["Total_Cobrado"].sum())
        colors = ["#3fff8b", "#60b4ff", "#ffd166", "#ff6b9d", "#c084fc"]

        pay_rows = ""
        for i, (_, pm) in enumerate(pay.iterrows()):
            monto = float(pm["Total_Cobrado"])
            pct   = (monto / pay_total * 100) if pay_total > 0 else 0
            color = colors[i % len(colors)]
            pay_rows += f"""
            <div class="dash-pay-row">
              <div class="dash-pay-header">
                <span>{_esc(pm["Metodo_Pago"])}</span>
                <span>{_money(monto)} <span class="dash-pay-pct">({pct:.1f}%)</span></span>
              </div>
              <div class="dash-pay-track">
                <div class="dash-pay-fill" style="width:{pct:.1f}%;background:{color}"></div>
              </div>
            </div>"""

        st.markdown(f'<div class="dash-card">{pay_rows}</div>', unsafe_allow_html=True)

    # ── Egresos por categoría ─────────────────────────────────────────────────
    if not egr_df.empty and "Categoria" in egr_df.columns and total_egresos > 0:
        st.markdown('<div class="dash-section">Egresos por Categoría</div>', unsafe_allow_html=True)
        egr_cat = (
            egr_df.groupby("Categoria", as_index=False)["Monto"]
            .sum()
            .sort_values("Monto", ascending=False)
        )
        egr_rows = ""
        for _, ec in egr_cat.iterrows():
            monto = float(ec["Monto"])
            pct   = (monto / total_egresos * 100) if total_egresos > 0 else 0
            egr_rows += f"""
            <div class="dash-egr-item">
              <span class="dash-egr-cat">{_esc(ec["Categoria"])}</span>
              <div style="text-align:right">
                <span class="dash-egr-amount">{_money(monto)}</span>
                <span style="font-size:0.6rem;color:#555;margin-left:6px">{pct:.1f}%</span>
              </div>
            </div>"""

        st.markdown(f'<div class="dash-card">{egr_rows}</div>', unsafe_allow_html=True)
