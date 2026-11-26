-- D1. The doctor with the most approved claims, visits in Q3 2026.
-- Doctor ids 1 and 2 are the same entry typed twice ("Locum Doctor" / "Locum doctor", same specialty),
-- so their claims are added together. Doctors that merely share a name keep separate ids.
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT min(d.name) AS doctor, count(*) AS approved_claims
FROM latest c JOIN doctor d ON d.doctor_id = TRY_CAST(c.doctor_id AS BIGINT)
WHERE c.approved_on IS NOT NULL AND c.voided_on IS NULL
  AND c.visit_date BETWEEN DATE '2026-07-01' AND DATE '2026-09-30'
GROUP BY CASE WHEN d.doctor_id = 2 THEN 1 ELSE d.doctor_id END
ORDER BY 2 DESC LIMIT 1;
