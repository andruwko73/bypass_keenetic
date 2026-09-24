"""Bounded private profiles for diagnostic-only route comparison."""
from copy import deepcopy
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import secrets
from urllib.parse import urlsplit, urlunsplit

from proxy_apply_coordinator import _atomic_json
from proxy_apply_state import _regular


MAX_PROFILES=8
MAX_STORE_BYTES=32768
PROTOCOLS=('vless','vless2','vmess','trojan','shadowsocks','hysteria2')


def public_host(value):
    text=str(value or '').strip().lower().rstrip('.')
    if len(text)>253 or not text:raise ValueError('Укажите домен назначения.')
    try:
        address=ipaddress.ip_address(text)
    except ValueError:
        try:text=text.encode('idna').decode('ascii')
        except UnicodeError:raise ValueError('Проверьте домен назначения.') from None
        if ('.' not in text or text.endswith(('.local','.localhost','.lan','.internal')) or
                any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',label) for label in text.split('.'))):
            raise ValueError('Укажите публичный домен назначения.')
        return text
    if not address.is_global:raise ValueError('Для проверки нужен публичный адрес.')
    return str(address)


def probe_url(value):
    parsed=urlsplit(str(value or '').strip())
    if (parsed.scheme!='https' or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.port not in (None,443) or len(parsed.path)>512
            or any(ord(c)<33 or ord(c)>126 for c in parsed.path)):
        raise ValueError('Укажите HTTPS-адрес без пароля, параметров и нестандартного порта.')
    host=public_host(parsed.hostname)
    authority='['+host+']' if ':' in host else host
    return urlunsplit(('https',authority,parsed.path or '/', '', ''))


def normalize_profile(value, *, existing_id=None):
    if not isinstance(value,dict):raise ValueError('Профиль не распознан.')
    allowed={'id','label','device','destination','url','wan','protocols','direct_allowed'}
    if set(value)-allowed:raise ValueError('Профиль содержит неподдерживаемые настройки.')
    label=str(value.get('label') or '').strip()
    if not 1<=len(label)<=64 or any(ord(c)<32 for c in label):raise ValueError('Введите название до 64 символов.')
    device=str(value.get('device') or 'router').strip()
    if device!='router':
        try:address=ipaddress.ip_address(device)
        except ValueError:raise ValueError('Укажите IP-адрес устройства в домашней сети.') from None
        home_networks=(ipaddress.ip_network('10.0.0.0/8'),ipaddress.ip_network('172.16.0.0/12'),ipaddress.ip_network('192.168.0.0/16'))
        if address.version!=4 or not any(address in network for network in home_networks):
            raise ValueError('Укажите IPv4-адрес устройства в домашней сети.')
        device=str(address)
    wan=str(value.get('wan') or '').strip()
    if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,15}',wan) or wan=='lo':raise ValueError('Выберите интернет-подключение.')
    protocols=value.get('protocols',[])
    if (not isinstance(protocols,(list,tuple)) or not 1<=len(protocols)<=3 or
            any(proto not in PROTOCOLS for proto in protocols) or len(set(protocols))!=len(protocols)):
        raise ValueError('Выберите от одного до трёх прокси для сравнения.')
    direct=value.get('direct_allowed',False)
    if type(direct) is not bool:raise ValueError('Проверьте разрешение прямого подключения.')
    identity=existing_id or value.get('id') or secrets.token_hex(6)
    if not isinstance(identity,str) or not re.fullmatch(r'[0-9a-f]{12}',identity):raise ValueError('Идентификатор профиля не распознан.')
    endpoint=probe_url(value.get('url'))
    destination=public_host(value.get('destination'))
    if urlsplit(endpoint).hostname!=destination:
        raise ValueError('Адрес проверки должен относиться к выбранному домену назначения.')
    return {'id':identity,'label':label,'device':device,'destination':destination,'url':endpoint,
            'wan':wan,'protocols':list(protocols),'direct_allowed':direct}


def profile_fingerprint(profile):
    value=normalize_profile(profile)
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


class RouteProfileStore:
    def __init__(self,path,*,lock):
        self.path=Path(path);self.lock=lock

    def _load(self):
        raw,_=_regular(self.path,MAX_STORE_BYTES)
        if raw is None:return {'schema':1,'revision':0,'profiles':[]}
        try:
            value=json.loads(raw)
            if (value['schema']!=1 or type(value['revision']) is not int or value['revision']<0 or
                    not isinstance(value['profiles'],list) or len(value['profiles'])>MAX_PROFILES):raise ValueError
            if any(not isinstance(p,dict) or not re.fullmatch(r'[0-9a-f]{12}',str(p.get('id') or '')) for p in value['profiles']):raise ValueError
            profiles=[normalize_profile(p) for p in value['profiles']]
            if len({p['id'] for p in profiles})!=len(profiles):raise ValueError
            return {'schema':1,'revision':value['revision'],'profiles':profiles}
        except (ValueError,KeyError,TypeError):
            raise ValueError('Не удалось прочитать профили. Существующие настройки сохранены.') from None

    def snapshot(self):
        # Writers use atomic replace. Readers may see the previous or next
        # complete revision without waiting behind a network apply operation.
        return deepcopy(self._load())

    def save(self,profile,*,expected_revision):
        with self.lock:
            state=self._load()
            if type(expected_revision) is not int or expected_revision!=state['revision']:
                raise ValueError('Профили уже изменились. Обновите страницу.')
            normalized=normalize_profile(profile)
            profiles=state['profiles'];index=next((i for i,p in enumerate(profiles) if p['id']==normalized['id']),None)
            if index is None:
                if len(profiles)>=MAX_PROFILES:raise ValueError('Доступно до восьми профилей. Удалите ненужный профиль.')
                profiles.append(normalized)
            else:profiles[index]=normalized
            state['revision']+=1
            if len(json.dumps(state).encode())>MAX_STORE_BYTES:raise ValueError('Размер профилей превышает лимит.')
            _atomic_json(self.path,state)
            return deepcopy(state)

    def remove(self,profile_id,*,expected_revision):
        with self.lock:
            state=self._load()
            if type(expected_revision) is not int or expected_revision!=state['revision']:
                raise ValueError('Профили уже изменились. Обновите страницу.')
            remaining=[p for p in state['profiles'] if p['id']!=profile_id]
            if len(remaining)==len(state['profiles']):raise ValueError('Профиль уже удалён. Обновите страницу.')
            state.update(profiles=remaining,revision=state['revision']+1)
            _atomic_json(self.path,state)
            return deepcopy(state)
