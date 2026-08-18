# SPIDER

**SPIDER cleans machine-written code of everything it does not need.**

**If you build products with AI coding agents, running it is not optional — it is hygiene.**

Because an agent writes fast, but it does not clean up after itself. It rewrites a function — the old one stays. It builds a new screen — the previous one remains. And the next day it reads your project, takes the old code for the living one, and builds on top of it: using the old, blind to the new. With every session the sediment grows, the build gets heavier, real bugs hide under the dead weight — and the agent you pay learns from its own garbage.

SPIDER does not guess — it proves. It cuts the project into individual statements, starts from the doors through which the outside world enters the program, and walks every path execution can possibly take. Everything no path reaches lands in one file: the place, the code, the evidence. Nothing is deleted for you — the last word belongs to your eyes.

One instrument for the whole project — backend, frontend, styles, shell. It never executes your code. It leaves a verifiable trail from end to end.

**Writing with AI? Then SPIDER is not a wish — it is hygiene.**

---

## How it works

Seven steps, each standing on the one before it:

1. **Snapshot and split.** Your source is copied and cut into addressable top-level statements — the analysis never touches or executes the project itself.
2. **Entry points.** Every door the outside world can knock on: a command line, a framework reading data out of the code, a bundler directive, the public surface of a package.
3. **The record.** One database row per statement; everything later steps establish is written down.
4. **The machine proves what it can.** Three graphs — the calls (via [Joern](https://github.com/joernio/joern)), the loading, and the names — walk reachability from the entries. Only a proven path marks a statement alive. The machine reads the wiring that breaks other tools: barrel re-exports, emulated namespaces, function overloads, self-registering modules, the published surface of a library.
5. **The traversal.** The intelligence walks whatever the machine could not, one statement at a time, under an enforced protocol.
6. **The review.** Everything never examined — style sheets first of all — is settled against the real source, with written evidence per decision.
7. **The final list.** One file: every statement nothing reaches, with its address, its code, its links, and a drift note against the live project. It is a list of places to check — never a delete script.

The result has two kinds of statements and no third: proven needed, or handed to your eyes with the reason nothing reaches it.

## What it reads

Python · TypeScript · JavaScript · CSS · shell — one cause-and-effect graph across the whole stack.

## What you need

- Python 3
- Node.js with `typescript@5` (only for TS/JS projects; pinned by the lockfile, installed inside the tool's own directory)
- Java 17+ and [Joern](https://github.com/joernio/joern) (only for step 4's call graph; the loading and name graphs need nothing but the snapshot)

## Where to start

Read [`SKILL.md`](SKILL.md) — it is the course of the work, and it is written to be followed step by step. Every step has its own reference under [`references/`](references/). The whole machinery is covered by the evaluation suite:

```bash
python evals/run_evals.py --self-test
```

## What SPIDER will not do

- It will not execute, build, or modify the analysed project.
- It will not delete anything, anywhere, ever.
- It will not hand you a verdict. It hands you evidence.

Dead code does not pay rent. Evict it — with proof.

## License

See [LICENSE](LICENSE).
