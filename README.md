# SPIDER

**An agent skill that finds the code your project does not need - and proves it.**

A spider walks its web thread by thread. So does this skill: it splits your whole
codebase into individual statements, starts at the entry points, and follows the
links. Whatever the execution reaches is alive. Whatever it never reaches is not
needed.

No guessing. No confidence percentages. No "probably safe to delete".

---

## What makes it different

### It works one statement at a time

Every other tool in this space works in coarse units - a whole file, a whole
export, a whole function. SPIDER gives **every top-level statement its own id and
its exact address**: file, first line, last line.

That is why it can tell you that three rules inside a stylesheet are alive and
the fourth one is dead, instead of shrugging at the file as a whole.

### One model across several languages

Python, TypeScript, JavaScript and CSS end up in **one list, measured by one
rule**. A style rule and a Python statement sit side by side and are traced the
same way.

Existing tools are single-language: one for JavaScript, one for Python, one for
CSS. You run three of them and then merge the answers by hand - and the moment a
TypeScript file uses a CSS class, no single tool sees both ends of the link.

### The intelligence reads. The program remembers.

The two halves of the work are cleanly split, and neither can do the other's job:

| The intelligence | The program |
| --- | --- |
| reads each statement and establishes its links | says which statement comes next |
| decides whether a statement is understood | keeps the path and the pending queue |
| proves a case against the real source code | computes the marks and the counts |

**The program decides nothing about the meaning of the code. The intelligence
keeps nothing in its head.** Across a thousand rounds, that is the difference
between a result you can defend and a result you hope is right.

### It is allowed to say "I do not understand this"

This is the part that matters most.

A static tool has two answers: used or unused. When it cannot see a link it has
to pick one - and it picks wrong. Tools that guess give you confidence
percentages. Tools that do not guess delete your live code and then ask you to
maintain a hand-written exception list.

SPIDER has a third state during the work: **unresolved**. A statement whose links
cannot be established is not declared dead. It is set aside and reviewed against
the real source code, one by one, until it is understood - twenty times over if
that is what it takes.

**A name assembled at runtime is never declared unused.** `styles[status]`,
`getattr(obj, name)`, a class built by string concatenation - no literal search
finds these, and that is exactly where careless tools destroy working code.
SPIDER marks them unresolved by rule, not by luck.

### The result is two kinds. There is no third.

- **First kind** - visited and working in the program. The program needs it.
- **Second kind** - never visited. The program does not need it.

Nothing is left in between, and the work is not reported as finished while a
single statement is still unresolved.

### Every step is written down and checkable

The whole analysis lives in a database and a set of plain files: which statement
sends information to which, which were visited, which were set aside, and what
was proved about each one. **Anyone can open the record afterwards and check the
reasoning** - including you, six months later.

### It ships with an answer key

Text alone cannot stop an agent from reasoning its way into a wrong
classification. A fixed answer key can.

`evals/` holds a small project carrying six deliberate traps, and the correct
answer for each one written down in advance. Twenty-nine machine checks. Run it
against the programs, or against a real analysis produced by any model:

```bash
python evals/run_evals.py --self-test
python evals/run_evals.py --check <analysis directory>
```

If a model declares every style rule an entry point, the check fails immediately
- before a single conclusion is drawn.

---

## Proven on a real project

858 statements across 66 files of a production Next.js application.

It found **two entire stylesheets, one abandoned screen with its stylesheet, and
nine separate dead rules** - 121 statements that nothing in the running program
ever reaches.

It also found five style rules that a name-based search had wrongly condemned:
the code addressed them through an assembled name. Those five were saved by the
unresolved state.

---

## Installing

**From the packaged release** - download `spider.skill` from the
[Releases](../../releases) page and install it into your agent's skills folder.

**From this repository** - copy the folder into your skills directory:

```bash
git clone https://github.com/baytcho/spider-dead-code-skill.git
cp -r spider-dead-code-skill ~/.claude/skills/spider
```

**Requirements**

- Python 3
- Node.js and `typescript` version 5, only if the project contains
  `.ts .tsx .js .jsx .mjs .cjs` files:

```bash
npm install typescript@5
```

---

## Using it

Ask your agent, in whatever words you like:

> Find the dead code in this project.

The skill asks two questions first - where to put the analysis, and which
directory to analyse - and does nothing until both are answered. It never guesses
a path, and **it never modifies, runs or builds your project**. The project is
only read.

Then it works through five steps:

| Step | What it produces |
| --- | --- |
| 1 | every top-level statement, numbered, with its address |
| 2 | the entry points - where execution enters the system |
| 3 | the database, one empty record per statement |
| 4 | the traversal: the links, filled in statement by statement |
| 5 | the review of everything that was not understood, against the real code |

Steps 4 and 5 alternate until nothing is left unresolved. Then the two kinds are
all that remain.

---

## How it is laid out

```
SKILL.md          the course of the work and every definition it stands on
scripts/          the programs that keep the order and hold the records
references/       the details of each step, read when that step begins
evals/            the test project and the answer key
```

---

## License

MIT. Use it, change it, ship it - keep the copyright line.

Built by [Roumen Baytchev](https://github.com/baytcho).
