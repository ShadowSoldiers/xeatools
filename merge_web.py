#!/usr/bin/env python3
"""
merge_web.py — Web GUI untuk merge_pdf
Instalasi: pip install flask
Jalankan : python merge_web.py
Buka     : Chrome Android → http://localhost:5000
"""

import sys
import json
import queue
import threading
from pathlib import Path

try:
    from flask import Flask, render_template_string, request, jsonify, Response, stream_with_context
except ImportError:
    print("ERROR: pip install flask")
    sys.exit(1)

try:
    import merge_core as core
except ImportError:
    print("ERROR: Pastikan merge_core.py ada di folder yang sama.")
    sys.exit(1)

app = Flask(__name__)

# ─── State global (single-user di HP) ───────────────────────
_state = {
    "running"   : False,
    "result"    : None,
    "log_queue" : queue.Queue(),
}

# ─────────────────────────────────────────────────────────────
# HTML TEMPLATE
# ─────────────────────────────────────────────────────────────
HTML = r"""
<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>merge_pdf</title>
<style>
  :root {
    --navy  : #1a3c5e;
    --teal  : #0891b2;
    --lteal : #e0f7ff;
    --green : #059669;
    --lgreen: #d1fae5;
    --orange: #ea580c;
    --red   : #dc2626;
    --gray  : #64748b;
    --lgray : #f0f4f8;
    --dark  : #0f172a;
    --white : #ffffff;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', sans-serif; background: var(--lgray);
         color: var(--dark); min-height: 100vh; }

  /* Header */
  .header { background: var(--navy); color: var(--white);
             padding: 14px 20px; position: sticky; top:0; z-index:99;
             display:flex; align-items:center; gap:12px;
             border-bottom: 3px solid var(--teal); }
  .header h1 { font-size: 1.15rem; font-weight: 700; color: var(--teal); }
  .header span { font-size: 0.78rem; color: #94a3b8; }

  /* Nav tabs */
  .tabs { display:flex; background: var(--navy); padding: 0 16px; gap:4px; }
  .tab  { padding: 9px 18px; font-size: 0.85rem; color: #94a3b8;
          border-bottom: 3px solid transparent; cursor:pointer; transition:.2s; }
  .tab.active { color: var(--teal); border-bottom-color: var(--teal);
                font-weight: 600; }

  /* Sections */
  .section { display:none; padding: 16px; max-width: 680px; margin: 0 auto; }
  .section.active { display:block; }

  /* Card */
  .card { background: var(--white); border-radius:12px;
          border: 1px solid #e2e8f0; margin-bottom: 14px;
          overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,.06); }
  .card-header { background: var(--navy); color: var(--white);
                 padding: 10px 16px; font-weight:600; font-size:.9rem;
                 border-left: 4px solid var(--teal); }
  .card-body { padding: 14px 16px; }

  /* Form */
  label { display:block; font-size:.82rem; color: var(--gray);
          font-weight:600; margin-bottom:4px; margin-top:10px; }
  input[type=text], input[type=email], input[type=password], input[type=number] {
    width:100%; padding:10px 12px; border:1px solid #cbd5e1;
    border-radius:8px; font-size:.9rem; background: var(--lgray);
    transition:.2s; }
  input:focus { outline:none; border-color: var(--teal);
                background: var(--white); box-shadow: 0 0 0 3px rgba(8,145,178,.15); }

  /* Buttons */
  .btn { display:inline-flex; align-items:center; gap:7px;
         padding: 11px 22px; border:none; border-radius:9px;
         font-size:.9rem; font-weight:600; cursor:pointer; transition:.2s; }
  .btn-primary { background: var(--teal); color: var(--white); }
  .btn-primary:hover { background: #0e7490; }
  .btn-primary:disabled { background: var(--gray); cursor:not-allowed; }
  .btn-success { background: var(--green); color: var(--white); }
  .btn-success:hover { background: #047857; }
  .btn-danger  { background: var(--red); color: var(--white); }
  .btn-danger:hover  { background: #b91c1c; }
  .btn-outline { background: transparent; color: var(--teal);
                 border: 2px solid var(--teal); }
  .btn-outline:hover { background: var(--lteal); }
  .btn-row { display:flex; gap:10px; flex-wrap:wrap; margin-top:14px; }
  .btn-full { width:100%; justify-content:center; }

  /* Log console */
  #log-box { background: #1e293b; color: #e2e8f0; border-radius:10px;
              padding: 12px; font-family: monospace; font-size: .82rem;
              height: 340px; overflow-y: auto; white-space: pre-wrap;
              line-height: 1.55; }
  .log-ok   { color: #34d399; }
  .log-warn { color: #fbbf24; }
  .log-fail { color: #f87171; }
  .log-info { color: #67e8f9; }
  .log-dim  { color: #64748b; }

  /* Progress bar */
  .progress-wrap { background: #e2e8f0; border-radius:99px;
                   height:8px; margin:10px 0; overflow:hidden; }
  .progress-bar  { background: var(--teal); height:100%;
                   border-radius:99px; transition: width .4s; }

  /* Summary table */
  table { width:100%; border-collapse:collapse; font-size:.88rem; }
  th { background: var(--navy); color: var(--white);
       padding: 9px 12px; text-align:left; font-weight:600; }
  td { padding: 8px 12px; border-bottom: 1px solid #e2e8f0; }
  tr:nth-child(even) td { background: var(--lgray); }
  .badge { display:inline-block; padding:2px 8px; border-radius:99px;
           font-size:.75rem; font-weight:600; }
  .badge-teal   { background: var(--lteal); color: var(--teal); }
  .badge-green  { background: var(--lgreen); color: var(--green); }
  .badge-orange { background: #fff7ed; color: var(--orange); }

  /* Stat cards */
  .stats { display:grid; grid-template-columns:repeat(2,1fr); gap:10px; margin-bottom:14px; }
  .stat  { background: var(--white); border-radius:10px; padding:12px 14px;
           border-left: 4px solid var(--teal);
           box-shadow: 0 1px 3px rgba(0,0,0,.06); }
  .stat-num { font-size:1.6rem; font-weight:700; color: var(--navy); }
  .stat-lbl { font-size:.75rem; color: var(--gray); margin-top:2px; }

  /* Alert */
  .alert { padding:10px 14px; border-radius:8px; margin:10px 0;
           font-size:.88rem; }
  .alert-info    { background: var(--lteal); color: var(--teal); }
  .alert-success { background: var(--lgreen); color: var(--green); }
  .alert-warn    { background: #fff7ed; color: var(--orange); }
  .alert-error   { background: #fef2f2; color: var(--red); }

  /* Email confirm section */
  .file-list { background: var(--lgray); border-radius:8px; padding:10px 14px;
               max-height:200px; overflow-y:auto; margin:8px 0; }
  .file-item { padding:4px 0; font-size:.83rem; color: var(--dark);
               border-bottom:1px solid #e2e8f0; }
  .file-item:last-child { border:none; }

  .spinner { display:inline-block; width:16px; height:16px;
             border:2px solid #fff; border-top-color:transparent;
             border-radius:50%; animation: spin .7s linear infinite; }
  @keyframes spin { to { transform:rotate(360deg); } }

  .hidden { display:none !important; }
  .mt8 { margin-top:8px; }
  .mt14 { margin-top:14px; }
  .bold { font-weight:700; }
  .teal { color: var(--teal); }
  .green { color: var(--green); }
  .red { color: var(--red); }
  .dim { color: var(--gray); }
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>merge_pdf</h1>
    <span>PT Galva Technologies Tbk</span>
  </div>
</div>

<div class="tabs">
  <div class="tab active" onclick="showTab('run')">▶ Jalankan</div>
  <div class="tab" onclick="showTab('config')">⚙ Konfigurasi</div>
  <div class="tab" onclick="showTab('ringkasan')">📊 Ringkasan</div>
</div>

<!-- ══════════ TAB: JALANKAN ══════════ -->
<div id="tab-run" class="section active">

  <div id="cfg-info" class="card">
    <div class="card-header">📂 Konfigurasi Aktif</div>
    <div class="card-body" id="cfg-info-body" style="font-size:.85rem;color:#64748b;">
      Memuat...
    </div>
  </div>

  <div class="card">
    <div class="card-header">▶ Proses Merge</div>
    <div class="card-body">
      <div id="progress-wrap" class="progress-wrap hidden">
        <div id="progress-bar" class="progress-bar" style="width:0%"></div>
      </div>
      <div id="log-box">Siap menjalankan merge...\n</div>
      <div class="btn-row">
        <button class="btn btn-primary" id="btn-run" onclick="startMerge()">
          ▶ Mulai Merge
        </button>
        <button class="btn btn-outline" onclick="clearLog()">
          🗑 Bersihkan Log
        </button>
      </div>
    </div>
  </div>

  <!-- Hasil & Konfirmasi Email -->
  <div id="result-section" class="hidden">
    <div class="card">
      <div class="card-header">📊 Hasil Merge</div>
      <div class="card-body">
        <div class="stats" id="stats-grid"></div>
        <table id="summary-table">
          <thead>
            <tr><th>Tipe Layanan</th><th>Jumlah File</th><th>Nilai Total</th></tr>
          </thead>
          <tbody id="summary-body"></tbody>
        </table>
      </div>
    </div>

    <div id="email-section" class="card">
      <div class="card-header">📧 Kirim Email</div>
      <div class="card-body">
        <div id="email-file-list"></div>
        <div id="email-status"></div>
        <div class="btn-row" id="email-btn-row">
          <button class="btn btn-success" onclick="sendEmails()">
            📧 Ya, Kirim Email
          </button>
          <button class="btn btn-outline" onclick="cancelEmail()">
            ✕ Lewati
          </button>
        </div>
      </div>
    </div>
  </div>

</div>

<!-- ══════════ TAB: KONFIGURASI ══════════ -->
<div id="tab-config" class="section">
  <div class="card">
    <div class="card-header">📂 Folder</div>
    <div class="card-body">
      <label>Folder Sumber (semua PDF mentah)</label>
      <input type="text" id="c-source" placeholder="/sdcard/Documents">
      <label>Folder Output (hasil merge)</label>
      <input type="text" id="c-output" placeholder="/sdcard/Documents/Hasil">
    </div>
  </div>

  <div class="card">
    <div class="card-header">📧 Email Gmail</div>
    <div class="card-body">
      <label>Email Pengirim (Gmail)</label>
      <input type="email" id="c-sender" placeholder="emailanda@gmail.com">
      <label>App Password (16 karakter)</label>
      <input type="password" id="c-password" placeholder="xxxx xxxx xxxx xxxx">
      <label>Penerima TO (pisah koma)</label>
      <input type="text" id="c-to" placeholder="penerima@gmail.com, penerima2@gmail.com">
      <label>CC (opsional, pisah koma)</label>
      <input type="text" id="c-cc" placeholder="">
      <label>BCC (opsional, pisah koma)</label>
      <input type="text" id="c-bcc" placeholder="">
      <div class="btn-row mt14">
        <button class="btn btn-primary" onclick="saveConfig()">💾 Simpan Konfigurasi</button>
      </div>
      <div id="config-status" class="mt8"></div>
    </div>
  </div>

  <div class="card">
    <div class="card-header">💡 Cara Buat App Password Gmail</div>
    <div class="card-body" style="font-size:.85rem;color:#64748b;line-height:1.7;">
      1. Buka <strong>myaccount.google.com</strong><br>
      2. Keamanan → <strong>2-Step Verification</strong> (aktifkan)<br>
      3. Kembali → cari <strong>App Passwords</strong><br>
      4. App: Mail, Device: Other → beri nama bebas<br>
      5. Klik <strong>Generate</strong> → salin 16 karakter<br>
      6. Tempel ke kolom App Password di atas
    </div>
  </div>
</div>

<!-- ══════════ TAB: RINGKASAN ══════════ -->
<div id="tab-ringkasan" class="section">
  <div class="card">
    <div class="card-header">📊 Ringkasan Total Terakhir</div>
    <div class="card-body">
      <pre id="ringkasan-content"
           style="font-size:.82rem;font-family:monospace;
                  white-space:pre-wrap;color:#0f172a;line-height:1.6;">
Belum ada data. Jalankan merge terlebih dahulu.</pre>
      <div class="btn-row mt14">
        <button class="btn btn-outline" onclick="loadRingkasan()">🔄 Refresh</button>
      </div>
    </div>
  </div>
</div>

<!-- ═══════════════════════════════════ -->
<script>
let currentResult = null;
const HARGA = {
  "Install"         : 199000,
  "Maintenance"     : 86000,
  "Repair - Service": 119000,
  "Take Report"     : 43000,
};

// ── Tab Navigation ─────────────────────────────────────────
function showTab(name) {
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  event.target.classList.add('active');
  if (name === 'config') loadConfig();
  if (name === 'ringkasan') loadRingkasan();
}

// ── Config ─────────────────────────────────────────────────
function loadConfig() {
  fetch('/api/config').then(r => r.json()).then(cfg => {
    document.getElementById('c-source').value   = cfg.source_dir || '';
    document.getElementById('c-output').value   = cfg.output_dir || '';
    document.getElementById('c-sender').value   = cfg.sender_email || '';
    document.getElementById('c-password').value = cfg.sender_password || '';
    document.getElementById('c-to').value  = (cfg.to  || []).join(', ');
    document.getElementById('c-cc').value  = (cfg.cc  || []).join(', ');
    document.getElementById('c-bcc').value = (cfg.bcc || []).join(', ');
    updateCfgInfo(cfg);
  });
}

function saveConfig() {
  const splitComma = s => s.split(',').map(x=>x.trim()).filter(Boolean);
  const cfg = {
    source_dir      : document.getElementById('c-source').value.trim(),
    output_dir      : document.getElementById('c-output').value.trim(),
    sender_email    : document.getElementById('c-sender').value.trim(),
    sender_password : document.getElementById('c-password').value.trim(),
    to  : splitComma(document.getElementById('c-to').value),
    cc  : splitComma(document.getElementById('c-cc').value),
    bcc : splitComma(document.getElementById('c-bcc').value),
  };
  fetch('/api/config', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify(cfg)
  }).then(r => r.json()).then(r => {
    const el = document.getElementById('config-status');
    if (r.ok) {
      el.innerHTML = '<div class="alert alert-success">✓ Konfigurasi disimpan.</div>';
      updateCfgInfo(cfg);
    } else {
      el.innerHTML = '<div class="alert alert-error">Gagal menyimpan.</div>';
    }
    setTimeout(() => el.innerHTML='', 3000);
  });
}

function updateCfgInfo(cfg) {
  const el = document.getElementById('cfg-info-body');
  if(!el) return;
  el.innerHTML =
    `<b>Sumber:</b> ${cfg.source_dir||'-'}<br>` +
    `<b>Output:</b> ${cfg.output_dir||'-'}<br>` +
    `<b>Email:</b> ${cfg.sender_email||'<span style="color:#ea580c">Belum diset</span>'}`;
}

// ── Merge Process ───────────────────────────────────────────
function appendLog(msg, cls='') {
  const box = document.getElementById('log-box');
  const span = document.createElement('span');
  if (cls) span.className = cls;
  span.textContent = msg + '\n';
  box.appendChild(span);
  box.scrollTop = box.scrollHeight;
}

function clearLog() {
  document.getElementById('log-box').innerHTML = '';
  document.getElementById('result-section').classList.add('hidden');
}

function startMerge() {
  const btn = document.getElementById('btn-run');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Memproses...';
  document.getElementById('result-section').classList.add('hidden');
  document.getElementById('log-box').innerHTML = '';
  document.getElementById('progress-wrap').classList.remove('hidden');
  document.getElementById('progress-bar').style.width = '5%';

  let totalPairs = 0; let done = 0;

  const es = new EventSource('/api/run');
  es.onmessage = function(e) {
    const ev = JSON.parse(e.data);
    const t  = ev.type; const d = ev.data;

    if (t === 'scan') {
      appendLog(`🔍 Scan: ${d.total} file PDF ditemukan`, 'log-info');
    } else if (t === 'classify') {
      appendLog(`📂 STBA: ${d.stba}  STATS: ${d.stats}  Tidak dikenali: ${d.unknown}`, 'log-info');
    } else if (t === 'pair_found') {
      totalPairs = d.pairs;
      appendLog(`🔗 Pasangan cocok: ${d.pairs}  |  Hanya STBA: ${d.only_stba}  |  Hanya STATS: ${d.only_stats}`, 'log-info');
      appendLog('');
    } else if (t === 'merge_ok') {
      done++;
      appendLog(`✓  [${d.key}]  ${d.nama}  →  ${d.folder}/`, 'log-ok');
      if (totalPairs > 0) {
        document.getElementById('progress-bar').style.width =
          Math.min(95, Math.round(done/totalPairs*90)+5) + '%';
      }
    } else if (t === 'merge_fail') {
      appendLog(`✗  [${d.key}] Gagal merge`, 'log-fail');
    } else if (t === 'file_kosong') {
      appendLog(`⚠  ${d.name}  →  File Kosong/`, 'log-warn');
    } else if (t === 'arsip') {
      appendLog('');
      appendLog(`📦 ${d.jumlah} file mentah diarsip ke [${d.folder}]`, 'log-info');
    } else if (t === 'txt_saved') {
      appendLog(`📝 ${d.path.split('/').pop()} disimpan`, 'log-dim');
    } else if (t === 'ringkasan') {
      appendLog(`📊 ringkasan_total.txt disimpan`, 'log-info');
    } else if (t === 'done') {
      document.getElementById('progress-bar').style.width = '100%';
      appendLog('');
      appendLog('══ Selesai ══', 'log-info');
      es.close();
      btn.disabled = false;
      btn.innerHTML = '▶ Mulai Merge';
      currentResult = d;
      showResult(d);
      setTimeout(()=>{
        document.getElementById('progress-wrap').classList.add('hidden');
      }, 1500);
    } else if (t === 'error') {
      appendLog(`ERROR: ${d.msg}`, 'log-fail');
      es.close();
      btn.disabled = false;
      btn.innerHTML = '▶ Mulai Merge';
    }
  };
  es.onerror = function() {
    appendLog('Koneksi terputus.', 'log-fail');
    es.close();
    btn.disabled = false;
    btn.innerHTML = '▶ Mulai Merge';
  };
}

function showResult(r) {
  document.getElementById('result-section').classList.remove('hidden');

  // Stat cards
  const stats = [
    ['✓ Berhasil', r.success + ' pasang', 'green'],
    ['✗ Gagal',    r.failed  + ' pasang', 'red'],
    ['File Kosong',r.file_kosong + ' file', 'orange'],
    ['Diarsip ke', r.folder_bulan || '-', 'teal'],
  ];
  const colors = {green:'#059669',red:'#dc2626',orange:'#ea580c',teal:'#0891b2'};
  document.getElementById('stats-grid').innerHTML = stats.map(([lbl,val,col]) =>
    `<div class="stat" style="border-left-color:${colors[col]}">
       <div class="stat-num" style="color:${colors[col]}">${val}</div>
       <div class="stat-lbl">${lbl}</div>
     </div>`
  ).join('');

  // Summary table
  const tbody = document.getElementById('summary-body');
  tbody.innerHTML = '';
  const summary = r.summary || {};
  let grandTotal = 0;
  for (const [folder, entries] of Object.entries(summary).sort()) {
    const harga = HARGA[folder] || 0;
    const total = entries.length * harga;
    grandTotal += total;
    const fmtRp = n => 'Rp ' + n.toLocaleString('id-ID');
    tbody.innerHTML +=
      `<tr>
        <td><span class="badge badge-teal">${folder}</span></td>
        <td>${entries.length} file</td>
        <td>${fmtRp(total)}</td>
       </tr>`;
  }
  tbody.innerHTML +=
    `<tr style="font-weight:700;background:#f0f4f8">
       <td>TOTAL</td><td></td>
       <td style="color:#0891b2">Rp ${grandTotal.toLocaleString('id-ID')}</td>
     </tr>`;

  // Email section
  if (!r.summary || Object.keys(r.summary).length === 0) {
    document.getElementById('email-section').classList.add('hidden');
    return;
  }
  let fileHtml = '';
  for (const [folder, entries] of Object.entries(r.summary).sort()) {
    fileHtml += `<div class="bold teal" style="margin-top:8px;font-size:.85rem">${folder} — ${entries.length} file</div>`;
    entries.forEach(([key, nama, serial]) => {
      fileHtml += `<div class="file-item">📄 ${key}.pdf  <span class="dim">— ${nama}</span>  <span class="dim" style="color:#0891b2">SN: ${serial}</span></div>`;
    });
  }
  document.getElementById('email-file-list').innerHTML =
    `<div class="alert alert-info">File berikut akan dikirim sebagai attachment email:</div>
     <div class="file-list">${fileHtml}</div>`;
  document.getElementById('email-status').innerHTML = '';
  document.getElementById('email-btn-row').classList.remove('hidden');
}

// ── Email ──────────────────────────────────────────────────
function sendEmails() {
  document.getElementById('email-btn-row').classList.add('hidden');
  document.getElementById('email-status').innerHTML =
    '<div class="alert alert-info"><span class="spinner"></span>  Mengirim email...</div>';

  fetch('/api/send-email', {method:'POST'})
    .then(r => r.json())
    .then(r => {
      if (r.ok > 0) {
        document.getElementById('email-status').innerHTML =
          `<div class="alert alert-success">✓ ${r.ok} email terkirim.</div>
           ${r.fail>0 ? `<div class="alert alert-warn">✗ ${r.fail} gagal.</div>` : ''}
           ${r.detail.map(([t,ok,msg])=>
             `<div class="file-item">${ok?'✓':'✗'} [${t}] ${msg}</div>`
           ).join('')}`;
      } else {
        document.getElementById('email-status').innerHTML =
          `<div class="alert alert-error">✗ Gagal kirim email.<br>${r.detail.map(([t,ok,msg])=>msg).join('<br>')}</div>`;
      }
    });
}

function cancelEmail() {
  document.getElementById('email-btn-row').classList.add('hidden');
  document.getElementById('email-status').innerHTML =
    '<div class="alert alert-warn">Pengiriman email dilewati.</div>';
}

// ── Ringkasan ──────────────────────────────────────────────
function loadRingkasan() {
  fetch('/api/ringkasan').then(r => r.json()).then(r => {
    document.getElementById('ringkasan-content').textContent =
      r.content || 'Belum ada data. Jalankan merge terlebih dahulu.';
  });
}

// ── Init ───────────────────────────────────────────────────
window.onload = function() {
  fetch('/api/config').then(r=>r.json()).then(cfg => {
    updateCfgInfo(cfg);
  });
};
</script>
</body>
</html>
"""

