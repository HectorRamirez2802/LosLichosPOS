"""
ticket.py  —  Generación de tickets para Los Lichos
----------------------------------------------------
• Genera un PDF con formato térmico de 80 mm (226 pt de ancho).
• Ofrece imprimir directamente con el visor PDF del sistema.
• Se puede usar desde pos.py y ventas.py sin dependencias extra.

Dependencia: reportlab  →  pip install reportlab
"""

import os
import sys
import subprocess
import tempfile
from datetime import datetime

from reportlab.lib.units import mm
from reportlab.lib.pagesizes import landscape
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, black, white

# ─── DATOS DE LA TIENDA ───────────────────────────────────────────────────────
TIENDA = {
    "nombre":    "Los Lichos",
    "direccion": "Norte 12 entre Oriente 5 y 7",
    "ciudad":    "94300 Orizaba, Ver., México",
    "telefono":  "+52 1 477 288 3651",
    "pie":       "¡Gracias por tu compra!",
}

# ─── DIMENSIONES TICKET TÉRMICO 80 mm ────────────────────────────────────────
ANCHO_PT   = 226        # 80 mm en puntos (1 mm ≈ 2.835 pt)
MARGEN     = 8 * mm
ANCHO_UTIL = ANCHO_PT - 2 * MARGEN

# Tipografías disponibles sin instalar nada extra
FONT_NORMAL = "Helvetica"
FONT_BOLD   = "Helvetica-Bold"

# Categorías cuya garantía aplica con el proveedor, no con la tienda
CATS_GARANTIA_PROVEEDOR = {
    "📺 Electrónica",
    "🔌 Línea blanca",
    "🛋 Muebles y decoración",
    "🛋️ Muebles y decoración",  # variante con emoji extendido
}


