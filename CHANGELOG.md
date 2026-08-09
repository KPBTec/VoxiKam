# CHANGELOG

Historial de versiones de **VoxiKam**, la plataforma de facturación SIP Class 4. Este changelog resume los cambios desde la perspectiva de quien opera la plataforma (nuevas funciones, mejoras y correcciones), sin detalles internos de implementación.

Todas las versiones siguen el esquema `MAJOR.MINOR.PATCH`:
- **MAJOR**: cambios de arquitectura o cambios importantes de compatibilidad.
- **MINOR**: nuevo módulo o mejora significativa.
- **PATCH**: corrección de errores, ajustes de interfaz, mejoras menores.

---

## v2.55.10 — 2026-08-09

- Nuevo: instalación en un solo paso. Ahora se puede instalar VoxiKam con `wget` + `sudo bash install.sh`, sin necesidad de clonar el repositorio a mano primero. El método anterior (clonar y correr `deploy.sh`) sigue funcionando igual.

---

## v2.55.9 — 2026-08-09

- Cambio interno de organización del código, sin impacto para el usuario.

---

## v2.55.8 — 2026-08-09

- Cambio interno de organización del código, sin impacto para el usuario.

---

## v2.55.7 — 2026-08-09

- Corregido (importante): los cambios de firewall (agregar/quitar IPs de proveedores) no se aplicaban solos al guardar — quedaban en la base de datos pero el firewall real no se actualizaba hasta una intervención manual. Ahora se aplican al instante, como corresponde.
- Corregido: bajo tráfico alto, el proceso que calcula la facturación podía chocar consigo mismo internamente y frenarse momentáneamente. Requiere una actualización de base de datos (automática, sin pérdida de datos).

---

## v2.55.6 — 2026-08-08

- Corregido: una regla de firewall con un rango de IPs (CIDR) se guardaba correctamente pero nunca se aplicaba de verdad — quedaba descartada en silencio. Si tenías alguna regla así cargada, ahora sí tiene efecto.

---

## v2.55.5 — 2026-08-08

- Nuevo: en Grupos de ruteo ahora se ve claramente qué clientes tienen acceso habilitado a cada grupo (separado de quién lo está usando en este momento), con opción de quitar ese acceso.
- Corregido: un error en la consola del navegador que aparecía en cada carga del panel para usuarios con un tema distinto al predeterminado. No afectaba el funcionamiento, solo generaba ruido en la consola.

---

## v2.55.4 — 2026-08-08

- Corregido: cuando un proveedor no respondía nada a una llamada (caído o inalcanzable), esa llamada fallida no quedaba registrada en el historial. Ahora sí.
- Corregido: los logs internos de reintento entre proveedores mostraban el número de grupo incorrecto — solo afectaba la lectura de logs, no el funcionamiento.

---

## v2.55.3 — 2026-08-08

- Corregido (crítico): en ciertos casos, al cortar una llamada, el otro extremo (cliente o proveedor) podía no enterarse del corte y seguir contando esa llamada como activa más tiempo del real, inflando la duración facturada de llamadas que en realidad ya habían terminado.
- Corregido: al quedarte momentáneamente sin proveedores o troncales activos en un grupo de ruteo, las llamadas nuevas podían quedar sin ninguna respuesta en vez de recibir un rechazo claro.

---

## v2.55.2 — 2026-08-06

- Corregido: en Live, las tarjetas de arriba (Contestadas, Activas por cliente) podían mostrar un número distinto al de la lista de llamadas de abajo. Ahora siempre coinciden.

---

## v2.55.1 — 2026-08-06

- Corregido: en Live, algunas llamadas ya terminadas podían quedar mostradas como si siguieran activas (sin operador/proveedor asignado, duración creciente). Ya no aparecen.
- Corregido en el SBC: una causa de fondo de lo anterior — reintentos de red podían hacer que Kamailio procesara el corte de una llamada dos veces. Requiere una actualización completa (Upgrade) para aplicarse, ya que reinicia Kamailio.

---

## v2.55.0 — 2026-08-02

- Nuevo en la web pública (voxikam.kpbtec.com): selector de idioma Español/English en el nav — toda la página (excepto el historial de versiones) ahora está disponible en inglés.

---

## v2.55.0 — 2026-08-02

- Nuevo: la web pública (voxikam.kpbtec.com) ahora tiene selector de idioma Español/English.
- Arreglos menores de diseño en esa misma web (dropdown de tema, íconos, ancho de página).

---

## v2.54.2 — 2026-08-02

- Mejora en la web pública (voxikam.kpbtec.com): el selector de tema del menú ahora es un desplegable con los 4 temas listados, no círculos de color sueltos.

---

## v2.54.1 — 2026-08-02

- Simplificado: Reportes → Consumos ya no repite las vistas por país/grupo/prefijo — esas viven en Reportes → Por destino, con más detalle (calidad de llamada y país incluidos).
- Mejoras menores en la web pública (voxikam.kpbtec.com): más claro qué hacen los círculos de color del selector de tema.

---

## v2.54.0 — 2026-08-02

- Nuevo: **Proveedores** — agrupá varias troncales/carriers del mismo proveedor real (ej. varias rutas de un mismo vendor) y mirá tus reportes también agrupados por proveedor, no solo por carrier individual. Nueva pantalla en Ruteo → Proveedores.
- Mejorado: **IPs de clientes** — ahora se ve una tabla de clientes y al hacer clic se abre el detalle de sus IPs autorizadas, donde también se pueden editar (antes solo se podían borrar y volver a crear).
- Renombrado: "Área" pasa a llamarse **"Grupo de prefijos"** en reportes y tarifas, para no confundirse con región geográfica.
- Mejorado: el selector de tema visual ahora vive dentro del menú lateral (sección "Apariencia"), y el logo de la barra lateral es un acceso directo al inicio.
- Mejorado: la ficha de cliente y la pantalla de Perfiles muestran menos información redundante — más limpio de un vistazo.

