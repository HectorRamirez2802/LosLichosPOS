import customtkinter as ctk
from PIL import Image, ImageTk
import os

# ─── LOGGING (primero que todo lo demás) ──────────────────────────────────────
from logger_config import setup_logging, install_global_handler, get_logger

setup_logging()            # crea pos.log y configura handlers
install_global_handler()   # cualquier excepción no capturada → pos.log

log = get_logger("main")

# ─── RESTO DE IMPORTS ─────────────────────────────────────────────────────────
from database import crear_tablas, migrar_schema

# ─── TEMA ─────────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ─── COLORES ──────────────────────────────────────────────────────────────────
COLORS = {
    "bg":         "#0d0f14",
    "sidebar":    "#151820",
    "surface":    "#1c2030",
    "surface2":   "#232840",
    "border":     "#2a2f45",
    "accent":     "#6c8aff",
    "green":      "#4ade80",
    "yellow":     "#fbbf24",
    "red":        "#ff6b6b",
    "text":       "#e8eaf6",
    "muted":      "#6b7280",
}

# ─── RUTAS DE IMAGEN ─────────────────────────────────────────────────────────────────────────────
# Pon tus imágenes en la carpeta  assets/  junto a main.py
# LOGO_SIDEBAR : imagen del panel izquierdo (PNG/JPG, ideal ~40x40 px o rectangular)
# ICON_WINDOW  : ícono de la ventana / ejecutable (.ico en Windows)
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
LOGO_SIDEBAR = os.path.join(BASE_DIR, "assets", "logo.png")   # ← pon tu imagen aquí
ICON_WINDOW  = os.path.join(BASE_DIR, "assets", "icon.ico")   # ← pon tu .ico aquí

