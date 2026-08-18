---
name: spider
description: 'SPIDER finds the code in a project that does not run and is not needed - dead style rules, abandoned screens, leftovers of old decisions. It splits the whole codebase into statements, lets a code property graph fill in every link it can prove, starts from the entry points, walks what is left and produces one file: every statement that has to be checked in the live code, with the file and the lines where it sits, because nothing the execution reaches leads to it. Use it for "find the dead code", "clean up unused code", "which files can I delete", "is anything in here unused", "what is safe to remove", "audit the codebase for leftovers", "dead code analysis", "unused CSS", "run SPIDER on this repo". Use it as well when the words are different but the person wants to know which parts of a project are alive and which are not - before a cleanup, before a rewrite, before handing a project over. Works on projects written in Python, TypeScript, JavaScript and CSS.'
---

# SPIDER - find the code a project does not need

## What this skill produces

**Running SPIDER produces one file.** It holds every statement that has to be
checked, each with its place in the source code - the file it comes from and the
lines it occupies - and the code as it stands in the live file.

A statement is in that file because it does not satisfy the conditions of the
cause-and-effect chain of the program: nothing the execution reaches leads to
it.

**Checking those statements in the live code is the last step of the work and it
is not optional.** The file is not a list of things to delete. It is a list of
places to look at, one by one, before anything is touched.

---

This skill establishes which code in a project runs and which does not. Not by
intuition and not by searching for names, but by tracing: every statement is
split out, the walk starts at the entry points and follows the links. Whatever
the execution reaches is alive. Whatever it never reaches is not needed by the
program.

Searching by name does not do this job. A name can be assembled at runtime and
no search will find it; the other way round, the same name can live in two
different files and lie to you. So here links are traced, not occurrences
counted.

**Between the database and the traversal the machine proves what it can.** It
does this from two sides, because execution arrives at a statement in two
ways. A code property graph, built over the same code, gives the calls: who
executes whom. The load graph, derived from the source itself, gives the
loading: a top-level statement runs exactly when its file is loaded, and no
call graph can express that. Version 2.1 had only the first, and in a real
project that half explained 54% of the living code and handed the rest to the
final list as though execution provably never reached it. **Version 2.2 adds
the load graph, and a walk that measures how much of the project it
explained.** What a machine can prove, a machine proves; the intelligence
then works on what is left, and the run says plainly how much that is. The
method does not change and the machine decides nothing.

---

## Where the definitions come from

**The definitions in this skill are the only authority.** General knowledge, the
internet and the documentation of any framework cannot override them, widen them
or reinterpret them. No case gets a new rule invented for it.

**The work never stops.** A case you cannot settle from the definitions is
exactly what the unresolved mark is for: mark the statement unresolved and carry
on. Step 6 takes it up against the real source code and settles it there. There
is no other place to put an unsettled case, and there is no pause.

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

**Code property graph** - one graph holding the structure of the code, the order
of execution and the movement of data at the same time. It is built by a tool
outside this skill and it decides nothing: it only establishes links that can be
proved from the code.

**Visited statement** - a statement that has been read and analysed and whose
record in the database has been filled in.

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

**The work runs in seven steps, one after another.** Do not begin the next step
before the previous one is finished. Each step stands on the file the previous
one left behind.

**Numbers in a report are computed from the database and the files.** A number
written from memory is a mistake - memory is lost between rounds, the file
stays.

**No verdict of needed or not needed is given in the middle of the work.** It
comes out by itself at the end, from how far the trace got.

**The graph does not read style sheets.** Step 4 reaches a sheet's own
at-rules through the load graph, and it says nothing at all about the rules
inside it. An empty record after step 4 means "not looked at", never "not
needed". Step 6 settles them one by one against the real source code. An
analysis that stops after step 4 because the numbers look complete will
delete live code.

**Unreached is not the same as dead.** A statement the machine did not reach
is one the machine saw no way into. That is proof only as far as the machine
can see, and the walk says how far that is: it measures its own coverage, and
step 7 refuses to write the list when the load graph never ran. Read the
coverage line before reading the list.

