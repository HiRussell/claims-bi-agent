-- X10. Claims (one per claim, any status) whose visit date is after today, 2026-11-30.
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT count(*) AS future_dated_claims
FROM latest
WHERE visit_date > DATE '2026-11-30';