---

## v2.53.3 — 2026-08-02

- Mejoras internas al proceso de actualización (`deploy.sh` más liviano y menos duplicado), sin cambios visibles para el usuario.

---

## v2.53.2 — 2026-08-01

- Mejoras internas al proceso de actualización (`deploy.sh` más liviano), sin cambios visibles para el usuario.

---

## v2.53.1 — 2026-07-30

- Mejoras internas al proceso de actualización (`deploy.sh`), sin cambios visibles para el usuario.

---

## v2.53.0 — 2026-07-30

- Nuevo: 4 temas visuales elegibles desde el panel — Bronce (oscuro, default), Papel (claro), Fósforo (terminal verde) y Vidrio (claro, minimalista). Se elige desde el selector en la barra lateral y se guarda por cuenta, no por navegador — se mantiene igual en cualquier dispositivo donde inicies sesión.

---

## v2.52.5 — 2026-07-30

- Corregido: al crear un cliente nuevo con tipo de facturación "postpago", quedaba guardado como "prepago" hasta que se editaba manualmente. Ahora se guarda correctamente desde la creación.

---

## v2.52.4 — 2026-07-27

- Mejoras internas de mantenimiento y optimización del proceso de despliegue, sin cambios visibles para el usuario.

---

## v2.52.3 — 2026-07-27

- Mejoras internas de estabilidad en las migraciones de base de datos (limpieza de columnas de permisos obsoletas que podían reaparecer tras una actualización).

---

## v2.52.2 — 2026-07-26

- Corregido: en Facturación → Recalcular tarifas y Reset facturación, a veces aparecía el error "Job no encontrado" apenas se iniciaba la operación, aunque el proceso siguiera corriendo bien de fondo. Ahora el sistema espera unos segundos antes de reportar un error real.

---

## v2.52.1 — 2026-07-26

- Corregido: Reset facturación podía fallar con un error de tiempo de espera agotado en instalaciones con mucho tráfico. Ahora corre en segundo plano, con progreso consultable, sin depender de que el navegador espere la respuesta completa.
- Mejorado el respaldo de seguridad que se genera antes de resetear el módulo de facturación, para que no consuma memoria excesiva en instalaciones con mucho historial.

---

## v2.52.0 — 2026-07-26

- Nueva función: Facturación → Reset facturación, para reiniciar por completo el módulo de facturas y recalcular el saldo de cada cliente desde su consumo real (útil para limpiar datos de prueba o inconsistencias acumuladas).
- Antes de resetear, se genera automáticamente un respaldo completo de facturas y movimientos de saldo; la acción requiere confirmación explícita escribiendo una palabra clave.

---

## v2.51.0 — 2026-07-26

- Corregido: el reporte "Por destino" podía seguir mostrando llamadas antiguas como "Sin área" después de correr "Recalcular histórico", aunque ya estuvieran bien clasificadas.
- Nuevo: panel "Historial de balance" en la ficha de cada cliente, con el detalle completo de los movimientos que explican su saldo actual (consumo facturado, ajustes manuales, pagos y recálculos).

---

## v2.50.0 — 2026-07-26

- Reorganización: la gestión de Áreas (crear/editar) pasa a una página propia (Tarifas → Áreas); Reportes → Áreas se renombra a "Por destino" y muestra solo el reporte de rentabilidad.
- Consumos ahora genera el reporte automáticamente al entrar a la página o cambiar el período, sin necesidad de presionar "Generar" cada vez.
- Consumos suma nuevas vistas "Por área" y "Por prefijo", junto a las ya existentes "Por cliente" y "Por carrier".

---

## v2.49.1 — 2026-07-26

- Corrección interna en el cálculo de resúmenes diarios que hacía más lenta cada actualización del sistema de lo necesario.

---

## v2.49.0 — 2026-07-26

- Mejorado: Recalcular tarifas ya no tiene un límite de 50.000 llamadas por corrida — ahora admite rangos de cualquier tamaño.
- La vista previa y la aplicación del recálculo corren en segundo plano con progreso en vivo, en vez de bloquear el navegador durante todo el proceso.
- Rendimiento del recálculo mejorado de forma muy significativa sobre grandes volúmenes de llamadas.

---

## v2.48.2 — 2026-07-26

- Corregido: la página Sistema → Logs a veces no se actualizaba correctamente tras una actualización de la plataforma.
- Mejorado: la clasificación de llamadas por área ahora también cubre llamadas no contestadas (ocupado, sin respuesta, etc.), no solo las contestadas — antes esas quedaban sin área asignada para siempre.

---

## v2.48.1 — 2026-07-25

- Corregido un problema de despliegue que impedía que algunas páginas de Facturas (panel admin y portal de cliente) se actualizaran correctamente en ciertas instalaciones.
- Mejorado: el resumen diario de consumo por área/reseller ya no reprocesa todo el histórico en cada actualización, solo lo pendiente.

---

## v2.48.0 — 2026-07-25

- Nueva página Sistema → Infraestructura: permite activar/desactivar HTTPS, backups automáticos de la base de datos y alertas de infraestructura por correo, todo desde el panel sin necesidad de acceso por consola.
- El panel de backups muestra el estado de la última corrida y una lista de los respaldos disponibles con tamaño y fecha.

---

## v2.47.0 — 2026-07-25

