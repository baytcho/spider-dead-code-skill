# SPIDER - the contract of the link kinds

Read this before touching `machine_links.py`. Every kind allowed into the
database is defined here completely: its name in the graph, the direction the
graph exports, the direction SPIDER stores, why reachability may travel along
it, and the test that holds it. A kind not in this table never enters the
database - it stays in the merged file for anyone to inspect.

---

## 1. The one direction SPIDER stores

Every link in the `links` table means: **source NEEDS target**. The statement
that depends stands first, the statement it depends on stands second.

Reachability travels only that way: from a living statement to what it needs.
The reverse - "what I need is used, so I am used" - is exactly how a dead
caller of a living function would come back to life, and it is forbidden on
every kind.

---

## 2. The causal kinds

| Kind | Producer exports | Flip | Stored as | Why reachability travels | Held by |
| --- | --- | --- | --- | --- | --- |
| `CALL` | call site -> callee | no | caller NEEDS callee | a living caller executes its callee | synthetic suite; real-graph suite |
| `REF` | user -> definition | no | user NEEDS definition | a living user needs the definition of the name it uses; it may land ONLY on a statement that defines a name (`defined-names.tsv`, written by the name graph) - the graph wires file-scope variables to the file node, whose address is line one, and that wiring is not a definition | synthetic suite |
| `IS_CALL_FOR_IMPORT` | importer -> imported | no | importer NEEDS imported | a living importer needs what it imports | synthetic suite |
| `LOADS` | loader -> loaded statement | no | loader NEEDS loaded statement | a statement that acts by the very act of loading runs exactly when its file is loaded, and the loading statement is what loads it | load-graph suite |
| `USES` | user -> definition | no | user NEEDS definition | a living statement writes a name; the statement that defines that name is needed by it | name-graph suite |

The sender side, for deriving the owner's two columns (the sender's outputs
gain the receiver; the receiver's inputs gain the sender):

| Kind | Sender | Because |
| --- | --- | --- |
| `CALL` | the caller | it sends its arguments into the callee |
| `REF` | the definition | it sends its value to the user |
| `IS_CALL_FOR_IMPORT` | the imported side | it sends the name to the importer |
| `LOADS` | the loader | it sends control into the statement that loading runs |
| `USES` | the definition | it sends its value to the statement that writes its name |

`LOADS` and `USES` are the two kinds not produced by the graph tool.
`load_links.py` derives the first and `name_links.py` the second from the
snapshot, so a project with no graph tool at all still has both halves of
reaching proved.

**What `LOADS` points at.** Loading a file proves only the statements that act
by the very act of loading: top-level calls and control flow, `from __future__`
imports, bare imports performed for their effect. A definition, a constant, an
import that only brings a name in - these become *available* when the file
loads, and being available is not being needed; they are needed only when a
living statement writes their name, which is exactly the `USES` link. Its two
producers:

- **an import**: the importing statement -> the loaded file's statements that
  act by loading;
- **an entry point**: the entry point -> the statements of its own file that
  act by loading, because a framework that reached the entry point had loaded
  the file to get there.

**The style sheet side of the same asymmetry.** A loaded style sheet runs only
the at-rules that pull in further sheets and the rules that name no class and
no id - those act by presence. A rule addressed to a class or an id becomes
available, and it is needed only where every name of its selector is written
by something alive. Without this asymmetry every rule of every loaded sheet
would count as reached and no dead style rule could ever be found.

Links stated by the intelligence carry kind `STATED`, origin `intelligence`,
and their sender is always the source - the intelligence states them directly
in the owner's own terms.

---

## 3. The structural kinds

`AST`, `CONTAINS`, `CFG`, `DOMINATE`, `POST_DOMINATE`, `CDG`, `ARGUMENT`,
`EVAL_TYPE`, `RECEIVER`, `CAPTURE`, `SOURCE_FILE`, `PARAMETER_LINK`,
`INHERITS_FROM`, `BINDS`, `TAGGED_BY`, `IMPORTS`, `REACHING_DEF`, the bodies
of conditions and loops, and anything else a graph release may add: structure
and order, not need.

**`REACHING_DEF` stands here, and that is a decision, not an omission.** It
was causal up to version 2.2. Between two TOP-LEVEL statements of one file the
graph's data-flow edge degenerates into the wiring of the module body: the
docstring, every import and every definition chain into one web, and a name
nobody uses is dragged alive by its neighbours - the neighbour trap that
ruined the first analysis, machine edition. Real data dependency between
top-level statements always writes the used name, and the name graph records
exactly that as `USES`. At this granularity `REACHING_DEF` adds no need of its
own, only neighbourhood.

They stay in `all-links.tsv`, translated and countable, and are never written
into the database. Reachability along "what stands inside what" or "what is
executed after what" is not reachability of need, and mixing the two is the
defect this contract exists to prevent.

---

## 4. Adding a kind

A new kind enters this table only with all five columns filled and a test in
the synthetic suite proving its direction. A kind added without its test is a
guess wearing a uniform.
