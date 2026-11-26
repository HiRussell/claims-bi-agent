-- S11. Per provider country (no provider -> Unknown): of the approved claims with a visit in Q3 2026,
-- the percentage that also carry a rejection date.
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT coalesce(p.country_code, 'Unknown') AS country,
       round(100.0 * count(*) FILTER (WHERE c.rejected_on IS NOT NULL) / count(*), 2) AS rejected_share_pct
FROM latest c LEFT JOIN provider p ON p.provider_id = c.provider_id
WHERE c.approved_on IS NOT NULL AND c.voided_on IS NULL AND c.visit_date BETWEEN DATE '2026-07-01' AND DATE '2026-09-30'
GROUP BY 1 ORDER BY 1;
