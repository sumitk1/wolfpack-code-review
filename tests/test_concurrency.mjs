// Concurrency-governor tests for scripts/wolfpack.js.
// Run: node tests/test_concurrency.mjs
//
// Stubs the Workflow harness globals (agent/parallel/pipeline/log/args) and
// verifies the host-resource governor:
//   1. default cap: never more than MAX_CONCURRENT (4) agent() calls in
//      flight, with 2 standard-profile targets whose breadth stages overlap
//      and whose clusters force multiple skeptic dockets
//   2. launch-time override: a `concurrency` field on the args targets wins
//      (min across targets, so the most conservative request holds)
//   3. fail-fast: an invalid concurrency value throws before any agent runs
// Without a governor the script fills every harness slot (min(16, cpus-2) —
// 12 on a 14-core host) with agents that each may spawn shell work.

import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const DEFAULT_CAP = 4 // must match the fallback in scripts/wolfpack.js

// 12 findings per lens -> clusters > docket cap (8) -> multiple skeptic dockets
const fakeFindings = lens => Array.from({ length: 12 }, (_, i) => ({
  id: `${lens}-${i + 1}`, severity: 'LOW', title: `t${i}`, location: 'f.py:1',
  rationale: 'r', recommendation: 'x', confidence: 0.9,
}))

// The Workflow harness wraps the script body in an async function (top-level
// `return` is legal there); reproduce that wrapping here.
const scriptPath = join(dirname(fileURLToPath(import.meta.url)), '..', 'scripts', 'wolfpack.js')
const src = readFileSync(scriptPath, 'utf8').replace('export const meta', 'const meta')
const wrapped = new Function('agent', 'parallel', 'pipeline', 'log', 'args',
  'return (async () => {\n' + src + '\n})()')

async function runScenario(args) {
  let inflight = 0
  let peak = 0
  const tick = () => new Promise(r => setTimeout(r, 5))
  const agent = async (prompt, opts = {}) => {
    inflight++
    peak = Math.max(peak, inflight)
    await tick()
    inflight--
    if (opts.phase === 'Breadth') {
      const lens = (opts.label || 'l').split('#')[0]
      return { lens, verdict: 'v', findings: fakeFindings(lens) }
    }
    if (opts.phase === 'Dedup') {
      // 20 clusters -> 3 dockets of 8/8/4 per skeptic
      return { clusters: Array.from({ length: 20 }, (_, i) => ({
        id: `F${i + 1}`, severity: 'LOW', title: 't', location: 'f.py:1',
        rationale: 'r', recommendation: 'x', signal_strength: 1, raised_by: ['correctness'],
      })) }
    }
    return { verdicts: [{ id: 'F1', ruling: 'UPHOLD', reason: 'r' }] }
  }
  const parallel = thunks => Promise.all(thunks.map(t => t().catch(() => null)))
  const pipeline = (items, ...stages) => Promise.all(items.map(async (item, i) => {
    let v = item
    for (const s of stages) v = await s(v, item, i)
    return v
  }))
  const results = await wrapped(agent, parallel, pipeline, () => {}, args)
  return { peak, results }
}

const target = (id, extra = {}) => ({
  id, packet: `/tmp/p-${id}.md`, checkout: `/tmp/c-${id}`, stack: 'py', profile: 'standard', ...extra,
})
let failed = false
const check = (ok, msg) => { console.log((ok ? 'PASS' : 'FAIL') + ': ' + msg); if (!ok) failed = true }

// 1. default cap
{
  const { peak, results } = await runScenario([target('r#1'), target('r#2')])
  check(peak <= DEFAULT_CAP, `default cap: peak ${peak} <= ${DEFAULT_CAP}`)
  check(peak >= 2, `default cap: peak ${peak} >= 2 (not fully serialized)`)
  check(results.length === 2 && results.every(r => r.skeptics.length), 'default cap: 2 targets completed')
}

// 2. launch-time override, min across targets wins
{
  const { peak, results } = await runScenario([target('r#1', { concurrency: 3 }), target('r#2', { concurrency: 2 })])
  check(peak <= 2, `override: peak ${peak} <= 2 (min of 3 and 2)`)
  check(results.length === 2 && results.every(r => r.skeptics.length), 'override: 2 targets completed')
}

// 3. invalid value fails fast
{
  const bad = await runScenario([target('r#1', { concurrency: 0 })]).then(() => null, e => e)
  check(bad instanceof Error && /concurrency/.test(bad.message), `invalid concurrency throws (got: ${bad && bad.message})`)
}

process.exit(failed ? 1 : 0)
