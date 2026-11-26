-- S19. Approved net SGD amount for Q1 2025 and for Q1 2026.
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
-- Rows: 2025 first, then 2026.
SELECT round(sum(claim_amt / currency_rate), 2) AS amount_sgd
FROM latest
WHERE approved_on IS NOT NULL AND voided_on IS NULL AND (visit_date BETWEEN DATE '2025-01-01' AND DATE '2025-03-31'
            OR visit_date BETWEEN DATE '2026-01-01' AND DATE '2026-03-31')
GROUP BY strftime(visit_date, '%Y') ORDER BY min(visit_date);
