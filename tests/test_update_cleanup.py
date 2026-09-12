"""Run the real cleanup functions against an isolated filesystem."""
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def run_cleanup_fixture(tmp_path, scenario):
    candidates = [shutil.which('bash')]
    if os.name == 'nt':
        candidates.insert(0, r'C:\Program Files\Git\bin\bash.exe')
    bash = next((p for p in candidates if p and Path(p).is_file()), None)
    assert bash, 'A POSIX shell is required for cleanup regression coverage'
    test_root = (tmp_path / 'root').as_posix()
    if os.name == 'nt':
        test_root = '/' + test_root[0].lower() + test_root[2:]
    source = (ROOT / 'script.sh').read_text(encoding='utf-8')
    function = re.search(
        r'^cleanup_completed_update_artifacts\(\) \{\n.*?^\}',
        source, re.M | re.S,
    ).group(0).replace('/opt/root', test_root)
    harness = f"""set -eu
TEST_ROOT='{test_root}'
mkdir -p "$TEST_ROOT"
{function}
backup_dir="$TEST_ROOT/backup-2026.09.12.21-02-16"
stage="$TEST_ROOT/update-2026.09.12.21-02-16"
legacy="$TEST_ROOT/bypass-installer-backups/20260912-192255"
mkdir -p "$backup_dir" "$stage/repo-archive" "$legacy" "$TEST_ROOT/live"
printf 'working program' > "$TEST_ROOT/live/main.py"
printf 'rollback payload' > "$backup_dir/rollback.sh"
printf 'downloaded archive' > "$stage/repo-archive/repo.tar.gz"
printf 'old install rollback' > "$legacy/rollback.sh"
ln -s "$backup_dir/rollback.sh" "$TEST_ROOT/bypass-last-update-rollback.sh"
[ -L "$TEST_ROOT/bypass-last-update-rollback.sh" ] || exit 77
ln -s "$legacy/rollback.sh" "$TEST_ROOT/bypass-last-rollback.sh"
{scenario}
[ "$(cat "$TEST_ROOT/live/main.py")" = 'working program' ]
"""
    result = subprocess.run(
        [bash, '-s'], input=harness, text=True, encoding='utf-8',
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30,
    )
    if result.returncode == 77:
        pytest.skip('This shell cannot create POSIX symlinks on this filesystem')
    assert result.returncode == 0, result.stdout


def test_success_cleanup_preserves_selected_rollback_not_newer_mtime(tmp_path):
    run_cleanup_fixture(tmp_path, """
mkdir -p "$TEST_ROOT/backup-2026.09.11.10-00-00" "$TEST_ROOT/update-older"
printf stale > "$TEST_ROOT/backup-2026.09.11.10-00-00/rollback.sh"
sleep 1
touch "$TEST_ROOT/backup-2026.09.11.10-00-00"
cleanup_completed_update_artifacts
[ ! -e "$stage" ]
[ ! -e "$TEST_ROOT/update-older" ]
[ ! -e "$TEST_ROOT/backup-2026.09.11.10-00-00" ]
[ ! -e "$legacy" ]
[ ! -L "$TEST_ROOT/bypass-last-rollback.sh" ]
[ "$(cat "$backup_dir/rollback.sh")" = 'rollback payload' ]
[ "$(readlink "$TEST_ROOT/bypass-last-update-rollback.sh")" = "$backup_dir/rollback.sh" ]
cleanup_completed_update_artifacts
[ -f "$backup_dir/rollback.sh" ]
""")


@pytest.mark.parametrize('damage', [
    'rm "$backup_dir/rollback.sh"',
    'rm "$TEST_ROOT/bypass-last-update-rollback.sh"; ln -s "$legacy/rollback.sh" "$TEST_ROOT/bypass-last-update-rollback.sh"',
])
def test_missing_or_mismatched_rollback_keeps_recovery_files(tmp_path, damage):
    run_cleanup_fixture(tmp_path, damage + """
if cleanup_completed_update_artifacts; then exit 1; fi
[ -f "$stage/repo-archive/repo.tar.gz" ]
[ -f "$legacy/rollback.sh" ]
""")


def test_cleanup_does_not_follow_directory_symlinks(tmp_path):
    run_cleanup_fixture(tmp_path, """
mkdir -p "$TEST_ROOT/outside"
printf keep > "$TEST_ROOT/outside/sentinel"
ln -s "$TEST_ROOT/outside" "$TEST_ROOT/update-linked"
ln -s "$TEST_ROOT/outside" "$TEST_ROOT/backup-linked"
ln -s "$TEST_ROOT/outside" "$TEST_ROOT/bypass-installer-backups/20260911-120000"
cleanup_completed_update_artifacts
[ "$(cat "$TEST_ROOT/outside/sentinel")" = keep ]
[ -L "$TEST_ROOT/update-linked" ]
[ -L "$TEST_ROOT/backup-linked" ]
[ -L "$TEST_ROOT/bypass-installer-backups/20260911-120000" ]
[ -f "$backup_dir/rollback.sh" ]
""")


def test_cleanup_is_only_after_runtime_and_network_success():
    source = (ROOT / 'script.sh').read_text(encoding='utf-8')
    start = source.index('start_updated_bot_transactionally || exit 1')
    network = source.index('run_update_ipset_refresh "После обновления"', start)
    cleanup = source.index('    cleanup_completed_update_artifacts || {', network)
    success = source.index('write_cli_update_status update false 100', cleanup)
    assert start < network < cleanup < success
    assert 'cleanup_completed_update_artifacts' not in source[start:network]
