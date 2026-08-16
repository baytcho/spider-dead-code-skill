# SPIDER - step 3: the database

Read this file before you begin step 3.

---

## 1. Where it is created

In the analysis directory. Every file the analysis needs lives in one and the
same directory.

If the analysis directory is not known from the current work, ask one question -
which directory is the analysis directory - and **stop** until an answer
arrives. The path is never invented and never assumed.

---

## 2. Terms

**Database** - the place where the results of analysing the statements are
recorded.

**Statement record** - the row in the database holding everything recorded about
one statement.

**Pending queue** - a list of statement ids waiting to be visited.

---

## 3. What the database holds

Records for the statements. One record per statement of the statement list.
Every record holds:

- the id of the statement - the id it was given in the statement list;
- which ids send information into it - the ids of the statements whose data
  enters this statement;
- which ids it sends the finished information to - the ids of the statements
  this one passes data to;
- visited;
- source;
- sink;
- unresolved.

And the pending queue.

---

## 4. When it is created

After both the statement list and the entry point list are ready.

---

## 5. What is not done in this step

Nothing except the statement ids is filled in. The records are created empty and
are filled in during the traversal.

---

## 6. Order of execution

### Move 1. The analysis directory

If it is known, the work goes on. If it is not, ask the question from section 1
and wait for the answer.

### Move 2. Creating

    python SKILL/scripts/database.py init --analysis "ANALYSIS"

The program:

- checks that both the statement list and the entry point list are in the
  directory; if one is missing it stops and says which;
- reads the statement ids from the statement list;
- creates `analysis.db` in the same directory;
- writes one empty record per statement - only the id is filled in;
- creates the empty pending queue;
- checks the count: there must be exactly as many records in the database as
  there are statements in the statement list.

If the database already exists, the program stops and does not overwrite it. A
command run twice by accident then cannot destroy the work already done.

### Move 3. Report

The numbers in the report are computed from the database and the files, never
from memory: how many statements are in the statement list, how many records are
in the database, how many fields besides the id are filled in (it must be zero),
how many entry points are in the entry point list.

---

## 7. How the database is laid out

`analysis.db` is a SQLite database. Two tables:

| Table | Columns |
| --- | --- |
| `statements` | `id`, `inputs`, `outputs`, `visited`, `is_source`, `is_sink`, `unresolved` |
| `pending_queue` | `id` |

At creation only `id` is filled in. Every other column is left empty. The
pending queue is created empty.

---

## 8. Forbidden

- Filling in anything except the statement ids.
- Overwriting an existing database.
- Modifying the statement list and the entry point list. They are only read.
- Modifying the project.
- A verdict of needed or not needed. That is not part of step 3.
- A number in the report written from memory.
