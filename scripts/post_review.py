#!/usr/bin/env python3
"""
Reusable inline-PR-review poster for the wolfpack panel.

Posts a single review (default event=COMMENT so it never overrides existing
approvals) with a markdown summary + line-anchored inline comments, via the
GitHub reviews API. Works on GitHub Enterprise (set the GH_HOST environment
variable — it wins — or edit the GH_HOST constant below).

Inline comments can ONLY attach to lines that appear in the PR diff (added or
context lines). If HEAD == PR head SHA, file line numbers == diff line numbers.

Usage:
    1. Edit REPO / PR / COMMIT / GH_HOST and the COMMENTS list below
       (or import build_payload / post from another script).
    2. Dry run:   python3 post_review.py
    3. Post:      python3 post_review.py --post

Summary body: put your synthesized review in SUMMARY_PATH (e.g. review-<pr>.md).
"""
import json
import os
import subprocess
import sys
import tempfile

# ---- configure per PR --------------------------------------------------------
GH_HOST = os.environ.get("GH_HOST") or "github.com"  # env wins, matching pr-review.md's GH_HOST=<host> convention
REPO = "OWNER/REPO"                            # e.g. your-org/your-repo
PR = 0
COMMIT = "<pr head sha>"                       # must match git rev-parse HEAD
EVENT = "COMMENT"                              # COMMENT | REQUEST_CHANGES | APPROVE
SUMMARY_PATH = "review.md"                     # markdown for the top-level review body

# Each inline comment: path is repo-relative; line is the NEW-side file line;
# side "RIGHT" = the post-change version. Use start_line+line for multi-line.
COMMENTS = [
    # {"path": "path/to/file", "line": 92, "side": "RIGHT", "body": "**Finding** ..."},
]
# -----------------------------------------------------------------------------


def build_payload():
    body = ""
    if SUMMARY_PATH and os.path.exists(SUMMARY_PATH):
        with open(SUMMARY_PATH) as f:
            body = f.read()
    payload = {"commit_id": COMMIT, "event": EVENT, "body": body}
    if COMMENTS:
        payload["comments"] = COMMENTS
    return payload


def post(payload):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(payload, f, indent=2)
        payload_path = f.name
    env = {**os.environ, "GH_HOST": GH_HOST}   # resolved above: env value if set, else the constant
    out = subprocess.run(
        ["gh", "api", "--method", "POST",
         f"/repos/{REPO}/pulls/{PR}/reviews", "--input", payload_path],
        env=env, capture_output=True, text=True,
    )
    print("STDOUT:", out.stdout[:1000])
    print("STDERR:", out.stderr[:1000])
    return out.returncode


def main():
    payload = build_payload()
    print(f"Review for {REPO}#{PR} @ {COMMIT[:10]} | event={EVENT} | "
          f"{len(payload.get('comments', []))} inline comments | "
          f"summary {len(payload['body'])} chars")
    if "--post" in sys.argv:
        sys.exit(post(payload))
    print("dry run — pass --post to submit")


if __name__ == "__main__":
    main()
