"""Small diagnostic page; no keys, automatic apply or background auto-probing."""
import html
import json
import time
from urllib.parse import urlsplit

from app_version import APP_VERSION_COUNTER
from route_profiles import PROTOCOLS, profile_fingerprint

LABELS={'vless':'Vless 1','vless2':'Vless 2','vmess':'VMess','trojan':'Trojan','shadowsocks':'Shadowsocks','hysteria2':'Hysteria2','direct':'Напрямую'}
STATES={'idle':'Проверка ещё не запускалась.','queued':'Подготавливаю проверку.','running':'Сравниваю маршруты. Обычно это занимает до трёх минут.',
        'completed':'Проверка завершена.','busy':'Сейчас работает другая проверка. Повторите позже.',
        'cancelling':'Останавливаю проверку после текущего запроса.','cancelled':'Проверка остановлена или настройки изменились. Можно запустить снова.',
        'failed':'Не удалось завершить проверку. Проверьте доступность адреса и повторите попытку.'}
REASONS={'stale':'Результат устарел','source_unverified':'Источник измерения не подтверждён','wan_unverified':'Интернет-подключение не подтверждено',
         'udp_unverified':'UDP не подтверждён','insufficient_samples':'Недостаточно измерений','unavailable':'Нет успешных ответов',
         'clock_changed':'Изменилось время роутера','generation_changed':'Ключи или маршруты изменились'}


def _escape(value):return html.escape(str(value),quote=True)


def navigation_html():
    return ('<div class="route-intersection-card route-diagnostics-entry">'
            '<div class="route-section-head"><strong>Качество маршрутов</strong>'
            '<small>Сравните доступные пути к сервису без изменения настроек.</small></div>'
            '<div class="route-intersection-actions"><form action="/route-diagnostics" method="get">'
            '<button type="submit">Диагностика маршрутов</button></form></div></div>')


def results_html(profiles,state,*,generation,now=None):
    now=time.time() if now is None else now
    rows=[];results=state.get('results',{})
    for profile in profiles:
        result=results.get(profile['id'],{})
        stale=bool(result) and (result.get('profile_fingerprint')!=profile_fingerprint(profile) or result.get('generation')!=generation or now-float(result.get('checked_at') or 0)>900 or float(result.get('checked_at') or 0)>now)
        winner='' if stale else result.get('recommended_protocol','')
        summary=('Рекомендация: '+LABELS.get(winner,'Нет данных')) if winner else ('Измерения устарели. Запустите проверку снова.' if stale else 'Для рекомендации пока нет подтверждённых измерений.')
        items=[]
        for window in result.get('windows',[])[:4]:
            metrics=window.get('metrics',{});proto=window.get('identity',{}).get('protocol','')
            reason=metrics.get('reason','')
            if stale:detail='Нет актуальных данных'
            elif reason:detail=REASONS.get(reason,'Нет подтверждённых данных')
            else:
                median=metrics.get('median_ms');p95=metrics.get('p95_ms')
                detail=f'Ответ HTTPS: обычно {median:.0f} мс, p95 {p95:.0f} мс; ответов {metrics.get("received_on_time",0)}/{metrics.get("sent",0)}'
            items.append('<li><strong>'+_escape(LABELS.get(proto,proto))+'</strong> — '+_escape(detail)+'</li>')
        for item in result.get('unavailable',[])[:4]:
            detail='Активный ключ не установлен' if item.get('reason')=='no_active_key' else 'Проверка этого пути недоступна'
            items.append('<li><strong>'+_escape(LABELS.get(item.get('protocol'),''))+'</strong> — '+detail+'</li>')
        source='Роутер' if profile['device']=='router' else profile['device']
        rows.append(f'''<article class="panel route-diagnostic-card">
            <h2>{_escape(profile['label'])}</h2>
            <p>{_escape(source)} · {_escape(profile['destination'])} · {_escape(profile['wan'])}</p>
            <p><strong>{_escape(summary)}</strong></p>
            <ul>{''.join(items)}</ul>
            <p class="field-hint">Игровая задержка, UDP и потери пакетов: нет данных.</p>
            <div class="route-diagnostic-actions">
              <button type="button" data-route-run="{_escape(profile['id'])}">Проверить маршрут</button>
              <button type="button" class="outline-button" data-route-remove="{_escape(profile['id'])}">Удалить профиль</button>
            </div>
        </article>''')
    return ''.join(rows) or '<p>Добавьте профиль устройства и адрес сервиса, чтобы сравнить доступные пути.</p>'


