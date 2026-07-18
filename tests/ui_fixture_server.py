#!/usr/bin/env python3
"""Local fixture server for the Playwright UI smoke test."""

import argparse
import base64
import hashlib
import html
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
sys.path.insert(0, str(APP_ROOT))
sys.path.insert(0, str(ROOT))

BACKGROUND_STATE = {
    "ok": True,
    "available": False,
    "enabled": False,
    "shade": 55,
    "url": "",
    "size": 0,
    "width": 0,
    "height": 0,
}
BACKGROUND_FIXTURE_URL = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScL4JwAAAABJRU5ErkJggg=="

import key_pool_web  # noqa: E402
import service_routes  # noqa: E402
import web_form_blocks  # noqa: E402
import web_form_template  # noqa: E402
import web_pool_form_blocks  # noqa: E402


def _svg_b64(color, text):
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
        f'<circle cx="16" cy="16" r="15" fill="{color}"/>'
        '<text x="16" y="21" text-anchor="middle" font-size="12" '
        'font-family="Arial" fill="#fff" font-weight="700">'
        f'{html.escape(text)}</text></svg>'
    )
    return base64.b64encode(svg.encode("utf-8")).decode("ascii")


TELEGRAM_SVG_B64 = _svg_b64("#229ed9", "TG")
YOUTUBE_SVG_B64 = _svg_b64("#ff0033", "YT")

CURRENT_KEYS = {
    "vless": "vless://fixture-active-vless@example.test:443?security=reality#active-vless",
    "vless2": "vless://fixture-active-vless2@example.test:443?security=reality#active-vless2",
    "vmess": "",
    "trojan": "",
    "shadowsocks": "",
}

POOLS = {
    "vless": [
        CURRENT_KEYS["vless"],
        "vless://fixture-backup-vless@example.test:443#backup-vless",
    ],
    "vless2": [
        "vless://fixture-backup-vless2@example.test:443#backup-vless2",
        CURRENT_KEYS["vless2"],
    ],
    "vmess": [],
    "trojan": [],
    "shadowsocks": [],
}

CUSTOM_CHECKS = [
    {
        "id": "chatgpt_services",
        "label": "ChatGPT / Codex",
        "url": "https://chatgpt.com/backend-api/models",
        "urls": ["https://chatgpt.com/backend-api/models"],
        "routes": ["chatgpt.com", "chat.openai.com"],
        "badge": "AI",
        "icon": "",
    }
]

ROUTE_SERVICE_ITEMS = [
    {"id": "telegram", "label": "Telegram", "badge": "TG", "icon": ""},
    {"id": "youtube", "label": "YouTube", "badge": "YT", "icon": ""},
    {"id": "chatgpt_services", "label": "ChatGPT / Codex", "badge": "AI", "icon": ""},
]
ROUTE_SERVICE_IDS = {item["id"] for item in ROUTE_SERVICE_ITEMS}

ROUTE_STATES = {
    "telegram": {"label": "Vless 1"},
    "youtube": {"label": "Vless 2"},
    "chatgpt_services": {"label": "частично: Vless 1 / Vless 2"},
}

APP_MODE_FIXTURES = {
    "simple": {
        "label": "Simple",
        "description": "fixture interface and Telegram bot",
        "pool": False,
        "telegram": True,
    },
    "advanced": {
        "label": "Advanced",
        "description": "fixture with key pool and Telegram bot",
        "pool": True,
        "telegram": True,
    },
    "web_only": {
        "label": "Web only",
        "description": "fixture key-pool web UI without Telegram bot",
        "pool": True,
        "telegram": False,
    },
}


def _normalize_app_mode(mode):
    mode = str(mode or "").strip().lower().replace("-", "_")
    return mode if mode in APP_MODE_FIXTURES else "advanced"


def _hash_key(key_value):
    return hashlib.sha256((key_value or "").encode("utf-8")).hexdigest()


