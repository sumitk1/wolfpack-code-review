# Wolfpack mode: code-audit

Audits a whole codebase / directory (not a diff) for quality, correctness,
security, completeness, and anti-patterns. Use when the input is a directory or
a set of source files.

## Ingestion
1. Collect files under the target path, excluding `node_modules/`, `.git/`,
   `dist/`, `build/`, `target/`, `.next/`, `__pycache__/`, binaries, lockfiles,
   and anything matched by `.gitignore`.
2. Count total characters. Size gates:
   - < 200k: pass full contents to reviewers via the packet.
   - 200k–500k: warn "large codebase — slower run", continue; packet carries a
     manifest + the hot files, reviewers read the rest from the checkout.
   - > 500k: warn and ask the user to narrow scope first.
3. Build a file manifest (`FILE: path (N lines)` blocks) into the packet.

## Panel size (by file count)
| Files | Reviewers | Skeptics |
|---|---|---|
| < 5 | 6 | 3 |
| 5–20 | 7–9 (default) | 3 |
| 20–50 | 9 + extra correctness/security | 3 |
| > 50 | scope down or audit per-package | 3 |

## Lenses
Use the full set from `contracts.md`. Emphasis: quality, correctness, security,
completeness, anti-pattern. The lifecycle/domain lenses apply if the code
manages infra or state. Every finding's `location` MUST be `path:line`.

## Adversarial phase
Point each skeptic ONLY at the file(s) named in the findings they are ruling on
(list the paths in the skeptic prompt) — not the whole codebase. The
invalid-refutation guard still applies.

## Output format → `<scratchpad>/wolf/out/audit.md` (unique-suffix if exists)
```markdown
# Wolfpack Code Audit: <path>
_Panel: N reviewers across M Claude models + 3 skeptics (adversarial pass). Mode: code-audit._

## Executive Summary
<overall quality, top risks, patterns across reviewers, priority actions>

## Issues by Severity
### High
#### `file:line` — <title>
<description> — **Fix:** <concrete>
### Medium / Low ...

## File Index
| File | High | Medium | Low | Total |
```
Sort within a severity by signal_strength desc.
