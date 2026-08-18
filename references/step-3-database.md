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
- the address of the statement - the file it comes from and the first and the
  last line it occupies in that file, exactly as the statement list holds them;
- which ids send information into it - the ids of the statements whose data
  enters this statement;
- which ids it sends the finished information to - the ids of the statements
  this one passes data to;
- visited;
- source;
- sink;
- unresolved.

And the pending queue.

The id and the address are written when the record is created. Everything else
is established by the analysis and stays empty until the traversal.

---

## 4. When it is created

After both the statement list and the entry point list are ready.

---

## 5. What is not done in this step

Nothing except the statement ids and their addresses is filled in. Everything
the analysis establishes - the links, visited, source, sink, unresolved - is
left empty and is filled in during the traversal.

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
- reads the statement ids and their addresses from the statement list;
- creates `analysis.db` in the same directory;
- writes one record per statement - the id and the address are filled in, every
  field the analysis establishes is left empty;
- creates the empty pending queue;
- checks the count: there must be exactly as many records in the database as
  there are statements in the statement list;
- checks that not one record was left without an address;
- validates the entry point list: refuses an empty list, an id that is not a
  statement, and a duplicated id - a traversal from an invalid entry proves
  nothing;
- records the names of the style rules from `css-selectors.tsv`, when step 1
  wrote any.

If the database already exists, the program stops and does not overwrite it. A
command run twice by accident then cannot destroy the work already done.

### Move 3. Report

The numbers in the report are computed from the database and the files, never
from memory: how many statements are in the statement list, how many records are
in the database, how many records carry an address (it must equal the records),
how many fields of the analysis are filled in (it must be zero), how many entry
points are in the entry point list.

---

## 7. How the database is laid out

`analysis.db` is a SQLite database. Two tables:

| Table | Columns |
| --- | --- |
| `statements` | `id`, `file`, `first_line`, `last_line`, `inputs`, `outputs`, `visited`, `visited_by`, `machine_state`, `reviewed`, `is_source`, `is_sink`, `unresolved` |
| `pending_queue` | `id` |
| `links` | `source`, `target`, `kind`, `origin` - every proven link, as "source needs target" |
| `css_selectors` | `statement_id`, `ordinal`, `selector`, `line` - every name of every style rule, addressable on its own |
| `meta` | `key`, `value` - who created the base, which code, which layout |

The states the new columns carry are defined in `states.md`; the kinds the
links table carries are defined in `link-kinds.md`.

At creation `id`, `file`, `first_line` and `last_line` are filled in - the
statement and where it comes from. Every other column is left empty. The pending
queue is created empty.

---

## 8. Forbidden

- Filling in anything except the statement ids and their addresses.
- Overwriting an existing database.
- Modifying the statement list and the entry point list. They are only read.
- Modifying the project.
- A verdict of needed or not needed. That is not part of step 3.
- A number in the report written from memory.
