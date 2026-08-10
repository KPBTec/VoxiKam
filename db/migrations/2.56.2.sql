-- Re-auditoría v2.56.0 (hallazgo alto): el rate limiting (por IP en
-- middleware/security.py y por cuenta en routers/auth.py) vivía en un dict
-- en memoria POR PROCESO — con uvicorn --workers N, el límite real quedaba
-- fragmentado en un factor ~N. Esta tabla es el almacén compartido entre
-- workers (mismo criterio ya usado para cors_state vía settings en
-- _cors_origin_syncer, backend/main.py).
--
-- Diseño "fixed window" (bucket = floor(unix_ts / window) * window) en vez
-- de sliding window real: UN solo INSERT...ON DUPLICATE KEY
-- UPDATE...RETURNING count por request, atómico — probado contra MariaDB
-- 11.8.6 real. Un sliding window real (fila por intento, DELETE+SELECT+INSERT)
-- sería 3 round-trips por request en un middleware que corre en casi todo el
-- tráfico — no vale el costo para la precisión extra que da.
CREATE TABLE IF NOT EXISTS rate_limit_counters (
    rl_key       VARCHAR(320)     NOT NULL,
    window_start BIGINT UNSIGNED  NOT NULL,
    count        INT UNSIGNED     NOT NULL DEFAULT 1,
    PRIMARY KEY (rl_key, window_start)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
