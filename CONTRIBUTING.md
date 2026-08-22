# Contributing to SPIDER

Thank you for helping make dead-code investigations more reliable. SPIDER favours small, evidence-backed changes over broad rewrites.

## Before opening a change

- Use the issue templates for bugs, false-positive cases and feature requests.
- Remove private code and credentials from every reproduction.
- For a classification problem, include the smallest source example that preserves the causal relationship.
- Explain which written definition or invariant produced the unexpected result.

## Local checks

SPIDER requires Python 3 and Node.js. From the repository root:

```bash
npm ci
python evals/run_evals.py --self-test
```

The self-test must finish with zero failures. If a change touches Joern export or graph translation, also run the real boundary suite described in [`evals/README.md`](evals/README.md).

## Pull requests

A focused pull request should include:

1. the problem and the smallest reproducer;
2. the definition or invariant affected;
3. the implementation;
4. a regression test or a reason one cannot be added;
5. any user-facing documentation change.

Do not weaken refusal checks merely to make a run complete. A named refusal is safer than a confident but unsupported finding.

## Scope decisions

The current unit of analysis is the top-level statement, and the project being analysed remains read-only. Proposals that change either property need an explicit design discussion before implementation.

## Conduct and security

Participation is governed by [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md). Report vulnerabilities exactly as described in [`SECURITY.md`](SECURITY.md).
