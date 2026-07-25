# Sistema POS — Los Lichos

Sistema de punto de venta de escritorio para **Los Lichos**, desarrollado en Python con [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) y SQLite.

## ✨ Funcionalidades

- 🛒 **Punto de venta** — registro de ventas al contado y a crédito/abono
- 📦 **Inventario** — control de productos y categorías
- 💳 **Abonos** — gestión de ventas a crédito con comprobantes de pago
- 📋 **Historial de ventas** — búsqueda, filtros por período y generación de cierres en PDF
- 🧾 **Tickets térmicos** — generación de tickets en PDF con formato de impresora térmica 80mm
- 🗄 **Respaldos** — exportación/importación de la base de datos (.db / .zip), backups automáticos y borrado protegido con usuario y contraseña

## 🛠 Tecnologías

- Python 3
- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) — interfaz gráfica
- SQLite — base de datos
- [ReportLab](https://www.reportlab.com/) — generación de PDFs (tickets y cierres de venta)
- PyInstaller — empaquetado como ejecutable (.exe)

## 📁 Estructura del proyecto

```
├── main.py                # Punto de entrada de la aplicación
├── database.py             # Conexión y esquema de la base de datos
├── backup.py                # Exportar / importar / formatear la BD
├── logger_config.py          # Configuración de logging (pos.log)
├── views/                     # Módulos de la interfaz (POS, inventario, ventas, etc.)
├── assets/                     # Íconos y logo
└── .gitignore
```

## 🔒 Notas de seguridad

- Las operaciones destructivas (formatear base de datos, eliminar backups) están protegidas con usuario y contraseña.
- La base de datos (`pos.db`), logs (`pos.log`) y backups (`backups/`) están excluidos del control de versiones — cada instalación mantiene sus propios datos localmente.

## 📄 Licencia

Uso privado — Los Lichos.
