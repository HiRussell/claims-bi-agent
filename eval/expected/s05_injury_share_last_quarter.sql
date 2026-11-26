-- S5. Percentage of approved claims with a visit in Q3 2026 whose visit type is Injury (code '2').
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT round(100.0 * count(*) FILTER (WHERE visit_type = '2') / count(*), 2) AS injury_share_pct
FROM latest
WHERE approved_on IS NOT NULL AND voided_on IS NULL AND visit_date BETWEEN DATE '2026-07-01' AND DATE '2026-09-30';
