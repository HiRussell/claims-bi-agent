-- S13. Drug-line cost in SGD by drug type, approved claims with a visit in October 2026.
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT t.descr AS drug_type, round(sum(d.cost / c.currency_rate), 2) AS cost_sgd
FROM claim_drug d
JOIN latest c ON c.claim_id = d.claim_id
JOIN drug g ON g.drug_id = d.drug_id
JOIN (SELECT DISTINCT value, descr FROM lookup WHERE type = 'DRUG_TYPE') t ON t.value = g.type
WHERE c.approved_on IS NOT NULL AND c.voided_on IS NULL AND c.visit_date BETWEEN DATE '2026-10-01' AND DATE '2026-10-31'
GROUP BY 1 ORDER BY 1;
