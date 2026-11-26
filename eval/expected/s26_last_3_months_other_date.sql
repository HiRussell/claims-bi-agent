-- S26. Today = 2026-01-10: approved net SGD amount per visit month for October, November and December 2025.
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT strftime(visit_date, '%Y-%m') AS month, round(sum(claim_amt / currency_rate), 2) AS amount_sgd
FROM latest
WHERE approved_on IS NOT NULL AND voided_on IS NULL AND visit_date BETWEEN DATE '2025-10-01' AND DATE '2025-12-31'
GROUP BY 1 ORDER BY 1;
