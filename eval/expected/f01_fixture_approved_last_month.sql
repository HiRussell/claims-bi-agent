-- F1 (second database: tests/fixture.sql, today = 2026-03-15). Approved claims with a visit in February 2026.
-- By hand: claims 2, 3, 5 and 6. Claim 1 is voided in its latest version; claim 4 is dated 2099.
WITH latest AS (
  SELECT c.* FROM claim c
  JOIN (SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id) l
    ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT count(*) AS approved_claims
FROM latest
WHERE approved_on IS NOT NULL AND voided_on IS NULL
  AND visit_date BETWEEN DATE '2026-02-01' AND DATE '2026-02-28';
