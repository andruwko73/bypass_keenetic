"""Diagnostic job lifecycle inside the existing background/probe coordinator."""
from copy import deepcopy
import threading
import time

from route_profiles import profile_fingerprint
from route_probe_runtime import DiagnosticCancelled, measure_profile


class RouteDiagnosticsRuntime:
    def __init__(self, *, store, capture_keys, current, coordinated, probe_lock,
                 resource_guard, measure=measure_profile, thread_factory=threading.Thread):
        self.store,self.capture_keys,self.current=store,capture_keys,current
        self.coordinated,self.probe_lock,self.resource_guard=coordinated,probe_lock,resource_guard
        self.measure,self.thread_factory=measure,thread_factory
        self._lock=threading.Lock();self._cancel=threading.Event();self._thread=None
        self._job={'running':False,'profile_id':'','state':'idle'}
        self._results={}

    def _profile(self,profile_id):
        matches=[p for p in self.store.snapshot()['profiles'] if p['id']==profile_id]
        if len(matches)!=1:raise ValueError('Профиль не найден. Обновите страницу.')
        return matches[0]

    def snapshot(self):
        with self._lock:
            return {'job':deepcopy(self._job),'results':deepcopy(self._results)}

    def start(self,profile_id):
        profile=self._profile(profile_id)
        if not self.resource_guard() or self.probe_lock.locked():
            raise ValueError('Сейчас выполняется другая проверка или роутер занят. Повторите позже.')
        with self._lock:
            if self._job['running']:raise ValueError('Диагностика уже выполняется. Дождитесь результата.')
            self._cancel.clear()
            self._job={'running':True,'profile_id':profile_id,'state':'queued','started_at':time.time()}
            self._thread=self.thread_factory(target=self._run,args=(profile,),name='route-diagnostics',daemon=True)
            try:self._thread.start()
            except BaseException:
                self._job.update(running=False,state='failed');self._thread=None
                raise

    def cancel(self):
        self._cancel.set()
        with self._lock:
            if self._job['running']:self._job['state']='cancelling'

    def close(self, timeout=12):
        """Give an in-flight request and owned-core cleanup bounded exit time."""
        self.cancel()
        with self._lock:
            thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=timeout)
        return not (thread and thread.is_alive())

    def _run(self,profile):
        state='failed';result=None
        def work():
            # Snapshot under the apply lock BEFORE claiming the probe slot.
            # Manual apply may own that lock while waiting for probe cleanup.
            keys,ticket=self.capture_keys()
            if not self.probe_lock.acquire(blocking=False):raise DiagnosticCancelled('busy')
            try:
                fingerprint=profile_fingerprint(profile)
                def still_current():
                    if self._cancel.is_set() or not self.current(ticket):return False
                    try:return profile_fingerprint(self._profile(profile['id']))==fingerprint
                    except ValueError:return False
                with self._lock:self._job['state']='running'
                output=self.measure(profile,keys,generation=ticket.generation,
                    still_current=still_current,resource_guard=self.resource_guard)
                if not still_current():raise DiagnosticCancelled('generation_changed')
                output['profile_fingerprint']=fingerprint
                return output
            finally:self.probe_lock.release()
        try:
            ran,result=self.coordinated('route diagnostics',work)
            state='completed' if ran else 'busy'
        except DiagnosticCancelled:
            state='cancelled'
        except Exception:
            # Upstream exceptions may include endpoint/key material. Only a
            # fixed state is exposed; there is no raw traceback or error text.
            state='failed'
        finally:
            with self._lock:
                if state=='completed' and result is not None:
                    self._results[profile['id']]=result
                    while len(self._results)>8:self._results.pop(next(iter(self._results)))
                self._job.update(running=False,state=state,finished_at=time.time())
