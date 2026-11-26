-- S8. The known country with the highest average approved claim size in SGD, visits in Q3 2026.
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT p.country_code AS country, round(sum(c.claim_amt / c.currency_rate) / count(*), 2) AS avg_claim_sgd
FROM latest c JOIN provider p ON p.provider_id = c.provider_id
WHERE c.approved_on IS NOT NULL AND c.voided_on IS NULL AND c.visit_date BETWEEN DATE '2026-07-01' AND DATE '2026-09-30'
GROUP BY 1 ORDER BY 2 DESC LIMIT 1;
