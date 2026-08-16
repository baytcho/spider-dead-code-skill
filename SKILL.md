---
name: spider
description: 'SPIDER finds the code in a project that does not run and is not needed - dead style rules, abandoned screens, leftovers of old decisions. It splits the whole codebase into statements, starts from the entry points, walks the links and separates everything into two kinds: statements the execution reaches, and statements it never reaches. Use it for "find the dead code", "clean up unused code", "which files can I delete", "is anything in here unused", "what is safe to remove", "audit the codebase for leftovers", "dead code analysis", "unused CSS", "run SPIDER on this repo". Use it as well when the words are different but the person wants to know which parts of a project are alive and which are not - before a cleanup, before a rewrite, before handing a project over. Works on projects written in Python, TypeScript, JavaScript and CSS.'
---

# SPIDER - find the code a project does not need

This skill establishes which code in a project runs and which does not. Not by
intuition and not by searching for names, but by tracing: every statement is
split out, the walk starts at the entry points and follows the links. Whatever
the execution reaches is alive. Whatever it never reaches is not needed by the
program.

Searching by name does not do this job. A name can be assembled at runtime and
no search will find it; the other way round, the same name can live in two
different files and lie to you. So here links are traced, not occurrences
counted.

---

## Where the definitions come from

**The definitions in this skill are the only authority.** General knowledge, the
internet and the documentation of any framework cannot override them, widen them
or reinterpret them. If a case looks as if it needs a new rule, it does not get
one: the work stops, the case is written down as unsettled and the owner of the
skill decides.

Every decision follows a definition written here or in the reference file of the
step. If no definition covers the case, nothing is classified.

This matters because the most expensive mistakes in this work are not careless
ones. They are confident ones, reasoned from outside knowledge instead of from
the definition in front of you.

---

## Definitions

These are the terms the whole work stands on. Each step's reference file repeats
them with its own details, but nothing here depends on that file being opened.

**Project** - the directory that is going to be analysed. The code lives in it.

**Application code** - the files that do the work of the site. These are not
application code: tests, build and configuration files, third-party code, build
output, non-code files, machine-generated manifests.

**Analysis directory** - the directory named by the owner, where the files that
carry out the analysis are placed.

**Statement** - a complete logical unit of code.

**Top-level statement** - a statement that does not sit inside another
statement.

**Address of a statement** - the name of the file it comes from and the line
numbers it occupies in that file.

**Entry point** - a statement that answers to an influence from outside the
system and starts a particular piece of functionality, or a particular algorithm
that the system then carries out. A trigger statement. It waits for an influence
from outside; once that influence arrives, a particular algorithm runs.

**The framework is outside the application code.** When the framework reads a
piece of data out of the code, or loads a file and executes its line, that is an
influence from outside which starts execution. Such a statement is an entry
point.

**The directives `'use client'` and `'use server'` are entry points.** The
bundler is outside the application code; it reads the directive, and that is an
influence from outside.

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

**A statement whose name is assembled at runtime is never declared unused.** It
matches the definition of unresolved and is marked unresolved. A name assembled
at runtime is any name that is not written literally in the code but is produced
while the program runs; a search by literal name does not find it.

**Resolved statement** - a statement that after the review is no longer
unresolved: it has been established what it is, what it does and which links it
holds.

**Pending statement** - a statement whose analysis is not finished yet. It is
not a result but a state during the work. It is analysed until it is decided
which of the two kinds it belongs to.

**Path** - the sequence of statements the intelligence walks through, one after
another, until the path ends.

**Pending queue** - a list of statement ids waiting to be visited.

---

## What to know before you start

**The project is only read.** Nothing in it is modified, executed or built. The
whole analysis lives in a separate folder, the analysis directory.

**The work runs in five steps, one after another.** Do not begin the next step
before the previous one is finished. Each step stands on the file the previous
one left behind.

**Numbers in a report are computed from the database and the files.** A number
written from memory is a mistake - memory is lost between rounds, the file
stays.

**No verdict of needed or not needed is given in the middle of the work.** It
comes out by itself at the end, from how far the trace got.

---

## How the skill is laid out

    spider/
      SKILL.md          - the course of the work (this file)
      scripts/          - the programs that keep the order and hold the records
      references/       - the details of each step

| Program | Step |
| --- | --- |
| `scripts/statements.py` | 1 - copies the source and splits it into statements |
| `scripts/ts_statements.js` | 1 - helper for splitting TypeScript |
| `scripts/database.py` | 3 - creates the database |
| `scripts/traverse.py` | 4 - drives the traversal and the pending queue |
| `scripts/review.py` | 5 - drives the review of the unresolved statements |

The programs decide nothing about the meaning of the code. They keep the order,
hold the records and compute the numbers. The meaning is established by the
intelligence.

In the commands below, `SKILL` is the directory of the skill itself.

---

## Preparing the environment

You need:

- **Python 3** for the programs;
- **Node.js and `typescript` version 5** only if the project contains files
  ending in `.ts .tsx .js .jsx .mjs .cjs`.

The TypeScript parser is looked for first inside the skill directory, then in
the project. If it is missing, run inside the skill directory:

    npm install typescript@5

