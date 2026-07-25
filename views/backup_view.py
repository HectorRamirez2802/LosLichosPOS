"""
views/backup_view.py  —  Pantalla de Respaldos — Los Lichos
"""

import os
import customtkinter as ctk
from tkinter import messagebox, ttk
import backup   # backup.py en la raíz del proyecto

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

_BACKUP_USER = "licho"
_BACKUP_PASS = "loslichos2020"


class _LoginEliminarBackupDialog(ctk.CTkToplevel):
    """
    Candado de usuario/contraseña que protege la eliminación de backups.
    Llama a on_success() solo si las credenciales son correctas
    (mismas credenciales que dan acceso al módulo de Respaldos).
    """

    def __init__(self, parent, on_success):
        super().__init__(parent)
        self._on_success = on_success
        self._intentos = 0

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
            frame, text="Ingresa tus credenciales para\neliminar este backup",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=C["text"], justify="center"
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
            fg_color=C["red"], hover_color="#cc3333",
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


class BackupView(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Siempre arranca mostrando el login integrado.
        # En main.py optimizado los módulos quedan en caché, así que este módulo
        # también expone on_show() para volver a pedir login cada vez que se entra.
        self._panel_login = None
        self._panel_contenido = None
        self._mostrar_login()

    def on_show(self):
        """
        Se llama desde main.py cada vez que el usuario vuelve a abrir Respaldos.
        Por seguridad, se destruye cualquier sesión previa y se muestra login.
        """
        self._mostrar_login()

    # ══════════════════════════════════════════════════════════════════════════
    #  PANEL DE LOGIN INTEGRADO
    # ══════════════════════════════════════════════════════════════════════════
    def _mostrar_login(self):
        """Construye y muestra el formulario de login centrado en la vista."""
        # Si el módulo quedó en caché, eliminar cualquier contenido protegido.
        if self._panel_contenido and self._panel_contenido.winfo_exists():
            self._panel_contenido.grid_forget()
            self._panel_contenido.destroy()
        self._panel_contenido = None

        # Evitar duplicar formularios de login si on_show() se llama más de una vez.
        if self._panel_login and self._panel_login.winfo_exists():
            self._panel_login.grid_forget()
            self._panel_login.destroy()
        self._panel_login = None

        # Fondo completo que ocupa todo el frame
        self._panel_login = ctk.CTkFrame(self, fg_color="transparent")
        self._panel_login.grid(row=0, column=0, sticky="nsew")
        self._panel_login.grid_columnconfigure(0, weight=1)
        self._panel_login.grid_rowconfigure(0, weight=1)

        # Tarjeta centrada
        card = ctk.CTkFrame(
            self._panel_login,
            fg_color=C["surface"],
            corner_radius=20,
            width=360,
        )
        card.grid(row=0, column=0)
        card.grid_columnconfigure(0, weight=1)
        card.grid_propagate(False)
        card.configure(width=360, height=420)

        # Ícono / título
        ctk.CTkLabel(
            card, text="🔒",
            font=ctk.CTkFont(size=42),
        ).grid(row=0, column=0, pady=(38, 0))

        ctk.CTkLabel(
            card, text="Área protegida",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=C["text"]
        ).grid(row=1, column=0, pady=(8, 4))

        ctk.CTkLabel(
            card,
            text="Ingresa tus credenciales para\nacceder a los respaldos.",
            font=ctk.CTkFont(size=12),
            text_color=C["muted"],
            justify="center",
        ).grid(row=2, column=0, pady=(0, 28))

        # Separador superior del formulario
        ctk.CTkFrame(card, fg_color=C["border"], height=1).grid(
            row=3, column=0, sticky="ew", padx=32, pady=(0, 24)
        )

        # Campo usuario
        ctk.CTkLabel(card, text="Usuario", font=ctk.CTkFont(size=11),
                     text_color=C["muted"]).grid(
            row=4, column=0, sticky="w", padx=32, pady=(0, 4))
        self._entry_user = ctk.CTkEntry(
            card, height=40,
            placeholder_text="Usuario",
            fg_color=C["surface2"], border_color=C["border"],
            text_color=C["text"], font=ctk.CTkFont(size=13),
            corner_radius=10,
        )
        self._entry_user.grid(row=5, column=0, sticky="ew", padx=32)
        self._entry_user.focus_set()

        # Campo contraseña
        ctk.CTkLabel(card, text="Contraseña", font=ctk.CTkFont(size=11),
                     text_color=C["muted"]).grid(
            row=6, column=0, sticky="w", padx=32, pady=(14, 4))
        self._entry_pass = ctk.CTkEntry(
            card, height=40,
            placeholder_text="Contraseña",
            show="●",
            fg_color=C["surface2"], border_color=C["border"],
            text_color=C["text"], font=ctk.CTkFont(size=13),
            corner_radius=10,
        )
        self._entry_pass.grid(row=7, column=0, sticky="ew", padx=32)
        self._entry_pass.bind("<Return>", lambda e: self._verificar())

        # Mensaje de error (oculto inicialmente)
        self._lbl_error = ctk.CTkLabel(
            card, text="",
            font=ctk.CTkFont(size=11),
            text_color=C["red"],
        )
        self._lbl_error.grid(row=8, column=0, pady=(8, 0))

        # Botón ingresar
        ctk.CTkButton(
            card, text="Ingresar", height=42,
            fg_color=C["accent"], hover_color="#8ba3ff",
            text_color="#fff", font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=10,
            command=self._verificar
        ).grid(row=9, column=0, sticky="ew", padx=32, pady=(16, 32))

    # ── Verificación de credenciales ──────────────────────────────────────────
    def _verificar(self):
        usuario    = self._entry_user.get().strip()
        contrasena = self._entry_pass.get()

        if usuario == _BACKUP_USER and contrasena == _BACKUP_PASS:
            self._panel_login.grid_forget()
            self._panel_login.destroy()
            self._panel_login = None
            self._construir_contenido()
        else:
            # Resaltar campos en rojo + mensaje inline
            self._entry_user.configure(border_color=C["red"])
            self._entry_pass.configure(border_color=C["red"])
            self._entry_pass.delete(0, "end")
            self._lbl_error.configure(text="Usuario o contraseña incorrectos.")
            self.after(1800, self._limpiar_error)

    def _limpiar_error(self):
        # Puede ejecutarse después de que el usuario cambió de módulo y el login
        # fue destruido; por eso se valida que los widgets sigan existiendo.
        try:
            if getattr(self, "_entry_user", None) and self._entry_user.winfo_exists():
                self._entry_user.configure(border_color=C["border"])
            if getattr(self, "_entry_pass", None) and self._entry_pass.winfo_exists():
                self._entry_pass.configure(border_color=C["border"])
            if getattr(self, "_lbl_error", None) and self._lbl_error.winfo_exists():
                self._lbl_error.configure(text="")
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════════════
    #  CONTENIDO REAL (solo visible tras autenticarse)
    # ══════════════════════════════════════════════════════════════════════════
    def _construir_contenido(self):
        self._panel_contenido = ctk.CTkFrame(self, fg_color="transparent")
        self._panel_contenido.grid(row=0, column=0, sticky="nsew")
        self._panel_contenido.grid_columnconfigure(0, weight=1)
        self._panel_contenido.grid_rowconfigure(2, weight=1)

        self._build_acciones(self._panel_contenido)
        self._build_historial(self._panel_contenido)

    # ── TARJETAS DE ACCIÓN ────────────────────────────────────────────────────
    def _build_acciones(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        frame.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        acciones = [
            (
                "⬆  Exportar .db",
                "Guarda una copia de la\nbase de datos como archivo .db",
                C["accent"],
                self._exportar_db,
            ),
            (
                "📦  Exportar .zip",
                "Respaldo comprimido, ideal\npara enviar o archivar",
                C["yellow"],
                self._exportar_zip,
            ),
            (
                "⬇  Importar / Restaurar",
                "Reemplaza la BD con un\narchivo .db o .zip anterior",
                C["red"],
                self._importar,
            ),
            (
                "💾  Backup ahora",
                "Guarda una copia automática\nen la carpeta /backups/",
                C["green"],
                self._backup_ahora,
            ),
            (
                "☢  Formatear BD",
                "Borra todos los datos y\nrecrea las tablas vacías",
                "#6b2020",
                self._formatear,
            ),
        ]

        for col, (titulo, desc, color, cmd) in enumerate(acciones):
            card = ctk.CTkFrame(frame, fg_color=C["surface"], corner_radius=14)
            card.grid(row=0, column=col, sticky="ew",
                      padx=(0 if col == 0 else 10, 0))
            card.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(
                card, text=titulo,
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=color if color != "#6b2020" else C["red"]
            ).pack(anchor="w", padx=18, pady=(18, 4))

            ctk.CTkLabel(
                card, text=desc,
                font=ctk.CTkFont(size=11),
                text_color=C["muted"],
                justify="left"
            ).pack(anchor="w", padx=18, pady=(0, 12))

            btn_color  = color if color != "#6b2020" else C["red"]
            btn_text_c = "#0d0f14" if color in (C["green"], C["yellow"]) else "#fff"
            ctk.CTkButton(
                card, text="Ejecutar", height=34,
                fg_color=btn_color, hover_color=btn_color,
                text_color=btn_text_c,
                font=ctk.CTkFont(size=12, weight="bold"),
                corner_radius=8,
                command=cmd
            ).pack(fill="x", padx=18, pady=(0, 18))

    # ── HISTORIAL DE BACKUPS ──────────────────────────────────────────────────
    def _build_historial(self, parent):
        header_row = ctk.CTkFrame(parent, fg_color="transparent")
        header_row.grid(row=1, column=0, sticky="ew")
        header_row.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header_row,
            text="Backups automáticos guardados",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=C["text"]
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        ctk.CTkButton(
            header_row, text="↺  Actualizar", width=120, height=32,
            fg_color=C["surface2"], hover_color=C["border"],
            text_color=C["muted"], font=ctk.CTkFont(size=12),
            command=self._cargar_historial
        ).grid(row=0, column=1, sticky="e", pady=(0, 8))

        table_card = ctk.CTkFrame(parent, fg_color=C["surface"], corner_radius=10)
        table_card.grid(row=2, column=0, sticky="nsew")
        table_card.grid_columnconfigure(0, weight=1)
        table_card.grid_rowconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1)

        # ttk.Treeview es bastante más ligero que crear una fila completa con
        # varios widgets CustomTkinter por cada backup. Mantiene la vista rápida
        # aunque se acumulen muchos respaldos automáticos.
        self._style_backups_tree()

        columns = ("archivo", "fecha", "tamano")
        self.tree_backups = ttk.Treeview(
            table_card,
            columns=columns,
            show="headings",
            selectmode="browse",
            style="Backups.Treeview",
            height=12,
        )
        self.tree_backups.heading("archivo", text="Archivo", anchor="w")
        self.tree_backups.heading("fecha", text="Fecha", anchor="w")
        self.tree_backups.heading("tamano", text="Tamaño", anchor="e")

        self.tree_backups.column("archivo", width=460, minwidth=240, anchor="w", stretch=True)
        self.tree_backups.column("fecha", width=180, minwidth=140, anchor="w", stretch=False)
        self.tree_backups.column("tamano", width=110, minwidth=90, anchor="e", stretch=False)

        yscroll = ttk.Scrollbar(
            table_card,
            orient="vertical",
            command=self.tree_backups.yview,
            style="Backups.Vertical.TScrollbar",
        )
        self.tree_backups.configure(yscrollcommand=yscroll.set)
        self.tree_backups.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=10)
        yscroll.grid(row=0, column=1, sticky="ns", padx=(0, 10), pady=10)

        self.tree_backups.bind("<<TreeviewSelect>>", lambda e: self._actualizar_acciones_backup())
        self.tree_backups.bind("<Double-1>", lambda e: self._copiar_backup_seleccionado())

        acciones_row = ctk.CTkFrame(parent, fg_color="transparent")
        acciones_row.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        acciones_row.grid_columnconfigure(0, weight=1)

        self.lbl_backup_info = ctk.CTkLabel(
            acciones_row,
            text="Selecciona un backup para restaurarlo o copiarlo. Doble clic = copiar.",
            font=ctk.CTkFont(size=11),
            text_color=C["muted"],
        )
        self.lbl_backup_info.grid(row=0, column=0, sticky="w")

        btns = ctk.CTkFrame(acciones_row, fg_color="transparent")
        btns.grid(row=0, column=1, sticky="e")

        self.btn_restaurar_sel = ctk.CTkButton(
            btns, text="Restaurar seleccionado", height=32, width=160,
            fg_color=C["red"], hover_color="#cc3333",
            text_color="#fff", font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=8,
            state="disabled",
            command=self._restaurar_backup_seleccionado,
        )
        self.btn_restaurar_sel.pack(side="left", padx=(0, 8))

        self.btn_copiar_sel = ctk.CTkButton(
            btns, text="Copiar seleccionado", height=32, width=150,
            fg_color=C["surface2"], hover_color=C["border"],
            text_color=C["accent"], font=ctk.CTkFont(size=12),
            corner_radius=8,
            state="disabled",
            command=self._copiar_backup_seleccionado,
        )
        self.btn_copiar_sel.pack(side="left", padx=(8, 0))

        self.btn_eliminar_sel = ctk.CTkButton(
            btns, text="🗑  Eliminar seleccionado", height=32, width=170,
            fg_color=C["surface2"], hover_color="#4a1f1f",
            text_color=C["red"], font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=8,
            state="disabled",
            command=self._eliminar_backup_seleccionado,
        )
        self.btn_eliminar_sel.pack(side="left", padx=(8, 0))

        self._backups_por_item = {}
        self._cargar_historial()

    def _style_backups_tree(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(
            "Backups.Treeview",
            background=C["surface"],
            foreground=C["text"],
            fieldbackground=C["surface"],
            borderwidth=0,
            rowheight=32,
            font=("Segoe UI", 10),
        )
        style.configure(
            "Backups.Treeview.Heading",
            background=C["surface2"],
            foreground=C["muted"],
            relief="flat",
            font=("Segoe UI", 10, "bold"),
        )
        style.map(
            "Backups.Treeview",
            background=[("selected", C["accent"])],
            foreground=[("selected", "#ffffff")],
        )
        style.configure(
            "Backups.Vertical.TScrollbar",
            troughcolor=C["surface"],
            background=C["surface2"],
            bordercolor=C["surface"],
            arrowcolor=C["muted"],
            relief="flat",
        )

    def _cargar_historial(self):
        self._backups_por_item = {}
        for item in self.tree_backups.get_children():
            self.tree_backups.delete(item)

        backups = backup.listar_backups()

        if not backups:
            self.lbl_backup_info.configure(
                text="No hay backups automáticos todavía. Usa 'Backup ahora' o espera al cierre del sistema.",
                text_color=C["muted"],
            )
            self._actualizar_acciones_backup()
            return

        for i, b in enumerate(backups):
            tag = "par" if i % 2 == 0 else "impar"
            iid = self.tree_backups.insert(
                "",
                "end",
                values=(b["nombre"], b["fecha_str"], f"{b['tamaño_kb']} KB"),
                tags=(tag,),
            )
            self._backups_por_item[iid] = b

        self.tree_backups.tag_configure("par", background=C["surface"])
        self.tree_backups.tag_configure("impar", background=C["surface2"])
        self.lbl_backup_info.configure(
            text=f"{len(backups)} backup(s) encontrado(s). Selecciona uno para restaurar o copiar.",
            text_color=C["muted"],
        )
        self._actualizar_acciones_backup()

    def _backup_seleccionado(self):
        sel = self.tree_backups.selection()
        if not sel:
            return None
        return self._backups_por_item.get(sel[0])

    def _actualizar_acciones_backup(self):
        b = self._backup_seleccionado() if hasattr(self, "tree_backups") else None
        estado = "normal" if b else "disabled"
        if hasattr(self, "btn_restaurar_sel"):
            self.btn_restaurar_sel.configure(state=estado)
            self.btn_copiar_sel.configure(state=estado)
        if hasattr(self, "btn_eliminar_sel"):
            self.btn_eliminar_sel.configure(state=estado)
        if b and hasattr(self, "lbl_backup_info"):
            self.lbl_backup_info.configure(
                text=f"Seleccionado: {b['nombre']}  •  {b['tamaño_kb']} KB",
                text_color=C["text"],
            )

    def _restaurar_backup_seleccionado(self):
        b = self._backup_seleccionado()
        if not b:
            messagebox.showwarning("Selecciona un backup", "Elige un respaldo de la tabla primero.")
            return
        self._restaurar_backup(b["ruta"], b["nombre"])

    def _copiar_backup_seleccionado(self):
        b = self._backup_seleccionado()
        if not b:
            return
        self._copiar_backup(b["ruta"], b["nombre"])

    # ── CALLBACKS ─────────────────────────────────────────────────────────────
    def _exportar_db(self):
        try:
            ruta = backup.exportar_bd()
            if ruta:
                messagebox.showinfo("✔ Exportado",
                    f"Base de datos exportada correctamente:\n{ruta}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _exportar_zip(self):
        try:
            ruta = backup.exportar_zip()
            if ruta:
                messagebox.showinfo("✔ Exportado",
                    f"Respaldo comprimido guardado en:\n{ruta}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _importar(self):
        confirm = messagebox.askyesno(
            "⚠ Confirmar restauración",
            "Esto reemplazará TODOS los datos actuales con el archivo que elijas.\n\n"
            "Se hará una copia de seguridad automática antes de continuar.\n\n"
            "¿Deseas continuar?",
        )
        if not confirm:
            return
        try:
            from tkinter import filedialog
            origen = filedialog.askopenfilename(
                title="Seleccionar respaldo",
                filetypes=[
                    ("Respaldo SQLite o ZIP", "*.db *.zip"),
                    ("Base de datos", "*.db"),
                    ("ZIP", "*.zip"),
                ],
            )
            if not origen:
                return

            if origen.lower().endswith(".zip"):
                ok = backup.importar_zip(origen=origen)
            else:
                ok = backup.importar_bd(origen=origen)

            if ok:
                messagebox.showinfo(
                    "✔ Restaurado",
                    "La base de datos fue restaurada correctamente.\n"
                    "Reinicia el sistema para asegurarte de que todo está al día."
                )
                self._cargar_historial()
        except Exception as e:
            messagebox.showerror("Error al restaurar", str(e))

    def _backup_ahora(self):
        try:
            ruta = backup.backup_automatico(prefijo="manual")
            messagebox.showinfo("✔ Backup guardado",
                f"Copia guardada en:\n{ruta}")
            self._cargar_historial()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _restaurar_backup(self, ruta: str, nombre: str):
        confirm = messagebox.askyesno(
            "Restaurar backup",
            f"¿Restaurar el backup:\n{nombre}?\n\n"
            "Todos los datos actuales serán reemplazados.\n"
            "Se guardará una copia de seguridad antes.",
        )
        if not confirm:
            return
        try:
            backup.importar_bd(origen=ruta)
            messagebox.showinfo("✔ Restaurado",
                "Base de datos restaurada. Reinicia el sistema.")
            self._cargar_historial()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _copiar_backup(self, ruta: str, nombre: str):
        try:
            from tkinter import filedialog
            import shutil
            destino = filedialog.asksaveasfilename(
                title="Guardar copia del backup",
                defaultextension=".db",
                filetypes=[("Base de datos", "*.db")],
                initialfile=nombre,
            )
            if not destino:
                return
            shutil.copy2(ruta, destino)
            messagebox.showinfo("✔ Copiado", f"Backup copiado en:\n{destino}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _eliminar_backup_seleccionado(self):
        b = self._backup_seleccionado()
        if not b:
            messagebox.showwarning("Selecciona un backup", "Elige un respaldo de la tabla primero.")
            return

        # Candado: pide usuario y contraseña antes de permitir el borrado.
        _LoginEliminarBackupDialog(
            self,
            on_success=lambda: self._confirmar_eliminar_backup(b),
        )

    def _confirmar_eliminar_backup(self, b: dict):
        confirm = messagebox.askyesno(
            "⚠ Eliminar backup",
            f"¿Eliminar permanentemente el backup:\n{b['nombre']}?\n\n"
            "Esta acción no se puede deshacer.",
        )
        if not confirm:
            return
        try:
            ruta = b["ruta"]
            if os.path.isfile(ruta):
                os.remove(ruta)
            messagebox.showinfo("✔ Eliminado", f"Backup eliminado:\n{b['nombre']}")
            self._cargar_historial()
        except Exception as e:
            messagebox.showerror("Error al eliminar", str(e))

    def _formatear(self):
        DialogoFormatear(self, on_confirmado=self._ejecutar_formato)

    def _ejecutar_formato(self):
        try:
            ruta_bk = backup.formatear_bd()
            messagebox.showinfo(
                "✔ Base de datos formateada",
                f"Todas las tablas fueron borradas y recreadas vacías.\n\n"
                f"Backup previo guardado en:\n{ruta_bk}\n\n"
                "Reinicia el sistema para continuar.",
            )
            self._cargar_historial()
        except Exception as e:
            messagebox.showerror("Error al formatear", str(e))


# ─── DIÁLOGO DE FORMATEO ──────────────────────────────────────────────────────
_FMT_USER = "star"
_FMT_PASS = "hectorin14"


class DialogoFormatear(ctk.CTkToplevel):
    """
    Doble candado para el formateo de BD:
      1. Login con credenciales específicas (star / hectorin14)
      2. Verificación matemática aleatoria
    """
    def __init__(self, parent, on_confirmado):
        super().__init__(parent)
        self.on_confirmado = on_confirmado
        self._paso = 1          # 1 = login, 2 = pregunta matemática

        self.title("☢  Formatear base de datos")
        self.geometry("420x460")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        self.grab_set()
        self.lift()
        self.focus_force()

        self._build_login()

    # ── PASO 1: LOGIN ─────────────────────────────────────────────────────────
    def _build_login(self):
        self._limpiar()
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self, text="☢",
            font=ctk.CTkFont(size=40),
        ).grid(row=0, column=0, pady=(28, 0))

        ctk.CTkLabel(
            self, text="Formatear base de datos",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=C["red"]
        ).grid(row=1, column=0, pady=(6, 2))

        ctk.CTkLabel(
            self,
            text="Esta acción borrará TODOS los datos.\nIngresa las credenciales de administrador.",
            font=ctk.CTkFont(size=11),
            text_color=C["muted"],
            justify="center"
        ).grid(row=2, column=0, pady=(0, 20))

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.grid(row=3, column=0, padx=36, sticky="ew")
        form.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(form, text="Usuario", font=ctk.CTkFont(size=11),
                     text_color=C["muted"]).grid(row=0, column=0, sticky="w", pady=(0, 4))
        self._e_user = ctk.CTkEntry(
            form, height=40, placeholder_text="Usuario",
            fg_color=C["surface2"], border_color=C["border"],
            text_color=C["text"], font=ctk.CTkFont(size=13), corner_radius=10
        )
        self._e_user.grid(row=1, column=0, sticky="ew")
        self._e_user.focus_set()

        ctk.CTkLabel(form, text="Contraseña", font=ctk.CTkFont(size=11),
                     text_color=C["muted"]).grid(row=2, column=0, sticky="w", pady=(14, 4))
        self._e_pass = ctk.CTkEntry(
            form, height=40, placeholder_text="Contraseña", show="●",
            fg_color=C["surface2"], border_color=C["border"],
            text_color=C["text"], font=ctk.CTkFont(size=13), corner_radius=10
        )
        self._e_pass.grid(row=3, column=0, sticky="ew")
        self._e_pass.bind("<Return>", lambda e: self._verificar_login())

        self._lbl_err = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=11), text_color=C["red"]
        )
        self._lbl_err.grid(row=4, column=0, pady=(8, 0))

        btn_f = ctk.CTkFrame(self, fg_color="transparent")
        btn_f.grid(row=5, column=0, padx=36, pady=(16, 28), sticky="ew")
        btn_f.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            btn_f, text="Cancelar", height=40,
            fg_color=C["surface2"], hover_color=C["surface"],
            text_color=C["muted"], font=ctk.CTkFont(size=13),
            command=self.destroy
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(
            btn_f, text="Continuar →", height=40,
            fg_color=C["red"], hover_color="#cc3333",
            text_color="#fff", font=ctk.CTkFont(size=13, weight="bold"),
            command=self._verificar_login
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

    def _verificar_login(self):
        if (self._e_user.get().strip() == _FMT_USER and
                self._e_pass.get() == _FMT_PASS):
            self._build_pregunta()
        else:
            self._e_user.configure(border_color=C["red"])
            self._e_pass.configure(border_color=C["red"])
            self._e_pass.delete(0, "end")
            self._lbl_err.configure(text="⚠  Credenciales incorrectas")
            self.after(1800, lambda: (
                self._e_user.configure(border_color=C["border"]),
                self._e_pass.configure(border_color=C["border"]),
                self._lbl_err.configure(text=""),
            ))

    # ── PASO 2: VERIFICACIÓN MATEMÁTICA ───────────────────────────────────────
    def _build_pregunta(self):
        import random
        self._limpiar()

        # Generar operación aleatoria con números visualmente grandes
        ops = [
            lambda: (random.randint(20, 99), random.randint(20, 99), "*",
                     lambda a, b: a * b),
            lambda: (random.randint(100, 999), random.randint(10, 99), "+",
                     lambda a, b: a + b),
            lambda: (random.randint(200, 999), random.randint(10, 99), "-",
                     lambda a, b: a - b),
            lambda: (random.randint(10, 30), random.randint(10, 30), "*",
                     lambda a, b: a * b),
        ]
        a, b, simbolo, fn = random.choice(ops)()
        self._respuesta_correcta = fn(a, b)
        pregunta = f"{a} {simbolo} {b} = ?"

        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self, text="🧮  Confirmación de seguridad",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=C["yellow"]
        ).grid(row=0, column=0, pady=(28, 4))

        ctk.CTkLabel(
            self,
            text="Último paso. Resuelve la operación\npara confirmar el formateo.",
            font=ctk.CTkFont(size=11),
            text_color=C["muted"],
            justify="center"
        ).grid(row=1, column=0, pady=(0, 24))

        # Tarjeta con la pregunta
        q_card = ctk.CTkFrame(self, fg_color=C["surface2"], corner_radius=12)
        q_card.grid(row=2, column=0, padx=48, sticky="ew")
        ctk.CTkLabel(
            q_card, text=pregunta,
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=C["text"]
        ).pack(pady=18)

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.grid(row=3, column=0, padx=48, pady=(20, 0), sticky="ew")
        form.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(form, text="Tu respuesta:", font=ctk.CTkFont(size=11),
                     text_color=C["muted"]).grid(row=0, column=0, sticky="w", pady=(0, 6))
        self._e_resp = ctk.CTkEntry(
            form, height=44, placeholder_text="Escribe el resultado...",
            fg_color=C["surface2"], border_color=C["border"],
            text_color=C["text"], font=ctk.CTkFont(size=16), corner_radius=10
        )
        self._e_resp.grid(row=1, column=0, sticky="ew")
        self._e_resp.focus_set()
        self._e_resp.bind("<Return>", lambda e: self._verificar_math())

        self._lbl_err2 = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=11), text_color=C["red"]
        )
        self._lbl_err2.grid(row=4, column=0, pady=(8, 0))

        btn_f = ctk.CTkFrame(self, fg_color="transparent")
        btn_f.grid(row=5, column=0, padx=48, pady=(14, 28), sticky="ew")
        btn_f.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            btn_f, text="Cancelar", height=40,
            fg_color=C["surface2"], hover_color=C["surface"],
            text_color=C["muted"], font=ctk.CTkFont(size=13),
            command=self.destroy
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(
            btn_f, text="☢  FORMATEAR", height=40,
            fg_color=C["red"], hover_color="#cc3333",
            text_color="#fff", font=ctk.CTkFont(size=13, weight="bold"),
            command=self._verificar_math
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

    def _verificar_math(self):
        try:
            resp = int(self._e_resp.get().strip())
        except ValueError:
            self._lbl_err2.configure(text="⚠  Ingresa solo números")
            return

        if resp == self._respuesta_correcta:
            self.destroy()
            self.on_confirmado()
        else:
            self._e_resp.configure(border_color=C["red"])
            self._e_resp.delete(0, "end")
            self._lbl_err2.configure(text=f"⚠  Respuesta incorrecta — intenta de nuevo")
            self.after(1800, lambda: (
                self._e_resp.configure(border_color=C["border"]),
                self._lbl_err2.configure(text=""),
            ))

    # ── HELPERS ───────────────────────────────────────────────────────────────
    def _limpiar(self):
        """Borra todos los widgets del diálogo antes de reconstruir un paso."""
        for w in self.winfo_children():
            w.destroy()