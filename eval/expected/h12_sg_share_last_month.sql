-- H12. Singapore providers' share (percent) of the approved net SGD amount, visits in October 2026.
-- The denominator is ALL approved claims of the month, including those with no known provider.
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT round(100.0 * sum(c.claim_amt / c.currency_rate) FILTER (WHERE p.country_code = 'SG')
             / sum(c.claim_amt / c.currency_rate), 2) AS sg_share_pct
FROM latest c LEFT JOIN provider p ON p.provider_id = c.provider_id
WHERE c.approved_on IS NOT NULL AND c.voided_on IS NULL
  AND c.visit_date BETWEEN DATE '2026-10-01' AND DATE '2026-10-31';