def _display_name(key_value):
    marker = (key_value or "").split("#", 1)[-1].strip()
    return marker or _hash_key(key_value)[:12]


def _probe_cache():
    now = int(time.time())
    cache = {}
    for proto, keys in POOLS.items():
        for index, key_value in enumerate(keys):
            cache[_hash_key(key_value)] = {
                "tg_ok": proto == "vless" or index == 0,
                "yt_ok": proto == "vless2" or index == 0,
                "custom": {"chatgpt_services": index == 0},
                "ts": now - (index * 60),
            }
    return cache


def _telegram_icon_html(opacity=1.0):
    return (
        '<img class="service-icon-img" src="data:image/svg+xml;base64,'
        f'{TELEGRAM_SVG_B64}" width="16" height="16" alt="Telegram" '
        f'style="vertical-align:middle;opacity:{float(opacity):.2f}">'
    )


def _youtube_icon_html(opacity=1.0):
    return (
        '<img class="service-icon-img" src="data:image/svg+xml;base64,'
        f'{YOUTUBE_SVG_B64}" width="16" height="16" alt="YouTube" '
        f'style="vertical-align:middle;opacity:{float(opacity):.2f}">'
    )


def _service_icon_html(icon, alt, opacity=1.0, size=18):
    label = (alt or icon or "WEB")[:3].upper()
    return (
        f'<span class="custom-service-badge custom-service-neutral" '
        f'title="{html.escape(str(alt or ""))}" '
        f'style="opacity:{float(opacity):.2f};min-width:{int(size)}px">'
        f'{html.escape(label)}</span>'
    )


def _status():
    return {
        "api_status": "ok",
        "proxy_mode": "vless",
        "socks_details": "SOCKS fixture is reachable.",
        "fallback_reason": "",
    }


def _protocol_statuses():
    return {
        "vless": {
            "tone": "ok",
            "label": "Works",
            "details": "Telegram and service checks pass on Vless 1.",
            "api_ok": True,
            "yt_ok": False,
            "custom": {"chatgpt_services": "ok"},
        },
        "vless2": {
            "tone": "ok",
            "label": "Works",
            "details": "YouTube checks pass on Vless 2.",
            "api_ok": False,
            "yt_ok": True,
            "custom": {"chatgpt_services": "ok"},
        },
        "vmess": {
            "tone": "empty",
            "label": "Empty",
            "details": "No active key in fixture.",
            "api_ok": False,
            "yt_ok": False,
            "custom": {"chatgpt_services": "unknown"},
        },
        "trojan": {
            "tone": "empty",
            "label": "Empty",
            "details": "No active key in fixture.",
            "api_ok": False,
            "yt_ok": False,
            "custom": {"chatgpt_services": "unknown"},
        },
        "shadowsocks": {
            "tone": "empty",
            "label": "Empty",
            "details": "No active key in fixture.",
            "api_ok": False,
            "yt_ok": False,
            "custom": {"chatgpt_services": "unknown"},
        },
    }


def _live_protocol_statuses():
    statuses = {proto: dict(status) for proto, status in _protocol_statuses().items()}
    statuses["vless"].update(
        {
            "details": "Live status only has the current Telegram endpoint result.",
            "api_ok": True,
            "yt_ok": False,
            "custom": {},
            "endpoint_ok": True,
        }
    )
    return statuses


