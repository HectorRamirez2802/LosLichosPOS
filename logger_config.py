"""
logger_config.py — Logging centralizado para Sistema POS Los Lichos
────────────────────────────────────────────────────────────────────
• Escribe en pos.log (rotación automática: 5 MB × 3 archivos)
• Captura TODAS las excepciones no controladas vía sys.excepthook
• Expone un bus de eventos en memoria para la consola de diagnóstico
• Uso en cualquier módulo:
      from logger_config import get_logger
      log = get_logger(__name__)
      log.info("Venta #%s registrada", venta_id)
      log.error("Stock insuficiente para %s", nombre)
      log.exception("Error SQLite")   # incluye traceback completo
"""

import sys
import logging
import logging.handlers
import os
import threading
from datetime import datetime

# ─── RUTAS ───────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH  = os.path.join(BASE_DIR, "pos.log")

# ─── FORMATO ─────────────────────────────────────────────────────────────────
#  Archivo : timestamp completo + nivel + módulo
#  Consola UI: solo [HH:MM:SS] mensaje  (manejado por DiagnosticoHandler abajo)
_FMT_FILE = "%(asctime)s [%(levelname)-8s] %(name)s — %(message)s"
_FMT_DATE = "%Y-%m-%d %H:%M:%S"

# ─── BUS DE EVENTOS EN MEMORIA ───────────────────────────────────────────────
#  Lista compartida que la ConsoleView lee para mostrar entradas.
#  Máximo 500 entradas para no crecer indefinidamente.
_MAX_ENTRIES = 500
_event_bus: list[dict] = []
_bus_lock   = threading.Lock()
_listeners: list = []   # callbacks registrados por la ConsoleView


def subscribe(callback):
    """Registra una función que se llama cada vez que llega una nueva entrada."""
    with _bus_lock:
        if callback not in _listeners:
            _listeners.append(callback)


def unsubscribe(callback):
    with _bus_lock:
        if callback in _listeners:
            _listeners.remove(callback)


def get_events() -> list[dict]:
    """Devuelve una copia de todos los eventos en memoria."""
    with _bus_lock:
        return list(_event_bus)


def _push_event(record: logging.LogRecord):
    """Empuja un evento al bus y notifica listeners."""
    hora  = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
    nivel = record.levelname          # DEBUG / INFO / WARNING / ERROR / CRITICAL
    msg   = record.getMessage()

    # Si hay excepción adjunta, agregar la última línea del traceback
    if record.exc_info and record.exc_info[1]:
        exc_line = str(record.exc_info[1])
        if exc_line:
            msg = f"{msg} → {exc_line}"

    entry = {"hora": hora, "nivel": nivel, "msg": msg, "ts": record.created}

    with _bus_lock:
        _event_bus.append(entry)
        if len(_event_bus) > _MAX_ENTRIES:
            _event_bus.pop(0)
        cbs = list(_listeners)

    for cb in cbs:
        try:
            cb(entry)
        except Exception:
            pass   # nunca dejar que un listener rompa el logging


# ─── HANDLER PERSONALIZADO → BUS ─────────────────────────────────────────────
class _BusHandler(logging.Handler):
    """Envía cada registro al bus en memoria (para la ConsoleView)."""

    def emit(self, record: logging.LogRecord):
        try:
            _push_event(record)
        except Exception:
            self.handleError(record)


# ─── SETUP ÚNICO ─────────────────────────────────────────────────────────────
_initialized = False


def setup_logging(level: int = logging.DEBUG):
    """
    Inicializa el sistema de logging. Llamar UNA sola vez desde main.py
    antes de importar cualquier otro módulo.
    """
    global _initialized
    if _initialized:
        return
    _initialized = True

    root = logging.getLogger()
    root.setLevel(level)

    # ── Handler 1: archivo rotativo pos.log ──────────────────────────────────
    fh = logging.handlers.RotatingFileHandler(
        LOG_PATH,
        maxBytes    = 5 * 1024 * 1024,   # 5 MB por archivo
        backupCount = 3,
        encoding    = "utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(_FMT_FILE, datefmt=_FMT_DATE))
    root.addHandler(fh)

    # ── Handler 2: bus en memoria → ConsoleView ───────────────────────────────
    bh = _BusHandler()
    bh.setLevel(logging.INFO)   # la UI solo muestra INFO en adelante
    root.addHandler(bh)

    # ── Silenciar loggers ruidosos de terceros ────────────────────────────────
    for noisy in ("PIL", "reportlab", "matplotlib"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.info("════════════════════════════════════════")
    logging.info("Sistema POS iniciado — %s",
                 datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
    logging.info("Log en: %s", LOG_PATH)
    logging.info("════════════════════════════════════════")


# ─── HOOK GLOBAL ─────────────────────────────────────────────────────────────
def _global_exception_handler(exc_type, exc_value, exc_traceback):
    """Captura cualquier excepción no controlada y la escribe en pos.log."""
    if issubclass(exc_type, KeyboardInterrupt):
        # Ctrl-C no es un error del sistema, dejar pasar
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logging.critical(
        "⚠ EXCEPCIÓN NO CONTROLADA: %s", exc_value,
        exc_info=(exc_type, exc_value, exc_traceback)
    )


def install_global_handler():
    """
    Instala el hook global. Llamar desde main.py justo después de
    setup_logging().
    """
    sys.excepthook = _global_exception_handler


# ─── HELPER PARA MÓDULOS ─────────────────────────────────────────────────────
def get_logger(name: str = "pos") -> logging.Logger:
    """
    Devuelve un logger con el nombre del módulo.
    Uso:  log = get_logger(__name__)
    """
    return logging.getLogger(name)