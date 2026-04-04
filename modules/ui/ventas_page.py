from __future__ import annotations

from datetime import datetime
from itertools import product as iterproduct
from typing import Any, cast
import re

import pandas as pd
import streamlit as st

from modules.core.constants import CAB_REQUIRED, DET_REQUIRED, EG_REQUIRED, SHEET_CATEGORIAS, SHEET_EGRESOS, SHEET_INVENTARIO, SHEET_VENTAS_CAB, SHEET_VENTAS_DET
from modules.data.helpers import (
    _align_required_columns,
    _clean_number,
    _next_egreso_id,
    comision_porcentaje,
    load_cabecera,
    load_catalogos,
    load_categorias,
    load_detalle,
    load_egresos,
    load_inventario,
    next_venta_id,
    parse_catalogos,
    save_sheet,
)
from modules.ui.styles import card, normalize_html


def render_ventas_page(conn, inv_df_full, cfg, APP_TZ, BODEGA_NAME, fmt_bodega, money) -> None:
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

    page_title = "Ventas" if st.session_state.get("ventas_modo", "ventas") == "ventas" else "Egresos"
    st.markdown(
        f"""
        <div class="app-header">
          <div class="app-top-label">SCHELETRO Manager</div>
          <div class="app-page-title">{page_title}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    modo_actual = st.session_state.get("ventas_modo", "ventas")
    modo_sel = st.segmented_control(
        "Modo",
        options=["ventas", "egresos"],
        format_func=lambda x: "Ventas" if x == "ventas" else "Egresos",
        default=modo_actual,
        label_visibility="collapsed",
        key="ventas_modo_seg",
    )
    if modo_sel and modo_sel != modo_actual:
        st.session_state["ventas_modo"] = modo_sel
        st.rerun()
    modo_actual = modo_sel or modo_actual

    if modo_actual == "ventas":
        with card():
            st.markdown("<div class='sche-section-title'>Bodega de salida</div>", unsafe_allow_html=True)
            bodega_venta = st.session_state.get("bodega_venta", "Casa")
            bodega_sel = st.segmented_control(
                "Bodega",
                options=["Casa", "Bodega"],
                default=bodega_venta,
                label_visibility="collapsed",
                key="bodega_seg",
            )
            if bodega_sel and bodega_sel != bodega_venta:
                st.session_state["bodega_venta"] = bodega_sel
                st.rerun()
            bodega_venta = bodega_sel or bodega_venta

        with card():
            st.markdown("<div class='sche-section-title'>Agregar producto</div>", unsafe_allow_html=True)

            productos = sorted([p for p in inv_activo["Producto"].dropna().unique().tolist() if str(p).strip()])
            producto_sel = st.selectbox("Producto", productos, index=0)

            df_p = inv_activo[inv_activo["Producto"] == producto_sel].copy()
            ccol, tcol = st.columns(2)
            with ccol:
                colores = sorted([c for c in df_p["Color"].dropna().unique().tolist() if str(c).strip()])
                color_sel = st.selectbox("Color", colores, index=0)
            with tcol:
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

            st.markdown(
                f"<div class='sku-band'><span class='sku'>{sku}</span><span class='price'>{money(precio_unit)}</span></div>",
                unsafe_allow_html=True,
            )

            cols = st.columns(2)
            with cols[0]:
                qty = st.number_input("Cantidad", min_value=1, max_value=max(1, stock_disp), value=1, step=1)
            with cols[1]:
                desc_u = st.number_input("Descuento unitario ($)", min_value=0.0, value=0.0, step=0.50, format="%.2f")

            if desc_u > precio_unit:
                st.warning("⚠️ El descuento unitario no puede ser mayor al precio unitario. Se ajustará.")
                desc_u = precio_unit

            subtotal_linea = round((precio_unit - desc_u) * int(qty), 2)
            st.markdown(
                f"<div class='small-note'>Bodega: <span class='pill'><b>{fmt_bodega(bodega_venta)}</b></span> · Subtotal: <b>{money(subtotal_linea)}</b></div>",
                unsafe_allow_html=True,
            )

            add_btn = st.button("➕ Añadir al carrito", use_container_width=True, disabled=(stock_disp <= 0), key="add_to_cart")
            if add_btn:
                cart = cast(list[dict[str, Any]], st.session_state["cart"])
                cart.append(
                    {
                        "SKU": sku,
                        "Drop": drop,
                        "Producto": producto_sel,
                        "Color": color_sel,
                        "Talla": talla_sel,
                        "Bodega_Salida": bodega_venta,
                        "Cantidad": int(qty),
                        "Precio_Unitario": float(precio_unit),
                        "Descuento_Unitario": float(desc_u),
                        "Subtotal_Linea": float(subtotal_linea),
                    }
                )
                st.session_state["cart"] = cart
                st.success("Agregado al carrito.")

        cart = cast(list[dict[str, Any]], st.session_state["cart"])
        with card():
            st.markdown("<div class='sche-section-title'>Carrito</div>", unsafe_allow_html=True)
            if not cart:
                st.caption("Aún no has agregado productos.")
            else:
                for i, item in enumerate(cart, start=1):
                    c1, c2 = st.columns([6, 2])
                    with c1:
                        st.markdown(f"<div class='cart-item-title'>{item['Producto']}</div>", unsafe_allow_html=True)
                        st.markdown(
                            f"<div class='cart-item-details'>{item['Color']} · {item['Talla']} · Qty: {item['Cantidad']} · <span class='cart-item-price'>{money(item['Subtotal_Linea'])}</span></div>",
                            unsafe_allow_html=True,
                        )
                        st.caption(f"SKU: {item['SKU']} · Bodega: {fmt_bodega(str(item['Bodega_Salida']))}")
                    with c2:
                        if st.button("🗑️ Quitar", key=f"rm_{i}_{item['SKU']}"):
                            cart.pop(i - 1)
                            st.session_state["cart"] = cart
                            st.rerun()

                if st.button("🧹 Vaciar carrito", use_container_width=True, key="vaciar_carrito_btn"):
                    st.session_state["cart"] = []
                    st.rerun()

        with card():
            st.markdown("<div class='sche-section-title'>Datos de venta</div>", unsafe_allow_html=True)
            cliente = st.text_input("Cliente", placeholder="Nombre del cliente", key="cliente")
            notas = st.text_area("Notas (opcional)", placeholder="Ej: entregar hoy, referencia, etc.", key="notas")

            metodo_pago = st.selectbox(
                "Método de pago",
                options=["Transferencia", "Efectivo", "Tarjeta", "Contra Entrega"],
                key="metodo_pago",
            )

            cc1, cc2 = st.columns(2)
            with cc1:
                envio_cliente = st.number_input(
                    "Envío cobrado al cliente ($)",
                    min_value=0.0,
                    step=0.50,
                    format="%.2f",
                    key="envio_cliente",
                )
            with cc2:
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

        total_lineas = round(sum(float(x["Subtotal_Linea"]) for x in cart), 2) if cart else 0.0
        total_cobrado = round(total_lineas + float(envio_cliente), 2)

        com_porc = comision_porcentaje(metodo_pago, cfg, override_pce)
        com_monto = round(total_cobrado * float(com_porc), 2)
        monto_a_recibir = round(total_cobrado - float(costo_courier) - com_monto, 2)
        monto_class = "gain-ok" if monto_a_recibir >= 0 else "gain-low"

        with card():
            st.markdown("<div class='sche-section-title'>Resumen</div>", unsafe_allow_html=True)
            raw_html = f"""
            <div class="summary-grid">
              <div class="summary-row"><div class="summary-label">Subtotal productos</div><div class="summary-value">{money(total_lineas)}</div></div>
              <div class="summary-row"><div class="summary-label">Envío cobrado</div><div class="summary-value">{money(envio_cliente)}</div></div>
              <div class="summary-row total-cobrado"><div>Total cobrado</div><div>{money(total_cobrado)}</div></div>
              <div class="divider"></div>
              <div class="summary-row"><div class="summary-label">Costo courier</div><div class="summary-value">{money(costo_courier)}</div></div>
              <div class="summary-row"><div class="summary-label">Comisión ({com_porc*100:.2f}%)</div><div class="summary-value">{money(com_monto)}</div></div>
              <div class="divider"></div>
              <div class="summary-row monto-recibir"><div>Monto a recibir</div><div class="{monto_class}">{money(monto_a_recibir)}</div></div>
            </div>
            """
            st.markdown(normalize_html(raw_html), unsafe_allow_html=True)

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

        save_btn = st.button("✅ REGISTRAR VENTA", use_container_width=True, disabled=not can_save, key="registrar_venta")
        if save_btn:
            try:
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
                bodega_label = fmt_bodega(bodega_venta)
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

                cab_df = _align_required_columns(cab_df, CAB_REQUIRED)
                cab_out = pd.concat([cab_df, pd.DataFrame([cab_row])], ignore_index=True)
                cab_out = _align_required_columns(cab_out, CAB_REQUIRED)
                save_sheet(conn, SHEET_VENTAS_CAB, cab_out)

                det_df = _align_required_columns(det_df, DET_REQUIRED)
                det_out = pd.concat([det_df, pd.DataFrame(det_rows)], ignore_index=True)
                det_out = _align_required_columns(det_out, DET_REQUIRED)
                save_sheet(conn, SHEET_VENTAS_DET, det_out)

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
                st.cache_data.clear()
                st.session_state["_reset_sale_pending"] = True
                st.rerun()
            except Exception as e:
                st.error("Error al registrar la venta.")
                st.exception(e)

    else:
        try:
            egresos_df_full = load_egresos(conn, ttl_s=45)
        except Exception as e:
            egresos_df_full = _align_required_columns(pd.DataFrame(), EG_REQUIRED)
            st.warning(f"No pude leer la hoja 'Egresos'. Detalle: {e}")

        # === NUEVO: Cargar categorías desde hoja maestra ===
        try:
            categorias_df = load_categorias(conn, ttl_s=60)
            categorias_list = sorted({
                c for c in categorias_df["Categoria"].dropna().astype(str).str.strip().unique().tolist()
                if c and c.lower() != "nan"
            })
        except Exception:
            categorias_list = []
        
        try:
            cat_df = load_catalogos(conn, ttl_s=600)
            cat = parse_catalogos(cat_df)
            drops_cat = cat.get("drops", []) or []
        except Exception:
            drops_cat = []

        def _pretty_drop_label(v: str) -> str:
            v = str(v or "").strip()
            m = re.match(r"^D(\d{3})$", v.upper())
            if m:
                return f"DROP {int(m.group(1)):02d}"
            if v.upper().startswith("DROP"):
                return v
            return v if v else "(Sin drop)"

        drop_pairs = [("(Sin drop)", "")]
        for d in drops_cat:
            val = (d.get("valor") or "").strip()
            if not val:
                continue
            drop_pairs.append((_pretty_drop_label(val), val))

        seen = set()
        drop_pairs_uniq = []
        for lab, val in drop_pairs:
            if val in seen:
                continue
            seen.add(val)
            drop_pairs_uniq.append((lab, val))
        drop_pairs = drop_pairs_uniq

        ss = st.session_state

        st.markdown('<div class="eg-card">', unsafe_allow_html=True)
        st.markdown('<div class="eg-h1">Agregar un gasto</div>', unsafe_allow_html=True)
        ss["eg_concepto"] = st.text_input(
            "Concepto",
            value=ss["eg_concepto"],
            placeholder="Ej: Publicidad",
            key="eg_concepto_input",
        )

        c_amt, c_icon = st.columns([8, 1])
        with c_amt:
            st.markdown('<div class="eg-label">Monto</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div class="eg-amount"><small>$</small> {ss["eg_monto"]:,.2f}</div>',
                unsafe_allow_html=True,
            )
        with c_icon:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            st.markdown("🧮")

        ss["eg_monto"] = st.number_input(
            "Monto",
            min_value=0.0,
            step=0.50,
            format="%.2f",
            value=float(ss["eg_monto"] or 0.0),
            key="eg_monto_input",
            label_visibility="collapsed",
        )

        can_save_eg = (float(ss["eg_monto"] or 0.0) > 0) and bool((ss["eg_concepto"] or "").strip())
        if st.button("+ Registrar Gasto", use_container_width=True, disabled=not can_save_eg, key="eg_guardar_btn"):
            st.cache_data.clear()
            eg_fresh = load_egresos(conn, ttl_s=0)
            new_id = _next_egreso_id(eg_fresh)
            row = {
                "Egreso_ID": new_id,
                "Fecha": str(ss["eg_fecha"]),
                "Concepto": (ss["eg_concepto"] or "").strip(),
                "Categoria": "" if ss["eg_categoria_sel"] == "(Sin categoría)" else (ss["eg_categoria_sel"] or "").strip(),
                "Monto": float(ss["eg_monto"] or 0.0),
                "Notas": (ss["eg_notas"] or "").strip(),
                "Drop": (ss["eg_drop_sel"] or "").strip(),
            }
            eg_out = pd.concat([eg_fresh, pd.DataFrame([row])], ignore_index=True)
            save_sheet(conn, SHEET_EGRESOS, eg_out)

            # === LIMPIEZA COMPLETA DESPUÉS DE GUARDAR ===
            # 1) Eliminar claves de widgets para forzar limpieza visual
            for k in ["eg_monto_input", "eg_concepto_input", "eg_notas_input", 
                      "eg_drop_select", "eg_categoria_sel_input", "eg_fecha_input"]:
                if k in st.session_state:
                    del st.session_state[k]
            # 2) Resetear variables de sesión
            ss["eg_monto"] = 0.0
            ss["eg_concepto"] = ""
            ss["eg_notas"] = ""
            ss["eg_drop_sel"] = ""
            ss["eg_categoria_sel"] = "(Sin categoría)"
            ss["eg_fecha"] = datetime.now(APP_TZ).date()
            # 3) Guardar mensaje de éxito en flag para mostrar después del rerun
            st.session_state["_eg_toast"] = f"Egreso guardado: {new_id}"
            st.rerun()

        st.markdown('</div>', unsafe_allow_html=True)

        # Mostrar toast si existe (después del rerun)
        if st.session_state.get("_eg_toast"):
            st.toast(st.session_state["_eg_toast"], icon="✅")
            del st.session_state["_eg_toast"]

        with st.expander("Más detalles", expanded=False):
            ss["eg_fecha"] = st.date_input("Fecha", value=ss["eg_fecha"], key="eg_fecha_input")

            st.markdown("**Categoría**")
            cat_cols = st.columns([7, 3])
            with cat_cols[0]:
                # Usar categorias_list (desde hoja Categorias) en lugar de solo las existentes en Egresos
                cat_opts = ["(Sin categoría)"] + categorias_list
                if ss["eg_categoria_sel"] not in cat_opts:
                    cat_opts = cat_opts + [ss["eg_categoria_sel"]]
                ss["eg_categoria_sel"] = st.selectbox(
                    "Categoría",
                    options=cat_opts,
                    index=cat_opts.index(ss["eg_categoria_sel"]) if ss["eg_categoria_sel"] in cat_opts else 0,
                    key="eg_categoria_sel_input",
                    label_visibility="collapsed",
                )
            with cat_cols[1]:
                ss["eg_categoria_new"] = st.text_input(
                    "Nueva",
                    value=ss["eg_categoria_new"],
                    placeholder="Nueva",
                    key="eg_categoria_new_input",
                    label_visibility="collapsed",
                )
                # Botón ➕ ahora guarda en hoja Categorias
                if st.button("➕", key="eg_cat_add_btn", use_container_width=True, help="Agregar y seleccionar"):
                    nueva = (ss["eg_categoria_new"] or "").strip()
                    if nueva and nueva not in categorias_list:
                        # Guardar en la hoja Categorias
                        cat_df = load_categorias(conn, ttl_s=0)
                        nueva_fila = pd.DataFrame([{"Categoria": nueva}])
                        cat_out = pd.concat([cat_df, nueva_fila], ignore_index=True)
                        save_sheet(conn, SHEET_CATEGORIAS, cat_out)
                        st.cache_data.clear()
                        ss["eg_categoria_sel"] = nueva
                        ss["eg_categoria_new"] = ""
                        st.rerun()

            drop_labels = [lab for lab, _ in drop_pairs]
            drop_values = [val for _, val in drop_pairs]
            drop_idx = 0
            if ss["eg_drop_sel"] in drop_values:
                drop_idx = drop_values.index(ss["eg_drop_sel"])

            drop_label = st.selectbox(
                "Drop",
                options=drop_labels,
                index=drop_idx,
                key="eg_drop_select",
            )
            ss["eg_drop_sel"] = drop_pairs[drop_labels.index(drop_label)][1]

            ss["eg_notas"] = st.text_area(
                "Notas",
                value=ss["eg_notas"],
                placeholder="Detalles adicionales",
                key="eg_notas_input",
            )

        st.markdown('<div class="eg-card">', unsafe_allow_html=True)
        st.markdown('<div class="eg-h1">Últimos movimientos</div>', unsafe_allow_html=True)
        if egresos_df_full.empty:
            st.caption("Aún no hay movimientos registrados.")
        else:
            eg_show = egresos_df_full.copy()
            eg_show["_fecha_dt"] = pd.to_datetime(eg_show["Fecha"], errors="coerce", dayfirst=True)
            eg_show = eg_show.sort_values("_fecha_dt", ascending=False).head(5)
            for _, row in eg_show.iterrows():
                st.markdown(
                    f'<div class="movimiento-item"><div><div class="movimiento-concepto">{row["Concepto"]}</div><div class="movimiento-fecha">{row["Fecha"]}</div></div><div class="movimiento-monto">{money(-float(row["Monto"]))}</div></div>',
                    unsafe_allow_html=True,
                )
        st.markdown('</div>', unsafe_allow_html=True)