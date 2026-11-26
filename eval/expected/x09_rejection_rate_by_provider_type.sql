-- X9. Per provider type: rejected claims as a percentage of all claims (one per claim), visits in Q3 2026.
-- Claims with no known provider form the 'Unknown' group.
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT coalesce(t.descr, 'Unknown') AS provider_type,
       round(100.0 * count(*) FILTER (WHERE c.rejected_on IS NOT NULL) / count(*), 2) AS rejection_rate_pct
FROM latest c
LEFT JOIN provider p ON p.provider_id = c.provider_id
LEFT JOIN (SELECT DISTINCT value, descr FROM lookup WHERE type = 'PROVIDER_TYPE') t ON CAST(t.value AS BIGINT) = p.type
WHERE c.visit_date BETWEEN DATE '2026-07-01' AND DATE '2026-09-30'
GROUP BY 1 ORDER BY 1;
