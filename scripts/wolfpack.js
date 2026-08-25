export const meta = {
  name: 'wolfpack-pr-review',
  description: 'Wolfpack panel review (Claude-only): breadth lenses -> dedup -> adversarial skeptics, per PR; profiles standard|economy|frugal, model alternation, skeptic dockets',
  phases: [
    { title: 'Breadth', detail: '7 lenses per PR (models/effort per profile)' },
    { title: 'Dedup', detail: 'one clusterer per PR (model per profile)' },
    { title: 'Skeptics', detail: 'standard: 3 skeptics, dockets <= 8 | economy: 2, <= 12 | frugal: 2, <= 15' },
  ],
}
const DEPTH = {
  max: 'Before listing any finding, reason exhaustively through every implication, assumption, and edge case. Trace each changed value from input to effect. Leave no stone unturned.',
  high: 'Think carefully and systematically before responding. Trace every logical chain and challenge every assumption.',
  med: 'Be thorough. Work through the diff section by section before listing findings.',
  min: 'Quickly identify the most obvious issues. Favor breadth over depth.',
}

const BRIEFS = {
  correctness: () => 'LOGIC & CORRECTNESS. Hunt: off-by-one, nil/empty/zero handling, type coercion, boundary/overflow, error-swallowing, races, idempotency, ordering assumptions, silent fallbacks that mask bugs, and "works in test / dies in prod" data-dependent failures. Trace each changed value from input to effect. Ask: what input makes this wrong?',
  security: () => 'SECURITY. Hunt: privilege escalation, secret handling, injection (shell/SQL/template), supply-chain (mutable image tags, unpinned deps), auth/token exposure and verification gaps, blast radius, least-privilege violations. Assume a hostile input and a hostile insider.',
  domain: (pr) => 'DOMAIN CORRECTNESS for the stack in this diff: ' + (pr.stack || 'the languages/frameworks visible in the diff') + '. Hunt the stack-specific edge cases: rendering/semantics gotchas, schema/migration semantics, framework behavior that differs from the author\'s apparent mental model, and whether the change actually achieves its stated operational goal in the real environment.',
  lifecycle: () => 'LIFECYCLE & OPERABILITY (day-2). Ask what happens over TIME, not just at merge: rollback/downgrade (does state get reverted, or orphaned forever?), restart/upgrade/re-deploy survival and ordering, drift when a toggle flips, migration paths, quota/limit interactions, mixed-environment assumptions (dev vs container vs prod). Findings must be triggered by real operational events.',
  quality: () => 'CODE QUALITY & DESIGN. Judge against DRY, YAGNI, SOLID, and the Zen of Python. Hunt: duplication/magic literals that can drift, leaky abstractions, poor naming, dead code, over-engineering, functions/files too big, comments that lie. Prefer a few high-signal findings over a laundry list of nits.',
  completeness: () => 'COMPLETENESS. Hunt: missing test coverage (esp. for the exact edge cases this change adds), untested defensive branches, missing docs updates, config added but not wired to every path, version bumps forgotten, and mismatches between what the PR description/design doc promises and what the diff actually delivers.',
  antipattern: () => 'ANTI-PATTERNS & FOOTGUNS. Hunt: silent failure, catch-and-ignore, hidden side effects, surprising defaults, values that render fine but explode at runtime, copy-paste drift, "temporary" hacks, and platform-specific anti-patterns for the stack in the diff.',
  // Full-panel cross-checks (>~500 changed lines): push these onto the standard
  // lens list on the OTHER elite model than their primary (see contracts.md).
  'correctness-b': () => 'LOGIC & CORRECTNESS, independent cross-check. Reason from scratch — do not assume the obvious bug is the only bug. Especially probe template/config rendering, shell quoting/expansion, and verification checks whose PASS condition can be satisfied by a broken state.',
  'security-b': () => 'SECURITY, independent cross-check on a different model. Focus extra on things that pass tests but fail or misbehave at deploy/runtime, and on whether elevated privileges are actually necessary or could be scoped down.',
}


