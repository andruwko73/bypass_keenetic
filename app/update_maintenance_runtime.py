import html


UPDATE_LABELS = {
    'update': 'Обновление до последнего релиза',
    'update_fork': 'Обновление из выбранного репозитория',
    'install': 'Установка программы',
    'rollback_update': 'Откат обновления',
}


def _progress(value):
    try:
        return max(0, min(100, int(value or 0)))
    except Exception:
        return 0


def _timestamp(value):
    try:
        return max(0.0, float(value or 0))
    except Exception:
        return 0.0


def maintenance_command_state(status):
    status = status if isinstance(status, dict) else {}
    command = str(status.get('command') or 'update').strip() or 'update'
    running = bool(status.get('running'))
    label = UPDATE_LABELS.get(command, 'Обновление программы')
    return {
        'running': running,
        'command': command,
        'label': label,
        'result': str(status.get('message') or ('Обновление выполняется…' if running else 'Обновление завершено.')),
        'progress': _progress(status.get('progress')),
        'progress_label': str(status.get('progress_label') or ''),
        'target_version': str(status.get('target_version') or ''),
        'started_at': _timestamp(status.get('started_at')),
        'updated_at': _timestamp(status.get('updated_at')),
        'finished_at': _timestamp(status.get('finished_at')),
    }


def render_maintenance_page(status, *, current_version=''):
    state = maintenance_command_state(status)
    target_version = state['target_version']
    target_suffix = f' {target_version}' if target_version else ''
    title = f'{state["label"]}{target_suffix}'
    progress = state['progress']
    label = state['progress_label'] or 'Подготовка обновления'
    message = state['result']
    current_version = str(current_version or '').strip()
    current_badge = f'<span class="version">{html.escape(current_version)}</span>' if current_version else ''
    return f'''<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="color-scheme" content="dark">
<title>{html.escape(title)}</title>
<style>
:root{{font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#e8f0f4;background:#071018}}
*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;display:grid;place-items:center;padding:20px;background:radial-gradient(circle at 25% 0,#12343b 0,transparent 42%),linear-gradient(145deg,#071018,#0b1721)}}
.card{{width:min(720px,100%);padding:28px;border:1px solid rgba(85,221,210,.42);border-radius:24px;background:rgba(14,27,38,.96);box-shadow:0 24px 70px rgba(0,0,0,.46);backdrop-filter:blur(18px) saturate(125%)}}
.head{{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}}h1{{margin:0;font-size:clamp(24px,5vw,38px);line-height:1.15}}.version{{flex:none;padding:8px 12px;border:1px solid rgba(85,221,210,.38);border-radius:12px;color:#8ff3eb;font-weight:800}}
.note{{margin:18px 0 22px;color:#b8c7d1;font-size:17px;line-height:1.5}}.progress-head{{display:flex;justify-content:space-between;gap:12px;margin-bottom:10px;font-weight:800}}.track{{height:16px;overflow:hidden;border-radius:999px;background:#263645}}.bar{{height:100%;width:{progress}%;border-radius:inherit;background:linear-gradient(90deg,#10c8bc,#6be5db);transition:width .35s ease}}
.message{{margin-top:18px;padding:16px;border-radius:16px;background:rgba(31,55,66,.72);white-space:pre-wrap;overflow-wrap:anywhere;color:#d8e3e9;line-height:1.45}}.hint{{margin:16px 0 0;color:#91a5b0;font-size:14px}}
</style>
</head>
<body>
<main class="card">
<div class="head"><h1 id="title">{html.escape(title)}</h1>{current_badge}</div>
<p class="note">Веб-интерфейс остаётся доступным. Telegram и фоновые проверки приостановлены до безопасного завершения замены файлов.</p>
<div class="progress-head"><span id="label">{html.escape(label)}</span><span id="percent">{progress}%</span></div>
<div class="track"><div class="bar" id="bar"></div></div>
<div class="message" id="message">{html.escape(message)}</div>
<p class="hint">Страница обновляется автоматически. Не перезагружайте роутер.</p>
</main>
<script>
(function(){{
let completed=false;
function text(id,value){{const node=document.getElementById(id);if(node)node.textContent=value||''}}
async function refresh(){{
  try{{
    const response=await fetch('/api/update_status',{{headers:{{Accept:'application/json'}},cache:'no-store'}});
    if(!response.ok)throw new Error('status');
    const state=await response.json();
    const progress=Math.max(0,Math.min(100,Number(state.progress||0)));
    text('label',state.progress_label||'Обновление выполняется');text('percent',Math.round(progress)+'%');text('message',state.message||'Обновление выполняется…');
    document.getElementById('bar').style.width=progress+'%';
    if(!state.running&&!completed){{completed=true;text('label','Обновление завершено');window.setTimeout(function(){{window.location.reload()}},1800)}}
  }}catch(error){{window.setTimeout(function(){{window.location.reload()}},1800)}}
}}
window.setInterval(refresh,2000);refresh();
}})();
</script>
</body>
</html>'''
