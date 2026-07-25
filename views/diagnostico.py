"""
views/diagnostico.py — Consola de Diagnóstico (Shift+Ctrl+H)
─────────────────────────────────────────────────────────────
Acceso restringido:
  1. PIN numérico
  2. Pregunta de seguridad (referencia a DMC5)

La ventana muestra en tiempo real los eventos del bus de logging.
Niveles con color:
  INFO     → texto normal (blanco/gris)
  WARNING  → amarillo
  ERROR    → rojo claro
  CRITICAL → rojo fuerte + negrita
"""

import tkinter as tk
import customtkinter as ctk
from datetime import datetime

import logger_config

# ─── CREDENCIALES ────────────────────────────────────────────────────────────
_PIN_CORRECTO        = "2802"
_PREGUNTA_SEGURIDAD  = (
    "Dante y Vergil subieron al Qliphoth…\n"
    "Únicamente para cerrar el cruce entre los dos mundos con la:"
)
_RESPUESTA_CORRECTA  = "yamato"   # se compara en minúsculas

# ─── COLORES (mismo sistema que main.py) ─────────────────────────────────────
_C = {
    "bg":       "#0d0f14",
    "surface":  "#1c2030",
    "surface2": "#232840",
    "border":   "#2a2f45",
    "accent":   "#6c8aff",
    "green":    "#4ade80",
    "yellow":   "#fbbf24",
    "red":      "#ff6b6b",
    "red2":     "#ff3333",
    "text":     "#e8eaf6",
    "muted":    "#6b7280",
    "sidebar":  "#151820",
}

_NIVEL_COLOR = {
    "DEBUG":    _C["muted"],
    "INFO":     _C["text"],
    "WARNING":  _C["yellow"],
    "ERROR":    _C["red"],
    "CRITICAL": _C["red2"],
}


