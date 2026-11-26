"""Connection setup shared by the agent's SQL tool and the SQL command.

What happens on every call (each call is independent, nothing is cached between calls):

1. The file named in CLAIMS_DB is attached READ_ONLY and its eight tables are copied into a private
   in-memory database. The copy of claim_diagnosis leaves out diagnosis_note, so the sensitive text is never
   present in the database that queries run against.
2. The source file is detached. From here on nothing can reach it, so the source data cannot be changed.
3. A small semantic layer of views is created on top of the copies (latest claim version, SGD amounts,
   "Unknown" attribution, de-duplicated lookups and diagnoses).
4. Memory is capped, external access (files, network, extensions) is disabled and the configuration is
   locked.

The in-memory copy is written during steps 1-3 only. The guard in sql_guard.py keeps queries read-only after
that; if it were ever bypassed, a write could only touch this throw-away copy.
"""
import duckdb

SOURCE_COLUMNS = {
    "lookup": ["type", "value", "descr"],
    "provider": ["provider_id", "name", "type", "country_code", "region"],
    "doctor": ["doctor_id", "name", "specialty"],
    "ref_icd": ["icd_id", "icd_code", "descr"],
    "drug": ["drug_id", "name", "type"],
    "claim": ["claim_id", "provider_id", "doctor_id", "visit_date", "approved_on", "rejected_on", "voided_on",
              "currency_code", "currency_rate", "claim_amt", "grand_total", "visit_type", "loaded_at"],
    "claim_diagnosis": ["claim_id", "icd_id"],          # diagnosis_note is deliberately not loaded
    "claim_drug": ["claim_id", "drug_id", "qty", "cost"],
}

# Codes are stored inconsistently (provider.type is the number 1, lookup.value is the text '001').
# Both sides are reduced to the same key: the integer value when the code is numeric, else trimmed upper text.
def _code_key(expr: str) -> str:
    return (f"coalesce(CAST(TRY_CAST(CAST({expr} AS VARCHAR) AS BIGINT) AS VARCHAR), "
            f"upper(trim(CAST({expr} AS VARCHAR))))")


