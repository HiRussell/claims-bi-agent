-- S25. Approved claims per provider region for providers in Singapore, visits in October 2026.
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT r.descr AS region, count(*) AS visits
FROM latest c
JOIN provider p ON p.provider_id = c.provider_id
JOIN (SELECT DISTINCT value, descr FROM lookup WHERE type = 'PROVIDER_REGION') r ON r.value = p.region
WHERE c.approved_on IS NOT NULL AND c.voided_on IS NULL AND p.country_code = 'SG' AND c.visit_date BETWEEN DATE '2026-10-01' AND DATE '2026-10-31'
GROUP BY 1 ORDER BY 2 DESC;
