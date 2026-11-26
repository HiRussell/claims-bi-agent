-- Q5. Number of providers per provider type. provider.type is a number (1), the lookup code is text ('001').
-- 12 providers are listed twice under a re-typed name; each real provider is counted once.
SELECT l.descr AS provider_type, count(DISTINCT rtrim(lower(p.name), '.')) AS providers
FROM provider p
JOIN (SELECT DISTINCT value, descr FROM lookup WHERE type = 'PROVIDER_TYPE') l
  ON CAST(l.value AS BIGINT) = p.type
GROUP BY 1 ORDER BY 2 DESC;
