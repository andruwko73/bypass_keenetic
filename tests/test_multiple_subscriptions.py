"""Subscription ownership and UI contracts, using only synthetic local data."""
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import pytest

APP = Path(__file__).resolve().parents[1] / 'app'
sys.path.insert(0, str(APP))
import subscription_runtime as runtime
import subscription_refresh_runtime as refresh_runtime
import managed_state_snapshot
import web_form_blocks
import web_post_actions


@pytest.mark.parametrize('proto', runtime.key_pool_store.PROTOCOLS)
def test_each_protocol_refreshes_two_sources_independently(proto):
    state = {}
    urls = ['https://example.test/first', 'https://example.test/second']
    old_keys = [f'{proto}-old-first', f'{proto}-old-second']
    for url, key in zip(urls, old_keys):
        state = runtime.update_subscription_record(
            state, proto, url=url, hwid_enabled=True,
            managed_keys=[key], imported_keys=[key],
        )
    pools = {proto: list(old_keys)}
    fetched = []
    new_key = f'{proto}-new-second'
    def fetch(url, **kwargs):
        fetched.append(url)
        if url == urls[0]:
            return {}, 'fixture fetch failure'
        return {'vless' if proto == 'vless2' else proto: [new_key]}, ''
    def update(owner, **updates):
        nonlocal state
        state = runtime.update_subscription_record(state, owner, **updates)
    def add(owner, keys, **options):
        nonlocal pools
        pools, added, removed, owned = runtime.sync_subscription_keys_to_pool(
            pools, owner, keys,
            previous_managed_keys=options['previous_managed_keys'],
            shared_keys=runtime.other_subscription_keys(state, owner, options['subscription_url']),
        )
        return pools, added, removed, owned, []
    clock = iter((100, 200, 201))
    results = [refresh_runtime.refresh_subscription_once(
        owner, record, auto_refresh_allowed=lambda value: value == proto,
        fetch_keys=fetch, add_keys_to_pool=add, update_record=update,
        write_log=lambda message: None, time_provider=lambda: next(clock),
    ) for owner, record in list(runtime.iter_subscription_records(state))]
    assert results == [False, True] and fetched == urls
    assert pools[proto] == [old_keys[0], new_key]
    first = runtime.subscription_record_for_url(state, proto, urls[0])
    second = runtime.subscription_record_for_url(state, proto, urls[1])
    assert first['last_error'] and first['last_success_at'] == 0
    assert first['managed_keys'] == [old_keys[0]]
    assert second['last_error'] == '' and second['last_success_at'] == 201
    assert second['imported_keys'] == [new_key]


def test_full_snapshot_restores_all_sources_after_legacy_writer(tmp_path):
    state = {}
    pools = {}
    for proto in runtime.key_pool_store.PROTOCOLS:
        pools[proto] = []
        for index in (1, 2):
            key = f'fixture-{proto}-{index}'
            pools[proto].append(key)
            state = runtime.update_subscription_record(
                state, proto, url=f'https://example.test/{proto}/{index}',
                name=f'Source {index}', hwid_enabled=True, managed_keys=[key],
                imported_keys=[key], last_success_at=100 + index,
            )
    subscriptions_path = tmp_path / 'subscriptions.json'
    pools_path = tmp_path / 'key_pools.json'
    subscriptions_path.write_text(json.dumps(runtime.serialize_subscription_state(state)), encoding='utf-8')
    pools_path.write_text(json.dumps(pools), encoding='utf-8')
    original = {p: p.read_bytes() for p in (subscriptions_path, pools_path)}
    snapshot = tmp_path / 'full-state'
    paths = tuple(original)
    managed_state_snapshot.backup_managed_state(snapshot, paths=paths)
    legacy = {'schema': 1, 'subscriptions': {
        proto: {k: value for k, value in item.items() if k != 'sources'}
        for proto, item in state.items()
    }}
    subscriptions_path.write_text(json.dumps(legacy), encoding='utf-8')
    pools_path.write_text('{}', encoding='utf-8')
    assert all(len(item['sources']) == 1 for item in runtime.normalize_subscription_state(legacy).values())
    managed_state_snapshot.verify_managed_state(snapshot, paths=paths)
    managed_state_snapshot.restore_managed_state(snapshot, paths=paths)
    assert {p: p.read_bytes() for p in paths} == original
    restored = runtime.normalize_subscription_state(json.loads(subscriptions_path.read_text(encoding='utf-8')))
    assert restored == state
    assert all(len(item['sources']) == 2 for item in restored.values())


