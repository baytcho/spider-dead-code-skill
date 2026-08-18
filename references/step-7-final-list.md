# SPIDER - step 7: the list to be checked in the live code

Read this file before you begin step 7.

---

## 1. What this step is

**This is what the whole work produces.** Everything before it exists so that
this file can be written.

The file holds every statement that has to be checked, each with its address in
the source code - the file it comes from and the lines it occupies - and the
code as it stands in the live file at the moment the list is written.

A statement is on the list because it does not satisfy the conditions of the
cause-and-effect chain of the program: nothing the execution reaches leads to
it.

**Checking every one of them in the live code is the last step of the work and
it is not optional.** The list is not a list of things to delete. It is a list
of things to look at.

---

## 2. What it works on

The database in the analysis directory and the live code in the project.

The live code, not the copy. The copy is a photograph taken at the start of the
work; what is going to be touched afterwards is the project.

---

## 3. When it is written

After step 6 is over and the traversal of step 5 has nowhere left to go.

The program refuses until every one of these is proved at once, from the files
and the database:

- the snapshot matches its manifest, file for file, sum for sum, with nothing
  added and nothing lost;
- no file was left unsplit;
- the entry point list is valid, not empty, and every entry is visited;
- when the machine ran: its fill and its walk have both finished;
- the traversal holds no handed-over statement and no pending queue;
- the reading of step 2 covered the whole statement list;
- not one statement is still marked unresolved;
- every never-examined statement has passed the review;
- the two columns of every record agree with the links table.

An unsettled case is not a result and has no place on the list.

---

## 4. Order of execution

    python SKILL/scripts/final_list.py build --analysis "ANALYSIS" --project "PROJECT"

Two files are written into the analysis directory:

| File | What it is |
| --- | --- |
| `to-check-in-live-code.md` | the list for reading, with the code of every statement |
| `to-check-in-live-code.tsv` | the same list as a table, for further work |

---

## 5. What every entry carries

- the id of the statement;
- the file it comes from;
- the first and the last line it occupies there;
- how many lines that is;
- which ids send information into it and which ids it sends to, as the analysis
  established them;
- the full path to the file in the live code;
- the code itself, line by line, with the line numbers, from the VERIFIED
  snapshot - and a note on the live file: `same`, `changed` or `missing`. A
  changed live file means the line numbers may sit elsewhere now; the entry
  says so and tells the checker to find the statement by its text.

Everything needed to open the place and look is in the entry. Nobody has to go
back to the database to check one statement.

---

## 6. What to say to whoever checks the list

Three things have to be proved for every statement on it:

1. does the statement have anything to do with the program;
2. does the program need it;
3. what does it do in the program.

And one rule that is not bent: a statement whose name is assembled while the
program runs is never declared unused. Searching for the whole written name does
not find such a name. Where it cannot be proved that something is unneeded, say
that it could not be proved, and go on. Do not guess.

Three traps have each turned a living statement into a seemingly dead one:

- a name built at runtime, where the code writes `status-${kind}` and the style
  sheet carries `status-success`;
- a rule used inside its own file, missed by a search that skips the file the
  statement sits in;
- a file name in an import mistaken for a class name, as in `@import "../x.css"`.

---

## 7. Forbidden

- Writing the list while one statement is still marked unresolved.
- Writing the list while an id is still in the pending queue.
- Presenting the list as a list of things to delete.
- Building the code of the entries from anything but the verified snapshot.
- Passing over a drifted live file in silence.
- A number in the report written from memory.
