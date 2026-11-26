-- T1. Claims whose rejection DATE (not visit date) falls in Q3 2026, latest version, visits up to 2026-11-30.
-- rejected_on is a timestamp at 02:00, so "<= DATE '2026-09-30'" would lose the last day; compare the date.
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT count(*) AS rejected_claims
FROM latest
WHERE CAST(rejected_on AS DATE) BETWEEN DATE '2026-07-01' AND DATE '2026-09-30'
  AND visit_date <= DATE '2026-11-30';
