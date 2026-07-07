import importlib
import os
import threading
import time


AUTO_RESOLVE_LOCK_PATH = '/opt/var/run/bypass_service_route_auto_resolve.lock'
AUTO_RESOLVE_BUSY_MARKERS = (
    '/opt/bin/unblock_update.sh',
    '/opt/bin/unblock_ipset.sh',
    '/opt/bin/unblock_dnsmasq.sh',
)


class _LazyModule:
    def __init__(self, module_name):
        object.__setattr__(self, '_module_name', module_name)
        object.__setattr__(self, '_module', None)

    def _load(self):
        module = object.__getattribute__(self, '_module')
        if module is None:
            module = importlib.import_module(object.__getattribute__(self, '_module_name'))
            object.__setattr__(self, '_module', module)
        return module

    def __getattr__(self, name):
        return getattr(self._load(), name)

    def __setattr__(self, name, value):
        if name.startswith('_'):
            object.__setattr__(self, name, value)
        else:
            setattr(self._load(), name, value)


key_pool_web = _LazyModule('key_pool_web')
route_intersections = _LazyModule('route_intersections')
service_routes = _LazyModule('service_routes')


def _noop():
    return None


def _process_running(pid):
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name == 'nt':
        return pid == os.getpid()
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _read_process_cmdline(pid, proc_root='/proc'):
    try:
        with open(os.path.join(proc_root, str(pid), 'cmdline'), 'rb') as file:
            return file.read(4096).replace(b'\x00', b' ').decode('utf-8', 'ignore')
    except Exception:
        return ''


def _busy_update_process_running(proc_root='/proc', markers=AUTO_RESOLVE_BUSY_MARKERS):
    try:
        names = os.listdir(proc_root)
    except Exception:
        return False
    for name in names:
        if not str(name).isdigit():
            continue
        cmdline = _read_process_cmdline(name, proc_root=proc_root)
        if cmdline and any(marker in cmdline for marker in markers):
            return True
    return False


def _read_auto_resolve_lock(lock_path):
    try:
        with open(lock_path, 'r', encoding='utf-8', errors='ignore') as file:
            parts = file.read().strip().split()
    except Exception:
        return 0, 0.0
    pid = 0
    timestamp = 0.0
    if parts:
        try:
            pid = int(parts[0])
        except (TypeError, ValueError):
            pid = 0
    if len(parts) > 1:
        try:
            timestamp = float(parts[1])
        except (TypeError, ValueError):
            timestamp = 0.0
    return pid, timestamp


