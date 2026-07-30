# 8. Reportes y Facturación

Este capítulo cubre la sección **Reportes** y la sección **Facturas** del panel de administración: dónde revisar la rentabilidad del negocio, cómo generar y gestionar las facturas de los clientes, cómo personalizar su plantilla, cómo recalcular tarifas con efecto retroactivo y cómo hacer un reset completo de facturación cuando hace falta arrancar de cero.

## 8.1 Reportes de rentabilidad

La opción **Reportes**, en el menú lateral, muestra la tabla de **consumos por cliente** en un período determinado: cuántas llamadas hizo cada cliente, cuántos minutos consumió, cuánto costó esa llamada en compra (lo que VoxiKam le paga al carrier), cuánto se le cobró en venta (lo que se le factura al cliente) y qué margen o ganancia deja esa diferencia.

Referencia visual: `img/admin-reports.png`.

En la captura de referencia, correspondiente a **julio 2026**, se ve la estructura de la tabla:

- Una fila por cliente, con las columnas **Llamadas**, **Minutos**, **Compra** (costo), **Venta** (facturado) y **Ganancia** (margen).
- Una fila de **Total general** al pie, que suma todas las columnas: en el ejemplo, **2111 llamadas** y **S/. 193.65** en ventas para todos los clientes del período.

Algunos ejemplos de la captura:

- **Comercial Andes SAC**: 514 llamadas, S/. 61.45 en ventas.
- **Distribuidora Milenio**: 514 llamadas, S/. 60.63 en ventas.
- **Call Center Norte**: 498 llamadas, S/. 47.57 en ventas.
- **Callao Voz SAC**: 13 llamadas, S/. 1.28 en ventas.
- **Grupo Reventa Perú**: 572 llamadas, S/. 22.72 en ventas, pero con una **ganancia negativa de -S/. 23.41**.

Este último caso es justamente el motivo por el que esta pantalla existe: **Grupo Reventa Perú** tuvo más llamadas que casi cualquier otro cliente del período, pero terminó dejando pérdida en vez de ganancia. Eso significa que el costo de compra de esas llamadas fue más alto que lo que se le cobró al cliente, probablemente porque su tarifa de venta quedó desactualizada o mal configurada frente al costo real del carrier. Revisar periódicamente esta tabla te permite detectar este tipo de casos a tiempo —clientes con margen negativo o anormalmente bajo— y corregir la tarifa correspondiente antes de que el problema se acumule mes a mes.

Para revisar un período distinto, cambiá el rango de fechas del reporte y volvé a consultar; la tabla y el total general se recalculan según el rango elegido.

## 8.2 Reporte por destino / área

Dentro de la misma sección **Reportes** hay un desglose adicional: el reporte **por destino / área**. Mientras la tabla de la sección anterior muestra rentabilidad por cliente, esta vista agrupa el mismo tipo de información (llamadas, facturación, margen) por **zona geográfica** de destino, para saber qué áreas dejan más o menos margen.

Referencia visual: `img/admin-areas.png`.

En la captura de referencia, para el período de julio 2026, el reporte muestra el mensaje **"Sin llamadas contestadas en el rango"**. Esto no es un error: ocurre porque las áreas creadas en este ambiente de demostración (**Lima Metropolitana**, **Provincias**) todavía no tienen **prefijos** asignados. Sin prefijos definidos, el sistema no tiene forma de asociar los números de destino de los CDRs a ninguna área, y por lo tanto no puede calcular el desglose.

Para que este reporte muestre datos, primero hay que asignar los prefijos correspondientes a cada área desde la sección de **Tarifas** (ver capítulo de Tarifas). Una vez que las áreas tengan prefijos configurados, las llamadas del período se agruparán automáticamente por área y el reporte mostrará cuánto se factura y qué margen deja cada zona geográfica.

## 8.3 Facturas

La opción **Facturas** permite generar y administrar las facturas de los clientes a partir de los CDRs (registros de llamadas) de un período.

Referencia visual: `img/admin-invoices.png`.

