import sqlite3
import os
import re
import unicodedata
from datetime import datetime, timedelta, date

# ─── CONFIGURACIÓN ────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "pos.db")


# ─── CONEXIÓN ─────────────────────────────────────────────────────────────────
def get_connection():
    """
    Conexión SQLite con ajustes seguros para POS.
    timeout evita errores momentáneos de "database is locked" si una venta/abono
    coincide con una lectura; WAL mantiene buena respuesta en lecturas concurrentes.
    """
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous  = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA temp_store = MEMORY")
    return conn


# ─── CREAR TABLAS ─────────────────────────────────────────────────────────────
def crear_tablas():
    conn = get_connection()
    cursor = conn.cursor()

    # PRODUCTOS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS productos (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo_barras  TEXT    NOT NULL UNIQUE,
            nombre         TEXT    NOT NULL,
            categoria      TEXT    DEFAULT '',
            precio         REAL    NOT NULL DEFAULT 0,
            costo          REAL    DEFAULT 0,
            stock          INTEGER NOT NULL DEFAULT 0,
            stock_minimo   INTEGER DEFAULT 5,
            activo         INTEGER DEFAULT 1,
            fecha_creacion TEXT    DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # VENTAS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ventas (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha            TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
            cliente          TEXT    DEFAULT 'Mostrador',
            total            REAL    NOT NULL DEFAULT 0,
            pagado           REAL    NOT NULL DEFAULT 0,
            tipo             TEXT    NOT NULL DEFAULT 'contado',
            nota             TEXT    DEFAULT '',
            metodo_pago      TEXT    NOT NULL DEFAULT 'efectivo',
            telefono         TEXT    DEFAULT '',
            subtotal_orig    REAL    DEFAULT 0,
            descuento_monto  REAL    DEFAULT 0,
            descuento_tipo   TEXT    DEFAULT '',
            descuento_valor  REAL    DEFAULT 0,
            descuento_etiq   TEXT    DEFAULT ''
        )
    """)

    # DETALLE DE VENTA
    # liquidado:     1 si el cliente ya pagó este producto
    # entregado:     1 si el producto fue físicamente entregado
    # entregado_a:   nombre de quien recibió el producto
    # fecha_entrega: fecha/hora en que se entregó
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS venta_items (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            venta_id           INTEGER NOT NULL,
            producto_id        INTEGER NOT NULL,
            nombre_producto    TEXT    NOT NULL,
            cantidad           INTEGER NOT NULL DEFAULT 1,
            precio_unitario    REAL    NOT NULL,
            subtotal           REAL    NOT NULL,
            liquidado          INTEGER NOT NULL DEFAULT 0,
            entregado          INTEGER NOT NULL DEFAULT 0,
            entregado_a        TEXT    DEFAULT '',
            fecha_entrega      TEXT    DEFAULT '',
            nota_item          TEXT    DEFAULT '',
            precio_ajustado    REAL    DEFAULT NULL,
            FOREIGN KEY (venta_id)    REFERENCES ventas(id),
            FOREIGN KEY (producto_id) REFERENCES productos(id)
        )
    """)

    # ABONOS
    # tipo: 'abono' (pago parcial normal) | 'liquidacion' (pago de un producto)
    # item_id: referencia al venta_items liquidado (solo para tipo='liquidacion')
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS abonos (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            venta_id    INTEGER NOT NULL,
            monto       REAL    NOT NULL,
            fecha       TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
            nota        TEXT    DEFAULT '',
            tipo        TEXT    NOT NULL DEFAULT 'abono',
            metodo_pago TEXT    NOT NULL DEFAULT 'efectivo',
            item_id     INTEGER DEFAULT NULL,
            FOREIGN KEY (venta_id) REFERENCES ventas(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS devoluciones (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            venta_id       INTEGER NOT NULL,
            item_id        INTEGER NOT NULL,
            producto_id    INTEGER NOT NULL,
            nombre_producto TEXT NOT NULL,
            cantidad       INTEGER NOT NULL,
            importe        REAL NOT NULL DEFAULT 0,
            subtotal_bruto REAL NOT NULL DEFAULT 0,
            salida_dinero  REAL NOT NULL DEFAULT 0,
            motivo         TEXT NOT NULL,
            fecha          TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (venta_id) REFERENCES ventas(id),
            FOREIGN KEY (item_id) REFERENCES venta_items(id),
            FOREIGN KEY (producto_id) REFERENCES productos(id)
        )
    """)


    _crear_indices(cursor)

    conn.commit()
    conn.close()
    print("✅ Tablas creadas correctamente.")




def _crear_indices(cursor):
    """Índices idempotentes para que ventas, abonos e inventario escalen mejor."""
    indices = [
        "CREATE INDEX IF NOT EXISTS idx_productos_activo_nombre ON productos(activo, nombre)",
        "CREATE INDEX IF NOT EXISTS idx_productos_codigo_activo ON productos(codigo_barras, activo)",
        "CREATE INDEX IF NOT EXISTS idx_productos_stock_min ON productos(activo, stock, stock_minimo)",
        "CREATE INDEX IF NOT EXISTS idx_ventas_fecha ON ventas(fecha DESC)",
        "CREATE INDEX IF NOT EXISTS idx_ventas_tipo_fecha ON ventas(tipo, fecha DESC)",
        "CREATE INDEX IF NOT EXISTS idx_ventas_cliente ON ventas(cliente COLLATE NOCASE)",
        "CREATE INDEX IF NOT EXISTS idx_venta_items_venta ON venta_items(venta_id)",
        "CREATE INDEX IF NOT EXISTS idx_venta_items_producto ON venta_items(producto_id)",
        "CREATE INDEX IF NOT EXISTS idx_abonos_venta_fecha ON abonos(venta_id, fecha DESC)",
        "CREATE INDEX IF NOT EXISTS idx_abonos_tipo_venta ON abonos(tipo, venta_id)",
        "CREATE INDEX IF NOT EXISTS idx_devoluciones_fecha ON devoluciones(fecha)",
        "CREATE INDEX IF NOT EXISTS idx_devoluciones_item ON devoluciones(item_id)",
    ]
    for sql in indices:
        cursor.execute(sql)


def optimizar_bd():
    """Ejecuta mantenimiento ligero. Úsalo ocasionalmente, no en cada venta."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        _crear_indices(cur)
        cur.execute("PRAGMA optimize")
        conn.commit()
    finally:
        conn.close()

# ─── MIGRACIÓN (segura e idempotente) ─────────────────────────────────────────
def migrar_schema():
    """
    Añade columnas nuevas a tablas ya existentes sin borrar datos.
    Es seguro llamarlo siempre al arrancar: si la columna ya existe, no hace nada.
    """
    conn = get_connection()
    cur  = conn.cursor()

    # Esta tabla también se crea durante crear_tablas(), pero repetirla aquí
    # permite recuperar bases antiguas o instalaciones donde solo se aplicó
    # parcialmente la actualización del esquema. Debe existir antes de crear
    # sus índices y antes de que las vistas ejecuten consultas sobre ella.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS devoluciones (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            venta_id        INTEGER NOT NULL,
            item_id         INTEGER NOT NULL,
            producto_id     INTEGER NOT NULL,
            nombre_producto TEXT    NOT NULL,
            cantidad        INTEGER NOT NULL,
            importe         REAL    NOT NULL DEFAULT 0,
            subtotal_bruto  REAL    NOT NULL DEFAULT 0,
            salida_dinero   REAL    NOT NULL DEFAULT 0,
            motivo          TEXT    NOT NULL,
            fecha           TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (venta_id) REFERENCES ventas(id),
            FOREIGN KEY (item_id) REFERENCES venta_items(id),
            FOREIGN KEY (producto_id) REFERENCES productos(id)
        )
    """)

    _asegurar_tabla_caducidades(cur)

    migraciones = [
        ("ALTER TABLE venta_items ADD COLUMN liquidado     INTEGER NOT NULL DEFAULT 0",),
        ("ALTER TABLE venta_items ADD COLUMN entregado     INTEGER NOT NULL DEFAULT 0",),
        ("ALTER TABLE venta_items ADD COLUMN entregado_a   TEXT    DEFAULT ''",),
        ("ALTER TABLE venta_items ADD COLUMN fecha_entrega TEXT    DEFAULT ''",),
        ("ALTER TABLE abonos      ADD COLUMN tipo          TEXT    NOT NULL DEFAULT 'abono'",),
        ("ALTER TABLE ventas      ADD COLUMN metodo_pago   TEXT    NOT NULL DEFAULT 'efectivo'",),
        ("ALTER TABLE abonos      ADD COLUMN metodo_pago   TEXT    NOT NULL DEFAULT 'efectivo'",),
        ("ALTER TABLE ventas      ADD COLUMN subtotal_orig   REAL DEFAULT 0",),
        ("ALTER TABLE ventas      ADD COLUMN descuento_monto REAL DEFAULT 0",),
        ("ALTER TABLE ventas      ADD COLUMN descuento_tipo  TEXT DEFAULT ''",),
        ("ALTER TABLE ventas      ADD COLUMN descuento_valor REAL DEFAULT 0",),
        ("ALTER TABLE ventas      ADD COLUMN descuento_etiq  TEXT DEFAULT ''",),
        ("ALTER TABLE venta_items ADD COLUMN nota_item       TEXT DEFAULT ''",),
        ("ALTER TABLE venta_items ADD COLUMN precio_ajustado REAL DEFAULT NULL",),
        # 1 = producto agregado DESPUÉS de aplicado el descuento de la cuenta:
        # se cobra a precio completo y no participa del factor de descuento.
        ("ALTER TABLE venta_items ADD COLUMN sin_descuento INTEGER NOT NULL DEFAULT 0",),
        ("ALTER TABLE ventas      ADD COLUMN telefono        TEXT DEFAULT ''",),
        ("ALTER TABLE abonos      ADD COLUMN item_id         INTEGER DEFAULT NULL",),
        ("ALTER TABLE devoluciones ADD COLUMN subtotal_bruto REAL NOT NULL DEFAULT 0",),
    ]
    for (sql,) in migraciones:
        try:
            cur.execute(sql)
        except sqlite3.OperationalError:
            pass   # columna ya existe → ignorar

    _crear_indices(cur)
    _normalizar_items_con_devolucion_parcial(conn)

    conn.commit()
    conn.close()


def factor_descuento_venta(venta, items):
    """
    Factor de descuento que aplica SOLO a los renglones con descuento.

    El descuento de una cuenta se guarda como un monto único (ventas.
    descuento_monto). Los productos agregados después (venta_items.
    sin_descuento = 1) se cobran a precio completo, así que se excluyen
    del cálculo:  factor = (total - sin_desc) / (subtotal_orig - sin_desc).

    venta : dict/Row con 'subtotal_orig' y 'total'.
    items : renglones de la venta (dicts con 'subtotal', 'sin_descuento'
            y opcionalmente 'cantidad_devuelta'; los devueltos se ignoran).
    """
    so    = float(venta["subtotal_orig"] or 0)
    total = float(venta["total"] or 0)
    if so <= 0:
        return 1.0
    sin_desc = sum(
        float(i.get("subtotal") or 0) for i in items
        if int(i.get("sin_descuento") or 0) and not int(i.get("cantidad_devuelta") or 0)
    )
    base = so - sin_desc
    if base <= 0.0001:
        return 1.0
    return max((total - sin_desc) / base, 0.0)


def subtotal_neto_item(item, factor):
    """Subtotal del renglón ya con descuento (los productos sin_descuento van a precio completo)."""
    f = 1.0 if int(item.get("sin_descuento") or 0) else factor
    return round(float(item.get("subtotal") or 0) * f, 2)


def _factor_desc_conn(conn, venta_id):
    """Igual que factor_descuento_venta, leyendo todo de la BD (dentro de una transacción)."""
    venta = conn.execute(
        "SELECT subtotal_orig, total FROM ventas WHERE id = ?", (venta_id,)
    ).fetchone()
    if venta is None:
        return 1.0
    items = [dict(r) for r in conn.execute("""
        SELECT vi.subtotal, vi.sin_descuento,
               COALESCE((SELECT SUM(d.cantidad) FROM devoluciones d
                         WHERE d.item_id = vi.id), 0) AS cantidad_devuelta
        FROM venta_items vi WHERE vi.venta_id = ?
    """, (venta_id,)).fetchall()]
    return factor_descuento_venta(venta, items)


def _separar_item_devuelto(conn, item, cantidad_devuelta, subtotal_devuelto):
    """Separa unidades devueltas de las que aún pertenecen al cliente.

    Conserva el renglón original como histórico devuelto (y mantiene sus
    referencias en devoluciones) y crea un renglón activo para las unidades
    restantes. Las unidades activas heredan el estado previo de entrega/pago.
    """
    cantidad_original = int(item["cantidad"] or 0)
    cantidad_devuelta = int(cantidad_devuelta or 0)
    cantidad_restante = cantidad_original - cantidad_devuelta
    if cantidad_devuelta <= 0 or cantidad_restante <= 0:
        return

    subtotal_original = float(item["subtotal"] or 0)
    subtotal_devuelto = float(subtotal_devuelto or 0)
    if subtotal_devuelto <= 0:
        subtotal_devuelto = subtotal_original * cantidad_devuelta / max(cantidad_original, 1)
    subtotal_devuelto = round(min(max(subtotal_devuelto, 0), subtotal_original), 2)
    subtotal_restante = round(max(subtotal_original - subtotal_devuelto, 0), 2)

    conn.execute("""
        UPDATE venta_items
        SET cantidad = ?, subtotal = ?, liquidado = 0, entregado = 0,
            entregado_a = '', fecha_entrega = ''
        WHERE id = ?
    """, (cantidad_devuelta, subtotal_devuelto, item["id"]))
    conn.execute("""
        INSERT INTO venta_items
            (venta_id, producto_id, nombre_producto, cantidad, precio_unitario,
             subtotal, liquidado, entregado, entregado_a, fecha_entrega,
             nota_item, precio_ajustado, sin_descuento)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        item["venta_id"], item["producto_id"], item["nombre_producto"],
        cantidad_restante, item["precio_unitario"], subtotal_restante,
        int(item["liquidado"] or 0), int(item["entregado"] or 0),
        item["entregado_a"] or "", item["fecha_entrega"] or "",
        item["nota_item"] or "", item["precio_ajustado"],
        int(item["sin_descuento"] or 0)
    ))