# ─── GENERADOR PRINCIPAL ──────────────────────────────────────────────────────
def generar_pdf(venta: dict, items: list, ruta: str | None = None,
                abono_info: dict | None = None) -> str:
    """
    Genera el PDF del ticket y lo guarda en `ruta`.
    Si `ruta` es None, crea un archivo temporal.
    Devuelve la ruta del PDF generado.

    venta:      dict con keys  → id, fecha, cliente, total, pagado, tipo
    items:      lista de dicts → nombre_producto, cantidad, precio_unitario, subtotal, categoria
    abono_info: (opcional) dict con keys → monto, pagado_antes
    """
    if ruta is None:
        fd, ruta = tempfile.mkstemp(suffix=".pdf", prefix=f"ticket_{venta['id']}_")
        os.close(fd)

    # Cada item ocupa siempre 2 líneas (nombre + detalle numérico)
    # y una línea adicional si tiene motivo/nota (para que nunca se corte)
    items_con_nota = sum(1 for it in items if (it.get("nota_item") or "").strip())
    lineas_items = len(items) * 2
    desc = venta.get("descuento", {})
    tiene_desc   = bool(desc and desc.get("monto", 0) > 0)
    tiene_motivo = bool(tiene_desc and (desc.get("motivo") or desc.get("etiqueta")))
    extra_desc = (0 if not tiene_desc else (46 * mm if tiene_motivo else 36 * mm))
    tiene_cliente = venta.get("cliente", "Mostrador") != "Mostrador"

    # ¿Algún ítem es de categoría con garantía de proveedor?
    tiene_garantia = any(
        (item.get("categoria") or "").strip() in CATS_GARANTIA_PROVEEDOR
        for item in items
    )
    es_abono      = venta.get("tipo") == "abono"
    es_saldado    = es_abono and venta.get("pagado", 0) >= venta.get("total", 0)

    alto_pt = (
        16 * mm   # encabezado tienda (nombre + slogan)
        + 14 * mm # dirección, ciudad, teléfono
        + 6 * mm  # separador
        + 10 * mm # folio + fecha
        + (9 * mm if tiene_cliente else 0)  # cliente (opcional)
        + 9 * mm  # tipo de pago
        + 9 * mm  # método de pago
        + 6 * mm  # separador
        + 7 * mm  # cabecera tabla
        + lineas_items * 14 * mm  # filas
        + items_con_nota * 8 * mm  # línea extra de motivo por ítem con nota
        + 6 * mm  # separador
        + 18 * mm # totales
        + (20 * mm if abono_info else 0)  # líneas extra del desglose de abono
        + extra_desc
        + (26 * mm if tiene_garantia else 0)  # aviso garantía proveedor
        + (20 * mm if es_abono else 0)        # leyenda 30 días apartado
        + 10 * mm # pie
        + 16 * mm # márgenes
    )

    c = canvas.Canvas(ruta, pagesize=(ANCHO_PT, alto_pt))
    y = alto_pt - MARGEN   # cursor vertical (de arriba hacia abajo)

    def nl(puntos=5):
        """Avanza el cursor hacia abajo."""
        nonlocal y
        y -= puntos

    def texto(txt, x=MARGEN, size=8, bold=False, color=black, align="left"):
        """Dibuja texto en la posición actual."""
        c.setFont(FONT_BOLD if bold else FONT_NORMAL, size)
        c.setFillColor(color)
        if align == "center":
            c.drawCentredString(ANCHO_PT / 2, y, txt)
        elif align == "right":
            c.drawRightString(ANCHO_PT - MARGEN, y, txt)
        else:
            c.drawString(x, y, txt)

    def linea_h(grosor=0.5, color=HexColor("#cccccc")):
        c.setStrokeColor(color)
        c.setLineWidth(grosor)
        c.line(MARGEN, y, ANCHO_PT - MARGEN, y)

    # ── ENCABEZADO ────────────────────────────────────────────────────────────
    nl(2)
    texto(TIENDA["nombre"], size=13, bold=True, align="center")
    nl(11)
    texto("Tu mercancía sin membresía", size=7.5, align="center",
          color=HexColor("#888888"))
    nl(10)
    texto(TIENDA["direccion"], size=7, align="center")
    nl(8)
    texto(TIENDA["ciudad"], size=7, align="center")
    nl(8)
    texto(f"Tel: {TIENDA['telefono']}", size=7, align="center")
    nl(10)

    linea_h(grosor=1)
    nl(8)

    # ── FOLIO Y FECHA ─────────────────────────────────────────────────────────
    fecha_fmt = venta["fecha"][:16].replace("T", "  ")
    texto(f"Folio: #{venta['id']}", size=7.5, bold=True)
    texto(fecha_fmt, size=7.5, align="right")
    nl(9)

    cliente = venta.get("cliente", "Mostrador")
    if cliente != "Mostrador":
        texto(f"Cliente: {cliente}", size=7.5)
        nl(9)

    tipo_label = "Crédito / Abono" if venta["tipo"] == "abono" else "Contado"
    texto(f"Tipo de pago: {tipo_label}", size=7.5)
    nl(9)

    metodo = venta.get("metodo_pago", "efectivo") or "efectivo"
    iconos = {"efectivo": "Efectivo", "tarjeta": "Tarjeta", "transferencia": "Transferencia"}
    metodo_label = iconos.get(metodo, metodo.capitalize())
    texto(f"Método de pago: {metodo_label}", size=7.5)
    nl(9)

    linea_h()
    nl(8)

    # ── CABECERA DE TABLA ─────────────────────────────────────────────────────
    texto("Producto",  size=7.5, bold=True, x=MARGEN)
    texto("Cant × P.Unit  =  Subtotal", size=7.5, bold=True, align="right")
    nl(7)
    linea_h()
    nl(8)

    # ── FILAS ─────────────────────────────────────────────────────────────────
    SANGRIA = MARGEN + 6

    def truncar_a_ancho(txt, font, size, ancho_max):
        """Corta `txt` (con '…' al final) para que quepa en `ancho_max` puntos,
        midiendo el ancho real del texto en vez de contar caracteres."""
        if c.stringWidth(txt, font, size) <= ancho_max:
            return txt
        corto = txt
        while corto and c.stringWidth(corto + "…", font, size) > ancho_max:
            corto = corto[:-1]
        return corto.rstrip() + "…"

    for item in items:
        nombre    = item["nombre_producto"]
        nota_item = (item.get("nota_item") or "").strip()

        nombre_mostrar = truncar_a_ancho(nombre, FONT_NORMAL, 8, ANCHO_UTIL)
        cant    = item["cantidad"]
        punit   = item.get("precio_ajustado") or item["precio_unitario"]
        sub     = item["subtotal"]

        texto(nombre_mostrar, size=8, x=MARGEN)
        nl(10)

        # El motivo/nota va en su propia línea, así el nombre largo
        # nunca se lo come.
        if nota_item:
            nota_mostrar = truncar_a_ancho(
                f"↳ {nota_item}", FONT_NORMAL, 7, ANCHO_UTIL - 6
            )
            texto(nota_mostrar, size=7, x=SANGRIA, color=HexColor("#fbbf24"))
            nl(9)

        detalle_izq = f"{cant} \u00d7 ${punit:.2f}"
        texto(detalle_izq, size=7.5, x=SANGRIA, color=HexColor("#555555"))
        texto(f"${sub:.2f}", size=7.5, bold=True, align="right")
        nl(12)

    nl(2)
    linea_h(grosor=1)
    nl(9)

    # ── TOTALES ───────────────────────────────────────────────────────────────
    total    = venta["total"]
    pagado   = venta["pagado"]
    cambio   = max(0.0, pagado - total)
    restante = max(0.0, total - pagado)

    # Descuento (opcional)
    desc = venta.get("descuento", {})
    if desc and desc.get("monto", 0) > 0:
        subtotal_orig = venta.get("subtotal", total)
        monto_desc    = desc["monto"]
        tipo_desc     = desc.get("tipo", "porcentaje")
        valor_desc    = desc.get("valor", 0)
        motivo        = desc.get("motivo", "") or desc.get("etiqueta", "") or ""

        texto("Subtotal:", size=8)
        texto(f"${subtotal_orig:.2f}", size=8, align="right")
        nl(10)

        if tipo_desc == "porcentaje":
            desc_label = f"Descuento: {valor_desc:.4g}%"
        else:
            desc_label = f"Descuento: −${monto_desc:.2f}"
        c.setFillColor(HexColor("#888888"))
        c.setFont(FONT_BOLD, 8)
        c.drawString(MARGEN, y, desc_label)
        c.drawRightString(ANCHO_PT - MARGEN, y, f"−${monto_desc:.2f}")
        c.setFillColor(black)
        nl(8)

        if motivo and motivo != desc_label:
            import re
            match = re.search(r'\((.+?)\)\s*$', motivo)
            motivo_limpio = match.group(1) if match else motivo
            if motivo_limpio:
                c.setFillColor(HexColor("#888888"))
                c.setFont(FONT_NORMAL, 7)
                c.drawString(MARGEN, y, motivo_limpio)
                c.setFillColor(black)
                nl(6)

        linea_h(grosor=0.5, color=HexColor("#888888"))
        nl(8)

    texto("TOTAL:", size=9, bold=True)
    texto(f"${total:.2f}", size=9, bold=True, align="right")
    nl(11)

    # Si es un ticket de abono puntual, mostrar desglose del movimiento
    if abono_info:
        pagado_antes_ab = float(abono_info.get("pagado_antes", 0))
        monto_ab        = float(abono_info.get("monto", 0))
        texto("Abonado antes:", size=8, color=HexColor("#888888"))
        texto(f"${pagado_antes_ab:.2f}", size=8, align="right",
              color=HexColor("#888888"))
        nl(10)
        texto("Este abono:", size=8, bold=True)
        texto(f"+${monto_ab:.2f}", size=8, bold=True,
              color=HexColor("#4ade80"), align="right")
        nl(10)
        prod_liq = abono_info.get("producto_liquidado", "")
        if prod_liq:
            texto(f"Liquidacion de: {prod_liq}", size=7.5,
                  color=HexColor("#fbbf24"))
            nl(9)
        linea_h(grosor=0.5, color=HexColor("#2a2f45"))
        nl(8)
        texto("Total pagado:", size=8)
        texto(f"${pagado:.2f}", size=8, align="right")
        nl(10)
    else:
        texto("Pagado:", size=8)
        texto(f"${pagado:.2f}", size=8, align="right")
        nl(10)

    if cambio > 0:
        texto("Cambio:", size=8)
        texto(f"${cambio:.2f}", size=8, align="right")
        nl(10)

    if restante > 0:
        texto("Saldo pendiente:", size=8, bold=True,
              color=HexColor("#cc3333"))
        texto(f"${restante:.2f}", size=8, bold=True,
              align="right", color=HexColor("#cc3333"))
        nl(10)

    nl(2)
    linea_h()
    nl(10)

    # ── AVISO DE GARANTÍA (Electrónica, Línea blanca, Muebles) ───────────────
    if tiene_garantia:
        texto("Garantia del producto", size=7, bold=True, align="center",
            color=HexColor("#555555"))
        nl(9)
        texto("aplica directamente con el proveedor", size=6.5, align="center",
            color=HexColor("#777777"))
        nl(8)
        texto("o fabricante.", size=6.5, align="center",
            color=HexColor("#777777"))
        nl(7)
        linea_h(grosor=0.5, color=HexColor("#777777"))
        nl(8)

    # ── LEYENDA DE APARTADO (solo abonos) ────────────────────────────────────
    if es_abono:
        nl(3)
        c.setFont(FONT_NORMAL, 6.5)
        c.setFillColor(HexColor("#888888"))
        c.drawCentredString(ANCHO_PT / 2, y, "En Sistema de Apartado tienes 30 días para liquidar")
        nl(8)
        c.drawCentredString(ANCHO_PT / 2, y, "a partir de la expedición de este ticket.")
        c.setFillColor(black)
        nl(10)

    # ── PIE ───────────────────────────────────────────────────────────────────
    texto(TIENDA["pie"], size=8, bold=True, align="center")
    nl(8)

