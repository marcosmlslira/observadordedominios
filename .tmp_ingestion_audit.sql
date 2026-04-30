\pset pager off
\echo 'SECTION:layer0_openintel_enabled'
SELECT source, count(*) AS total_habilitados,
       count(*) FILTER (WHERE priority <= 100) AS zonefile,
       count(*) FILTER (WHERE priority BETWEEN 101 AND 300) AS web_small,
       count(*) FILTER (WHERE priority > 300) AS web_large
FROM ingestion_tld_policy
WHERE source = 'openintel' AND is_enabled = true
GROUP BY source;

\echo 'SECTION:layer0_disabled'
SELECT source, tld, priority, updated_at
FROM ingestion_tld_policy
WHERE is_enabled = false
ORDER BY source, priority
LIMIT 200;

\echo 'SECTION:layer1_coverage_today'
WITH today_r2 AS (
    SELECT DISTINCT source, tld
    FROM ingestion_run
    WHERE phase IN ('r2', 'full')
      AND status = 'success'
      AND COALESCE(snapshot_date, started_at::date) = CURRENT_DATE
),
enabled AS (
    SELECT source, tld FROM ingestion_tld_policy WHERE is_enabled = true
)
SELECT e.source,
    count(*) AS total_habilitados,
    count(r.tld) AS r2_ok_hoje,
    count(*) - count(r.tld) AS r2_faltando,
    round(count(r.tld)::numeric / count(*) * 100, 1) AS cobertura_pct
FROM enabled e
LEFT JOIN today_r2 r ON r.source = e.source AND r.tld = e.tld
GROUP BY e.source
ORDER BY e.source;

\echo 'SECTION:layer1_missing_recent3d'
WITH recent_r2 AS (
    SELECT DISTINCT source, tld
    FROM ingestion_run
    WHERE phase IN ('r2', 'full')
      AND status = 'success'
      AND COALESCE(snapshot_date, started_at::date) >= CURRENT_DATE - 3
)
SELECT p.source, p.tld, p.priority
FROM ingestion_tld_policy p
LEFT JOIN recent_r2 r ON r.source = p.source AND r.tld = p.tld
WHERE p.is_enabled = true
  AND r.tld IS NULL
ORDER BY p.source, p.priority;

\echo 'SECTION:layer2_dual_phase_today'
SELECT source, r2_status, pg_status, count(*) AS tlds
FROM tld_daily_status_v
WHERE day = CURRENT_DATE
GROUP BY source, r2_status, pg_status
ORDER BY source, r2_status, pg_status;

\echo 'SECTION:layer2_r2ok_pg_not_success'
WITH latest_r2 AS (
    SELECT DISTINCT ON (source, tld)
        source, tld,
        COALESCE(snapshot_date, started_at::date) AS snap_date
    FROM ingestion_run
    WHERE phase IN ('r2', 'full')
      AND status = 'success'
    ORDER BY source, tld, started_at DESC
),
latest_pg AS (
    SELECT DISTINCT ON (source, tld)
        source, tld, status AS pg_status
    FROM ingestion_run
    WHERE phase IN ('pg', 'full')
    ORDER BY source, tld, started_at DESC
)
SELECT r.source, r.tld, r.snap_date, COALESCE(p.pg_status, 'never_run') AS pg_status
FROM latest_r2 r
LEFT JOIN latest_pg p ON p.source = r.source AND p.tld = r.tld
WHERE COALESCE(p.pg_status, 'never_run') != 'success'
ORDER BY r.source, r.snap_date DESC, r.tld;

\echo 'SECTION:layer2_missing_partitions'
WITH active_tlds AS (
    SELECT DISTINCT source, tld
    FROM ingestion_run
    WHERE status = 'success'
      AND phase IN ('pg', 'full')
      AND started_at > now() - interval '30 days'
),
existing_partitions AS (
    SELECT relname
    FROM pg_class
    WHERE relkind = 'r'
      AND relname LIKE 'domain_%'
)
SELECT a.source, a.tld,
       'domain_' || replace(a.tld, '.', '_') AS expected_partition,
       (p.relname IS NOT NULL) AS partition_exists
FROM active_tlds a
LEFT JOIN existing_partitions p
       ON p.relname = 'domain_' || replace(a.tld, '.', '_')
WHERE p.relname IS NULL
ORDER BY a.source, a.tld;

\echo 'SECTION:layer3_top_deviation'
SELECT m.tld, m.count AS pg_count, r.domains_seen AS last_snapshot_count,
       r.snapshot_date AS last_snapshot_date,
       round((m.count::numeric / NULLIF(r.domains_seen, 0) - 1) * 100, 2) AS desvio_pct
FROM tld_domain_count_mv m
LEFT JOIN LATERAL (
    SELECT domains_seen, snapshot_date
    FROM ingestion_run
    WHERE tld = m.tld
      AND status = 'success'
      AND domains_seen > 0
    ORDER BY started_at DESC
    LIMIT 1
) r ON true
WHERE r.domains_seen IS NOT NULL
ORDER BY abs(m.count::numeric / NULLIF(r.domains_seen, 0) - 1) DESC NULLS LAST
LIMIT 30;

\echo 'SECTION:layer3_zero_pg_count'
SELECT ir.source, ir.tld, ir.domains_inserted, ir.domains_seen,
       mv.count AS pg_count, ir.started_at
FROM (
    SELECT DISTINCT ON (source, tld)
        source, tld, domains_inserted, domains_seen, started_at
    FROM ingestion_run
    WHERE status = 'success' AND phase IN ('pg', 'full')
    ORDER BY source, tld, started_at DESC
) ir
LEFT JOIN tld_domain_count_mv mv ON mv.tld = ir.tld
WHERE COALESCE(mv.count, 0) = 0
  AND ir.domains_seen > 0
