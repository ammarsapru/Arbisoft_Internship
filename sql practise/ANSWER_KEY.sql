-- ============================================================
-- ANSWER KEY — Palmer Penguin Database
-- (SQLite syntax; minor tweaks noted for Postgres)
-- ============================================================

-- 1.
SELECT common_name, scientific_name FROM species;

-- 2.
SELECT * FROM observations WHERE body_mass_g > 5000 ORDER BY body_mass_g DESC;

-- 3.
SELECT * FROM observations WHERE sex = '';
-- (if you imported CSVs and blanks became NULL, use: WHERE sex IS NULL)

-- 4.
SELECT * FROM islands WHERE latitude < -65.0;

-- 5.
SELECT study_year, COUNT(*) AS n FROM observations GROUP BY study_year ORDER BY study_year;

-- 6.
SELECT MIN(flipper_length_mm) AS min_fl,
       MAX(flipper_length_mm) AS max_fl,
       ROUND(AVG(flipper_length_mm),1) AS avg_fl
FROM observations;

-- 7.
SELECT o.* FROM observations o
JOIN islands i ON o.island_id = i.island_id
WHERE o.study_year = 2008 AND i.island_name = 'Dream';

-- 8.
SELECT o.observation_id, s.common_name, i.island_name, o.body_mass_g
FROM observations o
JOIN species s ON o.species_id = s.species_id
JOIN islands i ON o.island_id = i.island_id;

-- 9.
SELECT r.first_name, r.last_name, COUNT(*) AS n
FROM observations o
JOIN researchers r ON o.researcher_id = r.researcher_id
GROUP BY r.researcher_id, r.first_name, r.last_name
ORDER BY n DESC
LIMIT 1;

-- 10.
SELECT s.common_name, ROUND(AVG(o.body_mass_g)) AS avg_mass
FROM observations o
JOIN species s ON o.species_id = s.species_id
GROUP BY s.common_name
ORDER BY avg_mass DESC;

-- 11.
SELECT i.island_name, COUNT(o.observation_id) AS n
FROM islands i
LEFT JOIN observations o ON o.island_id = i.island_id
GROUP BY i.island_name
ORDER BY n DESC;

-- 12.
SELECT s.common_name, ROUND(AVG(o.bill_length_mm),1) AS avg_bill
FROM observations o
JOIN species s ON o.species_id = s.species_id
GROUP BY s.common_name
HAVING AVG(o.bill_length_mm) > 45;

-- 13.
SELECT i.island_name, COUNT(DISTINCT o.species_id) AS species_count
FROM islands i
LEFT JOIN observations o ON o.island_id = i.island_id
GROUP BY i.island_name;

-- 14.
SELECT r.first_name, r.last_name, COUNT(*) AS n
FROM observations o
JOIN researchers r ON o.researcher_id = r.researcher_id
GROUP BY r.researcher_id, r.first_name, r.last_name
HAVING COUNT(*) > 30;

-- 15.
SELECT s.common_name, i.island_name, o.body_mass_g
FROM observations o
JOIN species s ON o.species_id = s.species_id
JOIN islands i ON o.island_id = i.island_id
WHERE o.body_mass_g = (SELECT MAX(body_mass_g) FROM observations);

-- 16.
SELECT s.common_name,
       ROUND(100.0 * SUM(CASE WHEN o.sex = '' THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_missing_sex
FROM observations o
JOIN species s ON o.species_id = s.species_id
GROUP BY s.common_name;

-- 17.
SELECT s.common_name, ROUND(AVG(o.body_mass_g)) AS avg_mass
FROM observations o
JOIN species s ON o.species_id = s.species_id
GROUP BY s.common_name
HAVING AVG(o.body_mass_g) > (SELECT AVG(body_mass_g) FROM observations);

-- 18.
SELECT s.common_name, i.island_name,
       ROUND(AVG(o.flipper_length_mm),1) AS avg_flipper
FROM observations o
JOIN species s ON o.species_id = s.species_id
JOIN islands i ON o.island_id = i.island_id
GROUP BY s.common_name, i.island_name
ORDER BY avg_flipper DESC
LIMIT 1;

-- 19.
INSERT INTO islands (island_id, island_name, region, latitude, longitude)
VALUES (4, 'Anvers', 'Palmer Archipelago', -64.55, -64.10);
INSERT INTO observations
  (observation_id, species_id, island_id, researcher_id,
   bill_length_mm, bill_depth_mm, flipper_length_mm, body_mass_g, sex, study_year)
VALUES (119, 1, 4, 1, 39.0, 18.0, 190, 3700, 'male', 2009);

-- 20.
DELETE FROM observations
WHERE researcher_id = (SELECT researcher_id FROM researchers WHERE role = 'Data Analyst');
SELECT COUNT(*) FROM observations;   -- verify it dropped
-- then reset: re-run schema.sql followed by seed_data.sql
