import base64
import os
import stat
import subprocess
import tarfile
from urllib.parse import quote

import requests


SCRIPT_PATH = '/opt/root/script.sh'
SCRIPT_MODE = stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH


def fetch_remote_text(url, timeout=20):
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.text


def _archive_ref_candidates(repo_ref):
    yield repo_ref
    if not repo_ref.startswith('refs/'):
        yield f'refs/heads/{repo_ref}'
        yield f'refs/tags/{repo_ref}'


def download_repo_file_from_archive(session, repo_owner, repo_name, repo_ref, path):
    suffix = '/' + path.strip('/')
    last_error = None
    for archive_ref in _archive_ref_candidates(repo_ref):
        archive_url = f'https://codeload.github.com/{repo_owner}/{repo_name}/tar.gz/{archive_ref}'
        try:
            with session.get(archive_url, stream=True, timeout=(10, 90)) as response:
                response.raise_for_status()
                response.raw.decode_content = True
                with tarfile.open(fileobj=response.raw, mode='r|gz') as archive:
                    for member in archive:
                        if member.isfile() and member.name.endswith(suffix):
                            extracted = archive.extractfile(member)
                            if extracted is not None:
                                return archive_url, extracted.read().decode('utf-8')
        except Exception as exc:
            last_error = exc
            continue
    if last_error is not None:
        raise last_error
    raise ValueError(f'GitHub archive did not contain {path}')


def download_repo_file_text(session, repo_owner, repo_name, repo_ref, path):
    headers = {'Cache-Control': 'no-cache', 'Pragma': 'no-cache'}
    raw_url = f'https://raw.githubusercontent.com/{repo_owner}/{repo_name}/{repo_ref}/{path}'
    try:
        response = session.get(raw_url, headers=headers, timeout=(5, 8))
        response.raise_for_status()
        return raw_url, response.text
    except requests.RequestException:
        pass

    try:
        return download_repo_file_from_archive(session, repo_owner, repo_name, repo_ref, path)
    except Exception:
        pass

    api_url = f'https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{quote(path, safe="/")}'
    response = session.get(
        api_url,
        params={'ref': repo_ref},
        headers={'Accept': 'application/vnd.github+json', **headers},
        timeout=(10, 30),
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get('encoding') != 'base64' or 'content' not in payload:
        raise ValueError('GitHub contents API returned unexpected file payload')
    content = ''.join(str(payload.get('content', '')).split())
    return response.url, base64.b64decode(content).decode('utf-8')


def resolve_repo_ref(session, repo_owner, repo_name, repo_ref):
    headers = {'Accept': 'application/vnd.github+json', 'Cache-Control': 'no-cache', 'Pragma': 'no-cache'}
    api_url = f'https://api.github.com/repos/{repo_owner}/{repo_name}/commits/{quote(repo_ref, safe="")}'
    try:
        response = session.get(api_url, headers=headers, timeout=(5, 12))
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException:
        return repo_ref
    sha = str(payload.get('sha') or '').strip()
    return sha or repo_ref


def download_repo_script(repo_owner, repo_name, branch='main'):
    session = requests.Session()
    session.trust_env = False
    repo_ref = resolve_repo_ref(session, repo_owner, repo_name, branch)
    url, script_text = download_repo_file_text(session, repo_owner, repo_name, repo_ref, 'script.sh')
    if '#!/bin/sh' not in script_text:
        raise ValueError('GitHub returned invalid script.sh')
    return url, script_text, repo_ref


def write_script(script_text, script_path=SCRIPT_PATH, mode=SCRIPT_MODE):
    with open(script_path, 'w', encoding='utf-8') as file:
        file.write(script_text)
    os.chmod(script_path, mode)


def direct_fetch_env(env_keys, environ=None):
    env = dict(os.environ if environ is None else environ)
    for key in env_keys:
        env.pop(key, None)
    return env


def run_script_and_collect(action, env, logs, progress_callback=None, script_path=SCRIPT_PATH):
    process = subprocess.Popen(
        ['/bin/sh', script_path, action],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
    )
    if process.stdout is not None:
        for line in process.stdout:
            clean_line = line.strip()
            if clean_line:
                logs.append(clean_line)
                if progress_callback:
                    progress_callback('\n'.join(logs))
    return_code = process.wait()
    if return_code != 0:
        logs.append(f'Команда завершилась с кодом {return_code}.')
    return return_code, '\n'.join(logs)
