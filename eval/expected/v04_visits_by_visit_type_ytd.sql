-- V4. Approved claims per visit type, visits from 2026-01-01 to 2026-11-30 (year to date).
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT l.descr AS visit_type, count(*) AS visits
FROM latest c
LEFT JOIN (SELECT DISTINCT value, descr FROM lookup WHERE type = 'VISIT_TYPE') l ON l.value = c.visit_type
WHERE c.approved_on IS NOT NULL AND c.voided_on IS NULL
  AND c.visit_date BETWEEN DATE '2026-01-01' AND DATE '2026-11-30'
GROUP BY 1 ORDER BY 2 DESC;
