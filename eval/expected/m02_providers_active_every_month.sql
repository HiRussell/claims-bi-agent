-- M2. Real providers with at least one approved claim in EACH of the six months May to October 2026.
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT count(*) AS providers
FROM (SELECT rtrim(lower(p.name), '.') AS provider FROM latest c JOIN provider p ON p.provider_id = c.provider_id
      WHERE c.approved_on IS NOT NULL AND c.voided_on IS NULL AND c.visit_date BETWEEN DATE '2026-05-01' AND DATE '2026-10-31'
      GROUP BY 1 HAVING count(DISTINCT strftime(c.visit_date, '%Y-%m')) = 6);
