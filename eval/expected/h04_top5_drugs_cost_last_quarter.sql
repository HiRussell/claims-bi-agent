-- H4. Top 5 drugs by drug-line cost in SGD on approved claims with a visit in Q3 2026.
-- Drug cost is in the claim's currency, so each line is divided by the claim's rate.
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT g.name AS drug, round(sum(d.cost / c.currency_rate), 2) AS cost_sgd
FROM claim_drug d
JOIN latest c ON c.claim_id = d.claim_id
JOIN drug g ON g.drug_id = d.drug_id
WHERE c.approved_on IS NOT NULL AND c.voided_on IS NULL
  AND c.visit_date BETWEEN DATE '2026-07-01' AND DATE '2026-09-30'
GROUP BY g.drug_id, g.name ORDER BY 2 DESC LIMIT 5;
