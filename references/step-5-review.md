# SPIDER - step 5: the review of the unresolved statements

Read this file before you begin step 5.

---

## 1. What it works on

The real source code in the project's working directory.

The statement ids and their addresses are only the starting information - where
the review begins.

If the analysis directory or the project directory is not known from the current
work, ask about the one that is missing and **stop** until an answer arrives.

---

## 2. Purpose

That not a single unresolved statement is left. That each of them falls into one
of the two kinds.

The review stops only when those two kinds are all that remain. There is no
third kind.

---

## 3. Terms

**Unresolved statement** - a statement marked unresolved during the traversal.

**Resolved statement** - a statement that after this review is no longer
unresolved: it has been established what it is, what it does and which links it
holds.

**Pending statement** - a statement whose analysis is not finished yet. It is
**not a result but a state during the work**. It is analysed by the intelligence
until it is decided which of the two kinds it belongs to - twenty times if that
is what it takes.

**Review file** - the file in which the result of this step is written.

---

## 4. The work

The intelligence receives a list of the statements to be reviewed - the
unresolved ones.

The review goes through every unresolved statement, one after another.

For each of them the intelligence goes into the real source code at its address
and checks how the statement works in the program.

Three things have to be proved: does the statement have anything to do with the
program, does the program need it, what does it do in the program.

---

## 5. What is written into the review file

Against the id of every reviewed statement, full and detailed information is
written:

- what the statement is;
- what it does;
- which links it holds;
- whether those links have anything to do with the program or not;
- if they do - why they were missed the first time and why they were not
  understood;
- the consequences of those mistakes.

---

## 6. What is written into the database

When a statement is resolved, its links are added to the database.

The ids the links point at are looked at. Each of them is checked for whether it
has been visited. If it has, nothing happens. If it has not, it is written into
the pending queue.

That is how the new pending queue is formed.

## 6a. What happens to a pending statement

Only two marks fall from it: **unresolved and visited**. The statement becomes
unvisited. Its record is not touched - the links and the other marks stay as the
traversal left them.

**If it works in the program**, it is placed according to what it is:

- if it is an entry point, its id goes into the entry point list;
- if it is not, it goes into the pending queue.

After that the traversal runs again and reaches it in its own turn.

**If it does not work in the program**, it becomes unvisited and stays there.
Nothing is put back: not into the entry points, not into the pending queue. It
belongs to the second kind and the work on it is done.

If its id is already in the entry point list, the program refuses. Being an
entry point means something outside reaches it, which contradicts "does not work
in the program". The traversal would hand it back as an entry point and the
round would never end. Which of the two is true is decided by the intelligence.

---

## 7. When the new queue starts

After the second review is over - after every unresolved statement has been
reviewed and the information from them has been recorded.

---

## 8. The result

A file listing the suspected errors, which have to be cleared after analysis by
the intelligence.

**The result has two kinds of statements. There is no third.**

**First kind:** statements that have been visited and work in the program. The
program needs them.

**Second kind:** statements that have not been visited. The program does not
need them.

Statements whose structure cannot be understood are not a third kind. They are
analysed until it is clear what they do - twenty times if that is what it takes.
After that each of them falls into one of the two kinds.

The review stops only when those two kinds are all that remain.

No final completion is reported while a statement is still marked unresolved.

---

## 9. Order of execution

### Move 1. The list

    python SKILL/scripts/review.py list --analysis "ANALYSIS"

Gives every unresolved statement with its address and its text, and says which
ones have already been reviewed.

### Move 2. Which one is next

    python SKILL/scripts/review.py next --analysis "ANALYSIS"

Gives the next unresolved statement that has not been reviewed. If there are no
more, it says so.

### Move 3. The review

The intelligence opens the **real source code** at the statement's address - not
the copy in the analysis directory - and proves the three things of section 4.
The copy is a photograph taken at the start of the work; the truth about the
program is in the project itself.

### Move 4. The entry in the review file

It is written into `review.md` in the analysis directory. Every statement starts
with a line:

    ## Statement N

Under it come the six things of section 5, each with a heading of its own. The
entry is written **before** the decision. The program does not accept a decision
for a statement that has no entry.

### Move 5. The decision

A resolved statement:

    python SKILL/scripts/review.py resolve --analysis "ANALYSIS" --id N --inputs "1,2" --outputs "5"

The program fills in the links, removes the unresolved mark, sets the source and
sink marks again and writes into the pending queue every id from the links that
has not been visited yet.

A pending statement - it is reopened:

    python SKILL/scripts/review.py reopen --analysis "ANALYSIS" --id N --place entry
    python SKILL/scripts/review.py reopen --analysis "ANALYSIS" --id N --place queue
    python SKILL/scripts/review.py reopen --analysis "ANALYSIS" --id N --place none

| Place | When |
| --- | --- |
| `entry` | it works in the program and is an entry point - its id goes into the entry point list |
| `queue` | it works in the program but is not an entry point - it goes into the pending queue |
| `none` | it does not work in the program - it stays unvisited and stays there, second kind |

The program removes only the unresolved and visited marks and places the id
where it was told. With `none` it is placed nowhere.

Moves 2 to 5 repeat until the unresolved statements run out.

### Move 6. The end of the step

    python SKILL/scripts/review.py finish --analysis "ANALYSIS"

The program checks that every unresolved statement has been gone through and
writes `suspected-errors.txt` - only the statements reopened in this pass. Those
are the suspected errors: the places where the previous traversal read the code
wrongly.

A statement found not to work in the program does not go into this file. It is
not an error - it belongs to the second kind and the work on it is done.

If even one unresolved statement has not been reviewed, the program refuses and
says which ones.

The file is a working list. While an id is in it, the work is not finished - the
traversal runs again. At the end it is empty.

The program reports that the work is done only when there is nowhere left to go:
no unresolved statement, nothing reopened, no id in the pending queue and no
unvisited entry point. If one of those four remains, the traversal still has
work and the step is not the end.

### Move 7. Report

The numbers in the report are computed from the database, never from memory.

---

## 10. The new pending queue

It fills up throughout step 5, but **it is not walked** until the step is over.

After the end: the traversal of step 4 is run again and walks the new queue by
its own rules.

---

## 11. Who decides what

| Who | What it decides |
| --- | --- |
| The intelligence | what the statement is; what it does; which links it holds; whether it is resolved or reopened; and where it is reopened to - the entry points, the pending queue or nowhere |
| The program | which one comes next; what goes into the new pending queue; removing the marks when a statement is reopened; assembling the file of suspected errors |

---

## 11a. When something has not come out right

An oversight by the intelligence is not called a shortcoming of the model.

When something has not come out right, check the definitions first. If the
definition covers the case, the mistake belongs to the intelligence and is
written up as its own.

---

## 12. Forbidden

- Deciding a statement without a written review entry.
- A second decision on an already resolved statement. A reopened one is reviewed
  anew when the traversal marks it unresolved again - that is not a second
  decision.
- Modifying the project. It is only read.
- Walking the new queue before the step is over.
- A number in the report written from memory.
- Calling your own oversight a shortcoming of the model.
- Reporting final completion while a statement is still marked unresolved.
- Stopping the work with a pending statement left. It is not a result.
