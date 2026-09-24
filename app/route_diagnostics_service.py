"""Authenticated web adapter for bounded, read-only route diagnostics."""
from pathlib import Path
import re
import socket

from proxy_apply_coordinator import ApplyBusy
from route_diagnostics_runtime import RouteDiagnosticsRuntime
from route_diagnostics_web import form_profile, render_page, results_html
from route_profiles import RouteProfileStore


def available_wans(route_path='/proc/net/route', *, index=socket.if_nametoindex):
    """Only kernel interfaces with an active IPv4 default route, never a guess."""
    names = []
    try:
        with Path(route_path).open() as routes:
            for number, line in enumerate(routes):
                if number > 256:
                    break
                parts = line.split()
                if len(parts) < 8 or parts[1] != '00000000' or parts[7] != '00000000':
                    continue
                name = parts[0]
                if (not re.fullmatch(r'[A-Za-z0-9_.:-]{1,15}', name) or name == 'lo'
                        or not int(parts[3], 16) & 1 or not index(name)):
                    continue
                if name not in names:
                    names.append(name)
    except (OSError, ValueError):
        return []
    return names[:8]


def memory_available(path='/proc/meminfo'):
    try:
        with Path(path).open() as file:
            for line in file:
                if line.startswith('MemAvailable:'):
                    return int(line.split()[1]) >= 96 * 1024
    except (OSError, ValueError, IndexError):
        pass
    return False


class RouteDiagnosticsService:
    def __init__(self, *, path, control, load_keys, coordinated, probe_lock,
                 resource_guard, wans=available_wans, runtime_factory=RouteDiagnosticsRuntime):
        self.control, self.load_keys, self.wans = control, load_keys, wans
        self.store = RouteProfileStore(path, lock=control.lock)
        self.runtime = runtime_factory(
            store=self.store, capture_keys=self._capture_keys, current=control.current,
            coordinated=coordinated, probe_lock=probe_lock, resource_guard=resource_guard,
        )

    def _capture_keys(self):
        with self.control.lock:
            ticket = self.control.capture()
            keys = self.load_keys()
            if not self.control.current(ticket):
                raise ApplyBusy('A newer manual action is pending')
            return keys, ticket

    def payload(self):
        error = ''
        try:
            state = self.store.snapshot()
        except (ValueError, OSError, RuntimeError):
            state = {'schema': 1, 'revision': -1, 'profiles': []}
            error = 'Не удалось прочитать профили. Существующий файл сохранён; изменение профилей временно недоступно.'
        diagnostics = self.runtime.snapshot()
        generation = self.control.generation()
        # The web response must never contain key text. Availability is enough
        # for form defaults; the worker takes its own coordinated key snapshot.
        active = [protocol for protocol, key in self.load_keys().items() if key]
        return dict(state, diagnostics=diagnostics, generation=generation, error=error, read_only=bool(error),
                    wans=self.wans(), active_protocols=active,
                    html=results_html(state['profiles'], diagnostics, generation=generation))

    def page(self, csrf_token):
        return render_page(self.payload(), csrf_token)

    def action(self, name, data):
        def value(field):
            values = data.get(field) or ['']
            return str(values[0])
        try:
            if name == 'cancel':
                self.runtime.cancel()
                message = 'Остановка запрошена.'
            elif name in ('save', 'remove', 'run'):
                revision = int(value('revision'))
                if name == 'save':
                    profile = form_profile(data)
                    if profile['wan'] not in self.wans():
                        raise ValueError('Интернет-подключение недоступно. Обновите страницу.')
                    self.store.save(profile, expected_revision=revision)
                    message = 'Профиль сохранён. Рабочие маршруты не изменены.'
                elif name == 'remove':
                    self.store.remove(value('profile_id'), expected_revision=revision)
                    message = 'Профиль удалён. Рабочие маршруты не изменены.'
                else:
                    state = self.store.snapshot()
                    if revision != state['revision']:
                        raise ValueError('Профили уже изменились. Обновите страницу.')
                    profile = next((p for p in state['profiles'] if p['id'] == value('profile_id')), None)
                    if profile is None:
                        raise ValueError('Профиль не найден. Обновите страницу.')
                    if profile['wan'] not in self.wans():
                        raise ValueError('Интернет-подключение недоступно. Обновите страницу.')
                    self.runtime.start(profile['id'])
                    message = 'Проверка запущена. Ключи и маршруты сохраняются.'
            else:
                return None
            return {'result': message, 'success': True, 'extra': {}}
        except ApplyBusy:
            message = 'Сейчас применяются настройки. Повторите позже.'
        except ValueError as exc:
            # Validation messages are fixed Russian text; parser exception
            # details (including an invalid URL or port) must stay private.
            message = str(exc) if str(exc) and 'А' <= str(exc)[0] <= 'Я' else 'Проверьте введённые данные и обновите страницу.'
        except (OSError, RuntimeError):
            message = 'Не удалось выполнить действие. Настройки сохранены.'
        return {'result': message, 'success': False, 'extra': {}}
