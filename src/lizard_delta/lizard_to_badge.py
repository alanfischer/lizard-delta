#!/usr/bin/env python3
"""
Generate a complexity badge SVG and violations HTML report from lizard CSV.

Reads lizard_report.csv and produces:
  complexity_badge.svg       — shields.io-style badge: "complexity | N violations"
  complexity_violations.html — sortable table of all over-threshold functions

Badge color: green (0 violations), orange (1-5), red (6+).

Locally runnable: lizard-to-badge
"""
import argparse
import csv
import html
import sys


# Approximate character widths for DejaVu Sans 11px (shields.io uses the same font).
# Values taken from the Verdana metrics table used by shields.io.
_WIDTHS = {
    " ": 3.3, "f": 5.4, "i": 2.8, "j": 2.8, "l": 2.8, "r": 3.8, "t": 4.3,
    "default": 6.5,
}


def _text_width(text):
    return sum(_WIDTHS.get(c, _WIDTHS["default"]) for c in text) + 10


def load_violations(csv_path, ccn_minor, ccn_major):
    violations = []
    try:
        with open(csv_path, newline="") as f:
            for row in csv.reader(f):
                if not row or row[0].strip().lower() == "nloc":
                    continue
                if len(row) < 10:
                    continue
                try:
                    ccn = int(float(row[1]))
                    if ccn > ccn_minor:
                        violations.append({
                            "function": row[7].strip(),
                            "file": row[6].strip(),
                            "ccn": ccn,
                            "line": int(row[9]),
                            "severity": "major" if ccn > ccn_major else "minor",
                        })
                except (ValueError, IndexError):
                    continue
    except FileNotFoundError:
        pass
    return sorted(violations, key=lambda v: v["ccn"], reverse=True)


def _badge_svg(label, value, color):
    lw = _text_width(label)
    vw = _text_width(value)
    tw = lw + vw
    lx = lw / 2
    vx = lw + vw / 2

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{tw:.0f}" height="20">\n'
        f'  <linearGradient id="s" x2="0" y2="100%">\n'
        f'    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>\n'
        f'    <stop offset="1" stop-opacity=".1"/>\n'
        f'  </linearGradient>\n'
        f'  <clipPath id="r">\n'
        f'    <rect width="{tw:.0f}" height="20" rx="3" fill="#fff"/>\n'
        f'  </clipPath>\n'
        f'  <g clip-path="url(#r)">\n'
        f'    <rect width="{lw:.0f}" height="20" fill="#555"/>\n'
        f'    <rect x="{lw:.0f}" width="{vw:.0f}" height="20" fill="{color}"/>\n'
        f'    <rect width="{tw:.0f}" height="20" fill="url(#s)"/>\n'
        f'  </g>\n'
        f'  <g fill="#fff" text-anchor="middle"'
        f' font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">\n'
        f'    <text x="{lx:.0f}" y="14" fill="#010101" fill-opacity=".3">{label}</text>\n'
        f'    <text x="{lx:.0f}" y="13">{label}</text>\n'
        f'    <text x="{vx:.0f}" y="14" fill="#010101" fill-opacity=".3">{value}</text>\n'
        f'    <text x="{vx:.0f}" y="13">{value}</text>\n'
        f'  </g>\n'
        f'</svg>\n'
    )


def _violations_html(violations, ccn_minor, ccn_major):
    count = len(violations)
    summary = (
        f"{count} function{'s' if count != 1 else ''} "
        f"exceed CCN threshold of {ccn_minor}"
    )

    if violations:
        rows = "\n".join(
            f"    <tr>"
            f"<td>{html.escape(v['function'])}</td>"
            f"<td>{html.escape(v['file'])}</td>"
            f"<td class='num'>{v['ccn']}</td>"
            f"<td class='num'>{v['line']}</td>"
            f"<td class='sev {v['severity']}'>{v['severity']}</td>"
            f"</tr>"
            for v in violations
        )
        table = (
            "<table>\n"
            "  <thead><tr>"
            "<th>Function</th><th>File</th>"
            "<th>CCN</th><th>Line</th><th>Severity</th>"
            "</tr></thead>\n"
            f"  <tbody>\n{rows}\n  </tbody>\n"
            "</table>"
        )
    else:
        table = "<p class='none'>No violations found.</p>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Complexity Violations</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      margin: 2rem; color: #24292e; background: #fff;
    }}
    h1 {{ font-size: 1.4rem; margin-bottom: .25rem; }}
    .summary {{ color: #586069; margin: 0 0 1.5rem; }}
    table {{ border-collapse: collapse; width: 100%; font-size: .875rem; }}
    th {{
      background: #f6f8fa; border: 1px solid #e1e4e8;
      padding: 6px 12px; text-align: left; white-space: nowrap;
    }}
    td {{ border: 1px solid #e1e4e8; padding: 6px 12px; }}
    tr:hover td {{ background: #f6f8fa; }}
    .num {{ text-align: center; font-variant-numeric: tabular-nums; }}
    .sev {{ text-align: center; font-weight: 600; }}
    .major {{ color: #d73a49; }}
    .minor {{ color: #e36209; }}
    .none {{ color: #28a745; font-weight: 600; }}
    td:nth-child(2) {{ font-family: "SFMono-Regular", Consolas, monospace; font-size: .8rem; }}
    td:nth-child(1) {{ font-family: "SFMono-Regular", Consolas, monospace; font-size: .8rem; }}
  </style>
</head>
<body>
  <h1>Complexity Violations</h1>
  <p class="summary">{html.escape(summary)} (minor &gt; {ccn_minor}, major &gt; {ccn_major})</p>
  {table}
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv",
        default="lizard_report.csv",
        dest="csv_path",
        help="lizard CSV input (default: lizard_report.csv)",
    )
    parser.add_argument(
        "--ccn-minor",
        default=30,
        type=int,
        dest="ccn_minor",
        help="CCN threshold for minor violations (default: 30)",
    )
    parser.add_argument(
        "--ccn-major",
        default=60,
        type=int,
        dest="ccn_major",
        help="CCN threshold for major violations (default: 60)",
    )
    parser.add_argument(
        "--badge-out",
        default="complexity_badge.svg",
        dest="badge_path",
        help="SVG badge output path (default: complexity_badge.svg)",
    )
    parser.add_argument(
        "--html-out",
        default="complexity_violations.html",
        dest="html_path",
        help="HTML violations report output path (default: complexity_violations.html)",
    )
    args = parser.parse_args()

    violations = load_violations(args.csv_path, args.ccn_minor, args.ccn_major)
    count = len(violations)

    has_major = any(v["severity"] == "major" for v in violations)
    label_value = f"{count} violation{'s' if count != 1 else ''}"

    if count == 0:
        color, value = "#4c1", "0 violations"
    elif has_major:
        color, value = "#e05d44", label_value  # red — at least one major
    else:
        color, value = "#dfb317", label_value  # yellow — minor only

    with open(args.badge_path, "w") as f:
        f.write(_badge_svg("complexity", value, color))

    with open(args.html_path, "w") as f:
        f.write(_violations_html(violations, args.ccn_minor, args.ccn_major))

    print(
        f"{count} violation{'s' if count != 1 else ''} — "
        f"{args.badge_path}, {args.html_path}"
    )


if __name__ == "__main__":
    main()
