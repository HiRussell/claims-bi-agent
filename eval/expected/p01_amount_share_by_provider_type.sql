-- P1. Percentage of the approved net SGD amount per provider type (no provider -> Unknown), visits in October 2026.
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT coalesce(t.descr, 'Unknown') AS provider_type,
       round(100.0 * sum(c.claim_amt / c.currency_rate) / sum(sum(c.claim_amt / c.currency_rate)) OVER (), 2) AS share_pct
FROM latest c
LEFT JOIN provider p ON p.provider_id = c.provider_id
LEFT JOIN (SELECT DISTINCT value, descr FROM lookup WHERE type = 'PROVIDER_TYPE') t ON CAST(t.value AS BIGINT) = p.type
WHERE c.approved_on IS NOT NULL AND c.voided_on IS NULL AND c.visit_date BETWEEN DATE '2026-10-01' AND DATE '2026-10-31'
GROUP BY 1 ORDER BY 1;
