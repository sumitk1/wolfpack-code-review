# Wolfpack mode: doc-review

Adversarially validates a design doc, plan, RFC, runbook, or set of docs.
Checks correctness, completeness, unstated assumptions, and security posture —
whatever an independent senior reviewer would flag.

## Ingestion
1. Read all provided doc files in full (`.md`, `.txt`, `.rst`; convert
   `.docx`/`.pdf` to text first).
2. If multiple files, concatenate with `=== FILE: <name> ===` separators into
   the packet.
3. No size gates needed (docs rarely exceed context). Count words for panel sizing.

## Panel size (by word count)
| Words | Reviewers | Skeptics |
|---|---|---|
| < 300 | 5 | 3 |
| 300–3,000 | 7 (default) | 3 |
| > 3,000 | scope to sections or split | 3 |

## Lenses (doc-flavored)
Reuse the `contracts.md` lenses but read them for prose, not code:
- correctness → factual errors, logical flaws, unsupported claims, internal contradictions.
- completeness → gaps, missing edge cases, unresolved threads, unaddressed requirements.
- security → unsafe assumptions, trust-boundary issues, data-exposure risks described.
- lifecycle → operability/rollout/rollback realism of the plan.
- a "free-form senior reviewer" pass (map to anti-pattern lens) → whatever stands out.
`location` = section/heading/paragraph (e.g. `Section: "Auth Flow"`), or `N/A`.

## Adversarial phase
Skeptics receive the FULL document (docs are small). Invalid-refutation guard
applies: a "not in the document" REJECT is only valid if the skeptic actually
read the doc.

## Output format → `<source>.review.md` alongside the source
```markdown
# Wolfpack Doc Review: <filename>
_Panel: N reviewers across M Claude models + 3 skeptics (adversarial pass). Mode: doc-review._

## Executive Summary
<overall quality, most critical findings, priority actions before proceeding>

## Findings (Critical → High → Medium → Low)
### <title>
**Lens**: <lens> | **Severity**: <sev>
<description referencing the section/claim> — **Recommendation:** <fix>
```

### Severity
| Severity | Criteria |
|---|---|
| Critical | blocks the plan; load-bearing factual error; exploitable assumption |
| High | significant gap/risk; material problems if unaddressed |
| Medium | noteworthy gap; degrades quality/reliability |
| Low | minor omission/polish |

The panel schemas only carry HIGH/MEDIUM/LOW; **Critical is assigned by the
orchestrator at Stage 4** by promoting the HIGHs that meet the criteria above.
