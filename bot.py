#!/usr/bin/python3

#  2023. Keenetic DNS bot /  Проект: bypass_keenetic / Автор: tas_unn
#  GitHub: https://github.com/tas-unn/bypass_keenetic
#  Данный бот предназначен для управления обхода блокировок на роутерах Keenetic
#  Демо-бот: https://t.me/keenetic_dns_bot
#
#  Файл: bot.py, Версия 2.2.1, последнее изменение: 19.04.2026, 15:10

import subprocess
import os
import ipaddress
import re
import stat
import sys
import time
import threading
import signal
import traceback
import gc
import concurrent.futures
import tarfile
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse

import telebot
from telebot import types
import base64
import shutil
# import datetime
import requests
import json
import html
import bot_config as config

# --- Пул ключей и авто-фейловер Telegram API ---
KEY_POOLS_PATH = '/opt/etc/bot/key_pools.json'
KEY_PROBE_CACHE_PATH = '/opt/etc/bot/key_probe_cache.json'
CUSTOM_CHECKS_PATH = '/opt/etc/bot/custom_checks.json'
AUTO_FAILOVER_GRACE_SECONDS = 60
AUTO_FAILOVER_POLL_SECONDS = 10
auto_failover_state = {
    'last_ok': 0.0,
    'last_fail': 0.0,
    'last_attempt': 0.0,
    'in_progress': False,
}
key_probe_cache_lock = threading.Lock()


def _hash_key(value):
    import hashlib
    return hashlib.sha1((value or '').encode('utf-8', errors='ignore')).hexdigest()


def _load_key_probe_cache():
    try:
        with open(KEY_PROBE_CACHE_PATH, 'r', encoding='utf-8') as f:
            value = json.load(f)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _save_key_probe_cache(cache):
    os.makedirs(os.path.dirname(KEY_PROBE_CACHE_PATH), exist_ok=True)
    with open(KEY_PROBE_CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


CUSTOM_CHECK_PRESETS = [
    {
        'id': 'chatgpt_services',
        'label': 'ChatGPT',
        'url': 'https://chatgpt.com',
        'urls': [
            'https://chatgpt.com',
            'https://chatgpt.com/codex',
            'https://api.openai.com',
        ],
        'badge': 'GPT',
        'icon': 'chatgpt',
    },
    {
        'id': 'claude',
        'label': 'Claude',
        'url': 'https://claude.ai',
        'urls': ['https://claude.ai', 'https://api.anthropic.com'],
        'badge': 'CL',
        'icon': 'claude',
    },
    {
        'id': 'gemini',
        'label': 'Gemini',
        'url': 'https://gemini.google.com',
        'urls': ['https://gemini.google.com', 'https://generativelanguage.googleapis.com'],
        'badge': 'GM',
        'icon': 'gemini',
    },
    {
        'id': 'copilot',
        'label': 'Copilot',
        'url': 'https://copilot.microsoft.com',
        'badge': 'CP',
        'icon': 'copilot',
    },
    {
        'id': 'perplexity',
        'label': 'Perplexity',
        'url': 'https://www.perplexity.ai',
        'badge': 'PX',
        'icon': 'perplexity',
    },
    {
        'id': 'grok',
        'label': 'Grok',
        'url': 'https://grok.com',
        'urls': ['https://grok.com', 'https://x.ai'],
        'badge': 'GX',
        'icon': 'grok',
    },
    {
        'id': 'deepseek',
        'label': 'DeepSeek',
        'url': 'https://chat.deepseek.com',
        'urls': ['https://chat.deepseek.com', 'https://api.deepseek.com'],
        'badge': 'DS',
        'icon': 'deepseek',
    },
    {
        'id': 'discord',
        'label': 'Discord',
        'url': 'https://discord.com',
        'urls': [
            'https://discord.com',
            'https://discordapp.com',
            'https://gateway.discord.gg',
            'https://cdn.discordapp.com',
        ],
        'badge': 'DC',
        'icon': 'discord',
    },
    {
        'id': 'meta_ai',
        'label': 'Meta AI',
        'url': 'https://www.meta.ai',
        'urls': ['https://www.meta.ai', 'https://ai.meta.com'],
        'badge': 'MA',
        'icon': 'meta',
    },
    {
        'id': 'instagram',
        'label': 'Instagram',
        'url': 'https://www.instagram.com',
        'badge': 'IG',
        'icon': 'instagram',
    },
    {
        'id': 'facebook',
        'label': 'Facebook',
        'url': 'https://www.facebook.com',
        'urls': ['https://www.facebook.com', 'https://graph.facebook.com'],
        'badge': 'FB',
        'icon': 'facebook',
    },
]
CUSTOM_CHECK_MAX = 12
CUSTOM_CHECK_REMOVED_IDS = {'mistral'}


def _normalize_check_url(value):
    url = (value or '').strip()
    if not url:
        raise ValueError('Укажите адрес для проверки')
    if not re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*://', url):
        url = 'https://' + url
    parsed = urlparse(url)
    if parsed.scheme not in ['http', 'https'] or not parsed.netloc:
        raise ValueError('Адрес должен быть HTTP/HTTPS URL или доменом')
    return url


def _custom_check_id(label, url):
    base = re.sub(r'[^a-z0-9]+', '_', (label or '').lower()).strip('_')[:24]
    return base or ('target_' + _hash_key(url)[:8])


def _sanitize_custom_check(item):
    if not isinstance(item, dict):
        return None
    try:
        raw_urls = item.get('urls')
        if isinstance(raw_urls, list):
            urls = []
            for value in raw_urls:
                normalized = _normalize_check_url(value)
                if normalized not in urls:
                    urls.append(normalized)
        else:
            urls = [_normalize_check_url(item.get('url', ''))]
    except ValueError:
        return None
    if not urls:
        return None
    url = urls[0]
    label = str(item.get('label') or urlparse(url).netloc or url).strip()[:40]
    check_id = str(item.get('id') or _custom_check_id(label, url)).strip()[:40]
    check_id = re.sub(r'[^a-zA-Z0-9_-]+', '_', check_id).strip('_') or _custom_check_id(label, url)
    badge = str(item.get('badge') or label[:3] or 'WEB').strip().upper()[:5]
    result = {
        'id': check_id,
        'label': label,
        'url': url,
        'badge': badge,
    }
    if len(urls) > 1:
        result['urls'] = urls[:4]
    if item.get('icon'):
        result['icon'] = str(item.get('icon'))[:24]
    return result


def _load_custom_checks():
    try:
        with open(CUSTOM_CHECKS_PATH, 'r', encoding='utf-8') as f:
            value = json.load(f)
    except Exception:
        return []
    source = value.get('checks', []) if isinstance(value, dict) else value
    if not isinstance(source, list):
        return []
    result = []
    seen = set()
    for item in source:
        check = _sanitize_custom_check(item)
        if not check:
            continue
        if check['id'] in CUSTOM_CHECK_REMOVED_IDS:
            continue
        unique_key = (check['id'], tuple(check.get('urls') or [check['url']]))
        if unique_key in seen:
            continue
        seen.add(unique_key)
        result.append(check)
        if len(result) >= CUSTOM_CHECK_MAX:
            break
    legacy_chatgpt_ids = {'chatgpt', 'codex', 'openai_api'}
    if any(item.get('id') in legacy_chatgpt_ids for item in result):
        result = [item for item in result if item.get('id') not in legacy_chatgpt_ids]
        if not any(item.get('id') == 'chatgpt_services' for item in result):
            preset = _sanitize_custom_check(CUSTOM_CHECK_PRESETS[0])
            if preset:
                result.insert(0, preset)
    return result


def _save_custom_checks(checks):
    result = []
    seen_ids = set()
    seen_urls = set()
    for item in checks or []:
        check = _sanitize_custom_check(item)
        if not check:
            continue
        if check['id'] in CUSTOM_CHECK_REMOVED_IDS:
            continue
        urls_key = tuple(check.get('urls') or [check['url']])
        if check['id'] in seen_ids or urls_key in seen_urls:
            continue
        seen_ids.add(check['id'])
        seen_urls.add(urls_key)
        result.append(check)
        if len(result) >= CUSTOM_CHECK_MAX:
            break
    os.makedirs(os.path.dirname(CUSTOM_CHECKS_PATH), exist_ok=True)
    with open(CUSTOM_CHECKS_PATH, 'w', encoding='utf-8') as f:
        json.dump({'checks': result}, f, ensure_ascii=False, indent=2)
    return result


def _custom_check_presets():
    return [dict(item) for item in CUSTOM_CHECK_PRESETS]


def _add_custom_check(label='', url='', preset_id=''):
    checks = _load_custom_checks()
    if len(checks) >= CUSTOM_CHECK_MAX:
        raise ValueError(f'Можно хранить не больше {CUSTOM_CHECK_MAX} дополнительных проверок')
    item = None
    if preset_id:
        for preset in CUSTOM_CHECK_PRESETS:
            if preset['id'] == preset_id:
                item = dict(preset)
                break
        if not item:
            raise ValueError('Неизвестный пресет проверки')
    else:
        item = {
            'label': (label or '').strip(),
            'url': (url or '').strip(),
        }
    check = _sanitize_custom_check(item)
    if not check:
        raise ValueError('Не удалось добавить проверку: проверьте название и URL')
    for existing in checks:
        if existing['id'] == check['id'] or tuple(existing.get('urls') or [existing['url']]) == tuple(check.get('urls') or [check['url']]):
            return checks, f'Проверка "{check["label"]}" уже есть в списке.'
    checks.append(check)
    checks = _save_custom_checks(checks)
    _invalidate_web_status_cache()
    _invalidate_key_status_cache()
    return checks, f'Проверка "{check["label"]}" добавлена.'


def _delete_custom_check(check_id):
    check_id = (check_id or '').strip()
    checks = _load_custom_checks()
    next_checks = [item for item in checks if item.get('id') != check_id]
    if len(next_checks) == len(checks):
        raise ValueError('Проверка не найдена')
    checks = _save_custom_checks(next_checks)
    _invalidate_web_status_cache()
    _invalidate_key_status_cache()
    return checks


def _record_key_probe(proto, key_value, tg_ok=None, yt_ok=None, custom=None):
    with key_probe_cache_lock:
        cache = _load_key_probe_cache()
        key_id = _hash_key(key_value)
        entry = cache.get(key_id, {})
        if not isinstance(entry, dict):
            entry = {}
        entry['proto'] = proto
        entry['ts'] = time.time()
        if tg_ok is not None:
            entry['tg_ok'] = bool(tg_ok)
        if yt_ok is not None:
            entry['yt_ok'] = bool(yt_ok)
        if custom is not None:
            existing_custom = entry.get('custom', {})
            if not isinstance(existing_custom, dict):
                existing_custom = {}
            for check_id, ok in (custom or {}).items():
                existing_custom[str(check_id)] = bool(ok)
            entry['custom'] = existing_custom
        cache[key_id] = entry
        _save_key_probe_cache(cache)


def _key_probe_is_fresh(entry, now=None, custom_checks=None):
    if not entry:
        return False
    try:
        ts = float(entry.get('ts', 0))
    except (TypeError, ValueError):
        return False
    if (now or time.time()) - ts >= KEY_PROBE_CACHE_TTL:
        return False
    custom_checks = custom_checks or []
    if custom_checks:
        custom = entry.get('custom', {})
        if not isinstance(custom, dict):
            return False
        return all(check.get('id') in custom for check in custom_checks)
    return True


def _key_probe_has_required_results(entry, custom_checks=None):
    if not isinstance(entry, dict):
        return False
    if 'tg_ok' not in entry or 'yt_ok' not in entry:
        return False
    custom_checks = custom_checks or []
    if custom_checks:
        custom = entry.get('custom', {})
        if not isinstance(custom, dict):
            return False
        return all(check.get('id') in custom for check in custom_checks)
    return True


TELEGRAM_SVG_B64 = 'PHN2ZyB3aWR0aD0iMTYiIGhlaWdodD0iMTYiIHZpZXdCb3g9IjAgMCA1MTIgNTEyIiBmaWxsPSJub25lIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPjxjaXJjbGUgY3g9IjI1NiIgY3k9IjI1NiIgcj0iMjU2IiBmaWxsPSIjMzdBRUUyIi8+PHBhdGggZD0iTTExOSAyNjVsMjY1LTEwNGMxMi01IDIzIDMgMTkgMTlsLTQ1IDIxMmMtMyAxMy0xMiAxNi0yNCAxMGwtNjYtNDktMzIgMzFjLTQgNC03IDctMTUgN2w2LTg1IDE1NS0xNDBjNy02LTItMTAtMTEtNGwtMTkyIDEyMS04My0yNmMtMTgtNi0xOC0xOCA0LTI2eiIgZmlsbD0iI2ZmZiIvPjwvc3ZnPg=='
YOUTUBE_SVG_B64 = 'PHN2ZyB3aWR0aD0iMTYiIGhlaWdodD0iMTYiIHZpZXdCb3g9IjAgMCA0NDMgMzIwIiBmaWxsPSJub25lIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPjxyZWN0IHdpZHRoPSI0NDMiIGhlaWdodD0iMzIwIiByeD0iNzAiIGZpbGw9IiNGRjAwMDAiLz48cG9seWdvbiBwb2ludHM9IjE3Nyw5NiAzNTUsMTYwIDE3NywyMjQiIGZpbGw9IiNmZmYiLz48L3N2Zz4='
CHATGPT_ICON_B64 = 'iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAYAAACqaXHeAAAM6ElEQVR42u1bbUxT5xc/994WqKAwMVBw8iJVZhCWMRcduA3ZgmCCss0QY7IFURGybG7fZOPTXlhiSFgijJW3qCMY14gbEhMlY+KUDBajIqAw0LlJGBMGG2VQ6L2/fXqe9NIWWqi4/388yU0ot/c+5/ye835OBQCg//AS6T++lgBYAmAJgP/20izWRoqiEACydTqCIJAgCCSK4v8nAABIURQSRXFWJm2/JwjCogIgPKo4gDHE1v3796mjo4Pu379PZrOZdDodhYWFUUxMDBkMBv49WZZJkqTFQwCPYFmtVgCALMuoqalBcnIyli1bBiKyu7y9vZGQkIDy8nJMTk6qnl+M5XEApqenAQBtbW3YsmWLQ6adXbGxsWhqagIATE1NwWq1QlEUyLIMq9WK6elp/j9PLY+qgNVqJY1GQ7W1tZSdnU0Wi4UkSSJZlkkURdq4cSNFR0fTihUryGw2008//UTt7e1ktVpJEAQCQIIgUGlpKeXl5c26l6dUxWMAMIJMJhNlZmaqGM/NzaWcnBx6+umn7Z7r6uqiiooKqqyspImJCZJlmYiI9u7dS3/99RcNDw+TJEmk1+spLi6OkpOTKSEhgQPGvMljtQGyLENRFHR1dUGn00Gj0YCIsGbNGly+fNnOPjBRttX1CxcuwMfHB5IkQZKkWVUlPj4eJ0+eVO3/WG3A9PQ0FEVBUlISiAiSJCEkJAS9vb1cn22JZDrNni0pKYHBYIBGo+HguXKlpaWhv79/QYaTFmrtp6amAABNTU2ceUEQ8O2333Lm2VIUhRtJALh48SI2b95sx1hERARyc3NRVVWFhoYGnD17FkVFRdi5cyd0Oh2ICF5eXiAiREZGoru7e96SQPMVedvV29uLlJQUiKIIIkJmZqbKI8w8oTt37mDPnj2cYSbyoaGhKCkpwdjYmNO9e3p6kJWVZQfCw4cPIcuy2yDQfH08ANTW1mLbtm3w9vYGEXEAmpuboSgK/y5zW6OjoygoKICvry+IiIu7l5cX3n33XQwODvJ3T01NwWKxcFvB7AZblZWVEASB771r1655qQLNh/lbt27hxRdfVIktO0W9Xo/x8XEV4wBw4sQJrF27VgUUESE9PR3Xr19XMT5TcmbaD6ZWRqNRJQnnzp1zGwRyl/nz589j+fLlqhO0BeD555/nhMqyDLPZjB07dtjpeVxcHM6ePasypLb24t69e+js7LQztLZAAcBrr70GIoIgCEhISHDbFpA7zF+6dAlarRaCIEAQBBAR3nnnHRw9epR/fuWVV1QEtrS0qMBatWoVioqKeNjLTpQxNzIygoKCAvj7+0MURWRlZeHu3bt2tLCIsLOzk79bFEV0dHS4BQK5YvBkWcbg4CD0ej0EQYAoili5ciUXuYaGBn6yMwG4cuUKRFGEl5cXcnJy8ODBA9Up2orr8ePHYTAY7KQqICAAn3zyCcxms4omxmRiYiJ/5tixY3YGeEEAMAKzs7NBRNBqtfDz80NbWxu/bzKZnALAJCAiIsKpnjc3N/MYgogQHR2Nbdu28c9Mup566imcPn2aPzcxMQFZlpGfn8+/e+jQIc8BwBDu7u6GRqPhJ1JdXQ0A3NidOXNmVglgAPz9998qPb979y53aUQEnU6H/Px8jIyMcC+zfv16FQhEhO3bt/MDAICSkhJ+LyMjwy1DSK5kdh988AEn4rnnnuP32H1XAAgPD8fExAQAwGw2o7CwEIGBgVzUMzIy8Ouvv9qBPzY2hg8//BD+/v4qWyJJEnJyczE8PIyamhq+v7vucFYAmGHatGkT36CiomJeAERFRQEATCYTYmJi7LzC5s2b8c033ziMMgGgr68Pb775pp19CAsLQ2JiInet+/fv94wKMOaHhoYQEBDA0bcNO10B4PvvvwcRITg4GCkpKfx7q1evhtFoxBdffAG9Xq+K71tbW1VSaMvMpUuXsHXrVjsAmWQUFxd7BgAmgrdv3+boBgcH8zDVNq6fDYDLly+rCPXy8sLhw4cxMDDA9xoYGMDhw4d5VCdJEvLy8mb1GFVVVQgPD+eGmdFoa5w9AkB7ezsnPiwsjPtvdwHQarVIT0/HtWvXnJ7utWvXkJ6erooqi4uLYbFYHMYMf/zxB3Jzc/n7iQg7d+5UheELBqCvr4+/PCAgAENDQ3YA1NXVcQBefvlllf4yG7BmzRqnUd3MLDEsLEwVZcbHx6O+vt4pcJ9++qkqJP78889dloI5bcD4+DhCQkI4MT/88ANHmBFhMpl4GpyWlsZ9tKIoYunUrFzfbRsYbb7zB+wGOQtj6+nqHpfCYmBhu2NatW2dnA2YDgNFXWVnJ72/atGlO5gHApckE1noaGhrire/c3Fy6fv065eXl8fsajYa+/PJLio+Pp48++ojMZjNptVpV6+qZZ56hkJAQ3tcLDAykwsJCam1tpd27d5PFYiGr1TqvLpfRaOR/p6Sk8Jbdgltj7AQzMjI4wqWlpfz+jz/+iNTUVH6PJSbr169HbW0tr/Xl5+fzxgZzp7b1vqmpKUxMTHB/74oEMFdXXV3NpXFm1rrgoigTsUOHDnEC3n//fciyzH00AHz11VfYsGGDXQUnKSkJ0dHRqs/Nzc1OK8IsFJ4NAJPJpDLOfn5+3DBnZ2cvPBdwBIBt6emFF15wWKAcHx9HYWEh98e2PQCDwYDjx4879RgPHjxATk4OvLy8IIrirF6goaEBAHDu3DmsXLkSoihCEATo9XoMDg663CVyCQD2oo6ODs6QVqtFV1eXKvW0RfzevXvYt28fJEmCv78/CgoKeK1vZswwOTmJoqIirFq1SuVlnEmAIAg4evQo3n77bZW0abVaLlkeKYk5AiEhIYFv+Prrr8/ZAO3s7MTPP//stCL89ddfIy4uzs4r7NixA2azWXWSbOLE1uswsFasWIHz588/+s4Q6wGwoMVoNM7ZAnek5zdu3EB6erqd4Vy7di1OnDhhlySZzWYEBwfbAUBEeOmll3hDZFF6gywk9vb2hiAIdpGg7QCExWJRMf7777/jvffe4wCyE/T19UVBQQFGR0dVjLNE57vvvlMx7+Pjg+TkZJw6dcph4/aRAMDE8eHDh9xVMUaysrLQ09Pj9Fmz2YzS0lJe4LA9xT179uDOnTsOGWHqsnv3bi4pKSkpPNFZ6JSI2+1x22YJc1cMBJ1Oh/T0dBQVFaGurg4NDQ2oqqpCXl4eIiIiHJbCL168OGcDtLGxkafBRGQ3SbboY3Js0/7+fqSlpbk80sJGYAwGA44dO8ZPd7YWeE9PD/R6PVeVpKQkO0P7WOYEbQk+efIk4uPjZ2WeDT/5+PjgwoULKjAdDUCwctqTTz7JwfPx8eGudyGDUR6bE7QdUwNALS0t1NTURO3t7fTbb7+RLMsUGBhIy5cvp1OnThw4dJk2bNhg997YsWOk1WqpvLyMFEUhIWEh1+hWWlpKtbW1vGUX4dZYOwEMBgO2b9+OFStW8LEFgJUrV2L48OG8YR7S0tLQ2NiocqHRaFCpVArp6enp6cn90RQnOTmZtLQ0uLi4UGVlJS1fvpxMJhMNDQ1Vnqjo7OxEa2srjxuh0WhUfX29hqZ1c3PDqFGj2DHZbLZ7M4rIV7gWmEl9fT3v42g0qmA/TgC8//77jP0mJiY4fPiw3VglJycjPj4eExMTnA6GmD2bZrNZhISEsH37djo7O1Vmrp8/fx4jIyP4/vvvqms6nQ7btm1jZWWFiYkJb29vYWFhgf9kZmaGdevW8X0MAM3NzRERkYHi4mKXFs7W1haKi4vZor8PKoqCqqoqrFy5kjfU2NgYqamp6O/vZ2RkZGdl3Nzc2LBhA6+//rrKALgF4JNPPhEAwNSpU2nfvn3cH/jly5fRqFGjccx2dnYqzt3Z2SkaGhrY8ePHu0y4Lh0OB7VaDQA4deoUAKBbty5jY2P49ttvXcuXL9eZJ0mSxNPTE76+vmb9fH5+Pqqrq9HZ2SnD6iQkJDQoKChI7ziBQEDxQ+lwOPB4PHz77bd8t3v37lF7ezs8PDzAQSGCDz/8kM0/smXL9Lvvvkt5eTldu3aVyWRSHx8fJCQk0NDQUCyk/5+fH5aWlqigoEBTUxNPT0+lp6drd2nt7e2lqqpKvb29fLAcRUVFLC0tCQAHDx4kIyODnTt34uLiYpVKZQACAwMJi8WiqqpKptNpCwoKLF68mDIzM2lxcTEikUiJiYnYvn07H3/8Mf39/Rw4cKBq+9WrV5ePHz8u3njjDUKhEE1NTYqKimKfwdnZGcHBwWzv9fX1VFRU0LlzZ/r6+qitrc3//ve/8+bNmwwYMIAvvvgCAGBmZobZbKbr169za+bOnUtLSwu7du0iIiLiyX09PT15/vnn2bt3L1tbW6xWK3t7e/jll19Yv349Ozs7zJ49m7KyMjp37oxQKMSaNWvYsGFD5v6FhYWQZRmWlpaoqKgAQGpqKqqrq7m8hISEcOHCBSIjI6m6upp2dnY6eN3+/fsJBAI0Nzfj9OnT5ObmUltbS8eOHWNubo4ff/wRLS0t3L59m4eHB8bHx4uPj6eioqJMXwEAL1684OHhQXFxMbe8Vq1axWKxYOPGjVx3wYIFNDU1MTg4mEtLS/Tr14+FhQUGBgZ49OhR7ty5Q19fH3q9Ho1Gg7KyMhYvXsx8tVgs6enpDBw4kLKyMrZv3862bdv4+OOPM2PGDPz9/QkJCWHEiBHs7u6yZMkS8fHxXLlyhVgslnvvvZfExER+/fXXLF68mL29PdauXUsqlUq6du2q3KCi2dnZ5OTk8PHxISIigqWlJX19fTw8PMjLy2Pjxo2k02l9fX3k5+fT2tqKIAiys7PZ29tjz549jI6OMmnSJC5fvsyDBw+YMGECpVIJAGBsbIzZbMbMmTN5+eWXiYqKouLiYg4dOsTHxwe1Wo2SkhKePXsGvV5Pp9Ohra2NpqYmVlZW4uHhQUxMDCUlJXR0dHBzc2PlypUYDAaWL19OeXk5dXV1vP7660xMTODj4yM/P5+UlBQmJydz7Ngx9vb2GBkZ4dChQ8zMzODs7MzV1ZWbNm0iLy+Ps7MzGxsbDBs2jGPHjvHqq69iZGSEt7c3GzZsYOvWrVi4cCE1NTU8PT0xMjLC8uXLiYyMRH19PSMjI1y8eJEbN27g6OiIY8eOcffuXWbPnk1ubm7YunUrJ06c4Pnnn+fMmTMkJSXh7u6OIAhwcXHh8ccfJy4ujjVr1jBlyhSmT5/O4MGD2bt3L4uLi2zatIlFixZx9+5d4uLiSEhI4O7u7u7evYuHh4eQZfn8+fN8/Pxobm5m7ty5s2bNGrZu3cr58+fJz88nLi6OxWLB3d0dKpUKGxsb8vLy6NixI0VRCA8PZ8WKFfz8/AgEArRaLQBgZ2eHr6+vxMTEyMjI4O7ujqCgIKqqqmjRogWBgYHExMTw8PAgKSmJkZERampq+OabbxgYGODcuXOsXr2a9evXM2fOHG7cuIFOp8PKygp3797l7t27mT17NsHBwQCAh4cH0dHRfPjhh1i9ejWFQoGqqio2bNgAAJg2bRpzc3Ns2LCBuLg4rl27xvTp03n77bd54IEHCAgI4Pnnn+fTTz/F3d0dZ2dn/PHHH8THx/Pmm2+iUChw5swZ9u/fz8TERKysrPD398e5c+cYPnw4Hx8fXFxcsHbtWu7du8fChQsJBAK4u7tj3rx5TJw4kZ6eHqmpqYSHh7N48WJmZmbYtm0bPj4+6Ojo4O3tjdFoJGJiYuzbt4+Liwtzc3P4+flx7tw5Hj58yO3bt3n77bfZt28fJ06c4Ofnh6urK5MmTeLr64uBgQF2dnY4Ozvj+PHjGB8fJyYmBna7HX/88QfHjx+PzWajq6uLkZGRuLi4UFtbS11dHVu2bMHX1xfj4+PcvXuX1atXU1hYyOLFi3n88cfJy8sjJydHbW0tHR0dBAIBjhw5QkBAADs7O8zMzBgZGfHFF18wZMgQDAwM+P7778nJySEpKYnJkyczY8YM9u7dy8DAAH5+fnz66acMDw9n4sSJeHh4EAgEuLi4YGRkhLCyMkZER5ubm+O677xgYGGBkZMTt27eJiYlhxowZHDlyhMTERKysrODm5sbVq1dxcnLCy8sLQ0NDvPPOO1RWVjJ79mzS0tJwc3PD8PBw7t27x6tXr9i3bx8A4OjoSEpKCh8fH5qamvD09MT8/Pw4d+4cZ86cwYULF7C1tUVpaSmFhYVUV1czcuRI8vPz2b59O0qlEjMzM4yNjfHSSy8xY8YMRkZGOHz4MH5+fnz99df8/f0xMTEhLS2NyWQiKysLz549Y2RkxNzcHAAQFxeHq6srXbt2MTg4mP79+zM3N8fHx4eCggL29vZ4enpiZGSERCLB7t27ePjhh2zatIk1a9YwMDCQe/fu4erqyu7du7l48SKurq5MmjSJZcuWcfHiRe7cuUOPHj2Ii4ujqqqK2Ww2GxsbLFq0iC+++IIvv/ySwsJCrl27RkJCAsHBwURGRlJYWBg7Ozu8vb2Jj4/n5s2bHDp0iLq6Oubm5vD19cXu3bs5e/YsCwsLDAwM8PHxwdDQEFVVVTzzzDPMmzeP3bt3s3HjRs6dO8f9+/fx9fXFwsICpVKJIAg0NzdHQUFBREZG8sYbb3D37l2mTJlCbm4uFhYWmDhxIkqlEm9vb2ZmZri4uFhYWFBfX88TTzzB3LlzvP322ywuLhISEoKJiQmRkZHEx8ezb98+Jk+ezODBg7m4uODg4IBSqcTq1avZsGEDJ0+eZG1tDV9fX+7du8fR0RHJyck4f/48Y8aM4e3tze7du3n11VdZsmQJv/76K0qlEo1Gg+PHjzNw4EBKS0uZNm0aAwMD/Pbbb+zZs4eJiQm+vr4AgLq6Oubm5pibm5Obm8vZs2eZMGECg8GA0WgkNzcXQ0NDs7Ozo6enR6/Xk5+fj6+uLyMhI3n33XQIDA1mwYAFXV1d8fHyoqKjA09MTc3Nz6uvr+eWXX7Bz5062bt3K0tISra2teHh4kEqlEBERgZ2dHb29vUyfPp2TkxO+vr7Y2tpiZGSERCLB6tWr+Pn5MTAwwNLSksLCQhYWFpibm+Pj44OZmRmRkZEMDw8nKSkJBwcHXF1dsaioiPj4eM6cOYNOp+P+/fvExMQQHR2Nq6srtra2ePXqFbdu3eL8+fOYmZlx7NgxSkpKGBgYoKioiGQy6eDgYKqqqti2bRuvv/66+Pn5sWfPHg4ODgiFQhw5coS5ubnExMQwOTnJyspK1tbW2LJlCwcOHMDW1hZLS0tKS0txcXHB0tISBQUFjI6O8v333/P9999jaGiIu7s7b731Fp6enrRarZiYmBAIBDA0NMSqVavIzs4mNjYWf39/qqqqeP3117m6uiI/P5+TkxP29vbk5OTw8vLC8PBwPDw8uLu7Y2dnx7Fjx1i1ahVLS0ts3LiR1atXk5CQwN69e3nrrbf4+OOP8fHx4ePjA4VCgYGBAY6OjkRHR7NkyRLOzs5cv36dK1eucPbsWZxOJwCAiYkJHR0dJCYm8vTpU9LT09mzZw9HR0d0dHRgYGCARCLB1dUVAPD19cXW1hbT09OYmJjw8vLC8PBwHn/8cQ4ePMjNmzfz8ccfAwDKysqYmZmhqqqK6upqbt26xfbt2ykoKODq6oqTkxPp6enExcUxbdq0sWzZMsrLy2nTpg0A4OTkRKPR0NfXx8bGhrKyMrZt28b58+fZsGEDR0dHhISE8N5773Hjxg3WrFlDU1MTqampnD17lrW1Nfbs2cPGxga9Xk9BQUGYTCacnJzQ6/W8+OKL3Lp1C6PRiJmZGQDw8PBgYmKCoqIiNjY2uLi4sLS0JBAI8P333/PVV1/x8ccfEwqFCAQCnJ2dcXd3x8TEhJ07d7JixQq2bt1KcXExZ86c4f333+fQoUNs3LiRXbt2sWHDhmzatInJkyfz8ccfAwA0NTVhYGCAm5sb2dnZ9OzZk7GxMQBgZWVFT08P8+bN4+TJk4yNjdHf38/8+fPp6emp5ORkDh48yMDAQF5eXnR0dMjlcmzatIn79+9z8OBBgYGBeHh4kEwmnJyc0NTUxMbGBm9vb+7evcvevXsxNjaGQqHA7t27+fDDD8nLy2NsbIyVlRXWr1/P2NhY1tbWmJub4+HhgYqKCo6Ojpw/fx5DQ0PMzc1xcnLC6tWr8fPz4+LFi9i9ezdHR0fMmzeP/Px8cnNzWVlZ4eLiIhgM8v7773P79m0mT56Mnp4ejx49wuVyMTY2xubmJgCgo6ODnZ0d9+7dY2xszJ07d3LlyhUKhQKbm5vEx8dza2vL1atX8fLyIi0tjZGREbdu3eLw4cM0Gg2Ki4u5cOECGxsbXLlyhY6ODkZGRjgcDs6ePUt3dze9Xk9PTw9XV1eYm5vDwcGB4uJiVqxYQWNjI9PT0wCA5ORkdu3aRbVaDR8fH+7evcuVK1fYvHkzOTk5nJ2dUVhYyMmTJ7l69SoAgIuLC+7u7qampvL19cXf35+SkhJ++eUXvv32W3p6etjZ2WHu3LksW7aM3Nxc3n77bQwODvL0008DADZv3szf35+YmBjOnz/PvXv3WLBgAf39/Tw8PGhpaSEpKYlNmzZx8uRJdu7cybVr1+ju7sYwDgBsbGzQ6/Xs27ePzz//nGXLlhEZGUlNTQ0A4OjoSExMDI1Gg5ubG3v27OHQoUNs2rSJXbt2sXHjRnp6emzatInVq1dz9OhRdu7cSUtLC8nJyQCAyMhI3n33Xfbs2cPR0RE0Gg2XLl3C1dUVPz8/GxsbBwcHnD17FhMTE6xcuZKJiQm2bt3K1tYWZ2dn9u3bR1lZGQDQ0dHBxsYGf39/Jk+ezJ07d9i8eTN9fX0sWbKEIAgEBATw8vLCy8sLXV1dxMTEkJmZyZ07d7JixQpmZmYAgNraWjY2Nri4uEhMTCQzM5OLi4sHDx7k7Nmz/P7774yMjODu7s7+/ftZsGABp06dIi0tjY2NDcHBwfj7+zN79mwA4O3tjaOjI3V1dYyMjPD19cXf35+RkRHm5uY4e/YsZ86cQalU4u7uTnJyMhMnTqSsrIyUlBQsLS2xsbGBgYEBU1NT6enp0d/fT0ZGBt7e3qSkpBAIBHh4eODq6oq3tzddXV2cO3eO5ORk3N3d8fDwwNfXF0mSxNfXF+vWrWNgYICJiQm2bNnC2dkZGxsbPD09+fjjj+nQoQOPP/44a9asYc2aNZSWllJZWcnZs2f59ddf2bVrF/Pnz6evr4+Liwujo6Nks9n49NNP+fTTT7l27RqZmZkMDAzw8vLCxMSE5cuX4+npibm5OWazGQUFBTQ1NVFVVUVHRwf29vYYGxvj6+uLq6sr0Wi0QqFAWVkZx48fZ2NjA0VRuH79OhMnTqSjo4OBgQFKpRJLS0s0Gg0A4OjoSGZmJrdu3eLx48ccPHgQDw8PjEaj6dOnM2nSJEKhEJmZmZQKBYmJiWzatIn+/ftz9uxZ5ubm+Pn5kZ6ezr1797C3t8fe3h5fX1/Onz/P/Pnz+fn5sW3bNs6fP8/GxkYAgL29PQoKChgZGWFlZYXJyckkJCSYmpqCw+Hg6OgIhUIBwMTEhMTERNauXUu5ubm0tLSYmZlhYmKCp6cnSkpK+P7776mvr2fRokXU1dWxs7PD29sbS0tL2b59O6dOnSIvL48xY8ZQWlpKXl4eDw8Pq6urHD58mLq6Oq6urmzatInS0lJycnLQ6/X8+OOPfPDBB5w5c4YBAwZgY2ODubk5/v7+vP7669TU1NDd3Y2TkxMTEhJwcnKCwWCAo6MjpaWl7Nixg4mJCTQ0NBQUFHD+/HmWLl3K3Llz8fPzQ0tLCx8fH3x8fHB1dUVfXx9eXl6UlpZy9+5d3n77bbZs2YIoisjIyDA8PMzU1BTLly/H3d0dR0dHrK2t8fX1xcrKCu3bt2P27NnMzc3x9/fH4/HQ6/Xs3buXlStXcv78eRYvXszWrVuJi4ujsbGRqKgoUlJSWFpaYvbs2Vy5coWJiQm2bNnC7t27+Pr6Ym5ujtFoREREBNnZ2fj4+GBlZYWQkBCAwMBAWlpaeHh4YGRkhLCwMH5+fvz8/OTk5JCQkICUlBT29vbo6emhUChw7NgxS0tLTJ8+nY6OjqSkpPD29sbd3Z2RkRE6nQ7T09NYW1tjZWWFhYUFJ0+eZPr06SwtLWFra4uNjQ0ODg7s3buXAwcO4Ofnh6mpKYaGhvD09OTm5oa9vT0A4Pz8nKqqKrZs2cLe3h4A4O3tjZGRERqNBh8fH9zc3Hh7e+Pn54eHhwfT09M4fPgw6enp/PDDDwwPDzM2NsbZ2Zndu3dTUVGBv78/w8PD2Nra4u/vz8LCAsHBwdzcnLQ6/X89NNP7Nu3j6mpKfbs2cPOzg5fX19KpRJtbW2MGjWKQqFAqVQiEAjw8PDA2NgYXV1d3N3dkZ+fz7lz5xgZGWH79u0MDw8nKSmJjo4O7t27R0ZGBh8fH4yMjHD//n2OHz+Ovb09Tk5O2L17N6dOncLLy4uRkRFGoxHnzp3D4/Hg7e2Nnp4e3bt3M2LECFJSUujq6uLx48cMDw9zcnLC29sbp9PJ2NiY2NhYdXV1fP311+zcuZM///wTX19fVldXc+bMGfr6+tzc3ODi4sLQ0BBPT0+4uLiQlZWFsbExtra2GBsbY2JiQm1tLYGBgZSWllJTU8P+/fuxsrLC1dUV8/PzWFhYwMTEhKmpKWazGb1ej8HBQZRKJd26dWNUqVS4uLhw7tw5Dhw4QFZWFiMjI/j7+2Nvb4+qqioA4O7uTnJyMtbW1tja2mJmZoZOp2NiYoKBgQF0Oh2RkZF8fHywtrbG7OwsX19f4uLiTE9PY2FhQWNjI+7u7igUCqKjo3n99dcZGRmhUCjQ0dGBgYEBjY2N2L17N3/99RfHx8cAgLe3N8bGxtja2mJmZoYkSSIpKQkAICcnB1tbW6xWK+vWrWNpaYmTkxMDAwNcXFwQCAQ0NjZiZ2eHvb09V69e5ejRo3h6ekJPTw9HR0e0tLQgEonQ6/Xw9fXFxsYGBwcHR0dHkEqlSE9PZ2VlhdFoRK/Xo6OjQ0NDQ2xsbPD29oZKpYKPjw9vb2/k5ubS0tLC3t4eAwMD/P39w8PDg6qqKmbOnMnQ0BAHBwe0tLTQ0NCAzWbj6+uLIAjExMQQFxcHAHh7e2NsbIzh4WHCwsIYGRlBQ0MDV1dX2Lx5M1FRUQCAo6Mj2traGB8fR6/Xs2PHDoqKigCA+Ph4wsLCeHh4oKSkhOzs7Kirq8PU1BRLS0uUl5eTkJDA4cOH+Pn5sW/fPmZmZpw5c4aSkhLOnz/PsWPHCAQC5ubmWltbKSoq4uDgQFVVFQ4ODrS0tODn54eHhwd7e3s0Gg2FhYXk5uZSWVlJZWUlZ2dnTpw4QWNjI6WlpWRmZkJRFHR0dGBlZYWZmRkAwNvbG5ubm9TU1DA3N8fExAQnT55k/fr1FBYWMjIywuDgIAAgEAi4uLjw8PDAyspKcnJyBAIBPT09FBUVMTU1hYODA0qlEjU1NZRKJbdu3eLw4cNpaWlhY2ODp6cnU1NT7Nixg+TkZPbt28fQ0BCFQoHbt28zNjbG3d0dR0dHfH19ycnJYWFhgcFgQK/Xc+LECfr6+li9ejUzMzN8fX0xm83s3buXrKwsGxsb5OTk0Gg0mJubY2Fhgbm5OVtbW2xsbIhEIlRVVWFmZsazZ8+YmZlhdHQ0Q0NDmJmZ4eDgQK1Wo6SkhJ07d2Y4HA7GxsbQ6/VYWFhgYGCAlZUV9vb2iIiIoKysjK2tLQDA1NQU9/f3mJubY2RkhJGREWZmZqjVahw/fpypqamUl5fj4uJCY2MjvV6PsbExIpEILy8vQ0NDAABtbW0sW7aMXbt2kZSUxNHRERaLBZVKJQAwNzcHABQKBRKJRPr6+mhpaWHWrFl8fX0xMDCgqqqKsbExBgYGeHp6YmpqCkVRCAwMZP78+Xz99deMjIxQKpXY2Njg7u6Oo6MjQ0NDLC0t4enpib29PZubm0ajEQAQFhZGZmam2NhY9u7di5OTE1FRUfT19eHq6oq7u7tMJpMXL17w9fXF2toaPz8/DAwM8PDwwMbGBh8fH8zMzODk5MS8efPYt28fZ86cwWAwYGBgAFtbWwCAv78/oaGh/Pz8WLt2LQ8PD3x8fLC0tMTExAQHBwe0Wi2lpaW0trbS0tKCw+FgMBiQSCQ0NTVhY2ODkZER3bt3x8rKCoVCYdmyZUhKSuLw4cP89NNP2LZtG2azGfX19fj7+yM/P5+TkxMeHh5ER0dz9epVvLy8cHBwwMzMDJ/Px9bWFvHx8dRqtQAA29vbkZERvV6PoaGhHB0d8fX1xczMDGdnZ7S0tBAIBPT09ODn5wfDw8NMTk7y9OlTkZGRaGtrY2NjA6PRiNraWgCAu7s7Xl5eCAQC3N3d4ePjAwC0tLTg6+uLw+Hg6OiIAQMGsGHDhgCALVu2kJ+fz8rKCltbW6xWKxMTEzQ0NDA6nQ6NRoM9e/YwMDDAtm3bCAQCTp06RVlZGQBAQkICtra2mJmZYWFhQWNjI5IkMTAwwMzMDK1Wi5WVFa2trdja2qJUKnH48GEA4OvrS0pKCgDA19cXe3t7bG1tYWFhwb59+7C0tMTU1BSFQoGbmxtLS0s4ODgwNDTEyspK8vPz2b9/P5IkMTU1hcVi4ezsjMlkIj09HR8fH0qlEktLS7S0tODp6YmSkhLGxsYwGAwAgEajQYFAQH5+fnh5eWFgYICLiwsA4O3tjdFoRKPRwNnZGd3d3WlpaZRKJfX19fT09ODh4YGdnR2RkZF8fHxwdnYGAGxsbGhpaeHn54e1tTXGxsbw8fHBy8uLXC4Xg8GAiYkJvV6P2NhYtra2KCgoYGRkhNzcXABAWVkZ9vb2Kysr+Pj4wM7ODkVRiKqqKrq6ukwmEwAgFArh7+8PMzMzLC0tERMTg7m5OQCAi4sLMzMzZGRk0Gg0mJubY2FhgbGxMSIiIvD29sbb2xulUglvb2+MRiPq6+vR6/Xw9/fHwcEB4+PjKJVKfH19MZvNxMbGcnFxwcrKCm9vb2RkZLC3t8fR0RE3Nze0Wi0AIDY2lqOjI3a7He/evWP8+PEsW7aMjo4OU1NTvLy8mJmZwdnZGYvFwtjYGLPZjKqqKkpKSjAajYyMjGBgYEBhYSGmpqZ4eXlhY2ODhYUFdXV1zJ49m6mpKe7u7ri6uiI/P5+MjAwmJibw8vLC3t4e5ubm8PDw4O3tjaOjI3Q6Hfr6+jg7O2NnZ4eBgQG9vb2YTCY0Gg3m5uY4e/Ys9vb2SEhIYG5ujpOTE7u7u6xWK/Pnz2f27Nn8/PzY2tpibGxMZmamwWAQBAEBAZSWllJWVgYASElJYWFhQXFxMSMjI+Li4vj6+uLh4UGj0WCxWEhPT8fZ2RmNRoP9+/dz+fJlJk+eTEhICJqmUf4ArioQLck/9yoAAAAASUVORK5CYII='


def _telegram_icon_html(opacity=1.0):
    style = f'vertical-align:middle;opacity:{opacity:g}'
    return f'<img src="data:image/svg+xml;base64,{TELEGRAM_SVG_B64}" width="16" height="16" alt="Telegram" style="{style}">'


def _youtube_icon_html(opacity=1.0):
    style = f'vertical-align:middle;opacity:{opacity:g}'
    return f'<img src="data:image/svg+xml;base64,{YOUTUBE_SVG_B64}" width="16" height="16" alt="YouTube" style="{style}">'


def _chatgpt_icon_html(opacity=1.0):
    style = f'vertical-align:middle;opacity:{opacity:g}'
    return f'<img src="/static/service-icons/chatgpt.png" width="18" height="18" alt="ChatGPT" style="{style}">'


def _service_icon_path(icon):
    icon = re.sub(r'[^a-z0-9_-]+', '', (icon or '').lower())
    if not icon:
        return ''
    return f'/static/service-icons/{icon}.png'


def _service_icon_html(icon, alt, opacity=1.0, size=18):
    src = _service_icon_path(icon)
    if not src:
        return ''
    safe_alt = html.escape(alt or icon)
    style = f'vertical-align:middle;opacity:{opacity:g}'
    return f'<img class="service-icon-img" src="{src}" width="{size}" height="{size}" alt="{safe_alt}" style="{style}">'


def _load_key_pools():
    try:
        with open(KEY_POOLS_PATH, 'r', encoding='utf-8') as f:
            value = json.load(f)
        if isinstance(value, dict):
            return _normalize_key_pools(value)
    except Exception:
        pass
    return {proto: [] for proto in ['shadowsocks', 'vmess', 'vless', 'vless2', 'trojan']}


def _dedupe_key_list(keys):
    result = []
    seen = set()
    for key_value in keys or []:
        key_value = str(key_value or '').strip()
        if not key_value or key_value in seen:
            continue
        seen.add(key_value)
        result.append(key_value)
    return result


def _normalize_key_pools(pools):
    normalized = {}
    for proto in ['shadowsocks', 'vmess', 'vless', 'vless2', 'trojan']:
        normalized[proto] = _dedupe_key_list((pools or {}).get(proto, []))
    return normalized


def _save_key_pools(pools):
    pools = _normalize_key_pools(pools)
    os.makedirs(os.path.dirname(KEY_POOLS_PATH), exist_ok=True)
    with open(KEY_POOLS_PATH, 'w', encoding='utf-8') as f:
        json.dump(pools, f, ensure_ascii=False, indent=2)


def _fetch_keys_from_subscription(url):
    """Загружает ключи из subscription-ссылки (base64-encoded список)."""
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        raw = resp.text.strip()
        # Пробуем декодировать как base64
        try:
            decoded = base64.b64decode(raw + '=' * (-len(raw) % 4)).decode('utf-8')
        except Exception:
            decoded = raw
        keys = [k.strip() for k in decoded.split('\n') if k.strip()]
        # Фильтруем только ключи известных протоколов
        result = {'shadowsocks': [], 'vmess': [], 'vless': [], 'vless2': [], 'trojan': []}
        for k in keys:
            if k.startswith('ss://'):
                result['shadowsocks'].append(k)
            elif k.startswith('vmess://'):
                result['vmess'].append(k)
            elif k.startswith('vless://'):
                result['vless'].append(k)
            elif k.startswith('trojan://'):
                result['trojan'].append(k)
        return result, None
    except requests.RequestException as exc:
        return None, f'Ошибка загрузки subscription: {exc}'
    except Exception as exc:
        return None, f'Ошибка обработки subscription: {exc}'
        


def _set_active_key(proto, key):
    pools = _load_key_pools()
    keys = _dedupe_key_list(pools.get(proto, []) or [])
    if key in keys:
        keys.remove(key)
    keys.insert(0, key)
    pools[proto] = keys
    _save_key_pools(pools)


def _install_key_for_protocol(proto, key_value, verify=True):
    if proto == 'shadowsocks':
        shadowsocks(key_value)
        return _apply_installed_proxy('shadowsocks', key_value, verify=verify)
    if proto == 'vmess':
        vmess(key_value)
        return _apply_installed_proxy('vmess', key_value, verify=verify)
    if proto == 'vless':
        vless(key_value)
        return _apply_installed_proxy('vless', key_value, verify=verify)
    if proto == 'vless2':
        vless2(key_value)
        return _apply_installed_proxy('vless2', key_value, verify=verify)
    if proto == 'trojan':
        trojan(key_value)
        return _apply_installed_proxy('trojan', key_value, verify=verify)
    raise ValueError(f'Unsupported protocol: {proto}')


def _attempt_auto_failover():
    now = time.time()
    if globals().get('pool_probe_lock') and pool_probe_lock.locked():
        return
    if auto_failover_state['in_progress']:
        return
    if auto_failover_state['last_attempt'] and now - auto_failover_state['last_attempt'] < 30:
        return

    proxy_url = proxy_settings.get(proxy_mode)
    ok, probe_message = _check_telegram_api_through_proxy(proxy_url, connect_timeout=4, read_timeout=6)
    if ok:
        auto_failover_state['last_ok'] = now
        auto_failover_state['last_fail'] = 0.0
        return

    if not auto_failover_state['last_fail']:
        auto_failover_state['last_fail'] = now

    if now - auto_failover_state['last_fail'] < AUTO_FAILOVER_GRACE_SECONDS:
        return

    auto_failover_state['in_progress'] = True
    auto_failover_state['last_attempt'] = now
    try:
        pools = _load_key_pools()
        candidates = []
        for proto in ['shadowsocks', 'vmess', 'vless', 'vless2', 'trojan']:
            for key_value in pools.get(proto, []) or []:
                candidates.append((proto, key_value))

        if not candidates:
            _write_runtime_log('Auto-failover: ключей в пулах нет, переключать не на что.')
            return

        _write_runtime_log(f'Auto-failover: Telegram API не отвечает >{AUTO_FAILOVER_GRACE_SECONDS}s (режим {proxy_mode}). Пробуем ключи из пулов.')
        for proto, key_value in candidates:
            try:
                result = _install_key_for_protocol(proto, key_value)
            except Exception as exc:
                _write_runtime_log(f'Auto-failover: ошибка установки {proto} ключа: {exc}')
                continue

            proxy_url = proxy_settings.get(proto)
            ok2, _ = _check_telegram_api_through_proxy(proxy_url, connect_timeout=6, read_timeout=10)
            if ok2:
                yt_ok, _ = _check_http_through_proxy(proxy_url, url='https://www.youtube.com', connect_timeout=3, read_timeout=5)
                update_proxy(proto)
                _set_active_key(proto, key_value)
                _record_key_probe(proto, key_value, tg_ok=True, yt_ok=yt_ok)
                auto_failover_state['last_ok'] = time.time()
                auto_failover_state['last_fail'] = 0.0
                _write_runtime_log(f'Auto-failover: переключено на {proto}; Telegram API доступен. {result}')
                return

        _write_runtime_log('Auto-failover: перебор ключей из пулов не дал доступа к Telegram API.')
    finally:
        auto_failover_state['in_progress'] = False


def _start_auto_failover_thread():
    def worker():
        while not shutdown_requested.is_set():
            try:
                _attempt_auto_failover()
            except Exception as exc:
                _write_runtime_log(f'Auto-failover error: {exc}')
            shutdown_requested.wait(AUTO_FAILOVER_POLL_SECONDS)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

token = config.token
usernames = config.usernames
routerip = config.routerip
browser_port = config.browser_port
fork_repo_owner = getattr(config, 'fork_repo_owner', 'andruwko73')
fork_repo_name = getattr(config, 'fork_repo_name', 'bypass_keenetic')
fork_button_label = getattr(config, 'fork_button_label', f'Fork by {fork_repo_owner}')
localportsh = config.localportsh
localporttrojan = config.localporttrojan
localportvmess = config.localportvmess
localportvless = config.localportvless
localportvless_transparent = str(int(localportvless) + 1)
localportvless2 = str(int(localportvless) + 2)
localportvless2_transparent = str(int(localportvless) + 3)
localportvmess_transparent = str(int(localportvless) + 4)
localportsh_bot = str(getattr(config, 'localportsh_bot', 10820))
localporttrojan_bot = str(getattr(config, 'localporttrojan_bot', 10830))
dnsovertlsport = config.dnsovertlsport
dnsoverhttpsport = config.dnsoverhttpsport

bot = telebot.TeleBot(token)
sid = "0"
PROXY_MODE_FILE = '/opt/etc/bot_proxy_mode'
BOT_AUTOSTART_FILE = '/opt/etc/bot_autostart'
TELEGRAM_COMMAND_JOB_FILE = '/opt/etc/bot/telegram_command_job.json'
TELEGRAM_COMMAND_RESULT_FILE = '/opt/etc/bot/telegram_command_result.json'
TELEGRAM_RESULT_RETRY_INTERVAL = 30

WEB_STATUS_CACHE_TTL = 60
KEY_STATUS_CACHE_TTL = 60
STATUS_CACHE_TTL = min(WEB_STATUS_CACHE_TTL, KEY_STATUS_CACHE_TTL)
WEB_STATUS_STARTUP_GRACE_PERIOD = 45
KEY_PROBE_CACHE_TTL = 3600
_KEY_PROBE_MAX_PER_RUN_VALUE = int(getattr(config, 'pool_probe_max_per_run', 0))
KEY_PROBE_MAX_PER_RUN = _KEY_PROBE_MAX_PER_RUN_VALUE if _KEY_PROBE_MAX_PER_RUN_VALUE > 0 else None
POOL_PROBE_ACTIVE_ONLY = False
POOL_PROBE_DELAY_SECONDS = float(getattr(config, 'pool_probe_delay_seconds', 0.3))
POOL_PROBE_MIN_AVAILABLE_KB = 120000
POOL_PROBE_TEST_PORT = str(getattr(config, 'pool_probe_test_port', 10991))
POOL_PROBE_BATCH_SIZE = max(1, int(getattr(config, 'pool_probe_batch_size', 3)))
POOL_PROBE_CONCURRENCY = max(1, min(int(getattr(config, 'pool_probe_concurrency', 1)), POOL_PROBE_BATCH_SIZE))
POOL_PROBE_PAGE_MAX_KEYS = max(1, int(getattr(config, 'pool_probe_page_max_keys', 12)))
POOL_PROBE_TG_CONNECT_TIMEOUT = float(getattr(config, 'pool_probe_tg_connect_timeout', 1.5))
POOL_PROBE_TG_READ_TIMEOUT = float(getattr(config, 'pool_probe_tg_read_timeout', 2))
POOL_PROBE_HTTP_CONNECT_TIMEOUT = float(getattr(config, 'pool_probe_http_connect_timeout', 1.5))
POOL_PROBE_HTTP_READ_TIMEOUT = float(getattr(config, 'pool_probe_http_read_timeout', 1.5))
POOL_PROBE_PAGE_REFRESH_INTERVAL = float(getattr(config, 'pool_probe_page_refresh_interval', 1800))
POOL_PROBE_SINGLE_TIMEOUT_SECONDS = max(
    8.0,
    POOL_PROBE_TG_CONNECT_TIMEOUT + POOL_PROBE_TG_READ_TIMEOUT +
    POOL_PROBE_HTTP_CONNECT_TIMEOUT + POOL_PROBE_HTTP_READ_TIMEOUT + 3.0,
)
POOL_PROBE_BATCH_TIMEOUT_SECONDS = float(
    getattr(config, 'pool_probe_batch_timeout_seconds', POOL_PROBE_SINGLE_TIMEOUT_SECONDS + 5.0)
)
POOL_PROBE_UI_POLL_EXTENSION_MS = int(getattr(config, 'pool_probe_ui_poll_extension_ms', 180000))
APP_BRANCH_LABEL = 'feature/independent-rework'
APP_BRANCH_DESCRIPTION = 'Telegram бот'
APP_VERSION_COUNTER = 429
APP_VERSION_LABEL = f'v{APP_VERSION_COUNTER}'
BOT_SOURCE_PATH = os.path.abspath(__file__)
CONNECTIVITY_CHECK_DOMAINS = [
    'full:connectivitycheck.gstatic.com',
    'full:connectivitycheck.android.com',
    'full:clients3.google.com',
    'full:clients4.google.com',
    'full:www.google.com',
    'full:www.gstatic.com',
]
TELEGRAM_UNBLOCK_ENTRIES = [
    '91.108.56.0/22',
    '91.108.4.0/22',
    '91.108.8.0/22',
    '91.108.16.0/22',
    '91.108.12.0/22',
    '149.154.160.0/20',
    '91.105.192.0/23',
    '91.108.20.0/22',
    '185.76.151.0/24',
    '5.28.192.0/21',
    '95.161.64.0/20',
    'api.telegram.org',
    'web.telegram.org',
    'my.telegram.org',
    't.me',
    'tx.me',
    'telegra.ph',
    'graph.org',
    'telegram.org',
    'telegram.me',
    'telegram.dog',
    'telegram-cdn.org',
    'telegramapp.org',
    'telegramdownload.com',
    'cdn-telegram.org',
    'telegram.ai',
    'telegram.asia',
    'telegram.biz',
    'telegram.cloud',
    'telegram.cn',
    'telegram.co',
    'telegram.com',
    'telegram.de',
    'telegram.dev',
    'telegram.eu',
    'telegram.fr',
    'telegram.host',
    'telegram.in',
    'telegram.info',
    'telegram.io',
    'telegram.jp',
    'telegram.net',
    'telegram.qa',
    'telegram.ru',
    'telegram.services',
    'telegram.solutions',
    'telegram.space',
    'telegram.team',
    'telegram.tech',
    'telegram.uk',
    'telegram.us',
    'telegram.website',
    'telegram.xyz',
    'telesco.pe',
    'comments.app',
    'contest.com',
    'fragment.com',
    'quiz.directory',
    'tg.dev',
    'tg.org',
    'tgram.org',
    'tdesktop.com',
    'teleg.xyz',
    'telega.one',
]
BOT_DIR = os.path.dirname(BOT_SOURCE_PATH)
STATIC_DIR = os.path.join(BOT_DIR, 'static')
README_PATH = os.path.join(BOT_DIR, 'README.md')
XRAY_SERVICE_SCRIPT = '/opt/etc/init.d/S24xray'
V2RAY_SERVICE_SCRIPT = '/opt/etc/init.d/S24v2ray'
XRAY_CONFIG_DIR = '/opt/etc/xray'
V2RAY_CONFIG_DIR = '/opt/etc/v2ray'
CORE_PROXY_CONFIG_DIR = XRAY_CONFIG_DIR if os.path.exists(XRAY_SERVICE_SCRIPT) else V2RAY_CONFIG_DIR
CORE_PROXY_SERVICE_SCRIPT = XRAY_SERVICE_SCRIPT if os.path.exists(XRAY_SERVICE_SCRIPT) else V2RAY_SERVICE_SCRIPT
CORE_PROXY_CONFIG_PATH = os.path.join(CORE_PROXY_CONFIG_DIR, 'config.json')
CORE_PROXY_ERROR_LOG = os.path.join(CORE_PROXY_CONFIG_DIR, 'error.log')
CORE_PROXY_ACCESS_LOG = os.path.join(CORE_PROXY_CONFIG_DIR, 'access.log')
VMESS_KEY_PATH = os.path.join(CORE_PROXY_CONFIG_DIR, 'vmess.key')
VLESS_KEY_PATH = os.path.join(CORE_PROXY_CONFIG_DIR, 'vless.key')
VLESS2_KEY_PATH = os.path.join(CORE_PROXY_CONFIG_DIR, 'vless2.key')

bot_ready = False
bot_polling = False
web_httpd = None
shutdown_requested = threading.Event()
proxy_mode = config.default_proxy_mode
proxy_settings = {
    'none': None,
    'shadowsocks': f'socks5h://127.0.0.1:{localportsh_bot}',
    'vmess': f'socks5h://127.0.0.1:{localportvmess}',
    'vless': f'socks5h://127.0.0.1:{localportvless}',
    'vless2': f'socks5h://127.0.0.1:{localportvless2}',
    'trojan': f'socks5h://127.0.0.1:{localporttrojan_bot}',
}
proxy_supports_http = {
    'none': True,
    'shadowsocks': True,
    'vmess': True,
    'vless': True,
    'vless2': True,
    'trojan': True,
}
status_snapshot_cache = {
    'timestamp': 0,
    'data': None,
    'signature': None,
}
status_refresh_lock = threading.Lock()
status_refresh_in_progress = set()
pool_probe_lock = threading.Lock()
pool_probe_auto_lock = threading.Lock()
pool_apply_lock = threading.Lock()
pool_probe_last_auto_started_at = 0
pool_probe_progress_lock = threading.Lock()
pool_probe_progress = {
    'running': False,
    'checked': 0,
    'total': 0,
    'started_at': 0,
    'finished_at': 0,
}
process_started_at = time.time()
web_command_lock = threading.Lock()
web_command_state = {
    'running': False,
    'command': '',
    'label': '',
    'result': '',
    'progress': 0,
    'progress_label': '',
    'started_at': 0,
    'finished_at': 0,
    'shown_after_finish': False,
}
web_flash_lock = threading.Lock()
web_flash_message = ''
DIRECT_FETCH_ENV_KEYS = [
    'HTTPS_PROXY',
    'HTTP_PROXY',
    'https_proxy',
    'http_proxy',
    'ALL_PROXY',
    'all_proxy',
]
RUNTIME_ERROR_LOG_PATHS = [
    '/opt/etc/error.log',
    '/opt/etc/bot/error.log',
]
MENU_STATE_UNSET = object()
TELEGRAM_CONFIRM_LEVEL = 30
chat_menu_state_lock = threading.Lock()
chat_menu_states = {}
chat_pool_pages = {}


def _is_local_web_client(address):
    try:
        ip_obj = ipaddress.ip_address((address or '').strip())
    except ValueError:
        return False
    return ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local


def _resolve_web_bind_host():
    candidate = str(routerip or '').strip()
    if not candidate:
        return ''
    try:
        ip_obj = ipaddress.ip_address(candidate)
    except ValueError:
        return ''
    if ip_obj.is_unspecified:
        return ''
    return candidate


def _normalize_username(value):
    if value is None:
        return ''
    normalized = str(value).strip()
    if normalized.startswith('@'):
        normalized = normalized[1:]
    return normalized.casefold()


def _build_authorized_identities(raw_values):
    if isinstance(raw_values, (str, int)):
        values = [raw_values]
    else:
        values = list(raw_values or [])

    normalized_usernames = set()
    numeric_ids = set()
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        if text.lstrip('-').isdigit():
            try:
                numeric_ids.add(int(text))
                continue
            except ValueError:
                pass
        normalized = _normalize_username(text)
        if normalized:
            normalized_usernames.add(normalized)
    return normalized_usernames, numeric_ids


AUTHORIZED_USERNAMES, AUTHORIZED_USER_IDS = _build_authorized_identities(usernames)
EXTRA_AUTHORIZED_USER_IDS = getattr(config, 'authorized_user_ids', [])
_, EXTRA_NUMERIC_USER_IDS = _build_authorized_identities(EXTRA_AUTHORIZED_USER_IDS)
AUTHORIZED_USER_IDS.update(EXTRA_NUMERIC_USER_IDS)


def _raw_github_url(path):
    return f'https://raw.githubusercontent.com/{fork_repo_owner}/{fork_repo_name}/main/{path}?ts={int(time.time())}'


def _fetch_remote_text(url, timeout=20):
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.text


SOCIALNET_SOURCE_URL = 'https://raw.githubusercontent.com/tas-unn/bypass_keenetic/main/socialnet.txt'
SOCIALNET_LOCAL_PATHS = [
    os.path.join(BOT_DIR, 'socialnet.txt'),
    '/opt/etc/bot/socialnet.txt',
    '/opt/etc/unblock/socialnet.txt',
]


SERVICE_LIST_SOURCES = {
    'youtube': {
        'label': 'YouTube',
        'aliases': ['youtube', 'yt', 'ютуб'],
        'url': 'https://raw.githubusercontent.com/itdoginfo/allow-domains/main/Services/youtube.lst',
    },
    'telegram': {
        'label': 'Telegram',
        'aliases': ['telegram', 'tg', 'телеграм', 'телега'],
        'url': 'https://raw.githubusercontent.com/itdoginfo/allow-domains/main/Services/telegram.lst',
        'entries': TELEGRAM_UNBLOCK_ENTRIES,
    },
    'meta': {
        'label': 'Instagram / Meta',
        'aliases': ['meta', 'instagram', 'insta', 'facebook', 'whatsapp', 'threads', 'инстаграм'],
        'url': 'https://raw.githubusercontent.com/itdoginfo/allow-domains/main/Services/meta.lst',
    },
    'discord': {
        'label': 'Discord',
        'aliases': ['discord', 'дискорд'],
        'url': 'https://raw.githubusercontent.com/itdoginfo/allow-domains/main/Services/discord.lst',
    },
    'tiktok': {
        'label': 'TikTok',
        'aliases': ['tiktok', 'tik-tok', 'тик ток', 'тикток'],
        'url': 'https://raw.githubusercontent.com/itdoginfo/allow-domains/main/Services/tiktok.lst',
    },
    'twitter': {
        'label': 'X / Twitter',
        'aliases': ['twitter', 'x', 'твиттер'],
        'url': 'https://raw.githubusercontent.com/itdoginfo/allow-domains/main/Services/twitter.lst',
    },
}

SOCIALNET_SERVICE_KEYS = ('telegram', 'meta', 'discord', 'tiktok', 'twitter')
SOCIALNET_ALL_KEY = 'all'
SOCIALNET_EXCLUDED_ENTRIES = {
    'youtube.com',
    'm.youtube.com',
    'tv.youtube.com',
    's.youtube.com',
    'youtu.be',
    'yt.be',
    'ytimg.com',
    'i.ytimg.com',
    'ytimg.l.google.com',
    'yt3.ggpht.com',
    'yt3.googleusercontent.com',
    'ggpht.com',
    'googlevideo.com',
    'youtubei.googleapis.com',
    'youtubeembeddedplayer.googleapis.com',
    'youtube-ui.l.google.com',
    'wide-youtube.l.google.com',
    'yt-video-upload.l.google.com',
    'play-fe.googleapis.com',
    'jnn-pa.googleapis.com',
    'returnyoutubedislikeapi.com',
    'youtubekids.com',
    'youtube-nocookie.com',
    'yting.com',
    'gvt1.com',
    'gvt2.com',
    'googleapis.com',
    'googleusercontent.com',
    'nhacmp3youtube.com',
}


def _service_list_alias_map():
    aliases = {}
    for key, source in SERVICE_LIST_SOURCES.items():
        aliases[key] = key
        aliases[source.get('label', key).lower()] = key
        for alias in source.get('aliases', []):
            aliases[alias.lower()] = key
    return aliases


def _get_chat_menu_state(chat_id):
    with chat_menu_state_lock:
        state = chat_menu_states.get(chat_id)
        if state is None:
            state = {'level': 0, 'bypass': None}
            chat_menu_states[chat_id] = state
        return dict(state)


def _set_chat_menu_state(chat_id, level=MENU_STATE_UNSET, bypass=MENU_STATE_UNSET):
    with chat_menu_state_lock:
        state = chat_menu_states.get(chat_id)
        if state is None:
            state = {'level': 0, 'bypass': None}
            chat_menu_states[chat_id] = state
        if level is not MENU_STATE_UNSET:
            state['level'] = level
        if bypass is not MENU_STATE_UNSET:
            state['bypass'] = bypass


def _get_pool_page(chat_id):
    with chat_menu_state_lock:
        return int(chat_pool_pages.get(chat_id, 0) or 0)


def _set_pool_page(chat_id, page):
    try:
        page = int(page)
    except (TypeError, ValueError):
        page = 0
    with chat_menu_state_lock:
        chat_pool_pages[chat_id] = max(0, page)


def _clear_pool_page(chat_id):
    with chat_menu_state_lock:
        chat_pool_pages.pop(chat_id, None)


def _telegram_info_text_from_readme():
    readme_text = ''
    try:
        readme_text = _fetch_remote_text(_raw_github_url('README.md'))
    except Exception:
        readme_text = _read_text_file(README_PATH)

    if not readme_text.strip():
        return (
            'Информация временно недоступна: README.md не найден.\n\n'
            'Откройте страницу роутера 192.168.1.1:8080 или README в репозитории форка.'
        )

    lines = readme_text.splitlines()
    sections = []
    current_title = ''
    current_lines = []

    def flush_section():
        if current_title and current_lines:
            sections.append((current_title, current_lines[:]))

    for raw_line in lines:
        line = raw_line.rstrip()
        if line.startswith('## '):
            flush_section()
            current_title = line[3:].strip()
            current_lines = []
            continue
        if current_title:
            current_lines.append(line)
    flush_section()

    wanted_titles = ['Об этом форке', 'Как работает бот на странице 192.168.1.1:8080']
    selected = []
    for wanted in wanted_titles:
        for title, section_lines in sections:
            if title == wanted:
                selected.append((title, section_lines))
                break

    if not selected:
        selected = sections[:2]

    text_lines = []
    for title, section_lines in selected:
        if text_lines:
            text_lines.append('')
        text_lines.append(f'<b>{html.escape(title)}</b>')
        for line in section_lines:
            stripped = line.strip()
            if stripped.startswith('### Скриншоты интерфейса'):
                break
            if not stripped:
                if text_lines and text_lines[-1] != '':
                    text_lines.append('')
                continue
            if stripped.startswith('<') or stripped.startswith('```'):
                continue
            if stripped.startswith('!['):
                continue
            cleaned = html.escape(stripped.replace('`', ''))
            cleaned = re.sub(
                r'\[([^\]]+)\]\(([^\)]+)\)',
                lambda match: f'<a href="{html.escape(match.group(2), quote=True)}">{html.escape(match.group(1))}</a>',
                cleaned,
            )
            text_lines.append(cleaned)

    cleaned_lines = []
    previous_blank = False
    for line in text_lines:
        if not line:
            if not previous_blank:
                cleaned_lines.append('')
            previous_blank = True
            continue
        cleaned_lines.append(line)
        previous_blank = False

    result = '\n'.join(cleaned_lines).strip()
    if not result:
        return 'Информация временно недоступна: README.md не содержит подходящего текста.'
    return result[:3900]


def _write_runtime_log(message, mode='a'):
    text = '' if message is None else str(message)
    if text and not text.endswith('\n'):
        text += '\n'
    for log_path in RUNTIME_ERROR_LOG_PATHS:
        try:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with open(log_path, mode, encoding='utf-8', errors='ignore') as file:
                file.write(text)
        except Exception:
            continue


def _message_debug_text(message):
    text = getattr(message, 'text', None)
    if text is None:
        return '<non-text>'
    text = str(text).replace('\r', ' ').replace('\n', ' ')
    if len(text) > 120:
        return text[:117] + '...'
    return text


def _authorize_message(message, handler_name):
    user = getattr(message, 'from_user', None)
    chat = getattr(message, 'chat', None)
    user_id = getattr(user, 'id', None)
    username = getattr(user, 'username', None)
    normalized_username = _normalize_username(username)
    chat_id = getattr(chat, 'id', None)
    chat_type = getattr(chat, 'type', None)

    authorized = False
    reason = 'unauthorized'
    if user_id in AUTHORIZED_USER_IDS:
        authorized = True
        reason = 'user_id'
    elif normalized_username and normalized_username in AUTHORIZED_USERNAMES:
        authorized = True
        reason = 'username'
    elif not normalized_username:
        reason = 'missing_username'

    _write_runtime_log(
        f'handler={handler_name} chat_id={chat_id} chat_type={chat_type} '
        f'user_id={user_id} username={username!r} authorized={authorized} '
        f'reason={reason} text={_message_debug_text(message)}'
    )
    return authorized, reason


def _send_unauthorized_message(message, reason):
    if reason == 'missing_username':
        text = 'У вашего Telegram-аккаунта не задан username. Задайте username в настройках Telegram и повторите команду.'
    else:
        text = 'Вы не являетесь автором канала'
    bot.send_message(message.chat.id, text)


def _read_json_file(path, default=None):
    try:
        with open(path, 'r', encoding='utf-8') as file:
            return json.load(file)
    except Exception:
        return default


def _write_json_file(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as file:
        json.dump(payload, file, ensure_ascii=False)


def _remove_file(path):
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def _has_socks_support():
    try:
        import socks  # noqa: F401
        return True
    except Exception:
        return False


def _daemonize_process():
    if os.name != 'posix':
        return
    try:
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
    except Exception:
        pass


def _request_shutdown(reason=''):
    global bot_polling
    if shutdown_requested.is_set():
        return
    shutdown_requested.set()
    bot_polling = False
    if reason:
        _write_runtime_log(f'Запрошена остановка бота: {reason}')
    try:
        bot.stop_polling()
    except Exception:
        pass
    try:
        bot.stop_bot()
    except Exception:
        pass
    if web_httpd is not None:
        try:
            threading.Thread(target=web_httpd.shutdown, daemon=True).start()
        except Exception:
            pass


def _finalize_shutdown():
    if web_httpd is not None:
        try:
            web_httpd.server_close()
        except Exception:
            pass
    try:
        bot.delete_webhook(timeout=10)
    except Exception as exc:
        _write_runtime_log(f'Не удалось удалить webhook при остановке: {exc}')
    try:
        bot.close()
    except Exception as exc:
        close_error = str(exc).lower()
        if '429' in close_error or 'too many requests' in close_error:
            _write_runtime_log('Bot API close недоступен в первые 10 минут после старта, остановка продолжена без него')
        else:
            _write_runtime_log(f'Не удалось закрыть bot instance при остановке: {exc}')


def _register_signal_handlers():
    if os.name != 'posix':
        return

    def _handle_stop_signal(signum, frame):
        try:
            signal_name = signal.Signals(signum).name
        except Exception:
            signal_name = str(signum)
        _request_shutdown(signal_name)

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _handle_stop_signal)
        except Exception:
            pass


def _is_polling_conflict(err):
    text = str(err).lower()
    return 'terminated by other getupdates request' in text or '409 conflict' in text


def _save_proxy_mode(proxy_type):
    try:
        os.makedirs(os.path.dirname(PROXY_MODE_FILE), exist_ok=True)
        with open(PROXY_MODE_FILE, 'w', encoding='utf-8') as file:
            file.write(proxy_type)
    except Exception:
        pass


def _proxy_mode_label(proxy_type):
    labels = {
        'none': 'None',
        'shadowsocks': 'Shadowsocks',
        'vmess': 'Vmess',
        'vless': 'Vless 1',
        'vless2': 'Vless 2',
        'trojan': 'Trojan',
    }
    return labels.get(proxy_type, proxy_type)


def _save_bot_autostart(enabled):
    try:
        if enabled:
            with open(BOT_AUTOSTART_FILE, 'w', encoding='utf-8') as file:
                file.write('1')
        elif os.path.exists(BOT_AUTOSTART_FILE):
            os.remove(BOT_AUTOSTART_FILE)
    except Exception:
        pass


def _prepare_entware_dns():
    try:
        result = subprocess.run(
            ['nslookup', 'bin.entware.net', '192.168.1.1'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode == 0:
            return 'Entware DNS уже доступен.'
    except Exception:
        pass

    notes = []
    try:
        subprocess.run(['ndmc', '-c', 'no opkg dns-override'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        subprocess.run(['ndmc', '-c', 'system configuration save'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        notes.append('opkg dns-override отключён')
    except Exception:
        notes.append('не удалось отключить opkg dns-override')

    try:
        resolv_conf = '/etc/resolv.conf'
        preserved_lines = []
        if os.path.exists(resolv_conf):
            with open(resolv_conf, 'r', encoding='utf-8', errors='ignore') as file:
                preserved_lines = [
                    line.rstrip('\n')
                    for line in file
                    if line.strip() and not line.lstrip().startswith('nameserver')
                ]
        with open(resolv_conf, 'w', encoding='utf-8') as file:
            file.write('nameserver 8.8.8.8\n')
            file.write('nameserver 1.1.1.1\n')
            if preserved_lines:
                file.write('\n'.join(preserved_lines) + '\n')
        notes.append('внешние DNS записаны первыми в /etc/resolv.conf')
    except Exception:
        notes.append('не удалось обновить /etc/resolv.conf')

    try:
        lookup_output = subprocess.check_output(
            ['nslookup', 'bin.entware.net', '8.8.8.8'],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        host_matches = re.findall(r'Address\s+\d+:\s+((?:\d{1,3}\.){3}\d{1,3})', lookup_output)
        entware_ip = host_matches[-1] if host_matches else ''
        if entware_ip:
            hosts_path = '/etc/hosts'
            preserved_lines = []
            if os.path.exists(hosts_path):
                with open(hosts_path, 'r', encoding='utf-8', errors='ignore') as file:
                    preserved_lines = [line.rstrip('\n') for line in file if 'bin.entware.net' not in line]
            with open(hosts_path, 'w', encoding='utf-8') as file:
                if preserved_lines:
                    file.write('\n'.join(preserved_lines) + '\n')
                file.write(f'{entware_ip} bin.entware.net\n')
            notes.append(f'bin.entware.net закреплён в /etc/hosts как {entware_ip}')
    except Exception:
        notes.append('не удалось закрепить bin.entware.net в /etc/hosts')

    return 'Подготовка Entware DNS: ' + ', '.join(notes)


def _ensure_legacy_bot_paths():
    mappings = [
        ('/opt/etc/bot/bot_config.py', '/opt/etc/bot_config.py'),
        ('/opt/etc/bot/main.py', '/opt/etc/bot.py'),
    ]
    notes = []
    for source_path, legacy_path in mappings:
        try:
            if not os.path.exists(source_path):
                continue
            if os.path.islink(legacy_path):
                if os.path.realpath(legacy_path) == os.path.realpath(source_path):
                    continue
                os.remove(legacy_path)
            elif os.path.exists(legacy_path):
                continue
            os.symlink(source_path, legacy_path)
            notes.append(f'{legacy_path} -> {source_path}')
        except Exception:
            try:
                shutil.copyfile(source_path, legacy_path)
                notes.append(f'{legacy_path} скопирован из {source_path}')
            except Exception:
                notes.append(f'не удалось подготовить {legacy_path}')
    if not notes:
        return 'Legacy-пути бота уже доступны.'
    return 'Подготовка legacy-путей: ' + ', '.join(notes)


def _chunk_text(text, limit=3500):
    if not text or not text.strip():
        return []
    chunks = []
    current = []
    current_len = 0
    for line in text.splitlines():
        extra = len(line) + 1
        if current and current_len + extra > limit:
            chunks.append('\n'.join(current))
            current = [line]
            current_len = extra
        else:
            current.append(line)
            current_len += extra
    if current:
        chunks.append('\n'.join(current))
    return chunks or ['']


def _send_telegram_chunks(chat_id, text, reply_markup=None):
    chunks = [chunk for chunk in _chunk_text(text) if chunk.strip()]
    for index, chunk in enumerate(chunks):
        markup = reply_markup if index == len(chunks) - 1 else None
        bot.send_message(chat_id, chunk, reply_markup=markup)


def _unblock_list_path(list_name):
    return os.path.join('/opt/etc/unblock', f'{list_name}.txt')


def _read_unblock_list_entries(list_name):
    list_path = _unblock_list_path(list_name)
    if not os.path.exists(list_path):
        raise FileNotFoundError(list_path)
    with open(list_path, encoding='utf-8') as file:
        return [line.strip() for line in file if line.strip()]


def _write_unblock_list_entries(list_name, entries):
    list_path = _unblock_list_path(list_name)
    with open(list_path, 'w', encoding='utf-8') as file:
        for line in sorted(set(entries)):
            if line:
                file.write(line + '\n')


def _normalize_unblock_route_name(list_name):
    safe_name = os.path.basename((list_name or '').strip())
    if safe_name.endswith('.txt'):
        safe_name = safe_name[:-4]
    if not safe_name or not re.match(r'^[A-Za-z0-9_-]+$', safe_name):
        raise ValueError('Некорректное имя списка')
    return safe_name


def _socialnet_entries_from_text(text):
    entries = []
    seen = set()
    for raw_line in (text or '').replace('\r', '\n').split('\n'):
        line = raw_line.split('#', 1)[0].strip()
        if not line or line.lower() in SOCIALNET_EXCLUDED_ENTRIES or line in seen:
            continue
        seen.add(line)
        entries.append(line)
    return entries


def _resolve_socialnet_service(value):
    normalized = (value or '').strip().lower()
    if normalized in ('', SOCIALNET_ALL_KEY, 'all', 'все', 'все соцсети'):
        return SOCIALNET_ALL_KEY
    aliases = _service_list_alias_map()
    key = aliases.get(normalized)
    if key in SOCIALNET_SERVICE_KEYS:
        return key
    return None


def _socialnet_service_label(service_key):
    if service_key == SOCIALNET_ALL_KEY:
        return 'Все соцсети'
    return SERVICE_LIST_SOURCES.get(service_key, {}).get('label', service_key)


def _load_service_entries(service_key):
    source = SERVICE_LIST_SOURCES.get(service_key)
    if not source:
        raise ValueError('Неизвестная соцсеть')
    if source.get('entries'):
        return _socialnet_entries_from_text('\n'.join(source['entries']))
    raw_text = _fetch_remote_text(source['url'], timeout=25)
    entries = _parse_service_domains(raw_text)
    if not entries:
        raise ValueError(f'Список {source["label"]} пуст')
    return entries


def _load_socialnet_entries(service_key=SOCIALNET_ALL_KEY):
    service_key = _resolve_socialnet_service(service_key)
    if not service_key:
        raise ValueError('Неизвестная соцсеть')
    if service_key != SOCIALNET_ALL_KEY:
        return _load_service_entries(service_key)
    for path in SOCIALNET_LOCAL_PATHS:
        try:
            if os.path.exists(path):
                entries = _socialnet_entries_from_text(_read_text_file(path))
                if entries:
                    return entries
        except Exception:
            continue
    social_text = _fetch_remote_text(SOCIALNET_SOURCE_URL, timeout=25)
    entries = _socialnet_entries_from_text(social_text)
    if not entries:
        raise ValueError('Список соцсетей пуст')
    return entries


def _apply_socialnet_list(list_name, service_key=SOCIALNET_ALL_KEY, remove=False):
    route_name = _normalize_unblock_route_name(list_name)
    service_key = _resolve_socialnet_service(service_key)
    if not service_key:
        raise ValueError('Неизвестная соцсеть')
    entries = set(_load_socialnet_entries(service_key))
    list_path = _unblock_list_path(route_name)
    current = set(_read_unblock_list_entries(route_name)) if os.path.exists(list_path) else set()
    before = len(current)
    if remove:
        current.difference_update(entries)
        changed = before - len(current)
        action = 'удалено'
    else:
        current.update(entries)
        changed = len(current) - before
        action = 'добавлено'
    _write_unblock_list_entries(route_name, current)
    subprocess.run(['/opt/bin/unblock_update.sh'], check=False)
    label = _list_label(f'{route_name}.txt')
    service_label = _socialnet_service_label(service_key)
    return f'✅ {service_label}: {action} {changed} записей в {label}. Всего в списке: {len(current)}.'


def _socialnet_service_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    options = [types.KeyboardButton(_socialnet_service_label(key)) for key in SOCIALNET_SERVICE_KEYS]
    options.append(types.KeyboardButton(_socialnet_service_label(SOCIALNET_ALL_KEY)))
    for index in range(0, len(options), 2):
        markup.row(*options[index:index + 2])
    markup.add(types.KeyboardButton("🔙 Назад"))
    return markup


def _list_actions_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    item1 = types.KeyboardButton("📑 Показать список")
    item2 = types.KeyboardButton("📝 Добавить в список")
    item3 = types.KeyboardButton("🗑 Удалить из списка")
    item4 = types.KeyboardButton("📥 Сервисы по запросу")
    back = types.KeyboardButton("🔙 Назад")
    markup.row(item1, item2, item3)
    markup.row(item4)
    markup.row(back)
    return markup


def _service_list_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    buttons = [types.KeyboardButton(source['label']) for source in SERVICE_LIST_SOURCES.values()]
    for index in range(0, len(buttons), 2):
        markup.row(*buttons[index:index + 2])
    markup.add(types.KeyboardButton("🔙 Назад"))
    return markup


def _resolve_service_list_name(value):
    normalized = (value or '').strip().lower()
    return _service_list_alias_map().get(normalized)


def _parse_service_domains(text):
    domains = []
    seen = set()
    for raw_line in text.replace('\r', '\n').split('\n'):
        line = raw_line.split('#', 1)[0].strip()
        if not line:
            continue
        for token in re.split(r'[\s,]+', line):
            item = token.strip().strip('"\'')
            item = re.sub(r'^(DOMAIN-SUFFIX|DOMAIN|HOST-SUFFIX),', '', item, flags=re.IGNORECASE)
            item = re.sub(r'^\+\.', '', item)
            item = re.sub(r'^\*\.', '', item)
            item = item.strip('/').lower()
            if not item or '/' in item or ':' in item:
                continue
            if not re.match(r'^[a-z0-9*_.-]+\.[a-z0-9_.-]+$', item):
                continue
            if item not in seen:
                seen.add(item)
                domains.append(item)
    return domains


def _append_entries_to_unblock_list(list_name, entries):
    existing = set(_read_unblock_list_entries(list_name)) if os.path.exists(_unblock_list_path(list_name)) else set()
    before = len(existing)
    existing.update(entries)
    _write_unblock_list_entries(list_name, existing)
    subprocess.run(['/opt/bin/unblock_update.sh'], check=False)
    return len(existing) - before, len(existing)


def _handle_getlist_request(message, service_name, route_name=None, reply_markup=None):
    service_key = _resolve_service_list_name(service_name)
    if not service_key:
        names = ', '.join(source['label'] for source in SERVICE_LIST_SOURCES.values())
        bot.send_message(message.chat.id, f'⚠️ Не знаю такой сервис. Доступно: {names}', reply_markup=reply_markup)
        return

    route = _resolve_unblock_list_selection(route_name) if route_name else None
    if route and route.endswith('.txt'):
        route = route[:-4]
    if service_key == 'telegram' and not route:
        route = 'vless'
    if not route:
        state = _get_chat_menu_state(message.chat.id)
        route = state.get('bypass')
    if not route:
        route = 'vless'
    if not re.match(r'^[A-Za-z0-9_-]+$', route or ''):
        bot.send_message(message.chat.id, '⚠️ Некорректное имя маршрута.', reply_markup=reply_markup)
        return

    source = SERVICE_LIST_SOURCES[service_key]
    try:
        if source.get('entries'):
            entries = list(source['entries'])
        else:
            raw_text = _fetch_remote_text(source['url'], timeout=25)
            entries = _parse_service_domains(raw_text)
        if not entries:
            bot.send_message(message.chat.id, f'⚠️ Список {source["label"]} загружен, но домены не найдены.', reply_markup=reply_markup)
            return
        added, total = _append_entries_to_unblock_list(route, entries)
    except requests.RequestException as exc:
        bot.send_message(message.chat.id, f'⚠️ Не удалось загрузить список {source["label"]}: {exc}', reply_markup=reply_markup)
        return
    except Exception as exc:
        bot.send_message(message.chat.id, f'⚠️ Не удалось применить список {source["label"]}: {exc}', reply_markup=reply_markup)
        return

    label = _list_label(f'{route}.txt')
    bot.send_message(
        message.chat.id,
        f'✅ {source["label"]}: добавлено {added} новых записей, всего в маршруте {label}: {total}. Списки применяются.',
        reply_markup=reply_markup,
    )


def _build_main_menu_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    item1 = types.KeyboardButton("🔰 Установка и удаление")
    item2 = types.KeyboardButton("🔑 Ключи и мосты")
    item3 = types.KeyboardButton("📝 Списки обхода")
    item4 = types.KeyboardButton("📄 Информация")
    item5 = types.KeyboardButton("⚙️ Сервис")
    markup.add(item1)
    markup.add(item2, item3)
    markup.add(item4, item5)
    return markup


def _build_keys_menu_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    item1 = types.KeyboardButton("Shadowsocks")
    item2 = types.KeyboardButton("Vmess")
    item3 = types.KeyboardButton("Vless 1")
    item4 = types.KeyboardButton("Vless 2")
    item5 = types.KeyboardButton("Trojan")
    item6 = types.KeyboardButton("Где брать ключи❔")
    item7 = types.KeyboardButton("🌐 Через браузер")
    item8 = types.KeyboardButton("📦 Пул ключей")
    markup.add(item1, item2)
    markup.add(item3, item4)
    markup.add(item5)
    markup.add(item6, item8)
    markup.add(item7)
    markup.add(types.KeyboardButton("🔙 Назад"))
    return markup


def _build_service_menu_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    item1 = types.KeyboardButton("♻️ Перезагрузить сервисы")
    item2 = types.KeyboardButton("‼️Перезагрузить роутер")
    item3 = types.KeyboardButton("‼️DNS Override")
    item4 = types.KeyboardButton("📊 Статус ключей")
    back = types.KeyboardButton("🔙 Назад")
    markup.add(item1, item2)
    markup.add(item3, item4)
    markup.add(back)
    return markup


def _build_telegram_confirm_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(types.KeyboardButton("✅ Подтвердить"), types.KeyboardButton("Отмена"))
    markup.row(types.KeyboardButton("🔙 Назад"))
    return markup


def _telegram_confirm_prompt(action):
    prompts = {
        'update_main': (
            'Переустановить версию main?',
            'Код и служебные файлы будут обновлены без сброса сохраненных ключей и списков. Во время обновления бот может временно пропасть из сети.',
        ),
        'update_independent': (
            'Переустановить ветку independent?',
            'Будет установлена ветка feature/independent-rework с сохранением локальных ключей, настроек и списков.',
        ),
        'update_no_bot': (
            'Перейти в web-only?',
            'Будет установлена версия без Telegram-бота. Ключи, настройки и списки сохранятся локально, управление останется через web-интерфейс.',
        ),
        'restart_services': (
            'Перезапустить сервисы?',
            'Службы прокси и DNS будут перезапущены; соединение может кратко пропасть.',
        ),
        'reboot': (
            'Перезагрузить роутер?',
            'Связь с роутером и ботом временно пропадет примерно на 1-2 минуты.',
        ),
        'dns_on': (
            'Включить DNS Override?',
            'Роутер сохранит конфигурацию и будет перезагружен.',
        ),
        'dns_off': (
            'Выключить DNS Override?',
            'Роутер сохранит конфигурацию и будет перезагружен.',
        ),
        'remove': (
            'Удалить компоненты?',
            'Будут удалены установленные компоненты программы. Кнопка защищена от случайного нажатия.',
        ),
    }
    title, details = prompts.get(action, ('Подтвердить действие?', 'Действие изменит настройки роутера.'))
    return f'{title}\n{details}'


def _execute_confirmed_telegram_action(chat_id, action, reply_markup):
    update_actions = {
        'update_main': {
            'repo_owner': fork_repo_owner,
            'repo_name': fork_repo_name,
            'branch': 'main',
            'message': (
                f'Запускаю установку/переустановку из ветки main форка {fork_repo_owner}/{fork_repo_name} без сброса ключей и списков. '
                'Обычно это занимает 1-3 минуты. Во время обновления бот может временно пропасть из сети, '
                'потому что сервис будет перезапущен. После запуска бот сам пришлет в этот чат лог и итоговое сообщение.'
            ),
        },
        'update_independent': {
            'repo_owner': 'andruwko73',
            'repo_name': 'bypass_keenetic',
            'branch': 'feature/independent-rework',
            'message': (
                'Запускаю переустановку из ветки andruwko73/bypass_keenetic (feature/independent-rework) без сброса ключей и списков.\n'
                'Обычно это занимает 1-3 минуты. Во время обновления бот может временно пропасть из сети.\n'
                'После запуска бот сам пришлет лог и итоговое сообщение.'
            ),
        },
        'update_no_bot': {
            'repo_owner': 'andruwko73',
            'repo_name': 'bypass_keenetic',
            'branch': 'feature/web-only',
            'message': (
                'Запускаю переустановку web-only из ветки andruwko73/bypass_keenetic (feature/web-only) без сброса ключей, настроек и списков.\n'
                'После перехода Telegram-бот будет отключён. Управление останется через web-интерфейс.'
            ),
        },
    }
    if action in update_actions:
        params = update_actions[action]
        started, status_message = _start_telegram_background_command(
            '-update',
            params['repo_owner'],
            params['repo_name'],
            chat_id,
            'main',
            branch=params['branch'],
        )
        if not started:
            bot.send_message(chat_id, status_message, reply_markup=reply_markup)
            return
        bot.send_message(chat_id, params['message'], reply_markup=reply_markup)
        return
    if action == 'restart_services':
        bot.send_message(chat_id, '🔄 Выполняется перезагрузка сервисов!', reply_markup=reply_markup)
        _restart_router_services()
        _send_message_after_service_restart(chat_id, '✅ Сервисы перезагружены!', reply_markup=reply_markup)
        return
    if action == 'reboot':
        bot.send_message(chat_id, '🔄 Роутер перезагружается. Это займёт около 2 минут.', reply_markup=reply_markup)
        _schedule_router_reboot()
        return
    if action == 'dns_on':
        bot.send_message(chat_id, _set_dns_override(True), reply_markup=reply_markup)
        return
    if action == 'dns_off':
        bot.send_message(chat_id, _set_dns_override(False), reply_markup=reply_markup)
        return
    if action == 'remove':
        return_code, output = _run_script_action('-remove', fork_repo_owner, fork_repo_name)
        _send_telegram_chunks(chat_id, output, reply_markup=reply_markup)
        if return_code == 0:
            bot.send_message(chat_id, '✅ Удаление завершено.', reply_markup=reply_markup)
        else:
            bot.send_message(chat_id, '⚠️ Удаление завершилось с ошибкой. Полный лог отправлен выше.', reply_markup=reply_markup)
        return
    bot.send_message(chat_id, 'Команда не распознана.', reply_markup=reply_markup)


def _telegram_command_markup(menu_name):
    return _build_service_menu_markup() if menu_name == 'service' else _build_main_menu_markup()


def _run_telegram_command_worker(action, repo_owner, repo_name, chat_id, menu_name, branch='main'):
    try:
        return_code, output = _run_script_action(action, repo_owner, repo_name, branch=branch)
    except Exception as exc:
        return_code = 1
        output = f'Ошибка запуска фоновой команды: {exc}'
    result = {
        'action': action,
        'chat_id': int(chat_id),
        'menu_name': menu_name,
        'return_code': return_code,
        'output': output,
        'finished_at': time.time(),
    }
    _write_json_file(TELEGRAM_COMMAND_RESULT_FILE, result)
    _remove_file(TELEGRAM_COMMAND_JOB_FILE)


def _start_telegram_background_command(action, repo_owner, repo_name, chat_id, menu_name, branch='main'):
    state = _read_json_file(TELEGRAM_COMMAND_JOB_FILE, {}) or {}
    started_at = float(state.get('started_at', 0) or 0)
    if state.get('running') and started_at and time.time() - started_at < 1800:
        return False, '⏳ Уже выполняется обновление. Дождитесь итогового сообщения после перезапуска бота.'

    _write_json_file(TELEGRAM_COMMAND_JOB_FILE, {
        'running': True,
        'action': action,
        'chat_id': int(chat_id),
        'menu_name': menu_name,
        'started_at': time.time(),
    })

    module_name = os.path.splitext(os.path.basename(BOT_SOURCE_PATH))[0]
    module_dir = os.path.dirname(BOT_SOURCE_PATH)
    code = (
        'import sys; '
        f"sys.path.insert(0, {module_dir!r}); "
        f'import {module_name} as bot_module; '
        f'bot_module._run_telegram_command_worker({action!r}, {repo_owner!r}, {repo_name!r}, {int(chat_id)!r}, {menu_name!r}, branch={branch!r})'
    )
    subprocess.Popen(
        [sys.executable, '-c', code],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
    )
    return True, ''


def _deliver_pending_telegram_command_result():
    result = _read_json_file(TELEGRAM_COMMAND_RESULT_FILE)
    if not isinstance(result, dict):
        return

    chat_id = result.get('chat_id')
    if not chat_id:
        _remove_file(TELEGRAM_COMMAND_RESULT_FILE)
        return

    markup = _telegram_command_markup(result.get('menu_name', 'main'))
    action = result.get('action', '')
    return_code = int(result.get('return_code', 1))
    output = (result.get('output') or '').strip()

    try:
        if output:
            _send_telegram_chunks(chat_id, output, reply_markup=markup)
        if return_code == 0:
            final_message = '✅ Обновление завершено. Лог отправлен выше.' if action == '-update' else '✅ Команда завершена. Лог отправлен выше.'
        else:
            final_message = '⚠️ Обновление завершилось с ошибкой. Полный лог отправлен выше.' if action == '-update' else '⚠️ Команда завершилась с ошибкой. Полный лог отправлен выше.'
        bot.send_message(chat_id, final_message, reply_markup=markup)
        _remove_file(TELEGRAM_COMMAND_RESULT_FILE)
    except Exception as exc:
        _write_runtime_log(f'Не удалось доставить результат фоновой Telegram-команды: {exc}')


def _start_telegram_result_retry_worker():
    def worker():
        while not shutdown_requested.is_set():
            try:
                if os.path.exists(TELEGRAM_COMMAND_RESULT_FILE):
                    _deliver_pending_telegram_command_result()
            except Exception as exc:
                _write_runtime_log(f'Ошибка retry-доставки результата фоновой Telegram-команды: {exc}')
            shutdown_requested.wait(TELEGRAM_RESULT_RETRY_INTERVAL)

    threading.Thread(target=worker, daemon=True).start()


def _install_proxy_from_message(message, key_type, key_value, reply_markup):
    installers = {
        'shadowsocks': shadowsocks,
        'vmess': vmess,
        'vless': vless,
        'vless2': vless2,
        'trojan': trojan,
    }
    try:
        installers[key_type](key_value)
        result = _apply_installed_proxy(key_type, key_value)
    except Exception as exc:
        result = f'Ошибка установки: {exc}'

    level_reset_markup = reply_markup
    try:
        bot.send_message(message.chat.id, result, reply_markup=level_reset_markup)
    except Exception:
        fallback_result = (
            f'{result}\n\n'
            'Текущий режим бота сохранён, но отправить подтверждение в этот чат не удалось.'
        )
        try:
            bot.send_message(message.chat.id, fallback_result, reply_markup=level_reset_markup)
        except Exception:
            pass
    return result


def _download_repo_file_text(session, repo_owner, repo_name, repo_ref, path):
    headers = {'Cache-Control': 'no-cache', 'Pragma': 'no-cache'}
    raw_url = f'https://raw.githubusercontent.com/{repo_owner}/{repo_name}/{repo_ref}/{path}'
    try:
        response = session.get(raw_url, headers=headers, timeout=(10, 30))
        response.raise_for_status()
        return raw_url, response.text
    except requests.RequestException:
        pass

    api_url = f'https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{quote(path, safe="/")}'
    response = session.get(
        api_url,
        params={'ref': repo_ref},
        headers={'Accept': 'application/vnd.github+json', **headers},
        timeout=(10, 30),
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get('encoding') != 'base64' or 'content' not in payload:
        raise ValueError('GitHub contents API returned unexpected file payload')
    content = ''.join(str(payload.get('content', '')).split())
    return response.url, base64.b64decode(content).decode('utf-8')


def _download_repo_script(repo_owner, repo_name, branch='main'):
    session = requests.Session()
    session.trust_env = False
    api_url = f'https://api.github.com/repos/{repo_owner}/{repo_name}/commits/{quote(branch, safe="")}'
    api_response = session.get(
        api_url,
        headers={'Accept': 'application/vnd.github+json', 'Cache-Control': 'no-cache', 'Pragma': 'no-cache'},
        timeout=(10, 30),
    )
    api_response.raise_for_status()
    repo_ref = str(api_response.json().get('sha', '')).strip()
    if not repo_ref:
        raise ValueError('GitHub не вернул commit SHA для script.sh')

    url, script_text = _download_repo_file_text(session, repo_owner, repo_name, repo_ref, 'script.sh')
    if '#!/bin/sh' not in script_text:
        raise ValueError('GitHub вернул некорректный script.sh')
    with open('/opt/root/script.sh', 'w', encoding='utf-8') as file:
        file.write(script_text)
    os.chmod('/opt/root/script.sh', stat.S_IRWXU)
    return url, script_text, repo_ref


def _download_repo_file_from_archive(session, repo_owner, repo_name, repo_ref, path):
    archive_ref = repo_ref if '/' not in repo_ref else f'refs/heads/{repo_ref}'
    archive_url = f'https://codeload.github.com/{repo_owner}/{repo_name}/tar.gz/{archive_ref}'
    suffix = '/' + path.strip('/')
    with session.get(archive_url, stream=True, timeout=(10, 90)) as response:
        response.raise_for_status()
        response.raw.decode_content = True
        with tarfile.open(fileobj=response.raw, mode='r|gz') as archive:
            for member in archive:
                if member.isfile() and member.name.endswith(suffix):
                    extracted = archive.extractfile(member)
                    if extracted is not None:
                        return archive_url, extracted.read().decode('utf-8')
    raise ValueError(f'GitHub archive did not contain {path}')


def _download_repo_file_text(session, repo_owner, repo_name, repo_ref, path):
    headers = {'Cache-Control': 'no-cache', 'Pragma': 'no-cache'}
    raw_url = f'https://raw.githubusercontent.com/{repo_owner}/{repo_name}/{repo_ref}/{path}'
    try:
        response = session.get(raw_url, headers=headers, timeout=(5, 8))
        response.raise_for_status()
        return raw_url, response.text
    except requests.RequestException:
        pass

    try:
        return _download_repo_file_from_archive(session, repo_owner, repo_name, repo_ref, path)
    except Exception:
        pass

    api_url = f'https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{quote(path, safe="/")}'
    response = session.get(
        api_url,
        params={'ref': repo_ref},
        headers={'Accept': 'application/vnd.github+json', **headers},
        timeout=(10, 30),
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get('encoding') != 'base64' or 'content' not in payload:
        raise ValueError('GitHub contents API returned unexpected file payload')
    content = ''.join(str(payload.get('content', '')).split())
    return response.url, base64.b64decode(content).decode('utf-8')


def _download_repo_script(repo_owner, repo_name, branch='main'):
    session = requests.Session()
    session.trust_env = False
    url, script_text = _download_repo_file_text(session, repo_owner, repo_name, branch, 'script.sh')
    if '#!/bin/sh' not in script_text:
        raise ValueError('GitHub returned invalid script.sh')
    with open('/opt/root/script.sh', 'w', encoding='utf-8') as file:
        file.write(script_text)
    os.chmod('/opt/root/script.sh', stat.S_IRWXU)
    return url, script_text, branch


def _build_direct_fetch_env():
    env = os.environ.copy()
    for key in DIRECT_FETCH_ENV_KEYS:
        env.pop(key, None)
    return env


def _run_script_action(action, repo_owner=None, repo_name=None, progress_command=None, branch='main'):
    logs = [_prepare_entware_dns(), _ensure_legacy_bot_paths()]
    direct_env = _build_direct_fetch_env()
    if progress_command:
        _set_web_command_progress(progress_command, '\n'.join(logs))
    if repo_owner and repo_name:
        url, script_text, repo_ref = _download_repo_script(repo_owner, repo_name, branch=branch)
        direct_env['REPO_REF'] = branch
        logs.append(f'Скрипт загружен из {url}')
        logs.append(f'Коммит обновления: {repo_ref[:12]}')
        if repo_owner == fork_repo_owner and 'BOT_CONFIG_PATH' not in script_text:
            logs.append('⚠️ GitHub отдал старую версию script.sh, но legacy-пути уже подготовлены на роутере.')
        if progress_command:
            _set_web_command_progress(progress_command, '\n'.join(logs))
        with open('/opt/root/script.sh', 'w', encoding='utf-8') as file:
            file.write(script_text)
        os.chmod('/opt/root/script.sh', stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)

    process = subprocess.Popen(
        ['/bin/sh', '/opt/root/script.sh', action],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=direct_env,
    )
    for line in process.stdout:
        clean_line = line.strip()
        if clean_line:
            logs.append(clean_line)
            if progress_command:
                _set_web_command_progress(progress_command, '\n'.join(logs))
    return_code = process.wait()
    if return_code != 0:
        logs.append(f'Команда завершилась с кодом {return_code}.')
    return return_code, '\n'.join(logs)


def _restart_router_services():
    commands = [
        '/opt/etc/init.d/S56dnsmasq restart',
        '/opt/etc/init.d/S22shadowsocks restart',
        CORE_PROXY_SERVICE_SCRIPT + ' restart',
        '/opt/etc/init.d/S22trojan restart',
    ]
    for command in commands:
        os.system(command)
    _invalidate_web_status_cache()
    return '✅ Сервисы перезагружены.'


def _send_message_after_service_restart(chat_id, text, reply_markup=None):
    active_mode = _load_proxy_mode()
    if active_mode in proxy_settings:
        update_proxy(active_mode)
    proxy_url = proxy_settings.get(active_mode)
    port = None
    if proxy_url:
        match = re.search(r':(\d+)$', proxy_url)
        if match:
            port = match.group(1)
    if port:
        for _ in range(12):
            if _check_socks5_handshake(port):
                break
            time.sleep(1)
    for _ in range(3):
        try:
            bot.send_message(chat_id, text, reply_markup=reply_markup)
            return True
        except Exception as exc:
            _write_runtime_log(f'Не удалось отправить Telegram-сообщение после перезапуска сервисов: {exc}')
            time.sleep(2)
    try:
        previous_mode = proxy_mode
        update_proxy('none')
        bot.send_message(chat_id, text, reply_markup=reply_markup)
        if previous_mode in proxy_settings:
            update_proxy(previous_mode)
        return True
    except Exception as exc:
        _write_runtime_log(f'Не удалось отправить Telegram-сообщение после перезапуска сервисов напрямую: {exc}')
        if active_mode in proxy_settings:
            update_proxy(active_mode)
        return False


def _schedule_router_reboot(delay_seconds=5):
    delay = max(1, int(delay_seconds))
    subprocess.Popen(
        ['/bin/sh', '-c', f'sleep {delay}; ndmc -c "system reboot" >/dev/null 2>&1'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
    )


def _set_dns_override(enabled):
    _save_bot_autostart(True)
    if enabled:
        os.system("ndmc -c 'opkg dns-override'")
        time.sleep(2)
        os.system("ndmc -c 'system configuration save'")
        _schedule_router_reboot()
        return '✅ DNS Override включен. Роутер будет автоматически перезагружен через несколько секунд.'
    os.system("ndmc -c 'no opkg dns-override'")
    time.sleep(2)
    os.system("ndmc -c 'system configuration save'")
    _schedule_router_reboot()
    return '✅ DNS Override выключен. Роутер будет автоматически перезагружен через несколько секунд.'


def _dns_override_enabled():
    try:
        result = subprocess.run(
            ['ndmc', '-c', 'show running-config'],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        return 'opkg dns-override' in (result.stdout or '')
    except Exception:
        return False


def _run_web_command(command):
    if command == 'install_original':
        _, output = _run_script_action('-install', 'tas-unn', 'bypass_keenetic')
        return output
    if command == 'update':
        _, output = _run_script_action('-update', fork_repo_owner, fork_repo_name, progress_command='update')
        return output
    if command == 'update_independent':
        _, output = _run_script_action(
            '-update',
            'andruwko73',
            'bypass_keenetic',
            progress_command='update_independent',
            branch='feature/independent-rework',
        )
        return output
    if command == 'update_no_bot':
        _, output = _run_script_action(
            '-update',
            'andruwko73',
            'bypass_keenetic',
            progress_command='update_no_bot',
            branch='feature/web-only',
        )
        return output
    if command == 'remove':
        _, output = _run_script_action('-remove', fork_repo_owner, fork_repo_name)
        return output
    if command == 'restart_services':
        return _restart_router_services()
    if command == 'dns_on':
        return _set_dns_override(True)
    if command == 'dns_off':
        return _set_dns_override(False)
    if command == 'reboot':
        os.system('ndmc -c system reboot')
        return '🔄 Роутер перезагружается. Это займёт около 2 минут.'
    return 'Команда не распознана.'


def _read_text_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
            return file.read()
    except Exception:
        return ''


def _current_bot_version():
    source_text = _read_text_file(BOT_SOURCE_PATH)
    match = re.search(r'^#\s*ВЕРСИЯ СКРИПТА\s+(.+?)\s*$', source_text, flags=re.MULTILINE)
    if match:
        return match.group(1).strip()
    match = re.search(r'Версия\s+([0-9][0-9.]*)', source_text)
    if match:
        return match.group(1).strip()
    for line in source_text.splitlines():
        if line.startswith('# ВЕРСИЯ СКРИПТА'):
            return line.replace('# ВЕРСИЯ СКРИПТА', '').strip()
    return 'неизвестна'


def _normalize_unblock_list(text):
    items = []
    seen = set()
    for raw_line in text.replace('\r', '\n').split('\n'):
        line = raw_line.strip()
        if not line or line in seen:
            continue
        seen.add(line)
        items.append(line)
    items.sort()
    return '\n'.join(items)


def _save_unblock_list(list_name, text):
    safe_name = os.path.basename(list_name)
    target_path = os.path.join('/opt/etc/unblock', safe_name)
    if not target_path.endswith('.txt'):
        raise ValueError('Список должен быть .txt файлом')
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    normalized = _normalize_unblock_list(text)
    with open(target_path, 'w', encoding='utf-8') as file:
        if normalized:
            file.write(normalized + '\n')
    subprocess.run(['/opt/bin/unblock_update.sh'], check=False)
    return f'✅ Список {safe_name} сохранён и применён.'


def _append_socialnet_list(list_name, service_key=SOCIALNET_ALL_KEY):
    return _apply_socialnet_list(list_name, service_key=service_key, remove=False)


def _remove_socialnet_list(list_name, service_key=SOCIALNET_ALL_KEY):
    return _apply_socialnet_list(list_name, service_key=service_key, remove=True)


def _list_label(file_name):
    base = file_name[:-4] if file_name.endswith('.txt') else file_name
    labels = {
        'shadowsocks': 'Shadowsocks',
        'vmess': 'Vmess',
        'vless': 'Vless 1',
        'vless-2': 'Vless 2',
        'trojan': 'Trojan',
    }
    return labels.get(base, base)


def _load_unblock_lists(with_content=True):
    unblock_dir = '/opt/etc/unblock'
    try:
        file_names = sorted(name for name in os.listdir(unblock_dir) if name.endswith('.txt'))
    except Exception:
        file_names = []
    file_names = [name for name in file_names if name not in ['vpn.txt', 'tor.txt'] and not name.startswith('vpn-')]
    preferred_order = ['vless.txt', 'vless-2.txt', 'vmess.txt', 'trojan.txt', 'shadowsocks.txt']
    ordered = []
    for item in preferred_order:
        if item in file_names:
            ordered.append(item)
    for item in file_names:
        if item not in ordered:
            ordered.append(item)
    result = []
    for file_name in ordered:
        entry = {
            'name': file_name,
            'label': _list_label(file_name),
        }
        if with_content:
            entry['content'] = _read_text_file(os.path.join(unblock_dir, file_name)).strip()
        result.append(entry)
    return result


def _telegram_unblock_list_options():
    return [(entry['label'], entry['name'][:-4]) for entry in _load_unblock_lists(with_content=False)]


def _resolve_unblock_list_selection(text):
    normalized = text.strip()
    for label, base_name in _telegram_unblock_list_options():
        if normalized in [label, base_name]:
            return base_name
    return normalized


def _transparent_list_route_label():
    config_text = _read_text_file(CORE_PROXY_CONFIG_PATH)
    has_vless_1 = 'in-vless-transparent' in config_text and 'proxy-vless' in config_text
    has_vless_2 = 'in-vless2-transparent' in config_text and 'proxy-vless2' in config_text
    if has_vless_1 and has_vless_2:
        return 'Vless 1 / Vless 2'
    if has_vless_1:
        return 'Vless 1'
    if has_vless_2:
        return 'Vless 2'
    return 'Не определён'


def _load_shadowsocks_key():
    try:
        with open('/opt/etc/shadowsocks.json', 'r', encoding='utf-8') as file:
            data = json.load(file)
        raw_uri = str(data.get('raw_uri', '') or '').strip()
        if raw_uri.startswith('ss://'):
            return raw_uri
        server = (data.get('server') or [''])[0]
        port = data.get('server_port', '')
        method = data.get('method', '')
        password = data.get('password', '')
        if not server or not port or not method:
            return ''
        encoded = base64.urlsafe_b64encode(f'{method}:{password}'.encode('utf-8')).decode('utf-8').rstrip('=')
        return f'ss://{encoded}@{server}:{port}'
    except Exception:
        return ''


def _load_trojan_key():
    try:
        with open('/opt/etc/trojan/config.json', 'r', encoding='utf-8') as file:
            data = json.load(file)
        raw_uri = str(data.get('raw_uri', '') or '').strip()
        if raw_uri.startswith('trojan://'):
            return raw_uri
        password = (data.get('password') or [''])[0]
        address = data.get('remote_addr', '')
        port = data.get('remote_port', '')
        if (
            str(address).strip().lower() == 'ownade' and
            str(port).strip() == '65432' and
            str(password).strip() == 'pw'
        ):
            return ''
        if not password or not address or not port:
            return ''
        query_params = []
        trojan_type = str(data.get('type', '') or '').strip()
        if trojan_type and trojan_type != 'tcp':
            query_params.append(('type', trojan_type))

        security = str(data.get('security', '') or '').strip()
        if security and security != 'tls':
            query_params.append(('security', security))

        sni = str(data.get('sni', '') or '').strip()
        if sni:
            query_params.append(('sni', sni))

        host = str(data.get('host', '') or '').strip()
        if host:
            query_params.append(('host', host))

        path = str(data.get('path', '') or '').strip()
        if path and path != '/':
            query_params.append(('path', path))

        service_name = str(data.get('serviceName', '') or '').strip()
        if service_name:
            query_params.append(('serviceName', service_name))

        fingerprint = str(data.get('fingerprint', '') or '').strip()
        if fingerprint and fingerprint != 'chrome':
            query_params.append(('fp', fingerprint))

        alpn = str(data.get('alpn', '') or '').strip()
        if alpn:
            query_params.append(('alpn', alpn))

        query_suffix = ''
        if query_params:
            query_suffix = '?' + urlencode(query_params)

        fragment = str(data.get('fragment', '') or '').strip()
        fragment_suffix = f'#{quote(fragment)}' if fragment else ''

        return f'trojan://{password}@{address}:{port}{query_suffix}{fragment_suffix}'
    except Exception:
        return ''


def _load_current_keys():
    return {
        'shadowsocks': _load_shadowsocks_key(),
        'vmess': _read_v2ray_key(VMESS_KEY_PATH) or '',
        'vless': _read_v2ray_key(VLESS_KEY_PATH) or '',
        'vless2': _read_v2ray_key(VLESS2_KEY_PATH) or '',
        'trojan': _load_trojan_key(),
    }


def _ensure_current_keys_in_pools(current_keys=None):
    current_keys = current_keys if current_keys is not None else _load_current_keys()
    pools = _load_key_pools()
    changed = False
    for proto in ['shadowsocks', 'vmess', 'vless', 'vless2', 'trojan']:
        key_value = (current_keys.get(proto) or '').strip()
        keys = _dedupe_key_list(pools.get(proto, []) or [])
        original_keys = list(keys)
        if key_value:
            keys = [candidate for candidate in keys if candidate != key_value]
            keys.insert(0, key_value)
        pools[proto] = keys
        if keys == original_keys:
            continue
        changed = True
    if changed:
        _save_key_pools(pools)
    return pools


def _invalidate_status_snapshot_cache():
    status_snapshot_cache['timestamp'] = 0
    status_snapshot_cache['data'] = None
    status_snapshot_cache['signature'] = None


def _invalidate_key_status_cache():
    _invalidate_status_snapshot_cache()


def _check_http_through_proxy(proxy_url, url='https://www.youtube.com', connect_timeout=2, read_timeout=3):
    try:
        response = requests.get(
            url,
            timeout=(connect_timeout, read_timeout),
            proxies={'https': proxy_url, 'http': proxy_url},
            stream=True,
        )
        status_code = response.status_code
        response.close()
        if status_code < 500:
            return True, f'Веб-доступ через ключ подтверждён (HTTP {status_code}).'
        return False, f'Веб-проверка через ключ вернула HTTP {status_code}.'
    except requests.exceptions.ConnectTimeout:
        return False, 'Прокси не установил соединение за отведённое время.'
    except requests.exceptions.ReadTimeout:
        return False, 'Удалённый сервер не ответил вовремя через этот ключ.'
    except requests.exceptions.RequestException as exc:
        return False, f'Веб-проверка через ключ завершилась ошибкой: {exc}'


def _check_custom_target_through_proxy(proxy_url, url, connect_timeout=2, read_timeout=3):
    try:
        target_url = _normalize_check_url(url)
        response = requests.get(
            target_url,
            timeout=(connect_timeout, read_timeout),
            proxies={'https': proxy_url, 'http': proxy_url},
            headers={'User-Agent': 'bypass_keenetic health check'},
            stream=True,
        )
        status_code = response.status_code
        response.close()
        if status_code < 500:
            return True, f'Доступ к {urlparse(target_url).netloc} подтверждён (HTTP {status_code}).'
        return False, f'{urlparse(target_url).netloc} вернул HTTP {status_code}.'
    except ValueError as exc:
        return False, str(exc)
    except requests.exceptions.ConnectTimeout:
        return False, 'Прокси не установил соединение за отведённое время.'
    except requests.exceptions.ReadTimeout:
        return False, 'Сервис не ответил вовремя через этот ключ.'
    except requests.exceptions.RequestException as exc:
        return False, f'Проверка сервиса завершилась ошибкой: {str(exc).splitlines()[0][:180]}'


def _probe_custom_targets(proxy_url, custom_checks=None, connect_timeout=2, read_timeout=3):
    results = {}
    for check in (custom_checks if custom_checks is not None else _load_custom_checks()):
        check_id = check.get('id')
        if not check_id:
            continue
        targets = check.get('urls') if isinstance(check.get('urls'), list) else [check.get('url', '')]
        target_results = []
        for target in targets:
            ok, _ = _check_custom_target_through_proxy(
                proxy_url,
                target,
                connect_timeout=connect_timeout,
                read_timeout=read_timeout,
            )
            target_results.append(ok)
        results[check_id] = bool(target_results) and all(target_results)
    return results


def _check_telegram_api_through_proxy(proxy_url=None, connect_timeout=6, read_timeout=10):
    url = 'https://api.telegram.org/'
    proxies = {'https': proxy_url, 'http': proxy_url} if proxy_url else None
    try:
        response = requests.get(url, timeout=(connect_timeout, read_timeout), proxies=proxies)
        if response.status_code < 500:
            return True, 'Доступ к api.telegram.org подтверждён.'
        return False, f'Telegram API вернул HTTP {response.status_code}.'
    except requests.exceptions.ConnectTimeout:
        return False, 'Прокси не установил соединение с api.telegram.org за отведённое время.'
    except requests.exceptions.ReadTimeout:
        return False, 'Сервер Telegram не ответил вовремя через этот ключ.'
    except requests.exceptions.RequestException as exc:
        error_text = str(exc)
        if 'Missing dependencies for SOCKS support' in error_text:
            return False, 'Отсутствует поддержка SOCKS (PySocks) для проверки Telegram API.'
        if 'SSLEOFError' in error_text or 'UNEXPECTED_EOF' in error_text:
            return False, 'Прокси-сервер разорвал TLS-соединение с api.telegram.org. Обычно это означает нерабочий ключ или проблему на удалённом сервере.'
        if 'Connection refused' in error_text:
            return False, 'Локальный SOCKS-порт отклонил соединение.'
        if 'RemoteDisconnected' in error_text:
            return False, 'Удалённая сторона закрыла соединение без ответа.'
        return False, f'Проверка Telegram API завершилась ошибкой: {error_text.splitlines()[0][:240]}'


def _key_requires_xray(key_name, key_value):
    if key_name not in ['vless', 'vless2']:
        return False
    try:
        parsed = _parse_vless_key(key_value)
    except Exception:
        return False
    security = (parsed.get('security') or '').strip().lower()
    flow = (parsed.get('flow') or '').strip().lower()
    return security == 'reality' or flow == 'xtls-rprx-vision'


def _core_proxy_runtime_name():
    if os.path.exists(XRAY_SERVICE_SCRIPT):
        return 'xray'
    return 'v2ray'


def _protocol_status_for_key(key_name, key_value):
    now = time.time()
    if not key_value.strip():
        return {
            'tone': 'empty',
            'label': 'Не сохранён',
            'details': 'Ключ ещё не сохранён на роутере.',
        }
    ports = {
        'shadowsocks': localportsh_bot,
        'vmess': localportvmess,
        'vless': localportvless,
        'vless2': localportvless2,
        'trojan': localporttrojan_bot,
    }
    port = ports.get(key_name)
    endpoint_ok, endpoint_message = _check_local_proxy_endpoint(key_name, port)
    if not endpoint_ok:
        return {
            'tone': 'fail',
            'label': 'Не работает',
            'details': f'{endpoint_message} Бот не может использовать этот ключ.',
        }

    if _key_requires_xray(key_name, key_value) and _core_proxy_runtime_name() != 'xray':
        return {
            'tone': 'warn',
            'label': 'Требует Xray',
            'details': (f'{endpoint_message} Этот ключ использует VLESS Reality/XTLS и должен работать через Xray, '
                        'а сейчас активен V2Ray. Локальный SOCKS поднят, но внешний трафик через ключ может не пройти.'),
        }

    proxy_url = proxy_settings.get(key_name)
    api_ok, api_message = _check_telegram_api_through_proxy(
        proxy_url,
        connect_timeout=5,
        read_timeout=8,
    )
    api_transient = (not api_ok) and _is_transient_telegram_api_failure(api_message)
    yt_ok, yt_message = _check_http_through_proxy(
        proxy_url,
        url='https://www.youtube.com',
        connect_timeout=2,
        read_timeout=3,
    )
    custom_checks = _load_custom_checks()
    cached_probe = _load_key_probe_cache().get(_hash_key(key_value), {})
    custom_states = _web_custom_probe_states(cached_probe, custom_checks)
    if api_transient:
        _record_key_probe(key_name, key_value, yt_ok=yt_ok)
    else:
        _record_key_probe(key_name, key_value, tg_ok=api_ok, yt_ok=yt_ok)
    custom_ok = any(state == 'ok' for state in custom_states.values())
    any_ok = api_ok or yt_ok or custom_ok
    service_parts = [
        f'Telegram: {"работает" if api_ok else ("перепроверяется" if api_transient else "не работает")}',
        f'YouTube: {"работает" if yt_ok else "не работает"}',
    ]
    for check in custom_checks:
        check_id = check.get('id')
        state = custom_states.get(check_id)
        if state in ('ok', 'fail'):
            service_parts.append(f'{check.get("label", "Сервис")}: {"работает" if state == "ok" else "не работает"}')
    details = f'Показан результат проверки активного ключа. {endpoint_message} ' + ', '.join(service_parts) + '.'
    if endpoint_ok and api_transient:
        return {
            'tone': 'warn',
            'label': 'Проверяется',
            'details': (f'{endpoint_message} Telegram API не ответил вовремя, идёт повторная проверка. '
                        'Статус обновится без перезагрузки страницы.').strip(),
            'endpoint_ok': endpoint_ok,
            'endpoint_message': endpoint_message,
            'api_ok': False,
            'api_message': api_message,
            'api_pending': True,
            'yt_ok': yt_ok,
            'yt_message': yt_message,
            'custom': custom_states,
        }
    return {
        'tone': 'ok' if api_ok else ('warn' if any_ok else 'fail'),
        'label': 'Работает' if api_ok else ('Частично работает' if any_ok else 'Не работает'),
        'details': details.strip(),
        'endpoint_ok': endpoint_ok,
        'endpoint_message': endpoint_message,
        'api_ok': api_ok,
        'api_message': api_message,
        'yt_ok': yt_ok,
        'yt_message': yt_message,
        'custom': custom_states,
    }


def _cached_protocol_status_for_key(key_name, key_value, custom_checks=None):
    if not key_value.strip():
        return {
            'tone': 'empty',
            'label': 'Не сохранён',
            'details': 'Ключ ещё не сохранён на роутере.',
        }
    custom_checks = custom_checks if custom_checks is not None else _load_custom_checks()
    probe = _load_key_probe_cache().get(_hash_key(key_value), {})
    custom_states = _web_custom_probe_states(probe, custom_checks)
    has_probe_result = (
        'tg_ok' in probe or
        'yt_ok' in probe or
        any(state in ('ok', 'fail') for state in custom_states.values())
    )
    if has_probe_result:
        api_ok = bool(probe.get('tg_ok')) if 'tg_ok' in probe else False
        yt_ok = bool(probe.get('yt_ok')) if 'yt_ok' in probe else False
        custom_ok = any(state == 'ok' for state in custom_states.values())
        any_ok = api_ok or yt_ok or custom_ok
        service_parts = []
        if 'tg_ok' in probe:
            service_parts.append(f'Telegram: {"работает" if api_ok else "не работает"}')
        if 'yt_ok' in probe:
            service_parts.append(f'YouTube: {"работает" if yt_ok else "не работает"}')
        for check in custom_checks:
            check_id = check.get('id')
            state = custom_states.get(check_id)
            if state in ('ok', 'fail'):
                service_parts.append(f'{check.get("label", "Сервис")}: {"работает" if state == "ok" else "не работает"}')
        details = 'Показан последний результат проверки пула.'
        if service_parts:
            details += ' ' + ', '.join(service_parts) + '.'
        return {
            'tone': 'ok' if api_ok else ('warn' if any_ok else 'fail'),
            'label': 'Работает' if api_ok else ('Частично работает' if any_ok else 'Не работает'),
            'details': details,
            'endpoint_ok': None,
            'endpoint_message': '',
            'api_ok': api_ok,
            'api_message': '',
            'yt_ok': yt_ok,
            'yt_message': '',
            'custom': custom_states,
        }
    return {
        'tone': 'warn',
        'label': 'Не проверялся',
        'details': 'Ключ ждёт фоновой проверки. Чтобы не перегружать роутер, ключи проверяются по одному.',
        'endpoint_ok': None,
        'endpoint_message': '',
        'api_ok': False,
        'api_message': '',
        'yt_ok': False,
        'yt_message': '',
        'custom': custom_states,
    }


def _placeholder_protocol_statuses(current_keys):
    result = {}
    for key_name, key_value in current_keys.items():
        if key_value.strip():
            result[key_name] = {
                'tone': 'warn',
                'label': 'Проверяется',
                'details': 'Фоновая проверка ключа выполняется. Статус обновится без перезагрузки страницы.',
            }
        else:
            result[key_name] = {
                'tone': 'empty',
                'label': 'Не сохранён',
                'details': 'Ключ ещё не сохранён на роутере.',
            }
    return result


def _web_command_label(command):
    labels = {
        'install_original': 'Установить оригинальную версию',
        'update': 'Переустановить из форка без сброса',
        'update_independent': 'Переустановка (ветка independent)',
        'update_no_bot': 'Переустановка (без Telegram бота)',
        'remove': 'Удалить компоненты',
        'restart_services': 'Перезапустить сервисы',
        'dns_on': 'DNS Override ВКЛ',
        'dns_off': 'DNS Override ВЫКЛ',
        'reboot': 'Перезагрузить роутер',
    }
    return labels.get(command, command)


def _get_web_command_state():
    with web_command_lock:
        return dict(web_command_state)


def _consume_web_command_state_for_render():
    with web_command_lock:
        snapshot = dict(web_command_state)
        if (snapshot.get('label') and not snapshot.get('running') and
                snapshot.get('finished_at') and snapshot.get('shown_after_finish')):
            cleared = {
                'running': False,
                'command': '',
                'label': '',
                'result': '',
                'progress': 0,
                'progress_label': '',
                'started_at': 0,
                'finished_at': 0,
                'shown_after_finish': False,
            }
            web_command_state.update(cleared)
            return cleared
        elif snapshot.get('label') and not snapshot.get('running') and snapshot.get('finished_at'):
            web_command_state['shown_after_finish'] = True
        return snapshot


def _estimate_web_command_progress(command, result_text):
    if command not in ('update', 'update_independent', 'update_no_bot'):
        return 0, ''
    if not result_text:
        return 5, 'Подготовка запуска обновления'

    progress_steps = [
        ('Бот запущен.', 100, 'Бот перезапущен, обновление завершено'),
        ('Обновление выполнено. Сервисы перезапущены.', 96, 'Сервисы обновлены, идёт перезапуск бота'),
        ('Версия бота', 90, 'Проверка версии и завершение обновления'),
        ('Обновления скачены, права настроены.', 82, 'Новые файлы установлены'),
        ('Бэкап создан.', 70, 'Резервная копия готова, идёт замена файлов'),
        ('Сервисы остановлены.', 60, 'Сервисы остановлены перед заменой файлов'),
        ('Файлы успешно скачаны и подготовлены.', 45, 'Файлы загружены, подготавливается установка'),
        ('Скачиваем обновления во временную папку и проверяем файлы.', 30, 'Идёт загрузка файлов из GitHub'),
        ('Пакеты обновлены.', 20, 'Пакеты Entware обновлены'),
        ('Начинаем обновление.', 12, 'Запущен сценарий обновления'),
        ('Скрипт загружен из', 8, 'Сценарий обновления получен с GitHub'),
        ('Legacy-пути бота уже доступны.', 6, 'Проверка путей запуска бота'),
        ('Подготовка legacy-путей:', 6, 'Подготовка путей запуска бота'),
        ('Подготовка Entware DNS:', 4, 'Проверка доступа Entware и GitHub'),
    ]
    for marker, percent, label in progress_steps:
        if marker in result_text:
            return percent, label
    return 8, 'Обновление запущено'


def _set_web_command_progress(command, result_text):
    progress, progress_label = _estimate_web_command_progress(command, result_text)
    with web_command_lock:
        web_command_state['result'] = result_text
        web_command_state['progress'] = progress
        web_command_state['progress_label'] = progress_label
        web_command_state['shown_after_finish'] = False


def _set_web_flash_message(message):
    global web_flash_message
    with web_flash_lock:
        web_flash_message = message or ''


def _consume_web_flash_message():
    global web_flash_message
    with web_flash_lock:
        message = web_flash_message
        web_flash_message = ''
    return message


def _finish_web_command(command, result):
    with web_command_lock:
        web_command_state['running'] = False
        web_command_state['command'] = command
        web_command_state['label'] = _web_command_label(command)
        web_command_state['result'] = result
        web_command_state['progress'] = 100 if command in ('update', 'update_independent', 'update_no_bot') else web_command_state.get('progress', 0)
        web_command_state['progress_label'] = 'Завершено' if command in ('update', 'update_independent', 'update_no_bot') else ''
        web_command_state['finished_at'] = time.time()
        web_command_state['shown_after_finish'] = False


def _execute_web_command(command):
    try:
        result = _run_web_command(command)
    except Exception as exc:
        result = f'Ошибка выполнения команды: {exc}'
    _finish_web_command(command, result)


def _start_web_command(command):
    label = _web_command_label(command)
    with web_command_lock:
        if web_command_state['running']:
            current_label = web_command_state['label'] or web_command_state['command']
            return False, f'⏳ Уже выполняется команда: {current_label}. Дождитесь завершения текущего запуска.'
        web_command_state['running'] = True
        web_command_state['command'] = command
        web_command_state['label'] = label
        web_command_state['result'] = ''
        web_command_state['progress'] = 5 if command in ('update', 'update_independent', 'update_no_bot') else 0
        web_command_state['progress_label'] = 'Подготовка запуска обновления' if command in ('update', 'update_independent', 'update_no_bot') else ''
        web_command_state['started_at'] = time.time()
        web_command_state['finished_at'] = 0
        web_command_state['shown_after_finish'] = False
    thread = threading.Thread(target=_execute_web_command, args=(command,), daemon=True)
    thread.start()
    return True, f'⏳ Команда "{label}" запущена. Статус обновится без перезагрузки страницы.'


def _load_bot_autostart():
    try:
        with open(BOT_AUTOSTART_FILE, 'r', encoding='utf-8') as file:
            return file.read().strip() == '1'
    except Exception:
        return False


def _invalidate_web_status_cache():
    _invalidate_status_snapshot_cache()


def _last_proxy_disable_reason():
    try:
        for log_path in RUNTIME_ERROR_LOG_PATHS:
            if not os.path.exists(log_path):
                continue
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as file:
                lines = file.readlines()
            for line in reversed(lines[-80:]):
                marker = 'Прокси-режим '
                if marker not in line or ' отключён при старте: ' not in line:
                    continue
                tail = line.split(' отключён при старте: ', 1)[1].strip()
                return tail
    except Exception:
        return ''
    return ''


def _load_proxy_mode():
    try:
        with open(PROXY_MODE_FILE, 'r', encoding='utf-8') as file:
            saved = file.read().strip()
        if saved in proxy_settings:
            return saved
    except Exception:
        pass
    return config.default_proxy_mode


def _wait_for_port(hosts, port, timeout=15):
    import socket
    if hosts is None:
        hosts = ['127.0.0.1', '::1', 'localhost']
    elif isinstance(hosts, str):
        hosts = [hosts]
    deadline = time.time() + timeout
    while time.time() < deadline:
        for host in hosts:
            try:
                addrs = socket.getaddrinfo(host, int(port), type=socket.SOCK_STREAM)
            except OSError:
                continue
            for family, socktype, proto, canonname, sockaddr in addrs:
                try:
                    with socket.socket(family, socktype, proto) as sock:
                        sock.settimeout(2)
                        sock.connect(sockaddr)
                        return True
                except OSError:
                    continue
        time.sleep(1)
    return False


def _port_is_listening(port):
    try:
        output = subprocess.check_output(['netstat', '-ltn'], stderr=subprocess.DEVNULL, text=True)
        for line in output.splitlines():
            if f':{port} ' in line or line.endswith(f':{port}'):
                return True
    except Exception:
        pass
    try:
        output = subprocess.check_output(['ss', '-ltn'], stderr=subprocess.DEVNULL, text=True)
        for line in output.splitlines():
            if f':{port} ' in line or line.endswith(f':{port}'):
                return True
    except Exception:
        pass
    return False

def _check_socks5_handshake(port, timeout=3):
    import socket
    try:
        with socket.create_connection(('127.0.0.1', int(port)), timeout=timeout) as sock:
            sock.sendall(b'\x05\x01\x00')
            data = sock.recv(2)
            return data == b'\x05\x00'
    except Exception:
        return False


def _wait_for_socks5_handshake(port, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _check_socks5_handshake(port):
            return True
        time.sleep(1)
    return False


def _ensure_service_port(port, restart_cmd=None, retries=2, sleep_after_restart=5, timeout=20):
    if _wait_for_port(None, port, timeout=timeout):
        return True
    if _port_is_listening(port):
        return True
    if restart_cmd:
        for _ in range(retries):
            os.system(restart_cmd)
            time.sleep(sleep_after_restart)
            if _wait_for_port(None, port, timeout=timeout):
                return True
            if _port_is_listening(port):
                return True
    return False


def _read_tail(file_path, lines=12):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
            content = file.readlines()
        if not content:
            return ''
        return ''.join(content[-lines:]).strip()
    except Exception as exc:
        return f'Не удалось прочитать {file_path}: {exc}'


def _v2ray_diagnostics():
    config_path = CORE_PROXY_CONFIG_PATH
    error_path = CORE_PROXY_ERROR_LOG
    diagnostics = []
    if not os.path.exists(config_path):
        diagnostics.append(f'Конфигурация v2ray не найдена: {config_path}')
    else:
        try:
            with open(config_path, 'r', encoding='utf-8') as file:
                config_data = json.load(file)
            inbounds = config_data.get('inbounds', [])
            ports = [str(inbound.get('port', '?')) for inbound in inbounds]
            details = [f'{port}({inbound.get("protocol", "?")})' for inbound, port in zip(inbounds, ports)]
            socks_status = []
            for inbound in inbounds:
                if inbound.get('protocol') == 'socks':
                    port = inbound.get('port')
                    if port:
                        socks_status.append(f'{port}:sock5={"ok" if _check_socks5_handshake(port) else "fail"}')
            if socks_status:
                details.append('socks:' + ','.join(socks_status))
            outbounds = []
            for outbound in config_data.get('outbounds', []):
                tag = outbound.get('tag', '')
                protocol = outbound.get('protocol', '')
                if protocol in ['vless', 'vmess']:
                    vnext = outbound.get('settings', {}).get('vnext', [])
                    if vnext:
                        entry = vnext[0]
                        addr = entry.get('address', '')
                        port = entry.get('port', '')
                        outbounds.append(f'{tag}:{protocol}->{addr}:{port}')
                    else:
                        outbounds.append(f'{tag}:{protocol}')
                else:
                    outbounds.append(f'{tag}:{protocol}')
            summary = f'Конфиг v2ray валиден. inbounds: {", ".join(ports)}'
            if details:
                summary += f' ({"; ".join(details)})'
            if outbounds:
                summary += f'; outbounds: {", ".join(outbounds)}'
            diagnostics.append(summary)
        except Exception as exc:
            diagnostics.append(f'Ошибка парсинга конфига v2ray: {exc}')
    error_tail = _read_tail(error_path, lines=12)
    if error_tail:
        diagnostics.append(f'Последние строки лога v2ray ({error_path}):\n{error_tail}')
    return ' '.join(diagnostics)


def _format_proxy_key_summary(key_type, key_value):
    if key_type == 'shadowsocks':
        server, port, method, password = _decode_shadowsocks_uri(key_value)
        return ('Параметры Shadowsocks: server={server}, port={port}, method={method}, '
                'password_len={password_len}').format(
                    server=server,
                    port=port,
                    method=method,
                    password_len=len(password))
    if key_type in ['vless', 'vless2']:
        data = _parse_vless_key(key_value)
        return ('Параметры VLESS: address={address}, host={host}, port={port}, uuid={id}, network={type}, '
                'serviceName={serviceName}, sni={sni}, security={security}, flow={flow}').format(**data)
    if key_type == 'vmess':
        data = _parse_vmess_key(key_value)
        service_name = data.get('serviceName') or data.get('grpcSettings', {}).get('serviceName', '')
        return ('Параметры VMESS: host={add}, port={port}, id={id}, network={net}, tls={tls}, '
                'serviceName={service_name}').format(service_name=service_name, **data)
    if key_type == 'trojan':
        data = _parse_trojan_key(key_value)
        return ('Параметры Trojan: address={address}, port={port}, sni={sni}, security={security}, '
                'network={type}, password_len={password_len}').format(
                    address=data['address'],
                    port=data['port'],
                    sni=data['sni'],
                    security=data['security'],
                    type=data['type'],
                    password_len=len(data['password']))
    return ''


def _v2ray_outbound_summary(vmess_key=None, vless_key=None):
    try:
        config_data = _build_v2ray_config(vmess_key, vless_key)
        lines = []
        for outbound in config_data.get('outbounds', []):
            tag = outbound.get('tag', '')
            protocol = outbound.get('protocol', '')
            stream = outbound.get('streamSettings', {})
            if protocol in ['vless', 'vmess']:
                vnext = outbound.get('settings', {}).get('vnext', [])
                if vnext:
                    entry = vnext[0]
                    addr = entry.get('address', '')
                    port = entry.get('port', '')
                    lines.append(f'{tag}:{protocol} -> {addr}:{port} stream={stream}')
                else:
                    lines.append(f'{tag}:{protocol} stream={stream}')
            else:
                lines.append(f'{tag}:{protocol} stream={stream}')
        return ' '.join(lines)
    except Exception as exc:
        return f'Не удалось построить сводный outbound-конфиг: {exc}'


def _parse_trojan_key(key):
    parsed = urlparse(key)
    if parsed.scheme != 'trojan':
        raise ValueError('Неверный протокол, ожидается trojan://')
    if not parsed.hostname:
        raise ValueError('В trojan-ключе отсутствует адрес сервера')
    if not parsed.username:
        raise ValueError('В trojan-ключе отсутствует пароль')
    params = parse_qs(parsed.query)
    return {
        'address': parsed.hostname,
        'port': parsed.port or 443,
        'password': parsed.username,
        'sni': params.get('sni', [''])[0],
        'security': params.get('security', ['tls'])[0],
        'type': params.get('type', ['tcp'])[0],
        'host': params.get('host', [''])[0],
        'path': params.get('path', ['/'])[0] or '/',
        'serviceName': params.get('serviceName', [''])[0],
        'fingerprint': params.get('fp', params.get('fingerprint', ['chrome']))[0],
        'alpn': params.get('alpn', [''])[0],
        'fragment': unquote(parsed.fragment or ''),
    }


def _build_proxy_diagnostics(key_type, key_value):
    key_summary = _format_proxy_key_summary(key_type, key_value)
    if key_type not in ['vmess', 'vless', 'vless2']:
        return key_summary
    error_tail = _read_tail(CORE_PROXY_ERROR_LOG, lines=25)
    lines = [line.strip() for line in error_tail.splitlines() if line.strip()]
    last_issue = ''
    for line in reversed(lines):
        if ('failed to process outbound traffic' in line or
                'failed to find an available destination' in line or
                'dial tcp' in line or
                'lookup ' in line):
            last_issue = line
            break
    issue_summary = ''
    if last_issue:
        lookup_match = re.search(r'lookup\s+([^\s]+)', last_issue)
        dial_match = re.search(r'dial tcp\s+([^:]+:\d+)', last_issue)
        if 'server misbehaving' in last_issue and lookup_match:
            issue_summary = f'Причина: прокси-ядро не смогло разрешить адрес {lookup_match.group(1)} через локальный DNS.'
        elif 'operation was canceled' in last_issue and dial_match:
            issue_summary = f'Причина: сервер {dial_match.group(1)} не установил соединение через прокси-ядро.'
        elif 'connection refused' in last_issue and dial_match:
            issue_summary = f'Причина: сервер {dial_match.group(1)} отклонил соединение.'
        elif 'timed out' in last_issue or 'i/o timeout' in last_issue:
            issue_summary = 'Причина: соединение через прокси завершилось по таймауту.'
        elif 'failed to find an available destination' in last_issue:
            issue_summary = 'Причина: прокси-ядро не смогло построить рабочее исходящее соединение.'
    parts = []
    if issue_summary:
        parts.append(issue_summary)
    elif key_summary:
        parts.append(key_summary)
    return ' '.join(parts)


def _pool_key_display_name(key_value):
    raw_key = (key_value or '').strip()
    label = ''
    try:
        if raw_key.startswith('vmess://'):
            data = _parse_vmess_key(raw_key)
            label = data.get('ps') or data.get('add') or ''
        else:
            parsed = urlparse(raw_key)
            label = unquote(parsed.fragment or '').strip()
            if not label and parsed.hostname:
                label = parsed.hostname
    except Exception:
        label = ''

    label = re.sub(r'\s+', ' ', label).strip()
    return label or 'Ключ прокси'


POOL_PROTOCOL_ORDER = ['vless', 'vless2', 'vmess', 'trojan', 'shadowsocks']
# Telegram прокручивает reply-клавиатуру целиком, без закрепления нижних строк.
# Поэтому показываем весь пул в одной прокручиваемой клавиатуре, а служебные
# кнопки добавляем после списка ключей.
POOL_PAGE_SIZE = 1000
POOL_PROTOCOL_LABELS = {
    'shadowsocks': 'Shadowsocks',
    'vmess': 'Vmess',
    'vless': 'Vless 1',
    'vless2': 'Vless 2',
    'trojan': 'Trojan',
}
POOL_PROTOCOL_BUTTON_PREFIXES = {
    'shadowsocks': 'SS',
    'vmess': 'VM',
    'vless': 'V1',
    'vless2': 'V2',
    'trojan': 'TR',
}
TELEGRAM_BUTTON_ICON = 'TG'
YOUTUBE_BUTTON_ICON = 'YT'


def _pool_proto_label(proto):
    return POOL_PROTOCOL_LABELS.get(proto, proto)


def _pool_proto_button_prefix(proto):
    return POOL_PROTOCOL_BUTTON_PREFIXES.get(proto, str(proto or '').upper())


def _pool_proto_from_button_prefix(prefix):
    value = (prefix or '').strip().upper()
    for proto, proto_prefix in POOL_PROTOCOL_BUTTON_PREFIXES.items():
        if value == proto_prefix.upper():
            return proto
    return None


def _shorten_button_text(text, limit=38):
    value = re.sub(r'\s+', ' ', str(text or '')).strip()
    if len(value) <= limit:
        return value
    return value[:max(1, limit - 1)].rstrip() + '…'


def _pool_add_page_controls(markup, info):
    if info['total_pages'] <= 1:
        return
    previous_button = 'Ключи ◀️' if info['page'] > 0 else '·'
    next_button = 'Ключи ▶️' if info['page'] < info['total_pages'] - 1 else '·'
    page_button = f'Стр. {info["page"] + 1}/{info["total_pages"]}'
    markup.row(
        types.KeyboardButton(previous_button),
        types.KeyboardButton(page_button),
        types.KeyboardButton(next_button),
    )


def _pool_protocol_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    buttons = [types.KeyboardButton(_pool_proto_label(proto)) for proto in POOL_PROTOCOL_ORDER]
    markup.row(buttons[0], buttons[1])
    markup.row(buttons[2], buttons[3])
    markup.row(buttons[4])
    markup.row(types.KeyboardButton('🔙 В меню ключей'), types.KeyboardButton('🔙 Назад'))
    return markup


def _resolve_pool_protocol(text):
    value = (text or '').strip().lower()
    aliases = {
        'shadowsocks': 'shadowsocks',
        'ss': 'shadowsocks',
        'vmess': 'vmess',
        'vless': 'vless',
        'vless 1': 'vless',
        'vless1': 'vless',
        'vless 2': 'vless2',
        'vless2': 'vless2',
        'trojan': 'trojan',
    }
    for proto, label in POOL_PROTOCOL_LABELS.items():
        aliases[label.lower()] = proto
        aliases[f'📦 {label}'.lower()] = proto
    return aliases.get(value)


def _remove_inline_keyboard(chat_id, message_id):
    if not chat_id or not message_id:
        return
    try:
        bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=None)
    except Exception as exc:
        if 'message is not modified' not in str(exc).lower():
            _write_runtime_log(f'Ошибка удаления inline-клавиатуры пула: {exc}')


def _clear_pool_inline_keyboard(chat_id, message_id=None):
    if message_id:
        _remove_inline_keyboard(chat_id, message_id)


def _pool_action_markup(proto, page=0):
    _, info = _format_pool_page(proto, page)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    current_keys = _load_current_keys()
    current_key = current_keys.get(proto)
    cache = _load_key_probe_cache()
    for offset, key_value in enumerate(info['keys'][info['start']:info['end']], start=info['start'] + 1):
        probe = cache.get(_hash_key(key_value), {})
        markup.row(types.KeyboardButton(_pool_key_button_label(offset, key_value, probe=probe, current_key=current_key, proto=proto)))
    _pool_add_page_controls(markup, info)
    markup.row(types.KeyboardButton('➕ Добавить ключи'), types.KeyboardButton('🔗 Загрузить subscription'))
    markup.row(types.KeyboardButton('🔍 Проверить пул'), types.KeyboardButton('🧹 Очистить пул'))
    markup.row(types.KeyboardButton('🗑 Удаление'), types.KeyboardButton('🔄 Обновить пул'))
    markup.row(types.KeyboardButton('🔙 К выбору протокола'), types.KeyboardButton('🔙 В меню ключей'))
    markup.row(types.KeyboardButton('🔙 Назад'))
    return markup


def _pool_delete_markup(proto, page=0):
    _, info = _format_pool_page(proto, page)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    current_keys = _load_current_keys()
    current_key = current_keys.get(proto)
    cache = _load_key_probe_cache()
    for offset, key_value in enumerate(info['keys'][info['start']:info['end']], start=info['start'] + 1):
        probe = cache.get(_hash_key(key_value), {})
        markup.row(types.KeyboardButton(_pool_key_button_label(offset, key_value, probe=probe, current_key=current_key, proto=proto, action='delete')))
    _pool_add_page_controls(markup, info)
    markup.row(types.KeyboardButton('🔙 К пулу'), types.KeyboardButton('🔙 Назад'))
    return markup


def _pool_clear_confirm_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(types.KeyboardButton('✅ Очистить пул'), types.KeyboardButton('Отмена'))
    markup.row(types.KeyboardButton('🔙 К пулу'), types.KeyboardButton('🔙 Назад'))
    return markup


def _pool_input_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(types.KeyboardButton('🔙 К пулу'), types.KeyboardButton('🔙 Назад'))
    return markup


def _pool_probe_text(probe):
    if not probe:
        return 'не проверялся'
    badges = []
    if probe.get('tg_ok'):
        badges.append(f'{TELEGRAM_BUTTON_ICON}✅')
    elif 'tg_ok' in probe:
        badges.append(f'{TELEGRAM_BUTTON_ICON}❌')
    if probe.get('yt_ok'):
        badges.append(f'{YOUTUBE_BUTTON_ICON}✅')
    elif 'yt_ok' in probe:
        badges.append(f'{YOUTUBE_BUTTON_ICON}❌')
    if not badges:
        return 'не проверялся'
    return ' '.join(badges)


def _pool_probe_button_text(probe):
    if not probe:
        return f'{TELEGRAM_BUTTON_ICON}? {YOUTUBE_BUTTON_ICON}?'
    tg = f'{TELEGRAM_BUTTON_ICON}✅' if probe.get('tg_ok') else (f'{TELEGRAM_BUTTON_ICON}❌' if 'tg_ok' in probe else f'{TELEGRAM_BUTTON_ICON}?')
    yt = f'{YOUTUBE_BUTTON_ICON}✅' if probe.get('yt_ok') else (f'{YOUTUBE_BUTTON_ICON}❌' if 'yt_ok' in probe else f'{YOUTUBE_BUTTON_ICON}?')
    return f'{tg} {yt}'


def _pool_key_button_label(index, key_value, probe=None, current_key=None, proto=None, action='apply'):
    display_name = _shorten_button_text(_pool_key_display_name(key_value), limit=24)
    status = _pool_probe_button_text(probe)
    proto_prefix = _pool_proto_button_prefix(proto)
    if action == 'delete':
        prefix = f'✕ {proto_prefix} {index}.'
    elif current_key and key_value == current_key:
        prefix = f'✅ {proto_prefix} {index}.'
    else:
        prefix = f'{proto_prefix} {index}.'
    return _shorten_button_text(f'{prefix} {display_name} {status}', limit=52)


def _pool_key_line(index, key_value, probe=None, current_key=None):
    marker = ' — АКТИВЕН' if current_key and key_value == current_key else ''
    display_name = _pool_key_display_name(key_value)
    key_hash = _hash_key(key_value)[:8]
    return f'{index}. {display_name}{marker} [{key_hash}] — {_pool_probe_text(probe)}'


def _format_pool_summary():
    current_keys = _load_current_keys()
    pools = _ensure_current_keys_in_pools(current_keys)
    lines = ['📦 Пул ключей', 'Выберите протокол для управления пулом.', '']
    for proto in POOL_PROTOCOL_ORDER:
        keys = pools.get(proto, []) or []
        current_key = current_keys.get(proto)
        active = 'активный есть' if current_key else 'активный не задан'
        lines.append(f'{_pool_proto_label(proto)}: {len(keys)} ключей, {active}')
    return '\n'.join(lines)


def _pool_status_summary(current_keys=None, key_pools=None, key_probe_cache=None, custom_checks=None):
    current_keys = current_keys if current_keys is not None else _load_current_keys()
    key_pools = key_pools if key_pools is not None else _ensure_current_keys_in_pools(current_keys)
    key_probe_cache = key_probe_cache if key_probe_cache is not None else _load_key_probe_cache()
    custom_checks = custom_checks if custom_checks is not None else _load_custom_checks()
    services = [
        {'label': 'Telegram', 'field': 'tg_ok', 'id': None, 'count': 0},
        {'label': 'YouTube', 'field': 'yt_ok', 'id': None, 'count': 0},
    ]
    for check in custom_checks:
        check_id = str(check.get('id') or '').strip()
        if not check_id:
            continue
        label = str(check.get('label') or check_id).strip() or check_id
        if len(label) > 18:
            label = label[:18] + '...'
        services.append({'label': label, 'field': None, 'id': check_id, 'count': 0})

    total_count = 0
    checked_count = 0
    all_services_count = 0
    any_service_count = 0
    for proto in POOL_PROTOCOL_ORDER:
        for pool_key in key_pools.get(proto, []) or []:
            total_count += 1
            probe = key_probe_cache.get(_hash_key(pool_key), {})
            custom = probe.get('custom', {}) if isinstance(probe, dict) else {}
            if not isinstance(custom, dict):
                custom = {}
            results = []
            for service in services:
                if service['field']:
                    if service['field'] not in probe:
                        continue
                    ok = bool(probe.get(service['field']))
                else:
                    if service['id'] not in custom:
                        continue
                    ok = bool(custom.get(service['id']))
                results.append(ok)
                if ok:
                    service['count'] += 1
            if len(results) == len(services):
                checked_count += 1
            if results and any(results):
                any_service_count += 1
            if len(results) == len(services) and all(results):
                all_services_count += 1

    active_key_count = sum(1 for proto in POOL_PROTOCOL_ORDER if (current_keys.get(proto) or '').strip())
    service_text = '. '.join(f"{service['label']}: {service['count']}" for service in services)
    note_parts = [
        f'В пулах: {total_count}',
        f'Проверено: {checked_count}',
    ]
    if service_text:
        note_parts.append(service_text)
    note_parts.append(f'Все сервисы: {all_services_count}')
    note_parts.append(f'Хотя бы один: {any_service_count}')
    note = '. '.join(note_parts) + '.'
    return {
        'active_key_count': active_key_count,
        'protocol_count': len(POOL_PROTOCOL_ORDER),
        'active_text': f'{active_key_count} / {len(POOL_PROTOCOL_ORDER)} активных ключей',
        'note': note,
        'pool_total_count': total_count,
        'checked_pool_count': checked_count,
        'all_services_count': all_services_count,
        'any_service_count': any_service_count,
        'services': [{'label': service['label'], 'count': service['count']} for service in services],
    }


def _format_pool_details(proto):
    current_keys = _load_current_keys()
    pools = _ensure_current_keys_in_pools(current_keys)
    cache = _load_key_probe_cache()
    keys = pools.get(proto, []) or []
    label = _pool_proto_label(proto)
    if not keys:
        return f'📦 {label}: пул пуст.'
    lines = [f'📦 {label}: {len(keys)} ключей', '* — текущий активный ключ', '']
    current_key = current_keys.get(proto)
    for index, key_value in enumerate(keys, start=1):
        probe = cache.get(_hash_key(key_value), {})
        lines.append(_pool_key_line(index, key_value, probe=probe, current_key=current_key))
    return '\n'.join(lines)


def _pool_page_info(proto, page=0):
    keys = _pool_keys_for_proto(proto)
    total = len(keys)
    total_pages = max(1, (total + POOL_PAGE_SIZE - 1) // POOL_PAGE_SIZE)
    try:
        page = int(page)
    except (TypeError, ValueError):
        page = 0
    page = max(0, min(page, total_pages - 1))
    start = page * POOL_PAGE_SIZE
    end = min(start + POOL_PAGE_SIZE, total)
    return {
        'keys': keys,
        'total': total,
        'total_pages': total_pages,
        'page': page,
        'start': start,
        'end': end,
    }


def _format_pool_page(proto, page=0, prefix=None):
    info = _pool_page_info(proto, page)
    label = _pool_proto_label(proto)
    header = f'📦 {label}: {info["total"]} ключей'
    if info['total_pages'] > 1:
        header += f' · стр. {info["page"] + 1}/{info["total_pages"]}'
    lines = []
    if prefix:
        lines.extend([prefix, ''])
    lines.append(header)
    if not info['keys']:
        lines.append('Пул пуст. Добавьте ключи вручную или через subscription.')
    else:
        lines.append('Ключи выведены в нижней клавиатуре.')
        lines.append('Нажмите кнопку с кодом протокола V1/V2/VM/TR/SS, чтобы применить ключ. Для удаления нажмите «🗑 Удаление».')
    return '\n'.join(lines), info


def _send_pool_page(chat_id, proto, page=0, prefix=None):
    text, info = _format_pool_page(proto, page, prefix=prefix)
    _set_pool_page(chat_id, info['page'])
    bot.send_message(chat_id, text, reply_markup=_pool_action_markup(proto, info['page']))


def _send_pool_delete_page(chat_id, proto, page=0, prefix=None):
    text, info = _format_pool_page(proto, page, prefix=prefix)
    _set_pool_page(chat_id, info['page'])
    bot.send_message(chat_id, text, reply_markup=_pool_delete_markup(proto, info['page']))


def _send_pool_details(chat_id, proto, prefix=None, suffix=None, reply_markup=None):
    parts = [part for part in (prefix, _format_pool_details(proto), suffix) if part]
    _send_telegram_chunks(chat_id, '\n\n'.join(parts), reply_markup=reply_markup)


def _pool_keys_for_proto(proto):
    pools = _ensure_current_keys_in_pools()
    return list(pools.get(proto, []) or [])


def _pool_key_by_index(proto, raw_index):
    keys = _pool_keys_for_proto(proto)
    try:
        index = int(str(raw_index).strip())
    except Exception:
        raise ValueError('Введите номер ключа из списка.')
    if index < 1 or index > len(keys):
        raise ValueError(f'Номер вне диапазона. В пуле {_pool_proto_label(proto)} ключей: {len(keys)}.')
    return index, keys[index - 1]


def _pool_reply_key_action(text):
    value = (text or '').strip()
    action = 'apply'
    lowered = value.lower()
    for marker in ('✕', '×', '❌', '🗑', 'x'):
        if lowered.startswith(marker.lower()):
            action = 'delete'
            value = value[len(marker):].strip()
            break
    for marker in ('✅', '✔️', '✔', '✓'):
        if value.startswith(marker):
            value = value[len(marker):].strip()
            break

    parts = value.split(maxsplit=1)
    if len(parts) == 2:
        button_proto = _pool_proto_from_button_prefix(parts[0])
        if button_proto:
            index_match = re.match(r'^(\d+)(?:[.)]\s|$)', parts[1])
            if index_match:
                return action, index_match.group(1), button_proto

    legacy_match = re.match(r'^(\d+)(?:[.)]\s|$)', value)
    if legacy_match:
        return 'legacy', legacy_match.group(1), None
    return None, None, None


def _pool_reply_page_delta(text):
    value = (text or '').strip()
    if value in ('Ключи ◀️', 'Ключи ◀', '◀️ Предыдущая', '◀ Предыдущая'):
        return -1
    if value in ('Ключи ▶️', 'Ключи ▶', 'Следующая ▶️', 'Следующая ▶'):
        return 1
    return 0


def _is_pool_page_indicator(text):
    return bool(re.match(r'^Стр\.\s+\d+/\d+$', (text or '').strip()))


def _is_pool_page_noop(text):
    value = (text or '').strip()
    return value in ('·', '') or _is_pool_page_indicator(value)


def _pool_key_by_callback_id(proto, key_id):
    key_id = (key_id or '').strip()
    for index, key_value in enumerate(_pool_keys_for_proto(proto), start=1):
        if _hash_key(key_value)[:12] == key_id:
            return index, key_value
    raise ValueError('Ключ не найден в пуле. Обновите пул и попробуйте снова.')


def _apply_pool_key(proto, key_value):
    result = _install_key_for_protocol(proto, key_value)
    _set_active_key(proto, key_value)
    _invalidate_web_status_cache()
    _invalidate_key_status_cache()
    return result


def _apply_pool_key_background(chat_id, proto, key_value, index, page=0):
    def worker():
        if not pool_apply_lock.acquire(blocking=False):
            bot.send_message(
                chat_id,
                'Уже выполняется применение ключа. Дождитесь результата и попробуйте снова.',
                reply_markup=_pool_action_markup(proto, page),
            )
            return
        try:
            result = _apply_pool_key(proto, key_value)
            display_name = _pool_key_display_name(key_value)
            prefix = f'✅ Ключ #{index} «{display_name}» применён для {_pool_proto_label(proto)}.\n{result}'
        except Exception as exc:
            prefix = f'Ошибка применения ключа #{index} из пула {_pool_proto_label(proto)}: {exc}'
        finally:
            pool_apply_lock.release()
        _send_pool_page(chat_id, proto, page=page, prefix=prefix)

    threading.Thread(target=worker, daemon=True).start()


def _v2ray_key_file_candidates(file_path):
    paths = [file_path]
    file_name = os.path.basename(file_path)
    for directory in (XRAY_CONFIG_DIR, V2RAY_CONFIG_DIR):
        candidate = os.path.join(directory, file_name)
        if candidate not in paths:
            paths.append(candidate)
    return paths


def _remove_file_if_exists(file_path):
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as exc:
        _write_runtime_log(f'Не удалось удалить {file_path}: {exc}')


def _clear_installed_key_for_protocol(proto):
    if proto == 'vmess':
        for file_path in _v2ray_key_file_candidates(VMESS_KEY_PATH):
            _remove_file_if_exists(file_path)
    elif proto == 'vless':
        for file_path in _v2ray_key_file_candidates(VLESS_KEY_PATH):
            _remove_file_if_exists(file_path)
    elif proto == 'vless2':
        for file_path in _v2ray_key_file_candidates(VLESS2_KEY_PATH):
            _remove_file_if_exists(file_path)
    elif proto == 'shadowsocks':
        _remove_file_if_exists('/opt/etc/shadowsocks.json')
    elif proto == 'trojan':
        _remove_file_if_exists('/opt/etc/trojan/config.json')
    else:
        raise ValueError('Неизвестный протокол')
    if _load_proxy_mode() == proto:
        update_proxy('none')
    _write_all_proxy_core_config()
    _restart_proxy_services_for_protocols([proto])


def _delete_pool_key(proto, key_value):
    pools = _load_key_pools()
    keys = _dedupe_key_list(pools.get(proto, []) or [])
    if key_value not in keys:
        raise ValueError('Ключ не найден в пуле.')
    current_key = (_load_current_keys().get(proto) or '').strip()
    was_current = bool(current_key and current_key == key_value)
    keys = [candidate for candidate in keys if candidate != key_value]
    promoted_key = keys[0] if was_current and keys else ''
    if promoted_key:
        _install_key_for_protocol(proto, promoted_key, verify=False)
        keys = [candidate for candidate in keys if candidate != promoted_key]
        keys.insert(0, promoted_key)
    elif was_current:
        _clear_installed_key_for_protocol(proto)
    pools[proto] = keys
    _save_key_pools(pools)
    cache = _load_key_probe_cache()
    cache.pop(_hash_key(key_value), None)
    _save_key_probe_cache(cache)
    _invalidate_web_status_cache()
    _invalidate_key_status_cache()


def _clear_pool(proto):
    pools = _load_key_pools()
    removed_keys = _dedupe_key_list(pools.get(proto, []) or [])
    pools[proto] = []
    _save_key_pools(pools)
    current_key = (_load_current_keys().get(proto) or '').strip()
    if current_key and current_key in removed_keys:
        _clear_installed_key_for_protocol(proto)
    if removed_keys:
        cache = _load_key_probe_cache()
        for key_value in removed_keys:
            cache.pop(_hash_key(key_value), None)
        _save_key_probe_cache(cache)
    _invalidate_web_status_cache()
    _invalidate_key_status_cache()
    return len(removed_keys)


def _proxy_config_snapshot_paths():
    return [
        CORE_PROXY_CONFIG_PATH,
        VMESS_KEY_PATH,
        VLESS_KEY_PATH,
        VLESS2_KEY_PATH,
        '/opt/etc/shadowsocks.json',
        '/opt/etc/trojan/config.json',
    ]


def _snapshot_proxy_config_files():
    snapshot = {}
    for file_path in _proxy_config_snapshot_paths():
        try:
            with open(file_path, 'rb') as file:
                snapshot[file_path] = file.read()
        except FileNotFoundError:
            snapshot[file_path] = None
        except Exception as exc:
            _write_runtime_log(f'Не удалось сохранить snapshot {file_path}: {exc}')
            snapshot[file_path] = None
    return snapshot


def _restore_proxy_config_files(snapshot):
    for file_path, content in (snapshot or {}).items():
        try:
            if content is None:
                if os.path.exists(file_path):
                    os.remove(file_path)
                continue
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'wb') as file:
                file.write(content)
        except Exception as exc:
            _write_runtime_log(f'Не удалось восстановить snapshot {file_path}: {exc}')


def _restart_proxy_services_for_protocols(protocols):
    commands = []
    if 'shadowsocks' in protocols:
        commands.append('/opt/etc/init.d/S22shadowsocks restart')
    if protocols:
        commands.append(CORE_PROXY_SERVICE_SCRIPT + ' restart')
    if 'trojan' in protocols:
        commands.append('/opt/etc/init.d/S22trojan restart')
    for command in dict.fromkeys(commands):
        os.system(command)
    if commands:
        time.sleep(3)
    _invalidate_web_status_cache()
    _invalidate_key_status_cache()


def _failed_custom_probe_results(custom_checks):
    return {
        check.get('id'): False
        for check in (custom_checks or [])
        if check.get('id')
    }


def _available_memory_kb():
    try:
        with open('/proc/meminfo', 'r', encoding='utf-8', errors='ignore') as file:
            for line in file:
                if line.startswith('MemAvailable:'):
                    parts = line.split()
                    if len(parts) >= 2:
                        return int(parts[1])
    except Exception:
        pass
    return None


def _set_pool_probe_progress(**updates):
    with pool_probe_progress_lock:
        pool_probe_progress.update(updates)


def _get_pool_probe_progress():
    with pool_probe_progress_lock:
        return dict(pool_probe_progress)


def _check_pool_key_through_proxy(proto, key_value, custom_checks=None, proxy_url=None):
    proxy_url = proxy_url or proxy_settings.get(proto)
    tg_ok, _ = _check_telegram_api_through_proxy(
        proxy_url,
        connect_timeout=POOL_PROBE_TG_CONNECT_TIMEOUT,
        read_timeout=POOL_PROBE_TG_READ_TIMEOUT,
    )
    yt_ok, _ = _check_http_through_proxy(
        proxy_url,
        connect_timeout=POOL_PROBE_HTTP_CONNECT_TIMEOUT,
        read_timeout=POOL_PROBE_HTTP_READ_TIMEOUT,
    )
    _record_key_probe(proto, key_value, tg_ok=tg_ok, yt_ok=yt_ok)
    if custom_checks:
        custom_results = _probe_custom_targets(
            proxy_url,
            custom_checks=custom_checks,
            connect_timeout=POOL_PROBE_HTTP_CONNECT_TIMEOUT,
            read_timeout=POOL_PROBE_HTTP_READ_TIMEOUT,
        )
        _record_key_probe(proto, key_value, custom=custom_results)


def _pool_probe_socks_inbound(port, tag):
    return {
        'port': int(port),
        'listen': '127.0.0.1',
        'protocol': 'socks',
        'settings': {'auth': 'noauth', 'udp': True, 'ip': '127.0.0.1'},
        'sniffing': {'enabled': True, 'destOverride': ['http', 'tls']},
        'tag': tag,
    }


def _proxy_outbound_from_key(proto, key_value, tag, email='t@t.tt'):
    if proto == 'shadowsocks':
        server, port, method, password = _decode_shadowsocks_uri(key_value)
        return {
            'tag': tag,
            'protocol': 'shadowsocks',
            'settings': {
                'servers': [{
                    'address': server,
                    'port': int(port),
                    'method': method,
                    'password': password,
                    'level': 0,
                }]
            },
        }
    if proto == 'vmess':
        data = _parse_vmess_key(key_value)
        stream_settings = {'network': data.get('net', 'tcp')}
        tls_mode = data.get('tls', 'tls')
        if tls_mode in ['tls', 'xtls']:
            stream_settings['security'] = tls_mode
            stream_settings[f'{tls_mode}Settings'] = {
                'allowInsecure': True,
                'serverName': data.get('add', ''),
            }
        else:
            stream_settings['security'] = 'none'
        if stream_settings['network'] == 'ws':
            stream_settings['wsSettings'] = {
                'path': data.get('path', '/'),
                'headers': {'Host': data.get('host', '')},
            }
        elif stream_settings['network'] == 'grpc':
            grpc_service = data.get('serviceName', '') or data.get('grpcSettings', {}).get('serviceName', '')
            stream_settings['grpcSettings'] = {'serviceName': grpc_service, 'multiMode': False}
        return {
            'tag': tag,
            'domainStrategy': 'UseIPv4',
            'protocol': 'vmess',
            'settings': {
                'vnext': [{
                    'address': data['add'],
                    'port': int(data['port']),
                    'users': [{
                        'id': data['id'],
                        'alterId': int(data.get('aid', 0)),
                        'email': email,
                        'security': 'auto',
                    }],
                }]
            },
            'streamSettings': stream_settings,
            'mux': {'enabled': True, 'concurrency': -1, 'xudpConcurrency': 16, 'xudpProxyUDP443': 'reject'},
        }
    if proto in ('vless', 'vless2'):
        data = _parse_vless_key(key_value)
        network = data.get('type', 'tcp') or 'tcp'
        security = data.get('security', 'none')
        stream_settings = {'network': network}
        if security in ['tls', 'xtls']:
            stream_settings['security'] = security
            stream_settings[f'{security}Settings'] = {
                'allowInsecure': True,
                'serverName': data.get('sni', ''),
            }
        elif security == 'reality':
            stream_settings['security'] = 'reality'
            stream_settings['realitySettings'] = {
                'serverName': data.get('sni', '') or data.get('host', '') or data.get('address', ''),
                'publicKey': data.get('publicKey', ''),
                'shortId': data.get('shortId', ''),
                'fingerprint': data.get('fingerprint', 'chrome'),
                'spiderX': data.get('spiderX', '/'),
            }
            if data.get('alpn'):
                stream_settings['realitySettings']['alpn'] = [item.strip() for item in data['alpn'].split(',') if item.strip()]
        else:
            stream_settings['security'] = 'none'
        if network == 'ws':
            stream_settings['wsSettings'] = {
                'path': data.get('path', '/'),
                'headers': {'Host': data.get('host', '')},
            }
        elif network == 'grpc':
            stream_settings['grpcSettings'] = {'serviceName': data.get('serviceName', ''), 'multiMode': False}
        return {
            'tag': tag,
            'domainStrategy': 'UseIPv4',
            'protocol': 'vless',
            'settings': {
                'vnext': [{
                    'address': data.get('address', data.get('host', '')),
                    'port': int(data['port']),
                    'users': [{
                        'id': data['id'],
                        'encryption': data.get('encryption', 'none'),
                        'flow': data.get('flow', ''),
                        'level': 0,
                    }],
                }]
            },
            'streamSettings': stream_settings,
        }
    if proto == 'trojan':
        data = _parse_trojan_key(key_value)
        stream_settings = {'network': data.get('type', 'tcp') or 'tcp', 'security': 'none'}
        if data.get('security', 'tls') == 'tls':
            stream_settings['security'] = 'tls'
            stream_settings['tlsSettings'] = {
                'allowInsecure': True,
                'serverName': data.get('sni') or data.get('host') or data.get('address', ''),
                'fingerprint': data.get('fingerprint', 'chrome'),
            }
            if data.get('alpn'):
                stream_settings['tlsSettings']['alpn'] = [item.strip() for item in data['alpn'].split(',') if item.strip()]
        if stream_settings['network'] == 'ws':
            stream_settings['wsSettings'] = {
                'path': data.get('path', '/'),
                'headers': {'Host': data.get('host') or data.get('sni') or data.get('address', '')},
            }
        elif stream_settings['network'] == 'grpc':
            stream_settings['grpcSettings'] = {'serviceName': data.get('serviceName', ''), 'multiMode': False}
        return {
            'tag': tag,
            'protocol': 'trojan',
            'settings': {
                'servers': [{
                    'address': data['address'],
                    'port': int(data['port']),
                    'password': data['password'],
                    'level': 0,
                }]
            },
            'streamSettings': stream_settings,
        }
    raise ValueError(f'Unsupported protocol: {proto}')


def _pool_probe_outbound(proto, key_value, tag):
    return _proxy_outbound_from_key(proto, key_value, tag, email='pool-probe@local')


def _build_pool_probe_core_config_batch(probe_tasks):
    config_json = {
        'log': {
            'access': '/dev/null',
            'error': '/dev/null',
            'loglevel': 'warning',
        },
        'inbounds': [],
        'outbounds': [],
        'routing': {
            'domainStrategy': 'IPIfNonMatch',
            'rules': [],
        },
    }
    test_routes = []
    for offset, (proto, key_value) in enumerate(probe_tasks):
        port = str(int(POOL_PROBE_TEST_PORT) + offset)
        inbound_tag = f'in-pool-probe-{offset}'
        outbound_tag = f'proxy-pool-probe-{offset}'
        config_json.setdefault('inbounds', []).append(_pool_probe_socks_inbound(port, inbound_tag))
        config_json.setdefault('outbounds', []).append(_pool_probe_outbound(proto, key_value, outbound_tag))
        test_routes.append({
            'type': 'field',
            'inboundTag': [inbound_tag],
            'outboundTag': outbound_tag,
            'enabled': True,
        })
    config_json['outbounds'].append({'protocol': 'freedom', 'tag': 'direct'})
    config_json['routing']['rules'] = test_routes
    return config_json


def _start_pool_probe_xray(config_json):
    xray_binary = shutil.which('xray') or '/opt/sbin/xray'
    config_path = f'/tmp/bypass_pool_probe_{os.getpid()}_{threading.get_ident()}.json'
    with open(config_path, 'w', encoding='utf-8') as file:
        json.dump(config_json, file, ensure_ascii=False, separators=(',', ':'))
    preexec_fn = None
    if os.name == 'posix' and hasattr(os, 'nice'):
        def lower_priority():
            try:
                os.nice(10)
            except Exception:
                pass
        preexec_fn = lower_priority
    process = subprocess.Popen(
        [xray_binary, 'run', '-c', config_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        preexec_fn=preexec_fn,
    )
    return process, config_path


def _stop_pool_probe_xray(process, config_path):
    pid = None
    try:
        pid = process.pid if process else None
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except Exception:
                try:
                    process.kill()
                    process.wait(timeout=2)
                except Exception:
                    if pid:
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except Exception:
                            pass
    except Exception:
        pass
    if pid:
        try:
            os.waitpid(pid, os.WNOHANG)
        except Exception:
            pass
    try:
        if config_path and os.path.exists(config_path):
            os.remove(config_path)
    except Exception:
        pass


def _cleanup_pool_probe_runtime(kill_processes=False):
    if kill_processes:
        try:
            output = subprocess.check_output(
                ['pgrep', '-f', '/tmp/bypass_pool_probe_'],
                stderr=subprocess.DEVNULL,
            ).decode('utf-8', errors='ignore')
            for raw_pid in output.split():
                try:
                    pid = int(raw_pid)
                except ValueError:
                    continue
                if pid != os.getpid():
                    os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
        time.sleep(0.2)
        try:
            output = subprocess.check_output(
                ['pgrep', '-f', '/tmp/bypass_pool_probe_'],
                stderr=subprocess.DEVNULL,
            ).decode('utf-8', errors='ignore')
            for raw_pid in output.split():
                try:
                    pid = int(raw_pid)
                except ValueError:
                    continue
                if pid != os.getpid():
                    os.kill(pid, signal.SIGKILL)
        except Exception:
            pass

    try:
        for name in os.listdir('/tmp'):
            if name.startswith('bypass_pool_probe_') and name.endswith('.json'):
                try:
                    os.remove(os.path.join('/tmp', name))
                except Exception:
                    pass
    except Exception:
        pass


def _select_pool_probe_tasks(tasks, max_keys=None, stale_only=False, missing_only=False):
    custom_checks = _load_custom_checks()
    cache = _load_key_probe_cache() if stale_only or missing_only else {}
    now = time.time()
    selected = []
    seen = set()
    for proto, key_value in tasks:
        key_value = (key_value or '').strip()
        if proto not in POOL_PROTOCOL_ORDER or not key_value:
            continue
        task_id = (proto, _hash_key(key_value))
        if task_id in seen:
            continue
        seen.add(task_id)
        if missing_only and _key_probe_has_required_results(cache.get(_hash_key(key_value)), custom_checks=custom_checks):
            continue
        if stale_only and _key_probe_is_fresh(cache.get(_hash_key(key_value)), now=now, custom_checks=custom_checks):
            continue
        selected.append((proto, key_value))
        if max_keys is not None and len(selected) >= max_keys:
            break
    return selected, custom_checks


def _queue_pool_key_probe(tasks, max_keys=None, stale_only=False, missing_only=False):
    selected, custom_checks = _select_pool_probe_tasks(
        tasks,
        max_keys=max_keys,
        stale_only=stale_only,
        missing_only=missing_only,
    )
    if POOL_PROBE_ACTIVE_ONLY:
        current_keys = _load_current_keys()
        selected = [
            (proto, key_value)
            for proto, key_value in selected
            if key_value == (current_keys.get(proto) or '').strip()
        ]
    if not selected:
        return False, 0
    if not pool_probe_lock.acquire(blocking=False):
        return False, len(selected)
    _set_pool_probe_progress(
        running=True,
        checked=0,
        total=len(selected),
        started_at=time.time(),
        finished_at=0,
    )
    def worker(probe_tasks, checks):
        try:
            total = len(probe_tasks)
            checked = 0
            marked_tasks = set()

            def mark_checked(proto, key_value):
                nonlocal checked
                task_key = (proto, _hash_key(key_value))
                if task_key in marked_tasks:
                    return
                marked_tasks.add(task_key)
                checked += 1
                _set_pool_probe_progress(checked=checked)

            while probe_tasks:
                available_kb = _available_memory_kb()
                if available_kb is not None and available_kb < POOL_PROBE_MIN_AVAILABLE_KB:
                    _write_runtime_log(
                        f'Проверка пула остановлена: свободной памяти {available_kb} KB, '
                        f'порог {POOL_PROBE_MIN_AVAILABLE_KB} KB.'
                    )
                    break
                raw_batch = probe_tasks[:POOL_PROBE_BATCH_SIZE]
                del probe_tasks[:POOL_PROBE_BATCH_SIZE]
                valid_batch = []
                for proto, key_value in raw_batch:
                    try:
                        _pool_probe_outbound(proto, key_value, 'proxy-pool-probe-validate')
                        valid_batch.append((proto, key_value))
                    except Exception as exc:
                        _write_runtime_log(f'Ошибка подготовки ключа из пула {_pool_proto_label(proto)}: {exc}')
                        _record_key_probe(
                            proto,
                            key_value,
                            tg_ok=False,
                            yt_ok=False,
                            custom=_failed_custom_probe_results(checks),
                        )
                        mark_checked(proto, key_value)
                if not valid_batch:
                    continue
                process = None
                config_path = None
                try:
                    process, config_path = _start_pool_probe_xray(_build_pool_probe_core_config_batch(valid_batch))
                    ready_batch = []
                    for offset, (proto, key_value) in enumerate(valid_batch):
                        port = str(int(POOL_PROBE_TEST_PORT) + offset)
                        if not _wait_for_socks5_handshake(port, timeout=6):
                            _write_runtime_log(f'Тестовый SOCKS-порт {port} не поднялся для {_pool_proto_label(proto)}.')
                            _record_key_probe(
                                proto,
                                key_value,
                                tg_ok=False,
                                yt_ok=False,
                                custom=_failed_custom_probe_results(checks),
                            )
                            mark_checked(proto, key_value)
                            continue
                        ready_batch.append((offset, proto, key_value))
                    if not ready_batch:
                        raise RuntimeError('Тестовые SOCKS-порты не поднялись.')
                    max_workers = min(POOL_PROBE_CONCURRENCY, len(ready_batch))
                    executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
                    future_map = {}
                    try:
                        for offset, proto, key_value in ready_batch:
                            port = str(int(POOL_PROBE_TEST_PORT) + offset)
                            proxy_url = f'socks5h://127.0.0.1:{port}'
                            future = executor.submit(
                                _check_pool_key_through_proxy,
                                proto,
                                key_value,
                                checks,
                                proxy_url,
                            )
                            future_map[future] = (proto, key_value)
                        done, pending = concurrent.futures.wait(
                            future_map,
                            timeout=POOL_PROBE_BATCH_TIMEOUT_SECONDS,
                        )
                        for future in done:
                            proto, key_value = future_map[future]
                            try:
                                future.result()
                            except Exception as exc:
                                _write_runtime_log(f'Ошибка проверки ключа из пула {_pool_proto_label(proto)}: {exc}')
                                _record_key_probe(
                                    proto,
                                    key_value,
                                    tg_ok=False,
                                    yt_ok=False,
                                    custom=_failed_custom_probe_results(checks),
                                )
                            finally:
                                mark_checked(proto, key_value)
                                _invalidate_web_status_cache()
                                _invalidate_key_status_cache()
                                gc.collect()
                        for future in pending:
                            proto, key_value = future_map[future]
                            future.cancel()
                            _write_runtime_log(
                                f'Проверка ключа из пула {_pool_proto_label(proto)} превысила лимит '
                                f'{POOL_PROBE_BATCH_TIMEOUT_SECONDS:g} сек.'
                            )
                            _record_key_probe(
                                proto,
                                key_value,
                                tg_ok=False,
                                yt_ok=False,
                                custom=_failed_custom_probe_results(checks),
                            )
                            mark_checked(proto, key_value)
                            _invalidate_web_status_cache()
                            _invalidate_key_status_cache()
                            gc.collect()
                    finally:
                        try:
                            executor.shutdown(wait=False, cancel_futures=True)
                        except TypeError:
                            executor.shutdown(wait=False)
                except Exception as exc:
                    _write_runtime_log(f'Ошибка проверки пачки ключей из пула: {exc}')
                    for proto, key_value in valid_batch:
                        _record_key_probe(
                            proto,
                            key_value,
                            tg_ok=False,
                            yt_ok=False,
                            custom=_failed_custom_probe_results(checks),
                        )
                        mark_checked(proto, key_value)
                finally:
                    _stop_pool_probe_xray(process, config_path)
                    _cleanup_pool_probe_runtime(kill_processes=True)
                    _invalidate_web_status_cache()
                    _invalidate_key_status_cache()
                    del raw_batch
                    del valid_batch
                    gc.collect()
                if checked < total and probe_tasks:
                    time.sleep(POOL_PROBE_DELAY_SECONDS)
        except Exception as exc:
            _write_runtime_log(f'Ошибка фоновой проверки пула ключей: {exc}')
        finally:
            _invalidate_web_status_cache()
            _invalidate_key_status_cache()
            _set_pool_probe_progress(running=False, checked=checked, total=total, finished_at=time.time())
            pool_probe_lock.release()
            gc.collect()

    threading.Thread(target=worker, args=(selected, custom_checks), daemon=True).start()
    return True, len(selected)


def _probe_pool_keys_background(proto, keys, max_keys=KEY_PROBE_MAX_PER_RUN, stale_only=True):
    if POOL_PROBE_ACTIVE_ONLY:
        current_key = (_load_current_keys().get(proto) or '').strip()
        keys = [current_key] if current_key and current_key in (keys or []) else []
        stale_only = False
    return _queue_pool_key_probe(
        [(proto, key_value) for key_value in (keys or [])],
        max_keys=max_keys,
        stale_only=stale_only,
    )


def _add_keys_to_pool(proto, keys_text):
    pools = _load_key_pools()
    if proto not in pools:
        pools[proto] = []
    new_keys = [line.strip() for line in (keys_text or '').splitlines() if line.strip()]
    added_keys = []
    for key_value in new_keys:
        if key_value not in pools[proto]:
            pools[proto].append(key_value)
            added_keys.append(key_value)
    _save_key_pools(pools)
    _probe_pool_keys_background(proto, added_keys)
    _invalidate_web_status_cache()
    _invalidate_key_status_cache()
    return len(added_keys)


def _web_probe_state(probe, key):
    if not probe or key not in probe:
        return 'unknown'
    return 'ok' if probe.get(key) else 'fail'


def _web_probe_checked_at(probe):
    try:
        ts = float((probe or {}).get('ts', 0))
    except (TypeError, ValueError):
        ts = 0
    if not ts:
        return ''
    return time.strftime('%d.%m %H:%M', time.localtime(ts))


def _web_custom_probe_states(probe, custom_checks=None):
    custom = (probe or {}).get('custom', {})
    if not isinstance(custom, dict):
        custom = {}
    result = {}
    for check in (custom_checks if custom_checks is not None else _load_custom_checks()):
        check_id = check.get('id')
        if not check_id:
            continue
        if check_id in custom:
            result[check_id] = 'ok' if custom.get(check_id) else 'fail'
        else:
            result[check_id] = 'unknown'
    return result


def _web_custom_checks():
    return [
        {
            'id': check.get('id', ''),
            'label': check.get('label', ''),
            'url': check.get('url', ''),
            'urls': check.get('urls') or [check.get('url', '')],
            'badge': check.get('badge', 'WEB'),
            'icon': check.get('icon', ''),
        }
        for check in _load_custom_checks()
    ]


def _web_custom_check_badges(probe, custom_checks=None):
    checks = custom_checks if custom_checks is not None else _load_custom_checks()
    if not checks:
        return ''
    states = _web_custom_probe_states(probe, checks)
    badges = []
    for check in checks:
        state = states.get(check.get('id'), 'unknown')
        safe_label = html.escape(check.get('label', 'Проверка'))
        safe_url = html.escape(_custom_check_url_text(check))
        badges.append(
            f'<span class="custom-service-slot custom-service-{state}" title="{safe_label}: {safe_url}">{_custom_check_status_icon_html(check, state)}</span>'
        )
    return ''.join(badges)


def _custom_check_url_text(check):
    urls = check.get('urls') if isinstance(check.get('urls'), list) else [check.get('url', '')]
    labels = []
    for url in urls:
        if not url:
            continue
        parsed = urlparse(url)
        label = parsed.netloc or url
        if parsed.path and parsed.path != '/':
            label += parsed.path
        labels.append(label)
    return ', '.join(labels)


def _custom_check_icon_html(check):
    if check.get('icon'):
        return f'<span class="preset-icon">{_service_icon_html(check.get("icon"), check.get("label", "Service"), opacity=1.0, size=20)}</span>'
    return f'<span class="custom-service-badge custom-service-neutral">{html.escape(check.get("badge", "WEB"))}</span>'


def _custom_check_status_icon_html(check, state):
    if state == 'ok':
        return _service_icon_html(check.get('icon'), check.get('label', 'Service'), opacity=1.0, size=18)
    if state == 'fail':
        return '<span class="service-probe-mark service-probe-fail">✕</span>'
    return '<span class="service-probe-mark service-probe-unknown">?</span>'


def _custom_check_header_icons(custom_checks=None):
    checks = custom_checks if custom_checks is not None else _load_custom_checks()
    icons = []
    for check in checks:
        label = check.get('label', 'Service')
        safe_label = html.escape(label)
        if check.get('icon'):
            content = _service_icon_html(check.get('icon'), label, opacity=1.0, size=16)
        else:
            content = f'<span class="custom-service-badge custom-service-neutral">{html.escape(check.get("badge", "WEB"))}</span>'
        icons.append(f'<span class="custom-service-slot custom-service-header" title="{safe_label}">{content}</span>')
    return ''.join(icons)


def _web_custom_checks_html(checks=None):
    checks = checks if checks is not None else _load_custom_checks()
    if not checks:
        return '<div class="custom-check-empty">Дополнительные проверки пока не добавлены.</div>'
    items = []
    for check in checks:
        safe_id = html.escape(check.get('id', ''))
        safe_label = html.escape(check.get('label', 'Проверка'))
        safe_url = html.escape(_custom_check_url_text(check))
        icon_html = _custom_check_icon_html(check)
        items.append(f'''<div class="custom-check-item">
            {icon_html}
            <span class="custom-check-copy"><strong>{safe_label}</strong><small>{safe_url}</small></span>
            <form method="post" action="/custom_check_delete" data-async-action="custom-check-delete" data-confirm-title="Удалить проверку?" data-confirm-message="Удалить дополнительную проверку {safe_label}?">
                <input type="hidden" name="id" value="{safe_id}">
                <button type="submit" class="pool-delete-btn" title="Удалить проверку">Удалить</button>
            </form>
        </div>''')
    return ''.join(items)


def _web_custom_presets_html(checks=None):
    checks = checks if checks is not None else _load_custom_checks()
    active_ids = {check.get('id') for check in checks}
    items = []
    for preset in _custom_check_presets():
        safe_id = html.escape(preset['id'])
        safe_label = html.escape(preset['label'])
        safe_url = html.escape(preset.get('url', ''))
        icon_html = _custom_check_icon_html(preset)
        disabled = ' disabled' if preset['id'] in active_ids else ''
        title = 'Уже добавлено' if disabled else f'Добавить проверку {safe_label}'
        items.append(f'''<form method="post" action="/custom_check_add" data-async-action="custom-check-add">
            <input type="hidden" name="preset" value="{safe_id}">
            <input type="hidden" name="label" value="{safe_label}">
            <input type="hidden" name="url" value="{safe_url}">
            <button type="submit" class="service-preset-btn"{disabled} data-custom-preset="{safe_id}" title="{html.escape(title)}">
                {icon_html}
                <span>{safe_label}</span>
            </button>
        </form>''')
    return ''.join(items)


def _web_pool_snapshot(current_keys=None, include_keys=False):
    current_keys = current_keys if current_keys is not None else _load_current_keys()
    pools = _ensure_current_keys_in_pools(current_keys)
    cache = _load_key_probe_cache()
    custom_checks = _load_custom_checks()
    result = {}
    for proto in POOL_PROTOCOL_ORDER:
        current_key = current_keys.get(proto, '')
        rows = []
        for index, key_value in enumerate(pools.get(proto, []) or [], start=1):
            probe = cache.get(_hash_key(key_value), {})
            row = {
                'index': index,
                'key_id': _hash_key(key_value)[:12],
                'display_name': _pool_key_display_name(key_value),
                'active': bool(current_key and key_value == current_key),
                'tg': _web_probe_state(probe, 'tg_ok'),
                'yt': _web_probe_state(probe, 'yt_ok'),
                'custom': _web_custom_probe_states(probe, custom_checks),
                'checked_at': _web_probe_checked_at(probe),
            }
            if include_keys:
                row['key'] = key_value
            rows.append(row)
        result[proto] = {
            'label': _pool_proto_label(proto),
            'count': len(rows),
            'rows': rows,
        }
    return result


def _check_local_proxy_endpoint(key_type, port):
    if key_type in ['shadowsocks', 'vmess', 'vless', 'vless2', 'trojan']:
        if _wait_for_socks5_handshake(port, timeout=3):
            return True, f'Локальный SOCKS-порт 127.0.0.1:{port} отвечает как SOCKS5.'
        if _port_is_listening(port):
            return False, f'Локальный порт 127.0.0.1:{port} открыт, но не отвечает как SOCKS5.'
        return False, f'Локальный порт 127.0.0.1:{port} недоступен.'
    return True, ''


def _shadowsocks_runtime_mode():
    init_script = _read_text_file('/opt/etc/init.d/S22shadowsocks')
    if 'PROCS=ss-redir' in init_script or 'ss-redir' in init_script:
        return 'redir'
    if 'PROCS=ss-local' in init_script or 'ss-local' in init_script:
        return 'socks'
    return 'unknown'


def _apply_installed_proxy(key_type, key_value, verify=True):
    settings = {
        'shadowsocks': {
            'label': 'Shadowsocks',
            'port': localportsh_bot,
            'restart_cmds': ['/opt/etc/init.d/S22shadowsocks restart', CORE_PROXY_SERVICE_SCRIPT + ' restart'],
            'startup_wait': 8,
        },
        'vmess': {
            'label': 'Vmess',
            'port': localportvmess,
            'restart_cmds': [CORE_PROXY_SERVICE_SCRIPT + ' restart'],
            'startup_wait': 18,
        },
        'vless': {
            'label': 'Vless 1',
            'port': localportvless,
            'restart_cmds': [CORE_PROXY_SERVICE_SCRIPT + ' restart'],
            'startup_wait': 18,
        },
        'vless2': {
            'label': 'Vless 2',
            'port': localportvless2,
            'restart_cmds': [CORE_PROXY_SERVICE_SCRIPT + ' restart'],
            'startup_wait': 18,
        },
        'trojan': {
            'label': 'Trojan',
            'port': localporttrojan_bot,
            'restart_cmds': ['/opt/etc/init.d/S22trojan restart', CORE_PROXY_SERVICE_SCRIPT + ' restart'],
            'startup_wait': 8,
        }
    }
    current = settings[key_type]
    active_mode = _load_proxy_mode()
    active_label = _proxy_mode_label(active_mode)
    for command in current['restart_cmds']:
        os.system(command)
    time.sleep(current['startup_wait'])

    diagnostics = _build_proxy_diagnostics(key_type, key_value)
    restart_cmd = current['restart_cmds'][-1]
    if not _ensure_service_port(current['port'], restart_cmd, retries=2, sleep_after_restart=5):
        return (f'⚠️ {current["label"]} ключ сохранён, но локальный порт 127.0.0.1:{current["port"]} '
                f'не поднялся. Текущий режим бота {active_label} сохранён. {diagnostics}').strip()

    endpoint_ok, endpoint_message = _check_local_proxy_endpoint(key_type, current['port'])
    if not endpoint_ok:
        return (f'⚠️ {current["label"]} ключ сохранён, но {endpoint_message} '
                f'Текущий режим бота {active_label} сохранён. {diagnostics}').strip()

    if not verify:
        return (f'✅ {current["label"]} ключ сохранён. {endpoint_message} '
                'Проверка Telegram API и YouTube выполняется в фоне; '
                f'статус обновится без перезагрузки страницы. Текущий режим бота {active_label} сохранён.').strip()

    api_ok, api_probe_message = _check_telegram_api_through_proxy(
        proxy_settings.get(key_type),
        connect_timeout=10,
        read_timeout=15,
    )
    yt_ok, _ = _check_http_through_proxy(proxy_settings.get(key_type), url='https://www.youtube.com', connect_timeout=3, read_timeout=5)
    _record_key_probe(key_type, key_value, tg_ok=api_ok, yt_ok=yt_ok)
    if api_ok:
        return (f'✅ {current["label"]} ключ сохранён. {endpoint_message} '
                f'Доступ к Telegram API через этот ключ подтверждён. '
                f'Текущий режим бота {active_label} сохранён.').strip()
    return (f'⚠️ {current["label"]} ключ сохранён. {endpoint_message} '
            f'Но Telegram API не проходит через этот ключ. '
            f'Текущий режим бота {active_label} сохранён. '
            f'❌ Не удалось подключиться к Telegram API: {api_probe_message} {diagnostics}').strip()


def update_proxy(proxy_type, persist=True):
    global proxy_mode
    proxy_url = proxy_settings.get(proxy_type)
    if proxy_url and proxy_url.startswith('socks') and not _has_socks_support():
        return False, ('Для SOCKS-прокси требуется модуль PySocks. '
                       'Установите python3-pysocks или выберите другой режим.')

    proxy_mode = proxy_type
    if proxy_supports_http.get(proxy_type, False) and proxy_url:
        telebot.apihelper.proxy = {'https': proxy_url, 'http': proxy_url}
        os.environ['HTTPS_PROXY'] = proxy_url
        os.environ['HTTP_PROXY'] = proxy_url
        os.environ['https_proxy'] = proxy_url
        os.environ['http_proxy'] = proxy_url
    else:
        telebot.apihelper.proxy = {}
        for key in ['HTTPS_PROXY', 'HTTP_PROXY', 'https_proxy', 'http_proxy']:
            if key in os.environ:
                del os.environ[key]

    if persist:
        _save_proxy_mode(proxy_type)
    _invalidate_web_status_cache()
    _invalidate_key_status_cache()
    return True, None


def check_telegram_api(retries=2, retry_delay=7, connect_timeout=30, read_timeout=45):
    last_result = None
    for attempt in range(retries + 1):
        proxy_url = proxy_settings.get(proxy_mode)
        ok, probe_message = _check_telegram_api_through_proxy(proxy_url, connect_timeout=connect_timeout, read_timeout=read_timeout)
        if ok:
            return '✅ Доступ к api.telegram.org подтверждён.'
        if 'PySocks' in probe_message:
            return ('❌ Не удалось подключиться к Telegram API: отсутствует поддержка SOCKS (PySocks). '
                    'Установите python3-pysocks или используйте режим без SOCKS.')
        if proxy_mode == 'none':
            last_result = f'❌ Прямой доступ к api.telegram.org не проходит: {probe_message}'
        else:
            last_result = f'❌ Доступ к Telegram API через режим {proxy_mode} не проходит: {probe_message}'
            if attempt < retries:
                time.sleep(retry_delay)
    return last_result


def _is_transient_telegram_api_failure(status_text):
    text = str(status_text or '').casefold()
    markers = [
        'network is unreachable',
        'timed out',
        'timeout',
        'таймаут',
        'не ответил вовремя',
        'за отведённое время',
        'за отведенное время',
        'max retries exceeded',
        'failed to establish a new connection',
        'connection reset',
    ]
    return any(marker in text for marker in markers)


def _build_web_status(current_keys, protocols=None):
    now = time.time()
    state_label = 'polling активен' if bot_polling else ('ожидает запуска' if not bot_ready else 'процесс запущен, polling недоступен')
    socks_details = ''
    socks_ok = False
    current_protocol = protocols.get(proxy_mode) if isinstance(protocols, dict) else None
    if current_protocol and proxy_mode in ['shadowsocks', 'vmess', 'vless', 'vless2', 'trojan']:
        socks_ok = bool(current_protocol.get('endpoint_ok'))
        socks_details = current_protocol.get('endpoint_message', '')
        api_ok = bool(current_protocol.get('api_ok'))
        api_message = str(current_protocol.get('api_message', '') or '')
        if api_ok:
            api_status = '✅ Доступ к api.telegram.org подтверждён.'
        elif socks_ok and _is_transient_telegram_api_failure(api_message):
            api_status = ('⏳ Telegram API не ответил вовремя через текущий режим. '
                          'Локальный SOCKS работает, идёт повторная проверка. '
                          'Статус обновится без перезагрузки страницы.')
        elif proxy_mode == 'none':
            api_status = f'❌ Прямой доступ к api.telegram.org не проходит: {api_message}'
        else:
            api_status = f'❌ Доступ к Telegram API через режим {proxy_mode} не проходит: {api_message}'
    elif proxy_mode in ['shadowsocks', 'vmess', 'vless', 'vless2', 'trojan']:
        port = {
            'shadowsocks': localportsh_bot,
            'vmess': localportvmess,
            'vless': localportvless,
            'vless2': localportvless2,
            'trojan': localporttrojan_bot,
        }.get(proxy_mode)
        if port:
            socks_ok = _check_socks5_handshake(port)
            socks_details = f'Локальный SOCKS {proxy_mode} 127.0.0.1:{port}: {"доступен" if socks_ok else "не отвечает как SOCKS5"}'
        api_status = check_telegram_api(retries=0, retry_delay=0, connect_timeout=5, read_timeout=8)
        if (proxy_mode != 'none' and socks_ok and not api_status.startswith('✅') and
                _is_transient_telegram_api_failure(api_status)):
            api_status = ('⏳ Telegram API не ответил вовремя через текущий режим. '
                          'Локальный SOCKS работает, идёт повторная проверка. '
                          'Статус обновится без перезагрузки страницы.')
    else:
        api_status = check_telegram_api(retries=0, retry_delay=0, connect_timeout=5, read_timeout=8)
    snapshot = {
        'state_label': state_label,
        'proxy_mode': proxy_mode,
        'api_status': api_status,
        'socks_details': socks_details,
        'fallback_reason': _last_proxy_disable_reason(),
    }
    return snapshot


def _status_snapshot_signature(current_keys):
    custom_signature = tuple((item.get('id'), item.get('url')) for item in _load_custom_checks())
    return (
        tuple((name, current_keys.get(name, '')) for name in sorted(current_keys)),
        custom_signature,
    )


def _build_status_snapshot(current_keys, force_refresh=False):
    signature = _status_snapshot_signature(current_keys)
    now = time.time()
    if pool_probe_lock.locked():
        return _active_mode_status_snapshot(current_keys)
    if (
        not force_refresh and
        status_snapshot_cache['data'] is not None and
        status_snapshot_cache['signature'] == signature and
        now - status_snapshot_cache['timestamp'] < STATUS_CACHE_TTL
    ):
        return status_snapshot_cache['data']

    custom_checks = _load_custom_checks()
    protocols = {}
    for key_name, key_value in current_keys.items():
        try:
            if key_name == proxy_mode:
                protocols[key_name] = _protocol_status_for_key(key_name, key_value)
            else:
                protocols[key_name] = _cached_protocol_status_for_key(key_name, key_value, custom_checks=custom_checks)
        except Exception as exc:
            _write_runtime_log(f'Ошибка проверки ключа {key_name}: {exc}')
            protocols[key_name] = {
                'tone': 'warn',
                'label': 'Ошибка проверки',
                'details': f'Не удалось завершить проверку ключа: {exc}',
            }

    snapshot = {
        'web': _build_web_status(current_keys, protocols=protocols),
        'protocols': protocols,
    }
    status_snapshot_cache['timestamp'] = now
    status_snapshot_cache['data'] = snapshot
    status_snapshot_cache['signature'] = signature
    return snapshot


def _active_mode_status_snapshot(current_keys):
    cached = _cached_status_snapshot(current_keys)
    if cached is not None and isinstance(cached, dict):
        protocols = dict(cached.get('protocols') or {})
    else:
        protocols = _placeholder_protocol_statuses(current_keys)

    if proxy_mode in current_keys:
        try:
            protocols[proxy_mode] = _protocol_status_for_key(proxy_mode, current_keys.get(proxy_mode, ''))
        except Exception as exc:
            _write_runtime_log(f'Ошибка быстрой проверки активного режима {proxy_mode}: {exc}')
            protocols[proxy_mode] = {
                'tone': 'warn',
                'label': 'Ошибка проверки',
                'details': f'Не удалось завершить быструю проверку активного режима: {exc}',
            }
    return {
        'web': _build_web_status(current_keys, protocols=protocols),
        'protocols': protocols,
    }


def _web_status_snapshot(force_refresh=False):
    current_keys = _load_current_keys()
    return _build_status_snapshot(current_keys, force_refresh=force_refresh)['web']


def _cached_status_snapshot(current_keys):
    now = time.time()
    signature = _status_snapshot_signature(current_keys)
    if (
        status_snapshot_cache['data'] is not None and
        status_snapshot_cache['signature'] == signature and
        now - status_snapshot_cache['timestamp'] < STATUS_CACHE_TTL
    ):
        return status_snapshot_cache['data']
    return None


def _placeholder_web_status_snapshot():
    return {
        'state_label': 'polling активен' if bot_polling else ('ожидает запуска' if not bot_ready else 'процесс запущен, polling недоступен'),
        'proxy_mode': proxy_mode,
        'api_status': '⏳ Проверяется связь текущего режима. Статус обновится без перезагрузки страницы.',
        'socks_details': '',
        'fallback_reason': _last_proxy_disable_reason(),
    }


def _protocol_status_snapshot(current_keys, force_refresh=False):
    return _build_status_snapshot(current_keys, force_refresh=force_refresh)['protocols']


def _cached_protocol_status_snapshot(current_keys):
    snapshot = _cached_status_snapshot(current_keys)
    if snapshot is not None:
        return snapshot['protocols']
    return None


def _refresh_status_caches_async(current_keys):
    if pool_probe_lock.locked():
        return
    signature = _status_snapshot_signature(current_keys)
    with status_refresh_lock:
        if signature in status_refresh_in_progress:
            return
        status_refresh_in_progress.add(signature)

    def worker():
        try:
            _build_status_snapshot(current_keys, force_refresh=True)
        except Exception as exc:
            _write_runtime_log(f'Ошибка фонового обновления статусов: {exc}')
        finally:
            with status_refresh_lock:
                status_refresh_in_progress.discard(signature)

    threading.Thread(target=worker, daemon=True).start()


def _probe_all_pool_keys_async(stale_only=True, max_keys=KEY_PROBE_MAX_PER_RUN, missing_only=False):
    """Запускает безопасную фоновую проверку пула через временный xray."""
    if POOL_PROBE_ACTIVE_ONLY:
        active_proto = proxy_mode if proxy_mode in POOL_PROTOCOL_ORDER else ''
        active_key = (_load_current_keys().get(active_proto, '') if active_proto else '').strip()
        tasks = [(active_proto, active_key)] if active_proto and active_key else []
        return _queue_pool_key_probe(tasks, max_keys=1, stale_only=False)
    pools = _load_key_pools()
    tasks = [
        (proto, key_value)
        for proto in POOL_PROTOCOL_ORDER
        for key_value in (pools.get(proto, []) or [])
    ]
    return _queue_pool_key_probe(tasks, max_keys=max_keys, stale_only=stale_only, missing_only=missing_only)


def _probe_pool_keys_on_page_load():
    """Refresh only stale or missing pool statuses on page open."""
    global pool_probe_last_auto_started_at

    if POOL_PROBE_PAGE_REFRESH_INTERVAL <= 0:
        return False, 0

    now = time.time()
    progress = _get_pool_probe_progress()
    recent_probe_at = max(float(progress.get('started_at') or 0), float(progress.get('finished_at') or 0))
    if progress.get('running') or (recent_probe_at and now - recent_probe_at < POOL_PROBE_PAGE_REFRESH_INTERVAL):
        return False, 0

    with pool_probe_auto_lock:
        if now - pool_probe_last_auto_started_at < POOL_PROBE_PAGE_REFRESH_INTERVAL:
            return False, 0
        pool_probe_last_auto_started_at = now

    started, queued = _probe_all_pool_keys_async(
        stale_only=False,
        max_keys=POOL_PROBE_PAGE_MAX_KEYS,
        missing_only=True,
    )
    if started or queued:
        return started, queued
    return False, 0


def _authorize_callback(call, handler_name):
    proxy = type('CallbackMessageProxy', (), {})()
    proxy.from_user = getattr(call, 'from_user', None)
    proxy.chat = getattr(getattr(call, 'message', None), 'chat', None)
    proxy.text = getattr(call, 'data', '')
    return _authorize_message(proxy, handler_name)


# список смайлов для меню
#  ✅ ❌ ♻️ 📃 📆 🔑 📄 ❗ ️⚠️ ⚙️ 📝 📆 🗑 📄️⚠️ 🔰 ❔ ‼️ 📑
@bot.message_handler(commands=['start'])
def start(message):
    authorized, reason = _authorize_message(message, 'start')
    if not authorized:
        _send_unauthorized_message(message, reason)
        return
    _set_chat_menu_state(message.chat.id, level=0, bypass=None)
    markup = _build_main_menu_markup()
    bot.send_message(message.chat.id, '✅ Добро пожаловать в меню!', reply_markup=markup)


@bot.callback_query_handler(func=lambda call: bool((getattr(call, 'data', '') or '').startswith('pool:')))
def pool_callback(call):
    try:
        authorized, reason = _authorize_callback(call, 'pool_callback')
        if not authorized:
            bot.answer_callback_query(call.id, 'Нет доступа', show_alert=True)
            return

        data = (call.data or '').split(':')
        action = data[1] if len(data) > 1 else ''
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        _clear_pool_inline_keyboard(chat_id, message_id)

        if action == 'protocols':
            _set_chat_menu_state(chat_id, level=20, bypass=None)
            _clear_pool_page(chat_id)
            bot.answer_callback_query(call.id, 'Кнопки перенесены вниз')
            bot.send_message(chat_id, _format_pool_summary(), reply_markup=_pool_protocol_markup())
            return

        if action == 'keys-menu':
            _set_chat_menu_state(chat_id, level=8, bypass=None)
            _clear_pool_page(chat_id)
            bot.answer_callback_query(call.id, 'Открыто меню ключей')
            bot.send_message(chat_id, '🔑 Ключи и мосты', reply_markup=_build_keys_menu_markup())
            return

        if action == 'select' and len(data) >= 3:
            proto = _resolve_pool_protocol(data[2])
            if not proto:
                raise ValueError('Неизвестный протокол.')
            _set_chat_menu_state(chat_id, level=21, bypass=proto)
            bot.answer_callback_query(call.id, f'Открыт пул {_pool_proto_label(proto)}')
            _send_pool_page(chat_id, proto, page=0)
            return

        if len(data) < 3:
            raise ValueError('Некорректная команда пула.')

        proto = _resolve_pool_protocol(data[2])
        if not proto:
            raise ValueError('Неизвестный протокол.')

        if action == 'page':
            page = data[3] if len(data) > 3 else 0
            _set_chat_menu_state(chat_id, level=21, bypass=proto)
            bot.answer_callback_query(call.id)
            _send_pool_page(chat_id, proto, page=page)
            return

        if action == 'add':
            _set_chat_menu_state(chat_id, level=22, bypass=proto)
            bot.answer_callback_query(call.id)
            bot.send_message(
                chat_id,
                f'Отправьте один или несколько ключей для пула {_pool_proto_label(proto)}. Каждый ключ с новой строки.',
                reply_markup=_pool_input_markup(),
            )
            return

        if action == 'subscribe':
            _set_chat_menu_state(chat_id, level=23, bypass=proto)
            bot.answer_callback_query(call.id)
            bot.send_message(
                chat_id,
                f'Отправьте subscription URL для пула {_pool_proto_label(proto)}.',
                reply_markup=_pool_input_markup(),
            )
            return

        if action == 'probe':
            page = data[3] if len(data) > 3 else 0
            started, queued = _probe_pool_keys_background(proto, _pool_keys_for_proto(proto), stale_only=False)
            bot.answer_callback_query(call.id, 'Проверка запущена' if started else 'Проверка уже выполняется')
            _set_chat_menu_state(chat_id, level=21, bypass=proto)
            prefix = (
                f'Запущена безопасная фоновая проверка пула. В очереди: {queued}. Ключи проверяются по одному с паузой, чтобы не перегружать память роутера.'
                if started else
                'Проверка пула уже выполняется. Дождитесь обновления статусов.'
            )
            _send_pool_page(chat_id, proto, page=page, prefix=prefix)
            return

        if action == 'clear-confirm':
            page = data[3] if len(data) > 3 else 0
            _set_chat_menu_state(chat_id, level=26, bypass=proto)
            _set_pool_page(chat_id, page)
            bot.answer_callback_query(call.id)
            bot.send_message(
                chat_id,
                f'Очистить весь пул {_pool_proto_label(proto)}? Это удалит все ключи из пула.',
                reply_markup=_pool_clear_confirm_markup(),
            )
            return

        if action == 'clear':
            page = data[3] if len(data) > 3 else 0
            removed = _clear_pool(proto)
            bot.answer_callback_query(call.id, 'Пул очищен')
            _set_chat_menu_state(chat_id, level=21, bypass=proto)
            _send_pool_page(chat_id, proto, page=page, prefix=f'Пул {_pool_proto_label(proto)} очищен. Удалено ключей: {removed}.')
            return

        if action in ('apply', 'delete') and len(data) >= 5:
            key_id = data[3]
            page = data[4]
            index, key_value = _pool_key_by_callback_id(proto, key_id)
            if action == 'apply':
                bot.answer_callback_query(call.id, f'Применяю ключ #{index}...')
                _set_chat_menu_state(chat_id, level=21, bypass=proto)
                bot.send_message(
                    chat_id,
                    f'Применяю ключ #{index} для {_pool_proto_label(proto)}. Это может занять до 30 секунд.',
                    reply_markup=_pool_action_markup(proto, page),
                )
                _apply_pool_key_background(chat_id, proto, key_value, index, page=page)
            else:
                _delete_pool_key(proto, key_value)
                bot.answer_callback_query(call.id, f'Ключ #{index} удалён')
                _set_chat_menu_state(chat_id, level=21, bypass=proto)
                _send_pool_page(chat_id, proto, page=page, prefix=f'Ключ #{index} удалён из пула {_pool_proto_label(proto)}.')
            return

        raise ValueError('Неизвестная команда пула.')
    except Exception as exc:
        _write_runtime_log(f'Ошибка callback пула ключей: {exc}')
        try:
            bot.answer_callback_query(call.id, f'Ошибка: {exc}', show_alert=True)
        except Exception:
            pass


@bot.message_handler(content_types=['text'])
def bot_message(message):
    try:
        authorized, reason = _authorize_message(message, 'text')
        if not authorized:
            _send_unauthorized_message(message, reason)
            return

        main = types.ReplyKeyboardMarkup(resize_keyboard=True)
        m1 = types.KeyboardButton("🔰 Установка и удаление")
        m2 = types.KeyboardButton("🔑 Ключи и мосты")
        m3 = types.KeyboardButton("📝 Списки обхода")
        m4 = types.KeyboardButton("📄 Информация")
        m5 = types.KeyboardButton("⚙️ Сервис")
        main.add(m1)
        main.add(m2, m3)
        main.add(m4, m5)

        service = types.ReplyKeyboardMarkup(resize_keyboard=True)
        m1 = types.KeyboardButton("♻️ Перезагрузить сервисы")
        m2 = types.KeyboardButton("‼️Перезагрузить роутер")
        m3 = types.KeyboardButton("‼️DNS Override")
        m4 = types.KeyboardButton("📊 Статус ключей")
        back = types.KeyboardButton("🔙 Назад")
        service.add(m1, m2)
        service.add(m3, m4)
        service.add(back)

        if message.chat.type == 'private':
            command = message.text.split(maxsplit=1)[0].split('@', 1)[0]
            if command == '/getlist':
                parts = message.text.split()
                if len(parts) < 2:
                    names = ', '.join(source['label'] for source in SERVICE_LIST_SOURCES.values())
                    bot.send_message(message.chat.id, f'Использование: /getlist название [маршрут]\nДоступно: {names}', reply_markup=main)
                    return
                route_name = parts[2] if len(parts) > 2 else None
                _handle_getlist_request(message, parts[1], route_name=route_name, reply_markup=main)
                return

            if message.text == '📊 Статус ключей':
                text_lines = ['<b>Статус доступа к Telegram по ключам (web):</b>']
                emoji = {'ok': '✅', 'warn': '⚠️', 'fail': '❌', 'empty': '➖'}
                proto_labels = {
                    'shadowsocks': 'Shadowsocks',
                    'vmess': 'Vmess',
                    'vless': 'Vless 1',
                    'vless2': 'Vless 2',
                    'trojan': 'Trojan',
                }
                try:
                    current_keys = _load_current_keys()
                    snapshot = _build_status_snapshot(current_keys, force_refresh=True)
                    statuses = snapshot.get('protocols', {}) if isinstance(snapshot, dict) else {}
                except Exception as exc:
                    statuses = {}
                    text_lines.append(f'❌ Ошибка получения статуса: {html.escape(str(exc))}')
                for proto in ['shadowsocks', 'vmess', 'vless', 'vless2', 'trojan']:
                    st = statuses.get(proto, {}) if isinstance(statuses, dict) else {}
                    mark = emoji.get(st.get('tone', 'empty'), '➖')
                    label = proto_labels.get(proto, proto)
                    status = st.get('label', 'Нет данных')
                    status_text = html.unescape(status).replace('\xa0', ' ')
                    has_telegram_icon = '<img' in status or 'Telegram' in status_text
                    # Удаляем HTML-теги из статуса: Telegram-сообщение не поддерживает <img>.
                    status_clean = re.sub(r'<[^>]+>', '', status_text).strip()
                    if has_telegram_icon and 'Telegram' not in status_clean:
                        status_clean = f'{status_clean} 📱 Telegram'
                    details = st.get('details', '')
                    text_lines.append(f"{mark} <b>{label}</b>: {status_clean}")
                    if details:
                        text_lines.append(f"<i>{details}</i>")
                bot.send_message(message.chat.id, '\n'.join(text_lines), parse_mode='HTML', reply_markup=service)
                return

            if message.text in ('📦 Пул ключей', '/pool'):
                _set_chat_menu_state(message.chat.id, level=20, bypass=None)
                _clear_pool_inline_keyboard(message.chat.id)
                _clear_pool_page(message.chat.id)
                bot.send_message(message.chat.id, _format_pool_summary(), reply_markup=_pool_protocol_markup())
                return

        if message.chat.type == 'private':

            state = _get_chat_menu_state(message.chat.id)
            level = state['level']
            bypass = state['bypass']

            def set_menu_state(new_level=MENU_STATE_UNSET, new_bypass=MENU_STATE_UNSET):
                nonlocal level, bypass
                if new_level is not MENU_STATE_UNSET:
                    level = new_level
                if new_bypass is not MENU_STATE_UNSET:
                    bypass = new_bypass
                _set_chat_menu_state(message.chat.id, level=level, bypass=bypass)

            if level == TELEGRAM_CONFIRM_LEVEL:
                if message.text == '✅ Подтвердить':
                    action = bypass
                    set_menu_state(0, None)
                    _execute_confirmed_telegram_action(message.chat.id, action, service)
                    return
                if message.text in ('Отмена', '🔙 Назад', 'Назад'):
                    set_menu_state(0, None)
                    bot.send_message(message.chat.id, 'Действие отменено.', reply_markup=service)
                    return
                bot.send_message(message.chat.id, _telegram_confirm_prompt(bypass), reply_markup=_build_telegram_confirm_markup())
                return

            if message.text == '⚙️ Сервис':
                bot.send_message(message.chat.id, '⚙️ Сервисное меню!', reply_markup=service)
                return

            if message.text == '♻️ Перезагрузить сервисы' or message.text == 'Перезагрузить сервисы':
                set_menu_state(TELEGRAM_CONFIRM_LEVEL, 'restart_services')
                bot.send_message(message.chat.id, _telegram_confirm_prompt('restart_services'), reply_markup=_build_telegram_confirm_markup())
                return

            if message.text == '‼️Перезагрузить роутер' or message.text == 'Перезагрузить роутер':
                set_menu_state(TELEGRAM_CONFIRM_LEVEL, 'reboot')
                bot.send_message(message.chat.id, _telegram_confirm_prompt('reboot'), reply_markup=_build_telegram_confirm_markup())
                return

            if message.text == '‼️DNS Override' or message.text == 'DNS Override':
                service = types.ReplyKeyboardMarkup(resize_keyboard=True)
                m1 = types.KeyboardButton("✅ DNS Override ВКЛ")
                m2 = types.KeyboardButton("❌ DNS Override ВЫКЛ")
                back = types.KeyboardButton("🔙 Назад")
                service.add(m1, m2)
                service.add(back)
                bot.send_message(message.chat.id, '‼️DNS Override!', reply_markup=service)
                return

            if message.text == "✅ DNS Override ВКЛ" or message.text == "❌ DNS Override ВЫКЛ":
                if message.text == "✅ DNS Override ВКЛ":
                    set_menu_state(TELEGRAM_CONFIRM_LEVEL, 'dns_on')
                    bot.send_message(message.chat.id, _telegram_confirm_prompt('dns_on'), reply_markup=_build_telegram_confirm_markup())
                    return

                if message.text == "❌ DNS Override ВЫКЛ":
                    set_menu_state(TELEGRAM_CONFIRM_LEVEL, 'dns_off')
                    bot.send_message(message.chat.id, _telegram_confirm_prompt('dns_off'), reply_markup=_build_telegram_confirm_markup())
                    return

            # Кнопка "Обновление" убрана из меню "Сервис" (заменена на "Статус ключей").

            if message.text == '📄 Информация':
                info_bot = _telegram_info_text_from_readme()
                bot.send_message(
                    message.chat.id,
                    info_bot,
                    parse_mode='HTML',
                    disable_web_page_preview=True,
                    reply_markup=main,
                )
                return

            if message.text == '/keys_free':
                url = _raw_github_url('keys.md')
                try:
                    keys_free = _fetch_remote_text(url)
                except requests.RequestException as exc:
                    bot.send_message(message.chat.id, f'⚠️ Не удалось загрузить список ключей: {exc}', reply_markup=main)
                    return
                bot.send_message(message.chat.id, keys_free, parse_mode='Markdown', disable_web_page_preview=True)
                return

            if message.text == '🔄 Обновления' or message.text == '/check_update':
                url = _raw_github_url('version.md')
                try:
                    bot_new_version = _fetch_remote_text(url)
                except requests.RequestException as exc:
                    bot.send_message(message.chat.id, f'⚠️ Не удалось проверить обновления: {exc}', reply_markup=service)
                    return
                bot_version = _current_bot_version()
                service_bot_version = "*ВАША ТЕКУЩАЯ " + str(bot_version) + "*\n\n"
                service_new_version = "*ПОСЛЕДНЯЯ ДОСТУПНАЯ ВЕРСИЯ:*\n\n" + str(bot_new_version)
                service_update_info = service_bot_version + service_new_version
                # bot.send_message(message.chat.id, service_bot_version, parse_mode='Markdown', reply_markup=service)
                bot.send_message(message.chat.id, service_update_info, parse_mode='Markdown', reply_markup=service)

                service_update_msg = "Если вы хотите обновить текущую версию на более новую, нажмите сюда /update"
                bot.send_message(message.chat.id, service_update_msg, parse_mode='Markdown', reply_markup=service)
                return

            if message.text == '/update':
                started, status_message = _start_telegram_background_command(
                    '-update',
                    fork_repo_owner,
                    fork_repo_name,
                    message.chat.id,
                    'service',
                )
                if not started:
                    bot.send_message(message.chat.id, status_message, reply_markup=service)
                    return
                bot.send_message(
                    message.chat.id,
                    f'Запускаю обновление из форка {fork_repo_owner}/{fork_repo_name}. Обычно это занимает 1-3 минуты. '
                    'Во время обновления бот может временно пропасть из сети, потому что сервис будет перезапущен. '
                    'После запуска бот сам пришлет в этот чат лог и итоговое сообщение.',
                    reply_markup=service,
                )
                return

            if message.text == "📥 Сервисы по запросу":
                if level == 2 and bypass:
                    set_menu_state(10)
                    bot.send_message(message.chat.id, f'Выберите сервис для маршрута {_list_label(bypass + ".txt")}', reply_markup=_service_list_markup())
                else:
                    set_menu_state(10, 'vless')
                    bot.send_message(message.chat.id, 'Выберите сервис. По умолчанию список будет добавлен в маршрут Vless 1.', reply_markup=_service_list_markup())
                return

            if message.text == '🔙 Назад' or message.text == "Назад":
                _clear_pool_inline_keyboard(message.chat.id)
                _clear_pool_page(message.chat.id)
                bot.send_message(message.chat.id, '✅ Добро пожаловать в меню!', reply_markup=main)
                set_menu_state(0, None)
                return

            if level == 1:
                # значит это список обхода блокировок
                selected_list = _resolve_unblock_list_selection(message.text)
                dirname = '/opt/etc/unblock/'
                dirfiles = os.listdir(dirname)

                for fln in dirfiles:
                    if fln == selected_list + '.txt':
                        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                        item1 = types.KeyboardButton("📑 Показать список")
                        item2 = types.KeyboardButton("📝 Добавить в список")
                        item3 = types.KeyboardButton("🗑 Удалить из списка")
                        item4 = types.KeyboardButton("📥 Сервисы по запросу")
                        back = types.KeyboardButton("🔙 Назад")
                        markup.row(item1, item2, item3)
                        markup.row(item4)
                        markup.row(back)
                        set_menu_state(2, selected_list)
                        bot.send_message(message.chat.id, "Меню " + _list_label(fln), reply_markup=markup)
                        return

                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                back = types.KeyboardButton("🔙 Назад")
                markup.add(back)
                bot.send_message(message.chat.id, "Не найден", reply_markup=markup)
                return

            if level == 2 and message.text == "📑 Показать список":
                try:
                    sites = sorted(_read_unblock_list_entries(bypass))
                except FileNotFoundError:
                    bot.send_message(message.chat.id, '⚠️ Файл списка не найден. Откройте список заново.', reply_markup=main)
                    set_menu_state(1, None)
                    return
                s = 'Список пуст'
                if sites:
                    s = '\n'.join(sites)
                if len(s) > 4096:
                    for x in range(0, len(s), 4096):
                        bot.send_message(message.chat.id, s[x:x + 4096])
                else:
                    bot.send_message(message.chat.id, s)
                #bot.send_message(message.chat.id, s)
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                item1 = types.KeyboardButton("📑 Показать список")
                item2 = types.KeyboardButton("📝 Добавить в список")
                item3 = types.KeyboardButton("🗑 Удалить из списка")
                item4 = types.KeyboardButton("📥 Сервисы по запросу")
                back = types.KeyboardButton("🔙 Назад")
                markup.row(item1, item2, item3)
                markup.row(item4)
                markup.row(back)
                bot.send_message(message.chat.id, "Меню " + bypass, reply_markup=markup)
                return

            if level == 2 and message.text == "📥 Сервисы по запросу":
                set_menu_state(10)
                bot.send_message(message.chat.id, f'Выберите сервис для маршрута {_list_label(bypass + ".txt")}', reply_markup=_service_list_markup())
                return

            if level == 2 and message.text == "📝 Добавить в список":
                bot.send_message(message.chat.id,
                                 "Введите имя сайта или домена для разблокировки, "
                                 "либо воспользуйтесь меню для других действий")
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                item1 = types.KeyboardButton("Добавить обход блокировок соцсетей")
                back = types.KeyboardButton("🔙 Назад")
                markup.add(item1, back)
                set_menu_state(3)
                bot.send_message(message.chat.id, "Меню " + bypass, reply_markup=markup)
                return

            if level == 2 and message.text == "🗑 Удалить из списка":
                bot.send_message(message.chat.id,
                                 "Введите имя сайта или домена для удаления из листа разблокировки,"
                                 "либо возвратитесь в главное меню")
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                item1 = types.KeyboardButton("Удалить обход блокировок соцсетей")
                back = types.KeyboardButton("🔙 Назад")
                markup.add(item1, back)
                set_menu_state(4)
                bot.send_message(message.chat.id, "Меню " + bypass, reply_markup=markup)
                return

            if level == 3:
                try:
                    mylist = set(_read_unblock_list_entries(bypass))
                except FileNotFoundError:
                    bot.send_message(message.chat.id, '⚠️ Файл списка не найден. Откройте список заново.', reply_markup=main)
                    set_menu_state(1, None)
                    return
                k = len(mylist)
                if message.text == "Добавить обход блокировок соцсетей":
                    set_menu_state(31)
                    bot.send_message(message.chat.id, f'Выберите соцсеть для добавления в {_list_label(bypass + ".txt")}.', reply_markup=_socialnet_service_markup())
                    return
                else:
                    if len(message.text) > 1:
                        mas = message.text.split('\n')
                        for site in mas:
                            mylist.add(site)
                sortlist = sorted(mylist)
                _write_unblock_list_entries(bypass, sortlist)
                if k != len(sortlist):
                    bot.send_message(message.chat.id, "✅ Успешно добавлено")
                else:
                    bot.send_message(message.chat.id, "Было добавлено ранее")
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                item1 = types.KeyboardButton("📑 Показать список")
                item2 = types.KeyboardButton("📝 Добавить в список")
                item3 = types.KeyboardButton("🗑 Удалить из списка")
                item4 = types.KeyboardButton("📥 Сервисы по запросу")
                back = types.KeyboardButton("🔙 Назад")
                markup.row(item1, item2, item3)
                markup.row(item4)
                markup.row(back)
                subprocess.run(["/opt/bin/unblock_update.sh"], check=False)
                set_menu_state(2)
                bot.send_message(message.chat.id, "Меню " + bypass, reply_markup=markup)
                return

            if level == 31:
                if message.text in ('🔙 Назад', 'Назад'):
                    set_menu_state(2)
                    bot.send_message(message.chat.id, "Меню " + bypass, reply_markup=_list_actions_markup())
                    return
                service_key = _resolve_socialnet_service(message.text)
                try:
                    result = _append_socialnet_list(bypass, service_key=service_key)
                except Exception as exc:
                    bot.send_message(message.chat.id, f'⚠️ Не удалось добавить соцсети: {exc}', reply_markup=_socialnet_service_markup())
                    return
                set_menu_state(2)
                bot.send_message(message.chat.id, result)
                bot.send_message(message.chat.id, "Меню " + bypass, reply_markup=_list_actions_markup())
                return

            if level == 32:
                if message.text in ('🔙 Назад', 'Назад'):
                    set_menu_state(2)
                    bot.send_message(message.chat.id, "Меню " + bypass, reply_markup=_list_actions_markup())
                    return
                service_key = _resolve_socialnet_service(message.text)
                try:
                    result = _remove_socialnet_list(bypass, service_key=service_key)
                except Exception as exc:
                    bot.send_message(message.chat.id, f'⚠️ Не удалось удалить соцсети: {exc}', reply_markup=_socialnet_service_markup())
                    return
                set_menu_state(2)
                bot.send_message(message.chat.id, result)
                bot.send_message(message.chat.id, "Меню " + bypass, reply_markup=_list_actions_markup())
                return

            if level == 4:
                try:
                    mylist = set(_read_unblock_list_entries(bypass))
                except FileNotFoundError:
                    bot.send_message(message.chat.id, '⚠️ Файл списка не найден. Откройте список заново.', reply_markup=main)
                    set_menu_state(1, None)
                    return
                if message.text == "Удалить обход блокировок соцсетей":
                    set_menu_state(32)
                    bot.send_message(message.chat.id, f'Выберите соцсеть для удаления из {_list_label(bypass + ".txt")}.', reply_markup=_socialnet_service_markup())
                    return
                k = len(mylist)
                mas = message.text.split('\n')
                for site in mas:
                    mylist.discard(site)
                _write_unblock_list_entries(bypass, mylist)
                if k != len(mylist):
                    bot.send_message(message.chat.id, "✅ Успешно удалено")
                else:
                    bot.send_message(message.chat.id, "Не найдено в списке")
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                item1 = types.KeyboardButton("📑 Показать список")
                item2 = types.KeyboardButton("📝 Добавить в список")
                item3 = types.KeyboardButton("🗑 Удалить из списка")
                item4 = types.KeyboardButton("📥 Сервисы по запросу")
                back = types.KeyboardButton("🔙 Назад")
                markup.row(item1, item2, item3)
                markup.row(item4)
                markup.row(back)
                set_menu_state(2)
                subprocess.run(["/opt/bin/unblock_update.sh"], check=False)
                bot.send_message(message.chat.id, "Меню " + bypass, reply_markup=markup)
                return

            if level == 10:
                target_route = bypass
                reply_markup = _list_actions_markup() if target_route else _service_list_markup()
                _handle_getlist_request(message, message.text, route_name=target_route, reply_markup=reply_markup)
                if target_route:
                    set_menu_state(2, target_route)
                return

            if level == 20:
                if message.text == '🔙 В меню ключей':
                    set_menu_state(8, None)
                    _clear_pool_page(message.chat.id)
                    bot.send_message(message.chat.id, '🔑 Ключи и мосты', reply_markup=_build_keys_menu_markup())
                    return
                proto = _resolve_pool_protocol(message.text)
                if not proto:
                    bot.send_message(message.chat.id, 'Выберите протокол кнопкой внизу.', reply_markup=_pool_protocol_markup())
                    return
                set_menu_state(21, proto)
                _send_pool_page(message.chat.id, proto, page=0)
                return

            if level == 21:
                proto = _resolve_pool_protocol(bypass)
                if not proto:
                    set_menu_state(20, None)
                    _clear_pool_inline_keyboard(message.chat.id)
                    _clear_pool_page(message.chat.id)
                    bot.send_message(message.chat.id, _format_pool_summary(), reply_markup=_pool_protocol_markup())
                    return
                page = _get_pool_page(message.chat.id)
                if message.text == '🔙 В меню ключей':
                    set_menu_state(8, None)
                    _clear_pool_page(message.chat.id)
                    bot.send_message(message.chat.id, '🔑 Ключи и мосты', reply_markup=_build_keys_menu_markup())
                    return
                selected_proto = _resolve_pool_protocol(message.text)
                if selected_proto:
                    set_menu_state(21, selected_proto)
                    _send_pool_page(message.chat.id, selected_proto, page=0)
                    return
                if message.text == '🔙 К выбору протокола':
                    set_menu_state(20, None)
                    _clear_pool_inline_keyboard(message.chat.id)
                    _clear_pool_page(message.chat.id)
                    bot.send_message(message.chat.id, _format_pool_summary(), reply_markup=_pool_protocol_markup())
                    return
                page_delta = _pool_reply_page_delta(message.text)
                if page_delta:
                    _send_pool_page(message.chat.id, proto, page=page + page_delta)
                    return
                if _is_pool_page_noop(message.text):
                    _send_pool_page(message.chat.id, proto, page=page)
                    return
                action, raw_index, button_proto = _pool_reply_key_action(message.text)
                if action:
                    if action == 'legacy' or not button_proto:
                        bot.send_message(
                            message.chat.id,
                            'Эта кнопка пула устарела и не содержит протокол. Откройте пул заново и нажмите кнопку вида V1/V2/VM/TR/SS.',
                            reply_markup=_pool_action_markup(proto, page),
                        )
                        return
                    if button_proto != proto:
                        proto = button_proto
                        page = 0
                        set_menu_state(21, proto)
                    if action == 'delete':
                        bot.send_message(
                            message.chat.id,
                            'Удаление доступно только через кнопку «🗑 Удаление». Это защищает от случайного нажатия старой кнопки.',
                            reply_markup=_pool_action_markup(proto, page),
                        )
                        return
                    try:
                        index, key_value = _pool_key_by_index(proto, raw_index)
                    except Exception as exc:
                        bot.send_message(message.chat.id, f'Ошибка выбора ключа: {exc}', reply_markup=_pool_action_markup(proto, page))
                        return
                    if action == 'apply':
                        bot.send_message(
                            message.chat.id,
                            f'Применяю ключ #{index} для {_pool_proto_label(proto)}. Это может занять до 30 секунд.',
                            reply_markup=_pool_action_markup(proto, page),
                        )
                        _apply_pool_key_background(message.chat.id, proto, key_value, index, page=page)
                    else:
                        try:
                            _delete_pool_key(proto, key_value)
                            _send_pool_page(message.chat.id, proto, page=page, prefix=f'Ключ #{index} удалён из пула {_pool_proto_label(proto)}.')
                        except Exception as exc:
                            bot.send_message(message.chat.id, f'Ошибка удаления ключа из пула: {exc}', reply_markup=_pool_action_markup(proto, page))
                    return
                if message.text in ('📋 Показать пул', '🔄 Обновить пул'):
                    _send_pool_page(message.chat.id, proto, page=page)
                    return
                if message.text == '🔙 К пулу':
                    _send_pool_page(message.chat.id, proto, page=page)
                    return
                if message.text == '➕ Добавить ключи':
                    set_menu_state(22)
                    bot.send_message(
                        message.chat.id,
                        f'Отправьте один или несколько ключей для пула {_pool_proto_label(proto)}. Каждый ключ с новой строки.',
                        reply_markup=_pool_input_markup(),
                    )
                    return
                if message.text == '🔗 Загрузить subscription':
                    set_menu_state(23)
                    bot.send_message(
                        message.chat.id,
                        f'Отправьте subscription URL для пула {_pool_proto_label(proto)}.',
                        reply_markup=_pool_input_markup(),
                    )
                    return
                if message.text == '✅ Применить ключ':
                    bot.send_message(message.chat.id, 'Используйте нижние кнопки ✅ с номером нужного ключа.', reply_markup=_pool_action_markup(proto, page))
                    return
                if message.text == '🗑 Удалить ключ':
                    bot.send_message(message.chat.id, 'Используйте нижние кнопки ✕ с номером нужного ключа.', reply_markup=_pool_action_markup(proto, page))
                    return
                if message.text == '🗑 Удаление':
                    set_menu_state(25)
                    bot.send_message(
                        message.chat.id,
                        f'Выберите ключ для удаления из пула {_pool_proto_label(proto)}. Активный ключ удалить можно, но режим бота останется прежним до применения другого ключа.',
                        reply_markup=_pool_delete_markup(proto, page),
                    )
                    return
                if message.text == '🧹 Очистить пул':
                    set_menu_state(26)
                    bot.send_message(
                        message.chat.id,
                        f'Очистить весь пул {_pool_proto_label(proto)}? Это удалит все ключи из пула.',
                        reply_markup=_pool_clear_confirm_markup(),
                    )
                    return
                if message.text in ['🔍 Проверить пул', '🔍 Проверить активный']:
                    started, queued = _probe_pool_keys_background(proto, _pool_keys_for_proto(proto), stale_only=False)
                    prefix = (
                        f'Запущена безопасная фоновая проверка пула {_pool_proto_label(proto)}. В очереди: {queued}. Ключи проверяются по одному с паузой, чтобы не перегружать память роутера.'
                        if started else
                        'Проверка пула уже выполняется или в пуле нет ключей для проверки.'
                    )
                    _send_pool_page(
                        message.chat.id,
                        proto,
                        page=page,
                        prefix=prefix,
                    )
                    return
                bot.send_message(message.chat.id, 'Выберите действие кнопкой внизу.', reply_markup=_pool_action_markup(proto, page))
                return

            if level == 22:
                proto = _resolve_pool_protocol(bypass)
                if not proto:
                    set_menu_state(20, None)
                    _clear_pool_inline_keyboard(message.chat.id)
                    _clear_pool_page(message.chat.id)
                    bot.send_message(message.chat.id, _format_pool_summary(), reply_markup=_pool_protocol_markup())
                    return
                if message.text == '🔙 К пулу':
                    set_menu_state(21)
                    _send_pool_page(message.chat.id, proto, page=_get_pool_page(message.chat.id))
                    return
                added = _add_keys_to_pool(proto, message.text)
                set_menu_state(21)
                _send_pool_page(
                    message.chat.id,
                    proto,
                    page=_get_pool_page(message.chat.id),
                    prefix=f'Добавлено ключей в пул {_pool_proto_label(proto)}: {added}',
                )
                return

            if level == 23:
                proto = _resolve_pool_protocol(bypass)
                if not proto:
                    set_menu_state(20, None)
                    _clear_pool_inline_keyboard(message.chat.id)
                    _clear_pool_page(message.chat.id)
                    bot.send_message(message.chat.id, _format_pool_summary(), reply_markup=_pool_protocol_markup())
                    return
                if message.text == '🔙 К пулу':
                    set_menu_state(21)
                    _send_pool_page(message.chat.id, proto, page=_get_pool_page(message.chat.id))
                    return
                try:
                    fetched, error = _fetch_keys_from_subscription(message.text.strip())
                    if error:
                        raise ValueError(error)
                    source_proto = 'vless' if proto == 'vless2' else proto
                    added = _add_keys_to_pool(proto, '\n'.join(fetched.get(source_proto, []) or []))
                    result = f'Загружено из subscription в пул {_pool_proto_label(proto)}: {added} новых ключей.'
                except Exception as exc:
                    result = f'Ошибка загрузки subscription: {exc}'
                set_menu_state(21)
                _send_pool_page(message.chat.id, proto, page=_get_pool_page(message.chat.id), prefix=result)
                return

            if level == 26:
                proto = _resolve_pool_protocol(bypass)
                if not proto:
                    set_menu_state(20, None)
                    _clear_pool_page(message.chat.id)
                    bot.send_message(message.chat.id, _format_pool_summary(), reply_markup=_pool_protocol_markup())
                    return
                page = _get_pool_page(message.chat.id)
                if message.text == '✅ Очистить пул':
                    removed = _clear_pool(proto)
                    set_menu_state(21)
                    _send_pool_page(message.chat.id, proto, page=page, prefix=f'Пул {_pool_proto_label(proto)} очищен. Удалено ключей: {removed}.')
                    return
                if message.text in ('Отмена', '🔙 К пулу'):
                    set_menu_state(21)
                    _send_pool_page(message.chat.id, proto, page=page, prefix='Очистка пула отменена.')
                    return
                bot.send_message(message.chat.id, 'Подтвердите очистку или нажмите отмену.', reply_markup=_pool_clear_confirm_markup())
                return

            if level == 24:
                proto = _resolve_pool_protocol(bypass)
                if not proto:
                    set_menu_state(20, None)
                    _clear_pool_inline_keyboard(message.chat.id)
                    _clear_pool_page(message.chat.id)
                    bot.send_message(message.chat.id, _format_pool_summary(), reply_markup=_pool_protocol_markup())
                    return
                try:
                    index, key_value = _pool_key_by_index(proto, message.text)
                    result = _apply_pool_key(proto, key_value)
                    result = f'Ключ #{index} применён для {_pool_proto_label(proto)}.\n{result}'
                except Exception as exc:
                    result = f'Ошибка применения ключа из пула: {exc}'
                set_menu_state(21)
                _send_pool_page(message.chat.id, proto, prefix=result)
                return

            if level == 25:
                proto = _resolve_pool_protocol(bypass)
                if not proto:
                    set_menu_state(20, None)
                    _clear_pool_inline_keyboard(message.chat.id)
                    _clear_pool_page(message.chat.id)
                    bot.send_message(message.chat.id, _format_pool_summary(), reply_markup=_pool_protocol_markup())
                    return
                page = _get_pool_page(message.chat.id)
                if message.text in ('🔙 К пулу', '🔙 Назад'):
                    set_menu_state(21)
                    _send_pool_page(message.chat.id, proto, page=page)
                    return
                page_delta = _pool_reply_page_delta(message.text)
                if page_delta:
                    set_menu_state(25)
                    _send_pool_delete_page(
                        message.chat.id,
                        proto,
                        page=page + page_delta,
                        prefix='Режим удаления: выберите ключ кнопкой ниже.',
                    )
                    return
                if _is_pool_page_noop(message.text):
                    _send_pool_delete_page(message.chat.id, proto, page=page)
                    return
                action, raw_index, button_proto = _pool_reply_key_action(message.text)
                if not action:
                    bot.send_message(message.chat.id, 'Выберите ключ для удаления кнопкой с кодом протокола V1/V2/VM/TR/SS.', reply_markup=_pool_delete_markup(proto, page))
                    return
                if action == 'legacy' or not button_proto:
                    bot.send_message(
                        message.chat.id,
                        'Эта кнопка пула устарела и не содержит протокол. Откройте пул заново и нажмите кнопку удаления вида ✕ V1/V2/VM/TR/SS.',
                        reply_markup=_pool_delete_markup(proto, page),
                    )
                    return
                if button_proto != proto:
                    proto = button_proto
                    page = 0
                    set_menu_state(25, proto)
                if action != 'delete':
                    bot.send_message(message.chat.id, 'Сейчас включен режим удаления. Нажмите кнопку ключа с префиксом ✕ или вернитесь к пулу.', reply_markup=_pool_delete_markup(proto, page))
                    return
                try:
                    index, key_value = _pool_key_by_index(proto, raw_index)
                    _delete_pool_key(proto, key_value)
                    result = f'Ключ #{index} удалён из пула {_pool_proto_label(proto)}.'
                except Exception as exc:
                    result = f'Ошибка удаления ключа из пула: {exc}'
                set_menu_state(21)
                _send_pool_page(message.chat.id, proto, page=page, prefix=result)
                return

            if level == 5:
                set_menu_state(0)
                _install_proxy_from_message(message, 'shadowsocks', message.text, main)
                return

            if level == 8:
                # значит это ключи и мосты
                if message.text == 'Где брать ключи❔':
                    url = _raw_github_url('keys.md')
                    try:
                        keys = _fetch_remote_text(url)
                    except requests.RequestException as exc:
                        bot.send_message(message.chat.id, f'⚠️ Не удалось загрузить справку по ключам: {exc}', reply_markup=main)
                        return
                    bot.send_message(message.chat.id, keys, parse_mode='Markdown', disable_web_page_preview=True)
                    set_menu_state(8)

                if message.text == 'Shadowsocks':
                    #bot.send_message(message.chat.id, "Скопируйте ключ сюда")
                    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                    back = types.KeyboardButton("🔙 Назад")
                    markup.add(back)
                    set_menu_state(5)
                    bot.send_message(message.chat.id, "🔑 Скопируйте ключ сюда", reply_markup=markup)
                    return

                if message.text == 'Vmess':
                    #bot.send_message(message.chat.id, "Скопируйте ключ сюда")
                    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                    back = types.KeyboardButton("🔙 Назад")
                    markup.add(back)
                    set_menu_state(9)
                    bot.send_message(message.chat.id, "🔑 Скопируйте ключ сюда", reply_markup=markup)
                    return

                if message.text == 'Vless' or message.text == 'Vless 1':
                    #bot.send_message(message.chat.id, "Скопируйте ключ сюда")
                    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                    back = types.KeyboardButton("🔙 Назад")
                    markup.add(back)
                    set_menu_state(11)
                    bot.send_message(message.chat.id, "🔑 Скопируйте ключ сюда", reply_markup=markup)
                    return

                if message.text == 'Vless 2':
                    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                    back = types.KeyboardButton("🔙 Назад")
                    markup.add(back)
                    set_menu_state(12)
                    bot.send_message(message.chat.id, "🔑 Скопируйте ключ сюда", reply_markup=markup)
                    return

                if message.text == 'Trojan':
                    #bot.send_message(message.chat.id, "Скопируйте ключ сюда")
                    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                    back = types.KeyboardButton("🔙 Назад")
                    markup.add(back)
                    set_menu_state(10)
                    bot.send_message(message.chat.id, "🔑 Скопируйте ключ сюда", reply_markup=markup)
                    return

            if level == 9:
                set_menu_state(0)
                _install_proxy_from_message(message, 'vmess', message.text, main)
                return

            if level == 10:
                set_menu_state(0)
                _install_proxy_from_message(message, 'trojan', message.text, main)
                return

            if level == 11:
                set_menu_state(0)
                _install_proxy_from_message(message, 'vless', message.text, main)
                return

            if level == 12:
                set_menu_state(0)
                _install_proxy_from_message(message, 'vless2', message.text, main)
                return

            if message.text == '🌐 Через браузер':
                bot.send_message(message.chat.id,
                                 f'Откройте в браузере: http://{routerip}:{browser_port}/\n'
                                 'Введите ключ Shadowsocks, Vmess, Vless 1, Vless 2 или Trojan на странице.', reply_markup=main)
                return

            if message.text == '🔰 Установка и удаление':
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                item1 = types.KeyboardButton("♻️ Установка / переустановка (ветка main)")
                item2 = types.KeyboardButton("♻️ Переустановка (ветка independent)")
                item3 = types.KeyboardButton("♻️ Переустановка (без Telegram бота)")
                item4 = types.KeyboardButton("⚠️ Удаление")
                back = types.KeyboardButton("🔙 Назад")
                markup.row(item1)
                markup.row(item2)
                markup.row(item3)
                markup.row(item4)
                markup.row(back)
                bot.send_message(message.chat.id, '🔰 Установка и удаление', reply_markup=markup)
                return

            if message.text in (
                '♻️ Установка / переустановка (ветка main)',
                '♻️ Установка переустановка (ветка main)',
                '♻️ Установка и переустановка',
                '♻️ Установка & переустановка',
            ):
                set_menu_state(TELEGRAM_CONFIRM_LEVEL, 'update_main')
                bot.send_message(message.chat.id, _telegram_confirm_prompt('update_main'), reply_markup=_build_telegram_confirm_markup())
                return

            if message.text == '♻️ Переустановка (ветка independent)':
                set_menu_state(TELEGRAM_CONFIRM_LEVEL, 'update_independent')
                bot.send_message(message.chat.id, _telegram_confirm_prompt('update_independent'), reply_markup=_build_telegram_confirm_markup())
                return

            if message.text == '♻️ Переустановка (без Telegram бота)':
                set_menu_state(TELEGRAM_CONFIRM_LEVEL, 'update_no_bot')
                bot.send_message(message.chat.id, _telegram_confirm_prompt('update_no_bot'), reply_markup=_build_telegram_confirm_markup())
                return

            if message.text == '⚠️ Удаление':
                set_menu_state(TELEGRAM_CONFIRM_LEVEL, 'remove')
                bot.send_message(message.chat.id, _telegram_confirm_prompt('remove'), reply_markup=_build_telegram_confirm_markup())
                return

            if message.text == "📝 Списки обхода":
                set_menu_state(1, None)
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                options = _telegram_unblock_list_options()
                buttons = [types.KeyboardButton(label) for label, _ in options]
                for index in range(0, len(buttons), 2):
                    markup.row(*buttons[index:index + 2])
                markup.add(types.KeyboardButton("📥 Сервисы по запросу"))
                back = types.KeyboardButton("🔙 Назад")
                markup.add(back)
                bot.send_message(message.chat.id, "📝 Списки обхода", reply_markup=markup)
                return

            if message.text == "🔑 Ключи и мосты":
                set_menu_state(8, None)
                bot.send_message(message.chat.id, "🔑 Ключи и мосты", reply_markup=_build_keys_menu_markup())
                return

    except Exception as error:
        _write_runtime_log(traceback.format_exc(), mode='w')
        try:
            os.chmod(r"/opt/etc/error.log", 0o0755)
        except Exception:
            pass
        try:
            if getattr(getattr(message, 'chat', None), 'type', None) == 'private':
                _set_chat_menu_state(message.chat.id, level=0, bypass=None)
                bot.send_message(
                    message.chat.id,
                    f'⚠️ Команда не выполнена из-за внутренней ошибки: {error}',
                    reply_markup=_build_main_menu_markup(),
                )
        except Exception:
            pass

class KeyInstallHTTPRequestHandler(BaseHTTPRequestHandler):
    def _request_is_allowed(self):
        client_ip = self.client_address[0] if self.client_address else ''
        return _is_local_web_client(client_ip)

    def _ensure_request_allowed(self):
        if self._request_is_allowed():
            return True
        self._send_html('<h1>403 Forbidden</h1><p>Веб-интерфейс доступен только из локальной сети.</p>', status=403)
        return False

    def _send_html(self, html, status=200):
        body = html.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def _send_redirect(self, location='/'):
        self.send_response(303)
        self.send_header('Location', location)
        self.send_header('Content-Length', '0')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        self.send_header('Connection', 'close')
        self.end_headers()
        self.close_connection = True

    def _send_png(self, filepath):
        try:
            with open(filepath, 'rb') as f:
                body = f.read()
            self.send_response(200)
            content_type = 'image/png'
            if body.lstrip().startswith(b'<svg'):
                content_type = 'image/svg+xml'
            self.send_header('Content-type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'public, max-age=86400')
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            self.send_response(404)
            self.send_header('Content-type', 'text/plain')
            self.send_header('Content-Length', '9')
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(b'Not Found')
        self.close_connection = True

    def _send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def _wants_json(self):
        accept = self.headers.get('Accept', '')
        requested_with = self.headers.get('X-Requested-With', '')
        return 'application/json' in accept or requested_with == 'fetch'

    def _send_action_result(self, result, success=True, extra=None, redirect='/'):
        if self._wants_json():
            payload = {
                'ok': bool(success),
                'result': result or '',
                'status': 'ok' if success else 'error',
            }
            if extra:
                payload.update(extra)
            self._send_json(payload, status=200 if success else 400)
            return
        _set_web_flash_message(result)
        self._send_redirect(redirect)

    def _build_form(self, message=''):
        command_state = _consume_web_command_state_for_render()
        current_keys = _load_current_keys()
        snapshot = _cached_status_snapshot(current_keys)
        status = snapshot['web'] if snapshot is not None else _placeholder_web_status_snapshot()
        protocol_statuses = snapshot['protocols'] if snapshot is not None else _placeholder_protocol_statuses(current_keys)
        pool_probe_started, pool_probe_queued = _probe_pool_keys_on_page_load()
        current_pool_probe_progress = _get_pool_probe_progress()
        pool_probe_pending = (
            bool(current_pool_probe_progress.get('running')) and
            int(current_pool_probe_progress.get('total') or 0) > 0
        )
        if snapshot is None:
            snapshot = _active_mode_status_snapshot(current_keys)
            status = snapshot['web']
            protocol_statuses = snapshot['protocols']
            if not pool_probe_pending:
                _refresh_status_caches_async(current_keys)
        unblock_lists = _load_unblock_lists()
        status_refresh_pending = (
            'Фоновая проверка связи выполняется' in status.get('api_status', '') or
            any(item.get('label') == 'Проверяется' for item in protocol_statuses.values()) or
            pool_probe_pending
        )

        message_block = ''
        if message:
            safe_message = html.escape(message)
            message_block = f'''<div id="web-action-message" class="notice notice-result">
  <strong>Результат</strong>
  <pre class="log-output">{safe_message}</pre>
</div>'''
        else:
            message_block = '''<div id="web-action-message" class="notice notice-result hidden">
  <strong>Результат</strong>
  <pre class="log-output"></pre>
</div>'''

        command_block = ''
        if command_state['label']:
            command_title = 'Команда выполняется' if command_state['running'] else 'Последняя команда'
            command_text = command_state['result'] or f'⏳ {command_state["label"]} ещё выполняется. Статус обновится без перезагрузки страницы.'
            command_block = f'''<div id="web-command-status" class="notice notice-status">
  <strong>{html.escape(command_title)}: {html.escape(command_state['label'])}</strong>
  <pre class="log-output">{html.escape(command_text)}</pre>
</div>'''
        else:
            command_block = '''<div id="web-command-status" class="notice notice-status hidden">
  <strong></strong>
  <pre class="log-output"></pre>
</div>'''

        socks_hidden = '' if status['socks_details'] else ' hidden'
        socks_block = f'<p id="web-socks-details" class="status-note"{socks_hidden}>{html.escape(status.get("socks_details", ""))}</p>'
        fallback_block = ''
        if status.get('fallback_reason') and status['proxy_mode'] == 'none':
            fallback_block = f'<p id="web-fallback-reason" class="status-note">Последняя неудачная попытка прокси: {html.escape(status["fallback_reason"])}</p>'
        else:
            fallback_block = '<p id="web-fallback-reason" class="status-note hidden"></p>'

        current_mode_label = {
            'none': 'Без прокси',
            'shadowsocks': 'Shadowsocks',
            'vmess': 'Vmess',
            'vless': 'Vless 1',
            'vless2': 'Vless 2',
            'trojan': 'Trojan',
        }.get(status['proxy_mode'], status['proxy_mode'])
        list_route_label = _transparent_list_route_label()

        mode_options = [
            ('none', 'Без прокси'),
            ('shadowsocks', 'Shadowsocks'),
            ('vmess', 'Vmess'),
            ('vless', 'Vless 1'),
            ('vless2', 'Vless 2'),
            ('trojan', 'Trojan'),
        ]
        mode_buttons_html = ''.join(
            f'''<form method="post" action="/set_proxy" data-async-action="set-proxy">
        <input type="hidden" name="proxy_type" value="{value}">
        <button type="submit" class="mode-choice{' active' if proxy_mode == value else ''}" data-mode-value="{value}">
            <span>{html.escape(label)}</span>
        </button>
    </form>'''
            for value, label in mode_options
        )
        mode_picker_block = f'''<div id="mode-picker" class="hero-popover mode-picker hidden">
    <div class="mode-picker-form">
        <span class="mode-picker-label">Активный протокол</span>
        <div class="mode-choice-grid">{mode_buttons_html}</div>
    </div>
</div>'''

        protocol_sections = [
            ('vless', 'Vless 1', 6, 'vless://...'),
            ('vless2', 'Vless 2', 6, 'vless://...'),
            ('vmess', 'Vmess', 6, 'vmess://...'),
            ('trojan', 'Trojan', 5, 'trojan://...'),
            ('shadowsocks', 'Shadowsocks', 5, 'shadowsocks://...'),
        ]
        key_pools = _ensure_current_keys_in_pools(current_keys)
        key_probe_cache = _load_key_probe_cache()
        custom_checks = _load_custom_checks()
        custom_checks_html = _web_custom_checks_html(custom_checks)
        custom_presets_html = _web_custom_presets_html(custom_checks)
        custom_header_icons = _custom_check_header_icons(custom_checks)
        custom_checks_json = json.dumps(_web_custom_checks(), ensure_ascii=False)
        if pool_probe_pending:
            progress_total = int(current_pool_probe_progress.get('total') or 0)
            progress_checked = int(current_pool_probe_progress.get('checked') or 0)
            topbar_status_text = (
                f'⏳ Фоновая проверка пула ключей выполняется: {progress_checked}/{progress_total}. '
                'Статусы обновятся без перезагрузки страницы.'
            )
        else:
            topbar_status_text = status['api_status']
        pool_table_class = 'pool-table has-custom-checks' if custom_checks else 'pool-table'
        pool_custom_col_width = 32 * max(1, len(custom_checks))
        pool_mobile_custom_col_width = max(28, 28 * len(custom_checks))
        protocol_tabs = []
        protocol_panels = []
        for panel_index, (key_name, title, rows, placeholder) in enumerate(protocol_sections):
            safe_value = html.escape(current_keys.get(key_name, ''))
            safe_title = html.escape(title)
            status_info = protocol_statuses.get(key_name, {'tone': 'empty', 'label': 'Не сохранён', 'details': 'Ключ ещё не сохранён на роутере.'})
            api_ok = status_info.get('api_ok', False)
            current_probe = key_probe_cache.get(_hash_key(current_keys.get(key_name, '')), {})
            current_tg_ok = api_ok or bool(current_probe.get('tg_ok'))
            current_yt_ok = bool(status_info.get('yt_ok', current_probe.get('yt_ok', False)))
            custom_states = status_info.get('custom') or _web_custom_probe_states(current_probe, custom_checks)
            active_status_icons = ''.join([
                _telegram_icon_html(opacity=1.0) if current_tg_ok else '',
                _youtube_icon_html(opacity=1.0) if current_yt_ok else '',
            ] + [
                _service_icon_html(check.get('icon'), check.get('label', 'Service'), opacity=1.0, size=18)
                for check in custom_checks
                if custom_states.get(check.get('id')) == 'ok'
            ])
            pool_keys = key_pools.get(key_name, [])
            pool_items_html = ''
            if pool_keys:
                for i, pk in enumerate(pool_keys):
                    safe_pk = html.escape(pk)
                    display_name = html.escape(_pool_key_display_name(pk))
                    key_id = _hash_key(pk)[:12]
                    is_current_key = bool(current_keys.get(key_name) and pk == current_keys.get(key_name))
                    is_active = 'активен' if is_current_key else ''
                    active_class = ' pool-row-active' if is_current_key else ''
                    probe = key_probe_cache.get(_hash_key(pk), {})
                    tg_badge = _telegram_icon_html(opacity=1.0) if probe.get('tg_ok') else (
                        '<span class="service-probe-mark service-probe-fail">✕</span>'
                        if 'tg_ok' in probe else
                        '<span class="service-probe-mark service-probe-unknown">?</span>'
                    )
                    yt_badge = _youtube_icon_html(opacity=1.0) if probe.get('yt_ok') else (
                        '<span class="service-probe-mark service-probe-fail">✕</span>'
                        if 'yt_ok' in probe else
                        '<span class="service-probe-mark service-probe-unknown">?</span>'
                    )
                    custom_badges = _web_custom_check_badges(probe, custom_checks)
                    checked_at = html.escape(_web_probe_checked_at(probe))
                    pool_items_html += f'''<tr class="pool-row{active_class}" data-pool-row data-protocol="{key_name}" data-key-id="{key_id}" data-key="{safe_pk}">
                        <td class="pool-key-cell">
                            <form method="post" action="/pool_apply" class="pool-apply-form" data-async-action="pool-apply">
                                <input type="hidden" name="type" value="{key_name}">
                                <input type="hidden" name="key" value="{safe_pk}">
                                <button type="submit" class="pool-apply-btn" title="Применить этот ключ">{display_name}</button>
                            </form>
                            <span class="pool-mobile-active" data-pool-key-meta data-pool-mobile-active>{is_active}</span>
                            <span class="pool-hash">{key_id}</span>
                        </td>
                        <td class="pool-service-cell" data-pool-tg>{tg_badge}</td>
                        <td class="pool-service-cell" data-pool-yt>{yt_badge}</td>
                        <td class="pool-custom-cell" data-pool-custom>{custom_badges}</td>
                        <td class="pool-checked-cell" data-pool-checked>{checked_at}</td>
                        <td class="pool-actions-cell">
                            <form method="post" action="/pool_delete" class="pool-item-form" data-async-action="pool-delete" data-confirm-title="Удалить ключ?" data-confirm-message="Удалить ключ из пула {safe_title}?">
                                <input type="hidden" name="type" value="{key_name}">
                                <input type="hidden" name="key" value="{safe_pk}">
                                <button type="submit" class="pool-delete-btn" title="Удалить ключ из пула">Удалить</button>
                            </form>
                        </td>
                    </tr>'''
            if not pool_items_html:
                pool_items_html = '<tr class="pool-row pool-empty-row"><td colspan="6">Пул пуст. Добавьте ключи или загрузите subscription.</td></tr>'
            tab_active = ' active' if panel_index == 0 else ''
            protocol_tabs.append(
                f'''<button type="button" class="seg-tab protocol-tab{tab_active}" data-protocol-target="{key_name}">
                    <span>{safe_title}</span>
                    <span class="tab-count">{len(pool_keys)}</span>
                </button>'''
            )
            protocol_panels.append(f'''<section class="protocol-workspace{tab_active}" data-protocol-card="{key_name}" data-protocol-panel="{key_name}">
        <div class="workspace-head">
            <div>
                <span class="eyebrow">Ключи и мосты</span>
                <h2>{safe_title}</h2>
                <p class="key-status-note" data-protocol-status-details>{html.escape(status_info['details'])}</p>
            </div>
            <span class="key-status-wrap"><span class="key-status-icons" data-protocol-status-icons>{active_status_icons}</span><span class="key-status-badge key-status-{status_info['tone']}" data-protocol-status-label>{status_info['label']}</span></span>
        </div>
        <div class="subtabs">
            <button type="button" class="subtab active" data-subview-target="key">Ключ</button>
            <button type="button" class="subtab" data-subview-target="pool">Пул ключей</button>
            <button type="button" class="subtab" data-subview-target="subscription">Subscription</button>
            <button type="button" class="subtab" data-subview-target="check">Проверка</button>
        </div>
        <div class="protocol-subview active" data-subview="key">
            <form method="post" action="/install" data-async-action="install" class="key-editor-form">
                <input type="hidden" name="type" value="{key_name}">
                <label class="field-label">Активный ключ {safe_title}</label>
                <textarea name="key" rows="{rows}" placeholder="{html.escape(placeholder)}" required data-key-textarea>{safe_value}</textarea>
                <div class="form-actions">
                    <button type="submit">Сохранить {safe_title}</button>
                </div>
            </form>
        </div>
        <div class="protocol-subview" data-subview="pool">
            <div class="pool-toolbar">
                <form method="post" action="/pool_probe" data-async-action="pool-probe">
                    <input type="hidden" name="type" value="{key_name}">
                    <button type="submit" class="secondary-button">Проверить пул</button>
                </form>
                <form method="post" action="/pool_clear" data-async-action="pool-clear" data-confirm-title="Очистить пул?" data-confirm-message="Очистить весь пул ключей для {safe_title}?">
                    <input type="hidden" name="type" value="{key_name}">
                    <button type="submit" class="danger pool-clear-btn">Очистить пул</button>
                </form>
            </div>
            <div class="pool-table-wrap">
                <table class="{pool_table_class}" style="--custom-col-mobile:{pool_mobile_custom_col_width}px">
                    <colgroup>
                        <col class="pool-col-key">
                        <col class="pool-col-icon">
                        <col class="pool-col-icon">
                        <col class="pool-col-custom" style="width:{pool_custom_col_width}px">
                        <col class="pool-col-checked">
                        <col class="pool-col-actions">
                    </colgroup>
                    <thead><tr><th class="pool-key-head">Ключ</th><th class="pool-icon-head">{_telegram_icon_html(opacity=1.0)}</th><th class="pool-icon-head">{_youtube_icon_html(opacity=1.0)}</th><th class="pool-icon-head pool-custom-head" data-custom-check-head>{custom_header_icons}</th><th class="pool-checked-head">Проверка</th><th class="pool-actions-head">Действия</th></tr></thead>
                    <tbody data-pool-body="{key_name}">{pool_items_html}</tbody>
                </table>
            </div>
        </div>
        <div class="protocol-subview protocol-subview-import" data-subview="subscription">
            <form method="post" action="/pool_add" class="pool-add-form" data-async-action="pool-add">
                <input type="hidden" name="type" value="{key_name}">
                <label class="field-label">Добавить ключи в пул</label>
                <textarea name="keys" rows="4" placeholder="Вставьте ключи, каждый с новой строки"></textarea>
                <button type="submit" class="secondary-button">Добавить в пул</button>
            </form>
            <form method="post" action="/pool_subscribe" class="pool-subscribe-form" data-async-action="pool-subscribe">
                <input type="hidden" name="type" value="{key_name}">
                <label class="field-label">Загрузить subscription</label>
                <input type="url" name="url" placeholder="https://sub.example.com/...">
                <button type="submit" class="secondary-button">Загрузить subscription</button>
            </form>
        </div>
        <div class="protocol-subview protocol-subview-check" data-subview="check">
            <div class="status-card">
                <span class="status-label">Состояние ключа</span>
                <span class="status-value">{status_info['label']}</span>
                <p class="status-note">{html.escape(status_info['details'])}</p>
            </div>
            <div class="custom-check-card">
                <div class="custom-check-head">
                    <span>
                        <strong>Дополнительные сервисы</strong>
                        <small>Проверяются через выбранный прокси вместе с Telegram и YouTube.</small>
                    </span>
                </div>
                <div class="service-preset-grid">{custom_presets_html}</div>
                <div class="custom-check-list" data-custom-check-list>{custom_checks_html}</div>
                <form method="post" action="/custom_check_add" class="custom-check-form" data-async-action="custom-check-add">
                    <input type="text" name="label" placeholder="Название, например ChatGPT">
                    <input type="text" name="url" placeholder="Домен, IP или URL: chatgpt.com">
                    <button type="submit" class="secondary-button">Добавить проверку</button>
                </form>
            </div>
            <form method="post" action="/pool_probe" data-async-action="pool-probe">
                <input type="hidden" name="type" value="{key_name}">
                <button type="submit">Проверить пул {safe_title}</button>
            </form>
        </div>
    </section>''')
        protocol_tabs_html = ''.join(protocol_tabs)
        protocol_panels_html = ''.join(protocol_panels)
        quick_key_proto = status['proxy_mode'] if status['proxy_mode'] in ['shadowsocks', 'vmess', 'vless', 'vless2', 'trojan'] else 'vless'
        quick_key_label = current_mode_label if quick_key_proto == status['proxy_mode'] else 'Vless 1'
        quick_key_value = html.escape(current_keys.get(quick_key_proto, ''))
        pool_summary = _pool_status_summary(current_keys, key_pools, key_probe_cache, custom_checks)
        pool_summary_note = pool_summary['note']
        if pool_probe_pending:
            pool_summary_note = (
                f"Фоновая проверка: {int(current_pool_probe_progress.get('checked') or 0)}/"
                f"{int(current_pool_probe_progress.get('total') or 0)}. {pool_summary_note}"
            )

        dns_override_active = _dns_override_enabled()
        update_buttons_html = f'''<form method="post" action="/command" data-async-action="command" data-confirm-title="Переустановить из форка?" data-confirm-message="Код и служебные файлы будут обновлены без сброса сохраненных ключей и списков.">
                <input type="hidden" name="command" value="update">
                <button type="submit">Переустановить из форка без сброса</button>
            </form>
            <form method="post" action="/command" data-async-action="command" data-confirm-title="Переустановить independent?" data-confirm-message="Будет установлена ветка feature/independent-rework с сохранением локальных настроек.">
                <input type="hidden" name="command" value="update_independent">
                <button type="submit">Переустановка (ветка independent)</button>
            </form>
            <form method="post" action="/command" data-async-action="command" data-confirm-title="Перейти в web-only?" data-confirm-message="Будет установлена версия без Telegram-бота. Ключи, настройки и списки сохранятся локально.">
                <input type="hidden" name="command" value="update_no_bot">
                <button type="submit">Переустановка (без Telegram бота)</button>
            </form>'''
        command_buttons = [
            ('restart_services', 'Перезапустить сервисы', '', 'Перезапустить сервисы?', 'Службы прокси и DNS будут перезапущены; соединение может кратко пропасть.'),
            ('dns_on', 'DNS Override ВКЛ', 'success-button' if dns_override_active else '', 'Включить DNS Override?', 'Роутер сохранит конфигурацию и перезагрузится.'),
            ('dns_off', 'DNS Override ВЫКЛ', 'danger', 'Выключить DNS Override?', 'Роутер сохранит конфигурацию и перезагрузится.'),
            ('remove', 'Удалить компоненты', 'danger', 'Удалить компоненты?', 'Будут удалены установленные компоненты программы. Настройки роутера могут измениться.'),
            ('reboot', 'Перезагрузить роутер', 'danger', 'Перезагрузить роутер?', 'Связь с веб-интерфейсом временно пропадет.'),
        ]
        command_buttons_html = ''.join(
            f'''<form method="post" action="/command" data-async-action="command"{f' data-confirm-title="{html.escape(confirm_title)}" data-confirm-message="{html.escape(confirm_message)}"' if confirm_title else ''}>
            <input type="hidden" name="command" value="{command}">
            <button type="submit" class="{button_class}">{html.escape(label)}</button>
        </form>'''
            for command, label, button_class, confirm_title, confirm_message in command_buttons
        )

        unblock_tabs = []
        unblock_panels = []
        for list_index, entry in enumerate(unblock_lists):
            safe_name = html.escape(entry['name'])
            safe_label = html.escape(entry['label'])
            safe_content = html.escape(entry['content'])
            active_class = ' active' if list_index == 0 else ''
            social_service_buttons = ''.join(
                f'''<button type="submit" name="service_key" value="{html.escape(key)}" formaction="/append_socialnet" class="secondary-button" data-confirm-title="Добавить {_socialnet_service_label(key)}?" data-confirm-message="Добавить {_socialnet_service_label(key)} в {safe_label}?">{html.escape(_socialnet_service_label(key))}</button>'''
                for key in SOCIALNET_SERVICE_KEYS
            )
            unblock_tabs.append(f'''<button type="button" class="seg-tab list-tab{active_class}" data-list-target="{safe_name}">{safe_label}</button>''')
            line_count = len([line for line in entry['content'].splitlines() if line.strip()])
            unblock_panels.append(f'''<section class="list-workspace{active_class}" data-list-panel="{safe_name}">
        <div class="workspace-head">
            <div>
                <span class="eyebrow">Список обхода</span>
                <h2>{safe_label}</h2>
                <p class="section-subtitle">Записей: {line_count}. Файл: <span class="file-chip">{safe_name}</span></p>
            </div>
        </div>
        <form method="post" action="/save_unblock_list" data-async-action="save-list" class="list-editor-form">
            <input type="hidden" name="list_name" value="{safe_name}">
            <textarea name="content" rows="12" placeholder="example.org&#10;api.telegram.org">{safe_content}</textarea>
            <div class="form-actions">
                <button type="submit">Сохранить список</button>
            </div>
            <div class="social-list-actions">
                <span class="social-list-title">Добавить соцсети</span>
                {social_service_buttons}
                <button type="submit" name="service_key" value="{SOCIALNET_ALL_KEY}" formaction="/append_socialnet" class="secondary-button" data-confirm-title="Добавить все соцсети?" data-confirm-message="Добавить все соцсети в {safe_label}?">Все соцсети</button>
                <button type="submit" name="service_key" value="{SOCIALNET_ALL_KEY}" formaction="/remove_socialnet" class="danger" data-confirm-title="Удалить все соцсети?" data-confirm-message="Удалить все соцсети из {safe_label}?">Удалить соцсети</button>
            </div>
        </form>
    </section>''')
        unblock_tabs_html = ''.join(unblock_tabs)
        unblock_panels_html = ''.join(unblock_panels)

        initial_status_pending = 'true' if status_refresh_pending else 'false'
        initial_command_running = 'true' if command_state['running'] else 'false'

        start_button_label = 'Повторить запуск бота' if bot_ready else 'Запустить бота'

        return f'''<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
    <link rel="icon" href="data:,">
  <title>Установка ключей прокси</title>
    <style>
        :root{{
            --bg:#12161d;
            --bg-accent:#1a2330;
            --surface:#171e28;
            --surface-soft:#202a38;
            --surface-strong:#263243;
            --border:#334155;
            --text:#edf3ff;
            --muted:#9fb0c8;
            --primary:#4f8cff;
            --primary-hover:#6aa0ff;
            --secondary:#d78644;
            --danger:#c95a47;
            --success-bg:#163326;
            --success-border:#2d7650;
            --warn-bg:#3e2e16;
            --warn-border:#b78332;
            --shadow:0 18px 40px rgba(2, 6, 23, 0.34);
        }}
        [data-theme="light"]{{
            --bg:#f3efe6;
            --bg-accent:#e7dcc7;
            --surface:#fffdf8;
            --surface-soft:#f5ede0;
            --surface-strong:#efe2cb;
            --border:#d7c5aa;
            --text:#1f2933;
            --muted:#6f7a86;
            --primary:#1f7a6a;
            --primary-hover:#165f53;
            --secondary:#c96f32;
            --danger:#a8442f;
            --success-bg:#e5f4ea;
            --success-border:#8cb79a;
            --warn-bg:#fff0d9;
            --warn-border:#d6a35b;
            --shadow:0 18px 40px rgba(76, 58, 36, 0.12);
        }}
        *{{box-sizing:border-box;}}
        body{{
            margin:0;
                        font-family:Segoe UI,Helvetica,Arial,sans-serif;
            color:var(--text);
                        background:
                radial-gradient(circle at top left, rgba(215,134,68,.16), transparent 34%),
                radial-gradient(circle at top right, rgba(79,140,255,.16), transparent 28%),
                linear-gradient(180deg, #0f141c 0%, var(--bg) 100%);
                        padding:20px;
        }}
        [data-theme="light"] body{{
            background:
                radial-gradient(circle at top left, rgba(201,111,50,.18), transparent 34%),
                radial-gradient(circle at top right, rgba(31,122,106,.16), transparent 28%),
                linear-gradient(180deg, #f8f4ec 0%, var(--bg) 100%);
        }}
                .shell{{max-width:1180px;margin:0 auto;}}
        .hero{{margin-bottom:16px;padding:22px 24px;border:1px solid var(--border);border-radius:24px;background:linear-gradient(140deg, rgba(23,30,40,.98), rgba(32,42,56,.9));box-shadow:var(--shadow);}}
        [data-theme="light"] .hero{{background:linear-gradient(140deg, rgba(255,253,248,.98), rgba(239,226,203,.88));}}
                .hero-copy{{max-width:700px;}}
                .hero-row{{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;}}
                .hero-actions{{display:flex;align-items:flex-start;gap:10px;flex-wrap:wrap;position:relative;justify-content:flex-end;}}
        .hero-meta{{display:flex;flex-wrap:wrap;gap:10px;margin:16px 0 0;}}
        .hero-chip{{display:inline-flex;align-items:center;padding:8px 12px;border-radius:999px;background:rgba(79,140,255,.08);border:1px solid rgba(96,165,250,.18);font-size:13px;font-weight:700;color:var(--text);}}
        .theme-toggle{{display:inline-flex;align-items:center;gap:8px;padding:10px 14px;border-radius:8px;border:1px solid rgba(78,216,205,.5);background:rgba(34,67,73,.28);color:#96f1eb;font-size:13px;font-weight:700;cursor:pointer;box-shadow:none;white-space:nowrap;}}
                .mode-toggle{{display:inline-flex;align-items:center;gap:8px;padding:10px 14px;border-radius:8px;border:1px solid rgba(78,216,205,.5);background:rgba(34,67,73,.28);color:#96f1eb;font-size:13px;font-weight:700;cursor:pointer;box-shadow:none;white-space:nowrap;}}
        .theme-toggle:hover{{filter:none;transform:none;background:rgba(35,98,104,.44);border-color:rgba(96,214,205,.62);}}
                .mode-toggle:hover{{filter:none;transform:none;background:rgba(35,98,104,.44);border-color:rgba(96,214,205,.62);}}
                .hero-popover{{position:absolute;top:54px;right:0;min-width:260px;padding:14px;border:1px solid var(--border);border-radius:18px;background:linear-gradient(180deg, rgba(23,30,40,.98), rgba(32,42,56,.96));box-shadow:var(--shadow);z-index:10;}}
                [data-theme="light"] .hero-popover{{background:linear-gradient(180deg, rgba(255,253,248,.98), rgba(245,237,224,.96));}}
                .hidden{{display:none;}}
                .mode-picker-form{{display:grid;gap:10px;}}
                .mode-picker-label{{font-size:12px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);}}
                .mode-choice-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px;}}
                .mode-choice-grid form{{display:block;margin:0;}}
                .mode-choice{{width:100%;min-height:34px;justify-content:center;background:rgba(34,67,73,.28);border-color:rgba(78,216,205,.5);box-shadow:none;color:#96f1eb;}}
                .mode-choice.active{{background:rgba(48,191,181,.18);border-color:rgba(78,216,205,.5);color:#94f3ec;}}
                .mode-choice:hover{{filter:none;transform:none;background:rgba(35,98,104,.42);}}
        h1{{margin:0 0 4px;font-size:22px;line-height:1.15;letter-spacing:0;color:var(--text);}}
        h2{{margin:0 0 14px;font-size:20px;color:var(--text);}}
            p{{margin:0 0 8px;line-height:1.5;color:var(--muted);}}
        .hero strong{{color:var(--text);}}
                .layout{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin-top:16px;}}
        .panel{{min-width:0;padding:18px;border:1px solid var(--border);border-radius:22px;background:linear-gradient(180deg, rgba(23,30,40,.96), rgba(32,42,56,.94));box-shadow:var(--shadow);}}
        [data-theme="light"] .panel{{background:linear-gradient(180deg, rgba(255,253,248,.96), rgba(245,237,224,.94));}}
        form{{display:grid;gap:12px;}}
                input,textarea,select{{width:100%;padding:13px 14px;border-radius:14px;border:1px solid var(--border);background:var(--surface-soft);color:var(--text);font-size:16px;outline:none;}}
                input:focus,textarea:focus,select:focus{{border-color:rgba(31,122,106,.6);box-shadow:0 0 0 4px rgba(31,122,106,.08);}}
        textarea{{min-height:138px;resize:vertical;}}
                input::placeholder,textarea::placeholder{{color:#8b8f92;}}
        button{{padding:13px 16px;border:1px solid rgba(78,216,205,.5);border-radius:8px;background:rgba(34,67,73,.28);color:#96f1eb;font-size:15px;font-weight:700;cursor:pointer;transition:border-color .15s ease, background-color .15s ease, color .15s ease;box-shadow:none;}}
        button:hover{{filter:none;transform:none;border-color:rgba(96,214,205,.62);background:rgba(35,98,104,.44);}}
        button:disabled{{cursor:wait;opacity:.72;filter:saturate(.7);transform:none;}}
                button.danger{{border-color:rgba(205,86,82,.52);background:rgba(94,36,42,.34);color:#ffb7b1;box-shadow:none;}}
                .success-button{{border-color:rgba(78,216,205,.5);background:rgba(34,67,73,.28);color:#96f1eb;box-shadow:none;}}
                .secondary-button{{border-color:rgba(78,216,205,.5);background:rgba(34,67,73,.28);color:#96f1eb;box-shadow:none;}}
        .status-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-bottom:14px;}}
        .status-card{{min-width:0;min-height:126px;display:flex;flex-direction:column;gap:6px;padding:16px;border-radius:8px;background:rgba(79,140,255,.08);border:1px solid rgba(96,165,250,.18);}}
        .status-label{{display:block;margin-bottom:8px;font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:#90a5c4;}}
                .status-value{{display:block;font-size:16px;line-height:1.4;color:var(--text);overflow-wrap:anywhere;word-break:break-word;}}
                .notice{{padding:12px 14px;border-radius:16px;margin-bottom:14px;}}
                .notice strong{{display:block;margin-bottom:8px;color:var(--text);}}
        .notice-result{{background:var(--warn-bg);border:1px solid var(--warn-border);}}
        .notice-status{{background:var(--success-bg);border:1px solid var(--success-border);}}
            .hero-status{{margin-top:12px;margin-bottom:0;}}
            .hero-status-compact p:last-child{{margin-bottom:0;}}
            .hero-status-header{{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:6px;}}
            .traffic-inline{{display:flex;flex-wrap:wrap;gap:8px;justify-content:flex-end;}}
            .traffic-chip{{display:inline-flex;align-items:center;gap:8px;padding:6px 10px;border-radius:999px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);}}
            .traffic-chip-label{{font-size:11px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);}}
            .traffic-chip-value{{font-size:13px;font-weight:700;color:var(--text);}}
                .status-note{{margin-top:6px;color:var(--text);font-size:14px;line-height:1.45;overflow-wrap:anywhere;word-break:break-word;}}
                .command-progress-block{{margin:14px 0 10px;padding:12px 14px;border:1px solid var(--border);border-radius:14px;background:rgba(255,255,255,.03);}}
                .command-progress-header{{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:8px;color:var(--text);font-size:13px;font-weight:700;}}
                .command-progress-track{{width:100%;height:10px;border-radius:999px;background:rgba(255,255,255,.08);overflow:hidden;}}
                .command-progress-fill{{height:100%;border-radius:999px;background:linear-gradient(90deg, var(--secondary), var(--primary));transition:width .35s ease;}}
                .log-output{{margin:0;white-space:pre-wrap;word-break:break-word;font:13px/1.45 Consolas,Monaco,monospace;color:var(--text);}}
                .eyebrow{{display:inline-block;margin-bottom:10px;font-size:12px;font-weight:800;letter-spacing:.14em;text-transform:uppercase;color:#8b6f4a;}}
                .section-title{{margin:0 0 6px;font-size:24px;color:var(--text);}}
                .section-subtitle{{margin:0;color:var(--muted);overflow-wrap:anywhere;word-break:break-word;}}
                .start-card{{display:flex;flex-direction:column;justify-content:space-between;}}
                .command-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:14px;}}
                .command-grid form{{min-width:0;}}
                .command-grid button{{width:100%;height:100%;min-height:48px;display:flex;align-items:center;justify-content:center;text-align:center;line-height:1.25;padding:12px 14px;}}
                .card-topline{{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;margin-bottom:8px;}}
                .file-chip{{display:inline-flex;align-items:center;padding:6px 10px;border-radius:999px;background:rgba(201,111,50,.12);border:1px solid rgba(201,111,50,.2);font-size:12px;font-weight:700;color:#7c4b21;}}
                .key-status-wrap{{display:inline-flex;align-items:center;justify-content:flex-end;gap:8px;max-width:62%;}}
                .key-status-icons{{display:inline-flex;gap:6px;align-items:center;flex:none;}}
                .key-status-badge{{display:inline-flex;align-items:center;max-width:100%;padding:6px 10px;border-radius:999px;border:1px solid transparent;font-size:12px;font-weight:700;white-space:normal;line-height:1.25;text-align:right;}}
                .key-status-ok{{background:rgba(31,122,106,.14);border-color:rgba(31,122,106,.3);color:#9be4d3;}}
                .key-status-fail{{background:rgba(168,68,47,.14);border-color:rgba(168,68,47,.28);color:#ffbeb2;}}
                .key-status-warn{{background:rgba(201,111,50,.14);border-color:rgba(201,111,50,.28);color:#f6c892;}}
                .key-status-empty{{background:rgba(159,176,200,.1);border-color:rgba(159,176,200,.18);color:var(--muted);}}
                .key-status-note{{margin:-4px 0 4px;color:var(--muted);font-size:14px;line-height:1.45;overflow-wrap:anywhere;}}
        .protocol-card{{min-width:0;}}
        .pool-details{{margin-top:12px;border-top:1px solid var(--border);padding-top:12px;cursor:pointer;}}
        .pool-summary{{font-size:13px;font-weight:700;color:var(--text);padding:4px 0;}}
        .pool-list{{list-style:none;padding:0;margin:8px 0;display:grid;gap:6px;}}
        .pool-item{{display:flex;align-items:center;gap:8px;padding:6px 10px;border-radius:10px;background:rgba(255,255,255,.03);border:1px solid var(--border);font-size:12px;}}
        .pool-item-active{{border-color:rgba(31,122,106,.62);background:rgba(31,122,106,.14);}}
        .pool-apply-form{{flex:1;min-width:0;margin:0;display:block;}}
        .pool-apply-btn{{width:100%;min-width:0;padding:4px 0;border:none;background:transparent;box-shadow:none;color:var(--text);font-size:12px;font-weight:700;text-align:left;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}}
        .pool-apply-btn:hover{{background:transparent;filter:none;transform:none;color:var(--primary-hover);}}
        .pool-key-icons{{display:inline-flex;gap:6px;align-items:center;}}
        .pool-key-meta{{color:var(--muted);font-size:11px;white-space:nowrap;}}
        .pool-item-form{{margin:0;padding:0;display:inline;}}
        .pool-delete-btn{{padding:2px 8px;border:none;border-radius:6px;background:rgba(168,68,47,.2);color:#ffbeb2;font-size:13px;cursor:pointer;line-height:1.4;box-shadow:none;min-width:0;}}
        .pool-delete-btn:hover{{background:rgba(168,68,47,.4);filter:none;transform:none;}}
        .pool-empty{{color:var(--muted);justify-content:center;}}
        .pool-add-form{{margin-top:8px;display:grid;gap:8px;}}
        .pool-add-actions{{display:flex;gap:8px;}}
        .pool-add-actions button{{padding:8px 14px;font-size:13px;}}
        .pool-subscribe-row{{margin-top:8px;display:flex;align-items:stretch;gap:8px;}}
        .pool-subscribe-form{{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;flex:1;}}
        .pool-subscribe-form button,.pool-clear-btn{{padding:8px 14px;font-size:13px;line-height:1.2;min-height:40px;white-space:nowrap;}}
        .pool-clear-form{{margin:0;display:flex;}}
        .pool-clear-btn{{height:100%;}}
        .secondary-button{{border-color:rgba(78,216,205,.5);background:rgba(34,67,73,.28);color:#96f1eb;box-shadow:none;}}
        .wide{{grid-column:1 / -1;}}
        .app-shell{{max-width:1240px;margin:0 auto;}}
        .topbar{{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:14px;padding:14px 16px;border:1px solid var(--border);border-radius:8px;background:rgba(23,30,40,.96);box-shadow:var(--shadow);position:sticky;top:10px;z-index:20;}}
        [data-theme="light"] .topbar{{background:rgba(255,253,248,.96);}}
        .brand{{display:flex;align-items:center;gap:12px;min-width:0;}}
        .brand-mark{{display:inline-flex;align-items:center;justify-content:center;width:40px;height:40px;border-radius:8px;background:rgba(31,122,106,.18);border:1px solid rgba(31,122,106,.35);color:#7ff0d8;font-size:15px;font-weight:900;text-transform:uppercase;}}
        .brand p{{margin:0;font-size:12px;color:var(--muted);}}
        .topbar-actions{{display:flex;align-items:center;justify-content:flex-end;gap:10px;flex-wrap:wrap;position:relative;}}
        .api-pill{{display:inline-flex;align-items:center;max-width:min(520px,42vw);padding:8px 10px;border-radius:8px;background:rgba(31,122,106,.14);border:1px solid rgba(31,122,106,.28);color:#9be4d3;font-size:12px;font-weight:700;line-height:1.35;white-space:normal;overflow:visible;text-overflow:clip;overflow-wrap:anywhere;word-break:break-word;}}
        .workspace-layout{{display:grid;grid-template-columns:128px minmax(0,1fr);gap:14px;align-items:start;}}
        .side-nav{{position:sticky;top:96px;display:grid;gap:8px;padding:10px;border:1px solid var(--border);border-radius:8px;background:rgba(23,30,40,.94);box-shadow:var(--shadow);}}
        [data-theme="light"] .side-nav{{background:rgba(255,253,248,.94);}}
        .nav-item{{display:flex;align-items:center;gap:8px;justify-content:flex-start;min-height:46px;padding:10px;border:1px solid transparent;border-radius:8px;background:transparent;color:var(--muted);box-shadow:none;font-size:14px;line-height:1.2;}}
        .nav-item:hover{{transform:none;filter:none;background:rgba(255,255,255,.05);}}
        .nav-item.active{{background:rgba(31,122,106,.18);border-color:rgba(31,122,106,.36);color:var(--text);}}
        .app-main{{min-width:0;}}
        .app-view{{display:none;}}
        .app-view.active{{display:block;}}
        .view-head{{margin-bottom:12px;padding:16px 18px;border:1px solid var(--border);border-radius:8px;background:rgba(23,30,40,.92);}}
        [data-theme="light"] .view-head{{background:rgba(255,253,248,.92);}}
        .view-head h2{{margin:0 0 6px;font-size:24px;}}
        .status-dashboard{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-bottom:12px;}}
        .status-card-wide{{grid-column:1 / -1;min-height:0;}}
        .segmented{{display:flex;gap:0;margin-bottom:12px;border:1px solid var(--border);border-radius:8px;overflow:auto;background:rgba(255,255,255,.03);}}
        .seg-tab{{display:flex;align-items:center;justify-content:center;gap:8px;min-width:118px;padding:12px 14px;border-radius:0;border-right:1px solid var(--border);background:transparent;color:var(--muted);box-shadow:none;white-space:nowrap;}}
        .seg-tab:last-child{{border-right:none;}}
        .seg-tab:hover{{transform:none;filter:none;background:rgba(255,255,255,.05);}}
        .seg-tab.active{{background:rgba(31,122,106,.22);color:var(--text);}}
        .tab-count{{display:inline-flex;align-items:center;justify-content:center;min-width:24px;padding:2px 6px;border-radius:999px;background:rgba(255,255,255,.08);font-size:12px;}}
        .protocol-workspace,.list-workspace{{display:none;padding:18px;border:1px solid var(--border);border-radius:8px;background:linear-gradient(180deg, rgba(23,30,40,.96), rgba(32,42,56,.94));box-shadow:var(--shadow);}}
        [data-theme="light"] .protocol-workspace,[data-theme="light"] .list-workspace{{background:linear-gradient(180deg, rgba(255,253,248,.96), rgba(245,237,224,.94));}}
        .protocol-workspace.active,.list-workspace.active{{display:block;}}
        .workspace-head{{display:flex;align-items:flex-start;justify-content:space-between;gap:14px;margin-bottom:14px;}}
        .subtabs{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));border:1px solid var(--border);border-radius:8px;overflow:hidden;margin-bottom:14px;}}
        .subtab{{border-radius:0;border-right:1px solid var(--border);background:transparent;color:var(--muted);box-shadow:none;}}
        .subtab:last-child{{border-right:none;}}
        .subtab.active{{background:rgba(31,122,106,.2);color:var(--text);}}
        .subtab:hover{{transform:none;filter:none;background:rgba(255,255,255,.05);}}
        .protocol-subview{{display:none;}}
        .protocol-subview.active{{display:grid;gap:14px;}}
        .field-label{{font-size:12px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);}}
        .form-actions{{display:flex;gap:10px;flex-wrap:wrap;}}
        .form-actions button{{min-width:160px;}}
        .social-list-actions{{display:grid;grid-template-columns:repeat(auto-fit,minmax(118px,1fr));gap:8px;align-items:stretch;margin-top:8px;}}
        .social-list-title{{display:flex;align-items:center;color:var(--muted);font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;}}
        .social-list-actions button{{width:100%;min-width:0;height:32px;min-height:32px;}}
        .pool-toolbar{{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:12px;}}
        .pool-toolbar form{{display:block;}}
        .pool-table-wrap{{overflow:auto;border:1px solid var(--border);border-radius:8px;}}
        .pool-table{{width:100%;border-collapse:collapse;font-size:13px;}}
        .pool-table th,.pool-table td{{padding:10px;border-bottom:1px solid var(--border);text-align:left;vertical-align:middle;}}
        .pool-table th{{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);background:rgba(255,255,255,.03);}}
        .pool-row:last-child td{{border-bottom:none;}}
        .pool-row-active{{background:rgba(31,122,106,.12);}}
        .pool-active-cell{{width:72px;color:#9be4d3;font-weight:700;}}
        .pool-key-cell{{min-width:260px;}}
        .pool-hash{{display:none;}}
        .pool-mobile-active{{display:none;margin-left:6px;padding:1px 6px;border-radius:5px;background:rgba(48,191,181,.16);border:1px solid rgba(48,191,181,.34);color:#9ff7ef;font-size:9px;font-weight:900;letter-spacing:.04em;text-transform:uppercase;line-height:1.2;vertical-align:middle;}}
        .pool-row-active .pool-mobile-active{{display:inline-flex;align-items:center;}}
        .pool-service-cell{{width:48px;text-align:center;}}
        .pool-checked-cell{{width:92px;color:var(--muted);font-size:12px;}}
        .pool-actions-cell{{width:110px;}}
        .pool-actions-cell form{{display:block;}}
        .pool-empty-row td{{text-align:center;color:var(--muted);}}
        .pool-add-form,.pool-subscribe-form,.list-editor-form{{margin-top:0;}}
        .overview-service-grid,.service-groups{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;}}
        .overview-service-grid{{margin-top:12px;}}
        .service-panel{{border-radius:8px;}}
        .service-panel h3{{margin:0 0 12px;font-size:18px;}}
        .key-status-icons img,.pool-service-cell img,.status-value img,.api-pill img{{width:20px!important;height:20px!important;}}
        /* Compact design pass: one visual language for cards, forms, buttons and navigation. */
        :root{{
            --scrollbar-size:8px;
            --scrollbar-track:#111923;
            --scrollbar-thumb:#415365;
            --scrollbar-thumb-hover:#53687d;
            --focus-ring:0 0 0 3px rgba(78,216,205,.16);
            --radius-panel:10px;
            --radius-control:8px;
        }}
        html{{scrollbar-color:var(--scrollbar-thumb) var(--scrollbar-track);scrollbar-width:thin;}}
        body{{font-family:Arial,"Segoe UI",system-ui,-apple-system,BlinkMacSystemFont,sans-serif;background:linear-gradient(145deg,#0c1118 0%,#111821 48%,#0b1016 100%);padding:14px;}}
        *{{scrollbar-color:var(--scrollbar-thumb) var(--scrollbar-track);scrollbar-width:thin;}}
        *::-webkit-scrollbar{{width:var(--scrollbar-size);height:var(--scrollbar-size);}}
        *::-webkit-scrollbar-track{{background:var(--scrollbar-track);border-radius:999px;}}
        *::-webkit-scrollbar-thumb{{background:var(--scrollbar-thumb);border:2px solid var(--scrollbar-track);border-radius:999px;}}
        *::-webkit-scrollbar-thumb:hover{{background:var(--scrollbar-thumb-hover);}}
        [data-theme="light"] body{{background:linear-gradient(145deg,#f7f3ea 0%,#ece3d4 100%);}}
        button{{min-height:32px;border:1px solid rgba(78,216,205,.5);border-radius:8px;background:rgba(34,67,73,.28);box-shadow:none;color:#96f1eb;font-size:12px;font-weight:650;line-height:1.2;padding:6px 9px;}}
        button:focus-visible,input:focus-visible,textarea:focus-visible,select:focus-visible{{outline:none;border-color:rgba(78,216,205,.62);box-shadow:var(--focus-ring);}}
        button:hover{{filter:none;transform:none;border-color:rgba(96,214,205,.62);background:rgba(35,98,104,.44);}}
        button.danger{{border-color:rgba(205,86,82,.52);background:rgba(94,36,42,.52);color:#ffb7b1;}}
        button.danger:hover{{background:rgba(122,45,49,.62);border-color:rgba(230,109,101,.68);}}
        .secondary-button,.success-button,.outline-button,.service-preset-btn{{border-color:rgba(78,216,205,.5);background:rgba(34,67,73,.28);color:#96f1eb;box-shadow:none;}}
        .secondary-button:hover,.success-button:hover,.outline-button:hover,.service-preset-btn:hover{{background:rgba(35,98,104,.44);border-color:rgba(96,214,205,.62);}}
        input,textarea,select{{border-radius:8px;background:rgba(11,17,25,.58);border:1px solid rgba(91,124,150,.42);font-size:12px;line-height:1.34;padding:7px 9px;}}
        input:focus,textarea:focus,select:focus{{border-color:rgba(78,216,205,.62);box-shadow:0 0 0 3px rgba(78,216,205,.1);}}
        textarea{{min-height:78px;}}
        .topbar,.side-nav,.view-head,.panel,.protocol-workspace,.list-workspace,.confirm-card{{border-radius:10px;background:rgba(17,25,35,.88);border-color:rgba(91,124,150,.34);box-shadow:0 14px 34px rgba(0,0,0,.22);backdrop-filter:blur(10px);}}
        .topbar{{top:8px;padding:9px 10px;margin-bottom:10px;justify-content:stretch;}}
        .brand-mark{{width:40px;height:40px;background:rgba(48,191,181,.14);border-color:rgba(83,232,219,.32);color:#78f5ec;}}
        h1{{font-size:18px;font-weight:700;}}
        h2{{font-size:19px;font-weight:700;line-height:1.22;}}
        .brand p,.section-subtitle,.status-note,.key-status-note{{color:#b9c6d3;}}
        .topbar-actions{{width:100%;display:grid;grid-template-columns:minmax(340px,.9fr) minmax(320px,1.2fr) auto auto auto;align-items:center;justify-content:stretch;gap:8px;}}
        .app-caption{{display:block;min-width:0;color:#eef7ff;white-space:normal;}}
        .app-caption strong{{display:block;max-width:none;font-size:15px;font-weight:800;line-height:1.18;letter-spacing:0;}}
        .app-branch{{display:block;margin-top:3px;font-size:11px;font-weight:700;line-height:1.2;color:var(--muted);}}
        .version-badge{{justify-self:end;align-self:start;display:inline-flex;align-items:center;justify-content:center;min-height:22px;padding:3px 7px;border-radius:7px;border:1px solid rgba(91,124,150,.42);background:rgba(17,25,35,.7);color:var(--muted);font-size:10px;font-weight:800;line-height:1;letter-spacing:.04em;white-space:nowrap;box-shadow:none;}}
        [data-theme="light"] .version-badge{{background:rgba(255,253,248,.82);}}
        .api-pill,.mode-toggle,.theme-toggle{{min-height:36px;border-radius:8px;border-color:rgba(91,124,150,.42);background:rgba(17,25,35,.76);box-shadow:none;font-size:12px;}}
        .mode-toggle,.theme-toggle{{border-color:rgba(78,216,205,.5);background:rgba(34,67,73,.28);color:#96f1eb;}}
        .api-pill{{display:grid;grid-template-columns:auto minmax(0,1fr);gap:7px;align-items:center;width:100%;max-width:none;font-size:12px;line-height:1.25;color:#d9e6ef;}}
        .api-pill::before{{content:"";display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:6px;background-color:rgba(48,191,181,.14);background-image:url("data:image/svg+xml;base64,{TELEGRAM_SVG_B64}");background-repeat:no-repeat;background-position:center;background-size:13px 13px;}}
        .workspace-layout{{grid-template-columns:138px minmax(0,1fr);gap:12px;}}
        .side-nav{{top:86px;padding:9px;gap:7px;}}
        .nav-item{{min-height:40px;padding:8px 9px;color:#c7d2df;}}
        .nav-item span{{font-size:13px;}}
        .nav-icon{{width:16px;height:16px;flex:none;stroke:currentColor;stroke-width:1.9;stroke-linecap:round;stroke-linejoin:round;fill:none;}}
        .nav-item.active{{background:rgba(48,191,181,.13);border-color:rgba(78,216,205,.32);color:#9af8f1;}}
        .view-head{{padding:11px 13px;margin-bottom:9px;}}
        .view-head h2{{margin-bottom:4px;font-size:19px;}}
        .eyebrow{{color:#d3a557;font-size:11px;letter-spacing:.14em;}}
        .section-subtitle{{font-size:13px;line-height:1.35;}}
        .status-dashboard{{grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;margin-bottom:9px;}}
        .status-card{{position:relative;min-height:76px;padding:10px;border-radius:9px;background:linear-gradient(145deg,rgba(20,31,43,.94),rgba(15,23,32,.94));border:1px solid rgba(91,124,150,.34);box-shadow:none;}}
        .status-card-wide{{grid-column:auto;}}
        .status-card-top{{display:flex;align-items:flex-start;gap:8px;width:100%;}}
        .status-copy{{min-width:0;flex:1;}}
        .card-icon{{display:inline-flex;align-items:center;justify-content:center;flex:none;width:28px;height:28px;border-radius:7px;background:rgba(48,191,181,.14);border:1px solid rgba(78,216,205,.22);color:#76eee5;font-size:15px;line-height:1;}}
        .card-icon img{{width:17px!important;height:17px!important;}}
        .status-dot{{width:8px;height:8px;border-radius:50%;background:#68d36f;box-shadow:0 0 0 3px rgba(104,211,111,.12);flex:none;margin-top:5px;}}
        .status-label{{margin:0 0 4px;color:#edf5fb;font-size:12px;font-weight:700;letter-spacing:0;text-transform:none;}}
        .status-value{{font-size:13px;font-weight:700;color:#75eee5;}}
        .status-card-wide .status-value{{font-size:12px;font-weight:600;line-height:1.35;color:#dce8f1;}}
        .status-note{{font-size:12px;line-height:1.35;}}
        .status-card .outline-button,.status-card form{{margin-top:auto;}}
        .status-card-actions{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:auto;}}
        .status-card-actions form{{display:block;margin:0;}}
        .status-card-actions button{{width:100%;min-width:0;margin-top:0;}}
        .overview-service-grid{{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:10px;}}
        .service-panel,.overview-key-panel{{padding:11px;border-radius:9px;background:linear-gradient(145deg,rgba(20,31,43,.94),rgba(15,23,32,.94));}}
        .service-panel h3{{font-size:14px;line-height:1.22;margin-bottom:8px;}}
        .command-grid{{gap:7px;margin-top:0;}}
        .command-grid button{{min-height:34px;justify-content:center;}}
        .overview-key-panel{{margin-top:10px;}}
        .overview-key-panel .key-editor-form{{display:grid;gap:7px;}}
        .overview-key-panel .form-actions{{gap:8px;}}
        .protocol-tabs,.list-tabs{{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));overflow:hidden;}}
        .protocol-tabs .seg-tab,.list-tabs .seg-tab{{min-width:0;}}
        .segmented,.subtabs,.pool-table-wrap{{border-color:rgba(91,124,150,.34);border-radius:var(--radius-panel);background:rgba(11,17,25,.34);overflow:hidden;}}
        .seg-tab,.subtab{{min-height:32px;color:#c7d2df;padding:6px 8px;font-size:12px;border-radius:0;}}
        .seg-tab.active,.subtab.active{{background:rgba(48,191,181,.14);color:#94f3ec;}}
        .key-status-wrap{{max-width:none;flex:none;gap:6px;align-items:center;}}
        .key-status-icons{{order:2;gap:5px;}}
        .key-status-badge{{order:1;max-width:none;padding:5px 9px;font-size:11px;line-height:1.15;white-space:nowrap;text-align:left;}}
        .protocol-workspace,.list-workspace{{padding:10px;}}
        .workspace-head{{margin-bottom:8px;}}
        .field-label{{color:#9fb0c8;letter-spacing:.08em;font-size:11px;}}
        .form-actions button{{min-width:140px;}}
        .protocol-subview.active{{gap:10px;}}
        .protocol-subview-import.active{{grid-template-columns:minmax(0,1.2fr) minmax(280px,.8fr);align-items:start;}}
        .protocol-subview-import .pool-add-form,.protocol-subview-import .pool-subscribe-form{{padding:9px;border:1px solid rgba(91,124,150,.28);border-radius:9px;background:rgba(255,255,255,.025);}}
        .protocol-subview-import .pool-add-form{{grid-template-columns:minmax(0,1fr) auto;align-items:end;}}
        .protocol-subview-import .pool-add-form .field-label{{grid-column:1 / -1;}}
        .protocol-subview-import .pool-add-form textarea{{min-height:68px;}}
        .protocol-subview-import .pool-add-form button{{justify-self:start;min-width:150px;}}
        .protocol-subview-import .pool-subscribe-form{{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:7px;align-items:end;}}
        .protocol-subview-import .pool-subscribe-form .field-label{{grid-column:1 / -1;}}
        .protocol-subview-import .pool-subscribe-form input{{min-width:0;}}
        .protocol-subview-import .pool-subscribe-form button{{white-space:nowrap;}}
        .protocol-subview-check > form{{justify-self:start;}}
        .protocol-subview-check > form button{{min-width:180px;}}
        .pool-table{{font-size:11px;}}
        .pool-table th,.pool-table td{{padding:4px 6px;line-height:1.22;}}
        .pool-table th{{font-size:10px;letter-spacing:.06em;}}
        .pool-icon-head{{text-align:center;letter-spacing:0;}}
        .pool-custom-head{{text-align:center;}}
        .pool-icon-head img{{width:16px!important;height:16px!important;margin:0;vertical-align:middle;}}
        .pool-key-cell{{min-width:220px;}}
        .pool-key-cell .pool-apply-form{{display:inline-block;max-width:100%;vertical-align:middle;}}
        .pool-apply-btn{{min-height:0;height:auto;padding:0;font-size:11px;font-weight:600;line-height:1.22;}}
        .pool-hash{{display:none;}}
        .pool-service-cell{{width:32px;}}
        .pool-custom-cell{{width:96px;}}
        .pool-custom-cell,.pool-service-cell{{text-align:center;}}
        .pool-table:not(.has-custom-checks) .pool-custom-head,
        .pool-table:not(.has-custom-checks) .pool-custom-cell{{display:none;}}
        .pool-table:not(.has-custom-checks) .pool-col-custom{{display:none;width:0!important;}}
        .pool-custom-empty{{color:var(--muted);font-size:10px;}}
        .custom-service-badge{{display:inline-flex;align-items:center;justify-content:center;min-width:24px;height:18px;margin:1px 2px 1px 0;padding:0 5px;border-radius:6px;border:1px solid rgba(91,124,150,.42);background:rgba(111,127,146,.15);color:#b9c6d3;font-size:10px;font-weight:800;line-height:1;letter-spacing:0;vertical-align:middle;}}
        .custom-service-slot{{display:inline-flex;align-items:center;justify-content:center;width:32px;min-width:32px;height:18px;margin:0;vertical-align:middle;}}
        .service-icon-img{{width:18px!important;height:18px!important;object-fit:contain;border-radius:5px;vertical-align:middle;}}
        .custom-service-slot .service-icon-img{{width:18px!important;height:18px!important;}}
        .key-status-icons .service-icon-img{{width:20px!important;height:20px!important;}}
        .service-probe-mark{{display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:5px;border:1px solid rgba(91,124,150,.34);font-size:11px;font-weight:800;line-height:1;}}
        .service-probe-fail{{color:var(--muted);background:transparent;border-color:transparent;}}
        .service-probe-unknown{{color:#9fb0c8;background:rgba(91,124,150,.12);}}
        .custom-service-ok{{background:rgba(31,122,106,.18);border-color:rgba(78,216,205,.38);color:#95f3ec;}}
        .custom-service-fail{{background:transparent;border-color:transparent;color:var(--muted);}}
        .custom-service-unknown,.custom-service-neutral{{background:rgba(91,124,150,.14);border-color:rgba(91,124,150,.34);color:#c7d2df;}}
        .pool-custom-cell .custom-service-slot{{background:transparent!important;border-color:transparent!important;}}
        .custom-check-card{{display:grid;gap:8px;padding:9px;border-radius:9px;border:1px solid rgba(91,124,150,.34);background:rgba(11,17,25,.36);}}
        .custom-check-head{{display:flex;justify-content:space-between;gap:10px;align-items:center;}}
        .custom-check-head strong{{display:block;font-size:13px;color:#edf5fb;}}
        .custom-check-head small{{display:block;margin-top:2px;color:#9fb0c8;font-size:11px;line-height:1.25;}}
        .service-preset-grid{{display:flex;flex-wrap:wrap;gap:6px;align-items:stretch;}}
        .service-preset-grid form{{margin:0;flex:0 0 86px;min-width:0;}}
        .service-preset-btn{{width:86px;min-width:0;display:flex;align-items:center;justify-content:center;gap:4px;min-height:28px;padding:4px 5px;background:rgba(34,67,73,.28);}}
        .service-preset-btn span:last-child{{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:10.5px;}}
        .service-preset-btn:disabled{{opacity:.55;cursor:default;}}
        .preset-icon{{display:inline-flex;align-items:center;justify-content:center;flex:none;width:18px;height:18px;border-radius:6px;overflow:hidden;}}
        .preset-icon img{{width:18px!important;height:18px!important;display:block;}}
        .custom-check-list{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:6px;}}
        .custom-check-empty{{padding:8px;border:1px dashed rgba(91,124,150,.34);border-radius:8px;color:#9fb0c8;font-size:12px;text-align:center;}}
        .custom-check-item{{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:6px;align-items:center;min-height:34px;padding:5px 6px;border-radius:8px;background:rgba(255,255,255,.03);border:1px solid rgba(91,124,150,.28);}}
        .custom-check-copy{{min-width:0;display:grid;gap:1px;}}
        .custom-check-copy strong{{font-size:12px;font-weight:700;color:#edf5fb;}}
        .custom-check-copy small{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#9fb0c8;font-size:10px;}}
        .custom-check-form{{display:grid;grid-template-columns:minmax(120px,.65fr) minmax(180px,1fr) auto;gap:7px;align-items:center;}}
        .custom-check-form button{{justify-self:start;white-space:nowrap;}}
        .pool-checked-cell{{width:74px;font-size:10px;}}
        .pool-actions-cell{{width:78px;}}
        .pool-delete-btn{{min-height:20px;height:auto;padding:1px 6px;font-size:10px;line-height:1.15;}}
        .pool-service-cell img{{width:16px!important;height:16px!important;}}
        .pool-table{{width:100%;table-layout:fixed;}}
        .pool-col-status{{width:0!important;visibility:collapse;}}
        .pool-col-icon{{width:32px;}}
        .pool-col-checked{{width:74px;}}
        .pool-col-actions{{width:78px;}}
        .pool-table th,.pool-table td{{vertical-align:middle;}}
        .pool-status-head,.pool-active-cell{{display:none;}}
        .pool-table .pool-icon-head,.pool-table .pool-service-cell,.pool-table .pool-custom-head,.pool-table .pool-custom-cell,.pool-table .pool-checked-head,.pool-table .pool-checked-cell,.pool-table .pool-actions-head,.pool-table .pool-actions-cell{{text-align:center;}}
        .pool-service-cell,.pool-custom-cell{{line-height:1;}}
        .pool-icon-head,.pool-service-cell,.pool-custom-head,.pool-custom-cell{{padding-left:0!important;padding-right:0!important;}}
        .pool-icon-head img,.pool-service-cell img,.pool-service-cell .service-probe-mark,.pool-custom-cell .service-probe-mark,.pool-custom-cell .custom-service-slot,.pool-custom-head .custom-service-slot{{display:inline-flex;margin-left:auto;margin-right:auto;vertical-align:middle;}}
        .pool-custom-head .service-icon-img,.pool-custom-cell .service-icon-img{{width:16px!important;height:16px!important;}}
        .pool-service-cell .service-probe-mark,.pool-custom-cell .service-probe-mark{{width:16px;height:16px;font-size:10px;}}
        .pool-custom-cell,.pool-custom-head{{white-space:nowrap;overflow:hidden;}}
        .pool-key-cell{{overflow:hidden;}}
        .pool-actions-cell form{{display:flex;justify-content:center;}}
        .pool-table-wrap{{max-height:min(54vh,460px);overflow-y:auto;overflow-x:hidden;}}
        .protocol-subview[data-subview="pool"].active{{min-height:0;grid-template-rows:auto minmax(0,1fr);}}
        .protocol-subview[data-subview="pool"].active .pool-table-wrap{{min-height:0;}}
        .pool-table-wrap,.protocol-subview-import.active,.list-editor-form textarea,.key-editor-form textarea,textarea{{scrollbar-gutter:stable;scrollbar-color:var(--scrollbar-thumb) var(--scrollbar-track);scrollbar-width:thin;}}
        .app-shell{{max-width:1600px;}}
        .protocol-workspace.active{{padding:9px;}}
        .protocol-workspace .workspace-head{{align-items:center;margin-bottom:6px;}}
        .protocol-workspace .workspace-head h2{{margin:0;font-size:18px;}}
        .protocol-workspace .workspace-head .eyebrow{{margin-bottom:5px;}}
        .key-status-note{{margin:3px 0 0;font-size:12px;line-height:1.25;}}
        .subtabs{{margin-bottom:8px;}}
        .subtab{{min-height:30px;padding:5px 8px;}}
        .protocol-subview.active{{gap:8px;}}
        .pool-toolbar{{margin-bottom:7px;}}
        .pool-toolbar form{{margin:0;}}
        .pool-toolbar button,.pool-clear-btn{{height:32px;min-height:32px;padding:5px 12px;line-height:1.15;}}
        .pool-table-wrap{{scrollbar-gutter:stable;max-height:min(58vh,500px);}}
        .pool-table th,.pool-table td{{padding:4px 5px;}}
        .pool-col-actions{{width:96px;}}
        .pool-actions-head,.pool-actions-cell{{width:96px;}}
        .pool-actions-head{{white-space:nowrap;font-size:9px;letter-spacing:.02em;}}
        .pool-delete-btn{{height:22px;min-height:22px;padding:2px 7px;font-size:10px;line-height:1;white-space:nowrap;}}
        .pool-checked-cell,.pool-checked-head{{white-space:nowrap;}}
        .protocol-subview-import.active{{grid-template-columns:minmax(0,1fr) minmax(420px,.72fr);gap:8px;align-items:stretch;}}
        .protocol-subview-import .pool-add-form,.protocol-subview-import .pool-subscribe-form{{height:106px;min-height:0;padding:8px;align-self:stretch;}}
        .protocol-subview-import .pool-add-form{{display:grid;grid-template-columns:minmax(0,1fr) 150px;grid-template-rows:auto 66px;gap:7px;align-items:stretch;align-content:start;}}
        .protocol-subview-import .pool-add-form .field-label{{grid-column:1 / -1;margin:0;}}
        .protocol-subview-import .pool-add-form textarea{{grid-column:1;min-height:66px;height:66px;resize:vertical;}}
        .protocol-subview-import .pool-add-form button{{grid-column:2;align-self:end;justify-self:stretch;width:100%;min-width:0;height:32px;margin-top:0;}}
        .protocol-subview-import .pool-subscribe-form{{display:grid;grid-template-columns:minmax(0,1fr) 190px;grid-template-rows:auto 66px;gap:7px;align-content:start;align-items:end;}}
        .protocol-subview-import .pool-subscribe-form .field-label{{grid-column:1 / -1;margin:0;}}
        .protocol-subview-import .pool-subscribe-form input{{height:32px;min-height:32px;align-self:end;}}
        .protocol-subview-import .pool-subscribe-form button{{height:32px;min-height:32px;width:100%;padding:5px 10px;white-space:nowrap;align-self:end;}}
        @media (min-width: 1024px){{
            html,body{{height:100%;overflow:hidden;}}
            body{{padding:8px;}}
            .app-shell{{height:calc(100vh - 16px);display:flex;flex-direction:column;min-height:0;}}
            .topbar{{position:static;flex:none;margin-bottom:8px;}}
            .workspace-layout{{flex:1;min-height:0;align-items:stretch;}}
            .side-nav{{position:static;align-self:start;}}
            .app-main{{height:100%;min-height:0;overflow:hidden;}}
            .app-view.active{{height:100%;min-height:0;overflow:hidden;}}
            .app-view[data-view="status"].active{{display:grid;grid-template-rows:auto auto auto auto;gap:8px;align-content:start;}}
            .app-view[data-view="keys"].active,.app-view[data-view="lists"].active{{display:grid;grid-template-rows:auto auto minmax(0,1fr);gap:8px;}}
            .view-head,.segmented,.status-dashboard,.overview-service-grid{{margin-bottom:0;}}
            .view-head{{padding:9px 12px;}}
            .status-dashboard{{gap:8px;}}
            .status-card{{min-height:68px;padding:9px;}}
            .overview-service-grid{{gap:8px;margin-top:0;}}
            .service-panel,.overview-key-panel{{padding:9px;}}
            .overview-key-panel{{min-height:0;overflow:hidden;align-self:start;}}
            .overview-key-panel .workspace-head{{display:none;}}
            .overview-key-panel .key-editor-form{{display:grid;grid-template-columns:minmax(0,1fr) minmax(480px,.42fr);grid-template-rows:auto 44px;gap:6px 10px;align-items:stretch;}}
            .overview-key-panel .key-editor-form .field-label{{grid-column:1 / -1;margin:0;line-height:1.1;}}
            .overview-key-panel textarea{{grid-column:1;grid-row:2;height:44px;min-height:44px;max-height:44px;resize:none;}}
            .overview-key-panel .form-actions{{grid-column:2;grid-row:2;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;align-self:stretch;align-items:stretch;margin:0;}}
            .overview-key-panel .form-actions button{{width:100%;min-width:0;height:44px;min-height:44px;padding:5px 10px;border-radius:8px;font-size:12px;font-weight:700;}}
            .protocol-panels,.list-panels{{min-height:0;overflow:hidden;}}
            .protocol-workspace.active{{height:100%;min-height:0;display:grid;grid-template-rows:auto auto minmax(0,1fr);overflow:hidden;}}
            .protocol-subview.active{{min-height:0;overflow:hidden;}}
            .protocol-subview[data-subview="pool"].active{{display:grid;grid-template-rows:auto minmax(0,1fr);}}
            .pool-table-wrap{{max-height:none;height:100%;min-height:0;}}
            .key-editor-form textarea[data-key-textarea]{{height:168px;min-height:168px;max-height:168px;}}
            .protocol-subview-import.active{{overflow:auto;}}
            .list-workspace.active{{height:100%;min-height:0;display:grid;grid-template-rows:auto minmax(0,1fr);overflow:hidden;}}
            .list-editor-form{{height:100%;min-height:0;display:grid;grid-template-rows:minmax(0,1fr) auto auto;gap:8px;align-content:stretch;}}
            .list-editor-form textarea{{height:100%;min-height:0;resize:none;}}
            .list-editor-form .form-actions{{height:auto;min-height:0;align-self:end;align-items:center;align-content:center;}}
            .list-editor-form .form-actions button{{height:32px;min-height:32px;flex:0 0 auto;align-self:center;}}
        }}
        @media (min-width: 1024px){{
            .protocol-workspace.active{{height:auto;min-height:0;display:block;overflow:visible;}}
            .protocol-workspace.active:has(.protocol-subview[data-subview="pool"].active){{height:100%;display:grid;grid-template-rows:auto auto minmax(0,1fr);overflow:hidden;}}
            .protocol-workspace.active:has(.protocol-subview[data-subview="pool"].active) .protocol-subview[data-subview="pool"].active{{min-height:0;display:grid;grid-template-rows:auto minmax(0,1fr);overflow:hidden;}}
            .protocol-workspace.active:has(.protocol-subview[data-subview="subscription"].active),
            .protocol-workspace.active:has(.protocol-subview[data-subview="key"].active),
            .protocol-workspace.active:has(.protocol-subview[data-subview="check"].active){{align-self:start;}}
            .protocol-subview-import.active{{overflow:visible;align-self:start;}}
        }}
        .mobile-nav{{display:none;}}
        .confirm-backdrop{{position:fixed;inset:0;z-index:100;display:flex;align-items:center;justify-content:center;padding:18px;background:rgba(2,6,23,.72);}}
        .confirm-backdrop.hidden{{display:none;}}
        .confirm-card{{width:min(420px,100%);padding:20px;border:1px solid var(--border);border-radius:8px;background:var(--surface);box-shadow:0 24px 70px rgba(0,0,0,.42);}}
        .confirm-card h2{{margin:0 0 10px;font-size:22px;}}
        .confirm-card p{{margin:0 0 18px;color:var(--muted);}}
        .confirm-actions{{display:grid;grid-template-columns:1fr 1fr;gap:10px;}}
        @media (max-width: 760px){{
            body{{padding:10px 10px calc(128px + env(safe-area-inset-bottom, 0px));scroll-padding-bottom:calc(128px + env(safe-area-inset-bottom, 0px));}}
                        .hero{{padding:16px;border-radius:20px;}}
            .topbar{{position:static;align-items:stretch;flex-direction:column;padding:10px;}}
            .app-shell,.topbar,.app-main,.app-view,.view-head,.status-card,.service-panel,.overview-key-panel,.mobile-nav{{box-sizing:border-box;max-width:100%;}}
            .topbar-actions{{width:100%;display:grid;grid-template-columns:1fr 1fr;justify-content:stretch;gap:8px;}}
            .app-caption{{display:grid;gap:2px;min-width:0;white-space:normal;}}
            .app-caption strong{{max-width:none;font-size:14px;overflow-wrap:anywhere;}}
            .section-subtitle,.status-note,.status-value{{overflow-wrap:anywhere;}}
            .app-caption,.api-pill{{grid-column:1 / -1;}}
            .api-pill,.theme-toggle,.mode-toggle,.version-badge{{width:100%;justify-content:center;max-width:none;text-align:center;}}
            .version-badge{{align-self:stretch;min-height:34px;font-size:10px;}}
            .api-pill{{justify-content:start;text-align:left;}}
            .workspace-layout{{display:block;}}
            .side-nav{{display:none;}}
            .app-main{{padding-bottom:calc(126px + env(safe-area-inset-bottom, 0px));}}
            .mobile-nav{{position:fixed;left:10px;right:10px;bottom:calc(10px + env(safe-area-inset-bottom, 0px));z-index:50;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:4px;padding:6px;border:1px solid rgba(91,124,150,.34);border-radius:var(--radius-panel);background:rgba(12,18,26,.96);box-shadow:0 14px 34px rgba(0,0,0,.34);}}
            .mobile-nav .nav-item{{justify-content:center;flex-direction:column;gap:3px;min-height:50px;font-size:11px;padding:6px;border-radius:var(--radius-control);}}
            .view-head{{padding:14px;border-radius:10px;}}
            .view-head h2{{font-size:20px;}}
            .status-dashboard,.overview-service-grid{{grid-template-columns:1fr;}}
            .status-card-actions{{grid-template-columns:1fr;}}
            .status-card-wide{{grid-column:auto;}}
            .status-card{{min-height:0;padding:12px;}}
            .status-card-top{{gap:10px;}}
            .card-icon{{width:34px;height:34px;font-size:18px;}}
            .status-label{{font-size:13px;}}
            .status-value{{font-size:15px;}}
            .status-card-wide .status-value{{font-size:13px;line-height:1.4;}}
            .segmented{{scroll-snap-type:x mandatory;}}
            .seg-tab{{min-width:96px;scroll-snap-align:start;}}
            .protocol-tabs,.list-tabs{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));overflow:hidden;scroll-snap-type:none;border-radius:var(--radius-panel);}}
            .protocol-tabs .seg-tab,.list-tabs .seg-tab{{min-width:0;border-right:1px solid var(--border);border-bottom:1px solid var(--border);white-space:normal;}}
            .protocol-tabs .seg-tab:nth-child(2n),.list-tabs .seg-tab:nth-child(2n){{border-right:none;}}
            .protocol-tabs .seg-tab:last-child,.list-tabs .seg-tab:last-child{{grid-column:1 / -1;border-right:none;border-bottom:none;}}
            .protocol-tabs .seg-tab:first-child,.list-tabs .seg-tab:first-child{{border-top-left-radius:calc(var(--radius-panel) - 1px);}}
            .protocol-tabs .seg-tab:nth-child(2),.list-tabs .seg-tab:nth-child(2){{border-top-right-radius:calc(var(--radius-panel) - 1px);}}
            .protocol-tabs .seg-tab:last-child,.list-tabs .seg-tab:last-child{{border-bottom-left-radius:calc(var(--radius-panel) - 1px);border-bottom-right-radius:calc(var(--radius-panel) - 1px);}}
            .protocol-workspace{{padding:9px;}}
            .protocol-workspace .workspace-head{{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:8px;margin-bottom:7px;}}
            .protocol-workspace .workspace-head .eyebrow{{display:none;}}
            .protocol-workspace .workspace-head h2{{font-size:18px;margin:0;}}
            .key-status-note{{display:none;}}
            .key-status-wrap{{max-width:100%;margin-top:0;}}
            .key-status-badge{{font-size:10px;padding:4px 7px;}}
            .key-status-icons .service-icon-img{{width:18px!important;height:18px!important;}}
            .subtabs{{grid-template-columns:repeat(2,minmax(0,1fr));}}
            .subtab{{min-height:30px;padding:5px 6px;}}
            .key-editor-form textarea[data-key-textarea]{{min-height:132px;max-height:34vh;resize:vertical;font-size:12px;line-height:1.32;}}
            .overview-key-panel .key-editor-form{{display:grid;gap:8px;}}
            .overview-key-panel textarea{{min-height:96px;max-height:24vh;resize:vertical;}}
            .overview-key-panel .form-actions{{display:grid;grid-template-columns:1fr;gap:8px;margin-bottom:18px;}}
            .overview-key-panel .form-actions button{{width:100%;min-width:0;}}
            .key-editor-form .form-actions{{margin-bottom:20px;}}
            .key-editor-form .form-actions button{{width:100%;}}
            .protocol-subview-import.active{{grid-template-columns:1fr;}}
            .protocol-subview-import .pool-add-form{{grid-template-columns:1fr;}}
            .protocol-subview-import .pool-add-form .field-label{{grid-column:auto;}}
            .protocol-subview-import .pool-subscribe-form{{grid-template-columns:minmax(0,1fr) auto;}}
            .pool-toolbar{{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-bottom:8px;}}
            .pool-toolbar button{{width:100%;}}
            .social-list-actions{{grid-template-columns:1fr;}}
            .pool-table-wrap{{overflow-x:hidden;}}
            .pool-table{{display:block;width:100%;min-width:0;table-layout:auto;font-size:10px;border-collapse:separate;border-spacing:0;}}
            .pool-table colgroup{{display:none;}}
            .pool-table thead,.pool-table tbody{{display:block;width:100%;}}
            .pool-table tr{{display:grid;grid-template-columns:minmax(0,1fr) 28px 28px 32px;align-items:stretch;width:100%;min-height:30px;border-bottom:1px solid var(--border);}}
            .pool-table.has-custom-checks tr{{grid-template-columns:minmax(0,1fr) 28px 28px var(--custom-col-mobile, 28px) 32px;}}
            .pool-table tr:last-child{{border-bottom:none;}}
            .pool-table th,.pool-table td{{display:flex;align-items:center;min-width:0;min-height:30px;height:100%;padding:4px 3px;border-bottom:none;}}
            .pool-table .pool-status-head,.pool-table .pool-active-cell,.pool-table .pool-checked-head,.pool-table .pool-checked-cell{{display:none;}}
            .pool-key-head,.pool-key-cell{{width:auto!important;min-width:0;}}
            .pool-key-head,.pool-key-cell{{justify-content:flex-start;}}
            .pool-key-cell .pool-apply-form{{display:block;max-width:none;}}
            .pool-row-active .pool-key-cell{{box-shadow:inset 3px 0 0 var(--accent);background:rgba(48,191,181,.12);}}
            .pool-row-active .pool-apply-btn{{color:#92fff2;}}
            .pool-mobile-active{{display:none;margin:2px 0 0 0;width:max-content;padding:1px 5px;border-radius:5px;background:rgba(48,191,181,.18);border:1px solid rgba(48,191,181,.35);color:#9ff7ef;font-size:8px;font-weight:900;letter-spacing:.06em;text-transform:uppercase;line-height:1.2;}}
            .pool-row-active .pool-mobile-active{{display:inline-flex;}}
            .pool-apply-btn{{display:block;width:100%;font-size:10.5px;line-height:1.18;text-align:left;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}}
            .pool-hash{{display:none;}}
            .pool-service-cell,.pool-icon-head,.pool-custom-cell,.pool-custom-head,.pool-actions-head,.pool-actions-cell{{width:auto!important;padding-left:2px!important;padding-right:2px!important;text-align:center;}}
            .pool-service-cell,.pool-icon-head,.pool-custom-cell,.pool-custom-head,.pool-actions-head,.pool-actions-cell{{justify-content:center;}}
            .custom-service-slot{{width:28px;min-width:28px;height:15px;margin:0;}}
            .custom-service-slot .service-icon-img,.pool-service-cell img,.pool-icon-head img{{width:14px!important;height:14px!important;}}
            .pool-service-cell .service-probe-mark,.pool-custom-cell .service-probe-mark{{width:14px;height:14px;font-size:9px;}}
            .pool-actions-head,.pool-actions-cell{{width:32px;padding-left:2px!important;padding-right:2px!important;text-align:center;}}
            .pool-table .pool-actions-head{{font-size:0;}}
            .pool-table .pool-actions-head::after{{content:"×";font-size:11px;}}
            .pool-actions-cell form{{display:flex;justify-content:center;}}
            .pool-actions-cell .pool-delete-btn{{width:22px;height:22px;min-height:22px;padding:0;font-size:0;border-radius:6px;}}
            .pool-actions-cell .pool-delete-btn::before{{content:"×";font-size:13px;line-height:1;}}
            .service-preset-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:5px;}}
            .service-preset-grid form{{min-width:0;}}
            .service-preset-btn{{width:100%;min-width:0;gap:3px;padding:4px 3px;}}
            .service-preset-btn span:last-child{{font-size:10px;}}
            .custom-check-list{{grid-template-columns:1fr;}}
            .custom-check-form{{grid-template-columns:1fr;}}
            .service-groups{{grid-template-columns:1fr;}}
            .form-actions{{display:grid;grid-template-columns:1fr;}}
            .hero-row{{flex-direction:column;align-items:stretch;}}
            .hero-actions{{width:100%;justify-content:stretch;}}
            .hero-status-header{{flex-direction:column;align-items:flex-start;}}
            .traffic-inline{{justify-content:flex-start;}}
            .theme-toggle,.mode-toggle{{justify-content:center;}}
            .hero-popover{{position:static;min-width:0;width:100%;}}
            .mode-picker-form{{gap:8px;}}
            .mode-choice-grid{{gap:6px;}}
            .mode-choice{{min-height:34px;padding:7px 5px;font-size:12px;line-height:1.12;white-space:normal;overflow-wrap:anywhere;word-break:normal;}}
            .mode-choice span{{display:block;min-width:0;max-width:100%;overflow-wrap:anywhere;}}
            .layout{{grid-template-columns:1fr;gap:12px;}}
                        .command-grid{{grid-template-columns:1fr;}}
            .status-grid{{grid-template-columns:1fr;}}
                        .panel{{padding:12px;border-radius:10px;}}
            .pool-subscribe-row{{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:stretch;}}
            .pool-subscribe-form{{display:contents;}}
            .pool-subscribe-form input{{grid-column:1 / -1;}}
            .protocol-subview-import .pool-subscribe-form{{display:grid;}}
            .protocol-subview-import .pool-subscribe-form input{{grid-column:auto;}}
            .command-grid{{grid-template-columns:1fr 1fr;gap:10px;}}
            .command-grid button{{min-height:42px;font-size:13px;}}
            button,input,textarea,select{{font-size:13px;}}
        }}
        @media (max-width: 430px){{
            .command-grid{{grid-template-columns:1fr;}}
            .status-card-top{{align-items:flex-start;}}
            .api-pill{{font-size:12px;}}
            .mode-choice{{font-size:11px;padding:7px 4px;}}
        }}
        /* Light theme final pass. Keep it after compact/mobile rules so no dark surfaces leak through. */
        [data-theme="light"]{{
            --bg:#f4f7fb;
            --bg-accent:#e8eef5;
            --surface:#ffffff;
            --surface-soft:#eef3f8;
            --surface-strong:#e3ebf3;
            --border:#c8d5e1;
            --text:#172033;
            --muted:#536274;
            --primary:#1f7a6a;
            --primary-hover:#166457;
            --secondary:#9c6a2f;
            --danger:#b44738;
            --success-bg:#e5f5ed;
            --success-border:#9ac8b2;
            --warn-bg:#fff4df;
            --warn-border:#ddb46f;
            --shadow:0 12px 28px rgba(46,63,86,.11);
            --scrollbar-track:#f4f8fc;
            --scrollbar-thumb:#9fb2c3;
            --scrollbar-thumb-hover:#7f94a9;
            --focus-ring:0 0 0 3px rgba(31,122,106,.14);
        }}
        [data-theme="light"] body{{color:var(--text);background:linear-gradient(145deg,#f8fbff 0%,#edf3f8 48%,#e7eef5 100%);}}
        [data-theme="light"] .topbar,
        [data-theme="light"] .side-nav,
        [data-theme="light"] .view-head,
        [data-theme="light"] .panel,
        [data-theme="light"] .protocol-workspace,
        [data-theme="light"] .list-workspace,
        [data-theme="light"] .confirm-card,
        [data-theme="light"] .service-panel,
        [data-theme="light"] .overview-key-panel,
        [data-theme="light"] .status-card{{background:rgba(255,255,255,.92);border-color:var(--border);box-shadow:var(--shadow);backdrop-filter:none;}}
        [data-theme="light"] .service-panel,
        [data-theme="light"] .overview-key-panel,
        [data-theme="light"] .status-card{{background:linear-gradient(145deg,rgba(255,255,255,.96),rgba(241,246,251,.96));}}
        [data-theme="light"] h1,
        [data-theme="light"] h2,
        [data-theme="light"] h3,
        [data-theme="light"] .app-caption,
        [data-theme="light"] .app-caption strong,
        [data-theme="light"] .status-label,
        [data-theme="light"] .custom-check-head strong,
        [data-theme="light"] .custom-check-copy strong{{color:var(--text);}}
        [data-theme="light"] .brand p,
        [data-theme="light"] .section-subtitle,
        [data-theme="light"] .status-note,
        [data-theme="light"] .key-status-note,
        [data-theme="light"] .field-label,
        [data-theme="light"] .custom-check-head small,
        [data-theme="light"] .custom-check-copy small,
        [data-theme="light"] .custom-check-empty,
        [data-theme="light"] .pool-hash,
        [data-theme="light"] .pool-checked-cell{{color:var(--muted);}}
        [data-theme="light"] .status-value,
        [data-theme="light"] .status-card-wide .status-value{{color:#1f6f62;}}
        [data-theme="light"] .api-pill,
        [data-theme="light"] .mode-toggle,
        [data-theme="light"] .theme-toggle,
        [data-theme="light"] .hero-chip,
        [data-theme="light"] .traffic-chip{{background:rgba(255,255,255,.84);border-color:var(--border);color:var(--text);}}
        [data-theme="light"] .api-pill{{color:#1f564f;}}
        [data-theme="light"] .api-pill::before,
        [data-theme="light"] .card-icon{{background-color:rgba(31,122,106,.12);border-color:rgba(31,122,106,.24);color:#1f7a6a;}}
        [data-theme="light"] .hero-popover{{background:linear-gradient(180deg,rgba(255,255,255,.98),rgba(241,246,251,.96));border-color:var(--border);}}
        [data-theme="light"] .mode-choice{{background:rgba(31,122,106,.08);border-color:rgba(31,122,106,.28);color:#1f6258;}}
        [data-theme="light"] .mode-choice.active{{background:rgba(31,122,106,.13);border-color:rgba(31,122,106,.42);color:#174f48;}}
        [data-theme="light"] .mode-choice:hover{{background:rgba(31,122,106,.13);border-color:rgba(31,122,106,.42);}}
        [data-theme="light"] button{{border-color:rgba(31,122,106,.28);background:rgba(31,122,106,.08);color:#1f6258;box-shadow:none;}}
        [data-theme="light"] button:hover{{border-color:rgba(31,122,106,.42);background:rgba(31,122,106,.13);color:#174f48;}}
        [data-theme="light"] button[type="submit"]:not(.danger):not(.pool-apply-btn):not(.pool-delete-btn){{background:rgba(31,122,106,.08);border-color:rgba(31,122,106,.28);color:#1f6258;}}
        [data-theme="light"] button[type="submit"]:not(.danger):not(.pool-apply-btn):not(.pool-delete-btn):hover{{background:rgba(31,122,106,.13);border-color:rgba(31,122,106,.42);color:#174f48;}}
        [data-theme="light"] .secondary-button,
        [data-theme="light"] .success-button,
        [data-theme="light"] .outline-button,
        [data-theme="light"] .service-preset-btn{{background:rgba(31,122,106,.08);border-color:rgba(31,122,106,.28);color:#1f6258;}}
        [data-theme="light"] .mode-toggle,
        [data-theme="light"] .theme-toggle{{background:rgba(31,122,106,.08);border-color:rgba(31,122,106,.28);color:#1f6258;}}
        [data-theme="light"] button.danger{{background:#f7dedb;border-color:#d79891;color:#8e2f28;}}
        [data-theme="light"] button.danger:hover{{background:#f1cbc6;border-color:#c77d75;}}
        [data-theme="light"] .success-button{{background:rgba(31,122,106,.08);border-color:rgba(31,122,106,.28);color:#1f6258;}}
        [data-theme="light"] input,
        [data-theme="light"] textarea,
        [data-theme="light"] select{{background:#fff;border-color:#c8d5e1;color:var(--text);}}
        [data-theme="light"] input::placeholder,
        [data-theme="light"] textarea::placeholder{{color:#7d8b9b;}}
        [data-theme="light"] input:focus,
        [data-theme="light"] textarea:focus,
        [data-theme="light"] select:focus{{border-color:#1f7a6a;box-shadow:0 0 0 3px rgba(31,122,106,.12);}}
        [data-theme="light"] .segmented,
        [data-theme="light"] .subtabs,
        [data-theme="light"] .pool-table-wrap,
        [data-theme="light"] .protocol-subview-import .pool-add-form,
        [data-theme="light"] .protocol-subview-import .pool-subscribe-form,
        [data-theme="light"] .custom-check-card{{background:rgba(255,255,255,.78);border-color:var(--border);}}
        [data-theme="light"] .seg-tab,
        [data-theme="light"] .subtab,
        [data-theme="light"] .nav-item{{color:#536274;}}
        [data-theme="light"] .seg-tab.active,
        [data-theme="light"] .subtab.active,
        [data-theme="light"] .nav-item.active{{background:rgba(31,122,106,.12);border-color:rgba(31,122,106,.3);color:#1f6258;}}
        [data-theme="light"] .seg-tab:hover,
        [data-theme="light"] .subtab:hover,
        [data-theme="light"] .nav-item:hover{{background:rgba(31,122,106,.06);}}
        [data-theme="light"] .tab-count{{background:#e0e9f2;color:#233144;}}
        [data-theme="light"] .pool-table th{{background:#eef3f8;color:#536274;}}
        [data-theme="light"] .pool-table th,
        [data-theme="light"] .pool-table td{{border-bottom-color:#d6e0ea;}}
        [data-theme="light"] .pool-row-active{{background:rgba(31,122,106,.1);}}
        [data-theme="light"] .pool-active-cell,
        [data-theme="light"] .pool-apply-btn{{color:#172033;}}
        [data-theme="light"] .pool-apply-btn:hover{{color:#1f7a6a;}}
        [data-theme="light"] .pool-delete-btn{{background:#f5deda;color:#92352d;border-color:#e3aaa4;}}
        [data-theme="light"] .pool-delete-btn:hover{{background:#edc8c2;}}
        [data-theme="light"] .key-status-ok,
        [data-theme="light"] .custom-service-ok{{background:rgba(31,122,106,.12);border-color:rgba(31,122,106,.3);color:#1f6258;}}
        [data-theme="light"] .key-status-warn{{background:#fff1d7;border-color:#deb36b;color:#875b1f;}}
        [data-theme="light"] .key-status-fail,
        [data-theme="light"] .custom-service-fail{{background:transparent;border-color:transparent;color:#526173;}}
        [data-theme="light"] .key-status-empty,
        [data-theme="light"] .custom-service-unknown,
        [data-theme="light"] .custom-service-neutral,
        [data-theme="light"] .service-probe-unknown{{background:#edf3f8;border-color:#c8d5e1;color:#536274;}}
        [data-theme="light"] .service-probe-fail{{background:#f7dedb;border-color:#d79891;color:#92352d;}}
        [data-theme="light"] .custom-check-item{{background:rgba(255,255,255,.82);border-color:#d6e0ea;}}
        [data-theme="light"] .custom-check-empty{{border-color:#c8d5e1;background:rgba(255,255,255,.55);}}
        [data-theme="light"] .notice-result{{background:var(--warn-bg);border-color:var(--warn-border);color:#6f4b18;}}
        [data-theme="light"] .notice-status{{background:var(--success-bg);border-color:var(--success-border);color:#174f3b;}}
        [data-theme="light"] .notice strong,
        [data-theme="light"] .log-output{{color:inherit;}}
        [data-theme="light"] .command-progress-block{{background:rgba(255,255,255,.72);border-color:var(--border);}}
        [data-theme="light"] .command-progress-track{{background:#d9e4ee;}}
        [data-theme="light"] .confirm-backdrop{{background:rgba(31,41,55,.36);}}
        [data-theme="light"] .mobile-nav{{background:rgba(255,255,255,.96);border-color:var(--border);box-shadow:0 14px 34px rgba(46,63,86,.18);}}
        </style>
    <script>
        const INITIAL_STATUS_PENDING = {initial_status_pending};
        const INITIAL_COMMAND_RUNNING = {initial_command_running};
        const POOL_PROBE_POLL_EXTENSION_MS = {POOL_PROBE_UI_POLL_EXTENSION_MS};
        const TELEGRAM_ICON_SRC = 'data:image/svg+xml;base64,{TELEGRAM_SVG_B64}';
        const YOUTUBE_ICON_SRC = 'data:image/svg+xml;base64,{YOUTUBE_SVG_B64}';
        const SERVICE_ICON_BASE = '/static/service-icons/';
        let customChecks = {custom_checks_json};
        const PROTOCOL_LABELS = {{
            none: 'Без прокси',
            shadowsocks: 'Shadowsocks',
            vmess: 'Vmess',
            vless: 'Vless 1',
            vless2: 'Vless 2',
            trojan: 'Trojan'
        }};
        let statusPollTimer = null;
        let statusPollUntil = 0;
        let commandPollTimer = null;

        (function() {{
            const savedTheme = localStorage.getItem('router-theme');
            const theme = savedTheme === 'light' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', theme);
        }})();

        function toggleTheme() {{
            const root = document.documentElement;
            const nextTheme = root.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
            root.setAttribute('data-theme', nextTheme);
            localStorage.setItem('router-theme', nextTheme);
            const label = document.getElementById('theme-toggle-label');
            if (label) {{
                label.textContent = nextTheme === 'light' ? 'Светлая тема' : 'Темная тема';
            }}
        }}

        function toggleModePicker() {{
            const picker = document.getElementById('mode-picker');
            if (!picker) {{
                return;
            }}
            picker.classList.toggle('hidden');
        }}

        function escapeHtml(value) {{
            return String(value || '').replace(/[&<>"']/g, function(char) {{
                return {{
                    '&': '&amp;',
                    '<': '&lt;',
                    '>': '&gt;',
                    '"': '&quot;',
                    "'": '&#39;'
                }}[char];
            }});
        }}

        function setupViewNavigation() {{
            const targets = document.querySelectorAll('[data-view-target]');
            function activate(view) {{
                let selected = view || 'status';
                if (selected === 'service' || !document.querySelector('[data-view="' + selected + '"]')) {{
                    selected = 'status';
                }}
                document.querySelectorAll('[data-view]').forEach(function(panel) {{
                    panel.classList.toggle('active', panel.dataset.view === selected);
                }});
                targets.forEach(function(button) {{
                    button.classList.toggle('active', button.dataset.viewTarget === selected);
                }});
            }}
            targets.forEach(function(button) {{
                button.addEventListener('click', function() {{
                    activate(button.dataset.viewTarget);
                }});
            }});
            localStorage.removeItem('router-active-view');
            activate('status');
        }}

        function setupSegmentedTabs(buttonSelector, panelSelector, targetAttribute, panelAttribute, storageKey) {{
            const buttons = document.querySelectorAll(buttonSelector);
            function activate(value) {{
                let selected = value || localStorage.getItem(storageKey) || (buttons[0] ? buttons[0].getAttribute(targetAttribute) : '');
                if (selected && !Array.from(buttons).some(function(button) {{ return button.getAttribute(targetAttribute) === selected; }})) {{
                    selected = buttons[0] ? buttons[0].getAttribute(targetAttribute) : '';
                }}
                buttons.forEach(function(button) {{
                    button.classList.toggle('active', button.getAttribute(targetAttribute) === selected);
                }});
                document.querySelectorAll(panelSelector).forEach(function(panel) {{
                    panel.classList.toggle('active', panel.getAttribute(panelAttribute) === selected);
                }});
                if (selected) {{
                    localStorage.setItem(storageKey, selected);
                }}
            }}
            buttons.forEach(function(button) {{
                button.addEventListener('click', function() {{
                    activate(button.getAttribute(targetAttribute));
                }});
            }});
            activate(localStorage.getItem(storageKey));
        }}

        function setupProtocolSubtabs() {{
            document.querySelectorAll('[data-protocol-panel]').forEach(function(panel) {{
                const buttons = panel.querySelectorAll('[data-subview-target]');
                function activate(value) {{
                    const selected = value || 'key';
                    buttons.forEach(function(button) {{
                        button.classList.toggle('active', button.dataset.subviewTarget === selected);
                    }});
                    panel.querySelectorAll('[data-subview]').forEach(function(subview) {{
                        subview.classList.toggle('active', subview.dataset.subview === selected);
                    }});
                }}
                buttons.forEach(function(button) {{
                    button.addEventListener('click', function() {{
                        activate(button.dataset.subviewTarget);
                    }});
                }});
                activate('key');
            }});
        }}

        function setOptionalText(id, text) {{
            const element = document.getElementById(id);
            if (!element) {{
                return;
            }}
            const value = text || '';
            element.textContent = value;
            element.classList.toggle('hidden', !value);
        }}

        function serviceIcon(src, alt) {{
            return '<img class="service-icon-img" src="' + src + '" width="16" height="16" alt="' + alt + '" style="vertical-align:middle;opacity:1">';
        }}

        function protocolIcons(status) {{
            let html = '';
            if (status && status.api_ok) {{
                html += serviceIcon(TELEGRAM_ICON_SRC, 'Telegram');
            }}
            if (status && status.yt_ok) {{
                html += serviceIcon(YOUTUBE_ICON_SRC, 'YouTube');
            }}
            if (status && status.custom) {{
                customChecks.forEach(function(check) {{
                    if (status.custom[check.id] === 'ok') {{
                        html += serviceIcon(serviceIconSrc(check.icon), check.label || 'Service');
                    }}
                }});
            }}
            return html;
        }}

        function probeBadge(state, service) {{
            if (state === 'ok') {{
                return serviceIcon(service === 'tg' ? TELEGRAM_ICON_SRC : YOUTUBE_ICON_SRC, service === 'tg' ? 'Telegram' : 'YouTube');
            }}
            if (state === 'fail') {{
                return '<span class="service-probe-mark service-probe-fail">✕</span>';
            }}
            return '<span class="service-probe-mark service-probe-unknown">?</span>';
        }}

        function customCheckById(id) {{
            for (let i = 0; i < customChecks.length; i += 1) {{
                if (customChecks[i].id === id) {{
                    return customChecks[i];
                }}
            }}
            return null;
        }}

        function customBadge(state, check) {{
            const status = state || 'unknown';
            const label = check ? check.label : 'Проверка';
            const url = check ? check.url : '';
            let content = '?';
            if (status === 'ok' && check && check.icon) {{
                content = serviceIcon(serviceIconSrc(check.icon), label);
            }} else if (status === 'fail') {{
                content = '<span class="service-probe-mark service-probe-fail">✕</span>';
            }} else {{
                content = '<span class="service-probe-mark service-probe-unknown">?</span>';
            }}
            return '<span class="custom-service-slot custom-service-' + status + '" title="' +
                escapeHtml(label + (url ? ': ' + url : '')) + '">' + content + '</span>';
        }}

        function renderCustomBadges(states) {{
            if (!customChecks.length) {{
                return '';
            }}
            return customChecks.map(function(check) {{
                const state = states && states[check.id] ? states[check.id] : 'unknown';
                return customBadge(state, check);
            }}).join('');
        }}

        function customUrlText(check) {{
            const urls = Array.isArray(check.urls) && check.urls.length ? check.urls : [check.url || ''];
            return urls.filter(Boolean).map(function(url) {{
                try {{
                    const parsed = new URL(url);
                    return (parsed.host || url) + (parsed.pathname && parsed.pathname !== '/' ? parsed.pathname : '');
                }} catch (error) {{
                    return url;
                }}
            }}).join(', ');
        }}

        function serviceIconSrc(icon) {{
            const safe = String(icon || '').replace(/[^a-z0-9_-]/gi, '').toLowerCase();
            return safe ? SERVICE_ICON_BASE + safe + '.png' : '';
        }}

        function customIconHtml(check) {{
            if (check && check.icon) {{
                return '<span class="preset-icon"><img src="' + serviceIconSrc(check.icon) + '" width="20" height="20" alt="' + escapeHtml(check.label || 'Service') + '"></span>';
            }}
            return '<span class="custom-service-badge custom-service-neutral">' + escapeHtml((check && check.badge) || 'WEB') + '</span>';
        }}

        function customHeaderIcons() {{
            if (!customChecks.length) {{
                return '';
            }}
            return customChecks.map(function(check) {{
                const label = check.label || 'Service';
                const content = check.icon
                    ? serviceIcon(serviceIconSrc(check.icon), label)
                    : '<span class="custom-service-badge custom-service-neutral">' + escapeHtml(check.badge || 'WEB') + '</span>';
                return '<span class="custom-service-slot custom-service-header" title="' + escapeHtml(label) + '">' + content + '</span>';
            }}).join('');
        }}

        function syncCustomCheckColumns() {{
            const hasChecks = customChecks.length > 0;
            const mobileWidth = Math.max(28, 28 * customChecks.length) + 'px';
            const desktopWidth = (32 * Math.max(1, customChecks.length)) + 'px';
            document.querySelectorAll('.pool-table').forEach(function(table) {{
                table.classList.toggle('has-custom-checks', hasChecks);
                table.style.setProperty('--custom-col-mobile', mobileWidth);
                const customCol = table.querySelector('.pool-col-custom');
                if (customCol) {{
                    customCol.style.width = desktopWidth;
                }}
            }});
        }}

        function renderCustomChecks(checks) {{
            customChecks = Array.isArray(checks) ? checks : [];
            const html = customChecks.length ? customChecks.map(function(check) {{
                return '<div class="custom-check-item">' +
                    customIconHtml(check) +
                    '<span class="custom-check-copy"><strong>' + escapeHtml(check.label || 'Проверка') + '</strong><small>' + escapeHtml(customUrlText(check)) + '</small></span>' +
                    '<form method="post" action="/custom_check_delete" data-async-action="custom-check-delete" data-confirm-title="Удалить проверку?" data-confirm-message="Удалить дополнительную проверку ' + escapeHtml(check.label || 'Проверка') + '?">' +
                        '<input type="hidden" name="id" value="' + escapeHtml(check.id || '') + '">' +
                        '<button type="submit" class="pool-delete-btn" title="Удалить проверку">Удалить</button>' +
                    '</form>' +
                '</div>';
            }}).join('') : '<div class="custom-check-empty">Дополнительные проверки пока не добавлены.</div>';
            document.querySelectorAll('[data-custom-check-list]').forEach(function(list) {{
                list.innerHTML = html;
                setupAsyncForms(list);
            }});
            const activeIds = customChecks.map(function(check) {{ return check.id; }});
            document.querySelectorAll('[data-custom-preset]').forEach(function(button) {{
                const active = activeIds.indexOf(button.dataset.customPreset) !== -1;
                button.disabled = active;
                button.title = active ? 'Уже добавлено' : 'Добавить проверку';
            }});
            document.querySelectorAll('[data-custom-check-head]').forEach(function(head) {{
                head.innerHTML = customHeaderIcons();
            }});
            syncCustomCheckColumns();
        }}

        function renderPoolBody(proto, pool) {{
            const body = document.querySelector('[data-pool-body="' + proto + '"]');
            if (!body || !pool) {{
                return;
            }}
            const rows = pool.rows || [];
            const tab = document.querySelector('[data-protocol-target="' + proto + '"] .tab-count');
            if (tab) {{
                tab.textContent = String(pool.count || rows.length);
            }}
            if (!rows.length) {{
                body.innerHTML = '<tr class="pool-row pool-empty-row"><td colspan="6">Пул пуст. Добавьте ключи или загрузите subscription.</td></tr>';
                return;
            }}
            body.innerHTML = rows.map(function(row) {{
                const activeClass = row.active ? ' pool-row-active' : '';
                const activeText = row.active ? 'активен' : '';
                const key = escapeHtml(row.key || '');
                return '<tr class="pool-row' + activeClass + '" data-pool-row data-protocol="' + proto + '" data-key-id="' + escapeHtml(row.key_id) + '" data-key="' + key + '">' +
                    '<td class="pool-key-cell">' +
                        '<form method="post" action="/pool_apply" class="pool-apply-form" data-async-action="pool-apply">' +
                            '<input type="hidden" name="type" value="' + proto + '">' +
                            '<input type="hidden" name="key" value="' + key + '">' +
                            '<button type="submit" class="pool-apply-btn" title="Применить этот ключ">' + escapeHtml(row.display_name) + '</button>' +
                        '</form>' +
                        '<span class="pool-mobile-active" data-pool-key-meta data-pool-mobile-active>' + activeText + '</span>' +
                        '<span class="pool-hash">' + escapeHtml(row.key_id) + '</span>' +
                    '</td>' +
                    '<td class="pool-service-cell" data-pool-tg>' + probeBadge(row.tg, 'tg') + '</td>' +
                    '<td class="pool-service-cell" data-pool-yt>' + probeBadge(row.yt, 'yt') + '</td>' +
                    '<td class="pool-custom-cell" data-pool-custom>' + renderCustomBadges(row.custom) + '</td>' +
                    '<td class="pool-checked-cell" data-pool-checked>' + escapeHtml(row.checked_at) + '</td>' +
                    '<td class="pool-actions-cell">' +
                        '<form method="post" action="/pool_delete" class="pool-item-form" data-async-action="pool-delete" data-confirm-title="Удалить ключ?" data-confirm-message="Удалить ключ из пула?">' +
                            '<input type="hidden" name="type" value="' + proto + '">' +
                            '<input type="hidden" name="key" value="' + key + '">' +
                            '<button type="submit" class="pool-delete-btn" title="Удалить ключ из пула">Удалить</button>' +
                        '</form>' +
                    '</td>' +
                '</tr>';
            }}).join('');
            setupAsyncForms(body);
        }}

        function updatePoolRows(proto, pool) {{
            const body = document.querySelector('[data-pool-body="' + proto + '"]');
            if (!body || !pool) {{
                return;
            }}
            const rows = pool.rows || [];
            const tab = document.querySelector('[data-protocol-target="' + proto + '"] .tab-count');
            if (tab) {{
                tab.textContent = String(pool.count || rows.length);
            }}
            body.querySelectorAll('[data-pool-row]').forEach(function(item) {{
                item.classList.remove('pool-row-active');
                const meta = item.querySelector('[data-pool-key-meta]');
                if (meta) {{
                    meta.textContent = '';
                }}
            }});
            rows.forEach(function(row) {{
                const item = body.querySelector('[data-key-id="' + row.key_id + '"]');
                if (!item) {{
                    return;
                }}
                item.classList.toggle('pool-row-active', !!row.active);
                const meta = item.querySelector('[data-pool-key-meta]');
                if (meta) {{
                    meta.textContent = row.active ? 'активен' : '';
                }}
                const tg = item.querySelector('[data-pool-tg]');
                if (tg) {{
                    tg.innerHTML = probeBadge(row.tg, 'tg');
                }}
                const yt = item.querySelector('[data-pool-yt]');
                if (yt) {{
                    yt.innerHTML = probeBadge(row.yt, 'yt');
                }}
                const custom = item.querySelector('[data-pool-custom]');
                if (custom) {{
                    custom.innerHTML = renderCustomBadges(row.custom);
                }}
                const checked = item.querySelector('[data-pool-checked]');
                if (checked) {{
                    checked.textContent = row.checked_at || '';
                }}
            }});
        }}

        function updatePoolStatus(pools) {{
            if (!pools) {{
                return;
            }}
            Object.keys(pools).forEach(function(proto) {{
                const rows = (pools[proto] && pools[proto].rows) || [];
                const hasFullKeys = rows.some(function(row) {{ return !!row.key; }});
                if (hasFullKeys || rows.length === 0) {{
                    renderPoolBody(proto, pools[proto]);
                }} else {{
                    updatePoolRows(proto, pools[proto]);
                }}
            }});
        }}

        function updateProtocolStatus(proto, status) {{
            const card = document.querySelector('[data-protocol-card="' + proto + '"]');
            if (!card || !status) {{
                return;
            }}
            const badge = card.querySelector('[data-protocol-status-label]');
            if (badge) {{
                badge.className = 'key-status-badge key-status-' + (status.tone || 'warn');
                badge.innerHTML = status.label || 'Проверяется';
            }}
            const details = card.querySelector('[data-protocol-status-details]');
            if (details) {{
                details.textContent = status.details || '';
            }}
            const icons = card.querySelector('[data-protocol-status-icons]');
            if (icons) {{
                icons.innerHTML = protocolIcons(status);
            }}
        }}

        function updateWebStatus(snapshot) {{
            if (!snapshot || !snapshot.web) {{
                return false;
            }}
            const web = snapshot.web;
            const modeLabel = document.getElementById('current-mode-label');
            if (modeLabel) {{
                modeLabel.textContent = PROTOCOL_LABELS[web.proxy_mode] || web.proxy_mode || 'Без прокси';
            }}
            const modeToggle = document.querySelector('#mode-toggle-button span:last-child');
            if (modeToggle) {{
                modeToggle.textContent = PROTOCOL_LABELS[web.proxy_mode] || web.proxy_mode || 'Без прокси';
            }}
            const apiStatus = document.getElementById('web-api-status');
            if (apiStatus) {{
                apiStatus.textContent = web.api_status || '';
            }}
            const apiPill = document.getElementById('web-api-pill');
            if (apiPill) {{
                const progress = snapshot.pool_probe_progress || {{}};
                const poolProbeVisible = !!snapshot.pool_probe_running && Number(progress.total || 0) > 0;
                const progressText = progress.total
                    ? '⏳ Фоновая проверка пула ключей выполняется: ' + (progress.checked || 0) + '/' + progress.total + '. Статусы обновятся без перезагрузки страницы.'
                    : '⏳ Фоновая проверка пула ключей выполняется. Статусы обновятся без перезагрузки страницы.';
                apiPill.textContent = poolProbeVisible ? progressText : (web.api_status || '');
            }}
            setOptionalText('web-socks-details', web.socks_details || '');
            const fallbackText = web.fallback_reason && web.proxy_mode === 'none'
                ? 'Последняя неудачная попытка прокси: ' + web.fallback_reason
                : '';
            setOptionalText('web-fallback-reason', fallbackText);

            let pending = (web.api_status || '').indexOf('Проверяется связь текущего режима') !== -1 ||
                (web.api_status || '').indexOf('Фоновая проверка') !== -1 ||
                (web.api_status || '').indexOf('перепроверяется') !== -1;
            const protocols = snapshot.protocols || {{}};
            Object.keys(protocols).forEach(function(proto) {{
                const status = protocols[proto];
                updateProtocolStatus(proto, status);
                if (status && status.label === 'Проверяется') {{
                    pending = true;
                }}
            }});
            if (snapshot.custom_checks) {{
                renderCustomChecks(snapshot.custom_checks);
            }}
            const poolSummary = snapshot.pool_summary || null;
            if (poolSummary) {{
                const progress = snapshot.pool_probe_progress || {{}};
                let summaryNote = poolSummary.note || '';
                if (!!snapshot.pool_probe_running && Number(progress.total || 0) > 0) {{
                    summaryNote = 'Фоновая проверка: ' + (progress.checked || 0) + '/' + progress.total + '. ' + summaryNote;
                }}
                setOptionalText('pool-active-summary', poolSummary.active_text || '');
                setOptionalText('pool-summary-note', summaryNote);
            }}
            updatePoolStatus(snapshot.pools);
            if (!!snapshot.pool_probe_running && Number((snapshot.pool_probe_progress || {{}}).total || 0) > 0) {{
                pending = true;
                statusPollUntil = Math.max(statusPollUntil, Date.now() + POOL_PROBE_POLL_EXTENSION_MS);
            }}
            return pending;
        }}

        function pollStatus() {{
            statusPollTimer = null;
            fetch('/api/status', {{
                headers: {{'Accept': 'application/json'}},
                cache: 'no-store'
            }})
                .then(function(response) {{ return response.json(); }})
                .then(function(payload) {{
                    const pending = updateWebStatus(payload);
                    if (pending) {{
                        statusPollUntil = Math.max(statusPollUntil, Date.now() + 30000);
                    }}
                }})
                .catch(function() {{}})
                .finally(function() {{
                    if (Date.now() < statusPollUntil && !document.hidden) {{
                        statusPollTimer = window.setTimeout(pollStatus, 4000);
                    }}
                }});
        }}

        function scheduleStatusPolling(durationMs) {{
            statusPollUntil = Math.max(statusPollUntil, Date.now() + durationMs);
            if (!statusPollTimer && !document.hidden) {{
                pollStatus();
            }}
        }}

        function showActionMessage(text, ok) {{
            const block = document.getElementById('web-action-message');
            if (!block) {{
                return;
            }}
            block.classList.remove('hidden');
            block.classList.toggle('notice-status', !!ok);
            block.classList.toggle('notice-result', !ok);
            const title = block.querySelector('strong');
            if (title) {{
                title.textContent = ok ? 'Результат' : 'Ошибка';
            }}
            const output = block.querySelector('.log-output');
            if (output) {{
                output.textContent = text || '';
            }}
        }}

        function showCommandState(state) {{
            const block = document.getElementById('web-command-status');
            if (!block) {{
                return false;
            }}
            if (!state || !state.label) {{
                block.classList.add('hidden');
                return false;
            }}
            block.classList.remove('hidden');
            const title = block.querySelector('strong');
            if (title) {{
                title.textContent = (state.running ? 'Команда выполняется: ' : 'Последняя команда: ') + state.label;
            }}
            const output = block.querySelector('.log-output');
            if (output) {{
                output.textContent = state.result || ('⏳ ' + state.label + ' ещё выполняется. Статус обновится без перезагрузки страницы.');
            }}
            return !!state.running;
        }}

        function pollCommandState() {{
            commandPollTimer = null;
            fetch('/api/command_state', {{
                headers: {{'Accept': 'application/json'}},
                cache: 'no-store'
            }})
                .then(function(response) {{ return response.json(); }})
                .then(function(payload) {{
                    if (showCommandState(payload)) {{
                        commandPollTimer = window.setTimeout(pollCommandState, 4000);
                    }} else {{
                        scheduleStatusPolling(30000);
                    }}
                }})
                .catch(function() {{
                    commandPollTimer = window.setTimeout(pollCommandState, 6000);
                }});
        }}

        function markProtocolPending(proto, text) {{
            const card = document.querySelector('[data-protocol-card="' + proto + '"]');
            if (!card) {{
                return;
            }}
            const badge = card.querySelector('[data-protocol-status-label]');
            if (badge) {{
                badge.className = 'key-status-badge key-status-warn';
                badge.textContent = 'Проверяется';
            }}
            const details = card.querySelector('[data-protocol-status-details]');
            if (details) {{
                details.textContent = text || 'Проверка Telegram API, YouTube и дополнительных сервисов выполняется в фоне.';
            }}
            const icons = card.querySelector('[data-protocol-status-icons]');
            if (icons) {{
                icons.innerHTML = '';
            }}
        }}

        function markPoolKeyActive(proto, key) {{
            document.querySelectorAll('[data-pool-row]').forEach(function(item) {{
                if (item.dataset.protocol !== proto) {{
                    return;
                }}
                const isActive = item.dataset.key === key;
                item.classList.toggle('pool-row-active', isActive);
                const meta = item.querySelector('[data-pool-key-meta]');
                if (meta) {{
                    meta.textContent = isActive ? 'активен' : '';
                }}
                const mobileMeta = item.querySelector('[data-pool-mobile-active]');
                if (mobileMeta) {{
                    mobileMeta.textContent = meta ? meta.textContent : '';
                }}
            }});
        }}

        function setButtonBusy(button, busy) {{
            if (!button) {{
                return;
            }}
            if (busy) {{
                button.dataset.originalText = button.textContent;
                button.disabled = true;
                button.textContent = 'Выполняется...';
            }} else {{
                button.disabled = false;
                if (button.dataset.originalText) {{
                    button.textContent = button.dataset.originalText;
                    delete button.dataset.originalText;
                }}
            }}
        }}

        function confirmAction(title, message) {{
            if (!title && !message) {{
                return Promise.resolve(true);
            }}
            const modal = document.getElementById('confirm-modal');
            const titleNode = document.getElementById('confirm-title');
            const messageNode = document.getElementById('confirm-message');
            const cancelButton = document.getElementById('confirm-cancel');
            const acceptButton = document.getElementById('confirm-accept');
            if (!modal || !cancelButton || !acceptButton) {{
                return Promise.resolve(window.confirm(message || title || 'Подтвердить действие?'));
            }}
            titleNode.textContent = title || 'Подтверждение';
            messageNode.textContent = message || 'Подтвердите действие.';
            modal.classList.remove('hidden');
            return new Promise(function(resolve) {{
                function cleanup(result) {{
                    modal.classList.add('hidden');
                    cancelButton.removeEventListener('click', onCancel);
                    acceptButton.removeEventListener('click', onAccept);
                    modal.removeEventListener('click', onBackdrop);
                    resolve(result);
                }}
                function onCancel() {{ cleanup(false); }}
                function onAccept() {{ cleanup(true); }}
                function onBackdrop(event) {{
                    if (event.target === modal) {{
                        cleanup(false);
                    }}
                }}
                cancelButton.addEventListener('click', onCancel);
                acceptButton.addEventListener('click', onAccept);
                modal.addEventListener('click', onBackdrop);
            }});
        }}

        function setupAsyncForms(root) {{
            const scope = root || document;
            scope.querySelectorAll('form[data-async-action]').forEach(function(form) {{
                if (form.dataset.asyncBound === '1') {{
                    return;
                }}
                form.dataset.asyncBound = '1';
                form.addEventListener('submit', function(event) {{
                    event.preventDefault();
                    const button = event.submitter || form.querySelector('button[type="submit"]');
                    const formData = new FormData(form);
                    if (button && button.name) {{
                        formData.append(button.name, button.value || '');
                    }}
                    const action = form.dataset.asyncAction || '';
                    const proto = formData.get('type') || '';
                    const key = formData.get('key') || '';
                    const confirmTitle = (button && button.dataset.confirmTitle) || form.dataset.confirmTitle || '';
                    const confirmMessage = (button && button.dataset.confirmMessage) || form.dataset.confirmMessage || '';
                    const actionUrl = (button && button.getAttribute('formaction')) || form.getAttribute('action');
                    confirmAction(confirmTitle, confirmMessage).then(function(confirmed) {{
                        if (!confirmed) {{
                            return;
                        }}
                        setButtonBusy(button, true);
                        if (proto && (action === 'install' || action === 'pool-apply' || action === 'pool-probe')) {{
                            markProtocolPending(proto);
                        }}
                        showActionMessage('⏳ Выполняется действие. Страница останется на месте.', true);
                        const requestBody = new URLSearchParams();
                        formData.forEach(function(value, name) {{
                            requestBody.append(name, value);
                        }});
                        fetch(actionUrl, {{
                        method: 'POST',
                        body: requestBody,
                        headers: {{
                            'Accept': 'application/json',
                            'X-Requested-With': 'fetch',
                            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'
                        }},
                        cache: 'no-store'
                    }})
                        .then(function(response) {{
                            return response.json().then(function(payload) {{
                                payload._responseOk = response.ok;
                                return payload;
                            }});
                        }})
                        .then(function(payload) {{
                            const ok = payload._responseOk && payload.ok !== false;
                            showActionMessage(payload.result || 'Готово.', ok);
                            if (ok && proto && action === 'install') {{
                                const card = form.closest('[data-protocol-card]');
                                const textarea = card ? card.querySelector('[data-key-textarea]') : null;
                                if (textarea) {{
                                    textarea.value = key;
                                }}
                            }}
                            if (ok && proto && action === 'pool-apply') {{
                                markPoolKeyActive(proto, key);
                                const card = form.closest('[data-protocol-card]');
                                const textarea = card ? card.querySelector('[data-key-textarea]') : null;
                                if (textarea) {{
                                    textarea.value = key;
                                }}
                            }}
                            if (payload.custom_checks) {{
                                renderCustomChecks(payload.custom_checks);
                            }}
                            if (payload.pools) {{
                                updatePoolStatus(payload.pools);
                            }}
                            if (payload.list_name && typeof payload.list_content === 'string') {{
                                const listPanel = document.querySelector('[data-list-panel="' + payload.list_name + '"]');
                                const listTextarea = listPanel ? listPanel.querySelector('textarea[name="content"]') : null;
                                if (listTextarea) {{
                                    listTextarea.value = payload.list_content;
                                }}
                            }}
                            if (action === 'set-proxy') {{
                                const picker = document.getElementById('mode-picker');
                                if (picker) {{
                                    picker.classList.add('hidden');
                                }}
                                const selectedMode = String(formData.get('proxy_type') || '');
                                const selectedLabel = payload.proxy_label || PROTOCOL_LABELS[selectedMode] || selectedMode || 'Без прокси';
                                document.querySelectorAll('.mode-choice').forEach(function(choice) {{
                                    choice.classList.toggle('active', choice.dataset.modeValue === selectedMode);
                                }});
                                const modeToggle = document.querySelector('#mode-toggle-button span:last-child');
                                if (modeToggle) {{
                                    modeToggle.textContent = selectedLabel;
                                }}
                                const currentMode = document.getElementById('current-mode-label');
                                if (currentMode) {{
                                    currentMode.textContent = selectedLabel;
                                }}
                            }}
                            if (action === 'command') {{
                                showCommandState(payload.command_state);
                                if (!commandPollTimer) {{
                                    pollCommandState();
                                }}
                                scheduleStatusPolling(120000);
                            }} else {{
                                scheduleStatusPolling(70000);
                            }}
                        }})
                        .catch(function(error) {{
                            showActionMessage('Ошибка запроса: ' + error, false);
                        }})
                        .finally(function() {{
                            setButtonBusy(button, false);
                        }});
                    }});
                }});
            }});
        }}

        document.addEventListener('DOMContentLoaded', function() {{
            const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
            const label = document.getElementById('theme-toggle-label');
            if (label) {{
                label.textContent = currentTheme === 'light' ? 'Светлая тема' : 'Темная тема';
            }}
            document.addEventListener('click', function(event) {{
                const picker = document.getElementById('mode-picker');
                const toggle = document.getElementById('mode-toggle-button');
                if (!picker || !toggle) {{
                    return;
                }}
                if (picker.classList.contains('hidden')) {{
                    return;
                }}
                if (!picker.contains(event.target) && !toggle.contains(event.target)) {{
                    picker.classList.add('hidden');
                }}
            }});
            document.addEventListener('visibilitychange', function() {{
                if (!document.hidden) {{
                    scheduleStatusPolling(30000);
                }}
            }});
            setupViewNavigation();
            setupSegmentedTabs('.protocol-tab', '[data-protocol-panel]', 'data-protocol-target', 'data-protocol-panel', 'router-active-protocol');
            setupSegmentedTabs('.list-tab', '[data-list-panel]', 'data-list-target', 'data-list-panel', 'router-active-list');
            setupProtocolSubtabs();
            setupAsyncForms();
            if (INITIAL_STATUS_PENDING) {{
                scheduleStatusPolling(POOL_PROBE_POLL_EXTENSION_MS);
            }}
            if (INITIAL_COMMAND_RUNNING) {{
                pollCommandState();
            }}
        }});
    </script>
</head>
<body>
    <div class="app-shell">
        <header class="topbar">
            <div class="topbar-actions">
                <div class="app-caption">
                    <strong>Локальная панель управления обходом на роутере</strong>
                    <span class="app-branch">Ветка: {html.escape(APP_BRANCH_LABEL)} · {html.escape(APP_BRANCH_DESCRIPTION)}</span>
                </div>
                <span class="api-pill" id="web-api-pill">{html.escape(topbar_status_text)}</span>
                <button type="button" id="mode-toggle-button" class="mode-toggle" onclick="toggleModePicker()">
                    <span>Режим бота:</span>
                    <span>{html.escape(current_mode_label)}</span>
                </button>
                <button type="button" class="theme-toggle" onclick="toggleTheme()" title="Переключить тему">
                    <span id="theme-toggle-label">Темная тема</span>
                </button>
                <span class="version-badge" title="Номер версии по количеству коммитов в ветке">{html.escape(APP_VERSION_LABEL)}</span>
                {mode_picker_block}
            </div>
        </header>
        {message_block}
        {command_block}
        <div class="workspace-layout">
            <nav class="side-nav" aria-label="Разделы">
                <button type="button" class="nav-item active" data-view-target="status">
                    <svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 11.5 12 5l8 6.5"></path><path d="M6.5 10.5V20h11V10.5"></path></svg>
                    <span>Статус</span>
                </button>
                <button type="button" class="nav-item" data-view-target="keys">
                    <svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="8" cy="15" r="4"></circle><path d="M11 12 21 2"></path><path d="m16 7 2 2"></path><path d="m14 9 2 2"></path></svg>
                    <span>Ключи</span>
                </button>
                <button type="button" class="nav-item" data-view-target="lists">
                    <svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M8 6h13"></path><path d="M8 12h13"></path><path d="M8 18h13"></path><path d="M3 6h.01"></path><path d="M3 12h.01"></path><path d="M3 18h.01"></path></svg>
                    <span>Списки</span>
                </button>
            </nav>
            <main class="app-main">
                <section class="app-view active" data-view="status">
                    <div class="view-head">
                        <span class="eyebrow">Обзор</span>
                        <h2>Статус и сервис</h2>
                        <p class="section-subtitle">Связь, активный режим и сервисные действия собраны в одном месте.</p>
                    </div>
                    <div class="status-dashboard">
                        <div class="status-card status-card-wide">
                            <div class="status-card-top">
                                <span class="card-icon">{_telegram_icon_html(opacity=1.0)}</span>
                                <div class="status-copy">
                                    <span class="status-label">Telegram API</span>
                                    <span class="status-value" id="web-api-status">{html.escape(status['api_status'])}</span>
                                    {socks_block}
                                    {fallback_block}
                                </div>
                                <span class="status-dot"></span>
                            </div>
                        </div>
                        <div class="status-card">
                            <div class="status-card-top">
                                <span class="card-icon">◇</span>
                                <div class="status-copy">
                                    <span class="status-label">Активный режим</span>
                                    <span class="status-value" id="current-mode-label">{html.escape(current_mode_label)}</span>
                                    <p class="status-note">Списки обхода: <span id="list-route-label">{html.escape(list_route_label)}</span></p>
                                </div>
                            </div>
                        </div>
                        <div class="status-card">
                            <div class="status-card-top">
                                    <span class="card-icon">⚿</span>
                                    <div class="status-copy">
                                        <span class="status-label">Ключи и пул</span>
                                    <span class="status-value" id="pool-active-summary">{html.escape(pool_summary['active_text'])}</span>
                                    <p class="status-note" id="pool-summary-note">{html.escape(pool_summary_note)}</p>
                                    </div>
                                </div>
                            <div class="status-card-actions">
                                <button type="button" class="outline-button" data-view-target="keys">Открыть ключи</button>
                                <form method="post" action="/pool_probe" data-async-action="pool-probe">
                                    <button type="submit" class="outline-button">Проверить все ключи</button>
                                </form>
                            </div>
                        </div>
                        <div class="status-card">
                            <div class="status-card-top">
                                <span class="card-icon">↗</span>
                                <div class="status-copy">
                                    <span class="status-label">Быстрый старт</span>
                                    <p class="status-note">После установки ключей можно сразу запустить или перезапустить Telegram-бота.</p>
                                </div>
                            </div>
                            <form method="post" action="/start" data-async-action="start">
                                <button type="submit">{start_button_label}</button>
                            </form>
                        </div>
                    </div>
                    <div class="overview-service-grid">
                        <section class="panel service-panel">
                            <h3>Переустановка компонентов</h3>
                            <div class="command-grid">{update_buttons_html}</div>
                        </section>
                        <section class="panel service-panel">
                            <h3>Сервисные команды</h3>
                            <div class="command-grid">{command_buttons_html}</div>
                        </section>
                    </div>
                    <section class="panel overview-key-panel">
                        <div class="workspace-head">
                            <div>
                                <span class="eyebrow">Ключ текущего режима</span>
                                <h2>{html.escape(quick_key_label)}</h2>
                                <p class="section-subtitle">Быстрое редактирование активного ключа. Полное управление пулом находится во вкладке “Ключи”.</p>
                            </div>
                        </div>
                        <form method="post" action="/install" data-async-action="install" class="key-editor-form">
                            <input type="hidden" name="type" value="{quick_key_proto}">
                            <label class="field-label">Ключ {html.escape(quick_key_label)}</label>
                            <textarea name="key" rows="4" placeholder="Вставьте ключ {html.escape(quick_key_label)}">{quick_key_value}</textarea>
                            <div class="form-actions">
                                <button type="submit">Сохранить ключ</button>
                                <button type="button" class="outline-button" data-view-target="keys">Открыть пул ключей</button>
                            </div>
                        </form>
                    </section>
                </section>

                <section class="app-view" data-view="keys">
                    <div class="view-head">
                        <span class="eyebrow">Ключи и мосты</span>
                        <h2>Подключения по протоколам</h2>
                        <p class="section-subtitle">Выберите протокол, сохраните активный ключ или управляйте его пулом.</p>
                    </div>
                    <div class="segmented protocol-tabs">{protocol_tabs_html}</div>
                    <div class="protocol-panels">{protocol_panels_html}</div>
                </section>

                <section class="app-view" data-view="lists">
                    <div class="view-head">
                        <span class="eyebrow">Маршрутизация</span>
                        <h2>Списки обхода</h2>
                        <p class="section-subtitle">Домены из выбранного списка будут отправляться через соответствующий протокол.</p>
                    </div>
                    <div class="segmented list-tabs">{unblock_tabs_html}</div>
                    <div class="list-panels">{unblock_panels_html}</div>
                </section>
            </main>
        </div>
        <nav class="mobile-nav" aria-label="Разделы">
            <button type="button" class="nav-item active" data-view-target="status">
                <svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 11.5 12 5l8 6.5"></path><path d="M6.5 10.5V20h11V10.5"></path></svg>
                <span>Статус</span>
            </button>
            <button type="button" class="nav-item" data-view-target="keys">
                <svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="8" cy="15" r="4"></circle><path d="M11 12 21 2"></path><path d="m16 7 2 2"></path><path d="m14 9 2 2"></path></svg>
                <span>Ключи</span>
            </button>
            <button type="button" class="nav-item" data-view-target="lists">
                <svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M8 6h13"></path><path d="M8 12h13"></path><path d="M8 18h13"></path><path d="M3 6h.01"></path><path d="M3 12h.01"></path><path d="M3 18h.01"></path></svg>
                <span>Списки</span>
            </button>
        </nav>
        <div id="confirm-modal" class="confirm-backdrop hidden" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
            <div class="confirm-card">
                <h2 id="confirm-title">Подтверждение</h2>
                <p id="confirm-message">Подтвердите действие.</p>
                <div class="confirm-actions">
                    <button type="button" id="confirm-cancel" class="secondary-button">Отмена</button>
                    <button type="button" id="confirm-accept" class="danger">Подтвердить</button>
                </div>
            </div>
        </div>
    </div>
</body>
</html>'''

    def do_GET(self):
        if not self._ensure_request_allowed():
            return
        path = urlparse(self.path).path
        if path in ['/', '/index.html', '/command']:
            self._send_html(self._build_form(_consume_web_flash_message()))
        elif path == '/api/status':
            try:
                current_keys = _load_current_keys()
                snapshot = _cached_status_snapshot(current_keys)
                if snapshot is None:
                    snapshot = _active_mode_status_snapshot(current_keys)
                    if not pool_probe_lock.locked():
                        _refresh_status_caches_async(current_keys)
                progress = _get_pool_probe_progress()
                pool_probe_running = (
                    bool(progress.get('running')) and
                    int(progress.get('total') or 0) > 0
                )
                payload = {
                    'web': snapshot.get('web', {}) if isinstance(snapshot, dict) else {},
                    'protocols': snapshot.get('protocols', {}) if isinstance(snapshot, dict) else {},
                    'pools': _web_pool_snapshot(current_keys),
                    'pool_summary': _pool_status_summary(current_keys),
                    'custom_checks': _web_custom_checks(),
                    'pool_probe_running': pool_probe_running,
                    'pool_probe_progress': progress,
                    'timestamp': time.time(),
                }
                self._send_json(payload, status=200)
            except Exception as exc:
                self._send_json({'error': str(exc)}, status=500)
        elif path == '/api/command_state':
            try:
                self._send_json(_get_web_command_state(), status=200)
            except Exception as exc:
                self._send_json({'error': str(exc)}, status=500)
        elif path == '/api/pool_probe':
            # Запустить безопасную фоновую проверку пула без массовых рестартов xray.
            try:
                started, queued = _probe_all_pool_keys_async(stale_only=False)
                status = 'started' if started else ('busy' if queued else 'empty')
                self._send_json({'status': status, 'queued': queued}, status=200)
            except Exception as exc:
                self._send_json({'error': str(exc)}, status=500)
        elif path == '/static/telegram.png':
            self._send_png(os.path.join(STATIC_DIR, 'telegram.png'))
        elif path == '/static/youtube.png':
            self._send_png(os.path.join(STATIC_DIR, 'youtube.png'))
        elif path.startswith('/static/service-icons/'):
            icon_name = os.path.basename(path)
            self._send_png(os.path.join(STATIC_DIR, 'service-icons', icon_name))
        else:
            self._send_html('<h1>404 Not Found</h1>', status=404)

    def do_POST(self):
        if not self._ensure_request_allowed():
            return
        path = urlparse(self.path).path
        if path == '/set_proxy':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            data = parse_qs(body)
            proxy_type = data.get('proxy_type', ['none'])[0]
            ok, error = update_proxy(proxy_type)
            if ok:
                result = f'Режим бота установлен: {proxy_type}'
            else:
                result = f'⚠️ {error}'
            _invalidate_web_status_cache()
            _invalidate_key_status_cache()
            self._send_action_result(
                result,
                success=ok,
                extra={'proxy_mode': proxy_type, 'proxy_label': _proxy_mode_label(proxy_type)},
            )
            return

        if path == '/start':
            global bot_ready
            bot_ready = True
            _save_bot_autostart(True)
            _invalidate_web_status_cache()
            result = 'Команда запуска принята. Если Telegram API доступен, бот начнет отвечать через несколько секунд.'
            self._send_action_result(result, success=True)
            return

        if path == '/command':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            data = parse_qs(body)
            command = data.get('command', [''])[0]
            started, result = _start_web_command(command)
            self._send_action_result(
                result,
                success=started,
                extra={'command_state': _get_web_command_state()},
            )
            return

        if path == '/save_unblock_list':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            data = parse_qs(body)
            list_name = data.get('list_name', [''])[0]
            content = data.get('content', [''])[0]
            success = True
            try:
                result = _save_unblock_list(list_name, content)
            except Exception as exc:
                success = False
                result = f'Ошибка сохранения списка: {exc}'
            list_content = _read_text_file(os.path.join('/opt/etc/unblock', os.path.basename(list_name))).strip() if success else ''
            self._send_action_result(
                result,
                success=success,
                extra={'list_name': os.path.basename(list_name), 'list_content': list_content},
            )
            return

        if path == '/append_socialnet':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            data = parse_qs(body)
            list_name = data.get('target_list_name', data.get('list_name', ['']))[0]
            service_key = data.get('service_key', [SOCIALNET_ALL_KEY])[0]
            success = True
            try:
                result = _append_socialnet_list(list_name, service_key=service_key)
            except Exception as exc:
                success = False
                result = f'Ошибка добавления соцсетей: {exc}'
            safe_name = _normalize_unblock_route_name(list_name) + '.txt' if success else os.path.basename(list_name)
            list_content = _read_text_file(os.path.join('/opt/etc/unblock', safe_name)).strip() if success else ''
            self._send_action_result(
                result,
                success=success,
                extra={'list_name': safe_name, 'list_content': list_content},
            )
            return

        if path == '/remove_socialnet':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            data = parse_qs(body)
            list_name = data.get('target_list_name', data.get('list_name', ['']))[0]
            service_key = data.get('service_key', [SOCIALNET_ALL_KEY])[0]
            success = True
            try:
                result = _remove_socialnet_list(list_name, service_key=service_key)
            except Exception as exc:
                success = False
                result = f'Ошибка удаления соцсетей: {exc}'
            safe_name = _normalize_unblock_route_name(list_name) + '.txt' if success else os.path.basename(list_name)
            list_content = _read_text_file(os.path.join('/opt/etc/unblock', safe_name)).strip() if success else ''
            self._send_action_result(
                result,
                success=success,
                extra={'list_name': safe_name, 'list_content': list_content},
            )
            return

        if path == '/custom_check_add':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            data = parse_qs(body)
            preset_id = data.get('preset', [''])[0]
            label = data.get('label', [''])[0]
            url = data.get('url', [''])[0]
            success = True
            try:
                checks, result = _add_custom_check(label=label, url=url, preset_id=preset_id)
                _probe_all_pool_keys_async(stale_only=False)
                _refresh_status_caches_async(_load_current_keys())
                if success and 'уже есть' not in result:
                    result += ' Фоновая проверка пула запущена.'
            except Exception as exc:
                success = False
                checks = _load_custom_checks()
                result = f'Ошибка добавления проверки: {exc}'
            self._send_action_result(
                result,
                success=success,
                extra={
                    'custom_checks': _web_custom_checks(),
                    'pools': _web_pool_snapshot(_load_current_keys(), include_keys=True),
                },
            )
            return

        if path == '/custom_check_delete':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            data = parse_qs(body)
            check_id = data.get('id', [''])[0]
            success = True
            try:
                _delete_custom_check(check_id)
                result = 'Проверка удалена.'
            except Exception as exc:
                success = False
                result = f'Ошибка удаления проверки: {exc}'
            self._send_action_result(
                result,
                success=success,
                extra={
                    'custom_checks': _web_custom_checks(),
                    'pools': _web_pool_snapshot(_load_current_keys(), include_keys=True),
                },
            )
            return

        if path == '/pool_probe':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            data = parse_qs(body)
            proto = data.get('type', [''])[0]
            success = True
            try:
                if not proto:
                    started, queued = _probe_all_pool_keys_async(stale_only=False)
                    if started:
                        result = f'Безопасная проверка всех пулов запущена. В очереди: {queued}. Проверка идет через временный тестовый xray и не разрывает текущее подключение.'
                    elif queued:
                        result = 'Проверка пулов уже выполняется. Дождитесь обновления статусов.'
                    else:
                        result = 'В пулах нет ключей, которым нужна проверка.'
                elif proto not in ['shadowsocks', 'vmess', 'vless', 'vless2', 'trojan']:
                    raise ValueError('Неизвестный протокол')
                else:
                    keys = _pool_keys_for_proto(proto)
                    started, queued = _probe_pool_keys_background(proto, keys, stale_only=False)
                    if started:
                        result = f'Безопасная проверка пула {proto} запущена. В очереди: {queued}. Проверка идет через временный тестовый xray и не разрывает текущее подключение.'
                    elif queued:
                        result = 'Проверка пула уже выполняется. Дождитесь обновления статусов.'
                    else:
                        result = f'В пуле {proto} нет ключей, которым нужна проверка.'
            except Exception as exc:
                success = False
                result = f'Ошибка запуска проверки пула: {exc}'
            self._send_action_result(
                result,
                success=success,
                extra={'pool_probe_started': success},
            )
            return

        if path == '/pool_add':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            data = parse_qs(body)
            proto = data.get('type', [''])[0]
            keys_text = data.get('keys', [''])[0]
            success = True
            try:
                if proto not in ['shadowsocks', 'vmess', 'vless', 'vless2', 'trojan']:
                    raise ValueError('Неизвестный протокол')
                added = _add_keys_to_pool(proto, keys_text)
                result = f'Добавлено ключей в пул {proto}: {added}'
            except Exception as exc:
                success = False
                result = f'Ошибка добавления в пул: {exc}'
            self._send_action_result(
                result,
                success=success,
                extra={'pools': _web_pool_snapshot(_load_current_keys(), include_keys=True)},
            )
            return

        if path == '/pool_delete':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            data = parse_qs(body)
            proto = data.get('type', [''])[0]
            key_to_delete = data.get('key', [''])[0]
            success = True
            try:
                _delete_pool_key(proto, key_to_delete)
                result = f'Ключ удалён из пула {proto}'
            except Exception as exc:
                success = False
                result = f'Ошибка удаления из пула: {exc}'
            self._send_action_result(
                result,
                success=success,
                extra={'pools': _web_pool_snapshot(_load_current_keys(), include_keys=True)},
            )
            return

        if path == '/pool_apply':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            data = parse_qs(body)
            proto = data.get('type', [''])[0]
            key_to_apply = data.get('key', [''])[0]
            success = True
            apply_lock_acquired = False
            try:
                if not pool_apply_lock.acquire(blocking=False):
                    raise ValueError('Сейчас выполняется проверка или применение ключа. Дождитесь завершения операции.')
                apply_lock_acquired = True
                pools = _load_key_pools()
                if proto not in ['shadowsocks', 'vmess', 'vless', 'vless2', 'trojan']:
                    raise ValueError('Неизвестный протокол')
                if key_to_apply not in (pools.get(proto, []) or []):
                    raise ValueError('Ключ не найден в пуле')
                result = _install_key_for_protocol(proto, key_to_apply, verify=False)
                _set_active_key(proto, key_to_apply)
                _invalidate_web_status_cache()
                _invalidate_key_status_cache()
                _refresh_status_caches_async(_load_current_keys())
            except Exception as exc:
                success = False
                result = f'Ошибка применения ключа из пула: {exc}'
            finally:
                if apply_lock_acquired:
                    pool_apply_lock.release()
            self._send_action_result(
                result,
                success=success,
                extra={'protocol': proto, 'key': key_to_apply, 'pools': _web_pool_snapshot(_load_current_keys(), include_keys=True)},
            )
            return

        if path == '/pool_clear':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            data = parse_qs(body)
            proto = data.get('type', [''])[0]
            success = True
            try:
                if proto not in ['shadowsocks', 'vmess', 'vless', 'vless2', 'trojan']:
                    raise ValueError('Неизвестный протокол')
                removed = _clear_pool(proto)
                result = f'Пул {proto} очищен. Удалено ключей: {removed}'
            except Exception as exc:
                success = False
                result = f'Ошибка очистки пула: {exc}'
            self._send_action_result(
                result,
                success=success,
                extra={'pools': _web_pool_snapshot(_load_current_keys(), include_keys=True)},
            )
            return

        if path == '/pool_subscribe':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            data = parse_qs(body)
            proto = data.get('type', [''])[0]
            sub_url = data.get('url', [''])[0]
            success = True
            try:
                if proto not in ['shadowsocks', 'vmess', 'vless', 'vless2', 'trojan']:
                    raise ValueError('Неизвестный протокол')
                fetched, error = _fetch_keys_from_subscription(sub_url)
                if error:
                    raise ValueError(error)
                pools = _load_key_pools()
                if proto not in pools:
                    pools[proto] = []
                added = 0
                added_keys = []
                # Если выбран vless2, добавляем vless:// ключи в пул vless2
                source_proto = proto
                if proto == 'vless2':
                    source_proto = 'vless'
                for k in fetched.get(source_proto, []):
                    if k not in pools[proto]:
                        pools[proto].append(k)
                        added += 1
                        added_keys.append(k)
                _save_key_pools(pools)
                # Запускаем фоновую проверку для добавленных ключей
                if added_keys:
                    _probe_pool_keys_background(proto, added_keys)
                result = f'Загружено из subscription и добавлено в пул {proto}: {added} ключей'
                _invalidate_web_status_cache()
                _invalidate_key_status_cache()
            except Exception as exc:
                success = False
                result = f'Ошибка загрузки subscription: {exc}'
            self._send_action_result(
                result,
                success=success,
                extra={'pools': _web_pool_snapshot(_load_current_keys(), include_keys=True)},
            )
            return
        

        # /pool_check убран: проверка выполняется автоматически и отображается значками в пуле.

        if path != '/install':
            self._send_html('<h1>404 Not Found</h1>', status=404)
            return
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode('utf-8')
        data = parse_qs(body)
        key_type = data.get('type', [''])[0]
        key_value = data.get('key', [''])[0]
        result = 'Ключ установлен.'
        success = True
        apply_lock_acquired = False
        try:
            if not pool_apply_lock.acquire(blocking=False):
                raise ValueError('Сейчас выполняется проверка или применение ключа. Дождитесь завершения операции.')
            apply_lock_acquired = True
            if key_type == 'shadowsocks':
                shadowsocks(key_value)
                result = _apply_installed_proxy('shadowsocks', key_value, verify=False)
            elif key_type == 'vmess':
                vmess(key_value)
                result = _apply_installed_proxy('vmess', key_value, verify=False)
            elif key_type == 'vless':
                vless(key_value)
                result = _apply_installed_proxy('vless', key_value, verify=False)
            elif key_type == 'vless2':
                vless2(key_value)
                result = _apply_installed_proxy('vless2', key_value, verify=False)
            elif key_type == 'trojan':
                trojan(key_value)
                result = _apply_installed_proxy('trojan', key_value, verify=False)
            else:
                success = False
                result = 'Тип ключа не распознан.'
        except Exception as exc:
            success = False
            result = f'Ошибка установки: {exc}'
        else:
            if success and key_type in ('shadowsocks', 'vmess', 'vless', 'vless2', 'trojan'):
                _set_active_key(key_type, key_value)
                _invalidate_web_status_cache()
                _invalidate_key_status_cache()
                _refresh_status_caches_async(_load_current_keys())
        finally:
            if apply_lock_acquired:
                pool_apply_lock.release()

        self._send_action_result(
            result,
            success=success,
            extra={'protocol': key_type, 'key': key_value, 'pools': _web_pool_snapshot(_load_current_keys(), include_keys=True)},
        )


def start_http_server():
    global web_httpd
    try:
        bind_host = _resolve_web_bind_host()
        class ReusableThreadingHTTPServer(ThreadingHTTPServer):
            allow_reuse_address = True

        server_address = (bind_host, int(browser_port))
        httpd = ReusableThreadingHTTPServer(server_address, KeyInstallHTTPRequestHandler)
        httpd.daemon_threads = True
        web_httpd = httpd
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        listen_host = bind_host or '0.0.0.0'
        _write_runtime_log(f'HTTP server listening on {listen_host}:{browser_port}; LAN-only access enforced')
    except Exception as err:
        _write_runtime_log(f'HTTP server start failed on port {browser_port}: {err}', mode='w')


def wait_for_bot_start():
    global bot_ready
    while not bot_ready and not shutdown_requested.is_set():
        time.sleep(1)


def _read_v2ray_key(file_path):
    candidate_paths = [file_path]
    file_name = os.path.basename(file_path)
    current_dir = os.path.dirname(file_path)
    alternate_dirs = []
    if current_dir == XRAY_CONFIG_DIR:
        alternate_dirs.append(V2RAY_CONFIG_DIR)
    elif current_dir == V2RAY_CONFIG_DIR:
        alternate_dirs.append(XRAY_CONFIG_DIR)
    for directory in alternate_dirs:
        candidate_paths.append(os.path.join(directory, file_name))

    for candidate_path in candidate_paths:
        try:
            with open(candidate_path, 'r', encoding='utf-8') as f:
                value = f.read().strip()
            if value:
                return value
        except Exception:
            continue
    return None


def _save_v2ray_key(file_path, key):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(key.strip())


def _parse_vmess_key(key):
    if not key.startswith('vmess://'):
        raise ValueError('Неверный протокол, ожидается vmess://')
    encodedkey = key[8:]
    try:
        decoded = base64.b64decode(encodedkey + '=' * (-len(encodedkey) % 4)).decode('utf-8')
    except Exception as exc:
        raise ValueError(f'Не удалось декодировать vmess-ключ: {exc}')
    try:
        data = json.loads(decoded.replace("'", '"'))
    except Exception as exc:
        raise ValueError(f'Неверный JSON в vmess-ключе: {exc}')
    if not data.get('add') or not data.get('port') or not data.get('id'):
        raise ValueError('В vmess-ключе нет server/port/id')
    if data.get('net') == 'grpc':
        service_name = data.get('serviceName') or data.get('grpcSettings', {}).get('serviceName')
        if not service_name:
            data['serviceName'] = data.get('add')
    return data


def _parse_vless_key(key):
    parsed = urlparse(key)
    if parsed.scheme != 'vless':
        raise ValueError('Неверный протокол, ожидается vless://')
    if not parsed.hostname:
        raise ValueError('В vless-ключе отсутствует адрес сервера')
    if not parsed.username:
        raise ValueError('В vless-ключе отсутствует UUID')
    params = parse_qs(parsed.query)
    address = parsed.hostname
    port = parsed.port or 443
    user_id = parsed.username
    security = params.get('security', ['none'])[0]
    encryption = params.get('encryption', ['none'])[0]
    flow = params.get('flow', [''])[0]
    host = params.get('host', [''])[0]
    if not address and host:
        address = host
    network = params.get('type', params.get('network', ['tcp']))[0]
    path = params.get('path', ['/'])[0]
    if path == '':
        path = '/'
    sni = params.get('sni', [''])[0] or host or address
    service_name = params.get('serviceName', [''])[0]
    public_key = params.get('pbk', params.get('publicKey', ['']))[0]
    short_id = params.get('sid', params.get('shortId', ['']))[0]
    fingerprint = params.get('fp', params.get('fingerprint', ['']))[0]
    spider_x = params.get('spx', params.get('spiderX', ['']))[0]
    alpn = params.get('alpn', [''])[0]
    if not service_name and (network == 'grpc' or security == 'reality'):
        service_name = address
    return {
        'address': address,
        'port': port,
        'id': user_id,
        'security': security,
        'encryption': encryption,
        'flow': flow,
        'host': host,
        'path': path,
        'sni': sni,
        'type': network,
        'serviceName': service_name,
        'publicKey': public_key,
        'shortId': short_id,
        'fingerprint': fingerprint,
        'spiderX': spider_x,
        'alpn': alpn
    }


def _build_v2ray_config(vmess_key=None, vless_key=None, vless2_key=None, shadowsocks_key=None, trojan_key=None):
    config_data = {
        'log': {
            'access': '/dev/null',
            'error': CORE_PROXY_ERROR_LOG,
            'loglevel': 'warning'
        },
        'dns': {
            'hosts': {
                'api.telegram.org': '149.154.167.220'
            },
            'servers': ['8.8.8.8', '1.1.1.1', 'localhost'],
            'queryStrategy': 'UseIPv4'
        },
        'inbounds': [],
        'outbounds': [],
        'routing': {
            'domainStrategy': 'IPIfNonMatch',
            'rules': []
        }
    }

    if vmess_key:
        vmess_outbound = _proxy_outbound_from_key('vmess', vmess_key, 'proxy-vmess')
        config_data['inbounds'].append({
            'port': int(localportvmess),
            'listen': '127.0.0.1',
            'protocol': 'socks',
            'settings': {
                'auth': 'noauth',
                'udp': True,
                'ip': '127.0.0.1'
            },
            'sniffing': {'enabled': True, 'destOverride': ['http', 'tls']},
            'tag': 'in-vmess'
        })
        config_data['inbounds'].append({
            'port': int(localportvmess_transparent),
            'listen': '0.0.0.0',
            'protocol': 'dokodemo-door',
            'settings': {
                'network': 'tcp',
                'followRedirect': True
            },
            'sniffing': {'enabled': True, 'destOverride': ['http', 'tls']},
            'tag': 'in-vmess-transparent'
        })
        config_data['outbounds'].append(vmess_outbound)
        config_data['routing']['rules'].append({
            'type': 'field',
            'inboundTag': ['in-vmess', 'in-vmess-transparent'],
            'outboundTag': 'proxy-vmess',
            'enabled': True
        })

    if shadowsocks_key:
        shadowsocks_outbound = _proxy_outbound_from_key('shadowsocks', shadowsocks_key, 'proxy-shadowsocks')
        config_data['inbounds'].append({
            'port': int(localportsh_bot),
            'listen': '127.0.0.1',
            'protocol': 'socks',
            'settings': {
                'auth': 'noauth',
                'udp': True,
                'ip': '127.0.0.1'
            },
            'sniffing': {'enabled': True, 'destOverride': ['http', 'tls']},
            'tag': 'in-shadowsocks'
        })
        config_data['outbounds'].append(shadowsocks_outbound)
        config_data['routing']['rules'].append({
            'type': 'field',
            'inboundTag': ['in-shadowsocks'],
            'outboundTag': 'proxy-shadowsocks',
            'enabled': True
        })

    def add_vless_route(key_value, socks_port, transparent_port, socks_tag, transparent_tag, outbound_tag):
        if not key_value:
            return
        vless_outbound = _proxy_outbound_from_key('vless', key_value, outbound_tag)
        config_data['inbounds'].append({
            'port': int(socks_port),
            'listen': '127.0.0.1',
            'protocol': 'socks',
            'settings': {
                'auth': 'noauth',
                'udp': True,
                'ip': '127.0.0.1'
            },
            'sniffing': {'enabled': True, 'destOverride': ['http', 'tls']},
            'tag': socks_tag
        })
        config_data['inbounds'].append({
            'port': int(transparent_port),
            'listen': '0.0.0.0',
            'protocol': 'dokodemo-door',
            'settings': {
                'network': 'tcp',
                'followRedirect': True
            },
            'sniffing': {'enabled': True, 'destOverride': ['http', 'tls']},
            'tag': transparent_tag
        })
        config_data['outbounds'].append(vless_outbound)
        config_data['routing']['rules'].append({
            'type': 'field',
            'inboundTag': [socks_tag, transparent_tag],
            'outboundTag': outbound_tag,
            'enabled': True
        })

    add_vless_route(vless_key, localportvless, localportvless_transparent, 'in-vless', 'in-vless-transparent', 'proxy-vless')
    add_vless_route(vless2_key, localportvless2, localportvless2_transparent, 'in-vless2', 'in-vless2-transparent', 'proxy-vless2')

    if trojan_key:
        trojan_outbound = _proxy_outbound_from_key('trojan', trojan_key, 'proxy-trojan')
        config_data['inbounds'].append({
            'port': int(localporttrojan_bot),
            'listen': '127.0.0.1',
            'protocol': 'socks',
            'settings': {
                'auth': 'noauth',
                'udp': True,
                'ip': '127.0.0.1'
            },
            'sniffing': {'enabled': True, 'destOverride': ['http', 'tls']},
            'tag': 'in-trojan'
        })
        config_data['outbounds'].append(trojan_outbound)
        config_data['routing']['rules'].append({
            'type': 'field',
            'inboundTag': ['in-trojan'],
            'outboundTag': 'proxy-trojan',
            'enabled': True
        })

    if config_data['outbounds']:
        config_data['outbounds'].append({'protocol': 'freedom', 'tag': 'direct'})
        config_data['routing']['rules'].insert(0, {
            'type': 'field',
            'domain': CONNECTIVITY_CHECK_DOMAINS,
            'outboundTag': 'direct',
            'enabled': True
        })
        config_data['routing']['rules'].append({
            'type': 'field',
            'port': '0-65535',
            'outboundTag': 'direct',
            'enabled': True
        })

    return config_data


def _write_v2ray_config(vmess_key=None, vless_key=None, vless2_key=None, shadowsocks_key=None, trojan_key=None):
    config_json = _build_v2ray_config(vmess_key, vless_key, vless2_key, shadowsocks_key, trojan_key)
    os.makedirs(CORE_PROXY_CONFIG_DIR, exist_ok=True)
    with open(CORE_PROXY_CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config_json, f, ensure_ascii=False, indent=2)


def _write_all_proxy_core_config():
    _write_v2ray_config(
        _read_v2ray_key(VMESS_KEY_PATH),
        _read_v2ray_key(VLESS_KEY_PATH),
        _read_v2ray_key(VLESS2_KEY_PATH),
        _load_shadowsocks_key(),
        _load_trojan_key(),
    )


def vless(key):
    _parse_vless_key(key)
    _save_v2ray_key(VLESS_KEY_PATH, key)
    _write_all_proxy_core_config()


def vless2(key):
    _parse_vless_key(key)
    _save_v2ray_key(VLESS2_KEY_PATH, key)
    _write_all_proxy_core_config()


def vmess(key):
    _parse_vmess_key(key)
    _save_v2ray_key(VMESS_KEY_PATH, key)
    _write_all_proxy_core_config()

def trojan(key):
    raw_key = key.strip()
    trojan_data = _parse_trojan_key(raw_key)
    config = {
        'run_type': 'nat',
        'local_addr': '::',
        'local_port': int(localporttrojan),
        'remote_addr': trojan_data['address'],
        'remote_port': int(trojan_data['port']),
        'password': [trojan_data['password']],
        'raw_uri': raw_key,
        'type': trojan_data['type'],
        'security': trojan_data['security'],
        'sni': trojan_data['sni'],
        'host': trojan_data['host'],
        'path': trojan_data['path'],
        'serviceName': trojan_data['serviceName'],
        'fingerprint': trojan_data['fingerprint'],
        'alpn': trojan_data['alpn'],
        'fragment': trojan_data['fragment'],
        'ssl': {
            'verify': False,
            'verify_hostname': False,
        }
    }
    with open('/opt/etc/trojan/config.json', 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, separators=(',', ':'))
    _write_all_proxy_core_config()

def _decode_shadowsocks_uri(key):
    if not key.startswith('ss://'):
        raise ValueError('Неверный протокол, ожидается ss://')
    payload = key[5:]
    payload, _, _ = payload.partition('#')
    payload, _, _ = payload.partition('?')
    if '@' in payload:
        left, right = payload.rsplit('@', 1)
        host_part = right
        if ':' not in host_part:
            raise ValueError('Не удалось определить host:port в Shadowsocks-ключе')
        server, port = host_part.split(':', 1)
        try:
            decoded = base64.urlsafe_b64decode(left + '=' * (-len(left) % 4)).decode('utf-8')
            if ':' not in decoded:
                raise ValueError('Неверный формат декодированного payload Shadowsocks')
            method, password = decoded.split(':', 1)
        except Exception:
            decoded = unquote(left)
            if ':' not in decoded:
                raise ValueError('Неверный формат Shadowsocks credentials')
            method, password = decoded.split(':', 1)
    else:
        decoded = base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)).decode('utf-8')
        if '@' not in decoded:
            raise ValueError('Не удалось разобрать Shadowsocks-ключ')
        creds, host_part = decoded.rsplit('@', 1)
        if ':' not in host_part or ':' not in creds:
            raise ValueError('Неверный формат раскодированного Shadowsocks-URI')
        server, port = host_part.split(':', 1)
        method, password = creds.split(':', 1)
    return server, port, method, password


def shadowsocks(key=None):
    raw_key = key.strip()
    server, port, method, password = _decode_shadowsocks_uri(raw_key)
    config = {
        'server': [server],
        'mode': 'tcp_and_udp',
        'server_port': int(port),
        'password': password,
        'timeout': 86400,
        'method': method,
        'local_address': '::',
        'local_port': int(localportsh),
        'fast_open': False,
        'ipv6_first': True,
        'raw_uri': raw_key
    }
    with open('/opt/etc/shadowsocks.json', 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    _write_all_proxy_core_config()

def main():
    global proxy_mode, bot_polling
    _daemonize_process()
    _register_signal_handlers()
    _write_runtime_log('main() entered', mode='w')
    _cleanup_pool_probe_runtime(kill_processes=True)
    start_http_server()
    try:
        _write_all_proxy_core_config()
        os.system(CORE_PROXY_SERVICE_SCRIPT + ' restart')
    except Exception as exc:
        _write_runtime_log(f'Не удалось пересобрать core proxy config при старте: {exc}')
    if _load_bot_autostart():
        globals()['bot_ready'] = True
    saved_proxy_mode = _load_proxy_mode()
    proxy_mode = saved_proxy_mode
    ok, error = update_proxy(proxy_mode)
    if not ok:
        proxy_mode = config.default_proxy_mode
        update_proxy(proxy_mode, persist=False)
        if saved_proxy_mode in proxy_settings:
            _save_proxy_mode(saved_proxy_mode)
    elif proxy_mode in ['shadowsocks', 'vmess', 'vless', 'vless2', 'trojan']:
        startup_settings = {
            'shadowsocks': localportsh_bot,
            'vmess': localportvmess,
            'vless': localportvless,
            'vless2': localportvless2,
            'trojan': localporttrojan_bot,
        }
        startup_port = startup_settings.get(proxy_mode)
        endpoint_ok, endpoint_message = _check_local_proxy_endpoint(proxy_mode, startup_port)
        if not endpoint_ok:
            _write_runtime_log(f'Прокси-режим {proxy_mode} не ответил при старте: {endpoint_message}. Перезапускаю core proxy.')
            try:
                os.system(CORE_PROXY_SERVICE_SCRIPT + ' restart')
                time.sleep(3)
            except Exception:
                pass
            endpoint_ok, endpoint_message = _check_local_proxy_endpoint(proxy_mode, startup_port)
        if not endpoint_ok:
            fallback_mode = proxy_mode
            _write_runtime_log(f'Прокси-режим {fallback_mode} временно отключён при старте: {endpoint_message}')
            update_proxy('none', persist=False)
            _save_proxy_mode(fallback_mode)
        else:
            api_status = check_telegram_api(retries=0, retry_delay=0, connect_timeout=8, read_timeout=10)
            if not api_status.startswith('✅'):
                _write_runtime_log(f'Прокси-режим {proxy_mode} не подтверждён при старте: {api_status}')
    _deliver_pending_telegram_command_result()
    _start_telegram_result_retry_worker()
    _start_auto_failover_thread()
    _ensure_current_keys_in_pools()
    wait_for_bot_start()
    while not shutdown_requested.is_set():
        try:
            bot_polling = True
            bot.infinity_polling(timeout=60, long_polling_timeout=50)
        except Exception as err:
            bot_polling = False
            _write_runtime_log(err)
            if shutdown_requested.is_set():
                break
            if _is_polling_conflict(err):
                _write_runtime_log('Обнаружен конфликт getUpdates, ожидание перед повторной попыткой 65 секунд')
                time.sleep(65)
            else:
                time.sleep(5)
        else:
            bot_polling = False
            if shutdown_requested.is_set():
                break
            time.sleep(2)
    _finalize_shutdown()


if __name__ == '__main__':
    main()
