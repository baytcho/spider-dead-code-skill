# SPIDER - step 2: the entry point list

Read this file before you begin step 2.

---

## 1. What it works on

The statement list - the one made in step 1, holding every statement of the
project's code with its id. It sits in the analysis directory.

If the analysis directory is not known from the current work, ask one question -
which directory is the analysis directory - and **stop** until an answer
arrives. The path is never invented and never assumed.

---

## 2. Terms

**Entry point** - a statement that answers to an influence from outside the
system and starts a particular piece of functionality, or a particular
algorithm that the system then carries out. A trigger statement. It waits for an
influence from outside; once that influence arrives, a particular algorithm
runs.

**The framework is outside the application code.** When the framework reads a
piece of data out of the code, or loads a file and executes its line, that is an
influence from outside which starts execution. Such a statement is an entry
point.

**The directives `'use client'` and `'use server'` are entry points.** The
bundler is outside the application code; it reads the directive, and that is an
influence from outside.

**Entry point list** - a file holding nothing but the ids of the statements that
are entry points of the system.

---

## 3. What is done

The entry point list is created. It sits in the analysis directory.

The intelligence reads every statement of the statement list in order, one after
another. For each statement it decides whether it matches the definition of an
entry point.

When a statement is an entry point, its id is written into the entry point list.
The ids stand in the order they were found.

---

## 4. What comes out

An entry point list holding nothing but the ids of the statements that are entry
points of the system.

---

## 5. Order of execution

### Move 1. The analysis directory

If it is known, the work goes on. If it is not, ask the question from section 1
and wait for the answer.

### Move 2. The three files

In the analysis directory there are:

| File | What it is |
| --- | --- |
| `statements.txt` | the statement list made in step 1 |
| `entry-points.txt` | the entry point list, created now |
| `read-progress.txt` | the id of the last statement read |

`entry-points.txt` is created empty. So is `read-progress.txt`, holding `0`.

### Move 3. The reading

The statement list is read **in order, from the beginning to the end**. One line
is one statement.

It is read in portions. After each portion:

- the ids of the entry points found are appended to the end of
  `entry-points.txt`, one per line, in the order they were found;
- the id of the last statement read is written into `read-progress.txt`.

That way interrupted work carries on from where it stopped: `read-progress.txt`
is read and the work resumes at the next statement. Memory is not relied on,
because memory is lost and the file stays.

Check that `entry-points.txt` ends with a newline before appending to it.
Otherwise the last old id and the first new one merge into a single number that
does not exist.

No statement is skipped. All of them are read, from the first to the last.

### Move 4. The decision on each statement

For each statement one thing is decided: does it match the definition of an
entry point from section 2. Nothing else is decided and nothing else is
recorded.

The framework is part of that definition. A statement the framework reads as
data, and a statement whose line the framework executes when it loads the file,
match the definition and are recorded as entry points. The framework is outside
the application code.

### Move 5. Report

The numbers in the report are computed from the files, never from memory: how
many statements were read, how many entry points were found.

The step is finished when `read-progress.txt` holds the id of the last statement
of the statement list.

---

## 6. Forbidden

- Modifying the statement list. It is only read.
- Modifying the project.
- Skipping statements.
- A verdict of needed or not needed. That is not part of step 2.
- A number in the report written from memory.
