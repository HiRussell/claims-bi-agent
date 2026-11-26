-- M4. Approved claims per active provider, visits in October 2026: claims at known providers divided by
-- the number of real providers with at least one such claim. Claims with no known provider are left out
-- of both sides (they are not a provider).
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT round(count(*) * 1.0 / count(DISTINCT rtrim(lower(p.name), '.')), 2) AS claims_per_provider
FROM latest c JOIN provider p ON p.provider_id = c.provider_id
WHERE c.approved_on IS NOT NULL AND c.voided_on IS NULL AND c.visit_date BETWEEN DATE '2026-10-01' AND DATE '2026-10-31';