**What this method deliberately cannot see.** The unit of measurement is the
top-level statement: a dead branch inside a living function is invisible, and
that is the method, not a defect. The two blindnesses of the earlier versions
are closed in this one: loading no longer proves the definitions of a loaded
file - an unused name in a loaded file is a candidate, because being
available is not being needed - and a `'use client'` or `'use server'`
directive in a file nothing imports is demoted: the bundler reads a directive
only out of a file it is given, so the outside influence never fires, and the
whole file stands as a finding.

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
| `scripts/joern_export.sc` | 4 - exports every link of a graph |
| `scripts/load_links.py` | 4 - derives the load graph from the snapshot itself |
| `scripts/name_links.py` | 4 - derives the name graph: who defines a name, who writes it |
| `scripts/machine_links.py` | 4 - merges, translates, records and walks the links |
| `scripts/traverse.py` | 5 - drives the traversal and the pending queue |
| `scripts/review.py` | 6 - drives the review of the unresolved statements |
| `scripts/style_links.py` | 6 - finds the users of every open style statement |
| `scripts/final_list.py` | 7 - writes the list to be checked in the live code |
| `scripts/version.py` | the one place the version numbers live |

The programs decide nothing about the meaning of the code. They keep the order,
hold the records and compute the numbers. The meaning is established by the
intelligence.

In the commands below, `SKILL` is the directory of the skill itself.

---

## Preparing the environment

You need:

- **Python 3** for the programs;
- **Node.js and `typescript` version 5** only if the project contains files
  ending in `.ts .tsx .js .jsx .mjs .cjs`;
- **Java 17 or newer and Joern** only for step 4.

The TypeScript parser lives inside the skill directory and nowhere else. If
it is missing, run inside the skill directory:

    npm install typescript@5

Version 5 is required and pinned by the skill's own lockfile. Version 6 is
the last release of the JavaScript codebase and keeps the parser; version 7
is the native rewrite and ships without this API. The parser is loaded ONLY
from the skill directory - never from the analysed project, because that
would execute the project's own code.

Java, on Windows, Debian or macOS in turn:

    winget install Microsoft.OpenJDK.21
    sudo apt-get install openjdk-21-jdk
    brew install openjdk@21

Joern is downloaded from its own releases at `github.com/joernio/joern` and
unpacked outside the project and outside the analysis directory. Check both
before step 4:

    java -version
    JOERN/joern-cli/joern --help

**Step 4 is the only step that needs them.** Without Java and Joern the work
still runs: steps 5 and 6 then start from an empty database, exactly as they did
before this step existed. It costs time, not correctness.

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
that have nothing to do with how the program runs. A test file is a test file
wherever it sits and whatever it is called.

The splitter reads Python, TypeScript and JavaScript, CSS, and shell
(`.sh`): a shell statement is a function with its body, a compound command
with its closer, or one command with its continuations and here-documents.

**The register of the whole world - `source-scope.tsv`, optional but
recommended.** One line per discovered file: path, role and evidence, where
the role is one of `application`, `test`, `control`, `migration`,
`generated`, `dependency`, `excluded`. When the register exists, the copy
refuses a listed file that is missing from it or carries another role, and
step 7 subtracts the registered files from the "live files never seen"
finding. It decides nothing; it records WHY every file is in or out, so
the decision itself can be checked later.

**A file that is not UTF-8 is quarantined, not fatal.** The copy names it
in the manifest, the work goes on, and the final list carries it as a
finding: nothing about a file nobody could read is proven.

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

One record is created per statement, plus the empty pending queue. The id and
the address - the file and the line numbers the statement occupies in it - are
written straight away. Everything the analysis establishes is left empty:
filling it in is the job of the steps that follow.

### Step 4 - the machine links

**Read `references/step-4-machine-links.md`, `references/link-kinds.md` and
`references/states.md`.**

Execution arrives at a statement in two ways, and this step proves both.

