from __future__ import annotations

from datetime import datetime
from math import ceil
import html

import pandas as pd
import streamlit as st

from modules.data.helpers import load_cabecera, load_detalle, load_inversiones


# --------------------------------------------------
# CSS específico de Finanzas
# --------------------------------------------------
def _inject_finanzas_css() -> None:
    st.markdown(
        """
        <style>
          /* Fondos transparentes para que hereden el color de la pestaña */
          .fin-card, .fin-card-low {
            background: transparent;
            border-radius: 16px;
            padding: 20px;
            margin-bottom: 16px;
            border: 1px solid rgba(255, 255, 255, 0.12);  /* Borde sutil */
          }
          /* Texto blanco normal, sin tintes */
          .fin-label {
            font-size: 0.65rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: #cccccc;
            margin-bottom: 4px;
          }
          .fin-big-number {
            font-size: 2.4rem;
            font-weight: 900;
            color: #ffffff;
            line-height: 1.1;
            margin-bottom: 16px;
          }
          .fin-mini-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 8px;
          }
          .fin-mini-label {
            font-size: 0.55rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #cccccc;
            display: block;
            margin-bottom: 2px;
          }
          .fin-mini-value {
            font-size: 0.88rem;
            font-weight: 700;
            color: #ffffff;
          }
          /* Ya no usamos verde; dejamos blanco para consistencia */
          .fin-mini-value.green { color: #ffffff; }

          .fin-eq-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
            margin-bottom: 10px;
          }
          .fin-eq-pct {
            font-size: 0.8rem;
            font-weight: 800;
            color: #a0a0a0;   /* Acento neutro */
          }
          .fin-bar-track {
            height: 10px;
            width: 100%;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 999px;
            overflow: hidden;
            margin-bottom: 10px;
          }
          .fin-bar-fill {
            height: 100%;
            background: #a0a0a0;   /* Relleno gris claro */
            border-radius: 999px;
          }
          .fin-eq-footer {
            display: flex;
            justify-content: space-between;
            font-size: 0.7rem;
            font-weight: 600;
            color: #ffffff;
          }
          .fin-eq-footer span.muted { color: #cccccc; }

          .fin-section-title {
            font-size: 1.08rem;
            font-weight: 800;
            color: #ffffff;
            margin: 20px 0 12px 0;
          }
          .fin-star-list {
            background: transparent;
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 16px;
            overflow: hidden;
          }
          .fin-star-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 14px 18px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
          }
          .fin-star-item:last-child { border-bottom: none; }
          .fin-star-left {
            display: flex;
            align-items: center;
            gap: 14px;
          }
          .fin-star-num {
            font-size: 0.82rem;
            font-weight: 800;
            color: #a0a0a0;
            min-width: 24px;
          }
          .fin-star-name {
            font-size: 0.88rem;
            font-weight: 600;
            color: #ffffff;
          }
          .fin-star-price {
            font-size: 0.88rem;
            font-weight: 800;
            color: #ffffff;
          }

          .fin-prog-label {
            display: flex;
            justify-content: space-between;
            font-size: 0.58rem;
            text-transform: uppercase;
            font-weight: 700;
            letter-spacing: 0.05em;
            color: #cccccc;
            margin-bottom: 6px;
          }
          .fin-bar-track-sm {
            height: 7px;
            width: 100%;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 999px;
            overflow: hidden;
            margin-bottom: 14px;
          }
          .fin-bar-fill-sm {
            height: 100%;
            background: #a0a0a0;
            border-radius: 999px;
          }
          .fin-metrics-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px 24px;
            padding-top: 4px;
          }
          .fin-metric-block.right { text-align: right; }
          .fin-metric-label {
            font-size: 0.58rem;
            text-transform: uppercase;
            font-weight: 700;
            letter-spacing: 0.05em;
            color: #cccccc;
            display: block;
            margin-bottom: 2px;
          }
          .fin-metric-value {
            font-size: 0.88rem;
            font-weight: 700;
            color: #ffffff;
          }
          .fin-metric-value.green { color: #ffffff; }

          .fin-pay-label {
            font-size: 0.65rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: #cccccc;
            margin-bottom: 16px;
            display: block;
          }
          .fin-pay-row {
            margin-bottom: 14px;
          }
          .fin-pay-top {
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
            margin-bottom: 6px;
          }
          .fin-pay-name {
            font-size: 0.88rem;
            font-weight: 600;
            color: #ffffff;
          }
          .fin-pay-amount {
            font-size: 0.88rem;
            font-weight: 800;
            color: #ffffff;
          }
          .fin-pay-bar-track {
            height: 5px;
            width: 100%;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 999px;
            overflow: hidden;
          }
          .fin-pay-bar-fill {
            height: 100%;
            background: #a0a0a0;
            border-radius: 999px;
          }

          .fin-kpi-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
            margin-bottom: 16px;
          }
          .fin-kpi-tile {
            background: transparent;
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 16px;
            padding: 18px;
          }
          .fin-kpi-label {
            font-size: 0.58rem;
            text-transform: uppercase;
            font-weight: 700;
            letter-spacing: 0.05em;
            color: #cccccc;
            display: block;
            margin-bottom: 6px;
          }
          .fin-kpi-value {
            font-size: 1.6rem;
            font-weight: 900;
            line-height: 1.1;
            color: #ffffff;
          }
          .fin-kpi-value.red { color: #ff6b6b; }    /* Podés cambiarlo si preferís otro tono de advertencia */
          .fin-kpi-value.green { color: #ffffff; }  /* Ya no usamos verde */
          .fin-kpi-sub {
            font-size: 0.62rem;
            color: #cccccc;
            margin-top: 4px;
            display: block;
          }

          .fin-warn {
            font-size: 0.75rem;
            color: #cccccc;
            padding: 8px 0 12px 0;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _esc(value: object) -> str:
    return html.escape(str(value))


def _calc_recuperacion_prendas(
    inversion: float,
    neto_recibido: float,
    unidades_vendidas: int | float,
) -> tuple[float, float, int | None]:
    """
    Calcula cuánta inversión falta por recuperar y cuántas prendas adicionales
    habría que vender usando el neto promedio real por unidad vendida.

    Se usa NETO porque el progreso actual de recuperación compara Neto vs Inversión.
    Si el producto todavía no tiene una base de venta neta válida, devuelve None
    para evitar inventar una cantidad.
    """
    inversion = float(inversion or 0.0)
    neto_recibido = float(neto_recibido or 0.0)
    unidades_vendidas = float(unidades_vendidas or 0.0)

    faltante = max(inversion - neto_recibido, 0.0)
    neto_promedio_por_prenda = (neto_recibido / unidades_vendidas) if unidades_vendidas > 0 else 0.0

    if faltante <= 0:
        prendas_faltantes = 0
    elif neto_promedio_por_prenda > 0:
        prendas_faltantes = int(ceil(faltante / neto_promedio_por_prenda))
    else:
        prendas_faltantes = None

    return round(faltante, 2), round(neto_promedio_por_prenda, 2), prendas_faltantes


# --------------------------------------------------
# Render principal
# --------------------------------------------------
def render_finanzas_page(conn, inv_df_full, APP_TZ) -> None:
    from modules.ui.styles import money

    _inject_finanzas_css()

    cab_df = load_cabecera(conn, ttl_s=60)
    det_df = load_detalle(conn, ttl_s=60)
    inv_df = inv_df_full.copy()
    invst_df = load_inversiones(conn, ttl_s=180)

    if not cab_df.empty:
        cab_df["_Fecha_dt"] = pd.to_datetime(cab_df["Fecha"], errors="coerce", dayfirst=True)
    else:
        cab_df["_Fecha_dt"] = pd.NaT

    if not det_df.empty:
        det_df["Subtotal_Linea"] = pd.to_numeric(det_df["Subtotal_Linea"], errors="coerce").fillna(0.0)
        det_df["Cantidad"] = pd.to_numeric(det_df["Cantidad"], errors="coerce").fillna(0).astype(int)
        det_df["Precio_Unitario"] = pd.to_numeric(det_df.get("Precio_Unitario", 0.0), errors="coerce").fillna(0.0)
        det_df["Descuento_Unitario"] = pd.to_numeric(det_df.get("Descuento_Unitario", 0.0), errors="coerce").fillna(0.0)
    else:
        det_df["Subtotal_Linea"] = 0.0
        det_df["Cantidad"] = 0
        det_df["Precio_Unitario"] = 0.0
        det_df["Descuento_Unitario"] = 0.0

    sku_cost = (
        inv_df[["SKU", "Costo_Unitario"]].copy()
        if (not inv_df.empty and "SKU" in inv_df.columns)
        else pd.DataFrame(columns=["SKU", "Costo_Unitario"])
    )
    if not sku_cost.empty:
        sku_cost["SKU"] = sku_cost["SKU"].astype(str).str.strip()
        sku_cost["Costo_Unitario"] = pd.to_numeric(sku_cost["Costo_Unitario"], errors="coerce").fillna(0.0)

    lines = det_df.merge(sku_cost, on="SKU", how="left")
    lines["Costo_Unitario"] = pd.to_numeric(lines.get("Costo_Unitario", 0.0), errors="coerce").fillna(0.0)
    lines["COGS_Linea"] = (lines["Costo_Unitario"] * lines["Cantidad"]).round(2)

    sale_line_tot = (
        lines.groupby("Venta_ID", as_index=False)["Subtotal_Linea"]
        .sum()
        .rename(columns={"Subtotal_Linea": "_Venta_Subtotal_Lineas"})
    )

    cab_cols = [
        "Venta_ID",
        "Total_Cobrado",
        "Monto_A_Recibir",
        "Costo_Logistica_Total",
        "Comision_Monto",
        "Metodo_Pago",
        "_Fecha_dt",
    ]
    cab = cab_df[cab_cols].copy()
    for col in ["Total_Cobrado", "Monto_A_Recibir", "Costo_Logistica_Total", "Comision_Monto"]:
        cab[col] = pd.to_numeric(cab[col], errors="coerce").fillna(0.0)

    lines = lines.merge(sale_line_tot, on="Venta_ID", how="left").merge(cab, on="Venta_ID", how="left")
    lines["_Venta_Subtotal_Lineas"] = pd.to_numeric(lines["_Venta_Subtotal_Lineas"], errors="coerce").fillna(0.0)
    lines["_Share"] = 0.0
    nz = lines["_Venta_Subtotal_Lineas"] > 0
    lines.loc[nz, "_Share"] = (
        lines.loc[nz, "Subtotal_Linea"] / lines.loc[nz, "_Venta_Subtotal_Lineas"]
    ).fillna(0.0)

    lines["_Monto_Asignado"] = (
        lines["_Share"] * pd.to_numeric(lines["Monto_A_Recibir"], errors="coerce").fillna(0.0)
    ).round(2)
    lines["_Cobrado_Asignado"] = (
        lines["_Share"] * pd.to_numeric(lines["Total_Cobrado"], errors="coerce").fillna(0.0)
    ).round(2)
    lines["_Logistica_Asignada"] = (
        lines["_Share"] * pd.to_numeric(lines["Costo_Logistica_Total"], errors="coerce").fillna(0.0)
    ).round(2)
    lines["_Ganancia_Neta_Linea"] = (lines["_Monto_Asignado"] - lines["COGS_Linea"]).round(2)

    drops_in_data = sorted(
        [d for d in lines.get("Drop", pd.Series(dtype=str)).dropna().astype(str).str.strip().unique().tolist() if d]
    )
    if not drops_in_data and not inv_df.empty and "Drop" in inv_df.columns:
        drops_in_data = sorted([d for d in inv_df["Drop"].dropna().astype(str).str.strip().unique().tolist() if d])

    now = datetime.now(APP_TZ)
    this_month = now.strftime("%Y-%m")

    options = ["Todo"] + [f"Drop {d}" for d in drops_in_data] + ["Este mes"]
    if "fin_filter" not in st.session_state:
        st.session_state.fin_filter = "Todo"

    h1, h2 = st.columns([3, 1])
    with h1:
        st.markdown(
            "<div style='font-size:2rem;font-weight:900;color:#dae2fd;margin-bottom:4px'>Finanzas</div>",
            unsafe_allow_html=True,
        )
    with h2:
        if st.button("🔄 Refrescar", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    sel = st.segmented_control(
        "Filtro",
        options=options,
        default=st.session_state.fin_filter,
        label_visibility="collapsed",
        key="fin_seg_ctrl",
    )
    if sel and sel != st.session_state.fin_filter:
        st.session_state.fin_filter = sel
        st.rerun()
    sel = sel or st.session_state.fin_filter

    cab_f = cab_df.copy()
    if not cab_f.empty:
        cab_f["_Fecha_dt"] = pd.to_datetime(cab_f["Fecha"], errors="coerce", dayfirst=True)
    if sel == "Este mes" and not cab_f.empty:
        cab_f = cab_f[cab_f["_Fecha_dt"].dt.strftime("%Y-%m") == this_month].copy()

    lines_f = lines.copy()
    if sel == "Este mes" and not cab_f.empty:
        vids = set(cab_f["Venta_ID"].astype(str).tolist())
        lines_f = lines_f[lines_f["Venta_ID"].astype(str).isin(vids)].copy()

    active_drop = None
    if sel.startswith("Drop "):
        active_drop = sel.replace("Drop ", "").strip()
        lines_f = lines_f[lines_f["Drop"].astype(str).str.strip() == active_drop].copy()

    total_cobrado = float(pd.to_numeric(lines_f["_Cobrado_Asignado"], errors="coerce").fillna(0.0).sum())
    neto_recibido = float(pd.to_numeric(lines_f["_Monto_Asignado"], errors="coerce").fillna(0.0).sum())
    unidades = int(pd.to_numeric(lines_f["Cantidad"], errors="coerce").fillna(0).sum())
    ganancia_neta = float(pd.to_numeric(lines_f["_Ganancia_Neta_Linea"], errors="coerce").fillna(0.0).sum())
    total_logistica = float(pd.to_numeric(lines_f["_Logistica_Asignada"], errors="coerce").fillna(0.0).sum())

    pct_logistica = (total_logistica / total_cobrado * 100) if total_cobrado > 0 else 0.0

    precio_bruto_total = float(
        (
            pd.to_numeric(lines_f.get("Precio_Unitario", 0.0), errors="coerce").fillna(0.0)
            * pd.to_numeric(lines_f.get("Cantidad", 0), errors="coerce").fillna(0)
        ).sum()
    )
    descuento_total = float(
        (
            pd.to_numeric(lines_f.get("Descuento_Unitario", 0.0), errors="coerce").fillna(0.0)
            * pd.to_numeric(lines_f.get("Cantidad", 0), errors="coerce").fillna(0)
        ).sum()
    )
    pct_descuento = (descuento_total / precio_bruto_total * 100) if precio_bruto_total > 0 else 0.0

    st.markdown(
        f"""
        <div class="fin-card">
          <div class="fin-label">Ventas Totales</div>
          <div class="fin-big-number">{money(total_cobrado)}</div>
          <div class="fin-mini-grid">
            <div>
              <span class="fin-mini-label">Neto</span>
              <span class="fin-mini-value">{money(neto_recibido)}</span>
            </div>
            <div>
              <span class="fin-mini-label">Unidades</span>
              <span class="fin-mini-value">{unidades}</span>
            </div>
            <div>
              <span class="fin-mini-label">Ganancia</span>
              <span class="fin-mini-value green">{money(ganancia_neta)}</span>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    def _inv_amount_for_scope(drop_name: str | None, lines_scope: pd.DataFrame) -> float:
        if invst_df.empty:
            return 0.0

        df = invst_df.copy()
        df["Tipo"] = df["Tipo"].astype(str).str.upper().str.strip()
        df["Referencia"] = df["Referencia"].astype(str).str.strip()
        df["Monto_Invertido"] = pd.to_numeric(df["Monto_Invertido"], errors="coerce").fillna(0.0)

        if drop_name:
            m = df[(df["Tipo"] == "DROP") & (df["Referencia"] == drop_name)]
            if not m.empty:
                return float(m["Monto_Invertido"].sum())
            prods = [p for p in lines_scope["Producto"].dropna().astype(str).str.strip().unique() if p]
            return float(df[(df["Tipo"] == "PRODUCTO") & (df["Referencia"].isin(prods))]["Monto_Invertido"].sum())

        drops_scope = [d for d in lines_scope["Drop"].dropna().astype(str).str.strip().unique() if d]
        m_drop = df[(df["Tipo"] == "DROP") & (df["Referencia"].isin(drops_scope))]
        if not m_drop.empty:
            return float(m_drop["Monto_Invertido"].sum())

        prods = [p for p in lines_scope["Producto"].dropna().astype(str).str.strip().unique() if p]
        return float(df[(df["Tipo"] == "PRODUCTO") & (df["Referencia"].isin(prods))]["Monto_Invertido"].sum())

    inv_total = _inv_amount_for_scope(active_drop, lines_f)
    if inv_total > 0:
        pct_eq = max(0.0, min(100.0, neto_recibido / inv_total * 100))
        faltante_global, neto_prom_global, prendas_global = _calc_recuperacion_prendas(
            inv_total,
            neto_recibido,
            unidades,
        )
        prendas_global_text = "—" if prendas_global is None else f"{prendas_global:,}"
        st.markdown(
            f"""
            <div class="fin-card-low">
              <div class="fin-eq-header">
                <span class="fin-label">Punto de Equilibrio Global</span>
                <span class="fin-eq-pct">{pct_eq:.1f}%</span>
              </div>
              <div class="fin-bar-track">
                <div class="fin-bar-fill" style="width:{pct_eq:.1f}%"></div>
              </div>
              <div class="fin-eq-footer">
                <span>Recuperado: {money(neto_recibido)}</span>
                <span class="muted">Meta: {money(inv_total)}</span>
              </div>
              <div class="fin-eq-footer">
                <span>Faltante: {money(faltante_global)}</span>
                <span class="muted">Prendas faltantes: {prendas_global_text}</span>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown('<div class="fin-card-low">', unsafe_allow_html=True)
        st.warning("No hay inversión registrada. Agregá montos en la hoja **Inversiones**.")
        st.markdown("</div>", unsafe_allow_html=True)

    if not lines_f.empty:
        star = (
            lines_f.groupby("Producto", as_index=False)["_Ganancia_Neta_Linea"]
            .sum()
            .sort_values("_Ganancia_Neta_Linea", ascending=False)
            .head(3)
        )

        star_items: list[str] = []
        for i, (_, r) in enumerate(star.iterrows(), start=1):
            num = f"{i:02d}"
            name = _esc(r["Producto"])
            price = money(float(r["_Ganancia_Neta_Linea"]))
            star_items.append(
                f'<div class="fin-star-item">'
                f'  <div class="fin-star-left">'
                f'    <span class="fin-star-num">{num}</span>'
                f'    <span class="fin-star-name">{name}</span>'
                f'  </div>'
                f'  <span class="fin-star-price">{price}</span>'
                f'</div>'
            )

        items_html = "".join(star_items)
        st.markdown(
            f'<div class="fin-section-title">Productos Estrella</div>'
            f'<div class="fin-star-list">{items_html}</div>',
            unsafe_allow_html=True,
        )

    st.markdown('<div class="fin-section-title">Detalle de Productos</div>', unsafe_allow_html=True)

    if lines_f.empty:
        st.info("Aún no hay ventas para mostrar.")
    else:
        inv_prod = pd.DataFrame(columns=["Tipo", "Referencia", "Monto_Invertido"])
        if not invst_df.empty:
            inv_prod = invst_df.copy()
            inv_prod["Tipo"] = inv_prod["Tipo"].astype(str).str.upper().str.strip()
            inv_prod["Referencia"] = inv_prod["Referencia"].astype(str).str.strip()
            inv_prod["Monto_Invertido"] = pd.to_numeric(inv_prod["Monto_Invertido"], errors="coerce").fillna(0.0)
            inv_prod = inv_prod[inv_prod["Tipo"] == "PRODUCTO"].copy()
            if active_drop:
                prods_in_drop = [p for p in lines_f["Producto"].dropna().astype(str).str.strip().unique() if p]
                inv_prod = inv_prod[inv_prod["Referencia"].isin(prods_in_drop)].copy()

        g = lines_f.groupby("Producto", as_index=False).agg(
            Unidades=("Cantidad", "sum"),
            Ingreso=("Subtotal_Linea", "sum"),
            Neto=("_Monto_Asignado", "sum"),
            COGS=("COGS_Linea", "sum"),
            Ganancia=("_Ganancia_Neta_Linea", "sum"),
        )

        if not inv_prod.empty:
            inv_map = inv_prod.groupby("Referencia", as_index=False)["Monto_Invertido"].sum()
            g = g.merge(inv_map, left_on="Producto", right_on="Referencia", how="left")
            g["Monto_Invertido"] = pd.to_numeric(g["Monto_Invertido"], errors="coerce").fillna(0.0)
        else:
            g["Monto_Invertido"] = 0.0

        for col in ["Ingreso", "Neto", "COGS", "Ganancia"]:
            g[col] = pd.to_numeric(g[col], errors="coerce").fillna(0.0)

        g["Margen_Pct"] = g.apply(lambda r: (r["Ganancia"] / r["Ingreso"] * 100) if r["Ingreso"] > 0 else 0.0, axis=1)
        g["ROI_Pct"] = g.apply(lambda r: (r["Ganancia"] / r["COGS"] * 100) if r["COGS"] > 0 else 0.0, axis=1)
        g["Pct_Rec"] = g.apply(
            lambda r: (r["Neto"] / r["Monto_Invertido"] * 100) if r["Monto_Invertido"] > 0 else -1.0,
            axis=1,
        )
        g = g.sort_values(["Pct_Rec", "Neto"], ascending=[False, False])

        missing_inv = int((g["Monto_Invertido"] <= 0).sum())
        if missing_inv > 0:
            st.markdown(
                f'<div class="fin-warn">⚠️ {missing_inv} producto(s) sin inversión asignada en hoja <b>Inversiones</b>.</div>',
                unsafe_allow_html=True,
            )

        for _, r in g.iterrows():
            prod = str(r["Producto"])
            unids = int(r["Unidades"])
            ingreso = float(r["Ingreso"])
            neto = float(r["Neto"])
            cogs = float(r["COGS"])
            ganancia = float(r["Ganancia"])
            margen = float(r["Margen_Pct"])
            roi = float(r["ROI_Pct"])
            invv = float(r["Monto_Invertido"])
            pct_rec = max(0.0, min(100.0, (neto / invv * 100) if invv > 0 else 0.0))
            prog_text = f"{money(neto)} / {money(invv)}" if invv > 0 else "Sin inversión asignada"
            faltante_rec, neto_prom_prenda, prendas_faltantes = _calc_recuperacion_prendas(
                invv,
                neto,
                unids,
            )
            faltante_text = money(faltante_rec) if invv > 0 else "—"
            prendas_faltantes_text = "—" if prendas_faltantes is None else f"{prendas_faltantes:,}"

            with st.expander(f"{prod} · {unids} unidades vendidas", expanded=False):
                st.markdown(
                    f"""
                    <div class="fin-prog-label">
                      <span>Progreso de recuperación</span>
                      <span>{prog_text}</span>
                    </div>
                    <div class="fin-bar-track-sm">
                      <div class="fin-bar-fill-sm" style="width:{pct_rec:.1f}%"></div>
                    </div>
                    <div class="fin-metrics-grid">
                      <div class="fin-metric-block">
                        <span class="fin-metric-label">Ingreso</span>
                        <span class="fin-metric-value">{money(ingreso)}</span>
                      </div>
                      <div class="fin-metric-block right">
                        <span class="fin-metric-label">Neto</span>
                        <span class="fin-metric-value">{money(neto)}</span>
                      </div>
                      <div class="fin-metric-block">
                        <span class="fin-metric-label">COGS</span>
                        <span class="fin-metric-value">{money(cogs)}</span>
                      </div>
                      <div class="fin-metric-block right">
                        <span class="fin-metric-label">Margen</span>
                        <span class="fin-metric-value green">{margen:.1f}%</span>
                      </div>
                      <div class="fin-metric-block">
                        <span class="fin-metric-label">Ganancia</span>
                        <span class="fin-metric-value">{money(ganancia)}</span>
                      </div>
                      <div class="fin-metric-block right">
                        <span class="fin-metric-label">ROI</span>
                        <span class="fin-metric-value green">{roi:.1f}%</span>
                      </div>
                      <div class="fin-metric-block">
                        <span class="fin-metric-label">Faltante</span>
                        <span class="fin-metric-value">{faltante_text}</span>
                      </div>
                      <div class="fin-metric-block right">
                        <span class="fin-metric-label">Prendas faltantes</span>
                        <span class="fin-metric-value green">{prendas_faltantes_text}</span>
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                if pct_rec >= 100.0:
                    st.success("¡Inversión recuperada! Cada venta ahora es ganancia pura.")

    st.markdown('<div class="fin-section-title">Métricas Operativas</div>', unsafe_allow_html=True)

    if not cab_f.empty and "Metodo_Pago" in cab_f.columns:
        cab_f["Total_Cobrado"] = pd.to_numeric(cab_f["Total_Cobrado"], errors="coerce").fillna(0.0)

        if active_drop and not lines_f.empty:
            vids_scope = set(lines_f["Venta_ID"].astype(str).unique())
            cab_scope = cab_f[cab_f["Venta_ID"].astype(str).isin(vids_scope)].copy()
        else:
            cab_scope = cab_f.copy()

        pay = (
            cab_scope.groupby("Metodo_Pago", as_index=False)["Total_Cobrado"]
            .sum()
            .sort_values("Total_Cobrado", ascending=False)
        )
        pay_total = float(pay["Total_Cobrado"].sum())

        pay_rows: list[str] = []
        for _, pm in pay.iterrows():
            metodo = _esc(pm["Metodo_Pago"])
            monto = float(pm["Total_Cobrado"])
            pct_bar = (monto / pay_total * 100) if pay_total > 0 else 0.0
            pay_rows.append(
                f'<div class="fin-pay-row">'
                f'  <div class="fin-pay-top">'
                f'    <span class="fin-pay-name">{metodo}</span>'
                f'    <span class="fin-pay-amount">{money(monto)}</span>'
                f'  </div>'
                f'  <div class="fin-pay-bar-track">'
                f'    <div class="fin-pay-bar-fill" style="width:{pct_bar:.1f}%"></div>'
                f'  </div>'
                f'</div>'
            )

        pay_rows_html = "".join(pay_rows)
        st.markdown(
            f'<div class="fin-card">'
            f'  <span class="fin-pay-label">Ventas por método de pago</span>'
            f'  {pay_rows_html}'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        f"""
        <div class="fin-kpi-grid">
          <div class="fin-kpi-tile">
            <span class="fin-kpi-label">Costo Logístico</span>
            <span class="fin-kpi-value red">{pct_logistica:.1f}%</span>
            <span class="fin-kpi-sub">Sobre ventas</span>
          </div>
          <div class="fin-kpi-tile">
            <span class="fin-kpi-label">Descuento Real</span>
            <span class="fin-kpi-value green">{pct_descuento:.1f}%</span>
            <span class="fin-kpi-sub">Por ventas</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