# ══════════════════════════════════════════════════════════════════════════════
#  VENTANA DE AUTENTICACIÓN
# ══════════════════════════════════════════════════════════════════════════════
class _AuthDialog(ctk.CTkToplevel):
    """
    Diálogo modal de dos pasos:
      Paso 1 → PIN
      Paso 2 → Pregunta de seguridad
    Si ambos son correctos, llama a on_success().
    """

    def __init__(self, parent, on_success):
        super().__init__(parent)
        self._on_success = on_success
        self._paso = 1

        self.title("Acceso restringido")
        self.geometry("420x280")
        self.resizable(False, False)
        self.configure(fg_color=_C["bg"])
        self.grab_set()
        self.focus_force()

        # centrar sobre el padre
        self.after(10, self._centrar)

        self._frame = ctk.CTkFrame(self, fg_color=_C["surface"], corner_radius=14)
        self._frame.pack(fill="both", expand=True, padx=20, pady=20)
        self._frame.grid_columnconfigure(0, weight=1)

        self._icono = ctk.CTkLabel(
            self._frame, text="🔒",
            font=ctk.CTkFont(size=32)
        )
        self._icono.grid(row=0, column=0, pady=(18, 4))

        self._titulo = ctk.CTkLabel(
            self._frame, text="Ingresa el PIN de acceso",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=_C["text"]
        )
        self._titulo.grid(row=1, column=0, pady=(0, 12))

        self._entry = ctk.CTkEntry(
            self._frame,
            placeholder_text="••••",
            show="•",
            width=180,
            height=40,
            font=ctk.CTkFont(size=16),
            justify="center",
        )
        self._entry.grid(row=2, column=0, pady=4)
        self._entry.bind("<Return>", lambda e: self._verificar())
        self._entry.focus()

        self._error_lbl = ctk.CTkLabel(
            self._frame, text="",
            font=ctk.CTkFont(size=12),
            text_color=_C["red"]
        )
        self._error_lbl.grid(row=3, column=0, pady=2)

        btn_row = ctk.CTkFrame(self._frame, fg_color="transparent")
        btn_row.grid(row=4, column=0, pady=(8, 0))

        ctk.CTkButton(
            btn_row, text="Cancelar", width=100,
            fg_color=_C["surface2"], hover_color=_C["border"],
            text_color=_C["muted"],
            command=self.destroy
        ).pack(side="left", padx=6)

        self._btn_ok = ctk.CTkButton(
            btn_row, text="Continuar", width=100,
            fg_color=_C["accent"],
            command=self._verificar
        )
        self._btn_ok.pack(side="left", padx=6)

    def _centrar(self):
        self.update_idletasks()
        pw = self.master.winfo_rootx() + self.master.winfo_width()  // 2
        ph = self.master.winfo_rooty() + self.master.winfo_height() // 2
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{pw - w//2}+{ph - h//2}")

    def _verificar(self):
        valor = self._entry.get().strip()
        self._error_lbl.configure(text="")

        if self._paso == 1:
            if valor == _PIN_CORRECTO:
                self._paso = 2
                self._mostrar_pregunta()
            else:
                self._error_lbl.configure(text="PIN incorrecto.")
                self._entry.delete(0, "end")

        elif self._paso == 2:
            if valor.lower() == _RESPUESTA_CORRECTA:
                self.destroy()
                self._on_success()
            else:
                self._error_lbl.configure(text="Respuesta incorrecta.")
                self._entry.delete(0, "end")

    def _mostrar_pregunta(self):
        self._titulo.configure(
            text=_PREGUNTA_SEGURIDAD,
            wraplength=340,
            justify="center"
        )
        self._entry.configure(show="", placeholder_text="Tu respuesta…")
        self._entry.delete(0, "end")
        self._icono.configure(text="🗡️⚔️")
        self._btn_ok.configure(text="Verificar")
        self._entry.focus()
        self.geometry("420x310")


# ══════════════════════════════════════════════════════════════════════════════
#  CONSOLA DE DIAGNÓSTICO
# ══════════════════════════════════════════════════════════════════════════════
class DiagnosticoWindow(ctk.CTkToplevel):
    """
    Ventana flotante con el log en tiempo real.
    Se abre solo tras autenticación exitosa.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.title("🖥  Consola de Diagnóstico — Los Lichos POS")
        self.geometry("780x480")
        self.minsize(600, 360)
        self.configure(fg_color=_C["bg"])

        self._build_ui()
        self._cargar_historial()

        # suscribirse al bus para recibir nuevas entradas
        logger_config.subscribe(self._on_new_entry)
        self.protocol("WM_DELETE_WINDOW", self._cerrar)

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        # Topbar
        top = ctk.CTkFrame(self, height=50, fg_color=_C["sidebar"], corner_radius=0)
        top.pack(fill="x")
        top.pack_propagate(False)
        top.columnconfigure(1, weight=1)

        ctk.CTkLabel(
            top, text="  🖥  Consola de Diagnóstico",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=_C["text"]
        ).pack(side="left", padx=14)

        # leyenda de colores
        leyenda = ctk.CTkFrame(top, fg_color="transparent")
        leyenda.pack(side="right", padx=14)
        for nivel, color in [("INFO", _C["text"]), ("WARNING", _C["yellow"]),
                              ("ERROR", _C["red"]), ("CRITICAL", _C["red2"])]:
            ctk.CTkLabel(
                leyenda, text=f"● {nivel}",
                font=ctk.CTkFont(size=11),
                text_color=color
            ).pack(side="left", padx=6)

        # Barra de filtro + botones
        bar = ctk.CTkFrame(self, fg_color=_C["surface"], corner_radius=0, height=44)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        self._filtro_var = ctk.StringVar(value="TODOS")
        for texto in ("TODOS", "INFO", "WARNING", "ERROR", "CRITICAL"):
            ctk.CTkButton(
                bar, text=texto, width=80, height=28,
                fg_color=_C["surface2"],
                hover_color=_C["border"],
                text_color=_C["muted"],
                font=ctk.CTkFont(size=11),
                command=lambda t=texto: self._aplicar_filtro(t)
            ).pack(side="left", padx=(6, 2), pady=8)

        ctk.CTkButton(
            bar, text="🗑 Limpiar", width=90, height=28,
            fg_color=_C["surface2"], hover_color=_C["border"],
            text_color=_C["muted"],
            font=ctk.CTkFont(size=11),
            command=self._limpiar
        ).pack(side="right", padx=10, pady=8)

        ctk.CTkButton(
            bar, text="📋 Copiar todo", width=100, height=28,
            fg_color=_C["surface2"], hover_color=_C["border"],
            text_color=_C["muted"],
            font=ctk.CTkFont(size=11),
            command=self._copiar_todo
        ).pack(side="right", padx=(0, 4), pady=8)

        # Área de texto con scroll
        text_frame = ctk.CTkFrame(self, fg_color=_C["surface"], corner_radius=10)
        text_frame.pack(fill="both", expand=True, padx=12, pady=(6, 12))

        # Usamos tk.Text nativo para poder colorear por nivel
        self._txt = tk.Text(
            text_frame,
            bg        = _C["surface"],
            fg        = _C["text"],
            font      = ("Consolas", 12),
            wrap      = "word",
            state     = "disabled",
            relief    = "flat",
            bd        = 0,
            padx      = 10,
            pady      = 8,
            cursor    = "arrow",
            selectbackground = _C["surface2"],
        )
        sb = tk.Scrollbar(text_frame, command=self._txt.yview, bg=_C["surface"])
        self._txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._txt.pack(fill="both", expand=True)

        # Tags de color por nivel
        self._txt.tag_configure("INFO",     foreground=_C["text"])
        self._txt.tag_configure("WARNING",  foreground=_C["yellow"])
        self._txt.tag_configure("ERROR",    foreground=_C["red"])
        self._txt.tag_configure("CRITICAL", foreground=_C["red2"],
                                font=("Consolas", 12, "bold"))
        self._txt.tag_configure("DEBUG",    foreground=_C["muted"])
        self._txt.tag_configure("hora",     foreground=_C["muted"])
        self._txt.tag_configure("sep",      foreground=_C["border"])

        # Barra de estado inferior
        self._status = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont(size=11),
            text_color=_C["muted"]
        )
        self._status.pack(pady=(0, 6))

        self._filtro_activo = "TODOS"
        self._total_entradas = 0

    # ── DATOS ─────────────────────────────────────────────────────────────────
    def _cargar_historial(self):
        """Vuelca el historial en memoria al abrir la ventana."""
        for entry in logger_config.get_events():
            self._insertar_entrada(entry, scroll=False)
        self._txt.see("end")
        self._actualizar_status()

    def _on_new_entry(self, entry: dict):
        """Callback del bus; se llama desde el hilo de logging → usar after()."""
        self.after(0, lambda: self._insertar_entrada(entry, scroll=True))

    def _insertar_entrada(self, entry: dict, scroll=True):
        nivel = entry.get("nivel", "INFO")
        if self._filtro_activo != "TODOS" and nivel != self._filtro_activo:
            return

        hora = entry.get("hora", "--:--:--")
        msg  = entry.get("msg", "")

        self._txt.configure(state="normal")
        self._txt.insert("end", f"[{hora}] ", "hora")
        self._txt.insert("end", f"{msg}\n", nivel)
        self._txt.configure(state="disabled")

        self._total_entradas += 1
        if scroll:
            self._txt.see("end")
        self._actualizar_status()

    def _aplicar_filtro(self, filtro: str):
        self._filtro_activo = filtro
        self._total_entradas = 0
        self._txt.configure(state="normal")
        self._txt.delete("1.0", "end")
        self._txt.configure(state="disabled")
        for entry in logger_config.get_events():
            self._insertar_entrada(entry, scroll=False)
        self._txt.see("end")
        self._actualizar_status()

    def _limpiar(self):
        self._total_entradas = 0
        self._txt.configure(state="normal")
        self._txt.delete("1.0", "end")
        self._txt.configure(state="disabled")
        self._actualizar_status()

    def _copiar_todo(self):
        contenido = self._txt.get("1.0", "end")
        self.clipboard_clear()
        self.clipboard_append(contenido)
        self._status.configure(text="✅ Contenido copiado al portapapeles.")
        self.after(2500, self._actualizar_status)

    def _actualizar_status(self):
        filtro_txt = f"Filtro: {self._filtro_activo}" if self._filtro_activo != "TODOS" else "Mostrando todos los niveles"
        self._status.configure(
            text=f"{filtro_txt}   •   {self._total_entradas} entradas visibles"
        )

    def _cerrar(self):
        logger_config.unsubscribe(self._on_new_entry)
        self.destroy()


# ══════════════════════════════════════════════════════════════════════════════
#  FUNCIÓN PÚBLICA — registra el atajo en la ventana raíz
# ══════════════════════════════════════════════════════════════════════════════
def registrar_atajo_diagnostico(root: ctk.CTk):
    """
    Llama esto desde main.py después de crear la ventana principal:
        from views.diagnostico import registrar_atajo_diagnostico
        registrar_atajo_diagnostico(app)

    Shift+Ctrl+H abre el diálogo de autenticación.
    Si ya hay una consola abierta, la trae al frente sin volver a autenticar.
    """
    _state = {"ventana": None}

    def _abrir_consola():
        if _state["ventana"] and _state["ventana"].winfo_exists():
            _state["ventana"].lift()
            _state["ventana"].focus_force()
            return
        win = DiagnosticoWindow(root)
        _state["ventana"] = win

    def _on_atajo(event=None):
        # Siempre pide PIN + pregunta, aunque la consola ya haya sido abierta antes
        def _exito():
            _abrir_consola()
        _AuthDialog(root, on_success=_exito)

    # Shift+Ctrl+H — ambas formas cubren Windows y Linux
    root.bind_all("<Control-H>",       _on_atajo)
    root.bind_all("<Control-Shift-H>", _on_atajo)