-- S2. The known provider whose approved net SGD amount rose most from Q2 2026 (Apr-Jun) to Q3 2026 (Jul-Sep).
-- Providers entered twice are added together (name compared in lower case without the trailing dot).
WITH last_load AS (
  SELECT claim_id, max(loaded_at) AS loaded_at FROM claim GROUP BY claim_id),
latest AS (            -- one row per claim: the version with the newest load timestamp
  SELECT c.* FROM claim c JOIN last_load l ON l.claim_id = c.claim_id AND l.loaded_at = c.loaded_at)
SELECT min(p.name) AS provider,
       round(coalesce(sum(c.claim_amt / c.currency_rate) FILTER (WHERE c.visit_date >= DATE '2026-07-01'), 0)
           - coalesce(sum(c.claim_amt / c.currency_rate) FILTER (WHERE c.visit_date <  DATE '2026-07-01'), 0), 2) AS increase_sgd
FROM latest c JOIN provider p ON p.provider_id = c.provider_id
WHERE c.approved_on IS NOT NULL AND c.voided_on IS NULL AND c.visit_date BETWEEN DATE '2026-04-01' AND DATE '2026-09-30'
GROUP BY rtrim(lower(p.name), '.') ORDER BY 2 DESC LIMIT 1;