- Corregido un caso raro de doble facturación de una misma llamada bajo alta carga.
- Activado soporte de HTTPS (cifrado) para todo el acceso a la plataforma.
- Activados backups automáticos diarios de la base de datos (antes no existían).
- Mejorada la resiliencia ante fallos: si una actualización del frontend fallara, el sistema restaura automáticamente la versión anterior en vez de quedar caído.
- Nueva alerta automática por correo cuando una tarea programada del sistema deja de funcionar o el disco/memoria del servidor se agotan.
- Reforzada la seguridad general: protección contra inyección de código en varios formularios (nombre de cliente, plantillas de alertas), validación real de archivos subidos (logo de factura), y cierre de un hueco que permitía acceso remoto sin la restricción de IP configurada.
- Password mínimo exigido también en el portal de clientes (ya existía para usuarios administradores).
- Nuevo registro de inicios de sesión exitosos (antes solo se registraban los fallidos).

---

## v2.46.0 — 2026-07-24

- Nuevo sistema de permisos granular por cliente/perfil, que reemplaza los antiguos interruptores simples — permite habilitar o restringir secciones específicas del panel con mucha más flexibilidad.
- Nueva función Recalcular tarifas (admin y reseller): permite recalcular retroactivamente el costo de llamadas ya facturadas cuando cambia una tarifa, con vista previa obligatoria antes de aplicar.
- Marcar una factura como pagada ahora sí actualiza el saldo del cliente automáticamente (antes eran dos registros desconectados entre sí).
- Firewall reorganizado en tres páginas separadas (reglas globales, IPs de clientes, Fail2ban), con soporte para ICMP.
- "Reportes" se renombra a "Consumos"; nueva página Sistema → Logs para ver registros de los servicios sin necesitar acceso por consola.
- Corregido un problema extendido de scroll horizontal en tablas que impedía ver el contenido completo en pantallas angostas (móvil/tablet), incluida la ficha de cliente.
- Revisión de seguridad general: verificación contra inyección SQL, contra scripts maliciosos en el nombre de cliente y en plantillas de alertas, y contra acceso indebido entre cuentas de reseller/cliente.
- El panel ahora muestra la fecha del último despliegue realizado, no solo la de la instalación original.

---

## v2.45.0 — 2026-07-23

- Reorganizado el menú: todos los reportes (consumos, calidad, áreas) ahora viven bajo un único grupo "Reportes" en el panel admin.
- Nuevo reporte de consumo por área/destino disponible también para el cliente final, con desglose de costo por destino.
- Agregadas métricas ASR/ACD/PDD (tasa de contestación, duración promedio, tiempo de post-marcado) al reporte por destino.
- Nuevo desglose de consumo por campaña propia del cliente, útil para quienes operan varias líneas bajo la misma cuenta (por ejemplo, un marcador con varias campañas).

---

## v2.44.0 — 2026-07-23

- Nuevo: los clientes prepago con saldo agotado ya no pueden originar llamadas nuevas (las llamadas ya en curso no se cortan).
- Aviso visual en la ficha del cliente y en el portal cuando un cliente prepago se queda sin saldo.
- Mejorado el reporte de rentabilidad por área para que cargue mucho más rápido en rangos de fechas largos.
- El selector de mes/año en Reportes ahora usa el mismo estilo tanto en el panel admin como en el portal de cliente.
- Corregido: al eliminar un Grupo de ruteo en uso, el mensaje de error ahora indica exactamente qué cliente(s) lo están usando.
- Corregido: en el panel Live, un cliente con varias líneas activas ya no aparecía repetido como si fueran clientes distintos.

---

## v2.43.1 — 2026-07-23

- Corregido: el reporte mensual del portal de cliente cargaba muy lento en instalaciones con mucho tráfico — ahora carga en pocos segundos.
- Corregido: el aviso de "llamadas sin área asignada" en la página Áreas tardaba mucho en calcularse — ahora se actualiza en segundo plano de forma periódica.
- Corregido el mismo tipo de lentitud en el dashboard del reseller (margen del mes).
- El selector de mes/año del portal de cliente ya no ofrece años sin ningún dato disponible.

---

## v2.43.0 — 2026-07-23

- Nuevo: Grupos de ruteo — permite definir un grupo de carriers con un algoritmo de reparto (prioridad, round robin o porcentaje) y asignarlo a cada cliente o campaña, reemplazando el mecanismo anterior de un solo carrier fijo.
- Corregido un bug importante: cambios en la asignación de grupo de ruteo de un cliente no se aplicaban en caliente y requerían un reinicio manual del sistema de telefonía — ahora se aplican solos.
- Nueva página "Entrante" para administrar los pares de red que reciben tráfico entrante, antes solo configurable a mano.
- Panel admin reorganizado: menú lateral reagrupado en Clientes → Red → Ruteo → Tráfico → Facturación → Sistema, con una navegación más intuitiva.
- La ficha de cliente y de sub-cliente de reseller se reorganizó en pestañas (General / Red y Ruteo) para reducir el scroll.

---

## v2.42.0 — 2026-07-16

- Nuevo: un mismo cliente puede tener varios prefijos técnicos (uno por campaña, por ejemplo si opera un marcador con varias campañas), viendo el consumo global y también desglosado por campaña.
- Nuevo reporte de consumo por campaña en el portal de cliente.
- Corregido: el widget "Activas por cliente" del panel Live no identificaba correctamente a los clientes con prefijos de 5 o más dígitos.
- Corregido el simulador de ruteo para que pruebe correctamente contra todos los prefijos de un cliente, no solo el principal.

---

## v2.41.1 — 2026-07-14