def test_legacy_migration_and_independent_pool_sources():
    first = 'https://subscriptions.example.test/one?token=fixture-one'
    second = 'https://subscriptions.example.test/two?token=fixture-two'
    legacy = {'subscriptions': {'vless': {
        'url': first, 'hwid_enabled': True, 'managed_keys': ['fixture-a'],
        'last_success_at': 100, 'last_attempt_at': 101, 'last_error': 'request timed out',
    }}}
    state = runtime.normalize_subscription_state(legacy)
    before = runtime.subscription_record_for_url(state, 'vless', first)
    state = runtime.update_subscription_record(state, 'vless', url=second, name='Вторая', hwid_enabled=True)
    assert runtime.subscription_record_for_url(state, 'vless', first) == before
    state = runtime.update_subscription_record(state, 'vless2', url=first, hwid_enabled=False)
    state = runtime.update_subscription_record(state, 'vless2', url=second, hwid_enabled=True)
    state = runtime.update_subscription_record(state, 'vless', url=second, last_success_at=200)
    assert len(list(runtime.iter_subscription_records(state))) == 4
    restored = runtime.normalize_subscription_state(json.loads(json.dumps(runtime.serialize_subscription_state(state))))
    assert restored == state
    assert runtime.subscription_record_for_url(restored, 'vless2', second)['last_success_at'] == 0
    assert runtime.latest_recent_subscription_success_at(restored, 210, max_age_seconds=20) == 200
    first_id = before['id']
    removed = runtime.remove_subscription_record(restored, 'vless', first_id)
    assert len(removed['vless']['sources']) == 1
    assert len(removed['vless2']['sources']) == 2
    removed = runtime.remove_subscription_record(removed, 'vless', removed['vless']['sources'][0]['id'])
    assert runtime.normalize_subscription_state(runtime.serialize_subscription_state(removed))['vless']['sources'] == []


def test_overlap_preserves_other_source_without_claiming_its_keys():
    state = runtime.update_subscription_record({}, 'vless2', url='https://example.test/a', managed_keys=['a', 'shared'])
    state = runtime.update_subscription_record(state, 'vless2', url='https://example.test/b', imported_keys=['b', 'shared'])
    pools, added, removed, owned = runtime.sync_subscription_keys_to_pool(
        {'vless2': ['manual', 'active', 'a', 'shared', 'b']}, 'vless2', {'vless': ['new']},
        previous_managed_keys=['a', 'shared', 'active'], preserve_keys=['active'],
        shared_keys=runtime.other_subscription_keys(state, 'vless2', 'https://example.test/a'),
    )
    assert pools['vless2'] == ['manual', 'active', 'shared', 'b', 'new']
    assert added == ['new'] and removed == ['a']
    assert owned == ['new', 'active']


def test_public_sources_hide_urls_keys_errors_and_escape_names():
    state = runtime.update_subscription_record(
        {}, 'vless2', url='https://example.test/private?token=fixture-secret',
        name='Second <script> & "source"', imported_keys=['private-key-material'],
        last_error='failed https://example.test/private?token=fixture-secret',
    )
    settings = runtime.subscription_public_settings(state)
    panel = web_form_blocks.render_subscription_sources('vless2', settings['vless2'], '<input name="csrf_token" value="fixture">')
    public = json.dumps(settings) + panel
    for private in ('fixture-secret', 'private-key-material', 'https://example.test/private'):
        assert private not in public
    assert '<script>' not in panel
    assert '&lt;script&gt;' in panel and '&quot;source&quot;' in panel
    assert '/pool_subscription_remove' in panel and '/pool_subscription_refresh' in panel


def test_subscription_actions_respect_modes_and_do_not_expose_errors():
    for path in ('/pool_subscription_remove', '/pool_subscription_refresh'):
        assert web_post_actions.dispatch({'pool_actions_enabled': False}, path, {}) is None
    calls = []
    context = web_post_actions.pool_action_context(remove_pool_subscription=lambda *args: calls.append(args))
    result = web_post_actions.dispatch(context, '/pool_subscription_remove', {'type': ['vless2'], 'subscription_id': ['fixture-id']})
    assert result['success'] and calls == [('vless2', 'fixture-id')]
    def fail(*args):
        raise ValueError('private-subscription-token')
    context['refresh_pool_subscription'] = fail
    result = web_post_actions.dispatch(context, '/pool_subscription_refresh', {'type': ['vless2'], 'subscription_id': ['fixture-id']})
    assert not result['success'] and 'private-subscription-token' not in str(result)


