# SPIDER - step 4: the machine links

Read this file before you begin step 4.

---

## 1. What it works on

The copy of the application code in the analysis directory, the statement list
and the database - all of them in the analysis directory.

The project itself is not touched. The graph is built over the copy, because the
addresses in the statement list point at the copy: the same file, the same line
numbers, no translation in between.

---

## 2. Why this step exists

The traversal is carried out by the intelligence, one statement at a time. On a
project of ten thousand statements that is thousands of readings.

A code property graph is repeatable: the same input gives the same output, for
anybody. Whatever the machine has already established does not have to be
established again by hand. This step lets the machine fill in what it can prove,
so that the intelligence works on what is left.

The method does not change. The machine records links; it decides nothing.

**Execution arrives at a statement in two ways, and this step proves both.**

1. **By being called.** Something living executes it. The code property graph
   proves this, as far as it can resolve the project's calls.
2. **By its file being loaded.** The unit of measurement of the whole method
   is the top-level statement, and a top-level statement runs exactly when its
   file is loaded. Loading is not a call. No call graph can express it.

Version 2.1 had only the first. On a real project of 7965 statements its walk
explained 54% of the living code and 60% of the loaded files; the remaining
1904 statements went into the final list as though execution provably never
reached them, when in truth the machine had simply not been given the means to
see the way in. `load_links.py` gives it those means, from the snapshot alone -
no graph tool, no Java, no network.

---

## 3. Terms

**Code property graph** - one graph holding the structure of the code, the order
of execution and the movement of data at the same time.

**Link kind** - what a link joins. A graph holds many kinds: who calls whom,
which name points at which definition, which file imports which, which value
reaches where, what stands inside what.

**Export** - a file in which every line is one link of the graph, written as
kind, from file, from line, to file, to line.

**Machine directory** - `machine` inside the analysis directory. The exports and
the graphs live there and nowhere else.

---

## 4. What this step cannot do

**The graph does not read style sheets.** Not one. No engine of this kind builds
a graph of files that carry only appearance. The load graph reaches a sheet's
own at-rules, because loading a sheet runs them, and it deliberately stops
there: an ordinary rule becomes available when its sheet loads, and being
available is not being needed. A rule is needed when the markup names it, and
that is step 6's work.

**An empty record after this step does not mean "not needed". It means "not
looked at".** A statement the machine never read is not evidence of anything.
Step 6 settles those against the real source code.

**And `unreached` means "I found no way in", not "there is none".** How much
that is worth depends on what this step was given. The walk therefore measures
its own coverage - files reached against files something loads - and names the
files that are loaded and still never walked. When the load graph was not
filled it says so, and step 7 refuses to write the list at all.

An analysis that skips step 6 because the numbers look complete will delete live
code. This is the one mistake this step can cause, and it is the reason the
sentences above stand here.

---

## 5. Preparing the tool

Two things are needed, both outside this skill.

**Java, release 17 or newer.** On Windows:

    winget install Microsoft.OpenJDK.21

On Debian or Ubuntu:

    sudo apt-get install openjdk-21-jdk

On macOS with Homebrew:

    brew install openjdk@21

**Joern.** Downloaded from its own releases at `github.com/joernio/joern` and
unpacked outside the project and outside the analysis directory. The unpacked
tree carries `joern-cli`, and inside it the programs used here: `pysrc2cpg`,
`jssrc2cpg`, `javasrc2cpg`, `c2cpg` and `joern` itself.

Check that both are there before anything else:

    java -version
    JOERN/joern-cli/joern --help

If either refuses, this step does not begin. Steps 5 and 6 work without it - the
traversal then starts from an empty database, as it did before this step
existed.

---

## 6. Three traps in the tool

**A path that is not plain ASCII breaks it.** Joern receives the arguments
through the Java runtime and a directory named in another alphabet arrives as
question marks. On Windows the short name of the directory gets round it:

    (New-Object -ComObject Scripting.FileSystemObject).GetFolder("PATH").ShortPath

On other systems the analysis directory is given an ASCII name from the start.

**It writes a working copy of every graph into the current directory.** Run it
from a directory of your own, never from inside the project or a repository, or
it leaves a folder of its own behind.

**It reports what it could not resolve while it builds.** Lines about a name with
many definitions are not errors: they are the places the machine is unsure
about. It writes no link for them, which is what it is supposed to do.

---

## 7. Order of execution

### Move 0. The load graph

    python SKILL/scripts/load_links.py derive --analysis "ANALYSIS"

It reads the statement list and the snapshot, works out which file loads which,
and writes `load-links.tsv`. It needs nothing else - no graph tool, no Java. A
project where the graph tool cannot be installed still gets this half of the
proof, and on a project whose calls the graph cannot resolve it is the half
that carries the run.

What it cannot resolve, it names: a module whose name matches two files of the
snapshot is reported as ambiguous and no link is written for it. When a project
writes its imports through an alias the build tool knows - `@/lib/x` for
`frontend/lib/x` - the program first tries every top directory of the snapshot,
and `machine/aliases.txt` states the mapping outright when that is not enough:

    @/<TAB>frontend/

