# 7. CDRs, Trazas SIP y Calidad ASR

Cuando una llamada ya terminó y hay que entender qué pasó con ella —cuánto costó, cuánto se facturó, por qué no se contestó o por qué se cortó— VoxiKam ofrece tres herramientas complementarias, agrupadas en el menú lateral bajo **Tráfico** (CDRs y Trazas SIP) y **Reportes** (Calidad ASR). Este capítulo cubre las tres.

## 7.1 CDRs

Un **CDR** (Call Detail Record, o "registro detallado de llamada") es la ficha completa de una llamada ya finalizada: quién llamó, a qué número, por qué carrier salió, cuánto duró, y —lo más importante para el negocio— cuánto costó comprarla, cuánto se facturó al cliente y cuál fue el margen obtenido.

La pantalla **CDRs** (menú **Tráfico → CDRs**) es el buscador que te permite encontrar ese registro puntual sin tener que revisar un reporte completo del día. Es la herramienta que usás cuando un cliente reclama por una llamada específica, cuando necesitás auditar el costo/margen de un número en particular, o cuando querés confirmar si una llamada realmente se contestó o no.

Referencia visual: `img/admin-cdrs.png`.

En la captura de referencia se observa la estructura de esta pantalla:

1. En la parte superior, dos pestañas que filtran por estado de la llamada: **Contestadas (200 OK)** —activa en la captura— y **No establecidas**. Es decir, podés buscar tanto llamadas que sí se completaron como llamadas que fallaron en algún punto de la señalización.
2. Un formulario de búsqueda con tres campos: **Teléfono (origen o destino)**, para buscar por el número que llamó o por el número al que se llamó; y un rango de fechas (**Desde** / **Hasta**) para acotar la ventana temporal de la búsqueda. Los botones **Buscar** y **Limpiar** ejecutan la consulta o reinician el formulario.
3. Debajo, el área de resultados. En la captura de referencia no se ingresó ningún número todavía, por lo que la pantalla muestra el mensaje **"Ingresá un teléfono (origen o destino) y hacé clic en Buscar."** — es decir, la tabla de resultados con el detalle de cada llamada (costo, venta, margen, duración, etc.) aparece recién después de ejecutar una búsqueda con un número cargado.

En resumen: los CDRs son el punto de partida para cualquier auditoría de una llamada puntual. En lugar de revisar reportes agregados, buscás directamente por el número involucrado y accedés al detalle económico y de estado de esa llamada específica.

## 7.2 Trazas SIP

Los CDRs te dicen **qué pasó** con una llamada (se contestó, no se contestó, cuánto costó), pero no te dicen **por qué**. Para ese nivel de detalle técnico existe la pantalla **Trazas SIP** (menú **Tráfico → Trazas SIP**).

Una traza SIP es la captura de los mensajes de señalización reales que viajaron durante una llamada: **INVITE** (inicio de la llamada), **180 Ringing** (el destino está timbrando), **200 OK** (el destino contestó), **BYE** (fin de la llamada), y así con cualquier otro mensaje o código de error que haya ocurrido en el camino. VoxiKam captura estos mensajes mediante un mecanismo llamado **HEP**, que Kamailio (el proxy SIP del sistema) envía en tiempo real, y los presenta como un **ladder diagram**: un diagrama de escalera donde cada mensaje aparece en el orden en que ocurrió, mostrando quién lo envió y quién lo recibió.

La ventaja de esta herramienta es que permite diagnosticar el problema de una llamada **sin necesidad de abrir una consola SSH ni usar un capturador de paquetes externo** (como tcpdump o Wireshark). Todo el flujo de señalización queda visible directamente en el panel de administración.

Referencia visual: `img/admin-traces.png`.

La pantalla tiene dos modos, disponibles como pestañas en la parte superior: **Stream en vivo** —activa en la captura— y **Buscar llamada**. En el modo stream en vivo se ven tres controles: **Iniciar stream**, **Actualizar** y **Limpiar**, junto con un contador de mensajes recibidos.

En la captura de referencia, el contador marca **"0 mensajes"** y el área principal muestra el aviso **"Presiona 'Iniciar stream' para ver tráfico en vivo"**. Esto es así porque el ambiente de demo no tiene tráfico SIP real corriendo (Kamailio no está activo en este entorno). En una instalación en producción, con Kamailio activo y llamadas circulando, al presionar **Iniciar stream** este panel se llena con el flujo de mensajes SIP en tiempo real —INVITE, 180, 200 OK, BYE, etc.— de todas las llamadas que van pasando por el sistema.

Desde ese stream, o directamente desde la pestaña **Buscar llamada** ingresando el **Call-ID** de una llamada puntual, se puede abrir el ladder diagram de esa llamada específica y revisar mensaje por mensaje qué ocurrió: si el destino nunca respondió, si hubo un rechazo con un código de error, en qué punto exacto se cortó la comunicación, etc.

En resumen: las Trazas SIP son la herramienta de diagnóstico técnico de VoxiKam. Cuando un CDR te dice que una llamada falló pero no alcanza para saber la causa, acá es donde se reconstruye la conversación SIP completa para encontrar el motivo exacto.

## 7.3 Calidad ASR

La tercera pieza del rompecabezas es entender, no ya una llamada puntual, sino el **comportamiento general** del tráfico: ¿qué porcentaje de las llamadas se están contestando? ¿Hay algún cliente o algún horario con un problema recurrente? Para esto existe la pantalla **Calidad ASR** (menú **Reportes → Calidad ASR**).

**ASR** significa **Answer Seizure Ratio**: el porcentaje de llamadas que fueron efectivamente contestadas sobre el total de llamadas intentadas. Un ASR bajo es una señal de alerta —puede indicar un problema de terminación con un destino o un carrier específico— y esta pantalla permite verlo desglosado **por cliente y por hora**, junto con el detalle de los códigos de error más comunes que explican las llamadas no contestadas:

- **487**: la llamada fue terminada por el llamante antes de que el destino contestara (cuelgue anticipado).
- **486**: el destino está **ocupado**.
- **404**: el destino **no fue encontrado** (número inexistente o mal enrutado).
- **503**: el **servicio no está disponible** (el carrier o el destino no puede atender la llamada en ese momento).

Ver la proporción de estos códigos ayuda a distinguir un problema de comportamiento del usuario (487) de un problema de red o de terminación (404, 503) o de saturación del destino (486).

Referencia visual: `img/admin-quality.png`.

En la captura de referencia se observa la estructura de esta pantalla:

1. Un subtítulo que aclara el propósito de la pantalla: **"Answer-Seizure Ratio · resumen horario por cliente"**.
2. Un formulario de filtro con un campo de **Fecha**, un selector de **Cliente** (con la opción **Todos** para ver el consolidado) y un botón **Filtrar**.
3. Debajo, la sección **Detalle por hora**, que en producción muestra la tabla o gráfico con el % de ASR por cliente y por hora, junto con el desglose de los códigos 487/486/404/503. En la captura de referencia, esta sección muestra el mensaje **"Sin datos para esta fecha"**, ya que el ambiente de demo no tiene tráfico registrado para el día consultado.

En resumen: Calidad ASR es la vista de negocio que complementa a los CDRs y a las Trazas SIP. Mientras las Trazas SIP te ayudan a diagnosticar una llamada puntual, Calidad ASR te ayuda a detectar patrones —un cliente con ASR bajo, una franja horaria problemática, un pico de código 503 que sugiere que un carrier está fallando— antes de que se conviertan en un reclamo.
