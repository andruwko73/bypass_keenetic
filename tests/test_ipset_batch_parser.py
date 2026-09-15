"""Differential tests against the frozen v1.1054 shell parser."""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "app" / "unblock_ipset.sh"
LEGACY = ROOT / "tests" / "fixtures" / "unblock_parse_legacy.sh"


def bash_binary():
    candidates = [shutil.which("bash")]
    if os.name == "nt":
        candidates.insert(0, r"C:\Program Files\Git\bin\bash.exe")
    return next((p for p in candidates if p and Path(p).is_file()), None)


def shell_function(source, name):
    found = re.search(r"^" + name + r"\(\) \{.*?^\}", source, re.M | re.S)
    assert found, name
    return found.group()


def run_parser(folder, text, policy="", excluded="", *, legacy=False, mirror=True, ipv6=True):
    folder.mkdir()
    if text is not None:
        (folder / "input").write_text(text, encoding="utf-8", newline="")
    (folder / "policy").write_text(policy, encoding="utf-8", newline="")
    (folder / "excluded").write_text(excluded, encoding="utf-8", newline="")
    source = LEGACY.read_text("utf-8") if legacy else SCRIPT.read_text("utf-8")
    if not legacy:
        source = "\n".join(shell_function(source, n) for n in ("parse_list_entries", "load_file_to_set"))
    harness = r"""
tmp_dir=.
restore_file=./restore
UDP_QUIC_POLICY_SOURCE=./policy
UDP_QUIC_EXCLUDE_SOURCE=./excluded
IPV4_RE='[0-9]{1,3}(\.[0-9]{1,3}){3}'
LOCAL_RE='localhost|^0\.|^127\.|^10\.|^172\.16\.|^192\.168\.|^::|^fc..:|^fd..:|^fe..:'
: > "$restore_file"
prepare_temp_set() { :; }
resolve_domains() { :; }
resolve_ipv6_domains() { :; }
fail_status() { printf '%s\n' "$1" >&2; exit 1; }
"""
    harness += source
    harness += '\nload_file_to_set ./input main tmp_main '
    harness += ('mirror tmp_mirror ' if mirror else "'' '' ")
    harness += ('ipv6 tmp_ipv6\n' if ipv6 else "'' ''\n")
    (folder / "harness.sh").write_text(harness, encoding="utf-8", newline="\n")
    shell = bash_binary()
    if shell is None:
        pytest.skip("Bash is needed for the legacy shell oracle")
    result = subprocess.run(
        [shell, "harness.sh"], cwd=folder, text=True, capture_output=True,
        timeout=120, env={**os.environ, "LC_ALL": "C", "BASH_ENV": "/dev/null"},
    )
    assert result.returncode == 0, result.stderr
    outputs = {
        p.name: p.read_bytes()
        for p in folder.iterdir()
        if p.name == "restore" or p.suffix in (".domains", ".source", ".missing")
    }
    return outputs


MIXED = """ # comment with 203.0.113.99
DOMAIN-SUFFIX,Example.COM
a.media.example
unrelated.test
clients3.google.com
WWW.GSTATIC.COM
*.EXAMPLE.COM
HOST-SUFFIX,+.Mixed.Example
DOMAIN,DOMAIN,Prefix.Example
 /slash.example/
2001:db8::1/64 # comment
2001:db8::2,ignored
::1
fc00::1
DOMAIN,first.example
203.0.113.1
203.0.113.1
198.51.100.0/24
198.51.100.1-198.51.100.4
local 10.0.0.1 then 203.0.113.2
192.168.1.1
999.888.777.666/123
broken[entry
literal$(touch should-not-exist).example
last.example"""
POLICY = """EXAMPLE.COM
DOMAIN-SUFFIX,media.example # comment
203.0.113.1
198.51.100.0/24
198.51.100.1-198.51.100.4
"""
EXCLUDE = "198.51.100.0/24\n"


@pytest.mark.parametrize("mirror,ipv6", [(True, True), (False, True), (True, False)])
def test_batch_parser_preserves_legacy_outputs(tmp_path, mirror, ipv6):
    old = run_parser(tmp_path / "old", MIXED.replace("\n", "\r\n"), POLICY, EXCLUDE,
                     legacy=True, mirror=mirror, ipv6=ipv6)
    new = run_parser(tmp_path / "new", MIXED.replace("\n", "\r\n"), POLICY, EXCLUDE,
                     mirror=mirror, ipv6=ipv6)
    assert new == old
    assert b"203.0.113.1" in new["restore"]
    assert b"10.0.0.1" not in new["restore"]
    assert b"clients3.google.com" not in new["main.domains"]
    assert not (tmp_path / "new" / "should-not-exist").exists()


@pytest.mark.parametrize("text", [None, "", "# only a comment\n \r\n", "203.0.113.7"])
def test_missing_empty_and_unterminated_sources(tmp_path, text):
    assert run_parser(tmp_path / "new", text) == run_parser(tmp_path / "old", text, legacy=True)


def test_batch_parser_without_policy(tmp_path):
    text = "DOMAIN,Example.COM\n203.0.113.1\n2001:db8::1"
    assert run_parser(tmp_path / "new", text) == run_parser(tmp_path / "old", text, legacy=True)


def test_policy_legacy_regex_and_exact_exclusion_semantics(tmp_path):
    text = "a.mediaXexample\n203.0.113.1\n198.51.100.2\n"
    policy = "media.example\n203.0.113.1 # direct\n198.51.100.2\n"
    excluded = "203.0.113.1\r\n198.51.100.2\n"
    assert run_parser(tmp_path / "new", text, policy, excluded) == run_parser(
        tmp_path / "old", text, policy, excluded, legacy=True
    )


def test_large_source_is_streamed_without_per_entry_subprocesses(tmp_path):
    text = "".join(f"203.0.113.{i % 254 + 1}\n" for i in range(20000))
    output = run_parser(tmp_path / "new", text)
    assert len(output["restore"].splitlines()) == 20000
    assert output["main.domains"] == b""


def test_parser_failure_aborts_before_resolution_or_set_swap(tmp_path):
    source = SCRIPT.read_text("utf-8")
    function = shell_function(source, "load_file_to_set")
    harness = r"""
tmp_dir=.
prepare_temp_set() { :; }
parse_list_entries() { return 2; }
resolve_domains() { touch must-not-resolve; }
resolve_ipv6_domains() { touch must-not-resolve; }
fail_status() { exit 41; }
""" + function + "\nload_file_to_set input main tmp_main mirror tmp_mirror ipv6 tmp_ipv6\n"
    (tmp_path / "input").write_text("203.0.113.1")
    (tmp_path / "harness.sh").write_text(harness, encoding="utf-8", newline="\n")
    shell = bash_binary()
    if shell is None:
        pytest.skip("Bash unavailable")
    result = subprocess.run([shell, "harness.sh"], cwd=tmp_path, capture_output=True, timeout=10)
    assert result.returncode == 41
    assert not (tmp_path / "must-not-resolve").exists()

