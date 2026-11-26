-- D2. Number of doctors per specialty. Ids 1 and 2 are one doctor entered twice, so 119 doctors, not 120.
SELECT l.descr AS specialty, count(DISTINCT CASE WHEN d.doctor_id = 2 THEN 1 ELSE d.doctor_id END) AS doctors
FROM doctor d
JOIN (SELECT DISTINCT value, descr FROM lookup WHERE type = 'SPECIALTY') l ON l.value = d.specialty
GROUP BY 1 ORDER BY 2 DESC;