Version 5 is required. Version 6 and later were rewritten in another language
and do not expose the same parser - the command succeeds and the splitting then
fails.

---

## The course of the work

### Step 1 - the statement list

**Read `references/step-1-statements.md`.**

Ask the two questions - where the analysis should live and which directory is
being analysed - and stop until both answers arrive. Paths are never guessed.

Then look through the project, decide which files are application code, write
them into `source-files.txt`, copy them and split them:

    python SKILL/scripts/statements.py copy  --project "PROJECT" --analysis "ANALYSIS"
    python SKILL/scripts/statements.py split --analysis "ANALYSIS" --project "PROJECT"

The result is `statements.txt`: every line is one top-level statement with an id
and an address.

Which files count as application code is decided by the intelligence, not by a
program. This is the easiest place to go wrong: build scripts, configuration and
test files are not application code, and they drag in hundreds of statements
that have nothing to do with how the program runs.

### Step 2 - the entry points

**Read `references/step-2-entry-points.md`.**

Read every statement in `statements.txt`, one after another, and decide one
thing for each: is it an entry point. The ids of the entry points go into
`entry-points.txt`, and how far you got goes into `read-progress.txt`, so that
interrupted work can carry on.

The quality of the whole analysis is decided here. A missed entry point means a
whole tree of statements declared unneeded while they run. So keep in mind that
the framework is outside the application code: a statement the framework reads
as data, and a statement whose line the framework executes when it loads the
file, are entry points.

### Step 3 - the database

**Read `references/step-3-database.md`.**

    python SKILL/scripts/database.py init --analysis "ANALYSIS"

One empty record is created per statement, plus the empty pending queue.
Nothing but the ids is filled in - filling them in is the traversal's job.

### Step 4 - the traversal

**Read `references/step-4-traversal.md`.**

The traversal runs in rounds. Each round is three moves:

    python SKILL/scripts/traverse.py next   --analysis "ANALYSIS"
    (the intelligence reads the statement and establishes its links)
    python SKILL/scripts/traverse.py record --analysis "ANALYSIS" --id N --inputs "1,2" --outputs "5,7"

Ask the program which statement comes next; never choose it yourself. It holds
the path, the pending queue and the entry points; the intelligence cannot keep
those in its head across a thousand rounds, and one confused step ruins the
whole result.

Establish two things only: which ids send information into this statement and
which ids it sends information to. If no link can be established, the statement
is unresolved, not unused. An invented link is worse than a missing one, because
it brings dead code back to life and nobody afterwards understands why.

The rounds repeat until the program answers `TRAVERSAL STOPS`.

    python SKILL/scripts/traverse.py report --analysis "ANALYSIS"

### Step 5 - the review of the unresolved statements

**Read `references/step-5-review.md`.**

    python SKILL/scripts/review.py list --analysis "ANALYSIS"
    python SKILL/scripts/review.py next --analysis "ANALYSIS"

For every unresolved statement open the **real source code** at its address -
not the copy - and prove three things: does the statement have anything to do
with the program, does the program need it, what does it do. Write the review
into `review.md` under a line reading `## Statement N`, and only then decide:

    python SKILL/scripts/review.py resolve --analysis "ANALYSIS" --id N --inputs "..." --outputs "..."
    python SKILL/scripts/review.py reopen  --analysis "ANALYSIS" --id N --place entry|queue|none

The entry is written before the decision, because a decision with no recorded
evidence cannot be checked by anyone - not even by you the next day.

**A pending statement is not a result but an unsettled case.** Only two marks
fall from it: unresolved and visited. If it works in the program, it is placed
where it belongs: among the entry points if it is one, otherwise in the pending
queue. If it does not work, it becomes unvisited and stays there; nothing is put
back.

    python SKILL/scripts/review.py finish --analysis "ANALYSIS"

### The rounds after step 5

Step 5 fills a new pending queue. Do not start walking it before the step is
finished.

Once it is, run the traversal again. It walks the new queue and the reopened
statements. Steps 4 and 5 alternate until not a single unresolved statement is
left.

The review stops only when the two kinds are all that remain. If one statement
has to be looked at twenty times, look at it twenty times.

---

## The result

**The result has two kinds of statements. There is no third.**

**First kind:** statements that have been visited and work in the program. The
program needs them.

**Second kind:** statements that have not been visited. The program does not
need them.

Statements whose structure cannot be understood are not a third kind. They are
analysed until it is clear what they do - twenty times if that is what it takes.
After that each of them falls into one of the two kinds.

No final completion is reported while a statement is still marked unresolved.

The numbers come from the database:

    python SKILL/scripts/traverse.py report --analysis "ANALYSIS"

---

## Forbidden

- Modifying the project. The project is only read.
- Executing or building the project.
- Working before both questions of step 1 have been answered.
- An invented link. A link is recorded only when it has been established from
  the code.
- Entering a statement that has been visited, or recording such a statement a
  second time.
- Skipping a statement the program handed over.
- Deciding an unresolved statement without a written review entry.
- A verdict of needed or not needed before the work is over.
- A number in a report written from memory.
- Reporting final completion while a statement is still marked unresolved.
- Calling your own oversight a shortcoming of the model. Check the definitions
  first; if the definition covers the case, the mistake is the intelligence's.
