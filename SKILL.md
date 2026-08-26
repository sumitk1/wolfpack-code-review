---
name: wolfpack-code-review
description: Use when a deep panel review is wanted — a "wolfpack", multi-agent, multi-reviewer, or adversarially-validated review of a PR, branch, or diff; a code audit of a directory; or adversarial validation of a design doc or plan — running entirely on Claude models inside Claude Code.
---

# Wolfpack Review

A pack of independent reviewer subagents hunts an input from every angle; an
adversarial skeptic pass culls findings that can't survive falsification; what
remains is a validated, severity-ranked report.

The panel runs entirely on **Claude models** through Claude Code's native
**Workflow** tool:

- The fleet is fixed and always live: **elite** = `fable`, `opus` ·
  **mid** = `sonnet` · **economy** = `haiku`, chosen per agent via
  `agent(prompt, {model, effort})`. No model-discovery stage is needed.
- Prompts are assembled per run from `references/contracts.md` (depth
  prefixes, lens briefs, skeptic prompt, JSON schemas).
- Parallel `agent()` calls are harness-managed; a dead or skipped agent
  resolves to `null` (`.filter(Boolean)`) — no process tree to reap, no
  orphans. The panel tolerates a missing lens: synthesize from survivors and
  note the gap.
- Output contracts are enforced at the tool layer with `agent(..., {schema})`
  and automatic retry — malformed-JSON casualties cannot happen.

**What a single-vendor panel costs you:** cross-vendor decorrelation.
Substitute what still decorrelates — independent contexts, disjoint lenses,
*different Claude models* (fable, opus, sonnet, haiku are distinct models, not
one model at sizes), and different effort levels — and lean harder on Stage 3:
the skeptic pass is what makes same-family findings defensible. Never assign a
lens and its `-b` cross-check the same model.

## Modes (router)

Pick from the input; if ambiguous, ask.

| Mode | Trigger | Reference |
|---|---|---|
| **pr-review** (default) | a PR url / number / branch / diff | `references/pr-review.md` |
| **code-audit** | a directory / codebase path | `references/code-audit.md` |
| **doc-review** | a design doc / plan / `.md` set | `references/doc-review.md` |

## The five stages

```
Stage 1  BREADTH    lens reviewers fan out in ONE Workflow barrier per target,
                    each on its tier's model at its lens's effort, all reading a
                    shared "review packet" (scoped input + verified experiments).
Stage 2  DEDUP      one mid-tier agent clusters raw findings; each cluster gets
                    signal_strength = # reviewers who independently raised it.
Stage 3  PRECISION  3 skeptics try to FALSIFY each cluster. Kill at >=2/3 REJECT —
                    but an invalid refutation ("can't find it") is a VOID vote.
Stage 4  SYNTHESIS  YOU (orchestrator) adjudicate ties, severity-bucket, write
                    the report. Post only after the user OKs.
```

## The panel

Depth→effort: `max`→`max`, `high`→`high`, `med`→`medium`, `min`→`low` — and keep
the matching depth-prefix prose in the prompt (see contracts.md); belt and braces.

| Lens | Tier | Model | Effort | Notes |
|---|---|---|---|---|
| correctness | elite | fable | max | |
| correctness-b | elite | opus | high | full panel only — different model than primary, always |
| security | elite | opus | max | |
| security-b | elite | fable | high | full panel only |
| domain | elite | opus | max | brief is stack-parameterized — fill in the diff's actual stack |
| lifecycle (day-2) | elite | fable | high | |
| quality | mid | sonnet | medium | |
| completeness | mid | sonnet | medium | |
| anti-pattern | economy | haiku | low | |
| skeptic-a | elite | fable | high | |
| skeptic-b | elite | opus | xhigh | |
| skeptic-c | mid | sonnet | xhigh | tier floor deliberately relaxed to buy a third weight family |

**Lean panel** (default for ≤ ~500 changed lines): drop the `-b` cross-checks →
7 reviewers + dedup + 3 skeptics ≈ 11 agents per target.
**Full panel**: 9 reviewers ≈ 13 agents per target.
**Economy profile** (named option, `profile: 'economy'` per target): same 7
lenses on opus/sonnet/haiku with nothing above `high` effort, 2 skeptics
(kill = both REJECT), dockets of 12 — ≈4–6× cheaper; use when usage limits
bind or diffs are small. Seat table in `references/contracts.md` §Panel
profiles. Always state the profile and quorum in the report footer.
**Frugal profile** (`profile: 'frugal'`): the floor — sonnet/haiku seats only,
nothing above `medium`, haiku dedup, sonnet+haiku skeptics, dockets of 15;
≈2–3× cheaper than economy again, at the cost of more Stage-4 filtering.

## Runtime expectations & straggler doctrine (learned from live runs)

