-- V1. Same as Q1 but with today = 2026-03-15, so last month is February 2026.
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT count(*) AS approved_claims
FROM latest
WHERE approved_on IS NOT NULL AND voided_on IS NULL
  AND visit_date BETWEEN DATE '2026-02-01' AND DATE '2026-02-28';