### Move 1. The machine directory

    mkdir ANALYSIS/machine

Every graph and every export lives there.

### Move 2. Building the graphs

One graph per language, over the copy in the analysis directory. Which frontend
to use follows from what the project holds:

    JOERN/joern-cli/pysrc2cpg  ANALYSIS/source            -o ANALYSIS/machine/python.cpg.bin
    JOERN/joern-cli/jssrc2cpg  ANALYSIS/source/frontend   -o ANALYSIS/machine/front.cpg.bin

A frontend built from a directory of its own is given the piece of the path that
makes its addresses whole again. That goes into `ANALYSIS/machine/prefixes.txt`,
one line per graph, the graph name and the prefix separated by a tab:

    front<TAB>frontend/

A graph built over the whole copy needs no line there.

### Move 3. Exporting every link

For every graph, with the two environment variables set:

    SPIDER_CPG=ANALYSIS/machine/python.cpg.bin
    SPIDER_OUT=ANALYSIS/machine/edges-python.tsv
    JOERN/joern-cli/joern --script SKILL/scripts/joern_export.sc

Every export has to be named `edges-NAME.tsv`, where NAME is the same name used
in `prefixes.txt`.

Every kind of link is exported. Nothing is selected and nothing is left out at
this point: what a link is worth is decided against the statement list, not
against an opinion about the kind.

### Move 4. Merging and translating

    python SKILL/scripts/machine_links.py merge --analysis "ANALYSIS"

The program merges every export into `all-links.tsv`, translates both ends of
every link into statement ids and writes the CAUSAL links into
`links-by-id.tsv`, in the one stored direction: source needs target, with
`REACHING_DEF` flipped because the graph exports it the other way. The
structural kinds stay in the merged file and go no further - the contract of
every kind is `link-kinds.md`. A malformed export line or a byte that is not
UTF-8 is a named error, never a silent skip.

### Move 5. Filling the database

    python SKILL/scripts/machine_links.py fill --analysis "ANALYSIS"

Both producers land together: `links-by-id.tsv` from the graph and
`load-links.tsv` from the load graph. Either may be missing - a run without a
graph tool has only the second, a project with no import anywhere has only the
first - but a fill with neither is refused, because it would be filling
nothing. A kind outside the contract of `link-kinds.md` is refused by name.

The causal links enter the `links` table and the two columns of every touched
record are DERIVED from it. **No visited mark is set.** A link alone proves
nothing about reachability; a database that already holds machine links is
refused - `reset --confirm` first.

### Move 6. The walk

    python SKILL/scripts/machine_links.py walk --analysis "ANALYSIS"

The walk starts at the entry points and follows the needs-links. What it
reaches is marked visited, by the machine, as `reached` - and that is the only
mark the machine ever sets. Everything else receives its honest machine state:
`unreached` (linked, but no way in was found), `untouched` (parsed, no link),
`unsupported` (a file the graph cannot read). An isolated nest of dead code -
dead calling dead - has links and stays unvisited.

**The walk then measures itself.** It reports how many files it reached
against how many files something loads, and it names the files that are loaded
and still never walked - each of those is either dead in its whole, or reached
in a way this machine cannot see. When no load graph was filled it says so in
plain words, and step 7 refuses to write the list on that basis. The numbers go
into the `meta` table so the refusal stands on a record, not on a memory.

To run the machine part again: `reset --confirm` removes the machine links and
marks in one transaction and touches nothing the review wrote.

### Move 7. Report

The numbers come from the database and the files, never from memory: how many
statements are filled, how many are left empty, how the empty ones split by
kind of file, and what share of the loaded files the walk explained. The style
sheets will be the largest part of the empty ones, and that is expected.

---

## 8. What comes after

The traversal of step 5 starts from the entry points that are still unvisited
and walks whatever the machine did not reach; after the walk it may stop on its
first round, and that is not the end of the analysis. Then `review.py sweep`
hands every statement the machine never examined to step 6, which settles each
of them against the real source code.

Neither step is skipped because this one filled a lot in.

---

## 9. Who decides what

| Who | What it decides |
| --- | --- |
| The machine | which links it can prove from the code |
| The programs | the merge, the translation into ids, the counting, the records |
| The intelligence | which files are analysed, which graph frontends are used, and every statement the machine left empty |

The machine never guesses. Where it is unsure it writes no link, and the
statement stays empty for step 6.

---

## 10. Forbidden

- Modifying the project.
- Building the graph over anything but the copy in the analysis directory.
- Selecting which kinds of link to export.
- Filling a database that already holds machine links.
- Setting a visited mark anywhere but in the walk, or on anything the walk
  did not reach.
- Carrying a structural kind into the database.
- Treating an empty record after this step as a verdict of not needed.
- Reporting the work finished after this step. It is the beginning of the
  analysis, not the end.
- A number in the report written from memory.
