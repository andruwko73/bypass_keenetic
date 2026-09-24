"""Small diagnostic page; no keys, automatic apply or background auto-probing."""
import html
import json
import time
from urllib.parse import urlsplit

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
        rows.append(f'''<article class="route-diagnostic-card">
            <h2>{_escape(profile['label'])}</h2>
            <p>{_escape(source)} · {_escape(profile['destination'])} · {_escape(profile['wan'])}</p>
            <p><strong>{_escape(summary)}</strong></p>
            <ul>{''.join(items)}</ul>
            <p class="muted">Игровая задержка, UDP и потери пакетов: нет данных.</p>
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
    checks=''.join(f'<label class="route-choice"><input type="checkbox" name="protocols" value="{proto}"'+(' checked' if proto in available[:2] else '')+f'> {_escape(LABELS[proto])}</label>' for proto in PROTOCOLS)
    nonce=_escape(csrf_token)
    cards=results_html(profiles,state,generation=payload['generation'])
    job=STATES.get(state.get('job',{}).get('state','idle'),STATES['idle'])
    return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Диагностика маршрутов</title><link rel="stylesheet" href="/static/app.css">
    <style>
    body{{padding:0}}.route-diagnostic-page{{max-width:1080px;margin:auto;padding:20px;overflow-wrap:anywhere}}
    .route-diagnostic-page h1{{font-size:clamp(24px,5vw,36px)}}
    .route-diagnostic-card,.route-diagnostic-form{{border:1px solid var(--border);border-radius:18px;padding:20px;margin-block:24px;background:var(--surface);color:var(--text)}}
    .route-diagnostic-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr));gap:18px}}
    .route-diagnostic-grid label{{display:grid;gap:8px;min-width:0}}
    .route-diagnostic-page input:not([type=checkbox]),.route-diagnostic-page select{{width:100%;box-sizing:border-box;min-height:44px;font-size:16px}}
    .route-diagnostic-actions{{display:flex;flex-wrap:wrap;gap:12px;margin-block-start:20px}}
    .route-diagnostic-actions button{{min-height:44px;max-width:100%}}
    .route-diagnostic-page .route-choice{{display:inline-flex;align-items:center;gap:8px;min-height:44px;margin-inline-end:16px}}
    .route-diagnostic-page [hidden]{{display:none!important}}
    .route-diagnostic-page input[type=checkbox]{{width:20px;height:20px;flex:0 0 20px}}
    .route-diagnostic-page a{{color:var(--text);text-underline-offset:4px}}
    .route-diagnostic-page .muted{{opacity:.8}}.route-diagnostic-page fieldset{{margin-block:20px;min-width:0}}
    .route-diagnostic-page button:focus-visible,.route-diagnostic-page a:focus-visible{{outline:3px solid #69e4dc;outline-offset:4px}}
    @media(max-width:480px){{.route-diagnostic-page{{padding:12px}}.route-diagnostic-card,.route-diagnostic-form{{padding:16px}}}}
    </style></head><body><main class="route-diagnostic-page">
    <a href="/">← Панель управления</a><h1>Диагностика маршрутов</h1>
    <p>Сравните доступные пути к сервису. Проверка даёт рекомендации и не меняет ключи или маршруты.</p>
    <p class="muted">Измерения выполняются с роутера. Время ответа HTTPS не является пингом игры и не включает Wi-Fi устройства.</p>
    <p id="route-job" role="status" aria-live="polite">{_escape(job)}</p>
    <p id="route-error" role="alert">{_escape(payload.get('error',''))}</p>
    <button type="button" class="outline-button" id="route-cancel" hidden>Остановить проверку</button>
    <section id="route-results" aria-label="Сохранённые профили">{cards}</section>
    <form id="route-profile-form" class="route-diagnostic-form">
      <h2>Добавить профиль</h2><input type="hidden" name="csrf_token" value="{nonce}">
      <div class="route-diagnostic-grid">
        <label>Название<input name="label" required maxlength="64" placeholder="Например, видео на ПК"></label>
        <label>HTTPS-адрес сервиса<input name="url" type="url" required placeholder="https://example.com/" aria-describedby="route-url-hint"></label>
        <label>Устройство<input name="device" placeholder="IP устройства или router" value="router" aria-describedby="route-device-hint"></label>
        <label>Интернет-подключение<select name="wan" required>{options}</select></label>
      </div>
      <p class="muted" id="route-url-hint">Открытый HTTPS-адрес без пароля и параметров. До 20 коротких запросов на каждый путь.</p>
      <p class="muted" id="route-device-hint">Укажите router для самого роутера или IPv4-адрес домашнего устройства. Сейчас профиль используется только для сравнения.</p>
      <fieldset><legend>Прокси для сравнения — до трёх</legend>{checks}</fieldset>
      <label class="route-choice"><input type="checkbox" name="direct_allowed" value="1"> Разрешить сравнение с прямым подключением</label>
      <p class="muted">Для сервисов, которым обязательно нужен прокси, оставьте прямое подключение выключенным.</p>
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
