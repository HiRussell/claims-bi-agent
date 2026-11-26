-- A1. Approved net amount in SGD of claims that carry a hypertension diagnosis, visits in October 2026.
-- A claim with two hypertension codes must be counted once, hence IN (...) instead of a join.
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT round(sum(claim_amt / currency_rate), 2) AS amount_sgd      -- 224 claims
FROM latest
WHERE approved_on IS NOT NULL AND voided_on IS NULL
  AND visit_date BETWEEN DATE '2026-10-01' AND DATE '2026-10-31'
  AND claim_id IN (SELECT d.claim_id FROM claim_diagnosis d JOIN ref_icd r ON r.icd_id = d.icd_id
                   WHERE lower(r.descr) LIKE '%hypertension%');
