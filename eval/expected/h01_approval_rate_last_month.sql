-- H1. Of the claims with a visit in October 2026 (one per claim), the percentage that are approved.
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT round(100.0 * count(*) FILTER (WHERE approved_on IS NOT NULL AND voided_on IS NULL) / count(*), 2) AS approval_rate_pct
FROM latest
WHERE visit_date BETWEEN DATE '2026-10-01' AND DATE '2026-10-31';
