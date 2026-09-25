"""Exercise installation shell functions without touching the host /opt."""
import os
from pathlib import Path
import re
import shutil
import shlex
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def shell_function(path, name):
    return re.search(r'^' + name + r'\(\) \{\n.*?^\}',
                     (ROOT / path).read_text(encoding='utf-8'), re.M | re.S).group(0)


def run_shell(tmp_path, script):
    bash = r'C:\Program Files\Git\bin\bash.exe' if os.name == 'nt' else shutil.which('bash')
    assert bash
    command = shlex.split(os.environ['BYPASS_TEST_SHELL']) if os.environ.get('BYPASS_TEST_SHELL') else [bash]
    result = subprocess.run(command + ['-s'], input='set -eu\n' + script,
                            cwd=tmp_path, encoding='utf-8', text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=15)
    assert result.returncode == 0, result.stdout


@pytest.mark.parametrize('failure', ['partial', 'move'])
def test_static_partial_transfer_or_move_failure_preserves_old_file(tmp_path, failure):
    run_shell(tmp_path, shell_function('script.sh', 'download_static_asset') + f'''
repo_file_url() {{ printf url; }}
download_repo_file_from_archive() {{ return 1; }}
download_repo_file_via_api() {{ return 1; }}
curl() {{
    while [ "$1" != -o ]; do shift; done
    shift; printf partial > "$1"
    [ {failure} = move ]
}}
mv() {{ return 1; }}
printf working > app.css
if download_static_asset static/app.css app.css; then exit 1; fi
[ "$(cat app.css)" = working ]
[ ! -e "app.css.update.$$" ]
''')


def test_offline_static_has_no_network_fallback(tmp_path):
    run_shell(tmp_path, shell_function('script.sh', 'download_static_asset') + '''
BYPASS_INSTALL_REPO=kit
REPO_APP_DIR=app
repo_file_url() { printf url; }
curl() { touch unexpected-network; return 1; }
download_repo_file_from_archive() { curl; }
download_repo_file_via_api() { curl; }
mkdir -p kit/app/static
printf kit-bytes > kit/app/static/app.css
download_static_asset static/app.css app.css
[ "$(cat app.css)" = kit-bytes ]
if download_static_asset static/missing.js missing.js; then exit 1; fi
[ ! -e unexpected-network ]
''')


@pytest.mark.parametrize('content', ['empty', 'html', 'partial', 'valid'])
def test_install_file_rejects_failed_or_invalid_responses(tmp_path, content):
    run_shell(tmp_path, shell_function('script.sh', 'download_install_file') + f'''
repo_file_url() {{ printf url; }}
curl() {{
    while [ "$1" != -o ]; do shift; done
    shift
    case {content} in
        empty) : > "$1";;
        html) printf '<html>gateway error</html>' > "$1";;
        partial) printf truncated > "$1"; return 18;;
        valid) printf '#!/bin/sh\\necho valid\\n' > "$1";;
    esac
}}
printf working > service
rc=0
download_install_file service service || rc=$?
if [ {content} = valid ]; then [ "$rc" = 0 ]; grep -q valid service;
else [ "$rc" = 1 ]; [ "$(cat service)" = working ]; fi
[ ! -e "service.install.$$" ]
''')


@pytest.mark.parametrize('provider', ['archive', 'api', 'curl'])
def test_static_destination_survives_nested_download_variables(tmp_path, provider):
    run_shell(tmp_path, shell_function('script.sh', 'download_static_asset') + f'''
provider={provider}
repo_file_url() {{ printf 'https://example.invalid/%s' "$1"; }}
download_repo_file_from_archive() {{
    url="$1"; target="$2"; repo_path=clobbered
    [ "$provider" = archive ] || return 1
    printf payload > "$target"
}}
download_repo_file_via_api() {{
    url="$1"; target="$2"; repo_path=clobbered
    [ "$provider" = api ] || return 1
    printf payload > "$target"
}}
curl() {{
    while [ "$1" != -o ]; do shift; done
    shift; target="$1"
    printf payload > "$target"
}}
download_static_asset static/app.css app.css
[ "$(cat app.css)" = payload ]
[ ! -e "app.css.update.$$" ]
''')


def test_failed_static_download_preserves_current_file(tmp_path):
    run_shell(tmp_path, shell_function('script.sh', 'download_static_asset') + '''
repo_file_url() { printf url; }
download_repo_file_from_archive() { return 1; }
download_repo_file_via_api() { return 1; }
curl() { return 1; }
printf working > app.css
if download_static_asset static/app.css app.css; then exit 1; fi
[ "$(cat app.css)" = working ]
[ ! -e "app.css.update.$$" ]
''')


@pytest.mark.parametrize('existing', ['current', 'legacy', 'none'])
def test_bootstrap_preserves_config_and_requires_explicit_reconfigure(tmp_path, existing):
    run_shell(tmp_path, shell_function('bootstrap/install.sh', 'guard_existing_configuration') + f'''
BOT_CONFIG_PATH=current
LEGACY_CONFIG_PATH=legacy
existing={existing}
if [ "$existing" != none ]; then printf private-config > "$existing"; fi
rc=0
guard_existing_configuration || rc=$?
if [ "$existing" = none ]; then
    [ "$rc" = 0 ]
else
    [ "$rc" = 3 ]
    [ "$(cat "$existing")" = private-config ]
fi
BYPASS_RECONFIGURE=1 guard_existing_configuration
''')