def _router_health():
    return {
        "memory_text": "Память: доступно 256 MB из 512 MB",
        "note": "Занято по данным роутера: 256 MB (50%); Нагрузка CPU: 2%\nПрограмма использует 42 MB RAM; Flash-носитель: занято 384 из 1024 MB (38%)",
        "dns_note": "DNS: ndnproxy; S56dnsmasq не используется; ipset обновлён: 1 мин назад; записи ipset: VLESS=488, VLESSUDP=187, VLESS2=340, VLESS2UDP=328, VMESS=0, VMESSUDP=0, Trojan=0, TrojanUDP=0, ShadowSocks=0, ShadowSocksUDP=0",
        "core_proxy_note": "Прокси: Xray работает на портах: 10811, 10812, 10813, 10814",
        "telegram_call_note": "Звонки через TPROXY работают для Telegram/WhatsApp/Discord на порте: Vless 11812",
        "used_percent": 50,
        "flash_storage_path": "/opt",
        "flash_total_kb": 1024 * 1024,
        "flash_used_kb": 384 * 1024,
        "flash_free_kb": 640 * 1024,
        "flash_used_percent": 38,
        "pool_probe_running": False,
    }


def _pool_summary(cache=None):
    return key_pool_web.pool_status_summary(
        CURRENT_KEYS,
        POOLS,
        cache or _probe_cache(),
        CUSTOM_CHECKS,
        _hash_key,
    )


def _pool_snapshot(protocols=None):
    return key_pool_web.web_pool_snapshot(
        CURRENT_KEYS,
        POOLS,
        _probe_cache(),
        CUSTOM_CHECKS,
        include_keys=False,
        hash_key=_hash_key,
        display_name=_display_name,
        probe_state=key_pool_web.web_probe_state,
        probe_checked_at=key_pool_web.web_probe_checked_at,
        protocols=protocols,
    )


def _route_tools_html(csrf_input_html):
    return "".join(
        [
            key_pool_web.web_route_profiles_html(
                service_routes.ROUTE_PROFILES,
                csrf_input_html=csrf_input_html,
            ),
            key_pool_web.web_route_intersections_html(
                {
                    "count": 1,
                    "issues": [
                        {
                            "message": "chatgpt.com пересекается с api.chatgpt.com",
                        }
                    ],
                },
                service_routes.protocol_options(),
                csrf_input_html=csrf_input_html,
            ),
            key_pool_web.web_service_route_tools_html(
                ROUTE_SERVICE_ITEMS,
                ROUTE_STATES,
                service_routes.protocol_options(),
                _service_icon_html,
                csrf_input_html=csrf_input_html,
                active_check_ids={item["id"] for item in CUSTOM_CHECKS},
                core_icon_html={
                    "telegram": _telegram_icon_html(opacity=1.0),
                    "youtube": _youtube_icon_html(opacity=1.0),
                },
            ),
        ]
    )


def _protocol_panel(protocol):
    protocol_sections = [section for section in web_form_blocks.PROTOCOL_SECTIONS if section[0] == protocol]
    if not protocol_sections:
        raise ValueError("unknown protocol")
    cache = _probe_cache()
    csrf_input_html = web_form_blocks.render_csrf_input("fixture-token")
    custom_presets_html = ""
    custom_checks_html = ""
    route_tools_html = ""
    table_class, custom_width, mobile_width = web_pool_form_blocks.pool_table_layout(CUSTOM_CHECKS)
    _tabs, panels = web_pool_form_blocks.render_protocol_tabs_and_panels(
        protocol_sections,
        CURRENT_KEYS,
        _protocol_statuses(),
        csrf_input_html,
        key_pools=POOLS,
        key_probe_cache=cache,
        custom_checks=CUSTOM_CHECKS,
        key_display_name=_display_name,
        hash_key=_hash_key,
        telegram_icon_html=_telegram_icon_html,
        youtube_icon_html=_youtube_icon_html,
        custom_check_badges=lambda probe, checks: key_pool_web.web_custom_check_badges(
            probe,
            checks,
            _service_icon_html,
        ),
        probe_checked_at=key_pool_web.web_probe_checked_at,
        custom_probe_states=key_pool_web.web_custom_probe_states,
        service_icon_html=_service_icon_html,
        pool_table_class=table_class,
        pool_custom_col_width=custom_width,
        pool_mobile_custom_col_width=mobile_width,
        custom_header_icons=key_pool_web.custom_check_header_icons(CUSTOM_CHECKS, _service_icon_html),
        custom_presets_html=custom_presets_html,
        custom_checks_html=custom_checks_html,
        route_tools_html=route_tools_html,
        active_protocol=protocol,
        pool_probe_pending=False,
        defer_pool_rows=True,
        defer_check_content=True,
    )
    return panels


