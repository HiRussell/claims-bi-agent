-- X5. Approved claims of "Harbour Family Clinic 1" with a visit in October 2026.
-- The provider is stored under two ids (1 and 401, "harbour family clinic 1."); both count.
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT count(*) AS approved_claims
FROM latest c JOIN provider p ON p.provider_id = c.provider_id
WHERE rtrim(lower(p.name), '.') = 'harbour family clinic 1'
  AND c.approved_on IS NOT NULL AND c.voided_on IS NULL
  AND c.visit_date BETWEEN DATE '2026-10-01' AND DATE '2026-10-31';