- Corregido un bug de facturación importante: llamadas cortas se cobraban como si hubieran durado un minuto completo, en vez de cobrarse por el tiempo real hablado. Afectaba a todos los planes de venta y a todos los carriers de compra.
- Nueva herramienta de recálculo para corregir retroactivamente llamadas ya facturadas con el error anterior, acreditando la diferencia al saldo del cliente afectado.
- Corregido: crear un cliente sin un plan de tarifas asignado ya no genera llamadas facturadas en cero en silencio — ahora es un campo obligatorio al alta.
- Mejorado el indicador de "Calidad" de una llamada: ahora muestra también el jitter/pérdida de paquetes promedio de toda la llamada, además del peor pico puntual, evitando que un solo pico aislado marque como "mala" una llamada que en realidad estuvo bien.
- Corregido: asignar un carrier sin tarifas de compra cargadas ya no es posible — antes se podía enrutar tráfico real sin registrar ningún costo. El panel de Carriers ahora marca con una advertencia a los que no tienen tarifas.
- Corregido: el gráfico "Por carrier" del dashboard en vivo siempre mostraba "Sin nombre" — ahora identifica correctamente el carrier de cada llamada activa.

---

## v2.41.0 — 2026-07-12

- Mejorada la infraestructura de almacenamiento de Trazas SIP para soportar un volumen mucho mayor sin quedarse sin espacio en disco, manteniendo la misma política de retención ya configurada.
- Sin cambios visibles: el ladder diagram y la descarga de trazas en formato .pcap funcionan igual que antes.

---

## v2.40.2 — 2026-07-11

- Corregido un problema de permisos: un reseller podía ver y asignar carriers de la plataforma que el administrador nunca le había habilitado.
- El prefijo técnico de un sub-cliente de reseller ahora se genera siempre automáticamente (ya no se puede editar a mano), evitando errores de configuración.

---

## v2.40.1 — 2026-07-11

- Corregido: el detalle de una llamada mostraba una sola cifra de "Duración" mezclando el tiempo de timbrado con el tiempo realmente hablado. Ahora se muestran por separado ("Duración total" y "Tiempo hablado").

---

## v2.40.0 — 2026-07-09

- Auditoría de seguridad completa de toda la plataforma (backend, frontend y componentes de telefonía): se corrigieron varias vulnerabilidades conocidas de las librerías utilizadas, incluida una falla crítica de autenticación en el backend.
- Actualizado el motor de conmutación de llamadas a una versión más reciente para nuevas instalaciones, cerrando una falla de seguridad conocida.
- Identificada una vulnerabilidad en el motor de audio sin una solución compatible disponible todavía para el sistema operativo usado — documentada para una futura actualización de infraestructura.

---

## v2.39.1 — 2026-07-09

- Corregido: el acceso a la sección "API Keys" y a los módulos del portal de reseller no respetaba correctamente el permiso configurado por el administrador tras iniciar sesión.
- Corregidas varias páginas del panel que no mostraban un error visible cuando fallaba la carga de datos.
- Corregido: el botón "Recalcular histórico" en Áreas quedaba deshabilitado para siempre después del primer uso.

---

## v2.39.0 — 2026-07-09

- Nueva página "Mis API Keys" en el portal de cliente, para crear, ver y revocar claves de acceso a la API.
- Nuevo botón para banear/liberar una IP directamente desde Firewall (antes solo se veía el estado, sin poder actuar).
- Mejorado el manejo de errores en gran parte del panel admin y de cliente: ahora se muestra un aviso claro cuando falla la carga de datos, en vez de dejar la pantalla en blanco o cargando indefinidamente.

---

## v2.38.0 — 2026-07-09

- Cerrado un hueco de seguridad crítico en el mecanismo interno de registro de llamadas.
- Corregido un bug de facturación: la configuración de "segundos del primer bloque" se guardaba pero nunca se aplicaba al cálculo real de la tarifa.
- Corregido: dos motores internos de cálculo de facturación podían dar resultados distintos para la misma llamada según qué camino la procesara — ahora siempre coinciden.
- Corregido: desactivar una tarifa desde el panel no siempre la sacaba de circulación en la facturación real.
- Reforzada la seguridad de sesión, eliminando un valor de respaldo inseguro que en un escenario de mala configuración podía permitir el acceso con credenciales falsificadas.
- Corregido: una factura que fallaba al generar su PDF no dejaba ningún rastro visible para el administrador — ahora el error queda registrado.
- Corregida la página "Trunk Guide" del portal de cliente, que se quedaba cargando indefinidamente si fallaba la consulta.

---

## v2.37.1 — 2026-07-09

- Mejoras internas de consistencia visual y de código, sin cambios funcionales visibles.

---

## v2.37.0 — 2026-07-09

- Corregido un bug de ruteo: dos clientes con un prefijo técnico donde uno es prefijo del otro (por ejemplo "100" y "1005") podían colisionar, haciendo que las llamadas de uno se facturaran al otro. Ahora la validación detecta también este caso.
- Nuevo: el administrador puede habilitar o restringir, por cada reseller, qué secciones ve en su portal (Sub-clientes, Tarifas propias, Carriers propios, Resumen) — antes un reseller siempre veía las cuatro sin poder restringirse.

---

## v2.36.0 — 2026-07-09

- Corregido un bug de ruteo/facturación: no existía validación de que el prefijo técnico de un cliente fuera único — dos clientes con el mismo prefijo hacían que las llamadas del segundo se facturaran al primero. Ahora se valida automáticamente en todos los casos.
- Nueva página "Resellers" separada de "Clientes", con conteo de sub-clientes por reseller.

---

## v2.35.0 — 2026-07-09

- Nuevo: un reseller ahora puede cargar sus propias troncales SIP (carriers) con sus propias tarifas de costo, y asignarlas a sus sub-clientes junto con (o en vez de) las de la plataforma.

---

## v2.34.1 — 2026-07-08

