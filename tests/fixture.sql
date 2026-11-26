-- A tiny claims database whose answers can be worked out by hand (as-of date 2026-03-15).
-- Used by the offline tests and, as a second database, by the evaluation.
CREATE TABLE lookup (type VARCHAR, value VARCHAR, descr VARCHAR);
CREATE TABLE provider (provider_id BIGINT, name VARCHAR, type BIGINT, country_code VARCHAR, region VARCHAR);
CREATE TABLE doctor (doctor_id BIGINT, name VARCHAR, specialty VARCHAR);
CREATE TABLE ref_icd (icd_id BIGINT, icd_code VARCHAR, descr VARCHAR);
CREATE TABLE drug (drug_id BIGINT, name VARCHAR, type VARCHAR);
CREATE TABLE claim (
  claim_id BIGINT, provider_id BIGINT, doctor_id VARCHAR, visit_date DATE,
  approved_on TIMESTAMP, rejected_on TIMESTAMP, voided_on TIMESTAMP,
  currency_code VARCHAR, currency_rate DOUBLE,
  claim_amt DECIMAL(18,2), grand_total DECIMAL(18,2), visit_type VARCHAR, loaded_at TIMESTAMP);
CREATE TABLE claim_diagnosis (claim_id BIGINT, icd_id BIGINT, diagnosis_note VARCHAR);
CREATE TABLE claim_drug (claim_id BIGINT, drug_id BIGINT, qty INTEGER, cost DECIMAL(18,2));
INSERT INTO lookup VALUES ('PROVIDER_TYPE','001','GP'), ('PROVIDER_TYPE','001','GP'),
  ('PROVIDER_TYPE','002','Specialist'), ('SPECIALTY','10','General Practice'), ('VISIT_TYPE','1','Sickness');
-- provider 3 is provider 1 entered again with a re-typed name; provider 4 shares the name but not the country
INSERT INTO provider VALUES (1,'A Clinic',1,'SG','C'), (2,'B Clinic',2,'MY','C'), (3,'a clinic.',1,'SG','C'),
  (4,'A Clinic',1,'MY','C');
INSERT INTO doctor VALUES (1,'Dr X','10');
INSERT INTO ref_icd VALUES (1,'X001','Flu'), (2,'X002','Cough');
INSERT INTO drug VALUES (1,'Drug-1','001');
INSERT INTO claim VALUES
  -- claim 1: approved first, voided in its latest version  -> NOT approved
  (1,1,'1','2026-01-03','2026-01-04',NULL,NULL,        'SGD',1.0,   100,107,'1','2026-01-05'),
  (1,1,'1','2026-01-03','2026-01-04',NULL,'2026-01-09','SGD',1.0,   100,107,'1','2026-01-10'),
  -- claim 2: 330 MYR at 3.3 MYR per SGD -> 100 SGD, no doctor
  (2,2,'', '2026-02-10','2026-02-11',NULL,NULL,        'MYR',3.3,   330,350,'1','2026-02-12'),
  -- claim 3: amount edited 50 -> 80 and approved later, provider 0 does not exist -> Unknown
  (3,0,'0','2026-02-15',NULL,        NULL,NULL,        'SGD',1.0,    50, 55,'1','2026-02-16'),
  (3,0,'0','2026-02-15','2026-02-18',NULL,NULL,        'SGD',1.0,    80, 88,'1','2026-02-19'),
  -- claim 4: visit date in the future -> excluded by the as-of filter
  (4,1,'1','2099-01-01','2026-02-01',NULL,NULL,        'SGD',1.0,   999,999,'1','2026-02-02'),
  -- claim 5: approved AND rejected -> still approved; 115000 IDR at 11500 -> 10 SGD
  (5,3,'1','2026-02-20','2026-02-21','2026-02-22',NULL,'IDR',11500, 115000,120000,'1','2026-02-23'),
  -- claim 6: unusable rate -> SGD amount is NULL, not zero and not infinity
  (6,2,'1','2026-02-21','2026-02-22',NULL,NULL,        'MYR',0,     500,550,'1','2026-02-23');
INSERT INTO claim_diagnosis VALUES (2,1,'SECRET-NOTE-ALPHA'), (2,1,'SECRET-NOTE-BETA'), (2,2,'SECRET-NOTE-GAMMA'),
  (3,9001,'SECRET-NOTE-DELTA'), (3,9002,'SECRET-NOTE-EPSILON'), (5,1,'SECRET-NOTE-ZETA');
INSERT INTO claim_drug VALUES (2,1,2,30.00);
