# FACTUSOL + GOOGLE SHEETS + STREAMLIT + INFORMES PDF (ARTES BUHO)

Arquitectura activa (100% gratuita y open source):

- Fuente de datos: Google Sheets
- Capa analitica compartida: Python (pandas)
- Dashboard: Streamlit
- Informes corporativos: PDF con ReportLab + matplotlib
- Almacenamiento operativo: Google Drive
- Versionado: GitHub

## 1) Objetivo

Sistema unificado para:

1. Leer datos de Google Sheets.
2. Limpiar y normalizar automaticamente.
3. Reutilizar la misma logica para paneles e informes.
4. Generar informes PDF semanal/mensual/anual.
5. Crear/reutilizar estructura en Drive:
   - Informes/InformeSemanal
   - Informes/InformeMensual
   - Informes/InformeAnual
6. Preparar email corporativo sin enviar correos todavia.

## 2) Estructura del proyecto

```text
proyecto/
  app.py
  main.py
  config.py
  data_processing.py
  insights.py
  requirements.txt
  .env.example
  .streamlit/
    config.toml
  assets/
    logo_artes_buho.png
  shared/
    __init__.py
    data_loader.py
    insights.py
    analytics.py
  reporting/
    __init__.py
    periods.py
    naming.py
    drive_manager.py
    email_manager.py
    pdf_builder.py
    generator.py
    cli.py
  scripts/
    simulate_factusol_to_sheets.py
    create_drive_launcher_doc.py
  tests/
    test_periods.py
    test_naming.py
    test_drive_manager.py
    test_email_manager.py
```

## 3) Preparacion

1. Crear entorno virtual:

```powershell
python -m venv .venv
```

2. Activar entorno:

```powershell
.\.venv\Scripts\Activate.ps1
```

3. Instalar dependencias:

```powershell
pip install -r requirements.txt
```

4. Crear `.env`:

```powershell
Copy-Item .env.example .env
```

5. Ajustar credenciales Google en `.env`.

## 4) Simulacion coherente de datos Factusol

```powershell
python scripts/simulate_factusol_to_sheets.py
```

Crea/actualiza:

- `hoja_clientes`
- `hoja_facturas`
- `hoja_lineas`
- `hoja_articulos`

Y elimina pestañas legacy de arquitectura anterior si existen.

## 5) Dashboard (Streamlit)

```powershell
streamlit run app.py
```

## 6) Informes PDF corporativos (CLI)

### Semanal

```powershell
python main.py generate weekly --run-datetime "2026-04-06 08:00"
```

### Mensual

```powershell
python main.py generate monthly --run-datetime "2026-04-01 08:00"
```

### Anual

```powershell
python main.py generate annual --run-datetime "2027-01-01 08:00"
```

### Dry-run (sin subida a Drive, sin envio email)

```powershell
python main.py generate weekly --run-datetime "2026-04-06 08:00" --dry-run
```

### Overwrite en Drive

```powershell
python main.py generate weekly --run-datetime "2026-04-06 08:00" --overwrite
```

### Omitir subida a Drive

```powershell
python main.py generate monthly --run-datetime "2026-04-01 08:00" --skip-drive-upload
```

### Preparar estructura de carpetas en Drive

```powershell
python main.py prepare-drive
```

### Preview de email (sin envio)

```powershell
python main.py preview-email weekly --run-datetime "2026-04-06 08:00"
```

## 7) Reglas de periodo y naming

### Semanal
- Ejecucion prevista: lunes 08:00.
- Cobertura: semana anterior completa (lunes-domingo).
- Nombre: `YYMMDD_InformeSemanal.pdf` (fecha de generacion).

Ejemplo:
- Run: `2026-04-06 08:00`
- Cobertura: `2026-03-30` a `2026-04-05`
- Nombre: `260406_InformeSemanal.pdf`

### Mensual
- Ejecucion prevista: dia 1 08:00.
- Cobertura: mes anterior completo.
- Nombre: `YYMM_InformeMensual.pdf` (periodo analizado).

