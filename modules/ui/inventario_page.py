from datetime import datetime
import re

import pandas as pd
import streamlit as st

from modules.core.constants import INV_REQUIRED, SHEET_CATALOGOS, SHEET_INVENTARIO
from modules.data.helpers import (
    ensure_unique_skus,
    get_existing_product_code,
    load_catalogos,
    load_inventario,
    parse_catalogos,
    save_sheet,
    size_sort_key,
    suggest_product_code,
    build_sku,
)


def _inject_inv_css() -> None:
    st.markdown("""
    <style>
      :root {
        --inv-bg:       #0e0e0e;
        --inv-card:     #1a1a1a;
        --inv-card-hi:  #20201f;
        --inv-card-hi2: #262626;
        --inv-card-low: #131313;
        --inv-primary:  #3fff8b;
        --inv-text:     #ffffff;
        --inv-muted:    #adaaaa;
        --inv-border:   rgba(72,72,71,0.4);
      }

      /* ── Tab nav ── */
      .inv-nav {
        background: #121212;
        border: 1px solid rgba(255,255,255,0.05);
        border-radius: 16px;
        padding: 6px;
        display: flex;
        gap: 4px;
        margin-bottom: 24px;
      }
      .inv-nav-btn {
        flex: 1;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 5px;
        padding: 12px 6px;
        border-radius: 12px;
        border: none;
        background: transparent;
        color: rgba(255,255,255,0.35);
        cursor: pointer;
        font-size: 0.6rem;
        font-weight: 900;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        transition: all 0.15s;
      }
      .inv-nav-btn:hover { color: rgba(255,255,255,0.6); }
      .inv-nav-btn.active {
        background: #1e1e1e;
        border: 1px solid rgba(255,255,255,0.05);
        color: var(--inv-primary);
      }
      .inv-nav-icon { font-size: 1.2rem; }

      /* ── Page title ── */
      .inv-page-title {
        font-size: 1.9rem;
        font-weight: 800;
        color: var(--inv-text);
        margin-bottom: 20px;
        letter-spacing: -0.01em;
      }
      .inv-page-title.upper {
        text-transform: uppercase;
        font-size: 1.7rem;
      }
      .inv-page-sub {
        font-size: 0.78rem;
        color: var(--inv-muted);
        font-weight: 500;
        margin-top: -14px;
        margin-bottom: 24px;
      }

      /* ── Producto card (inventario) ── */
      .inv-prod-summary {
        background: var(--inv-card);
        border-radius: 14px;
        padding: 18px 20px;
        margin-bottom: 10px;
        cursor: pointer;
        display: flex;
        justify-content: space-between;
        align-items: center;
      }
      .inv-prod-name {
        font-size: 1.08rem;
        font-weight: 700;
        color: var(--inv-text);
      }
      .inv-prod-stock {
        font-size: 0.72rem;
        color: var(--inv-primary);
        margin-top: 3px;
        font-weight: 600;
      }

      /* ── Detalle dentro del expander ── */
      .inv-bodega-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 16px;
      }
      .inv-bodega-item {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 0.88rem;
      }
      .inv-bodega-label { font-weight: 700; color: var(--inv-text); }
      .inv-bodega-val   { color: var(--inv-text); }

      .inv-section-title {
        font-size: 1rem;
        font-weight: 700;
        color: var(--inv-text);
        margin: 16px 0 10px 0;
      }
      .inv-talla-title {
        font-size: 0.88rem;
        font-weight: 700;
        color: var(--inv-text);
        margin-bottom: 8px;
      }
      .inv-bar-label {
        font-size: 0.78rem;
        color: var(--inv-muted);
        margin-bottom: 3px;
      }
      .inv-bar-track {
        height: 7px;
        width: 100%;
        background: var(--inv-card-hi2);
        border-radius: 999px;
        overflow: hidden;
        margin-bottom: 10px;
      }
      .inv-bar-fill {
        height: 100%;
        background: var(--inv-primary);
        border-radius: 999px;
      }

      /* ── Transferir ── */
      .inv-tr-card {
        background: var(--inv-card);
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 16px;
        position: relative;
        overflow: hidden;
      }
      .inv-tr-label {
        font-size: 0.6rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: var(--inv-muted);
        display: block;
        margin-bottom: 10px;
      }
      .inv-tr-sku-box {
        background: var(--inv-card-hi2);
        border: 1px solid rgba(72,72,71,0.2);
        border-radius: 12px;
        padding: 16px;
      }
      .inv-tr-sku-name {
        font-size: 1rem;
        font-weight: 700;
        color: var(--inv-text);
      }
      .inv-tr-sku-code {
        font-size: 0.72rem;
        font-family: monospace;
        color: var(--inv-primary);
        font-weight: 700;
        margin-top: 3px;
        letter-spacing: 0.08em;
      }
      .inv-tr-stock-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 12px;
        margin: 16px 0;
      }
      .inv-tr-stock-tile {
        background: var(--inv-card-low);
        border: 1px solid rgba(72,72,71,0.15);
        border-radius: 12px;
        padding: 14px;
      }
      .inv-tr-tile-label {
        font-size: 0.58rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: var(--inv-muted);
        display: block;
        margin-bottom: 6px;
      }
      .inv-tr-tile-name {
        font-size: 1rem;
        font-weight: 700;
        color: var(--inv-text);
        display: block;
        margin-bottom: 8px;
      }
      .inv-tr-tile-stock-row {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
      }
      .inv-tr-stock-mini-label {
        font-size: 0.58rem;
        text-transform: uppercase;
        font-weight: 700;
        color: var(--inv-muted);
      }
      .inv-tr-stock-num {
        font-size: 1.8rem;
        font-weight: 900;
        color: var(--inv-primary);
        line-height: 1;
      }
      .inv-tr-stock-num.zero { color: var(--inv-muted); }

      /* dirección */
      .inv-tr-dir-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 8px;
        margin-bottom: 16px;
      }
      .inv-tr-dir-btn {
        padding: 12px 10px;
        border-radius: 10px;
        border: 1px solid rgba(72,72,71,0.15);
        background: #000;
        color: var(--inv-muted);
        font-size: 0.65rem;
        font-weight: 900;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        cursor: pointer;
        opacity: 0.4;
        text-align: center;
      }
      .inv-tr-dir-btn.active {
        background: rgba(63,255,139,0.06);
        border-color: rgba(63,255,139,0.35);
        color: var(--inv-primary);
        opacity: 1;
      }

      /* botón transferir */
      .inv-tr-submit {
        width: 100%;
        padding: 18px;
        border-radius: 14px;
        border: none;
        background: linear-gradient(135deg, #3fff8b 0%, #13ea79 100%);
        color: #004820;
        font-size: 0.75rem;
        font-weight: 900;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        cursor: pointer;
        box-shadow: 0 10px 30px rgba(63,255,139,0.25);
        margin-top: 8px;
      }

      /* ── Ingreso ── */
      .inv-ing-section-title {
        font-size: 0.6rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: var(--inv-muted);
        margin-bottom: 6px;
      }
    </style>
    """, unsafe_allow_html=True)


