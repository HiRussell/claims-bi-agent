-- Q7. The known specialty with the most approved claims, visits up to 2026-11-30.
-- claim.doctor_id is text ('' and '0' mean no doctor); those claims are 'Unknown' and not ranked.
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT l.descr AS specialty, count(*) AS claims
FROM latest c
JOIN doctor d ON d.doctor_id = TRY_CAST(c.doctor_id AS BIGINT)
JOIN (SELECT DISTINCT value, descr FROM lookup WHERE type = 'SPECIALTY') l ON l.value = d.specialty
WHERE c.approved_on IS NOT NULL AND c.voided_on IS NULL AND c.visit_date <= DATE '2026-11-30'
GROUP BY 1 ORDER BY 2 DESC LIMIT 1;