Observed on a real 3-PR run: lens reviewers 1–11 min (opus/max the slowest),
dedup 1–2 min, **skeptics dominate wall-clock** — a skeptic's cost scales with
the number of findings it must verify, not the diff size, and an xhigh skeptic
on a 10+-finding docket can run 20–40 min. That is grinding, not hanging.

- **Cap each skeptic call's docket at ~8 findings.** More clusters than that →
  chunk the cluster list and issue multiple smaller skeptic calls per skeptic
  identity (same model/effort, disjoint dockets). Many short calls beat one
  40-minute call and keep each call inside a ~15-minute envelope.
- **The harness has no per-agent kill**, so distinguish grinding from dead by
  evidence: the run's transcript dir (`agent-*.jsonl` mtimes) advancing =
  working. **No writes for >15 min = dead**: `TaskStop` the workflow, then
  relaunch with `{scriptPath, resumeFromRunId}` — completed agents replay from
  cache; only stragglers re-run. Never kill a run on elapsed time alone while
  its files are still growing, and never wait forever on one whose files aren't.
- **Safeguard false-positives are model-correlated.** Observed: every fable
  panelist reviewing auth/JWT-heavy diffs died with an API-safeguards flag
  while opus/sonnet/haiku on the same packet sailed through — 5 lens slots and
  2 skeptics lost in one run. The failure is (model × content), not
  content-invalid, so: (1) never put one model on ALL instances of a lens
  across targets — alternate fable/opus per target (the `alt` flag) so a
  model-wide flag costs half a lens, not the whole lens; (2) recover by
  re-running dead slots on the other elite model via a follow-up workflow whose
  merge stage dedups the late findings against the already-adjudicated clusters
  (reinforce or append; skeptic-verify only the new ones); (3) report the
  reduced quorum honestly (2 skeptic votes = valid quorum, kill needs both
  REJECTs).
- **Resume matching is byte-exact.** Renaming the workflow's `meta.name` or
  reordering/removing `args` targets invalidates ALL cached agent results and
  silently re-runs the expensive lens fleet live. To re-run a subset, change
  nothing except the calls you intend to re-run — same meta, same args, same
  prompts byte-for-byte — and watch the first minute for unexpected live
  Breadth agents.

## Host memory doctrine (learned from a 40GB live blow-up)

The harness runs up to `min(16, cpus-2)` agents at once and a batch panel
saturates every slot. Two multipliers turned that into macOS "your system has
run out of application memory" on a 48GB host: each in-flight agent's
transcript lives in the CLI process, and reviewers who were told to "run the
tests" each booted their own toolchain (`npm ci`, `tsc`, `cdk synth`, jest,
pytest — 1-3GB apiece, ×12 concurrent).

- **Builds and test suites run exactly once — by the orchestrator at packet
  build (Playbook §3).** Reviewer and skeptic prompts forbid toolchain
  launches (installs, builds, test suites, containers); the packet's verified
  experiments ARE the execution evidence, and a reviewer who needs a new
  experiment names the command in the finding instead of running it.
- **Size the panel's concurrency at launch.** A semaphore in
  `scripts/wolfpack.js` gates the panel's own in-flight `agent()` calls below
  the harness cap, reading `concurrency` from the args targets — MIN across
  targets wins, absent → default 4. The Workflow sandbox cannot measure the
  host itself, so the orchestrator does it right before building packets and
  stamps the value via `build_packet.py --concurrency N`. Sizing: check
  `memory_pressure -Q` (macOS; Linux: `free -m`) — free < 25% or other
  memory-heavy apps open → 2 · free 25–50% → 4 · free > 50% on an idle
  host → 6–8. The value never invalidates resume caching (cache keys hash
  prompts/opts). `node tests/test_concurrency.mjs` verifies the gate.
- **Run big batches in a fresh session, and let it end.** Every completed
  agent's transcript and cached result is retained in the CLI process for
  resume — an all-day session that has run many panels holds all of them
  (observed: 21 workflows / 865 agents in one session, heap ratcheting all
  day). Reports and `args-*.json` live on disk; nothing is lost by exiting.
- The terminal app itself accumulates the progress-tree redraws of a
  100+-agent run in scrollback; cap scrollback lines if the terminal's own
  footprint keeps growing across long runs.

Multiple targets (e.g. several PRs) go through **one** Workflow run,
`pipeline()`d so each target's stages proceed independently — never one workflow
per target. Note the session's workflow-size guideline in the run log when the
panel exceeds it; a requested panel review is the scale the user asked for.
Prefer one or two targets per workflow so an interrupt is cheap.

## Playbook

1. **Route the mode**, read its reference doc, resolve the target
   (`gh pr view <n> --json number,headRefOid,baseRefName,title,url`).
