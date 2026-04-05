from __future__ import annotations

from datetime import datetime
from typing import Any, cast
import re

import pandas as pd
import streamlit as st

from modules.core.constants import (
    CAB_REQUIRED, DET_REQUIRED, EG_REQUIRED,
    SHEET_CATEGORIAS, SHEET_EGRESOS, SHEET_INVENTARIO,
    SHEET_VENTAS_CAB, SHEET_VENTAS_DET,
)
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
from modules.ui.styles import money, normalize_html


def _inject_ventas_css() -> None:
    st.markdown("""
    <style>
      :root {
        --v-bg:       #000000;
        --v-card:     rgba(23,23,23,0.5);
        --v-card-s:   #171717;
        --v-border:   rgba(38,38,38,1);
        --v-primary:  #10b981;
        --v-text:     #ffffff;
        --v-muted:    #737373;
        --v-muted2:   #525252;
        --v-input:    #262626;
        --v-danger:   #f87171;
        --v-warn-bg:  rgba(249,115,22,0.1);
        --v-warn-bdr: rgba(249,115,22,0.2);
        --v-warn-txt: #fb923c;
      }

      /* ── Section titles ── */
      .v-section-title {
        font-size: 1.05rem;
        font-weight: 600;
        color: var(--v-text);
        margin-bottom: 14px;
      }

      /* ── Card ── */
      .v-card {
        background: var(--v-card);
        border: 1px solid var(--v-border);
        border-radius: 20px;
        padding: 20px;
        margin-bottom: 20px;
      }

      /* ── Field label ── */
      .v-label {
        font-size: 0.65rem;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--v-muted);
        display: block;
        margin-bottom: 6px;
      }

      /* ── Bodega pills ── */
      .v-bodega-row { display: flex; gap: 10px; margin-bottom: 4px; }
      .v-bodega-pill {
        flex: 1;
        text-align: center;
        padding: 14px;
        border-radius: 14px;
        background: #171717;
        border: 1px solid transparent;
        font-size: 0.82rem;
        font-weight: 500;
        color: var(--v-muted);
        cursor: pointer;
        transition: all 0.15s;
      }
      .v-bodega-pill.active {
        border-color: var(--v-primary);
        background: rgba(16,185,129,0.1);
        color: var(--v-primary);
        font-weight: 700;
      }

      /* ── SKU band ── */
      .v-sku-band {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 10px 0;
        margin: 8px 0;
      }
      .v-sku-group { display: flex; flex-direction: column; }
      .v-sku-micro {
        font-size: 0.58rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--v-muted);
        margin-bottom: 2px;
      }
      .v-sku-code { font-size: 0.75rem; font-family: monospace; color: #d4d4d4; }
      .v-price-group { display: flex; flex-direction: column; align-items: flex-end; }
      .v-price-big { font-size: 1.15rem; font-weight: 700; color: var(--v-primary); }

      /* ── Bodega + subtotal footer ── */
      .v-cart-footer {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding-top: 10px;
        border-top: 1px solid var(--v-border);
        margin-top: 5px;
        margin-bottom: 20px;
      }
      .v-cart-footer-left { display: flex; align-items: center; gap: 6px; font-size: 0.78rem; color: var(--v-muted); }
      .v-cart-footer-right { font-size: 0.92rem; font-weight: 700; color: var(--v-text); }
      .v-cart-footer-right span { font-size: 0.72rem; color: var(--v-muted); margin-right: 6px; }

      /* ── Warning banner ── */
      .v-warn {
        background: var(--v-warn-bg);
        border: 1px solid var(--v-warn-bdr);
        border-radius: 12px;
        padding: 10px 14px;
        display: flex;
        align-items: center;
        gap: 10px;
        font-size: 0.78rem;
        font-weight: 500;
        color: var(--v-warn-txt);
        margin-bottom: 8px;
      }

      /* ── Cart item ── */
      .v-cart-item {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 14px 16px;
        background: rgba(23,23,23,0.4);
        border: 1px solid transparent;
        border-radius: 16px;
        margin-bottom: 8px;
      }
      .v-cart-item-name { font-size: 0.88rem; font-weight: 600; color: var(--v-text); }
      .v-cart-item-meta { font-size: 0.7rem; color: var(--v-muted); margin-top: 2px; }
      .v-cart-badge {
        background: rgba(16,185,129,0.15);
        color: var(--v-primary);
        font-size: 0.6rem;
        font-weight: 700;
        padding: 3px 8px;
        border-radius: 6px;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        margin-left: 8px;
      }

      /* ── Resumen card ── */
      .v-resumen-card {
        background: #171717;
        border-radius: 24px;
        padding: 24px;
        margin-bottom: 20px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.4);
        border: 1px solid rgba(255,255,255,0.05);
      }
      .v-resumen-title { font-size: 0.88rem; font-weight: 500; color: var(--v-muted); margin-bottom: 20px; }
      .v-resumen-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 10px;
      }
      .v-resumen-label { font-size: 0.82rem; color: var(--v-muted); }
      .v-resumen-value { font-size: 0.82rem; font-weight: 600; color: var(--v-text); }
      .v-resumen-divider { height: 1px; background: var(--v-border); margin: 10px 0; }
      .v-resumen-total-label { font-size: 0.82rem; font-weight: 700; color: var(--v-text); }
      .v-resumen-total-val   { font-size: 0.82rem; font-weight: 700; color: var(--v-text); }
      .v-resumen-red { color: var(--v-danger) !important; }
      .v-monto-box {
        background: rgba(16,185,129,0.1);
        border: 1px solid rgba(16,185,129,0.2);
        border-radius: 16px;
        padding: 20px;
        text-align: center;
        margin-top: 20px;
      }
      .v-monto-label {
        font-size: 0.65rem;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.18em;
        color: rgba(16,185,129,0.8);
        display: block;
        margin-bottom: 4px;
      }
      .v-monto-value { font-size: 2.5rem; font-weight: 900; color: var(--v-primary); letter-spacing: -0.02em; }
      .v-monto-value.red { color: var(--v-danger); }

      /* ── CTA button ── */
      .v-cta-btn {
        width: 100%;
        padding: 18px;
        border-radius: 16px;
        border: none;
        background: var(--v-primary);
        color: #000;
        font-size: 1.05rem;
        font-weight: 900;
        letter-spacing: 0.01em;
        cursor: pointer;
        box-shadow: 0 8px 24px rgba(16,185,129,0.25);
        margin-bottom: 20px;
      }

      /* ── Egresos ── */
      .eg-summary-card {
        background: #171717;
        border-radius: 18px;
        padding: 24px;
        margin-bottom: 20px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.4);
        border: 1px solid rgba(255,255,255,0.05);
      }
      .eg-summary-label { font-size: 0.78rem; font-weight: 500; color: var(--v-muted); margin-bottom: 4px; }
      .eg-summary-sublabel { font-size: 0.72rem; color: var(--v-muted); margin-bottom: 4px; }
      .eg-summary-total { font-size: 2.2rem; font-weight: 700; letter-spacing: -0.02em; color: var(--v-text); }

      .eg-form-card {
        background: var(--v-card);
        border: 1px solid var(--v-border);
        border-radius: 20px;
        padding: 20px;
        margin-bottom: 20px;
      }

      .eg-cat-chip-row {
        display: flex;
        gap: 10px;
        overflow-x: auto;
        padding-bottom: 6px;
        margin-bottom: 16px;
        scrollbar-width: none;
      }
      .eg-cat-chip {
        flex-shrink: 0;
        display: flex;
        flex-direction: column;
        align-items: center;
        padding: 14px 16px;
        background: #171717;
        border-radius: 16px;
        min-width: 90px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.4);
        border: 1px solid rgba(255,255,255,0.05);
      }
      .eg-cat-icon {
        width: 40px; height: 40px;
        border-radius: 12px;
        display: flex; align-items: center; justify-content: center;
        font-size: 1.1rem;
        margin-bottom: 8px;
      }
      .eg-cat-name  { font-size: 0.68rem; color: var(--v-muted); font-weight: 500; }
      .eg-cat-total { font-size: 1rem; font-weight: 700; color: var(--v-text); margin-top: 2px; }

      .eg-tx-item {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 14px 16px;
        background: rgba(23,23,23,0.4);
        border-radius: 16px;
        margin-bottom: 8px;
        border: 1px solid transparent;
      }
      .eg-tx-icon-wrap {
        width: 40px; height: 40px;
        border-radius: 50%;
        background: var(--v-input);
        display: flex; align-items: center; justify-content: center;
        font-size: 1rem;
        margin-right: 14px;
        flex-shrink: 0;
      }
      .eg-tx-concept { font-size: 0.88rem; font-weight: 500; color: var(--v-text); }
      .eg-tx-meta    { font-size: 0.7rem; color: var(--v-muted); margin-top: 2px; }
      .eg-tx-amount  { font-size: 0.88rem; font-weight: 600; color: var(--v-danger); white-space: nowrap; margin-left: 14px; }
    </style>
    """, unsafe_allow_html=True)


