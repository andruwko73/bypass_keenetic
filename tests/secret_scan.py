from pathlib import Path
import os
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]

BASE_TOKEN_PATTERNS = [
    ('telegram_bot_token', re.compile(r'\bbot\d{8,}:[A-Za-z0-9_-]{25,}\b')),
    ('telegram_token_value', re.compile(r'\b\d{8,}:[A-Za-z0-9_-]{25,}\b')),
    ('proxy_uri', re.compile(r'\b(?:vless|vmess|trojan|ss)://[^\s\'"<>]+', re.I)),
    ('private_key_block', re.compile(r'-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----')),
]

SAFE_PROXY_MARKERS = (
    'fixture',
    'example',
    'sample',
    '00000000-0000-0000-0000-000000000000',
    'uuid@',
    'secret@example',
    'password@example',
    'vless://one',
    'vless://two',
    'vless://hidden',
    'vless://...',
    'vmess://...',
    'trojan://...',
)

SAFE_TOKEN_MARKERS = (
    'secret-token',
    '<redacted',
    '<token',
    'bot<',
)

SKIP_SUFFIXES = {
    '.jpg',
    '.png',
    '.ico',
}


def tracked_files():
    result = subprocess.run(
        ['git', 'ls-files'],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    for raw in result.stdout.splitlines():
        path = ROOT / raw
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        if path.is_file():
            yield path


def local_denylist_patterns():
    denylist_raw = str(os.environ.get('BYPASS_SECRET_SCAN_DENYLIST', '') or '').strip()
    if not denylist_raw:
        return []
    denylist_path = Path(denylist_raw)
    try:
        text = denylist_path.read_text(encoding='utf-8')
    except Exception as exc:
        print(f'warning: failed to read BYPASS_SECRET_SCAN_DENYLIST: {exc}', file=sys.stderr)
        return []
    patterns = []
    for index, raw in enumerate(text.splitlines(), start=1):
        value = raw.strip()
        if not value or value.startswith('#'):
            continue
        patterns.append((f'local_secret_literal_{index}', re.compile(re.escape(value), re.I)))
    return patterns


def is_allowed(kind, line):
    lowered = line.lower()
    if kind == 'proxy_uri':
        if "return f'" in lowered or 'return f"' in lowered:
            return True
        return any(marker in lowered for marker in SAFE_PROXY_MARKERS)
    if kind in {'telegram_bot_token', 'telegram_token_value'}:
        return any(marker in lowered for marker in SAFE_TOKEN_MARKERS)
    return False


def main():
    token_patterns = list(BASE_TOKEN_PATTERNS) + local_denylist_patterns()
    findings = []
    for path in tracked_files():
        try:
            text = path.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            for kind, pattern in token_patterns:
                if not pattern.search(line):
                    continue
                if is_allowed(kind, line):
                    continue
                rel = path.relative_to(ROOT)
                findings.append(f'{rel}:{line_no}: {kind}')
    if findings:
        print('Potential secrets found:')
        print('\n'.join(findings))
        return 1
    print('secret_scan: ok')
    return 0
if __name__ == '__main__':
    sys.exit(main())
