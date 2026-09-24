import math
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from route_quality import MeasurementWindow, ProbeReply, RouteIdentity, recommend, window_metrics


def window(*, protocol='vless', kind='udp_echo', latency=50, count=20,
           replies=None, verified=True, generation=3, wan='wan0', **identity):
    scope=RouteIdentity('desktop','voice',wan,protocol,'key0','tcp','owned-endpoint',kind,generation)
    scope=replace(scope,**identity)
    return MeasurementWindow(scope,100,120,count,500,
                             tuple(ProbeReply(i,latency) for i in range(count)) if replies is None else replies,
                             verified,verified,verified)


def select(*windows, direct_allowed=False, kind='udp_echo', generations=None):
    return recommend(list(windows),now=125,direct_allowed=direct_allowed,required_kind=kind,
                     expected_generations=generations if generations is not None else {
                         (w.identity.protocol,w.identity.key_id,w.identity.wan):w.identity.generation for w in windows})


def test_loss_late_duplicate_and_jitter_have_defined_denominators():
    replies=(ProbeReply(0,10),ProbeReply(1,30),ProbeReply(1,40),ProbeReply(2,900),ProbeReply(3,20))
    metrics=window_metrics(window(count=5,replies=replies),now=125,minimum_samples=2)
    assert metrics['received_on_time']==3
    assert metrics['loss_rate']==.4
    assert metrics['late_replies']==1 and metrics['duplicates']==1
    assert metrics['median_ms']==20 and metrics['p95_ms']==30
    assert metrics['jitter_ms']==15


def test_http_is_not_udp_or_game_ping():
    metrics=window_metrics(window(kind='https'),now=125)
    assert metrics['metric_kind']=='https_response_time'
    assert metrics['loss_rate'] is None and metrics['jitter_ms'] is None
    assert metrics['http_failure_rate']==0
    assert select(window(kind='https'))['recommended'] is None


@pytest.mark.parametrize('field,value,reason',[
    ('wan_verified',False,'wan_unverified'),('source_verified',False,'source_unverified'),
    ('udp_associate_verified',False,'udp_unverified'),
])
def test_unproven_route_is_not_ranked(field,value,reason):
    w=replace(window(),**{field:value})
    assert select(w)['excluded'][0]['reason']==reason


def test_direct_requires_explicit_permission():
    direct=window(protocol='direct',latency=1)
    proxy=window(latency=50)
    assert select(direct,proxy)['recommended']==proxy.identity
    assert select(direct,proxy,direct_allowed=True)['recommended']==direct.identity


def test_partial_fast_route_does_not_win_over_stable_route():
    bad=window(protocol='vless2',replies=tuple(ProbeReply(i,1) for i in range(19)))
    stable=window(latency=50)
    assert select(bad,stable)['recommended']==stable.identity


def test_tail_precedes_median():
    spikes=window(protocol='vless2',replies=tuple(ProbeReply(i,490 if i>=18 else 1) for i in range(20)))
    stable=window(latency=50)
    assert select(spikes,stable)['recommended']==stable.identity


def test_generations_do_not_reuse_old_observations():
    w=window()
    result=select(w,generations={('vless','key0','wan0'):4})
    assert result['recommended'] is None
    assert result['excluded'][0]['reason']=='generation_changed'


@pytest.mark.parametrize('now,reason',[(119,'clock_changed'),(1021,'stale')])
def test_stale_and_future_measurements(now,reason):
    assert window_metrics(window(),now=now)['reason']==reason


def test_sample_count_missing_metrics_and_no_zero_loss_invention():
    result=window_metrics(window(count=1,replies=()),now=125)
    assert result['reason']=='insufficient_samples'
    assert result['median_ms'] is None and result['p95_ms'] is None
    assert result['loss_rate']==1
    assert result['jitter_ms'] is None


@pytest.mark.parametrize('identity',[
    {'device':'console'}, {'destination':'other-service'}, {'endpoint_id':'other-server'}, {'test_kind':'https'},
])
def test_cannot_merge_different_scopes(identity):
    with pytest.raises(ValueError,match='different scopes'):
        select(window(),replace(window(protocol='vless2'),identity=replace(window().identity,**identity)))


def test_multiple_verified_wans_are_distinct_candidates():
    a,b=window(wan='wan0',latency=80),window(wan='wan1',latency=40)
    assert select(a,b)['recommended']==b.identity
    assert select(a,b)['eligible_count']==2


@pytest.mark.parametrize('value',[math.nan,math.inf,-1,True,'5'])
def test_reject_invalid_latencies(value):
    with pytest.raises(ValueError):ProbeReply(1,value)


def test_duplicate_windows_and_unbounded_samples_rejected():
    with pytest.raises(ValueError):select(window(),window())
    with pytest.raises(ValueError):window(count=65)
    with pytest.raises(ValueError):replace(window(),replies=tuple(ProbeReply(0,1) for _ in range(41)))
    with pytest.raises(ValueError):replace(window(),replies=(ProbeReply(25,1),))


def test_safe_identity_does_not_accept_raw_urls_or_keys():
    with pytest.raises(ValueError):window(key_id='vless://private@example.invalid')
    with pytest.raises(ValueError):window(endpoint_id='https://example.com/token')


def test_metrics_do_not_mutate_evidence():
    w=window();before=repr(w)
    select(w);window_metrics(w,now=125)
    assert repr(w)==before
