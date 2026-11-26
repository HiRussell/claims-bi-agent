-- R5. For claims with a visit in Q3 2026 and more than one version: average days from first to last load.
SELECT round(avg(date_diff('day', first_load, last_load)), 2) AS avg_days
FROM (SELECT claim_id, min(loaded_at) AS first_load, max(loaded_at) AS last_load, count(*) AS n
      FROM claim WHERE visit_date BETWEEN DATE '2026-07-01' AND DATE '2026-09-30' GROUP BY claim_id)
WHERE n > 1;
