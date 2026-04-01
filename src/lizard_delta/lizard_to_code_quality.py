#!/usr/bin/env python3
"""
Convert lizard CSV complexity report to GitLab Code Quality JSON format.

Reads lizard_report.csv (produced by lizard.sh) and writes
gl-code-quality-report.json. GitLab reads that file as a Code Quality
report, annotating MR diffs with functions whose cyclomatic complexity
exceeds the threshold.

Thresholds are controlled by CLI args (default: --ccn-minor=30, --ccn-major=60).

With --base-csv (produced by lizard-base): for changed files, delta
reporting applies the following rules:
  - CCN crosses max upward (e.g. 15 -> 31): new issue
  - CCN increases while already above max (e.g. 31 -> 32): new issue
  - CCN decreases while previously above max (e.g. 32 -> 31 or 31 -> 15): resolved issue
  - CCN changes stay entirely below max (e.g. 15 -> 10): no issue

Unchanged files (no base data) use threshold-only reporting.

Locally runnable: lizard-to-code-quality
"""
import argparse
import csv
import hashlib
import json
import sys


def severity(ccn, ccn_major):
    return "major" if ccn > ccn_major else "minor"


def fingerprint(file_path, function_name, suffix=""):
    return hashlib.md5(f"{file_path}:{function_name}{suffix}".encode()).hexdigest()


def load_csv(csv_path):
    """Load lizard CSV.

    Returns (functions, files) where:
      functions: {(file_path, long_name): (ccn, start_line, function_name)}
      files:     set of file paths present in the CSV

    long_name (row[8]) includes the full parameter signature, so overloaded
    methods within the same file get distinct keys (e.g. two Swift methods
    both named "tableView" but with different parameters).
    """
    functions = {}
    files = set()
    try:
        with open(csv_path, newline="") as f:
            for row in csv.reader(f):
                if not row or row[0].strip().lower() == "nloc":
                    continue
                if len(row) < 10:
                    continue
                try:
                    ccn = int(float(row[1]))
                    file_path = row[6].strip()
                    function_name = row[7].strip()
                    long_name = row[8].strip()
                    start_line = int(row[9])
                    functions[(file_path, long_name)] = (ccn, start_line, function_name)
                    files.add(file_path)
                except (ValueError, IndexError):
                    continue
    except FileNotFoundError:
        return {}, set()
    return functions, files


def make_issue(description, fp, ccn, ccn_major, file_path, start_line):
    return {
        "description": description,
        "check_name": "cyclomatic_complexity",
        "fingerprint": fp,
        "severity": severity(ccn, ccn_major),
        "location": {
            "path": file_path,
            "lines": {"begin": start_line},
        },
    }


def convert(csv_path, json_path, base_csv_path=None, ccn_minor=30, ccn_major=60):
    current_funcs, _ = load_csv(csv_path)
    base_funcs, base_files = load_csv(base_csv_path) if base_csv_path else ({}, set())

    issues = []
    threshold_count = 0
    worsened_count = 0

    for (file_path, long_name), (ccn, start_line, function_name) in current_funcs.items():
        if file_path in base_files:
            # File was changed in this MR — apply delta rules.
            base_entry = base_funcs.get((file_path, long_name))
            base_ccn = base_entry[0] if base_entry else None

            if ccn > ccn_minor:
                if base_ccn is None or base_ccn <= ccn_minor:
                    # Case: function newly above threshold (was below or is new).
                    # Stable fingerprint absent from target report → "new issue".
                    issues.append(make_issue(
                        f"Function '{function_name}' has cyclomatic complexity"
                        f" of {ccn} (threshold: {ccn_minor})",
                        fingerprint(file_path, long_name),
                        ccn, ccn_major, file_path, start_line,
                    ))
                    threshold_count += 1
                elif ccn >= base_ccn:
                    # Case: was already above threshold, same or worse.
                    # Always emit stable fingerprint to carry it over (not resolved).
                    issues.append(make_issue(
                        f"Function '{function_name}' has cyclomatic complexity"
                        f" of {ccn} (threshold: {ccn_minor})",
                        fingerprint(file_path, long_name),
                        ccn, ccn_major, file_path, start_line,
                    ))
                    threshold_count += 1
                    if ccn > base_ccn:
                        # Also got worse: emit a distinct "worsened" fingerprint
                        # absent from target → surfaces as a "new issue" in GitLab.
                        delta = ccn - base_ccn
                        issues.append(make_issue(
                            f"Function '{function_name}' complexity increased"
                            f" by {delta} ({base_ccn} \u2192 {ccn})",
                            fingerprint(file_path, long_name, ":worsened"),
                            ccn, ccn_major, file_path, start_line,
                        ))
                        worsened_count += 1
                else:
                    # Case: still above threshold but complexity decreased (e.g. 32 -> 31).
                    # Emit nothing — the stable fingerprint from the target report is
                    # absent here → GitLab surfaces it as a "resolved issue".
                    pass
            # else: ccn <= ccn_minor — emit nothing.
            # If base_ccn was > ccn_minor, the target pipeline's stable fingerprint
            # for this function is absent here → GitLab surfaces it as "resolved".
        else:
            # Unchanged file or new file: threshold-only reporting.
            if ccn > ccn_minor:
                issues.append(make_issue(
                    f"Function '{function_name}' has cyclomatic complexity"
                    f" of {ccn} (threshold: {ccn_minor})",
                    fingerprint(file_path, long_name),
                    ccn, ccn_major, file_path, start_line,
                ))
                threshold_count += 1

    with open(json_path, "w") as f:
        json.dump(issues, f, indent=2)

    parts = []
    if worsened_count:
        parts.append(f"{worsened_count} function(s) complexity increased while already above {ccn_minor}")
    if threshold_count - worsened_count > 0:
        parts.append(f"{threshold_count - worsened_count} function(s) exceed CCN threshold of {ccn_minor}")
    print(", ".join(parts) + " — see gl-code-quality-report.json" if parts else "No complexity issues found")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv",
        default="lizard_report.csv",
        dest="csv_path",
        help="lizard CSV input (default: lizard_report.csv)",
    )
    parser.add_argument(
        "--base-csv",
        default=None,
        dest="base_csv_path",
        help="lizard CSV for merge base, produced by lizard-base"
        " (enables delta reporting for changed files)",
    )
    parser.add_argument(
        "--out",
        default="gl-code-quality-report.json",
        dest="json_path",
        help="Code Quality JSON output (default: gl-code-quality-report.json)",
    )
    parser.add_argument(
        "--ccn-minor",
        default=30,
        type=int,
        dest="ccn_minor",
        help="CCN at which a function is flagged (default: 30)",
    )
    parser.add_argument(
        "--ccn-major",
        default=60,
        type=int,
        dest="ccn_major",
        help="CCN at which severity escalates to major (default: 60)",
    )
    args = parser.parse_args()
    convert(args.csv_path, args.json_path, args.base_csv_path, args.ccn_minor, args.ccn_major)


if __name__ == "__main__":
    main()
