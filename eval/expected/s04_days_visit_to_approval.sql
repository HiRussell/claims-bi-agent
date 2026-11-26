-- S4. Average number of days from the visit date to the approval date, approved claims, visits in October 2026.
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT round(avg(date_diff('day', visit_date, CAST(approved_on AS DATE))), 2) AS avg_days
FROM latest
WHERE approved_on IS NOT NULL AND voided_on IS NULL AND visit_date BETWEEN DATE '2026-10-01' AND DATE '2026-10-31';
