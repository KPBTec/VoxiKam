# 11. Administración del sistema

Este capítulo cubre las pantallas de infraestructura y administración del propio VoxiKam: no son pantallas de operación diaria del negocio (clientes, carriers, tarifas), sino de mantenimiento de la plataforma — cuánto espacio ocupa, quién puede entrar, qué tan sanos están sus servicios internos y cómo se resguarda la información. La mayoría vive en el menú lateral **Sistema**, aunque **Auditoría** está en **Seguridad**, **Usuarios admin** está en **Clientes** y **Entrante** está en **Ruteo** — se agrupan acá porque conceptualmente son todas tareas de administración de la plataforma más que de gestión comercial.

Todas las capturas de este capítulo corresponden a un ambiente de **demo recién instalado**. Por eso varias pantallas aparecen vacías, en "unknown" o con mensajes de "todavía no corrió" — es el estado esperado antes de que el sistema lleve tráfico real y hayan corrido los primeros ciclos de cada proceso automático, no un error de instalación.

## 11.1 Retención de datos

La pantalla **Retención de datos** (menú **Sistema → Retención de datos**) define cuántas horas o días se conservan las **Trazas SIP** capturadas antes de purgarse automáticamente. Es una decisión de espacio en disco: cuanto más tiempo se retienen las trazas, más margen hay para investigar un incidente después de que ocurrió, pero también más crece la base de datos en escenarios de tráfico alto. Es importante notar que esta ventana de retención aplica solo a las trazas de diagnóstico — los **CDRs**, al ser registros de facturación, nunca se purgan.

Referencia visual: `img/admin-traffic-sampling.png`.

La pantalla ofrece atajos preconfigurados (1 hora, 6 horas, 1 día, 3 días, 7 días, 30 días, 90 días, 6 meses) más un campo de **Horas exactas** para un valor puntual, y un botón **Guardar**. En la captura de referencia el demo está configurado en **1 día (24 horas)**. El purgado en sí lo ejecutan dos procesos distintos: uno fino, por hora, a cargo del servicio de captura HEP; y uno grueso, por día completo, a cargo del cron nocturno de particiones (más liviano cuando las tablas ya son grandes).

## 11.2 Sincronización externa

**Sincronización externa** (menú **Sistema → Sync externa**) exporta los CDRs hacia una base de datos externa propia —MySQL/MariaDB, PostgreSQL o SQL Server— para que un equipo de BI pueda analizarlos con sus propias herramientas de reportería, sin necesidad de darle acceso directo a la base de datos de producción de VoxiKam. La copia es incremental y de solo lectura sobre VoxiKam, y corre automáticamente todas las noches (00:15) o a pedido con el botón **Sincronizar ahora**.

Referencia visual: `img/admin-external-sync.png`.

La configuración pide el motor de destino (pestañas MySQL/MariaDB, PostgreSQL, SQL Server), el host, puerto, base de datos, usuario y contraseña, junto con un botón **Probar conexión** antes de guardar. El usuario de destino solo necesita permisos de **CREATE** (una vez, para crear la tabla `cdrs` si no existe) e **INSERT** sobre esa tabla. En la captura de referencia la sincronización todavía no está habilitada y las secciones **Última corrida** e **Historial** muestran "todavía no corrió" / "Sin corridas todavía", porque es una instalación recién configurada a la que aún no le tocó ejecutar su primer ciclo nocturno.

## 11.3 Correo

La pantalla **Correo** (menú **Sistema → Correo**) configura el proveedor de envío de emails que usa todo el sistema —alertas de balance, avisos de infraestructura y el envío de facturas por correo comparten esta misma configuración—, de modo que hay un solo lugar para el proveedor y el remitente sin importar qué módulo dispare el correo. Si no se configura, las alertas y facturas se siguen generando y quedando registradas, pero ningún correo llega a enviarse.

Referencia visual: `img/admin-mail-config.png`.

Hay dos proveedores posibles, como pestañas: **Resend (API)** —un servicio de correo transaccional externo, para el cual hay que crear cuenta, verificar el dominio propio y generar una API key— o **SMTP propio**. Los campos configurables son la API key (o los datos del SMTP) y el **remitente** (el correo que verá el destinatario como origen). En la captura de referencia el demo usa Resend con el remitente `no-reply@kpbtec.com` pero sin ninguna API key cargada todavía. También hay un checkbox para alertar por correo cuando una llamada queda huérfana por un reinicio de Kamailio, y una tarjeta aparte de **Enviar correo de prueba**, para confirmar que el envío funciona antes de depender de él para alertas o facturación (requiere guardar la configuración primero).

## 11.4 Auditoría

**Auditoría** (menú **Seguridad → Auditoría**) es el log detallado de cambios de configuración hechos por los administradores (o por resellers con permisos delegados): quién creó o editó qué entidad, cuándo, y qué campo cambió de qué valor a qué valor. No es un log de absolutamente todo, sino uno selectivo, enfocado en cambios con impacto en servicio, dinero o seguridad.

Referencia visual: `img/admin-audit.png`.

