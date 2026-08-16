# SPIDER evaluations

These tests exist because the most expensive mistake in this work is a confident
one: a classification reasoned from outside knowledge instead of from the
definitions in SKILL.md. Text alone cannot prevent that. A fixed answer key can
catch it.

The folder is not part of the packaged skill. It lives in the repository, for
development.

## What is here

    evals/
      project/        a small project with every trap the skill has to survive
      expected.json   the answer key
      run_evals.py    the runner
      README.md       this file

## How to run

Check that the programs themselves behave exactly as the skill describes:

    python evals/run_evals.py --self-test

Check a real run made by an intelligence over `evals/project`:

    python evals/run_evals.py --check <analysis directory>

Exit code 0 means every check passed.

## The answer key, and where each answer comes from

Every expectation below follows from a definition written in SKILL.md. None of
them is a new rule.

### The project splits into 17 statements

Six style rules, two TypeScript statements, nine TSX statements. If the count
moves, either the project changed or the splitter did.

### The entry points are exactly 3, 4, 9 and 12

| Id | What it is | The definition it comes from |
| --- | --- | --- |
| 3 | `export const metadata` | the framework reads it as data, and the framework is outside the application code |
| 4 | `export default RootLayout` | the framework loads the file and calls it |
| 9 | `'use client'` | the bundler reads the directive |
| 12 | `export default Page` | the framework loads the file and calls it |

**No style rule is an entry point.** A style rule is reached through the
statement that brings the stylesheet in. A run that declares the six style rules
entry points fails this check, and it fails it before any conclusion is drawn.

### Statement 12 is unresolved on the first visit

It carries `styles[state]` - a name assembled at runtime. The definition is
unconditional: such a statement is never declared unused; it is marked
unresolved. That is what step 5 exists for.

Once the real code is read, the values the name can take are written in the same
file: `done` and `pending`. So the review resolves it and the two rules become
reachable.

### Four statements stay unvisited at the end

| Id | What it is | Why nothing reaches it |
| --- | --- | --- |
| 8 | `.orphan` | the name appears nowhere in the code |
| 13 | `.wrapper` | `unused.module.css` is imported by nobody |
| 14 | `.wrapper span` | the same |
| 17 | `neverCalled` | the function is called nowhere |

These four are the result the skill exists to produce. Each of them is a
searchable fact, not a judgement.

### Nothing is left unresolved

The work is finished only when no statement carries the unresolved mark, nothing
was reopened in the last pass, the pending queue is empty and every entry point
has been visited.

## The traps this project carries on purpose

- a name assembled at runtime, which no literal search finds;
- a style rule that exists and is named nowhere;
- a whole stylesheet that nobody imports;
- an exported function that nobody calls;
- a directive that the bundler reads;
- data that the framework reads instead of code that somebody calls.

Every one of them has burned a real analysis at least once.
