import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from route_diagnostics_runtime import RouteDiagnosticsRuntime
from route_profiles import RouteProfileStore


class DeferredThread:
    def __init__(self,*,target,args,**kwargs):self.target,self.args=target,args
    def start(self):pass
    def run(self):self.target(*self.args)


def setup(tmp_path,measure=None):
    store=RouteProfileStore(tmp_path/'profiles.json',lock=threading.RLock())
    profile={'id':'abcdef123456','label':'Проверка','device':'router','destination':'example.com',
        'url':'https://example.com/','wan':'eth1','protocols':['vless'],'direct_allowed':False}
    store.save(profile,expected_revision=0)
    runtime=RouteDiagnosticsRuntime(store=store,capture_keys=lambda:({'vless':'private'},SimpleNamespace(generation=3)),
        current=lambda ticket:True,coordinated=lambda name,callback:(True,callback()),probe_lock=threading.Lock(),
        resource_guard=lambda:True,measure=measure or (lambda *a,**kw:{'recommended_protocol':'vless'}),thread_factory=DeferredThread)
    return runtime,store,profile


def test_single_job_and_release_probe_lock(tmp_path):
    runtime,store,profile=setup(tmp_path)
    runtime.start(profile['id'])
    with pytest.raises(ValueError,match='уже выполняется'):runtime.start(profile['id'])
    runtime._thread.run()
    state=runtime.snapshot()
    assert state['job']['state']=='completed' and not state['job']['running']
    assert not runtime.probe_lock.locked()
    assert state['results'][profile['id']]['profile_fingerprint']


def test_manual_intent_rejects_late_result(tmp_path):
    runtime,store,profile=setup(tmp_path)
    runtime.start(profile['id']);runtime.current=lambda ticket:False
    runtime._thread.run()
    assert runtime.snapshot()['job']['state']=='cancelled'
    assert runtime.snapshot()['results']=={}


def test_profile_changed_during_probe_rejects_result(tmp_path):
    runtime,store,profile=setup(tmp_path)
    def measure(*args,**kwargs):
        store.save(profile|{'url':'https://example.com/new'},expected_revision=1)
        return {'recommended_protocol':'vless'}
    runtime.measure=measure;runtime.start(profile['id']);runtime._thread.run()
    assert runtime.snapshot()['results']=={}
    assert not runtime.probe_lock.locked()


def test_cancellation_and_errors_release_all_locks(tmp_path):
    runtime,store,profile=setup(tmp_path)
    runtime.start(profile['id']);runtime.cancel();runtime._thread.run()
    assert runtime.snapshot()['job']['state']=='cancelled'
    def fail(*args,**kwargs):raise RuntimeError('private-key-must-not-escape')
    runtime.measure=fail;runtime.start(profile['id']);runtime._thread.run()
    assert runtime.snapshot()['job']['state']=='failed'
    assert 'private' not in str(runtime.snapshot())
    assert not runtime.probe_lock.locked()


def test_no_parallel_pool_probe_or_background_worker(tmp_path):
    runtime,store,profile=setup(tmp_path)
    runtime.probe_lock.acquire()
    with pytest.raises(ValueError):runtime.start(profile['id'])
    runtime.probe_lock.release()
    runtime.coordinated=lambda *args:(False,None)
    runtime.start(profile['id']);runtime._thread.run()
    assert runtime.snapshot()['job']['state']=='busy' and not runtime.snapshot()['results']


def test_resource_guard_and_returned_snapshot(tmp_path):
    runtime,store,profile=setup(tmp_path)
    runtime.resource_guard=lambda:False
    with pytest.raises(ValueError):runtime.start(profile['id'])
    state=runtime.snapshot();state['job']['running']=True
    assert not runtime.snapshot()['job']['running']


def test_apply_snapshot_precedes_probe_slot_to_avoid_manual_apply_deadlock(tmp_path):
    runtime,store,profile=setup(tmp_path)
    def capture():
        assert not runtime.probe_lock.locked()
        return {},SimpleNamespace(generation=3)
    runtime.capture_keys=capture
    runtime.start(profile['id']);runtime._thread.run()
    assert runtime.snapshot()['job']['state']=='completed'


def test_shutdown_waits_for_cleanup_without_leaving_probe_thread(tmp_path):
    runtime,store,profile=setup(tmp_path)
    entered=threading.Event();cleaned=threading.Event()
    def measure(*args,still_current,**kwargs):
        entered.set()
        try:
            while still_current():
                runtime._cancel.wait(.01)
            return {}
        finally:
            cleaned.set()
    runtime.measure=measure;runtime.thread_factory=threading.Thread
    runtime.start(profile['id'])
    assert entered.wait(2)
    assert runtime.close(timeout=2)
    assert cleaned.is_set() and not runtime.probe_lock.locked()
    assert not runtime.snapshot()['job']['running']
