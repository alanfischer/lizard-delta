#!/usr/bin/env python3
"""
Run lizard on the merge-base versions of changed files.
Produces lizard_base_report.csv for delta comparison in lizard_to_code_quality.py.

Usage: lizard-base [--out lizard_base_report.csv] [--base-ref COMMIT] [--target-branch BRANCH]
Locally runnable: lizard-base
"""
import argparse
import subprocess
import sys
import tempfile
import os


def get_merge_base(target_branch):
    for ref in [f"origin/{target_branch}", target_branch]:
        r = subprocess.run(["git", "merge-base", "HEAD", ref], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    # The ref may not have been fetched (e.g. CI runners often only fetch the
    # source branch).  Try fetching it before falling back to HEAD~1.
    subprocess.run(["git", "fetch", "origin", target_branch], capture_output=True)
    for ref in [f"origin/{target_branch}", target_branch]:
        r = subprocess.run(["git", "merge-base", "HEAD", ref], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    r = subprocess.run(["git", "rev-parse", "HEAD~1"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def get_changed_files(base_ref):
    r = subprocess.run(["git", "diff", "--name-only", base_ref], capture_output=True, text=True)
    if r.returncode != 0:
        return []
    return [f.strip() for f in r.stdout.splitlines() if f.strip()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="lizard_base_report.csv")
    parser.add_argument("--base-ref", default=None)
    parser.add_argument("--target-branch", default="main",
                        help="Branch to find merge base against (default: main)")
    args = parser.parse_args()

    base_ref = args.base_ref or get_merge_base(args.target_branch)

    if not base_ref:
        print("WARNING: could not determine merge base; skipping base analysis", file=sys.stderr)
        open(args.out, "w").close()
        return

    changed_files = get_changed_files(base_ref)
    if not changed_files:
        print("No changed files found; skipping base analysis")
        open(args.out, "w").close()
        return

    print(f"Analyzing {len(changed_files)} file(s) at merge base {base_ref[:8]}")

    out_abs = os.path.abspath(args.out)
    with tempfile.TemporaryDirectory() as tmpdir:
        extracted = []
        for rel_path in changed_files:
            r = subprocess.run(["git", "show", f"{base_ref}:{rel_path}"], capture_output=True)
            if r.returncode != 0:
                continue
            dest = os.path.join(tmpdir, rel_path)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(r.stdout)
            extracted.append(dest)

        if not extracted:
            print("All changed files are new; no base data to compare")
            open(args.out, "w").close()
            return

        print(f"Extracted {len(extracted)} file(s) from base commit")
        r = subprocess.run(
            ["lizard", "--modified", "--csv", "--output_file", out_abs] + extracted,
            capture_output=True, text=True,
        )
        if r.returncode not in (0, 1):
            print(f"lizard error: {r.stderr}", file=sys.stderr)
            open(args.out, "w").close()
            return

        prefix = tmpdir + os.sep
        with open(out_abs) as f:
            content = f.read()
        with open(out_abs, "w") as f:
            f.write(content.replace(prefix, ""))

    print(f"Base report written to {args.out}")


if __name__ == "__main__":
    main()
