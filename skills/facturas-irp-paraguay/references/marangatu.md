# carga en Marangatu

Circuito revisado el 2026-09-07
Comprobá la interfaz actual y la guía oficial antes de actuar

## acceso y preparación

Usá el [flujo de validación](validacion.md) antes y después de la carga
Un lote en revisión no se envía al portal

Entrá desde [DNIT](https://www.dnit.gov.py) → Sistema Marangatu
Usá una sesión autorizada; si falta, pedile al usuario que ingrese y resuelva cualquier verificación
Confirmá titular, ejercicio y obligaciones activas del RUC
Consultá o solicitá el reporte de comprobantes registrados y conciliá por identidad fiscal con el libro local
Guardá estado por documento: pendiente, ya registrado, cargado, rechazado, confirmado

## carga de comprobantes

En Declaraciones Informativas → Gestión de Comprobantes Informativos, distinguí los circuitos

**Electrónicos y virtuales**

Usá Obtener Comprobantes Electrónicos y Virtuales, período y sección correspondiente
Conciliá compras y ajustes antes de imputar a IRP/IVA/otras obligaciones
No los incluyas en carga manual ni en el archivo de importación de preimpresos
Para lotes grandes o perfiles transaccionales, usá el archivo generado por el propio sistema y su mecanismo de devolución
No pulses Imputar todo salvo que el conjunto completo esté revisado para la misma imputación
La imputación no llena automáticamente la declaración de liquidación

[guía oficial actualizada de electrónicos y virtuales](https://www.dnit.gov.py/documents/20123/437212/Gu%C3%ADa%2BPaso%2Ba%2BPaso%2B-%2BC%C3%B3mo%2Bobtener%2Bcomprobantes%2Belectr%C3%B3nicos%2By%2Bvirtuales.pdf/31a43846-a0e3-9ad9-7003-bc19bc5bc92d?t=1778092596059)

**Preimpresos y otros respaldos admitidos**

Usá registro manual para pocos comprobantes y la importación oficial para lotes
La planilla interna de esta skill no es un archivo de importación
Generá el archivo fiscal sólo después de leer la especificación vigente y mapear cada tipo documental, pago e imputación
Según la especificación publicada, se admiten TXT tabulado o CSV, UTF-8, dentro de ZIP, hasta 5.000 registros por archivo
Nombre base: RUC sin DV, `REG`, período mensual `MMAAAA` o anual `AAAA` y secuencia alfanumérica de hasta cinco caracteres, separados por `_`
El archivo interior y el ZIP comparten nombre base
Verificá si corresponde 955 mensual o 956 anual según las obligaciones del RUC

[especificación oficial del importador](https://www.dnit.gov.py/documents/44828/0/Especificaciones%2BT%C3%A9cnicas%2Bpara%2Bregistro%2Bde%2Bcomprobantes%2Ben%2BMarangatu.pdf/fd50732c-4232-750a-b253-5b14843cdccb?t=1682430005384.pdf)

## conciliación y presentación

Esperá el procesamiento, leé rechazos y corregí sólo esas filas
Descargá un reporte nuevo y ejecutá `conciliar_lote` antes de confirmar la presentación
Antes de reintentar, consultá qué aceptó el sistema para no duplicarlo
Compará cantidades e importes con el reporte descargado, incluyendo partidas no imputadas y ajustes
Resolvé las diferencias antes de presentar
Cuando la autorización cubra confirmar el registro, revisá el resumen y completá la confirmación
Conservá Formulario 241/talón y resumen como evidencia

El registro anual de 2025 venció en febrero de 2026; ese aviso no fija por sí solo las fechas de otros ejercicios
Consultá siempre el calendario por terminación del RUC y prórrogas aplicables

[aviso DNIT sobre registro anual 2025 y talón 241](https://www.dnit.gov.py/en/web/portal-institucional/w/vencimiento-del-registro-anual-de-comprobantes-correspondiente-al-ejercicio-2025)

## declaración IRP-RSP

Abrí la declaración de obligación 715 y Formulario 515 del ejercicio correcto desde las opciones que muestre Marangatu
Conciliá ingresos, egresos, familiares, retenciones y resultados con el instructivo actual
Mostrá el borrador completo, impuesto estimado y pendientes antes de pedir una autorización que aún falte
Con autorización para presentar, enviá y verificá número de orden/acuse; pagar requiere que el encargo también cubra el pago concreto
No traslades campos por número desde una versión vieja del formulario
Al terminar informá el estado real: preparado, registrado, confirmado, presentado o pagado

[guías y reportes oficiales](https://www.dnit.gov.py/en/web/portal-institucional/registro-de-comprobantes)
