from datetime import datetime

import streamlit as st


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

    st.session_state.setdefault("ventas_modo", "ventas")
    st.session_state.setdefault("eg_monto", 0.0)
    st.session_state.setdefault("eg_fecha", datetime.now().date())
    st.session_state.setdefault("eg_concepto", "")
    st.session_state.setdefault("eg_categoria_sel", "(Sin categoría)")
    st.session_state.setdefault("eg_categoria_new", "")
    st.session_state.setdefault("eg_drop_sel", "")
    st.session_state.setdefault("eg_notas", "")


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