2. **Checkout at head.** Reviewers read live files, so give them a checkout whose
   lines match the diff: `git worktree add --detach <scratchpad>/wolf/pr<N> <headRefOid>`.
   Scratch output goes to `<scratchpad>/wolf/out/`, not the user's repo.
   **Closed / merged PRs review exactly the same way**: fetch the head via
   `git fetch origin refs/pull/<N>/head` (GitHub keeps that ref after the
   branch is deleted), `gh pr diff` and `gh pr view --json body` still work, and
   `POST …/pulls/<N>/reviews` (event `COMMENT`) still posts. Put the PR state
   in the packet metadata with a note that recommendations must be phrased as
   follow-up changes against the base branch — there is no branch to push
   fixes to. (`scripts/build_packet.py` does all of this; measure free memory
   first and pass `--concurrency N` per the Host memory doctrine sizing table.)
3. **Build the shared review packet** (one file all reviewers read): target
   metadata, the full diff in a ```diff fence (exclude generated giants —
   lockfiles, generated schemas — with a note naming them), **verified
   experiments** (run the tests/build NOW at the head SHA — sandboxed if the
   author is untrusted, since building/testing a PR executes its code; a verified
   "bad input → bad output" table beats speculation — this is the ONLY stage
   where builds/tests run, see Host memory doctrine), and a **known/accepted
   items** list (already-filed issues, deliberate scope cuts) so the panel
   doesn't re-raise them as discoveries.
4. **Run the Workflow** — breadth barrier → dedup agent → skeptic barrier, per
   target. Complete script template in `references/contracts.md` §Workflow;
   batch-ready implementation in `scripts/wolfpack.js` (copy it to the run's
   scratch dir; pass targets via `args`). Reviewer prompts point at packet
   path + worktree path; findings travel to skeptics **inline in the prompt**
   (Workflow scripts have no filesystem).
5. **Adjudicate (Stage 4):**
   - Kill rule: drop a finding **only if ≥2 of 3 skeptics REJECT with a valid
     reason**. A REJECT justified by "not found / can't locate" is VOID — discard
     that vote; if that takes the finding below the kill line, it survives.
   - Consensus UPHOLD → keep, weight severity by signal_strength.
   - Skeptics split → YOU re-verify against the code and break the tie; show the
     dissent in the report.
   - Prefer precision: when in doubt, downgrade rather than inflate. On the
     frugal profile, re-verify every HIGH against the code (or delegate that to
     one mid-tier adjudicator agent per target) before anything is posted.
6. **Write the report** to `<scratchpad>/wolf/out/review-<id>.md` in the mode's
   output format (verdict first; findings with `file:line`, evidence, concrete
   fix; a "considered and dismissed" section; footer = panel composition + note
   that findings survived an adversarial skeptic pass).
7. **Post only after the user OKs** — summary comment (`gh pr comment`) or
   line-anchored inline review via `scripts/post_review.py` (event `COMMENT` so
   existing approvals aren't overridden; verify each target line is a `+`/context
   line in the diff first).
8. **Clean up** the worktrees: `git worktree remove <path>`.

## Tuning

- Change lenses/tiers/efforts by editing the tables in `references/contracts.md`
  — it is the single source of truth for the panel.
- Cost scales with elite/max lenses; `sonnet`/`haiku` lenses are the cheap ones.
- Reviewers and skeptics are **read-only and toolchain-free by instruction**:
  they may read/grep and run cheap read-only shell (`git show`, one-liner
  interpreter checks) but never modify files and never launch installs, builds,
  test suites, or containers — see Host memory doctrine. Builds/tests happen
  once, at packet build. Caveat on that packet step: running an untrusted PR's
  tests is arbitrary code execution with your ambient credentials, and
  `build_packet.py` worktrees share `.git` (hooks/config) with your clone —
  sandbox or skip test-runs for untrusted authors. Fixes are a separate step by
  the main agent after the human picks findings.

## Files

- `SKILL.md` — this playbook + router.
- `references/contracts.md` — lens briefs, depth prefixes, reviewer/skeptic
  prompts, JSON schemas, complete Workflow script template.
- `references/pr-review.md` / `code-audit.md` / `doc-review.md` — per-mode
  ingestion, panel sizing, output format.
- `scripts/post_review.py` — inline-review poster (github.com default).
- `scripts/wolfpack.js` — the batch Workflow script: `PROFILES`
  (standard | economy | frugal), `alt` model swap, skeptic dockets; targets via `args`.
- `scripts/build_packet.py` — per-target prep + packet: pull-ref fetch (open,
  closed and merged PRs), detached worktree, diff/body, known-items list,
  `--profile`, `--concurrency` (launch-time panel sizing), upserts
  `args-<batch>.json`. Edit `CLONES`/`GLOBAL_KNOWN` per
  repo, or set `WOLF_CLONE=<path>` to point at a clone without editing.
- `scripts/wolftools.py` — `split` a workflow output into per-target findings,
  `table`, `report` (profile/quorum-aware footer), `post` (COMMENT review).
