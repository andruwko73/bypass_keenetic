"""The tooltip, API score and current service result must agree."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import key_pool_web as web
import probe_cache
from protocol_catalog import PROTOCOL_DISPLAY_ORDER


def row_for(probe, proto='vless'):
    return web.web_pool_snapshot({}, {proto: ['fixture-key']}, {'fixture-key': probe}, [],
        include_keys=False, hash_key=lambda key: key, display_name=lambda key: 'Fixture',
        probe_state=web.web_probe_state, probe_checked_at=web.web_probe_checked_at,
        protocols=[proto])[proto]['rows'][0]


@pytest.mark.parametrize('proto', PROTOCOL_DISPLAY_ORDER)
@pytest.mark.parametrize('score', [62, 74, 75])
def test_score_without_speed_badge_is_used_for_sorting(proto, score):
    row = row_for({'yt_ok': True, 'tg_ok': True, 'yt_score': score, 'yt_latency_ms': 500}, proto)
    assert row['yt_score'] == score and row['yt_quality_label'] == ''
    assert f'Оценка YouTube: {score}/100' in row['quality_summary']
    assert 'скорость скачивания не измерена' in row['quality_summary']
    assert 'не проценты' in row['quality_summary'] and 'key' not in row


@pytest.mark.parametrize('probe', [
    {'yt_ok': False, 'tg_ok': False},
    {'yt_ok': False, 'yt_stability': 'fail'},
    {'yt_ok': False, 'googlevideo_ok': False},
])
def test_failed_check_hides_old_fast_measurement(probe):
    row = row_for(dict(probe, yt_quality='fast', yt_score=100, yt_throughput_mbps=55, yt_latency_ms=200))
    assert row['yt'] == 'fail' and row['yt_score'] == 0
    assert row['yt_quality_label'] == '' and row['yt_stream_tier'] == ''
    assert '0/100' in row['quality_summary'] and 'не работает' in row['quality_summary']
    assert '55 Мбит/с' not in row['quality_summary'] and '200 мс' not in row['quality_summary']


def test_unknown_is_not_a_fake_zero_or_twenty_score():
    row = row_for({'yt_score': 20})
    assert row['yt_score'] is None and row['yt'] == 'unknown'
    assert '/100' not in row['quality_summary']
    assert 'ещё не рассчитана' in row['quality_summary']


def test_unstable_does_not_show_fast_badge():
    row = row_for({'yt_ok': False, 'yt_stability': 'unstable', 'yt_score': 45,
                  'yt_throughput_mbps': 50, 'yt_quality': 'fast'})
    assert row['yt'] == 'warn' and row['yt_score'] == 45 and row['yt_quality_label'] == ''
    assert 'нестабильно' in row['quality_summary']


def test_measured_speed_and_no_data_are_distinct():
    row = row_for({'yt_ok': True, 'yt_score': 100, 'yt_quality': 'fast', 'yt_throughput_mbps': 55})
    assert row['yt_quality_label'] == 'Быстро'
    assert 'Скорость тестовой загрузки: 55 Мбит/с' in row['quality_summary']
    assert 'Предварительная' not in row['quality_summary']
    zero = row_for({'yt_ok': True, 'yt_score': 70, 'yt_throughput_mbps': 0})
    assert 'Скорость тестовой загрузки: 0 Мбит/с' in zero['quality_summary']
    assert 'не измерена' not in zero['quality_summary']


@pytest.mark.parametrize('score', ['invalid', float('nan'), float('inf'), None])
def test_invalid_scores_do_not_break_pool_rendering(score):
    assert row_for({'yt_ok': True, 'yt_score': score})['yt_score'] is None


def test_explained_score_scale_matches_existing_formula():
    partial = probe_cache.youtube_quality_score(yt_ok=True, yt_latency_ms=500)
    full = probe_cache.youtube_quality_score(yt_ok=True, yt_latency_ms=500, yt_throughput_mbps=100)
    failed = probe_cache.youtube_quality_score(yt_ok=False)
    assert partial['yt_score'] == 75 and partial['yt_quality'] == ''
    assert full['yt_score'] == 100 and failed['yt_score'] == 0
