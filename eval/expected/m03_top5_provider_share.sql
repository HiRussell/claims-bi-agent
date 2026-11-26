-- M3. Share (percent) of ALL approved net SGD amount in Q3 2026 that comes from the five largest real providers.
-- The denominator includes claims with no known provider.
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
, per_provider AS (
  SELECT rtrim(lower(p.name), '.') AS provider, sum(c.claim_amt / c.currency_rate) AS amt
  FROM latest c JOIN provider p ON p.provider_id = c.provider_id
  WHERE c.approved_on IS NOT NULL AND c.voided_on IS NULL AND c.visit_date BETWEEN DATE '2026-07-01' AND DATE '2026-09-30' GROUP BY 1)
SELECT round(100.0 * (SELECT sum(amt) FROM (SELECT amt FROM per_provider ORDER BY amt DESC LIMIT 5))
             / (SELECT sum(claim_amt / currency_rate) FROM latest WHERE approved_on IS NOT NULL AND voided_on IS NULL AND visit_date BETWEEN DATE '2026-07-01' AND DATE '2026-09-30'), 2) AS top5_share_pct;