def render_page(payload,csrf_token):
    profiles=payload['profiles'];state=payload['diagnostics']
    wans=payload.get('wans',[])
    options=''.join(f'<option value="{_escape(name)}">{_escape(name)}</option>' for name in wans)
    if not options:options='<option value="">Нет доступного подключения</option>'
    available=payload.get('active_protocols',[])
    checks=''.join(f'<label class="subscription-hwid-toggle route-choice"><input class="subscription-switch-input" type="checkbox" name="protocols" value="{proto}"'+(' checked' if proto in available[:2] else '')+f'><span class="subscription-switch-ui" aria-hidden="true"></span><span class="subscription-hwid-label">{_escape(LABELS[proto])}</span></label>' for proto in PROTOCOLS)
    nonce=_escape(csrf_token)
    cards=results_html(profiles,state,generation=payload['generation'])
    job=STATES.get(state.get('job',{}).get('state','idle'),STATES['idle'])
    return f'''<!doctype html><html lang="ru" class="route-diagnostics"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
    <title>Диагностика маршрутов</title><link rel="icon" href="data:,">
    <link rel="stylesheet" href="/static/app.css?v={_escape(APP_VERSION_COUNTER)}">
    <script src="/static/app.js?v={_escape(APP_VERSION_COUNTER)}" defer></script>
    </head><body><main class="shell route-diagnostic-page">
    <header class="view-head route-diagnostic-header">
      <div class="route-diagnostic-heading"><h1>Диагностика маршрутов</h1>
        <form action="/" method="get"><button type="submit" class="outline-button">← Панель управления</button></form>
      </div>
      <p class="field-hint">Сравните доступные пути к сервису. Проверка даёт рекомендации и не меняет ключи или маршруты.</p>
      <p class="field-hint">Измерения выполняются с роутера. Время ответа HTTPS не является пингом игры и не включает Wi-Fi устройства.</p>
    </header>
    <section class="panel route-diagnostic-status" aria-label="Состояние проверки">
      <p id="route-job" role="status" aria-live="polite">{_escape(job)}</p>
      <p id="route-error" role="alert">{_escape(payload.get('error',''))}</p>
      <div class="route-diagnostic-actions"><button type="button" class="outline-button" id="route-cancel" hidden>Остановить проверку</button></div>
    </section>
    <section id="route-results" aria-label="Сохранённые профили">{cards}</section>
    <form id="route-profile-form" class="panel route-diagnostic-form">
      <h2>Добавить профиль</h2><input type="hidden" name="csrf_token" value="{nonce}">
      <div class="route-diagnostic-grid">
        <label><span class="field-label">Название</span><input name="label" required maxlength="64" placeholder="Например, видео на ПК"></label>
        <label><span class="field-label">HTTPS-адрес сервиса</span><input name="url" type="url" required placeholder="https://example.com/" aria-describedby="route-url-hint"></label>
        <label><span class="field-label">Устройство</span><input name="device" placeholder="IP устройства или router" value="router" aria-describedby="route-device-hint"></label>
        <label><span class="field-label">Интернет-подключение</span><select name="wan" required>{options}</select></label>
      </div>
      <p class="field-hint" id="route-url-hint">Открытый HTTPS-адрес без пароля и параметров. До 20 коротких запросов на каждый путь.</p>
      <p class="field-hint" id="route-device-hint">Укажите router для самого роутера или IPv4-адрес домашнего устройства. Сейчас профиль используется только для сравнения.</p>
      <fieldset class="route-diagnostic-options"><legend class="field-label">Прокси для сравнения — до трёх</legend><div class="route-diagnostic-choices">{checks}</div></fieldset>
      <label class="subscription-hwid-toggle route-choice"><input class="subscription-switch-input" type="checkbox" name="direct_allowed" value="1"><span class="subscription-switch-ui" aria-hidden="true"></span><span class="subscription-hwid-label">Разрешить сравнение с прямым подключением</span></label>
      <p class="field-hint">Для сервисов, которым обязательно нужен прокси, оставьте прямое подключение выключенным.</p>
      <div class="route-diagnostic-actions"><button type="submit"{' disabled' if len(profiles)>=8 or not wans or payload.get('read_only') else ''}>Сохранить профиль</button></div>
    </form></main>
    <script>
    (()=>{{
      const csrf={json.dumps(csrf_token)},states={json.dumps(STATES,ensure_ascii=False)};
      let revision={int(payload['revision'])},timer=0,busy=false;
      const error=document.getElementById('route-error');
      async function refresh(){{
        clearTimeout(timer);
        const response=await fetch('/api/route_diagnostics',{{cache:'no-store',headers:{{Accept:'application/json'}}}});
        if(!response.ok)throw new Error('Панель недоступна. Обновите страницу.');
        const data=await response.json();revision=data.revision;
        document.querySelector('#route-profile-form button[type=submit]').disabled=data.profiles.length>=8||!data.wans.length||data.read_only;
        if(data.error)error.textContent=data.error;
        document.getElementById('route-results').innerHTML=data.html;
        const job=data.diagnostics.job;
        document.getElementById('route-job').textContent=states[job.state]||states.idle;
        document.getElementById('route-cancel').hidden=!job.running;
        document.querySelectorAll('[data-route-run]').forEach(button=>button.disabled=job.running);
        if(job.running)timer=setTimeout(()=>refresh().catch(showError),5000);
      }}
      function showError(reason){{error.textContent=reason.message||'Не удалось выполнить действие. Повторите попытку.';}}
      async function action(name,data){{
        if(busy)return;busy=true;error.textContent='';
        data.set('csrf_token',csrf);data.set('revision',String(revision));
        try{{
          const response=await fetch('/route_diagnostics/'+name,{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded','Accept':'application/json','X-CSRF-Token':csrf}},body:data}});
          const result=await response.json();if(!response.ok||!result.ok)throw new Error(result.result||'Действие не выполнено.');
          await refresh();if(name==='save')document.getElementById('route-profile-form').reset();
        }}catch(reason){{showError(reason);}}finally{{busy=false;}}
      }}
      document.getElementById('route-profile-form').addEventListener('submit',event=>{{event.preventDefault();action('save',new URLSearchParams(new FormData(event.currentTarget)));}});
      document.addEventListener('click',event=>{{
        const run=event.target.closest('[data-route-run]'),remove=event.target.closest('[data-route-remove]');
        if(run)action('run',new URLSearchParams({{profile_id:run.dataset.routeRun}}));
        if(remove)action('remove',new URLSearchParams({{profile_id:remove.dataset.routeRemove}}));
      }});
      document.getElementById('route-cancel').addEventListener('click',()=>action('cancel',new URLSearchParams()));
      refresh().catch(showError);
    }})();
    </script></body></html>'''


def form_profile(data):
    def value(name,default=''):return str((data.get(name) or [default])[0]).strip()
    url=value('url')
    return {'label':value('label'),'device':value('device','router'),'destination':urlsplit(url).hostname or '',
            'url':url,'wan':value('wan'),'protocols':list(data.get('protocols') or []),'direct_allowed':value('direct_allowed')=='1'}
