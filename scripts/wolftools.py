"""Generic Stage-4 tooling for wolfpack batches.
  python3 wolftools.py split <workflow.output> <batchname>      -> findings-<key>.json per target + adjudication table
  python3 wolftools.py table <batchname>                        -> print table again
  python3 wolftools.py report <batchname> <adjudication.json>   -> out/review-<key>.md per target (+ inline-<key>.json)
  python3 wolftools.py post <batchname> <key> [--dry]           -> POST COMMENT review with inline comments
adjudication.json: { "<key>": {"verdict": "...", "final": {"F1":"HIGH"|"MEDIUM"|"LOW"|"DISMISSED"}, "note": {"F1":"..."}, "panel": "..."} }
"""
import json, re, subprocess, sys, os
RV = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(RV, "out"); os.makedirs(OUT, exist_ok=True)
NLENS = 7

def load_args(batch):
    return {a["key"]: a for a in json.load(open(f"{RV}/args-{batch}.json"))}

def split(output_file, batch):
    doc = json.load(open(output_file))
    res = doc["result"] if isinstance(doc, dict) and "result" in doc else doc
    args = load_args(batch); byid = {a["id"]: k for k, a in args.items()}
    keys = []
    for r in res:
        k = byid[r["pr"]]; keys.append(k)
        json.dump(r, open(f"{RV}/findings-{k}.json", "w"), indent=1)
    json.dump(keys, open(f"{RV}/keys-{batch}.json", "w"))
    table(batch)

PANEL_DESC = {
    "standard": "7 lens reviewers across 4 Claude models + 3 adversarial skeptics (standard profile)",
    "economy": "7 lens reviewers (economy profile: opus/sonnet/haiku, no max/xhigh effort) + 2 adversarial skeptics",
    "frugal": "7 lens reviewers (frugal profile: sonnet/haiku only, nothing above medium effort) + 2 adversarial skeptics (sonnet/medium, haiku/medium)",
}
KILL_DESC = {3: "≥2/3 REJECT with a valid reason", 2: "both skeptics REJECT with a valid reason (2-vote quorum)"}

def votes_for(skeptics):
    out = {}
    for s in skeptics or []:
        nm = s["skeptic"].replace("skeptic-", "")
        for v in s["verdicts"]:
            out.setdefault(v["id"], []).append((nm, v["ruling"] + (f"→{v['new_severity']}" if v.get("new_severity") else ""), v.get("reason", "")))
    return out

def table(batch):
    for k in json.load(open(f"{RV}/keys-{batch}.json")):
        d = json.load(open(f"{RV}/findings-{k}.json")); v = votes_for(d["skeptics"])
        print(f"\n######## {k} ({d['pr']})  lenses={len(d['lensVerdicts'])} gaps={d['gaps']} skeptics={[ (s['skeptic'], s.get('dockets_done'), s.get('dockets_total')) for s in d['skeptics']]}")
        for lv in d["lensVerdicts"]: print(f"   [{lv['lens']}] {lv['verdict'][:160]}")
        for c in d["clusters"]:
            print(f"{c['id']:4} {c['severity']:6} sig{c['signal_strength']} {c['location'][:50]:50} | {c['title'][:95]}")
            print(f"      votes={[f'{a}:{b}' for a,b,_ in v.get(c['id'], [])]}")

