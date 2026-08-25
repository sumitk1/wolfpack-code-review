# Wolfpack — contracts (single source of truth for the panel)

Edit lenses, tiers, and efforts HERE; the Workflow script template below (and
`scripts/wolfpack.js`) consumes these.

## Depth prefixes (prepend to the reviewer prompt, matched to `effort`)

| depth | effort | prefix |
|---|---|---|
| max | max | "Before listing any finding, reason exhaustively through every implication, assumption, and edge case. Trace each changed value from input to effect. Leave no stone unturned." |
| high | high | "Think carefully and systematically before responding. Trace every logical chain and challenge every assumption." |
| med | medium | "Be thorough. Work through the diff section by section before listing findings." |
| min | low | "Quickly identify the most obvious issues. Favor breadth over depth." |

## Lens briefs (domain lens is stack-parameterized)

- **correctness** (elite/fable/max): LOGIC & CORRECTNESS. Hunt: off-by-one,
  nil/empty/zero handling, type coercion, boundary/overflow, error-swallowing,
  races, idempotency, ordering assumptions, silent fallbacks that mask bugs, and
  "works in test / dies in prod" data-dependent failures. Trace each changed
  value from input to effect. Ask: what input makes this wrong?
- **correctness-b** (elite/opus/high, full panel): LOGIC & CORRECTNESS,
  independent cross-check. Same brief as the primary but reason from scratch —
  do not assume the obvious bug is the only bug. Especially probe
  template/config rendering, shell quoting/expansion, and verification checks
  whose PASS condition can be satisfied by a broken state.
- **security** (elite/opus/max): SECURITY. Hunt: privilege escalation, secret
  handling, injection (shell/SQL/template), supply-chain (mutable image tags,
  unpinned deps), auth/token exposure, blast radius, and least-privilege
  violations. Assume a hostile input and a hostile insider.
- **security-b** (elite/fable/high, full panel): SECURITY, independent
  cross-check on a different model. Focus extra on things that pass tests but
  fail or misbehave at deploy/runtime, and on whether elevated privileges are
  actually necessary or could be scoped down.
- **quality** (mid/sonnet/medium): CODE QUALITY & DESIGN. Judge against DRY,
  YAGNI, SOLID, and the Zen of Python (even for non-Python). Hunt:
  duplication/magic literals that can drift, leaky abstractions, poor naming,
  dead code, over-engineering, functions/files that are too big, and comments
  that lie. Prefer a few high-signal findings over a laundry list of nits.
- **completeness** (mid/sonnet/medium): COMPLETENESS. Hunt: missing test
  coverage (esp. for the exact edge cases this change adds), untested defensive
  branches, missing docs/CHANGELOG updates, config added but not wired to every
  path, version bumps forgotten, and mismatches between what the description or
  design doc promises and what the diff actually delivers.
- **antipattern** (economy/haiku/low): ANTI-PATTERNS & FOOTGUNS. Hunt: silent
  failure, catch-and-ignore, hidden side effects, surprising defaults, values
  that render fine but explode at runtime, copy-paste drift, "temporary" hacks,
  and platform-specific anti-patterns for the stack in the diff.
- **domain** (elite/opus/max): DOMAIN CORRECTNESS for the stack in the diff —
  **fill this in per run** (e.g. Python/FastAPI/SQLAlchemy/Alembic/Docker, or
  Kubernetes/Helm, or React/TS). Hunt the stack's rendering/semantics edge
  cases, schema gaps, migration/rollout semantics, and whether the change
  actually achieves its stated operational goal in the real environment.
- **lifecycle** (elite/fable/high): LIFECYCLE & OPERABILITY (day-2). Ask what
  happens over TIME, not just at merge: disable/uninstall/rollback (does state
  get reverted, or orphaned forever?), restart/upgrade/re-deploy survival and
  ordering, drift when a toggle flips, migration paths, quota/limit
  interactions, mixed-environment assumptions. Findings must be triggered by
  real operational events.

## Reviewer prompt template

