-- H6. Rows of the raw claim table (claim versions) with a load timestamp on 2026-11-15.
SELECT count(*) AS records_loaded
FROM claim
WHERE CAST(loaded_at AS DATE) = DATE '2026-11-15';