# ── MARCA DE AGUA "LIQUIDADO" (abono saldado) ─────────────────────────────
    if es_saldado:

        c.saveState()

        c.setFillColor(HexColor("#cc0000"), alpha=0.13)
        c.setFont(FONT_BOLD, 42)

        cx = ANCHO_PT / 2 + (5 * mm)

        # Centrar sobre el área de productos
        mm_hasta_productos = (
            16 + 14 + 6 + 10 +
            (9 if tiene_cliente else 0) +
            9 + 9 + 6 + 7
        ) * mm

        inicio_productos = alto_pt - mm_hasta_productos
        altura_productos = lineas_items * 14 * mm

        # Se sube aproximadamente 32 mm para compensar la rotación
        cy = inicio_productos - (altura_productos / 2) + (60 * mm)

        c.translate(cx, cy)
        c.rotate(38) 
        c.drawCentredString(0, 0, "LIQUIDADO")

        c.restoreState()

    c.save()
    return ruta

# ─── IMPRIMIR ─────────────────────────────────────────────────────────────────
def imprimir_pdf(ruta: str):
    """
    Abre el PDF con el visor/impresor predeterminado del sistema.
    En Windows usa `start`, en macOS `open`, en Linux `xdg-open`.
    """
    try:
        if sys.platform.startswith("win"):
            os.startfile(ruta)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", ruta])
        else:
            subprocess.Popen(["xdg-open", ruta])
    except Exception as e:
        print(f"[ticket] No se pudo abrir el PDF: {e}")


