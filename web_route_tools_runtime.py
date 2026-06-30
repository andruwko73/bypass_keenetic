import key_pool_web
import route_intersections
import service_routes
import threading
import time


def _noop():
    return None


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
    ):
        self.custom_check_presets_getter = custom_check_presets_getter
        self.service_icon_html = service_icon_html
        self.telegram_icon_html = telegram_icon_html
        self.youtube_icon_html = youtube_icon_html
        self.sync_udp_policy_config = sync_udp_policy_config or _noop
        self.invalidate_web_status_cache = invalidate_web_status_cache or _noop
        self.intersections_cache_ttl = max(1.0, float(intersections_cache_ttl or 1.0))
        self.auto_resolve_cooldown = max(30.0, float(auto_resolve_cooldown or 30.0))
        self._intersections_lock = threading.Lock()
        self._intersections_cache = {'signature': None, 'timestamp': 0.0, 'report': None}
        self._auto_resolve_cache = {'signature': None, 'timestamp': 0.0, 'running': False, 'result': None}
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

    def _intersections_signature(self):
        return (
            self._route_files_signature(),
            route_intersections.runtime_ipset_signature(),
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

    def _maybe_auto_resolve_intersections(self, report, signature):
        if not int(report.get('count') or 0):
            return None
        auto_signature = self._auto_resolve_signature(report, signature)
        if not auto_signature[1]:
            return None
        now = time.time()
        with self._intersections_lock:
            cached = dict(self._auto_resolve_cache)
            if cached.get('signature') == auto_signature:
                if cached.get('running'):
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
        service_items = self.service_items()
        worker = threading.Thread(
            target=self._auto_resolve_intersections_worker,
            args=(dict(report), service_items, auto_signature),
            daemon=True,
        )
        worker.start()
        return {'status': 'scheduled', 'signature': auto_signature}

    def _auto_resolve_intersections_worker(self, report, service_items, auto_signature):
        try:
            result = service_routes.auto_resolve_service_route_intersections(
                report=report,
                service_items=service_items,
                before_update=self.sync_udp_policy_config,
            )
            result['status'] = 'finished'
        except Exception as exc:
            result = {'status': 'error', 'services': 0, 'error': str(exc)}
        if result.get('services'):
            self.invalidate_web_status_cache()
        with self._intersections_lock:
            self._auto_resolve_cache = {
                'signature': auto_signature,
                'timestamp': time.time(),
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

    def intersections_snapshot(self):
        now = time.time()
        signature = self._intersections_signature()
        with self._intersections_lock:
            cached_report = self._intersections_cache.get('report')
            if cached_report is not None and self._intersections_cache.get('signature') == signature:
                return dict(cached_report)
        report = route_intersections.analyze_route_intersections()
        auto_result = self._maybe_auto_resolve_intersections(report, signature)
        if auto_result and auto_result.get('status') in ('scheduled', 'running'):
            report['auto_resolve_pending'] = dict(auto_result)
        elif auto_result and auto_result.get('services'):
            report['auto_resolved'] = dict(auto_result)
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

    def tools_html(self, csrf_input_html, custom_checks=None):
        service_items = self.service_items()
        route_states = service_routes.service_route_summary(service_items)
        protocol_options = service_routes.protocol_options()
        active_check_ids = {check.get('id') for check in custom_checks or []}
        return ''.join([
            key_pool_web.web_route_profiles_html(
                service_routes.ROUTE_PROFILES,
                csrf_input_html=csrf_input_html,
            ),
            key_pool_web.web_route_intersections_html(
                self.intersections_snapshot(),
                protocol_options,
                csrf_input_html=csrf_input_html,
            ),
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
