# -----------------------------
# Sheets / Tabs (DEBEN coincidir con tus pestañas)
# -----------------------------
SHEET_INVENTARIO = "Inventario"
SHEET_VENTAS_CAB = "Ventas_Cabecera"
SHEET_VENTAS_DET = "Ventas_Detalle"
SHEET_CONFIG = "Config"
SHEET_INVERSIONES = "Inversiones"
SHEET_CATEGORIAS = "Categorias"
CAB_REQUIRED = ["Venta_ID", "Fecha", "Cliente", "Total"]
DET_REQUIRED = ["Detalle_ID", "Venta_ID", "Producto", "Cantidad", "Precio"]
INV_REQUIRED = ["Inventario_ID", "Producto", "Cantidad", "Ubicacion"]
INVEST_REQUIRED = ["Inversion_ID", "Fecha", "Monto", "Descripcion"]
CAT_REQUIRED = ["Categoria"]
EG_REQUIRED = ["Egreso_ID", "Fecha", "Concepto", "Categoria", "Monto", "Notas", "Drop"]

# -----------------------------
# -----------------------------
# Catálogos (Drops / Colores) + generación de SKU

SHEET_CATALOGOS = "Catalogos"

# -----------------------------
# Egresos
SHEET_EGRESOS = "Egresos"
EG_REQUIRED = ["Egreso_ID", "Fecha", "Concepto", "Categoria", "Monto", "Notas", "Drop"]
