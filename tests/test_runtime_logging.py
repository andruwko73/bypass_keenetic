import concurrent.futures
import os
import sys
import multiprocessing
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import runtime_logging as logs


def _process_writer(path, number):
    for i in range(150):
        logs.append_log(path, f'Процесс {number}, строка {i}', limit=4096)


@pytest.mark.skipif(os.name == 'nt', reason='router cross-process flock requires POSIX')
def test_process_writers_share_rotation_lock(tmp_path):
    path = str(tmp_path / 'parallel.log')
    with concurrent.futures.ProcessPoolExecutor(max_workers=3, mp_context=multiprocessing.get_context('spawn')) as pool:
        list(pool.map(_process_writer, [path]*3, range(3)))
    assert Path(path).stat().st_size <= 4096
    lines = Path(path).read_text(encoding='utf-8').splitlines()
    assert lines and all('Процесс ' in line and ', строка ' in line for line in lines)


def test_append_is_bounded_timestamped_and_keeps_last_lines(tmp_path):
    path = tmp_path / 'runtime.log'
    for i in range(3000):
        logs.append_log(path, f'строка {i}', limit=4096)
        assert path.stat().st_size <= 4096
    text = path.read_text(encoding='utf-8')
    assert 'строка 2999' in text and 'строка 1\n' not in text
    assert text[:4].isdigit()


def test_concurrent_writers_remain_bounded_and_utf8(tmp_path):
    path = tmp_path / 'runtime.log'
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda i: logs.append_log(path, f'Проверка {i}', limit=4096), range(1000)))
    assert path.stat().st_size <= 4096
    assert 'Проверка' in path.read_text(encoding='utf-8')


def test_periodic_retention_keeps_external_append_descriptor_and_ignores_symlinks(tmp_path):
    path = tmp_path / 'external.log'
    with path.open('ab', buffering=0) as writer:
        writer.write(b'old\n'*5000 + b'recent\n')
        inode = path.stat().st_ino
        assert logs.trim_logs({str(path): 4096}) == 1
        assert path.stat().st_ino == inode
        writer.write(b'after trim\n')
    assert b'recent\nafter trim\n' in path.read_bytes()
    assert path.stat().st_size <= 4096
    target = tmp_path / 'unrelated'
    target.write_bytes(b'x'*5000)
    link = tmp_path / 'link'
    if os.name != 'nt':
        link.symlink_to(target)
        assert logs.trim_logs({str(link): 1024}) == 0
        assert target.stat().st_size == 5000


def test_huge_message_and_missing_file_do_not_grow_archives(tmp_path):
    path = tmp_path / 'runtime.log'
    logs.append_log(path, 'Я'*1000000, limit=4096)
    assert path.stat().st_size <= 4096
    path.read_text(encoding='utf-8')
    assert logs.trim_logs({str(tmp_path/'missing'): 4096}) == 0
    assert len(list(tmp_path.iterdir())) == 1
