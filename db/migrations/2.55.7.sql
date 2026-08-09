-- _billing_worker (backend/main.py) hace SELECT ... FOR UPDATE SKIP LOCKED
-- filtrando por buycost=0 AND sessionbill=0 — sin un índice que arranque por
-- esos dos campos, el motor examina (y bloquea de paso) filas ya facturadas
-- que no matchean, y con --workers > 1 (varios procesos corriendo este
-- worker en paralelo) eso produce deadlocks reales entre ellos — confirmado
-- en producción (vd1sbc2, 2026-08-09). SKIP LOCKED por sí solo no alcanza
-- si el índice no acota qué filas se tocan.
ALTER TABLE cdrs ADD INDEX idx_billing_pending (buycost, sessionbill, disposition, start_ts);
