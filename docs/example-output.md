# Example output

This example is condensed from the repository's deterministic evaluation fixture. The fixture contains 17 top-level statements across TypeScript, TSX and CSS and deliberately includes dynamic style names, an unimported stylesheet and an uncalled exported function.

## Summary

| Result | Count |
| --- | ---: |
| Statements in the project | 17 |
| Proven or established as used | 13 |
| Candidates to check | 4 |
| Unresolved at completion | 0 |

## Candidate checklist

| Id | Source | Why it remains on the list |
| ---: | --- | --- |
| 8 | `app/page.module.css:14-16` — `.orphan` | The selector name appears nowhere in the project snapshot. |
| 13 | `app/unused.module.css:1-3` — `.wrapper` | Nothing imports the stylesheet. |
| 14 | `app/unused.module.css:5-7` — `.wrapper span` | Nothing imports the stylesheet. |
| 17 | `lib/helpers.ts:5-7` — `neverCalled` | No reached statement calls the function. |

## One candidate in the final report

```markdown
## Statement 17

| | |
| --- | --- |
| File | `lib/helpers.ts` |
| Lines | 5 to 7 (3 lines) |
| Ids that send in | none |
| Ids it sends to | none |
| Machine state | unreached |
| Live file | same |

**The code, from the verified snapshot:**

    5 | export function neverCalled(name: string) {
    6 |   return name.toLowerCase();
    7 | }
```

The full generated report also records whether a human review occurred and warns when the live file changed or disappeared after the snapshot. It deliberately says **candidate**: the code must still be inspected in the live project before any edit.

## A dynamic case that stays alive

The fixture uses `styles[state]`, where `state` can be `pending` or `done`. A literal-name search alone cannot establish that relationship. SPIDER marks the statement unresolved, reviews the values against the source, then reaches both `.pending` and `.done`. They do not appear in the candidate list.

The full answer key and its reasons are in [`evals/expected.json`](../evals/expected.json) and [`evals/README.md`](../evals/README.md).