- Ampliado el registro de Auditoría para cubrir acciones que antes no dejaban rastro: cambios de tarifas y prefijos, generación y marcado de facturas como pagadas, configuración de correo, perfiles de cliente, y encendido/apagado de servicios del sistema.

---

## v2.34.0 — 2026-07-08

- Corregido: la traza SIP de una llamada (diagrama de secuencia) ahora también muestra el tramo de entrada (origen → sistema), que antes faltaba, sin generar registros duplicados.

---

## v2.33.4 — 2026-07-08

- Agregada una guía con ejemplos de uso del comando de administración del sistema directamente en el panel Sistema → Salud.

---

## v2.33.3 — 2026-07-08

- Mejorada la velocidad de búsqueda de llamadas por teléfono y fecha (hasta el doble de rápido en búsquedas comunes).
- Corregido: las tareas programadas podían mostrarse en rojo por errores antiguos aunque las corridas más recientes estuvieran bien — ahora Sistema → Salud refleja siempre el estado más reciente.
- Detalle de llamada: "Resultado", "Código SIP" y "Quién colgó" ahora son filas separadas y más claras.
- Nuevo semáforo de calidad (verde/amarillo/rojo), fácil de interpretar sin conocimientos técnicos.
- Corregido: la traza SIP no mostraba el tramo de entrada de cada llamada, solo el de salida.

---

## v2.33.2 — 2026-07-08

- Corregido un error interno de permisos que podía impedir el arranque de un servicio del sistema tras una actualización.

---

## v2.33.1 — 2026-07-08

- Mejoras internas de administración de servicios del sistema operativo, sin impacto funcional.

---

## v2.33.0 — 2026-07-08

- Nueva función: Plantilla de factura editable (Reportes → Plantilla de factura) — permite personalizar el logo, encabezado de empresa, pie de página y color de acento del PDF de las facturas, sin modificar la estructura de la tabla de llamadas.

---

## v2.32.0 — 2026-07-08

- Nuevo CLI de administración para reiniciar servicios y ver logs sin necesidad de recordar nombres técnicos.
- Nueva tarjeta en Sistema → Salud con el estado de los servicios propios de la plataforma y sus últimos registros.
- Nueva sección para ver, y en una lista permitida apagar/reencender, otros servicios del sistema operativo desde el panel.
- Sistema → Correo rediseñado: ahora soporta tanto un proveedor de correo externo como un servidor SMTP propio, con explicación de cada opción y un botón de "Enviar correo de prueba".

---

## v2.31.0 — 2026-07-08

- Corregido: un área recién creada sin prefijos asignados no podía aparecer en el selector al crear un nuevo prefijo, quedando "atrapada" sin forma de asignarle nada desde el panel.
- Ahora se puede editar un prefijo de destino existente directamente (antes solo se podía crear o borrar).
- Nuevo: un reseller puede crear sus propios prefijos y grupos de destino, igual que el administrador, y usarlos junto con los de la plataforma en sus propias tarifas.

---

## v2.30.0 — 2026-07-08

- El Dashboard se simplificó: el diagnóstico técnico interno (tareas programadas, captura de trazas) se movió a la nueva página Sistema → Salud, dejando el Dashboard enfocado en indicadores de negocio.
- La tabla "Llamadas activas por cliente" del Dashboard se reemplazó por un resumen compacto, con enlace directo a Live para ver el detalle completo.

---

## v2.29.0 — 2026-07-08

- Corregido un problema donde, tras reiniciar el servidor completo, el sistema de telefonía y el motor de audio podían quedar caídos y requerir un reinicio manual — ahora arrancan solos de forma confiable.
- Corregido un bug serio: los PDF de facturas ya generadas se borraban en cada actualización de la plataforma, dejando el enlace de descarga roto. Ahora se preservan, y las facturas afectadas antes de este fix se pueden regenerar sin perder el historial de llamadas.

---

## v2.28.2 — 2026-07-08

- Corregido: en instalaciones con dos interfaces de red, la traza SIP mostraba una de las IPs del propio sistema como si fuera "Destino" en vez de identificarla correctamente.
- Rediseñado el detalle de CDR con un layout de tabla más ordenado; el costo de compra ya no se muestra en rojo, para no confundirse con una alerta.

---

## v2.28.1 — 2026-07-08

- Corregido: llamadas interrumpidas por un reinicio del sistema (que sí se contestaron pero no llegaron a facturarse) ya no se contaban como "fallidas" en las métricas de tasa de contestación (ASR), tanto en el dashboard como en reportes y en el portal de cliente.
- Corregido: editar un sub-cliente de reseller ahora queda registrado en Auditoría (antes no dejaba rastro).
- Los sub-clientes desactivados ahora se ocultan por defecto en el listado del reseller.

---

## v2.28.0 — 2026-07-08

- Nueva interfaz completa para la reventa multinivel: el administrador puede convertir un cliente en reseller desde su ficha, y el reseller obtiene un portal propio para ver el margen del mes, administrar sus sub-clientes y sus propios planes de tarifas.

---

## v2.27.0 — 2026-07-07

- Corregido: las búsquedas de llamadas por teléfono y fecha eran muy lentas (varios segundos) — ahora son notablemente más rápidas.
- El "Detalle de llamada" en CDRs ya no se abre como ventana emergente — se muestra integrado en la misma pantalla de resultados.
- La pantalla de CDRs ahora abre mostrando el día de hoy por defecto, en vez de escanear todo el historial sin ninguna fecha.
- Corregido: filtrar Calidad ASR por un cliente específico daba un error en vez de aplicar el filtro.
- Nuevo interruptor para activar/desactivar el correo de aviso de llamadas interrumpidas por reinicio del sistema.

---

## v2.26.0 — 2026-07-07