const FINDINGS_SCHEMA = {
  type: 'object', required: ['lens', 'verdict', 'findings'],
  properties: {
    lens: { type: 'string' },
    verdict: { type: 'string' },
    findings: { type: 'array', items: {
      type: 'object',
      required: ['id', 'severity', 'title', 'location', 'rationale', 'recommendation', 'confidence'],
      properties: {
        id: { type: 'string' }, severity: { enum: ['HIGH', 'MEDIUM', 'LOW'] },
        title: { type: 'string' }, location: { type: 'string' },
        rationale: { type: 'string' }, recommendation: { type: 'string' },
        confidence: { type: 'number' },
      } } },
  },
}
const CLUSTERS_SCHEMA = {
  type: 'object', required: ['clusters'],
  properties: { clusters: { type: 'array', items: {
    type: 'object',
    required: ['id', 'severity', 'title', 'location', 'rationale', 'recommendation', 'signal_strength', 'raised_by'],
    properties: {
      id: { type: 'string' }, severity: { enum: ['HIGH', 'MEDIUM', 'LOW'] },
      title: { type: 'string' }, location: { type: 'string' },
      rationale: { type: 'string' }, recommendation: { type: 'string' },
      signal_strength: { type: 'integer' },
      raised_by: { type: 'array', items: { type: 'string' } },
    } } } },
}
const VERDICTS_SCHEMA = {
  type: 'object', required: ['verdicts'],
  properties: { verdicts: { type: 'array', items: {
    type: 'object', required: ['id', 'ruling', 'reason'],
    properties: {
      id: { type: 'string' },
      ruling: { enum: ['UPHOLD', 'DOWNGRADE', 'REJECT', 'DUPLICATE'] },
      new_severity: { enum: ['HIGH', 'MEDIUM', 'LOW', null] },
      duplicate_of: { type: ['string', 'null'] },
      reason: { type: 'string' },
    } } } },
}

function reviewerPrompt(l, pr) {
  return DEPTH[l.depth] + '\n\n' +
    'You are one lens on a WOLFPACK code-review panel — multiple independent reviewers on different models, whose findings are then adversarially validated by skeptics and merged.\n\n' +
    '## YOUR LENS\n' + BRIEFS[l.key](pr) + '\n\n' +
    'Stay in your lane: report issues under YOUR lens only; other lenses are covered by other reviewers.\n\n' +
    '## INPUT\nRead the review packet at ' + pr.packet + ' first — it holds the PR metadata, the diff, verified experiments, and a KNOWN/ACCEPTED list you must not re-raise. Then investigate the live checkout of the full repo at this PR\'s head: ' + pr.checkout + ' (read/grep/read-only shell only — git show, run tests in that checkout; NEVER modify files, never touch any directory other than the packet and the checkout named here).\n\n' +
    'RULES OF ENGAGEMENT\n' +
    '- Scope = the diff (plus just enough surrounding code to judge it). Do NOT review pre-existing code untouched by the change unless the diff makes it newly reachable.\n' +
    '- PRECISION OVER RECALL. A wrong finding costs more than a missed one. If you cannot defend it against a skeptic, set confidence < 0.5 or drop it.\n' +
    '- No taste-as-bug. Style opinions go in LOW at most, and only if defensible.\n' +
    '- Cite evidence (file:line, output of a command you ran). Do not invent facts.\n' +
    '- Cap yourself at your top 3-6 findings. An empty findings array is a valid answer.\n' +
    '- Severity: HIGH = correctness/security/data-loss/outage, merge-blocker. MEDIUM = real defect or maintainability risk. LOW = polish/nits/docs.\n' +
    'Your final output is consumed by a program: emit the structured result only.'
}

function dedupPrompt(reviews, pr) {
  return 'You are the DEDUP stage of a wolfpack review of ' + pr.id + '. Cluster these raw panel findings into stable ids F1..Fn. Merge findings that describe the same underlying defect even if worded differently or located a few lines apart. For each cluster: signal_strength = number of DISTINCT lenses that raised it; list them in raised_by; keep the clearest location, the strongest short rationale, the most concrete recommendation, and the HIGHEST severity claimed. Do NOT drop, judge, or add findings — clustering only.\n\nRAW FINDINGS (JSON):\n' + JSON.stringify(reviews)
}

function skepticPrompt(clustersJson, pr) {
  return 'You are an ADVERSARIAL VALIDATOR on a wolfpack code-review panel for ' + pr.id + '. Your job is NOT to find new issues — it is to try to FALSIFY the candidate findings, so only defensible ones survive. Be tough AND fair.\n\n' +
    'Review packet: ' + pr.packet + '. Live checkout at the PR head: ' + pr.checkout + '. For EACH candidate finding below, independently VERIFY it against the actual code (read/grep/git show/run the relevant test read-only) before ruling.\n\n' +
    'Rule REJECT / DOWNGRADE when a finding is: not supported by the diff (hallucinated line, wrong file, misread logic); already handled elsewhere (a guard/validation/test the reviewer missed); out of scope (pre-existing code the change did not touch or make newly reachable); listed in the packet\'s KNOWN/ACCEPTED items; speculative with no realistic trigger; a taste opinion dressed up as a bug; or a duplicate (mark duplicate_of).\n' +
    'Rule UPHOLD when you can restate the concrete failure and its trigger from the code.\n\n' +
    'INVALID-REFUTATION GUARD (critical): you must actually look at the referenced code. A REJECT justified only by "can\'t find it / not in the repo / file missing" is INVALID — that means YOU failed to open the file. Read the file first; if you still cannot verify either way, rule UPHOLD (uncertain), never REJECT.\n\n' +
    'Downstream kill rule (FYI): a finding is dropped only if ' + profileOf(pr).killRule + '. You are READ-ONLY; never modify files.\n\n' +
    'CANDIDATE FINDINGS (JSON):\n' + clustersJson +
    '\nRule on EVERY id. Your final output is consumed by a program: emit the structured result only.'
}


