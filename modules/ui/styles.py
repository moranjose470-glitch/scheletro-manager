from contextlib import contextmanager

import streamlit as st


# -----------------------------
# UI helpers (tu estilo card)
# -----------------------------
def money(x: float) -> str:
    try:
        return f"${float(x):,.2f}"
    except Exception:
        return "$0.00"


def normalize_html(html: str) -> str:
    return "\n".join(line.lstrip() for line in html.splitlines()).strip()


@contextmanager
def card():
    with st.container():
        st.markdown('<div class="card-marker"></div>', unsafe_allow_html=True)
        yield


def inject_css() -> None:
    st.markdown(
        """
        <style>
          .block-container {
              padding-top: 0.6rem;
              padding-bottom: 118px;
              max-width: 100%;
          }
          #MainMenu {visibility: hidden;}
          footer {visibility: hidden;}
          header {visibility: hidden;}
          .stVerticalBlock { gap: 0.6rem; }

          @media (min-width: 768px) {
              .block-container {
                  max-width: 720px;
                  margin-left: auto;
                  margin-right: auto;
              }
          }

          .card-marker { display:none; }
          div[data-testid="stVerticalBlock"]:has(.card-marker) {
            border: 1px solid rgba(255,255,255,0.08);
            background: rgba(20,20,20,0.72);
            border-radius: 22px;
            padding: 16px 16px;
            backdrop-filter: blur(8px);
          }
          div[data-testid="stVerticalBlock"]:has(.card-marker) > div:first-child { margin-top: 0 !important; }

          .card-html {
            border: 1px solid rgba(255,255,255,0.08);
            background: rgba(20,20,20,0.72);
            border-radius: 22px;
            padding: 16px 16px;
            backdrop-filter: blur(8px);
          }

          .app-header { margin: 0 0 6px 0; }
          .app-top-label {
            font-size: 0.82rem;
            opacity: 0.62;
            letter-spacing: 0.35px;
            margin: 0 0 2px 0;
          }
          .app-page-title {
            font-size: 2.15rem;
            font-weight: 800;
            line-height: 1.08;
            margin: 0 0 10px 0;
          }

          /* Marcadores para los botones de modo (Ventas/Egresos) y bodega */
          .mode-tab-marker,
          .mode-tab-active,
          .bodega-tab-marker,
          .bodega-tab-active,
          .scheletro-nav-state {
            display: none;
          }

          /* =========================================================
             REGLAS RESPONSIVAS PARA BOTONES EN FILA (2 o 3 columnas)
             ========================================================= */
          
          div[data-testid="stHorizontalBlock"]:has(> div[data-testid="stColumn"] > .mode-tab-marker,
                                                   > div[data-testid="stColumn"] > .mode-tab-active,
                                                   > div[data-testid="stColumn"] > .bodega-tab-marker,
                                                   > div[data-testid="stColumn"] > .bodega-tab-active,
                                                   > div[data-testid="stColumn"] > .scheletro-nav-state) {
              flex-wrap: nowrap !important;
          }

          div[data-testid="stColumn"]:has(.mode-tab-marker),
          div[data-testid="stColumn"]:has(.mode-tab-active),
          div[data-testid="stColumn"]:has(.bodega-tab-marker),
          div[data-testid="stColumn"]:has(.bodega-tab-active),
          div[data-testid="stColumn"]:has(.scheletro-nav-state) {
              flex: 1 1 0% !important;
              min-width: 0 !important;
          }

          div[data-testid="stColumn"]:has(.mode-tab-marker) div[data-testid="stButton"] > button,
          div[data-testid="stColumn"]:has(.mode-tab-active) div[data-testid="stButton"] > button,
          div[data-testid="stColumn"]:has(.bodega-tab-marker) div[data-testid="stButton"] > button,
          div[data-testid="stColumn"]:has(.bodega-tab-active) div[data-testid="stButton"] > button,
          div[data-testid="stColumn"]:has(.scheletro-nav-state) div[data-testid="stButton"] > button {
              white-space: normal !important;
              word-break: break-word !important;
              width: 100% !important;
          }

          @media (max-width: 480px) {
              div[data-testid="stColumn"]:has(.mode-tab-marker) div[data-testid="stButton"] > button,
              div[data-testid="stColumn"]:has(.mode-tab-active) div[data-testid="stButton"] > button,
              div[data-testid="stColumn"]:has(.bodega-tab-marker) div[data-testid="stButton"] > button,
              div[data-testid="stColumn"]:has(.bodega-tab-active) div[data-testid="stButton"] > button {
                  font-size: 0.85rem !important;
                  padding: 8px 4px !important;
              }
              div[data-testid="stColumn"]:has(.scheletro-nav-state) div[data-testid="stButton"] > button {
                  font-size: 0.7rem !important;
                  padding: 6px 2px !important;
              }
          }

          /* =========================================================
             ESTILOS VISIBLES PARA BOTONES (sin necesidad de hover)
             ========================================================= */

          /* Botones de modo (Ventas/Egresos) */
          div[data-testid="column"]:has(.mode-tab-marker) div[data-testid="stButton"] > button,
          div[data-testid="column"]:has(.mode-tab-active) div[data-testid="stButton"] > button {
            min-height: 66px !important;
            border-radius: 20px !important;
            border: 1px solid rgba(255,255,255,0.15) !important;
            background: rgba(255,255,255,0.08) !important;  /* Más visible */
            color: rgba(255,255,255,0.90) !important;      /* Texto más claro */
            font-size: 1rem !important;
            font-weight: 700 !important;
            box-shadow: none !important;
          }

          div[data-testid="column"]:has(.mode-tab-marker) div[data-testid="stButton"] > button:hover,
          div[data-testid="column"]:has(.mode-tab-active) div[data-testid="stButton"] > button:hover {
            border-color: rgba(255,255,255,0.25) !important;
            background: rgba(255,255,255,0.12) !important;
            color: rgba(255,255,255,1) !important;
          }

          div[data-testid="column"]:has(.mode-tab-active) div[data-testid="stButton"] > button {
            background: rgba(255,255,255,0.15) !important;
            border-color: rgba(255,255,255,0.25) !important;
            color: white !important;
          }

          /* Botones de bodega (Casa/Bodega) */
          div[data-testid="column"]:has(.bodega-tab-marker) div[data-testid="stButton"] > button,
          div[data-testid="column"]:has(.bodega-tab-active) div[data-testid="stButton"] > button {
            min-height: 62px !important;
            border-radius: 18px !important;
            border: 1px solid rgba(255,255,255,0.15) !important;
            background: rgba(255,255,255,0.08) !important;
            color: rgba(255,255,255,0.90) !important;
            font-size: 1rem !important;
            font-weight: 700 !important;
            box-shadow: none !important;
          }

          div[data-testid="column"]:has(.bodega-tab-marker) div[data-testid="stButton"] > button:hover,
          div[data-testid="column"]:has(.bodega-tab-active) div[data-testid="stButton"] > button:hover {
            border-color: rgba(255,255,255,0.25) !important;
            background: rgba(255,255,255,0.12) !important;
            color: white !important;
          }

          div[data-testid="column"]:has(.bodega-tab-active) div[data-testid="stButton"] > button {
            border-color: rgba(34,197,94,0.7) !important;
            background: rgba(34,197,94,0.2) !important;
            color: #38d46a !important;
            box-shadow: inset 0 0 0 1px rgba(34,197,94,0.2) !important;
          }

          /* Resto de estilos existentes (sin cambios importantes) */
          .sche-section-title {
            font-size: 1.08rem;
            font-weight: 700;
            margin: 0 0 12px 0;
          }

          .small-note { opacity:0.72; font-size: 0.86rem; }
          .pill {
            display:inline-block;
            padding:4px 10px;
            border-radius:999px;
            border:1px solid rgba(255,255,255,0.10);
            background:rgba(255,255,255,0.03);
          }

          .sku-band {
            background: rgba(0,0,0,0.35);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 16px;
            padding: 10px 12px;
            margin: 10px 0 10px 0;
            display: flex;
            justify-content: space-between;
            gap: 12px;
            align-items: center;
          }
          .sku-band .sku {
            font-family: monospace;
            font-size: 0.86rem;
            opacity: 0.72;
          }
          .sku-band .price {
            font-weight: 800;
            color: #38d46a;
          }

          .cart-item-title {
            font-weight: 700;
            font-size: 1rem;
            margin: 0 0 2px 0;
          }
          .cart-item-details {
            opacity: 0.75;
            font-size: 0.88rem;
          }
          .cart-item-price {
            color: #38d46a;
            font-weight: 700;
          }

          .summary-grid { display: grid; grid-template-columns: 1fr; gap: 10px; }
          .summary-row { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; }
          .summary-label { opacity: 0.75; }
          .summary-value { font-weight: 800; }
          .total-cobrado { font-size: 1.12rem; font-weight: 800; }
          .divider { height:1px; background:rgba(255,255,255,0.10); margin:4px 0; }
          .monto-recibir { font-size: 1.32rem; font-weight: 900; }
          .gain-ok { color: #38d46a; font-weight: 900; }
          .gain-low { color: #ff4d4d; font-weight: 900; }

          .eg-card {
              background: rgba(20,20,20,0.72);
              border: 1px solid rgba(255,255,255,0.08);
              border-radius: 22px;
              padding: 18px 18px;
              margin: 10px 0 14px 0;
              backdrop-filter: blur(8px);
          }
          .eg-h1 {
              font-size: 1.5rem;
              font-weight: 800;
              margin: 0 0 10px 0;
          }
          .eg-label {
              opacity: 0.85;
              font-weight: 600;
              margin-bottom: 6px;
          }
          .eg-amount {
              font-size: 2.8rem;
              font-weight: 900;
              letter-spacing: 0.4px;
              line-height: 1.0;
              margin: 0;
          }
          .eg-amount small {
              font-size: 1.15rem;
              opacity: 0.8;
              font-weight: 800;
          }
          .movimiento-item {
              display:flex;
              justify-content:space-between;
              align-items:center;
              gap:12px;
              padding: 12px 0;
              border-bottom:1px solid rgba(255,255,255,0.06);
          }
          .movimiento-item:last-child { border-bottom:none; }
          .movimiento-concepto { font-weight:700; }
          .movimiento-fecha { opacity:0.62; font-size:0.82rem; }
          .movimiento-monto { color:#ff4d4d; font-weight:800; }

          input, textarea { font-size: 16px !important; }

          .scheletro-bottom-nav-marker {
              display: none;
          }

          div[data-testid="stVerticalBlock"]:has(.scheletro-bottom-nav-marker) {
              position: sticky !important;
              bottom: max(10px, env(safe-area-inset-bottom)) !important;
              z-index: 900 !important;
              margin-top: 18px !important;
              padding: 0 !important;
              background: transparent !important;
              border: 0 !important;
              box-shadow: none !important;
          }

          div[data-testid="stVerticalBlock"]:has(.scheletro-bottom-nav-marker) > div[data-testid="stHorizontalBlock"] {
              background: rgba(10,10,10,0.92);
              border: 1px solid rgba(255,255,255,0.08);
              border-radius: 22px;
              padding: 10px;
              backdrop-filter: blur(10px);
              box-shadow: 0 10px 34px rgba(0,0,0,0.45);
              gap: 6px !important;
              align-items: stretch !important;
          }

          div[data-testid="stVerticalBlock"]:has(.scheletro-bottom-nav-marker) > div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
              min-width: 0 !important;
          }

          /* Botones de la barra inferior (ahora visibles sin hover) */
          div[data-testid="stVerticalBlock"]:has(.scheletro-bottom-nav-marker)
            div[data-testid="stButton"] > button {
              width: 100%;
              min-height: 58px !important;
              border-radius: 16px !important;
              border: 1px solid rgba(255,255,255,0.15) !important;
              background: rgba(255,255,255,0.07) !important;
              color: rgba(255,255,255,0.85) !important;
              padding: 8px 2px !important;
              font-size: 0.78rem !important;
              font-weight: 700 !important;
              line-height: 1.05 !important;
              white-space: pre-line !important;
              box-shadow: none !important;
          }

          div[data-testid="stVerticalBlock"]:has(.scheletro-bottom-nav-marker)
            div[data-testid="stButton"] > button:hover {
              background: rgba(255,255,255,0.12) !important;
              color: white !important;
              border-color: rgba(255,255,255,0.25) !important;
          }

          div[data-testid="column"]:has(.scheletro-nav-state.active)
            div[data-testid="stButton"] > button {
              background: rgba(34,197,94,0.18) !important;
              border-color: rgba(34,197,94,0.5) !important;
              color: #38d46a !important;
          }

          div[data-testid="column"]:has(.scheletro-nav-state.active)
            div[data-testid="stButton"] > button:hover {
              background: rgba(34,197,94,0.25) !important;
          }

          @media (max-width: 480px) {
              .block-container {
                  padding-bottom: 118px;
              }
              div[data-testid="stVerticalBlock"]:has(.scheletro-bottom-nav-marker)
                div[data-testid="stButton"] > button {
                  min-height: 54px !important;
                  font-size: 0.74rem !important;
              }
          }
        </style>
        """,
        unsafe_allow_html=True,
    )