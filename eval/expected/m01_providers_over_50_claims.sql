-- M1. Real providers (duplicates merged) with more than 50 approved claims, visits in Q3 2026.
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT count(*) AS providers
FROM (SELECT rtrim(lower(p.name), '.') AS provider FROM latest c JOIN provider p ON p.provider_id = c.provider_id
      WHERE c.approved_on IS NOT NULL AND c.voided_on IS NULL AND c.visit_date BETWEEN DATE '2026-07-01' AND DATE '2026-09-30' GROUP BY 1 HAVING count(*) > 50);