La pantalla tiene un filtro lateral por categoría (Todas, Clientes, Ruteo, Tarifas, Seguridad, Facturación, Sistema) y una tabla con columnas **Fecha**, **Quién**, **Entidad**, **Campo**, **Antes** y **Ahora**. En la captura de referencia, correspondiente a este demo recién configurado, se ven entradas reales como la creación de un webhook, la creación de áreas geográficas, facturas marcadas como pagadas, la creación de reglas de firewall, y la creación de los tres carriers de prueba (Andino Telecom, Fibra Sur Networks y VoIP Internacional) con sus tarifas de compra asociadas — la mayoría atribuidas al usuario **Administrador**, útil justamente para trazabilidad de "quién hizo qué" cuando varios administradores comparten el panel.

## 11.5 Usuarios admin

**Usuarios admin** (menú **Clientes → Usuarios**) es el CRUD de las cuentas que pueden entrar al panel de administración: permite crear nuevos administradores (nombre, email y contraseña), resetear la contraseña de una cuenta existente y desactivarla si esa persona deja de necesitar acceso. Antes de crear usuarios adicionales, solo existe el admin único generado durante la instalación.

Referencia visual: `img/admin-users.png`.

En la captura de referencia hay un único usuario: **Administrador** (`admin@kpbtec-demo.local`), marcado con la etiqueta **Super admin** y en estado **Activo**. El super admin —el admin creado durante la instalación— es un caso especial: nadie más puede desactivar su cuenta ni resetear su contraseña, precisamente para evitar quedarse sin acceso al sistema por un error de otro administrador.

## 11.6 Salud del sistema

**Salud del sistema** (menú **Sistema → Salud**) muestra el estado de los servicios internos de VoxiKam —Backend, Frontend, Captura HEP, ClickHouse, Kamailio y RTPEngine— junto con el estado de los cron jobs programados (particionado de tablas, resumen nocturno de CDRs, cálculo de ASR, sincronización del firewall, etc.). La pantalla se auto-actualiza cada 30 segundos.

Referencia visual: `img/admin-system-health.png`.

En la captura de referencia todos los servicios (incluido Autotune) aparecen en estado **"unknown"**, y los cron jobs listados muestran **"sin logs" / "nunca corrió"**. Esto es normal en una instalación recién hecha: el estado real recién se refleja después de que cada proceso corra su primer ciclo programado. La pantalla también incluye una sección de **captura de trazas (mini-Homer)**, que indica cuánto tráfico SIP/RTCP está procesando el listener antes de guardarlo (y si empieza a descartar mensajes por saturación), y un acceso a "otros servicios del sistema" para un barrido más amplio del servidor, no solo de VoxiKam.

## 11.7 Infraestructura

**Infraestructura** (menú **Sistema → Infraestructura**) reúne tres configuraciones que antes solo podían tocarse por consola SSH: el estado de **HTTPS** (vía Let's Encrypt), la programación del **backup automático** de la base de datos, y si las **alertas de infraestructura por correo** están activas.

Referencia visual: `img/admin-system-infra.png`.

En la captura de referencia, HTTPS está **inactivo** (el demo corre en HTTP plano, sobre el dominio `localhost`); el **backup automático** está activado, con horario diario a las **02:30** y una retención de **14 días** (cubre MariaDB —facturas, saldos, clientes— y, en la medida de lo posible, ClickHouse); y las **alertas de infraestructura** están activadas, revisando cada 15 minutos si algún cron se cuelga o si el disco/memoria del servidor se agotan, y avisando por correo con el mismo remitente configurado en la pantalla de Correo.

## 11.8 Logs

La pantalla **Logs** (menú **Sistema → Logs**) permite ver en vivo las últimas líneas del log de cada servicio (Backend, y el resto de los servicios y crons del sistema) directamente desde el panel, sin necesidad de entrar por SSH. Es una herramienta de solo lectura pensada para un diagnóstico rápido; reiniciar un servicio o seguir un log de forma continua sigue siendo tarea de la consola.

Referencia visual: `img/admin-system-logs.png`.

La pantalla tiene un selector de servicio, un selector de cantidad de líneas a mostrar y un botón de auto-actualización. En la captura de referencia está seleccionado **Backend (FastAPI)** con **100 líneas**, y el resultado muestra **"Sin líneas para mostrar"** — algo puntual y esperable en un demo sin actividad reciente en ese servicio en el momento de la captura.

## 11.9 Entrante

La pantalla **Entrante** (menú **Ruteo → Entrante**) configura los **peers** de la red local (por ejemplo, un Asterisk o ViciBox propio) que reciben las llamadas **entrantes** enviadas por los carriers — es el flujo inverso al de los clientes salientes: acá el carrier llama hacia adentro y VoxiKam entrega esa llamada a un sistema propio.

Referencia visual: `img/admin-inbound.png`.

El formulario para dar de alta un peer pide **Host/IP**, **Puerto** (5060 por defecto) y una **descripción** opcional. En la captura de referencia todavía no hay ningún peer cargado — el mensaje **"Sin peers configurados todavía"** es el estado normal antes de dar de alta el primero, algo esperable en esta instalación de demo recién hecha.