```
<depth prefix>

You are one lens on a WOLFPACK code-review panel — multiple independent
reviewers on different models, whose findings are then adversarially validated
by skeptics and merged.

## YOUR LENS
<lens brief>

Stay in your lane: report issues that fall under YOUR lens. Other lenses are
covered by other reviewers, so don't dilute your signal by straying.

## INPUT
Read the review packet at <packet path>, then investigate the live checkout at
<worktree path> (read/grep/read-only shell only — git show, run tests in a
scratch venv; NEVER modify files or run mutating/network-write commands).

RULES OF ENGAGEMENT
- Scope = the diff (and just enough surrounding code to judge it). Do NOT
  review pre-existing code untouched by the change unless the diff makes it
  newly reachable.
- PRECISION OVER RECALL. A wrong finding costs more than a missed one. If you
  can't defend it against a skeptic, set confidence < 0.5 or drop it.
- No taste-as-bug. Style opinions go in LOW at most, and only if defensible.
- Cite evidence (file:line, rendered output, a command you ran). Don't invent facts.
- Cap yourself at your top 3-6 findings. Empty findings is a valid answer.
- Severity: HIGH = correctness/security/data-loss/outage; merge-blocker.
  MEDIUM = real defect or maintainability risk; should fix. LOW = polish/nits/docs.
```

Output is enforced by schema (below) — no fenced-JSON instructions needed.

## Panel profiles (named options — pick per target with `profile`)

The lens list is the same in every profile; a profile only changes which
model/effort sits in each seat, how many skeptics vote, and the docket size.
Select with `profile: 'economy'` or `profile: 'frugal'` on a target in `args` (absent = `standard`).

| seat | **standard** (default) | **economy** | **frugal** |
|---|---|---|---|
| correctness | fable / max | opus / high | sonnet / medium |
| security | opus / max | sonnet / high | sonnet / medium |
| domain | opus / max | sonnet / medium | haiku / medium |
| lifecycle | fable / high | sonnet / medium | haiku / low |
| quality | sonnet / medium | haiku / low | haiku / low |
| completeness | sonnet / medium | haiku / low | haiku / low |
| antipattern | haiku / low | haiku / low | haiku / low |
| dedup | sonnet / medium | sonnet / low | haiku / low |
| skeptics | fable/high · opus/xhigh · sonnet/xhigh | sonnet/high · opus/medium | sonnet/medium · haiku/medium |
| docket cap | 8 | 12 | 15 |
| kill rule | ≥2 of 3 valid REJECTs | **both** skeptics REJECT with a valid reason | **both** skeptics REJECT with a valid reason |
| `alt` swaps | fable ↔ opus on the elite seats | opus ↔ sonnet on correctness/security | (ignored) |
| agents / target (lean) | 11 (+ extra skeptic dockets) | 10 (+ extra skeptic dockets) | 10 (+ extra skeptic dockets) |

**When to use economy:** usage limits are binding, the diff is small or
low-risk, or many targets run in one batch. It keeps one elite seat (opus on
the correctness lens), nothing above `high` effort, and the full skeptic pass on
a 2-vote quorum — roughly 4–6× cheaper per target than standard. Cost is
dominated by `max`/`xhigh` thinking and by each skeptic docket re-reading the
packet, which is why economy also raises the docket cap. The report footer
must name the profile and the quorum (`wolftools.py report` does this from the
`profile`/`quorum` fields the script emits); never present an economy review
as a standard one. Depth prefixes follow the effort column as usual.

**When to use frugal:** the floor — usage limits are nearly exhausted or the
batch is large and the diffs are conventional. No fable/opus seat at all,
nothing above `medium` effort, haiku dedup, and a sonnet + haiku skeptic pair
on the same 2-vote quorum; roughly 2–3× cheaper than economy again. The trade
is precision: expect more surviving noise, so the orchestrator's Stage-4
adjudication must re-verify every HIGH against the code (or delegate that to a
mid-tier adjudicator per target) before anything is posted.

Live implementation of the profiles: the `PROFILES` table in
`scripts/wolfpack.js` (`profileOf(pr)` resolves lenses, skeptics, dedup,
docket and the kill-rule sentence, and fails fast on an unknown name before any
agent spends tokens). Copy it to the run's scratch dir and pass targets via
`args` (built by `scripts/build_packet.py`).

## Skeptic prompt (findings embedded inline)

