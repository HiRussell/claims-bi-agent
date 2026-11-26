-- H11. Average approved claim size in SGD for GP and Specialist providers, visits 2026-01-01 to 2026-11-30.
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT t.descr AS provider_type, round(sum(c.claim_amt / c.currency_rate) / count(*), 2) AS avg_claim_sgd
FROM latest c
JOIN provider p ON p.provider_id = c.provider_id
JOIN (SELECT DISTINCT value, descr FROM lookup WHERE type = 'PROVIDER_TYPE') t ON CAST(t.value AS BIGINT) = p.type
WHERE c.approved_on IS NOT NULL AND c.voided_on IS NULL
  AND c.visit_date BETWEEN DATE '2026-01-01' AND DATE '2026-11-30'
  AND t.descr IN ('GP', 'Specialist')
GROUP BY 1 ORDER BY 1;
