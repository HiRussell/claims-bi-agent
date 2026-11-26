-- F3 (second database). Number of real providers. By hand: 3. Provider 3 ('a clinic.') is provider 1
-- ('A Clinic') entered twice; provider 4 has the same name but is in another country, so it is separate.
SELECT count(*) AS providers
FROM (SELECT DISTINCT rtrim(lower(name), '.'), type, country_code, region FROM provider);
