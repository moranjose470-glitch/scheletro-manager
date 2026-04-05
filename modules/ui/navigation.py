import streamlit as st


def init_navigation_state() -> None:
    if "scheletro_page" not in st.session_state:
        st.session_state.scheletro_page = "Ventas"


def _scheletro_set_page(p: str) -> None:
    st.session_state.scheletro_page = p
    st.rerun()


def render_bottom_nav(page: str) -> None:
    with st.container():
        st.markdown('<div class="scheletro-bottom-nav-marker"></div>', unsafe_allow_html=True)

        c1, c2, c3, c4 = st.columns(4)

        def _nav_btn(col, label: str, ico: str, target: str) -> None:
            active = page == target
            with col:
                marker_cls = "scheletro-nav-state active" if active else "scheletro-nav-state"
                st.markdown(f'<div class="{marker_cls}"></div>', unsafe_allow_html=True)
                if st.button(ico, key=f"nav_{target}", use_container_width=True, help=label):
                    _scheletro_set_page(target)

        _nav_btn(c1, "Dashboard", "📊", "Dashboard")
        _nav_btn(c2, "Inventario", "📦", "Inventario")
        _nav_btn(c3, "Ventas", "🛒", "Ventas")
        _nav_btn(c4, "Finanzas", "📈", "Finanzas")