def report(batch, adj_file):
    ADJ = json.load(open(adj_file)); args = load_args(batch)
    for k, a in ADJ.items():
        if k not in args: continue
        d = json.load(open(f"{RV}/findings-{k}.json")); t = args[k]
        clusters = {c["id"]: c for c in d["clusters"]}; votes = votes_for(d["skeptics"])
        vstr = lambda i: "; ".join(f"{nm} {tag}" for nm, tag, _ in votes.get(i, []))
        L = [f"# Wolfpack Review — {t['repo']}#{t['pr']}",
             f"_Panel: {a.get('panel', PANEL_DESC.get(d.get('profile', 'standard'), PANEL_DESC['standard']))}. Mode: pr-review. Head: `{open(f'{RV}/sha-{k}').read().strip()[:10]}`. Every finding below survived an adversarial skeptic pass; kill rule = {KILL_DESC.get(d.get('quorum', 3), KILL_DESC[3])} (a \"can't find it\" REJECT is void)._",
             "", "## Verdict", a["verdict"], ""]
        for bucket, prefix in (("HIGH", "H"), ("MEDIUM", "M")):
            ids = sorted([i for i in clusters if a["final"].get(i) == bucket], key=lambda i: (-clusters[i]["signal_strength"], int(re.sub(r"\D", "", i) or 0)))
            L.append(f"## {bucket.title()}")
            if not ids: L.append("_None._")
            for n, i in enumerate(ids, 1):
                c = clusters[i]
                L += [f"### {prefix}{n} ({i}) — {c['title']}", f"`{c['location']}` _(signal {c['signal_strength']}/{NLENS}; skeptics: {vstr(i)})_", c["rationale"].strip(), f"**Fix:** {c['recommendation'].strip()}"]
                if i in a.get("note", {}): L.append(f"> **Orchestrator:** {a['note'][i]}")
                L.append("")
            L.append("")
        ids = sorted([i for i in clusters if a["final"].get(i) == "LOW"], key=lambda i: int(re.sub(r"\D", "", i) or 0))
        L.append("## Low")
        if not ids: L.append("_None._")
        for n, i in enumerate(ids, 1):
            c = clusters[i]; extra = f" _{a['note'][i]}_" if i in a.get("note", {}) else ""
            L.append(f"- **L{n} ({i})** — {c['title']} `{c['location']}` (signal {c['signal_strength']}; skeptics: {vstr(i)}). **Fix:** {c['recommendation'].strip()}{extra}")
        L += ["", "## Considered and dismissed (adversarial validation)"]
        dis = [i for i in clusters if a["final"].get(i) == "DISMISSED"]
        if not dis: L.append("_None._")
        for i in dis:
            c = clusters[i]; rej = [1 for _, tag, _ in votes.get(i, []) if tag.startswith("REJECT")]
            L.append(f"- **{i}** — {c['title']} `{c['location']}` — REJECTED by {len(rej)}/{len(votes.get(i, []))} skeptics. {a.get('note', {}).get(i, '')}")
        missing = [i for i in clusters if i not in a["final"]]
        if missing: print(f"!! {k}: unadjudicated clusters {missing}")
        L += ["", "_Generated by the wolfpack-code-review skill (Claude-only panel). Reviewers and skeptics were read-only and worked from a shared packet (diff, verified experiments, known/accepted items)._"]
        open(f"{OUT}/review-{k}.md", "w").write("\n".join(L))
        # inline anchors for HIGH/MEDIUM
        valid = right_lines(f"{RV}/diff-{k}.patch"); cm = []; skipped = []
        for i, c in clusters.items():
            sev = a["final"].get(i)
            if sev not in ("HIGH", "MEDIUM"): continue
            placed = None
            for path, lo, hi in anchors(c["location"]):
                vl = valid.get(path) or valid.get(path.lstrip("./"))
                if not vl: continue
                cand = [l for l in range(lo, hi + 1) if l in vl]
                if cand: placed = (path, cand[0]); break
            if not placed: skipped.append((i, c["location"])); continue
            body = f"**[wolfpack] {sev} — {i}: {c['title']}**\n\n{c['rationale'].strip()}\n\n**Fix:** {c['recommendation'].strip()}"
            if i in a.get("note", {}): body += f"\n\n_Orchestrator: {a['note'][i]}_"
            cm.append({"path": placed[0], "line": placed[1], "side": "RIGHT", "body": body})
        json.dump(cm, open(f"{OUT}/inline-{k}.json", "w"), indent=1)
        counts = {b: sum(1 for i in clusters if a["final"].get(i) == b) for b in ("HIGH", "MEDIUM", "LOW", "DISMISSED")}
        print(k, counts, f"inline={len(cm)}", f"unanchored={skipped}" if skipped else "")

def right_lines(patch):
    """NEW-side line numbers that exist in the diff (added or context lines) per file.
    Only lines inside a hunk count — file headers and metadata between hunks must
    not inflate the set, or an inline comment could anchor to a line the GitHub
    API rejects (which voids the whole review)."""
    out = {}; path = None; new = None
    for ln in open(patch, encoding="utf-8", errors="replace"):
        if ln.startswith("diff --git"):
            path = None; new = None; continue
        if ln.startswith("+++ ") and new is None:  # header only outside hunks: an added '++ x' line is '+++ x' inside one
            p = ln[4:].strip(); path = p[2:] if p.startswith("b/") else p; out.setdefault(path, set()); continue
        m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", ln)
        if m: new = int(m.group(1)); continue
        if new is None or path is None: continue
        if ln.startswith("+"): out[path].add(new); new += 1
        elif ln.startswith("-") or ln.startswith("\\"): pass
        else: out[path].add(new); new += 1
    return out

LOC = re.compile(r"([A-Za-z0-9_./-]+\.[A-Za-z0-9]+|\.dockerignore|\.gitignore|\.env\.example|Dockerfile|Makefile):(\d+)(?:[-–](\d+))?")
def anchors(loc):
    for m in LOC.finditer(loc): yield m.group(1), int(m.group(2)), int(m.group(3) or m.group(2))

def post(batch, k, dry=False):
    t = load_args(batch)[k]; sha = open(f"{RV}/sha-{k}").read().strip()
    payload = {"commit_id": sha, "event": "COMMENT", "body": open(f"{OUT}/review-{k}.md").read(), "comments": json.load(open(f"{OUT}/inline-{k}.json"))}
    p = f"{OUT}/payload-{k}.json"; json.dump(payload, open(p, "w"))
    print(f"{t['repo']}#{t['pr']} @ {sha[:10]}: body {len(payload['body'])} chars, {len(payload['comments'])} inline")
    if dry: return
    r = subprocess.run(["gh", "api", "--method", "POST", f"/repos/{t['repo']}/pulls/{t['pr']}/reviews", "--input", p, "--jq", '"posted review id=\\(.id) state=\\(.state) url=\\(.html_url)"'], capture_output=True, text=True)
    print(r.stdout.strip() or r.stderr.strip()[:500])
    if r.returncode: sys.exit(r.returncode)  # a rejected review (e.g. 422 bad anchor) must not exit 0

if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "split": split(sys.argv[2], sys.argv[3])
    elif cmd == "table": table(sys.argv[2])
    elif cmd == "report": report(sys.argv[2], sys.argv[3])
    elif cmd == "post": post(sys.argv[2], sys.argv[3], "--dry" in sys.argv)