VIEWS = [
    # One row per (type, code). The raw lookup has repeated rows; joining to it directly multiplies rows.
    f"""CREATE VIEW lookup_clean AS
        SELECT type, {_code_key('value')} AS code_key, min(descr) AS descr, count(DISTINCT descr) AS descr_variants
        FROM lookup GROUP BY 1, 2""",

    # provider_id -> provider_key. The provider table holds the same provider more than once under a
    # different id with a re-typed name ("Harbour Family Clinic 1" / "harbour family clinic 1."). Rows are
    # merged only when the normalised name AND type, country and region all match; the smallest id is the key.
    """CREATE VIEW provider_map AS
        WITH p AS (
            SELECT *, trim(regexp_replace(regexp_replace(lower(name), '[^a-z0-9 ]', '', 'g'), ' +', ' ', 'g')) AS name_key
            FROM provider
            QUALIFY row_number() OVER (PARTITION BY provider_id ORDER BY name, type, country_code, region) = 1)
        SELECT provider_id, name, type, country_code, region,
               CASE WHEN name_key = '' THEN provider_id
                    ELSE min(provider_id) OVER (PARTITION BY name_key, type, country_code, region) END AS provider_key
        FROM p""",

    # One row per real provider (after merging duplicates), codes decoded.
    f"""CREATE VIEW provider_dim AS
        WITH g AS (
            SELECT provider_key, arg_min(name, provider_id) AS name, arg_min(type, provider_id) AS type,
                   arg_min(country_code, provider_id) AS country_code, arg_min(region, provider_id) AS region,
                   count(*) AS source_rows
            FROM provider_map GROUP BY provider_key)
        SELECT g.provider_key AS provider_id, g.name AS provider_name, g.type AS provider_type_code,
               coalesce(t.descr, 'Unknown') AS provider_type,
               coalesce(nullif(upper(trim(g.country_code)), ''), 'Unknown') AS country_code,
               g.region AS region_code, coalesce(r.descr, 'Unknown') AS region, g.source_rows
        FROM g
        LEFT JOIN lookup_clean t ON t.type = 'PROVIDER_TYPE' AND t.code_key = {_code_key('g.type')}
        LEFT JOIN lookup_clean r ON r.type = 'PROVIDER_REGION' AND r.code_key = {_code_key('g.region')}""",

    # doctor_id -> doctor_key. Doctors are people, and people share names: two doctors with the IDENTICAL name
    # are kept apart. Two rows are merged only when the same name is typed differently ("Locum Doctor" /
    # "Locum doctor") and the specialty matches, which is the signature of one doctor entered twice.
    """CREATE VIEW doctor_map AS
        WITH d AS (
            SELECT *, trim(regexp_replace(regexp_replace(lower(name), '[^a-z0-9 ]', '', 'g'), ' +', ' ', 'g')) AS name_key
            FROM doctor
            QUALIFY row_number() OVER (PARTITION BY doctor_id ORDER BY name, specialty) = 1)
        SELECT doctor_id, name, specialty,
               CASE WHEN name_key <> '' AND min(name) OVER w <> max(name) OVER w
                    THEN min(doctor_id) OVER w ELSE doctor_id END AS doctor_key
        FROM d
        WINDOW w AS (PARTITION BY name_key, specialty)""",

    # One row per real doctor, specialty decoded.
    f"""CREATE VIEW doctor_dim AS
        WITH g AS (
            SELECT doctor_key, arg_min(name, doctor_id) AS name, arg_min(specialty, doctor_id) AS specialty,
                   count(*) AS source_rows
            FROM doctor_map GROUP BY doctor_key)
        SELECT g.doctor_key AS doctor_id, g.name AS doctor_name, g.specialty AS specialty_code,
               coalesce(s.descr, 'Unknown') AS specialty, g.source_rows
        FROM g LEFT JOIN lookup_clean s ON s.type = 'SPECIALTY' AND s.code_key = {_code_key('g.specialty')}""",

    f"""CREATE VIEW drug_dim AS
        WITH g AS (
            SELECT * FROM drug QUALIFY row_number() OVER (PARTITION BY drug_id ORDER BY name, type) = 1)
        SELECT g.drug_id, g.name AS drug_name, g.type AS drug_type_code, coalesce(t.descr, 'Unknown') AS drug_type
        FROM g LEFT JOIN lookup_clean t ON t.type = 'DRUG_TYPE' AND t.code_key = {_code_key('g.type')}""",

    # One row per claim_id: the most recently loaded version, then status flags, SGD amounts and attributes.
    # The version is chosen BEFORE any status filter, so a claim whose latest version is voided is not
    # "rescued" by an older approved version.
    f"""CREATE VIEW claim_latest AS
        WITH versions AS (SELECT DISTINCT * FROM claim),
        ranked AS (
            SELECT *,
                   row_number() OVER (PARTITION BY claim_id ORDER BY loaded_at DESC NULLS LAST,
                       approved_on, rejected_on, voided_on, claim_amt, grand_total, provider_id, doctor_id,
                       visit_date, currency_code, currency_rate, visit_type) AS rn,
                   count(*) OVER (PARTITION BY claim_id) AS version_count
            FROM versions)
        SELECT c.claim_id, c.visit_date, strftime(c.visit_date, '%Y-%m') AS visit_month,
               (c.approved_on IS NOT NULL AND c.voided_on IS NULL) AS is_approved,
               (c.rejected_on IS NOT NULL) AS is_rejected,
               (c.voided_on IS NOT NULL) AS is_voided,
               c.approved_on, c.rejected_on, c.voided_on,
               c.currency_code, c.currency_rate, c.claim_amt, c.grand_total,
               CASE WHEN c.currency_rate > 0 AND isfinite(c.currency_rate)
                    THEN CAST(c.claim_amt AS DOUBLE) / c.currency_rate END AS claim_amt_sgd,
               CASE WHEN c.currency_rate > 0 AND isfinite(c.currency_rate)
                    THEN CAST(c.grand_total AS DOUBLE) / c.currency_rate END AS grand_total_sgd,
               c.visit_type AS visit_type_code, coalesce(vt.descr, 'Unknown') AS visit_type,
               pm.provider_key AS provider_id, c.provider_id AS provider_id_raw,
               coalesce(p.provider_name, 'Unknown') AS provider_name,
               coalesce(p.provider_type, 'Unknown') AS provider_type,
               coalesce(p.country_code, 'Unknown') AS country_code,
               coalesce(p.region, 'Unknown') AS region,
               dm.doctor_key AS doctor_id, c.doctor_id AS doctor_id_raw,
               coalesce(d.doctor_name, 'Unknown') AS doctor_name,
               coalesce(d.specialty, 'Unknown') AS specialty,
               c.loaded_at, c.version_count
        FROM ranked c
        LEFT JOIN provider_map pm ON pm.provider_id = c.provider_id
        LEFT JOIN provider_dim p ON p.provider_id = pm.provider_key
        LEFT JOIN doctor_map dm ON dm.doctor_id = TRY_CAST(c.doctor_id AS BIGINT)
        LEFT JOIN doctor_dim d ON d.doctor_id = dm.doctor_key
        LEFT JOIN lookup_clean vt ON vt.type = 'VISIT_TYPE' AND vt.code_key = {_code_key('c.visit_type')}
        WHERE c.rn = 1""",

    # One row per (claim, stored ICD id). Repeated pairs are collapsed; ids missing from ref_icd keep their
    # id but are labelled 'Unknown'. A claim can have several diagnoses, so groups overlap.
    """CREATE VIEW claim_icd AS
        WITH icd AS (
            SELECT * FROM ref_icd QUALIFY row_number() OVER (PARTITION BY icd_id ORDER BY icd_code, descr) = 1)
        SELECT DISTINCT cd.claim_id, cd.icd_id, coalesce(icd.icd_code, 'Unknown') AS icd_code,
               coalesce(icd.descr, 'Unknown') AS diagnosis
        FROM claim_diagnosis cd LEFT JOIN icd ON icd.icd_id = cd.icd_id""",
]


def connect(path: str) -> duckdb.DuckDBPyConnection:
    """Build the guarded in-memory database from the DuckDB file at `path`."""
    con = duckdb.connect(":memory:")
    escaped = str(path).replace("'", "''")
    con.execute(f"ATTACH '{escaped}' AS src (READ_ONLY)")
    try:
        for table, cols in SOURCE_COLUMNS.items():
            col_list = ", ".join(f'"{c}"' for c in cols)
            con.execute(f'CREATE TABLE main."{table}" AS SELECT {col_list} FROM src.main."{table}"')
    finally:
        con.execute("DETACH src")
    for ddl in VIEWS:
        con.execute(ddl)
    con.execute("SET memory_limit = '2GB'")
    con.execute("SET enable_external_access = false")
    con.execute("SET lock_configuration = true")
    return con