def _normalizar_items_con_devolucion_parcial(conn):
    """Migra devoluciones parciales ya registradas a renglones separados."""
    rows = conn.execute("""
        SELECT vi.*,
               SUM(d.cantidad) AS cantidad_devuelta,
               SUM(d.subtotal_bruto) AS subtotal_devuelto
        FROM venta_items vi
        JOIN devoluciones d ON d.item_id = vi.id
        GROUP BY vi.id
        HAVING SUM(d.cantidad) > 0 AND SUM(d.cantidad) < vi.cantidad
    """).fetchall()
    for item in rows:
        _separar_item_devuelto(
            conn, item, item["cantidad_devuelta"], item["subtotal_devuelto"]
        )


# ══════════════════════════════════════════════════════════════════════════════
#  PRODUCTOS
# ══════════════════════════════════════════════════════════════════════════════

def agregar_producto(codigo_barras, nombre, precio, costo=0, stock=0,
                     categoria="", stock_minimo=5):
    conn = get_connection()
    try:
        # Si el código ya existe pero fue eliminado (activo=0), reactivarlo
        # con los nuevos datos en lugar de rechazarlo
        existente = conn.execute(
            "SELECT id, activo FROM productos WHERE codigo_barras = ?",
            (codigo_barras,)
        ).fetchone()

        if existente:
            if existente["activo"] == 0:
                conn.execute("""
                    UPDATE productos
                    SET nombre = ?, precio = ?, costo = ?, stock = ?,
                        categoria = ?, stock_minimo = ?, activo = 1
                    WHERE codigo_barras = ?
                """, (nombre, precio, costo, stock, categoria, stock_minimo,
                      codigo_barras))
                conn.commit()
                return True
            else:
                # Producto activo con ese código ya existe → rechazar
                return False

        conn.execute("""
            INSERT INTO productos
                (codigo_barras, nombre, precio, costo, stock, categoria, stock_minimo)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (codigo_barras, nombre, precio, costo, stock, categoria, stock_minimo))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def obtener_productos(solo_activos=True):
    conn = get_connection()
    query = "SELECT * FROM productos"
    if solo_activos:
        query += " WHERE activo = 1"
    query += " ORDER BY nombre ASC"
    rows = conn.execute(query).fetchall()
    conn.close()
    return rows


def buscar_por_codigo(codigo_barras):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM productos WHERE codigo_barras = ? AND activo = 1",
        (codigo_barras,)
    ).fetchone()
    conn.close()
    return row


def buscar_por_nombre(texto):
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM productos
        WHERE nombre LIKE ? AND activo = 1
        ORDER BY
            CASE WHEN LOWER(nombre) LIKE ? THEN 0 ELSE 1 END,
            nombre
        LIMIT 10
    """, (f"%{texto}%", f"{texto.lower()}%")).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def buscar_productos_inventario(texto="", limite=500):
    """Búsqueda para el módulo Inventario, por nombre o código."""
    texto = (texto or "").strip().lower()
    conn = get_connection()
    if texto:
        like = f"%{texto}%"
        rows = conn.execute("""
            SELECT * FROM productos
            WHERE activo = 1
              AND (LOWER(nombre) LIKE ? OR LOWER(codigo_barras) LIKE ?)
            ORDER BY
              CASE WHEN LOWER(codigo_barras) = ? THEN 0
                   WHEN LOWER(nombre) LIKE ? THEN 1
                   ELSE 2 END,
              nombre ASC
            LIMIT ?
        """, (like, like, texto, f"{texto}%", int(limite))).fetchall()
    else:
        rows = conn.execute("""
            SELECT * FROM productos
            WHERE activo = 1
            ORDER BY nombre ASC
            LIMIT ?
        """, (int(limite),)).fetchall()
    conn.close()
    return rows


def resumen_productos():
    conn = get_connection()
    row = conn.execute("""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN stock = 0 THEN 1 ELSE 0 END) AS sin_stock,
            SUM(CASE WHEN stock > 0 AND stock <= stock_minimo THEN 1 ELSE 0 END) AS stock_bajo,
            COUNT(DISTINCT NULLIF(categoria, '')) AS categorias
        FROM productos
        WHERE activo = 1
    """).fetchone()
    conn.close()
    return row


def obtener_categorias():
    """Categorías registradas: las que usa al menos un producto activo
    (con o sin stock). Aparecen al dar de alta el primer producto con esa
    categoría y desaparecen cuando ya no queda ninguno que la use."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT DISTINCT TRIM(categoria) AS categoria
        FROM productos
        WHERE activo = 1 AND TRIM(COALESCE(categoria, '')) <> ''
        ORDER BY categoria COLLATE NOCASE
    """).fetchall()
    conn.close()
    return [r["categoria"] for r in rows]


def actualizar_producto(id, codigo_barras, nombre, precio, costo,
                        stock, categoria, stock_minimo):
    conn = get_connection()
    conn.execute("""
        UPDATE productos
        SET codigo_barras = ?, nombre = ?, precio = ?, costo = ?,
            stock = ?, categoria = ?, stock_minimo = ?
        WHERE id = ?
    """, (codigo_barras, nombre, precio, costo, stock, categoria, stock_minimo, id))
    conn.commit()
    conn.close()


def desactivar_producto(id):
    conn = get_connection()
    conn.execute("UPDATE productos SET activo = 0 WHERE id = ?", (id,))
    conn.commit()
    conn.close()


# ══════════════════════════════════════════════════════════════════════════════
#  CADUCIDADES (solo productos de categoría alimenticia; solo se consulta en Inventario)
# ══════════════════════════════════════════════════════════════════════════════

# Con cuántos días de anticipación se avisa que un producto está por caducar.
DIAS_ALERTA_CADUCIDAD = 15

# Una categoría se considera "alimenticia" si contiene alguna de estas palabras
# (sin importar mayúsculas, acentos ni emojis). Para incluir/excluir una
# categoría, agrega o quita su palabra clave aquí.
_CLAVES_CATEGORIA_ALIMENTICIA = (
    "aliment", "despensa", "abarrote", "migaj", "dulc", "golosina", "botana",
    "snack", "bebida", "refresco", "licor", "lacteo", "embutido", "carne",
    "fruta", "verdura", "panader", "galleta", "congelad", "comida",
)


def _sin_acentos(texto):
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in texto if not unicodedata.combining(c)).lower()


def es_categoria_alimenticia(categoria):
    """True si la categoría (texto libre) corresponde a alimentos/bebidas."""
    t = _sin_acentos(categoria)
    return any(clave in t for clave in _CLAVES_CATEGORIA_ALIMENTICIA)