- Corregido un problema importante: si el sistema de telefonía se reiniciaba con llamadas en curso, esas llamadas se contestaban pero nunca se registraban ni facturaban, sin dejar ningún rastro. Ahora se archivan automáticamente con una marca especial ("interrumpida por reinicio") y se notifica por correo al administrador para revisión manual.

---

## v2.25.0 — 2026-07-07

- Cambiado el comportamiento de "Eliminar cliente": ahora desactiva al cliente en vez de borrarlo permanentemente, evitando perder el historial de llamadas asociado. Se puede reactivar en cualquier momento.
- Corregido: un usuario del portal de un cliente recién desactivado podía seguir con su sesión iniciada por un tiempo — ahora se bloquea de inmediato.

---

## v2.24.19 — 2026-07-07

- Corregido: intentar borrar un cliente con facturas o historial asociado ya no muestra un error genérico del sistema — ahora explica claramente por qué no se puede borrar.

---

## v2.24.18 — 2026-07-07

- Agregada la base para una futura API pública de consulta de saldo y llamadas para clientes, con autoservicio de claves de acceso propias.
- Agregada la base técnica para la reventa multinivel (resellers), todavía sin interfaz visible en esta versión.

---

## v2.24.17 — 2026-07-07

- La traza SIP completa de una llamada ahora se puede ver directamente desde su detalle en CDRs, sin necesitar ir a la página de Trazas SIP por separado.
- La pantalla de CDRs ya no carga automáticamente todas las llamadas al abrir — ahora requiere una búsqueda explícita, evitando cargas lentas innecesarias.
- La retención de Trazas SIP puede configurarse hasta 6 meses (antes 30 días); los CDRs (registros de facturación) nunca se borran.

---

## v2.24.16 — 2026-07-07

- Simplificada la tabla principal de CDRs a las columnas esenciales (Fecha, Origen, Destino, Cliente, Tiempo); el resto de los detalles (carrier, costos, calidad, etc.) se ve al hacer clic en cada llamada.
- El detalle de calidad ahora muestra también la cantidad de paquetes perdidos, no solo el porcentaje.

---

## v2.24.15 — 2026-07-07

- Corregido: el gráfico "Llamadas por minuto" del Dashboard mostraba huecos en cero de forma intermitente cuando había mucho tráfico simultáneo. Ahora se mantiene preciso incluso con alto volumen de llamadas concurrentes.

---

## v2.24.14 — 2026-07-06

- Mejoras internas de registro (logs) y validación del motor de audio, sin impacto funcional para el usuario.

---

## v2.24.13 — 2026-07-06

- Mejoras internas de organización de logs del sistema (separación y rotación diaria).

---

## v2.24.12 — 2026-07-06

- Nuevo: el usuario administrador principal (creado en la instalación) queda protegido — ningún otro administrador puede desactivarlo ni resetear su contraseña.

---

## v2.24.11 — 2026-07-06

- Mejorada la capacidad del sistema de captura de trazas SIP ante picos de tráfico, reduciendo el riesgo de perder paquetes durante ráfagas de llamadas.
- Nuevo indicador de "Descartes de kernel" en el Dashboard, para detectar si el sistema está perdiendo paquetes por falta de capacidad.

---

## v2.24.10 — 2026-07-06

- Nueva tarjeta en el Dashboard mostrando la capacidad y el estado de la cola de captura de trazas SIP, para anticipar si el sistema necesita más recursos.

---

## v2.24.9 — 2026-07-06

- Nuevo: cada llamada contestada muestra ahora su calidad de audio real (jitter y % de pérdida de paquetes), sin necesitar herramientas externas.
- Agregado un límite de seguridad para evitar que picos de tráfico saturen la memoria del sistema de captura de calidad.

---

## v2.24.8 — 2026-07-06

- Corregido un bug crítico: bajo ciertas condiciones, el panel Live podía borrar por error el registro de llamadas activas reales en curso. Ahora se protege contra esa condición y se muestra un aviso visible si el dato en vivo no es confiable, en vez de mostrar ceros engañosos.

---

## v2.24.7 — 2026-07-06

- Corregido: varios botones del panel no mostraban el cursor de "mano" al pasar el mouse por encima.

---

## v2.24.6 — 2026-07-05

- Mejorado el diseño de los indicadores de CPU/RAM del Dashboard (ya no se superponen visualmente) y agregado un tercer indicador de uso de Disco.
- Rediseñada la sección de tareas programadas con un resumen de estado más claro.

---

## v2.24.5 — 2026-07-05

- Corregido: el menú lateral no se adaptaba a pantallas angostas y tapaba el contenido en dispositivos móviles/tablets — ahora se convierte en un menú desplegable.
- Mejorada la animación de apertura/cierre de los grupos del menú.

---

## v2.24.4 — 2026-07-05

- Corrección interna de un valor de configuración obsoleto sin efecto real, que solo generaba confusión en los registros de instalación.

---

## v2.24.3 — 2026-07-05

- La configuración de correo (antes mezclada dentro de Alertas de balance) se movió a un panel propio, Sistema → Correo, ya que la usan varias funciones distintas.
- Nuevo botón "Recalcular histórico" en Áreas para clasificar correctamente llamadas antiguas que habían quedado sin área asignada.

---

## v2.24.2 — 2026-07-05

- Mejorado el diseño de la sección de tareas programadas del Dashboard, que antes se veía amontonada.

---

## v2.24.1 — 2026-07-05

- Corregido: el menú lateral podía dejar varios grupos abiertos a la vez, dificultando saber en qué sección se estaba — ahora funciona como acordeón (un solo grupo abierto a la vez).

---

## v2.24.0 — 2026-07-05

