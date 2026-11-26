-- S3. Approved claims and approved net SGD amount for Q2 2026 and for Q3 2026 (last quarter and the one before).
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
-- Rows: Q2 first, then Q3.
SELECT count(*) AS approved_claims, round(sum(claim_amt / currency_rate), 2) AS amount_sgd
FROM latest
WHERE approved_on IS NOT NULL AND voided_on IS NULL AND visit_date BETWEEN DATE '2026-04-01' AND DATE '2026-09-30'
GROUP BY CASE WHEN visit_date < DATE '2026-07-01' THEN 2 ELSE 3 END ORDER BY min(visit_date);
