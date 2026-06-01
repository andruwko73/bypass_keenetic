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
sys.path.insert(0, str(ROOT))

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


def _router_health():
    return {
        "memory_text": "available 256 MB, used 256 of 512 MB",
        "note": "Router fixture: CPU 0.10 / 0.08 / 0.05. Bot RSS 42 MB.",
        "dns_note": "DNS: ndnproxy. ipset updated: fixture.",
        "core_proxy_note": "Xray: alive, config OK, ports: 10811:ok, 10812:ok, 10813:ok, 10814:ok.",
        "used_percent": 50,
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
    )
    return panels


def _page_html():
    cache = _probe_cache()
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
    table_class, custom_width, mobile_width = web_pool_form_blocks.pool_table_layout(CUSTOM_CHECKS)
    protocol_tabs_html, protocol_panels_html = web_pool_form_blocks.render_protocol_tabs_and_panels(
        web_form_blocks.PROTOCOL_SECTIONS,
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
        active_protocol="vless",
        lazy_protocol_panels=True,
        pool_probe_pending=False,
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
    pool_summary = _pool_summary(cache)
    quick_key = form_basics["quick_key"]
    return web_form_template.render_web_form(
        APP_BRANCH_DESCRIPTION="fixture",
        APP_BRANCH_LABEL="ci/fixture",
        APP_VERSION_LABEL="ui-smoke",
        POOL_PROBE_UI_POLL_EXTENSION_MS=1000,
        TELEGRAM_SVG_B64=TELEGRAM_SVG_B64,
        YOUTUBE_SVG_B64=YOUTUBE_SVG_B64,
        _telegram_icon_html=_telegram_icon_html,
        csrf_token="fixture-token",
        command_block=form_basics["command_block"],
        command_buttons_html=web_form_blocks.render_router_command_buttons(csrf_input_html, dns_override_active=False),
        app_runtime_mode_description="fixture with key pool and Telegram bot",
        app_runtime_mode_label="Advanced",
        app_runtime_mode_picker_block=web_form_blocks.render_app_runtime_mode_picker(
            "advanced",
            [
                ("advanced", "Advanced", "Fixture full UI"),
                ("web", "Web only", "Fixture web UI"),
            ],
            csrf_input_html,
        ),
        current_mode_label=current_mode_label,
        custom_checks_json=json.dumps(key_pool_web.web_custom_checks(CUSTOM_CHECKS), ensure_ascii=False),
        event_history_html=key_pool_web.web_event_history_html(
            [
                {
                    "ts": int(time.time()),
                    "action": "key_switch",
                    "protocol_label": "Vless 1",
                    "service": "telegram",
                    "message": "fixture active key",
                    "level": "info",
                }
            ]
        ),
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
        quick_start_note="Fixture bot controls are visible for UI smoke.",
        router_health=_router_health(),
        socks_block=form_basics["socks_block"],
        start_button_label="Start bot",
        status=status,
        topbar_status_text=status["api_status"],
        unblock_panels_html=unblock_panels_html,
        unblock_tabs_html=unblock_tabs_html,
        enable_custom_checks=True,
        enable_key_pool=True,
        enable_telegram=True,
    )


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
            self._send(_page_html(), "text/html; charset=utf-8")
            return
        if path == "/static/app.css":
            self._send(
                web_form_template.render_web_style_asset(TELEGRAM_SVG_B64=TELEGRAM_SVG_B64),
                "text/css; charset=utf-8",
            )
            return
        if path == "/static/app.js":
            self._send(
                web_form_template.render_web_script_asset(
                    POOL_PROBE_UI_POLL_EXTENSION_MS=1000,
                    TELEGRAM_SVG_B64=TELEGRAM_SVG_B64,
                    YOUTUBE_SVG_B64=YOUTUBE_SVG_B64,
                    csrf_token="",
                    custom_checks_json="[]",
                    initial_command_running="false",
                    initial_status_pending="false",
                    enable_async_forms=True,
                    enable_custom_checks=True,
                    enable_key_pool=True,
                    enable_live_status=True,
                ),
                "application/javascript; charset=utf-8",
            )
            return
        if path == "/api/status":
            self._json(
                {
                    "web": _status(),
                    "protocols": _protocol_statuses(),
                    "router_health": _router_health(),
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
        if path == "/api/service_routes":
            self._json({"route_tools_html": _route_tools_html("")})
            return
        if path == "/api/command_state":
            self._json({"running": False})
            return
        if path == "/api/pool_probe":
            self._json({"status": "idle", "running": False, "progress": {}})
            return
        self._send("not found", "text/plain; charset=utf-8", status=404)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    args = parser.parse_args()
    httpd = ThreadingHTTPServer((args.host, args.port), FixtureHandler)
    print(f"Serving UI fixture on http://{args.host}:{args.port}/", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
