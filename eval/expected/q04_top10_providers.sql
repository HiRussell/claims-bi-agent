-- Q4. Top 10 known providers by approved net amount in SGD, visits up to 2026-11-30.
-- The provider table lists 12 providers twice ("Harbour Family Clinic 1" and "harbour family clinic 1."),
-- so amounts are added per cleaned name, not per provider_id.
-- Claims with no matching provider are left out of the ranking (the agent must say so).
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT rtrim(lower(p.name), '.') AS provider, round(sum(c.claim_amt / c.currency_rate), 2) AS amount_sgd
FROM latest c JOIN provider p ON p.provider_id = c.provider_id
WHERE c.approved_on IS NOT NULL AND c.voided_on IS NULL AND c.visit_date <= DATE '2026-11-30'
GROUP BY 1 ORDER BY 2 DESC LIMIT 10;
