-- E6. Claims with a visit in October 2026 whose FIRST stored version carries a rejection date
-- and whose latest version is approved.
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
, first_load AS (SELECT claim_id, min(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
first_version AS (SELECT c.* FROM claim c JOIN first_load f ON f.claim_id = c.claim_id AND f.loaded_at = c.loaded_at)
SELECT count(*) AS claims
FROM latest l JOIN first_version f ON f.claim_id = l.claim_id
WHERE l.visit_date BETWEEN DATE '2026-10-01' AND DATE '2026-10-31' AND f.rejected_on IS NOT NULL AND l.approved_on IS NOT NULL AND l.voided_on IS NULL;
