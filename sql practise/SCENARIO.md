# Scenario: Palmer Station Penguin Research Database

## The setting
You've just joined **Palmer Station**, a research base in the Antarctic
Peninsula. For three field seasons (2007–2009), a small team of biologists
tagged and measured penguins across three islands in the Palmer Archipelago.
Their notes are scattered in spreadsheets. Your job: stand up a proper
relational database so the team can store measurements and answer questions
about the colonies.

This scenario is built on the **real Palmer Penguins dataset** (collected by
Dr. Kristen Gorman, Palmer Station LTER) — the measurement ranges, species,
and islands are authentic. The individual observation rows here are
synthetically generated within those real-world ranges so you have a clean,
self-contained set to practice on.

## The data model (4 tables)

```
   islands            species           researchers
   --------           --------          -----------
   island_id (PK)     species_id (PK)   researcher_id (PK)
   ...                ...               ...
      \                  |                 /
       \                 |                /
        \                |               /
              observations (fact table)
              -----------------------
              observation_id (PK)
              species_id     (FK -> species)
              island_id      (FK -> islands)
              researcher_id  (FK -> researchers)
              bill_length_mm, bill_depth_mm,
              flipper_length_mm, body_mass_g,
              sex, study_year
```

- **islands** — 3 rows. Where penguins were observed.
- **species** — 3 rows. Adelie, Gentoo, Chinstrap.
- **researchers** — 4 rows. Who recorded the measurement.
- **observations** — 118 rows. One physical measurement of one penguin.
  This is your fact table; every row points at one island, one species,
  and one researcher.

## Why this fits your goal
- Exactly 4 tables, each ~5–10 columns — small enough to hold in your head.
- Three foreign keys into a single fact table — real JOIN practice.
- Mixed data types: text, integers, decimals, a CHECK-constrained column,
  and intentionally missing `sex` values (blank) so you practice filtering
  for messy data.
- You build it from scratch (CREATE), load it (INSERT), prune it (DELETE),
  and interrogate it (SELECT).

## Files in this package
| File | What it's for |
|------|---------------|
| `schema.sql`     | CREATE TABLE statements (try writing your own first, then compare) |
| `seed_data.sql`  | All INSERT statements — paste straight in if you don't want CSV import |
| `data/*.csv`     | The same data as CSVs, for practicing imports |
| `SETUP.md`       | Step-by-step: install a DB, create the command center, load data |
| `EXERCISES.md`   | Graded query challenges, easy -> hard |
| `ANSWER_KEY.sql` | Solutions to every exercise |
