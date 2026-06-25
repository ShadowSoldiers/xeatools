#!/usr/bin/env python3
"""
merge_web.py — Web GUI untuk XEA Tools
Tab: Download | Merge | Schedule | Konfigurasi | Ringkasan
Jalankan : python merge_web.py
Buka     : Chrome Android → http://localhost:5000
"""

import sys, json, queue, threading, subprocess, os
from pathlib import Path
from datetime import datetime, date

try:
    from flask import Flask, render_template_string, request, jsonify, Response, stream_with_context
except ImportError:
    print("ERROR: pip install flask"); sys.exit(1)

try:
    import merge_core as core
except ImportError:
    print("ERROR: Pastikan merge_core.py ada di folder yang sama."); sys.exit(1)

try:
    import galva_download as dl
except ImportError:
    dl = None

# APScheduler (opsional)
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    _scheduler = BackgroundScheduler()
    _scheduler.start()
    _HAS_SCHEDULER = True
except Exception:
    _scheduler = None
    _HAS_SCHEDULER = False

app   = Flask(__name__)
_state = {"result": None, "dl_result": None}

# ── Versi aplikasi (dari git) ────────────────────────────────
def get_version():
    try:
        work = str(Path(__file__).parent)
        v = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=work, stderr=subprocess.DEVNULL, timeout=5
        ).decode().strip()
        d = subprocess.check_output(
            ["git", "log", "-1", "--format=%cd", "--date=format:%d %b %Y %H:%M"],
            cwd=work, stderr=subprocess.DEVNULL, timeout=5
        ).decode().strip()
        return v, d
    except Exception:
        # Fallback: baca versi dari file jika git tidak tersedia
        ver_file = Path(__file__).parent / ".version"
        if ver_file.exists():
            v = ver_file.read_text().strip()
            return v, ""
        return "-", ""

# ── Schedule job ─────────────────────────────────────────────
def _run_scheduled_job():
    cfg = core.load_config()
    save_dir = cfg.get("source_dir", "/sdcard/Download/galva_docs")
    username = cfg.get("xea_username", "")
    password = cfg.get("xea_password", "")
    if not username or not password:
        return
    today     = date.today()
    from datetime import timedelta
    date_from = today.replace(day=1)
    date_to   = today
    dl.run_download(username, password, date_from, date_to, save_dir)
    core.run_merge(cfg["source_dir"], cfg["output_dir"], cfg.get("digit_count", 6))

def _apply_schedule():
    if not _HAS_SCHEDULER:
        return
    _scheduler.remove_all_jobs()
    cfg = core.load_config()
    if not cfg.get("schedule_enabled"):
        return
    t    = cfg.get("schedule_time", "08:00").split(":")
    days = cfg.get("schedule_days", [1,2,3,4,5])
    day_map = {0:"sun",1:"mon",2:"tue",3:"wed",4:"thu",5:"fri",6:"sat"}
    dow = ",".join(day_map[d] for d in days if d in day_map)
    if not dow:
        return
    _scheduler.add_job(
        _run_scheduled_job, CronTrigger(
            hour=int(t[0]), minute=int(t[1]), day_of_week=dow
        ), id="auto_job", replace_existing=True
    )

_apply_schedule()

