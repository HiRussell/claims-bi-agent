-- S20. The weekday with the most approved claims, visits from 2026-01-01 to 2026-11-30.
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT dayname(visit_date) AS weekday, count(*) AS visits
FROM latest
WHERE approved_on IS NOT NULL AND voided_on IS NULL AND visit_date BETWEEN DATE '2026-01-01' AND DATE '2026-11-30'
GROUP BY 1 ORDER BY 2 DESC LIMIT 1;