def _protocol_check_panel(protocol):
    protocol_sections = [section for section in web_form_blocks.PROTOCOL_SECTIONS if section[0] == protocol]
    if not protocol_sections:
        raise ValueError("unknown protocol")
    _key_name, title, _rows, _placeholder = protocol_sections[0]
    csrf_input_html = web_form_blocks.render_csrf_input("fixture-token")
    custom_presets_html = key_pool_web.web_custom_presets_html(
        CUSTOM_CHECKS,
        [],
        _service_icon_html,
        csrf_input_html,
    )
    custom_checks_html = key_pool_web.web_custom_checks_html(
        [item for item in CUSTOM_CHECKS if item.get("id") not in ROUTE_SERVICE_IDS],
        _service_icon_html,
        csrf_input_html,
        empty_message="",
    )
    route_tools_html = _route_tools_html(csrf_input_html)
    return web_pool_form_blocks.render_protocol_check_content(
        key_name=protocol,
        title=title,
        status_info=_protocol_statuses().get(protocol, {}),
        custom_presets_html=custom_presets_html,
        custom_checks_html=custom_checks_html,
        route_tools_html=route_tools_html,
        csrf_input_html=csrf_input_html,
        enable_key_pool=True,
        enable_custom_checks=True,
        pool_probe_pending=False,
    )


