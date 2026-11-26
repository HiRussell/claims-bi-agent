-- H10. Same as Q9 with today = 2026-02-10: last quarter is Q4 2025 (October to December 2025).
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT count(*) AS rejected_claims
FROM latest
WHERE rejected_on IS NOT NULL
  AND visit_date BETWEEN DATE '2025-10-01' AND DATE '2025-12-31';
