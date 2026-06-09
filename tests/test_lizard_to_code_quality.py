import hashlib
import json

from lizard_delta.lizard_to_code_quality import convert

# Two classes in one file overriding the same signature (e.g. two Kotlin data
# classes each with a hand-written `equals(other: Any?)`). lizard's long_name
# has no class qualifier, so both rows share file_path + long_name.
COLLIDING_ROWS = (
    '24,19,200,1,27,"equals@19-45@a/B.kt","a/B.kt","equals","equals other : Any?",19,45\n'
    '11,8,88,1,14,"equals@70-83@a/B.kt","a/B.kt","equals","equals other : Any?",70,83\n'
)


def run_convert(tmp_path, csv_text, base_csv_text=None, ccn_minor=15, ccn_major=30):
    csv_path = tmp_path / "lizard_report.csv"
    csv_path.write_text(csv_text)
    base_csv_path = None
    if base_csv_text is not None:
        base_csv_path = tmp_path / "lizard_base_report.csv"
        base_csv_path.write_text(base_csv_text)
    json_path = tmp_path / "out.json"
    convert(
        str(csv_path),
        str(json_path),
        str(base_csv_path) if base_csv_path else None,
        ccn_minor=ccn_minor,
        ccn_major=ccn_major,
    )
    return json.loads(json_path.read_text())


def test_same_signature_collision_keeps_over_threshold_finding(tmp_path):
    issues = run_convert(tmp_path, COLLIDING_ROWS)
    assert len(issues) == 1
    assert issues[0]["location"]["lines"]["begin"] == 19
    assert "complexity of 19" in issues[0]["description"]


def test_same_signature_collision_both_over_threshold(tmp_path):
    rows = (
        '24,19,200,1,27,"equals@19-45@a/B.kt","a/B.kt","equals","equals other : Any?",19,45\n'
        '30,22,150,1,20,"equals@70-89@a/B.kt","a/B.kt","equals","equals other : Any?",70,89\n'
    )
    issues = run_convert(tmp_path, rows)
    assert len(issues) == 2
    fingerprints = {issue["fingerprint"] for issue in issues}
    assert len(fingerprints) == 2
    assert {issue["location"]["lines"]["begin"] for issue in issues} == {19, 70}


def test_delta_mode_collision_carries_over_unchanged_finding(tmp_path):
    # File present in base with identical rows: the CCN 19 finding must carry
    # over (stable fingerprint), not silently disappear.
    issues = run_convert(tmp_path, COLLIDING_ROWS, base_csv_text=COLLIDING_ROWS)
    assert len(issues) == 1
    assert issues[0]["location"]["lines"]["begin"] == 19


def test_first_occurrence_fingerprint_is_backward_compatible(tmp_path):
    # Functions without a collision (the overwhelmingly common case) must keep
    # the exact fingerprint v0.3.1 produced, so existing GitLab findings don't
    # all churn as resolved+new on upgrade.
    rows = '43,30,203,2,50,"f@51-100@a/C.kt","a/C.kt","f","f x : Int",51,100\n'
    issues = run_convert(tmp_path, rows)
    assert len(issues) == 1
    expected = hashlib.md5("a/C.kt:f x : Int".encode()).hexdigest()
    assert issues[0]["fingerprint"] == expected


def test_threshold_and_severity(tmp_path):
    rows = (
        '10,15,100,1,10,"at_minor@1-10@a/D.kt","a/D.kt","at_minor","at_minor",1,10\n'
        '10,16,100,1,10,"over_minor@11-20@a/D.kt","a/D.kt","over_minor","over_minor",11,20\n'
        '10,31,100,1,10,"over_major@21-30@a/D.kt","a/D.kt","over_major","over_major",21,30\n'
    )
    issues = run_convert(tmp_path, rows)
    by_line = {issue["location"]["lines"]["begin"]: issue for issue in issues}
    assert set(by_line) == {11, 21}
    assert by_line[11]["severity"] == "minor"
    assert by_line[21]["severity"] == "major"
