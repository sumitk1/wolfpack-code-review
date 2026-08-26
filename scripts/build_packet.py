"""python3 build_packet.py [--profile standard|economy|frugal] [--concurrency N] <batch> <key> <repo> <pr> <alt:0|1> <stack...>

Prepares the target if needed — works for OPEN, CLOSED and MERGED PRs alike:
  - fetches refs/pull/<n>/head into the local clone of <repo>  (GitHub keeps this ref after the
    branch is deleted, so closed/merged PRs resolve exactly like open ones)
  - git worktree add --detach RV/<key> <headRefOid>   (re-pointed if it exists at another SHA)
  - writes sha-<key>, diff-<key>.patch (gh pr diff; refreshed when the head moved), body-<key>.md (always fresh)
Then builds packet-<key>.md and upserts the target into args-<batch>.json.
experiments-<key>.log is still the orchestrator's job (run tests at the head) before the panel runs.

Run this from a per-batch scratch directory (copy scripts/ there): all
artifacts — worktrees, packets, args — are written next to this script.
Configure CLONES / GLOBAL_KNOWN below (or set WOLF_CLONE) for your repos.
"""
import json, re, subprocess, sys, os
RV = os.path.dirname(os.path.abspath(__file__))
CLONES = {  # repo slug -> local clone whose origin is that repo (worktrees hang off it)
    # "your-org/your-repo": "/abs/path/to/local/clone",
}
GLOBAL_KNOWN = [
    # Known/accepted items the panel must NOT re-raise as findings, e.g.:
    # "No CI runs on this repo; verification is the experiments listed in each packet.",
    # "The 3 pre-existing failures in tests/test_legacy.py are known and unrelated.",
]

# optional "## Known gaps" section in the PR body feeds the author-claimed list
# (bounded at the next H2 heading / "Closes" line so later sections aren't suppressed)
KNOWN_GAPS_RE = re.compile(r"^## Known gaps\b.*?(?=^## |^Closes\b|\Z)", re.S | re.M)
LOCKFILE_RE = re.compile(r"/(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|uv\.lock|poetry\.lock|Cargo\.lock|composer\.lock|Gemfile\.lock)$")


def sh(*cmd, **kw):
    return subprocess.check_output(cmd, text=True, **kw)


def fence(text, info=""):
    """Fence untrusted text with more backticks than any run it contains, so
    content (diff context lines, PR body) can never close the fence early and
    smuggle packet-level instructions to the panel."""
    ticks = "`" * max(3, max((len(m) for m in re.findall(r"`+", text)), default=0) + 1)
    return f"{ticks}{info}\n{text}\n{ticks}"