- El menú lateral del panel admin se reorganizó en grupos colapsables (Clientes/Red/Tarifas/Tráfico/Reportes/Alertas/Sistema) para facilitar la navegación a medida que crecieron las funciones disponibles.

---

## v2.23.0 — 2026-07-05

- Nueva sección de "Notas internas" en la ficha de Cliente y de Carrier, para dejar comentarios con fecha y autor que se van acumulando (a diferencia del campo de notas anterior, que se sobrescribía en cada edición).

---

## v2.22.0 — 2026-07-05

- Nuevo: opción para enviar automáticamente la factura por correo al generarla, con el PDF adjunto.
- Nuevo botón para reenviar manualmente cualquier factura, incluidas las más antiguas.

---

## v2.21.0 — 2026-07-05

- Nuevo: importar tarifas masivamente desde un archivo CSV (dentro de un borrador revisable antes de publicar) y exportar tarifas vigentes a CSV.

---

## v2.20.0 — 2026-07-05

- Nueva función Pricelists: permite preparar un borrador de cambios de tarifas, revisar qué precios subirían o bajarían antes de aplicar, y publicar o descartar el borrador sin afectar la facturación en curso.

---

## v2.19.0 — 2026-07-05

- Nuevo panel para configurar cuánto tiempo se conservan las trazas SIP capturadas (antes fijo en "solo el día de hoy").

---

## v2.18.0 — 2026-07-05

- Nuevo simulador de ruteo: permite ver, para un cliente y destino dados, qué tarifa se cobraría y por qué carrier saldría la llamada, sin necesidad de originar una llamada real.

---

## v2.17.0 — 2026-07-05

- Nueva función Disconnect Policies: alerta por correo/webhook cuando un cliente supera cierto porcentaje de llamadas cortadas por un motivo específico (ocupado, no encontrado, etc.) — solo informa, no corta el servicio.

---

## v2.16.0 — 2026-07-05

- Nuevo: soporte para Webhooks — notificaciones automáticas a una URL propia cuando se crea un CDR, hay una alerta de saldo, o cambia el estado de un cliente.

---

## v2.15.0 — 2026-07-05

- Nueva función de sincronización externa de CDRs hacia una base de datos propia (MySQL, PostgreSQL o SQL Server), útil para conectar herramientas de reportería externas sin tocar la base de datos de producción.

---

## v2.14.0 — 2026-07-05

- Nuevo indicador de estado de las tareas programadas del sistema en el Dashboard.

---

## v2.13.0 — 2026-07-05

- Nueva función Áreas: agrupa prefijos de destino y muestra un reporte de rentabilidad (llamadas, minutos, compra, venta, margen) por área para un rango de fechas.

---

## v2.12.0 — 2026-07-04

- Mejoras internas de rendimiento en el almacenamiento de llamadas y trazas SIP, pensadas para instalaciones con mucho volumen.

---

## v2.11.0 — 2026-07-04

- Nuevo panel de Auditoría: registra cambios importantes (clientes, carriers, firewall, alertas, usuarios admin) con quién los hizo, cuándo y qué cambió.

---

## v2.10.0 — 2026-07-04

- Nuevo panel de Usuarios: permite crear varias cuentas de administrador individuales (antes todo el equipo compartía una sola cuenta), con opción de desactivar o resetear contraseña.

---

## v2.9.0 — 2026-07-04

- Nuevo: alertas automáticas por correo cuando el saldo de un cliente prepago o postpago cruza un umbral configurable.
- Nuevo historial de movimientos de saldo (ledger), para poder reconstruir por qué el saldo de un cliente es el que es.
- Nuevo campo "tipo de facturación" (prepago/postpago) configurable por cliente.

---

## v2.8.9 — 2026-07-03

- Corregido: no era posible editar el email de un cliente desde el panel (el campo faltaba en el formulario, aunque el sistema sí lo soportaba).
- Corregido: la traza SIP no capturaba el mensaje de "colgado" de la llamada, dando la falsa impresión de que la llamada nunca terminaba.
- Nueva función: descargar la traza SIP de una llamada como archivo .pcap para analizar con herramientas externas.
- Corregido: navegar desde el detalle de una llamada a su traza SIP podía tardar varios segundos o no mostrar nada.
- Mejoras varias en el portal de cliente: quitada una tabla redundante en el resumen, corregido el nombre mostrado en la leyenda del gráfico de llamadas, y mejorado el selector de mes en Reportes.

---

## v2.8.8 — 2026-07-02

- Corregido un mensaje de diagnóstico interno engañoso sobre reintentos de carrier fallidos, sin impacto en el enrutamiento real de llamadas.

---

## v2.8.7 — 2026-07-02

- Corregido: tras un reinicio completo del servidor, el sistema de telefonía podía arrancar antes de que la base de datos estuviera lista, causando fallos — ahora espera correctamente.

---

## v2.8.6 — 2026-07-02

- Corregido un límite de sesiones de audio concurrentes que podía reaparecer accidentalmente tras una actualización y provocar rechazo de llamadas bajo alto tráfico.

---

## v2.8.5 — 2026-07-02

- Corregido un problema visual donde la insignia de versión se superponía con el pie de página del panel.

---

## v2.8.4 — 2026-07-01

- Corregido: llamadas rechazadas (ocupado, no encontrado, sin carrier disponible) podían dejar sesiones de audio abiertas innecesariamente en el servidor. Ahora se liberan de inmediato en todos los casos: llamada contestada y colgada, cancelada, o rechazada.

---

## v2.8.3 — 2026-07-01

- Corregido un error crítico de instalación que podía impedir el arranque de los servicios al migrar desde una instalación anterior de la plataforma.

---

## v2.8.2 — 2026-07-01

