import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import router_health_runtime as health


@pytest.mark.parametrize('path,mounts,expected', [
    ('/opt/etc/bot', '/dev/ubi0_0 /storage ubifs rw 0 0\n/dev/ubi0_0 /opt ubifs rw 0 0', 'internal'),
    ('/opt/etc/bot', '/dev/sda1 /opt ext4 rw 0 0\n/dev/ubi0_0 /storage ubifs rw 0 0', 'external'),
    ('/opt/etc/bot', '/dev/mtdblock1 /opt jffs2 rw 0 0', 'internal'),
    ('/opt/etc/bot', '/dev/ubi0_0 /opt ubifs rw 0 0\n/dev/sda1 /opt/etc ext4 rw 0 0', 'external'),
    ('/opt/etc/bot', '/dev/ubi0_0 /opt-other ubifs rw 0 0', 'unknown'),
    ('/opt/etc/bot', 'tmpfs /opt tmpfs rw 0 0', 'unknown'),
    ('/tmp/disk with spaces/bot', '/dev/sda1 /tmp/disk\\040with\\040spaces ext4 rw 0 0', 'external'),
    ('/opt/etc/bot', '', 'unknown'),
])
def test_storage_label_uses_own_mount(path, mounts, expected):
    assert health.storage_kind_for_path(path, mounts) == expected


def test_storage_read_and_payload_follow_internal_symlink_without_changing_ram():
    storage = health.read_flash_storage(
        paths=('/opt/etc/bot',), path_exists=lambda _: True,
        disk_usage=lambda _: SimpleNamespace(total=98*1024**2, used=57*1024**2, free=41*1024**2),
        realpath=lambda _: '/storage/etc/bot',
        read_text=lambda *_args, **_kwargs: '/dev/ubi0_0 /storage ubifs rw 0 0',
    )
    payload = health.build_router_health_payload(
        meminfo={'MemTotal':486*1024,'MemAvailable':184*1024}, ndmc_system={},
        load_text='0.1', bot_rss_kb=74*1024, xray_rss_kb=32*1024,
        trojan_rss_kb=7*1024, shadowsocks_rss_kb=2*1024,
        probe_progress={}, temp_xray_count=0, flash_storage=storage,
    )
    assert payload['flash_storage_kind'] == 'internal'
    assert 'Внутренняя память: занято 57 из 98 МБ (58%)' in payload['note']
    assert 'Flash-носитель' not in payload['note']
    assert payload['program_rss_kb'] == 115*1024
    assert payload['bot_rss_kb'] == 74*1024
    assert payload['available_kb'] == 184*1024
