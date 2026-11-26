-- H13. The five approved claims with the largest net amount in SGD, visits in October 2026.
-- Ranking on the local amount would wrongly put IDR claims first.
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT claim_id, round(claim_amt / currency_rate, 2) AS amount_sgd
FROM latest
WHERE approved_on IS NOT NULL AND voided_on IS NULL AND visit_date BETWEEN DATE '2026-10-01' AND DATE '2026-10-31'
ORDER BY claim_amt / currency_rate DESC LIMIT 5;
