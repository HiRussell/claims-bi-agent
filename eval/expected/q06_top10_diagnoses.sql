-- Q6. Top 10 known diagnoses by number of approved claims, visits up to 2026-11-30.
-- A claim counts once per diagnosis even if the pair is stored twice; a claim with two diagnoses counts in both.
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT r.descr AS diagnosis, count(DISTINCT c.claim_id) AS claims
FROM latest c
JOIN claim_diagnosis d ON d.claim_id = c.claim_id
JOIN ref_icd r ON r.icd_id = d.icd_id
WHERE c.approved_on IS NOT NULL AND c.voided_on IS NULL AND c.visit_date <= DATE '2026-11-30'
GROUP BY r.icd_id, r.descr ORDER BY 2 DESC LIMIT 10;
