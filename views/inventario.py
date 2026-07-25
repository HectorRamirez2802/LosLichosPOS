import customtkinter as ctk
import database as db
from tkinter import messagebox

# ─── COLORES ──────────────────────────────────────────────────────────────────
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

# Categorías predefinidas (también usadas en tarjeta de stats)
CATEGORIAS_PREDEFINIDAS = {
    "🍎 Alimentos y despensa",
    "🍬 Dulceria",
    "🧴 Belleza y salud personal",
    "🍞 Panadería y repostería",
    "🧴 Salud y belleza",
    "🧼 Limpieza y hogar",
    "📺 Electrónica",
    "🔌 Línea blanca",
    "🛋 Muebles y decoración",
    "🍽 Cocina y hogar",
    "👕 Ropa y calzado",
    "🧸 Juguetes y temporada",
    "🐶 Mascotas",
    "🚗 Automotriz",
    "👶 Bebés",
    "💍 Joyería y relojes",
    "🌳 Jardín y exterior",
    "🏋 Deportes y ejercicio",
    "👓 Óptica",
    "📝 Papelería",          # ← NUEVA
    "🍺 Bebidas y licores",  # ← NUEVA
    "📦 Otros",
}

# Orden fijo tal como lo pidió el usuario
CATEGORIAS_LISTA = [
    "🍎 Alimentos y despensa",
    "🍬 Dulceria",    
    "🧴 Belleza y salud personal",
    "🍞 Panadería y repostería",
    "🧴 Salud y belleza",
    "🧼 Limpieza y hogar",
    "📺 Electrónica",
    "🔌 Línea blanca",
    "🛋 Muebles y decoración",
    "🍽 Cocina y hogar",
    "👕 Ropa y calzado",
    "🧸 Juguetes y temporada",
    "🐶 Mascotas",
    "🚗 Automotriz",
    "👶 Bebés",
    "💍 Joyería y relojes",
    "🌳 Jardín y exterior",
    "🏋 Deportes y ejercicio",
    "👓 Óptica",
    "📝 Papelería",          # ← NUEVA
    "🍺 Bebidas y licores",  # ← NUEVA
    "📦 Otros",
]