def render_inventario_page(conn, inv_df_full, fmt_bodega, bodega1_nombre, bodega2_nombre) -> None:

    _inject_inv_css()

    # ── Estado del tab activo ──────────────────────────────────────
    if "inv_tab" not in st.session_state:
        st.session_state.inv_tab = "inventario"

    # ── Tab navigation ────────────────────────────────────────────
    with st.container():
        st.markdown('<div class="inv-tabs-nav-marker"></div>', unsafe_allow_html=True)
        t1, t2, t3 = st.columns(3)

        with t1:
            cls = "inv-tabs-state active" if st.session_state.inv_tab == "inventario" else "inv-tabs-state"
            st.markdown(f'<div class="{cls}"></div>', unsafe_allow_html=True)
            if st.button("\nINVENTARIO", key="inv_tab_btn_inv", use_container_width=True):
                st.session_state.inv_tab = "inventario"
                st.rerun()

        with t2:
            cls = "inv-tabs-state active" if st.session_state.inv_tab == "transferir" else "inv-tabs-state"
            st.markdown(f'<div class="{cls}"></div>', unsafe_allow_html=True)
            if st.button("\nTRANSFERIR", key="inv_tab_btn_tr", use_container_width=True):
                st.session_state.inv_tab = "transferir"
                st.rerun()

        with t3:
            cls = "inv-tabs-state active" if st.session_state.inv_tab == "ingreso" else "inv-tabs-state"
            st.markdown(f'<div class="{cls}"></div>', unsafe_allow_html=True)
            if st.button("\nINGRESO", key="inv_tab_btn_ing", use_container_width=True):
                st.session_state.inv_tab = "ingreso"
                st.rerun()

    tab = st.session_state.inv_tab

    # ── Datos base ────────────────────────────────────────────────
    inv_df = inv_df_full.copy()
    if "Activo" in inv_df.columns:
        inv_df = inv_df[inv_df["Activo"].fillna(True) == True].copy()

    cat_df = load_catalogos(conn, ttl_s=600)
    cat = parse_catalogos(cat_df)
    colores_cat = cat.get("colores", [])
    color_to_code = {c["valor"]: c["codigo"] for c in colores_cat}
    color_to_code.setdefault("Standard", "STD")
    color_to_code.setdefault("STANDARD", "STD")

    # ══════════════════════════════════════════════════════════════
    # TAB: INVENTARIO
    # ══════════════════════════════════════════════════════════════
    if tab == "inventario":
        c_title, c_btn = st.columns([3, 1])
        with c_title:
            st.markdown('<div class="inv-page-title">Inventario</div>', unsafe_allow_html=True)
        with c_btn:
            if st.button("🔄 Refrescar", use_container_width=True):
                st.cache_data.clear()
                st.rerun()

        if inv_df.empty:
            st.info("No hay filas en Inventario todavía.")
        else:
            productos = sorted(inv_df["Producto"].dropna().astype(str).unique().tolist())
            for producto in productos:
                p_df = inv_df[inv_df["Producto"] == producto].copy()

                casa_total = int(p_df.get("Stock_Casa", 0).fillna(0).sum())
                bod_total = int(p_df.get("Stock_Bodega", 0).fillna(0).sum())
                total = casa_total + bod_total

                with st.expander(f"**{producto}** — Stock Total: {total}", expanded=False):
                    st.markdown(
                        f'<div class="inv-bodega-row">'
                        f'<div class="inv-bodega-item"><span class="inv-bodega-label">{bodega1_nombre}:</span><span class="inv-bodega-val">{casa_total}</span></div>'
                        f'<div class="inv-bodega-item"><span class="inv-bodega-label">{bodega2_nombre}:</span><span class="inv-bodega-val">{bod_total}</span></div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                    colors = (
                        p_df.get("Color", pd.Series([], dtype=str))
                        .fillna("Standard").astype(str).str.strip().unique().tolist()
                    )
                    colors = [c for c in colors if c and c.lower() != "nan"]
                    has_real_colors = any(c.lower() != "standard" for c in colors)

                    show_df = p_df
                    if has_real_colors:
                        colors_sorted = sorted(colors, key=lambda x: (x.lower() == "standard", x))
                        st.markdown('<div class="inv-section-title">Color:</div>', unsafe_allow_html=True)
                        selected_color = st.radio(
                            label="Color",
                            options=colors_sorted,
                            horizontal=True,
                            label_visibility="collapsed",
                            key=f"inv_color_{producto}",
                        )
                        show_df = p_df[
                            p_df["Color"].fillna("Standard").astype(str).str.strip() == selected_color
                        ].copy()

                    sizes = (
                        show_df.get("Talla", pd.Series([], dtype=str))
                        .fillna("OS").astype(str).str.strip().unique().tolist()
                    )
                    sizes = [s for s in sizes if s and s.lower() != "nan"]
                    has_sizes = not (len(sizes) == 1 and sizes[0].upper() == "OS")

                    st.markdown('<div class="inv-section-title">Stock por talla:</div>', unsafe_allow_html=True)

                    if not has_sizes:
                        casa = int(show_df.get("Stock_Casa", 0).fillna(0).sum())
                        bod = int(show_df.get("Stock_Bodega", 0).fillna(0).sum())
                        mx = max(casa, bod, 1)
                        st.markdown('<div class="inv-talla-title">Talla OS</div>', unsafe_allow_html=True)
                        c1, c2 = st.columns(2)
                        with c1:
                            pct = int((casa / mx) * 100)
                            st.markdown(
                                f'<div class="inv-bar-label">{bodega1_nombre}: {casa} u.</div>'
                                f'<div class="inv-bar-track"><div class="inv-bar-fill" style="width:{pct}%"></div></div>',
                                unsafe_allow_html=True,
                            )
                        with c2:
                            pct = int((bod / mx) * 100)
                            st.markdown(
                                f'<div class="inv-bar-label">{bodega2_nombre}: {bod} u.</div>'
                                f'<div class="inv-bar-track"><div class="inv-bar-fill" style="width:{pct}%"></div></div>',
                                unsafe_allow_html=True,
                            )
                    else:
                        sizes_sorted = sorted(sizes, key=size_sort_key)
                        for talla in sizes_sorted:
                            row = show_df[
                                show_df["Talla"].fillna("OS").astype(str).str.strip().str.upper() == str(talla).upper()
                            ]
                            casa = int(row.get("Stock_Casa", 0).fillna(0).sum())
                            bod = int(row.get("Stock_Bodega", 0).fillna(0).sum())
                            mx = max(casa, bod, 1)

                            st.markdown(f'<div class="inv-talla-title">Talla {talla}</div>', unsafe_allow_html=True)
                            c1, c2 = st.columns(2)
                            with c1:
                                pct = int((casa / mx) * 100)
                                st.markdown(
                                    f'<div class="inv-bar-label">{bodega1_nombre}: {casa} u.</div>'
                                    f'<div class="inv-bar-track"><div class="inv-bar-fill" style="width:{pct}%"></div></div>',
                                    unsafe_allow_html=True,
                                )
                            with c2:
                                pct = int((bod / mx) * 100)
                                st.markdown(
                                    f'<div class="inv-bar-label">{bodega2_nombre}: {bod} u.</div>'
                                    f'<div class="inv-bar-track"><div class="inv-bar-fill" style="width:{pct}%"></div></div>',
                                    unsafe_allow_html=True,
                                )

    # ══════════════════════════════════════════════════════════════
    # TAB: TRANSFERIR
    # ══════════════════════════════════════════════════════════════
    elif tab == "transferir":
        st.markdown('<div class="inv-page-title upper">Transferir Stock</div>', unsafe_allow_html=True)
        st.markdown('<div class="inv-page-sub">Gestiona transferencias internas entre almacenes</div>', unsafe_allow_html=True)

        inv_latest = load_inventario(conn, ttl_s=45)
        if "Activo" in inv_latest.columns:
            inv_latest = inv_latest[inv_latest["Activo"].fillna(True) == True].copy()

        if inv_latest.empty:
            st.warning("No hay SKUs en Inventario.")
        else:
            inv_latest["__label"] = (
                inv_latest["Producto"].astype(str)
                + " - "
                + inv_latest["Color"].fillna("Standard").astype(str)
                + " - "
                + inv_latest["Talla"].fillna("OS").astype(str)
            )

            st.markdown('<span class="inv-tr-label">Producto Seleccionado (SKU)</span>', unsafe_allow_html=True)
            sku_options = inv_latest["__label"].tolist()
            label_sel = st.selectbox("SKU", sku_options, key="transfer_sku_label", label_visibility="collapsed")

            sel_row = inv_latest[inv_latest["__label"] == label_sel].iloc[0]
            sku = str(sel_row["SKU"])
            sku_label = str(sel_row["__label"])

            st.markdown(
                f'<div class="inv-tr-sku-box">'
                f'<div class="inv-tr-sku-name">{sku_label}</div>'
                f'<div class="inv-tr-sku-code">SKU: {sku}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

            casa_stock = int(sel_row.get("Stock_Casa", 0) or 0)
            bod_stock = int(sel_row.get("Stock_Bodega", 0) or 0)

            if "transfer_dir" not in st.session_state:
                st.session_state.transfer_dir = f"{fmt_bodega('Casa')} ➜ {fmt_bodega('Bodega')}"

            dir_opt1 = f"{fmt_bodega('Casa')} ➜ {fmt_bodega('Bodega')}"
            dir_opt2 = f"{fmt_bodega('Bodega')} ➜ {fmt_bodega('Casa')}"
            direction = st.session_state.transfer_dir

            is_casa_to_bod = direction == dir_opt1
            orig_name = bodega1_nombre if is_casa_to_bod else bodega2_nombre
            dest_name = bodega2_nombre if is_casa_to_bod else bodega1_nombre
            orig_stock = casa_stock if is_casa_to_bod else bod_stock
            dest_stock = bod_stock if is_casa_to_bod else casa_stock

            st.markdown(
                f'<div class="inv-tr-stock-grid">'
                f'<div class="inv-tr-stock-tile">'
                f'<span class="inv-tr-tile-label">Origen</span>'
                f'<span class="inv-tr-tile-name">{orig_name}</span>'
                f'<div class="inv-tr-tile-stock-row">'
                f'<span class="inv-tr-stock-mini-label">Stock</span>'
                f'<span class="inv-tr-stock-num {"" if orig_stock > 0 else "zero"}">{orig_stock}</span>'
                f'</div></div>'
                f'<div class="inv-tr-stock-tile">'
                f'<span class="inv-tr-tile-label">Destino</span>'
                f'<span class="inv-tr-tile-name">{dest_name}</span>'
                f'<div class="inv-tr-tile-stock-row">'
                f'<span class="inv-tr-stock-mini-label">Stock</span>'
                f'<span class="inv-tr-stock-num {"" if dest_stock > 0 else "zero"}">{dest_stock}</span>'
                f'</div></div>'
                f'</div>',
                unsafe_allow_html=True,
            )

            st.markdown('<span class="inv-tr-label">Ruta de Transferencia</span>', unsafe_allow_html=True)
            with st.container():
                st.markdown('<div class="transfer-route-nav-marker"></div>', unsafe_allow_html=True)
                d1, d2 = st.columns(2)

                with d1:
                    cls = "transfer-route-state active" if is_casa_to_bod else "transfer-route-state"
                    st.markdown(f'<div class="{cls}"></div>', unsafe_allow_html=True)
                    if st.button(
                        f"{bodega1_nombre} → {bodega2_nombre}",
                        use_container_width=True,
                        key="dir_btn_1",
                    ):
                        st.session_state.transfer_dir = dir_opt1
                        st.rerun()

                with d2:
                    cls = "transfer-route-state active" if not is_casa_to_bod else "transfer-route-state"
                    st.markdown(f'<div class="{cls}"></div>', unsafe_allow_html=True)
                    if st.button(
                        f"{bodega2_nombre} → {bodega1_nombre}",
                        use_container_width=True,
                        key="dir_btn_2",
                    ):
                        st.session_state.transfer_dir = dir_opt2
                        st.rerun()

            st.markdown('<span class="inv-tr-label" style="margin-top:12px;display:block">Cantidad a Transferir</span>', unsafe_allow_html=True)
            qty = st.number_input(
                "Cantidad",
                min_value=1,
                step=1,
                value=1,
                key="transfer_qty",
                label_visibility="collapsed",
            )
            st.caption("El stock se actualizará instantáneamente tras la confirmación.")

            def _can_move() -> tuple[bool, str]:
                if is_casa_to_bod:
                    if qty > casa_stock:
                        return False, f"No hay suficiente stock en {bodega1_nombre}."
                else:
                    if qty > bod_stock:
                        return False, f"No hay suficiente stock en {bodega2_nombre}."
                return True, ""

            ok, msg = _can_move()
            if not ok:
                st.error(msg)

            if st.button("⇄  TRANSFERIR STOCK", use_container_width=True, disabled=not ok, type="primary"):
                st.cache_data.clear()
                inv_fresh = load_inventario(conn, ttl_s=45)
                if "Activo" in inv_fresh.columns:
                    inv_fresh = inv_fresh[inv_fresh["Activo"].fillna(True) == True].copy()

                idx = inv_fresh.index[inv_fresh["SKU"].astype(str) == sku]
                if idx.empty:
                    st.error("SKU no encontrado. Refrescá e intentá otra vez.")
                    st.stop()

                i0 = idx[0]
                if is_casa_to_bod:
                    inv_fresh.at[i0, "Stock_Casa"] = int(inv_fresh.at[i0, "Stock_Casa"] or 0) - int(qty)
                    inv_fresh.at[i0, "Stock_Bodega"] = int(inv_fresh.at[i0, "Stock_Bodega"] or 0) + int(qty)
                else:
                    inv_fresh.at[i0, "Stock_Bodega"] = int(inv_fresh.at[i0, "Stock_Bodega"] or 0) - int(qty)
                    inv_fresh.at[i0, "Stock_Casa"] = int(inv_fresh.at[i0, "Stock_Casa"] or 0) + int(qty)

                save_sheet(conn, SHEET_INVENTARIO, inv_fresh)
                st.success("✅ Transferencia realizada.")
                st.cache_data.clear()
                st.rerun()

    # ══════════════════════════════════════════════════════════════
    # TAB: INGRESO
    # ══════════════════════════════════════════════════════════════
    elif tab == "ingreso":
        st.markdown('<div class="inv-page-title upper">Ingreso de <b>Producto</b></div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="inv-page-sub" style="text-transform:uppercase;letter-spacing:0.08em;font-size:0.62rem;">Configuración de nueva entrada</div>',
            unsafe_allow_html=True,
        )

        def _np_init_state() -> None:
            ss = st.session_state
            ss.setdefault("np_stage", "define")
            ss.setdefault("np_tiene_tallas", True)
            ss.setdefault("np_tiene_colores", True)
            ss.setdefault("np_nombre", "")
            ss.setdefault("np_drop_sel", "")
            ss.setdefault("np_add_drop", False)
            ss.setdefault("np_new_drop", "")
            ss.setdefault("np_new_drop_code", "")
            ss.setdefault("np_costo", 0.0)
            ss.setdefault("np_precio", 0.0)
            ss.setdefault("np_almacen", "Casa")
            ss.setdefault("np_prod_code", "")
            ss.setdefault("np_allow_stock0", False)
            ss.setdefault("np_colores_sel", ["Standard"])
            ss.setdefault("np_tallas_sel", ["S", "M", "L", "XL"])
            ss.setdefault("np_variants", {"colores": ["Standard"], "tallas": ["OS"]})

        def _np_clear_stock_keys() -> None:
            kill = [k for k in st.session_state.keys() if str(k).startswith("np_stock_")]
            for k in kill:
                try:
                    del st.session_state[k]
                except Exception:
                    pass

        def _np_unlock_variants() -> None:
            st.session_state["np_stage"] = "define"
            _np_clear_stock_keys()

        def _np_lock_variants() -> None:
            tiene_tallas = bool(st.session_state.get("np_tiene_tallas", True))
            tiene_colores = bool(st.session_state.get("np_tiene_colores", True))
            tallas = st.session_state.get("np_tallas_sel", []) or []
            colores = st.session_state.get("np_colores_sel", []) or []
            tallas = ["OS"] if not tiene_tallas else ([s.strip().upper() for s in tallas if str(s).strip()] or ["S"])
            colores = ["Standard"] if not tiene_colores else ([str(c).strip() for c in colores if str(c).strip()] or ["Standard"])
            st.session_state["np_variants"] = {"colores": colores, "tallas": tallas}
            st.session_state["np_stage"] = "stock"
            _np_clear_stock_keys()

        def _np_reset_all() -> None:
            keys = [
                "np_stage", "np_tiene_tallas", "np_tiene_colores", "np_nombre",
                "np_drop_sel", "np_add_drop", "np_new_drop", "np_new_drop_code",
                "np_costo", "np_precio", "np_almacen", "np_prod_code",
                "np_allow_stock0", "np_colores_sel", "np_tallas_sel", "np_variants",
            ]
            for k in keys:
                if k in st.session_state:
                    del st.session_state[k]
            _np_clear_stock_keys()
            _np_init_state()

        _np_init_state()

        stage = str(st.session_state.get("np_stage", "define"))
        locked = stage == "stock"

        drops = cat.get("drops", [])
        colores_cat2 = cat.get("colores", [])
        drop_vals = [d.get("valor", "") for d in drops if str(d.get("valor", "")).strip()] or ["(sin drops en Catalogos)"]
        color_vals = [c.get("valor", "") for c in colores_cat2 if str(c.get("valor", "")).strip()] or []

        color_to_code2 = {c.get("valor", ""): c.get("codigo", "") for c in colores_cat2}
        color_to_code2.setdefault("Standard", "STD")
        color_to_code2.setdefault("STANDARD", "STD")

        if st.session_state.get("np_drop_sel") not in drop_vals:
            st.session_state["np_drop_sel"] = drop_vals[0]

        if not str(st.session_state.get("np_prod_code", "")).strip() and str(st.session_state.get("np_nombre", "")).strip():
            st.session_state["np_prod_code"] = suggest_product_code(str(st.session_state.get("np_nombre", "")))

        sw1, sw2 = st.columns(2)
        with sw1:
            st.toggle("Tiene tallas", key="np_tiene_tallas", disabled=locked, on_change=_np_unlock_variants)
        with sw2:
            st.toggle("Tiene variante de color", key="np_tiene_colores", disabled=locked, on_change=_np_unlock_variants)

        st.markdown('<div class="inv-ing-section-title">Nombre del Producto</div>', unsafe_allow_html=True)
        st.text_input(
            "Nombre",
            key="np_nombre",
            disabled=locked,
            placeholder="Ej. Oversized Graphic Tee",
            on_change=_np_unlock_variants,
            label_visibility="collapsed",
        )

        st.markdown('<div class="inv-ing-section-title">Drop</div>', unsafe_allow_html=True)
        st.selectbox(
            "Drop",
            options=drop_vals,
            key="np_drop_sel",
            disabled=locked,
            on_change=_np_unlock_variants,
            label_visibility="collapsed",
        )

        with st.expander("Agregar drop nuevo (opcional)", expanded=False):
            st.checkbox("Agregar drop nuevo", key="np_add_drop", disabled=locked)
            if st.session_state.get("np_add_drop", False):
                st.text_input("Nuevo drop (ej: D005)", key="np_new_drop", disabled=locked)
                st.text_input("Código drop", key="np_new_drop_code", disabled=locked)

        c1, c2 = st.columns(2)
        with c1:
            st.markdown('<div class="inv-ing-section-title">Costo del Producto ($)</div>', unsafe_allow_html=True)
            st.number_input(
                "Costo",
                min_value=0.0,
                step=0.50,
                format="%.2f",
                key="np_costo",
                disabled=locked,
                on_change=_np_unlock_variants,
                label_visibility="collapsed",
            )
        with c2:
            st.markdown('<div class="inv-ing-section-title">Precio de Venta ($)</div>', unsafe_allow_html=True)
            st.number_input(
                "Precio",
                min_value=0.0,
                step=0.50,
                format="%.2f",
                key="np_precio",
                disabled=locked,
                on_change=_np_unlock_variants,
                label_visibility="collapsed",
            )

        st.markdown('<div class="inv-ing-section-title">Almacén Inicial</div>', unsafe_allow_html=True)
        st.radio(
            "Almacén",
            options=["Casa", "Bodega"],
            horizontal=True,
            key="np_almacen",
            format_func=fmt_bodega,
            disabled=locked,
            on_change=_np_unlock_variants,
            label_visibility="collapsed",
        )

        st.markdown('<div class="inv-ing-section-title">Código Producto (3 Letras)</div>', unsafe_allow_html=True)
        st.text_input(
            "Código",
            key="np_prod_code",
            disabled=locked,
            help="SKU: DROP-PROD-COLOR-TALLA",
            on_change=_np_unlock_variants,
            label_visibility="collapsed",
        )

        st.toggle("Permitir guardar con stock 0", key="np_allow_stock0", disabled=locked)

        tiene_tallas = bool(st.session_state.get("np_tiene_tallas", True))
        tiene_colores = bool(st.session_state.get("np_tiene_colores", True))

        if not locked:
            if tiene_tallas:
                st.multiselect("Tallas", options=["XS", "S", "M", "L", "XL", "XXL", "XXXL", "OS"], key="np_tallas_sel")
            else:
                st.session_state["np_tallas_sel"] = ["OS"]

            if tiene_colores:
                if not color_vals:
                    st.info("No hay colores en Catalogos. Se usará 'Standard'.")
                    st.session_state["np_colores_sel"] = ["Standard"]
                else:
                    st.multiselect("Colores", options=color_vals, key="np_colores_sel")
            else:
                st.session_state["np_colores_sel"] = ["Standard"]

            b1, b2 = st.columns(2)
            with b1:
                if st.button("✅ Aplicar variantes", use_container_width=True):
                    _np_lock_variants()
                    st.rerun()
            with b2:
                if st.button("🧹 Limpiar formulario", use_container_width=True):
                    _np_reset_all()
                    st.rerun()

        if locked:
            v = st.session_state.get("np_variants", {}) or {}
            v_colors = [str(x) for x in (v.get("colores") or ["Standard"]) if str(x).strip()]
            v_sizes = [str(x).upper() for x in (v.get("tallas") or ["OS"]) if str(x).strip()]

            st.markdown(
                f"**Variantes:** {len(v_colors)} color(es) × {len(v_sizes)} talla(s) = **{len(v_colors) * len(v_sizes)} SKU(s)**"
            )

            top_l, top_r = st.columns(2)
            with top_l:
                if st.button("↩️ Editar variantes", use_container_width=True):
                    _np_unlock_variants()
                    st.rerun()
            with top_r:
                if st.button("🧹 Limpiar", use_container_width=True):
                    _np_reset_all()
                    st.rerun()

            st.markdown("### Stock inicial (unidades)")

            total_units = 0
            stock_map: dict[tuple[str, str], int] = {}

            def _stk_key(color: str, talla: str) -> str:
                c = re.sub(r"[^A-Za-z0-9]", "", str(color)).upper()[:12] or "STD"
                t = re.sub(r"[^A-Za-z0-9]", "", str(talla)).upper()[:6] or "OS"
                return f"np_stock_{c}_{t}"

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

            st.caption(f"**Total de unidades:** {int(total_units)}")

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

            if st.button("💾 Guardar producto", use_container_width=True, disabled=not can_save, type="primary"):
                try:
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
                            cat_write = pd.concat(
                                [cat_write, pd.DataFrame([{"Catalogo": "DROP", "Valor": nd, "Codigo": nd_code}])],
                                ignore_index=True,
                            )
                            save_sheet(conn, SHEET_CATALOGOS, cat_write)

                    drop_sel = str(st.session_state.get("np_drop_sel", "")).strip()
                    drop_code = next(
                        (str(d.get("codigo", "")).strip() for d in drops if str(d.get("valor", "")).strip() == drop_sel),
                        None,
                    )
                    if not drop_code or str(drop_code).lower() == "nan":
                        drop_code = drop_sel.strip().upper()

                    raw_pc = re.sub(r"[^A-Za-z0-9]", "", str(st.session_state.get("np_prod_code", "")).strip()).upper()[:3] or "PRD"
                    prod_code = (raw_pc + "XXX")[:3]

                    costo = float(st.session_state.get("np_costo", 0.0) or 0.0)
                    precio = float(st.session_state.get("np_precio", 0.0) or 0.0)
                    almacen = str(st.session_state.get("np_almacen", "Casa"))

                    existing_code = get_existing_product_code(inv_df, nombre)
                    if existing_code:
                        prod_code = str(existing_code).strip().upper()[:3]

                    inv_now = load_inventario(conn, ttl_s=45).copy()
                    existing_skus = set(inv_now["SKU"].astype(str).str.strip().tolist())

                    rows = []
                    for col in v_colors:
                        col_label = str(col).strip() if tiene_colores else "Standard"
                        col_code = color_to_code2.get(col_label) or color_to_code2.get(col_label.title())
                        if not col_code:
                            col_code = re.sub(r"\s+", "", col_label).upper()[:3] or "STD"
                        for talla in v_sizes:
                            talla_label = str(talla).strip().upper() if tiene_tallas else "OS"
                            sku_new = build_sku(drop_code, prod_code, col_code, talla_label)
                            qty = int(stock_map.get((col, talla), 0) or 0)
                            rows.append({
                                "SKU": sku_new,
                                "Drop": drop_code,
                                "Producto": nombre,
                                "Color": col_label,
                                "Talla": talla_label,
                                "Stock_Casa": qty if almacen == "Casa" else 0,
                                "Stock_Bodega": qty if almacen == "Bodega" else 0,
                                "Costo_Unitario": float(costo),
                                "Precio_Lista": float(precio),
                                "Activo": True,
                            })

                    ok_unique, dups = ensure_unique_skus([r["SKU"] for r in rows], existing_skus)
                    if not ok_unique:
                        st.error("SKUs duplicados: " + ", ".join(dups))
                        st.stop()

                    inv_out = inv_now.copy()
                    for col in INV_REQUIRED:
                        if col not in inv_out.columns:
                            inv_out[col] = None
                    inv_out = pd.concat([inv_out, pd.DataFrame(rows)], ignore_index=True)
                    save_sheet(conn, SHEET_INVENTARIO, inv_out)

                    st.success(f"✅ Producto creado: {nombre} ({len(rows)} SKU(s))")
                    st.cache_data.clear()
                    _np_reset_all()
                    st.rerun()

                except Exception as e:
                    st.error("Error al guardar el producto.")
                    st.exception(e)
