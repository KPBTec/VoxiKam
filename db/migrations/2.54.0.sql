CREATE TABLE IF NOT EXISTS providers (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(120) NOT NULL,
    notes       TEXT NULL,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- Auditoría v2.55 (workflow multi-agente): esta migración ya corrió bien en
-- producción, pero no era idempotente — ninguna de las 3 cláusulas tenía
-- IF NOT EXISTS, exactamente el mismo problema que causó el incidente real
-- con la migración 2.55.7 (ver esa migración y CHANGELOG v2.55.11). Retrofit
-- puramente defensivo para el próximo deploy, no cambia nada de lo ya
-- aplicado hoy.
ALTER TABLE carriers
    ADD COLUMN IF NOT EXISTS provider_id INT UNSIGNED NULL AFTER name,
    ADD INDEX IF NOT EXISTS idx_provider (provider_id);

-- MariaDB no tiene "ADD CONSTRAINT IF NOT EXISTS" — se chequea a mano contra
-- information_schema antes de intentar agregar el FK, mismo criterio.
SET @fk_exists = (
    SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'carriers'
      AND CONSTRAINT_NAME = 'fk_carriers_provider'
);
SET @ddl = IF(@fk_exists = 0,
    'ALTER TABLE carriers ADD CONSTRAINT fk_carriers_provider FOREIGN KEY (provider_id) REFERENCES providers(id) ON DELETE SET NULL',
    'SELECT 1');
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
