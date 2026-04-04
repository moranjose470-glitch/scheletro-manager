import streamlit as st


def init_navigation_state() -> None:
    if "scheletro_page" not in st.session_state:
        st.session_state.scheletro_page = "Ventas"


def _scheletro_set_page(p: str) -> None:
    st.session_state.scheletro_page = p
    st.rerun()


def render_bottom_nav(page: str) -> None:
    with st.container():
        # Marker para poder “seleccionar” este bloque con CSS y fijarlo abajo
        st.markdown('<div class="scheletro-bottom-nav-marker"></div>', unsafe_allow_html=True)

        # Caja visual (otra capa para estilos)
        st.markdown('<div class="scheletro-bottom-nav">', unsafe_allow_html=True)

        c1, c2, c3, c4 = st.columns(4)

        def _nav_btn(col, label, ico, target):
            active = (page == target)
            wrapper_open = '<div class="is-active">' if active else '<div>'
            wrapper_close = '</div>'
            with col:
                st.markdown(wrapper_open, unsafe_allow_html=True)
                # Botón (no cambia URL, no abre pestaña)
                if st.button(f"{ico}", key=f"nav_{target}", use_container_width=True):
                    _scheletro_set_page(target)
                st.markdown(wrapper_close, unsafe_allow_html=True)

        _nav_btn(c1, "Dashboard", "📊", "Dashboard")
        _nav_btn(c2, "Inventario", "📦", "Inventario")
        _nav_btn(c3, "Ventas", "🛒", "Ventas")
        _nav_btn(c4, "Finanzas", "📈", "Finanzas")

        st.markdown('</div>', unsafe_allow_html=True)
