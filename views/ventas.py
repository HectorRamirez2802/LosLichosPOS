import customtkinter as ctk
import database as db
from views import ticket as tkt
import sqlite3
import shutil
from tkinter import messagebox, filedialog, ttk

C = {
    "bg":       "#0d0f14",
    "surface":  "#1c2030",
    "surface2": "#232840",
    "border":   "#2a2f45",
    "accent":   "#6c8aff",
    "green":    "#4ade80",
    "yellow":   "#fbbf24",
    "red":      "#ff6b6b",
    "text":     "#e8eaf6",
    "muted":    "#6b7280",
}

# ─── CREDENCIALES PARA ELIMINAR VENTAS ───────────────────────────────────────
_BACKUP_USER = "licho"
_BACKUP_PASS = "loslichos2020"


class _LoginEliminarDialog(ctk.CTkToplevel):
    """
    Diálogo de login que protege la eliminación de ventas.
    Llama a on_success() solo si usuario y contraseña son correctos.
    """

    def __init__(self, parent, on_success):
        super().__init__(parent)
        self._on_success = on_success
        self._intentos   = 0

        self.title("Autenticación requerida")
        self.geometry("380x300")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        self.grab_set()
        self.focus_force()
        self.after(10, self._centrar)

        frame = ctk.CTkFrame(self, fg_color=C["surface"], corner_radius=14)
        frame.pack(fill="both", expand=True, padx=20, pady=20)
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            frame, text="🔐",
            font=ctk.CTkFont(size=30)
        ).grid(row=0, column=0, pady=(18, 2))

        ctk.CTkLabel(
            frame, text="Ingresa tus credenciales para continuar",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=C["text"], wraplength=300, justify="center"
        ).grid(row=1, column=0, pady=(0, 14), padx=16)

        self._user_entry = ctk.CTkEntry(
            frame, placeholder_text="Usuario",
            height=36, fg_color=C["surface2"],
            border_color=C["border"], text_color=C["text"],
            font=ctk.CTkFont(size=13),
        )
        self._user_entry.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 6))

        self._pass_entry = ctk.CTkEntry(
            frame, placeholder_text="Contraseña", show="•",
            height=36, fg_color=C["surface2"],
            border_color=C["border"], text_color=C["text"],
            font=ctk.CTkFont(size=13),
        )
        self._pass_entry.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 4))

        self._error_lbl = ctk.CTkLabel(
            frame, text="",
            font=ctk.CTkFont(size=11),
            text_color=C["red"]
        )
        self._error_lbl.grid(row=4, column=0, pady=(0, 2))

        btn_row = ctk.CTkFrame(frame, fg_color="transparent")
        btn_row.grid(row=5, column=0, pady=(6, 16))

        ctk.CTkButton(
            btn_row, text="Cancelar", width=100,
            fg_color=C["surface2"], hover_color=C["border"],
            text_color=C["muted"],
            command=self.destroy
        ).pack(side="left", padx=6)

        ctk.CTkButton(
            btn_row, text="Confirmar", width=100,
            fg_color=C["accent"],
            command=self._verificar
        ).pack(side="left", padx=6)

        self._user_entry.focus()
        self._user_entry.bind("<Return>", lambda e: self._pass_entry.focus())
        self._pass_entry.bind("<Return>", lambda e: self._verificar())

    def _centrar(self):
        self.update_idletasks()
        pw = self.master.winfo_rootx() + self.master.winfo_width()  // 2
        ph = self.master.winfo_rooty() + self.master.winfo_height() // 2
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{pw - w//2}+{ph - h//2}")

    def _verificar(self):
        usuario = self._user_entry.get().strip()
        clave   = self._pass_entry.get().strip()

        if usuario == _BACKUP_USER and clave == _BACKUP_PASS:
            self.destroy()
            self._on_success()
        else:
            self._intentos += 1
            self._error_lbl.configure(text=f"Usuario o contraseña incorrectos. (intento {self._intentos})")
            self._pass_entry.delete(0, "end")
            self._pass_entry.focus()


class VentasView(ctk.CTkFrame):
    """
    Historial de ventas optimizado.

    Cambio importante respecto a la versión anterior:
    - Ya no se crea una fila con muchos CTkLabel/CTkButton por cada venta.
    - La lista principal usa ttk.Treeview, que es mucho más ligero.
    - El detalle de productos se carga solo para la venta seleccionada.
    - La búsqueda usa debounce para no consultar/redibujar en cada tecla.
    - Se usa paginación para evitar pintar cientos/miles de registros a la vez.

    FIX (bug de la tabla "achatada" en ciertos equipos):
    - Antes solo la fila 3 (la tabla) tenía weight=1 y sin minsize, así que en
      pantallas/ventanas con poca altura disponible, esa fila se comprimía
      hasta casi desaparecer mientras el resto de secciones (stats, filtros,
      panel de detalle) se quedaban con su tamaño fijo intacto.
    - Ahora la fila de la tabla tiene un minsize garantizado y el panel de
      detalle (que siempre está visible debajo) se hizo más compacto para
      dejarle más espacio a la tabla principal.
    """

    PAGE_SIZE = 100

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        # FIX: minsize evita que la tabla de ventas colapse en pantallas/ventanas
        # con poca altura disponible (bug reportado en otros equipos).
        self.grid_rowconfigure(3, weight=1, minsize=220)

        self.page = 1
        self.total_rows = 0
        self._ventas_cache = {}
        self._search_after_id = None

        self._ensure_perf_indexes()
        self._build_stats()
        self._build_toolbar()
        self._build_actions()
        self._build_tabla()
        self._build_detalle()
        self.cargar_ventas()

    def on_show(self):
        """Se llama desde main.py cuando vuelves a entrar al módulo Ventas.

        Permite mantener el historial actualizado sin necesitar un botón manual
        de refrescar. Conserva filtros, búsqueda y página actual.
        """
        self.cargar_ventas()

    # ════════════════════════════════════════════════════════════════════════
    #  PEQUEÑAS MEJORAS DE BD — SEGURAS, NO BORRAN DATOS
    # ════════════════════════════════════════════════════════════════════════
    def _ensure_perf_indexes(self):
        """Crea índices útiles para historial, filtros y detalle de ventas."""
        try:
            conn = sqlite3.connect(db.DB_PATH)
            cur = conn.cursor()
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ventas_fecha_id ON ventas(fecha DESC, id DESC)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ventas_tipo_fecha ON ventas(tipo, fecha DESC)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ventas_cliente ON ventas(cliente)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_venta_items_venta_id ON venta_items(venta_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_abonos_venta_id ON abonos(venta_id)")
            conn.commit()
        except Exception as e:
            print(f"[ventas] No se pudieron crear índices: {e}")
        finally:
            try:
                conn.close()
            except Exception:
                pass

    # ════════════════════════════════════════════════════════════════════════
    #  ESTADÍSTICAS
    # ════════════════════════════════════════════════════════════════════════
    def _build_stats(self):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.stat_hoy,      self.stat_hoy_lbl      = self._stat_card(frame, "Ventas hoy",      "—", C["accent"], 0)
        self.stat_ingresos, self.stat_ingresos_lbl = self._stat_card(frame, "Ingresos hoy",    "—", C["green"],  1)
        self.stat_total,    self.stat_total_lbl    = self._stat_card(frame, "En período",       "—", C["text"],   2)
        self.stat_cobrado,  self.stat_cobrado_lbl  = self._stat_card(frame, "Cobrado período",  "—", C["yellow"], 3)

    def _stat_card(self, parent, label, valor, color, col):
        card = ctk.CTkFrame(parent, fg_color=C["surface"], corner_radius=12)
        card.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 10, 0))
        card.grid_propagate(False)
        card.configure(height=90)

        lbl_titulo = ctk.CTkLabel(
            card, text=label, font=ctk.CTkFont(size=10),
            text_color=C["muted"], anchor="w", wraplength=160
        )
        lbl_titulo.place(x=16, y=12)

        lbl = ctk.CTkLabel(
            card, text=valor,
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=color, anchor="w"
        )
        lbl.place(x=16, y=46)
        return lbl, lbl_titulo

    # ════════════════════════════════════════════════════════════════════════
    #  FILTROS
    # ════════════════════════════════════════════════════════════════════════
    def _build_toolbar(self):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        frame.grid_columnconfigure(0, weight=1)

        self.buscador = ctk.CTkEntry(
            frame,
            placeholder_text="🔍  Buscar por cliente o folio...",
            height=40, fg_color=C["surface"], border_color=C["border"],
            text_color=C["text"], font=ctk.CTkFont(size=13),
        )
        self.buscador.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        self.buscador.bind("<KeyRelease>", self._programar_busqueda)

        self.filtro_var = ctk.StringVar(value="todas")
        filtros = [("Todas", "todas"), ("Contado", "contado"), ("Abono", "abono")]
        self.btns_filtro = {}
        for j, (label, valor) in enumerate(filtros):
            btn = ctk.CTkButton(
                frame, text=label, width=90, height=40,
                fg_color=C["accent"] if valor == "todas" else C["surface2"],
                hover_color="#8ba3ff" if valor == "todas" else C["surface"],
                text_color="#fff" if valor == "todas" else C["muted"],
                font=ctk.CTkFont(size=13),
                command=lambda v=valor: self._set_filtro(v)
            )
            btn.grid(row=0, column=j + 1, padx=(0, 6))
            self.btns_filtro[valor] = btn

        periodo_frame = ctk.CTkFrame(frame, fg_color="transparent")
        periodo_frame.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(18, 0))

        ctk.CTkLabel(
            periodo_frame, text="Período:",
            font=ctk.CTkFont(size=12), text_color=C["muted"]
        ).pack(side="left", padx=(0, 10))

        self.periodo_var = ctk.StringVar(value="todo")
        periodos = [
            ("Hoy",         "hoy"),
            ("Esta semana", "semana"),
            ("Este mes",    "mes"),
            ("Todo",        "todo"),
        ]
        self.btns_periodo = {}
        for label, valor in periodos:
            activo = valor == "todo"
            btn = ctk.CTkButton(
                periodo_frame, text=label, width=105, height=32,
                fg_color=C["accent"] if activo else C["surface2"],
                hover_color="#8ba3ff" if activo else C["surface"],
                text_color="#fff" if activo else C["muted"],
                font=ctk.CTkFont(size=12),
                corner_radius=8,
                command=lambda v=valor: self._set_periodo(v)
            )
            btn.pack(side="left", padx=(0, 6))
            self.btns_periodo[valor] = btn

        ctk.CTkLabel(periodo_frame, text="|", font=ctk.CTkFont(size=14),
                     text_color=C["border"]).pack(side="left", padx=(4, 10))

        self._fecha_esp       = None
        self._fecha_esp_desde = None
        self._fecha_esp_hasta = None

        fecha_grp = ctk.CTkFrame(periodo_frame, fg_color="transparent")
        fecha_grp.pack(side="left", padx=(0, 0))

        self.btn_fecha_esp = ctk.CTkButton(
            fecha_grp, text="📅  Fecha...", width=110, height=32,
            fg_color=C["surface2"], hover_color=C["surface"],
            text_color=C["muted"], font=ctk.CTkFont(size=12),
            corner_radius=8,
            command=self._abrir_selector_fecha
        )
        self.btn_fecha_esp.pack(side="left", padx=(0, 0))

        self.btn_limpiar_fecha = ctk.CTkButton(
            fecha_grp, text="✕", width=28, height=28,
            fg_color="#2a1520", hover_color="#3d1f2a",
            text_color=C["red"], font=ctk.CTkFont(size=11),
            corner_radius=6,
            command=self._limpiar_fecha_esp
        )

        ctk.CTkLabel(periodo_frame, text="|", font=ctk.CTkFont(size=14),
                     text_color=C["border"]).pack(side="left", padx=(12, 12))

        self.btn_cierre = ctk.CTkButton(
            periodo_frame, text="🖨  Cierre", width=110, height=32,
            fg_color=C["surface2"], hover_color=C["surface"],
            text_color=C["muted"], font=ctk.CTkFont(size=12),
            corner_radius=8,
            command=self._imprimir_cierre
        )
        self.btn_cierre.pack(side="left")


    def _programar_busqueda(self, _event=None):
        """Evita recargar la tabla en cada tecla; espera 250 ms."""
        if self._search_after_id:
            try:
                self.after_cancel(self._search_after_id)
            except Exception:
                pass
        self._search_after_id = self.after(250, self._busqueda_debounce)

    def _busqueda_debounce(self):
        self._search_after_id = None
        self.page = 1
        self.cargar_ventas()

    def _set_filtro(self, valor):
        self.filtro_var.set(valor)
        for k, btn in self.btns_filtro.items():
            if k == valor:
                btn.configure(fg_color=C["accent"], text_color="#fff", hover_color="#8ba3ff")
            else:
                btn.configure(fg_color=C["surface2"], text_color=C["muted"], hover_color=C["surface"])
        self.page = 1
        self.cargar_ventas()

    def _fecha_limite(self):
        """Devuelve (fecha_desde, fecha_hasta) como strings YYYY-MM-DD o None."""
        from datetime import datetime, timedelta
        if self._fecha_esp_desde:
            return self._fecha_esp_desde, self._fecha_esp_hasta
        periodo = self.periodo_var.get()
        hoy = datetime.now()
        if periodo == "hoy":
            d = hoy.strftime("%Y-%m-%d")
            return d, d
        if periodo == "semana":
            inicio = hoy - timedelta(days=hoy.weekday())
            return inicio.strftime("%Y-%m-%d"), None
        if periodo == "mes":
            return hoy.strftime("%Y-%m-01"), None
        return None, None

    def _abrir_selector_fecha(self):
        SelectorFechaDialog(self, on_rango=self._aplicar_fecha_esp)

    def _aplicar_fecha_esp(self, desde: str, hasta: str, etiqueta: str):
        self._fecha_esp       = etiqueta
        self._fecha_esp_desde = desde
        self._fecha_esp_hasta = hasta
        self.btn_fecha_esp.configure(
            text=f"📅  {etiqueta}",
            fg_color=C["accent"], text_color="#fff", hover_color="#8ba3ff"
        )
        for _k, btn in self.btns_periodo.items():
            btn.configure(fg_color=C["surface2"], text_color=C["muted"], hover_color=C["surface"])
        self.periodo_var.set("todo")
        self.btn_limpiar_fecha.pack(side="left", padx=(4, 0))
        self.page = 1
        self.cargar_ventas()

    def _limpiar_fecha_esp(self):
        self._fecha_esp       = None
        self._fecha_esp_desde = None
        self._fecha_esp_hasta = None
        self.btn_fecha_esp.configure(
            text="📅  Fecha...",
            fg_color=C["surface2"], text_color=C["muted"], hover_color=C["surface"]
        )
        self.btn_limpiar_fecha.pack_forget()
        self._set_periodo("todo")

    def _set_periodo(self, valor):
        if self._fecha_esp_desde:
            self._fecha_esp       = None
            self._fecha_esp_desde = None
            self._fecha_esp_hasta = None
            self.btn_fecha_esp.configure(
                text="📅  Fecha...",
                fg_color=C["surface2"], text_color=C["muted"], hover_color=C["surface"]
            )
            self.btn_limpiar_fecha.pack_forget()
        self.periodo_var.set(valor)
        for k, btn in self.btns_periodo.items():
            if k == valor:
                btn.configure(fg_color=C["accent"], text_color="#fff", hover_color="#8ba3ff")
            else:
                btn.configure(fg_color=C["surface2"], text_color=C["muted"], hover_color=C["surface"])
        self.page = 1
        self.cargar_ventas()

    # ════════════════════════════════════════════════════════════════════════
    #  ACCIONES PRINCIPALES
    # ════════════════════════════════════════════════════════════════════════
    def _build_actions(self):
        frame = ctk.CTkFrame(self, fg_color=C["surface"], corner_radius=10)
        frame.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        frame.grid_columnconfigure(0, weight=1)

        self.lbl_seleccion = ctk.CTkLabel(
            frame, text="Selecciona una venta para ver productos o aplicar acciones.",
            font=ctk.CTkFont(size=12), text_color=C["muted"], anchor="w"
        )
        self.lbl_seleccion.grid(row=0, column=0, sticky="ew", padx=14, pady=10)

        botones = ctk.CTkFrame(frame, fg_color="transparent")
        botones.grid(row=0, column=1, sticky="e", padx=8, pady=8)

        ctk.CTkButton(
            botones, text="🧾 Ticket", width=92, height=32,
            fg_color=C["surface2"], hover_color=C["border"],
            text_color=C["accent"], font=ctk.CTkFont(size=12),
            command=self._reimprimir_sel
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            botones, text="✏ Editar", width=88, height=32,
            fg_color="#1e2a1e", hover_color="#2a3f2a",
            text_color=C["green"], font=ctk.CTkFont(size=12),
            command=self._editar_sel
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            botones, text="🗑 Eliminar", width=94, height=32,
            fg_color="#2a1e1e", hover_color="#3f2a2a",
            text_color=C["red"], font=ctk.CTkFont(size=12),
            command=self._eliminar_sel
        ).pack(side="left")

    # ════════════════════════════════════════════════════════════════════════
    #  TABLA DE VENTAS — ttk.Treeview
    # ════════════════════════════════════════════════════════════════════════
    def _build_tabla(self):
        self._configurar_estilo_treeview()

        cont = ctk.CTkFrame(self, fg_color=C["surface"], corner_radius=10)
        cont.grid(row=3, column=0, sticky="nsew")
        cont.grid_columnconfigure(0, weight=1)
        cont.grid_rowconfigure(0, weight=1)

        columns = (
            "folio", "fecha", "cliente", "total", "pagado",
            "descuento", "tipo", "metodo", "estado"
        )
        self.tree = ttk.Treeview(
            cont,
            columns=columns,
            show="headings",
            selectmode="browse",
            style="Ventas.Treeview"
        )

        encabezados = {
            "folio":     ("Folio",       76,  "center"),
            "fecha":     ("Fecha",       145, "w"),
            "cliente":   ("Cliente",     260, "w"),
            "total":     ("Total",       105, "e"),
            "pagado":    ("Pagado",      105, "e"),
            "descuento": ("Descuento",   105, "center"),
            "tipo":      ("Tipo",        95,  "center"),
            "metodo":    ("Método",      125, "center"),
            "estado":    ("Estado",      115, "center"),
        }
        for col, (txt, width, anchor) in encabezados.items():
            self.tree.heading(col, text=txt)
            self.tree.column(col, width=width, minwidth=60, anchor=anchor, stretch=(col == "cliente"))

        yscroll = ttk.Scrollbar(cont, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(cont, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)

        self.tree.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=(8, 0))
        yscroll.grid(row=0, column=1, sticky="ns", pady=(8, 0), padx=(0, 8))
        xscroll.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))

        self.tree.bind("<<TreeviewSelect>>", self._on_venta_select)
        self.tree.bind("<Double-1>", lambda _e: self._ver_productos_seleccion())
        self.tree.bind("<Return>", lambda _e: self._ver_productos_seleccion())
        self.tree.bind("<Delete>", lambda _e: self._eliminar_sel())

        pag = ctk.CTkFrame(self, fg_color="transparent")
        pag.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        pag.grid_columnconfigure(1, weight=1)

        self.btn_prev = ctk.CTkButton(
            pag, text="◀ Anterior", width=110, height=32,
            fg_color=C["surface2"], hover_color=C["surface"],
            text_color=C["muted"], font=ctk.CTkFont(size=12),
            command=self._pagina_anterior
        )
        self.btn_prev.grid(row=0, column=0, sticky="w")

        self.lbl_pagina = ctk.CTkLabel(
            pag, text="", font=ctk.CTkFont(size=12),
            text_color=C["muted"]
        )
        self.lbl_pagina.grid(row=0, column=1)

        self.btn_next = ctk.CTkButton(
            pag, text="Siguiente ▶", width=110, height=32,
            fg_color=C["surface2"], hover_color=C["surface"],
            text_color=C["muted"], font=ctk.CTkFont(size=12),
            command=self._pagina_siguiente
        )
        self.btn_next.grid(row=0, column=2, sticky="e")

    def _configurar_estilo_treeview(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(
            "Ventas.Treeview",
            background=C["surface"],
            foreground=C["text"],
            fieldbackground=C["surface"],
            bordercolor=C["border"],
            rowheight=30,
            font=("Segoe UI", 10),
        )
        style.configure(
            "Ventas.Treeview.Heading",
            background=C["surface2"],
            foreground=C["muted"],
            relief="flat",
            font=("Segoe UI", 10, "bold"),
        )
        style.map(
            "Ventas.Treeview",
            background=[("selected", C["accent"])],
            foreground=[("selected", "#ffffff")],
        )
        style.configure(
            "Detalle.Treeview",
            background=C["bg"],
            foreground=C["text"],
            fieldbackground=C["bg"],
            rowheight=28,
            font=("Segoe UI", 10),
        )
        style.configure(
            "Detalle.Treeview.Heading",
            background=C["surface2"],
            foreground=C["muted"],
            relief="flat",
            font=("Segoe UI", 9, "bold"),
        )
        style.map(
            "Detalle.Treeview",
            background=[("selected", C["accent"])],
            foreground=[("selected", "#ffffff")],
        )

    # ════════════════════════════════════════════════════════════════════════
    #  PANEL DE DETALLE — SOLO UNA VENTA A LA VEZ
    # ════════════════════════════════════════════════════════════════════════
    def _build_detalle(self):
        self.detalle = ctk.CTkFrame(self, fg_color=C["surface"], corner_radius=10)
        self.detalle.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        self.detalle.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(self.detalle, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        top.grid_columnconfigure(0, weight=1)

        self.lbl_detalle = ctk.CTkLabel(
            top, text="Productos de la venta seleccionada",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=C["text"], anchor="w"
        )
        self.lbl_detalle.grid(row=0, column=0, sticky="w")

        self.lbl_descuento = ctk.CTkLabel(
            top, text="", font=ctk.CTkFont(size=11),
            text_color=C["yellow"], anchor="e"
        )
        self.lbl_descuento.grid(row=0, column=1, sticky="e")

        table_frame = ctk.CTkFrame(self.detalle, fg_color=C["bg"], corner_radius=8)
        table_frame.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))
        table_frame.grid_columnconfigure(0, weight=1)

        cols = ("producto", "precio", "cantidad", "subtotal", "detalle")
        self.detalle_tree = ttk.Treeview(
            table_frame,
            columns=cols,
            show="headings",
            # FIX: se reduce de 5 a 3 filas visibles para dejarle más espacio
            # vertical disponible a la tabla principal de ventas (row 3).
            height=3,
            style="Detalle.Treeview",
            selectmode="none"
        )
        specs = {
            "producto": ("Producto", 360, "w"),
            "precio":   ("Precio unit.", 110, "e"),
            "cantidad": ("Cantidad", 80, "center"),
            "subtotal": ("Subtotal", 110, "e"),
            "detalle":  ("Detalle", 240, "w"),
        }
        for col, (txt, width, anchor) in specs.items():
            self.detalle_tree.heading(col, text=txt)
            self.detalle_tree.column(col, width=width, minwidth=60, anchor=anchor, stretch=(col in ("producto", "detalle")))

        det_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.detalle_tree.yview)
        self.detalle_tree.configure(yscrollcommand=det_scroll.set)
        self.detalle_tree.grid(row=0, column=0, sticky="ew", padx=(8, 0), pady=8)
        det_scroll.grid(row=0, column=1, sticky="ns", pady=8, padx=(0, 8))

        self._limpiar_detalle()

    def _limpiar_detalle(self):
        for item in self.detalle_tree.get_children():
            self.detalle_tree.delete(item)
        self.lbl_detalle.configure(text="Productos de la venta seleccionada")
        self.lbl_descuento.configure(text="")

    # ════════════════════════════════════════════════════════════════════════
    #  CONSULTAS SQL
    # ════════════════════════════════════════════════════════════════════════
    def _fecha_siguiente(self, fecha: str) -> str:
        from datetime import datetime, timedelta
        return (datetime.strptime(fecha, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")

    def _period_where(self):
        clauses = []
        params = []
        fecha_desde, fecha_hasta = self._fecha_limite()
        if fecha_desde:
            clauses.append("fecha >= ?")
            params.append(fecha_desde)
        if fecha_hasta:
            clauses.append("fecha < ?")
            params.append(self._fecha_siguiente(fecha_hasta))
        return clauses, params

    def _where_actual(self):
        clauses, params = self._period_where()

        texto = self.buscador.get().strip()
        if texto:
            texto_like = f"%{texto}%"
            folio = texto.replace("#", "").strip()
            if folio.isdigit():
                clauses.append("(cliente LIKE ? COLLATE NOCASE OR id = ?)")
                params.extend([texto_like, int(folio)])
            else:
                clauses.append("cliente LIKE ? COLLATE NOCASE")
                params.append(texto_like)

        filtro = self.filtro_var.get()
        if filtro != "todas":
            clauses.append("tipo = ?")
            params.append(filtro)

        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        return where, params

    def _fetch_ventas(self):
        where, params = self._where_actual()
        offset = max(self.page - 1, 0) * self.PAGE_SIZE

        sql_count = f"SELECT COUNT(*) AS c FROM ventas{where}"
        sql_rows = f"""
            SELECT
                id, fecha, cliente, total, pagado, tipo, metodo_pago,
                subtotal_orig, descuento_monto, descuento_tipo,
                descuento_valor, descuento_etiq
            FROM ventas
            {where}
            ORDER BY fecha DESC, id DESC
            LIMIT ? OFFSET ?
        """

        conn = sqlite3.connect(db.DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            total = conn.execute(sql_count, params).fetchone()["c"]
            rows = conn.execute(sql_rows, params + [self.PAGE_SIZE, offset]).fetchall()
            return total, rows
        finally:
            conn.close()

    def _actualizar_stats(self):
        from datetime import datetime, timedelta

        hoy = datetime.now().strftime("%Y-%m-%d")
        manana = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        conn = sqlite3.connect(db.DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            row_hoy = conn.execute(
                """
                SELECT COUNT(*) AS c, COALESCE(SUM(pagado), 0) AS s
                FROM ventas
                WHERE fecha >= ? AND fecha < ?
                """,
                (hoy, manana)
            ).fetchone()

            pclauses, pparams = self._period_where()
            pwhere = " WHERE " + " AND ".join(pclauses) if pclauses else ""
            row_periodo = conn.execute(
                f"SELECT COUNT(*) AS c, COALESCE(SUM(pagado), 0) AS s FROM ventas{pwhere}",
                pparams
            ).fetchone()
        finally:
            conn.close()

        periodo = self.periodo_var.get()
        if self._fecha_esp_desde:
            lbl_conteo   = f"Ventas {self._fecha_esp}"
            lbl_ingresos = f"Ingresos {self._fecha_esp}"
        else:
            lbl_conteo   = {"hoy": "Ventas hoy", "semana": "Ventas semana",
                            "mes": "Ventas mes", "todo": "Ventas totales"}.get(periodo, "Ventas")
            lbl_ingresos = {"hoy": "Ingresos hoy", "semana": "Ingresos semana",
                            "mes": "Ingresos mes", "todo": "Total cobrado"}.get(periodo, "Ingresos")

        self.stat_hoy.configure(text=str(row_hoy["c"]))
        self.stat_ingresos.configure(text=f"${float(row_hoy['s']):.2f}")
        self.stat_total.configure(text=str(row_periodo["c"]))
        self.stat_cobrado.configure(text=f"${float(row_periodo['s']):.2f}")
        self.stat_total_lbl.configure(text=lbl_conteo)
        self.stat_cobrado_lbl.configure(text=lbl_ingresos)

    # ════════════════════════════════════════════════════════════════════════
    #  CARGA Y RENDER LIGERO
    # ════════════════════════════════════════════════════════════════════════
    def cargar_ventas(self):
        venta_seleccionada = self._get_selected_venta_id(default=None)
        self._actualizar_stats()

        try:
            self.total_rows, rows = self._fetch_ventas()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudieron cargar las ventas:\n{e}")
            return

        for item in self.tree.get_children():
            self.tree.delete(item)

        self._ventas_cache = {}
        for i, v in enumerate(rows):
            vid = int(v["id"])
            iid = str(vid)
            self._ventas_cache[iid] = dict(v)
            saldada = float(v["pagado"] or 0) >= float(v["total"] or 0)
            tag = "even" if i % 2 == 0 else "odd"
            if not saldada:
                tag = tag + " pendiente"

            self.tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    f"#{vid}",
                    self._fmt_fecha(v["fecha"]),
                    v["cliente"] or "Mostrador",
                    f"${float(v['total'] or 0):.2f}",
                    f"${float(v['pagado'] or 0):.2f}",
                    self._fmt_descuento(v),
                    "Contado" if v["tipo"] == "contado" else "Abono",
                    self._fmt_metodo(v["metodo_pago"] if "metodo_pago" in v.keys() else "efectivo"),
                    "Saldada" if saldada else "Pendiente",
                ),
                tags=tuple(tag.split())
            )

        self.tree.tag_configure("even", background=C["surface"])
        self.tree.tag_configure("odd", background=C["surface2"])
        self.tree.tag_configure("pendiente", foreground=C["red"])

        self._actualizar_paginacion(len(rows))

        if venta_seleccionada and str(venta_seleccionada) in self._ventas_cache:
            self.tree.selection_set(str(venta_seleccionada))
            self.tree.see(str(venta_seleccionada))
            self._cargar_detalle_venta(venta_seleccionada)
        elif rows:
            first = str(rows[0]["id"])
            self.tree.selection_set(first)
            self._on_venta_select()
        else:
            self._limpiar_detalle()
            self.lbl_seleccion.configure(text="No hay ventas que mostrar con los filtros actuales.")

    def _actualizar_paginacion(self, visibles):
        import math
        total_pages = max(1, math.ceil(self.total_rows / self.PAGE_SIZE))
        if self.page > total_pages:
            self.page = total_pages

        inicio = ((self.page - 1) * self.PAGE_SIZE + 1) if self.total_rows else 0
        fin = min(self.page * self.PAGE_SIZE, self.total_rows)
        self.lbl_pagina.configure(
            text=f"Página {self.page}/{total_pages}  •  Mostrando {inicio}-{fin} de {self.total_rows}"
        )
        self.btn_prev.configure(state="normal" if self.page > 1 else "disabled")
        self.btn_next.configure(state="normal" if self.page < total_pages else "disabled")

    def _pagina_anterior(self):
        if self.page > 1:
            self.page -= 1
            self.cargar_ventas()

    def _pagina_siguiente(self):
        import math
        total_pages = max(1, math.ceil(self.total_rows / self.PAGE_SIZE))
        if self.page < total_pages:
            self.page += 1
            self.cargar_ventas()

    # ════════════════════════════════════════════════════════════════════════
    #  FORMATOS Y SELECCIÓN
    # ════════════════════════════════════════════════════════════════════════
    def _fmt_fecha(self, fecha):
        if not fecha:
            return ""
        return str(fecha)[:16].replace("T", "  ")

    def _fmt_metodo(self, metodo):
        metodo = (metodo or "efectivo").strip().lower()
        iconos = {"efectivo": "💵", "tarjeta": "💳", "transferencia": "📲"}
        nombres = {"efectivo": "Efectivo", "tarjeta": "Tarjeta", "transferencia": "Transferencia"}
        return f"{iconos.get(metodo, '💵')} {nombres.get(metodo, metodo.capitalize())}"

    def _fmt_descuento(self, v):
        try:
            monto = float(v["descuento_monto"] or 0)
            if monto <= 0:
                return "N/A"
            tipo = v["descuento_tipo"] or ""
            valor = float(v["descuento_valor"] or 0)
            if tipo == "porcentaje":
                return f"{valor:.4g}%"
            return f"−${monto:.2f}"
        except Exception:
            return "N/A"

    def _get_selected_venta_id(self, default=None):
        try:
            sel = self.tree.selection()
            if not sel:
                return default
            return int(sel[0])
        except Exception:
            return default

    def _on_venta_select(self, _event=None):
        vid = self._get_selected_venta_id(default=None)
        if not vid:
            self._limpiar_detalle()
            self.lbl_seleccion.configure(text="Selecciona una venta para ver productos o aplicar acciones.")
            return
        venta = self._ventas_cache.get(str(vid), {})
        cliente = venta.get("cliente") or "Mostrador"
        total = float(venta.get("total") or 0)
        pagado = float(venta.get("pagado") or 0)
        self.lbl_seleccion.configure(
            text=f"Venta #{vid}  •  {cliente}  •  Total ${total:.2f}  •  Pagado ${pagado:.2f}"
        )
        self._cargar_detalle_venta(vid)

    # ════════════════════════════════════════════════════════════════════════
    #  DETALLE Y ACCIONES
    # ════════════════════════════════════════════════════════════════════════
    def _cargar_detalle_venta(self, venta_id: int):
        self._limpiar_detalle()
        self.lbl_detalle.configure(text=f"Productos de la venta #{venta_id}")

        try:
            items = db.obtener_items_venta(venta_id)
        except Exception as e:
            self.lbl_detalle.configure(text=f"No se pudo cargar el detalle: {e}")
            return

        if not items:
            self.detalle_tree.insert("", "end", values=("Sin productos registrados", "", "", "", ""))
            return

        # Leer datos de descuento de la venta antes de renderizar items
        _factor = 1.0
        _tiene_desc = False
        try:
            conn = sqlite3.connect(db.DB_PATH)
            conn.row_factory = sqlite3.Row
            vrow = conn.execute(
                "SELECT subtotal_orig, descuento_monto, descuento_etiq, total FROM ventas WHERE id = ?",
                (venta_id,)
            ).fetchone()
            conn.close()
            if vrow:
                desc_monto = float(vrow["descuento_monto"] or 0)
                if desc_monto > 0:
                    sub_orig  = float(vrow["subtotal_orig"] or 0)
                    total_fin = float(vrow["total"] or 0)
                    etiq      = vrow["descuento_etiq"] or "Descuento"
                    if sub_orig > 0:
                        _factor     = total_fin / sub_orig
                        _tiene_desc = True
                    self.lbl_descuento.configure(
                        text=f"Subtotal: ${sub_orig:.2f}  •  {etiq}: −${desc_monto:.2f}  •  Total: ${total_fin:.2f}"
                    )
        except Exception:
            pass

        # Encabezados con viñeta si hay descuento
        if _tiene_desc:
            self.detalle_tree.heading("precio",   text="Precio unit. 🏷️")
            self.detalle_tree.heading("subtotal", text="Subtotal 🏷️")
        else:
            self.detalle_tree.heading("precio",   text="Precio unit.")
            self.detalle_tree.heading("subtotal", text="Subtotal")

        for i, item in enumerate(items):
            tag = "even" if i % 2 == 0 else "odd"
            precio_unit = round(float(item.get("precio_unitario") or 0) * _factor, 2)
            subtotal_aj = round(float(item.get("subtotal") or 0) * _factor, 2)
            self.detalle_tree.insert(
                "", "end",
                values=(
                    item.get("nombre_producto", ""),
                    f"${precio_unit:.2f}",
                    str(item.get("cantidad", "")),
                    f"${subtotal_aj:.2f}",
                    item.get("nota_item", "") or "N/A",
                ),
                tags=(tag,)
            )
        self.detalle_tree.tag_configure("even", background=C["bg"])
        self.detalle_tree.tag_configure("odd", background=C["surface2"])

    def _ver_productos_seleccion(self):
        vid = self._get_selected_venta_id(default=None)
        if not vid:
            messagebox.showinfo("Sin selección", "Selecciona una venta primero.", parent=self)
            return
        self._cargar_detalle_venta(vid)

    def _reimprimir_sel(self):
        vid = self._get_selected_venta_id(default=None)
        if not vid:
            messagebox.showinfo("Sin selección", "Selecciona una venta primero.", parent=self)
            return
        self._reimprimir(vid)

    def _editar_sel(self):
        vid = self._get_selected_venta_id(default=None)
        if not vid:
            messagebox.showinfo("Sin selección", "Selecciona una venta primero.", parent=self)
            return
        self._editar(vid)

    def _eliminar_sel(self):
        vid = self._get_selected_venta_id(default=None)
        if not vid:
            messagebox.showinfo("Sin selección", "Selecciona una venta primero.", parent=self)
            return
        self._eliminar(vid)

    def _imprimir_cierre(self):
        CierreDialog(self)

    def _reimprimir(self, venta_id: int):
        ReimprimirDialog(self, venta_id=venta_id)

    def _editar(self, venta_id: int):
        EditarVentaDialog(self, venta_id=venta_id, on_save=self.cargar_ventas)

    def _eliminar(self, venta_id: int):
        def _proceder():
            confirmado = messagebox.askyesno(
                "Eliminar venta",
                f"¿Eliminar la venta #{venta_id}?\n\n"
                "• Se restaurará el stock de los productos.\n"
                "• Se borrarán los abonos asociados.\n"
                f"• El folio #{venta_id} no se reutilizará.\n\n"
                "Esta acción no se puede deshacer.",
                icon="warning",
            )
            if confirmado:
                try:
                    db.eliminar_venta(venta_id)
                    self.cargar_ventas()
                except Exception as e:
                    messagebox.showerror("Error", f"No se pudo eliminar la venta:\n{e}", parent=self)

        _LoginEliminarDialog(self, on_success=_proceder)

    # ════════════════════════════════════════════════════════════════════════
    #  ETIQUETAS DE PERÍODO — USADAS POR CIERRE
    # ════════════════════════════════════════════════════════════════════════
    def _etiqueta_periodo(self) -> str:
        from datetime import datetime
        if self._fecha_esp:
            return self._fecha_esp
        periodo = self.periodo_var.get()
        hoy = datetime.now()
        return {
            "hoy":    f"Hoy — {hoy.strftime('%d/%m/%Y')}",
            "semana": f"Esta semana ({hoy.strftime('%Y')})",
            "mes":    hoy.strftime("%B %Y").capitalize(),
            "todo":   "Todas las ventas",
        }.get(periodo, "Período")


# ─── SELECTOR DE FECHA / RANGO ──────────────────────────────────────────────
class SelectorFechaDialog(ctk.CTkToplevel):
    """
    Diálogo para elegir un rango de fechas: día específico, mes completo o año completo.
    Llama a on_rango(desde: str, hasta: str, etiqueta: str) al confirmar.
    """
    MESES = [
        "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
    ]

    def __init__(self, parent, on_rango):
        super().__init__(parent)
        self.on_rango = on_rango
        self.title("Seleccionar período")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        self.grab_set()
        self.lift()
        self.focus_force()
        self._build()

    def _build(self):
        from datetime import datetime
        hoy = datetime.now()
        self.geometry("380x460")
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self, text="📅  Filtrar por período",
            font=ctk.CTkFont(size=15, weight="bold"), text_color=C["text"]
        ).grid(row=0, column=0, padx=24, pady=(22, 2), sticky="w")

        ctk.CTkLabel(
            self, text="Elige si quieres filtrar por un día, un mes completo o un año completo.",
            font=ctk.CTkFont(size=11), text_color=C["muted"], wraplength=330, justify="left"
        ).grid(row=1, column=0, padx=24, pady=(0, 16), sticky="w")

        # ── Tipo de rango ────────────────────────────────────────────────────
        tipo_frame = ctk.CTkFrame(self, fg_color=C["surface2"], corner_radius=10)
        tipo_frame.grid(row=2, column=0, padx=24, sticky="ew", pady=(0, 14))
        tipo_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.tipo_var = ctk.StringVar(value="dia")
        self._btns_tipo = {}
        for col, (label, valor) in enumerate([("Día", "dia"), ("Semana", "semana"), ("Mes", "mes"), ("Año", "anio")]):
            activo = valor == "dia"
            btn = ctk.CTkButton(
                tipo_frame, text=label, height=34,
                fg_color=C["accent"] if activo else "transparent",
                hover_color="#8ba3ff" if activo else C["surface"],
                text_color="#fff" if activo else C["muted"],
                font=ctk.CTkFont(size=12, weight="bold" if activo else "normal"),
                corner_radius=8,
                command=lambda v=valor: self._cambiar_tipo(v)
            )
            btn.grid(row=0, column=col, padx=4, pady=4, sticky="ew")
            self._btns_tipo[valor] = btn

        # ── Panel de selección (se reconstruye según tipo) ───────────────────
        self._panel = ctk.CTkFrame(self, fg_color="transparent")
        self._panel.grid(row=3, column=0, padx=24, sticky="ew")
        self._panel.grid_columnconfigure(0, weight=1)

        self._anio_actual  = hoy.year
        self._mes_actual   = hoy.month
        self._dia_actual   = hoy.day

        self._mostrar_panel_dia()

        # ── Botones Aplicar / Cancelar ───────────────────────────────────────
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=4, column=0, padx=24, pady=20, sticky="ew")
        btn_frame.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            btn_frame, text="Aplicar", height=42,
            fg_color=C["accent"], hover_color="#8ba3ff",
            text_color="#fff", font=ctk.CTkFont(size=13, weight="bold"),
            command=self._aplicar
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(
            btn_frame, text="Cancelar", height=42,
            fg_color=C["surface2"], hover_color=C["surface"],
            text_color=C["muted"], font=ctk.CTkFont(size=13),
            command=self.destroy
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

    def _cambiar_tipo(self, tipo):
        self.tipo_var.set(tipo)
        for k, btn in self._btns_tipo.items():
            activo = k == tipo
            btn.configure(
                fg_color=C["accent"] if activo else "transparent",
                hover_color="#8ba3ff" if activo else C["surface"],
                text_color="#fff" if activo else C["muted"],
                font=ctk.CTkFont(size=12, weight="bold" if activo else "normal"),
            )
        for w in self._panel.winfo_children():
            w.destroy()
        if tipo == "dia":
            self._mostrar_panel_dia()
        elif tipo == "semana":
            self._mostrar_panel_semana()
        elif tipo == "mes":
            self._mostrar_panel_mes()
        else:
            self._mostrar_panel_anio()

    # ── Panel DÍA (con soporte de rango) ───────────────────────────────────
    def _mostrar_panel_dia(self):
        from datetime import datetime
        hoy = datetime.now()
        self.cal = None
        try:
            from tkcalendar import Calendar
            self.geometry("380x560")

            ctk.CTkLabel(
                self._panel,
                text="Haz clic en un día para elegirlo. Para un rango, activa el interruptor y selecciona inicio y fin.",
                font=ctk.CTkFont(size=10), text_color=C["muted"],
                wraplength=330, justify="left"
            ).grid(row=0, column=0, sticky="w", pady=(0, 6))

            # ── Toggle rango ────────────────────────────────────────────────
            tog_row = ctk.CTkFrame(self._panel, fg_color="transparent")
            tog_row.grid(row=1, column=0, sticky="ew", pady=(0, 6))

            ctk.CTkLabel(
                tog_row, text="Seleccionar rango de días:",
                font=ctk.CTkFont(size=11), text_color=C["text"]
            ).pack(side="left", padx=(0, 8))

            self._rango_var = ctk.BooleanVar(value=False)
            self._toggle_rango = ctk.CTkSwitch(
                tog_row, text="", variable=self._rango_var,
                width=44, height=22,
                fg_color=C["surface2"], progress_color=C["accent"],
                command=self._on_toggle_rango
            )
            self._toggle_rango.pack(side="left")

            # ── Calendario ─────────────────────────────────────────────────
            self.cal = Calendar(
                self._panel,
                selectmode="day",
                year=self._anio_actual, month=self._mes_actual, day=self._dia_actual,
                date_pattern="yyyy-mm-dd",
                background=C["surface"], foreground=C["text"],
                bordercolor=C["border"],
                headersbackground=C["surface2"], headersforeground=C["accent"],
                selectbackground=C["accent"], selectforeground="#fff",
                normalbackground=C["surface"], normalforeground=C["text"],
                weekendbackground=C["surface2"], weekendforeground=C["muted"],
                othermonthbackground=C["bg"], othermonthforeground=C["border"],
                font="TkDefaultFont 11", showweeknumbers=False,
            )
            self.cal.grid(row=2, column=0, sticky="ew")

            # ── Indicador de rango seleccionado ────────────────────────────
            self._lbl_rango = ctk.CTkLabel(
                self._panel, text="",
                font=ctk.CTkFont(size=11), text_color=C["accent"]
            )
            self._lbl_rango.grid(row=3, column=0, pady=(6, 0))

            # Estado interno para modo rango
            self._rango_inicio = None
            self._rango_fin    = None
            self._esperando_fin = False
            self.cal.bind("<<CalendarSelected>>", self._on_cal_click)

        except Exception:
            # Fallback: dos entries de texto
            self.geometry("380x460")
            self._rango_var = ctk.BooleanVar(value=True)  # siempre rango en fallback

            ctk.CTkLabel(
                self._panel, text="Desde (AAAA-MM-DD):",
                font=ctk.CTkFont(size=12), text_color=C["muted"]
            ).grid(row=0, column=0, sticky="w", pady=(0, 4))
            self.entry_dia_desde = ctk.CTkEntry(
                self._panel, height=42, placeholder_text="Ej: 2025-06-01",
                fg_color=C["surface"], border_color=C["border"],
                text_color=C["text"], font=ctk.CTkFont(size=14),
            )
            self.entry_dia_desde.insert(0, hoy.strftime("%Y-%m-%d"))
            self.entry_dia_desde.grid(row=1, column=0, sticky="ew", pady=(0, 10))

            ctk.CTkLabel(
                self._panel, text="Hasta (AAAA-MM-DD):",
                font=ctk.CTkFont(size=12), text_color=C["muted"]
            ).grid(row=2, column=0, sticky="w", pady=(0, 4))
            self.entry_dia_hasta = ctk.CTkEntry(
                self._panel, height=42, placeholder_text="Ej: 2025-06-30",
                fg_color=C["surface"], border_color=C["border"],
                text_color=C["text"], font=ctk.CTkFont(size=14),
            )
            self.entry_dia_hasta.insert(0, hoy.strftime("%Y-%m-%d"))
            self.entry_dia_hasta.grid(row=3, column=0, sticky="ew")

    def _on_toggle_rango(self):
        """Activa/desactiva el modo de selección de rango."""
        if self._rango_var.get():
            # Entrar en modo rango: reiniciar selección
            self._rango_inicio  = None
            self._rango_fin     = None
            self._esperando_fin = False
            self._lbl_rango.configure(
                text="1er clic: día inicio  |  2do clic: día fin"
            )
        else:
            # Volver a modo un solo día
            self._rango_inicio  = None
            self._rango_fin     = None
            self._esperando_fin = False
            self._lbl_rango.configure(text="")
            # Limpiar resaltado
            try:
                for tag in list(self.cal.tag_names()):
                    if tag.startswith("rango_"):
                        self.cal.tag_delete(tag)
            except Exception:
                pass

    def _on_cal_click(self, _event=None):
        """Maneja clics en el calendario según modo (día único vs rango)."""
        from datetime import datetime
        if not self._rango_var.get():
            # Modo día único — nada extra que hacer
            self._lbl_rango.configure(text="")
            return

        fecha_str = self.cal.get_date()
        try:
            fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        except Exception:
            return

        if not self._esperando_fin:
            # Primer clic: inicio del rango
            self._rango_inicio  = fecha
            self._rango_fin     = None
            self._esperando_fin = True
            d, m, a = fecha.day, fecha.month, fecha.year
            self._lbl_rango.configure(
                text=f"Inicio: {d:02d}/{m:02d}/{a}  →  Elige el día final"
            )
        else:
            # Segundo clic: fin del rango
            if fecha < self._rango_inicio:
                fecha, self._rango_inicio = self._rango_inicio, fecha
            self._rango_fin     = fecha
            self._esperando_fin = False
            d1, m1, a1 = self._rango_inicio.day, self._rango_inicio.month, self._rango_inicio.year
            d2, m2, a2 = self._rango_fin.day,    self._rango_fin.month,    self._rango_fin.year
            if self._rango_inicio == self._rango_fin:
                self._lbl_rango.configure(
                    text=f"✔ Día: {d1:02d}/{m1:02d}/{a1}"
                )
            else:
                self._lbl_rango.configure(
                    text=f"✔ Del {d1:02d}/{m1:02d}/{a1} al {d2:02d}/{m2:02d}/{a2}"
                )

    # ── Panel SEMANA (rango de días) ────────────────────────────────────────
    def _mostrar_panel_semana(self):
        from datetime import datetime, timedelta
        self.geometry("380x460")
        f = self._panel

        hoy = datetime.now()
        # Inicializar con la semana actual (lunes a domingo)
        lunes = hoy - timedelta(days=hoy.weekday())
        self._semana_inicio = lunes.replace(hour=0, minute=0, second=0, microsecond=0)

        ctk.CTkLabel(
            f, text="Selecciona la semana:",
            font=ctk.CTkFont(size=12), text_color=C["muted"]
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        nav_row = ctk.CTkFrame(f, fg_color="transparent")
        nav_row.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        nav_row.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(nav_row, text="◀", width=36, height=36,
                      fg_color=C["surface2"], hover_color=C["surface"],
                      text_color=C["text"], font=ctk.CTkFont(size=14),
                      command=self._semana_anterior).grid(row=0, column=0)

        self.lbl_semana = ctk.CTkLabel(
            nav_row, text="",
            font=ctk.CTkFont(size=13, weight="bold"), text_color=C["accent"]
        )
        self.lbl_semana.grid(row=0, column=1)

        ctk.CTkButton(nav_row, text="▶", width=36, height=36,
                      fg_color=C["surface2"], hover_color=C["surface"],
                      text_color=C["text"], font=ctk.CTkFont(size=14),
                      command=self._semana_siguiente).grid(row=0, column=2)

        # Días de la semana (visualización)
        self.dias_frame = ctk.CTkFrame(f, fg_color=C["surface2"], corner_radius=10)
        self.dias_frame.grid(row=2, column=0, sticky="ew", pady=(0, 8))

        ctk.CTkLabel(
            f, text="Se incluirán todos los días de la semana mostrada.",
            font=ctk.CTkFont(size=10), text_color=C["muted"], wraplength=300
        ).grid(row=3, column=0, pady=(4, 0))

        self._actualizar_semana()

    def _actualizar_semana(self):
        from datetime import timedelta
        for w in self.dias_frame.winfo_children():
            w.destroy()
        # Configurar 7 columnas de igual peso para que quepan todas
        for col in range(7):
            self.dias_frame.grid_columnconfigure(col, weight=1)
        fin = self._semana_inicio + timedelta(days=6)
        fmt = "%d/%m/%Y"
        self.lbl_semana.configure(
            text=f"{self._semana_inicio.strftime(fmt)} — {fin.strftime(fmt)}"
        )
        dias_es = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
        for i in range(7):
            dia = self._semana_inicio + timedelta(days=i)
            ctk.CTkLabel(
                self.dias_frame,
                text=f"{dias_es[i]}\n{dia.strftime('%d')}",
                font=ctk.CTkFont(size=10), text_color=C["text"],
                height=44, corner_radius=8,
                fg_color=C["surface"] if i < 5 else C["surface2"]
            ).grid(row=0, column=i, padx=2, pady=8, sticky="ew")

    def _semana_anterior(self):
        from datetime import timedelta
        self._semana_inicio -= timedelta(weeks=1)
        self._actualizar_semana()

    def _semana_siguiente(self):
        from datetime import timedelta
        self._semana_inicio += timedelta(weeks=1)
        self._actualizar_semana()

    # ── Panel MES ──────────────────────────────────────────────────────────
    def _mostrar_panel_mes(self):
        self.geometry("380x440")
        f = self._panel

        # Selector de año
        anio_row = ctk.CTkFrame(f, fg_color="transparent")
        anio_row.grid(row=0, column=0, sticky="ew", pady=(4, 12))
        anio_row.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(anio_row, text="◀", width=36, height=36,
                      fg_color=C["surface2"], hover_color=C["surface"],
                      text_color=C["text"], font=ctk.CTkFont(size=14),
                      command=self._anio_menos_mes).grid(row=0, column=0)

        self.lbl_anio_mes = ctk.CTkLabel(
            anio_row, text=str(self._anio_actual),
            font=ctk.CTkFont(size=16, weight="bold"), text_color=C["text"]
        )
        self.lbl_anio_mes.grid(row=0, column=1)

        ctk.CTkButton(anio_row, text="▶", width=36, height=36,
                      fg_color=C["surface2"], hover_color=C["surface"],
                      text_color=C["text"], font=ctk.CTkFont(size=14),
                      command=self._anio_mas_mes).grid(row=0, column=2)

        # Grid de meses
        self.meses_frame = ctk.CTkFrame(f, fg_color="transparent")
        self.meses_frame.grid(row=1, column=0, sticky="ew")
        self._dibujar_meses()

    def _dibujar_meses(self):
        for w in self.meses_frame.winfo_children():
            w.destroy()
        for i, nombre in enumerate(self.MESES):
            fila, col = divmod(i, 3)
            activo = (i + 1) == self._mes_actual
            btn = ctk.CTkButton(
                self.meses_frame, text=nombre, height=34, width=100,
                fg_color=C["accent"] if activo else C["surface2"],
                hover_color="#8ba3ff" if activo else C["surface"],
                text_color="#fff" if activo else C["text"],
                font=ctk.CTkFont(size=11),
                corner_radius=8,
                command=lambda m=i + 1: self._seleccionar_mes(m)
            )
            btn.grid(row=fila, column=col, padx=3, pady=3)

    def _seleccionar_mes(self, mes):
        self._mes_actual = mes
        self._dibujar_meses()

    def _anio_menos_mes(self):
        self._anio_actual -= 1
        self.lbl_anio_mes.configure(text=str(self._anio_actual))
        self._dibujar_meses()

    def _anio_mas_mes(self):
        self._anio_actual += 1
        self.lbl_anio_mes.configure(text=str(self._anio_actual))
        self._dibujar_meses()

    # ── Panel AÑO ──────────────────────────────────────────────────────────
    def _mostrar_panel_anio(self):
        self.geometry("380x460")
        f = self._panel

        anio_row = ctk.CTkFrame(f, fg_color="transparent")
        anio_row.grid(row=0, column=0, sticky="ew", pady=20)
        anio_row.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(anio_row, text="◀", width=36, height=36,
                      fg_color=C["surface2"], hover_color=C["surface"],
                      text_color=C["text"], font=ctk.CTkFont(size=14),
                      command=self._anio_menos).grid(row=0, column=0)

        self.lbl_anio = ctk.CTkLabel(
            anio_row, text=str(self._anio_actual),
            font=ctk.CTkFont(size=28, weight="bold"), text_color=C["accent"]
        )
        self.lbl_anio.grid(row=0, column=1)

        ctk.CTkButton(anio_row, text="▶", width=36, height=36,
                      fg_color=C["surface2"], hover_color=C["surface"],
                      text_color=C["text"], font=ctk.CTkFont(size=14),
                      command=self._anio_mas).grid(row=0, column=2)

        ctk.CTkLabel(
            f, text="Se incluirán todas las ventas del año seleccionado.",
            font=ctk.CTkFont(size=11), text_color=C["muted"], wraplength=300, justify="center"
        ).grid(row=1, column=0, pady=(0, 8))

    def _anio_menos(self):
        self._anio_actual -= 1
        self.lbl_anio.configure(text=str(self._anio_actual))

    def _anio_mas(self):
        self._anio_actual += 1
        self.lbl_anio.configure(text=str(self._anio_actual))

    # ── Aplicar ────────────────────────────────────────────────────────────
    def _aplicar(self):
        from datetime import datetime, timedelta
        import calendar
        tipo = self.tipo_var.get()

        if tipo == "dia":
            # ── Con tkcalendar ──────────────────────────────────────────────
            if hasattr(self, "cal") and self.cal:
                es_rango = self._rango_var.get()

                if not es_rango:
                    # Día único: lo que tenga seleccionado el calendario
                    try:
                        fecha = self.cal.get_date()
                        datetime.strptime(fecha, "%Y-%m-%d")
                    except Exception:
                        messagebox.showerror("Fecha inválida",
                                             "No se pudo leer la fecha del calendario.", parent=self)
                        return
                    d, m, a = fecha[8:], fecha[5:7], fecha[:4]
                    self.on_rango(fecha, fecha, f"{d}/{m}/{a}")
                else:
                    # Modo rango: necesitamos inicio y fin
                    if not self._rango_inicio or not self._rango_fin:
                        messagebox.showerror(
                            "Rango incompleto",
                            "Haz clic en el día de inicio y luego en el día de fin.",
                            parent=self
                        )
                        return
                    desde = self._rango_inicio.strftime("%Y-%m-%d")
                    hasta = self._rango_fin.strftime("%Y-%m-%d")
                    d1 = self._rango_inicio.strftime("%d/%m/%Y")
                    d2 = self._rango_fin.strftime("%d/%m/%Y")
                    if desde == hasta:
                        etiqueta = d1
                    else:
                        etiqueta = f"{d1} – {d2}"
                    self.on_rango(desde, hasta, etiqueta)

            # ── Fallback (dos entries de texto) ─────────────────────────────
            else:
                try:
                    desde = self.entry_dia_desde.get().strip()
                    hasta = self.entry_dia_hasta.get().strip()
                    datetime.strptime(desde, "%Y-%m-%d")
                    datetime.strptime(hasta, "%Y-%m-%d")
                    if hasta < desde:
                        desde, hasta = hasta, desde
                except Exception:
                    messagebox.showerror("Fecha inválida",
                                         "Usa el formato AAAA-MM-DD (ej. 2025-06-01)", parent=self)
                    return
                d1 = f"{desde[8:]}/{desde[5:7]}/{desde[:4]}"
                d2 = f"{hasta[8:]}/{hasta[5:7]}/{hasta[:4]}"
                etiqueta = d1 if desde == hasta else f"{d1} – {d2}"
                self.on_rango(desde, hasta, etiqueta)

        elif tipo == "semana":
            inicio = self._semana_inicio
            fin    = inicio + timedelta(days=6)
            desde  = inicio.strftime("%Y-%m-%d")
            hasta  = fin.strftime("%Y-%m-%d")
            fmt    = "%-d/%m/%Y" if hasattr(inicio, "day") else "%d/%m/%Y"
            try:
                etiqueta = f"Semana del: {inicio.strftime(fmt)} - {fin.strftime(fmt)}"
            except Exception:
                etiqueta = f"Semana del: {inicio.strftime('%d/%m/%Y')} - {fin.strftime('%d/%m/%Y')}"
            self.on_rango(desde, hasta, etiqueta)

        elif tipo == "mes":
            a, m = self._anio_actual, self._mes_actual
            ultimo_dia = calendar.monthrange(a, m)[1]
            desde = f"{a:04d}-{m:02d}-01"
            hasta = f"{a:04d}-{m:02d}-{ultimo_dia:02d}"
            etiqueta = f"{self.MESES[m - 1]} {a}"
            self.on_rango(desde, hasta, etiqueta)

        else:  # anio
            a = self._anio_actual
            desde = f"{a:04d}-01-01"
            hasta = f"{a:04d}-12-31"
            self.on_rango(desde, hasta, str(a))

        self.destroy()


# ─── DIÁLOGO EDITAR VENTA ────────────────────────────────────────────────────
class EditarVentaDialog(ctk.CTkToplevel):
    """
    Permite editar cliente, total, pagado, tipo y nota de una venta.
    El folio/ID nunca cambia.
    """
    def __init__(self, parent, venta_id: int, on_save=None):
        super().__init__(parent)
        self.venta_id = venta_id
        self.on_save  = on_save

        self.title(f"Editar Venta — Folio #{venta_id}")
        self.geometry("440x560")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        self.grab_set()
        self.lift()
        self.focus_force()

        self._cargar_datos()
        self._build()

    def _cargar_datos(self):
        conn = sqlite3.connect(db.DB_PATH)
        conn.row_factory = sqlite3.Row
        self._venta = conn.execute(
            "SELECT * FROM ventas WHERE id = ?", (self.venta_id,)
        ).fetchone()
        conn.close()

    def _build(self):
        v = self._venta
        self.grid_columnconfigure(0, weight=1)

        # Título
        ctk.CTkLabel(
            self, text=f"✏  Editar Venta — Folio #{self.venta_id}",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=C["text"]
        ).grid(row=0, column=0, padx=24, pady=(22, 4), sticky="w")

        ctk.CTkLabel(
            self, text="El folio no cambia. Solo se actualizan los datos de la venta.",
            font=ctk.CTkFont(size=11), text_color=C["muted"]
        ).grid(row=1, column=0, padx=24, pady=(0, 16), sticky="w")

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.grid(row=2, column=0, padx=24, sticky="ew")
        form.grid_columnconfigure(1, weight=1)

        def campo(row, label, widget_factory):
            ctk.CTkLabel(
                form, text=label, font=ctk.CTkFont(size=12),
                text_color=C["muted"], anchor="w"
            ).grid(row=row, column=0, sticky="w", pady=6, padx=(0, 14))
            w = widget_factory(form)
            w.grid(row=row, column=1, sticky="ew", pady=6)
            return w

        # Cliente
        self.ent_cliente = campo(0, "Cliente", lambda p: ctk.CTkEntry(
            p, height=36, fg_color=C["surface"], border_color=C["border"],
            text_color=C["text"], font=ctk.CTkFont(size=13)
        ))
        self.ent_cliente.insert(0, v["cliente"])

        # Total
        self.ent_total = campo(1, "Total ($)", lambda p: ctk.CTkEntry(
            p, height=36, fg_color=C["surface"], border_color=C["border"],
            text_color=C["text"], font=ctk.CTkFont(size=13)
        ))
        self.ent_total.insert(0, str(v["total"]))

        # Pagado
        self.ent_pagado = campo(2, "Pagado ($)", lambda p: ctk.CTkEntry(
            p, height=36, fg_color=C["surface"], border_color=C["border"],
            text_color=C["text"], font=ctk.CTkFont(size=13)
        ))
        self.ent_pagado.insert(0, str(v["pagado"]))
        # Aviso de límite
        self.lbl_pagado_warn = ctk.CTkLabel(
            form, text="", font=ctk.CTkFont(size=11), text_color=C["red"]
        )
        self.lbl_pagado_warn.grid(row=2, column=1, sticky="w")
        self.ent_pagado.bind("<KeyRelease>", self._validar_pagado)
        self.ent_total.bind("<KeyRelease>", self._validar_pagado)

        # Tipo
        self.tipo_var = ctk.StringVar(value=v["tipo"])
        tipo_frame = ctk.CTkFrame(form, fg_color="transparent")
        tipo_frame.grid(row=3, column=1, sticky="ew", pady=6)
        ctk.CTkLabel(
            form, text="Tipo", font=ctk.CTkFont(size=12),
            text_color=C["muted"], anchor="w"
        ).grid(row=3, column=0, sticky="w", pady=6, padx=(0, 14))
        ctk.CTkRadioButton(
            tipo_frame, text="Contado", variable=self.tipo_var, value="contado",
            text_color=C["text"], font=ctk.CTkFont(size=13)
        ).pack(side="left", padx=(0, 16))
        ctk.CTkRadioButton(
            tipo_frame, text="Abono", variable=self.tipo_var, value="abono",
            text_color=C["text"], font=ctk.CTkFont(size=13)
        ).pack(side="left")

        # Nota
        self.ent_nota = campo(4, "Nota", lambda p: ctk.CTkEntry(
            p, height=36, fg_color=C["surface"], border_color=C["border"],
            text_color=C["text"], font=ctk.CTkFont(size=13)
        ))
        self.ent_nota.insert(0, v["nota"] or "")

        # Método de pago
        metodo_actual = v["metodo_pago"] if "metodo_pago" in v.keys() else "efectivo"
        metodo_actual = metodo_actual or "efectivo"
        ctk.CTkLabel(
            form, text="Método", font=ctk.CTkFont(size=12),
            text_color=C["muted"], anchor="w"
        ).grid(row=5, column=0, sticky="w", pady=6, padx=(0, 14))

        metodo_frame = ctk.CTkFrame(form, fg_color="transparent")
        metodo_frame.grid(row=5, column=1, sticky="ew", pady=6)
        metodo_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.metodo_var = ctk.StringVar(value=metodo_actual)
        self._btns_metodo = {}
        for col_m, (lbl_m, val_m) in enumerate([
            ("💵 Efectivo", "efectivo"),
            ("💳 Tarjeta",  "tarjeta"),
            ("📲 Transf.",  "transferencia"),
        ]):
            activo_m = val_m == metodo_actual
            btn_m = ctk.CTkButton(
                metodo_frame, text=lbl_m, height=34,
                fg_color=C["accent"] if activo_m else C["surface2"],
                hover_color="#8ba3ff",
                text_color="#fff" if activo_m else C["muted"],
                font=ctk.CTkFont(size=11, weight="bold" if activo_m else "normal"),
                command=lambda v=val_m: self._set_metodo(v)
            )
            btn_m.grid(row=0, column=col_m, sticky="ew",
                       padx=(0 if col_m == 0 else 4, 4 if col_m < 2 else 0))
            self._btns_metodo[val_m] = btn_m

        # Botones
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=3, column=0, padx=24, pady=(20, 0), sticky="ew")
        btn_frame.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            btn_frame, text="💾  Guardar", height=42,
            fg_color=C["accent"], hover_color="#8ba3ff",
            text_color="#fff", font=ctk.CTkFont(size=13, weight="bold"),
            command=self._guardar
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(
            btn_frame, text="Cancelar", height=42,
            fg_color="transparent", hover_color=C["surface2"],
            text_color=C["muted"], font=ctk.CTkFont(size=13),
            border_width=1, border_color=C["border"],
            command=self.destroy
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

    def _set_metodo(self, metodo):
        self.metodo_var.set(metodo)
        for valor, btn in self._btns_metodo.items():
            if valor == metodo:
                btn.configure(fg_color=C["accent"], text_color="#fff",
                               font=ctk.CTkFont(size=11, weight="bold"))
            else:
                btn.configure(fg_color=C["surface2"], text_color=C["muted"],
                               font=ctk.CTkFont(size=11, weight="normal"))

    def _validar_pagado(self, _event=None):
        try:
            total  = float(self.ent_total.get().strip())
            pagado = float(self.ent_pagado.get().strip())
            if pagado > total:
                self.lbl_pagado_warn.configure(text=f"⚠ No puede superar el total (${total:.2f})")
            else:
                self.lbl_pagado_warn.configure(text="")
        except ValueError:
            self.lbl_pagado_warn.configure(text="")

    def _guardar(self):
        cliente = self.ent_cliente.get().strip() or "Mostrador"
        nota    = self.ent_nota.get().strip()
        tipo    = self.tipo_var.get()

        try:
            total  = float(self.ent_total.get().strip())
            pagado = float(self.ent_pagado.get().strip())
        except ValueError:
            messagebox.showerror("Error", "Total y Pagado deben ser números.", parent=self)
            return

        if total < 0 or pagado < 0:
            messagebox.showerror("Error", "Los montos no pueden ser negativos.", parent=self)
            return

        if pagado > total:
            messagebox.showerror(
                "Error",
                f"El monto pagado (${pagado:.2f}) no puede superar el total (${total:.2f}).",
                parent=self
            )
            return

        try:
            db.editar_venta(self.venta_id, cliente, total, pagado, tipo, nota,
                            self.metodo_var.get())
            if self.on_save:
                self.on_save()
            self.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar:\n{e}", parent=self)


# ─── DIÁLOGO REIMPRIMIR ───────────────────────────────────────────────────────
class ReimprimirDialog(ctk.CTkToplevel):
    """
    Diálogo compacto para reimprimir o descargar el ticket de una venta existente.
    """
    def __init__(self, parent, venta_id: int):
        super().__init__(parent)
        self.venta_id = venta_id
        self._pdf     = None

        self.title(f"Ticket — Folio #{venta_id}")
        self.geometry("340x200")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        self.grab_set()
        self.lift()
        self.focus_force()
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self, text=f"🧾  Ticket — Folio #{self.venta_id}",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=C["text"]
        ).grid(row=0, column=0, columnspan=2, padx=24, pady=(22, 6), sticky="w")

        ctk.CTkLabel(
            self, text="¿Qué deseas hacer con el ticket?",
            font=ctk.CTkFont(size=12), text_color=C["muted"]
        ).grid(row=1, column=0, columnspan=2, padx=24, pady=(0, 16), sticky="w")

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=2, column=0, padx=24, sticky="ew")
        btn_frame.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            btn_frame, text="🖨  Imprimir", height=42,
            fg_color=C["accent"], hover_color="#8ba3ff",
            text_color="#fff", font=ctk.CTkFont(size=13, weight="bold"),
            command=self._imprimir
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(
            btn_frame, text="⬇  Guardar PDF", height=42,
            fg_color=C["surface2"], hover_color=C["surface"],
            text_color=C["text"], font=ctk.CTkFont(size=13),
            command=self._guardar_pdf
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        ctk.CTkButton(
            self, text="Cerrar", height=34,
            fg_color="transparent", hover_color=C["surface2"],
            text_color=C["muted"], font=ctk.CTkFont(size=12),
            border_width=1, border_color=C["border"],
            command=self.destroy
        ).grid(row=3, column=0, padx=24, pady=(12, 20), sticky="ew")

    def _get_pdf(self) -> str:
        if self._pdf is None:
            self._pdf = tkt.ticket_desde_venta_id(self.venta_id, abrir=False)
        return self._pdf

    def _imprimir(self):
        try:
            tkt.imprimir_pdf(self._get_pdf())
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo generar el ticket:\n{e}", parent=self)

    def _guardar_pdf(self):
        destino = filedialog.asksaveasfilename(
            parent=self,
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")],
            initialfile=f"ticket_{self.venta_id}.pdf",
            title="Guardar ticket como PDF"
        )
        if not destino:
            return
        try:
            shutil.copy2(self._get_pdf(), destino)
            messagebox.showinfo("✔ Guardado", f"Ticket guardado en:\n{destino}", parent=self)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar:\n{e}", parent=self)

# ─── DIÁLOGO CIERRE DE VENTAS ─────────────────────────────────────────────────
class CierreDialog(ctk.CTkToplevel):
    """
    Genera un cierre de ventas en PDF (hoja carta/A4) según el filtro activo
    en VentasView y permite imprimirlo o guardarlo.
    """
    def __init__(self, ventas_view: "VentasView"):
        super().__init__(ventas_view)
        self.vv = ventas_view
        self._pdf_path = None

        etiqueta = ventas_view._etiqueta_periodo()
        self.title(f"Cierre — {etiqueta}")
        self.geometry("360x210")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        self.grab_set()
        self.lift()
        self.focus_force()
        self._build(etiqueta)

    def _build(self, etiqueta: str):
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self, text=f"🖨  Cierre: {etiqueta}",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=C["text"]
        ).grid(row=0, column=0, columnspan=2, padx=24, pady=(22, 4), sticky="w")

        ctk.CTkLabel(
            self, text="Genera el cierre de ventas del período activo en la vista.",
            font=ctk.CTkFont(size=11), text_color=C["muted"], wraplength=310, justify="left"
        ).grid(row=1, column=0, columnspan=2, padx=24, pady=(0, 16), sticky="w")

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=2, column=0, padx=24, sticky="ew")
        btn_frame.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            btn_frame, text="🖨  Imprimir", height=42,
            fg_color=C["accent"], hover_color="#8ba3ff",
            text_color="#fff", font=ctk.CTkFont(size=13, weight="bold"),
            command=self._imprimir
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(
            btn_frame, text="⬇  Guardar PDF", height=42,
            fg_color=C["surface2"], hover_color=C["surface"],
            text_color=C["text"], font=ctk.CTkFont(size=13),
            command=self._guardar_pdf
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        ctk.CTkButton(
            self, text="Cerrar", height=34,
            fg_color="transparent", hover_color=C["surface2"],
            text_color=C["muted"], font=ctk.CTkFont(size=12),
            border_width=1, border_color=C["border"],
            command=self.destroy
        ).grid(row=3, column=0, padx=24, pady=(12, 20), sticky="ew")

    # ── Generar PDF de cierre ─────────────────────────────────────────────
    def _get_pdf(self) -> str:
        if self._pdf_path:
            return self._pdf_path
        self._pdf_path = self._generar_cierre_pdf()
        return self._pdf_path

    def _generar_cierre_pdf(self) -> str:
        """Crea el PDF de cierre usando reportlab y devuelve la ruta temporal."""
        import tempfile, os, sqlite3
        from datetime import datetime

        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.units import cm
            from reportlab.lib import colors
            from reportlab.platypus import (
                SimpleDocTemplate, Table, TableStyle, Paragraph,
                Spacer, HRFlowable
            )
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
        except ImportError:
            raise RuntimeError(
                "Falta la librería 'reportlab'.\n"
                "Instálala con:  pip install reportlab"
            )

        vv = self.vv
        fecha_desde, fecha_hasta = vv._fecha_limite()
        etiqueta = vv._etiqueta_periodo()
        filtro   = vv.filtro_var.get()
        texto    = vv.buscador.get().strip().lower()

        # ── Obtener ventas ────────────────────────────────────────────────
        conn = sqlite3.connect(db.DB_PATH)
        conn.row_factory = sqlite3.Row
        ventas_raw = conn.execute(
            "SELECT * FROM ventas ORDER BY fecha ASC"
        ).fetchall()
        conn.close()

        def en_periodo(v):
            d = v["fecha"][:10]
            if fecha_desde and d < fecha_desde:
                return False
            if fecha_hasta and d > fecha_hasta:
                return False
            return True

        ventas = []
        for v in ventas_raw:
            if texto and texto not in v["cliente"].lower():
                continue
            if filtro != "todas" and v["tipo"] != filtro:
                continue
            if not en_periodo(v):
                continue
            ventas.append(v)

        # ── Totales ───────────────────────────────────────────────────────
        total_ventas  = len(ventas)
        total_monto   = sum(v["total"]  for v in ventas)
        total_cobrado = sum(v["pagado"] for v in ventas)
        total_pendiente = total_monto - total_cobrado
        contado_cnt   = sum(1 for v in ventas if v["tipo"] == "contado")
        abono_cnt     = sum(1 for v in ventas if v["tipo"] == "abono")

        # ── Construir PDF ─────────────────────────────────────────────────
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf",
                                          prefix="cierre_")
        tmp.close()
        ruta = tmp.name

        doc = SimpleDocTemplate(
            ruta,
            pagesize=letter,
            leftMargin=2*cm, rightMargin=2*cm,
            topMargin=2*cm, bottomMargin=2*cm,
        )

        estilos = getSampleStyleSheet()
        st_titulo  = ParagraphStyle("titulo",  fontSize=20, fontName="Helvetica-Bold",
                                    spaceAfter=4, alignment=TA_CENTER)
        st_sub     = ParagraphStyle("sub",     fontSize=12, fontName="Helvetica",
                                    textColor=colors.HexColor("#555555"),
                                    spaceAfter=2, alignment=TA_CENTER)
        st_seccion = ParagraphStyle("seccion", fontSize=11, fontName="Helvetica-Bold",
                                    spaceBefore=14, spaceAfter=6)
        st_normal  = ParagraphStyle("normal",  fontSize=10, fontName="Helvetica",
                                    leading=14)
        st_derecha = ParagraphStyle("derecha", fontSize=10, fontName="Helvetica",
                                    alignment=TA_RIGHT)

        historia = []

        # Encabezado — mejor espaciado entre título y subtítulo
        historia.append(Spacer(1, 6))
        historia.append(Paragraph("CIERRE DE VENTAS", st_titulo))
        historia.append(Spacer(1, 8))
        historia.append(Paragraph(etiqueta, st_sub))
        historia.append(Spacer(1, 6))
        historia.append(Paragraph(
            f"Generado: {datetime.now().strftime('%d/%m/%Y  %H:%M')}",
            ParagraphStyle("gen", fontSize=9, textColor=colors.grey,
                           alignment=TA_CENTER, spaceAfter=10)
        ))
        historia.append(HRFlowable(width="100%", thickness=1.5,
                                   color=colors.HexColor("#6c8aff"), spaceAfter=16))

        # ── Resumen ───────────────────────────────────────────────────────
        historia.append(Paragraph("Resumen del período", st_seccion))

        resumen_data = [
            ["Concepto", "Valor"],
            ["Total de ventas",       str(total_ventas)],
            ["  · Contado",           str(contado_cnt)],
            ["  · Abono/crédito",     str(abono_cnt)],
            ["Monto total facturado", f"${total_monto:.2f}"],
            ["Cobrado",               f"${total_cobrado:.2f}"],
            ["Pendiente por cobrar",  f"${total_pendiente:.2f}"],
        ]

        AZUL = colors.HexColor("#6c8aff")
        FONDO_HDR = colors.HexColor("#1c2030")
        FONDO_ALT = colors.HexColor("#f5f7ff")

        t_resumen = Table(resumen_data, colWidths=["65%", "35%"])
        t_resumen.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (-1, 0), AZUL),
            ("TEXTCOLOR",    (0, 0), (-1, 0), colors.white),
            ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",     (0, 0), (-1, 0), 10),
            ("FONTSIZE",     (0, 1), (-1, -1), 10),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, FONDO_ALT]),
            ("ALIGN",        (1, 0), (1, -1), "RIGHT"),
            ("LEFTPADDING",  (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING",   (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
            ("GRID",         (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("FONTNAME",     (0, 4), (0, 6), "Helvetica-Bold"),
        ]))
        historia.append(t_resumen)

        # ── Detalle de ventas ─────────────────────────────────────────────
        if ventas:
            historia.append(Spacer(1, 14))
            historia.append(Paragraph("Detalle de ventas", st_seccion))

            cab = ["Folio", "Fecha", "Cliente", "Total", "Pagado", "Tipo"]
            filas = [cab]
            for v in ventas:
                filas.append([
                    f"#{v['id']}",
                    v["fecha"][:10],
                    v["cliente"],
                    f"${v['total']:.2f}",
                    f"${v['pagado']:.2f}",
                    v["tipo"].capitalize(),
                ])

            anchos = [1.2*cm, 2.6*cm, None, 2.2*cm, 2.2*cm, 2*cm]
            t_det = Table(filas, colWidths=anchos, repeatRows=1)
            t_det.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, 0), AZUL),
                ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
                ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE",      (0, 0), (-1, -1), 8),
                ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, FONDO_ALT]),
                ("ALIGN",         (3, 0), (4, -1), "RIGHT"),
                ("ALIGN",         (0, 0), (0, -1), "CENTER"),
                ("LEFTPADDING",   (0, 0), (-1, -1), 5),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
                ("TOPPADDING",    (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("GRID",          (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
            ]))
            historia.append(t_det)

        # Pie de página — branding
        historia.append(Spacer(1, 24))
        historia.append(HRFlowable(width="100%", thickness=0.5,
                                   color=colors.HexColor("#cccccc"), spaceAfter=8))
        historia.append(Paragraph(
            "Los Lichos",
            ParagraphStyle("pie_nombre", fontSize=11, fontName="Helvetica-Bold",
                           textColor=colors.HexColor("#6c8aff"), alignment=TA_CENTER,
                           spaceAfter=2)
        ))
        historia.append(Paragraph(
            "Tu mercancía sin membresía",
            ParagraphStyle("pie_slogan", fontSize=9, fontName="Helvetica",
                           textColor=colors.grey, alignment=TA_CENTER)
        ))

        doc.build(historia)
        return ruta

    def _imprimir(self):
        try:
            tkt.imprimir_pdf(self._get_pdf())
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo generar el cierre:\n{e}", parent=self)

    def _guardar_pdf(self):
        from datetime import datetime
        etiqueta = self.vv._etiqueta_periodo().replace(" ", "_").replace("/", "-")
        nombre   = f"cierre_{etiqueta}_{datetime.now().strftime('%Y%m%d')}.pdf"
        destino  = filedialog.asksaveasfilename(
            parent=self,
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")],
            initialfile=nombre,
            title="Guardar cierre como PDF"
        )
        if not destino:
            return
        try:
            shutil.copy2(self._get_pdf(), destino)  
            messagebox.showinfo("✔ Guardado", f"Cierre guardado en:\n{destino}", parent=self)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar:\n{e}", parent=self)