def test_bot_two_sources_import_refresh_failure_remove_and_restart(tmp_path):
    (tmp_path / 'bot_config.py').write_text((APP / 'bot_config.example.py').read_text(encoding='utf-8'), encoding='utf-8')
    script = textwrap.dedent('''
        import json, sys
        from pathlib import Path
        import bot
        import subscription_runtime
        bot.KEY_POOLS_PATH = str(Path.cwd() / 'pools.json')
        bot.SUBSCRIPTION_STATE_PATH = str(Path.cwd() / 'subscriptions.json')
        bot._probe_pool_keys_background = lambda *a, **k: None
        bot._forget_unreferenced_key_probes = lambda *a, **k: None
        bot._invalidate_pool_data_cache = lambda: None
        bot._memory_cleanup = lambda *a, **k: None
        bot._maybe_start_nightly_subscription_pool_probe = lambda *a: None
        bot._run_coordinated_background_task = lambda name, call: (True, call())
        bot._subscription_auto_refresh_allowed = lambda proto: True
        bot._subscription_refresh_due = lambda record, now: bool(record.get('url') and record.get('hwid_enabled'))
        bot.SUBSCRIPTION_AUTO_REFRESH_ENABLED = True
        logs, fetched_urls = [], []
        bot._write_runtime_log = logs.append
        current = {p: 'vless://fixture-active@example.test:443' for p in ('vless', 'vless2')}
        bot._load_current_keys = lambda: dict(current)
        bot._subscription_active_key_is_working = lambda *args: True
        def forbidden(*args, **kwargs):
            raise AssertionError('subscription operation must not install a key')
        bot._install_key_for_protocol = forbidden
        def uri(name): return 'vless://fixture-' + name + '@example.test:443'
        snapshots = {}
        def fetch(url, **kwargs):
            fetched_urls.append(url)
            value = snapshots[url]
            if isinstance(value, Exception): raise value
            return {'vless': value}, ''
        bot._fetch_keys_from_subscription = fetch
        bot._key_pool_store().save_key_pools(bot.KEY_POOLS_PATH, {p: [uri('manual'), current[p]] for p in current})
        for proto in current:
            a, b = 'https://example.test/' + proto + '/a', 'https://example.test/' + proto + '/b'
            snapshots[a], snapshots[b] = [uri('a'), uri('shared'), current[proto]], [uri('b'), uri('shared')]
            bot._import_pool_subscription(proto, a, use_router_hwid=True, name='First')
            bot._import_pool_subscription(proto, b, use_router_hwid=True, name='Second')
            bot._import_pool_subscription(proto, b, use_router_hwid=True)
            assert len(bot._load_subscription_state()[proto]['sources']) == 2
            snapshots[a] = [uri('a2'), uri('a3'), uri('a4')]
            bot._import_pool_subscription(proto, a, use_router_hwid=True)
            pool = bot._key_pool_store().load_key_pools(bot.KEY_POOLS_PATH)[proto]
            assert uri('a') not in pool
            assert all(k in pool for k in (uri('manual'), uri('shared'), uri('b'), current[proto]))
            assert uri('shared') not in bot._subscription_record(proto, url=a)['managed_keys']
        before_failure = bot._key_pool_store().load_key_pools(bot.KEY_POOLS_PATH)
        failed_url = 'https://example.test/vless2/b'
        snapshots[failed_url] = TimeoutError('private-subscription-token')
        fetched_urls.clear()
        bot._run_subscription_auto_refresh_cycle()
        assert len(fetched_urls) == 4 and set(fetched_urls) == set(snapshots)
        assert bot._key_pool_store().load_key_pools(bot.KEY_POOLS_PATH) == before_failure
        assert 'private-subscription-token' not in str(logs)
        assert bot._subscription_record('vless2', url=failed_url)['last_error']
        other = bot._subscription_record('vless', url='https://example.test/vless/a')
        assert not other['last_error']
        removed = bot._subscription_record('vless2', url='https://example.test/vless2/a')
        bot._remove_pool_subscription('vless2', removed['id'])
        fetched_urls.clear()
        assert bot._refresh_subscription_once('vless2', removed) is False
        assert fetched_urls == []
        assert bot._key_pool_store().load_key_pools(bot.KEY_POOLS_PATH) == before_failure
        state = bot._load_subscription_state()
        assert len(state['vless']['sources']) == 2 and len(state['vless2']['sources']) == 1
        bot._subscription_refresh_due = lambda *args: False
        assert bot._refresh_subscription_once('vless', other) is False
        assert fetched_urls == []
        print('multiple subscriptions integration passed')
    ''')
    environment = dict(os.environ, BYPASS_KEENETIC_COMMAND_WORKER='1', PYTHONIOENCODING='utf-8', PYTHONPATH=os.pathsep.join([str(tmp_path), str(APP)]))
    result = subprocess.run([sys.executable, '-c', script], cwd=tmp_path, env=environment, capture_output=True, text=True, encoding='utf-8', timeout=40)
    assert result.returncode == 0, result.stderr
    check = "import bot; state=bot._subscription_runtime().normalize_subscription_state(__import__('json').load(open('subscriptions.json'))); assert len(state['vless']['sources']) == 2 and len(state['vless2']['sources']) == 1"
    restarted = subprocess.run([sys.executable, '-c', check], cwd=tmp_path, env=environment, capture_output=True, text=True, encoding='utf-8', timeout=20)
    assert restarted.returncode == 0, restarted.stderr
