\pset pager off
SELECT 'layer1_missing_recent3d_count_by_source' as section;
WITH recent_r2 AS (
  SELECT DISTINCT source, tld
  FROM ingestion_run
  WHERE phase IN ('r2','full') AND status='success'
    AND COALESCE(snapshot_date, started_at::date) >= CURRENT_DATE - 3
)
SELECT p.source, count(*)
FROM ingestion_tld_policy p
LEFT JOIN recent_r2 r ON r.source=p.source AND r.tld=p.tld
WHERE p.is_enabled=true AND r.tld IS NULL
GROUP BY p.source
ORDER BY p.source;

SELECT 'layer1_missing_recent3d_sample' as section;
WITH recent_r2 AS (
  SELECT DISTINCT source, tld
  FROM ingestion_run
  WHERE phase IN ('r2','full') AND status='success'
    AND COALESCE(snapshot_date, started_at::date) >= CURRENT_DATE - 3
)
SELECT p.source, p.tld, p.priority
FROM ingestion_tld_policy p
LEFT JOIN recent_r2 r ON r.source=p.source AND r.tld=p.tld
WHERE p.is_enabled=true AND r.tld IS NULL
ORDER BY p.source, p.priority, p.tld
LIMIT 40;

SELECT 'layer2_dual_phase_today' as section;
SELECT source, r2_status, pg_status, count(*) AS tlds
FROM tld_daily_status_v
WHERE day = CURRENT_DATE
GROUP BY source, r2_status, pg_status
ORDER BY source, r2_status, pg_status;

SELECT 'layer2_r2ok_pg_not_success_count' as section;
WITH latest_r2 AS (
    SELECT DISTINCT ON (source, tld) source, tld, COALESCE(snapshot_date, started_at::date) AS snap_date
    FROM ingestion_run
    WHERE phase IN ('r2', 'full') AND status='success'
    ORDER BY source, tld, started_at DESC
), latest_pg AS (
    SELECT DISTINCT ON (source, tld) source, tld, status AS pg_status
    FROM ingestion_run
    WHERE phase IN ('pg','full')
    ORDER BY source, tld, started_at DESC
)
SELECT r.source, count(*)
FROM latest_r2 r
LEFT JOIN latest_pg p ON p.source=r.source AND p.tld=r.tld
WHERE COALESCE(p.pg_status, 'never_run') != 'success'
GROUP BY r.source
ORDER BY r.source;

SELECT 'layer2_missing_partitions_count' as section;
WITH active_tlds AS (
  SELECT DISTINCT source, tld
  FROM ingestion_run
  WHERE status='success' AND phase IN ('pg','full')
    AND started_at > now() - interval '30 days'
), existing_partitions AS (
  SELECT relname FROM pg_class WHERE relkind='r' AND relname LIKE 'domain_%'
)
SELECT a.source, count(*)
FROM active_tlds a
LEFT JOIN existing_partitions p ON p.relname='domain_' || replace(a.tld,'.','_')
WHERE p.relname IS NULL
GROUP BY a.source
ORDER BY a.source;

SELECT 'layer4_days_since_last_success_count' as section;
WITH last_ok AS (
  SELECT DISTINCT ON (source,tld) source, tld, COALESCE(snapshot_date, started_at::date) AS last_ok_date
  FROM ingestion_run
  WHERE status='success' AND phase IN ('r2','pg','full')
  ORDER BY source,tld,started_at DESC
), policy AS (
  SELECT source, tld FROM ingestion_tld_policy WHERE is_enabled=true
)
SELECT p.source, count(*)
FROM policy p
LEFT JOIN last_ok l ON l.source=p.source AND l.tld=p.tld
WHERE l.last_ok_date IS NULL OR CASE p.source
 WHEN 'czds' THEN (CURRENT_DATE - l.last_ok_date) > 2
 WHEN 'openintel' THEN (CURRENT_DATE - l.last_ok_date) > 7
 ELSE false END
GROUP BY p.source
ORDER BY p.source;

SELECT 'layer4_coverage_30d_under_70_count' as section;
WITH ok_days AS (
  SELECT DISTINCT source,tld,COALESCE(snapshot_date,started_at::date) AS ok_day
  FROM ingestion_run
  WHERE status='success' AND phase IN ('r2','pg','full')
    AND started_at >= CURRENT_DATE - 30
)
SELECT p.source, count(*)
FROM (
  SELECT p.source,p.tld,count(o.ok_day) AS dias_ok
  FROM ingestion_tld_policy p
  LEFT JOIN ok_days o ON o.source=p.source AND o.tld=p.tld
  WHERE p.is_enabled=true
  GROUP BY p.source,p.tld
  HAVING count(o.ok_day)::numeric/30 < 0.7
) p
GROUP BY p.source
ORDER BY p.source;

SELECT 'layer4_never_success_count' as section;
SELECT p.source, count(*)
FROM ingestion_tld_policy p
WHERE p.is_enabled=true
  AND NOT EXISTS (
    SELECT 1 FROM ingestion_run ir
    WHERE ir.source=p.source AND ir.tld=p.tld AND ir.status='success'
  )
GROUP BY p.source
ORDER BY p.source;
