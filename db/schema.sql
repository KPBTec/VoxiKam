-- =============================================================================
-- KPBTec VoxiKam — Schema completo
-- MariaDB 10.11+
-- =============================================================================

SET NAMES utf8mb4;
SET time_zone = '+00:00';
SET foreign_key_checks = 0;

-- -----------------------------------------------------------------------------
-- USUARIOS (admin + clientes)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name          VARCHAR(120)  NOT NULL,
    email         VARCHAR(180)  NOT NULL UNIQUE,
    password_hash VARCHAR(255)  NOT NULL,
    role          ENUM('admin','client') NOT NULL DEFAULT 'client',
    is_superadmin TINYINT(1)    NOT NULL DEFAULT 0, -- solo el admin primario; otros admins no pueden desactivarlo ni resetear su contraseña
    customer_id   INT UNSIGNED  NULL,          -- NULL si role=admin
    is_active     TINYINT(1)    NOT NULL DEFAULT 1,
    -- Preferencia visual del panel — 'bronce' (default), 'papel', 'fosforo'
    -- o 'vidrio'. Por cuenta (admin o cliente), solo estética.
    ui_theme      VARCHAR(20)   NOT NULL DEFAULT 'bronce',
    created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_role (role),
    INDEX idx_customer (customer_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- PERFILES DE CLIENTE (conjuntos de módulos reutilizables)
-- -----------------------------------------------------------------------------
-- Los show_* individuales (uno por columna) se reemplazaron por el árbol de
-- permission_resources/profile_permissions de abajo — un perfil ahora es
-- solo el nombre/descripción; el detalle de qué ve se guarda en
-- profile_permissions(profile_id=este.id, ...), no en columnas acá.
CREATE TABLE IF NOT EXISTS customer_profiles (
    id               INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name             VARCHAR(100)  NOT NULL,
    description      TEXT          NULL,
    created_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- PERMISOS GRANULARES (menú → submenú/sección) — estilo MagnusBilling.
-- Reemplaza los show_* de arriba (que quedaban uno por columna, sin poder
-- controlar nada DENTRO de una página ni agregar un ítem nuevo sin una
-- migración de ALTER TABLE). permission_resources es el árbol de TODO lo
-- controlable (una fila = un ítem de menú o una sección dentro de una
-- página, con parent_key opcional para anidar). profile_permissions guarda
-- los overrides — de un perfil (profile_id) O de un cliente puntual sin
-- perfil asignado (customer_id), nunca ambos en la misma fila. Resolución
-- (ver backend/auth.py::has_permission()): COALESCE(override del cliente,
-- override del perfil, default_visible de la plataforma) — mismo criterio
-- de precedencia que ya usaban require_module()/require_reseller_module().
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS permission_resources (
    resource_key    VARCHAR(60)  NOT NULL PRIMARY KEY,
    parent_key      VARCHAR(60)  NULL,
    label           VARCHAR(80)  NOT NULL,
    sort_order      SMALLINT     NOT NULL DEFAULT 0,
    default_visible TINYINT(1)   NOT NULL DEFAULT 1,
    FOREIGN KEY (parent_key) REFERENCES permission_resources(resource_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- INSERT IGNORE — mismo criterio que el seed de countries/reglas de balance:
-- se re-siembra completo en cada deploy, agregar un resource nuevo acá
-- alcanza para que aparezca en el próximo --update/--upgrade sin pisar los
-- default_visible que un admin ya haya customizado via profile_permissions.
INSERT IGNORE INTO permission_resources (resource_key, parent_key, label, sort_order, default_visible) VALUES
('overview',            NULL,       'Resumen',                                       10, 1),
('overview_kpis',       'overview', 'KPIs (llamadas/minutos/consumido/disponible hoy)', 11, 1),
('overview_last_calls', 'overview', 'Últimas llamadas',                              12, 1),
('calls',               NULL,       'Mis llamadas',                                  20, 1),
('quality',             NULL,       'Calidad ASR',                                   30, 1),
('reports',             NULL,       'Reportes',                                      40, 1),
('invoices',            NULL,       'Facturas',                                      50, 0),
('trunk_guide',         NULL,       'Trunk Guide',                                   60, 1),
('carriers',            NULL,       'Mis carriers',                                  70, 1),
('api_access',          NULL,       'API Keys',                                      80, 0),
('reseller_dashboard',  NULL,       'Reseller: Resumen',                             90, 1),
('reseller_customers',  NULL,       'Sub-clientes',                                  91, 1),
('reseller_rates',      NULL,       'Tarifas propias',                               92, 1),
('reseller_carriers',   NULL,       'Carriers propios',                              93, 1);

CREATE TABLE IF NOT EXISTS profile_permissions (
    id           INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    profile_id   INT UNSIGNED NULL,
    customer_id  INT UNSIGNED NULL,
    resource_key VARCHAR(60)  NOT NULL,
    can_view     TINYINT(1)   NOT NULL DEFAULT 1,
    UNIQUE KEY uq_profile_resource  (profile_id, resource_key),
    UNIQUE KEY uq_customer_resource (customer_id, resource_key),
    FOREIGN KEY (profile_id)   REFERENCES customer_profiles(id) ON DELETE CASCADE,
    FOREIGN KEY (customer_id)  REFERENCES customers(id) ON DELETE CASCADE,
    FOREIGN KEY (resource_key) REFERENCES permission_resources(resource_key) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- CLIENTES (trunks SIP)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS customers (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    parent_customer_id INT UNSIGNED NULL,        -- NULL = depende directo de la plataforma; si no, es sub-cliente de un reseller
    is_reseller     TINYINT(1)    NOT NULL DEFAULT 0,  -- activado a mano por el admin — igual que users.is_superadmin
    name            VARCHAR(120)  NOT NULL,
    company         VARCHAR(180)  NULL,
    email           VARCHAR(180)  NOT NULL,
    phone           VARCHAR(30)   NULL,
    balance         DECIMAL(12,4) NOT NULL DEFAULT 0.0000,
    credit_limit    DECIMAL(12,4) NOT NULL DEFAULT 0.0000,
    rate_plan_id    INT UNSIGNED  NULL,
    profile_id      INT UNSIGNED  NULL,          -- perfil de módulos asignado (NULL = flags propios)
    calllimit       SMALLINT UNSIGNED NOT NULL DEFAULT 10,    -- llamadas simultáneas máx
    cpslimit        SMALLINT UNSIGNED NOT NULL DEFAULT 2,     -- calls per second máx
    -- NULL = sin asignar (antes ''; UNIQUE no puede convivir con '' repetido
    -- en muchos clientes sin prefijo — NULL sí, MariaDB permite múltiples
    -- NULL en una columna UNIQUE). La API sigue devolviendo/aceptando "" —
    -- la conversión ''<->NULL vive en customers.py/reseller.py, no acá.
    -- Encontrado en producción real: sin UNIQUE, una condición de carrera en
    -- la auto-asignación de reseller.py::_next_techprefix() dejó 2 clientes
    -- con el mismo prefijo — Kamailio le robaba las llamadas a uno de los dos.
    techprefix      VARCHAR(20)   NULL,                       -- prefijo asignado (ej: 1001)
    currency        CHAR(3)       NOT NULL DEFAULT 'PEN',
    -- Los show_* individuales se reemplazaron por profile_permissions
    -- (customer_id=este.id, ...) cuando el cliente no tiene profile_id — ver
    -- la tabla permission_resources más arriba y backend/auth.py::has_permission().
    status          ENUM('active','suspended','expired','deleted') NOT NULL DEFAULT 'active',  -- 'deleted' = desactivado desde el panel, nunca se borra la fila (cdrs.customer_id no puede tener FK)
    billing_type    ENUM('prepago','postpago') NOT NULL DEFAULT 'prepago',
    last_topup_amount DECIMAL(12,4) NULL,        -- último recargo positivo — referencia del 100% para alertas de % en prepago
    last_alert_rule_id INT UNSIGNED NULL,        -- última regla de balance_alert_rules ya notificada (evita reenviar en cada CDR)
    notes           TEXT          NULL,
    -- El grupo de ruteo de este cliente — ÚNICO mecanismo de selección de
    -- carriers salientes, no hay una lista de carriers separada por fuera
    -- de un grupo (ver carrier_groups más abajo). NULL solo antes de que
    -- se le asigne el primer carrier — backend/routers/customers.py::
    -- assign_carrier() crea el grupo "Principal" automáticamente la
    -- primera vez (mismo gesto simple de siempre, "agregar un carrier"),
    -- así que en la práctica queda NULL únicamente para un cliente sin
    -- ningún carrier asignado todavía. Un grupo de 1 solo miembro es el
    -- caso "carrier único" de siempre; 2+ miembros con algorithm=
    -- 'round_robin' o 'percent' reparten tráfico de verdad. Cada prefijo
    -- de campaña (customer_prefixes.routing_group_id) puede apuntar a un
    -- grupo DISTINTO — NULL ahí significa "heredar este mismo grupo".
    routing_group_id INT UNSIGNED NULL,
    created_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (parent_customer_id) REFERENCES customers(id) ON DELETE RESTRICT,
    FOREIGN KEY (routing_group_id) REFERENCES carrier_groups(id) ON DELETE SET NULL,
    INDEX idx_status (status),
    UNIQUE KEY uq_techprefix (techprefix),
    INDEX idx_parent (parent_customer_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- LEDGER DE TRANSACCIONES DE BALANCE
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS balance_transactions (
    id            BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    customer_id   INT UNSIGNED  NOT NULL,
    -- invoice_payment = crédito automático al marcar una factura pagada;
    -- recalc = ajuste neto de un recálculo de tarifas (Tramo D, admin/reseller).
    type          ENUM('cdr','manual','invoice_payment','recalc') NOT NULL,
    amount        DECIMAL(12,4) NOT NULL,        -- negativo = débito, positivo = crédito/recargo
    balance_after DECIMAL(12,4) NOT NULL,
    reference     VARCHAR(100)  NULL,            -- call_id del CDR, o nota del ajuste manual
    created_by    VARCHAR(50)   NULL,            -- username del admin si fue manual
    created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    INDEX idx_customer_date (customer_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- REGLAS DE ALERTA DE BALANCE (prepago: % de saldo restante · postpago: balance absoluto)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS balance_alert_rules (
    id           INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    billing_type ENUM('prepago','postpago') NOT NULL,
    label        VARCHAR(80)   NOT NULL,
    threshold    DECIMAL(12,4) NOT NULL,         -- prepago: % restante (ej 20) · postpago: balance absoluto (ej -1000)
    active       TINYINT(1)    NOT NULL DEFAULT 1,
    created_at   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO balance_alert_rules (id, billing_type, label, threshold, active) VALUES
    (1, 'prepago',  'Saldo bajo — 30% restante',  30,    1),
    (2, 'prepago',  'Saldo crítico — 20% restante', 20,  1),
    (3, 'postpago', 'Consumo alto — balance -1000', -1000, 1),
    (4, 'postpago', 'Consumo crítico — balance -3000', -3000, 1);

-- -----------------------------------------------------------------------------
-- IPs AUTORIZADAS POR CLIENTE
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS customer_ips (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    customer_id INT UNSIGNED NOT NULL,
    ip          VARCHAR(45)  NOT NULL,    -- IPv4 o IPv6
    description VARCHAR(120) NULL,
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_customer_ip (customer_id, ip),
    INDEX idx_ip (ip),
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- PEERS LAN (Asterisk/ViciBox) — tráfico ENTRANTE (carrier → Asterisk, Grupo 1
-- de dispatcher). Reemplaza el campo suelto settings.lan_peers (un CSV
-- "host:puerto,host:puerto" sin CRUD ni pantalla propia — scripts/
-- gen_dispatcher.py ya lo parseaba así, pero nunca existió el endpoint ni la
-- página "Settings > LAN Peers" que sus propios comentarios daban por hecha).
-- Mismo criterio que customer_ips: alta/baja simple con descripción, sin edición.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lan_peers (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    host        VARCHAR(100) NOT NULL,
    port        SMALLINT UNSIGNED NOT NULL DEFAULT 5060,
    description VARCHAR(120) NULL,
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_host_port (host, port)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- PREFIJOS DE CAMPAÑA POR CLIENTE (ej. Vicidial: 1 cliente, N campañas)
-- `customers.techprefix` sigue siendo el prefijo "principal" (sin cambios) —
-- esta tabla contiene SOLO prefijos adicionales, con etiqueta propia, que
-- facturan al mismo customer_id pero permiten desglosar consumo por campaña.
-- Un cliente que no usa la feature tiene 0 filas acá.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS customer_prefixes (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    customer_id INT UNSIGNED NOT NULL,
    techprefix  VARCHAR(20)  NOT NULL,
    label       VARCHAR(120) NOT NULL DEFAULT '',
    -- Grupo de ruteo de ESTE prefijo de campaña puntual — NULL = hereda el
    -- grupo del cliente (customers.routing_group_id), igual que antes un
    -- prefijo sin pin propio caía al reparto del cliente. Solo se setea acá
    -- cuando esta campaña puntual necesita un grupo DISTINTO al resto.
    routing_group_id INT UNSIGNED NULL,
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_techprefix (techprefix),
    INDEX idx_customer (customer_id),
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
    FOREIGN KEY (routing_group_id) REFERENCES carrier_groups(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- PROVEEDORES — agrupa carriers/troncales que en la vida real son el mismo
-- proveedor SIP con varias rutas (ej. Itelvox1/2/3 son 3 troncales de un
-- mismo proveedor "Itelvox"). Cada troncal sigue teniendo su propio host y
-- sus propias tarifas en `carriers`/`carrier_rates` — providers es solo
-- agrupación para organización y reportes, no cambia ruteo ni rating.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS providers (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(120) NOT NULL,
    notes       TEXT NULL,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- CARRIERS (providers SIP salientes)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS carriers (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name            VARCHAR(120)  NOT NULL,
    -- NULL = sin proveedor asignado todavía (ver providers arriba) — puramente
    -- organizacional, no participa del ruteo ni del rating por prefijo.
    provider_id     INT UNSIGNED  NULL,
    host            VARCHAR(100)  NOT NULL,
    port            SMALLINT UNSIGNED NOT NULL DEFAULT 5060,
    priority        TINYINT UNSIGNED  NOT NULL DEFAULT 10,   -- mayor = primero en dispatcher
    outbound_prefix VARCHAR(20)   NOT NULL DEFAULT '',       -- prefijo que agrega este carrier
    remove_prefix   VARCHAR(20)   NOT NULL DEFAULT '',       -- prefijo a quitar antes de enviar
    failover_id     INT UNSIGNED  NULL,                      -- carrier de fallback
    dispatcher_group SMALLINT UNSIGNED NOT NULL DEFAULT 2,   -- grupo base en dispatcher.list
    status          ENUM('active','inactive','maintenance') NOT NULL DEFAULT 'active',
    -- NULL = sin límite (comportamiento actual, sin cambios). Si se setea,
    -- kamailio.cfg.j2 encola (no rechaza) los INVITEs que excedan este CPS
    -- hacia este carrier — ver route[OUTBOUND_TO_CARRIER] y el htable de
    -- conteo/cola ahí. gen_dispatcher.py lo pasa como atributo cps= en
    -- dispatcher.list, mismo mecanismo que carid=/prefix=.
    cps_limit       SMALLINT UNSIGNED NULL,
    notes           TEXT          NULL,
    -- NULL = carrier de la plataforma (admin). Si no es NULL, es una troncal
    -- propia de ESE reseller — mismo criterio "mini admin" que prefixes/
    -- rate_plans (modelo MagnusBilling: el reseller carga su propio proveedor
    -- upstream). gen_dispatcher.py NO necesita saber de esta columna — un
    -- carrier entra a un grupo (carrier_group_members) sin importar quién
    -- es su dueño, la pertenencia a un grupo es lo único que rutea.
    owner_customer_id INT UNSIGNED NULL,
    created_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_status   (status),
    INDEX idx_owner    (owner_customer_id),
    INDEX idx_provider (provider_id),
    FOREIGN KEY (owner_customer_id) REFERENCES customers(id) ON DELETE CASCADE,
    FOREIGN KEY (provider_id) REFERENCES providers(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- GRUPOS DE RUTEO — ÚNICO mecanismo de asignación cliente↔carriers. No existe
-- una tabla aparte de "carriers asignados al cliente": el gesto simple de
-- "asignale un carrier a este cliente" (backend/routers/customers.py::
-- assign_carrier) crea/reutiliza el grupo "Principal" del cliente
-- (customers.routing_group_id) por detrás — un grupo de 1 solo miembro es
-- exactamente el caso "carrier único" de siempre. Cada PREFIJO
-- (customers.routing_group_id / customer_prefixes.routing_group_id) puede
-- apuntar a un grupo DISTINTO, independiente de los demás prefijos del
-- mismo cliente — y varios clientes pueden compartir el mismo grupo (ej.
-- un grupo "Premium" armado por el admin y ofrecido a varios). Con 2+
-- miembros, 'round_robin' o 'percent' reparten tráfico de verdad
-- (algoritmos 4/11 de dispatcher — ver route[OUTBOUND_TO_CARRIER] en
-- kamailio.cfg.j2 y gen_dispatcher.py::build_routes_cfg).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS carrier_groups (
    id                 INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name               VARCHAR(120) NOT NULL,
    algorithm          ENUM('priority','round_robin','percent') NOT NULL DEFAULT 'priority',
    -- NULL = grupo de la plataforma (admin). Si no, es propio de ESE
    -- reseller — mismo criterio que carriers.owner_customer_id.
    owner_customer_id  INT UNSIGNED NULL,
    created_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_owner (owner_customer_id),
    FOREIGN KEY (owner_customer_id) REFERENCES customers(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS carrier_group_members (
    group_id   INT UNSIGNED NOT NULL,
    carrier_id INT UNSIGNED NOT NULL,
    priority   TINYINT UNSIGNED NOT NULL DEFAULT 10,  -- usado si algorithm='priority'
    weight     TINYINT UNSIGNED NULL,                  -- usado si algorithm='percent' (NULL=1, ver gen_dispatcher.py)
    PRIMARY KEY (group_id, carrier_id),
    FOREIGN KEY (group_id)   REFERENCES carrier_groups(id) ON DELETE CASCADE,
    -- RESTRICT (no CASCADE) a propósito: borrar un carrier que es miembro
    -- de un grupo debe fallar explícito (409 a nivel API, ver
    -- backend/routers/carriers.py) en vez de dejar un grupo en uso sin
    -- miembros en silencio.
    FOREIGN KEY (carrier_id) REFERENCES carriers(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Visibilidad explícita de grupos para el portal del CLIENTE — nunca se
-- infiere qué grupos puede ver (ej. por intersección de miembros), eso
-- reintroduce la fragilidad que este diseño evita. El cliente en
-- /my/carriers solo ve/elige grupos que el admin/reseller le asignó acá
-- explícitamente, con su propio display_label anónimo. Distinto del grupo
-- "Principal" propio (customers.routing_group_id) — un cliente puede tener
-- 0+ grupos ADICIONALES habilitados acá, además del suyo.
CREATE TABLE IF NOT EXISTS customer_carrier_groups (
    customer_id    INT UNSIGNED NOT NULL,
    group_id       INT UNSIGNED NOT NULL,
    display_label  VARCHAR(20) NOT NULL DEFAULT '',
    PRIMARY KEY (customer_id, group_id),
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
    FOREIGN KEY (group_id)    REFERENCES carrier_groups(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- TABLA DE RESPALDO DEL htable "techmap" DE KAMAILIO (techprefix → grupo)
-- Reemplaza voxikam-routes.cfg (bloques if/else compilados vía #!include_file,
-- que Kamailio solo relee al ARRANCAR — encontrado en producción real en
-- vd1sbc2: un cliente con override a un grupo round_robin/percent recién
-- creado seguía ruteando 100% al carrier viejo hasta reiniciar Kamailio a
-- mano, porque el archivo se regeneraba bien pero el proceso nunca releía
-- esa lógica compilada). Esquema EXACTO que exige el módulo htable de
-- Kamailio para auto-cargar/recargar una tabla desde MySQL (columnas fijas,
-- no se puede renombrar sin togear modparam("htable", ...) en
-- templates/kamailio.cfg.j2) — ver
-- https://kamailio.org/docs/modules/5.6.x/modules/htable.html.
-- Cada fila: key_name=techprefix (ej "1001"), key_value="grp:cid:alg" (ej
-- "1005:1:11" — grp=carrier_groups.id real usado como número de grupo de
-- dispatcher, ver gen_dispatcher.py; alg vacío si el grupo es 'priority',
-- "4" si 'round_robin', "11" si 'percent'). scripts/gen_dispatcher.py
-- REEMPLAZA el contenido completo en cada corrida (TRUNCATE + INSERT) y
-- dispara `kamcmd htable.reload techmap` — confirmado real contra Kamailio
-- 5.6.3 en Docker que esto recarga altas/bajas/cambios sin reiniciar el
-- proceso, a diferencia de #!include_file.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS techprefix_map (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    key_name    VARCHAR(64)  NOT NULL,
    key_type    INT UNSIGNED NOT NULL DEFAULT 0,
    value_type  INT UNSIGNED NOT NULL DEFAULT 0,
    key_value   VARCHAR(256) NOT NULL,
    expires     INT UNSIGNED NOT NULL DEFAULT 0,
    UNIQUE KEY uq_key_name (key_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Bloqueo de llamadas nuevas para clientes PREPAGO sin saldo (billing_type=
-- 'prepago' AND balance<=0) — mismo esquema htable de Kamailio que
-- techprefix_map de arriba, pero como LISTA DE BLOQUEO en vez de mapeo: solo
-- contiene una fila por cada techprefix (principal o de campaña) que está
-- bloqueado ahora mismo. Ausencia de la clave = permitido. scripts/
-- sync_balance_block.py REEMPLAZA el contenido completo cada corrida y
-- dispara `kamcmd htable.reload balance_block`. No corta una llamada ya en
-- curso (el saldo real se descuenta recién al colgar, ver
-- backend/main.py::_billing_worker()) — solo evita que se origine una
-- llamada NUEVA una vez que el saldo ya está en 0 o negativo. Postpago
-- nunca aparece acá.
CREATE TABLE IF NOT EXISTS balance_block_map (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    key_name    VARCHAR(64)  NOT NULL,
    key_type    INT UNSIGNED NOT NULL DEFAULT 0,
    value_type  INT UNSIGNED NOT NULL DEFAULT 0,
    key_value   VARCHAR(256) NOT NULL,
    expires     INT UNSIGNED NOT NULL DEFAULT 0,
    UNIQUE KEY uq_key_name (key_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- PREFIJOS DESTINO (tabla global de destinos)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS prefixes (
    id                 INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    prefix             VARCHAR(20)  NOT NULL UNIQUE,
    destination        VARCHAR(100) NOT NULL,
    group_name         VARCHAR(50)  NOT NULL DEFAULT '',  -- agrupación para precio por grupo (ej: FIJO LIMA)
    country            VARCHAR(60)  NULL,
    -- NULL = prefijo de la plataforma (creado por el admin, visible para todos).
    -- Si no es NULL, es un prefijo privado creado por ESE reseller (como "mini
    -- admin" — MagnusBilling permite lo mismo) — solo lo ve/edita/borra él y
    -- el admin. El motor de tarifación (cdrs.py::ingest_cdr) no filtra por esta
    -- columna: hace longest-prefix-match contra TODA la tabla sin importar
    -- dueño, así que un prefijo privado del reseller tarifa igual de bien que
    -- uno de la plataforma en cuanto el reseller le pone tarifa en su rate_plan.
    owner_customer_id  INT UNSIGNED NULL,
    INDEX idx_prefix (prefix),
    INDEX idx_group  (group_name),
    INDEX idx_owner  (owner_customer_id),
    FOREIGN KEY (owner_customer_id) REFERENCES customers(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- PAÍSES — catálogo estático ISO-3166-1 alpha-2, para areas.country_code.
-- Nunca se edita desde el panel — se re-siembra completo en cada deploy
-- (INSERT ... ON DUPLICATE KEY UPDATE, ver más abajo), así que agregar un
-- país nuevo acá alcanza para que aparezca en el próximo --update/--upgrade.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS countries (
    code CHAR(2)     NOT NULL PRIMARY KEY,
    name VARCHAR(80) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO countries (code, name) VALUES
('PE','Perú'),('AR','Argentina'),('BO','Bolivia'),('BR','Brasil'),('CL','Chile'),
('CO','Colombia'),('CR','Costa Rica'),('CU','Cuba'),('DO','República Dominicana'),
('EC','Ecuador'),('SV','El Salvador'),('GT','Guatemala'),('HN','Honduras'),
('MX','México'),('NI','Nicaragua'),('PA','Panamá'),('PY','Paraguay'),
('PR','Puerto Rico'),('UY','Uruguay'),('VE','Venezuela'),
('US','Estados Unidos'),('CA','Canadá'),
('ES','España'),('PT','Portugal'),('FR','Francia'),('DE','Alemania'),('IT','Italia'),
('GB','Reino Unido'),('IE','Irlanda'),('NL','Países Bajos'),('BE','Bélgica'),
('CH','Suiza'),('AT','Austria'),('SE','Suecia'),('NO','Noruega'),('DK','Dinamarca'),
('FI','Finlandia'),('IS','Islandia'),('PL','Polonia'),('CZ','República Checa'),
('SK','Eslovaquia'),('HU','Hungría'),('RO','Rumania'),('BG','Bulgaria'),
('GR','Grecia'),('HR','Croacia'),('SI','Eslovenia'),('RS','Serbia'),
('BA','Bosnia y Herzegovina'),('ME','Montenegro'),('MK','Macedonia del Norte'),
('AL','Albania'),('XK','Kosovo'),('MT','Malta'),('CY','Chipre'),('LU','Luxemburgo'),
('EE','Estonia'),('LV','Letonia'),('LT','Lituania'),('UA','Ucrania'),
('BY','Bielorrusia'),('MD','Moldavia'),('RU','Rusia'),('AD','Andorra'),
('MC','Mónaco'),('SM','San Marino'),('VA','Ciudad del Vaticano'),('LI','Liechtenstein'),
('CN','China'),('JP','Japón'),('KR','Corea del Sur'),('KP','Corea del Norte'),
('IN','India'),('PK','Pakistán'),('BD','Bangladés'),('LK','Sri Lanka'),
('NP','Nepal'),('BT','Bután'),('MM','Myanmar'),('TH','Tailandia'),
('VN','Vietnam'),('LA','Laos'),('KH','Camboya'),('MY','Malasia'),
('SG','Singapur'),('ID','Indonesia'),('PH','Filipinas'),('TW','Taiwán'),
('HK','Hong Kong'),('MO','Macao'),('MN','Mongolia'),('KZ','Kazajistán'),
('UZ','Uzbekistán'),('TM','Turkmenistán'),('TJ','Tayikistán'),('KG','Kirguistán'),
('AF','Afganistán'),('IR','Irán'),('IQ','Irak'),('SY','Siria'),('LB','Líbano'),
('JO','Jordania'),('IL','Israel'),('PS','Palestina'),('SA','Arabia Saudita'),
('YE','Yemen'),('OM','Omán'),('AE','Emiratos Árabes Unidos'),('QA','Catar'),
('BH','Baréin'),('KW','Kuwait'),('TR','Turquía'),('GE','Georgia'),
('AM','Armenia'),('AZ','Azerbaiyán'),
('EG','Egipto'),('LY','Libia'),('TN','Túnez'),('DZ','Argelia'),('MA','Marruecos'),
('SD','Sudán'),('SS','Sudán del Sur'),('ET','Etiopía'),('ER','Eritrea'),
('DJ','Yibuti'),('SO','Somalia'),('KE','Kenia'),('UG','Uganda'),('TZ','Tanzania'),
('RW','Ruanda'),('BI','Burundi'),('CD','Rep. Democrática del Congo'),
('CG','República del Congo'),('CM','Camerún'),('CF','República Centroafricana'),
('TD','Chad'),('NE','Níger'),('NG','Nigeria'),('BJ','Benín'),('TG','Togo'),
('GH','Ghana'),('CI','Costa de Marfil'),('LR','Liberia'),('SL','Sierra Leona'),
('GN','Guinea'),('GW','Guinea-Bisáu'),('GQ','Guinea Ecuatorial'),('GA','Gabón'),
('ST','Santo Tomé y Príncipe'),('CV','Cabo Verde'),('SN','Senegal'),
('GM','Gambia'),('ML','Malí'),('BF','Burkina Faso'),('MR','Mauritania'),
('ZA','Sudáfrica'),('NA','Namibia'),('BW','Botsuana'),('ZW','Zimbabue'),
('ZM','Zambia'),('MW','Malaui'),('MZ','Mozambique'),('AO','Angola'),
('SZ','Esuatini'),('LS','Lesoto'),('MG','Madagascar'),('MU','Mauricio'),
('SC','Seychelles'),('KM','Comoras'),
('AU','Australia'),('NZ','Nueva Zelanda'),('FJ','Fiyi'),('PG','Papúa Nueva Guinea'),
('SB','Islas Salomón'),('VU','Vanuatu'),('WS','Samoa'),('TO','Tonga'),
('KI','Kiribati'),('TV','Tuvalu'),('NR','Nauru'),('PW','Palaos'),
('FM','Micronesia'),('MH','Islas Marshall'),
('BZ','Belice'),('GY','Guyana'),('SR','Surinam'),('HT','Haití'),
('JM','Jamaica'),('TT','Trinidad y Tobago'),('BB','Barbados'),('BS','Bahamas'),
('GD','Granada'),('LC','Santa Lucía'),('VC','San Vicente y las Granadinas'),
('AG','Antigua y Barbuda'),('DM','Dominica'),('KN','San Cristóbal y Nieves');

-- -----------------------------------------------------------------------------
-- ÁREAS — registro formal de prefixes.group_name (rename-safe, con reporte propio)
-- No hay FK con prefixes: el acople es por (nombre, país) — areas.name +
-- areas.country_code = prefixes.group_name + prefixes.country — igual criterio
-- de acople por texto que ya usan rates.py/carriers.py. Renombrar un área en el
-- panel cascadea el UPDATE a prefixes.group_name en la misma transacción.
-- country_code SÍ tiene FK real a countries — default 'PE' (Perú), pedido
-- explícito: toda área nueva arranca en Perú salvo que se elija otro país.
-- UNIQUE es compuesto (name, country_code), no solo name — el mismo nombre de
-- área puede repetirse en países distintos (ej. "MOVILES" en PE y en otro país).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS areas (
    id           INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name         VARCHAR(50)  NOT NULL,
    description  VARCHAR(255) NULL,
    country_code CHAR(2)      NOT NULL DEFAULT 'PE',
    created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_area_name_country (name, country_code),
    INDEX idx_country (country_code),
    FOREIGN KEY (country_code) REFERENCES countries(code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- PLANES TARIFARIOS
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rate_plans (
    id                 INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name               VARCHAR(80)  NOT NULL,
    owner_customer_id  INT UNSIGNED NULL,   -- NULL = plan de la plataforma; si no, plan propio de un reseller
    currency           CHAR(3)      NOT NULL DEFAULT 'PEN',
    description        VARCHAR(255) NULL,
    status             ENUM('active','inactive') NOT NULL DEFAULT 'active',
    created_at         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- name UNIQUE se reemplaza por (owner_customer_id, name) — MariaDB trata NULL
    -- como distinto en índices únicos, así que "sin nombres repetidos entre
    -- planes de la plataforma" (owner NULL) se valida a mano en rates.py.
    UNIQUE KEY uq_plan_owner_name (owner_customer_id, name),
    INDEX idx_owner (owner_customer_id),
    FOREIGN KEY (owner_customer_id) REFERENCES customers(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- TARIFAS — lo que cobro al cliente (sell rates)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rates (
    id                    INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    rate_plan_id          INT UNSIGNED    NOT NULL,
    prefix_id             INT UNSIGNED    NOT NULL,
    rateinitial           DECIMAL(10,6)   NOT NULL DEFAULT 0.000000,  -- S/./min al cliente
    connectcharge         DECIMAL(10,6)   NOT NULL DEFAULT 0.000000,  -- cargo fijo conexión
    initblock             SMALLINT UNSIGNED NOT NULL DEFAULT 1,       -- seg. primer bloque (1 = por segundo real)
    billingblock          SMALLINT UNSIGNED NOT NULL DEFAULT 1,       -- seg. bloques siguientes (1 = por segundo real)
    minimal_time_charge   SMALLINT UNSIGNED NOT NULL DEFAULT 0,       -- mínimo facturable seg.
    status                ENUM('active','inactive') NOT NULL DEFAULT 'active',
    effective_date        DATE NULL,
    UNIQUE KEY uq_plan_prefix (rate_plan_id, prefix_id),
    INDEX idx_rate_plan (rate_plan_id),
    FOREIGN KEY (rate_plan_id) REFERENCES rate_plans(id) ON DELETE CASCADE,
    FOREIGN KEY (prefix_id)    REFERENCES prefixes(id)   ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- PRICELISTS: borrador/aprobación de tarifas antes de publicar a `rates`
-- (billing worker sigue leyendo SOLO `rates` — esto es una capa de revisión
-- previa, nunca se lee en el camino de facturación)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rate_plan_drafts (
    id            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    rate_plan_id  INT UNSIGNED NOT NULL,
    label         VARCHAR(120) NOT NULL,
    status        ENUM('draft','published','discarded') NOT NULL DEFAULT 'draft',
    created_by    VARCHAR(120) NULL,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at  DATETIME NULL,
    published_by  VARCHAR(120) NULL,
    FOREIGN KEY (rate_plan_id) REFERENCES rate_plans(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS rate_plan_draft_items (
    id                  BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    draft_id            INT UNSIGNED NOT NULL,
    prefix_id           INT UNSIGNED NOT NULL,
    rateinitial         DECIMAL(10,6) NOT NULL,
    connectcharge       DECIMAL(10,6) NOT NULL DEFAULT 0,
    billingblock        SMALLINT UNSIGNED NOT NULL DEFAULT 1,
    minimal_time_charge SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    UNIQUE KEY uq_draft_prefix (draft_id, prefix_id),
    FOREIGN KEY (draft_id)   REFERENCES rate_plan_drafts(id) ON DELETE CASCADE,
    FOREIGN KEY (prefix_id)  REFERENCES prefixes(id)         ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- TARIFAS CARRIER — lo que me cobra el carrier (buy rates)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS carrier_rates (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    carrier_id      INT UNSIGNED  NOT NULL,
    prefix_id       INT UNSIGNED  NOT NULL,
    buy_rate        DECIMAL(10,6) NOT NULL DEFAULT 0.000000,  -- S/./min que me cobra
    connectcharge   DECIMAL(10,6) NOT NULL DEFAULT 0.000000,  -- antes "connect_charge" — unificado con rates.connectcharge (v2.24.19)
    billingblock    SMALLINT UNSIGNED NOT NULL DEFAULT 1,
    effective_date  DATE NULL,
    UNIQUE KEY uq_carrier_prefix (carrier_id, prefix_id),
    INDEX idx_carrier (carrier_id),
    FOREIGN KEY (carrier_id) REFERENCES carriers(id) ON DELETE CASCADE,
    FOREIGN KEY (prefix_id)  REFERENCES prefixes(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- CDRs — registro de llamadas
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cdrs (
    id              BIGINT UNSIGNED AUTO_INCREMENT,
    call_id         VARCHAR(120)  NOT NULL,               -- Call-ID SIP
    customer_id     INT UNSIGNED  NOT NULL,
    carrier_id      INT UNSIGNED  NULL,
    src_ip          VARCHAR(45)   NOT NULL,
    src_number      VARCHAR(40)   NOT NULL,               -- CLI (caller)
    dst_number      VARCHAR(40)   NOT NULL,               -- destino sin prefijo
    dst_number_raw  VARCHAR(40)   NOT NULL,               -- destino con prefijo del cliente
    prefix_matched  VARCHAR(20)   NULL,                   -- prefijo que hizo match
    -- Prefijo técnico de campaña (customers.techprefix o customer_prefixes)
    -- que rutéo esta llamada — capturado por Kamailio en $dlg_var(techprefix)
    -- al momento del match, porque se descarta del R-URI antes de esto. Sin
    -- backfill posible: CDRs de antes de esta columna quedan NULL para
    -- siempre, el dato nunca se guardó en ningún lado.
    techprefix      VARCHAR(20)   NULL,
    start_ts        DATETIME(3)   NOT NULL,
    answer_ts       DATETIME(3)   NULL,
    end_ts          DATETIME(3)   NULL,
    sessiontime     INT UNSIGNED  NOT NULL DEFAULT 0,     -- duración total seg.
    billsec         INT UNSIGNED  NOT NULL DEFAULT 0,     -- seg. facturables
    buycost         DECIMAL(10,6) NOT NULL DEFAULT 0,     -- lo que me cobra el carrier
    reseller_cost   DECIMAL(10,6) NULL,                   -- solo si el cliente tiene reseller: lo que el reseller "paga" (tarifa de plataforma) — margen reseller = sessionbill - reseller_cost, margen plataforma = reseller_cost - buycost
    sessionbill     DECIMAL(10,6) NOT NULL DEFAULT 0,     -- lo que cobro al cliente
    lucro           DECIMAL(10,6) GENERATED ALWAYS AS (sessionbill - buycost) STORED,
    sip_code        SMALLINT UNSIGNED NOT NULL DEFAULT 200,  -- código SIP final (200 contestada, 486 ocupado, 487 cancelada, etc.)
    disposition     ENUM('ANSWERED','NO_ANSWER','BUSY','FAILED','RESTART_ORPHANED') NOT NULL DEFAULT 'ANSWERED',  -- RESTART_ORPHANED: llamada contestada cuyo BYE nunca llegó porque Kamailio se reinició — ver scripts/cleanup_active_calls.py
    call_state      VARCHAR(20)   NULL,                      -- sngrep-style: COMPLETED CANCELLED BUSY REJECTED DIVERTED
    hangup_cause    VARCHAR(30)   NULL,
    INDEX idx_customer_date   (customer_id, start_ts),
    INDEX idx_carrier_date    (carrier_id, start_ts),
    INDEX idx_date            (start_ts),
    INDEX idx_call_id         (call_id),
    INDEX idx_disposition     (disposition),
    PRIMARY KEY (id, start_ts)             -- start_ts en la PK: requisito de MySQL para particionar por esa columna
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
-- Particionado por mes. Arranca con un rango vacío + catch-all (p_future);
-- scripts/cron_partitions.py (cron diario) va separando meses reales de p_future
-- conforme avanza el tiempo — así este archivo no queda con fechas fijas.
PARTITION BY RANGE (TO_DAYS(start_ts)) (
    PARTITION p_start  VALUES LESS THAN (TO_DAYS('2000-01-01')),
    PARTITION p_future VALUES LESS THAN MAXVALUE
);

-- prefix_matched se calculaba SOLO durante la facturación (backend/main.py::
-- _calc_bill(), backend/routers/cdrs.py::ingest_cdr()), y esos dos caminos
-- solo procesan disposition='ANSWERED' AND billsec>0 — toda llamada
-- NO_ANSWER/BUSY/etc. quedaba con prefix_matched NULL para siempre, sin
-- importar cuántas veces se corriera el backfill manual (routers/areas.py::
-- run_backfill()), porque nunca pasaba por ahí. El área de una llamada no
-- depende de si se facturó — depende solo del dst_number, que está desde el
-- INSERT original (templates/kamailio.cfg.j2::event_route[dialog:end]).
-- Este trigger corre DENTRO de MySQL en cada INSERT, sin importar
-- disposition, con la misma query de longest-prefix-match que ya usa
-- _calc_bill() contra `prefixes` (no `carrier_rates` — el área no necesita
-- carrier ni tarifa, solo el destino). No reemplaza el cálculo de
-- prefix_matched que hace la facturación (que sigue escribiendo el mismo
-- valor después, sin conflicto) — solo cubre el hueco de las llamadas que
-- nunca pasan por ahí. El backfill manual de areas.py sigue haciendo falta
-- una sola vez para el histórico ya insertado ANTES de este trigger.
-- Probado contra MariaDB real (Docker) con ANSWERED/NO_ANSWER/BUSY y un
-- destino sin prefijo configurado — comportamiento correcto en los 4 casos.
DELIMITER $$
CREATE TRIGGER IF NOT EXISTS trg_cdrs_prefix_matched
BEFORE INSERT ON cdrs
FOR EACH ROW
BEGIN
    IF NEW.prefix_matched IS NULL THEN
        SET NEW.prefix_matched = (
            SELECT prefix FROM prefixes
            WHERE NEW.dst_number LIKE CONCAT(prefix, '%')
            ORDER BY LENGTH(prefix) DESC
            LIMIT 1
        );
    END IF;
END$$
DELIMITER ;

-- CDRs de llamadas fallidas (separado para no inflar el principal)
CREATE TABLE IF NOT EXISTS cdrs_failed (
    id          BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    call_id     VARCHAR(120) NOT NULL,
    customer_id INT UNSIGNED NOT NULL,
    carrier_id  INT UNSIGNED NULL,
    src_ip      VARCHAR(45)  NOT NULL,
    src_number  VARCHAR(40)  NOT NULL,
    dst_number  VARCHAR(40)  NOT NULL,
    start_ts    DATETIME(3)  NOT NULL,
    sip_code    SMALLINT UNSIGNED NULL,
    call_state  VARCHAR(20)      NULL,                       -- CANCELLED BUSY REJECTED
    hangup_cause VARCHAR(30) NULL,
    INDEX idx_customer (customer_id),
    INDEX idx_date     (start_ts)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- TIMESERIES DE LLAMADAS (cron cada 1 min → dashboard histórico)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS calls_timeseries (
    id              BIGINT UNSIGNED   AUTO_INCREMENT PRIMARY KEY,
    ts              DATETIME          NOT NULL,              -- truncado al minuto
    customer_id     INT UNSIGNED      NOT NULL,
    carrier_id      INT UNSIGNED      NOT NULL,
    call_count      SMALLINT UNSIGNED NOT NULL DEFAULT 0,   -- total iniciadas
    answered_count  SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    failed_count    SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    UNIQUE KEY uq_ts_cust_carr (ts, customer_id, carrier_id),
    INDEX idx_ts (ts)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- ASR QUALITY — resumen de calidad por hora y cliente (ASR Dashboard)
-- Llenado por cron_quality.py cada minuto via UPSERT
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS traffic_quality_hourly (
    id          BIGINT UNSIGNED   AUTO_INCREMENT PRIMARY KEY,
    ts_hour     DATETIME          NOT NULL,              -- truncado a la hora: 2026-06-22 15:00:00
    customer_id INT UNSIGNED      NOT NULL,
    total       INT UNSIGNED      NOT NULL DEFAULT 0,   -- total intentos (answered + failed)
    answered    INT UNSIGNED      NOT NULL DEFAULT 0,   -- llamadas contestadas (cdrs)
    short_calls INT UNSIGNED      NOT NULL DEFAULT 0,   -- contestadas con billsec < 5s (buzón)
    c_487       INT UNSIGNED      NOT NULL DEFAULT 0,   -- Request Terminated
    c_486       INT UNSIGNED      NOT NULL DEFAULT 0,   -- Busy
    c_404       INT UNSIGNED      NOT NULL DEFAULT 0,   -- Not Found
    c_503       INT UNSIGNED      NOT NULL DEFAULT 0,   -- Service Unavailable
    c_other     INT UNSIGNED      NOT NULL DEFAULT 0,   -- otros códigos de error
    UNIQUE KEY uq_hour_customer (ts_hour, customer_id),
    INDEX idx_ts_hour (ts_hour),
    INDEX idx_customer_hour (customer_id, ts_hour)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- LLAMADAS ACTIVAS (updated by Kamailio dialog.so events → FastAPI)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS active_calls (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    call_id     VARCHAR(120) NOT NULL UNIQUE,
    customer_id INT UNSIGNED NOT NULL,
    carrier_id  INT UNSIGNED NULL,
    src_ip      VARCHAR(45)  NOT NULL,
    src_number  VARCHAR(40)  NOT NULL,
    dst_number  VARCHAR(40)  NOT NULL,
    codec       VARCHAR(20)  NULL,
    started_at  DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    INDEX idx_customer (customer_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- RESÚMENES PRECALCULADOS (cron nightly)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cdr_summary_day (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    summary_date    DATE         NOT NULL,
    customer_id     INT UNSIGNED NOT NULL,
    carrier_id      INT UNSIGNED NULL,
    nbcall          INT UNSIGNED NOT NULL DEFAULT 0,       -- llamadas contestadas
    nbcall_fail     INT UNSIGNED NOT NULL DEFAULT 0,       -- fallidas
    sessiontime     INT UNSIGNED NOT NULL DEFAULT 0,       -- segundos totales
    buycost         DECIMAL(12,4) NOT NULL DEFAULT 0,
    sessionbill     DECIMAL(12,4) NOT NULL DEFAULT 0,
    lucro           DECIMAL(12,4) NOT NULL DEFAULT 0,
    asr             DECIMAL(5,2)  NOT NULL DEFAULT 0,      -- % contestadas
    aloc            DECIMAL(8,2)  NOT NULL DEFAULT 0,      -- duración promedio seg.
    UNIQUE KEY uq_day_cust_carrier (summary_date, customer_id, carrier_id),
    INDEX idx_date (summary_date),
    INDEX idx_customer (customer_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS cdr_summary_month (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    summary_month   CHAR(7)      NOT NULL,                 -- "2026-06"
    customer_id     INT UNSIGNED NOT NULL,
    carrier_id      INT UNSIGNED NULL,
    nbcall          INT UNSIGNED NOT NULL DEFAULT 0,
    nbcall_fail     INT UNSIGNED NOT NULL DEFAULT 0,
    sessiontime     INT UNSIGNED NOT NULL DEFAULT 0,
    buycost         DECIMAL(12,4) NOT NULL DEFAULT 0,
    sessionbill     DECIMAL(12,4) NOT NULL DEFAULT 0,
    lucro           DECIMAL(12,4) NOT NULL DEFAULT 0,
    asr             DECIMAL(5,2)  NOT NULL DEFAULT 0,
    aloc            DECIMAL(8,2)  NOT NULL DEFAULT 0,
    UNIQUE KEY uq_month_cust_carrier (summary_month, customer_id, carrier_id),
    INDEX idx_month    (summary_month),
    INDEX idx_customer (customer_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Margen de reseller — tabla separada de cdr_summary_day a propósito: el filtro
-- de fuente es distinto (disposition='ANSWERED' AND reseller_cost IS NOT NULL,
-- ver cdrs.py::ingest_cdr — reseller_cost solo existe con billsec>0 y
-- parent_customer_id) del que usa cdr_summary_day (todas las llamadas salvo
-- RESTART_ORPHANED). Sumar reseller_cost como columna extra en esa misma fila
-- daría un margen inflado por llamadas fallidas con sessionbill pero sin
-- reseller_cost — mismo tipo de bug de ASR ya encontrado antes en esta tabla.
CREATE TABLE IF NOT EXISTS cdr_summary_day_reseller (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    summary_date    DATE         NOT NULL,
    customer_id     INT UNSIGNED NOT NULL,     -- sub-cliente (cdrs.customer_id)
    nbcall          INT UNSIGNED  NOT NULL DEFAULT 0,
    revenue         DECIMAL(12,4) NOT NULL DEFAULT 0,  -- sessionbill
    cost            DECIMAL(12,4) NOT NULL DEFAULT 0,  -- reseller_cost
    margin          DECIMAL(12,4) NOT NULL DEFAULT 0,
    UNIQUE KEY uq_day_cust (summary_date, customer_id),
    INDEX idx_customer (customer_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Consumo/rentabilidad por área (backend/routers/areas.py::area_report(), y su
-- espejo cliente portal.py::my_report_by_area()) — agregado diario por
-- (cliente, prefix_matched), NO por nombre de área: el nombre se resuelve con
-- un JOIN a `prefixes` en el momento de leer, igual que cdr_summary_day
-- resuelve customer_id/carrier_id contra customers/carriers. Si se guardara
-- el nombre de área ya resuelto acá, renombrar un área (areas.py::
-- update_area(), que ya cascadea a prefixes.group_name) dejaría el histórico
-- cacheado con el nombre viejo hasta el próximo recálculo — con
-- prefix_matched como clave, un rename se refleja al instante en todo el
-- histórico, sin tocar esta tabla.
-- customer_id sí es parte de la clave (a diferencia de la primera versión de
-- esta tabla) — hace falta para el desglose "por cliente" del admin y para
-- que el cliente vea SOLO lo suyo en su portal. area_report() sin filtro de
-- cliente simplemente suma ignorando esta columna (SUM de todos los clientes).
-- pdd_ms_sum: PDD (post-dial delay) no se trackeaba en ningún lado — se
-- aproxima con start_ts→answer_ts (tiempo hasta 200 OK; no se trackea el
-- 180 Ringing por separado). Se guarda la SUMA de ms, no el promedio, para
-- poder promediar bien al combinar varios días (promediar promedios da un
-- número incorrecto si los días tienen distinto volumen de llamadas).
CREATE TABLE IF NOT EXISTS cdr_summary_day_area (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    summary_date    DATE         NOT NULL,
    customer_id     INT UNSIGNED NOT NULL,
    prefix_matched  VARCHAR(20)  NOT NULL DEFAULT '',  -- '' = CDRs sin prefix_matched (ver "Sin área")
    nbcall          INT UNSIGNED    NOT NULL DEFAULT 0,  -- contestadas
    nbcall_fail     INT UNSIGNED    NOT NULL DEFAULT 0,  -- fallidas (para ASR)
    sessiontime     INT UNSIGNED    NOT NULL DEFAULT 0,  -- segundos, solo contestadas (para ACD)
    pdd_ms_sum      BIGINT UNSIGNED NOT NULL DEFAULT 0,  -- suma de ms hasta contestar (para PDD)
    buycost         DECIMAL(12,4) NOT NULL DEFAULT 0,
    sessionbill     DECIMAL(12,4) NOT NULL DEFAULT 0,
    lucro           DECIMAL(12,4) NOT NULL DEFAULT 0,
    UNIQUE KEY uq_day_cust_prefix (summary_date, customer_id, prefix_matched),
    INDEX idx_date (summary_date),
    INDEX idx_customer (customer_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Consumo por prefijo de campaña propio del cliente (portal.py::my_campaigns())
-- — techprefix acá es el prefijo del MARCADOR del cliente (ej. Vicidial),
-- no el destino de la llamada (eso es cdr_summary_day_area de arriba). Antes
-- este reporte escaneaba cdrs en vivo en cada carga (documentado como
-- "no se tocan cdr_summary_day/month en esta primera vuelta" — esta es esa
-- segunda vuelta). Mismo criterio híbrido: días cerrados desde acá, hoy en
-- vivo acotado a su partición diaria.
CREATE TABLE IF NOT EXISTS cdr_summary_day_campaign (
    id            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    summary_date  DATE         NOT NULL,
    customer_id   INT UNSIGNED NOT NULL,
    techprefix    VARCHAR(20)  NOT NULL DEFAULT '',  -- '' = cdrs.techprefix NULL (histórico previo a v2.42.0, ver "Sin campaña")
    nbcall        INT UNSIGNED  NOT NULL DEFAULT 0,  -- contestadas
    sessiontime   INT UNSIGNED  NOT NULL DEFAULT 0,  -- segundos, solo contestadas
    sessionbill   DECIMAL(12,4) NOT NULL DEFAULT 0,
    UNIQUE KEY uq_day_cust_techprefix (summary_date, customer_id, techprefix),
    INDEX idx_customer (customer_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- FIREWALL (reglas nftables gestionadas desde admin)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS firewall_rules (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    ip          VARCHAR(50)  NOT NULL,
    action      ENUM('allow','deny') NOT NULL DEFAULT 'allow',
    service     ENUM('all','sip','rtp','ssh','icmp') NOT NULL DEFAULT 'all',
    description VARCHAR(180) NULL,
    jail        TINYINT(1)   NOT NULL DEFAULT 0,
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_action (action)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- FACTURAS
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS invoices (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    customer_id     INT UNSIGNED  NOT NULL,
    period_start    DATE          NOT NULL,
    period_end      DATE          NOT NULL,
    nbcall          INT UNSIGNED  NOT NULL DEFAULT 0,
    total_minutes   DECIMAL(10,2) NOT NULL DEFAULT 0,
    subtotal        DECIMAL(12,4) NOT NULL DEFAULT 0,
    tax_rate        DECIMAL(5,2)  NOT NULL DEFAULT 18.00,  -- IGV Perú
    tax_amount      DECIMAL(12,4) NOT NULL DEFAULT 0,
    total           DECIMAL(12,4) NOT NULL DEFAULT 0,
    currency        CHAR(3)       NOT NULL DEFAULT 'PEN',
    status          ENUM('draft','sent','paid','cancelled') NOT NULL DEFAULT 'draft',
    pdf_path        VARCHAR(255)  NULL,
    paid_at         DATETIME      NULL,
    emailed_at      DATETIME      NULL,
    notes           TEXT          NULL,
    -- NULL = el pago de esta factura todavía no se acreditó al balance del
    -- cliente. Se estampa una sola vez, al marcarla 'paid' (o en el backfill
    -- de una-sola-vez para facturas que ya estaban 'paid' antes de este
    -- cambio) — evita acreditar dos veces si mark-paid se llama otra vez o
    -- si el backfill corre más de una vez sobre la misma factura.
    balance_credited_at DATETIME  NULL,
    created_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_customer (customer_id),
    INDEX idx_status   (status),
    INDEX idx_period   (period_start, period_end),
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- TRAZAS SIP (mini-Homer embebido — recibe HEP3 desde Kamailio)
-- Retención: solo el día en curso (limpieza automática por sip-hep.service +
-- cron_partitions.py, ver backend/hep_listener.py::_cleanup)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sip_traces (
    id          BIGINT UNSIGNED AUTO_INCREMENT,
    call_id     VARCHAR(255)    NOT NULL,
    captured_at DATETIME(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    src_ip      VARCHAR(45)     NOT NULL DEFAULT '',
    src_port    SMALLINT UNSIGNED NULL,
    dst_ip      VARCHAR(45)     NOT NULL DEFAULT '',
    dst_port    SMALLINT UNSIGNED NULL,
    sip_method  VARCHAR(20)     NULL,            -- INVITE, BYE, ACK… (NULL si es response)
    sip_status  SMALLINT UNSIGNED NULL,          -- 100, 180, 200, 4xx… (NULL si es request)
    from_uri    VARCHAR(80)     NULL,            -- número origen (user part del From: header)
    to_uri      VARCHAR(80)     NULL,            -- número destino (user part del To: header)
    request_uri VARCHAR(180)    NULL,            -- Request-URI de la primera línea (INVITE/BYE/etc.)
    user_agent  VARCHAR(120)    NULL,
    via_branch  VARCHAR(80)     NULL,
    cseq        VARCHAR(40)     NULL,
    reason      VARCHAR(80)     NULL,            -- Reason header (e.g. "SIP ;cause=486 ;text=Busy Here")
    raw_message TEXT            NOT NULL,        -- TEXT max 64KB — suficiente para SIP
    INDEX idx_call_id         (call_id),
    INDEX idx_captured        (captured_at),     -- range query para cleanup y búsqueda por fecha
    INDEX idx_from_uri        (from_uri),
    INDEX idx_to_uri          (to_uri),
    INDEX idx_cid_captured    (call_id, captured_at), -- búsqueda call_id + fecha (traces search)
    PRIMARY KEY (id, captured_at)           -- captured_at en la PK: requisito de MySQL para particionar por esa columna
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC DEFAULT CHARSET=utf8mb4
-- Particionado por día — la retención real es "solo hoy" (ver backend/hep_listener.py::_cleanup),
-- así que borrar por DROP PARTITION en vez de DELETE evita el costo fila-por-fila en una tabla
-- de alto volumen. scripts/cron_partitions.py crea las particiones de los próximos días y
-- elimina las vencidas todas las noches.
PARTITION BY RANGE (TO_DAYS(captured_at)) (
    PARTITION p_start  VALUES LESS THAN (TO_DAYS('2000-01-01')),
    PARTITION p_future VALUES LESS THAN MAXVALUE
);

-- -----------------------------------------------------------------------------
-- CONFIGURACIÓN GLOBAL
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS settings (
    key_name    VARCHAR(60)  NOT NULL PRIMARY KEY,
    value       TEXT         NOT NULL,
    description VARCHAR(255) NULL,
    updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- MIGRACIONES DE SCHEMA — desde v2.53.0 (ver deploy.sh::run_pending_migrations())
-- -----------------------------------------------------------------------------
-- Reemplaza el patrón viejo de "ALTER TABLE ... ADD COLUMN IF NOT EXISTS"
-- repetido a mano en las ramas --update y --upgrade de deploy.sh (llevaba a
-- podas manuales periódicas del propio deploy.sh contra dumps reales, ver
-- CHANGELOG v2.52.4 y v2.52.3). Cada versión con cambios de schema se
-- registra una sola vez acá — un deploy futuro consulta esta tabla y corre
-- SOLO lo que falte, sin volver a chequear columna por columna cada vez.
-- Bootstrap: en cualquier instalación existente que llega a v2.53.0 (todo el
-- parque real a la fecha de este cambio), se asume el schema ya al día hasta
-- acá — se siembra la fila '2.53.0' sin correr SQL, ya que todos los ALTER
-- necesarios para llegar hasta acá ya corrieron con el patrón viejo.
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     VARCHAR(20) NOT NULL PRIMARY KEY,
    applied_at  DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- AUDITORÍA DE CONFIG — selectiva, no un log de todo (ver backend/audit.py)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS settings_history (
    id          BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    entity      VARCHAR(30)   NOT NULL,        -- customer, carrier, firewall_rule, alert_rule, admin_user...
    entity_id   INT UNSIGNED  NOT NULL,
    field       VARCHAR(40)   NOT NULL,        -- nombre de columna, o evento (created/deleted/activated...)
    old_value   TEXT          NULL,
    new_value   TEXT          NULL,
    changed_by  VARCHAR(120)  NULL,            -- nombre del admin (users.name)
    changed_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_entity (entity, entity_id, changed_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- SINCRONIZACIÓN EXTERNA DE CDRs (opcional) — un solo destino, fila fija id=1
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS external_sync_config (
    id            TINYINT UNSIGNED PRIMARY KEY DEFAULT 1,
    engine        ENUM('mysql','postgres','sqlserver') NOT NULL DEFAULT 'mysql',
    host          VARCHAR(120)  NOT NULL DEFAULT '',
    port          SMALLINT UNSIGNED NOT NULL DEFAULT 3306,
    db_name       VARCHAR(120)  NOT NULL DEFAULT '',
    db_user       VARCHAR(120)  NOT NULL DEFAULT '',
    db_pass       VARCHAR(255)  NOT NULL DEFAULT '',
    enabled       TINYINT(1)    NOT NULL DEFAULT 0,
    last_sync_at  DATETIME      NULL,
    last_sync_id  BIGINT UNSIGNED NOT NULL DEFAULT 0,  -- cursor: último cdrs.id sincronizado (incremental)
    last_status   VARCHAR(20)   NULL,
    last_error    TEXT          NULL,
    updated_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
INSERT IGNORE INTO external_sync_config (id) VALUES (1);

CREATE TABLE IF NOT EXISTS external_sync_log (
    id          BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    started_at  DATETIME NOT NULL,
    finished_at DATETIME NULL,
    rows_synced INT UNSIGNED NOT NULL DEFAULT 0,  -- insertadas con éxito en el destino
    -- Antes cron_external_sync.py tragaba CUALQUIER error por fila (no solo
    -- duplicados de un reintento) y rows_synced contaba filas LEÍDAS de
    -- cdrs, no filas realmente insertadas — status quedaba en 'ok' aunque
    -- se perdieran filas en el destino, sin ningún rastro.
    rows_failed INT UNSIGNED NOT NULL DEFAULT 0,
    status      VARCHAR(20) NOT NULL,   -- running / ok / partial / error
    detail      TEXT NULL,
    INDEX idx_started (started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- WEBHOOKS — notificaciones salientes por evento (ver backend/webhooks.py)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS webhooks (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    url         VARCHAR(500) NOT NULL,
    event       VARCHAR(50)  NOT NULL,  -- cdr.created / customer.balance_alert / customer.status_changed
    secret      VARCHAR(64)  NOT NULL,  -- firma HMAC-SHA256 en header X-VoxiKam-Signature
    enabled     TINYINT(1)   NOT NULL DEFAULT 1,
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_event (event, enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- DISCONNECT POLICIES — alertas por % de un tipo de corte sobre traffic_quality_hourly
-- (NO suspende ni bloquea nada — mismo criterio que balance_alert_rules: solo avisa)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS disconnect_policies (
    id            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    label         VARCHAR(100) NOT NULL,
    code_column   ENUM('c_487','c_486','c_404','c_503','c_other','short_calls') NOT NULL,
    threshold_pct DECIMAL(5,2) NOT NULL,
    min_calls     INT UNSIGNED NOT NULL DEFAULT 20,  -- mínimo de llamadas en la hora para evaluar (evita falsos positivos con poco volumen)
    active        TINYINT(1)   NOT NULL DEFAULT 1,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
INSERT IGNORE INTO disconnect_policies (id, label, code_column, threshold_pct, min_calls) VALUES
    (1, 'Congestión — muchos 503 (sin carriers)',       'c_503', 30, 20),
    (2, 'Muchos rechazos — 486 (ocupado)',               'c_486', 50, 20),
    (3, 'Destino no encontrado — muchos 404',            'c_404', 40, 20);

CREATE TABLE IF NOT EXISTS disconnect_policy_alerts (
    id          BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    policy_id   INT UNSIGNED NOT NULL,
    customer_id INT UNSIGNED NOT NULL,
    ts_hour     DATETIME     NOT NULL,
    pct         DECIMAL(5,2) NOT NULL,
    total_calls INT UNSIGNED NOT NULL,
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_policy_customer_hour (policy_id, customer_id, ts_hour)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id          BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    webhook_id  INT UNSIGNED NOT NULL,
    event       VARCHAR(50)  NOT NULL,
    payload     TEXT         NOT NULL,
    status_code SMALLINT     NULL,
    attempt     TINYINT UNSIGNED NOT NULL DEFAULT 1,
    success     TINYINT(1)   NOT NULL DEFAULT 0,
    error       TEXT         NULL,
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_webhook (webhook_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- API KEYS — acceso programático de clientes a /api/v1/* (saldo, CDRs).
-- Credencial de ENTRADA (a diferencia de webhooks.secret, que se reutiliza para
-- firmar salidas) — por eso solo se guarda el hash, nunca la key en texto plano.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS api_keys (
    id            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    customer_id   INT UNSIGNED  NOT NULL,
    label         VARCHAR(100)  NOT NULL DEFAULT '',
    key_prefix    VARCHAR(12)   NOT NULL,   -- ej "vk_live_xxxx", para identificar en el panel
    key_hash      VARCHAR(64)   NOT NULL,   -- SHA-256 hex de la key completa
    created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_used_at  DATETIME      NULL,
    revoked       TINYINT(1)    NOT NULL DEFAULT 0,
    revoked_at    DATETIME      NULL,
    UNIQUE KEY uq_key_hash (key_hash),
    INDEX idx_customer (customer_id, revoked),
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- COMENTARIOS INTERNOS (Logic log) — notas atribuidas y con fecha, distinto de
-- customers.notes (un solo campo libre que se pisa en cada edición)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS entity_comments (
    id          BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    entity      ENUM('customer','carrier') NOT NULL,
    entity_id   INT UNSIGNED NOT NULL,
    body        TEXT         NOT NULL,
    created_by  VARCHAR(120) NULL,
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_entity (entity, entity_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- CALIDAD DE MEDIO (RTP) por llamada — vía RTPEngine → homer/HEP (proto_type=5,
-- PROTO_RTCP_JSON), capturado por backend/hep_listener.py. Una fila por
-- call_id, valores PEOR observado durante la llamada (no promedio) — más útil
-- para diagnóstico que un promedio que puede esconder un pico puntual.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS call_media_stats (
    call_id              VARCHAR(255)  NOT NULL PRIMARY KEY,
    max_jitter_ms         DECIMAL(8,2) NOT NULL DEFAULT 0,
    max_packet_loss_pct   DECIMAL(5,2) NOT NULL DEFAULT 0,
    packets_lost           INT UNSIGNED NOT NULL DEFAULT 0, -- acumulado, del último reporte RTCP (dato real, no derivado)
    report_count          INT UNSIGNED NOT NULL DEFAULT 0,
    -- sum_* / report_count = promedio de toda la llamada (mismo criterio que
    -- "Average Jitter" del carrier, ej. Digitalk) — el peor valor (arriba)
    -- sigue guardándose aparte, sirve para detectar picos puntuales, pero
    -- como badge de "Calidad" usar solo el peor de N reportes marca como
    -- mala una llamada excelente que tuvo un solo microcorte (caso real
    -- encontrado: 112 reportes, 1 pico de 58ms, promedio real 0.078ms).
    sum_jitter_ms          DECIMAL(14,4) NOT NULL DEFAULT 0,
    sum_packet_loss_pct    DECIMAL(14,4) NOT NULL DEFAULT 0,
    updated_at            DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_updated (updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SET foreign_key_checks = 1;
