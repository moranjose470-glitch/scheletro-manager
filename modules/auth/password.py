import hmac

import streamlit as st


# =========================
# Seguridad: Password Gate
# =========================
def require_password() -> None:
    """Bloquea la app con una contraseña guardada en Streamlit Secrets.

    En Streamlit Cloud -> Settings -> Secrets agrega:
    APP_PASSWORD = "TU_CLAVE"
    """
    app_pw = st.secrets.get("APP_PASSWORD", None)
    if not app_pw:
        st.error("No está configurado APP_PASSWORD en Secrets. Ve a Settings → Secrets y agrégalo.")
        st.stop()

    # Invalida sesión si cambia la contraseña (evita sesiones viejas)
    pw_fp = f"len:{len(str(app_pw))}"
    if st.session_state.get("_pw_fp") != pw_fp:
        st.session_state["_pw_fp"] = pw_fp
        st.session_state["_auth_ok"] = False
        st.session_state.pop("_auth_error", None)

    # Si ya está autenticado, botón de logout
    if st.session_state.get("_auth_ok", False):
        with st.sidebar:
            if st.button("Cerrar sesión 🔒", use_container_width=True, key="_logout_btn"):
                st.session_state["_auth_ok"] = False
                st.rerun()
        return

    # Callbacks: se ejecutan antes de instanciar widgets (evita StreamlitAPIException)
    def _login_action():
        pw_in = str(st.session_state.get("_auth_pw", ""))
        if hmac.compare_digest(pw_in, str(app_pw)):
            st.session_state["_auth_ok"] = True
            st.session_state.pop("_auth_error", None)
        else:
            st.session_state["_auth_ok"] = False
            st.session_state["_auth_error"] = "Contraseña incorrecta."

    def _clear_action():
        st.session_state["_auth_pw"] = ""
        st.session_state.pop("_auth_error", None)

    st.title("SCHELETRO Manager 🔒")
    st.markdown("### Acceso restringido")

    with st.form("login_form", clear_on_submit=True):
        st.text_input("Contraseña", type="password", key="_auth_pw")
        c1, c2 = st.columns([1, 1])
        with c1:
            st.form_submit_button("Entrar", use_container_width=True, on_click=_login_action)
        with c2:
            st.form_submit_button("Limpiar", use_container_width=True, on_click=_clear_action)

    err = st.session_state.get("_auth_error")
    if err:
        st.error(err)

    st.stop()