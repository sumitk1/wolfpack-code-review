# wolfpack-code-review

A [Claude Code](https://claude.com/claude-code) **skill** that runs a
multi-agent, adversarially-validated code review: a pack of independent
reviewer subagents ("lenses") hunts a PR, codebase, or design doc from every
angle; an adversarial skeptic pass tries to **falsify** every finding; only
findings that survive make the report.

```
Stage 1  BREADTH    7–9 lens reviewers fan out in parallel (correctness,
                    security, domain, lifecycle, quality, completeness,
                    anti-patterns), each on its own Claude model + effort level
Stage 2  DEDUP      one agent clusters duplicate findings across reviewers
Stage 3  PRECISION  3 skeptics independently try to REFUTE each finding;
                    a finding dies at >=2/3 valid REJECTs — but a lazy
                    "can't find it" refutation is a VOID vote
Stage 4  SYNTHESIS  the orchestrator adjudicates, severity-buckets, writes the
                    report, and posts it only after you approve
```

Why the design works:

- **Independent contexts decorrelate errors.** Each reviewer reads the same
  "review packet" cold, on its own model (fable / opus / sonnet / haiku) and
  its own reasoning-effort level, through exactly one lens. Agreement between
  reviewers is signal (`signal_strength`), not echo.
- **Precision comes from falsification, not politeness.** The skeptic pass is
  biased *against* findings — but the **invalid-refutation guard** forces
  every REJECT to cite the actual code, so subtle findings aren't killed by a
  skeptic that never opened the file.
- **Verified experiments beat speculation.** The packet includes the output of
  actually building/testing the change at the head SHA, plus a known/accepted
  list so the panel doesn't re-discover filed issues.

## Requirements

- **Claude Code** with the **Workflow** orchestration tool (this skill's
  engine — it drives the parallel `agent()` fan-out with per-agent
  model/effort and schema-enforced structured output).
- `gh` (GitHub CLI), authenticated — for PR review mode and posting reviews.
- `git`, `python3` — packet prep and Stage-4 tooling.

## Install

```bash
git clone https://github.com/sumitk1/wolfpack-code-review.git \
  ~/.claude/skills/wolfpack-code-review
```

Claude Code picks the skill up from `~/.claude/skills/` automatically.

## Use

Ask for it in a session:

> run a wolfpack review of PR 42
> wolfpack-audit the src/server directory
> adversarially validate docs/design.md

Three modes, routed from the input:

| Mode | Input | Output |
|---|---|---|
| **pr-review** (default) | PR url / number / branch / diff | severity-bucketed review, optional inline PR comments |
| **code-audit** | a directory / codebase | executive summary + issues by severity + file index |
| **doc-review** | design doc / plan / RFC | `<doc>.review.md` alongside the source |

Nothing is posted to GitHub without your explicit OK; reviewers and skeptics
are **read-only** by instruction (they may read, grep, and run tests — never
modify files).

## Cost profiles

A full panel is deliberately expensive — ~11–13 agents per target, several at
maximum reasoning effort. Two cheaper named profiles trade depth for cost:

| Profile | Seats | Skeptics | Rough cost |
|---|---|---|---|
| `standard` | fable/opus on the lead lenses, max/xhigh effort | 3 (kill = ≥2/3 valid REJECTs) | baseline |
| `economy` | one opus seat, rest sonnet/haiku, ≤ high effort | 2 (kill = both REJECT validly) | ~4–6× cheaper |
| `frugal` | sonnet/haiku only, ≤ medium effort | 2 (kill = both REJECT validly) | ~2–3× cheaper again |

The report footer always names the profile and skeptic quorum used — a frugal
review is never presented as a standard one.

## Repo layout

```
SKILL.md                    playbook + mode router (the skill entry point)
references/contracts.md     lens briefs, depth prefixes, prompts, JSON schemas,
                            panel profiles, Workflow script template
references/pr-review.md     per-mode ingestion, panel sizing, output format
references/code-audit.md
references/doc-review.md
scripts/wolfpack.js         batch-ready Workflow script (profiles, alt-model
                            swap, skeptic dockets); copy to a scratch dir per run
scripts/build_packet.py     per-target prep: pull-ref fetch (works on open,
                            closed AND merged PRs), detached worktree, packet,
                            args-<batch>.json
scripts/wolftools.py        Stage-4 tooling: split / table / report / post
scripts/post_review.py      standalone line-anchored review poster
tests/test_parsers.py       regression tests for the diff/anchor/packet parsers
```

`scripts/` is meant to be **copied into a per-batch scratch directory** —
`build_packet.py` and `wolftools.py` write worktrees, packets, and findings
next to themselves, not into your repo. Edit `CLONES` / `GLOBAL_KNOWN` in
`build_packet.py` for your repos (or set `WOLF_CLONE=<path>` — the environment
variable wins over `CLONES`).

## Cautions

- **Content goes to the model.** The packet embeds the full diff (or doc).
  Don't run it over files containing live credentials or data you can't send
  to the Claude API.
- **Reviewed content is untrusted input.** A hostile diff could try to steer
  reviewers ("ignore your instructions…"). Reviewer output is schema-constrained
  and Stage 4 is human-adjudicated, which limits prompt injection — but
  "read-only" constrains the agents' tool calls, not code the PR itself runs:
  **building or testing an untrusted PR executes its code** with your ambient
  credentials, and `build_packet.py` worktrees share `.git` (hooks/config) with
  your clone. Sandbox test-runs for untrusted authors, adjudicate Stage 4
  yourself, and treat any finding that quotes instructions from the diff with
  suspicion.
- **Skeptics dominate wall-clock.** An xhigh skeptic on a 10+-finding docket
  can grind for 20–40 minutes; that's working, not hung. The docket caps in
  the profiles exist to keep each call short — see the straggler doctrine in
  `SKILL.md` before killing anything.

## License

MIT — see [LICENSE](LICENSE).
