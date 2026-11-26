-- E8. Claims whose FIRST load happened in October 2026 (new claims, as opposed to edits of older ones).
SELECT count(*) AS new_claims
FROM (SELECT claim_id, min(loaded_at) AS first_load FROM claim GROUP BY claim_id)
WHERE CAST(first_load AS DATE) BETWEEN DATE '2026-10-01' AND DATE '2026-10-31';
