-- S14. Approved claims with a visit in October 2026 that carry more than one distinct diagnosis code.
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT count(*) AS claims
FROM (SELECT c.claim_id FROM latest c JOIN claim_diagnosis d ON d.claim_id = c.claim_id
      WHERE c.approved_on IS NOT NULL AND c.voided_on IS NULL AND c.visit_date BETWEEN DATE '2026-10-01' AND DATE '2026-10-31'
      GROUP BY c.claim_id HAVING count(DISTINCT d.icd_id) > 1);
