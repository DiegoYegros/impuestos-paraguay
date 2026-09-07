# impuestos-paraguay

Skills y scripts para preparar impuestos de Paraguay con un agente de IA
Por ahora incluye [facturas-irp-paraguay](skills/facturas-irp-paraguay/SKILL.md), para gastos del IRP-RSP y su registro en Marangatu

El agente lee las facturas y revisa las normas de la DNIT
Los scripts detectan duplicados, calculan el subtotal deducible y generan la planilla
La carga en Marangatu requiere herramientas de navegador y una sesión autorizada

## usar la skill

Copiá `skills/facturas-irp-paraguay` al directorio de skills de tu agente
En Codex podés enlazarla desde la raíz del repositorio

```bash
mkdir -p "$HOME/.codex/skills"
ln -s "$PWD/skills/facturas-irp-paraguay" "$HOME/.codex/skills/facturas-irp-paraguay"
```

Adjuntá los comprobantes o indicá una carpeta y pedí

```text
$facturas-irp-paraguay procesá estas facturas para el IRP y armame la planilla
```

Python 3.11 o posterior alcanza para generar el libro JSON y CSV
El generador XLSX incluido usa Node y `@oai/artifact-tool`, disponible en el runtime de planillas de Codex
Los pasos y alternativas están en [datos.md](skills/facturas-irp-paraguay/references/datos.md)

## pruebas

```bash
python3 -m unittest discover -s skills/facturas-irp-paraguay/scripts -p 'test_*.py'
```

Las pruebas usan datos ficticios
Guardá documentos, perfiles tributarios y resultados fuera de este repositorio

## validar y conciliar

El [flujo de validación](skills/facturas-irp-paraguay/references/validacion.md) comprueba cada fila del XLSX contra la extracción y los reportes de Marangatu
Una duda bloquea el lote y aparece en `revision.html`, con el motivo y el comprobante
Después de cargar, un reporte nuevo permite detectar faltantes, duplicados y diferencias

## servidor MCP

El servidor trabaja por stdio con archivos locales
Consulta reportes descargados de Marangatu y muestra su fecha; no inicia sesión ni envía datos al portal

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
IMPUESTOS_DATOS=/ruta/privada .venv/bin/python servidor_mcp.py
```

Configurá tu cliente MCP con ese comando y la variable `IMPUESTOS_DATOS`
Usá un solo servidor por directorio de datos

| herramienta | uso |
| --- | --- |
| `validar_lote` | coteja archivos y reporte previo, genera la bandeja |
| `conciliar_lote` | compara el lote con el reporte posterior |
| `obtener_facturas_cargadas` | lista coincidencias verificadas con el portal |
| `obtener_facturas_pendientes` | lista facturas ausentes del reporte previo |
| `obtener_facturas_en_revision` | muestra dudas, diferencias y respaldos |
| `obtener_resumen_lote` | indica vigencia, estados y ubicación de la bandeja |

Todas reciben `lote`; las listas aceptan `desde` y `limite`, hasta 200 filas por consulta
El servidor usa el [SDK oficial de MCP](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x)
Para ejecutar también las pruebas de protocolo, usá el Python del entorno virtual
