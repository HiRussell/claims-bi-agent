-- R3. Average number of stored versions per claim, claims with a visit in October 2026.
SELECT round(count(*) * 1.0 / count(DISTINCT claim_id), 2) AS avg_versions
FROM claim WHERE visit_date BETWEEN DATE '2026-10-01' AND DATE '2026-10-31';
