<div align="center">

<img src="docs/logo.svg" alt="la plataforma anterior" width="380"/>

### Plataforma SIP Class 4 — Billing, Monitoreo y Control de Tráfico

[![Version](https://img.shields.io/badge/version-2.3-blue?style=flat-square)](CHANGELOG.md)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue?style=flat-square)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Debian%2012%2B-orange?style=flat-square)](#-instalación)
[![Telegram](https://img.shields.io/badge/soporte-Telegram-2CA5E0?style=flat-square&logo=telegram)](https://t.me/KPBTec)

*Diseñada para operadores, revendedores de voz y empresas que necesitan saber*
*exactamente por dónde sale cada llamada, cuánto les cuesta y qué margen les genera.*

**Un producto de [KPBTec](https://github.com/KPBTec) · Knowledge, Protection & Business Technology**

</div>

---

## 🎯 ¿Por qué la plataforma anterior?

La mayoría de plataformas de billing SIP fueron diseñadas para equipos técnicos: configuración en consola, sin visibilidad en tiempo real y con portales cliente básicos o inexistentes. la plataforma anterior cambia ese paradigma.

> **Un operador no debería necesitar acceso SSH para agregar una IP al firewall, ver cuánto está generando un cliente hoy o detectar que un carrier está fallando.**

la plataforma anterior reúne en un solo panel todo lo que un operador necesita para administrar su tráfico SIP, controlar sus márgenes y darle a cada cliente visibilidad sobre su propio consumo — sin tocar una consola.

---

## 👥 ¿Para quién está hecho?

| Perfil | Cómo lo usa |
|---|---|
| 🏪 **Revendedor de voz** | Da trunks SIP a sus clientes, los tarifea con sus propias rates y les genera facturas automáticamente |
| 📊 **Empresa con campañas** | Mide rentabilidad por cliente o campaña: minutos, costo de compra, costo de venta y margen en tiempo real |
| 🖥️ **Operador pequeño** | Tiene su propio SBC con control de IPs, límites de tráfico, firewall gestionado y portal para sus clientes |

---

## 🏗️ Arquitectura técnica

la plataforma anterior es una plataforma **Class 4**: switching de tránsito y billing. No incluye IVR, voicemail ni colas (Class 5). Construida sobre tres componentes probados en producción:

```
📞 Cliente SIP (Asterisk / softphone)
        │
        │  SIP INVITE
        ▼
┌───────────────────────────────────────────────────┐
│               🔀 KAMAILIO SBC                     │
│                                                   │
│  ✔ Verifica IP del cliente (ACL por lista blanca) │
│  ✔ Identifica al cliente por techprefix           │
│  ✔ Dispatcher: LCR + failover automático          │
│  ✔ Genera CDR en el BYE final                     │
│  ✔ HEP mirror → captura trazas SIP                │
└──────────────┬────────────────────────────────────┘
               │
               │  Oferta / respuesta SDP
               ▼
┌──────────────────────────────┐
│       🎙️ RTPENGINE           │   Relay de media RTP/SRTP
│       (proxy de media)       │   NAT traversal transparente
└──────────────────────────────┘
               │
               │  BYE → POST /api/admin/cdrs/ingest
               ▼
┌──────────────────────────────────────────────────────┐
│            ⚙️ CAPA DE APLICACIÓN                     │
│                                                      │
│  Nginx :7666  →  FastAPI (Python)  →  MariaDB        │
│             →  Next.js (React)                       │
│                                                      │
│  ✔ Billing worker: calcula buy/sell cost c/30s       │
│  ✔ Descuenta balance del cliente en tiempo real      │
│  ✔ API REST para panel admin y portal cliente        │
│  ✔ Genera configuraciones nftables y dispatcher      │
└──────────────────────────────────────────────────────┘
```

> **Kamailio maneja el SIP en tiempo real — la plataforma anterior no intercepta ninguna llamada activa.** Solo entra al finalizar cada llamada para calcular costos y actualizar saldos, garantizando que un problema en la capa de aplicación nunca afecte el tráfico en curso.

---

## 🔑 Dos vistas, dos mundos

la plataforma anterior tiene dos portales completamente separados: uno para el operador que administra el sistema, y otro para cada cliente que usa el servicio. Cada uno con su propio acceso, sus propios datos y sus propias funciones.

---

## 🔧 Vista Operador — Panel de Administración

Acceso exclusivo para administradores. Control total del sistema desde una sola interfaz web.

| Módulo | Descripción |
|---|---|
| 📈 **Dashboard** | KPIs del día en tiempo real: llamadas activas, completadas, minutos, ingresos y ASR global con gráfico por cliente |
| 🔴 **Live** | Monitor de llamadas activas ahora mismo: cliente, carrier en uso, origen, destino y duración en curso |
| 👤 **Clientes** | CRUD de trunks SIP: techprefix, plan de tarifas, IPs autorizadas, carriers asignados, balance prepago, límites y perfil de módulos |
| 🧩 **Perfiles** | Conjuntos de módulos del portal asignables a múltiples clientes — cambia un perfil y aplica a todos los clientes asignados |
| 🌐 **Carriers** | Gateways SIP de salida con rates de compra por prefijo de destino |
| 💰 **Tarifas** | Rate plans con precio de venta por prefijo E.164: por minuto, cargo de conexión y tiempo mínimo facturable |
| 📋 **CDRs** | Historial completo de llamadas con costo de compra, costo de venta y margen calculado por registro |
| 🔍 **Trazas SIP** | Ladder diagram de mensajes SIP capturados vía HEP desde Kamailio — diagnostica llamadas sin abrir consola |
| 📡 **Calidad ASR** | Answer Seizure Ratio por cliente y hora con desglose de códigos: 487, 486, 404, 503 |
| 📊 **Reportes** | Rentabilidad consolidada por cliente y período: llamadas, minutos, compra, venta y margen |
| 🧾 **Facturas** | Generación automática de PDF desde CDRs del período seleccionado |
| 🛡️ **Firewall** | Reglas `ALLOW` / `DENY` / `JAIL` por IP o CIDR gestionadas desde el panel — sin SSH ni consola |

<details>
<summary>⚙️ Configuración por cliente (expandir)</summary>

Cada cliente en la plataforma anterior es un trunk SIP independiente con su propia configuración:

| Campo | Descripción |
|---|---|
| 🏷️ **Techprefix** | Identificador único que Kamailio usa para reconocer al cliente en cada INVITE |
| 💰 **Plan de tarifas** | Rate plan asignado — define cuánto se cobra por minuto según destino |
| ⚡ **Calls máx / CPS** | Límite de llamadas simultáneas y calls-per-second, aplicados en tiempo real |
| 🔒 **IPs autorizadas** | Lista blanca de IPs y CIDRs — cualquier INVITE fuera de ella es rechazado |
| 🌐 **Carriers de salida** | Carriers con prioridad — failover automático si el primero falla |
| 💳 **Balance** | Saldo prepago descontado automáticamente por cada CDR contestado |
| 🧩 **Perfil de módulos** | Qué módulos puede ver el cliente en su portal |

</details>

---

## 👤 Vista Cliente — Portal Personal

Cada cliente accede a su propio portal con visibilidad exclusiva sobre su tráfico. Los módulos disponibles los define el operador mediante perfiles — el cliente solo ve lo que el operador habilita.

| Módulo | Descripción |
|---|---|
| 🏠 **Resumen** | Actividad del día: llamadas, minutos, costo acumulado y gráfico de tráfico en tiempo real (1h / 3h / 6h / 12h) |
| 📞 **Mis llamadas** | Historial paginado de CDRs propios con filtros de fecha: hora, origen, destino, duración y costo |
| 📡 **Calidad ASR** | Dashboard de calidad del tráfico propio — detecta problemas de terminación por destino |
| 📊 **Reportes** | Resumen mensual con desglose día a día: llamadas, minutos y costo total |
| 🧾 **Facturas** | Facturas emitidas por el operador, descargables directamente desde el portal |
| 📖 **Trunk Guide** | Guía de configuración personalizada con los datos propios del cliente listos para copiar en Asterisk |

> **Visibilidad controlada por el operador.** El operador decide qué ve cada cliente mediante perfiles de módulos — desde acceso mínimo solo con resumen, hasta visibilidad completa con facturas incluidas.

---

## 🔐 Seguridad en Capas

> **La seguridad no debería ser una configuración opcional — debería estar encendida desde el día uno.** En la plataforma anterior, cada capa de protección está activa por defecto, sin configuración adicional.

La mayoría de plataformas SIP exponen su panel en el puerto 80 sin rate limiting, con contraseñas en texto plano y sin separación real entre usuarios. la plataforma anterior fue diseñado con el modelo opuesto: defensa en profundidad desde el kernel hasta la base de datos.

```
🌐 Internet
   │
   ▼  🧱 nftables (kernel)
   │     Bloqueo por IP/CIDR antes de que el paquete llegue a ningún servicio.
   │     Reglas gestionadas desde el panel web — sin tocar consola.
   │
   ▼  🔁 Nginx — primera línea de aplicación
   │     Rate limiting por endpoint. Bloqueo automático de user-agents
   │     maliciosos: sqlmap, nikto, masscan, nmap, entre otros.
   │     Headers de seguridad HTTP activos por defecto.
   │
   ▼  ⚙️  FastAPI — capa de negocio
   │     Rate limiting interno: 10 req/60s en login, 300 req/60s en API.
   │     Headers: X-Frame-Options DENY, CSP estricto, Referrer-Policy.
   │     Cada endpoint protegido por dependencia de rol — no por convención.
   │
   ▼  🎫 Autenticación JWT HS256
   │     Tokens con expiración de 8 horas. Passwords con bcrypt (cost 12).
   │     Sin sesiones en servidor — sin riesgo de session fixation.
   │
   ▼  🗄️  MariaDB — aislada por diseño
         Bind exclusivo en 127.0.0.1. Puerto no estándar (33100–33999).
         Usuario dedicado con permisos mínimos. Sin acceso remoto posible.
```

| Capa | Qué protege |
|---|---|
| 🔒 **ACL SIP (Kamailio)** | Cada `INVITE` debe venir de una IP autorizada — IPs desconocidas son descartadas silenciosamente, sin revelar que el servidor existe |
| 👁️ **Aislamiento de datos** | Un cliente solo puede ver sus propios CDRs — la restricción está en la DB, no solo en el frontend |
| 👥 **Separación de roles** | Admin y cliente son roles incompatibles validados en el backend — conocer la URL no da acceso |

---

## 🚀 Instalación

```bash
git clone <repo> /opt/kaplabilling
cd /opt/kaplabilling
sudo ./install.sh
```

Corre en **Debian 12+**. Detecta IPs del servidor, solicita configuración mínima y en aproximadamente 10 minutos el sistema está operativo.

### Modos de actualización

| Comando | Cuándo usarlo |
|---|---|
| `sudo ./install.sh --update` | ✅ Código + migraciones DB + rebuild frontend. Kamailio no se interrumpe. |
| `sudo ./install.sh --upgrade` | ⚙️ Como `--update` pero también reinicia Kamailio. |
| `sudo ./install.sh --reinstall` | 🔄 Reinstalación completa desde cero. |

### Acceso post-instalación

| Recurso | Ubicación |
|---|---|
| 🌐 Panel web | `http://<DOMAIN>:<WEB_PORT>` (puerto default: `7666`) |
| 🔑 Credenciales | `/kaplabilling-install/logs-configs/credentials.conf` |
| 📄 Logs | `/kaplabilling-install/logs-configs/install-YYYYMMDD.log` |

```bash
# Reiniciar servicios
systemctl restart kaplabilling-backend kaplabilling-frontend kaplabilling-hep

# Ver logs en tiempo real
journalctl -u kaplabilling-backend -n 50 -f
```

> 📋 Ver historial de versiones en [CHANGELOG.md](CHANGELOG.md) · Versión actual en [release.conf](release.conf)

---

## 📜 Licencia

Este proyecto está licenciado bajo los términos de la [Licencia AGPL v3](LICENSE), que requiere que cualquier modificación distribuida o usada como servicio de red sea publicada bajo los mismos términos.

> **Autoría**: Este software fue creado y es mantenido por [KPBTec](https://github.com/KPBTec).  
> Aunque es de código abierto, se agradece el reconocimiento correspondiente en derivados o menciones públicas.

---

## 👤 Autor

Desarrollado por [KPBTec](https://github.com/KPBTec) · Knowledge, Protection & Business Technology  
© 2026 – Todos los derechos reservados.
