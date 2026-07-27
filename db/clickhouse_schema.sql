-- VoxiKam — SIP Class 4 Billing & Monitoring Platform
-- Copyright (c) 2026 KPBTec
-- By KPBTec · https://github.com/KPBTec
-- © 2026 – Todos los derechos reservados.
--
-- Schema ClickHouse para sip_traces (captura HEP de trazas SIP) — separada de
-- MariaDB (db/schema.sql) por volumen: MySQL/InnoDB no puede sostener la
-- retención de 90 días configurable desde el panel a este ritmo de escritura
-- sin disco desproporcionado. cdrs, customers, call_media_stats y el resto
-- del schema siguen 100% en MariaDB — solo sip_traces se mueve acá.
--
-- deploy.sh ya la aplica solo (PASO 6b). Para aplicarla a mano: usar el
-- ch_native_port de credentials.conf (protocolo nativo, no ch_port/8123 que
-- es la interfaz HTTP) — los puertos son random por instalación, no 9000 fijo:
--   clickhouse-client --host 127.0.0.1 --port <ch_native_port> < db/clickhouse_schema.sql

CREATE DATABASE IF NOT EXISTS sip_platform;

CREATE TABLE IF NOT EXISTS sip_platform.sip_traces
(
    id           UInt64,
    call_id      String,
    captured_at  DateTime64(3),
    src_ip       String,
    src_port     Nullable(UInt16),
    dst_ip       String,
    dst_port     Nullable(UInt16),
    sip_method   LowCardinality(Nullable(String)),
    sip_status   Nullable(UInt16),
    -- String no-nullable (no Nullable(String)) — el índice ngrambf_v1 de abajo
    -- no soporta columnas Nullable (BAD_ARGUMENTS real al aplicar el schema).
    -- '' hace de sentinel en vez de NULL para respuestas SIP sin from/to.
    from_uri     String,
    to_uri       String,
    request_uri  Nullable(String),
    user_agent   Nullable(String),
    via_branch   Nullable(String),
    cseq         Nullable(String),
    reason       Nullable(String),
    raw_message  String,

    INDEX idx_from_uri from_uri TYPE ngrambf_v1(4, 4096, 2, 0) GRANULARITY 4,
    INDEX idx_to_uri   to_uri   TYPE ngrambf_v1(4, 4096, 2, 0) GRANULARITY 4
)
ENGINE = MergeTree
-- Particionado diario: da pruning por fecha a /calls y /stream, y hace que
-- el TTL de abajo purgue soltando particiones enteras (barato), igual que
-- DROP PARTITION en el esquema viejo de MySQL (scripts/cron_partitions.py).
PARTITION BY toDate(captured_at)
-- call_id primero: el lookup exacto por Call-ID (ladder diagram, export
-- .pcap — backend/routers/traces.py::get_trace()/download_pcap()) es el path
-- de lectura más caliente; captured_at/id dan el orden cronológico correcto
-- dentro de una misma llamada sin necesidad de ORDER BY explícito costoso.
ORDER BY (call_id, captured_at, id)
-- Valor inicial = settings.sip_traces_retention_hours actual (2160h/90 días).
-- Se mantiene sincronizado en vivo desde el panel Traffic Sampling — ver
-- backend/routers/traffic_sampling.py::set_config().
TTL toDateTime(captured_at) + INTERVAL 2160 HOUR
SETTINGS index_granularity = 8192;