# ─── API PÚBLICA ──────────────────────────────────────────────────────────────
def ticket_desde_venta_id(venta_id: int, abrir: bool = True) -> str:
    """
    Genera (y opcionalmente abre) el ticket de una venta existente en DB.
    Devuelve la ruta del PDF.
    """
    import sqlite3
    import database as db

    conn = sqlite3.connect(db.DB_PATH)
    conn.row_factory = sqlite3.Row

    venta = conn.execute(
        "SELECT * FROM ventas WHERE id = ?", (venta_id,)
    ).fetchone()

    # JOIN con productos para traer la categoría de cada ítem
    items = conn.execute("""
        SELECT vi.*, p.categoria
        FROM venta_items vi
        LEFT JOIN productos p ON p.id = vi.producto_id
        WHERE vi.venta_id = ?
        ORDER BY vi.id ASC
    """, (venta_id,)).fetchall()

    conn.close()

    if not venta:
        raise ValueError(f"No existe la venta #{venta_id}")

    venta_dict = dict(venta)

    # Reconstruir el dict de descuento a partir de las columnas guardadas
    desc_monto = venta_dict.get("descuento_monto") or 0
    if desc_monto > 0:
        etiq = venta_dict.get("descuento_etiq", "") or ""
        import re
        match = re.search(r'\((.+?)\)\s*$', etiq)
        motivo_rec = match.group(1) if match else ""
        venta_dict["descuento"] = {
            "monto":    desc_monto,
            "tipo":     venta_dict.get("descuento_tipo", ""),
            "valor":    venta_dict.get("descuento_valor", 0),
            "etiqueta": etiq,
            "motivo":   motivo_rec,
        }
        venta_dict["subtotal"] = venta_dict.get("subtotal_orig") or venta_dict["total"]
    else:
        venta_dict["descuento"] = {}
        venta_dict["subtotal"]  = venta_dict["total"]

    ruta = generar_pdf(venta_dict, [dict(i) for i in items])
    if abrir:
        imprimir_pdf(ruta)
    return ruta


