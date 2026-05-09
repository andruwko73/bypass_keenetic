def render_web_styles(TELEGRAM_SVG_B64=''):
    return '''        :root{
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
            --control-height:36px;
        }
        [data-theme="light"]{
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
        }
        *{box-sizing:border-box;}
        body{
            margin:0;
                        font-family:Segoe UI,Helvetica,Arial,sans-serif;
            color:var(--text);
                        background:
                radial-gradient(circle at top left, rgba(215,134,68,.16), transparent 34%),
                radial-gradient(circle at top right, rgba(79,140,255,.16), transparent 28%),
                linear-gradient(180deg, #0f141c 0%, var(--bg) 100%);
                        padding:20px;
        }
        [data-theme="light"] body{
            background:
                radial-gradient(circle at top left, rgba(201,111,50,.18), transparent 34%),
                radial-gradient(circle at top right, rgba(31,122,106,.16), transparent 28%),
                linear-gradient(180deg, #f8f4ec 0%, var(--bg) 100%);
        }
                .shell{max-width:1180px;margin:0 auto;}
        .hero{margin-bottom:16px;padding:22px 24px;border:1px solid var(--border);border-radius:24px;background:linear-gradient(140deg, rgba(23,30,40,.98), rgba(32,42,56,.9));box-shadow:var(--shadow);}
        [data-theme="light"] .hero{background:linear-gradient(140deg, rgba(255,253,248,.98), rgba(239,226,203,.88));}
                .hero-copy{max-width:700px;}
                .hero-row{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;}
                .hero-actions{display:flex;align-items:flex-start;gap:10px;flex-wrap:wrap;position:relative;justify-content:flex-end;}
        .hero-meta{display:flex;flex-wrap:wrap;gap:10px;margin:16px 0 0;}
        .hero-chip{display:inline-flex;align-items:center;padding:8px 12px;border-radius:999px;background:rgba(79,140,255,.08);border:1px solid rgba(96,165,250,.18);font-size:13px;font-weight:700;color:var(--text);}
        .theme-toggle{display:inline-flex;align-items:center;gap:8px;padding:10px 14px;border-radius:8px;border:1px solid rgba(78,216,205,.5);background:rgba(34,67,73,.28);color:#96f1eb;font-size:13px;font-weight:700;cursor:pointer;box-shadow:none;white-space:nowrap;}
                .mode-toggle{display:inline-flex;align-items:center;gap:8px;padding:10px 14px;border-radius:8px;border:1px solid rgba(78,216,205,.5);background:rgba(34,67,73,.28);color:#96f1eb;font-size:13px;font-weight:700;cursor:pointer;box-shadow:none;white-space:nowrap;}
        .theme-toggle:hover{filter:none;transform:none;background:rgba(35,98,104,.44);border-color:rgba(96,214,205,.62);}
                .mode-toggle:hover{filter:none;transform:none;background:rgba(35,98,104,.44);border-color:rgba(96,214,205,.62);}
                .hero-popover{position:absolute;top:54px;right:0;min-width:260px;padding:14px;border:1px solid var(--border);border-radius:18px;background:linear-gradient(180deg, rgba(23,30,40,.98), rgba(32,42,56,.96));box-shadow:var(--shadow);z-index:10;}
                [data-theme="light"] .hero-popover{background:linear-gradient(180deg, rgba(255,253,248,.98), rgba(245,237,224,.96));}
                .hidden{display:none;}
                .mode-picker-form{display:grid;gap:10px;}
                .mode-picker-label{font-size:12px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);}
                .mode-choice-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px;}
                .mode-choice-grid form{display:block;margin:0;}
                .mode-choice{width:100%;height:var(--control-height);min-height:var(--control-height);justify-content:center;background:rgba(34,67,73,.28);border-color:rgba(78,216,205,.5);box-shadow:none;color:#96f1eb;}
                .app-mode-choice-grid{grid-template-columns:repeat(2,minmax(0,1fr));}
                .mode-choice.active{background:rgba(48,191,181,.18);border-color:rgba(78,216,205,.5);color:#94f3ec;}
                .mode-choice:hover{filter:none;transform:none;background:rgba(35,98,104,.42);}
        h1{margin:0 0 4px;font-size:22px;line-height:1.15;letter-spacing:0;color:var(--text);}
        h2{margin:0 0 14px;font-size:20px;color:var(--text);}
            p{margin:0 0 8px;line-height:1.5;color:var(--muted);}
        .hero strong{color:var(--text);}
                .layout{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin-top:16px;}
        .panel{min-width:0;padding:18px;border:1px solid var(--border);border-radius:22px;background:linear-gradient(180deg, rgba(23,30,40,.96), rgba(32,42,56,.94));box-shadow:var(--shadow);}
        [data-theme="light"] .panel{background:linear-gradient(180deg, rgba(255,253,248,.96), rgba(245,237,224,.94));}
        form{display:grid;gap:12px;}
                input,textarea,select{width:100%;padding:13px 14px;border-radius:14px;border:1px solid var(--border);background:var(--surface-soft);color:var(--text);font-size:16px;outline:none;}
                input:focus,textarea:focus,select:focus{border-color:rgba(31,122,106,.6);box-shadow:0 0 0 4px rgba(31,122,106,.08);}
        textarea{min-height:138px;resize:vertical;}
                input::placeholder,textarea::placeholder{color:#8b8f92;}
        button{min-height:var(--control-height);height:var(--control-height);display:inline-flex;align-items:center;justify-content:center;text-align:center;padding:0 12px;border:1px solid rgba(78,216,205,.5);border-radius:8px;background:rgba(34,67,73,.28);color:#96f1eb;font-size:15px;font-weight:700;line-height:1.15;cursor:pointer;transition:border-color .15s ease, background-color .15s ease, color .15s ease;box-shadow:none;}
        button:hover{filter:none;transform:none;border-color:rgba(96,214,205,.62);background:rgba(35,98,104,.44);}
        button:disabled{cursor:wait;opacity:.72;filter:saturate(.7);transform:none;}
                button.danger{border-color:rgba(205,86,82,.52);background:rgba(94,36,42,.34);color:#ffb7b1;box-shadow:none;}
                .success-button{border-color:rgba(78,216,205,.5);background:rgba(34,67,73,.28);color:#96f1eb;box-shadow:none;}
                .secondary-button{border-color:rgba(78,216,205,.5);background:rgba(34,67,73,.28);color:#96f1eb;box-shadow:none;}
        .status-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-bottom:14px;}
        .status-card{min-width:0;min-height:126px;display:flex;flex-direction:column;gap:6px;padding:16px;border-radius:8px;background:rgba(79,140,255,.08);border:1px solid rgba(96,165,250,.18);}
        .status-label{display:block;margin-bottom:8px;font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:#90a5c4;}
                .status-value{display:block;font-size:16px;line-height:1.4;color:var(--text);overflow-wrap:anywhere;word-break:break-word;}
                .notice{padding:12px 14px;border-radius:16px;margin-bottom:14px;}
                .notice strong{display:block;margin-bottom:8px;color:var(--text);}
        .notice-result{background:var(--warn-bg);border:1px solid var(--warn-border);}
        .notice-status{background:var(--success-bg);border:1px solid var(--success-border);}
            .hero-status{margin-top:12px;margin-bottom:0;}
            .hero-status-compact p:last-child{margin-bottom:0;}
            .hero-status-header{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:6px;}
            .traffic-inline{display:flex;flex-wrap:wrap;gap:8px;justify-content:flex-end;}
            .traffic-chip{display:inline-flex;align-items:center;gap:8px;padding:6px 10px;border-radius:999px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);}
            .traffic-chip-label{font-size:11px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);}
            .traffic-chip-value{font-size:13px;font-weight:700;color:var(--text);}
                .status-note{margin-top:6px;color:var(--text);font-size:14px;line-height:1.45;overflow-wrap:anywhere;word-break:break-word;}
                .command-progress-block{margin:14px 0 10px;padding:12px 14px;border:1px solid var(--border);border-radius:14px;background:rgba(255,255,255,.03);}
                .command-progress-header{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:8px;color:var(--text);font-size:13px;font-weight:700;}
                .command-progress-track{width:100%;height:10px;border-radius:999px;background:rgba(255,255,255,.08);overflow:hidden;}
                .command-progress-fill{height:100%;border-radius:999px;background:linear-gradient(90deg, var(--secondary), var(--primary));transition:width .35s ease;}
                .log-output{margin:0;white-space:pre-wrap;word-break:break-word;font:13px/1.45 Consolas,Monaco,monospace;color:var(--text);}
                .eyebrow{display:inline-block;margin-bottom:10px;font-size:12px;font-weight:800;letter-spacing:.14em;text-transform:uppercase;color:#8b6f4a;}
                .section-title{margin:0 0 6px;font-size:24px;color:var(--text);}
                .section-subtitle{margin:0;color:var(--muted);overflow-wrap:anywhere;word-break:break-word;}
                .start-card{display:flex;flex-direction:column;justify-content:space-between;}
                .app-mode-control{position:relative;margin:0;min-width:0;z-index:15;}
                .app-mode-command{width:100%;justify-content:space-between;gap:12px;}
                .app-mode-control .app-mode-picker{top:calc(100% + 8px);left:0;right:auto;width:min(420px,calc(100vw - 32px));min-width:260px;z-index:30;}
                .command-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:14px;}
                .command-grid.service-command-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px 12px;margin-top:10px;}
                .command-grid form{min-width:0;}
                .command-grid button{width:100%;height:var(--control-height);min-height:var(--control-height);display:flex;align-items:center;justify-content:center;text-align:center;line-height:1.15;padding:0 12px;}
                .card-topline{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;margin-bottom:8px;}
                .file-chip{display:inline-flex;align-items:center;padding:6px 10px;border-radius:999px;background:rgba(201,111,50,.12);border:1px solid rgba(201,111,50,.2);font-size:12px;font-weight:700;color:#7c4b21;}
                .key-status-wrap{display:inline-flex;align-items:center;justify-content:flex-end;gap:8px;max-width:62%;}
                .key-status-icons{display:inline-flex;gap:6px;align-items:center;flex:none;}
                .key-status-badge{display:inline-flex;align-items:center;max-width:100%;padding:6px 10px;border-radius:999px;border:1px solid transparent;font-size:12px;font-weight:700;white-space:normal;line-height:1.25;text-align:right;}
                .key-status-ok{background:rgba(31,122,106,.14);border-color:rgba(31,122,106,.3);color:#9be4d3;}
                .key-status-fail{background:rgba(168,68,47,.14);border-color:rgba(168,68,47,.28);color:#ffbeb2;}
                .key-status-warn{background:rgba(201,111,50,.14);border-color:rgba(201,111,50,.28);color:#f6c892;}
                .key-status-empty{background:rgba(159,176,200,.1);border-color:rgba(159,176,200,.18);color:var(--muted);}
                .key-status-note{margin:-4px 0 4px;color:var(--muted);font-size:14px;line-height:1.45;overflow-wrap:anywhere;}
        .protocol-card{min-width:0;}
        .pool-details{margin-top:12px;border-top:1px solid var(--border);padding-top:12px;cursor:pointer;}
        .pool-summary{font-size:13px;font-weight:700;color:var(--text);padding:4px 0;}
        .pool-list{list-style:none;padding:0;margin:8px 0;display:grid;gap:6px;}
        .pool-item{display:flex;align-items:center;gap:8px;padding:6px 10px;border-radius:10px;background:rgba(255,255,255,.03);border:1px solid var(--border);font-size:12px;}
        .pool-item-active{border-color:rgba(31,122,106,.62);background:rgba(31,122,106,.14);}
        .pool-apply-form{flex:1;min-width:0;margin:0;display:block;}
        .pool-apply-btn{width:100%;min-width:0;padding:4px 0;border:none;background:transparent;box-shadow:none;color:var(--text);font-size:12px;font-weight:700;text-align:left;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
        .pool-apply-btn:hover{background:transparent;filter:none;transform:none;color:var(--primary-hover);}
        .pool-key-icons{display:inline-flex;gap:6px;align-items:center;}
        .pool-key-meta{color:var(--muted);font-size:11px;white-space:nowrap;}
        .pool-item-form{margin:0;padding:0;display:inline;}
        .pool-delete-btn{padding:2px 8px;border:none;border-radius:6px;background:rgba(168,68,47,.2);color:#ffbeb2;font-size:13px;cursor:pointer;line-height:1.4;box-shadow:none;min-width:0;}
        .pool-delete-btn:hover{background:rgba(168,68,47,.4);filter:none;transform:none;}
        .pool-empty{color:var(--muted);justify-content:center;}
        .pool-add-form{margin-top:8px;display:grid;gap:8px;}
        .pool-add-actions{display:flex;gap:8px;}
        .pool-add-actions button{padding:8px 14px;font-size:13px;}
        .pool-subscribe-row{margin-top:8px;display:flex;align-items:stretch;gap:8px;}
        .pool-subscribe-form{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;flex:1;}
        .pool-subscribe-form button,.pool-clear-btn{height:var(--control-height);min-height:var(--control-height);padding:0 12px;font-size:13px;line-height:1.15;white-space:nowrap;}
        .pool-clear-form{margin:0;display:flex;}
        .pool-clear-btn{height:100%;}
        .secondary-button{border-color:rgba(78,216,205,.5);background:rgba(34,67,73,.28);color:#96f1eb;box-shadow:none;}
        .wide{grid-column:1 / -1;}
        .app-shell{max-width:1240px;margin:0 auto;}
        .topbar{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:14px;padding:14px 16px;border:1px solid var(--border);border-radius:8px;background:rgba(23,30,40,.96);box-shadow:var(--shadow);position:sticky;top:10px;z-index:20;}
        [data-theme="light"] .topbar{background:rgba(255,253,248,.96);}
        .brand{display:flex;align-items:center;gap:12px;min-width:0;}
        .brand-mark{display:inline-flex;align-items:center;justify-content:center;width:40px;height:40px;border-radius:8px;background:rgba(31,122,106,.18);border:1px solid rgba(31,122,106,.35);color:#7ff0d8;font-size:15px;font-weight:900;text-transform:uppercase;}
        .brand p{margin:0;font-size:12px;color:var(--muted);}
        .topbar-actions{display:flex;align-items:center;justify-content:flex-end;gap:10px;flex-wrap:wrap;position:relative;min-width:0;}
        .api-pill{display:inline-flex;align-items:center;max-width:min(520px,42vw);padding:8px 10px;border-radius:8px;background:rgba(31,122,106,.14);border:1px solid rgba(31,122,106,.28);color:#9be4d3;font-size:12px;font-weight:700;line-height:1.35;white-space:normal;overflow:visible;text-overflow:clip;overflow-wrap:anywhere;word-break:break-word;}
        .workspace-layout{display:grid;grid-template-columns:128px minmax(0,1fr);gap:14px;align-items:start;}
        .side-nav{position:sticky;top:96px;display:grid;gap:8px;padding:10px;border:1px solid var(--border);border-radius:8px;background:rgba(23,30,40,.94);box-shadow:var(--shadow);}
        [data-theme="light"] .side-nav{background:rgba(255,253,248,.94);}
        .nav-item{display:flex;align-items:center;gap:8px;justify-content:flex-start;min-height:46px;padding:10px;border:1px solid transparent;border-radius:8px;background:transparent;color:var(--muted);box-shadow:none;font-size:14px;line-height:1.2;}
        .nav-item:hover{transform:none;filter:none;background:rgba(255,255,255,.05);}
        .nav-item.active{background:rgba(31,122,106,.18);border-color:rgba(31,122,106,.36);color:var(--text);}
        .app-main{min-width:0;}
        .app-view{display:none;}
        .app-view.active{display:block;}
        .view-head{margin-bottom:12px;padding:16px 18px;border:1px solid var(--border);border-radius:8px;background:rgba(23,30,40,.92);}
        [data-theme="light"] .view-head{background:rgba(255,253,248,.92);}
        .view-head h2{margin:0 0 6px;font-size:24px;}
        .status-dashboard{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-bottom:12px;}
        .status-card-wide{grid-column:1 / -1;min-height:0;}
        .segmented{display:flex;gap:0;margin-bottom:12px;border:1px solid var(--border);border-radius:8px;overflow:auto;background:rgba(255,255,255,.03);}
        .seg-tab{display:flex;align-items:center;justify-content:center;gap:8px;min-width:118px;padding:12px 14px;border-radius:0;border-right:1px solid var(--border);background:transparent;color:var(--muted);box-shadow:none;white-space:nowrap;}
        .seg-tab:last-child{border-right:none;}
        .seg-tab:hover{transform:none;filter:none;background:rgba(255,255,255,.05);}
        .seg-tab.active{background:rgba(31,122,106,.22);color:var(--text);}
        .tab-count{display:inline-flex;align-items:center;justify-content:center;min-width:24px;padding:2px 6px;border-radius:999px;background:rgba(255,255,255,.08);font-size:12px;}
        .protocol-workspace,.list-workspace{display:none;padding:18px;border:1px solid var(--border);border-radius:8px;background:linear-gradient(180deg, rgba(23,30,40,.96), rgba(32,42,56,.94));box-shadow:var(--shadow);}
        [data-theme="light"] .protocol-workspace,[data-theme="light"] .list-workspace{background:linear-gradient(180deg, rgba(255,253,248,.96), rgba(245,237,224,.94));}
        .protocol-workspace.active,.list-workspace.active{display:block;}
        .workspace-head{display:flex;align-items:flex-start;justify-content:space-between;gap:14px;margin-bottom:14px;}
        .subtabs{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));border:1px solid var(--border);border-radius:8px;overflow:hidden;margin-bottom:14px;}
        .subtab{border-radius:0;border-right:1px solid var(--border);background:transparent;color:var(--muted);box-shadow:none;}
        .subtab:last-child{border-right:none;}
        .subtab.active{background:rgba(31,122,106,.2);color:var(--text);}
        .subtab:hover{transform:none;filter:none;background:rgba(255,255,255,.05);}
        .protocol-subview{display:none;}
        .protocol-subview.active{display:grid;gap:14px;}
        .field-label{font-size:12px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);}
        .form-actions{display:flex;gap:10px;flex-wrap:wrap;}
        .form-actions button{min-width:160px;}
        .social-list-actions{display:grid;grid-template-columns:repeat(auto-fit,minmax(118px,1fr));gap:8px;align-items:stretch;margin-top:8px;}
        .social-list-title{display:flex;align-items:center;color:var(--muted);font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;}
        .social-list-actions button{width:100%;min-width:0;height:var(--control-height);min-height:var(--control-height);}
        .pool-toolbar{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:12px;}
        .pool-toolbar form{display:block;}
        .pool-table-wrap{overflow:auto;border:1px solid var(--border);border-radius:8px;}
        .pool-table{width:100%;border-collapse:collapse;font-size:13px;}
        .pool-table th,.pool-table td{padding:10px;border-bottom:1px solid var(--border);text-align:left;vertical-align:middle;}
        .pool-table th{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);background:rgba(255,255,255,.03);}
        .pool-row:last-child td{border-bottom:none;}
        .pool-row-active{background:rgba(31,122,106,.12);}
        .pool-active-cell{width:72px;color:#9be4d3;font-weight:700;}
        .pool-key-cell{min-width:260px;}
        .pool-hash{display:none;}
        .pool-mobile-active{display:none;margin-left:6px;padding:1px 6px;border-radius:5px;background:rgba(48,191,181,.16);border:1px solid rgba(48,191,181,.34);color:#9ff7ef;font-size:9px;font-weight:900;letter-spacing:.04em;text-transform:uppercase;line-height:1.2;vertical-align:middle;}
        .pool-row-active .pool-mobile-active{display:inline-flex;align-items:center;}
        .pool-service-cell{width:48px;text-align:center;}
        .pool-checked-cell{width:92px;color:var(--muted);font-size:12px;}
        .pool-actions-cell{width:110px;}
        .pool-actions-cell form{display:block;}
        .pool-empty-row td{text-align:center;color:var(--muted);}
        .pool-add-form,.pool-subscribe-form,.list-editor-form{margin-top:0;}
        .overview-service-grid,.service-groups{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;}
        .overview-service-grid{margin-top:12px;}
        .service-panel-wide{grid-column:1 / -1;}
        .service-panel{position:relative;z-index:6;overflow:visible;border-radius:8px;}
        .service-panel h3{margin:0 0 12px;font-size:18px;}
        .key-status-icons img,.pool-service-cell img,.status-value img,.api-pill img{width:20px!important;height:20px!important;}
        /* Compact design pass: one visual language for cards, forms, buttons and navigation. */
        :root{
            --scrollbar-size:8px;
            --scrollbar-track:#111923;
            --scrollbar-thumb:#415365;
            --scrollbar-thumb-hover:#53687d;
            --focus-ring:0 0 0 3px rgba(78,216,205,.16);
            --radius-panel:10px;
            --radius-control:8px;
        }
        html{scrollbar-color:var(--scrollbar-thumb) var(--scrollbar-track);scrollbar-width:thin;}
        body{font-family:Arial,"Segoe UI",system-ui,-apple-system,BlinkMacSystemFont,sans-serif;background:linear-gradient(145deg,#0c1118 0%,#111821 48%,#0b1016 100%);padding:14px;}
        *{scrollbar-color:var(--scrollbar-thumb) var(--scrollbar-track);scrollbar-width:thin;}
        *::-webkit-scrollbar{width:var(--scrollbar-size);height:var(--scrollbar-size);}
        *::-webkit-scrollbar-track{background:var(--scrollbar-track);border-radius:999px;}
        *::-webkit-scrollbar-thumb{background:var(--scrollbar-thumb);border:2px solid var(--scrollbar-track);border-radius:999px;}
        *::-webkit-scrollbar-thumb:hover{background:var(--scrollbar-thumb-hover);}
        [data-theme="light"] body{background:linear-gradient(145deg,#f7f3ea 0%,#ece3d4 100%);}
        button{min-height:var(--control-height);height:var(--control-height);display:inline-flex;align-items:center;justify-content:center;text-align:center;border:1px solid rgba(78,216,205,.5);border-radius:8px;background:rgba(34,67,73,.28);box-shadow:none;color:#96f1eb;font-size:12px;font-weight:650;line-height:1.15;padding:0 12px;}
        button:focus-visible,input:focus-visible,textarea:focus-visible,select:focus-visible{outline:none;border-color:rgba(78,216,205,.62);box-shadow:var(--focus-ring);}
        button:hover{filter:none;transform:none;border-color:rgba(96,214,205,.62);background:rgba(35,98,104,.44);}
        button.danger{border-color:rgba(205,86,82,.52);background:rgba(94,36,42,.52);color:#ffb7b1;}
        button.danger:hover{background:rgba(122,45,49,.62);border-color:rgba(230,109,101,.68);}
        .secondary-button,.success-button,.outline-button,.service-preset-btn{border-color:rgba(78,216,205,.5);background:rgba(34,67,73,.28);color:#96f1eb;box-shadow:none;}
        .secondary-button:hover,.success-button:hover,.outline-button:hover,.service-preset-btn:hover{background:rgba(35,98,104,.44);border-color:rgba(96,214,205,.62);}
        input,textarea,select{border-radius:8px;background:rgba(11,17,25,.58);border:1px solid rgba(91,124,150,.42);font-size:12px;line-height:1.34;padding:7px 9px;}
        input:focus,textarea:focus,select:focus{border-color:rgba(78,216,205,.62);box-shadow:0 0 0 3px rgba(78,216,205,.1);}
        textarea{min-height:78px;}
        .topbar,.side-nav,.view-head,.panel,.protocol-workspace,.list-workspace,.confirm-card{border-radius:10px;background:rgba(17,25,35,.88);border-color:rgba(91,124,150,.34);box-shadow:0 14px 34px rgba(0,0,0,.22);backdrop-filter:blur(10px);}
        .topbar{top:8px;padding:9px 10px;margin-bottom:10px;justify-content:stretch;}
        .brand-mark{width:40px;height:40px;background:rgba(48,191,181,.14);border-color:rgba(83,232,219,.32);color:#78f5ec;}
        h1{font-size:18px;font-weight:700;}
        h2{font-size:19px;font-weight:700;line-height:1.22;}
        .brand p,.section-subtitle,.status-note,.key-status-note{color:#b9c6d3;}
        .topbar-actions{width:100%;display:grid;grid-template-columns:minmax(340px,.9fr) minmax(320px,1.2fr) auto auto auto;align-items:center;justify-content:stretch;gap:8px;}
        .theme-control{position:relative;min-width:0;}
        .theme-control .theme-toggle{width:100%;justify-content:center;}
        .theme-control .theme-picker{top:calc(100% + 8px);right:0;width:min(420px,calc(100vw - 32px));min-width:260px;z-index:32;}
        .app-caption{display:block;min-width:0;color:#eef7ff;white-space:normal;overflow-wrap:anywhere;word-break:break-word;}
        .app-caption strong{display:block;max-width:none;font-size:15px;font-weight:800;line-height:1.18;letter-spacing:0;white-space:normal;overflow-wrap:anywhere;word-break:break-word;}
        .app-branch{display:block;margin-top:3px;font-size:11px;font-weight:700;line-height:1.2;color:var(--muted);white-space:normal;overflow-wrap:anywhere;word-break:break-word;}
        .version-badge{justify-self:end;align-self:start;display:inline-flex;align-items:center;justify-content:center;min-height:22px;padding:3px 7px;border-radius:7px;border:1px solid rgba(91,124,150,.42);background:rgba(17,25,35,.7);color:var(--muted);font-size:10px;font-weight:800;line-height:1;letter-spacing:.04em;white-space:nowrap;box-shadow:none;}
        [data-theme="light"] .version-badge{background:rgba(255,253,248,.82);}
        .api-pill,.mode-toggle,.theme-toggle{height:var(--control-height);min-height:var(--control-height);min-width:0;border-radius:8px;border-color:rgba(91,124,150,.42);background:rgba(17,25,35,.76);box-shadow:none;font-size:12px;}
        .mode-toggle,.theme-toggle{border-color:rgba(78,216,205,.5);background:rgba(34,67,73,.28);color:#96f1eb;}
        .api-pill{display:grid;grid-template-columns:auto minmax(0,1fr);gap:7px;align-items:center;width:100%;max-width:none;font-size:12px;line-height:1.25;color:#d9e6ef;}
        .api-pill::before{content:"";display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:6px;background-color:rgba(48,191,181,.14);background-image:url("data:image/svg+xml;base64,{TELEGRAM_SVG_B64}");background-repeat:no-repeat;background-position:center;background-size:13px 13px;}
        .workspace-layout{grid-template-columns:138px minmax(0,1fr);gap:12px;}
        .side-nav{top:86px;padding:9px;gap:7px;}
        .nav-item{height:var(--control-height);min-height:var(--control-height);padding:0 10px;color:#c7d2df;}
        .nav-item span{font-size:13px;}
        .nav-icon{width:16px;height:16px;flex:none;stroke:currentColor;stroke-width:1.9;stroke-linecap:round;stroke-linejoin:round;fill:none;}
        .nav-item.active{background:rgba(48,191,181,.13);border-color:rgba(78,216,205,.32);color:#9af8f1;}
        .view-head{padding:11px 13px;margin-bottom:9px;}
        .view-head h2{margin-bottom:4px;font-size:19px;}
        .eyebrow{color:#d3a557;font-size:11px;letter-spacing:.14em;}
        .section-subtitle{font-size:13px;line-height:1.35;}
        .status-dashboard{grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;margin-bottom:9px;}
        .status-card{position:relative;min-height:76px;padding:10px;border-radius:9px;background:linear-gradient(145deg,rgba(20,31,43,.94),rgba(15,23,32,.94));border:1px solid rgba(91,124,150,.34);box-shadow:none;}
        .status-card-wide{grid-column:auto;}
        .status-card-top{display:flex;align-items:flex-start;gap:8px;width:100%;}
        .status-copy{min-width:0;flex:1;}
        .card-icon{display:inline-flex;align-items:center;justify-content:center;flex:none;width:28px;height:28px;border-radius:7px;background:rgba(48,191,181,.14);border:1px solid rgba(78,216,205,.22);color:#76eee5;font-size:15px;line-height:1;}
        .card-icon img{width:17px!important;height:17px!important;}
        .status-dot{width:8px;height:8px;border-radius:50%;background:#68d36f;box-shadow:0 0 0 3px rgba(104,211,111,.12);flex:none;margin-top:5px;}
        .status-label{margin:0 0 4px;color:#edf5fb;font-size:12px;font-weight:700;letter-spacing:0;text-transform:none;}
        .status-value{font-size:13px;font-weight:700;color:#75eee5;}
        .status-card-wide .status-value{font-size:12px;font-weight:600;line-height:1.35;color:#dce8f1;}
        .status-note{font-size:12px;line-height:1.35;}
        .status-card .outline-button,.status-card form{margin-top:auto;}
        .status-card-actions{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:auto;}
        .quick-start-actions{grid-template-columns:repeat(auto-fit,minmax(180px,1fr));}
        .status-card-actions form{display:block;margin:0;}
        .status-card-actions button{width:100%;min-width:0;margin-top:0;}
        .overview-service-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:10px;}
        .service-panel,.overview-key-panel{padding:11px;border-radius:9px;background:linear-gradient(145deg,rgba(20,31,43,.94),rgba(15,23,32,.94));}
        .service-panel h3{font-size:14px;line-height:1.22;margin-bottom:8px;}
        .command-grid{gap:7px;margin-top:0;}
        .command-grid button{height:var(--control-height);min-height:var(--control-height);justify-content:center;}
        .overview-key-panel{position:relative;z-index:1;margin-top:10px;}
        .overview-key-panel .key-editor-form{display:grid;gap:7px;}
        .overview-key-panel .form-actions{gap:8px;}
        .protocol-tabs,.list-tabs{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));overflow:hidden;}
        .protocol-tabs .seg-tab,.list-tabs .seg-tab{min-width:0;}
        .segmented,.subtabs,.pool-table-wrap{border-color:rgba(91,124,150,.34);border-radius:var(--radius-panel);background:rgba(11,17,25,.34);overflow:hidden;}
        .seg-tab,.subtab{height:var(--control-height);min-height:var(--control-height);color:#c7d2df;padding:0 10px;font-size:12px;border-radius:0;}
        .seg-tab.active,.subtab.active{background:rgba(48,191,181,.14);color:#94f3ec;}
        .key-status-wrap{max-width:none;flex:none;gap:6px;align-items:center;}
        .key-status-icons{order:2;gap:5px;}
        .key-status-badge{order:1;max-width:none;padding:5px 9px;font-size:11px;line-height:1.15;white-space:nowrap;text-align:left;}
        .protocol-workspace,.list-workspace{padding:10px;}
        .workspace-head{margin-bottom:8px;}
        .field-label{color:#9fb0c8;letter-spacing:.08em;font-size:11px;}
        .form-actions button{min-width:140px;}
        .protocol-subview.active{gap:10px;}
        .protocol-subview-import.active{grid-template-columns:minmax(0,1.2fr) minmax(280px,.8fr);align-items:start;}
        .protocol-subview-import .pool-add-form,.protocol-subview-import .pool-subscribe-form{padding:9px;border:1px solid rgba(91,124,150,.28);border-radius:9px;background:rgba(255,255,255,.025);}
        .protocol-subview-import .pool-add-form{grid-template-columns:minmax(0,1fr) auto;align-items:end;}
        .protocol-subview-import .pool-add-form .field-label{grid-column:1 / -1;}
        .protocol-subview-import .pool-add-form textarea{min-height:68px;}
        .protocol-subview-import .pool-add-form button{justify-self:start;min-width:150px;}
        .protocol-subview-import .pool-subscribe-form{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:7px;align-items:end;}
        .protocol-subview-import .pool-subscribe-form .field-label{grid-column:1 / -1;}
        .protocol-subview-import .pool-subscribe-form input{min-width:0;}
        .protocol-subview-import .pool-subscribe-form button{white-space:nowrap;}
        .protocol-subview-check > form{justify-self:start;}
        .protocol-subview-check > form button{min-width:180px;}
        .pool-table{font-size:11px;}
        .pool-table th,.pool-table td{padding:4px 6px;line-height:1.22;}
        .pool-table th{font-size:10px;letter-spacing:.06em;}
        .pool-icon-head{text-align:center;letter-spacing:0;}
        .pool-custom-head{text-align:center;}
        .pool-icon-head img{width:16px!important;height:16px!important;margin:0;vertical-align:middle;}
        .pool-key-cell{min-width:220px;}
        .pool-key-cell .pool-apply-form{display:inline-block;max-width:100%;vertical-align:middle;}
        .pool-apply-btn{min-height:0;height:auto;padding:0;font-size:11px;font-weight:600;line-height:1.22;}
        .pool-hash{display:none;}
        .pool-service-cell{width:32px;}
        .pool-custom-cell{width:96px;}
        .pool-custom-cell,.pool-service-cell{text-align:center;}
        .pool-table:not(.has-custom-checks) .pool-custom-head,
        .pool-table:not(.has-custom-checks) .pool-custom-cell{display:none;}
        .pool-table:not(.has-custom-checks) .pool-col-custom{display:none;width:0!important;}
        .pool-custom-empty{color:var(--muted);font-size:10px;}
        .custom-service-badge{display:inline-flex;align-items:center;justify-content:center;min-width:24px;height:18px;margin:1px 2px 1px 0;padding:0 5px;border-radius:6px;border:1px solid rgba(91,124,150,.42);background:rgba(111,127,146,.15);color:#b9c6d3;font-size:10px;font-weight:800;line-height:1;letter-spacing:0;vertical-align:middle;}
        .custom-service-slot{display:inline-flex;align-items:center;justify-content:center;width:32px;min-width:32px;height:18px;margin:0;vertical-align:middle;}
        .service-icon-img{width:18px!important;height:18px!important;object-fit:contain;border-radius:5px;vertical-align:middle;}
        .custom-service-slot .service-icon-img{width:18px!important;height:18px!important;}
        .key-status-icons .service-icon-img{width:20px!important;height:20px!important;}
        .service-probe-mark{display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:5px;border:1px solid rgba(91,124,150,.34);font-size:11px;font-weight:800;line-height:1;}
        .service-probe-fail{color:var(--muted);background:transparent;border-color:transparent;}
        .service-probe-unknown{color:#9fb0c8;background:rgba(91,124,150,.12);}
        .custom-service-ok{background:rgba(31,122,106,.18);border-color:rgba(78,216,205,.38);color:#95f3ec;}
        .custom-service-fail{background:transparent;border-color:transparent;color:var(--muted);}
        .custom-service-unknown,.custom-service-neutral{background:rgba(91,124,150,.14);border-color:rgba(91,124,150,.34);color:#c7d2df;}
        .pool-custom-cell .custom-service-slot{background:transparent!important;border-color:transparent!important;}
        .custom-check-card{display:grid;gap:8px;padding:9px;border-radius:9px;border:1px solid rgba(91,124,150,.34);background:rgba(11,17,25,.36);}
        .custom-check-head{display:flex;justify-content:space-between;gap:10px;align-items:center;}
        .custom-check-head strong{display:block;font-size:13px;color:#edf5fb;}
        .custom-check-head small{display:block;margin-top:2px;color:#9fb0c8;font-size:11px;line-height:1.25;}
        .service-preset-grid{display:flex;flex-wrap:wrap;gap:6px;align-items:stretch;}
        .service-preset-grid form{margin:0;flex:0 0 86px;min-width:0;}
        .service-preset-btn{width:86px;min-width:0;display:flex;align-items:center;justify-content:center;gap:4px;height:var(--control-height);min-height:var(--control-height);padding:0 5px;background:rgba(34,67,73,.28);}
        .service-preset-btn span:last-child{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:10.5px;}
        .service-preset-btn:disabled{opacity:.55;cursor:default;}
        .preset-icon{display:inline-flex;align-items:center;justify-content:center;flex:none;width:18px;height:18px;border-radius:6px;overflow:hidden;}
        .preset-icon img{width:18px!important;height:18px!important;display:block;}
        .custom-check-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:6px;}
        .custom-check-empty{padding:8px;border:1px dashed rgba(91,124,150,.34);border-radius:8px;color:#9fb0c8;font-size:12px;text-align:center;}
        .custom-check-item{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:6px;align-items:center;min-height:34px;padding:5px 6px;border-radius:8px;background:rgba(255,255,255,.03);border:1px solid rgba(91,124,150,.28);}
        .custom-check-copy{min-width:0;display:grid;gap:1px;}
        .custom-check-copy strong{font-size:12px;font-weight:700;color:#edf5fb;}
        .custom-check-copy small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#9fb0c8;font-size:10px;}
        .custom-check-form{display:grid;grid-template-columns:minmax(120px,.55fr) minmax(180px,1fr) auto auto;gap:7px;align-items:center;}
        .custom-check-form button{justify-self:start;white-space:nowrap;}
        .pool-checked-cell{width:74px;font-size:10px;}
        .pool-actions-cell{width:78px;}
        .pool-delete-btn{min-height:20px;height:auto;padding:1px 6px;font-size:10px;line-height:1.15;}
        .pool-service-cell img{width:16px!important;height:16px!important;}
        .pool-table{width:100%;table-layout:fixed;}
        .pool-col-status{width:0!important;visibility:collapse;}
        .pool-col-icon{width:32px;}
        .pool-col-checked{width:74px;}
        .pool-col-actions{width:78px;}
        .pool-table th,.pool-table td{vertical-align:middle;}
        .pool-status-head,.pool-active-cell{display:none;}
        .pool-table .pool-icon-head,.pool-table .pool-service-cell,.pool-table .pool-custom-head,.pool-table .pool-custom-cell,.pool-table .pool-checked-head,.pool-table .pool-checked-cell,.pool-table .pool-actions-head,.pool-table .pool-actions-cell{text-align:center;}
        .pool-service-cell,.pool-custom-cell{line-height:1;}
        .pool-icon-head,.pool-service-cell,.pool-custom-head,.pool-custom-cell{padding-left:0!important;padding-right:0!important;}
        .pool-icon-head img,.pool-service-cell img,.pool-service-cell .service-probe-mark,.pool-custom-cell .service-probe-mark,.pool-custom-cell .custom-service-slot,.pool-custom-head .custom-service-slot{display:inline-flex;margin-left:auto;margin-right:auto;vertical-align:middle;}
        .pool-custom-head .service-icon-img,.pool-custom-cell .service-icon-img{width:16px!important;height:16px!important;}
        .pool-service-cell .service-probe-mark,.pool-custom-cell .service-probe-mark{width:16px;height:16px;font-size:10px;}
        .pool-custom-cell,.pool-custom-head{white-space:nowrap;overflow:hidden;}
        .pool-key-cell{overflow:hidden;}
        .pool-actions-cell form{display:flex;justify-content:center;}
        .pool-table-wrap{max-height:min(54vh,460px);overflow-y:auto;overflow-x:hidden;}
        .protocol-subview[data-subview="pool"].active{min-height:0;grid-template-rows:auto minmax(0,1fr);}
        .protocol-subview[data-subview="pool"].active .pool-table-wrap{min-height:0;}
        .pool-table-wrap,.protocol-subview-import.active,.list-editor-form textarea,.key-editor-form textarea,textarea{scrollbar-gutter:stable;scrollbar-color:var(--scrollbar-thumb) var(--scrollbar-track);scrollbar-width:thin;}
        .app-shell{max-width:1600px;}
        .protocol-workspace.active{padding:9px;}
        .protocol-workspace .workspace-head{align-items:center;margin-bottom:6px;}
        .protocol-workspace .workspace-head h2{margin:0;font-size:18px;}
        .protocol-workspace .workspace-head .eyebrow{margin-bottom:5px;}
        .key-status-note{margin:3px 0 0;font-size:12px;line-height:1.25;}
        .subtabs{margin-bottom:8px;}
        .subtab{height:var(--control-height);min-height:var(--control-height);padding:0 8px;}
        .protocol-subview.active{gap:8px;}
        .pool-toolbar{margin-bottom:7px;}
        .pool-toolbar form{margin:0;}
        .pool-toolbar button,.pool-clear-btn{height:var(--control-height);min-height:var(--control-height);padding:0 12px;line-height:1.15;}
        .pool-table-wrap{scrollbar-gutter:stable;max-height:min(58vh,500px);}
        .pool-table th,.pool-table td{padding:4px 5px;}
        .pool-col-actions{width:96px;}
        .pool-actions-head,.pool-actions-cell{width:96px;}
        .pool-actions-head{white-space:nowrap;font-size:9px;letter-spacing:.02em;}
        .pool-delete-btn{height:22px;min-height:22px;padding:2px 7px;font-size:10px;line-height:1;white-space:nowrap;}
        .pool-checked-cell,.pool-checked-head{white-space:nowrap;}
        .protocol-subview-import.active{grid-template-columns:minmax(0,1fr) minmax(420px,.72fr);gap:8px;align-items:stretch;}
        .protocol-subview-import .pool-add-form,.protocol-subview-import .pool-subscribe-form{height:106px;min-height:0;padding:8px;align-self:stretch;}
        .protocol-subview-import .pool-add-form{display:grid;grid-template-columns:minmax(0,1fr) 150px;grid-template-rows:auto 66px;gap:7px;align-items:stretch;align-content:start;}
        .protocol-subview-import .pool-add-form .field-label{grid-column:1 / -1;margin:0;}
        .protocol-subview-import .pool-add-form textarea{grid-column:1;min-height:66px;height:66px;resize:vertical;}
        .protocol-subview-import .pool-add-form button{grid-column:2;align-self:end;justify-self:stretch;width:100%;min-width:0;height:var(--control-height);min-height:var(--control-height);margin-top:0;}
        .protocol-subview-import .pool-subscribe-form{display:grid;grid-template-columns:minmax(0,1fr) 190px;grid-template-rows:auto 66px;gap:7px;align-content:start;align-items:end;}
        .protocol-subview-import .pool-subscribe-form .field-label{grid-column:1 / -1;margin:0;}
        .protocol-subview-import .pool-subscribe-form input{height:var(--control-height);min-height:var(--control-height);align-self:end;}
        .protocol-subview-import .pool-subscribe-form button{height:var(--control-height);min-height:var(--control-height);width:100%;padding:0 10px;white-space:nowrap;align-self:end;}
        @media (min-width: 1024px){
            html,body{height:100%;overflow:hidden;}
            body{padding:8px;}
            .app-shell{height:calc(100vh - 16px);display:flex;flex-direction:column;min-height:0;}
            .topbar{position:static;flex:none;margin-bottom:8px;}
            .workspace-layout{flex:1;min-height:0;align-items:stretch;}
            .side-nav{position:static;align-self:start;}
            .app-main{height:100%;min-height:0;overflow:hidden;}
            .app-view.active{height:100%;min-height:0;overflow:hidden;}
            .app-view[data-view="status"].active{display:grid;grid-template-rows:auto auto auto auto;gap:8px;align-content:start;}
            .app-view[data-view="keys"].active,.app-view[data-view="lists"].active{display:grid;grid-template-rows:auto auto minmax(0,1fr);gap:8px;}
            .view-head,.segmented,.status-dashboard,.overview-service-grid{margin-bottom:0;}
            .view-head{padding:9px 12px;}
            .status-dashboard{gap:8px;}
            .status-card{min-height:68px;padding:9px;}
            .overview-service-grid{gap:8px;margin-top:0;}
            .service-panel,.overview-key-panel{padding:9px;}
            .overview-key-panel{min-height:0;overflow:hidden;align-self:start;}
            .overview-key-panel .workspace-head{display:none;}
            .overview-key-panel .key-editor-form{display:grid;grid-template-columns:minmax(0,1fr) minmax(480px,.42fr);grid-template-rows:auto 44px;gap:6px 10px;align-items:stretch;}
            .overview-key-panel .key-editor-form .field-label{grid-column:1 / -1;margin:0;line-height:1.1;}
            .overview-key-panel textarea{grid-column:1;grid-row:2;height:44px;min-height:44px;max-height:44px;resize:none;}
            .overview-key-panel .form-actions{grid-column:2;grid-row:2;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;align-self:stretch;align-items:stretch;margin:0;}
            .overview-key-panel .form-actions button{width:100%;min-width:0;height:var(--control-height);min-height:var(--control-height);padding:0 10px;border-radius:8px;font-size:12px;font-weight:700;}
            .protocol-panels,.list-panels{min-height:0;overflow:hidden;}
            .protocol-workspace.active{height:100%;min-height:0;display:grid;grid-template-rows:auto auto minmax(0,1fr);overflow:hidden;}
            .protocol-subview.active{min-height:0;overflow:hidden;}
            .protocol-subview[data-subview="pool"].active{display:grid;grid-template-rows:auto minmax(0,1fr);}
            .pool-table-wrap{max-height:none;height:100%;min-height:0;}
            .key-editor-form textarea[data-key-textarea]{height:168px;min-height:168px;max-height:168px;}
            .protocol-subview-import.active{overflow:auto;}
            .list-workspace.active{height:100%;min-height:0;display:grid;grid-template-rows:auto minmax(0,1fr);overflow:hidden;}
            .list-editor-form{height:100%;min-height:0;display:grid;grid-template-rows:minmax(0,1fr) auto auto;gap:8px;align-content:stretch;}
            .list-editor-form textarea{height:100%;min-height:0;resize:none;}
            .list-editor-form .form-actions{height:auto;min-height:0;align-self:end;align-items:center;align-content:center;}
            .list-editor-form .form-actions button{height:var(--control-height);min-height:var(--control-height);flex:0 0 auto;align-self:center;}
        }
        @media (min-width: 1024px){
            .protocol-workspace.active{height:auto;min-height:0;display:block;overflow:visible;}
            .protocol-workspace.active:has(.protocol-subview[data-subview="pool"].active){height:100%;display:grid;grid-template-rows:auto auto minmax(0,1fr);overflow:hidden;}
            .protocol-workspace.active:has(.protocol-subview[data-subview="pool"].active) .protocol-subview[data-subview="pool"].active{min-height:0;display:grid;grid-template-rows:auto minmax(0,1fr);overflow:hidden;}
            .protocol-workspace.active:has(.protocol-subview[data-subview="subscription"].active),
            .protocol-workspace.active:has(.protocol-subview[data-subview="key"].active),
            .protocol-workspace.active:has(.protocol-subview[data-subview="check"].active){align-self:start;}
            .protocol-subview-import.active{overflow:visible;align-self:start;}
        }
        .mobile-nav{display:none;}
        .confirm-backdrop{position:fixed;inset:0;z-index:100;display:flex;align-items:center;justify-content:center;padding:18px;background:rgba(2,6,23,.72);}
        .confirm-backdrop.hidden{display:none;}
        .confirm-card{width:min(420px,100%);padding:20px;border:1px solid var(--border);border-radius:8px;background:var(--surface);box-shadow:0 24px 70px rgba(0,0,0,.42);}
        .confirm-card h2{margin:0 0 10px;font-size:22px;}
        .confirm-card p{margin:0 0 18px;color:var(--muted);}
        .confirm-actions{display:grid;grid-template-columns:1fr 1fr;gap:10px;}
        @media (max-width: 760px){
            :root{--control-height:38px;}
            html,body{max-width:100%;overflow-x:hidden;}
            body{padding:10px 10px calc(128px + env(safe-area-inset-bottom, 0px));scroll-padding-bottom:calc(128px + env(safe-area-inset-bottom, 0px));}
                        .hero{padding:16px;border-radius:20px;}
            .topbar{position:static;align-items:stretch;flex-direction:column;padding:10px;}
            .app-shell,.topbar,.app-main,.app-view,.view-head,.status-card,.service-panel,.overview-key-panel,.mobile-nav{box-sizing:border-box;max-width:100%;}
            .topbar-actions{width:100%;display:grid;grid-template-columns:1fr 1fr;justify-content:stretch;gap:8px;}
            .app-caption{display:grid;gap:2px;width:100%;max-width:calc(100vw - 32px);min-width:0;white-space:normal;overflow-wrap:anywhere;word-break:break-word;}
            .app-caption strong,.app-branch{max-width:100%;min-width:0;white-space:normal;overflow-wrap:anywhere;word-break:break-word;}
            .app-caption strong{max-width:28ch;font-size:14px;line-height:1.18;}
            .section-subtitle,.status-note,.status-value{overflow-wrap:anywhere;}
            .app-caption,.api-pill{grid-column:1 / -1;}
            .theme-control{width:100%;}
            .theme-control .theme-picker{min-width:0;width:100%;}
            .api-pill,.theme-toggle,.mode-toggle,.version-badge{width:100%;justify-content:center;max-width:none;text-align:center;}
            .theme-toggle,.mode-toggle{min-width:0;gap:5px;padding-left:6px;padding-right:6px;font-size:12px;}
            .theme-toggle span,.mode-toggle span{min-width:0;}
            .theme-toggle span:last-child,.mode-toggle span:last-child{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
            .version-badge{align-self:stretch;min-height:34px;font-size:10px;}
            .api-pill{justify-content:start;text-align:left;}
            .workspace-layout{display:block;}
            .side-nav{display:none;}
            .app-main{padding-bottom:calc(126px + env(safe-area-inset-bottom, 0px));}
            .mobile-nav{position:fixed;left:10px;right:10px;bottom:calc(10px + env(safe-area-inset-bottom, 0px));z-index:50;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:4px;padding:6px;border:1px solid rgba(91,124,150,.34);border-radius:var(--radius-panel);background:rgba(12,18,26,.96);box-shadow:0 14px 34px rgba(0,0,0,.34);}
            .mobile-nav .nav-item{justify-content:center;flex-direction:column;gap:3px;min-height:50px;font-size:11px;padding:6px;border-radius:var(--radius-control);}
            .view-head{padding:14px;border-radius:10px;}
            .view-head h2{font-size:20px;}
            .status-dashboard,.overview-service-grid{grid-template-columns:1fr;}
            .status-card-actions{grid-template-columns:1fr;}
            .status-card-wide{grid-column:auto;}
            .status-card{min-height:0;padding:12px;}
            .status-card-top{gap:10px;}
            .card-icon{width:34px;height:34px;font-size:18px;}
            .status-label{font-size:13px;}
            .status-value{font-size:15px;}
            .status-card-wide .status-value{font-size:13px;line-height:1.4;}
            .segmented{scroll-snap-type:x mandatory;}
            .seg-tab{min-width:96px;scroll-snap-align:start;}
            .protocol-tabs,.list-tabs{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));overflow:hidden;scroll-snap-type:none;border-radius:var(--radius-panel);}
            .protocol-tabs .seg-tab,.list-tabs .seg-tab{min-width:0;border-right:1px solid var(--border);border-bottom:1px solid var(--border);white-space:normal;}
            .protocol-tabs .seg-tab:nth-child(2n),.list-tabs .seg-tab:nth-child(2n){border-right:none;}
            .protocol-tabs .seg-tab:last-child,.list-tabs .seg-tab:last-child{grid-column:1 / -1;border-right:none;border-bottom:none;}
            .protocol-tabs .seg-tab:first-child,.list-tabs .seg-tab:first-child{border-top-left-radius:calc(var(--radius-panel) - 1px);}
            .protocol-tabs .seg-tab:nth-child(2),.list-tabs .seg-tab:nth-child(2){border-top-right-radius:calc(var(--radius-panel) - 1px);}
            .protocol-tabs .seg-tab:last-child,.list-tabs .seg-tab:last-child{border-bottom-left-radius:calc(var(--radius-panel) - 1px);border-bottom-right-radius:calc(var(--radius-panel) - 1px);}
            .protocol-workspace{padding:9px;}
            .protocol-workspace .workspace-head{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:8px;margin-bottom:7px;}
            .protocol-workspace .workspace-head .eyebrow{display:none;}
            .protocol-workspace .workspace-head h2{font-size:18px;margin:0;}
            .key-status-note{display:none;}
            .key-status-wrap{max-width:100%;margin-top:0;}
            .key-status-badge{font-size:10px;padding:4px 7px;}
            .key-status-icons .service-icon-img{width:18px!important;height:18px!important;}
            .subtabs{grid-template-columns:repeat(2,minmax(0,1fr));}
            .subtab{height:var(--control-height);min-height:var(--control-height);padding:0 6px;}
            .key-editor-form textarea[data-key-textarea]{min-height:132px;max-height:34vh;resize:vertical;font-size:12px;line-height:1.32;}
            .overview-key-panel .key-editor-form{display:grid;gap:8px;}
            .overview-key-panel textarea{min-height:96px;max-height:24vh;resize:vertical;}
            .overview-key-panel .form-actions{display:grid;grid-template-columns:1fr;gap:8px;margin-bottom:18px;}
            .overview-key-panel .form-actions button{width:100%;min-width:0;}
            .key-editor-form .form-actions{margin-bottom:20px;}
            .key-editor-form .form-actions button{width:100%;}
            .protocol-subview-import.active{grid-template-columns:1fr;}
            .protocol-subview-import .pool-add-form{grid-template-columns:1fr;}
            .protocol-subview-import .pool-add-form .field-label{grid-column:auto;}
            .protocol-subview-import .pool-subscribe-form{grid-template-columns:minmax(0,1fr) auto;}
            .pool-toolbar{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-bottom:8px;}
            .pool-toolbar button{width:100%;}
            .social-list-actions{grid-template-columns:1fr;}
            .pool-table-wrap{overflow-x:hidden;}
            .pool-table{display:block;width:100%;min-width:0;table-layout:auto;font-size:10px;border-collapse:separate;border-spacing:0;}
            .pool-table colgroup{display:none;}
            .pool-table thead,.pool-table tbody{display:block;width:100%;}
            .pool-table tr{display:grid;grid-template-columns:minmax(0,1fr) 28px 28px 32px;align-items:stretch;width:100%;min-height:30px;border-bottom:1px solid var(--border);}
            .pool-table.has-custom-checks tr{grid-template-columns:minmax(0,1fr) 28px 28px var(--custom-col-mobile, 28px) 32px;}
            .pool-table tr:last-child{border-bottom:none;}
            .pool-table th,.pool-table td{display:flex;align-items:center;min-width:0;min-height:30px;height:100%;padding:4px 3px;border-bottom:none;}
            .pool-table .pool-status-head,.pool-table .pool-active-cell,.pool-table .pool-checked-head,.pool-table .pool-checked-cell{display:none;}
            .pool-key-head,.pool-key-cell{width:auto!important;min-width:0;}
            .pool-key-head,.pool-key-cell{justify-content:flex-start;}
            .pool-key-cell .pool-apply-form{display:block;max-width:none;}
            .pool-row-active .pool-key-cell{box-shadow:inset 3px 0 0 var(--accent);background:rgba(48,191,181,.12);}
            .pool-row-active .pool-apply-btn{color:#92fff2;}
            .pool-mobile-active{display:none;margin:2px 0 0 0;width:max-content;padding:1px 5px;border-radius:5px;background:rgba(48,191,181,.18);border:1px solid rgba(48,191,181,.35);color:#9ff7ef;font-size:8px;font-weight:900;letter-spacing:.06em;text-transform:uppercase;line-height:1.2;}
            .pool-row-active .pool-mobile-active{display:inline-flex;}
            .pool-apply-btn{display:block;width:100%;font-size:10.5px;line-height:1.18;text-align:left;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
            .pool-hash{display:none;}
            .pool-service-cell,.pool-icon-head,.pool-custom-cell,.pool-custom-head,.pool-actions-head,.pool-actions-cell{width:auto!important;padding-left:2px!important;padding-right:2px!important;text-align:center;}
            .pool-service-cell,.pool-icon-head,.pool-custom-cell,.pool-custom-head,.pool-actions-head,.pool-actions-cell{justify-content:center;}
            .custom-service-slot{width:28px;min-width:28px;height:15px;margin:0;}
            .custom-service-slot .service-icon-img,.pool-service-cell img,.pool-icon-head img{width:14px!important;height:14px!important;}
            .pool-service-cell .service-probe-mark,.pool-custom-cell .service-probe-mark{width:14px;height:14px;font-size:9px;}
            .pool-actions-head,.pool-actions-cell{width:32px;padding-left:2px!important;padding-right:2px!important;text-align:center;}
            .pool-table .pool-actions-head{font-size:0;}
            .pool-table .pool-actions-head::after{content:"×";font-size:11px;}
            .pool-actions-cell form{display:flex;justify-content:center;}
            .pool-actions-cell .pool-delete-btn{width:22px;height:22px;min-height:22px;padding:0;font-size:0;border-radius:6px;}
            .pool-actions-cell .pool-delete-btn::before{content:"×";font-size:13px;line-height:1;}
            .service-preset-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:5px;}
            .service-preset-grid form{min-width:0;}
            .service-preset-btn{width:100%;min-width:0;gap:3px;padding:0 3px;}
            .service-preset-btn span:last-child{font-size:10px;}
            .custom-check-list{grid-template-columns:1fr;}
            .custom-check-form{grid-template-columns:minmax(0,.9fr) minmax(0,1.1fr);align-items:stretch;}
            .custom-check-form input[type="text"]{grid-column:1 / -1;}
            .custom-check-form button{width:100%;height:var(--control-height);min-height:var(--control-height);justify-self:stretch;display:flex;align-items:center;justify-content:center;white-space:normal;line-height:1.15;}
            .service-groups{grid-template-columns:1fr;}
            .form-actions{display:grid;grid-template-columns:1fr;}
            .hero-row{flex-direction:column;align-items:stretch;}
            .hero-actions{width:100%;justify-content:stretch;}
            .hero-status-header{flex-direction:column;align-items:flex-start;}
            .traffic-inline{justify-content:flex-start;}
            .theme-toggle,.mode-toggle{justify-content:center;}
            .hero-popover{position:static;min-width:0;width:100%;}
            .app-mode-control .app-mode-picker{position:static;min-width:0;width:100%;margin-top:8px;}
            .mode-picker-form{gap:8px;}
            .mode-choice-grid{gap:6px;}
            .mode-choice{height:var(--control-height);min-height:var(--control-height);padding:0 5px;font-size:12px;line-height:1.12;white-space:normal;overflow-wrap:anywhere;word-break:normal;}
            .mode-choice span{display:block;min-width:0;max-width:100%;overflow-wrap:anywhere;}
            .layout{grid-template-columns:1fr;gap:12px;}
                        .command-grid{grid-template-columns:1fr;}
            .status-grid{grid-template-columns:1fr;}
                        .panel{padding:12px;border-radius:10px;}
            .pool-subscribe-row{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:stretch;}
            .pool-subscribe-form{display:contents;}
            .pool-subscribe-form input{grid-column:1 / -1;}
            .protocol-subview-import .pool-subscribe-form{display:grid;}
            .protocol-subview-import .pool-subscribe-form input{grid-column:auto;}
            .command-grid{grid-template-columns:1fr 1fr;gap:10px;}
            .command-grid.service-command-grid{grid-template-columns:1fr;}
            .command-grid button{height:var(--control-height);min-height:var(--control-height);font-size:13px;}
            button,input,textarea,select{font-size:13px;}
            .custom-check-form button:first-of-type{white-space:nowrap;font-size:12px;padding-left:6px;padding-right:6px;}
        }
        @media (max-width: 430px){
            .topbar-actions{grid-template-columns:1fr;}
            .app-caption,.api-pill{grid-column:auto;}
            .command-grid{grid-template-columns:1fr;}
            .command-grid.service-command-grid{grid-template-columns:1fr;}
            .status-card-top{align-items:flex-start;}
            .api-pill{font-size:12px;}
            .mode-choice{font-size:11px;padding:0 4px;}
        }
        @media (max-width: 560px){
            .topbar-actions{grid-template-columns:1fr;}
            .app-caption,.api-pill{grid-column:auto;}
        }
        /* Light theme final pass. Keep it after compact/mobile rules so no dark surfaces leak through. */
        [data-theme="light"]{
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
        }
        [data-theme="light"] body{color:var(--text);background:linear-gradient(145deg,#f8fbff 0%,#edf3f8 48%,#e7eef5 100%);}
        [data-theme="light"] .topbar,
        [data-theme="light"] .side-nav,
        [data-theme="light"] .view-head,
        [data-theme="light"] .panel,
        [data-theme="light"] .protocol-workspace,
        [data-theme="light"] .list-workspace,
        [data-theme="light"] .confirm-card,
        [data-theme="light"] .service-panel,
        [data-theme="light"] .overview-key-panel,
        [data-theme="light"] .status-card{background:rgba(255,255,255,.92);border-color:var(--border);box-shadow:var(--shadow);backdrop-filter:none;}
        [data-theme="light"] .service-panel,
        [data-theme="light"] .overview-key-panel,
        [data-theme="light"] .status-card{background:linear-gradient(145deg,rgba(255,255,255,.96),rgba(241,246,251,.96));}
        [data-theme="light"] h1,
        [data-theme="light"] h2,
        [data-theme="light"] h3,
        [data-theme="light"] .app-caption,
        [data-theme="light"] .app-caption strong,
        [data-theme="light"] .status-label,
        [data-theme="light"] .custom-check-head strong,
        [data-theme="light"] .custom-check-copy strong{color:var(--text);}
        [data-theme="light"] .brand p,
        [data-theme="light"] .section-subtitle,
        [data-theme="light"] .status-note,
        [data-theme="light"] .key-status-note,
        [data-theme="light"] .field-label,
        [data-theme="light"] .custom-check-head small,
        [data-theme="light"] .custom-check-copy small,
        [data-theme="light"] .custom-check-empty,
        [data-theme="light"] .pool-hash,
        [data-theme="light"] .pool-checked-cell{color:var(--muted);}
        [data-theme="light"] .status-value,
        [data-theme="light"] .status-card-wide .status-value{color:#1f6f62;}
        [data-theme="light"] .api-pill,
        [data-theme="light"] .mode-toggle,
        [data-theme="light"] .theme-toggle,
        [data-theme="light"] .hero-chip,
        [data-theme="light"] .traffic-chip{background:rgba(255,255,255,.84);border-color:var(--border);color:var(--text);}
        [data-theme="light"] .api-pill{color:#1f564f;}
        [data-theme="light"] .api-pill::before,
        [data-theme="light"] .card-icon{background-color:rgba(31,122,106,.12);border-color:rgba(31,122,106,.24);color:#1f7a6a;}
        [data-theme="light"] .hero-popover{background:linear-gradient(180deg,rgba(255,255,255,.98),rgba(241,246,251,.96));border-color:var(--border);}
        [data-theme="light"] .mode-choice{background:rgba(31,122,106,.08);border-color:rgba(31,122,106,.28);color:#1f6258;}
        [data-theme="light"] .mode-choice.active{background:rgba(31,122,106,.13);border-color:rgba(31,122,106,.42);color:#174f48;}
        [data-theme="light"] .mode-choice:hover{background:rgba(31,122,106,.13);border-color:rgba(31,122,106,.42);}
        [data-theme="light"] button{border-color:rgba(31,122,106,.28);background:rgba(31,122,106,.08);color:#1f6258;box-shadow:none;}
        [data-theme="light"] button:hover{border-color:rgba(31,122,106,.42);background:rgba(31,122,106,.13);color:#174f48;}
        [data-theme="light"] button[type="submit"]:not(.danger):not(.pool-apply-btn):not(.pool-delete-btn){background:rgba(31,122,106,.08);border-color:rgba(31,122,106,.28);color:#1f6258;}
        [data-theme="light"] button[type="submit"]:not(.danger):not(.pool-apply-btn):not(.pool-delete-btn):hover{background:rgba(31,122,106,.13);border-color:rgba(31,122,106,.42);color:#174f48;}
        [data-theme="light"] .secondary-button,
        [data-theme="light"] .success-button,
        [data-theme="light"] .outline-button,
        [data-theme="light"] .service-preset-btn{background:rgba(31,122,106,.08);border-color:rgba(31,122,106,.28);color:#1f6258;}
        [data-theme="light"] .mode-toggle,
        [data-theme="light"] .theme-toggle{background:rgba(31,122,106,.08);border-color:rgba(31,122,106,.28);color:#1f6258;}
        [data-theme="light"] button.danger{background:#f7dedb;border-color:#d79891;color:#8e2f28;}
        [data-theme="light"] button.danger:hover{background:#f1cbc6;border-color:#c77d75;}
        [data-theme="light"] .success-button{background:rgba(31,122,106,.08);border-color:rgba(31,122,106,.28);color:#1f6258;}
        [data-theme="light"] input,
        [data-theme="light"] textarea,
        [data-theme="light"] select{background:#fff;border-color:#c8d5e1;color:var(--text);}
        [data-theme="light"] input::placeholder,
        [data-theme="light"] textarea::placeholder{color:#7d8b9b;}
        [data-theme="light"] input:focus,
        [data-theme="light"] textarea:focus,
        [data-theme="light"] select:focus{border-color:#1f7a6a;box-shadow:0 0 0 3px rgba(31,122,106,.12);}
        [data-theme="light"] .segmented,
        [data-theme="light"] .subtabs,
        [data-theme="light"] .pool-table-wrap,
        [data-theme="light"] .protocol-subview-import .pool-add-form,
        [data-theme="light"] .protocol-subview-import .pool-subscribe-form,
        [data-theme="light"] .custom-check-card{background:rgba(255,255,255,.78);border-color:var(--border);}
        [data-theme="light"] .seg-tab,
        [data-theme="light"] .subtab,
        [data-theme="light"] .nav-item{color:#536274;}
        [data-theme="light"] .seg-tab.active,
        [data-theme="light"] .subtab.active,
        [data-theme="light"] .nav-item.active{background:rgba(31,122,106,.12);border-color:rgba(31,122,106,.3);color:#1f6258;}
        [data-theme="light"] .seg-tab:hover,
        [data-theme="light"] .subtab:hover,
        [data-theme="light"] .nav-item:hover{background:rgba(31,122,106,.06);}
        [data-theme="light"] .tab-count{background:#e0e9f2;color:#233144;}
        [data-theme="light"] .pool-table th{background:#eef3f8;color:#536274;}
        [data-theme="light"] .pool-table th,
        [data-theme="light"] .pool-table td{border-bottom-color:#d6e0ea;}
        [data-theme="light"] .pool-row-active{background:rgba(31,122,106,.1);}
        [data-theme="light"] .pool-active-cell,
        [data-theme="light"] .pool-apply-btn{color:#172033;}
        [data-theme="light"] .pool-apply-btn:hover{color:#1f7a6a;}
        [data-theme="light"] .pool-delete-btn{background:#f5deda;color:#92352d;border-color:#e3aaa4;}
        [data-theme="light"] .pool-delete-btn:hover{background:#edc8c2;}
        [data-theme="light"] .key-status-ok,
        [data-theme="light"] .custom-service-ok{background:rgba(31,122,106,.12);border-color:rgba(31,122,106,.3);color:#1f6258;}
        [data-theme="light"] .key-status-warn{background:#fff1d7;border-color:#deb36b;color:#875b1f;}
        [data-theme="light"] .key-status-fail,
        [data-theme="light"] .custom-service-fail{background:transparent;border-color:transparent;color:#526173;}
        [data-theme="light"] .key-status-empty,
        [data-theme="light"] .custom-service-unknown,
        [data-theme="light"] .custom-service-neutral,
        [data-theme="light"] .service-probe-unknown{background:#edf3f8;border-color:#c8d5e1;color:#536274;}
        [data-theme="light"] .service-probe-fail{background:#f7dedb;border-color:#d79891;color:#92352d;}
        [data-theme="light"] .custom-check-item{background:rgba(255,255,255,.82);border-color:#d6e0ea;}
        [data-theme="light"] .custom-check-empty{border-color:#c8d5e1;background:rgba(255,255,255,.55);}
        [data-theme="light"] .notice-result{background:var(--warn-bg);border-color:var(--warn-border);color:#6f4b18;}
        [data-theme="light"] .notice-status{background:var(--success-bg);border-color:var(--success-border);color:#174f3b;}
        [data-theme="light"] .notice strong,
        [data-theme="light"] .log-output{color:inherit;}
        [data-theme="light"] .command-progress-block{background:rgba(255,255,255,.72);border-color:var(--border);}
        [data-theme="light"] .command-progress-track{background:#d9e4ee;}
        [data-theme="light"] .confirm-backdrop{background:rgba(31,41,55,.36);}
        [data-theme="light"] .mobile-nav{background:rgba(255,255,255,.96);border-color:var(--border);box-shadow:0 14px 34px rgba(46,63,86,.18);}
        /* Liquid Glass is an optional interface theme for controls and navigation. */
        [data-theme="glass"]{
            --bg:#091119;
            --bg-accent:#142531;
            --surface:#111c27;
            --surface-soft:#142231;
            --surface-strong:#1d3342;
            --border:rgba(145,255,241,.28);
            --text:#f3fbff;
            --muted:#aec1d3;
            --primary:#8af7ee;
            --primary-hover:#b5fff8;
            --secondary:#e5bd73;
            --danger:#dc6d61;
            --success-bg:rgba(35,122,92,.2);
            --success-border:rgba(123,238,184,.36);
            --warn-bg:rgba(139,96,31,.18);
            --warn-border:rgba(226,180,106,.38);
            --shadow:0 18px 48px rgba(0,0,0,.38);
            --scrollbar-track:#081018;
            --scrollbar-thumb:#42606e;
            --scrollbar-thumb-hover:#5b7f8c;
            --focus-ring:0 0 0 3px rgba(138,247,238,.18);
            --glass-bg:rgba(17,31,42,.58);
            --glass-bg-strong:rgba(25,48,61,.72);
            --glass-border:rgba(145,255,241,.3);
            --glass-highlight:rgba(255,255,255,.26);
            --glass-shadow:0 20px 52px rgba(0,0,0,.42), inset 0 1px 0 rgba(255,255,255,.18);
            --glass-blur:18px;
        }
        [data-theme="glass"] body{
            color:var(--text);
            background:
                linear-gradient(135deg, rgba(9,17,25,.98), rgba(12,27,34,.98) 44%, rgba(7,12,20,.98)),
                linear-gradient(90deg, rgba(138,247,238,.08), rgba(229,189,115,.08) 52%, rgba(178,139,255,.06));
        }
        [data-theme="glass"] body::before{
            content:"";
            position:fixed;
            inset:0;
            pointer-events:none;
            background:
                linear-gradient(115deg, rgba(255,255,255,.055), transparent 30%, rgba(138,247,238,.035) 58%, transparent 82%),
                linear-gradient(180deg, rgba(255,255,255,.025), transparent 42%, rgba(255,255,255,.018));
            opacity:.72;
        }
        [data-theme="glass"] .app-shell{position:relative;}
        [data-theme="glass"] .topbar,
        [data-theme="glass"] .side-nav,
        [data-theme="glass"] .mobile-nav,
        [data-theme="glass"] .api-pill,
        [data-theme="glass"] .mode-toggle,
        [data-theme="glass"] .theme-toggle,
        [data-theme="glass"] .version-badge,
        [data-theme="glass"] .hero-popover,
        [data-theme="glass"] .segmented,
        [data-theme="glass"] .subtabs{
            background:
                linear-gradient(135deg, rgba(255,255,255,.16), rgba(255,255,255,.035) 36%, rgba(138,247,238,.08)),
                var(--glass-bg);
            border-color:var(--glass-border);
            box-shadow:var(--glass-shadow);
            backdrop-filter:blur(var(--glass-blur)) saturate(155%);
            -webkit-backdrop-filter:blur(var(--glass-blur)) saturate(155%);
        }
        [data-theme="glass"] .view-head,
        [data-theme="glass"] .panel,
        [data-theme="glass"] .protocol-workspace,
        [data-theme="glass"] .list-workspace,
        [data-theme="glass"] .confirm-card,
        [data-theme="glass"] .service-panel,
        [data-theme="glass"] .overview-key-panel,
        [data-theme="glass"] .status-card{
            background:
                linear-gradient(145deg, rgba(23,38,50,.92), rgba(12,22,31,.88)),
                rgba(12,22,31,.86);
            border-color:rgba(145,255,241,.18);
            box-shadow:0 14px 36px rgba(0,0,0,.25);
            backdrop-filter:blur(8px) saturate(125%);
            -webkit-backdrop-filter:blur(8px) saturate(125%);
        }
        [data-theme="glass"] .hero-popover{
            transform-origin:top right;
            transition:opacity .18s ease, transform .2s cubic-bezier(.2,.85,.2,1), visibility .18s ease;
        }
        [data-theme="glass"] .hero-popover.hidden{
            display:block;
            opacity:0;
            visibility:hidden;
            pointer-events:none;
            transform:translateY(-6px) scale(.97);
        }
        [data-theme="glass"] .hero-popover:not(.hidden){
            opacity:1;
            visibility:visible;
            transform:translateY(0) scale(1);
        }
        [data-theme="glass"] button,
        [data-theme="glass"] .secondary-button,
        [data-theme="glass"] .success-button,
        [data-theme="glass"] .outline-button,
        [data-theme="glass"] .service-preset-btn,
        [data-theme="glass"] .mode-choice,
        [data-theme="glass"] .seg-tab,
        [data-theme="glass"] .subtab,
        [data-theme="glass"] .nav-item{
            background:
                linear-gradient(135deg, rgba(255,255,255,.13), rgba(255,255,255,.03) 44%, rgba(138,247,238,.08)),
                rgba(18,39,47,.48);
            border-color:rgba(145,255,241,.34);
            color:#a9fff7;
            box-shadow:inset 0 1px 0 rgba(255,255,255,.14);
            backdrop-filter:blur(12px) saturate(145%);
            -webkit-backdrop-filter:blur(12px) saturate(145%);
            transition:transform .18s cubic-bezier(.2,.8,.2,1), background-color .18s ease, border-color .18s ease, box-shadow .18s ease, color .18s ease;
        }
        [data-theme="glass"] button:hover,
        [data-theme="glass"] .secondary-button:hover,
        [data-theme="glass"] .success-button:hover,
        [data-theme="glass"] .outline-button:hover,
        [data-theme="glass"] .service-preset-btn:hover,
        [data-theme="glass"] .mode-choice:hover,
        [data-theme="glass"] .seg-tab:hover,
        [data-theme="glass"] .subtab:hover,
        [data-theme="glass"] .nav-item:hover{
            transform:translateY(-1px);
            border-color:rgba(180,255,249,.54);
            background:
                linear-gradient(135deg, rgba(255,255,255,.18), rgba(255,255,255,.05) 42%, rgba(138,247,238,.12)),
                rgba(23,58,66,.58);
            box-shadow:0 12px 28px rgba(0,0,0,.22), inset 0 1px 0 rgba(255,255,255,.22);
        }
        [data-theme="glass"] button:active,
        [data-theme="glass"] .mode-choice:active,
        [data-theme="glass"] .seg-tab:active,
        [data-theme="glass"] .subtab:active,
        [data-theme="glass"] .nav-item:active{transform:scale(.985);}
        [data-theme="glass"] button.danger{
            background:linear-gradient(135deg, rgba(255,199,190,.12), rgba(96,30,37,.58));
            border-color:rgba(241,118,107,.48);
            color:#ffc8c2;
        }
        [data-theme="glass"] button.danger:hover{
            background:linear-gradient(135deg, rgba(255,215,207,.16), rgba(123,43,49,.66));
            border-color:rgba(255,151,141,.62);
        }
        [data-theme="glass"] .mode-choice.active,
        [data-theme="glass"] .seg-tab.active,
        [data-theme="glass"] .subtab.active,
        [data-theme="glass"] .nav-item.active,
        [data-theme="glass"] [data-theme-choice].active{
            background:
                linear-gradient(135deg, rgba(255,255,255,.2), rgba(138,247,238,.18) 55%, rgba(229,189,115,.12)),
                rgba(30,75,80,.64);
            border-color:rgba(173,255,248,.58);
            color:#f2fffe;
            box-shadow:0 12px 30px rgba(32,211,198,.12), inset 0 1px 0 rgba(255,255,255,.24);
        }
        [data-theme="glass"] input,
        [data-theme="glass"] textarea,
        [data-theme="glass"] select{
            background:rgba(5,13,20,.62);
            border-color:rgba(145,255,241,.22);
            color:var(--text);
            box-shadow:inset 0 1px 0 rgba(255,255,255,.06);
        }
        [data-theme="glass"] input::placeholder,
        [data-theme="glass"] textarea::placeholder{color:#8fa4b5;}
        [data-theme="glass"] .status-label,
        [data-theme="glass"] .app-caption strong,
        [data-theme="glass"] h1,
        [data-theme="glass"] h2,
        [data-theme="glass"] h3{color:#f5fbff;}
        [data-theme="glass"] .status-value,
        [data-theme="glass"] .status-card-wide .status-value{color:#9ffff7;}
        [data-theme="glass"] .section-subtitle,
        [data-theme="glass"] .status-note,
        [data-theme="glass"] .key-status-note,
        [data-theme="glass"] .field-label,
        [data-theme="glass"] .app-branch{color:#b6c9d9;}
        [data-theme="glass"] .eyebrow{color:#e6bf73;}
        [data-theme="glass"] .card-icon,
        [data-theme="glass"] .api-pill::before{
            background-color:rgba(138,247,238,.16);
            border-color:rgba(145,255,241,.32);
            box-shadow:inset 0 1px 0 rgba(255,255,255,.16);
        }
        [data-theme="glass"] .pool-table th{background:rgba(16,32,43,.82);color:#b7cad8;}
        [data-theme="glass"] .pool-row-active{background:rgba(138,247,238,.08);}
        [data-theme="glass"] [data-liquid]{
            position:relative;
            overflow:hidden;
            isolation:isolate;
        }
        [data-theme="glass"] [data-liquid]::before{
            content:"";
            position:absolute;
            inset:0;
            z-index:0;
            pointer-events:none;
            border-radius:inherit;
            background:
                radial-gradient(circle at var(--mx, 50%) var(--my, 50%), rgba(255,255,255,.18), rgba(138,247,238,.07) 24%, transparent 58%),
                linear-gradient(115deg, transparent 0 30%, rgba(255,255,255,.08) 46%, transparent 62% 100%);
            opacity:0;
            transition:opacity .18s ease;
        }
        [data-theme="glass"] [data-liquid] > *{position:relative;z-index:2;}
        [data-theme="glass"] [data-liquid]:hover::before,
        [data-theme="glass"] [data-liquid]:focus-visible::before,
        [data-theme="glass"] [data-liquid].liquid-active::before{opacity:1;}
        .liquid-global-lens{
            position:fixed;
            left:0;
            top:0;
            width:58px;
            height:58px;
            pointer-events:none;
            border-radius:999px;
            z-index:70;
            display:none;
            opacity:0;
            transform:translate3d(calc(var(--lx, -100px) - 50%),calc(var(--ly, -100px) - 50%),0) scale(.82);
            background:
                radial-gradient(circle at 34% 24%, rgba(255,255,255,.48) 0 3px, rgba(255,255,255,.14) 20%, rgba(255,255,255,.04) 44%, transparent 72%),
                radial-gradient(circle at 58% 62%, rgba(138,247,238,.09), transparent 58%);
            border:1px solid rgba(236,255,253,.46);
            box-shadow:
                inset 0 1px 1px rgba(255,255,255,.48),
                inset 0 -8px 14px rgba(7,20,29,.16),
                0 4px 14px rgba(0,0,0,.2),
                0 0 18px rgba(138,247,238,.16);
            backdrop-filter:saturate(145%) brightness(1.08);
            -webkit-backdrop-filter:saturate(145%) brightness(1.08);
            transition:opacity .12s ease;
            will-change:transform,opacity;
        }
        [data-theme="glass"] .liquid-global-lens{display:block;}
        [data-theme="glass"] .liquid-global-lens-active{
            opacity:1;
            transform:translate3d(calc(var(--lx, -100px) - 50%),calc(var(--ly, -100px) - 50%),0) scale(1);
        }
        @supports not ((backdrop-filter:blur(1px)) or (-webkit-backdrop-filter:blur(1px))){
            [data-theme="glass"] .topbar,
            [data-theme="glass"] .side-nav,
            [data-theme="glass"] .mobile-nav,
            [data-theme="glass"] .api-pill,
            [data-theme="glass"] .mode-toggle,
            [data-theme="glass"] .theme-toggle,
            [data-theme="glass"] .version-badge,
            [data-theme="glass"] .hero-popover,
            [data-theme="glass"] .segmented,
            [data-theme="glass"] .subtabs{background:rgba(14,28,38,.96);}
        }
        @media (prefers-reduced-motion: reduce){
            [data-theme="glass"] *,
            [data-theme="glass"] .hero-popover{transition:none!important;animation:none!important;}
            [data-theme="glass"] button:hover,
            [data-theme="glass"] .mode-choice:hover,
            [data-theme="glass"] .seg-tab:hover,
            [data-theme="glass"] .subtab:hover,
            [data-theme="glass"] .nav-item:hover{transform:none;}
            [data-theme="glass"] .liquid-global-lens{transition:none!important;}
        }
        @media (prefers-contrast: more){
            [data-theme="glass"] .topbar,
            [data-theme="glass"] .side-nav,
            [data-theme="glass"] .mobile-nav,
            [data-theme="glass"] .hero-popover,
            [data-theme="glass"] button,
            [data-theme="glass"] .mode-choice,
            [data-theme="glass"] .seg-tab,
            [data-theme="glass"] .subtab,
            [data-theme="glass"] .nav-item{
                background:rgba(8,18,26,.96);
                border-color:rgba(190,255,245,.6);
            }
        }
        @media (max-width: 760px){
            [data-theme="glass"]{--glass-blur:12px;}
            [data-theme="glass"] .liquid-global-lens{width:54px;height:54px;}
            [data-theme="glass"] .mobile-nav{background:rgba(13,27,36,.82);}
            [data-theme="glass"] .hero-popover.hidden{display:none;}
        }
'''.replace('{TELEGRAM_SVG_B64}', str(TELEGRAM_SVG_B64 or ''))