# ─── FORMULARIO PRODUCTO (ventana emergente) ──────────────────────────────────
class FormularioProducto(ctk.CTkToplevel):
    def __init__(self, parent, on_guardar, producto=None):
        super().__init__(parent)
        self.on_guardar = on_guardar
        self.producto   = producto
        self.es_edicion = producto is not None

        self.title("Editar producto" if self.es_edicion else "Nuevo producto")
        self.geometry("480x580")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        self.grab_set()
        self.lift()
        self.focus_force()

        self._build()
        if self.es_edicion:
            self._prellenar()

    def _campo(self, parent, label, row, placeholder=""):
        ctk.CTkLabel(
            parent, text=label,
            font=ctk.CTkFont(size=12),
            text_color=C["muted"]
        ).grid(row=row, column=0, sticky="w", pady=(12, 2), padx=24)
        entry = ctk.CTkEntry(
            parent,
            placeholder_text=placeholder,
            height=38,
            fg_color=C["surface2"],
            border_color=C["border"],
            text_color=C["text"],
            font=ctk.CTkFont(size=13),
        )
        entry.grid(row=row + 1, column=0, sticky="ew", padx=24)
        return entry

    def _campo_categoria(self, row):
        """Entry de categoría con dropdown flotante via place() — no mueve la interfaz."""
        import tkinter as tk

        ctk.CTkLabel(
            self, text="Categoría",
            font=ctk.CTkFont(size=12),
            text_color=C["muted"]
        ).grid(row=row, column=0, sticky="w", pady=(12, 2), padx=24)

        entry = ctk.CTkEntry(
            self,
            placeholder_text="Escribe o elige una categoría...",
            height=38,
            fg_color=C["surface2"],
            border_color=C["border"],
            text_color=C["text"],
            font=ctk.CTkFont(size=13),
        )
        entry.grid(row=row + 1, column=0, sticky="ew", padx=24)

        # Dropdown flotante: hijo de self (el CTkToplevel), posicionado con place()
        # Al ser hijo de la misma ventana NO genera una ventana nueva y NO
        # afecta el layout de grid porque place() es independiente de grid.
        dd_frame = tk.Frame(self, bg=C["border"], bd=0)

        lb = tk.Listbox(
            dd_frame,
            bg=C["surface2"],
            fg=C["text"],
            selectbackground=C["accent"],
            selectforeground="#ffffff",
            font=("Segoe UI", 12),
            borderwidth=0,
            highlightthickness=0,
            activestyle="none",
            relief="flat",
            height=7,
            exportselection=False,
        )
        lb.pack(fill="both", expand=True, padx=1, pady=1)

        dd_visible = {"v": False}

        def _posicionar():
            """Calcula coordenadas del entry relativas a self y coloca dd_frame."""
            entry.update_idletasks()
            # Posición del entry relativa a la ventana (self)
            ex = entry.winfo_x() + 24   # mismo padx=24 del grid
            ey = entry.winfo_y() + entry.winfo_height() + 2
            ew = entry.winfo_width()
            dd_frame.place(x=ex, y=ey, width=ew)
            dd_frame.lift()

        def poblar(opciones):
            lb.delete(0, "end")
            for op in opciones:
                lb.insert("end", op)

        def mostrar(opciones):
            poblar(opciones)
            _posicionar()
            dd_visible["v"] = True

        def ocultar():
            if dd_visible["v"]:
                dd_frame.place_forget()
                dd_visible["v"] = False

        def elegir(event=None):
            sel = lb.curselection()
            if sel:
                entry.delete(0, "end")
                entry.insert(0, lb.get(sel[0]))
            ocultar()
            entry.focus_set()

        def al_escribir(event):
            if event.keysym in ("Up", "Down", "Return", "Escape"):
                return
            texto = entry.get().strip().lower()
            filtradas = [c for c in CATEGORIAS_LISTA if texto in c.lower()] if texto else CATEGORIAS_LISTA
            mostrar(filtradas)

        def al_enfocar(event):
            mostrar(CATEGORIAS_LISTA)

        def navegar(event):
            if not dd_visible["v"]:
                return
            size = lb.size()
            if size == 0:
                return
            sel = lb.curselection()
            if event.keysym == "Down":
                nuevo = (sel[0] + 1) if sel else 0
                nuevo = min(nuevo, size - 1)
            else:
                nuevo = (sel[0] - 1) if sel else size - 1
                nuevo = max(nuevo, 0)
            lb.selection_clear(0, "end")
            lb.selection_set(nuevo)
            lb.see(nuevo)

        def confirmar(event):
            if dd_visible["v"]:
                elegir()

        entry.bind("<FocusIn>",      al_enfocar)
        entry.bind("<KeyRelease>",   al_escribir)
        entry.bind("<Down>",         navegar)
        entry.bind("<Up>",           navegar)
        entry.bind("<Return>",       confirmar)
        entry.bind("<Escape>",       lambda e: ocultar())

        lb.bind("<ButtonRelease-1>", elegir)
        lb.bind("<Return>",          elegir)

        def clic_global(event):
            # Si el formulario ya fue destruido, no hacer nada
            try:
                if not dd_frame.winfo_exists():
                    return
            except Exception:
                return
            w = event.widget
            entry_inner = str(entry._entry) if hasattr(entry, "_entry") else ""
            if (w is lb or
                str(w) == entry_inner or
                str(w).startswith(str(dd_frame))):
                return
            ocultar()

        # Guardar el id del binding para poder eliminarlo al cerrar
        _bid = self.bind_all("<Button-1>", clic_global, add=True)

        def _limpiar(event=None):
            try:
                self.unbind_all("<Button-1>")
            except Exception:
                pass

        self.bind("<Destroy>", _limpiar)

        return entry

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self,
            text="Editar producto" if self.es_edicion else "Nuevo producto",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color=C["text"]
        ).grid(row=0, column=0, pady=(24, 0), padx=24, sticky="w")

        self.e_codigo    = self._campo(self, "Código de barras *", 1, "Ej: 7501234567890")
        self.e_nombre    = self._campo(self, "Nombre del producto *", 3, "Ej: Coca-Cola 600ml")
        self.e_categoria = self._campo_categoria(5)

        num_frame = ctk.CTkFrame(self, fg_color="transparent")
        num_frame.grid(row=8, column=0, sticky="ew", padx=24, pady=(12, 0))
        num_frame.grid_columnconfigure((0, 1, 2), weight=1)

        def num_campo(parent, label, col):
            ctk.CTkLabel(
                parent, text=label,
                font=ctk.CTkFont(size=12),
                text_color=C["muted"]
            ).grid(row=0, column=col, sticky="w", padx=(0 if col == 0 else 8, 0))
            e = ctk.CTkEntry(
                parent, height=38,
                fg_color=C["surface2"],
                border_color=C["border"],
                text_color=C["text"],
                font=ctk.CTkFont(size=13),
            )
            e.grid(row=1, column=col, sticky="ew", padx=(0 if col == 0 else 8, 0))
            return e

        self.e_precio       = num_campo(num_frame, "Precio de venta *", 0)
        self.e_costo        = num_campo(num_frame, "Costo", 1)
        self.e_stock        = num_campo(num_frame, "Stock actual *", 2)
        self.e_stock_minimo = self._campo(self, "Stock mínimo (alerta)", 9, "5")

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=11, column=0, sticky="ew", padx=24, pady=(20, 24))
        btn_frame.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            btn_frame, text="Cancelar", height=40,
            fg_color=C["surface2"], hover_color=C["surface"],
            text_color=C["text"], font=ctk.CTkFont(size=13),
            command=self.destroy
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(
            btn_frame, text="Guardar", height=40,
            fg_color=C["accent"], hover_color="#8ba3ff",
            text_color="#ffffff", font=ctk.CTkFont(size=13, weight="bold"),
            command=self._guardar
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

    def _prellenar(self):
        p = self.producto
        self.e_codigo.insert(0, p["codigo_barras"])
        self.e_nombre.insert(0, p["nombre"])
        self.e_categoria.insert(0, p["categoria"] or "")
        self.e_precio.insert(0, str(p["precio"]))
        self.e_costo.insert(0, str(p["costo"] or 0))
        self.e_stock.insert(0, str(p["stock"]))
        self.e_stock_minimo.insert(0, str(p["stock_minimo"] or 5))

    def _guardar(self):
        codigo = self.e_codigo.get().strip()
        nombre = self.e_nombre.get().strip()
        precio = self.e_precio.get().strip()
        stock  = self.e_stock.get().strip()

        if not codigo or not nombre or not precio or not stock:
            messagebox.showerror("Error", "Completa los campos obligatorios (*)", parent=self)
            return

        try:
            precio_f       = float(precio)
            costo_f        = float(self.e_costo.get().strip() or 0)
            stock_i        = int(stock)
            stock_minimo_i = int(self.e_stock_minimo.get().strip() or 5)
        except ValueError:
            messagebox.showerror("Error", "Precio, costo y stock deben ser números", parent=self)
            return

        datos = {
            "codigo_barras": codigo,
            "nombre":        nombre,
            "categoria":     self.e_categoria.get().strip(),
            "precio":        precio_f,
            "costo":         costo_f,
            "stock":         stock_i,
            "stock_minimo":  stock_minimo_i,
        }
        self.on_guardar(datos, self.producto["id"] if self.es_edicion else None)
        self.destroy()


# ─── VISTA PRINCIPAL DE INVENTARIO ───────────────────────────────────────────

class InventarioView(ctk.CTkFrame):
    """Inventario optimizado con ttk.Treeview.

    CustomTkinter se conserva para tarjetas, buscador y formularios; la tabla
    pesada se renderiza con Treeview para evitar cientos de widgets por fila.
    """
    PAGE_SIZE = 250

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._productos_after_id = None
        self._pagina = 0
        self._total_resultados = 0
        self._productos_by_id = {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._build_stats()
        self._build_toolbar()
        self._build_tabla()
        self.cargar_productos()

    def on_show(self):
        self.cargar_productos(mantener_pagina=True)

    # ── ESTADÍSTICAS ──────────────────────────────────────────────────────
    def _build_stats(self):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.stat_total = self._stat_card(frame, "Total productos", "—", C["accent"], 0)
        self.stat_sin   = self._stat_card(frame, "Sin stock",       "—", C["red"],    1)
        self.stat_bajo  = self._stat_card(frame, "Stock bajo",      "—", C["yellow"], 2)
        self.stat_cats  = self._stat_card(frame, "Categorías",      "—", C["text"],   3)

    def _stat_card(self, parent, label, valor, color, col):
        card = ctk.CTkFrame(parent, fg_color=C["surface"], corner_radius=12)
        card.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 10, 0))
        card.grid_propagate(False)
        card.configure(height=84)
        ctk.CTkLabel(card, text=label, font=ctk.CTkFont(size=11),
                     text_color=C["muted"]).place(x=16, y=12)
        lbl = ctk.CTkLabel(card, text=valor,
                           font=ctk.CTkFont(size=25, weight="bold"),
                           text_color=color)
        lbl.place(x=16, y=42)
        return lbl

    # ── FILTROS / ACCIONES ─────────────────────────────────────────────────
    def _build_toolbar(self):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        frame.grid_columnconfigure(0, weight=1)

        self.buscador = ctk.CTkEntry(
            frame,
            placeholder_text="🔍  Buscar por nombre o código de barras...",
            height=40,
            fg_color=C["surface"],
            border_color=C["border"],
            text_color=C["text"],
            font=ctk.CTkFont(size=13),
        )
        self.buscador.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.buscador.bind("<KeyRelease>", self._programar_cargar_productos)
        self.buscador.bind("<Return>", lambda e: self.cargar_productos(reset_pagina=True))

        ctk.CTkButton(
            frame, text="＋  Nuevo", height=40, width=110,
            fg_color=C["accent"], hover_color="#8ba3ff",
            text_color="#ffffff", font=ctk.CTkFont(size=13, weight="bold"),
            command=self._abrir_formulario_nuevo
        ).grid(row=0, column=1, padx=(0, 8))

        ctk.CTkButton(
            frame, text="✏  Editar", height=40, width=100,
            fg_color=C["surface2"], hover_color=C["surface"],
            text_color=C["muted"], font=ctk.CTkFont(size=13),
            command=self._editar_seleccionado
        ).grid(row=0, column=2, padx=(0, 8))

        ctk.CTkButton(
            frame, text="🗑  Eliminar", height=40, width=110,
            fg_color="#2a1520", hover_color="#3d1f2a",
            text_color=C["red"], font=ctk.CTkFont(size=13),
            command=self._eliminar_seleccionado
        ).grid(row=0, column=3, padx=(0, 8))

        ctk.CTkButton(
            frame, text="🖨  Cierre de mes", height=40, width=140,
            fg_color=C["surface2"], hover_color=C["surface"],
            text_color=C["muted"], font=ctk.CTkFont(size=13),
            corner_radius=8,
            command=self._abrir_cierre_mes
        ).grid(row=0, column=4)

    # ── TREEVIEW ────────────────────────────────────────────────────────────
    def _setup_tree_style(self):
        import tkinter as tk
        from tkinter import ttk
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Lichos.Treeview",
            background=C["surface"], foreground=C["text"],
            fieldbackground=C["surface"], bordercolor=C["border"],
            rowheight=32, font=("Segoe UI", 10), borderwidth=0,
        )
        style.configure(
            "Lichos.Treeview.Heading",
            background=C["surface2"], foreground=C["muted"],
            relief="flat", font=("Segoe UI", 10, "bold"),
        )
        style.map(
            "Lichos.Treeview",
            background=[("selected", C["accent"])],
            foreground=[("selected", "#ffffff")],
        )

    def _build_tabla(self):
        import tkinter as tk
        from tkinter import ttk
        self._setup_tree_style()

        cont = ctk.CTkFrame(self, fg_color=C["surface"], corner_radius=10)
        cont.grid(row=2, column=0, sticky="nsew")
        cont.grid_rowconfigure(0, weight=1)
        cont.grid_columnconfigure(0, weight=1)

        columnas = ("codigo", "nombre", "categoria", "costo", "precio", "stock")
        self.tabla = ttk.Treeview(
            cont, columns=columnas, show="headings", selectmode="browse",
            style="Lichos.Treeview"
        )
        self.tabla.grid(row=0, column=0, sticky="nsew", padx=(1, 0), pady=1)

        vsb = ttk.Scrollbar(cont, orient="vertical", command=self.tabla.yview)
        vsb.grid(row=0, column=1, sticky="ns", pady=1)
        hsb = ttk.Scrollbar(cont, orient="horizontal", command=self.tabla.xview)
        hsb.grid(row=1, column=0, sticky="ew", padx=1)
        self.tabla.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        headers = {
            "codigo": "Código",
            "nombre": "Nombre",
            "categoria": "Categoría",
            "costo": "Costo",
            "precio": "Precio",
            "stock": "Stock",
        }
        widths = {"codigo": 140, "nombre": 280, "categoria": 210, "costo": 95, "precio": 95, "stock": 90}
        anchors = {"codigo": "w", "nombre": "w", "categoria": "w", "costo": "e", "precio": "e", "stock": "center"}
        for col in columnas:
            self.tabla.heading(col, text=headers[col], anchor="w")
            self.tabla.column(col, width=widths[col], minwidth=70, anchor=anchors[col], stretch=(col in ("nombre", "categoria")))

        self.tabla.tag_configure("even", background=C["surface"])
        self.tabla.tag_configure("odd", background=C["surface2"])
        self.tabla.tag_configure("sin_stock", foreground=C["red"])
        self.tabla.tag_configure("stock_bajo", foreground=C["yellow"])
        self.tabla.tag_configure("stock_ok", foreground=C["text"])

        self.tabla.bind("<Double-1>", lambda e: self._editar_seleccionado())
        self.tabla.bind("<Return>", lambda e: self._editar_seleccionado())
        self.tabla.bind("<Delete>", lambda e: self._eliminar_seleccionado())

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        footer.grid_columnconfigure(1, weight=1)

        self.btn_prev = ctk.CTkButton(
            footer, text="← Anterior", width=110, height=32,
            fg_color=C["surface2"], hover_color=C["surface"],
            text_color=C["muted"], command=self._pagina_anterior
        )
        self.btn_prev.grid(row=0, column=0, sticky="w")

        self.lbl_pagina = ctk.CTkLabel(
            footer, text="", font=ctk.CTkFont(size=12), text_color=C["muted"]
        )
        self.lbl_pagina.grid(row=0, column=1)

        self.btn_next = ctk.CTkButton(
            footer, text="Siguiente →", width=110, height=32,
            fg_color=C["surface2"], hover_color=C["surface"],
            text_color=C["muted"], command=self._pagina_siguiente
        )
        self.btn_next.grid(row=0, column=2, sticky="e")

    # ── CARGA DE DATOS ──────────────────────────────────────────────────────
    def _programar_cargar_productos(self, _event=None):
        if self._productos_after_id:
            try:
                self.after_cancel(self._productos_after_id)
            except Exception:
                pass
        self._productos_after_id = self.after(180, lambda: self.cargar_productos(reset_pagina=True))

    def _query_productos(self, texto, limite, offset):
        texto = (texto or "").strip().lower()
        conn = db.get_connection()
        try:
            if texto:
                like = f"%{texto}%"
                params = [like, like]
                total = conn.execute("""
                    SELECT COUNT(*) AS n
                    FROM productos
                    WHERE activo = 1
                      AND (LOWER(nombre) LIKE ? OR LOWER(codigo_barras) LIKE ?)
                """, params).fetchone()["n"]
                rows = conn.execute("""
                    SELECT * FROM productos
                    WHERE activo = 1
                      AND (LOWER(nombre) LIKE ? OR LOWER(codigo_barras) LIKE ?)
                    ORDER BY
                      CASE WHEN LOWER(codigo_barras) = ? THEN 0
                           WHEN LOWER(nombre) LIKE ? THEN 1
                           ELSE 2 END,
                      nombre ASC
                    LIMIT ? OFFSET ?
                """, [like, like, texto, f"{texto}%", int(limite), int(offset)]).fetchall()
            else:
                total = conn.execute("SELECT COUNT(*) AS n FROM productos WHERE activo = 1").fetchone()["n"]
                rows = conn.execute("""
                    SELECT * FROM productos
                    WHERE activo = 1
                    ORDER BY nombre ASC
                    LIMIT ? OFFSET ?
                """, (int(limite), int(offset))).fetchall()
        finally:
            conn.close()
        return total, rows

    def _actualizar_stats(self):
        try:
            resumen = db.resumen_productos()
            self.stat_total.configure(text=str(resumen["total"] or 0))
            self.stat_sin.configure(text=str(resumen["sin_stock"] or 0))
            self.stat_bajo.configure(text=str(resumen["stock_bajo"] or 0))
            self.stat_cats.configure(text=str(resumen["categorias"] or 0))
        except Exception:
            pass

    def cargar_productos(self, reset_pagina=False, mantener_pagina=False):
        self._productos_after_id = None
        if not hasattr(self, "tabla") or not self.tabla.winfo_exists():
            return
        if reset_pagina:
            self._pagina = 0

        selected = self.tabla.selection()[0] if self.tabla.selection() else None
        texto = self.buscador.get().strip()
        offset = self._pagina * self.PAGE_SIZE
        total, productos = self._query_productos(texto, self.PAGE_SIZE, offset)
        if offset >= total and self._pagina > 0:
            self._pagina = max(0, (max(total, 1) - 1) // self.PAGE_SIZE)
            total, productos = self._query_productos(texto, self.PAGE_SIZE, self._pagina * self.PAGE_SIZE)

        self._total_resultados = total
        self._productos_by_id = {}
        self.tabla.delete(*self.tabla.get_children())

        for i, p in enumerate(productos):
            prod = dict(p)
            iid = str(prod["id"])
            self._productos_by_id[iid] = prod
            stock = int(prod.get("stock") or 0)
            minimo = int(prod.get("stock_minimo") or 0)
            if stock == 0:
                stock_txt = f"{stock} ⚠"
                stock_tag = "sin_stock"
            elif stock <= minimo:
                stock_txt = f"{stock} ↓"
                stock_tag = "stock_bajo"
            else:
                stock_txt = str(stock)
                stock_tag = "stock_ok"
            self.tabla.insert(
                "", "end", iid=iid,
                values=(
                    prod.get("codigo_barras", ""),
                    prod.get("nombre", ""),
                    prod.get("categoria") or "—",
                    f"${float(prod.get('costo') or 0):.2f}",
                    f"${float(prod.get('precio') or 0):.2f}",
                    stock_txt,
                ),
                tags=("even" if i % 2 == 0 else "odd", stock_tag)
            )

        if selected and selected in self._productos_by_id:
            self.tabla.selection_set(selected)
            self.tabla.focus(selected)
        elif productos:
            first = str(dict(productos[0])["id"])
            self.tabla.selection_set(first)
            self.tabla.focus(first)

        self._actualizar_stats()
        self._actualizar_paginacion()

    def _actualizar_paginacion(self):
        total_paginas = max(1, (self._total_resultados + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        self.lbl_pagina.configure(
            text=f"Página {self._pagina + 1} de {total_paginas}  ·  {self._total_resultados} producto(s)"
        )
        estado_prev = "normal" if self._pagina > 0 else "disabled"
        estado_next = "normal" if (self._pagina + 1) < total_paginas else "disabled"
        self.btn_prev.configure(state=estado_prev, text_color=C["muted"] if estado_prev == "normal" else C["border"])
        self.btn_next.configure(state=estado_next, text_color=C["muted"] if estado_next == "normal" else C["border"])

    def _pagina_anterior(self):
        if self._pagina > 0:
            self._pagina -= 1
            self.cargar_productos()

    def _pagina_siguiente(self):
        total_paginas = max(1, (self._total_resultados + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        if (self._pagina + 1) < total_paginas:
            self._pagina += 1
            self.cargar_productos()

    # ── ACCIONES ────────────────────────────────────────────────────────────
    def _producto_seleccionado(self):
        sel = self.tabla.selection() if hasattr(self, "tabla") else ()
        if not sel:
            messagebox.showinfo("Selecciona un producto", "Selecciona un producto de la tabla primero.")
            return None
        return self._productos_by_id.get(sel[0])

    def _abrir_cierre_mes(self):
        CierreInventarioDialog(self)

    def _abrir_formulario_nuevo(self):
        FormularioProducto(self, on_guardar=self._guardar_producto)

    def _abrir_formulario_editar(self, producto):
        if producto:
            FormularioProducto(self, on_guardar=self._guardar_producto, producto=producto)

    def _editar_seleccionado(self):
        self._abrir_formulario_editar(self._producto_seleccionado())

    def _guardar_producto(self, datos, producto_id=None):
        if producto_id is None:
            ok = db.agregar_producto(
                codigo_barras=datos["codigo_barras"],
                nombre=datos["nombre"],
                precio=datos["precio"],
                costo=datos["costo"],
                stock=datos["stock"],
                categoria=datos["categoria"],
                stock_minimo=datos["stock_minimo"],
            )
            if not ok:
                messagebox.showerror("Error", "Ya existe un producto con ese código de barras.")
                return
        else:
            db.actualizar_producto(
                id=producto_id,
                codigo_barras=datos["codigo_barras"],
                nombre=datos["nombre"],
                precio=datos["precio"],
                costo=datos["costo"],
                stock=datos["stock"],
                categoria=datos["categoria"],
                stock_minimo=datos["stock_minimo"],
            )
        self.cargar_productos(mantener_pagina=True)

    def _eliminar_seleccionado(self):
        producto = self._producto_seleccionado()
        if producto:
            self._eliminar(producto)

    def _eliminar(self, producto):
        confirmar = messagebox.askyesno(
            "Confirmar",
            f"¿Eliminar '{producto['nombre']}'?\n\nEl historial de ventas se conserva.",
        )
        if confirmar:
            db.desactivar_producto(producto["id"])
            self.cargar_productos(mantener_pagina=True)

# ─── DIÁLOGO CIERRE DE INVENTARIO (CIERRE DE MES) ────────────────────────────
class CierreInventarioDialog(ctk.CTkToplevel):
    """
    Permite elegir el mes/año y genera un PDF de cierre de inventario con la tabla:
      Producto | Stock inicial | Venta | Stock final
    El pie de página muestra "Los Lichos" y "Tu mercancía sin membresía".
    """

    MESES = [
        "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
    ]

    def __init__(self, parent):
        super().__init__(parent)
        from datetime import datetime
        self._ahora = datetime.now()
        self._pdf_path = None

        self.title("Cierre de inventario — mes")
        self.geometry("400x310")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        self.grab_set()
        self.lift()
        self.focus_force()
        self._build()

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self, text="📦  Cierre de inventario",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=C["text"]
        ).grid(row=0, column=0, padx=24, pady=(22, 4), sticky="w")

        ctk.CTkLabel(
            self, text="Selecciona el mes y año para generar el reporte.",
            font=ctk.CTkFont(size=11), text_color=C["muted"]
        ).grid(row=1, column=0, padx=24, pady=(0, 18), sticky="w")

        # ── Selectores ──────────────────────────────────────────────────────
        sel_frame = ctk.CTkFrame(self, fg_color="transparent")
        sel_frame.grid(row=2, column=0, padx=24, sticky="ew")
        sel_frame.grid_columnconfigure((0, 1), weight=1)

        # Mes
        ctk.CTkLabel(sel_frame, text="Mes", font=ctk.CTkFont(size=12),
                     text_color=C["muted"]).grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.combo_mes = ctk.CTkComboBox(
            sel_frame,
            values=self.MESES,
            height=36,
            fg_color=C["surface2"], border_color=C["border"],
            button_color=C["accent"], button_hover_color="#8ba3ff",
            text_color=C["text"], font=ctk.CTkFont(size=13),
            state="readonly",
        )
        self.combo_mes.set(self.MESES[self._ahora.month - 1])
        self.combo_mes.grid(row=1, column=0, sticky="ew", padx=(0, 10))

        # Año
        anio_actual = self._ahora.year
        anios = [str(a) for a in range(anio_actual - 3, anio_actual + 1)]
        ctk.CTkLabel(sel_frame, text="Año", font=ctk.CTkFont(size=12),
                     text_color=C["muted"]).grid(row=0, column=1, sticky="w", pady=(0, 4))
        self.combo_anio = ctk.CTkComboBox(
            sel_frame,
            values=anios,
            height=36,
            fg_color=C["surface2"], border_color=C["border"],
            button_color=C["accent"], button_hover_color="#8ba3ff",
            text_color=C["text"], font=ctk.CTkFont(size=13),
            state="readonly",
        )
        self.combo_anio.set(str(anio_actual))
        self.combo_anio.grid(row=1, column=1, sticky="ew")

        # ── Botones ──────────────────────────────────────────────────────────
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=3, column=0, padx=24, pady=(18, 0), sticky="ew")
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
        ).grid(row=4, column=0, padx=24, pady=(10, 20), sticky="ew")

    # ── Generación del PDF ────────────────────────────────────────────────────
    def _mes_anio(self):
        mes  = self.MESES.index(self.combo_mes.get()) + 1
        anio = int(self.combo_anio.get())
        return mes, anio

    def _get_pdf(self) -> str:
        """Genera (o reutiliza) el PDF y devuelve su ruta."""
        # Regenerar siempre por si cambiaron los selectors
        self._pdf_path = self._generar_pdf()
        return self._pdf_path

    def _generar_pdf(self) -> str:
        import tempfile, calendar
        from datetime import datetime

        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.units import cm
            from reportlab.lib import colors
            from reportlab.platypus import (
                SimpleDocTemplate, Table, TableStyle,
                Paragraph, Spacer, HRFlowable
            )
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.enums import TA_CENTER, TA_RIGHT
        except ImportError:
            raise RuntimeError(
                "Falta la librería 'reportlab'.\n"
                "Instálala con:  pip install reportlab"
            )

        mes, anio = self._mes_anio()
        nombre_mes = self.MESES[mes - 1]
        etiqueta   = f"{nombre_mes} {anio}"

        # ── Datos desde la BD ────────────────────────────────────────────────
        filas_datos = db.ventas_por_producto_en_mes(anio, mes)

        # ── Archivo temporal ─────────────────────────────────────────────────
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf",
                                          prefix="cierre_inv_")
        tmp.close()
        ruta = tmp.name

        PAGE_W, PAGE_H = letter
        MARGEN = 2 * cm

        # ── Estilos ──────────────────────────────────────────────────────────
        AZUL       = colors.HexColor("#6c8aff")
        FONDO_ALT  = colors.HexColor("#f5f7ff")
        GRIS_LINE  = colors.HexColor("#cccccc")
        GRIS_TEXT  = colors.HexColor("#555555")
        PIE_AZUL   = colors.HexColor("#6c8aff")

        st_titulo = ParagraphStyle(
            "titulo", fontSize=18, fontName="Helvetica-Bold",
            alignment=TA_CENTER, spaceAfter=6
        )
        st_sub = ParagraphStyle(
            "sub", fontSize=12, fontName="Helvetica",
            textColor=GRIS_TEXT, alignment=TA_CENTER, spaceAfter=2
        )
        st_gen = ParagraphStyle(
            "gen", fontSize=9, fontName="Helvetica",
            textColor=colors.grey, alignment=TA_CENTER, spaceAfter=12
        )
        st_pie_nombre = ParagraphStyle(
            "pie_nombre", fontSize=11, fontName="Helvetica-Bold",
            textColor=PIE_AZUL, alignment=TA_CENTER, spaceAfter=2
        )
        st_pie_slogan = ParagraphStyle(
            "pie_slogan", fontSize=9, fontName="Helvetica",
            textColor=colors.grey, alignment=TA_CENTER
        )

        # ── Ancho útil de la tabla ───────────────────────────────────────────
        ancho_util = PAGE_W - 2 * MARGEN
        # Proporciones: Producto 50%, Stock inicial 17%, Venta 16%, Stock final 17%
        col_widths = [
            ancho_util * 0.50,
            ancho_util * 0.17,
            ancho_util * 0.16,
            ancho_util * 0.17,
        ]

        # ── Cabecera de la tabla ─────────────────────────────────────────────
        cab = ["Producto", "Stock inicial", "Venta", "Stock final"]
        tabla_data = [cab]

        total_inicial = 0
        total_vendido = 0
        total_final   = 0

        for f in filas_datos:
            tabla_data.append([
                f["nombre"],
                str(f["stock_inicial"]),
                str(f["vendido"]),
                str(f["stock_final"]),
            ])
            total_inicial += f["stock_inicial"]
            total_vendido += f["vendido"]
            total_final   += f["stock_final"]

        # Fila de totales
        tabla_data.append([
            "TOTAL",
            str(total_inicial),
            str(total_vendido),
            str(total_final),
        ])

        tabla = Table(tabla_data, colWidths=col_widths, repeatRows=1)
        n_filas = len(tabla_data)
        tabla.setStyle(TableStyle([
            # Encabezado
            ("BACKGROUND",    (0, 0), (-1, 0), AZUL),
            ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
            ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, 0), 10),
            ("ALIGN",         (0, 0), (-1, 0), "CENTER"),
            # Filas de datos
            ("FONTNAME",      (0, 1), (-1, n_filas - 2), "Helvetica"),
            ("FONTSIZE",      (0, 1), (-1, n_filas - 2), 9),
            ("ROWBACKGROUNDS",(0, 1), (-1, n_filas - 2), [colors.white, FONDO_ALT]),
            # Alineación de columnas numéricas
            ("ALIGN",         (1, 1), (-1, -1), "CENTER"),
            ("ALIGN",         (0, 1), (0, -1), "LEFT"),
            # Padding uniforme
            ("LEFTPADDING",   (0, 0), (-1, -1), 8),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            # Grilla
            ("GRID",          (0, 0), (-1, -1), 0.4, GRIS_LINE),
            # Fila de totales
            ("BACKGROUND",    (0, n_filas - 1), (-1, n_filas - 1), colors.HexColor("#e8ecff")),
            ("FONTNAME",      (0, n_filas - 1), (-1, n_filas - 1), "Helvetica-Bold"),
            ("FONTSIZE",      (0, n_filas - 1), (-1, n_filas - 1), 9),
            ("LINEABOVE",     (0, n_filas - 1), (-1, n_filas - 1), 1.0, AZUL),
        ]))

        # ── Historia del documento ───────────────────────────────────────────
        historia = []

        historia.append(Spacer(1, 6))
        historia.append(Paragraph("CIERRE DE INVENTARIO", st_titulo))
        historia.append(Spacer(1, 6))
        historia.append(Paragraph(etiqueta, st_sub))
        historia.append(Paragraph(
            f"Generado: {datetime.now().strftime('%d/%m/%Y  %H:%M')}",
            st_gen
        ))
        historia.append(HRFlowable(
            width="100%", thickness=1.5,
            color=AZUL, spaceAfter=14
        ))

        historia.append(tabla)

        # Pie de página (en el flujo, después de la tabla)
        historia.append(Spacer(1, 20))
        historia.append(HRFlowable(
            width="100%", thickness=0.5,
            color=GRIS_LINE, spaceAfter=8
        ))
        historia.append(Paragraph("Los Lichos", st_pie_nombre))
        historia.append(Paragraph("Tu mercancía sin membresía", st_pie_slogan))

        # ── Construir ────────────────────────────────────────────────────────
        doc = SimpleDocTemplate(
            ruta,
            pagesize=letter,
            leftMargin=MARGEN,
            rightMargin=MARGEN,
            topMargin=MARGEN,
            bottomMargin=MARGEN,
        )
        doc.build(historia)
        return ruta

    # ── Acciones ──────────────────────────────────────────────────────────────
    def _imprimir(self):
        try:
            from views import ticket as tkt
            tkt.imprimir_pdf(self._get_pdf())
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("Error", f"No se pudo generar el cierre:\n{e}", parent=self)

    def _guardar_pdf(self):
        from tkinter import messagebox, filedialog
        import shutil
        mes, anio = self._mes_anio()
        nombre_mes = self.MESES[mes - 1]
        nombre_archivo = f"cierre_inventario_{nombre_mes}_{anio}.pdf"
        destino = filedialog.asksaveasfilename(
            parent=self,
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")],
            initialfile=nombre_archivo,
            title="Guardar cierre de inventario"
        )
        if not destino:
            return
        try:
            shutil.copy2(self._get_pdf(), destino)
            messagebox.showinfo(
                "✔ Guardado",
                f"Cierre guardado en:\n{destino}",
                parent=self
            )
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar:\n{e}", parent=self)