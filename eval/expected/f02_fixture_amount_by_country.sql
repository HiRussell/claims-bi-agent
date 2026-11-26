-- F2 (second database, today = 2026-03-15). Approved net amount in SGD by provider country, visits up to today.
-- By hand: MY = 100 (claim 2; claim 6 has rate 0 and cannot be converted), SG = 10 (claim 5, booked on a
-- duplicate of provider 1), Unknown = 80 (claim 3, provider 0 does not exist).
WITH latest AS (
  SELECT c.* FROM claim c
  JOIN (SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id) l
    ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT coalesce(p.country_code, 'Unknown') AS country,
       round(sum(CASE WHEN c.currency_rate > 0 THEN c.claim_amt / c.currency_rate END), 2) AS amount_sgd
FROM latest c LEFT JOIN provider p ON p.provider_id = c.provider_id
WHERE c.approved_on IS NOT NULL AND c.voided_on IS NULL AND c.visit_date <= DATE '2026-03-15'
GROUP BY 1 ORDER BY 1;