def _page_html(mode="advanced"):
    mode = _normalize_app_mode(mode)
    mode_fixture = APP_MODE_FIXTURES[mode]
    enable_key_pool = bool(mode_fixture["pool"])
    enable_telegram = bool(mode_fixture["telegram"])
    enable_custom_checks = enable_key_pool
    cache = _probe_cache() if enable_key_pool else {}
    csrf_input_html = web_form_blocks.render_csrf_input("fixture-token")
    status = _status()
    current_mode_label = web_form_blocks.proxy_mode_label(status["proxy_mode"])
    form_basics = web_form_blocks.render_form_basics(
        "",
        {"running": False},
        status,
        CURRENT_KEYS,
        current_mode_label,
        live=True,
    )
    if enable_custom_checks:
        custom_presets_html = ""
        custom_checks_html = ""
        route_tools_html = ""
        table_class, custom_width, mobile_width = web_pool_form_blocks.pool_table_layout(CUSTOM_CHECKS)
    else:
        custom_presets_html = ""
        custom_checks_html = ""
        route_tools_html = ""
        table_class, custom_width, mobile_width = web_pool_form_blocks.pool_table_layout([])
    protocol_tabs_html, protocol_panels_html = web_pool_form_blocks.render_protocol_tabs_and_panels(
        web_form_blocks.PROTOCOL_SECTIONS,
        CURRENT_KEYS,
        _protocol_statuses(),
        csrf_input_html,
        key_pools=POOLS if enable_key_pool else None,
        key_probe_cache=cache if enable_key_pool else None,
        custom_checks=CUSTOM_CHECKS if enable_custom_checks else None,
        key_display_name=_display_name,
        hash_key=_hash_key,
        telegram_icon_html=_telegram_icon_html,
        youtube_icon_html=_youtube_icon_html,
        custom_check_badges=lambda probe, checks: key_pool_web.web_custom_check_badges(
            probe,
            checks,
            _service_icon_html,
        ),
        probe_checked_at=key_pool_web.web_probe_checked_at,
        custom_probe_states=key_pool_web.web_custom_probe_states,
        service_icon_html=_service_icon_html,
        pool_table_class=table_class,
        pool_custom_col_width=custom_width,
        pool_mobile_custom_col_width=mobile_width,
        custom_header_icons=key_pool_web.custom_check_header_icons(CUSTOM_CHECKS, _service_icon_html) if enable_custom_checks else "",
        custom_presets_html=custom_presets_html,
        custom_checks_html=custom_checks_html,
        route_tools_html=route_tools_html,
        active_protocol="vless",
        lazy_protocol_panels=True,
        enable_key_pool=enable_key_pool,
        enable_custom_checks=enable_custom_checks,
        pool_probe_pending=False,
        defer_pool_rows=enable_key_pool,
        defer_check_content=enable_key_pool,
    )
    unblock_tabs_html, unblock_panels_html = web_form_blocks.render_unblock_lists(
        [
            {
                "name": "vless",
                "label": "Vless 1",
                "content": "telegram.org\nchatgpt.com\nchat.openai.com",
            },
            {
                "name": "vless2",
                "label": "Vless 2",
                "content": "youtube.com\ngooglevideo.com\nrutracker.org",
            },
        ],
        csrf_input_html,
        (),
        "all",
        lambda key: "All services" if key == "all" else str(key),
    )
    pool_summary = _pool_summary(cache) if enable_key_pool else {"active_text": "", "note": ""}
    quick_key = form_basics["quick_key"]
    return web_form_template.render_web_form(
        APP_BRANCH_DESCRIPTION="fixture",
        APP_BRANCH_LABEL="ci/fixture",
        APP_VERSION_LABEL="ui-smoke",
        TELEGRAM_SVG_B64=TELEGRAM_SVG_B64,
        YOUTUBE_SVG_B64=YOUTUBE_SVG_B64,
        _telegram_icon_html=_telegram_icon_html,
        csrf_token="fixture-token",
        command_block=form_basics["command_block"],
        command_buttons_html=web_form_blocks.render_router_command_buttons(csrf_input_html, dns_override_active=False),
        app_runtime_mode_description=mode_fixture["description"],
        app_runtime_mode_label=mode_fixture["label"],
        app_runtime_mode_picker_block=web_form_blocks.render_app_runtime_mode_picker(
            mode,
            [
                ("simple", "Simple", "Fixture web UI without key pool"),
                ("advanced", "Advanced", "Fixture full UI"),
                ("web_only", "Web only", "Fixture key-pool UI without Telegram bot"),
            ],
            csrf_input_html,
        ),
        current_mode_label=current_mode_label,
        custom_checks_json=json.dumps(
            key_pool_web.web_custom_checks(CUSTOM_CHECKS) if enable_custom_checks else [],
            ensure_ascii=False,
        ),
        event_history_html="",
        fallback_block=form_basics["fallback_block"],
        initial_command_running=form_basics["initial_command_running"],
        initial_status_pending="false",
        list_route_label="Vless 1 / Vless 2",
        message_block=form_basics["message_block"],
        mode_picker_block=web_form_blocks.render_button_mode_picker(status["proxy_mode"], csrf_input_html=csrf_input_html),
        mode_toggle_label="Mode:",
        pool_summary=pool_summary,
        pool_summary_note=pool_summary["note"],
        protocol_panels_html=protocol_panels_html,
        protocol_tabs_html=protocol_tabs_html,
        quick_key_label=quick_key["label"],
        quick_key_proto=quick_key["proto"],
        quick_key_value=quick_key["value"],
        quick_start_note=(
            "Fixture web controls are visible for UI smoke."
            if not enable_telegram else
            "Fixture bot controls are visible for UI smoke."
        ),
        router_health=_router_health(),
        socks_block=form_basics["socks_block"],
        start_button_label="Start bot",
        status=status,
        topbar_status_text=status["api_status"],
        unblock_panels_html=unblock_panels_html,
        unblock_tabs_html=unblock_tabs_html,
        enable_custom_checks=enable_custom_checks,
        enable_key_pool=enable_key_pool,
        enable_telegram=enable_telegram,
        bot_ready=enable_telegram,
    )