```
You are an ADVERSARIAL VALIDATOR on a wolfpack code-review panel. Your job is
NOT to find new issues — it is to try to FALSIFY the candidate findings, so only
defensible ones survive. Precision of the final report depends on you being
tough AND fair.

Review packet: <packet path>. Live checkout: <worktree path>. For EACH candidate
finding below, independently VERIFY it against the actual code (read/grep/
git show/run the relevant test) before ruling.

Rule REJECT / DOWNGRADE when a finding is:
- Not supported by the diff (hallucinated line, wrong file, misread logic).
- Already handled elsewhere (a guard/validation/test the reviewer missed).
- Out of scope (pre-existing code the change didn't touch or make newly reachable).
- Speculative with no realistic trigger, or a taste opinion dressed up as a bug.
- Duplicate of another finding (mark which id it duplicates).

Rule UPHOLD when you can restate the concrete failure and its trigger from the code.

INVALID-REFUTATION GUARD (critical): you must actually look at the referenced
code. A REJECT justified only by "can't find it / not in the repo / file
missing" is INVALID — that means YOU failed to open the file, not that the
finding is wrong. Read the file first; if you still can't verify either way,
rule UPHOLD (uncertain), never REJECT. Do not refute merely because you are unsure.

Downstream kill rule (FYI): a finding is dropped only if <KILL RULE: standard
">=2 of 3 skeptics REJECT it with a valid reason" | economy/frugal "BOTH of the
2 skeptics REJECT it with a valid reason"> (a "not-found" REJECT never counts).
You are READ-ONLY.

CANDIDATE FINDINGS (JSON):
<findings json>
```

## JSON Schemas

```js
const FINDINGS_SCHEMA = {
  type: 'object', required: ['lens', 'verdict', 'findings'],
  properties: {
    lens: { type: 'string' },
    verdict: { type: 'string', description: 'one sentence overall' },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'severity', 'title', 'location', 'rationale', 'recommendation', 'confidence'],
        properties: {
          id: { type: 'string', description: '<LENS-1> style' },
          severity: { enum: ['HIGH', 'MEDIUM', 'LOW'] },
          title: { type: 'string', description: '<=100 char imperative summary' },
          location: { type: 'string', description: 'path/to/file:line or symbol' },
          rationale: { type: 'string', description: 'why real, tied to the diff, cite evidence' },
          recommendation: { type: 'string', description: 'concrete fix' },
          confidence: { type: 'number' },
        },
      },
    },
  },
}

const CLUSTERS_SCHEMA = {
  type: 'object', required: ['clusters'],
  properties: {
    clusters: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'severity', 'title', 'location', 'rationale', 'recommendation', 'signal_strength', 'raised_by'],
        properties: {
          id: { type: 'string', description: 'F1..Fn' },
          severity: { enum: ['HIGH', 'MEDIUM', 'LOW'] },
          title: { type: 'string' },
          location: { type: 'string' },
          rationale: { type: 'string', description: 'merged, kept short' },
          recommendation: { type: 'string' },
          signal_strength: { type: 'integer', description: '# reviewers who independently raised it' },
          raised_by: { type: 'array', items: { type: 'string' } },
        },
      },
    },
  },
}

const VERDICTS_SCHEMA = {
  type: 'object', required: ['verdicts'],
  properties: {
    verdicts: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'ruling', 'reason'],
        properties: {
          id: { type: 'string' },
          ruling: { enum: ['UPHOLD', 'DOWNGRADE', 'REJECT', 'DUPLICATE'] },
          new_severity: { enum: ['HIGH', 'MEDIUM', 'LOW', null] },
          duplicate_of: { type: ['string', 'null'] },
          reason: { type: 'string', description: 'cite the ACTUAL code you inspected' },
        },
      },
    },
  },
}
```

## Workflow script template (pr-review, lean panel, N targets)

The `LENSES`/`SKEPTICS` literals below are the **standard** profile; for the
economy/frugal seats substitute the matching column of the profile table (or
use `scripts/wolfpack.js`, whose `PROFILES` map carries all three and switches
per target).

Adapt paths/lenses per run; pass targets via `args`. The fields the Workflow
script itself reads are `id`, `packet`, `checkout`, `stack` (+ `alt`, `profile`
in `scripts/wolfpack.js`) — but the Stage-4 tooling (`wolftools.py`) also needs
`key`, `repo`, and `pr` on each target, so use the full shape
`scripts/build_packet.py` emits:

```js
args = [{ id: 'myrepo#58', key: 'pr58', repo: 'my-org/myrepo', pr: 58,
          packet: '/abs/packet-pr58.md', checkout: '/abs/wolf/pr58',
          stack: 'Python/FastAPI/...', alt: false, profile: 'standard' }, ...]
```

