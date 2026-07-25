"""
backup.py  —  Respaldo y restauración de la base de datos — Los Lichos
-----------------------------------------------------------------------
Funciones:
  • exportar_bd()      → copia el .db a un archivo elegido por el usuario
  • importar_bd()      → reemplaza el .db con uno elegido por el usuario
  • backup_automatico()→ guarda una copia fechada en la carpeta /backups/
  • limpiar_backups_viejos() → conserva solo los N más recientes

Se llama desde la UI (BackupView) o desde main.py al cerrar.
"""

import os
import shutil
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path

import database as db   # para obtener DB_PATH


# ─── RUTAS ────────────────────────────────────────────────────────────────────
BASE_DIR    = Path(os.path.dirname(os.path.abspath(db.__file__)))
BACKUPS_DIR = BASE_DIR / "backups"
BACKUPS_DIR.mkdir(exist_ok=True)


# ─── HELPERS INTERNOS ─────────────────────────────────────────────────────────
def _checkpoint():
    """
    Fuerza que WAL escriba todo al archivo principal antes de copiar.
    Seguro llamarlo aunque WAL no esté activo.
    """
    try:
        conn = sqlite3.connect(db.DB_PATH)
        conn.execute("PRAGMA wal_checkpoint(FULL)")
        conn.close()
    except Exception:
        pass


