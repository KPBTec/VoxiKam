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
    customer_id   INT UNSIGNED  NULL,          -- NULL si role=admin
    is_active     TINYINT(1)    NOT NULL DEFAULT 1,
    created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_role (role),
    INDEX idx_customer (customer_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- PERFILES DE CLIENTE (conjuntos de módulos reutilizables)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS customer_profiles (
    id               INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name             VARCHAR(100)  NOT NULL,
    description      TEXT          NULL,
    show_calls       TINYINT(1)    NOT NULL DEFAULT 1,
    show_quality     TINYINT(1)    NOT NULL DEFAULT 1,
    show_reports     TINYINT(1)    NOT NULL DEFAULT 1,
    show_invoices    TINYINT(1)    NOT NULL DEFAULT 0,
    show_trunk_guide TINYINT(1)    NOT NULL DEFAULT 1,
    created_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- CLIENTES (trunks SIP)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS customers (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
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
    techprefix      VARCHAR(20)   NOT NULL DEFAULT '',        -- prefijo asignado (ej: 1001)
    currency        CHAR(3)       NOT NULL DEFAULT 'PEN',
    show_calls      TINYINT(1)    NOT NULL DEFAULT 1,         -- módulo Mis llamadas
    show_quality    TINYINT(1)    NOT NULL DEFAULT 1,         -- módulo Calidad ASR
    show_reports    TINYINT(1)    NOT NULL DEFAULT 1,         -- módulo Reportes
    show_invoices   TINYINT(1)    NOT NULL DEFAULT 0,         -- módulo Facturas (deshabilitado por defecto)
    show_trunk_guide TINYINT(1)   NOT NULL DEFAULT 1,         -- módulo Trunk Guide
    status          ENUM('active','suspended','expired') NOT NULL DEFAULT 'active',
    notes           TEXT          NULL,
    created_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_status (status),
    INDEX idx_techprefix (techprefix)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

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
-- CARRIERS (providers SIP salientes)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS carriers (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name            VARCHAR(120)  NOT NULL,
    host            VARCHAR(100)  NOT NULL,
    port            SMALLINT UNSIGNED NOT NULL DEFAULT 5060,
    priority        TINYINT UNSIGNED  NOT NULL DEFAULT 10,   -- mayor = primero en dispatcher
    outbound_prefix VARCHAR(20)   NOT NULL DEFAULT '',       -- prefijo que agrega este carrier
    remove_prefix   VARCHAR(20)   NOT NULL DEFAULT '',       -- prefijo a quitar antes de enviar
    failover_id     INT UNSIGNED  NULL,                      -- carrier de fallback
    dispatcher_group SMALLINT UNSIGNED NOT NULL DEFAULT 2,   -- grupo base en dispatcher.list
    status          ENUM('active','inactive','maintenance') NOT NULL DEFAULT 'active',
    notes           TEXT          NULL,
    created_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- ASIGNACIÓN CLIENTE ↔ CARRIERS
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS customer_carriers (
    customer_id INT UNSIGNED NOT NULL,
    carrier_id  INT UNSIGNED NOT NULL,
    priority    TINYINT UNSIGNED NOT NULL DEFAULT 10,
    PRIMARY KEY (customer_id, carrier_id),
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
    FOREIGN KEY (carrier_id)  REFERENCES carriers(id)  ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- PREFIJOS DESTINO (tabla global de destinos)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS prefixes (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    prefix      VARCHAR(20)  NOT NULL UNIQUE,
    destination VARCHAR(100) NOT NULL,
    group_name  VARCHAR(50)  NOT NULL DEFAULT '',  -- agrupación para precio por grupo (ej: FIJO LIMA)
    country     VARCHAR(60)  NULL,
    INDEX idx_prefix (prefix),
    INDEX idx_group  (group_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Tabla de optimización para longest-prefix-match (Magnus pattern)
CREATE TABLE IF NOT EXISTS prefix_lengths (
    length      TINYINT UNSIGNED NOT NULL,
    count       INT UNSIGNED     NOT NULL DEFAULT 0,
    PRIMARY KEY (length)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- PLANES TARIFARIOS
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rate_plans (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(80)  NOT NULL UNIQUE,
    currency    CHAR(3)      NOT NULL DEFAULT 'PEN',
    description VARCHAR(255) NULL,
    status      ENUM('active','inactive') NOT NULL DEFAULT 'active',
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
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
    initblock             SMALLINT UNSIGNED NOT NULL DEFAULT 60,      -- seg. primer bloque
    billingblock          SMALLINT UNSIGNED NOT NULL DEFAULT 60,      -- seg. bloques siguientes
    minimal_time_charge   SMALLINT UNSIGNED NOT NULL DEFAULT 0,       -- mínimo facturable seg.
    status                ENUM('active','inactive') NOT NULL DEFAULT 'active',
    effective_date        DATE NULL,
    UNIQUE KEY uq_plan_prefix (rate_plan_id, prefix_id),
    INDEX idx_rate_plan (rate_plan_id),
    FOREIGN KEY (rate_plan_id) REFERENCES rate_plans(id) ON DELETE CASCADE,
    FOREIGN KEY (prefix_id)    REFERENCES prefixes(id)   ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- TARIFAS CARRIER — lo que me cobra el carrier (buy rates)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS carrier_rates (
    id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    carrier_id      INT UNSIGNED  NOT NULL,
    prefix_id       INT UNSIGNED  NOT NULL,
    buy_rate        DECIMAL(10,6) NOT NULL DEFAULT 0.000000,  -- S/./min que me cobra
    connect_charge  DECIMAL(10,6) NOT NULL DEFAULT 0.000000,
    billingblock    SMALLINT UNSIGNED NOT NULL DEFAULT 60,
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
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    call_id         VARCHAR(120)  NOT NULL,               -- Call-ID SIP
    customer_id     INT UNSIGNED  NOT NULL,
    carrier_id      INT UNSIGNED  NULL,
    src_ip          VARCHAR(45)   NOT NULL,
    src_number      VARCHAR(40)   NOT NULL,               -- CLI (caller)
    dst_number      VARCHAR(40)   NOT NULL,               -- destino sin prefijo
    dst_number_raw  VARCHAR(40)   NOT NULL,               -- destino con prefijo del cliente
    prefix_matched  VARCHAR(20)   NULL,                   -- prefijo que hizo match
    start_ts        DATETIME(3)   NOT NULL,
    answer_ts       DATETIME(3)   NULL,
    end_ts          DATETIME(3)   NULL,
    sessiontime     INT UNSIGNED  NOT NULL DEFAULT 0,     -- duración total seg.
    billsec         INT UNSIGNED  NOT NULL DEFAULT 0,     -- seg. facturables
    buycost         DECIMAL(10,6) NOT NULL DEFAULT 0,     -- lo que me cobra el carrier
    sessionbill     DECIMAL(10,6) NOT NULL DEFAULT 0,     -- lo que cobro al cliente
    lucro           DECIMAL(10,6) GENERATED ALWAYS AS (sessionbill - buycost) STORED,
    sip_code        SMALLINT UNSIGNED NOT NULL DEFAULT 200,  -- código SIP final (200 contestada, 486 ocupado, 487 cancelada, etc.)
    disposition     ENUM('ANSWERED','NO_ANSWER','BUSY','FAILED') NOT NULL DEFAULT 'ANSWERED',
    call_state      VARCHAR(20)   NULL,                      -- sngrep-style: COMPLETED CANCELLED BUSY REJECTED DIVERTED
    hangup_cause    VARCHAR(30)   NULL,
    INDEX idx_customer_date   (customer_id, start_ts),
    INDEX idx_carrier_date    (carrier_id, start_ts),
    INDEX idx_date            (start_ts),
    INDEX idx_call_id         (call_id),
    INDEX idx_disposition     (disposition)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

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

-- -----------------------------------------------------------------------------
-- FIREWALL (reglas nftables gestionadas desde admin)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS firewall_rules (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    ip          VARCHAR(50)  NOT NULL,
    action      ENUM('allow','deny') NOT NULL DEFAULT 'allow',
    service     ENUM('all','sip','rtp','ssh') NOT NULL DEFAULT 'all',
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
    notes           TEXT          NULL,
    created_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_customer (customer_id),
    INDEX idx_status   (status),
    INDEX idx_period   (period_start, period_end),
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- TRAZAS SIP (mini-Homer embebido — recibe HEP3 desde Kamailio)
-- Retención: 7 días (limpieza automática por sip-hep.service)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sip_traces (
    id          BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
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
    INDEX idx_cid_captured    (call_id, captured_at) -- búsqueda call_id + fecha (traces search)
) ENGINE=InnoDB ROW_FORMAT=DYNAMIC DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- CONFIGURACIÓN GLOBAL
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS settings (
    key_name    VARCHAR(60)  NOT NULL PRIMARY KEY,
    value       TEXT         NOT NULL,
    description VARCHAR(255) NULL,
    updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SET foreign_key_checks = 1;
