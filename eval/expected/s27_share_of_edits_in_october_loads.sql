-- S27. Of the claim rows loaded in October 2026, the percentage that are edits (not the first row of their claim).
SELECT round(100.0 * count(*) FILTER (WHERE c.loaded_at > f.first_loaded) / count(*), 2) AS edit_share_pct
FROM claim c
JOIN (SELECT claim_id, min(loaded_at) AS first_loaded FROM claim GROUP BY claim_id) f ON f.claim_id = c.claim_id
WHERE CAST(c.loaded_at AS DATE) BETWEEN DATE '2026-10-01' AND DATE '2026-10-31';