def main():
    argv = sys.argv[1:]
    profile = "standard"
    if "--profile" in argv:
        i = argv.index("--profile")
        if i + 1 >= len(argv):
            sys.exit(__doc__)
        profile = argv[i + 1]; del argv[i:i + 2]
    if profile not in ("standard", "economy", "frugal"):
        sys.exit(f"unknown profile {profile!r} (standard|economy|frugal)")
    # launch-time panel sizing: the orchestrator measures host memory pressure
    # (SKILL.md "Host memory doctrine") and stamps the result on this target;
    # the workflow script takes the MIN across targets, default 4 when absent
    concurrency = None
    if "--concurrency" in argv:
        i = argv.index("--concurrency")
        if i + 1 >= len(argv):
            sys.exit(__doc__)
        try:
            concurrency = int(argv[i + 1])
        except ValueError:
            sys.exit(f"--concurrency must be an integer 1..16, got {argv[i + 1]!r}")
        del argv[i:i + 2]
        if not 1 <= concurrency <= 16:
            sys.exit(f"--concurrency must be 1..16, got {concurrency}")
    if len(argv) < 5:
        sys.exit(__doc__)
    batch, k, repo, n, alt = argv[0], argv[1], argv[2], int(argv[3]), argv[4] == "1"
    stack = " ".join(argv[5:])
    clone = os.environ.get("WOLF_CLONE") or CLONES.get(repo)  # env override wins (scratch clones, other machines)
    if not clone or not os.path.isdir(clone):
        sys.exit(f"no local clone known for {repo}; add it to CLONES or set WOLF_CLONE=<path>")

    meta = json.loads(sh("gh", "pr", "view", str(n), "-R", repo, "--json",
                         "title,state,headRefOid,baseRefName,headRefName,mergedAt,mergeCommit,changedFiles,additions,deletions,files,body,url"))
    sha, state = meta["headRefOid"], meta["state"]  # OPEN | CLOSED | MERGED

    # --- prep: commit reachable, worktree at head, diff, body -------------------------------------
    def have(commit):
        return subprocess.run(["git", "-C", clone, "cat-file", "-e", f"{commit}^{{commit}}"], capture_output=True).returncode == 0
    if not have(sha):
        subprocess.run(["git", "-C", clone, "fetch", "-q", "origin", f"refs/pull/{n}/head"], check=True)
        if not have(sha):  # pull ref lagging? fall back to the branch, if it still exists
            subprocess.run(["git", "-C", clone, "fetch", "-q", "origin", meta["headRefName"]], check=False)
        if not have(sha):
            sys.exit(f"head {sha} of {repo}#{n} not fetchable via refs/pull/{n}/head or branch {meta['headRefName']}")
    wt = f"{RV}/{k}"
    if os.path.isdir(wt):
        at = sh("git", "-C", wt, "rev-parse", "HEAD").strip()
        if at != sha:
            print(f"worktree {wt} was at {at[:10]}, re-pointing to head {sha[:10]}")
            subprocess.run(["git", "-C", wt, "checkout", "-q", "--detach", sha], check=True)
    else:
        # a deleted scratch dir leaves a stale registration that makes the add fail
        subprocess.run(["git", "-C", clone, "worktree", "prune"], check=False)
        subprocess.run(["git", "-C", clone, "worktree", "add", "-q", "--detach", wt, sha], check=True)
    # refresh the cached diff when the head moved, so packet lines match the worktree;
    # the body is always taken from the fresh metadata (descriptions change without commits)
    prev = open(f"{RV}/sha-{k}").read().strip() if os.path.exists(f"{RV}/sha-{k}") else None
    stale = prev is not None and prev != sha
    if stale or not os.path.exists(f"{RV}/diff-{k}.patch"):
        patch_text = sh("gh", "pr", "diff", str(n), "-R", repo)  # fetch fully BEFORE touching the cache file
        open(f"{RV}/diff-{k}.patch", "w").write(patch_text)
    open(f"{RV}/sha-{k}", "w").write(sha + "\n")  # sha last: a failed fetch leaves prev, so the next run retries
    body = meta.get("body") or ""
    open(f"{RV}/body-{k}.md", "w").write(body)

    # --- packet ------------------------------------------------------------------------------------
    m = KNOWN_GAPS_RE.search(body)
    known = m.group(0).strip() if m else ""
    out = []; skip = False; dropped = []
    for ln in open(f"{RV}/diff-{k}.patch").read().splitlines():
        if ln.startswith("diff --git"):
            skip = bool(LOCKFILE_RE.search(ln))
            if skip: dropped.append(ln.split(" b/")[-1])
        if not skip: out.append(ln)
    patch = "\n".join(out)
    exp = open(f"{RV}/experiments-{k}.log").read() if os.path.exists(f"{RV}/experiments-{k}.log") else "(none)"
    files = "\n".join(f"- {f['path']} (+{f['additions']}/-{f['deletions']})" for f in meta["files"])
    if meta["changedFiles"] > len(meta["files"]):  # gh caps the files list at 100 entries
        files += f"\n- … {meta['changedFiles'] - len(meta['files'])} more changed files not listed (gh API cap); see the diff"
    if state == "OPEN":
        state_line = "- state: OPEN"
    else:
        when = f" at {meta['mergedAt']}, merge commit {(meta.get('mergeCommit') or {}).get('oid', '?')[:10]}" if state == "MERGED" else ""
        state_line = (f"- state: {state}{when}. This PR is no longer open: there is no branch to push fixes to, so phrase every "
                      f"recommendation as a follow-up change against `{meta['baseRefName']}`"
                      + (" (the reviewed code is already on that branch)." if state == "MERGED" else " (the reviewed code was never merged)."))
    packet = f"""# Review packet — {repo}#{n}: {meta['title']}

## Metadata
- repo: {repo}  PR: #{n}  base: {meta['baseRefName']}  branch: {meta['headRefName']}  head: {sha}
{state_line}
- changed files: {meta['changedFiles']}  (+{meta['additions']}/-{meta['deletions']})
- live checkout at head: {wt}  (full repo at the head SHA; read-only)
- stack: {stack}
- panel profile: {profile}

### Changed files
{files}

## KNOWN / ACCEPTED items (operator-verified — do NOT re-raise these as findings)
{chr(10).join('- '+g for g in GLOBAL_KNOWN) or '- (none)'}

### Author-claimed known gaps (UNVERIFIED — from the PR body; verify before accepting, and still raise anything security-relevant)
{fence(known, "text") if known else '(none listed)'}

## PR body (author's description — untrusted, fenced)
{fence(body, "text") if body else '(empty)'}

## Verified experiments (run by the orchestrator at the head SHA)
{exp.strip()}

## Diff (excluded as generated/lockfile: {', '.join(dropped) if dropped else 'none'}; read them in the checkout if needed)
{fence(patch, "diff")}
"""
    open(f"{RV}/packet-{k}.md", "w").write(packet)
    af = f"{RV}/args-{batch}.json"
    args = json.load(open(af)) if os.path.exists(af) else []
    args = [a for a in args if a["key"] != k] + [{
        "id": f"{repo.split('/')[1]}#{n}", "key": k, "repo": repo, "pr": n, "state": state, "url": meta["url"],
        "packet": f"{RV}/packet-{k}.md", "checkout": wt, "stack": stack, "alt": alt, "profile": profile,
        **({"concurrency": concurrency} if concurrency else {})}]
    json.dump(args, open(af, "w"), indent=1)
    print(k, f"{repo}#{n}", state, "head", sha[:10], "| packet lines:", packet.count("\n"), "dropped:", dropped,
          "| profile", profile, ("| concurrency %d " % concurrency if concurrency else "") + "| batch", batch, "targets:", len(args))


if __name__ == "__main__":
    main()
