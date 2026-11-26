-- V2. Gross amount (grand_total, incl. tax) in SGD of approved claims with a visit in October 2026.
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT round(sum(grand_total / currency_rate), 2) AS gross_sgd
FROM latest
WHERE approved_on IS NOT NULL AND voided_on IS NULL
  AND visit_date BETWEEN DATE '2026-10-01' AND DATE '2026-10-31';
