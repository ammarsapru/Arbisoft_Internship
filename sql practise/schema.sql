-- ============================================================
-- PALMER STATION PENGUIN RESEARCH DATABASE — SCHEMA
-- SQLite-compatible (notes for MySQL/PostgreSQL inline)
-- ============================================================

-- Drop in reverse-dependency order so re-runs are clean
DROP TABLE IF EXISTS observations;
DROP TABLE IF EXISTS researchers;
DROP TABLE IF EXISTS species;
DROP TABLE IF EXISTS islands;

-- ---------- Lookup table: islands ----------
CREATE TABLE islands (
    island_id    INTEGER PRIMARY KEY,
    island_name  TEXT    NOT NULL UNIQUE,
    region       TEXT    NOT NULL,
    latitude     REAL,
    longitude    REAL
);

-- ---------- Lookup table: species ----------
CREATE TABLE species (
    species_id           INTEGER PRIMARY KEY,
    common_name          TEXT NOT NULL UNIQUE,
    scientific_name      TEXT NOT NULL,
    avg_lifespan_years   INTEGER,
    conservation_status  TEXT
);

-- ---------- Lookup table: researchers ----------
CREATE TABLE researchers (
    researcher_id  INTEGER PRIMARY KEY,
    first_name     TEXT NOT NULL,
    last_name      TEXT NOT NULL,
    institution    TEXT,
    role           TEXT,
    start_year     INTEGER
);

-- ---------- Fact table: observations ----------
CREATE TABLE observations (
    observation_id     INTEGER PRIMARY KEY,
    species_id         INTEGER NOT NULL,
    island_id          INTEGER NOT NULL,
    researcher_id      INTEGER NOT NULL,
    bill_length_mm     REAL,
    bill_depth_mm      REAL,
    flipper_length_mm  INTEGER,
    body_mass_g        INTEGER,
    sex                TEXT CHECK (sex IN ('male','female','')),
    study_year         INTEGER NOT NULL,
    FOREIGN KEY (species_id)    REFERENCES species(species_id),
    FOREIGN KEY (island_id)     REFERENCES islands(island_id),
    FOREIGN KEY (researcher_id) REFERENCES researchers(researcher_id)
);

-- MySQL note: INTEGER PRIMARY KEY -> INT AUTO_INCREMENT PRIMARY KEY,
--             TEXT -> VARCHAR(n), REAL -> DECIMAL(5,1) or FLOAT.
-- PostgreSQL note: INTEGER PRIMARY KEY -> SERIAL PRIMARY KEY, TEXT is fine.
