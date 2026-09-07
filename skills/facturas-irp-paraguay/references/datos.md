# datos y ejecución

## contrato de extracción

El agente lee las imágenes y escribe JSON UTF-8 con `perfil` y `documentos`
Los scripts no llaman a ningún modelo ni servicio de OCR
Guardá la entrada, inventario y resultados juntos en una carpeta del ejercicio fuera del repositorio
No agregues datos reales a los ejemplos o tests de la skill

`perfil` lleva `ejercicio` entero, `ruc_titular` texto, `contribuyente_iva` booleano o null, `inicio_deducciones` ISO o null, `normativa_verificada` booleano y `fuentes_vigencia` lista de objetos con URL, fecha de consulta, artículo y vigencia aplicable
`inicio_deducciones` es el día siguiente al cruce confirmado en el primer año, o el 1 de enero en ejercicios posteriores
Guardá además familiares habilitados y evidencia del perfil si corresponde

Cada documento lleva los campos siguientes

| campos | contenido |
| --- | --- |
| id | identificador único de fila, estable entre ejecuciones |
| fuentes | lista de archivo absoluto, sha256 del inventario y ubicacion de página/recorte |
| fecha, emisor, ruc_emisor, destinatario, ruc_destinatario | transcripción, fechas ISO y RUC con DV como texto |
| tipo, origen | `factura`, `nota_credito`, `nota_debito`, `recibo`, `otro`; origen `preimpreso`, `electronico`, `virtual`, `otro` |
| timbrado, numero, cdc | texto conservando ceros y separadores, null si falta |
| concepto, detalle | descripción y partidas con importes, evidencia y clasificación por concepto |
| moneda, pais | `PYG`, `PY` para caso nacional; códigos reales en otros casos |
| total_gs | entero sin separadores, null si no se puede determinar |
| condicion | `contado`, `credito` o null, sin adivinar por la foto |
| pagos | lista de fecha ISO, monto_gs entero y respaldo del pago vinculado |
| candidato_gs | porción bruta pagada admisible, antes de exclusiones, no necesariamente el total de factura |
| iva_credito_gs, otro_impuesto_gs | exclusiones dentro del candidato, sin solaparlas; 0 sólo si verificaste que no corresponde excluir |
| categoria | alimentación como `alimentacion`, vestimenta, alquiler, mantenimiento, equipamiento, salud, educacion, movilidad, recreacion, actividad u otra categoría específica |
| decision | `deducible`, `no_deducible`, `revisar` |
| motivo, norma_url, articulo | razón concreta de la decisión y respaldo normativo |
| controles | booleanos o null para las verificaciones abajo |
| observaciones | lista de problemas sin resolver, vacía cuando no hay |
| factura_asociada | id o identidad `cdc:…` / `doc:RUC\|tipo\|timbrado\|numero` de la factura original para ajustes |
| ya_registrado | booleano o null, sustentado en consulta real de Marangatu |

`controles` contiene `documento_valido`, `destinatario_valido`, `financiacion_valida`, `pago_verificado`, `categoria_admitida`, `sin_doble_deduccion`
Usá `true` cuando cotejaste el hecho y guardaste evidencia
Un original legible no prueba por sí solo la validez fiscal, el pago ni la financiación
Para contado, el respaldo puede ser la propia factura válida que declara esa condición cuando corresponda
Retené texto literal de campos dudosos en `detalle`; nunca uses cero como sustituto de un monto desconocido

## ejecutar

Desde la carpeta de la skill, con Python 3.11 o posterior

```bash
python3 scripts/facturas.py inventario /ruta/facturas --out /ruta/lote/inventario.json
# el agente lee los originales y produce extraccion.json
python3 scripts/facturas.py libro /ruta/lote/extraccion.json --out-dir /ruta/lote/salida
python3 -m unittest discover -s scripts -p 'test_*.py'
```

El libro produce `libro.json` y `libro-interno.csv`
La cifra es un subtotal identificado, no la obligación anual
Los casos especiales quedan sin monto deducible validado aunque el agente proponga uno
Para resolverlos, documentá la conciliación específica y actualizá el libro/planilla mediante el agente, conservando fórmula, fuentes y registro del ajuste
Conservá los datos originales al resolver un caso pendiente

## generar XLSX

Usá la skill de planillas disponible y su runtime de `@oai/artifact-tool`
Si el runtime no está localizado, pedí las rutas con `load_workspace_dependencies`
Copiá `scripts/planilla.mjs` a una carpeta temporal de trabajo y enlazá allí `node_modules` al directorio de dependencias devuelto
Ejecutá con el Node de ese runtime

```text
NODE /ruta/temporal/planilla.mjs /ruta/lote/salida/libro.json /ruta/lote/salida/facturas-irp.xlsx
```

El generador produce Facturas, Pendientes, Carga, Resumen y previsualizaciones PNG para revisar
Comprobá `verificacion.json`, que las fórmulas no tengan errores y el subtotal coincida con JSON
Mirá las vistas y ajustá los anchos si el texto se corta
Entregá la planilla y un mensaje breve, conservando JSON/CSV como respaldo
Si falta ese runtime, usá otra herramienta de planillas o entregá el CSV

## reanudación

Antes de correr el script, uní los documentos anteriores y nuevos del mismo titular y ejercicio
Guardá el histórico de ajustes y el estado real de carga en un manifiesto local
`ya_registrado` cambia la ruta de carga, no elimina una deducción del libro anual
Si dos copias tienen datos contradictorios, ambas quedan para revisión; resolvé desde originales y conservá la explicación
Un CSV interno no cumple el esquema de importación de Marangatu

Para cargar al portal, completá el [flujo de validación](validacion.md), con la segunda lectura, los campos de Carga y los reportes previo y posterior
