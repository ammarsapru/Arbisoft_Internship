# SQL Practise

Hands-on SQL practice covering two themes: querying a small relational database
end-to-end, and modelling every kind of table relationship.

## 1. Palmer Station Penguin Research Database

A self-contained practice database built on the real **Palmer Penguins** dataset
(collected by Dr. Kristen Gorman, Palmer Station LTER). You build the schema from
scratch, load it, and work through graded query exercises from warm-up `SELECT`s
to multi-join subqueries.

### Data model (4 tables)

```
   islands            species           researchers
   --------           --------          -----------
   island_id (PK)     species_id (PK)   researcher_id (PK)

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
- **observations** — 118 rows. One physical measurement of one penguin; the fact
  table, with three foreign keys for real `JOIN` practice.

Mixed data types (text, integers, decimals, a `CHECK`-constrained column) and
intentionally missing `sex` values give practice with messy, realistic data.

### Files

| File | What it's for |
|------|---------------|
| `SCENARIO.md`     | The story and the data model |
| `SETUP.md`        | Step-by-step: install a DB (SQLite or PostgreSQL), build, and load |
| `EXERCISES.md`    | 20 graded query challenges, easy → hard |
| `ANSWER_KEY.sql`  | Solutions to every exercise |
| `schema.sql`      | `CREATE TABLE` statements (SQLite-compatible, with notes for MySQL/Postgres) |
| `seed_data.sql`   | All `INSERT` statements — paste straight in if you skip the CSV import |
| `data/*.csv`      | The same data as CSVs (`islands`, `species`, `researchers`, `observations`) for import practice |

### Quick start

1. Read `SCENARIO.md`, then follow `SETUP.md`.
2. Build the schema: run `schema.sql`.
3. Load the data: run `seed_data.sql`, **or** import the CSVs from `data/` in the
   order `islands → species → researchers → observations` (foreign keys first).
4. Verify the load — you should get `3, 3, 4, 118`:
   ```sql
   SELECT COUNT(*) FROM islands;
   SELECT COUNT(*) FROM species;
   SELECT COUNT(*) FROM researchers;
   SELECT COUNT(*) FROM observations;
   ```
5. Work through `EXERCISES.md`, checking against `ANSWER_KEY.sql`.

## 2. Table Relationships (SQL Server)

A 12-table SQL Server schema that demonstrates every relationship type in one
place.

| File | What it's for |
|------|---------------|
| `relationships.sql` | Full 12-table schema with seed data |
| `many_to_many.sql`  | Quick check of the `OrderProducts` junction table |

- **One-to-One (1:1)** — `Employees ↔ EmployeeBadges`, enforced with a `UNIQUE` foreign key.
- **One-to-Many (1:M)** — e.g. `Departments → Employees`, `Customers → Orders`.
- **Many-to-Many (M:M)** — `Orders ↔ Products` via the `OrderProducts` junction table.

> Note: `relationships.sql` and `many_to_many.sql` use T-SQL (`GO`, `OBJECT_ID`,
> `sys.tables`) and are intended to run against **SQL Server**, whereas the
> penguin scripts target SQLite/PostgreSQL.