# ─────────────────────────────────────────────────────────────
# HTML
# ─────────────────────────────────────────────────────────────
HTML = r"""
<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>XEA Tools</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
:root{
  --bg:#f0f4f8;--surface:#ffffff;--card:#ffffff;
  --navy:#1a3c5e;--teal:#0891b2;--lteal:#e0f7ff;
  --green:#059669;--lgreen:#d1fae5;--orange:#ea580c;
  --red:#dc2626;--gray:#64748b;--lgray:#f0f4f8;
  --dark:#0f172a;--white:#ffffff;
  --border:#e2e8f0;--text:#0f172a;--muted:#64748b;
  --input-bg:#f0f4f8;
  --transition: background .25s, color .25s, border-color .25s;
}
[data-theme="dark"]{
  --bg:#0a0f1e;--surface:#111827;--card:#161f35;
  --navy:#0f172a;--lgray:#1e293b;
  --dark:#e2e8f0;--white:#1e293b;
  --border:#1e3a5f;--text:#e2e8f0;--muted:#64748b;
  --input-bg:#1e293b;
}
*{box-sizing:border-box;margin:0;padding:0;transition:background .2s,color .2s,border-color .2s}
body{font-family:'Segoe UI',sans-serif;background:var(--lgray);color:var(--dark);min-height:100vh}
[data-theme="dark"]{
  --navy:#0f172a;--lgray:#0f172a;--white:#1e293b;--dark:#e2e8f0;--gray:#94a3b8;
  --border-color:#1e3a5f;
}
[data-theme="dark"] body{background:#0a0f1e;color:#e2e8f0}
[data-theme="dark"] .card{background:#111827;border-color:#1e3a5f}
[data-theme="dark"] .card-body{background:#111827;color:#e2e8f0}
[data-theme="dark"] input[type=text],[data-theme="dark"] input[type=email],
[data-theme="dark"] input[type=password],[data-theme="dark"] input[type=date],
[data-theme="dark"] input[type=time],[data-theme="dark"] input[type=number]{
  background:#1e293b;color:#e2e8f0;border-color:#1e3a5f}
[data-theme="dark"] .file-list,[data-theme="dark"] .day-btn{background:#1e293b;border-color:#1e3a5f}
[data-theme="dark"] #log-box,[data-theme="dark"] #dl-log-box{background:#020817}
[data-theme="dark"] table td{border-color:#1e3a5f}
[data-theme="dark"] tr:nth-child(even) td{background:#1e293b}
[data-theme="dark"] .stat{background:#111827;border-color:#1e3a5f}
[data-theme="dark"] .stat-num{color:#67e8f9}
[data-theme="dark"] .alert-info{background:rgba(8,145,178,.15);color:#67e8f9}
[data-theme="dark"] .alert-success{background:rgba(5,150,105,.15);color:#34d399}
[data-theme="dark"] .alert-warn{background:rgba(234,88,12,.15);color:#fb923c}
[data-theme="dark"] .alert-error{background:rgba(220,38,38,.15);color:#f87171}
[data-theme="dark"] pre{background:#020817;color:#e2e8f0}
.theme-btn{background:none;border:1px solid #334155;color:#94a3b8;
  padding:5px 10px;border-radius:6px;font-size:.8rem;cursor:pointer;margin-left:auto}
.theme-btn:hover{border-color:var(--teal);color:var(--teal)}
.header{background:var(--navy);color:var(--white);padding:12px 16px;position:sticky;top:0;z-index:99;
  display:flex;align-items:center;gap:10px;border-bottom:3px solid var(--teal)}
.header h1{font-size:1.1rem;font-weight:700;color:var(--teal)}
.header span{font-size:.75rem;color:#94a3b8}
.tabs{display:flex;background:var(--navy);padding:0 12px;gap:2px;overflow-x:auto}
.tab{padding:9px 14px;font-size:.8rem;color:#94a3b8;border-bottom:3px solid transparent;
  cursor:pointer;transition:.2s;white-space:nowrap;flex-shrink:0}
.tab.active{color:var(--teal);border-bottom-color:var(--teal);font-weight:600}
.section{display:none;padding:14px;max-width:680px;margin:0 auto}
.section.active{display:block}
.card{background:var(--white);border-radius:12px;border:1px solid #e2e8f0;
  margin-bottom:12px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.06)}
.card-header{background:var(--navy);color:var(--white);padding:10px 14px;
  font-weight:600;font-size:.88rem;border-left:4px solid var(--teal)}
.card-body{padding:14px}
label{display:block;font-size:.8rem;color:var(--gray);font-weight:600;
  margin-bottom:4px;margin-top:10px}
input[type=text],input[type=email],input[type=password],input[type=number],
input[type=date],input[type=time]{
  width:100%;padding:10px 12px;border:1px solid #cbd5e1;border-radius:8px;
  font-size:.9rem;background:var(--lgray);transition:.2s}
input:focus{outline:none;border-color:var(--teal);background:var(--white);
  box-shadow:0 0 0 3px rgba(8,145,178,.15)}
.row2{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.btn{display:inline-flex;align-items:center;gap:7px;padding:11px 20px;
  border:none;border-radius:9px;font-size:.88rem;font-weight:600;cursor:pointer;transition:.2s}
.btn-primary{background:var(--teal);color:var(--white)}
.btn-primary:hover{background:#0e7490}
.btn-primary:disabled{background:var(--gray);cursor:not-allowed}
.btn-success{background:var(--green);color:var(--white)}
.btn-success:hover{background:#047857}
.btn-danger{background:var(--red);color:var(--white)}
.btn-outline{background:transparent;color:var(--teal);border:2px solid var(--teal)}
.btn-outline:hover{background:var(--lteal)}
.btn-row{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
#log-box,#dl-log-box{background:#1e293b;color:#e2e8f0;border-radius:10px;padding:12px;
  font-family:monospace;font-size:.8rem;height:300px;overflow-y:auto;
  white-space:pre-wrap;line-height:1.55}
.log-ok{color:#34d399}.log-warn{color:#fbbf24}.log-fail{color:#f87171}
.log-info{color:#67e8f9}.log-dim{color:#64748b}
.progress-wrap{background:#e2e8f0;border-radius:99px;height:8px;margin:10px 0;overflow:hidden}
.progress-bar{background:var(--teal);height:100%;border-radius:99px;transition:width .4s}
table{width:100%;border-collapse:collapse;font-size:.86rem}
th{background:var(--navy);color:var(--white);padding:8px 12px;text-align:left;font-weight:600}
td{padding:8px 12px;border-bottom:1px solid #e2e8f0}
tr:nth-child(even) td{background:var(--lgray)}
.badge{display:inline-block;padding:2px 8px;border-radius:99px;font-size:.73rem;font-weight:600}
.badge-teal{background:var(--lteal);color:var(--teal)}
.stats{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-bottom:12px}
.stat{background:var(--white);border-radius:10px;padding:12px 14px;
  border-left:4px solid var(--teal);box-shadow:0 1px 3px rgba(0,0,0,.06)}
.stat-num{font-size:1.5rem;font-weight:700;color:var(--navy)}
.stat-lbl{font-size:.73rem;color:var(--gray);margin-top:2px}
.alert{padding:10px 14px;border-radius:8px;margin:10px 0;font-size:.85rem}
.alert-info{background:var(--lteal);color:var(--teal)}
.alert-success{background:var(--lgreen);color:var(--green)}
.alert-warn{background:#fff7ed;color:var(--orange)}
.alert-error{background:#fef2f2;color:var(--red)}
.file-list{background:var(--lgray);border-radius:8px;padding:10px 14px;
  max-height:180px;overflow-y:auto;margin:8px 0}
.file-item{padding:4px 0;font-size:.81rem;border-bottom:1px solid #e2e8f0}
.file-item:last-child{border:none}
.spinner{display:inline-block;width:14px;height:14px;border:2px solid #fff;
  border-top-color:transparent;border-radius:50%;animation:spin .7s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.toggle-row{display:flex;align-items:center;justify-content:space-between;
  padding:10px 0;border-bottom:1px solid #e2e8f0}
.toggle-row:last-child{border:none}
.toggle{position:relative;width:46px;height:26px}
.toggle input{opacity:0;width:0;height:0}
.slider{position:absolute;inset:0;background:#cbd5e1;border-radius:99px;cursor:pointer;transition:.3s}
.slider:before{content:'';position:absolute;width:20px;height:20px;left:3px;bottom:3px;
  background:white;border-radius:50%;transition:.3s}
input:checked+.slider{background:var(--teal)}
input:checked+.slider:before{transform:translateX(20px)}
.day-grid{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}
.day-btn{padding:6px 12px;border-radius:8px;border:1px solid #cbd5e1;background:var(--lgray);
  font-size:.8rem;cursor:pointer;transition:.2s}
.day-btn.active{background:var(--teal);color:white;border-color:var(--teal)}
.version-tag{font-family:monospace;font-size:.75rem;background:rgba(255,255,255,.1);
  padding:2px 8px;border-radius:4px;color:#94a3b8}
.hidden{display:none!important}
.mt8{margin-top:8px}.mt12{margin-top:12px}.dim{color:var(--gray)}
.bold{font-weight:700}.teal{color:var(--teal)}.green{color:var(--green)}.red{color:var(--red)}
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>XEA Tools</h1>
    <span>PT Galva Technologies Tbk</span>
  </div>
  <span class="version-tag" id="ver-tag" style="margin-left:auto">v–</span>
  <button class="theme-btn" onclick="toggleTheme()" id="theme-btn">🌙</button>
</div>

<div class="tabs">
  <div class="tab active" onclick="showTab('download')">📥 Download</div>
  <div class="tab" onclick="showTab('cari')">🔍 Cari</div>
  <div class="tab" onclick="showTab('merge')">▶ Merge</div>
  <div class="tab" onclick="showTab('statistik')">📊 Statistik</div>
  <div class="tab" onclick="showTab('schedule')">⏰ Schedule</div>
  <div class="tab" onclick="showTab('config')">⚙ Konfigurasi</div>
  <div class="tab" onclick="showTab('logmerge')">📋 Log</div>
</div>

<!-- ══════════ TAB: DOWNLOAD ══════════ -->
<div id="tab-download" class="section active">
  <div id="dl-akun-info" class="card">
    <div class="card-header">🔑 Akun Galva XEA</div>
    <div class="card-body" id="dl-akun-body" style="font-size:.85rem;color:var(--gray)">
      Memuat...
    </div>
  </div>

  <div class="card">
    <div class="card-header">📅 Rentang Tanggal & Filter</div>
    <div class="card-body">
      <div class="row2">
        <div>
          <label>Dari Tanggal</label>
          <input type="date" id="dl-dari">
        </div>
        <div>
          <label>Sampai Tanggal</label>
          <input type="date" id="dl-sampai">
        </div>
      </div>
      <label>Tipe Pekerjaan</label>
      <div class="day-grid" style="margin-bottom:8px">
        <div class="day-btn active" data-type="MAIN" onclick="toggleType(this)">Maintenance</div>
        <div class="day-btn active" data-type="SERV" onclick="toggleType(this)">Service</div>
        <div class="day-btn active" data-type="INST" onclick="toggleType(this)">Install</div>
        <div class="day-btn active" data-type="TKRP" onclick="toggleType(this)">Take Report</div>
      </div>
      <div class="btn-row">
        <button class="btn btn-primary" id="btn-dl" onclick="startDownload()">
          📥 Mulai Download
        </button>
        <button class="btn btn-outline" onclick="clearDlLog()">🗑 Bersihkan</button>
      </div>
    </div>
  </div>

  <div class="card">
    <div class="card-header">📋 Log Download</div>
    <div class="card-body">
      <div id="dl-progress-wrap" class="progress-wrap hidden">
        <div id="dl-progress-bar" class="progress-bar" style="width:0%"></div>
      </div>
      <div id="dl-log-box">Siap mengunduh dokumen...\n</div>
      <div id="dl-result-stats" class="hidden" style="margin-top:10px"></div>
      <div id="dl-lanjut-wrap" class="hidden" style="margin-top:10px">
        <button class="btn btn-success" style="width:100%;justify-content:center"
          onclick="lanjutMerge()">▶ Lanjut ke Merge</button>
      </div>
    </div>
  </div>

  <div class="card">
    <div class="card-header">📁 File di Folder Sumber</div>
    <div class="card-body">
      <div id="dl-history-info" style="font-size:.82rem;color:var(--gray);margin-bottom:8px">
        Memuat...
      </div>
      <div id="dl-history-list" class="file-list hidden"></div>
      <div class="btn-row mt8">
        <button class="btn btn-outline" style="font-size:.8rem;padding:8px 14px"
          onclick="loadDlHistory()">🔄 Refresh</button>
      </div>
    </div>
  </div>
</div>

<!-- ══════════ TAB: MERGE ══════════ -->
<div id="tab-merge" class="section">
  <div id="cfg-info" class="card">
    <div class="card-header">📂 Konfigurasi Aktif</div>
    <div class="card-body" id="cfg-info-body" style="font-size:.85rem;color:var(--gray)">
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
        <button class="btn btn-primary" id="btn-run" onclick="startMerge()">▶ Mulai Merge</button>
        <button class="btn btn-outline" onclick="clearLog()">🗑 Bersihkan Log</button>
      </div>
    </div>
  </div>

  <div id="result-section" class="hidden">
    <div class="card">
      <div class="card-header">📊 Hasil Merge</div>
      <div class="card-body">
        <div class="stats" id="stats-grid"></div>
        <table id="summary-table">
          <thead><tr><th>Tipe Layanan</th><th>Jumlah</th><th>Nilai Total</th></tr></thead>
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
          <button class="btn btn-success" onclick="sendEmails()">📧 Ya, Kirim Email</button>
          <button class="btn btn-outline" onclick="cancelEmail()">✕ Lewati</button>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- ══════════ TAB: CARI ══════════ -->
<div id="tab-cari" class="section">
  <div class="card">
    <div class="card-header">🔍 Cari Order Berdasarkan Perusahaan</div>
    <div class="card-body">
      <label>Nama Perusahaan / Pelanggan</label>
      <div style="display:flex;gap:8px;margin-top:4px">
        <input type="text" id="cari-keyword" placeholder="PT HON CHUAN, BANK MANDIRI, ..."
          onkeydown="if(event.key==='Enter') cariOrder()">
        <button class="btn btn-primary" onclick="cariOrder()" style="flex-shrink:0">🔍 Cari</button>
      </div>
      <div class="alert alert-info mt8" style="font-size:.8rem">
        Cari dilakukan langsung ke API Galva XEA. Hasil menampilkan status download & merge.
      </div>
    </div>
  </div>

  <div id="cari-loading" class="hidden">
    <div class="alert alert-info"><span class="spinner"></span> Mencari...</div>
  </div>

  <div id="cari-result" class="hidden">
    <div class="card">
      <div class="card-header" id="cari-result-header">Hasil Pencarian</div>
      <div class="card-body" style="padding:0">
        <table>
          <thead>
            <tr>
              <th>Nomor Order</th>
              <th>Tipe</th>
              <th>Status</th>
              <th>Download</th>
            </tr>
          </thead>
          <tbody id="cari-tbody"></tbody>
        </table>
      </div>
    </div>
  </div>

  <div id="cari-empty" class="hidden">
    <div class="alert alert-warn">Tidak ada order ditemukan untuk kata kunci tersebut.</div>
  </div>
</div>

<!-- ══════════ TAB: STATISTIK ══════════ -->
<div id="tab-statistik" class="section">
  <div class="card">
    <div class="card-header">📊 Statistik Merge per Bulan</div>
    <div class="card-body">
      <div id="statistik-meta" style="font-size:.82rem;color:var(--gray);margin-bottom:12px">
        Memuat...
      </div>
      <canvas id="statistik-chart" style="max-height:320px"></canvas>
      <div class="btn-row mt12">
        <button class="btn btn-outline" onclick="loadStatistik()">🔄 Refresh</button>
      </div>
    </div>
  </div>

  <div id="statistik-table-wrap" class="card hidden">
    <div class="card-header">📋 Detail per Bulan</div>
    <div class="card-body" style="padding:0">
      <table>
        <thead>
          <tr>
            <th>Bulan</th>
            <th>Install</th>
            <th>Maintenance</th>
            <th>Repair/Service</th>
            <th>Take Report</th>
            <th>Total</th>
          </tr>
        </thead>
        <tbody id="statistik-tbody"></tbody>
      </table>
    </div>
  </div>
</div>

<!-- ══════════ TAB: SCHEDULE ══════════ -->
<div id="tab-schedule" class="section">
  <div class="card">
    <div class="card-header">⏰ Jadwal Otomatis</div>
    <div class="card-body">
      <div class="toggle-row">
        <div>
          <div style="font-weight:600;font-size:.9rem">Aktifkan Jadwal</div>
          <div class="dim" style="font-size:.78rem">Download + Merge otomatis sesuai jadwal</div>
        </div>
        <label class="toggle">
          <input type="checkbox" id="sch-enabled" onchange="toggleSchedule()">
          <span class="slider"></span>
        </label>
      </div>

      <div id="sch-options">
        <label>Waktu Mulai</label>
        <input type="time" id="sch-time" value="08:00" style="max-width:160px">

        <label>Hari Aktif</label>
        <div class="day-grid" id="day-grid">
          <div class="day-btn" data-day="1" onclick="toggleDay(this)">Sen</div>
          <div class="day-btn" data-day="2" onclick="toggleDay(this)">Sel</div>
          <div class="day-btn" data-day="3" onclick="toggleDay(this)">Rab</div>
          <div class="day-btn" data-day="4" onclick="toggleDay(this)">Kam</div>
          <div class="day-btn" data-day="5" onclick="toggleDay(this)">Jum</div>
          <div class="day-btn" data-day="6" onclick="toggleDay(this)">Sab</div>
          <div class="day-btn" data-day="0" onclick="toggleDay(this)">Min</div>
        </div>

        <div class="alert alert-info mt12">
          ℹ Jadwal akan mengunduh dokumen bulan berjalan lalu menjalankan merge otomatis.
          Pastikan akun Galva XEA sudah dikonfigurasi.
        </div>
      </div>

      <div class="btn-row mt12">
        <button class="btn btn-primary" onclick="saveSchedule()">💾 Simpan Jadwal</button>
      </div>
      <div id="sch-status" class="mt8"></div>
    </div>
  </div>

  <div class="card">
    <div class="card-header">📋 Status Scheduler</div>
    <div class="card-body" id="sch-info" style="font-size:.85rem;color:var(--gray)">
      Memuat...
    </div>
  </div>
</div>

<!-- ══════════ TAB: KONFIGURASI ══════════ -->
<div id="tab-config" class="section">

  <div class="card">
    <div class="card-header">📂 Folder</div>
    <div class="card-body">
      <label>Folder Sumber (hasil download / PDF mentah)</label>
      <input type="text" id="c-source" placeholder="/sdcard/Download/galva_docs">
      <label>Folder Output (hasil merge)</label>
      <input type="text" id="c-output" placeholder="/sdcard/Documents/Hasil">
    </div>
  </div>

  <div class="card">
    <div class="card-header">🔑 Akun Galva XEA</div>
    <div class="card-body">
      <label>Username</label>
      <input type="text" id="c-xea-user" placeholder="depo.surabaya.iii" autocomplete="off">
      <label>Password</label>
      <input type="password" id="c-xea-pass" placeholder="••••••••" autocomplete="off">
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
      <input type="text" id="c-to">
      <label>CC (opsional)</label>
      <input type="text" id="c-cc">
      <label>BCC (opsional)</label>
      <input type="text" id="c-bcc">
      <div class="btn-row mt12">
        <button class="btn btn-primary" onclick="saveConfig()">💾 Simpan Konfigurasi</button>
      </div>
      <div id="config-status" class="mt8"></div>
    </div>
  </div>

  <div class="card">
    <div class="card-header">🔄 Update Aplikasi</div>
    <div class="card-body">
      <div id="update-info" style="font-size:.85rem;color:var(--gray)">Memuat versi...</div>
      <div class="btn-row mt12">
        <button class="btn btn-outline" onclick="checkUpdate()">🔍 Cek Update</button>
        <button class="btn btn-success hidden" id="btn-apply-update" onclick="applyUpdate()">
          ⬇ Terapkan Update
        </button>
      </div>
      <div id="update-status" class="mt8"></div>
    </div>
  </div>

  <div class="card">
    <div class="card-header">💡 Cara Buat App Password Gmail</div>
    <div class="card-body" style="font-size:.83rem;color:var(--gray);line-height:1.7">
      1. Buka <strong>myaccount.google.com</strong><br>
      2. Keamanan → <strong>2-Step Verification</strong> (aktifkan)<br>
      3. Cari <strong>App Passwords</strong> → buat baru<br>
      4. Salin 16 karakter → tempel ke kolom App Password di atas
    </div>
  </div>
</div>

<!-- ══════════ TAB: LOG MERGE ══════════ -->
<div id="tab-logmerge" class="section">

  <div class="card">
    <div class="card-header">📋 Log Merge per Tipe Layanan</div>
    <div class="card-body">
      <div id="logmerge-meta" style="font-size:.8rem;color:var(--gray);margin-bottom:10px">
        Memuat...
      </div>

      <!-- Filter per tipe -->
      <div id="logmerge-filter" class="day-grid" style="margin-bottom:12px"></div>

      <!-- Isi log -->
      <pre id="logmerge-content"
           style="font-size:.78rem;font-family:monospace;white-space:pre-wrap;
                  color:var(--dark);line-height:1.65;background:var(--lgray);
                  padding:12px;border-radius:8px;max-height:460px;overflow-y:auto">
Belum ada log. Jalankan merge terlebih dahulu.</pre>

      <div class="btn-row mt12">
        <button class="btn btn-outline" onclick="loadLogMerge()">🔄 Refresh</button>
        <button class="btn btn-outline" onclick="searchLogMerge()"
          style="font-size:.8rem">🔍 Cari Nomor</button>
      </div>
      <div id="logmerge-search" class="hidden mt8">
        <input type="text" id="logmerge-keyword" placeholder="Ketik nomor order / nama pelanggan..."
          oninput="filterLogContent()">
      </div>
    </div>
  </div>

  <div class="card">
    <div class="card-header">ℹ Tentang Log Ini</div>
    <div class="card-body" style="font-size:.82rem;color:var(--gray);line-height:1.7">
      Log disimpan di <code style="font-family:monospace">/sdcard/Documents/log_merge.txt</code><br>
      Bersifat <b>append</b> — setiap merge menambah entri baru di bawah.<br>
      Gunakan log ini untuk <b>recheck</b> apakah nomor order sudah pernah diproses sebelumnya.
    </div>
  </div>
</div>

<!-- ═════════════════════════════════════ -->
<script>
const HARGA = {
  "Install":199000,"Maintenance":86000,"Repair - Service":119000,"Take Report":43000
};
let currentResult = null;

// ── Dark Mode ──────────────────────────────────────────────
function initTheme() {
  const saved = localStorage.getItem('xea-theme');
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  const theme = saved || (prefersDark ? 'dark' : 'light');
  setTheme(theme);
}
function setTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  const btn = document.getElementById('theme-btn');
  if (btn) btn.textContent = theme === 'dark' ? '☀️' : '🌙';
  localStorage.setItem('xea-theme', theme);
}
function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme') || 'light';
  setTheme(current === 'dark' ? 'light' : 'dark');
}

// ── Tab ────────────────────────────────────────────────────
function showTab(name) {
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  event.target.classList.add('active');
  if (name === 'config')    loadConfig();
  if (name === 'logmerge')  loadLogMerge();
  if (name === 'schedule')  loadSchedule();
  if (name === 'download')  loadDlInfo();
  if (name === 'merge')     loadCfgInfo();
  if (name === 'statistik') loadStatistik();
  if (name === 'cari')      document.getElementById('cari-keyword').focus();
}

function toggleType(el) {
  el.classList.toggle('active');
}

function getSelectedTypes() {
  return [...document.querySelectorAll('.day-btn[data-type].active')]
    .map(b => b.dataset.type);
}

// ── Cari ───────────────────────────────────────────────────
function cariOrder() {
  const kw = document.getElementById('cari-keyword').value.trim();
  if (!kw) return;

  document.getElementById('cari-loading').classList.remove('hidden');
  document.getElementById('cari-result').classList.add('hidden');
  document.getElementById('cari-empty').classList.add('hidden');

  fetch(`/api/search?q=${encodeURIComponent(kw)}`)
    .then(r => r.json())
    .then(r => {
      document.getElementById('cari-loading').classList.add('hidden');
      const results = r.results || [];
      if (results.length === 0) {
        document.getElementById('cari-empty').classList.remove('hidden');
        return;
      }
      document.getElementById('cari-result-header').textContent =
        `Hasil Pencarian "${kw}" — ${results.length} order`;
      const statusColor = { merged:'var(--green)', downloaded:'var(--teal)', new:'var(--gray)' };
      const statusLabel = { merged:'✓ Dimerge', downloaded:'↓ Diunduh', new:'● Baru' };
      document.getElementById('cari-tbody').innerHTML = results.map(o =>
        `<tr>
          <td style="font-family:monospace;font-size:.82rem">${o.number}</td>
          <td>${o.type_name||o.type_code}</td>
          <td style="font-size:.8rem">${o.status}</td>
          <td><span style="color:${statusColor[o.dl_status]};font-size:.8rem;font-weight:600">
            ${statusLabel[o.dl_status]}</span></td>
        </tr>`
      ).join('');
      document.getElementById('cari-result').classList.remove('hidden');
    })
    .catch(() => {
      document.getElementById('cari-loading').classList.add('hidden');
      document.getElementById('cari-empty').innerHTML =
        '<div class="alert alert-error">Gagal menghubungi server.</div>';
      document.getElementById('cari-empty').classList.remove('hidden');
    });
}

// ── Statistik ──────────────────────────────────────────────
let _chartInstance = null;
function loadStatistik() {
  document.getElementById('statistik-meta').textContent = 'Memuat...';
  fetch('/api/statistik').then(r => r.json()).then(r => {
    if (!r.months || r.months.length === 0) {
      document.getElementById('statistik-meta').textContent =
        'Belum ada data. Jalankan merge terlebih dahulu.';
      return;
    }
    document.getElementById('statistik-meta').innerHTML =
      `<b>${r.total_all}</b> pekerjaan tercatat sejak <b>${r.months[0]}</b>`;

    const colors = {
      'Install'        : '#0891b2',
      'Maintenance'    : '#059669',
      'Repair - Service':'#ea580c',
      'Take Report'    : '#7c3aed',
    };
    const tipes = ['Install','Maintenance','Repair - Service','Take Report'];

    if (_chartInstance) _chartInstance.destroy();
    const ctx = document.getElementById('statistik-chart').getContext('2d');
    _chartInstance = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: r.months,
        datasets: tipes.map(t => ({
          label: t,
          data: r.months.map(m => (r.data[m] || {})[t] || 0),
          backgroundColor: colors[t] + 'cc',
          borderColor: colors[t],
          borderWidth: 1,
          borderRadius: 4,
        }))
      },
      options: {
        responsive: true,
        plugins: {
          legend: { position: 'bottom',
            labels: { color: document.documentElement.getAttribute('data-theme') === 'dark'
              ? '#e2e8f0' : '#0f172a', font: { size: 11 } }
          }
        },
        scales: {
          x: { stacked: true,
            ticks: { color: document.documentElement.getAttribute('data-theme') === 'dark'
              ? '#e2e8f0' : '#0f172a' }},
          y: { stacked: true, beginAtZero: true,
            ticks: { color: document.documentElement.getAttribute('data-theme') === 'dark'
              ? '#e2e8f0' : '#0f172a' }}
        }
      }
    });

    // Tabel detail
    const tbody = document.getElementById('statistik-tbody');
    tbody.innerHTML = r.months.map(m => {
      const d = r.data[m] || {};
      const total = tipes.reduce((s, t) => s + (d[t]||0), 0);
      return `<tr>
        <td><b>${m}</b></td>
        ${tipes.map(t => `<td>${d[t]||0}</td>`).join('')}
        <td><b>${total}</b></td>
      </tr>`;
    }).join('');
    document.getElementById('statistik-table-wrap').classList.remove('hidden');
  }).catch(() => {
    document.getElementById('statistik-meta').textContent = 'Gagal memuat statistik.';
  });
}
function loadVersion() {
  fetch('/api/version').then(r=>r.json()).then(r=>{
    document.getElementById('ver-tag').textContent = 'v' + r.version;
    const el = document.getElementById('update-info');
    if (el) el.innerHTML =
      `<b>Versi saat ini:</b> ${r.version}<br><span class="dim">${r.date}</span>`;
  }).catch(()=>{});
}

// ── Download ───────────────────────────────────────────────
function loadDlInfo() {
  fetch('/api/config').then(r=>r.json()).then(cfg=>{
    const user = cfg.xea_username || '';
    const el   = document.getElementById('dl-akun-body');
    if (user) {
      el.innerHTML = `<b>Username:</b> ${user}<br><span class="dim">Password: ••••••••</span>`;
    } else {
      el.innerHTML = '<span style="color:var(--orange)">⚠ Akun XEA belum dikonfigurasi — isi di tab Konfigurasi</span>';
    }
  });
  const today = new Date();
  const y = today.getFullYear(), m = String(today.getMonth()+1).padStart(2,'0');
  const d = String(today.getDate()).padStart(2,'0');
  document.getElementById('dl-dari').value   = `${y}-${m}-01`;
  document.getElementById('dl-sampai').value = `${y}-${m}-${d}`;
  loadDlHistory();
}

function appendDlLog(msg, cls='') {
  const box  = document.getElementById('dl-log-box');
  const span = document.createElement('span');
  if (cls) span.className = cls;
  span.textContent = msg + '\n';
  box.appendChild(span);
  box.scrollTop = box.scrollHeight;
}

function clearDlLog() {
  document.getElementById('dl-log-box').innerHTML = '';
  document.getElementById('dl-result-stats').classList.add('hidden');
  document.getElementById('dl-progress-wrap').classList.add('hidden');
}

function startDownload() {
  const dari   = document.getElementById('dl-dari').value;
  const sampai = document.getElementById('dl-sampai').value;
  if (!dari || !sampai) { alert('Isi rentang tanggal terlebih dahulu'); return; }

  const types = getSelectedTypes();
  if (types.length === 0) { alert('Pilih minimal satu tipe pekerjaan'); return; }

  const btn = document.getElementById('btn-dl');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Mengunduh...';
  document.getElementById('dl-log-box').innerHTML = '';
  document.getElementById('dl-result-stats').classList.add('hidden');
  document.getElementById('dl-lanjut-wrap').classList.add('hidden');
  document.getElementById('dl-progress-wrap').classList.remove('hidden');
  document.getElementById('dl-progress-bar').style.width = '5%';

  let qualified = 0; let done = 0;
  const typeParam = types.join(',');
  const es = new EventSource(`/api/download?dari=${dari}&sampai=${sampai}&types=${typeParam}`);
  es.onmessage = function(e) {
    const ev = JSON.parse(e.data);
    const t = ev.type; const d = ev.data;

    if (t === 'login')      appendDlLog(`🔐 Login sebagai ${d.username}...`, 'log-info');
    else if (t === 'login_ok')   appendDlLog(`✓ Login berhasil (keyUserId: ${d.key_user_id})`, 'log-ok');
    else if (t === 'login_fail') appendDlLog(`✗ Login gagal: ${d.msg}`, 'log-fail');
    else if (t === 'fetch')      appendDlLog(`⟳ ${d.msg}`, 'log-info');
    else if (t === 'scan') {
      qualified = d.qualified;
      appendDlLog(`📋 Total order: ${d.total}  |  Diproses: ${d.qualified}  |  Skip status: ${d.skipped_status}  |  Skip tanggal: ${d.skipped_date}`, 'log-info');
      appendDlLog('');
    }
    else if (t === 'download_ok') {
      done++;
      appendDlLog(`✓  ${d.filename}  —  ${d.customer}`, 'log-ok');
      if (qualified > 0)
        document.getElementById('dl-progress-bar').style.width =
          Math.min(95, Math.round(done/qualified*90)+5) + '%';
    }
    else if (t === 'download_skip') {
      const reason = d.reason === 'sudah diproses saat FN'
        ? '(Repair/Service — sudah diunduh saat status Finish)'
        : '(sudah ada)';
      appendDlLog(`–  ${d.filename} ${reason}`, 'log-dim');
    }
    else if (t === 'download_fail') appendDlLog(`✗  ${d.number} ${d.doc_code} — ${d.msg||''}`, 'log-fail');
    else if (t === 'error')         appendDlLog(`ERROR: ${d.msg}`, 'log-fail');
    else if (t === 'done') {
      document.getElementById('dl-progress-bar').style.width = '100%';
      appendDlLog('');
      appendDlLog(`══ Selesai ══  Diunduh: ${d.saved}  Skip: ${d.skipped}  Gagal: ${d.failed}`, 'log-info');
      if (d.skipped > 0)
        appendDlLog(`  ℹ ${d.skipped} file dilewati — sudah pernah diunduh sebelumnya`, 'log-dim');
      document.getElementById('dl-result-stats').className = 'alert alert-' + (d.saved > 0 ? 'success' : 'warn');
      document.getElementById('dl-result-stats').innerHTML =
        d.saved > 0
          ? `✓ ${d.saved} file berhasil diunduh ke ${d.save_dir}`
          : `⚠ Tidak ada file baru. ${d.skipped} sudah ada, ${d.failed} gagal.`;
      document.getElementById('dl-result-stats').classList.remove('hidden');
      // Tombol lanjut ke merge — muncul selalu setelah download selesai
      document.getElementById('dl-lanjut-wrap').classList.remove('hidden');
      es.close();
      btn.disabled = false;
      btn.innerHTML = '📥 Mulai Download';
      setTimeout(()=>{ document.getElementById('dl-progress-wrap').classList.add('hidden'); }, 1500);
      loadDlHistory();
    }
  };
  es.onerror = function() {
    appendDlLog('Koneksi terputus.', 'log-fail');
    es.close();
    btn.disabled = false;
    btn.innerHTML = '📥 Mulai Download';
  };
}

function lanjutMerge() {
  // Pindah ke tab Merge dan sembunyikan tombol lanjut
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-merge').classList.add('active');
  document.querySelectorAll('.tab')[1].classList.add('active');
  document.getElementById('dl-lanjut-wrap').classList.add('hidden');
  loadCfgInfo();
}

function loadDlHistory() {
  fetch('/api/download/files').then(r=>r.json()).then(r=>{
    const info = document.getElementById('dl-history-info');
    const list = document.getElementById('dl-history-list');
    if (!r.files || r.files.length === 0) {
      info.innerHTML = '<span class="dim">Belum ada file di folder sumber.</span>';
      list.classList.add('hidden');
      return;
    }
    const stba  = r.files.filter(f => f.includes('_STBA'));
    const stats = r.files.filter(f => f.includes('_STATS') || f.includes('_STAT'));
    info.innerHTML =
      `<b>${r.files.length}</b> file PDF di folder sumber &nbsp;·&nbsp; ` +
      `<span class="teal">${stba.length} STBA</span> &nbsp;·&nbsp; ` +
      `<span style="color:var(--green)">${stats.length} STAT</span>`;
    list.innerHTML = r.files.map(f =>
      `<div class="file-item">📄 ${f}</div>`
    ).join('');
    list.classList.remove('hidden');
  }).catch(()=>{
    document.getElementById('dl-history-info').innerHTML =
      '<span class="dim">Tidak bisa memuat daftar file.</span>';
  });
}

// ── Merge ──────────────────────────────────────────────────
function loadCfgInfo() {
  fetch('/api/config').then(r=>r.json()).then(cfg=>{
    const el = document.getElementById('cfg-info-body');
    if (el) el.innerHTML =
      `<b>Sumber:</b> ${cfg.source_dir||'-'}<br><b>Output:</b> ${cfg.output_dir||'-'}`;
  });
}

function appendLog(msg, cls='') {
  const box  = document.getElementById('log-box');
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
    const t = ev.type; const d = ev.data;
    if (t==='scan')       appendLog(`🔍 Scan: ${d.total} file PDF ditemukan`, 'log-info');
    else if (t==='cleanup') {
      if (d.jumlah > 0)
        appendLog(`🗑 ${d.jumlah} file duplikat dihapus: ${d.deleted.join(', ')}`, 'log-warn');
    }
    else if (t==='log_check') {
      appendLog(`📋 log_merge.txt: ${d.total_processed} key sudah pernah diproses`, 'log-dim');
    }
    else if (t==='merge_skip') {
      appendLog(`⏭  [${d.key}] dilewati — ${d.reason}`, 'log-warn');
    }
    else if (t==='classify')   appendLog(`📂 STBA:${d.stba}  STATS:${d.stats}  Unknown:${d.unknown}`, 'log-info');
    else if (t==='pair_found') {
      totalPairs = d.pairs;
      appendLog(`🔗 Cocok:${d.pairs}  |  Hanya STBA:${d.only_stba}  |  Hanya STATS:${d.only_stats}`, 'log-info');
      appendLog('');
    }
    else if (t==='merge_ok') {
      done++;
      appendLog(`✓  [${d.key}]  ${d.nama}  →  ${d.folder}/`, 'log-ok');
      if (totalPairs > 0)
        document.getElementById('progress-bar').style.width =
          Math.min(95, Math.round(done/totalPairs*90)+5) + '%';
    }
    else if (t==='merge_fail')  appendLog(`✗  [${d.key}] Gagal merge`, 'log-fail');
    else if (t==='file_kosong') appendLog(`⚠  ${d.name} → File Kosong/`, 'log-warn');
    else if (t==='arsip')       appendLog(`📦 ${d.jumlah} file diarsip ke [${d.folder}]`, 'log-info');
    else if (t==='txt_saved')   appendLog(`📝 ${d.path.split('/').pop()} disimpan`, 'log-dim');
    else if (t==='ringkasan')     appendLog(`📊 ringkasan_total.txt disimpan`, 'log-dim');
    else if (t==='merge_log_saved') {
      if (d.path) appendLog(`📋 log_merge.txt diperbarui → ${d.path}`, 'log-info');
    }
    else if (t==='done') {
      document.getElementById('progress-bar').style.width = '100%';
      appendLog(''); appendLog('══ Selesai ══', 'log-info');
      es.close();
      btn.disabled = false; btn.innerHTML = '▶ Mulai Merge';
      currentResult = d;
      showResult(d);
      setTimeout(()=>{ document.getElementById('progress-wrap').classList.add('hidden'); }, 1500);
    }
    else if (t==='error') {
      appendLog(`ERROR: ${d.msg}`, 'log-fail');
      es.close(); btn.disabled = false; btn.innerHTML = '▶ Mulai Merge';
    }
  };
  es.onerror = function() {
    appendLog('Koneksi terputus.', 'log-fail');
    es.close(); btn.disabled = false; btn.innerHTML = '▶ Mulai Merge';
  };
}

function showResult(r) {
  document.getElementById('result-section').classList.remove('hidden');
  const colors = {green:'#059669',red:'#dc2626',orange:'#ea580c',teal:'#0891b2'};
  const stats = [
    ['✓ Berhasil', r.success+' pasang','green'],
    ['✗ Gagal',    r.failed +' pasang','red'],
    ['File Kosong',r.file_kosong+' file','orange'],
    ['Diarsip ke', r.folder_bulan||'-','teal'],
  ];
  document.getElementById('stats-grid').innerHTML = stats.map(([lbl,val,col])=>
    `<div class="stat" style="border-left-color:${colors[col]}">
       <div class="stat-num" style="color:${colors[col]}">${val}</div>
       <div class="stat-lbl">${lbl}</div></div>`
  ).join('');

  const tbody = document.getElementById('summary-body');
  tbody.innerHTML = '';
  let grandTotal = 0;
  for (const [folder, entries] of Object.entries(r.summary||{}).sort()) {
    const harga = HARGA[folder]||0;
    const total = entries.length * harga;
    grandTotal += total;
    tbody.innerHTML += `<tr>
      <td><span class="badge badge-teal">${folder}</span></td>
      <td>${entries.length} file</td>
      <td>Rp ${total.toLocaleString('id-ID')}</td></tr>`;
  }
  tbody.innerHTML += `<tr style="font-weight:700;background:var(--lgray)">
    <td>TOTAL</td><td></td>
    <td style="color:var(--teal)">Rp ${grandTotal.toLocaleString('id-ID')}</td></tr>`;

  if (!r.summary || Object.keys(r.summary).length === 0) {
    document.getElementById('email-section').classList.add('hidden'); return;
  }
  let fileHtml = '';
  for (const [folder, entries] of Object.entries(r.summary).sort()) {
    fileHtml += `<div class="bold teal" style="margin-top:8px;font-size:.83rem">${folder} — ${entries.length} file</div>`;
    entries.forEach(([key, nama, serial]) => {
      fileHtml += `<div class="file-item">📄 ${key}.pdf <span class="dim">— ${nama}</span> <span style="color:var(--teal)">SN:${serial}</span></div>`;
    });
  }
  document.getElementById('email-file-list').innerHTML =
    `<div class="alert alert-info">File berikut akan dikirim sebagai attachment:</div>
     <div class="file-list">${fileHtml}</div>`;
  document.getElementById('email-status').innerHTML = '';
  document.getElementById('email-btn-row').classList.remove('hidden');
}

function sendEmails() {
  document.getElementById('email-btn-row').classList.add('hidden');
  const statusEl = document.getElementById('email-status');
  statusEl.innerHTML =
    `<div class="alert alert-info"><span class="spinner"></span> Menyiapkan email...</div>
     <div class="progress-wrap" style="margin-top:8px">
       <div id="email-progress" class="progress-bar" style="width:0%"></div>
     </div>
     <div id="email-log" style="margin-top:8px;font-size:.82rem"></div>`;

  const es = new EventSource('/api/send-email-stream');
  es.onmessage = function(e) {
    const ev = JSON.parse(e.data);
    const t = ev.type; const d = ev.data;
    const logEl = document.getElementById('email-log');
    const progEl = document.getElementById('email-progress');

    if (t === 'email_start') {
      statusEl.querySelector('.alert').innerHTML =
        `<span class="spinner"></span> Mengirim ${d.total} email...`;
    }
    else if (t === 'email_sending') {
      if (logEl) logEl.innerHTML +=
        `<div style="color:var(--teal)">⟳ [${d.tipe}] Mengirim ${d.jumlah_file} file...</div>`;
      if (progEl) progEl.style.width = Math.round((d.idx-1)/d.total*100) + '%';
    }
    else if (t === 'email_result') {
      if (logEl) logEl.innerHTML +=
        d.ok
          ? `<div style="color:var(--green)">✓ [${d.tipe}] ${d.msg}</div>`
          : `<div style="color:var(--red)">✗ [${d.tipe}] ${d.msg}</div>`;
      if (progEl) progEl.style.width = Math.round(d.idx/d.total*100) + '%';
    }
    else if (t === 'email_done') {
      if (progEl) progEl.style.width = '100%';
      const alertClass = d.ok > 0 ? 'alert-success' : 'alert-error';
      statusEl.querySelector('.alert').className = `alert ${alertClass}`;
      statusEl.querySelector('.alert').innerHTML =
        d.ok > 0
          ? `✓ ${d.ok} email berhasil dikirim.${d.fail > 0 ? ` (${d.fail} gagal)` : ''}`
          : `✗ Semua email gagal dikirim.`;
      es.close();
    }
    else if (t === 'error') {
      statusEl.querySelector('.alert').className = 'alert alert-error';
      statusEl.querySelector('.alert').innerHTML = `✗ Error: ${d.msg}`;
      es.close();
    }
  };
  es.onerror = function() {
    es.close();
    const el = document.getElementById('email-status');
    if (el) el.innerHTML = '<div class="alert alert-error">✗ Koneksi terputus saat kirim email.</div>';
  };
}

function cancelEmail() {
  document.getElementById('email-btn-row').classList.add('hidden');
  document.getElementById('email-status').innerHTML =
    '<div class="alert alert-warn">Pengiriman email dilewati.</div>';
}

// ── Schedule ───────────────────────────────────────────────
function loadSchedule() {
  fetch('/api/config').then(r=>r.json()).then(cfg=>{
    document.getElementById('sch-enabled').checked = !!cfg.schedule_enabled;
    document.getElementById('sch-time').value      = cfg.schedule_time || '08:00';
    const days = cfg.schedule_days || [1,2,3,4,5];
    document.querySelectorAll('.day-btn').forEach(btn=>{
      const d = parseInt(btn.dataset.day);
      btn.classList.toggle('active', days.includes(d));
    });
    updateSchInfo(cfg);
  });
  fetch('/api/schedule/status').then(r=>r.json()).then(r=>{
    document.getElementById('sch-info').innerHTML =
      r.enabled
        ? `<span class="green">● Aktif</span> — setiap hari <b>${r.days}</b> pukul <b>${r.time}</b>`
        : `<span class="dim">● Tidak aktif</span>`;
  }).catch(()=>{
    document.getElementById('sch-info').innerHTML = '<span class="dim">Scheduler tidak tersedia</span>';
  });
}

function updateSchInfo(cfg) {}

function toggleDay(el) {
  el.classList.toggle('active');
}

function toggleSchedule() {
  const on = document.getElementById('sch-enabled').checked;
  document.getElementById('sch-options').style.opacity = on ? '1' : '.5';
}

function saveSchedule() {
  const days = [];
  document.querySelectorAll('.day-btn.active').forEach(b => days.push(parseInt(b.dataset.day)));
  const payload = {
    schedule_enabled: document.getElementById('sch-enabled').checked,
    schedule_time   : document.getElementById('sch-time').value,
    schedule_days   : days,
  };
  fetch('/api/schedule', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify(payload)
  }).then(r=>r.json()).then(r=>{
    const el = document.getElementById('sch-status');
    el.innerHTML = r.ok
      ? '<div class="alert alert-success">✓ Jadwal disimpan.</div>'
      : '<div class="alert alert-error">Gagal menyimpan jadwal.</div>';
    setTimeout(()=>el.innerHTML='', 3000);
    loadSchedule();
  });
}

// ── Config ─────────────────────────────────────────────────
function loadConfig() {
  fetch('/api/config').then(r=>r.json()).then(cfg=>{
    document.getElementById('c-source').value   = cfg.source_dir||'';
    document.getElementById('c-output').value   = cfg.output_dir||'';
    document.getElementById('c-xea-user').value = cfg.xea_username||'';
    document.getElementById('c-xea-pass').value = cfg.xea_password||'';
    document.getElementById('c-sender').value   = cfg.sender_email||'';
    document.getElementById('c-password').value = cfg.sender_password||'';
    document.getElementById('c-to').value  = (cfg.to ||[]).join(', ');
    document.getElementById('c-cc').value  = (cfg.cc ||[]).join(', ');
    document.getElementById('c-bcc').value = (cfg.bcc||[]).join(', ');
  });
}

function saveConfig() {
  const split = s => s.split(',').map(x=>x.trim()).filter(Boolean);
  const cfg = {
    source_dir     : document.getElementById('c-source').value.trim(),
    output_dir     : document.getElementById('c-output').value.trim(),
    xea_username   : document.getElementById('c-xea-user').value.trim(),
    xea_password   : document.getElementById('c-xea-pass').value.trim(),
    sender_email   : document.getElementById('c-sender').value.trim(),
    sender_password: document.getElementById('c-password').value.trim(),
    to : split(document.getElementById('c-to').value),
    cc : split(document.getElementById('c-cc').value),
    bcc: split(document.getElementById('c-bcc').value),
  };
  fetch('/api/config', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify(cfg)
  }).then(r=>r.json()).then(r=>{
    const el = document.getElementById('config-status');
    el.innerHTML = r.ok
      ? '<div class="alert alert-success">✓ Konfigurasi disimpan.</div>'
      : '<div class="alert alert-error">Gagal menyimpan.</div>';
    setTimeout(()=>el.innerHTML='', 3000);
  });
}

// ── Update ─────────────────────────────────────────────────
function checkUpdate() {
  const el = document.getElementById('update-status');
  el.innerHTML = '<div class="alert alert-info"><span class="spinner"></span> Mengecek...</div>';
  document.getElementById('btn-apply-update').classList.add('hidden');
  fetch('/api/check-update').then(r=>r.json()).then(r=>{
    if (r.up_to_date) {
      el.innerHTML = '<div class="alert alert-success">✓ Sudah versi terbaru.</div>';
    } else if (r.has_update) {
      el.innerHTML =
        `<div class="alert alert-warn">⚠ Ada update tersedia!<br>
         Lokal: <b>${r.local}</b> → GitHub: <b>${r.remote}</b><br>
         <span class="dim" style="font-size:.78rem">File berubah: ${r.changed||''}</span></div>`;
      document.getElementById('btn-apply-update').classList.remove('hidden');
    } else {
      el.innerHTML = `<div class="alert alert-warn">${r.msg||'Tidak bisa cek update.'}</div>`;
    }
  }).catch(()=>{
    el.innerHTML = '<div class="alert alert-error">Gagal cek update.</div>';
  });
}

function applyUpdate() {
  const el  = document.getElementById('update-status');
  const btn = document.getElementById('btn-apply-update');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Menerapkan...';
  el.innerHTML = '<div class="alert alert-info"><span class="spinner"></span> Mengunduh update dari GitHub...</div>';
  fetch('/api/apply-update', {method:'POST'}).then(r=>r.json()).then(r=>{
    if (r.ok) {
      el.innerHTML =
        `<div class="alert alert-success">✓ Update berhasil! Versi baru: <b>${r.version}</b><br>
         <span class="dim">Server akan restart dalam 3 detik...</span></div>`;
      setTimeout(()=>{ window.location.reload(); }, 3500);
    } else {
      el.innerHTML = `<div class="alert alert-error">✗ Update gagal: ${r.error}</div>`;
      btn.disabled = false;
      btn.innerHTML = '⬇ Terapkan Update';
    }
  }).catch(()=>{
    el.innerHTML = '<div class="alert alert-error">Koneksi terputus saat update.</div>';
    btn.disabled = false;
    btn.innerHTML = '⬇ Terapkan Update';
  });
}

// ── Log Merge ──────────────────────────────────────────────
let _fullLogContent = '';
const TIPE_ORDER = ['Install','Maintenance','Repair - Service','Take Report','Lainnya','File Kosong'];

function loadLogMerge() {
  document.getElementById('logmerge-meta').textContent = 'Memuat...';
  fetch('/api/log-merge').then(r=>r.json()).then(r=>{
    _fullLogContent = r.content || '';
    if (!_fullLogContent) {
      document.getElementById('logmerge-meta').textContent =
        'Belum ada log. Jalankan merge terlebih dahulu.';
      document.getElementById('logmerge-content').textContent = '';
      document.getElementById('logmerge-filter').innerHTML = '';
      return;
    }
    // Hitung entri per tipe
    const counts = {};
    TIPE_ORDER.forEach(t => {
      const matches = (_fullLogContent.match(new RegExp(`\\[${t}\\]`, 'g')) || []).length;
      if (matches > 0) counts[t] = matches;
    });
    // Render filter buttons
    const filterEl = document.getElementById('logmerge-filter');
    filterEl.innerHTML = `<div class="day-btn active" data-tipe="semua" onclick="filterLogTipe(this)">Semua</div>`;
    Object.entries(counts).forEach(([tipe, n]) => {
      filterEl.innerHTML +=
        `<div class="day-btn" data-tipe="${tipe}" onclick="filterLogTipe(this)">${tipe} (${n})</div>`;
    });
    // Hitung total sesi merge
    const sesi = (_fullLogContent.match(/MERGE LOG/g) || []).length;
    document.getElementById('logmerge-meta').innerHTML =
      `<b>${sesi}</b> sesi merge tersimpan &nbsp;·&nbsp; ` +
      Object.entries(counts).map(([t,n])=>
        `<span class="badge badge-teal">${t}: ${n}</span>`).join(' ');
    document.getElementById('logmerge-content').textContent = _fullLogContent;
  }).catch(()=>{
    document.getElementById('logmerge-meta').textContent = 'Tidak bisa memuat log.';
  });
}

function filterLogTipe(el) {
  document.querySelectorAll('#logmerge-filter .day-btn').forEach(b=>b.classList.remove('active'));
  el.classList.add('active');
  const tipe = el.dataset.tipe;
  if (tipe === 'semua') {
    document.getElementById('logmerge-content').textContent = _fullLogContent;
    return;
  }
  // Filter: tampilkan hanya blok yang mengandung tipe terpilih
  const lines = _fullLogContent.split('\n');
  const out = []; let inBlock = false; let inTipe = false;
  lines.forEach(line => {
    if (line.includes('MERGE LOG')) { inBlock = true; inTipe = false; out.push(line); return; }
    if (line.match(/^\s*\[.+\]\s*—/)) {
      inTipe = line.includes(`[${tipe}]`);
      if (inTipe) out.push(line);
      return;
    }
    if (inTipe) out.push(line);
    else if (inBlock && !line.trim()) out.push(''); // jaga separator
  });
  document.getElementById('logmerge-content').textContent = out.join('\n');
}

function searchLogMerge() {
  document.getElementById('logmerge-search').classList.toggle('hidden');
  document.getElementById('logmerge-keyword').focus();
}

function filterLogContent() {
  const kw = document.getElementById('logmerge-keyword').value.toLowerCase();
  if (!kw) { document.getElementById('logmerge-content').textContent = _fullLogContent; return; }
  const lines = _fullLogContent.split('\n');
  const out = lines.filter(l =>
    l.toLowerCase().includes(kw) || l.includes('MERGE LOG') || l.includes('===')
  );
  document.getElementById('logmerge-content').textContent = out.join('\n');
}

// ── Init ───────────────────────────────────────────────────
window.onload = function() {
  initTheme();
  loadVersion();
  loadDlInfo();
  loadCfgInfo();
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

@app.route("/api/version")
def api_version():
    v, d = get_version()
    return jsonify({"version": v, "date": d})

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

# ── Download SSE ─────────────────────────────────────────────
@app.route("/api/download")
def api_download():
    if dl is None:
        return jsonify({"error": "galva_download.py tidak ditemukan"}), 500

    dari   = request.args.get("dari", "")
    sampai = request.args.get("sampai", "")
    types  = request.args.get("types", "")
    try:
        date_from = datetime.strptime(dari,   "%Y-%m-%d").date()
        date_to   = datetime.strptime(sampai, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Format tanggal salah"}), 400

    type_filter = [t.strip() for t in types.split(",") if t.strip()] if types else None

    cfg      = core.load_config()
    username = cfg.get("xea_username", "")
    password = cfg.get("xea_password", "")
    save_dir = cfg.get("source_dir", "/sdcard/Download/galva_docs")

    q = queue.Queue()

    def cb(event, data):
        def fix(obj):
            if isinstance(obj, Path): return str(obj)
            if isinstance(obj, dict): return {k: fix(v) for k, v in obj.items()}
            if isinstance(obj, list): return [fix(v) for v in obj]
            return obj
        q.put({"type": event, "data": fix(data)})

    def worker():
        try:
            result = dl.run_download(username, password, date_from, date_to,
                                     save_dir, type_filter=type_filter, cb=cb)
            # Simpan account_name ke config jika ada
            if result.get("account_name"):
                cfg2 = core.load_config()
                cfg2["xea_account_name"] = result["account_name"]
                core.save_config(cfg2)
            _state["dl_result"] = result
        except Exception as e:
            q.put({"type": "error", "data": {"msg": str(e)}})
        finally:
            q.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def generate():
        while True:
            item = q.get()
            if item is None: break
            yield f"data: {json.dumps(item)}\n\n"

    return Response(stream_with_context(generate()),
                    mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

# ── Merge SSE ────────────────────────────────────────────────
@app.route("/api/run")
def api_run():
    cfg = core.load_config()
    q   = queue.Queue()

    def cb(event, data):
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
                cfg.get("digit_count", 6), cb)
            _state["result"] = result
        except Exception as e:
            q.put({"type": "error", "data": {"msg": str(e)}})
        finally:
            q.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def generate():
        while True:
            item = q.get()
            if item is None: break
            yield f"data: {json.dumps(item)}\n\n"

    return Response(stream_with_context(generate()),
                    mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

# ── Send Email SSE ───────────────────────────────────────────
@app.route("/api/send-email-stream")
def api_send_email_stream():
    result = _state.get("result")
    if not result or not result.get("summary"):
        def gen_err():
            yield f"data: {json.dumps({'type':'error','data':{'msg':'Tidak ada hasil merge'}})}\n\n"
        return Response(stream_with_context(gen_err()),
                        mimetype="text/event-stream",
                        headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

    cfg = core.load_config()
    q   = queue.Queue()

    def cb(event, data):
        q.put({"type": event, "data": data})

    def worker():
        try:
            core.do_send_emails(result["summary"], cfg, cb)
        except Exception as e:
            q.put({"type": "error", "data": {"msg": str(e)}})
        finally:
            q.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def generate():
        while True:
            item = q.get()
            if item is None: break
            yield f"data: {json.dumps(item)}\n\n"

    return Response(stream_with_context(generate()),
                    mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

# ── Schedule ─────────────────────────────────────────────────
@app.route("/api/schedule", methods=["POST"])
def api_schedule_post():
    try:
        data = request.get_json()
        cfg  = core.load_config()
        cfg["schedule_enabled"] = data.get("schedule_enabled", False)
        cfg["schedule_time"]    = data.get("schedule_time", "08:00")
        cfg["schedule_days"]    = data.get("schedule_days", [1,2,3,4,5])
        core.save_config(cfg)
        _apply_schedule()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route("/api/schedule/status")
def api_schedule_status():
    cfg  = core.load_config()
    days_label = {0:"Min",1:"Sen",2:"Sel",3:"Rab",4:"Kam",5:"Jum",6:"Sab"}
    days = ", ".join(days_label.get(d,"?") for d in cfg.get("schedule_days",[]))
    return jsonify({
        "enabled"   : cfg.get("schedule_enabled", False),
        "time"      : cfg.get("schedule_time", "08:00"),
        "days"      : days,
        "has_scheduler": _HAS_SCHEDULER,
    })

# ── Check Update ─────────────────────────────────────────────
@app.route("/api/check-update")
def api_check_update():
    try:
        work = str(Path(__file__).parent)
        subprocess.run(["git", "fetch", "origin", "main", "--quiet"],
                       cwd=work, timeout=15, capture_output=True)
        local  = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                          cwd=work).decode().strip()
        remote = subprocess.check_output(["git", "rev-parse", "--short", "FETCH_HEAD"],
                                          cwd=work).decode().strip()
        if local == remote:
            return jsonify({"up_to_date": True, "local": local, "remote": remote})
        # Daftar file yang berubah
        changed = subprocess.check_output(
            ["git", "diff", "--name-only", "HEAD", "FETCH_HEAD"],
            cwd=work).decode().strip().replace("\n", ", ")
        return jsonify({"has_update": True, "local": local,
                        "remote": remote, "changed": changed})
    except Exception as e:
        return jsonify({"msg": str(e)})

@app.route("/api/apply-update", methods=["POST"])
def api_apply_update():
    try:
        work = str(Path(__file__).parent)
        # Fetch & reset hard — tidak peduli diverged history
        subprocess.run(["git", "fetch", "origin", "main", "--quiet"],
                       cwd=work, timeout=30, capture_output=True, check=True)
        subprocess.run(["git", "reset", "--hard", "FETCH_HEAD"],
                       cwd=work, capture_output=True, check=True)
        new_ver = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=work).decode().strip()
        # Exit dengan kode 42 → start_manual.sh akan restart otomatis
        def restart():
            import time
            time.sleep(1)
            os._exit(42)
        threading.Thread(target=restart, daemon=True).start()
        return jsonify({"ok": True, "version": new_ver})
    except subprocess.CalledProcessError as e:
        return jsonify({"ok": False, "error": e.stderr.decode() if e.stderr else str(e)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

# ── Search ───────────────────────────────────────────────────
@app.route("/api/search")
def api_search():
    if dl is None:
        return jsonify({"results": [], "error": "galva_download.py tidak ditemukan"})
    keyword = request.args.get("q", "").strip()
    if not keyword:
        return jsonify({"results": []})
    cfg      = core.load_config()
    username = cfg.get("xea_username", "")
    password = cfg.get("xea_password", "")
    try:
        result = dl.search_orders(username, password, keyword)
        return jsonify(result)
    except Exception as e:
        return jsonify({"results": [], "error": str(e)})

# ── Statistik ────────────────────────────────────────────────
@app.route("/api/statistik")
def api_statistik():
    """Parse log_merge.txt dan return statistik per bulan per tipe."""
    candidates = [
        Path("/sdcard/Documents/log_merge.txt"),
        Path.home() / "Documents" / "log_merge.txt",
    ]
    log_path = next((p for p in candidates if p.exists()), None)
    if not log_path:
        return jsonify({"months": [], "data": {}, "total_all": 0})

    import re
    tipe_map = {
        "Install": "Install",
        "Maintenance": "Maintenance",
        "Repair - Service": "Repair - Service",
        "Take Report": "Take Report",
    }
    data       = {}
    total_all  = 0
    cur_month  = None
    cur_tipe   = None

    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip()
            # Baris header: "  MERGE LOG  —  2026-05-22 17:53"
            m = re.search(r"MERGE LOG\s*[—-]\s*(\d{4}-\d{2})", line)
            if m:
                cur_month = m.group(1)  # "2026-05"
                if cur_month not in data:
                    data[cur_month] = {}
                continue
            # Baris tipe: "  [Maintenance]  —  3 pekerjaan"
            m = re.search(r"\[(.+?)\]\s*[—-]\s*(\d+)\s*pekerjaan", line)
            if m and cur_month:
                tipe_raw = m.group(1)
                if tipe_raw in tipe_map:
                    cur_tipe = tipe_map[tipe_raw]
                    count = int(m.group(2))
                    data[cur_month][cur_tipe] = \
                        data[cur_month].get(cur_tipe, 0) + count
                    total_all += count

    # Format bulan ke "Mei 2026"
    bulan_id = ["","Jan","Feb","Mar","Apr","Mei","Jun",
                "Jul","Agu","Sep","Okt","Nov","Des"]
    def fmt_month(ym):
        try:
            y, m = ym.split("-")
            return f"{bulan_id[int(m)]} {y}"
        except Exception:
            return ym

    months_sorted = sorted(data.keys())
    result = {
        "months"   : [fmt_month(m) for m in months_sorted],
        "data"     : {fmt_month(m): data[m] for m in months_sorted},
        "total_all": total_all,
    }
    return jsonify(result)

# ── Log Merge ────────────────────────────────────────────────
@app.route("/api/log-merge")
def api_log_merge():
    """Baca log merge persisten dari /sdcard/Documents/log_merge.txt."""
    candidates = [
        Path("/sdcard/Documents/log_merge.txt"),
        Path.home() / "Documents" / "log_merge.txt",
    ]
    for p in candidates:
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                return jsonify({"content": f.read(), "path": str(p)})
    return jsonify({"content": "", "path": ""})

@app.route("/api/download/files")
def api_download_files():
    """Daftar file PDF di folder sumber."""
    cfg      = core.load_config()
    src_dir  = Path(cfg.get("source_dir", ""))
    if not src_dir.exists():
        return jsonify({"files": [], "total": 0})
    files = sorted(
        p.name for p in src_dir.glob("*.pdf")
        if p.is_file()
    ) + sorted(
        p.name for p in src_dir.glob("*.PDF")
        if p.is_file()
    )
    # Deduplikasi case-insensitive
    seen, unique = set(), []
    for f in files:
        if f.lower() not in seen:
            seen.add(f.lower())
            unique.append(f)
    return jsonify({"files": unique, "total": len(unique)})

# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 54)
    print("  XEA Tools  —  Web GUI")
    print("=" * 54)
    print("  Buka di Chrome Android:")
    print("  ➜  http://localhost:5000")
    print("=" * 54)
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