En la captura de referencia se ve un listado de **8 facturas**, correspondientes a los meses de **mayo y junio de 2026**, para **4 clientes** distintos. Cada fila muestra, entre otros datos, el cliente, el número de factura, el monto total y el **estado**:

- **draft** (borrador): la factura ya fue generada pero todavía no fue marcada como pagada. Por ejemplo, la factura **#2 de Comercial Andes SAC**, por **S/. 86.79**, aparece en estado draft.
- **paid** (pagada): la factura ya fue cobrada y acreditada. Por ejemplo, la factura **#1 de Comercial Andes SAC**, por **S/. 31.62**, aparece en estado paid.

### Generar una factura

Para generar una factura nueva:

1. Elegí el **cliente** para el que querés facturar.
2. Elegí el **período** (rango de fechas) que va a cubrir la factura.
3. Generá la factura. VoxiKam toma todos los CDRs del cliente dentro de ese período, calcula el monto facturable, aplica el **impuesto** correspondiente (IGV, 18% en Perú) y arma el PDF con el total final.

### Marcar como pagada

Cuando el cliente efectivamente paga una factura, marcala como **pagada** desde el listado. Al hacerlo, VoxiKam **acredita el monto directamente al balance del cliente** de forma automática, sin necesidad de ningún registro manual adicional.

## 8.4 Plantilla de factura

La opción **Plantilla de factura** permite personalizar la apariencia del PDF que se genera para cada factura.

Referencia visual: `img/admin-invoice-template.png`.

En la captura de referencia se ven las opciones de personalización disponibles, cada una con su casillero:

- **Logo**
- **Encabezado de empresa**
- **Pie de página**
- **Color de acento**

En el ejemplo de la captura, todos los casilleros están **desmarcados**, es decir, la factura se genera con la plantilla por defecto, sin ninguna personalización aplicada. Para personalizar el PDF, marcá los elementos que querés activar (por ejemplo, subir un logo o definir un color de acento) y guardá los cambios; las facturas que se generen a partir de ese momento usarán la plantilla personalizada.

## 8.5 Recalcular tarifas (billing-recalc)

La opción **Recalcular tarifas** permite recalcular retroactivamente el costo de compra y el precio de venta de CDRs que **ya fueron facturados**, cuando una tarifa cambia después de que esas llamadas ya ocurrieron.

Referencia visual: `img/admin-billing-recalc.png`.

Un caso típico: un cliente negocia con vos un precio nuevo a mitad de mes, con **efecto retroactivo** desde el día 1. Las llamadas de la primera quincena ya se cursaron y ya se calcularon con la tarifa vieja, pero deberían recalcularse con la tarifa nueva para que la factura del mes refleje el precio acordado.

Para usar esta función:

1. Elegí el **alcance**: **Cliente** o **Carrier**, según si el cambio de tarifa aplica al precio de venta de un cliente o al costo de compra de un carrier.
2. Elegí el **período** a recalcular (en la captura de referencia, **July 2026**).
3. Generá una **vista previa** antes de aplicar el recálculo, para revisar el impacto (cuánto cambia el costo o la venta) antes de confirmar los cambios de forma definitiva.

## 8.6 Reset facturación

**Reset facturación** es una acción de mantenimiento **destructiva e irreversible**: borra por completo el historial de facturas y el balance de un cliente, dejándolo en cero.

Referencia visual: `img/admin-billing-reset.png`.

En la captura de referencia, la pantalla advierte que esta acción borraría las **8 facturas** actuales del cliente y **todo su historial de balance**, y pide escribir la palabra de confirmación **"RESETEAR"** antes de permitir ejecutar la acción. Esta confirmación explícita existe precisamente porque no hay forma de deshacer un reset una vez ejecutado.

Este reset está pensado para un caso puntual: **limpiar datos de prueba** acumulados durante una implementación (facturas y balances generados mientras se probaba el sistema), antes de salir a producción con datos reales. **No es una acción de uso rutinario** ni debe usarse para corregir errores puntuales en una factura —para eso existen la edición de facturas individuales y el recálculo de tarifas descrito en la sección anterior—. Usala únicamente cuando estés seguro de que todo el historial de facturación de ese cliente debe desaparecer.