- Corregida la migración automática desde instalaciones anteriores de la plataforma para que tome correctamente todas las credenciales necesarias.

---

## v2.8.1 — 2026-07-01

- Mejoras internas de organización de archivos de configuración, sin impacto funcional.

---

## v2.8.0 — 2026-07-01

- Mejorado el auto-ajuste de recursos del sistema de telefonía: ahora también se recalcula automáticamente en cada arranque del servidor, no solo al ejecutar una actualización manual.

---

## v2.7.4 — 2026-07-01

- Ajustado el uso de memoria del sistema de telefonía para dar más margen de seguridad en servidores con más RAM disponible.

---

## v2.7.3 — 2026-07-01

- Ajuste automático del número de procesos del sistema de telefonía según la cantidad real de procesadores del servidor (antes era un valor fijo).

---

## v2.7.2 — 2026-07-01

- Corregido un bug importante: las sesiones de audio no se liberaban al colgar una llamada con normalidad, acumulándose hasta expirar solas por tiempo agotado — podía degradar la capacidad del sistema con el tiempo.

---

## v2.7.1 — 2026-07-01

- El uso de memoria del sistema de telefonía ahora se ajusta automáticamente según la RAM real del servidor, en vez de usar un valor fijo.

---

## v2.7.0 — 2026-07-01

- Nuevo: migración automática y segura desde instalaciones de la versión anterior de la plataforma, preservando todos los datos existentes.

---

## v2.6.5 — 2026-07-01

- Mejoras internas de mantenimiento del código fuente, sin impacto para el usuario.

---

## v2.6.4 — 2026-07-01

- Corregido un límite importante de capacidad: el sistema de telefonía tenía un límite de memoria por defecto que restringía el número de llamadas simultáneas muy por debajo del hardware disponible. Ahora se ajusta según la memoria real del servidor.

---

## v2.6.3 — 2026-07-01

- Mejorado el rendimiento de la validación de sesión, reduciendo la carga sobre la base de datos en pantallas con actualización en vivo (por ejemplo, Trazas SIP).

---

## v2.6.2 — 2026-07-01

- El número de procesos del backend ahora se ajusta automáticamente al tamaño del servidor.

---

## v2.6.1 — 2026-07-01

- Nueva sección en Firewall para ver y desbanear IPs bloqueadas automáticamente por intentos sospechosos.
- Corregidos varios problemas que podían impedir que la protección automática contra intentos de acceso indebido arrancara correctamente en el servidor.

---

## v2.6.0 — 2026-07-01

- Nueva protección automática: bloqueo temporal de IPs tras varios intentos fallidos de inicio de sesión o actividad de escaneo sospechosa.
- Esquema de numeración de versiones homogeneizado (sin impacto para el usuario).

---

## v2.5 — 2026-06-30

- Nueva identidad visual: paleta de colores, tipografía y diseño renovados en toda la plataforma.
- El número de versión mostrado en el panel ahora siempre está actualizado.

---

## v2.4 — 2026-06-30

- Nuevo logo y rediseño visual de la pantalla de inicio de sesión y del menú lateral.

---

## v2.3 — 2026-06-25

- El instalador ahora instala automáticamente los componentes de telefonía si no están presentes, sin pasos manuales previos.
- El instalador muestra el tiempo total de instalación y un enlace para reportar comentarios.

---

## v2.2 — 2026-06-22

- El panel "En vivo" (Live) ahora obtiene los datos directamente del sistema de telefonía en tiempo real, evitando registros fantasma.
- CDRs separado en dos pestañas: llamadas contestadas y llamadas no establecidas, con filtros rápidos por código de resultado.
- Nuevo modo de actualización rápida que actualiza código y base de datos sin afectar el sistema de telefonía ni cortar llamadas activas.

---

## v2.1 — 2026-06-22

- Corregido: llamadas que quedaban "colgadas" en el registro de llamadas activas sin cerrarse nunca. Ahora se limpian automáticamente tras un tiempo máximo, con opción de limpieza manual desde el panel.
- La búsqueda de trazas SIP pasó de tardar hasta 14 segundos a menos de 100 milisegundos en la mayoría de los casos.

---

## v2.0 — 2026-06-22

- Ajustes de rendimiento en todo el sistema para reducir la pérdida de paquetes de audio durante picos de tráfico y aumentar la capacidad de llamadas simultáneas soportadas.

---

## v1.9 — 2026-06-22

- Nuevo gráfico de llamadas por minuto en el Dashboard, con selector de rango de tiempo, disponible también en el portal de cliente.
- Nueva columna "Estado de llamada" en CDRs (completada, ocupado, cancelada, rechazada, transferida), con colores.

---

## v1.7 — 2026-06-21

- El administrador ahora puede crear acceso al portal para un cliente directamente desde su ficha.
- Las reglas de Firewall ahora permiten restringir por tipo de servicio (SIP, RTP, SSH), no solo abrir todo el tráfico.
- Corregido un bug de facturación relacionado con la normalización de números de destino.

---

## v1.6 — 2026-06-21

- Nueva función: ver el flujo completo de señalización SIP de cualquier llamada directamente desde el navegador, sin necesidad de acceso técnico al servidor. Incluye búsqueda por número o identificador de llamada y vista en vivo del tráfico SIP.

---

## v1.5

- Nuevo portal de cliente: resumen de saldo, llamadas del mes, facturas y guía de configuración SIP.
- Nueva función de Facturación: generación de facturas en PDF por cliente y período.

---

## v1.0

- Primera versión de VoxiKam: instalador de un solo comando, panel de administración completo (clientes, carriers, tarifas, firewall, reportes, facturas), dashboard de llamadas en vivo, y gestión de firewall desde el panel.