def _ts() -> str:
    """Timestamp compacto para nombres de archivo."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


# ─── EXPORTAR ─────────────────────────────────────────────────────────────────
def exportar_bd(destino: str | None = None) -> str | None:
    """
    Copia la BD a `destino` (ruta elegida por el usuario).
    Si destino es None abre un filedialog.
    Devuelve la ruta destino o None si el usuario canceló.
    """
    if destino is None:
        from tkinter import filedialog
        destino = filedialog.asksaveasfilename(
            title="Exportar base de datos",
            defaultextension=".db",
            filetypes=[
                ("Base de datos SQLite", "*.db"),
                ("Todos los archivos", "*.*"),
            ],
            initialfile=f"lichos_backup_{_ts()}.db",
        )
        if not destino:
            return None

    _checkpoint()
    shutil.copy2(db.DB_PATH, destino)
    return destino


def exportar_zip(destino: str | None = None) -> str | None:
    """
    Igual que exportar_bd pero empaqueta el .db en un .zip comprimido.
    Útil para enviar por correo o WhatsApp.
    """
    if destino is None:
        from tkinter import filedialog
        destino = filedialog.asksaveasfilename(
            title="Exportar respaldo comprimido",
            defaultextension=".zip",
            filetypes=[("Archivo ZIP", "*.zip")],
            initialfile=f"lichos_backup_{_ts()}.zip",
        )
        if not destino:
            return None

    _checkpoint()
    with zipfile.ZipFile(destino, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(db.DB_PATH, arcname="pos.db")
    return destino


# ─── IMPORTAR / RESTAURAR ─────────────────────────────────────────────────────
def importar_bd(origen: str | None = None) -> bool:
    """
    Reemplaza la BD activa con el archivo elegido.
    Hace una copia de seguridad automática de la BD actual antes de sustituirla.
    Devuelve True si tuvo éxito.
    """
    if origen is None:
        from tkinter import filedialog
        origen = filedialog.askopenfilename(
            title="Restaurar base de datos",
            filetypes=[
                ("Base de datos SQLite", "*.db"),
                ("Todos los archivos", "*.*"),
            ],
        )
        if not origen:
            return False

    # Validar que el archivo sea un SQLite válido
    try:
        conn_test = sqlite3.connect(origen)
        conn_test.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        conn_test.close()
    except sqlite3.DatabaseError:
        raise ValueError("El archivo seleccionado no es una base de datos SQLite válida.")

    # Respaldar la BD actual antes de sobreescribir
    backup_automatico(prefijo="pre_importacion")

    # Cerrar cualquier conexión antes de copiar
    _checkpoint()
    shutil.copy2(origen, db.DB_PATH)
    return True


def importar_zip(origen: str | None = None) -> bool:
    """
    Restaura desde un .zip generado con exportar_zip().
    """
    if origen is None:
        from tkinter import filedialog
        origen = filedialog.askopenfilename(
            title="Restaurar desde ZIP",
            filetypes=[("Archivo ZIP", "*.zip")],
        )
        if not origen:
            return False

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(origen, "r") as zf:
            nombres = zf.namelist()
            db_dentro = next((n for n in nombres if n.endswith(".db")), None)
            if not db_dentro:
                raise ValueError("El ZIP no contiene ningún archivo .db")
            zf.extract(db_dentro, tmp)
            tmp_db = os.path.join(tmp, db_dentro)
            return importar_bd(origen=tmp_db)


# ─── BACKUP AUTOMÁTICO ────────────────────────────────────────────────────────
def backup_automatico(prefijo: str = "auto") -> str:
    """
    Guarda una copia de la BD en backups/<prefijo>_YYYYMMDD_HHMMSS.db
    Devuelve la ruta del backup creado.
    """
    nombre   = f"{prefijo}_{_ts()}.db"
    destino  = BACKUPS_DIR / nombre
    _checkpoint()
    shutil.copy2(db.DB_PATH, destino)
    return str(destino)


def limpiar_backups_viejos(conservar: int = 10):
    """
    Elimina backups automáticos más allá de los `conservar` más recientes.
    Solo toca archivos que empiezan con 'auto_' para no borrar manuales.
    """
    archivos = sorted(
        [f for f in BACKUPS_DIR.glob("auto_*.db")],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    for viejo in archivos[conservar:]:
        try:
            viejo.unlink()
        except OSError:
            pass


# ─── FORMATEAR BD (solo desarrollo) ──────────────────────────────────────────
def formatear_bd() -> str:
    """
    ⚠ OPERACIÓN DESTRUCTIVA — solo para desarrollo.
    1. Hace un backup automático con prefijo 'pre_formato'.
    2. Borra todos los DEMÁS backups existentes, dejando únicamente
       el respaldo de seguridad recién creado en el paso 1.
    3. Borra todas las tablas de la BD activa.
    4. Las recrea vacías con db.crear_tablas() + db.migrar_schema().
    Devuelve la ruta del backup previo creado (el único que sobrevive).
    """
    # Guardar copia antes de destruir nada
    ruta_backup = backup_automatico(prefijo="pre_formato")

    # Borrar todos los backups anteriores, conservando solo el que
    # se acaba de crear como red de seguridad de este formateo.
    for f in BACKUPS_DIR.glob("*.db"):
        if str(f) != str(ruta_backup):
            try:
                f.unlink()
            except OSError:
                pass

    # Borrar todas las tablas
    conn = sqlite3.connect(db.DB_PATH)
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        tablas = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        for (tabla,) in tablas:
            conn.execute(f"DROP TABLE IF EXISTS [{tabla}]")
        conn.commit()
    finally:
        conn.close()

    # Recrear esquema limpio
    db.crear_tablas()
    db.migrar_schema()

    return ruta_backup


def listar_backups() -> list[dict]:
    """
    Devuelve todos los backups en /backups/ ordenados del más reciente al más viejo.
    Cada item: {nombre, ruta, fecha_str, tamaño_kb}
    """
    resultado = []
    for f in sorted(BACKUPS_DIR.glob("*.db"),
                    key=lambda x: x.stat().st_mtime, reverse=True):
        st = f.stat()
        resultado.append({
            "nombre":    f.name,
            "ruta":      str(f),
            "fecha_str": datetime.fromtimestamp(st.st_mtime).strftime("%d/%m/%Y  %H:%M"),
            "tamaño_kb": round(st.st_size / 1024, 1),
        })
    return resultado