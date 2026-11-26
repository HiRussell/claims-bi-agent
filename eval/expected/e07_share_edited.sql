-- E7. Percentage of claims with a visit in October 2026 that have more than one stored version.
SELECT round(100.0 * count(*) FILTER (WHERE n > 1) / count(*), 2) AS edited_pct
FROM (SELECT claim_id, count(*) AS n FROM claim WHERE visit_date BETWEEN DATE '2026-10-01' AND DATE '2026-10-31' GROUP BY claim_id);
