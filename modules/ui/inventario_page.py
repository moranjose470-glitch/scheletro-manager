from __future__ import annotations

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


def render_inventario_page(conn, inv_df_full, fmt_bodega, bodega1_nombre, bodega2_nombre) -> None:
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