def parsear_fecha_usuario(texto):
    """
    Convierte lo que escribe el usuario a ISO (AAAA-MM-DD).
    Acepta DD/MM/AAAA, DD-MM-AAAA, DD/MM/AA y AAAA-MM-DD. Lanza ValueError.
    """
    t = (texto or "").strip()
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", t)
    if m:
        a, mes, d = int(m[1]), int(m[2]), int(m[3])
    else:
        m = re.fullmatch(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4}|\d{2})", t)
        if not m:
            raise ValueError("Fecha inválida. Usa el formato DD/MM/AAAA.")
        d, mes, a = int(m[1]), int(m[2]), int(m[3])
        if a < 100:
            a += 2000
    try:
        return date(a, mes, d).isoformat()
    except ValueError:
        raise ValueError(f"La fecha «{t}» no existe en el calendario.")


def formatear_fecha(iso):
    """AAAA-MM-DD -> DD/MM/AAAA (si no se puede, devuelve el texto tal cual)."""
    try:
        return datetime.strptime(str(iso)[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return str(iso or "")


def estado_caducidad(fecha_iso, dias=None, hoy=None):
    """
    Devuelve (estado, dias_restantes):
      'caducado'    -> la fecha ya pasó
      'por_caducar' -> vence hoy o dentro de los próximos `dias` días
      'ok'          -> falta más que eso
    """
    dias = DIAS_ALERTA_CADUCIDAD if dias is None else dias
    hoy  = hoy or date.today()
    restantes = (datetime.strptime(str(fecha_iso)[:10], "%Y-%m-%d").date() - hoy).days
    if restantes < 0:
        return "caducado", restantes
    if restantes <= dias:
        return "por_caducar", restantes
    return "ok", restantes


def _asegurar_tabla_caducidades(conn):
    """Crea la tabla si no existe (acepta conexión o cursor). Idempotente."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS producto_caducidades (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id     INTEGER NOT NULL,
            fecha_caducidad TEXT    NOT NULL,
            cantidad        INTEGER DEFAULT NULL,
            FOREIGN KEY (producto_id) REFERENCES productos(id)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_caducidades_producto "
        "ON producto_caducidades(producto_id)"
    )


def obtener_caducidades(producto_id):
    """Fechas de caducidad de un producto, de la más próxima a la más lejana."""
    conn = get_connection()
    try:
        _asegurar_tabla_caducidades(conn)
        rows = conn.execute("""
            SELECT id, fecha_caducidad, cantidad
            FROM producto_caducidades
            WHERE producto_id = ?
            ORDER BY fecha_caducidad ASC, id ASC
        """, (producto_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def obtener_caducidades_productos(producto_ids):
    """{producto_id: [caducidades ordenadas]} para varios productos en pocas consultas."""
    ids = [int(i) for i in producto_ids]
    resultado = {}
    if not ids:
        return resultado
    conn = get_connection()
    try:
        _asegurar_tabla_caducidades(conn)
        for k in range(0, len(ids), 500):
            lote = ids[k:k + 500]
            marcas = ",".join("?" * len(lote))
            for r in conn.execute(f"""
                SELECT id, producto_id, fecha_caducidad, cantidad
                FROM producto_caducidades
                WHERE producto_id IN ({marcas})
                ORDER BY fecha_caducidad ASC, id ASC
            """, lote).fetchall():
                resultado.setdefault(r["producto_id"], []).append(dict(r))
        return resultado
    finally:
        conn.close()


def guardar_caducidades(producto_id, caducidades):
    """
    Reemplaza las fechas de caducidad de un producto.

    caducidades: lista de dicts {"fecha": 'AAAA-MM-DD' o 'DD/MM/AAAA',
                                 "cantidad": int | None (opcional)}.
    Si una misma fecha viene repetida se unifica en un solo renglón
    (cantidades sumadas; sin cantidad si ninguna la traía).
    """
    por_fecha = {}
    for c in (caducidades or []):
        iso = parsear_fecha_usuario(c.get("fecha"))
        cant = c.get("cantidad")
        if cant in ("", None):
            cant = None
        else:
            cant = int(cant)
            if cant <= 0:
                raise ValueError("La cantidad de cada fecha debe ser mayor que cero.")
        if iso in por_fecha:
            previa = por_fecha[iso]
            por_fecha[iso] = None if (previa is None and cant is None) else (previa or 0) + (cant or 0)
        else:
            por_fecha[iso] = cant

    conn = get_connection()
    try:
        _asegurar_tabla_caducidades(conn)
        conn.execute("DELETE FROM producto_caducidades WHERE producto_id = ?", (producto_id,))
        for iso, cant in sorted(por_fecha.items()):
            conn.execute("""
                INSERT INTO producto_caducidades (producto_id, fecha_caducidad, cantidad)
                VALUES (?, ?, ?)
            """, (producto_id, iso, cant))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def eliminar_caducidad(caducidad_id):
    """Quita una fecha puntual (p. ej. cuando ese lote ya se vendió o se retiró)."""
    conn = get_connection()
    try:
        _asegurar_tabla_caducidades(conn)
        conn.execute("DELETE FROM producto_caducidades WHERE id = ?", (caducidad_id,))
        conn.commit()
    finally:
        conn.close()


def obtener_alertas_caducidad(dias=None, hoy=None):
    """
    Fechas ya vencidas o que vencen dentro de los próximos `dias` días.

    Solo cuenta productos activos, de categoría alimenticia y con existencias
    (si el stock es 0 ya no hay nada que pueda caducar).
    Devuelve dicts: id, producto_id, nombre, codigo_barras, categoria, stock,
    fecha_caducidad, cantidad, estado ('caducado'|'por_caducar'), dias_restantes.
    Ordenados de la fecha más próxima a la más lejana.
    """
    dias = DIAS_ALERTA_CADUCIDAD if dias is None else dias
    hoy  = hoy or date.today()
    limite = (hoy + timedelta(days=dias)).isoformat()
    conn = get_connection()
    try:
        _asegurar_tabla_caducidades(conn)
        rows = conn.execute("""
            SELECT c.id, c.producto_id, c.fecha_caducidad, c.cantidad,
                   p.nombre, p.codigo_barras, p.categoria, p.stock
            FROM producto_caducidades c
            JOIN productos p ON p.id = c.producto_id
            WHERE p.activo = 1 AND p.stock > 0 AND c.fecha_caducidad <= ?
            ORDER BY c.fecha_caducidad ASC, p.nombre ASC
        """, (limite,)).fetchall()
    finally:
        conn.close()

    alertas = []
    for r in rows:
        if not es_categoria_alimenticia(r["categoria"]):
            continue
        estado, restantes = estado_caducidad(r["fecha_caducidad"], dias, hoy)
        d = dict(r)
        d["estado"] = estado
        d["dias_restantes"] = restantes
        alertas.append(d)
    return alertas


def descontar_stock(producto_id, cantidad):
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE productos SET stock = stock - ? WHERE id = ? AND stock >= ?",
            (cantidad, producto_id, cantidad)
        )
        if cur.rowcount == 0:
            conn.rollback()
            raise ValueError(
                f"Stock insuficiente para producto_id={producto_id} "
                f"(se intentó descontar {cantidad} unidades)."
            )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def productos_stock_bajo():
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM productos
        WHERE stock <= stock_minimo AND activo = 1
        ORDER BY stock ASC
    """).fetchall()
    conn.close()
    return rows


# ══════════════════════════════════════════════════════════════════════════════
#  VENTAS
# ══════════════════════════════════════════════════════════════════════════════

def registrar_venta(items, tipo="contado", cliente="Mostrador", pagado=None,
                    nota="", metodo_pago="efectivo", descuento=None, telefono=""):
    """
    Registra una venta completa en una sola transacción.

    items: lista de dicts con keys:
        - producto_id
        - nombre_producto
        - cantidad
        - precio_unitario

    descuento: dict opcional con keys tipo, valor, monto, etiqueta

    Devuelve el ID de la venta creada.
    """
    subtotal_orig = sum(i["cantidad"] * (i.get("precio_ajustado") or i["precio_unitario"]) for i in items)
    desc = descuento or {}
    descuento_monto = desc.get("monto", 0) or 0
    descuento_tipo  = desc.get("tipo", "") or ""
    descuento_valor = desc.get("valor", 0) or 0
    descuento_etiq  = desc.get("etiqueta", "") or ""
    total = max(subtotal_orig - descuento_monto, 0)
    if pagado is None:
        pagado = total

    conn = get_connection()
    try:
        cursor = conn.execute("""
            INSERT INTO ventas
                (cliente, total, pagado, tipo, nota, metodo_pago,
                 subtotal_orig, descuento_monto, descuento_tipo, descuento_valor, descuento_etiq,
                 telefono)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (cliente, total, pagado, tipo, nota, metodo_pago,
              subtotal_orig, descuento_monto, descuento_tipo, descuento_valor, descuento_etiq,
              telefono or ""))
        venta_id = cursor.lastrowid

        for item in items:
            precio_u = item.get("precio_ajustado") or item["precio_unitario"]
            subtotal = item["cantidad"] * precio_u
            nota_item = item.get("nota_item", "") or ""
            precio_aj = item.get("precio_ajustado")   # None si no hay ajuste
            conn.execute("""
                INSERT INTO venta_items
                    (venta_id, producto_id, nombre_producto, cantidad,
                     precio_unitario, subtotal, nota_item, precio_ajustado)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (venta_id, item["producto_id"], item["nombre_producto"],
                  item["cantidad"], precio_u, subtotal, nota_item, precio_aj))

            resultado = conn.execute(
                "UPDATE productos SET stock = stock - ? WHERE id = ? AND stock >= ?",
                (item["cantidad"], item["producto_id"], item["cantidad"])
            )
            if resultado.rowcount == 0:
                raise ValueError(
                    f"Stock insuficiente para '{item['nombre_producto']}' "
                    f"(se intentó descontar {item['cantidad']} unidades)."
                )

        if tipo == "abono" and pagado > 0:
            conn.execute("""
                INSERT INTO abonos (venta_id, monto, nota, tipo, metodo_pago)
                VALUES (?, ?, 'Anticipo inicial', 'abono', ?)
            """, (venta_id, pagado, metodo_pago))

        conn.commit()
        return venta_id

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def agregar_item_venta(venta_id, producto_id, nombre_producto, cantidad,
                        precio_unitario, nota_item="", precio_ajustado=None):
    """
    Agrega un producto a una venta/cuenta YA EXISTENTE (usado para agregar
    artículos a una cuenta a crédito sin tener que registrar de nuevo al
    cliente). Descuenta stock y ajusta el total (y subtotal_orig, para no
    romper el cálculo de descuento general) de la venta.

    precio_unitario  : precio normal (de catálogo) del producto.
    precio_ajustado  : precio distinto al normal, opcional -- para casos
                        como producto dañado / sin caja / muestra de piso,
                        igual que la nota + ajuste de precio del POS.
    nota_item        : observación del renglón (aparece en el ticket).

    Si el producto ya está en la cuenta como renglón "simple" pendiente
    (no liquidado, no entregado, sin nota ni precio ajustado, mismo precio
    unitario) Y este agregado tampoco trae nota/ajuste, se suma la cantidad
    a ese renglón en lugar de crear uno nuevo -- por ejemplo, si el cliente
    ya tenía 1 Coca en la cuenta y compra otra, queda como "Coca ×2" y no
    como dos productos separados. Un renglón con nota o precio ajustado
    (p.ej. un producto dañado) siempre se agrega aparte, para no mezclar su
    precio/observación con el stock normal.

    Devuelve el ID del venta_items afectado (nuevo o el que se fusionó).
    """
    precio_efectivo = precio_ajustado if precio_ajustado is not None else precio_unitario
    subtotal = cantidad * precio_efectivo
    tiene_nota_o_ajuste = bool((nota_item or "").strip()) or precio_ajustado is not None

    conn = get_connection()
    try:
        venta = conn.execute(
            "SELECT total, subtotal_orig, descuento_monto FROM ventas WHERE id = ?",
            (venta_id,)
        ).fetchone()
        if venta is None:
            raise ValueError(f"La venta/cuenta {venta_id} no existe.")

        # Si la cuenta ya tiene un descuento, el producto nuevo se cobra a
        # precio completo: se marca sin_descuento para que el descuento
        # siga aplicando únicamente a los productos originales.
        sin_desc = 1 if float(venta["descuento_monto"] or 0) > 0 else 0
        # NOTA: una devolución NO cierra la cuenta. Se pueden seguir agregando
        # productos aunque ya existan devoluciones en la venta; los renglones
        # devueltos permanecen bloqueados como historial (ver abajo).

        # Si la cuenta nunca tuvo un descuento general (subtotal_orig en 0,
        # dato legado), la sincronizamos con el total actual antes de sumar,
        # para no generar un "descuento" fantasma al dividir total/subtotal.
        subtotal_orig_actual = venta["subtotal_orig"] or 0
        if subtotal_orig_actual <= 0:
            subtotal_orig_actual = venta["total"]

        # ── Buscar renglón existente para fusionar (mismo producto, aún
        #    "simple": sin liquidar, sin entregar, sin nota/precio ajustado,
        #    mismo precio unitario) -- solo si este agregado tampoco trae
        #    nota ni ajuste de precio ────────────────────────────────────
        existente = None
        if not tiene_nota_o_ajuste:
            existente = conn.execute("""
                SELECT id, cantidad, subtotal FROM venta_items
                WHERE venta_id = ? AND producto_id = ?
                  AND liquidado = 0 AND entregado = 0
                  AND NOT EXISTS (
                      SELECT 1 FROM devoluciones d WHERE d.item_id = venta_items.id
                  )
                  AND (nota_item IS NULL OR nota_item = '')
                  AND precio_ajustado IS NULL
                  AND precio_unitario = ?
                  AND sin_descuento = ?
                ORDER BY id DESC LIMIT 1
            """, (venta_id, producto_id, precio_efectivo, sin_desc)).fetchone()

        if existente:
            item_id = existente["id"]
            conn.execute("""
                UPDATE venta_items
                SET cantidad = cantidad + ?, subtotal = subtotal + ?
                WHERE id = ?
            """, (cantidad, subtotal, item_id))
        else:
            cursor = conn.execute("""
                INSERT INTO venta_items
                    (venta_id, producto_id, nombre_producto, cantidad,
                     precio_unitario, subtotal, nota_item, precio_ajustado,
                     sin_descuento)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (venta_id, producto_id, nombre_producto, cantidad,
                  precio_efectivo, subtotal, nota_item or "", precio_ajustado,
                  sin_desc))
            item_id = cursor.lastrowid

        resultado = conn.execute(
            "UPDATE productos SET stock = stock - ? WHERE id = ? AND stock >= ?",
            (cantidad, producto_id, cantidad)
        )
        if resultado.rowcount == 0:
            raise ValueError(
                f"Stock insuficiente para '{nombre_producto}' "
                f"(se intentó descontar {cantidad} unidades)."
            )

        conn.execute(
            "UPDATE ventas SET total = total + ?, subtotal_orig = ? WHERE id = ?",
            (subtotal, subtotal_orig_actual + subtotal, venta_id)
        )

        conn.commit()
        return item_id

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def eliminar_item_venta(item_id):
    """
    Quita un producto de una cuenta (por ejemplo, si se agregó por error).
    Restaura el stock y resta el importe del total (y subtotal_orig) de
    la venta.

    Solo permite quitar renglones pendientes: si el producto ya fue
    liquidado o entregado, se rechaza para no descuadrar los pagos/entregas
    ya registrados; en ese caso primero hay que revertir la liquidación o
    la entrega desde su propio diálogo.
    """
    conn = get_connection()
    try:
        item = conn.execute(
            "SELECT * FROM venta_items WHERE id = ?", (item_id,)
        ).fetchone()
        if item is None:
            raise ValueError("El producto ya no existe en esta cuenta.")

        if item["liquidado"]:
            raise ValueError(
                "Este producto ya fue liquidado y no se puede quitar. "
                "Si fue un error, primero reviértelo desde el historial de abonos."
            )
        if item["entregado"]:
            raise ValueError(
                "Este producto ya fue marcado como entregado y no se puede quitar. "
                "Primero desmarca la entrega desde el registro de entrega."
            )

        devuelta = conn.execute(
            "SELECT COALESCE(SUM(cantidad), 0) FROM devoluciones WHERE item_id = ?",
            (item_id,)
        ).fetchone()[0]
        if devuelta:
            raise ValueError("Este producto ya tiene una devolución registrada y no se puede quitar de la cuenta.")

        venta = conn.execute(
            "SELECT total, subtotal_orig FROM ventas WHERE id = ?",
            (item["venta_id"],)
        ).fetchone()

        subtotal_orig_actual = venta["subtotal_orig"] or 0
        if subtotal_orig_actual <= 0:
            subtotal_orig_actual = venta["total"]
        nuevo_subtotal_orig = max(subtotal_orig_actual - item["subtotal"], 0)
        # Lo que realmente se descuenta del total es el importe NETO del
        # renglón: completo si es un producto agregado sin descuento, o con
        # el factor de descuento si es uno de los originales.
        if int(item["sin_descuento"] or 0):
            neto = float(item["subtotal"])
        else:
            neto = round(float(item["subtotal"]) * _factor_desc_conn(conn, item["venta_id"]), 2)
        nuevo_total = max(venta["total"] - neto, 0)

        conn.execute(
            "UPDATE productos SET stock = stock + ? WHERE id = ?",
            (item["cantidad"], item["producto_id"])
        )
        conn.execute("DELETE FROM venta_items WHERE id = ?", (item_id,))
        conn.execute(
            "UPDATE ventas SET total = ?, subtotal_orig = ?, descuento_monto = ? WHERE id = ?",
            (nuevo_total, nuevo_subtotal_orig,
             max(round(nuevo_subtotal_orig - nuevo_total, 2), 0.0), item["venta_id"])
        )

        conn.commit()
        return True

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def _fecha_hasta_exclusiva(fecha_hasta: str | None) -> str | None:
    if not fecha_hasta:
        return None
    try:
        return (datetime.strptime(fecha_hasta[:10], "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    except ValueError:
        return None


def _where_ventas(texto="", tipo="todas", fecha_desde=None, fecha_hasta=None):
    where = []
    params = []

    texto = (texto or "").strip().lower()
    if texto:
        where.append("LOWER(cliente) LIKE ?")
        params.append(f"%{texto}%")

    if tipo and tipo != "todas":
        where.append("tipo = ?")
        params.append(tipo)

    if fecha_desde:
        where.append("fecha >= ?")
        params.append(fecha_desde[:10])

    hasta_excl = _fecha_hasta_exclusiva(fecha_hasta)
    if hasta_excl:
        where.append("fecha < ?")
        params.append(hasta_excl)

    return where, params


def obtener_ventas(limite=100):
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM ventas
        ORDER BY fecha DESC
        LIMIT ?
    """, (limite,)).fetchall()
    conn.close()
    return rows


def buscar_ventas_filtradas(texto="", tipo="todas", fecha_desde=None,
                            fecha_hasta=None, limite=200, orden="DESC"):
    """
    Devuelve ventas ya filtradas desde SQLite.
    Evita cargar todo en Python y luego filtrar, que se vuelve lento al crecer la BD.
    """
    where, params = _where_ventas(texto, tipo, fecha_desde, fecha_hasta)
    sql = "SELECT * FROM ventas"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += f" ORDER BY fecha {'ASC' if orden.upper() == 'ASC' else 'DESC'} LIMIT ?"
    params.append(int(limite))

    conn = get_connection()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows


def resumen_ventas(fecha_desde=None, fecha_hasta=None, tipo="todas", texto=""):
    """Resumen rápido para tarjetas: conteo, total y cobrado."""
    where, params = _where_ventas(texto, tipo, fecha_desde, fecha_hasta)
    sql = """
        SELECT
            COUNT(*) AS total_ventas,
            COALESCE(SUM(total), 0) AS monto_total,
            COALESCE(SUM(CASE WHEN tipo = 'contado' THEN pagado + COALESCE(
                (SELECT SUM(d.importe) FROM devoluciones d WHERE d.venta_id = ventas.id), 0
            ) ELSE 0 END), 0)
              + COALESCE((SELECT SUM(a.monto) FROM abonos a
                          JOIN ventas va ON va.id = a.venta_id
                          WHERE va.tipo = 'abono'
                            AND (? IS NULL OR a.fecha >= ?)
                            AND (? IS NULL OR a.fecha < ?)), 0)
              - COALESCE((SELECT SUM(d.salida_dinero) FROM devoluciones d
                          JOIN ventas vd ON vd.id = d.venta_id
                          WHERE vd.tipo = 'contado'
                            AND (? IS NULL OR d.fecha >= ?)
                            AND (? IS NULL OR d.fecha < ?)), 0) AS monto_cobrado
        FROM ventas
    """
    desde_ts = f"{fecha_desde} 00:00:00" if fecha_desde else None
    hasta_ts = f"{_fecha_hasta_exclusiva(fecha_hasta)} 00:00:00" if fecha_hasta else None
    mov_params = [desde_ts, desde_ts, hasta_ts, hasta_ts,
                  desde_ts, desde_ts, hasta_ts, hasta_ts]
    if where:
        sql += " WHERE " + " AND ".join(where)

    conn = get_connection()
    row = conn.execute(sql, mov_params + params).fetchone()
    conn.close()
    return row


def obtener_venta_por_id(venta_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM ventas WHERE id = ?", (venta_id,)).fetchone()
    conn.close()
    return row


def buscar_cuentas_abono(texto="", solo_pendientes=False, limite=300):
    """Cuentas a crédito/abono filtradas desde SQLite."""
    where = ["tipo = 'abono'"]
    params = []

    texto = (texto or "").strip().lower()
    if texto:
        where.append("LOWER(cliente) LIKE ?")
        params.append(f"%{texto}%")
    if solo_pendientes:
        where.append("pagado < total")

    sql = """
        SELECT ventas.*, (total - pagado) AS restante,
               (SELECT MAX(a.fecha) FROM abonos a
                WHERE a.venta_id = ventas.id
                  AND a.tipo IN ('abono', 'liquidacion')
                  AND a.monto > 0) AS ultimo_abono
        FROM ventas
        WHERE {where}
        ORDER BY fecha DESC
        LIMIT ?
    """.format(where=" AND ".join(where))
    params.append(int(limite))

    conn = get_connection()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows


def resumen_cuentas_abono():
    """Resumen para tarjetas del módulo Abonos."""
    conn = get_connection()
    row = conn.execute("""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN pagado < total THEN 1 ELSE 0 END) AS pendientes,
            SUM(CASE WHEN pagado >= total THEN 1 ELSE 0 END) AS saldadas,
            COALESCE(SUM(CASE WHEN pagado < total THEN total - pagado ELSE 0 END), 0) AS deuda
        FROM ventas
        WHERE tipo = 'abono'
    """).fetchone()
    conn.close()
    return row


def obtener_items_venta(venta_id):
    """
    Devuelve los productos de una venta.
    Incluye el campo 'liquidado' y 'categoria' (via JOIN con productos)
    para que el ticket pueda mostrar el aviso de garantía de proveedor.
    """
    conn = get_connection()
    rows = conn.execute("""
        SELECT vi.*, p.categoria,
               COALESCE((SELECT SUM(d.cantidad) FROM devoluciones d
                         WHERE d.item_id = vi.id), 0) AS cantidad_devuelta
        FROM venta_items vi
        LEFT JOIN productos p ON p.id = vi.producto_id
        WHERE vi.venta_id = ?
        ORDER BY vi.id ASC
    """, (venta_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def obtener_devolucion_item(item_id):
    """Devuelve cantidad aún retornable y datos contables del renglón de venta."""
    conn = get_connection()
    try:
        row = conn.execute("""
            SELECT vi.*, v.tipo AS tipo_venta, v.total AS total_venta,
                   v.pagado,
                   CASE WHEN COALESCE(v.subtotal_orig, 0) > 0 THEN v.subtotal_orig
                        ELSE (SELECT COALESCE(SUM(vix.subtotal), 0) FROM venta_items vix
                              WHERE vix.venta_id = v.id) END AS subtotal_orig,
                   v.descuento_monto,
                   COALESCE((SELECT SUM(d.cantidad) FROM devoluciones d
                             WHERE d.item_id = vi.id), 0) AS cantidad_devuelta
                   ,COALESCE((SELECT SUM(d.importe) FROM devoluciones d
                              WHERE d.item_id = vi.id), 0) AS importe_devuelto
                   ,COALESCE((SELECT SUM(d.subtotal_bruto) FROM devoluciones d
                              WHERE d.item_id = vi.id), 0) AS bruto_devuelto
            FROM venta_items vi
            JOIN ventas v ON v.id = vi.venta_id
            WHERE vi.id = ?
        """, (item_id,)).fetchone()
        if not row:
            return None
        info = dict(row)
        info["factor_item"] = (
            1.0 if int(info.get("sin_descuento") or 0)
            else _factor_desc_conn(conn, info["venta_id"])
        )
        return info
    finally:
        conn.close()


def listar_ventas_devolucion(tipo=None, limite=250):
    """Ventas recientes candidatas para registrar devolución."""
    conn = get_connection()
    try:
        if tipo:
            rows = conn.execute("""
                SELECT id, fecha, cliente, tipo, total, pagado FROM ventas
                WHERE tipo = ? ORDER BY fecha DESC, id DESC LIMIT ?
            """, (tipo, int(limite))).fetchall()
        else:
            rows = conn.execute("""
                SELECT id, fecha, cliente, tipo, total, pagado FROM ventas
                ORDER BY fecha DESC, id DESC LIMIT ?
            """, (int(limite),)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def listar_devoluciones(venta_id=None, limite=200):
    conn = get_connection()
    try:
        if venta_id is None:
            rows = conn.execute("""
                SELECT d.*, v.cliente FROM devoluciones d
                JOIN ventas v ON v.id = d.venta_id
                ORDER BY d.fecha DESC, d.id DESC LIMIT ?
            """, (int(limite),)).fetchall()
        else:
            rows = conn.execute("""
                SELECT d.*, v.cliente FROM devoluciones d
                JOIN ventas v ON v.id = d.venta_id
                WHERE d.venta_id = ? ORDER BY d.fecha DESC, d.id DESC LIMIT ?
            """, (int(venta_id), int(limite))).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _aplicar_devolucion_en_conn(conn, item_id, cantidad, motivo, fecha):
    """Núcleo de una devolución dentro de una transacción YA abierta.

    No hace commit ni inserta el movimiento negativo en abonos (eso lo decide
    quien llama, para poder agrupar varios productos en un solo reembolso).
    Devuelve un dict con el detalle de la línea.

    Regla contable (cuentas a crédito): el dinero abonado pertenece a la CUENTA,
    no a un producto. Al devolver productos baja el total de la cuenta y el
    reembolso es solo lo abonado que excede ese nuevo total:
        reembolso = max(pagado - nuevo_total, 0)
    """
    item = conn.execute("""
        SELECT vi.*, v.tipo AS tipo_venta, v.total AS total_venta,
               v.pagado, v.subtotal_orig
        FROM venta_items vi JOIN ventas v ON v.id = vi.venta_id
        WHERE vi.id = ?
    """, (item_id,)).fetchone()
    if not item:
        raise ValueError("No se encontró el producto de la venta.")
    devuelta = conn.execute(
        "SELECT COALESCE(SUM(cantidad), 0) FROM devoluciones WHERE item_id = ?",
        (item_id,)
    ).fetchone()[0]
    disponible = int(item["cantidad"]) - int(devuelta or 0)
    if cantidad > disponible:
        raise ValueError(
            f"Solo quedan {disponible} unidad(es) de '{item['nombre_producto']}' disponibles para devolver."
        )

    bruto = round(float(item["subtotal"]) / max(int(item["cantidad"]), 1) * cantidad, 2)
    subtotal_orig = float(item["subtotal_orig"] or 0)
    total_venta = float(item["total_venta"] or 0)
    if subtotal_orig <= 0:
        subtotal_orig = float(conn.execute(
            "SELECT COALESCE(SUM(subtotal), 0) FROM venta_items WHERE venta_id = ?",
            (item["venta_id"],)
        ).fetchone()[0] or 0)
    bruto_devuelto_item = conn.execute(
        "SELECT COALESCE(SUM(subtotal_bruto), 0) FROM devoluciones WHERE item_id = ?",
        (item_id,)
    ).fetchone()[0]
    # Factor propio del renglón: los productos agregados después del
    # descuento (sin_descuento) se devuelven a precio completo.
    if int(item["sin_descuento"] or 0):
        factor = 1.0
    else:
        factor = _factor_desc_conn(conn, item["venta_id"])
    importe = round(bruto * factor, 2)
    nuevo_total = max(round(total_venta - importe, 2), 0.0)
    nuevo_subtotal = max(round(subtotal_orig - bruto, 2), 0.0)
    pagado = float(item["pagado"] or 0)
    es_credito = item["tipo_venta"] != "contado"
    salida = max(round(pagado - nuevo_total, 2), 0.0) if es_credito else importe
    nuevo_pagado = max(0.0, round(pagado - salida, 2)) if es_credito else nuevo_total

    conn.execute("UPDATE productos SET stock = stock + ? WHERE id = ?",
                 (cantidad, item["producto_id"]))
    conn.execute("""
        UPDATE ventas
        SET total = ?, subtotal_orig = ?, descuento_monto = ?, pagado = ?
        WHERE id = ?
    """, (nuevo_total, nuevo_subtotal, max(round(nuevo_subtotal - nuevo_total, 2), 0.0),
          nuevo_pagado, item["venta_id"]))

    conn.execute("""
        INSERT INTO devoluciones
            (venta_id, item_id, producto_id, nombre_producto, cantidad,
             importe, subtotal_bruto, salida_dinero, motivo, fecha)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (item["venta_id"], item_id, item["producto_id"], item["nombre_producto"],
          cantidad, importe, bruto, salida, motivo, fecha))

    cantidad_devuelta_total = int(devuelta or 0) + cantidad
    subtotal_devuelto_total = float(bruto_devuelto_item or 0) + bruto
    if cantidad_devuelta_total < int(item["cantidad"]):
        # Divide el renglón: la porción devuelta queda bloqueada y el
        # remanente conserva su propio ID y puede entregarse/liquidarse.
        _separar_item_devuelto(
            conn, item, cantidad_devuelta_total, subtotal_devuelto_total
        )
    else:
        conn.execute("""
            UPDATE venta_items
            SET liquidado = 0, entregado = 0, entregado_a = '', fecha_entrega = ''
            WHERE id = ?
        """, (item_id,))

    return {
        "venta_id": item["venta_id"], "item_id": item_id,
        "nombre": item["nombre_producto"], "cantidad": cantidad,
        "importe": importe, "salida": salida, "tipo_venta": item["tipo_venta"],
        "nuevo_total": nuevo_total, "nuevo_pagado": nuevo_pagado,
    }


def _normalizar_selecciones(selecciones):
    """Valida [(item_id, cantidad), ...] y devuelve una lista limpia sin repetidos."""
    if not selecciones:
        raise ValueError("Selecciona al menos un producto para devolver.")
    limpias, vistos = [], set()
    for item_id, cantidad in selecciones:
        try:
            item_id = int(item_id)
            cantidad = int(cantidad)
        except (TypeError, ValueError):
            raise ValueError("La cantidad debe ser un número entero.")
        if cantidad <= 0:
            raise ValueError("La cantidad debe ser mayor que cero.")
        if item_id in vistos:
            raise ValueError("Un mismo producto está repetido en la selección.")
        vistos.add(item_id)
        limpias.append((item_id, cantidad))
    return limpias


def _devolver_lote_en_conn(conn, selecciones, motivo, fecha, reembolso_deseado=None):
    """Aplica varias devoluciones de UNA misma venta y arma el resultado agregado.

    reembolso_deseado: solo cuentas a crédito. Dinero total que el cajero entregará
    al cliente; por defecto es el mínimo automático (lo abonado que excede el nuevo
    total). Puede ser mayor —hasta el crédito libre de la cuenta— cuando el cliente
    pide que le regresen dinero aunque aún le quede saldo por pagar (p. ej. pagó
    un producto en específico, lo devuelve y no quiere dejar ese dinero abonado
    para los demás). El excedente aumenta el saldo pendiente de la cuenta."""
    selecciones = _normalizar_selecciones(selecciones)
    ventas = {
        r["venta_id"] for r in conn.execute(
            "SELECT venta_id FROM venta_items WHERE id IN (%s)" % ",".join("?" * len(selecciones)),
            [s[0] for s in selecciones]
        ).fetchall()
    }
    if len(ventas) != 1:
        raise ValueError("Todos los productos deben pertenecer a la misma venta/cuenta.")
    venta_id = ventas.pop()
    venta_ini = conn.execute(
        "SELECT total, pagado, tipo FROM ventas WHERE id = ?", (venta_id,)
    ).fetchone()

    lineas = [
        _aplicar_devolucion_en_conn(conn, item_id, cant, motivo, fecha)
        for item_id, cant in selecciones
    ]
    venta_fin = conn.execute(
        "SELECT total, pagado, tipo FROM ventas WHERE id = ?", (venta_id,)
    ).fetchone()
    importe = round(sum(l["importe"] for l in lineas), 2)
    salida_auto = round(sum(l["salida"] for l in lineas), 2)
    salida = salida_auto
    reembolso_max = salida_auto

    if venta_ini["tipo"] != "contado":
        # Crédito libre: lo abonado que NO respalda productos liquidados
        # explícitamente (con su propio movimiento de liquidación).
        factor = _factor_desc_conn(conn, venta_id)
        explicito = round(sum(
            float(r["subtotal"]) * (1.0 if int(r["sin_descuento"] or 0) else factor)
            for r in conn.execute("""
                SELECT vi.subtotal, vi.sin_descuento FROM venta_items vi
                WHERE vi.venta_id = ? AND vi.liquidado = 1
                  AND NOT EXISTS (SELECT 1 FROM devoluciones d WHERE d.item_id = vi.id)
                  AND EXISTS (SELECT 1 FROM abonos a
                              WHERE a.venta_id = vi.venta_id AND a.tipo = 'liquidacion'
                                AND (a.item_id = vi.id OR a.nota = vi.nombre_producto))
            """, (venta_id,)).fetchall()
        ), 2)
        libre = max(round(float(venta_fin["pagado"]) - explicito, 2), 0.0)
        reembolso_max = round(salida_auto + libre, 2)

        if reembolso_deseado is not None:
            deseado = round(float(reembolso_deseado), 2)
            if deseado + 0.001 < salida_auto:
                raise ValueError(
                    f"El reembolso no puede ser menor a ${salida_auto:.2f} "
                    "(es lo abonado que excede el nuevo total de la cuenta)."
                )
            if deseado > reembolso_max + 0.001:
                raise ValueError(
                    f"El reembolso máximo posible es ${reembolso_max:.2f}: "
                    "el resto respalda productos ya liquidados que siguen en la cuenta."
                )
            extra = round(deseado - salida_auto, 2)
            if extra > 0:
                conn.execute("UPDATE ventas SET pagado = ? WHERE id = ?",
                             (round(float(venta_fin["pagado"]) - extra, 2), venta_id))
                lineas[-1]["salida"] = round(lineas[-1]["salida"] + extra, 2)
                conn.execute(
                    "UPDATE devoluciones SET salida_dinero = salida_dinero + ? "
                    "WHERE id = (SELECT MAX(id) FROM devoluciones WHERE venta_id = ?)",
                    (extra, venta_id))
                # La cuenta ya no está saldada: los productos que solo se habían
                # marcado como liquidados por estar saldada vuelven a pendientes.
                conn.execute("""
                    UPDATE venta_items SET liquidado = 0
                    WHERE venta_id = ? AND liquidado = 1
                      AND NOT EXISTS (SELECT 1 FROM abonos a
                                      WHERE a.venta_id = venta_items.venta_id
                                        AND a.tipo = 'liquidacion'
                                        AND (a.item_id = venta_items.id
                                             OR a.nota = venta_items.nombre_producto))
                """, (venta_id,))
                salida = deseado
                venta_fin = conn.execute(
                    "SELECT total, pagado, tipo FROM ventas WHERE id = ?", (venta_id,)
                ).fetchone()
    return {
        "venta_id": venta_id,
        "tipo_venta": venta_ini["tipo"],
        "lineas": lineas,
        "piezas": sum(l["cantidad"] for l in lineas),
        "importe": importe,                       # baja del total de la cuenta
        "salida_dinero": salida,                  # dinero que sale de caja
        "salida_automatica": salida_auto,         # mínimo que corresponde por regla
        "reembolso_max": reembolso_max,           # tope que el cajero puede entregar
        "total_antes": float(venta_ini["total"]), "pagado_antes": float(venta_ini["pagado"]),
        "nuevo_total": float(venta_fin["total"]), "nuevo_pagado": float(venta_fin["pagado"]),
        "saldo_pendiente": max(round(float(venta_fin["total"]) - float(venta_fin["pagado"]), 2), 0.0),
    }


def simular_devolucion(selecciones, reembolso_deseado=None):
    """Calcula el efecto de una devolución SIN guardar nada (vista previa).

    Ejecuta la misma lógica que la devolución real dentro de una transacción
    que siempre se revierte, así la vista previa nunca difiere del resultado.
    """
    conn = get_connection()
    try:
        res = _devolver_lote_en_conn(
            conn, selecciones, "simulación", datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            reembolso_deseado
        )
        return res
    finally:
        conn.rollback()
        conn.close()


def registrar_devolucion_multiple(selecciones, motivo, fecha=None, reembolso_deseado=None):
    """Registra la devolución de VARIOS productos de una misma venta en una sola operación.

    selecciones: lista de (item_id, cantidad).

    - Contado: el importe de lo devuelto sale de caja.
    - Crédito/abono: se devuelve al cliente solo lo abonado que excede el nuevo
      total de la cuenta. Los abonos son de la cuenta, no de un producto
      específico, por eso se calcula sobre el conjunto devuelto y no producto
      por producto. Si se devuelve toda la cuenta, se reembolsa todo lo abonado.
    - reembolso_deseado (opcional, solo crédito): entrega más dinero del mínimo
      automático, hasta el crédito libre de la cuenta (ver _devolver_lote_en_conn).
    - El reembolso queda como UN solo movimiento negativo en abonos (así el
      cierre del día refleja la salida de caja en la fecha real de la devolución).
    """
    motivo = (motivo or "").strip()
    if not motivo:
        raise ValueError("Escribe el motivo de la devolución.")
    fecha = fecha or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_connection()
    try:
        res = _devolver_lote_en_conn(conn, selecciones, motivo, fecha, reembolso_deseado)
        if res["tipo_venta"] == "abono" and res["salida_dinero"] > 0:
            conn.execute("""
                INSERT INTO abonos (venta_id, monto, fecha, nota, tipo, metodo_pago)
                VALUES (?, ?, ?, ?, 'devolucion', 'efectivo')
            """, (res["venta_id"], -res["salida_dinero"], fecha, f"Devolución: {motivo}"))
        conn.commit()
        return res
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def registrar_devolucion(item_id, cantidad, motivo):
    """Devolución de un solo producto (se conserva por compatibilidad)."""
    return registrar_devolucion_multiple([(item_id, cantidad)], motivo)


def items_devolubles(venta_id):
    """Productos de la venta con unidades aún devolvibles y su valor NETO unitario.

    El valor neto ya incluye el descuento general de la cuenta, que es lo que
    realmente bajaría del total al devolver cada pieza.
    """
    conn = get_connection()
    try:
        factor = _factor_desc_conn(conn, venta_id)
        rows = conn.execute("""
            SELECT vi.*,
                   COALESCE((SELECT SUM(d.cantidad) FROM devoluciones d
                             WHERE d.item_id = vi.id), 0) AS cantidad_devuelta
            FROM venta_items vi WHERE vi.venta_id = ? ORDER BY vi.id ASC
        """, (venta_id,)).fetchall()
        out = []
        for r in rows:
            r = dict(r)
            disponible = int(r["cantidad"]) - int(r["cantidad_devuelta"] or 0)
            if disponible <= 0:
                continue
            f = 1.0 if int(r.get("sin_descuento") or 0) else factor
            neto_unit = round(float(r["subtotal"]) / max(int(r["cantidad"]), 1) * f, 2)
            r["disponible"] = disponible
            r["neto_unitario"] = neto_unit
            out.append(r)
        return out
    finally:
        conn.close()


def buscar_ventas_devolucion(texto="", tipo="todas", solo_con_pendientes=True, limite=250):
    """Ventas/cuentas candidatas a devolución, con cuánto queda por devolver."""
    where, params = [], []
    if tipo in ("contado", "abono"):
        where.append("v.tipo = ?")
        params.append(tipo)
    texto = (texto or "").strip()
    if texto:
        folio = texto.replace("#", "").strip()
        if folio.isdigit():
            where.append("(v.cliente LIKE ? COLLATE NOCASE OR v.id = ?)")
            params += [f"%{texto}%", int(folio)]
        else:
            where.append("v.cliente LIKE ? COLLATE NOCASE")
            params.append(f"%{texto}%")
    sql = """
        SELECT * FROM (
            SELECT v.id, v.fecha, v.cliente, v.tipo, v.total, v.pagado,
                   COALESCE((SELECT SUM(vi.cantidad) FROM venta_items vi
                             WHERE vi.venta_id = v.id), 0)
                 - COALESCE((SELECT SUM(d.cantidad) FROM devoluciones d
                             WHERE d.venta_id = v.id), 0) AS piezas_disponibles,
                   (SELECT COUNT(*) FROM devoluciones d WHERE d.venta_id = v.id) AS n_devoluciones
            FROM ventas v
            %s
        ) %s
        ORDER BY fecha DESC, id DESC LIMIT ?
    """ % (("WHERE " + " AND ".join(where)) if where else "",
           "WHERE piezas_disponibles > 0" if solo_con_pendientes else "")
    conn = get_connection()
    try:
        return [dict(r) for r in conn.execute(sql, params + [int(limite)]).fetchall()]
    finally:
        conn.close()


def obtener_resumen_venta_devolucion(venta_id):
    """Datos de cabecera de una venta para la pantalla de devoluciones."""
    conn = get_connection()
    try:
        v = conn.execute("SELECT * FROM ventas WHERE id = ?", (venta_id,)).fetchone()
        if not v:
            return None
        v = dict(v)
        ab = conn.execute("""
            SELECT COALESCE(SUM(CASE WHEN monto > 0 THEN monto ELSE 0 END), 0) AS recibido,
                   COALESCE(SUM(CASE WHEN tipo = 'devolucion' THEN -monto ELSE 0 END), 0) AS reembolsado
            FROM abonos WHERE venta_id = ?
        """, (venta_id,)).fetchone()
        v["abonos_recibidos"] = float(ab["recibido"])
        v["reembolsado"] = float(ab["reembolsado"])
        return v
    finally:
        conn.close()


def listar_devoluciones_filtrado(texto="", fecha_desde=None, fecha_hasta=None, limite=300):
    """Historial de devoluciones con búsqueda por cliente/producto/folio y rango de fechas."""
    where, params = [], []
    texto = (texto or "").strip()
    if texto:
        folio = texto.replace("#", "").strip()
        like = f"%{texto}%"
        if folio.isdigit():
            where.append("(v.cliente LIKE ? COLLATE NOCASE OR d.nombre_producto LIKE ? COLLATE NOCASE OR d.venta_id = ?)")
            params += [like, like, int(folio)]
        else:
            where.append("(v.cliente LIKE ? COLLATE NOCASE OR d.nombre_producto LIKE ? COLLATE NOCASE)")
            params += [like, like]
    if fecha_desde:
        where.append("d.fecha >= ?")
        params.append(f"{fecha_desde} 00:00:00")
    hasta_excl = _fecha_hasta_exclusiva(fecha_hasta)
    if hasta_excl:
        where.append("d.fecha < ?")
        params.append(f"{hasta_excl} 00:00:00")
    sql = """
        SELECT d.*, v.cliente, v.tipo AS tipo_venta FROM devoluciones d
        JOIN ventas v ON v.id = d.venta_id
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY d.fecha DESC, d.id DESC LIMIT ?"
    conn = get_connection()
    try:
        return [dict(r) for r in conn.execute(sql, params + [int(limite)]).fetchall()]
    finally:
        conn.close()


def resumen_devoluciones(fecha_desde=None, fecha_hasta=None):
    """Totales de devoluciones del periodo: piezas, valor devuelto y dinero que salió de caja."""
    where, params = [], []
    if fecha_desde:
        where.append("fecha >= ?")
        params.append(f"{fecha_desde} 00:00:00")
    hasta_excl = _fecha_hasta_exclusiva(fecha_hasta)
    if hasta_excl:
        where.append("fecha < ?")
        params.append(f"{hasta_excl} 00:00:00")
    sql = """
        SELECT COUNT(*) AS lineas,
               COALESCE(SUM(cantidad), 0)      AS piezas,
               COALESCE(SUM(importe), 0)       AS importe,
               COALESCE(SUM(salida_dinero), 0) AS salida_caja
        FROM devoluciones
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    conn = get_connection()
    try:
        return dict(conn.execute(sql, params).fetchone())
    finally:
        conn.close()


def ventas_del_dia():
    hoy = datetime.now().strftime("%Y-%m-%d")
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM ventas
        WHERE fecha LIKE ?
        ORDER BY fecha DESC
    """, (f"{hoy}%",)).fetchall()
    conn.close()
    return rows


def ventas_por_producto_en_mes(anio: int, mes: int) -> list:
    """
    Devuelve una lista de dicts con el movimiento de inventario del mes:
      - producto_id
      - nombre
      - stock_actual   (stock actual en la BD; es el stock FINAL al momento del cierre)
      - vendido        (total de unidades vendidas en el mes)
      - stock_inicial  (stock_actual + vendido; lo que había al inicio del mes)
    Solo incluye productos activos.
    """
    prefijo = f"{anio:04d}-{mes:02d}-%"
    conn = get_connection()
    rows = conn.execute("""
        SELECT
            p.id AS producto_id,
            p.nombre AS nombre,
            p.stock AS stock_actual,
            COALESCE((SELECT SUM(vi.cantidad)
                      FROM venta_items vi JOIN ventas v ON v.id = vi.venta_id
                      WHERE vi.producto_id = p.id AND v.fecha LIKE ?), 0)
              - COALESCE((SELECT SUM(d.cantidad) FROM devoluciones d
                          WHERE d.producto_id = p.id AND d.fecha LIKE ?), 0) AS vendido
        FROM productos p
        WHERE p.activo = 1
        ORDER BY p.nombre ASC
    """, (prefijo, prefijo)).fetchall()
    conn.close()

    result = []
    for r in rows:
        vendido       = r["vendido"]
        stock_actual  = r["stock_actual"]
        stock_inicial = stock_actual + vendido
        result.append({
            "nombre":        r["nombre"],
            "stock_inicial": stock_inicial,
            "vendido":       vendido,
            "stock_final":   stock_actual,
        })
    return result


def resumen_del_dia():
    hoy = datetime.now().strftime("%Y-%m-%d")
    conn = get_connection()
    manana = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    row = conn.execute("""
        SELECT
            COUNT(*)    AS total_ventas,
            SUM(total)  AS monto_total,
            COALESCE(SUM(CASE WHEN tipo = 'contado' THEN pagado + COALESCE(
                (SELECT SUM(d.importe) FROM devoluciones d WHERE d.venta_id = ventas.id), 0
            ) ELSE 0 END), 0)
              + COALESCE((SELECT SUM(a.monto) FROM abonos a
                          JOIN ventas va ON va.id = a.venta_id
                          WHERE va.tipo = 'abono' AND a.fecha >= ? AND a.fecha < ?), 0)
              - COALESCE((SELECT SUM(d.salida_dinero) FROM devoluciones d
                          JOIN ventas vd ON vd.id = d.venta_id
                          WHERE vd.tipo = 'contado' AND d.fecha >= ? AND d.fecha < ?), 0)
              AS monto_cobrado
        FROM ventas
        WHERE fecha LIKE ?
    """, (hoy, manana, hoy, manana, f"{hoy}%")).fetchone()
    conn.close()
    return row


def editar_venta(venta_id, cliente, total, pagado, tipo, nota, metodo_pago="efectivo"):
    conn = get_connection()
    try:
        if conn.execute("SELECT 1 FROM devoluciones WHERE venta_id = ? LIMIT 1", (venta_id,)).fetchone():
            raise ValueError("No se puede editar una venta con devoluciones registradas.")
        pagado = min(pagado, total)
        conn.execute("""
            UPDATE ventas
            SET cliente = ?, total = ?, pagado = ?, tipo = ?, nota = ?, metodo_pago = ?
            WHERE id = ?
        """, (cliente, total, pagado, tipo, nota, metodo_pago, venta_id))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def actualizar_telefono_venta(venta_id, telefono):
    """Actualiza solo el teléfono de una venta."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE ventas SET telefono = ? WHERE id = ?",
            (telefono.strip() if telefono else "", venta_id)
        )
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def eliminar_venta(venta_id):
    """
    Elimina una venta, sus ítems y sus abonos.
    Restaura el stock de cada producto afectado.
    """
    conn = get_connection()
    try:
        if conn.execute("SELECT 1 FROM devoluciones WHERE venta_id = ? LIMIT 1", (venta_id,)).fetchone():
            raise ValueError("Esta venta tiene devoluciones registradas y no se puede eliminar para conservar el historial de caja e inventario.")
        items = conn.execute(
            "SELECT producto_id, cantidad FROM venta_items WHERE venta_id = ?",
            (venta_id,)
        ).fetchall()
        for item in items:
            conn.execute(
                "UPDATE productos SET stock = stock + ? WHERE id = ?",
                (item["cantidad"], item["producto_id"])
            )

        conn.execute("DELETE FROM venta_items WHERE venta_id = ?", (venta_id,))
        conn.execute("DELETE FROM abonos       WHERE venta_id = ?", (venta_id,))
        conn.execute("DELETE FROM ventas        WHERE id = ?",       (venta_id,))

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def ventas_con_saldo_pendiente():
    conn = get_connection()
    rows = conn.execute("""
        SELECT *, (total - pagado) AS restante
        FROM ventas
        WHERE tipo = 'abono' AND pagado < total
        ORDER BY fecha DESC
    """).fetchall()
    conn.close()
    return rows


# ══════════════════════════════════════════════════════════════════════════════
#  ABONOS
# ══════════════════════════════════════════════════════════════════════════════

def marcar_items_liquidados_si_saldada(venta_id, conn):
    """
    Auxiliar: si pagado >= total, marca todos los items como liquidados.
    Recibe una conexion abierta (no la cierra).
    """
    venta = conn.execute(
        "SELECT total, pagado FROM ventas WHERE id = ?", (venta_id,)
    ).fetchone()
    if venta and venta["pagado"] >= venta["total"]:
        conn.execute(
            """
            UPDATE venta_items SET liquidado = 1
            WHERE venta_id = ?
              AND NOT EXISTS (
                  SELECT 1 FROM devoluciones d WHERE d.item_id = venta_items.id
              )
            """,
            (venta_id,)
        )


def registrar_abono(venta_id, monto, nota="", metodo_pago="efectivo"):
    """
    Registra un pago parcial normal y actualiza el campo 'pagado' de la venta.
    Si con este abono se salda la deuda completa, marca todos los items
    como liquidados (el cliente se puede llevar todo).
    """
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO abonos (venta_id, monto, nota, tipo, metodo_pago)
            VALUES (?, ?, ?, 'abono', ?)
        """, (venta_id, monto, nota, metodo_pago))

        conn.execute("""
            UPDATE ventas
            SET pagado = MIN(total, pagado + ?)
            WHERE id = ?
        """, (monto, venta_id))

        marcar_items_liquidados_si_saldada(venta_id, conn)

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def obtener_abonos(venta_id):
    """
    Devuelve todos los abonos de una venta en orden descendente (más reciente primero).
    Incluye el campo 'tipo' ('abono' o 'liquidacion').
    """
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM abonos WHERE venta_id = ? ORDER BY fecha DESC, id DESC
    """, (venta_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def editar_abono(abono_id, nuevo_monto, metodo_pago=None):
    """
    Cambia el monto (y opcionalmente el método de pago) de un abono
    y recalcula 'pagado' sumando todos los abonos.
    Solo aplicable a abonos de tipo 'abono' (no liquidaciones).
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT venta_id FROM abonos WHERE id = ?", (abono_id,)
        ).fetchone()
        if not row:
            return False
        venta_id = row["venta_id"]
        tipo_row = conn.execute("SELECT tipo FROM abonos WHERE id = ?", (abono_id,)).fetchone()
        if tipo_row and tipo_row["tipo"] != "abono":
            raise ValueError("Solo se pueden editar abonos normales.")

        if metodo_pago is not None:
            conn.execute(
                "UPDATE abonos SET monto = ?, metodo_pago = ? WHERE id = ?",
                (nuevo_monto, metodo_pago, abono_id)
            )
        else:
            conn.execute(
                "UPDATE abonos SET monto = ? WHERE id = ?",
                (nuevo_monto, abono_id)
            )

        conn.execute("""
            UPDATE ventas
            SET pagado = MIN(total, (
                SELECT COALESCE(SUM(monto), 0) FROM abonos WHERE venta_id = ventas.id
            ))
            WHERE id = ?
        """, (venta_id,))

        marcar_items_liquidados_si_saldada(venta_id, conn)

        venta = conn.execute(
            "SELECT total, pagado FROM ventas WHERE id = ?", (venta_id,)
        ).fetchone()
        if venta and venta["pagado"] < venta["total"]:
            liq_ids = conn.execute("""
                SELECT vi.id
                FROM venta_items vi
                WHERE vi.venta_id = ? AND vi.liquidado = 1
                  AND EXISTS (
                      SELECT 1 FROM abonos a
                      WHERE a.venta_id = ? AND a.tipo = 'liquidacion'
                        AND (a.item_id = vi.id OR a.nota = vi.nombre_producto)
                  )
            """, (venta_id, venta_id)).fetchall()
            liq_set = {r["id"] for r in liq_ids}

            items_liq = conn.execute(
                "SELECT id FROM venta_items WHERE venta_id = ? AND liquidado = 1",
                (venta_id,)
            ).fetchall()
            for it in items_liq:
                if it["id"] not in liq_set:
                    conn.execute(
                        "UPDATE venta_items SET liquidado = 0 WHERE id = ?",
                        (it["id"],)
                    )

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def eliminar_abono(abono_id):
    """
    Elimina un abono y recalcula 'pagado'.
    - Si era de tipo 'liquidacion': revierte el item asociado a liquidado=0.
    - Si era abono normal y la cuenta ya no queda saldada: des-marca los items
      que se habian marcado automaticamente (los que no tienen liquidacion propia).
    """
    conn = get_connection()
    try:
        abono = conn.execute(
            "SELECT * FROM abonos WHERE id = ?", (abono_id,)
        ).fetchone()
        if not abono:
            return False

        if (abono["tipo"] or "abono") == "devolucion":
            raise ValueError("Los reembolsos de devolución no se pueden borrar desde el historial de abonos.")

        venta_id = abono["venta_id"]
        tipo     = abono["tipo"] if abono["tipo"] else "abono"

        if tipo == "liquidacion":
            # Preferir item_id directo (columna agregada); fallback por subtotal para
            # abonos antiguos que no tienen item_id guardado.
            item_id_liq = abono["item_id"] if abono["item_id"] else None
            if item_id_liq:
                conn.execute(
                    "UPDATE venta_items SET liquidado = 0 WHERE id = ?",
                    (item_id_liq,)
                )
            else:
                # Fallback: buscar por nota (nombre producto) entre los liquidados
                nota = abono["nota"] or ""
                item = conn.execute("""
                    SELECT id FROM venta_items
                    WHERE venta_id = ? AND liquidado = 1
                      AND nombre_producto = ?
                    ORDER BY id DESC
                    LIMIT 1
                """, (venta_id, nota)).fetchone()
                if item:
                    conn.execute(
                        "UPDATE venta_items SET liquidado = 0 WHERE id = ?",
                        (item["id"],)
                    )

        conn.execute("DELETE FROM abonos WHERE id = ?", (abono_id,))

        conn.execute("""
            UPDATE ventas
            SET pagado = MIN(total, (
                SELECT COALESCE(SUM(monto), 0) FROM abonos WHERE venta_id = ventas.id
            ))
            WHERE id = ?
        """, (venta_id,))

        venta = conn.execute(
            "SELECT total, pagado FROM ventas WHERE id = ?", (venta_id,)
        ).fetchone()
        if venta and venta["pagado"] < venta["total"]:
            liq_ids = conn.execute("""
                SELECT vi.id
                FROM venta_items vi
                WHERE vi.venta_id = ? AND vi.liquidado = 1
                  AND EXISTS (
                      SELECT 1 FROM abonos a
                      WHERE a.venta_id = ? AND a.tipo = 'liquidacion'
                        AND a.monto = vi.subtotal
                  )
            """, (venta_id, venta_id)).fetchall()
            liq_set = {r["id"] for r in liq_ids}

            items_liq = conn.execute(
                "SELECT id FROM venta_items WHERE venta_id = ? AND liquidado = 1",
                (venta_id,)
            ).fetchall()
            for it in items_liq:
                if it["id"] not in liq_set:
                    conn.execute(
                        "UPDATE venta_items SET liquidado = 0 WHERE id = ?",
                        (it["id"],)
                    )

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def liquidar_item(item_id, venta_id, subtotal_producto, nombre_producto,
                  metodo_pago="efectivo"):
    """
    Liquida un producto específico de una venta a crédito.

    subtotal_producto debe llegar YA AJUSTADO por el factor de descuento
    (el llamador en abonos.py aplica el factor antes de llamar aquí).

    Lógica:
      - Calcula el crédito libre (pagado - suma_subtotales_ya_liquidados_ajustados).
      - Si el crédito cubre el producto, lo marca como liquidado sin cobro extra.
      - Si falta dinero, registra un abono de tipo 'liquidacion' por la diferencia.
      - El nombre del producto se guarda en la nota del abono para el historial.
      - Si pagado >= total tras la operacion, todos los items se marcan liquidados.

    Devuelve el monto efectivamente cobrado (puede ser 0 si el credito ya cubria).
    """
    conn = get_connection()
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if conn.execute(
            "SELECT 1 FROM devoluciones WHERE item_id = ? LIMIT 1", (item_id,)
        ).fetchone():
            raise ValueError("El producto tiene una devolución registrada y no se puede liquidar.")

        venta = conn.execute(
            "SELECT total, pagado, subtotal_orig FROM ventas WHERE id = ?", (venta_id,)
        ).fetchone()
        pagado_actual = venta["pagado"]
        total_venta   = venta["total"]
        subtotal_orig = venta["subtotal_orig"] or 0

        # Factor para ajustar los subtotales YA liquidados (que están en BD sin descuento)
        factor = _factor_desc_conn(conn, venta_id)

        # subtotal_producto ya viene ajustado desde abonos.py — NO aplicar factor de nuevo.
        # Solo aplicar factor a los subtotales ya liquidados que viven en BD (precio bruto).
        ya_liquidado = round(sum(
            float(r["subtotal"]) * (1.0 if int(r["sin_descuento"] or 0) else factor)
            for r in conn.execute("""
                SELECT subtotal, sin_descuento
                FROM venta_items
                WHERE venta_id = ? AND liquidado = 1
                  AND NOT EXISTS (
                      SELECT 1 FROM devoluciones d WHERE d.item_id = venta_items.id
                  )
            """, (venta_id,)).fetchall()
        ), 2)

        credito_libre = max(pagado_actual - ya_liquidado, 0.0)
        faltante = max(subtotal_producto - credito_libre, 0.0)

        # Siempre registrar en historial, incluso cuando faltante==0 (cubierto por crédito).
        # item_id vincula el abono al item para poder desliquidar correctamente al eliminar.
        conn.execute("""
            INSERT INTO abonos (venta_id, monto, fecha, nota, tipo, metodo_pago, item_id)
            VALUES (?, ?, ?, ?, 'liquidacion', ?, ?)
        """, (venta_id, faltante, now, nombre_producto, metodo_pago, item_id))

        if faltante > 0:
            conn.execute("""
                UPDATE ventas
                SET pagado = MIN(total, pagado + ?)
                WHERE id = ?
            """, (faltante, venta_id))

        conn.execute(
            "UPDATE venta_items SET liquidado = 1 WHERE id = ?",
            (item_id,)
        )

        marcar_items_liquidados_si_saldada(venta_id, conn)

        conn.commit()
        return faltante
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════════════
#  ENTREGAS
# ══════════════════════════════════════════════════════════════════════════════

def registrar_entrega(item_id, entregado, entregado_a="", fecha_entrega=""):
    """
    Marca o desmarca la entrega física de un producto.
      entregado    : 1 para marcar como entregado, 0 para desmarcar
      entregado_a  : nombre de quien recibió el producto
      fecha_entrega: texto libre de fecha/hora de entrega
    """
    conn = get_connection()
    try:
        if entregado and conn.execute(
            "SELECT 1 FROM devoluciones WHERE item_id = ? LIMIT 1", (item_id,)
        ).fetchone():
            raise ValueError("El producto tiene una devolución registrada y no se puede marcar como entregado.")
        conn.execute("""
            UPDATE venta_items
            SET entregado = ?, entregado_a = ?, fecha_entrega = ?
            WHERE id = ?
        """, (1 if entregado else 0,
              entregado_a.strip() if entregado else "",
              fecha_entrega.strip() if entregado else "",
              item_id))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════════════
#  PUNTO DE ENTRADA (prueba rápida)
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print(f"📂 Base de datos en: {DB_PATH}")
    crear_tablas()
    migrar_schema()   # aplica columnas nuevas si la DB ya existía

    resultado = agregar_producto(
        codigo_barras = "7501234567890",
        nombre        = "Coca-Cola 600ml",
        precio        = 18.0,
        costo         = 12.0,
        stock         = 50,
        categoria     = "Bebidas"
    )
    print("Producto agregado:" if resultado else "Producto ya existe (código repetido)")

    p = buscar_por_codigo("7501234567890")
    if p:
        print(f"✅ Encontrado: {p['nombre']} — ${p['precio']} — Stock: {p['stock']}")

    venta_id = registrar_venta(
        items=[{
            "producto_id"     : p["id"],
            "nombre_producto" : p["nombre"],
            "cantidad"        : 2,
            "precio_unitario" : p["precio"],
        }],
        tipo    = "contado",
        cliente = "Mostrador"
    )
    print(f"✅ Venta #{venta_id} registrada")

    p2 = buscar_por_codigo("7501234567890")
    print(f"📦 Stock después de venta: {p2['stock']} (debería ser 48)")

    resumen = resumen_del_dia()
    print(f"📊 Ventas hoy: {resumen['total_ventas']} — Total: ${resumen['monto_total']}")
