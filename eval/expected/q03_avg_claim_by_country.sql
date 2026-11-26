-- Q3. Average approved claim size in SGD by the provider's country, visits up to 2026-11-30.
-- Claims whose provider is not in the provider table stay in the result as 'Unknown'.
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT coalesce(p.country_code, 'Unknown') AS country,
       round(sum(c.claim_amt / c.currency_rate) / count(*), 2) AS avg_claim_sgd
FROM latest c LEFT JOIN provider p ON p.provider_id = c.provider_id
WHERE c.approved_on IS NOT NULL AND c.voided_on IS NULL AND c.visit_date <= DATE '2026-11-30'
GROUP BY 1 ORDER BY 1;
