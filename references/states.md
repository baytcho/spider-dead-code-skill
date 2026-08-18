# SPIDER - the states of a statement

Read this before writing any code that touches the database. Every test of the
machinery checks transitions of this model, not incidents.

---

## 1. Why two axes

One mark with an author still loses information: a statement can be reached by
the machine AND reviewed by a person, and the two facts answer two different
questions. So every statement carries two independent axes, and the final
category is DERIVED from them - it is never stored as a third mark that could
disagree with the first two.

---

## 2. The machine axis - `machine_state`

Set only by `machine_links.py walk`, in one transaction, from the entry points
along the proven causal links.

| Value | Meaning |
| --- | --- |
| (empty) | the machine never ran over this base |
| `reached` | the walk arrived here from an entry point; `visited=1`, `visited_by='machine'` |
| `unreached` | the statement has proven links, but no path from any entry leads to it |
| `untouched` | the graph parsed its file and found no link touching it |
| `unsupported` | its file is one the graph cannot read at all - style sheets first of all |

`unreached` is the machine's honest **"I found no way in"**. How much that is
worth depends on what the machine was given. With the load graph filled it
covers both ways execution arrives - the call and the loading - and unreached
is a real finding. Without it only calls were walked, and a call graph cannot
express that loading a file runs its top-level statements; unreached then
means blindness, not absence. Version 2.1 called it "execution provably does
not lead here" in every case, and in a real project that turned 1904 live
statements into candidates. The walk now measures its own coverage and step 7
refuses to write the list when the load graph never ran.

`untouched` and `unsupported` are the machine's honest "I never looked" - and
they are NOT the same thing as unreached. Treating them the same deletes live
code.

---

## 3. The review axis - `reviewed` and `unresolved`

Set only by the review of step 6, each decision leaning on a written entry in
`review.md`.

| State | Meaning |
| --- | --- |
| `unresolved=1` | the case is open: handed to the review and not settled yet |
| `reviewed=1` | a decision with recorded evidence exists for this statement |
| neither | the review never touched it |

`review.py sweep` opens a case (`unresolved=1`) for every statement the
machine never looked at. `resolve` closes it as understood: the links are
recorded, `visited=1`, `visited_by='intelligence'`, `reviewed=1`. `reopen`
closes it the other way: `visited` falls, `reviewed=1` stays, and the
statement goes where the decision put it - the entry list, the queue, or
nowhere.

---

## 4. The links, and where the columns come from

Every proven link lives in the `links` table as `source NEEDS target`, with
its kind and its origin (`machine` or `intelligence`). The two columns of the
owner's record - which ids send information in, which ids it sends to - are
DERIVED from that table, by the sender rules of `link-kinds.md`. They are
never written twice, so the two sides of a link cannot disagree.

---

## 5. The derived final category

Computed, never stored:

| Condition | Category |
| --- | --- |
| `visited=1` | first kind - the program uses it (proven by walk, traversal or review) |
| `visited` empty, examined | second kind - a candidate for the check in the live code |
| `visited` empty, never examined | NOT a category - the work is not finished |

"Examined" means: `machine_state='unreached'` (the machine, having been given
both the calls and the loading, found no way in), or `reviewed=1` (a person
settled it). A statement that is neither cannot appear in the final list; step
7 refuses while one exists - and it refuses the whole list when the walk had
no load graph, because then `unreached` was never an examination at all.

---

## 6. The allowed transitions

    (empty record)
        -> machine walk:    visited=1 + machine_state=reached      [machine]
        -> machine walk:    machine_state=unreached/untouched/unsupported
        -> traversal record: visited=1 (+unresolved when stated so) [intelligence]
        -> sweep:           unresolved=1                           [program, by rule]
    unresolved=1
        -> resolve:         visited=1, reviewed=1, unresolved falls
        -> reopen entry:    visited falls, reviewed=1, id into the entry list
        -> reopen queue:    visited falls, reviewed=1, id into the queue
        -> reopen none:     visited falls, reviewed=1, placed nowhere
    visited=1
        -> (nothing; a visited statement is never recorded twice)
    machine anything
        -> reset --confirm: every machine mark and link falls; the review stays

No other transition exists. A program that needs another one is wrong.