**The load graph and the name graph first, because they need nothing but
the snapshot:**

    python SKILL/scripts/load_links.py derive --analysis "ANALYSIS"
    python SKILL/scripts/name_links.py derive --analysis "ANALYSIS"

A statement that acts by the very act of loading runs exactly when its file
is loaded - that is the load graph, and no call graph can express it. A
definition is needed exactly when a living statement writes its name - that
is the name graph, and it also writes the record of who defines what, which
the merge checks the graph's name references against. The two run in this
order, before the merge.

**The call graph, second, when the tools for it are present:**

    mkdir ANALYSIS/machine
    JOERN/joern-cli/pysrc2cpg ANALYSIS/source          -o ANALYSIS/machine/python.cpg.bin
    JOERN/joern-cli/jssrc2cpg ANALYSIS/source/frontend -o ANALYSIS/machine/front.cpg.bin

Then, once per graph, with the two variables set - on POSIX shells
`SPIDER_CPG=... SPIDER_OUT=...`, in PowerShell `$env:SPIDER_CPG = "..."` and
`$env:SPIDER_OUT = "..."`:

    JOERN/joern-cli/joern --script SKILL/scripts/joern_export.sc

    python SKILL/scripts/machine_links.py merge --analysis "ANALYSIS"

**Both go into the database together:**

    python SKILL/scripts/machine_links.py fill  --analysis "ANALYSIS"
    python SKILL/scripts/machine_links.py walk  --analysis "ANALYSIS"

Every kind of link is exported, not a chosen few. What happens to each kind is
the contract of `link-kinds.md`: the causal kinds - calls, name references,
imports, loading, name use - enter the database as "source needs target"
links; a `REF` may land only on a statement that defines a name, checked
against the name graph's record; the structural kinds - containment, order,
dominance, types, and since this version the graph's data flow, whose
top-level edges are only the wiring of the module body - stay in the merged
file and never enter the database. Structure is not need, and mixing the two
is how unreachable code gets declared alive.

**The one asymmetry of the load graph.** Loading a code file proves only the
statements that act by the very act of loading - top-level calls and control
flow, `from __future__`, imports performed for their effect. A definition or
a constant becomes available, and being available is not being needed: it is
needed exactly when a living statement writes its name, which is the name
graph's `USES` link. A loaded style sheet runs only the at-rules that pull in
further sheets and the rules that name no class and no id; a rule addressed
to a class or an id is needed where every name of its selector is written by
something alive, which step 6 establishes. Without this asymmetry no dead
statement in a loaded file could ever be found.

**fill sets no mark.** A link alone proves nothing about reachability. The
visited mark comes only from **walk**, which starts at the entry points and
follows the needs-links; whatever it reaches is proven used, and it is the
only thing the machine may ever mark. An isolated nest of dead code - a dead
statement calling another dead statement - has links and stays unvisited, as
it must.

**walk measures its own coverage and says it out loud.** It reports how many
files it reached against how many files something loads, and it names the
files that are loaded and still never walked. When the load graph was not
filled it says so, and step 7 then refuses to write the list at all: without
it, "unreached" means only that the machine saw no way in. In a real run of
this skill that difference was 1904 statements, most of them live code.

To run the machine part again, `machine_links.py reset --confirm` removes the
machine links and the machine marks in one transaction and touches nothing the
review wrote.

Three traps live in the graph tool and every one of them has cost a working
day: a path that is not plain ASCII arrives as question marks; the tool writes
a working copy of the graph into the current directory; and the lines it
prints about names with many definitions are not errors but the places it is
unsure about, for which it writes no link at all.

### Step 5 - the traversal

**Read `references/step-5-traversal.md`.**

The traversal runs in rounds. Each round is three moves:

    python SKILL/scripts/traverse.py next   --analysis "ANALYSIS"
    (the intelligence reads the statement and establishes its links)
    python SKILL/scripts/traverse.py record --analysis "ANALYSIS" --id N --inputs "1,2" --outputs "5,7"

