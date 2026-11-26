-- H5. Approved net amount in SGD by provider region, visits August to October 2026.
-- The region rows of the lookup table are stored twice, hence DISTINCT. No provider -> 'Unknown'.
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT coalesce(r.descr, 'Unknown') AS region, round(sum(c.claim_amt / c.currency_rate), 2) AS amount_sgd
FROM latest c
LEFT JOIN provider p ON p.provider_id = c.provider_id
LEFT JOIN (SELECT DISTINCT value, descr FROM lookup WHERE type = 'PROVIDER_REGION') r ON r.value = p.region
WHERE c.approved_on IS NOT NULL AND c.voided_on IS NULL
  AND c.visit_date BETWEEN DATE '2026-08-01' AND DATE '2026-10-31'
GROUP BY 1 ORDER BY 1;