class FixtureHTTPServer(ThreadingHTTPServer):
    request_queue_size = 128
    daemon_threads = True


class FixtureHandler(BaseHTTPRequestHandler):
    server_version = "BypassKeeneticUiFixture/1.0"

    def log_message(self, _format, *_args):
        return

    def _send(self, body, content_type, status=200):
        if isinstance(body, str):
            payload = body.encode("utf-8")
        else:
            payload = body
        self.send_response(status)
        self.send_header("X-Bypass-UI-Fixture", "1")
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, payload, status=200):
        self._send(json.dumps(payload, ensure_ascii=False), "application/json; charset=utf-8", status=status)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path in ("/", "/index.html", "/command"):
            params = parse_qs(parsed.query or "", keep_blank_values=True)
            mode = (params.get("mode") or ["advanced"])[0]
            self._send(_page_html(mode), "text/html; charset=utf-8")
            return
        if path in ("/static/telegram.svg", "/static/youtube.svg"):
            asset_path = APP_ROOT / "static" / path.rsplit("/", 1)[-1]
            try:
                body = asset_path.read_bytes()
                content_type = "image/svg+xml" if body.lstrip().startswith(b"<svg") else "image/png"
                self._send(body, content_type)
            except OSError:
                self._send("not found", "text/plain; charset=utf-8", status=404)
            return
        if path == "/static/app.css":
            self._send((APP_ROOT / "static" / "app.css").read_text(encoding="utf-8"), "text/css; charset=utf-8")
            return
        if path == "/static/app.js":
            self._send((APP_ROOT / "static" / "app.js").read_text(encoding="utf-8"), "application/javascript; charset=utf-8")
            return
        if path == "/api/ui_background":
            self._json(dict(BACKGROUND_STATE))
            return
        if path == "/api/router_health":
            self._json(_router_health())
            return
        if path == "/api/status":
            params = parse_qs(parsed.query or "", keep_blank_values=True)
            lite = (params.get("lite") or [""])[0] == "1"
            self._json(
                {
                    "web": _status(),
                    "protocols": _live_protocol_statuses() if lite else _protocol_statuses(),
                    "router_health": _router_health(),
                    "bot_ready": True,
                    "pool_summary": _pool_summary(),
                    "pool_probe_running": False,
                    "pool_probe_progress": {},
                    "timestamp": time.time(),
                }
            )
            return
        if path == "/api/pools":
            params = parse_qs(parsed.query or "", keep_blank_values=True)
            requested = []
            for name in ("protocols", "protocol", "proto"):
                requested.extend(params.get(name, []))
            protocols = []
            for item in ",".join(requested).split(","):
                item = item.strip()
                if item:
                    protocols.append(item)
            self._json(
                {
                    "pools": _pool_snapshot(protocols or None),
                    "pool_summary": _pool_summary(),
                    "custom_checks": key_pool_web.web_custom_checks(CUSTOM_CHECKS),
                    "timestamp": time.time(),
                }
            )
            return
        if path == "/api/protocol_panel":
            params = parse_qs(parsed.query or "", keep_blank_values=True)
            protocol = (params.get("proto") or params.get("protocol") or [""])[0]
            try:
                self._json({"ok": True, "protocol": protocol, "html": _protocol_panel(protocol)})
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            return
        if path == "/api/protocol_check_panel":
            params = parse_qs(parsed.query or "", keep_blank_values=True)
            protocol = (params.get("proto") or params.get("protocol") or [""])[0]
            try:
                self._json({"ok": True, "protocol": protocol, "html": _protocol_check_panel(protocol)})
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, status=400)
            return
        if path == "/api/service_routes":
            self._json({"route_tools_html": _route_tools_html("")})
            return
        if path == "/api/router_metrics":
            now = time.time()
            self._json(
                {
                    "timestamp": now,
                    "load": {"load1": 0.12, "load5": 0.10, "load15": 0.08},
                    "processes": {
                        "bot": {
                            "name": "bot",
                            "pid": 123,
                            "running": True,
                            "rss_kb": 65536,
                            "cpu_percent": 1.25,
                        },
                        "xray": {
                            "name": "xray",
                            "pid": 456,
                            "running": True,
                            "rss_kb": 32768,
                            "cpu_percent": 0.5,
                        },
                    },
                    "summary": {
                        "samples": 2,
                        "bot_rss_min_kb": 64000,
                        "bot_rss_max_kb": 65536,
                        "xray_rss_min_kb": 32000,
                        "xray_rss_max_kb": 32768,
                        "load1_max": 0.12,
                    },
                    "history": [
                        {
                            "timestamp": now - 60,
                            "load1": 0.08,
                            "bot_rss_kb": 64000,
                            "bot_cpu_percent": 0.4,
                            "xray_rss_kb": 32000,
                            "xray_cpu_percent": 0.3,
                        },
                        {
                            "timestamp": now,
                            "load1": 0.12,
                            "bot_rss_kb": 65536,
                            "bot_cpu_percent": 1.25,
                            "xray_rss_kb": 32768,
                            "xray_cpu_percent": 0.5,
                        },
                    ],
                }
            )
            return
        if path == "/api/event_history":
            events = [
                {
                    "ts": int(time.time()) - index * 60,
                    "action": "stream_guard_defer" if index % 3 == 0 else "key_switch",
                    "protocol_label": "Vless 2" if index % 3 == 0 else "Vless 1",
                    "service": "youtube" if index % 3 == 0 else "telegram",
                    "message": f"fixture event {index}",
                    "level": "info",
                }
                for index in range(60)
            ]
            self._json({"events": events, "html": key_pool_web.web_event_history_html(events)})
            return
        if path == "/api/command_state":
            self._json({"running": False})
            return
        if path == "/api/pool_probe":
            self._json({"status": "idle", "running": False, "progress": {}})
            return
        self._send("not found", "text/plain; charset=utf-8", status=404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length") or "0")
        body = self.rfile.read(length).decode("utf-8", errors="replace") if length else ""
        params = parse_qs(body, keep_blank_values=True)
        if path == "/api/ui_background/upload":
            BACKGROUND_STATE.update({
                "ok": True,
                "available": True,
                "enabled": True,
                "url": BACKGROUND_FIXTURE_URL,
                "size": max(1, length),
                "width": 1,
                "height": 1,
            })
            self._json(dict(BACKGROUND_STATE))
            return
        if path == "/api/ui_background/settings":
            try:
                shade = max(0, min(80, int((params.get("shade") or [55])[0])))
            except (TypeError, ValueError):
                shade = 55
            BACKGROUND_STATE.update({"ok": True, "shade": shade, "enabled": bool(BACKGROUND_STATE["available"])})
            self._json(dict(BACKGROUND_STATE))
            return
        if path == "/api/ui_background/delete":
            BACKGROUND_STATE.update({
                "ok": True,
                "available": False,
                "enabled": False,
                "url": "",
                "size": 0,
                "width": 0,
                "height": 0,
            })
            self._json(dict(BACKGROUND_STATE))
            return
        protocol = (params.get("type") or params.get("protocol") or ["vless"])[0]
        if path == "/pool_apply":
            self._json(
                {
                    "ok": True,
                    "result": "Fixture key applied",
                    "key_id": (params.get("key_id") or [""])[0],
                    "pools": _pool_snapshot([protocol]),
                    "pool_summary": _pool_summary(),
                    "timestamp": time.time(),
                }
            )
            return
        self._json({"ok": True, "result": "Fixture action accepted", "timestamp": time.time()})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    args = parser.parse_args()
    httpd = FixtureHTTPServer((args.host, args.port), FixtureHandler)
    print(f"Serving UI fixture on http://{args.host}:{args.port}/", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
