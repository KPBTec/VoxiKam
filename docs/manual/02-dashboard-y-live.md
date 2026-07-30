# 2. Dashboard y Llamadas en curso

Al iniciar sesión en VoxiKam, el panel de administración te lleva directo al **Dashboard**. Esta es la pantalla de inicio y su objetivo es darte una vista rápida del estado del negocio sin tener que entrar a ningún reporte: cuánto tráfico hay, cuánto se ha facturado en el día y si el sistema está saludable.

## 2.1 Dashboard

El Dashboard reúne, en una sola pantalla, los indicadores clave (KPIs) del día:

- **Llamadas activas** en este momento.
- **Llamadas completadas** en el día.
- **Minutos** cursados.
- **Ingresos** del día.
- **ASR global** (tasa de respuesta de llamadas), junto con un gráfico de tráfico desglosado **por cliente**.

Además de estos indicadores de negocio, el Dashboard muestra la **salud básica del servidor**: uso de CPU, uso de RAM y uso de disco, para que puedas detectar de un vistazo si el equipo está bajo estrés antes de que eso afecte el servicio.

Referencia visual: `img/admin-dashboard.png`.

En la captura de referencia (tomada en un ambiente de demostración, sin tráfico real circulando) se puede ver la estructura de la pantalla:

1. En la parte superior, tres medidores circulares con el estado del sistema: **CPU 22%**, **RAM 90% (6.8 / 7.6 GB)** y **Disco 24%**. Un uso de RAM tan alto como el mostrado (90%) es un valor a vigilar en un servidor real, aunque en este caso corresponde a las características del ambiente de demo.
2. Un aviso indicando que el snapshot de llamadas activas de Kamailio no se está actualizando. Esto ocurre cuando el proceso de Kamailio no está corriendo en el servidor, como sucede en este entorno de demostración; en una instalación en producción, con Kamailio activo, este aviso no aparece y el indicador de llamadas activas se actualiza con normalidad.
3. Las tarjetas de KPIs del día: **Activas ahora**, **Llamadas hoy**, **Facturado hoy** y **Ganancia hoy**. En la captura todos estos valores están en **S/. 0.00** o en **0**, precisamente porque es un ambiente de demo sin tráfico live; en un ambiente productivo con llamadas circulando, estas tarjetas reflejan cifras reales y se actualizan de forma automática.
4. Más abajo, el bloque de **Llamadas por minuto**, con dos gráficos: uno agrupado **por carrier** y otro agrupado **por cliente**, con selectores de rango (1h, 3h, 6h, 12h) para ajustar la ventana de tiempo que se visualiza.

En resumen: el Dashboard es el punto de partida para cualquier operador. Con una sola mirada puedes saber si hay tráfico corriendo, cuánto se ha facturado y ganado en el día, y si el servidor está funcionando dentro de parámetros normales.

## 2.2 Live / Llamadas en curso

La opción **Live**, en el menú lateral, abre la pantalla de **Llamadas en curso**. A diferencia del Dashboard, que resume el día completo, esta pantalla es un **monitor en tiempo real**: muestra exactamente qué llamadas están activas en este preciso momento, sin necesidad de esperar a que ninguna termine ni de generar ningún reporte.

Para cada llamada contestada que está en curso, la tabla muestra:

- **Cliente**: a quién pertenece la llamada.
- **Carrier** en uso: por dónde está saliendo esa llamada.
- **Destino**: el número al que se está llamando.
- **Duración transcurrida**: cuánto tiempo lleva la llamada activa.

Esto es útil para tener una idea inmediata de cuánto tráfico está circulando en un momento dado y por dónde está saliendo, sin depender de reportes que se generan después de que las llamadas finalizan.

Referencia visual: `img/admin-live.png`.

En la captura de referencia se observa la estructura de esta pantalla:

1. Un aviso similar al del Dashboard, indicando que el snapshot de Kamailio no se actualiza y que por lo tanto los contadores de **Contestadas**, **Timbrando** y **Clientes activos** no son confiables en ese momento (de nuevo, esto ocurre porque Kamailio no está corriendo en este ambiente de demo). El mismo aviso aclara que, pese a ello, la tabla de **Llamadas contestadas** de más abajo sigue siendo real porque proviene de otra fuente.
2. Cuatro tarjetas de resumen: **Contestadas**, **Timbrando**, **Clientes activos** y **Mayor tiempo** (la llamada activa con más duración acumulada).
3. La tabla de **Llamadas contestadas**, con las columnas Cliente, Carrier, Origen, Destino, Inicio y Duración. En el ejemplo de la captura aparecen tres llamadas en curso:
   - **Call Center Norte**, vía carrier **Fibra Sur Networks**, hacia el destino **519012345**, con **16m 56s** de duración.
   - **Comercial Andes SAC**, vía carrier **Andino Telecom**, con **15m 31s** de duración.
   - **Distribuidora Milenio**, vía carrier **VoIP Internacional**, con **14m 58s** de duración.

Esta pantalla se actualiza automáticamente (cada 10 segundos, según indica la propia interfaz), por lo que no es necesario refrescar la página para ver los cambios en el tráfico en curso.
