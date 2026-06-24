-- =============================================================================
-- KPBTec VoxiKam — Seed inicial
-- Ejecutar DESPUÉS de schema.sql
-- =============================================================================

SET NAMES utf8mb4;

-- -----------------------------------------------------------------------------
-- USUARIO ADMIN
-- -----------------------------------------------------------------------------
INSERT INTO users (name, email, password_hash, role, customer_id)
VALUES ('Administrador', '__ADMIN_EMAIL__', '__ADMIN_HASH__', 'admin', NULL);

-- -----------------------------------------------------------------------------
-- PLAN TARIFARIO POR DEFECTO
-- -----------------------------------------------------------------------------
INSERT INTO rate_plans (name, currency, description, status)
VALUES ('Plan Estándar PEN', 'PEN', 'Plan por defecto en soles peruanos', 'active');

-- -----------------------------------------------------------------------------
-- PREFIJOS — SOLO PERÚ
-- group_name define el grupo de precio: FIJO LIMA / FIJO PROVINCIA / MOVILES
-- Billing usa longest-prefix-match: 5154XXXXXX → match con 5154 (gana sobre 51)
-- -----------------------------------------------------------------------------
INSERT INTO prefixes (prefix, destination, group_name, country) VALUES
-- Fijo Lima y Callao (área 1)
('511',  'Fijo Lima y Callao',  'FIJO LIMA',       'PE'),

-- Fijos provincia (área 2 dígitos + 6 dígitos = 10 en total)
('5141', 'Fijo Amazonas',       'FIJO PROVINCIA',  'PE'),
('5143', 'Fijo Ancash',         'FIJO PROVINCIA',  'PE'),
('5183', 'Fijo Apurimac',       'FIJO PROVINCIA',  'PE'),
('5154', 'Fijo Arequipa',       'FIJO PROVINCIA',  'PE'),
('5166', 'Fijo Ayacucho',       'FIJO PROVINCIA',  'PE'),
('5176', 'Fijo Cajamarca',      'FIJO PROVINCIA',  'PE'),
('5184', 'Fijo Cusco',          'FIJO PROVINCIA',  'PE'),
('5167', 'Fijo Huancavelica',   'FIJO PROVINCIA',  'PE'),
('5162', 'Fijo Huanuco',        'FIJO PROVINCIA',  'PE'),
('5156', 'Fijo Ica',            'FIJO PROVINCIA',  'PE'),
('5164', 'Fijo Junin',          'FIJO PROVINCIA',  'PE'),
('5144', 'Fijo La Libertad',    'FIJO PROVINCIA',  'PE'),
('5174', 'Fijo Lambayeque',     'FIJO PROVINCIA',  'PE'),
('5165', 'Fijo Loreto',         'FIJO PROVINCIA',  'PE'),
('5182', 'Fijo Madre de Dios',  'FIJO PROVINCIA',  'PE'),
('5153', 'Fijo Moquegua',       'FIJO PROVINCIA',  'PE'),
('5163', 'Fijo Pasco',          'FIJO PROVINCIA',  'PE'),
('5173', 'Fijo Piura',          'FIJO PROVINCIA',  'PE'),
('5151', 'Fijo Puno',           'FIJO PROVINCIA',  'PE'),
('5142', 'Fijo San Martin',     'FIJO PROVINCIA',  'PE'),
('5152', 'Fijo Tacna',          'FIJO PROVINCIA',  'PE'),
('5172', 'Fijo Tumbes',         'FIJO PROVINCIA',  'PE'),
('5161', 'Fijo Ucayali',        'FIJO PROVINCIA',  'PE'),

-- Móviles (519X cubre todos: 9 es el primer dígito del número móvil peruano)
('5190', 'Moviles 90X',         'MOVILES',         'PE'),
('5191', 'Moviles 91X',         'MOVILES',         'PE'),
('5192', 'Moviles 92X',         'MOVILES',         'PE'),
('5193', 'Moviles 93X',         'MOVILES',         'PE'),
('5194', 'Moviles 94X',         'MOVILES',         'PE'),
('5195', 'Moviles 95X',         'MOVILES',         'PE'),
('5196', 'Moviles 96X',         'MOVILES',         'PE'),
('5197', 'Moviles 97X',         'MOVILES',         'PE'),
('5198', 'Moviles 98X',         'MOVILES',         'PE'),
('5199', 'Moviles 99X',         'MOVILES',         'PE');

-- Optimización para longest-prefix-match
INSERT INTO prefix_lengths (length, count)
SELECT LENGTH(prefix), COUNT(*) FROM prefixes GROUP BY LENGTH(prefix)
ON DUPLICATE KEY UPDATE count = VALUES(count);

-- -----------------------------------------------------------------------------
-- TARIFAS POR DEFECTO — aplica precio por grupo (ajustar en panel)
-- -----------------------------------------------------------------------------
INSERT INTO rates (rate_plan_id, prefix_id, rateinitial, connectcharge, initblock, billingblock, minimal_time_charge)
SELECT
    (SELECT id FROM rate_plans WHERE name = 'Plan Estándar PEN'),
    p.id,
    CASE
        WHEN p.group_name = 'MOVILES'         THEN 0.250000
        WHEN p.group_name = 'FIJO LIMA'       THEN 0.120000
        WHEN p.group_name = 'FIJO PROVINCIA'  THEN 0.120000
        ELSE 0.120000
    END,
    0.000000,
    60, 60, 0
FROM prefixes p;

-- -----------------------------------------------------------------------------
-- CONFIGURACIÓN GLOBAL
-- -----------------------------------------------------------------------------
INSERT INTO settings (key_name, value, description) VALUES
('platform_name',      '__PLATFORM_NAME__',    'Nombre de la plataforma'),
('platform_version',   '__PLATFORM_VERSION__', 'Versión instalada de la plataforma anterior'),
('default_currency',   'PEN',                  'Moneda por defecto'),
('tax_rate',           '18.00',                'IGV / IVA en porcentaje'),
('invoice_prefix',     'INV',                  'Prefijo para facturas'),
('invoice_next_number','1001',                 'Siguiente número de factura'),
('cdr_retention_days', '365',                  'Días de retención de CDRs'),
('public_ip',          '__PUBLIC_IP__',         'IP pública del SBC'),
('private_ip',         '__PRIVATE_IP__',        'IP privada del SBC'),
('sbc_domain',         '__SBC_DOMAIN__',        'Dominio del SBC para trunk guide'),
('ssh_port',           '__SSH_PORT__',          'Puerto SSH del servidor (para reglas firewall)'),
('lan_peers',          '',                      'IPs Asterisk/ViciBox LAN (host:puerto, coma-separados) — genera Grupo 1 dispatcher')
ON DUPLICATE KEY UPDATE value=VALUES(value), description=VALUES(description);
