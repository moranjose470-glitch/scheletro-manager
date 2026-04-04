from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from modules.ui.styles import card
from modules.data.helpers import load_cabecera, load_detalle, load_inversiones


def render_finanzas_page(conn, inv_df_full, APP_TZ, money) -> None:
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