ORDER BY ir.source, ir.tld;

\echo 'SECTION:layer3_zscore_outliers'
WITH daily AS (
    SELECT source, tld, COALESCE(snapshot_date, started_at::date) AS day,
           SUM(domains_inserted) AS inserted, SUM(domains_deleted) AS deleted
    FROM ingestion_run
    WHERE status = 'success'
      AND phase IN ('pg', 'full')
      AND started_at >= CURRENT_DATE - 30
    GROUP BY source, tld, day
),
stats AS (
    SELECT source, tld, avg(inserted) AS avg_inserted, stddev(inserted) AS std_inserted
    FROM daily
    GROUP BY source, tld
    HAVING count(*) >= 3
)
SELECT d.source, d.tld, d.day, d.inserted,
       round(s.avg_inserted) AS media_diaria,
       round(s.std_inserted) AS desvio_padrao,
       round((d.inserted - s.avg_inserted) / NULLIF(s.std_inserted, 0), 1) AS z_score
FROM daily d
JOIN stats s ON s.source = d.source AND s.tld = d.tld
WHERE abs((d.inserted - s.avg_inserted) / NULLIF(s.std_inserted, 0)) > 3
ORDER BY abs((d.inserted - s.avg_inserted) / NULLIF(s.std_inserted, 0)) DESC;

\echo 'SECTION:layer4_days_since_last_success'
WITH last_ok AS (
    SELECT DISTINCT ON (source, tld)
        source, tld,
        COALESCE(snapshot_date, started_at::date) AS last_ok_date
    FROM ingestion_run
    WHERE status = 'success'
      AND phase IN ('r2', 'pg', 'full')
    ORDER BY source, tld, started_at DESC
),
policy AS (
    SELECT source, tld FROM ingestion_tld_policy WHERE is_enabled = true
)
SELECT p.source, p.tld, l.last_ok_date,
       CURRENT_DATE - l.last_ok_date AS dias_sem_run,
       CASE p.source
           WHEN 'czds' THEN (CURRENT_DATE - l.last_ok_date) > 2
           WHEN 'openintel' THEN (CURRENT_DATE - l.last_ok_date) > 7
           ELSE false
       END AS fora_do_limiar
FROM policy p
LEFT JOIN last_ok l ON l.source = p.source AND l.tld = p.tld
WHERE l.last_ok_date IS NULL
   OR CASE p.source
          WHEN 'czds' THEN (CURRENT_DATE - l.last_ok_date) > 2
          WHEN 'openintel' THEN (CURRENT_DATE - l.last_ok_date) > 7
          ELSE false
      END
ORDER BY p.source, dias_sem_run DESC NULLS FIRST;

\echo 'SECTION:layer4_coverage_30d_under_70'
WITH ok_days AS (
    SELECT DISTINCT source, tld, COALESCE(snapshot_date, started_at::date) AS ok_day
    FROM ingestion_run
    WHERE status = 'success'
      AND phase IN ('r2', 'pg', 'full')
      AND started_at >= CURRENT_DATE - 30
)
SELECT p.source, p.tld,
       count(o.ok_day) AS dias_ok,
       30 - count(o.ok_day) AS dias_sem_run,
       round(count(o.ok_day)::numeric / 30 * 100, 0) AS cobertura_30d_pct
FROM ingestion_tld_policy p
LEFT JOIN ok_days o ON o.source = p.source AND o.tld = p.tld
WHERE p.is_enabled = true
GROUP BY p.source, p.tld
HAVING count(o.ok_day)::numeric / 30 < 0.7
ORDER BY cobertura_30d_pct ASC;

\echo 'SECTION:layer4_never_success'
SELECT p.source, p.tld, p.priority, p.created_at
FROM ingestion_tld_policy p
WHERE p.is_enabled = true
  AND NOT EXISTS (
      SELECT 1 FROM ingestion_run ir
      WHERE ir.source = p.source
        AND ir.tld = p.tld
        AND ir.status = 'success'
  )
ORDER BY p.source, p.priority;

\echo 'SECTION:executive_summary'
WITH
today_summary AS (
    SELECT source,
        count(*) FILTER (WHERE r2_status = 'success' AND pg_status = 'success') AS completos,
        count(*) FILTER (WHERE r2_status = 'success' AND pg_status != 'success') AS r2_ok_pg_pendente,
        count(*) FILTER (WHERE r2_status = 'failed') AS r2_falhou,
        count(*) FILTER (WHERE r2_status = 'running' OR pg_status = 'running') AS rodando,
        count(*) AS total_com_atividade
    FROM tld_daily_status_v
    WHERE day = CURRENT_DATE
    GROUP BY source
),
enabled_total AS (
    SELECT source, count(*) AS total_habilitados
    FROM ingestion_tld_policy WHERE is_enabled = true GROUP BY source
)
SELECT e.source, e.total_habilitados,
    COALESCE(t.completos, 0) AS completos,
    COALESCE(t.r2_ok_pg_pendente, 0) AS pg_pendente,
    COALESCE(t.r2_falhou, 0) AS r2_falhou,
    COALESCE(t.rodando, 0) AS rodando,
    e.total_habilitados - COALESCE(t.total_com_atividade, 0) AS sem_atividade_hoje,
    round(COALESCE(t.completos, 0)::numeric / e.total_habilitados * 100, 1) AS pct_completo
FROM enabled_total e
LEFT JOIN today_summary t ON t.source = e.source
ORDER BY e.source;
