-- E4. Approved net SGD amount for the quarter before last quarter: Q2 2026, 2026-04-01 to 2026-06-30.
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT round(sum(claim_amt / currency_rate), 2) AS amount_sgd FROM latest
WHERE approved_on IS NOT NULL AND voided_on IS NULL AND visit_date BETWEEN DATE '2026-04-01' AND DATE '2026-06-30';
