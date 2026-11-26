-- G1. Three different doctors are called "Dr Gina Lee" (ids 57, 70, 119, three specialties).
-- Approved claims with a visit in Q3 2026 for EACH of them; one combined figure would be wrong.
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT d.doctor_id, count(*) AS approved_claims
FROM latest c JOIN doctor d ON d.doctor_id = TRY_CAST(c.doctor_id AS BIGINT)
WHERE c.approved_on IS NOT NULL AND c.voided_on IS NULL AND c.visit_date BETWEEN DATE '2026-07-01' AND DATE '2026-09-30' AND d.name = 'Dr Gina Lee'
GROUP BY d.doctor_id ORDER BY d.doctor_id;