# ─────────────────────────────────────────────────────────────
# FLASK ROUTES
# ─────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify(core.load_config())

@app.route("/api/config", methods=["POST"])
def post_config():
    try:
        cfg = core.load_config()
        cfg.update(request.get_json())
        core.save_config(cfg)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route("/api/run")
def api_run():
    """Server-Sent Events — stream progress dari merge."""
    cfg = core.load_config()
    q   = queue.Queue()

    def cb(event, data):
        # Konversi Path ke str agar bisa di-JSON-kan
        def fix(obj):
            if isinstance(obj, Path): return str(obj)
            if isinstance(obj, dict): return {k: fix(v) for k, v in obj.items()}
            if isinstance(obj, list): return [fix(v) for v in obj]
            if isinstance(obj, tuple): return [fix(v) for v in obj]
            return obj
        q.put({"type": event, "data": fix(data)})

    def worker():
        try:
            result = core.run_merge(
                cfg["source_dir"], cfg["output_dir"],
                cfg.get("digit_count", 6), cb
            )
            _state["result"] = result
        except Exception as e:
            q.put({"type": "error", "data": {"msg": str(e)}})
        finally:
            q.put(None)  # sentinel

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    def generate():
        while True:
            item = q.get()
            if item is None:
                break
            yield f"data: {json.dumps(item)}\n\n"

    return Response(stream_with_context(generate()),
                    mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache",
                             "X-Accel-Buffering": "no"})

@app.route("/api/send-email", methods=["POST"])
def api_send_email():
    result = _state.get("result")
    if not result or not result.get("summary"):
        return jsonify({"ok": 0, "fail": 0, "detail": [], "error": "Tidak ada hasil merge"})
    cfg = core.load_config()
    email_result = core.do_send_emails(result["summary"], cfg)
    detail = [(t, ok, msg) for t, ok, msg in email_result["detail"]]
    return jsonify({"ok": email_result["ok"],
                    "fail": email_result["fail"],
                    "detail": detail})

@app.route("/api/ringkasan")
def api_ringkasan():
    cfg      = core.load_config()
    txt_path = Path(cfg["output_dir"]) / "ringkasan_total.txt"
    if txt_path.exists():
        with open(txt_path, "r", encoding="utf-8") as f:
            return jsonify({"content": f.read()})
    return jsonify({"content": ""})

# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 54)
    print("  merge_pdf  —  Web GUI")
    print("=" * 54)
    print("  Buka di Chrome Android:")
    print("  ➜  http://localhost:5000")
    print("=" * 54)
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
