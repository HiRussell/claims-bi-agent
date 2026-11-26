-- H14. Claims whose latest version has no approval, no rejection and no void date, visits up to 2026-11-30.
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT count(*) AS pending_claims
FROM latest
WHERE approved_on IS NULL AND rejected_on IS NULL AND voided_on IS NULL
  AND visit_date <= DATE '2026-11-30';