def ticket_desde_datos(venta: dict, items: list,
                       guardar_en: str | None = None,
                       abrir: bool = True) -> str:
    """
    Genera el ticket a partir de datos en memoria (útil justo después de registrar
    la venta, antes de cerrar el diálogo).
    Devuelve la ruta del PDF.

    IMPORTANTE: cada dict en `items` debe incluir el campo 'categoria'
    para que el aviso de garantía de proveedor funcione correctamente.
    """
    ruta = generar_pdf(venta, items, ruta=guardar_en)
    if abrir:
        imprimir_pdf(ruta)
    return ruta


# ─── TICKET DE ABONO ──────────────────────────────────────────────────────────
def generar_pdf_abono(abono: dict, venta: dict, ruta: str | None = None) -> str:
    """
    Genera un comprobante PDF de un abono individual.

    abono: dict con keys → id, monto, fecha, nota, tipo, metodo_pago
    venta: dict con keys → id, cliente, total, pagado, fecha
    Devuelve la ruta del PDF generado.
    """
    if ruta is None:
        fd, ruta = tempfile.mkstemp(
            suffix=".pdf", prefix=f"abono_{abono['id']}_venta_{venta['id']}_"
        )
        os.close(fd)

    alto_pt = (
        16 * mm   # encabezado tienda
        + 14 * mm # dirección
        + 6 * mm  # separador
        + 10 * mm # folio venta + fecha abono
        + 10 * mm # cliente
        + 6 * mm  # separador
        + 64 * mm # cuerpo: monto, tipo, método, saldo (ampliado por desglose)
        + 10 * mm # pie
        + 14 * mm # márgenes
    )

    c = canvas.Canvas(ruta, pagesize=(ANCHO_PT, alto_pt))
    y = alto_pt - MARGEN

    def nl(puntos=5):
        nonlocal y
        y -= puntos

    def texto(txt, x=MARGEN, size=8, bold=False, color=black, align="left"):
        c.setFont(FONT_BOLD if bold else FONT_NORMAL, size)
        c.setFillColor(color)
        if align == "center":
            c.drawCentredString(ANCHO_PT / 2, y, txt)
        elif align == "right":
            c.drawRightString(ANCHO_PT - MARGEN, y, txt)
        else:
            c.drawString(x, y, txt)

    def linea_h(grosor=0.5, color=HexColor("#cccccc")):
        c.setStrokeColor(color)
        c.setLineWidth(grosor)
        c.line(MARGEN, y, ANCHO_PT - MARGEN, y)

    # ── ENCABEZADO ────────────────────────────────────────────────────────────
    nl(2)
    texto(TIENDA["nombre"], size=13, bold=True, align="center")
    nl(11)
    texto("Tu mercancía sin membresía", size=7.5, align="center",
          color=HexColor("#888888"))
    nl(10)
    texto(TIENDA["direccion"], size=7, align="center")
    nl(8)
    texto(TIENDA["ciudad"], size=7, align="center")
    nl(8)
    texto(f"Tel: {TIENDA['telefono']}", size=7, align="center")
    nl(10)

    linea_h(grosor=1)
    nl(8)

    # ── TÍTULO COMPROBANTE ────────────────────────────────────────────────────
    texto("COMPROBANTE DE ABONO", size=9, bold=True, align="center")
    nl(11)

    # ── DATOS IDENTIFICADORES ─────────────────────────────────────────────────
    fecha_abono = abono["fecha"][:16].replace("T", "  ")
    texto(f"Abono #: {abono['id']}", size=7.5, bold=True)
    texto(fecha_abono, size=7.5, align="right")
    nl(9)

    texto(f"Folio venta: #{venta['id']}", size=7.5)
    texto(venta["fecha"][:10], size=7.5, align="right")
    nl(9)

    cliente = venta.get("cliente", "Mostrador")
    texto(f"Cliente: {cliente}", size=7.5)
    nl(9)

    linea_h()
    nl(8)

    # ── DETALLE DEL ABONO ─────────────────────────────────────────────────────
    c.setFont(FONT_BOLD, 16)
    c.setFillColor(HexColor("#4ade80"))
    c.drawCentredString(ANCHO_PT / 2, y, f"+${abono['monto']:.2f}")
    c.setFillColor(black)
    nl(18)

    tipo = abono.get("tipo", "abono")
    if tipo == "liquidacion":
        tipo_label = "Liquidación de producto"
        nota_txt   = abono.get("nota") or ""
        if nota_txt:
            texto(f"Producto: {nota_txt}", size=7.5, align="center",
                  color=HexColor("#fbbf24"))
            nl(9)
    else:
        tipo_label = "Abono a cuenta"
        nota_txt   = abono.get("nota") or ""
        if nota_txt:
            texto(nota_txt, size=7.5, align="center",
                  color=HexColor("#888888"))
            nl(9)

    texto(tipo_label, size=7.5, align="center", color=HexColor("#888888"))
    nl(9)

    metodo = abono.get("metodo_pago", "efectivo") or "efectivo"
    iconos = {"efectivo": "Efectivo", "tarjeta": "Tarjeta", "transferencia": "Transferencia"}
    metodo_label = iconos.get(metodo, metodo.capitalize())
    texto(f"Método de pago: {metodo_label}", size=7.5, align="center")
    nl(9)

    linea_h(grosor=0.5, color=HexColor("#2a2f45"))
    nl(8)

    # ── RESUMEN DE CUENTA ─────────────────────────────────────────────────────
    total_venta = venta["total"]
    pagado_tras = venta["pagado"]           # ya incluye este abono
    monto_abono = abono["monto"]
    pagado_antes = max(pagado_tras - monto_abono, 0.0)
    restante    = max(total_venta - pagado_tras, 0.0)

    texto("Total de la venta:", size=7.5)
    texto(f"${total_venta:.2f}", size=7.5, align="right")
    nl(9)

    texto("Abonado anteriormente:", size=7.5, color=HexColor("#888888"))
    texto(f"${pagado_antes:.2f}", size=7.5, align="right", color=HexColor("#888888"))
    nl(9)

    texto("Este abono:", size=7.5, bold=True)
    texto(f"+${monto_abono:.2f}", size=7.5, bold=True,
          color=HexColor("#4ade80"), align="right")
    nl(9)

    linea_h(grosor=0.5, color=HexColor("#2a2f45"))
    nl(7)

    texto("Total pagado:", size=7.5)
    texto(f"${pagado_tras:.2f}", size=7.5, bold=True,
          color=HexColor("#4ade80"), align="right")
    nl(9)

    if restante > 0:
        texto("Saldo pendiente:", size=8, bold=True,
              color=HexColor("#ff6b6b"))
        texto(f"${restante:.2f}", size=8, bold=True,
              color=HexColor("#ff6b6b"), align="right")
        nl(9)
    else:
        texto("✔ Cuenta saldada", size=8, bold=True,
              color=HexColor("#4ade80"), align="center")
        nl(9)

    nl(2)
    linea_h()
    nl(10)

    # ── PIE ───────────────────────────────────────────────────────────────────
    texto(TIENDA["pie"], size=8, bold=True, align="center")
    nl(8)

    c.save()
    return ruta


