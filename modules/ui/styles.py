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
              padding-bottom: 92px;
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

          .mode-tab-marker,
          .mode-tab-active,
          .bodega-tab-marker,
          .bodega-tab-active {
            display: none;
          }

          div[data-testid="column"]:has(.mode-tab-marker) div[data-testid="stButton"] > button,
          div[data-testid="column"]:has(.mode-tab-active) div[data-testid="stButton"] > button {
            min-height: 66px !important;
            border-radius: 20px !important;
            border: 1px solid rgba(255,255,255,0.06) !important;
            background: rgba(255,255,255,0.03) !important;
            color: rgba(255,255,255,0.70) !important;
            font-size: 1rem !important;
            font-weight: 700 !important;
            box-shadow: none !important;
          }

          div[data-testid="column"]:has(.mode-tab-marker) div[data-testid="stButton"] > button:hover,
          div[data-testid="column"]:has(.mode-tab-active) div[data-testid="stButton"] > button:hover {
            border-color: rgba(255,255,255,0.10) !important;
            background: rgba(255,255,255,0.05) !important;
            color: rgba(255,255,255,0.92) !important;
          }

          div[data-testid="column"]:has(.mode-tab-active) div[data-testid="stButton"] > button {
            background: rgba(255,255,255,0.10) !important;
            color: rgba(255,255,255,0.98) !important;
            border-color: rgba(255,255,255,0.10) !important;
          }

          div[data-testid="column"]:has(.bodega-tab-marker) div[data-testid="stButton"] > button,
          div[data-testid="column"]:has(.bodega-tab-active) div[data-testid="stButton"] > button {
            min-height: 62px !important;
            border-radius: 18px !important;
            border: 1px solid rgba(255,255,255,0.10) !important;
            background: rgba(255,255,255,0.04) !important;
            color: rgba(255,255,255,0.70) !important;
            font-size: 1rem !important;
            font-weight: 700 !important;
            box-shadow: none !important;
          }

          div[data-testid="column"]:has(.bodega-tab-marker) div[data-testid="stButton"] > button:hover,
          div[data-testid="column"]:has(.bodega-tab-active) div[data-testid="stButton"] > button:hover {
            border-color: rgba(255,255,255,0.14) !important;
            background: rgba(255,255,255,0.06) !important;
            color: rgba(255,255,255,0.92) !important;
          }

          div[data-testid="column"]:has(.bodega-tab-active) div[data-testid="stButton"] > button {
            border-color: rgba(34,197,94,0.55) !important;
            background: rgba(34,197,94,0.16) !important;
            color: #38d46a !important;
            box-shadow: inset 0 0 0 1px rgba(34,197,94,0.12) !important;
          }

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

          .scheletro-bottom-nav {
              position: fixed;
              bottom: 0;
              left: 0;
              right: 0;
              z-index: 9999;
              width: 100%;
              max-width: 720px;
              margin: 0 auto 14px auto;
              border-radius: 22px;
              background: rgba(16,16,16,0.92);
              border: 1px solid rgba(255,255,255,0.08);
              box-shadow: 0 10px 34px rgba(0,0,0,0.55);
              padding: 10px 10px 8px 10px;
              backdrop-filter: blur(10px);
          }
          .scheletro-bottom-nav div[data-testid="stButton"] > button {
              width: 100%;
              border: 0 !important;
              background: transparent !important;
              color: rgba(255,255,255,0.70) !important;
              padding: 10px 6px !important;
              border-radius: 16px !important;
              font-weight: 600 !important;
              line-height: 1.05 !important;
          }
          .scheletro-bottom-nav div[data-testid="stButton"] > button:hover {
              background: rgba(255,255,255,0.06) !important;
              color: rgba(255,255,255,0.92) !important;
          }
          .scheletro-bottom-nav div[data-testid="stButton"] > button:focus {
              outline: none !important;
              box-shadow: 0 0 0 2px rgba(34,197,94,0.30) !important;
          }
          .scheletro-bottom-nav .is-active button {
              color: rgba(34,197,94,1) !important;
          }
          .scheletro-bottom-nav .is-active button:hover {
              background: rgba(34,197,94,0.10) !important;
          }

          /* ── FIX MÓVIL: forzar botones del nav siempre en fila ── */
          div[data-testid="stVerticalBlock"]:has(.scheletro-bottom-nav-marker)
            div[data-testid="stHorizontalBlock"] {
              flex-direction: row !important;
              flex-wrap: nowrap !important;
              gap: 4px !important;
              align-items: stretch !important;
          }
          div[data-testid="stVerticalBlock"]:has(.scheletro-bottom-nav-marker)
            div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
              flex: 1 1 0 !important;
              min-width: 0 !important;
              width: auto !important;
          }
          /* Reducir padding interior en botones del nav en pantallas pequeñas */
          @media (max-width: 480px) {
              .scheletro-bottom-nav div[data-testid="stButton"] > button {
                  padding: 8px 2px !important;
                  font-size: 0.78rem !important;
              }
          }
        </style>
        """,
        unsafe_allow_html=True,
    )
