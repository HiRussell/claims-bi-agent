-- Q2. Approved net amount in SGD per visit month, November 2025 to October 2026 (12 complete months).
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT strftime(visit_date, '%Y-%m') AS month, round(sum(claim_amt / currency_rate), 2) AS amount_sgd
FROM latest
WHERE approved_on IS NOT NULL AND voided_on IS NULL
  AND visit_date BETWEEN DATE '2025-11-01' AND DATE '2026-10-31'
GROUP BY 1 ORDER BY 1;
