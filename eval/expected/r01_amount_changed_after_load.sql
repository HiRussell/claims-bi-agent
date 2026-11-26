-- R1. Claims with a visit in October 2026 whose claim amount differs between at least two of their versions.
SELECT count(*) AS claims
FROM (SELECT claim_id FROM claim WHERE visit_date BETWEEN DATE '2026-10-01' AND DATE '2026-10-31' GROUP BY claim_id HAVING count(DISTINCT claim_amt) > 1);
