-- R4. Claims with a visit in October 2026 whose FIRST load was more than 3 days after the visit.
SELECT count(*) AS claims
FROM (SELECT claim_id, min(visit_date) AS visit_date, CAST(min(loaded_at) AS DATE) AS first_load
      FROM claim WHERE visit_date BETWEEN DATE '2026-10-01' AND DATE '2026-10-31' GROUP BY claim_id)
WHERE date_diff('day', visit_date, first_load) > 3;
