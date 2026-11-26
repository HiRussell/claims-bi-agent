-- R2. Claims with a visit in Q3 2026 that were approved (approved, not voided) in some version
-- but are not approved in their latest version.
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT count(*) AS claims
FROM latest
WHERE visit_date BETWEEN DATE '2026-07-01' AND DATE '2026-09-30' AND NOT (approved_on IS NOT NULL AND voided_on IS NULL)
  AND claim_id IN (SELECT claim_id FROM claim WHERE approved_on IS NOT NULL AND voided_on IS NULL);
