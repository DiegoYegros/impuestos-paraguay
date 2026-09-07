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
