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
    ):
        self.custom_check_presets_getter = custom_check_presets_getter
        self.service_icon_html = service_icon_html
        self.telegram_icon_html = telegram_icon_html
        self.youtube_icon_html = youtube_icon_html
        self.sync_udp_policy_config = sync_udp_policy_config or _noop
        self.invalidate_web_status_cache = invalidate_web_status_cache or _noop
        self.intersections_cache_ttl = max(1.0, float(intersections_cache_ttl or 1.0))
        self._intersections_lock = threading.Lock()
        self._intersections_cache = {'signature': None, 'timestamp': 0.0, 'report': None}

    def service_items(self):
        return service_routes.route_service_items(presets=self.custom_check_presets_getter())

    def summary(self):
        return service_routes.service_route_summary(self.service_items())

    def standalone_custom_checks(self, custom_checks):
        route_service_ids = {item.get('id') for item in self.service_items()}
        return [
            check for check in (custom_checks or [])
            if check.get('id') not in route_service_ids
        ]

    def intersections_snapshot(self):
        now = time.time()
        signature = (
            route_intersections.route_files_signature(),
            int(now // self.intersections_cache_ttl),
        )
        with self._intersections_lock:
            cached_report = self._intersections_cache.get('report')
            if cached_report is not None and self._intersections_cache.get('signature') == signature:
                return dict(cached_report)
        report = route_intersections.analyze_route_intersections()
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
