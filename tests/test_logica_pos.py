import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import database as db


class PruebaConBaseTemporal(unittest.TestCase):
    def setUp(self):
        carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(carpeta.cleanup)
        self.ruta = Path(carpeta.name) / "pos.db"
        ruta_temporal = patch.object(db, "DB_PATH", self.ruta)
        ruta_temporal.start()
        self.addCleanup(ruta_temporal.stop)


class VentasTest(PruebaConBaseTemporal):
    def setUp(self):
        super().setUp()
        db.crear_tablas()
        self.items = []
        for precio in (80, 20):
            codigo = str(precio)
            db.agregar_producto(codigo, codigo, precio, stock=10)
            producto = db.buscar_por_codigo(codigo)
            self.items.append(dict(producto_id=producto["id"], nombre_producto=codigo,
                                   cantidad=1, precio_unitario=precio))

    def cuenta(self, pagado):
        return db.registrar_venta(self.items, tipo="abono", cliente="Prueba", pagado=pagado)

    def saldo(self, venta):
        fila = db.obtener_venta_por_id(venta)
        return fila["total"], fila["pagado"], sum(a["monto"] for a in db.obtener_abonos(venta))

    def test_quitar_con_excedente_exige_devolucion(self):
        venta = self.cuenta(60)
        item = db.obtener_items_venta(venta)[0]["id"]
        with self.assertRaises(db.RequiereDevolucion):
            db.eliminar_item_venta(item)
        self.assertEqual(self.saldo(venta), (100, 60, 60))
        self.assertEqual(db.buscar_por_codigo("80")["stock"], 9)
        res = db.registrar_devolucion_multiple([(item, 1)], "Prueba")
        self.assertEqual(res["salida_dinero"], 40)
        self.assertEqual(self.saldo(venta), (20, 20, 20))
        self.assertEqual(db.buscar_por_codigo("80")["stock"], 10)

    def test_quitar_sin_excedente_salda_cuenta(self):
        venta = self.cuenta(20)
        db.eliminar_item_venta(db.obtener_items_venta(venta)[0]["id"])
        self.assertEqual(self.saldo(venta), (20, 20, 20))
        self.assertEqual(db.obtener_items_venta(venta)[0]["liquidado"], 1)

    def test_precio_cero_es_distinto_de_ausencia_de_ajuste(self):
        gratis = dict(self.items[0], precio_ajustado=0)
        for items, total in (([gratis], 0), ([gratis, self.items[1]], 20),
                             ([dict(self.items[0], precio_ajustado=None)], 80)):
            with self.subTest(total=total):
                venta = db.registrar_venta(items)
                self.assertEqual(db.obtener_venta_por_id(venta)["total"], total)
                lineas = db.obtener_items_venta(venta)
                self.assertEqual(sum(i["subtotal"] for i in lineas), total)
                self.assertEqual(lineas[0]["precio_unitario"], total if total == 80 else 0)

    def test_correcciones_conservan_historial_y_cierre(self):
        venta = self.cuenta(30)
        for pagado in (50, 40, 40):
            db.editar_venta(venta, "Prueba", 100, pagado, "abono", "", motivo_ajuste="Conteo")
        self.assertEqual(self.saldo(venta), (100, 40, 40))
        abonos = db.obtener_abonos(venta)
        self.assertEqual([(a["tipo"], a["monto"]) for a in abonos],
                         [("ajuste", -10), ("ajuste", 20), ("abono", 30)])
        self.assertIn("Conteo", abonos[0]["nota"])
        with self.assertRaises(ValueError):
            db.eliminar_abono(abonos[0]["id"])
        self.assertEqual(db.resumen_ventas()["monto_cobrado"], 40)

    def test_edicion_desactualizada_y_sobrepago_no_alteran_cuenta(self):
        venta = self.cuenta(30)
        db.registrar_abono(venta, 20)
        with self.assertRaises(ValueError):
            db.editar_venta(venta, "Prueba", 100, 40, "abono", "",
                            estado_esperado=("abono", 100, 30, 30))
        with self.assertRaises(ValueError):
            db.registrar_abono(venta, 51)
        with self.assertRaises(ValueError):
            db.editar_venta(venta, "Prueba", 100, 50, "contado", "")
        self.assertEqual(self.saldo(venta), (100, 50, 50))

    def test_reclasificacion_conserva_fecha_del_anticipo(self):
        venta = db.registrar_venta(self.items)
        db.editar_venta(venta, "Prueba", 100, 40, "abono", "")
        self.assertEqual(self.saldo(venta), (100, 40, 40))
        abono, = db.obtener_abonos(venta)
        self.assertEqual(abono["fecha"], db.obtener_venta_por_id(venta)["fecha"])


class MigracionTest(PruebaConBaseTemporal):
    def test_respalda_y_migra_antes_de_indexar(self):
        with closing(sqlite3.connect(self.ruta)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("CREATE TABLE abonos(id INTEGER PRIMARY KEY, venta_id INTEGER, "
                         "monto REAL, fecha TEXT, nota TEXT)")
            conn.execute("INSERT INTO abonos VALUES(1, 3, 15, '2020-01-01', 'Anticipo')")
            conn.commit()
            db.crear_tablas()
            db.migrar_schema()
            self.assertEqual(conn.execute("SELECT tipo, monto FROM abonos").fetchone(), ("abono", 15))
            indices = {r[1] for r in conn.execute("PRAGMA index_list(abonos)")}
            self.assertIn("idx_abonos_tipo_venta", indices)
        copia, = (self.ruta.parent / "backups").glob("*.db")
        with closing(sqlite3.connect(copia)) as conn:
            self.assertNotIn("tipo", {r[1] for r in conn.execute("PRAGMA table_info(abonos)")})
            self.assertEqual(conn.execute("SELECT monto FROM abonos").fetchone(), (15,))

    def test_migracion_fallida_revierte_y_permite_reintentar(self):
        with closing(sqlite3.connect(self.ruta)) as conn:
            conn.execute("CREATE TABLE abonos(id INTEGER PRIMARY KEY)")
        with self.assertRaises(sqlite3.OperationalError):
            db.crear_tablas()
        with closing(sqlite3.connect(self.ruta)) as conn:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 0)
            self.assertEqual([r[1] for r in conn.execute("PRAGMA table_info(abonos)")], ["id"])
            for declaracion in ("venta_id INTEGER", "monto REAL", "fecha TEXT", "nota TEXT"):
                conn.execute(f"ALTER TABLE abonos ADD COLUMN {declaracion}")
        db.crear_tablas()


if __name__ == "__main__":
    unittest.main()
