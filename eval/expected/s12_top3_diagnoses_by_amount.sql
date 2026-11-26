-- S12. Top 3 known diagnoses by approved net SGD amount, visits in October 2026.
-- A claim's amount counts once per diagnosis it carries (repeated claim-diagnosis rows are removed first).
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT r.descr AS diagnosis, round(sum(c.claim_amt / c.currency_rate), 2) AS amount_sgd
FROM latest c
JOIN (SELECT DISTINCT claim_id, icd_id FROM claim_diagnosis) d ON d.claim_id = c.claim_id
JOIN ref_icd r ON r.icd_id = d.icd_id
WHERE c.approved_on IS NOT NULL AND c.voided_on IS NULL AND c.visit_date BETWEEN DATE '2026-10-01' AND DATE '2026-10-31'
GROUP BY r.icd_id, r.descr ORDER BY 2 DESC LIMIT 3;
