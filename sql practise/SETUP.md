# Setting Up Your SQL Command Center

You have two solid paths. **DB Browser for SQLite** is the fastest way to get
a graphical "command center" running with zero server setup — recommended if
you just want to practice SQL. If you'd rather work the way most jobs do, the
PostgreSQL path is included too.

---

## PATH A — DB Browser for SQLite (recommended, easiest)

SQLite needs no server; the whole database is a single file. DB Browser gives
you a GUI with a tab to run SQL, a tab to browse tables, and a tab to import
CSVs.

### 1. Install
- Go to **https://sqlitebrowser.org** and download for your OS
  (Windows / macOS / Linux). Install it like any normal app.

### 2. Create the database
1. Open DB Browser → **New Database** → save it as `penguins.db`.
2. When it pops up a "create table" dialog, click **Cancel** — you'll use SQL.

### 3. Build the schema (CREATE stage)
1. Go to the **Execute SQL** tab.
2. Open `schema.sql`, copy its contents in, click **Run** (the ▶ play button).
   This creates all 4 tables.

### 4. Load the data (INSERT stage) — pick ONE:

**Option 1 — paste the SQL (simplest):**
- New Execute SQL tab → paste all of `seed_data.sql` → Run.

**Option 2 — import the CSVs (practices real importing):**
- **File → Import → Table from CSV file.**
- Import in this order so foreign keys resolve:
  `islands.csv`, `species.csv`, `researchers.csv`, then `observations.csv`.
- Check "Column names in first line." Import each into a table of the same name.
  (If a table already exists from schema.sql, import into it.)

### 5. Save
- Click **Write Changes** (top toolbar). Nothing is permanent until you do.

### 6. Start querying
- Execute SQL tab → type a query → Run. Try:
  ```sql
  SELECT * FROM species;
  ```

---

## PATH B — PostgreSQL + pgAdmin (closer to industry)

### 1. Install
- Download the installer from **https://www.postgresql.org/download/**.
  It bundles the Postgres server **and pgAdmin** (the GUI command center).
- During install, set a password for the `postgres` user and remember it.

### 2. Create a database
- Open **pgAdmin** → connect with your password → right-click
  **Databases → Create → Database** → name it `penguins`.

### 3. Open the query tool
- Right-click the `penguins` database → **Query Tool**. This is your command center.

### 4. Build + load
- Open `schema.sql`, paste, run. **Note:** change `INTEGER PRIMARY KEY`
  to `SERIAL PRIMARY KEY` if you want auto-increment (see comments in the file;
  for this dataset the IDs are explicit, so plain INTEGER PRIMARY KEY also works).
- Open `seed_data.sql`, paste, run.

### 5. Query
- Same Query Tool. Type SQL, press **F5** or the ▶ button.

---

## Verifying it loaded
Run this in either tool — you should get 3, 3, 4, 118:
```sql
SELECT COUNT(*) FROM islands;
SELECT COUNT(*) FROM species;
SELECT COUNT(*) FROM researchers;
SELECT COUNT(*) FROM observations;
```

## A note on the DELETE stage
To practice deletes safely, work on a copy, or just re-run `schema.sql`
(it drops and recreates the tables) followed by `seed_data.sql` to reset.
Good things to try:
```sql
-- delete one researcher's records, then the researcher
DELETE FROM observations WHERE researcher_id = 3;
DELETE FROM researchers  WHERE researcher_id = 3;

-- delete all 2007 observations
DELETE FROM observations WHERE study_year = 2007;
```
To make the database enforce foreign keys in SQLite, run this once per session:
```sql
PRAGMA foreign_keys = ON;
```
(Postgres enforces them automatically.)
