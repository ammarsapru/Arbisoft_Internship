# Exercises — Palmer Penguin Database

Work top to bottom; they ramp from warm-up to genuinely tricky.
Solutions are in `ANSWER_KEY.sql`.

## Warm-up (SELECT, WHERE, ORDER BY)
1. List every species with its scientific name.
2. Show all observations with a body mass over 5000 g, heaviest first.
3. Find observations where `sex` was not recorded (the blank ones).
4. List islands south of latitude -65.0.

## Filtering & functions
5. How many penguins were measured in each study year?
6. Show the min, max, and average flipper length across all observations.
7. List observations from 2008 on Dream island. (You'll need the island_id.)

## Joins (the core skill)
8. Show each observation's species **common name** and **island name**
   instead of their IDs.
9. Which researcher recorded the most observations? Show their full name and the count.
10. Average body mass per species, with the species name — heaviest first.
11. Count observations per island, showing island names with zero handled correctly.

## Grouping & having
12. Which species has an average bill length above 45 mm?
13. For each island, show how many distinct species were observed there.
14. List researchers who recorded more than 30 observations.

## Harder (subqueries / multi-join)
15. Find the single heaviest penguin and report its species and island names.
16. For each species, what percentage of its observations are missing a sex value?
17. Show species whose average body mass is above the overall average body mass.
18. Which island–species combination has the highest average flipper length?

## CREATE / INSERT / DELETE drills
19. Add a new island ("Anvers", region "Palmer Archipelago"), then insert a
    new observation tied to it. (Watch the foreign keys.)
20. Delete every observation recorded by the "Data Analyst", then verify the
    count dropped. Then reset the database from the scripts.
