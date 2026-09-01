import sqlite3
import os
from datetime import datetime, timedelta

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
        ("ALTER TABLE ventas      ADD COLUMN telefono        TEXT DEFAULT ''",),
        ("ALTER TABLE abonos      ADD COLUMN item_id         INTEGER DEFAULT NULL",),
    ]
    for (sql,) in migraciones:
        try:
            cur.execute(sql)
        except sqlite3.OperationalError:
            pass   # columna ya existe → ignorar

    _crear_indices(cur)

    conn.commit()
    conn.close()


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
            "SELECT total, subtotal_orig FROM ventas WHERE id = ?",
            (venta_id,)
        ).fetchone()
        if venta is None:
            raise ValueError(f"La venta/cuenta {venta_id} no existe.")

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
                  AND (nota_item IS NULL OR nota_item = '')
                  AND precio_ajustado IS NULL
                  AND precio_unitario = ?
                ORDER BY id DESC LIMIT 1
            """, (venta_id, producto_id, precio_efectivo)).fetchone()

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
                     precio_unitario, subtotal, nota_item, precio_ajustado)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (venta_id, producto_id, nombre_producto, cantidad,
                  precio_efectivo, subtotal, nota_item or "", precio_ajustado))
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

        venta = conn.execute(
            "SELECT total, subtotal_orig FROM ventas WHERE id = ?",
            (item["venta_id"],)
        ).fetchone()

        subtotal_orig_actual = venta["subtotal_orig"] or 0
        if subtotal_orig_actual <= 0:
            subtotal_orig_actual = venta["total"]
        nuevo_subtotal_orig = max(subtotal_orig_actual - item["subtotal"], 0)
        nuevo_total = max(venta["total"] - item["subtotal"], 0)

        conn.execute(
            "UPDATE productos SET stock = stock + ? WHERE id = ?",
            (item["cantidad"], item["producto_id"])
        )
        conn.execute("DELETE FROM venta_items WHERE id = ?", (item_id,))
        conn.execute(
            "UPDATE ventas SET total = ?, subtotal_orig = ? WHERE id = ?",
            (nuevo_total, nuevo_subtotal_orig, item["venta_id"])
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
            COALESCE(SUM(pagado), 0) AS monto_cobrado
        FROM ventas
    """
    if where:
        sql += " WHERE " + " AND ".join(where)

    conn = get_connection()
    row = conn.execute(sql, params).fetchone()
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
        SELECT *, (total - pagado) AS restante
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
        SELECT vi.*, p.categoria
        FROM venta_items vi
        LEFT JOIN productos p ON p.id = vi.producto_id
        WHERE vi.venta_id = ?
        ORDER BY vi.id ASC
    """, (venta_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


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
            p.id              AS producto_id,
            p.nombre          AS nombre,
            p.stock           AS stock_actual,
            COALESCE(SUM(vi.cantidad), 0) AS vendido
        FROM productos p
        LEFT JOIN venta_items vi
            ON vi.producto_id = p.id
            AND vi.venta_id IN (
                SELECT id FROM ventas WHERE fecha LIKE ?
            )
        WHERE p.activo = 1
        GROUP BY p.id, p.nombre, p.stock
        ORDER BY p.nombre ASC
    """, (prefijo,)).fetchall()
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
    row = conn.execute("""
        SELECT
            COUNT(*)    AS total_ventas,
            SUM(total)  AS monto_total,
            SUM(pagado) AS monto_cobrado
        FROM ventas
        WHERE fecha LIKE ?
    """, (f"{hoy}%",)).fetchone()
    conn.close()
    return row


def editar_venta(venta_id, cliente, total, pagado, tipo, nota, metodo_pago="efectivo"):
    conn = get_connection()
    try:
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
            "UPDATE venta_items SET liquidado = 1 WHERE venta_id = ?",
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
        SELECT * FROM abonos WHERE venta_id = ? ORDER BY fecha DESC
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

        venta = conn.execute(
            "SELECT total, pagado, subtotal_orig FROM ventas WHERE id = ?", (venta_id,)
        ).fetchone()
        pagado_actual = venta["pagado"]
        total_venta   = venta["total"]
        subtotal_orig = venta["subtotal_orig"] or 0

        # Factor para ajustar los subtotales YA liquidados (que están en BD sin descuento)
        if subtotal_orig > 0 and subtotal_orig != total_venta:
            factor = total_venta / subtotal_orig
        else:
            factor = 1.0

        # subtotal_producto ya viene ajustado desde abonos.py — NO aplicar factor de nuevo.
        # Solo aplicar factor a los subtotales ya liquidados que viven en BD (precio bruto).
        ya_liquidado_bruto = conn.execute("""
            SELECT COALESCE(SUM(subtotal), 0) AS suma
            FROM venta_items
            WHERE venta_id = ? AND liquidado = 1
        """, (venta_id,)).fetchone()["suma"]
        ya_liquidado = round(ya_liquidado_bruto * factor, 2)

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