-- Q9. Claims with rejected_on set (latest version) and a visit in Q3 2026 (July to September).
-- Not restricted to approved claims: the question asks about rejections.
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT count(*) AS rejected_claims
FROM latest
WHERE rejected_on IS NOT NULL
  AND visit_date BETWEEN DATE '2026-07-01' AND DATE '2026-09-30';
