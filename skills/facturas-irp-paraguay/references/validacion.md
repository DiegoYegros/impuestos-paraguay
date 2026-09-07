# validación y revisión

Antes de cargar, cotejá cada factura con su original y validá el XLSX completo
Después de cargar, descargá un reporte nuevo de Marangatu y comparalo con el mismo lote
Una carga aceptada por el portal todavía necesita esa conciliación

## archivos del lote

Usá un directorio privado fuera del repo, con una carpeta por titular y ejercicio
El identificador del lote admite letras, números, guion y guion bajo
No reutilices un lote para otro contribuyente

```text
directorio-privado/
  lote-2026/
    inventario.json
    extraccion.json
    facturas-irp.xlsx
    marangatu-antes.json
    marangatu-despues.json
    originales/
    reportes/
```

Los originales y reportes pueden vivir en otras carpetas dentro del directorio privado
Sus rutas y hashes deben coincidir con los documentos del lote
El inventario debe cubrir todos los originales usados y cada original debe estar vinculado a la extracción

## segunda lectura y hoja Carga

Cotejá RUC, destinatario, fecha, timbrado, número, moneda, condición de pago e importes con el original
Revisá gravadas al 10%, gravadas al 5% y exentas, todos como importes brutos en guaraníes
Verificá la imputación fiscal con los respaldos y las reglas aplicables
No completes campos dudosos para hacer pasar el validador

En cada documento de `extraccion.json`, agregá

```json
{
  "ruc_destinatario": "1000000-0",
  "gravado_10_gs": 110000,
  "gravado_5_gs": 0,
  "exento_gs": 0,
  "imputaciones": ["IRP"],
  "cotejo_original": {
    "verificado": true,
    "evidencia": "segunda lectura del original, página 1, campos e importes coinciden"
  }
}
```

El ejemplo es ficticio
Marcá el cotejo como verificado sólo después de leer el comprobante otra vez
Un hash permite detectar cambios del archivo; la lectura contra el original verifica la extracción

Regenerá el libro y la planilla con esos datos
La hoja Carga conserva los campos fiscales que se compararán con el portal
El validador también comprueba Facturas y el subtotal de Resumen, sin ejecutar fórmulas de las filas

Este flujo admite facturas nacionales al contado con imputación única al IRP
Los documentos especiales y las imputaciones múltiples quedan en revisión
Conservá sus datos reales y resolvé su tratamiento antes de ampliar el flujo

## reportes de Marangatu

Descargá el reporte completo del titular y ejercicio y conservá el archivo original
Si la descarga está paginada o en proceso, esperá a completarla
Transcribí sus filas a `marangatu-antes.json` y cotejalas con la descarga, incluyendo la cantidad y el total
La normalización requiere lectura del agente; el servidor no inicia sesión ni descarga reportes

```json
{
  "ruc_titular": "1000000-0",
  "ejercicio": 2026,
  "consultado_en": "2026-09-07T15:00:00-03:00",
  "completo": true,
  "cotejado_con_original": true,
  "fuente": {"archivo": "/ruta/privada/reportes/descarga.csv", "sha256": "hash-del-archivo"},
  "cantidad": 0,
  "total_gs": 0,
  "documentos": []
}
```

La lista vacía sólo corresponde a un reporte realmente sin registros
Cada fila debe incluir los campos de la hoja Carga, salvo el id local, más `referencia_original` y `estado_registro`
`referencia_original` identifica la fila o página de la descarga
`estado_registro` admite `registrado` o `confirmado`; las filas rechazadas o en procesamiento no prueban una carga
`imputaciones` usa `IRP`, `IVA`, `IRE` o `NO_IMPUTAR` según el reporte
Si el reporte no muestra un campo requerido, consultá su detalle en Marangatu y conservá el respaldo; mientras falte, el lote queda bloqueado

Los reportes vencen a las 24 horas para este flujo, como control local de frescura
Eso no es un plazo tributario

## antes de cargar

Ejecutá `validar_lote` por MCP o la CLI
Se comprueban inventario, originales, extracción, ambas hojas de datos y reporte previo
Las facturas que ya coinciden con el portal quedan como cargadas
Las ausentes quedan pendientes; las diferencias pasan a en revisión
Si hay una duda o error, `apto_para_carga` es falso y `para_cargar` queda vacío para todo el lote

Abrí `revision.html` para ver los motivos y los originales
Corregí la extracción o agregá el respaldo faltante, regenerá la planilla y validá de nuevo
No hay un botón para aprobar dudas sin corregirlas

Con `apto_para_carga: true`, prepará únicamente los ids de `para_cargar`
Revisá la vigencia justo antes de operar el portal con `obtener_resumen_lote`
Un cambio en los archivos invalida el resultado
El XLSX y el manifiesto del validador siguen siendo archivos internos; la importación fiscal usa la especificación de Marangatu
La autorización para cargar, presentar o pagar se resuelve según el encargo

## después de cargar

Descargá un reporte nuevo y guardá su normalización como `marangatu-despues.json`
Su fecha debe ser posterior a la validación previa y a la operación de carga
Ejecutá `conciliar_lote`

La comparación usa identidad fiscal, campos e importes de cada factura
Detecta faltantes, duplicados, cambios de imputación y registros del portal ausentes del libro
También conserva las facturas ya registradas antes de la carga
Sólo `conciliado: true` permite dar por terminado el lote
Si falta el reporte posterior o tiene problemas, el lote vuelve a en revisión
Consultá el portal antes de reintentar una carga para evitar duplicados

Cada ejecución guarda un resultado fechado en `historial/`, además del resultado actual y la bandeja HTML
Las herramientas de consulta informan la fecha del reporte y si la validación sigue vigente

## CLI

Desde la carpeta de la skill

```bash
python3 scripts/validacion.py validar lote-2026 --datos /ruta/privada
python3 scripts/validacion.py conciliar lote-2026 --datos /ruta/privada
python3 scripts/validacion.py consultar lote-2026 --datos /ruta/privada
```