def ticket_desde_abono(abono_id: int, abrir: bool = True) -> str:
    """
    Genera el ticket de venta completo (mismo formato que la reimpresión normal)
    pero con el desglose puntual de ese abono en la sección de totales:
      Abonado antes: $X  |  Este abono: +$Y  |  Total pagado: $Z  |  Resta: $W
    El campo `pagado` de la venta se ajusta al acumulado hasta ese abono.
    Devuelve la ruta del PDF.
    """
    import sqlite3
    import database as db

    conn = sqlite3.connect(db.DB_PATH)
    conn.row_factory = sqlite3.Row

    abono = conn.execute(
        "SELECT * FROM abonos WHERE id = ?", (abono_id,)
    ).fetchone()
    if not abono:
        conn.close()
        raise ValueError(f"No existe el abono #{abono_id}")
    abono = dict(abono)

    venta = conn.execute(
        "SELECT * FROM ventas WHERE id = ?", (abono["venta_id"],)
    ).fetchone()
    items = conn.execute("""
        SELECT vi.*, p.categoria
        FROM venta_items vi
        LEFT JOIN productos p ON p.id = vi.producto_id
        WHERE vi.venta_id = ?
        ORDER BY vi.id ASC
    """, (abono["venta_id"],)).fetchall()

    # Cuánto se había pagado ANTES de este abono
    abonos_anteriores = conn.execute("""
        SELECT COALESCE(SUM(monto), 0) AS suma
        FROM abonos
        WHERE venta_id = ? AND fecha < ?
    """, (abono["venta_id"], abono["fecha"])).fetchone()
    conn.close()

    if not venta:
        raise ValueError(f"No existe la venta #{abono['venta_id']}")

    pagado_antes = float(abonos_anteriores["suma"])
    pagado_tras  = pagado_antes + float(abono["monto"])

    venta_dict = dict(venta)

    # Reconstruir descuento
    import re
    desc_monto = venta_dict.get("descuento_monto") or 0
    if desc_monto > 0:
        etiq = venta_dict.get("descuento_etiq", "") or ""
        match = re.search(r'\((.+?)\)\s*$', etiq)
        motivo_rec = match.group(1) if match else ""
        venta_dict["descuento"] = {
            "monto":    desc_monto,
            "tipo":     venta_dict.get("descuento_tipo", ""),
            "valor":    venta_dict.get("descuento_valor", 0),
            "etiqueta": etiq,
            "motivo":   motivo_rec,
        }
        venta_dict["subtotal"] = venta_dict.get("subtotal_orig") or venta_dict["total"]
    else:
        venta_dict["descuento"] = {}
        venta_dict["subtotal"]  = venta_dict["total"]

    # Ajustar pagado al momento del abono
    venta_dict["pagado"] = pagado_tras

    abono_info = {
        "monto":        float(abono["monto"]),
        "pagado_antes": pagado_antes,
        "producto_liquidado": (abono["nota"] or "") if abono.get("tipo") == "liquidacion" else "",
    }

    ruta = generar_pdf(venta_dict, [dict(i) for i in items], abono_info=abono_info)
    if abrir:
        imprimir_pdf(ruta)
    return ruta


def ticket_abono_desde_datos(abono: dict, venta: dict,
                              guardar_en: str | None = None,
                              abrir: bool = True) -> str:
    """
    Genera el comprobante de abono desde datos en memoria
    (útil justo después de registrar el abono).
    Devuelve la ruta del PDF.
    """
    ruta = generar_pdf_abono(abono, venta, ruta=guardar_en)
    if abrir:
        imprimir_pdf(ruta)
    return ruta