Ejemplo:
- Run: `2026-04-01 08:00`
- Cobertura: marzo 2026
- Nombre: `2603_InformeMensual.pdf`

### Anual
- Ejecucion prevista: 1 de enero 08:00.
- Cobertura: anio anterior completo.
- Nombre: `YYYY_InformeAnual.pdf`.

Ejemplo:
- Run: `2027-01-01 08:00`
- Cobertura: 2026
- Nombre: `2026_InformeAnual.pdf`

## 8) Programacion automatica

### Cron (Linux/Mac)

```bash
# Semanal (lunes 08:00)
0 8 * * 1 /ruta/python /ruta/proyecto/main.py generate weekly

# Mensual (dia 1, 08:00)
0 8 1 * * /ruta/python /ruta/proyecto/main.py generate monthly

# Anual (1 enero, 08:00)
0 8 1 1 * /ruta/python /ruta/proyecto/main.py generate annual
```

### Windows Task Scheduler (GUI o schtasks)

```powershell
# Semanal
schtasks /Create /TN "ArtesBuho_InformeSemanal" /SC WEEKLY /D MON /ST 08:00 /TR "python C:\ruta\proyecto\main.py generate weekly"

# Mensual
schtasks /Create /TN "ArtesBuho_InformeMensual" /SC MONTHLY /D 1 /ST 08:00 /TR "python C:\ruta\proyecto\main.py generate monthly"

# Anual
schtasks /Create /TN "ArtesBuho_InformeAnual" /SC YEARLY /M JAN /D 1 /ST 08:00 /TR "python C:\ruta\proyecto\main.py generate annual"
```

## 9) Drive: estructura exacta

El sistema crea/reutiliza en la carpeta padre de la hoja fuente:

- `Informes`
- `Informes/InformeSemanal`
- `Informes/InformeMensual`
- `Informes/InformeAnual`

Comportamiento ante duplicados:

- Por defecto: `skip` si ya existe el mismo archivo.
- Con `--overwrite`: reemplaza el archivo existente.

Soporte Shared Drives:

- `supportsAllDrives=True`
- `includeItemsFromAllDrives=True`

## 10) Email preparado (no activo)

- Capa desacoplada en `reporting/email_manager.py`.
- `EMAIL_ENABLED=False` por defecto.
- Hay `preview-email` y `dry-run`.
- No se envian correos reales en esta fase.

## 11) Tests

```powershell
pytest -q
```

Cobertura minima incluida:

- periodos (`tests/test_periods.py`)
- naming (`tests/test_naming.py`)
- creacion/reutilizacion Drive en modo simulado (`tests/test_drive_manager.py`)
- dry-run email (`tests/test_email_manager.py`)

## 12) Notas de autenticacion Google

Opciones soportadas:

- `GOOGLE_CREDENTIALS_FILE` (service account)
- `GOOGLE_OAUTH_TOKEN_FILE` (oauth token)

Permisos necesarios:

- Lectura Sheets
- Escritura/lectura Drive
- (Opcional) Docs para lanzador de panel

Si usas Shared Drive:

- Asegura permisos de lectura/escritura para la identidad usada (service account u oauth user).

---

Empresa: ARTES BUHO  
Desarrollador: RUBEN COTON

## CIERRE CLOUD 2026-04-08
- Estado: sincronizado para migracion a nuevo PC/sistema.
- Preparado para retomar desde GitHub.
- Ultima revision: 2026-04-08 15:26:05 +02:00

## CIERRE MIGRACION CLOUD

- Fecha: 2026-04-08
- Estado: listo para retomar desde otro sistema


<!-- MIGRACION_CLOUD_START -->
## ESTADO MIGRACION CLOUD
- Revisado: 2026-04-08
- Repo listo para continuar en otro sistema.
- Estado Git al cerrar: sincronizado en GitHub.
<!-- MIGRACION_CLOUD_END -->