Ask the program which statement comes next; never choose it yourself. The
program enforces this: record accepts only the id the last `next` handed
over, and refuses everything else. It holds the path, the pending queue and
the entry points; the intelligence cannot keep those in its head across a
thousand rounds, and one confused step ruins the whole result.

Establish two things only: which ids send information into this statement and
which ids it sends information to. If no link can be established, the statement
is unresolved, not unused. An invented link is worse than a missing one, because
it brings dead code back to life and nobody afterwards understands why.

The rounds repeat until the program answers `TRAVERSAL STOPS`. After step 4 that
answer can come on the very first round, because the machine has already reached
every entry point. That is not the end of the analysis: it is the point where
step 6 takes over everything the machine never looked at.

    python SKILL/scripts/traverse.py report --analysis "ANALYSIS"

### Step 6 - the review of the unresolved statements

**Read `references/step-6-review.md`.**

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

**This step also carries everything step 4 could not look at** - the whole of
the style sheets first of all. One command hands them over:

    python SKILL/scripts/review.py sweep --analysis "ANALYSIS"

It marks every statement the machine never examined - unsupported files and
parsed-but-never-linked statements - as unresolved, so the rounds of this
step take them up one by one. Statements the machine linked but did not
reach are not swept by default: when the graph resolves the project's calls,
execution provably does not lead to them, and the final list is exactly the
check they get. When the intelligence establishes from the real source code
that the graph does not resolve the ways this project calls its own code,
`sweep --unreached` hands those statements to the review as well, and the
review divides them the ordinary way.

For the style sheets a finder does the searching:

    python SKILL/scripts/style_links.py find --analysis "ANALYSIS"

It writes `style-candidates.tsv`: for every open style statement, every place
in the snapshot that names it - searched by the whole name AND by its joined
beginnings, on the identifier boundaries of the style language, with the
definition's own span excluded rather than its whole file. Its rows are
evidence for the review, never decisions; a statement with nothing found
says so explicitly, and that is a reason to look closer, not a verdict.

When a resolve opens new work, only the OUTPUTS go into the pending queue -
the direction the information flows. The inputs are recorded but never
queued: walking backwards along them is how a dead caller of a living
statement would be visited and declared alive.

Three traps turn a live statement into a seemingly dead one: a name
assembled while the program runs, a rule used inside its own file, and a file
name in an import mistaken for a class name. The finder above exists because
each of them has cost a real mistake.

    python SKILL/scripts/review.py finish --analysis "ANALYSIS"

### The rounds after step 6

Step 6 fills a new pending queue. Do not start walking it before the step is
finished.

Once it is, run the traversal again. It walks the new queue and the reopened
statements. Steps 5 and 6 alternate until not a single unresolved statement is
left.

The review stops only when the two kinds are all that remain. If one statement
has to be looked at twenty times, look at it twenty times.

### Step 7 - the list to be checked in the live code

**Read `references/step-7-final-list.md`.**

    python SKILL/scripts/final_list.py build --analysis "ANALYSIS" --project "PROJECT"

This is what the whole work was for. The program writes the list of every
statement that has to be checked, each with its file, its lines, the links the
analysis established and its code from the verified snapshot, with a drift
note for the live file.

It refuses until everything is proved at once: the snapshot matches its
manifest sum for sum, nothing was left unsplit, the entries are valid and
all visited, the machine - when it ran - finished both fill and walk, the
traversal holds no open round and no queue, the reading of step 2 reached
the end, not one statement is unresolved, every never-examined statement
passed the review, and the columns agree with the links table. The code in
the list comes from the verified snapshot; the live files are only compared
against it, and every drifted one is named.

Checking the statements on that list, in the live code, is the last step and it
is not optional.

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

The second kind is not a list of things to delete. It is a list of things to
check in the live code, one by one, before anything is touched.

---

## Forbidden

- Modifying the project. The project is only read.
- Executing or building the project.
- Working before both questions of step 1 have been answered.
- Building the graph of step 4 over anything but the copy in the analysis
  directory.
- Selecting which kinds of link to export in step 4.
- Treating an empty record after step 4 as a verdict of not needed.
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