```js
export const meta = {
  name: 'wolfpack-pr-review',
  description: 'Wolfpack panel review (Claude-only): breadth lenses -> dedup -> adversarial skeptics',
  phases: [{ title: 'Breadth' }, { title: 'Dedup' }, { title: 'Precision' }],
}

const LENSES = [
  { key: 'correctness',  model: 'fable',  effort: 'max',    depth: 'max' },
  { key: 'security',     model: 'opus',   effort: 'max',    depth: 'max' },
  { key: 'domain',       model: 'opus',   effort: 'max',    depth: 'max' },
  { key: 'lifecycle',    model: 'fable',  effort: 'high',   depth: 'high' },
  { key: 'quality',      model: 'sonnet', effort: 'medium', depth: 'med' },
  { key: 'completeness', model: 'sonnet', effort: 'medium', depth: 'med' },
  { key: 'antipattern',  model: 'haiku',  effort: 'low',    depth: 'min' },
]
const SKEPTICS = [
  { key: 'skeptic-a', model: 'fable',  effort: 'high' },
  { key: 'skeptic-b', model: 'opus',   effort: 'xhigh' },
  { key: 'skeptic-c', model: 'sonnet', effort: 'xhigh' },
]
// Skeptic wall-clock scales with docket size, not diff size (observed: 10+
// findings at xhigh -> 20-40 min). Chunk clusters into dockets of <= 8 per
// skeptic call: SKEPTICS.flatMap over chunk(clusters, 8), then merge verdicts
// per skeptic key before adjudication. See SKILL.md straggler doctrine.

// Paste FINDINGS_SCHEMA / CLUSTERS_SCHEMA / VERDICTS_SCHEMA and the prompt
// builders (reviewerPrompt(lens, pr), dedupPrompt(reviews, pr),
// skepticPrompt(clustersJson, pr)) from this file.

const results = await pipeline(
  args,
  pr => parallel(LENSES.map(l => () =>
    agent(reviewerPrompt(l, pr), {
      label: `${l.key}#${pr.id}`, phase: 'Breadth',
      schema: FINDINGS_SCHEMA, model: l.model, effort: l.effort,
    })
  )).then(rs => ({                              // a dead lens = a noted gap, never a blocker
    reviews: rs.map((r, i) => r ? { lens: LENSES[i].key, verdict: r.verdict, findings: r.findings } : null).filter(Boolean),
    gaps: rs.map((r, i) => r ? null : LENSES[i].key).filter(Boolean),
  })),
  (st, pr) => agent(dedupPrompt(st.reviews, pr), {
    label: `dedup#${pr.id}`, phase: 'Dedup',
    schema: CLUSTERS_SCHEMA, model: 'sonnet', effort: 'medium',
  }).then(d => d ? { ...st, clusters: d.clusters }
    // dead dedup = noted gap, not a crash: raw findings pass through as 1-lens clusters
    : { ...st, gaps: [...st.gaps, 'dedup'],
        clusters: st.reviews.flatMap(r => r.findings.map(f => ({ ...f, signal_strength: 1, raised_by: [r.lens] }))) }),
  (st, pr) => parallel(SKEPTICS.map(s => () =>
    agent(skepticPrompt(JSON.stringify(st.clusters), pr), {
      label: `${s.key}#${pr.id}`, phase: 'Precision',
      schema: VERDICTS_SCHEMA, model: s.model, effort: s.effort,
    }).then(v => v && { skeptic: s.key, verdicts: v.verdicts })
  )).then(vs => {
    const ok = vs.filter(Boolean)             // quorum = skeptics that returned, so the footer reports the real run
    return { pr: pr.id, profile: 'standard', quorum: ok.length,
             lensVerdicts: st.reviews.map(r => ({ lens: r.lens, verdict: r.verdict })),
             gaps: st.gaps, clusters: st.clusters, skeptics: ok }
  })
)
return results
```

(This output shape — `skeptic`-keyed verdicts plus `gaps`/`profile`/`quorum` —
is what `scripts/wolftools.py` consumes; keep it if you adapt the template.)

Dedup prompt core: "Cluster these raw panel findings into stable ids F1..Fn.
Merge findings that describe the same underlying defect even if worded
differently or located a few lines apart. signal_strength = number of DISTINCT
reviewers (by lens) who raised it; list them in raised_by. Keep rationales
short. Do not drop, judge, or add findings — clustering only. RAW FINDINGS:
<json of [{lens, findings}]>."

Stage 4 (kill rule, invalid-refutation guard, tie-breaks) is orchestrator work —
see SKILL.md Playbook §5.
