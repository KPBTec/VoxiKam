-- Auditoría v2.55 (workflow multi-agente): ingest_cdr() hace
-- SELECT id FROM carriers WHERE host = :host, pero carriers no indexaba
-- host. Impacto bajo hoy (tabla chica), pero puramente defensivo y sin
-- costo si la tabla crece o el endpoint se reactiva.
ALTER TABLE carriers ADD INDEX IF NOT EXISTS idx_host (host);