// ---------------------------------------------------------------------------
// PANEL PROFILES — select per target with pr.profile ('standard' when absent).
//   standard: the contracts.md default panel — elite seats (fable/opus) at
//             max/high effort, 3 skeptics (two elite, one xhigh sonnet), dockets
//             of <= 8. Kill = >=2 of 3 valid REJECTs.
//   economy:  one elite seat (opus on correctness), nothing above `high` effort,
//             haiku on the three cheap lenses, 2 skeptics (sonnet/high +
//             opus/medium), dockets of <= 12 (fewer packet re-reads).
//             Kill = BOTH skeptics REJECT with a valid reason. Roughly 4-6x
//             cheaper per target; use when usage limits bite or for small /
//             low-risk diffs. Report the 2-vote quorum honestly.
//   frugal:   sonnet/haiku only, nothing above `medium` effort, haiku dedup,
//             2 skeptics (sonnet/medium + haiku/medium), dockets of <= 15.
//             Kill = BOTH REJECT validly. The floor: use when usage limits are
//             nearly gone; expect more noise for Stage 4 to filter.
// pr.alt === true swaps the two lead seats' models so an API-safeguard flag on
// one model costs half a lens across the batch, not the whole lens.
// Resume caching matches on byte-identical prompts/opts: when editing this
// script for a resumed run, change nothing except the calls you intend to
// re-run (same meta, same args, same prompt text).
// ---------------------------------------------------------------------------
const PROFILES = {
  standard: {
    lenses: pr => {
      const A = pr.alt ? 'opus' : 'fable', B = pr.alt ? 'fable' : 'opus'
      return [
        { key: 'correctness',  model: A,        effort: 'max',    depth: 'max' },
        { key: 'security',     model: B,        effort: 'max',    depth: 'max' },
        { key: 'domain',       model: 'opus',   effort: 'max',    depth: 'max' },
        { key: 'lifecycle',    model: A,        effort: 'high',   depth: 'high' },
        { key: 'quality',      model: 'sonnet', effort: 'medium', depth: 'med' },
        { key: 'completeness', model: 'sonnet', effort: 'medium', depth: 'med' },
        { key: 'antipattern',  model: 'haiku',  effort: 'low',    depth: 'min' },
      ]
    },
    skeptics: pr => {
      const A = pr.alt ? 'opus' : 'fable', B = pr.alt ? 'fable' : 'opus'
      return [
        { key: 'skeptic-a', model: A,        effort: 'high' },
        { key: 'skeptic-b', model: B,        effort: 'xhigh' },
        { key: 'skeptic-c', model: 'sonnet', effort: 'xhigh' },
      ]
    },
    dedup: { model: 'sonnet', effort: 'medium' },
    docket: 8,
    killRule: '>=2 of 3 skeptics REJECT it with a valid reason',
  },
  economy: {
    lenses: pr => {
      const A = pr.alt ? 'sonnet' : 'opus', B = pr.alt ? 'opus' : 'sonnet'
      return [
        { key: 'correctness',  model: A,        effort: 'high',   depth: 'high' },
        { key: 'security',     model: B,        effort: 'high',   depth: 'high' },
        { key: 'domain',       model: 'sonnet', effort: 'medium', depth: 'med' },
        { key: 'lifecycle',    model: 'sonnet', effort: 'medium', depth: 'med' },
        { key: 'quality',      model: 'haiku',  effort: 'low',    depth: 'min' },
        { key: 'completeness', model: 'haiku',  effort: 'low',    depth: 'min' },
        { key: 'antipattern',  model: 'haiku',  effort: 'low',    depth: 'min' },
      ]
    },
    skeptics: pr => [
      { key: 'skeptic-a', model: 'sonnet', effort: 'high' },
      { key: 'skeptic-b', model: 'opus',   effort: 'medium' },
    ],
    dedup: { model: 'sonnet', effort: 'low' },
    docket: 12,
    killRule: 'BOTH of the 2 skeptics REJECT it with a valid reason',
  },
  frugal: {
    // Cheapest sane panel: no fable/opus anywhere. sonnet on the two lead
    // lenses at medium effort, haiku on the other five, haiku dedup, 2 skeptics
    // (sonnet/medium + haiku/medium), dockets of <= 15. Kill = BOTH skeptics
    // REJECT with a valid reason. Roughly 2-3x cheaper than economy again;
    // the orchestrator's Stage-4 adjudication carries more of the precision
    // burden, so re-verify every HIGH against the code before reporting it.
    lenses: pr => [
      { key: 'correctness',  model: 'sonnet', effort: 'medium', depth: 'med' },
      { key: 'security',     model: 'sonnet', effort: 'medium', depth: 'med' },
      { key: 'domain',       model: 'haiku',  effort: 'medium', depth: 'med' },
      { key: 'lifecycle',    model: 'haiku',  effort: 'low',    depth: 'min' },
      { key: 'quality',      model: 'haiku',  effort: 'low',    depth: 'min' },
      { key: 'completeness', model: 'haiku',  effort: 'low',    depth: 'min' },
      { key: 'antipattern',  model: 'haiku',  effort: 'low',    depth: 'min' },
    ],
    skeptics: pr => [
      { key: 'skeptic-a', model: 'sonnet', effort: 'medium' },
      { key: 'skeptic-b', model: 'haiku',  effort: 'medium' },
    ],
    dedup: { model: 'haiku', effort: 'low' },
    docket: 15,
    killRule: 'BOTH of the 2 skeptics REJECT it with a valid reason',
  },
}
function profileOf(pr) {
  const p = PROFILES[pr.profile]
  if (!p) throw new Error('unknown panel profile "' + pr.profile + '" on target ' + pr.id + ' (use standard|economy|frugal)')
  return p
}
function chunk(xs, n) { const out = []; for (let i = 0; i < xs.length; i += n) out.push(xs.slice(i, i + n)); return out }

