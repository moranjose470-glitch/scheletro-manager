# -----------------------------
# Sheets / Tabs (DEBEN coincidir con tus pestañas)
# -----------------------------
SHEET_INVENTARIO = "Inventario"
SHEET_VENTAS_CAB = "Ventas_Cabecera"
SHEET_VENTAS_DET = "Ventas_Detalle"
SHEET_CONFIG = "Config"
SHEET_INVERSIONES = "Inversiones"
SHEET_CATEGORIAS = "Categorias"
SHEET_CATALOGOS = "Catalogos"
SHEET_EGRESOS = "Egresos"

# -----------------------------
# Columnas esperadas (sin destruir columnas extra)
# -----------------------------
CAT_REQUIRED = ["Categoria"]

INV_REQUIRED = [
    "SKU",
    "Drop",
    "Producto",
    "Color",
    "Talla",
    "Stock_Casa",
    "Stock_Bodega",
    "Costo_Unitario",
    "Precio_Lista",
    "Activo",
]

CAB_REQUIRED = [
    "Venta_ID",
    "Fecha",
    "Hora",
    "Cliente",
    "Metodo_Pago",
    "Envio_Cobrado_Total",
    "Costo_Logistica_Total",
    "Comision_Porc",
    "Total_Lineas",
    "Total_Cobrado",
    "Comision_Monto",
    "Monto_A_Recibir",
    "Notas",
    "Estado",
]

DET_REQUIRED = [
    "Venta_ID",
    "Linea",
    "SKU",
    "Producto",
    "Drop",
    "Color",
    "Talla",
    "Bodega_Salida",
    "Cantidad",
    "Precio_Unitario",
    "Descuento_Unitario",
    "Subtotal_Linea",
]

INVEST_REQUIRED = [
    "Tipo",
    "Referencia",
    "Monto_Invertido",
    "Notas",
]

EG_REQUIRED = [
    "Egreso_ID",
    "Fecha",
    "Concepto",
    "Categoria",
    "Monto",
    "Notas",
    "Drop",
]