def render_ventas_page(
    conn,           # GSheetsConnection — de get_conn() en app.py
    inv_df_full,    # DataFrame — de load_inventario() en app.py
    cfg,            # dict — de load_config() en app.py
    APP_TZ,         # ZoneInfo — timezone de Config sheet
    BODEGA_NAME,    # dict {"Casa": nombre, "Bodega": nombre} — de cfg en app.py
    fmt_bodega,     # función — definida en app.py, usa BODEGA_NAME
    money,          # función — de modules/ui/styles.py, formatea a $0.00
) -> None:

    _inject_ventas_css()

    inv_df = inv_df_full

    if inv_df is None or inv_df.empty:
        st.warning("No pude cargar el Inventario desde Google Sheets (si viste 429, esperá 60–90s).")
        st.stop()

    inv_activo = inv_df[inv_df["Activo"] == True].copy()
    if inv_activo.empty and len(inv_df) > 0:
        st.warning("Tu inventario tiene filas, pero el filtro 'Activo' quedó en 0. Permito ventas usando TODOS los SKUs.")
        inv_activo = inv_df.copy()

    if inv_activo.empty:
        st.warning("Tu Inventario está vacío o todo está inactivo.")
        st.stop()

    # ── Modo toggle (Ventas / Egresos) ────────────────────────────
    if "ventas_modo" not in st.session_state:
        st.session_state["ventas_modo"] = "ventas"

    modo_actual = st.session_state["ventas_modo"]

    with st.container():
        st.markdown('<div class="ventas-mode-nav-marker"></div>', unsafe_allow_html=True)
        m1, m2 = st.columns(2)

        with m1:
            cls = "ventas-mode-state active" if modo_actual == "ventas" else "ventas-mode-state"
            st.markdown(f'<div class="{cls}"></div>', unsafe_allow_html=True)
            if st.button("🛒  Ventas", key="ventas_modo_btn_ventas", use_container_width=True):
                if modo_actual != "ventas":
                    st.session_state["ventas_modo"] = "ventas"
                    st.rerun()

        with m2:
            cls = "ventas-mode-state active" if modo_actual == "egresos" else "ventas-mode-state"
            st.markdown(f'<div class="{cls}"></div>', unsafe_allow_html=True)
            if st.button("💸  Egresos", key="ventas_modo_btn_egresos", use_container_width=True):
                if modo_actual != "egresos":
                    st.session_state["ventas_modo"] = "egresos"
                    st.rerun()

    modo_actual = st.session_state["ventas_modo"]

    # ══════════════════════════════════════════════════════════════
    # MODO: VENTAS
    # ══════════════════════════════════════════════════════════════
    if modo_actual == "ventas":

        # ── 1. Bodega de Salida ───────────────────────────────────
        st.markdown('<div class="v-section-title">Bodega de Salida</div>', unsafe_allow_html=True)

        if "bodega_venta" not in st.session_state:
            st.session_state["bodega_venta"] = "Casa"

        bodega_venta = st.session_state["bodega_venta"]

        with st.container():
            st.markdown('<div class="bodega-sel-nav-marker"></div>', unsafe_allow_html=True)
            b1, b2 = st.columns(2)

            with b1:
                cls = "bodega-sel-state active" if bodega_venta == "Casa" else "bodega-sel-state"
                st.markdown(f'<div class="{cls}"></div>', unsafe_allow_html=True)
                if st.button(fmt_bodega("Casa"), key="bodega_btn_casa", use_container_width=True):
                    if bodega_venta != "Casa":
                        st.session_state["bodega_venta"] = "Casa"
                        st.rerun()

            with b2:
                cls = "bodega-sel-state active" if bodega_venta == "Bodega" else "bodega-sel-state"
                st.markdown(f'<div class="{cls}"></div>', unsafe_allow_html=True)
                if st.button(fmt_bodega("Bodega"), key="bodega_btn_bodega", use_container_width=True):
                    if bodega_venta != "Bodega":
                        st.session_state["bodega_venta"] = "Bodega"
                        st.rerun()

        bodega_venta = st.session_state["bodega_venta"]

        # ── 2. Agregar Producto ───────────────────────────────────
        st.markdown('<div class="v-section-title" style="margin-top:20px">Agregar Producto</div>', unsafe_allow_html=True)

        st.markdown('<span class="v-label">Producto</span>', unsafe_allow_html=True)
        productos = sorted([p for p in inv_activo["Producto"].dropna().unique().tolist() if str(p).strip()])
        producto_sel = st.selectbox("Producto", productos, index=0, label_visibility="collapsed")

        df_p = inv_activo[inv_activo["Producto"] == producto_sel].copy()
        ccol, tcol = st.columns(2)
        with ccol:
            st.markdown('<span class="v-label">Color</span>', unsafe_allow_html=True)
            colores = sorted([c for c in df_p["Color"].dropna().unique().tolist() if str(c).strip()])
            color_sel = st.selectbox("Color", colores, index=0, label_visibility="collapsed")
        with tcol:
            st.markdown('<span class="v-label">Talla</span>', unsafe_allow_html=True)
            df_pc = df_p[df_p["Color"] == color_sel].copy()
            tallas = sorted([t for t in df_pc["Talla"].dropna().unique().tolist() if str(t).strip()])
            talla_sel = st.selectbox("Talla", tallas, index=0, label_visibility="collapsed")

        df_pct = df_pc[df_pc["Talla"] == talla_sel].copy()
        if df_pct.empty:
            st.error("No encontré esa variante en inventario.")
            st.stop()

        row = df_pct.iloc[0]
        sku        = str(row["SKU"]).strip()
        drop       = str(row["Drop"]).strip()
        precio_unit = float(_clean_number(row["Precio_Lista"]))
        stock_casa   = int(_clean_number(row["Stock_Casa"]))
        stock_bodega = int(_clean_number(row["Stock_Bodega"]))
        stock_disp   = stock_casa if bodega_venta == "Casa" else stock_bodega

        # Warning banner
        if stock_disp <= 0:
            st.markdown(f'<div class="v-warn">⚠️ AGOTADO en {fmt_bodega(bodega_venta)}</div>', unsafe_allow_html=True)
        elif stock_disp <= 2:
            st.markdown(f'<div class="v-warn">⚠️ Pocas unidades en {fmt_bodega(bodega_venta)}</div>', unsafe_allow_html=True)

        # SKU + precio
        st.markdown(
            f'<div class="v-sku-band">'
            f'<div class="v-sku-group">'
            f'<span class="v-sku-micro">SKU</span>'
            f'<span class="v-sku-code">{sku}</span>'
            f'</div>'
            f'<div class="v-price-group">'
            f'<span class="v-sku-micro">Precio</span>'
            f'<span class="v-price-big">{money(precio_unit)}</span>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Cantidad + descuento
        q_col, d_col = st.columns(2)
        with q_col:
            st.markdown('<span class="v-label">Cantidad</span>', unsafe_allow_html=True)
            qty = st.number_input("Cantidad", min_value=1, max_value=max(1, stock_disp),
                                  value=1, step=1, label_visibility="collapsed")
        with d_col:
            st.markdown('<span class="v-label">Descuento unit. ($)</span>', unsafe_allow_html=True)
            desc_u = st.number_input("Descuento", min_value=0.0, value=0.0, step=0.50,
                                     format="%.2f", label_visibility="collapsed")

        if desc_u > precio_unit:
            st.warning("El descuento no puede superar el precio unitario.")
            desc_u = precio_unit

        subtotal_linea = round((precio_unit - desc_u) * int(qty), 2)

        # Bodega + subtotal footer
        st.markdown(
            f'<div class="v-cart-footer">'
            f'<div class="v-cart-footer-left">🏠 {fmt_bodega(bodega_venta)}</div>'
            f'<div class="v-cart-footer-right"><span>Subtotal</span>{money(subtotal_linea)}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        add_btn = st.button("🛒  + Añadir al carrito", use_container_width=True,
                            disabled=(stock_disp <= 0), key="add_to_cart",
                            type="secondary")
        if add_btn:
            cart_list = cast(list[dict[str, Any]], st.session_state["cart"])
            cart_list.append({
                "SKU": sku, "Drop": drop, "Producto": producto_sel,
                "Color": color_sel, "Talla": talla_sel,
                "Bodega_Salida": bodega_venta,
                "Cantidad": int(qty),
                "Precio_Unitario": float(precio_unit),
                "Descuento_Unitario": float(desc_u),
                "Subtotal_Linea": float(subtotal_linea),
            })
            st.session_state["cart"] = cart_list
            st.toast("Agregado al carrito ✅")


        # ── 3. Carrito ────────────────────────────────────────────
        cart = cast(list[dict[str, Any]], st.session_state["cart"])
        n_items = len(cart)

        cart_title_html = (
            f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:14px">'
            f'<span class="v-section-title" style="margin-bottom:0">Carrito</span>'
            f'{"<span class=\'v-cart-badge\'>" + str(n_items) + " ITEM" + ("S" if n_items != 1 else "") + "</span>" if n_items > 0 else ""}'
            f'</div>'
        )
        st.markdown(cart_title_html, unsafe_allow_html=True)

        if not cart:
            st.caption("Aún no has agregado productos.")
        else:
            for i, item in enumerate(cart, start=1):
                c_left, c_right = st.columns([6, 2])
                with c_left:
                    color_str = f" · {item['Color']}" if str(item['Color']).lower() not in ("", "standard", "nan") else ""
                    st.markdown(
                        f'<div class="v-cart-item">'
                        f'<div>'
                        f'<div class="v-cart-item-name">{item["Producto"]}{color_str} · {item["Talla"]}</div>'
                        f'<div class="v-cart-item-meta">Cant: {item["Cantidad"]} · {money(item["Subtotal_Linea"])} · {fmt_bodega(str(item["Bodega_Salida"]))}</div>'
                        f'</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                with c_right:
                    if st.button("Quitar", key=f"rm_{i}_{item['SKU']}", use_container_width=True):
                        cart.pop(i - 1)
                        st.session_state["cart"] = cart
                        st.rerun()

            if st.button("🧹 Vaciar carrito", use_container_width=True, key="vaciar_carrito_btn"):
                st.session_state["cart"] = []
                st.rerun()

        # ── 4. Datos de venta ──────────────────────────────────────
        st.markdown('<div class="v-section-title" style="margin-top:20px">Datos de venta</div>', unsafe_allow_html=True)

        st.markdown('<span class="v-label">Nombre del cliente</span>', unsafe_allow_html=True)
        cliente = st.text_input("Cliente", placeholder="Escribe el nombre completo...",
                                key="cliente", label_visibility="collapsed")

        st.markdown('<span class="v-label">Notas (opcional)</span>', unsafe_allow_html=True)
        notas = st.text_area("Notas", placeholder="Información adicional sobre la venta...",
                             key="notas", label_visibility="collapsed")

        st.markdown('<span class="v-label">Método de pago</span>', unsafe_allow_html=True)
        metodo_pago = st.selectbox(
            "Método de pago",
            options=["Transferencia", "Efectivo", "Tarjeta", "Contra Entrega"],
            key="metodo_pago", label_visibility="collapsed",
        )

        cc1, cc2 = st.columns(2)
        with cc1:
            st.markdown('<span class="v-label">Envío cobrado ($)</span>', unsafe_allow_html=True)
            envio_cliente = st.number_input("Envío", min_value=0.0, step=0.50, format="%.2f",
                                            key="envio_cliente", label_visibility="collapsed")
        with cc2:
            st.markdown('<span class="v-label">Costo real courier ($)</span>', unsafe_allow_html=True)
            costo_courier = st.number_input("Courier", min_value=0.0, step=0.50, format="%.2f",
                                            key="costo_courier", label_visibility="collapsed")

        override_pce: float | None = None
        if metodo_pago == "Contra Entrega":
            st.markdown("**Comisión PCE (Contra Entrega)**")
            pce_mode = st.radio("Comisión", ["2.99%", "Otro"], horizontal=True, key="pce_mode")
            if pce_mode == "Otro":
                p_val = st.number_input("Porcentaje PCE (%)", min_value=0.0, step=0.10,
                                        format="%.2f", key="pce_otro")
                override_pce = float(p_val) / 100.0


        # ── 5. Resumen ────────────────────────────────────────────
        total_lineas    = round(sum(float(x["Subtotal_Linea"]) for x in cart), 2) if cart else 0.0
        total_cobrado   = round(total_lineas + float(envio_cliente), 2)
        com_porc        = comision_porcentaje(metodo_pago, cfg, override_pce)
        com_monto       = round(total_cobrado * float(com_porc), 2)
        monto_a_recibir = round(total_cobrado - float(costo_courier) - com_monto, 2)
        monto_class     = "" if monto_a_recibir >= 0 else "red"

        st.markdown(
            f'<div class="v-resumen-card">'
            f'<div class="v-resumen-title">Resumen Económico</div>'
            f'<div class="v-resumen-row"><span class="v-resumen-label">Subtotal productos</span><span class="v-resumen-value">{money(total_lineas)}</span></div>'
            f'<div class="v-resumen-row"><span class="v-resumen-label">Envío cobrado</span><span class="v-resumen-value">{money(envio_cliente)}</span></div>'
            f'<div class="v-resumen-divider"></div>'
            f'<div class="v-resumen-row"><span class="v-resumen-total-label">Total cobrado</span><span class="v-resumen-total-val">{money(total_cobrado)}</span></div>'
            f'<div class="v-resumen-divider"></div>'
            f'<div class="v-resumen-row"><span class="v-resumen-label">Costo courier</span><span class="v-resumen-value v-resumen-red">-{money(costo_courier)}</span></div>'
            f'<div class="v-resumen-row"><span class="v-resumen-label">Comisión ({com_porc*100:.2f}%)</span><span class="v-resumen-value v-resumen-red">-{money(com_monto)}</span></div>'
            f'<div class="v-monto-box">'
            f'<span class="v-monto-label">Monto a recibir</span>'
            f'<span class="v-monto-value {monto_class}">{money(monto_a_recibir)}</span>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # ── 6. CTA Registrar Venta ────────────────────────────────
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

        save_btn = st.button("REGISTRAR VENTA", use_container_width=True,
                             disabled=not can_save, key="registrar_venta", type="primary")
        if save_btn:
            try:
                latest_inv = load_inventario(conn, ttl_s=0)
                col_stock  = "Stock_Casa" if bodega_venta == "Casa" else "Stock_Bodega"

                for item in cart:
                    sku_i  = str(item["SKU"]).strip()
                    qty_i  = int(item["Cantidad"])
                    match  = latest_inv[latest_inv["SKU"].astype(str).str.strip() == sku_i]
                    if match.empty:
                        raise ValueError(f"SKU no encontrado: {sku_i}")
                    available = int(_clean_number(match.iloc[0].get(col_stock, 0)))
                    if available < qty_i:
                        raise ValueError(f"Stock insuficiente para {sku_i}. Disponible={available}, Pedido={qty_i}")

                cab_df   = load_cabecera(conn, ttl_s=0)
                det_df   = load_detalle(conn, ttl_s=0)
                now      = datetime.now(APP_TZ)
                year     = int(now.strftime("%Y"))
                venta_id = next_venta_id(cab_df, year)
                fecha    = now.strftime("%Y-%m-%d")
                hora     = now.strftime("%H:%M:%S")

                cab_row = {
                    "Venta_ID": venta_id, "Fecha": fecha, "Hora": hora,
                    "Cliente": str(cliente).strip(), "Metodo_Pago": metodo_pago,
                    "Envio_Cobrado_Total": float(envio_cliente),
                    "Costo_Logistica_Total": float(costo_courier),
                    "Comision_Porc": float(com_porc),
                    "Total_Lineas": float(total_lineas),
                    "Total_Cobrado": float(total_cobrado),
                    "Comision_Monto": float(com_monto),
                    "Monto_A_Recibir": float(monto_a_recibir),
                    "Notas": str(notas).strip(), "Estado": "COMPLETADA",
                }

                det_rows: list[dict[str, Any]] = []
                for idx, item in enumerate(cart, start=1):
                    det_rows.append({
                        "Venta_ID": venta_id, "Linea": idx,
                        "SKU": str(item["SKU"]).strip(),
                        "Producto": str(item["Producto"]).strip(),
                        "Drop": str(item["Drop"]).strip(),
                        "Color": str(item["Color"]).strip(),
                        "Talla": str(item["Talla"]).strip(),
                        "Bodega_Salida": fmt_bodega(bodega_venta),
                        "Cantidad": int(item["Cantidad"]),
                        "Precio_Unitario": float(item["Precio_Unitario"]),
                        "Descuento_Unitario": float(item["Descuento_Unitario"]),
                        "Subtotal_Linea": float(item["Subtotal_Linea"]),
                    })

                cab_df  = _align_required_columns(cab_df, CAB_REQUIRED)
                cab_out = pd.concat([cab_df, pd.DataFrame([cab_row])], ignore_index=True)
                cab_out = _align_required_columns(cab_out, CAB_REQUIRED)
                save_sheet(conn, SHEET_VENTAS_CAB, cab_out)

                det_df  = _align_required_columns(det_df, DET_REQUIRED)
                det_out = pd.concat([det_df, pd.DataFrame(det_rows)], ignore_index=True)
                det_out = _align_required_columns(det_out, DET_REQUIRED)
                save_sheet(conn, SHEET_VENTAS_DET, det_out)

                inv_updated = latest_inv.copy()
                for item in cart:
                    sku_i  = str(item["SKU"]).strip()
                    qty_i  = int(item["Cantidad"])
                    mask   = inv_updated["SKU"].astype(str).str.strip() == sku_i
                    ix     = inv_updated.index[mask].tolist()[0]
                    inv_updated.loc[ix, col_stock] = int(_clean_number(inv_updated.loc[ix, col_stock])) - qty_i

                save_sheet(conn, SHEET_INVENTARIO, inv_updated)
                st.success(f"✅ Venta registrada: {venta_id}")
                st.cache_data.clear()
                st.session_state["_reset_sale_pending"] = True
                st.rerun()
            except Exception as e:
                st.error("Error al registrar la venta.")
                st.exception(e)

    # ══════════════════════════════════════════════════════════════
    # MODO: EGRESOS
    # ══════════════════════════════════════════════════════════════
    else:
        try:
            egresos_df_full = load_egresos(conn, ttl_s=45)
        except Exception as e:
            egresos_df_full = _align_required_columns(pd.DataFrame(), EG_REQUIRED)
            st.warning(f"No pude leer la hoja 'Egresos'. Detalle: {e}")

        # Categorías maestras
        try:
            categorias_df  = load_categorias(conn, ttl_s=60)
            categorias_list = sorted({
                c for c in categorias_df["Categoria"].dropna().astype(str).str.strip().unique()
                if c and c.lower() != "nan"
            })
        except Exception:
            categorias_list = []

        # Catálogos (drops)
        try:
            cat_df    = load_catalogos(conn, ttl_s=600)
            cat       = parse_catalogos(cat_df)
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
        seen: set[str] = set()
        for d in drops_cat:
            val = (d.get("valor") or "").strip()
            if not val or val in seen:
                continue
            seen.add(val)
            drop_pairs.append((_pretty_drop_label(val), val))

        ss = st.session_state

        # ── Resumen del mes ───────────────────────────────────────
        total_mes = 0.0
        if not egresos_df_full.empty:
            now_tz = datetime.now(APP_TZ)
            mes_str = now_tz.strftime("%Y-%m")
            eg_tmp = egresos_df_full.copy()
            eg_tmp["_dt"] = pd.to_datetime(eg_tmp["Fecha"], errors="coerce", dayfirst=True)
            eg_mes = eg_tmp[eg_tmp["_dt"].dt.strftime("%Y-%m") == mes_str]
            total_mes = float(pd.to_numeric(eg_mes["Monto"], errors="coerce").fillna(0).sum())

        st.markdown(
            f'<div class="eg-summary-card">'
            f'<div class="eg-summary-label">Resumen del mes</div>'
            f'<div class="eg-summary-sublabel">Gasto Total:</div>'
            f'<div class="eg-summary-total">{money(total_mes)}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # ── Agregar Gasto ─────────────────────────────────────────
        st.markdown('<div class="v-section-title">Agregar Gasto</div>', unsafe_allow_html=True)

        st.markdown('<span class="v-label">Concepto</span>', unsafe_allow_html=True)
        ss["eg_concepto"] = st.text_input(
            "Concepto", value=ss["eg_concepto"],
            placeholder="Ej: Publicidad en Instagram",
            key="eg_concepto_input", label_visibility="collapsed",
        )

        amt_col, cat_col = st.columns(2)
        with amt_col:
            st.markdown('<span class="v-label">Monto</span>', unsafe_allow_html=True)
            ss["eg_monto"] = st.number_input(
                "Monto", min_value=0.0, step=0.50, format="%.2f",
                value=float(ss["eg_monto"] or 0.0),
                key="eg_monto_input", label_visibility="collapsed",
            )
        with cat_col:
            st.markdown('<span class="v-label">Categoría</span>', unsafe_allow_html=True)
            cat_opts = ["(Sin categoría)"] + categorias_list
            if ss["eg_categoria_sel"] not in cat_opts:
                cat_opts = cat_opts + [ss["eg_categoria_sel"]]
            ss["eg_categoria_sel"] = st.selectbox(
                "Categoría", options=cat_opts,
                index=cat_opts.index(ss["eg_categoria_sel"]) if ss["eg_categoria_sel"] in cat_opts else 0,
                key="eg_categoria_sel_input", label_visibility="collapsed",
            )

        # Nueva categoría
        nc1, nc2 = st.columns([4, 1])
        with nc1:
            st.markdown('<span class="v-label">Nueva Categoría</span>', unsafe_allow_html=True)
            ss["eg_categoria_new"] = st.text_input(
                "Nueva cat", value=ss["eg_categoria_new"], placeholder="Nombre...",
                key="eg_categoria_new_input", label_visibility="collapsed",
            )
        with nc2:
            st.markdown("<div style='height:22px'></div>", unsafe_allow_html=True)
            if st.button("➕", key="eg_cat_add_btn", use_container_width=True, help="Agregar categoría"):
                nueva = (ss["eg_categoria_new"] or "").strip()
                if nueva and nueva not in categorias_list:
                    cat_df_fresh = load_categorias(conn, ttl_s=0)
                    nueva_fila   = pd.DataFrame([{"Categoria": nueva}])
                    cat_out      = pd.concat([cat_df_fresh, nueva_fila], ignore_index=True)
                    save_sheet(conn, SHEET_CATEGORIAS, cat_out)
                    st.cache_data.clear()
                    ss["eg_categoria_sel"] = nueva
                    ss["eg_categoria_new"] = ""
                    st.rerun()

        can_save_eg = (float(ss["eg_monto"] or 0.0) > 0) and bool((ss["eg_concepto"] or "").strip())
        if st.button("Registrar Gasto", use_container_width=True,
                     disabled=not can_save_eg, key="eg_guardar_btn", type="primary"):
            st.cache_data.clear()
            eg_fresh = load_egresos(conn, ttl_s=0)
            new_id   = _next_egreso_id(eg_fresh)
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

            for k in ["eg_monto_input", "eg_concepto_input", "eg_notas_input",
                      "eg_drop_select", "eg_categoria_sel_input", "eg_fecha_input"]:
                if k in st.session_state:
                    del st.session_state[k]
            ss["eg_monto"]         = 0.0
            ss["eg_concepto"]      = ""
            ss["eg_notas"]         = ""
            ss["eg_drop_sel"]      = ""
            ss["eg_categoria_sel"] = "(Sin categoría)"
            ss["eg_fecha"]         = datetime.now(APP_TZ).date()
            st.session_state["_eg_toast"] = f"Egreso guardado: {new_id}"
            st.rerun()


        if st.session_state.get("_eg_toast"):
            st.toast(st.session_state["_eg_toast"], icon="✅")
            del st.session_state["_eg_toast"]

        with st.expander("Más detalles (fecha, drop, notas)", expanded=False):
            ss["eg_fecha"] = st.date_input("Fecha", value=ss["eg_fecha"], key="eg_fecha_input")

            drop_labels = [lab for lab, _ in drop_pairs]
            drop_values = [val for _, val in drop_pairs]
            drop_idx    = drop_values.index(ss["eg_drop_sel"]) if ss["eg_drop_sel"] in drop_values else 0
            drop_label  = st.selectbox("Drop", options=drop_labels, index=drop_idx, key="eg_drop_select")
            ss["eg_drop_sel"] = drop_pairs[drop_labels.index(drop_label)][1]

            ss["eg_notas"] = st.text_area("Notas", value=ss["eg_notas"],
                                          placeholder="Detalles adicionales", key="eg_notas_input")

        # ── Gastos por Categoría ──────────────────────────────────
        if not egresos_df_full.empty and "Categoria" in egresos_df_full.columns:
            cat_totals = (
                egresos_df_full[egresos_df_full["Categoria"].astype(str).str.strip() != ""]
                .groupby("Categoria")["Monto"]
                .apply(lambda x: pd.to_numeric(x, errors="coerce").fillna(0).sum())
                .sort_values(ascending=False)
            )
            if not cat_totals.empty:
                st.markdown('<div class="v-section-title" style="margin-top:20px">Gastos por Categoría</div>', unsafe_allow_html=True)
                icons = ["👕", "⚙️", "🧾", "💼", "🗂️", "🔧", "🎯", "💡"]
                chips_html = '<div class="eg-cat-chip-row">'
                for i, (cat_name, cat_total) in enumerate(cat_totals.items()):
                    icon = icons[i % len(icons)]
                    chips_html += (
                        f'<div class="eg-cat-chip">'
                        f'<div class="eg-cat-icon" style="background:rgba(16,185,129,0.15)">{icon}</div>'
                        f'<span class="eg-cat-name">{cat_name}</span>'
                        f'<span class="eg-cat-total">{money(float(cat_total))}</span>'
                        f'</div>'
                    )
                chips_html += '</div>'
                st.markdown(chips_html, unsafe_allow_html=True)

        # ── Últimos Movimientos ───────────────────────────────────
        st.markdown('<div class="v-section-title" style="margin-top:20px">Últimos Movimientos</div>', unsafe_allow_html=True)

        if egresos_df_full.empty:
            st.caption("Aún no hay movimientos registrados.")
        else:
            eg_show = egresos_df_full.copy()
            eg_show["_fecha_dt"] = pd.to_datetime(eg_show["Fecha"], errors="coerce", dayfirst=True)
            eg_show = eg_show.sort_values("_fecha_dt", ascending=False).head(10)

            cat_icons_map = {"materiales": "⚙️", "samples": "👕", "suscripciones": "🧾"}
            for _, r in eg_show.iterrows():
                cat_raw  = str(r.get("Categoria", "")).strip().lower()
                icon     = cat_icons_map.get(cat_raw, "💸")
                concepto = str(r.get("Concepto", ""))
                cat_str  = str(r.get("Categoria", "")).strip() or "Sin categoría"
                fecha    = str(r.get("Fecha", ""))
                monto    = float(pd.to_numeric(r.get("Monto", 0), errors="coerce") or 0)

                st.markdown(
                    f'<div class="eg-tx-item">'
                    f'<div style="display:flex;align-items:center;flex:1;min-width:0">'
                    f'<div class="eg-tx-icon-wrap">{icon}</div>'
                    f'<div style="min-width:0">'
                    f'<div class="eg-tx-concept">{concepto}</div>'
                    f'<div class="eg-tx-meta">{cat_str} · {fecha}</div>'
                    f'</div>'
                    f'</div>'
                    f'<span class="eg-tx-amount">-{money(monto)}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
