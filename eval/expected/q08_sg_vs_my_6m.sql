-- Q8. Singapore vs Malaysia (provider country), approved claims, May to October 2026, per month.
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT strftime(c.visit_date, '%Y-%m') AS month, p.country_code AS country,
       round(sum(c.claim_amt / c.currency_rate), 2) AS amount_sgd, count(*) AS visits
FROM latest c JOIN provider p ON p.provider_id = c.provider_id
WHERE c.approved_on IS NOT NULL AND c.voided_on IS NULL
  AND p.country_code IN ('SG', 'MY')
  AND c.visit_date BETWEEN DATE '2026-05-01' AND DATE '2026-10-31'
GROUP BY 1, 2 ORDER BY 1, 2;