class ServiceRouteToolsRuntime:
    def __init__(
        self,
        *,
        custom_check_presets_getter,
        service_icon_html,
        telegram_icon_html,
        youtube_icon_html,
        sync_udp_policy_config=None,
        invalidate_web_status_cache=None,
        intersections_cache_ttl=20.0,
        auto_resolve_cooldown=300.0,
        auto_resolve_lock_path=AUTO_RESOLVE_LOCK_PATH,
        auto_resolve_lock_ttl=600.0,
        time_provider=time.time,
        thread_factory=threading.Thread,
    ):
        self.custom_check_presets_getter = custom_check_presets_getter
        self.service_icon_html = service_icon_html
        self.telegram_icon_html = telegram_icon_html
        self.youtube_icon_html = youtube_icon_html
        self.sync_udp_policy_config = sync_udp_policy_config or _noop
        self.invalidate_web_status_cache = invalidate_web_status_cache or _noop
        self.intersections_cache_ttl = max(1.0, float(intersections_cache_ttl or 1.0))
        self.auto_resolve_cooldown = max(30.0, float(auto_resolve_cooldown or 30.0))
        self.auto_resolve_lock_path = str(auto_resolve_lock_path or '').strip()
        self.auto_resolve_lock_ttl = max(60.0, float(auto_resolve_lock_ttl or 60.0))
        self._time = time_provider or time.time
        self._thread_factory = thread_factory or threading.Thread
        self._intersections_lock = threading.Lock()
        self._intersections_cache = {'signature': None, 'timestamp': 0.0, 'report': None}
        self._auto_resolve_cache = {'signature': None, 'timestamp': 0.0, 'running': False, 'result': None}
        self._auto_resolve_worker = None
        self._service_items_cache = {'signature': None, 'items': None}
        self._summary_cache = {'signature': None, 'summary': None}

    def _route_files_signature(self):
        return route_intersections.route_files_signature()

    def _custom_presets_signature(self, presets):
        signature = []
        for item in presets or []:
            if not isinstance(item, dict):
                continue
            signature.append((
                str(item.get('id') or ''),
                str(item.get('label') or ''),
                str(item.get('url') or ''),
                str(item.get('badge') or ''),
                str(item.get('icon') or ''),
                tuple(str(value) for value in (item.get('urls') or [])),
                tuple(str(value) for value in (item.get('routes') or [])),
            ))
        return tuple(signature)

    def _intersections_signature(self, include_runtime=True):
        return (
            self._route_files_signature(),
            route_intersections.runtime_ipset_signature() if include_runtime else None,
            bool(include_runtime),
        )

    def _auto_resolve_signature(self, report, signature):
        issue_parts = []
        for issue in (report.get('issues') or [])[:16]:
            service_keys = tuple(sorted(str(key or '') for key in (issue.get('service_keys') or []) if key))
            if not service_keys:
                continue
            samples = tuple(str(value or '') for value in (issue.get('samples') or issue.get('entries') or [])[:5])
            issue_parts.append((
                str(issue.get('kind') or ''),
                tuple(str(route or '') for route in (issue.get('routes') or [])),
                service_keys,
                samples,
            ))
        return (signature[0], tuple(issue_parts))

    def _auto_resolve_lock_active(self, lock_path, now):
        if _busy_update_process_running():
            return True
        pid, timestamp = _read_auto_resolve_lock(lock_path)
        if pid and _process_running(pid):
            return True
        if timestamp and now - timestamp < self.auto_resolve_lock_ttl:
            return True
        try:
            os.unlink(lock_path)
        except FileNotFoundError:
            pass
        except Exception:
            return True
        return False

    def _acquire_auto_resolve_lock(self, auto_signature):
        if not self.auto_resolve_lock_path:
            return '', None
        now = self._time()
        if _busy_update_process_running():
            return '', {'status': 'running', 'signature': auto_signature, 'external': True}
        directory = os.path.dirname(self.auto_resolve_lock_path)
        if directory:
            try:
                os.makedirs(directory, exist_ok=True)
            except Exception:
                return '', {'status': 'running', 'signature': auto_signature, 'external': True}
        payload = f'{os.getpid()} {now:.3f}\n'
        for _attempt in range(2):
            try:
                fd = os.open(self.auto_resolve_lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
                try:
                    os.write(fd, payload.encode('ascii', 'ignore'))
                finally:
                    os.close(fd)
                return self.auto_resolve_lock_path, None
            except FileExistsError:
                if self._auto_resolve_lock_active(self.auto_resolve_lock_path, now):
                    return '', {'status': 'running', 'signature': auto_signature, 'external': True}
            except Exception:
                return '', {'status': 'running', 'signature': auto_signature, 'external': True}
        return '', {'status': 'running', 'signature': auto_signature, 'external': True}

    def _release_auto_resolve_lock(self, lock_path):
        if not lock_path:
            return
        pid, _timestamp = _read_auto_resolve_lock(lock_path)
        if pid and pid != os.getpid():
            return
        try:
            os.unlink(lock_path)
        except FileNotFoundError:
            pass
        except Exception:
            pass

    def _maybe_auto_resolve_intersections(self, report, signature):
        if not int(report.get('count') or 0):
            return None
        auto_signature = self._auto_resolve_signature(report, signature)
        if not auto_signature[1]:
            return None
        now = self._time()
        with self._intersections_lock:
            cached = dict(self._auto_resolve_cache)
            if cached.get('signature') == auto_signature:
                if cached.get('running'):
                    if now - float(cached.get('timestamp') or 0.0) < self.auto_resolve_lock_ttl:
                        return {'status': 'running', 'signature': auto_signature}
                if now - float(cached.get('timestamp') or 0.0) < self.auto_resolve_cooldown:
                    result = cached.get('result')
                    if isinstance(result, dict):
                        return dict(result)
                    return None
            self._auto_resolve_cache = {
                'signature': auto_signature,
                'timestamp': now,
                'running': True,
                'result': None,
            }
        lock_path, external_result = self._acquire_auto_resolve_lock(auto_signature)
        if external_result:
            with self._intersections_lock:
                self._auto_resolve_cache = {
                    'signature': auto_signature,
                    'timestamp': now,
                    'running': True,
                    'result': dict(external_result),
                }
            return dict(external_result)
        service_items = self.service_items()
        worker = self._thread_factory(
            target=self._auto_resolve_intersections_worker,
            args=(dict(report), service_items, auto_signature, lock_path),
            daemon=True,
        )
        self._auto_resolve_worker = worker
        worker.start()
        return {'status': 'scheduled', 'signature': auto_signature}

    def _auto_resolve_intersections_worker(self, report, service_items, auto_signature, lock_path):
        try:
            result = service_routes.auto_resolve_service_route_intersections(
                report=report,
                service_items=service_items,
                before_update=self.sync_udp_policy_config,
            )
            result['status'] = 'finished'
        except Exception as exc:
            result = {'status': 'error', 'services': 0, 'error': str(exc)}
        finally:
            self._release_auto_resolve_lock(lock_path)
        if result.get('services'):
            self.invalidate_web_status_cache()
        with self._intersections_lock:
            self._auto_resolve_cache = {
                'signature': auto_signature,
                'timestamp': self._time(),
                'running': False,
                'result': dict(result),
            }
            self._intersections_cache = {'signature': None, 'timestamp': 0.0, 'report': None}
            self._summary_cache = {'signature': None, 'summary': None}

    def _service_items_snapshot(self):
        presets = self.custom_check_presets_getter()
        signature = self._custom_presets_signature(presets)
        with self._intersections_lock:
            cached_items = self._service_items_cache.get('items')
            if cached_items is not None and self._service_items_cache.get('signature') == signature:
                return [dict(item) for item in cached_items], signature
        items = service_routes.route_service_items(presets=presets)
        with self._intersections_lock:
            self._service_items_cache = {'signature': signature, 'items': [dict(item) for item in items]}
        return [dict(item) for item in items], signature

    def service_items(self):
        items, _signature = self._service_items_snapshot()
        return items

    def summary(self):
        items, service_items_signature = self._service_items_snapshot()
        signature = (self._route_files_signature(), service_items_signature)
        with self._intersections_lock:
            cached_summary = self._summary_cache.get('summary')
            if cached_summary is not None and self._summary_cache.get('signature') == signature:
                return dict(cached_summary)
        summary = service_routes.service_route_summary(items)
        with self._intersections_lock:
            self._summary_cache = {'signature': signature, 'summary': dict(summary)}
        return dict(summary)

    def standalone_custom_checks(self, custom_checks):
        route_service_ids = {item.get('id') for item in self.service_items()}
        return [
            check for check in (custom_checks or [])
            if check.get('id') not in route_service_ids
        ]

    def intersections_snapshot(self, include_runtime=True):
        now = self._time()
        include_runtime = bool(include_runtime)
        signature = self._intersections_signature(include_runtime=include_runtime)
        with self._intersections_lock:
            cached_report = self._intersections_cache.get('report')
            cached_timestamp = float(self._intersections_cache.get('timestamp') or 0.0)
            if (
                cached_report is not None
                and self._intersections_cache.get('signature') == signature
                and now - cached_timestamp < self.intersections_cache_ttl
            ):
                return dict(cached_report)
        try:
            report = route_intersections.analyze_route_intersections(include_runtime=include_runtime)
        except TypeError as exc:
            if 'include_runtime' not in str(exc) and 'unexpected keyword' not in str(exc):
                raise
            report = route_intersections.analyze_route_intersections()
        auto_result = self._maybe_auto_resolve_intersections(report, signature)
        cacheable_report = True
        if auto_result and auto_result.get('status') in ('scheduled', 'running'):
            report['auto_resolve_pending'] = dict(auto_result)
            auto_signature = auto_result.get('signature')
            with self._intersections_lock:
                cacheable_report = bool(
                    self._auto_resolve_cache.get('running') and
                    self._auto_resolve_cache.get('signature') == auto_signature
                )
        elif auto_result and auto_result.get('services'):
            report['auto_resolved'] = dict(auto_result)
        if cacheable_report:
            with self._intersections_lock:
                self._intersections_cache = {
                    'signature': signature,
                    'timestamp': now,
                    'report': dict(report),
                }
        return dict(report)

    def invalidate_intersections_cache(self):
        with self._intersections_lock:
            self._intersections_cache = {'signature': None, 'timestamp': 0.0, 'report': None}
            self._auto_resolve_cache = {'signature': None, 'timestamp': 0.0, 'running': False, 'result': None}
            self._summary_cache = {'signature': None, 'summary': None}

    def apply_service_route(self, service_key, target_protocol):
        result = service_routes.apply_service_route(
            service_key,
            target_protocol,
            before_update=self.sync_udp_policy_config,
        )
        self.invalidate_intersections_cache()
        self.invalidate_web_status_cache()
        return result

    def apply_service_profile(self, profile_id):
        result = service_routes.apply_service_profile(
            profile_id,
            service_items=self.service_items(),
            before_update=self.sync_udp_policy_config,
        )
        self.invalidate_intersections_cache()
        self.invalidate_web_status_cache()
        return result

    def resolve_route_intersections(self, target_route):
        result = route_intersections.resolve_route_intersections(
            target_route,
            before_update=self.sync_udp_policy_config,
        )
        self.invalidate_intersections_cache()
        self.invalidate_web_status_cache()
        return result

    def tools_html(
        self,
        csrf_input_html,
        custom_checks=None,
        *,
        include_intersections=True,
        include_runtime_intersections=False,
    ):
        service_items = self.service_items()
        route_states = service_routes.service_route_summary(service_items)
        protocol_options = service_routes.protocol_options()
        active_check_ids = {check.get('id') for check in custom_checks or []}
        if include_intersections:
            intersections_html = key_pool_web.web_route_intersections_html(
                self.intersections_snapshot(include_runtime=include_runtime_intersections),
                protocol_options,
                csrf_input_html=csrf_input_html,
            )
        else:
            intersections_html = '''<div class="route-intersection-card" data-route-tools-deferred="1">
                <strong>Проверяю пересечения списков</strong>
                <small>Маршруты загрузятся без блокировки интерфейса.</small>
            </div>'''
        return ''.join([
            key_pool_web.web_route_profiles_html(
                service_routes.ROUTE_PROFILES,
                csrf_input_html=csrf_input_html,
            ),
            intersections_html,
            key_pool_web.web_service_route_tools_html(
                service_items,
                route_states,
                protocol_options,
                self.service_icon_html,
                csrf_input_html=csrf_input_html,
                active_check_ids=active_check_ids,
                core_icon_html={
                    'telegram': self.telegram_icon_html(opacity=1.0),
                    'youtube': self.youtube_icon_html(opacity=1.0),
                },
            ),
        ])
