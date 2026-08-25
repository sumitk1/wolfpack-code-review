# Wolfpack mode: pr-review (default)

Reviews a pull request (or a diff / branch) — the flagship mode. Scopes strictly
to the change, not the whole repo.

## Ingestion
1. Resolve the PR: `gh pr view <n|url|branch> --json number,headRefOid,baseRefName,title,body,url`
   (prefix `GH_HOST=<host>` on GitHub Enterprise).
2. Give reviewers a checkout whose file lines == diff lines:
   `git worktree add --detach <scratchpad>/wolf/pr<N> <headRefOid>`.
3. Build the review packet (SKILL.md Playbook §3): PR metadata + full diff
   (exclude generated giants — lockfiles, generated schemas — naming them in the
   packet) + **verified experiments** (build/test the change at head NOW; the
   highest-value part) + known/accepted items so the panel doesn't re-raise
   filed issues as discoveries.

## Panel size (by diff size, generated files excluded from the count)
| Changed lines | Reviewers | Skeptics |
|---|---|---|
| < 500 | 7 (lean) | 3 |
| 500–1500 | 9 (full) | 3 |
| > 1500 | 9 + duplicate correctness/security lenses | 3 |

Default lean lens set: correctness, security, domain, lifecycle, quality,
completeness, anti-pattern. Full adds the `-b` cross-checks on the other elite
model. Note: `scripts/wolfpack.js` ships the 7-lens lean panel in all
profiles; for a full panel, push the `correctness-b` / `security-b` entries
(briefs already in its `BRIEFS` map) onto that target's lens list.

## Reviewer content
Point each reviewer at the packet path + the worktree path. They may read/grep
and run read-only shell (`git show`, run the package's tests) to verify.

## Output format → `<scratchpad>/wolf/out/review-<pr>.md`
```markdown
# Wolfpack Review — <repo>#<pr> (<title>)
_Panel: N reviewers across M Claude models + 3 skeptics (adversarial pass). Mode: pr-review._

## Verdict
<2–4 sentences: does it achieve its goal? is anything merge-blocking?>

## High
### H1 — <title>
`file:line` _(signal K/N; skeptics: <verdicts>)_
<rationale + evidence>
**Fix:** <concrete>

## Medium
...

## Low
- **L1** — <title> `file:line` <one line>

## Considered and dismissed (adversarial validation)
- <finding> — REJECTED by ≥2/3 skeptics: <why>
```

## Posting (only after user OK)
Summary comment (`gh pr comment <n> --body-file review.md`), or line-anchored
inline review via `scripts/post_review.py` (`event: COMMENT` so existing
approvals aren't overridden). Verify each target line is a `+`/context line in
the diff first, or the API rejects the whole review.