// normalize once, then fail fast on a typo'd profile before any agent spends tokens
args.forEach(pr => { pr.profile = pr.profile || 'standard'; profileOf(pr) })
const byProfile = args.reduce((m, pr) => { m[pr.profile] = (m[pr.profile] || 0) + 1; return m }, {})
log('Wolfpack: ' + args.length + ' targets (' + Object.entries(byProfile).map(([k, n]) => n + ' ' + k).join(', ') + ') x (7 lenses + dedup + skeptics, docketed) — a batch panel review is the requested scale')

const results = await pipeline(
  args,
  pr => {
    const LENSES = profileOf(pr).lenses(pr)
    return parallel(LENSES.map(l => () =>
      agent(reviewerPrompt(l, pr), {
        label: l.key + '#' + pr.id, phase: 'Breadth',
        schema: FINDINGS_SCHEMA, model: l.model, effort: l.effort,
      })
    )).then(rs => ({
      reviews: rs.map((r, i) => r ? { lens: LENSES[i].key, verdict: r.verdict, findings: r.findings } : null).filter(Boolean),
      gaps: rs.map((r, i) => r ? null : LENSES[i].key).filter(Boolean),
    }))
  },
  (st, pr) => {
    const total = st.reviews.reduce((n, r) => n + r.findings.length, 0)
    log(pr.id + ': ' + total + ' raw findings from ' + st.reviews.length + ' lenses' + (st.gaps.length ? ' (gaps: ' + st.gaps.join(',') + ')' : ''))
    if (total === 0) return Promise.resolve({ ...st, clusters: [] })
    return agent(dedupPrompt(st.reviews, pr), {
      label: 'dedup#' + pr.id, phase: 'Dedup',
      schema: CLUSTERS_SCHEMA, model: profileOf(pr).dedup.model, effort: profileOf(pr).dedup.effort,
    }).then(d => ({ ...st, clusters: d.clusters }))
  },
  (st, pr) => {
    const P = profileOf(pr), SKEPTICS = P.skeptics(pr)
    const base = {
      pr: pr.id, profile: pr.profile, quorum: SKEPTICS.length,
      lensVerdicts: st.reviews.map(r => ({ lens: r.lens, verdict: r.verdict })),
      gaps: st.gaps, clusters: st.clusters,
    }
    if (!st.clusters.length) return Promise.resolve({ ...base, skeptics: [] })
    const dockets = chunk(st.clusters, P.docket)
    log(pr.id + ': ' + st.clusters.length + ' clusters -> ' + dockets.length + ' docket(s) per skeptic')
    return parallel(SKEPTICS.map(s => () =>
      parallel(dockets.map((d, di) => () =>
        agent(skepticPrompt(JSON.stringify(d), pr), {
          label: s.key + '#' + pr.id + (dockets.length > 1 ? '/' + (di + 1) : ''), phase: 'Skeptics',
          schema: VERDICTS_SCHEMA, model: s.model, effort: s.effort,
        })
      )).then(parts => {
        const ok = parts.filter(Boolean)
        return ok.length ? { skeptic: s.key, dockets_done: ok.length, dockets_total: dockets.length, verdicts: ok.flatMap(p => p.verdicts) } : null
      })
    )).then(vs => ({ ...base, skeptics: vs.filter(Boolean) }))
  }
)
return results.filter(Boolean)
