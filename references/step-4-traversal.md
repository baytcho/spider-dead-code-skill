# SPIDER - step 4: the traversal

Read this file before you begin step 4.

---

## 1. What it works on

The statement list, the entry point list and the database - all of them in the
analysis directory. The pending queue lives inside the database.

If the analysis directory is not known from the current work, ask one question -
which directory is the analysis directory - and **stop** until an answer
arrives.

---

## 2. Terms

**Visited statement** - a statement that has been read and analysed by the
intelligence and whose record in the database has been filled in.

**Source** - a statement that has only ids it sends information to, and no ids
that send information into it.

**Sink** - a statement where the information ends and there are no statements it
is meant for.

**Unresolved statement** - a statement in one of these situations: information
enters it from a source that is not recorded; another statement sends
information to it while that is not recorded on its side; it points at something
that is not in the program; it uses a variable that is defined nowhere.

**Path** - the sequence of statements the intelligence walks through, one after
another, until the path ends.

---

## 3. The beginning

Take the id of the statement that is the first entry point and has not been
visited.

---

## 4. Working on one statement

The statement is read. The intelligence understands where its data comes from
and where its data goes.

In the statement's record in the database these are filled in:

- which ids send information into it;
- which ids it sends the finished information to;
- it is marked visited.

If the statement matches the definition of a source, it is marked as a source.

If the statement matches the definition of a sink, it is marked as a sink.

If the statement matches the definition of unresolved, it is marked unresolved
and visited.

**A statement whose name is assembled at runtime is never declared unused. It
matches the definition of unresolved and is marked unresolved.**

A name assembled at runtime is any name that is not written literally in the
code but is produced while the program runs. A search by literal name does not
find it. So the statement carrying it is marked unresolved instead of being
passed over.

After the first traversal there are only unresolved statements. Mistakes are
settled after the second traversal.

If the statement's id was in the pending queue, it is removed from it.

---

## 5. Movement

From the outputs of the statement the walk goes forward to the smallest id that
has not been visited.

The other outputs are written into the pending queue. If an output id is already
in the pending queue, nothing happens - it is not written twice. If an output
has been visited, it is not written.

A statement that has been visited is never entered again.

The path has ended in three cases: the statement has no output; all of its
outputs have been visited; the statement is unresolved.

---

## 6. When the path has ended

The smallest id is taken out of the pending queue and a new trace starts from
it.

When not a single id is left in the pending queue, the id of the next unvisited
statement from the entry point list is taken.

When the pending queue is empty and every statement of the entry point list has
been visited, the traversal stops.

---

## 7. Order of execution

The traversal runs in rounds. Each round is three moves and repeats until the
word comes that the traversal stops.

### Move 1. Which one is next

    python SKILL/scripts/traverse.py next --analysis "ANALYSIS"

The program answers with the id of the statement, its address and its text, and
says where it came from: the path, the pending queue or the entry points. When
there are no more, it answers `TRAVERSAL STOPS` and the traversal is over.

Which one comes next is decided by the program, following the rules of sections
3, 5 and 6. None of it is decided from memory, because one missed id ruins the
whole result.

### Move 2. The reading

The intelligence reads the statement. When needed it opens the file at its
address and looks at the code around it. It establishes two things and only
those:

- which ids send information into this statement;
- which ids this statement sends information to.

If the statement matches the definition of unresolved, that is the third thing
established.

### Move 3. The recording

    python SKILL/scripts/traverse.py record --analysis "ANALYSIS" --id N --inputs "1,2" --outputs "5,7"

For an unresolved statement add `--unresolved`. An empty list is passed as `""`.

The program fills in the record, marks it visited, sets the source and sink
marks following the definitions of section 2, removes the id from the pending
queue, picks the next one following the rules of movement and writes the
remaining outputs into the pending queue.

The answer says which statement was recorded, which marks it got, which one is
next and whether the path has ended.

### Move 4. Report

    python SKILL/scripts/traverse.py report --analysis "ANALYSIS"

The numbers in the report are computed from the database, never from memory.

---

## 8. Who decides what

| Who | What it decides |
| --- | --- |
| The intelligence | which ids send information in; which ids it sends information to; whether the statement is unresolved |
| The program | which statement comes next; what goes into and out of the pending queue; the source and sink marks, which follow directly from the two lists of ids |

The program decides nothing about the meaning of a statement. The intelligence
does not keep the queue in its head.

---

## 9. Forbidden

- Entering a statement that has been visited.
- Recording a visited statement a second time.
- Skipping a statement the program handed over.
- Modifying the statement list, the entry point list or the project. They are
  only read.
- A verdict of needed or not needed. That is not part of step 4.
- A number in the report written from memory.
- An invented link. A link is recorded only when it has been established from
  the code. If no link has been established, the statement is unresolved.
