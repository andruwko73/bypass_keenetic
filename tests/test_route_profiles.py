import json
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from route_profiles import RouteProfileStore,normalize_profile,profile_fingerprint,probe_url,public_host


def profile(**kwargs):
    return dict(label='Видео на ПК',device='192.168.1.10',destination='example.com',
                url='https://example.com/health',wan='eth1',protocols=['vless','vless2'],direct_allowed=False)|kwargs


def test_private_profile_revision_and_cas(tmp_path):
    store=RouteProfileStore(tmp_path/'profiles.json',lock=threading.RLock())
    state=store.save(profile(),expected_revision=0)
    assert state['revision']==1 and len(state['profiles'])==1
    original=store.path.read_bytes()
    with pytest.raises(ValueError,match='уже изменились'):store.save(profile(),expected_revision=0)
    assert store.path.read_bytes()==original
    state=store.save(state['profiles'][0]|{'label':'Новое имя'},expected_revision=1)
    assert state['revision']==2 and len(state['profiles'])==1
    assert store.remove(state['profiles'][0]['id'],expected_revision=2)['profiles']==[]


def test_corrupt_store_not_overwritten(tmp_path):
    path=tmp_path/'profiles.json';path.write_text('{broken')
    store=RouteProfileStore(path,lock=threading.RLock())
    with pytest.raises(ValueError):store.save(profile(),expected_revision=0)
    assert path.read_text()=='{broken'


def test_missing_identity_is_not_silently_regenerated(tmp_path):
    path=tmp_path/'profiles.json'
    path.write_text(json.dumps({'schema':1,'revision':0,'profiles':[profile()]}))
    with pytest.raises(ValueError):RouteProfileStore(path,lock=threading.RLock()).snapshot()


def test_profile_count_bounded(tmp_path):
    store=RouteProfileStore(tmp_path/'profiles.json',lock=threading.RLock())
    for i in range(8):store.save(profile(),expected_revision=i)
    with pytest.raises(ValueError,match='восьми'):store.save(profile(),expected_revision=8)
    assert store.snapshot()['revision']==8


@pytest.mark.parametrize('url',[
    'http://example.com/','https://user:pass@example.com/','https://example.com/?token=secret',
    'https://example.com/#secret','https://example.com:8080/','https://localhost/',
    'https://127.0.0.1/','https://192.168.1.1/','https://[::1]/','file:///etc/passwd',
])
def test_no_credentials_private_targets_or_non_https(url):
    with pytest.raises(ValueError):probe_url(url)


@pytest.mark.parametrize('changes',[
    {'direct_allowed':'yes'},{'protocols':[]},{'protocols':['vless','vless']},
    {'protocols':['direct']},{'wan':'lo'},{'wan':'eth1; reboot'},
    {'device':'8.8.8.8'},{'device':'127.0.0.1'},{'device':'192.0.2.1'},
    {'url':'https://other.example.com/'},{'automatic':True},{'label':'bad\nlabel'},
])
def test_invalid_or_automatic_settings_rejected(changes):
    with pytest.raises(ValueError):normalize_profile(profile(**changes))


def test_profile_identity_and_order_affect_fingerprint():
    value=normalize_profile(profile())
    assert profile_fingerprint(value)==profile_fingerprint(dict(reversed(list(value.items()))))
    assert profile_fingerprint(value)!=profile_fingerprint(value|{'device':'router'})
    assert profile_fingerprint(value)!=profile_fingerprint(value|{'wan':'ppp0'})


def test_snapshot_cannot_mutate_store(tmp_path):
    store=RouteProfileStore(tmp_path/'profiles.json',lock=threading.RLock())
    store.save(profile(),expected_revision=0)
    state=store.snapshot();state['profiles'][0]['protocols'].clear()
    assert store.snapshot()['profiles'][0]['protocols']==['vless','vless2']
