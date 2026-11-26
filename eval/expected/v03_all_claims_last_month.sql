-- V3. All claims regardless of status with a visit in October 2026: one per claim, not one per stored version.
SELECT count(DISTINCT c.claim_id) AS claims
FROM claim c
JOIN (SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id) l
  ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at
WHERE c.visit_date BETWEEN DATE '2026-10-01' AND DATE '2026-10-31';