# ─── VENTANA PRINCIPAL ────────────────────────────────────────────────────────
class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Sistema POS — Los Lichos")
        self.geometry("1200x700")
        self.minsize(1000, 600)
        self.configure(fg_color=COLORS["bg"])

        # ── Ícono de ventana / ejecutable ─────────────────────────────────────────────
        if os.path.isfile(ICON_WINDOW):
            try:
                self.iconbitmap(ICON_WINDOW)
            except Exception:
                pass  # si falla (Linux/Mac), se ignora sin romper nada

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        try:
            crear_tablas()
            migrar_schema()
            log.info("Base de datos lista (tablas OK, schema migrado)")
        except Exception:
            log.exception("Error al inicializar la base de datos")

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_content_area()
        self.mostrar_modulo("pos")

        # ── Consola de diagnóstico (Shift+Ctrl+H) ────────────────────────────
        from views.diagnostico import registrar_atajo_diagnostico
        registrar_atajo_diagnostico(self)
        log.info("Atajo de diagnóstico registrado (Shift+Ctrl+H)")

    # ── CIERRE SEGURO ─────────────────────────────────────────────────────────
    def _on_close(self):
        log.info("Cerrando aplicación…")
        try:
            import backup
            backup.backup_automatico(prefijo="auto")
            backup.limpiar_backups_viejos(conservar=15)
            log.info("Backup automático completado al cerrar")
        except Exception:
            log.exception("Error en backup automático al cerrar")
        finally:
            self.destroy()

    # ── SIDEBAR ───────────────────────────────────────────────────────────────
    def _build_sidebar(self):
        self.sidebar = ctk.CTkFrame(
            self, width=200, corner_radius=0,
            fg_color=COLORS["sidebar"]
        )
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(10, weight=1)
        self.sidebar.grid_propagate(False)

        # ── Logo sidebar ──────────────────────────────────────────────────
        if os.path.isfile(LOGO_SIDEBAR):
            try:
                _img = Image.open(LOGO_SIDEBAR).convert("RGBA")
                _w, _h = _img.size
                _new_w = 200
                _new_h = int(_h * _new_w / _w)
                _ctk_img = ctk.CTkImage(_img, size=(_new_w, _new_h))

                logo_frame = ctk.CTkFrame(
                    self.sidebar, fg_color="transparent", corner_radius=0,
                    height=_new_h + 24, width=200
                )
                logo_frame.grid(row=0, column=0, padx=0, pady=(8, 4), sticky="ew")
                logo_frame.grid_propagate(False)

                lbl = ctk.CTkLabel(logo_frame, image=_ctk_img, text="", compound="center")
                # x=0 → pegado al borde izquierdo; ajusta si quieres más margen
                lbl.place(x=0, y=12)
            except Exception:
                logo_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent", corner_radius=0)
                logo_frame.grid(row=0, column=0, padx=0, pady=(12, 4), sticky="ew")
                ctk.CTkLabel(
                    logo_frame, text="🏪  Los Lichos",
                    font=ctk.CTkFont(size=15, weight="bold"),
                    text_color=COLORS["text"]
                ).pack(pady=12, padx=12)
        else:
            logo_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent", corner_radius=0)
            logo_frame.grid(row=0, column=0, padx=0, pady=(12, 4), sticky="ew")
            ctk.CTkLabel(
                logo_frame, text="🏪  Los Lichos",
                font=ctk.CTkFont(size=15, weight="bold"),
                text_color=COLORS["text"]
            ).pack(pady=12, padx=12)

        ctk.CTkFrame(self.sidebar, height=1, fg_color=COLORS["border"]).grid(
            row=1, column=0, sticky="ew", padx=16, pady=8
        )

        self.nav_buttons = {}
        nav_items = [
            ("pos",        "🛒  Punto de Venta"),
            ("inventario", "📦  Inventario"),
            ("abonos",     "💳  Abonos"),
            ("ventas",     "📋  Historial"),
            ("respaldos",  "🗄  Respaldos"),
        ]
        for i, (key, label) in enumerate(nav_items):
            btn = ctk.CTkButton(
                self.sidebar,
                text=label,
                anchor="w",
                height=44,
                corner_radius=10,
                fg_color="transparent",
                hover_color=COLORS["surface2"],
                text_color=COLORS["muted"],
                font=ctk.CTkFont(size=14),
                command=lambda k=key: self.mostrar_modulo(k)
            )
            btn.grid(row=i + 2, column=0, padx=12, pady=3, sticky="ew")
            self.nav_buttons[key] = btn

        ctk.CTkFrame(self.sidebar, height=1, fg_color=COLORS["border"]).grid(
            row=9, column=0, sticky="ew", padx=16, pady=8
        )
        ctk.CTkLabel(
            self.sidebar,
            text="Sistema Lichos POS v1.5",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["muted"]
        ).grid(row=11, column=0, pady=(0, 16))

    # ── ÁREA DE CONTENIDO ─────────────────────────────────────────────────────
    def _build_content_area(self):
        self.content_wrapper = ctk.CTkFrame(
            self, corner_radius=0, fg_color=COLORS["bg"]
        )
        self.content_wrapper.grid(row=0, column=1, sticky="nsew")
        self.content_wrapper.grid_rowconfigure(1, weight=1)
        self.content_wrapper.grid_columnconfigure(0, weight=1)

        self.topbar = ctk.CTkFrame(
            self.content_wrapper, height=60, corner_radius=0,
            fg_color=COLORS["sidebar"]
        )
        self.topbar.grid(row=0, column=0, sticky="ew")
        self.topbar.grid_propagate(False)
        self.topbar.grid_columnconfigure(1, weight=1)

        self.topbar_title = ctk.CTkLabel(
            self.topbar, text="",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLORS["text"]
        )
        self.topbar_title.grid(row=0, column=0, padx=24, pady=16, sticky="w")

        self.topbar_info = ctk.CTkLabel(
            self.topbar, text="",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["muted"]
        )
        self.topbar_info.grid(row=0, column=2, padx=24, pady=16, sticky="e")

        self.content_frame = ctk.CTkFrame(
            self.content_wrapper, corner_radius=0,
            fg_color=COLORS["bg"]
        )
        self.content_frame.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        self.content_frame.grid_rowconfigure(0, weight=1)
        self.content_frame.grid_columnconfigure(0, weight=1)

        self.modulo_actual = None
        self.modulos = {}

    # ── NAVEGACIÓN ────────────────────────────────────────────────────────────
    TITULOS = {
        "pos":        "🛒  Punto de Venta",
        "inventario": "📦  Inventario",
        "abonos":     "💳  Gestión de Abonos",
        "ventas":     "📋  Historial de Ventas",
        "respaldos":  "🗄  Respaldos de Base de Datos",
    }

    def mostrar_modulo(self, key):
        for k, btn in self.nav_buttons.items():
            if k == key:
                btn.configure(fg_color=COLORS["accent"], text_color="#ffffff")
            else:
                btn.configure(fg_color="transparent", text_color=COLORS["muted"])

        self.topbar_title.configure(text=self.TITULOS.get(key, ""))
        self._actualizar_info_topbar()

        if self.modulo_actual:
            self.modulo_actual.grid_remove()

        if key not in self.modulos:
            try:
                if key == "pos":
                    from views.pos import POSView
                    view = POSView(self.content_frame, self)
                elif key == "inventario":
                    from views.inventario import InventarioView
                    view = InventarioView(self.content_frame, self)
                elif key == "abonos":
                    from views.abonos import AbonosView
                    view = AbonosView(self.content_frame, self)
                elif key == "ventas":
                    from views.ventas import VentasView
                    view = VentasView(self.content_frame, self)
                elif key == "respaldos":
                    from views.backup_view import BackupView
                    view = BackupView(self.content_frame, self)
                else:
                    return
                log.info("Módulo cargado: %s", self.TITULOS.get(key, key))
            except Exception:
                log.exception("Error al cargar módulo '%s'", key)
                return

            view.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
            self.modulos[key] = view
        else:
            view = self.modulos[key]
            view.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
            if hasattr(view, "on_show"):
                try:
                    view.on_show()
                except Exception:
                    log.exception("Error en on_show() de módulo '%s'", key)

        self.modulo_actual = view

    def _actualizar_info_topbar(self):
        from datetime import datetime
        ahora = datetime.now().strftime("%A %d de %B, %Y  %H:%M")
        self.topbar_info.configure(text=ahora)


# ─── PUNTO DE ENTRADA ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        app = App()
        app.mainloop()
    except Exception:
        log.exception("Error fatal en la aplicación principal")