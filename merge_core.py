#!/usr/bin/env python3
"""
merge_core.py — Logika inti, dipakai oleh TUI dan Web GUI.
Semua fungsi PDF, email, dan file management ada di sini.
"""

import re
import ssl
import shutil
import smtplib
import json
import os
import base64
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    raise ImportError("Jalankan: pip install pypdf")

# ─────────────────────────────────────────────────────────────
# FILE KONFIGURASI (disimpan di HP agar persisten)
# ─────────────────────────────────────────────────────────────
CONFIG_FILE = str(Path.home() / "merge_pdf_config.json")
KEY_FILE    = str(Path.home() / ".xea_key")

DEFAULT_CONFIG = {
    "source_dir"      : "/sdcard/Documents",
    "output_dir"      : "/sdcard/Documents/Hasil",
    "digit_count"     : 6,
    "xea_username"    : "",
    "xea_password"    : "",
    "sender_email"    : "",
    "sender_password" : "",
    "to"              : [],
    "cc"              : [],
    "bcc"             : [],
    "subject_template": "Laporan PDF - {tipe_layanan}",
    "body_template"   : (
        "Dear All,\n\nBerikut daftar pelanggan untuk Tipe Layanan [{tipe_layanan}]:\n\n"
        "{daftar_pelanggan}\n\nTerlampir {jumlah_file} file PDF.\n\n"
        "Email ini dikirim otomatis oleh {nama_akun}."
    ),
    "schedule_enabled": False,
    "schedule_time"   : "08:00",
    "schedule_days"   : [1, 2, 3, 4, 5],
}

# ─────────────────────────────────────────────────────────────
# ENKRIPSI CONFIG
# ─────────────────────────────────────────────────────────────

def _get_or_create_key() -> bytes:
    """Ambil atau buat kunci enkripsi Fernet. Disimpan di ~/.xea_key (chmod 600)."""
    key_path = Path(KEY_FILE)
    if key_path.exists():
        return key_path.read_bytes().strip()
    # Buat kunci baru
    try:
        from cryptography.fernet import Fernet
        key = Fernet.generate_key()
    except ImportError:
        # Fallback: kunci berbasis UUID device (tidak butuh library)
        import hashlib, platform
        seed = platform.node() + str(Path.home())
        raw  = hashlib.sha256(seed.encode()).digest()
        key  = base64.urlsafe_b64encode(raw)
    key_path.write_bytes(key + b"\n")
    try:
        os.chmod(KEY_FILE, 0o600)
    except Exception:
        pass
    return key


def _encrypt(data: str, key: bytes) -> bytes:
    """Enkripsi string JSON. Pakai Fernet jika tersedia, XOR-base64 sebagai fallback."""
    try:
        from cryptography.fernet import Fernet
        return Fernet(key).encrypt(data.encode("utf-8"))
    except ImportError:
        # Fallback XOR sederhana — lebih baik dari plain text
        raw = data.encode("utf-8")
        k   = key[:32]
        xor = bytes(b ^ k[i % len(k)] for i, b in enumerate(raw))
        return b"XOR:" + base64.b64encode(xor)


def _decrypt(data: bytes, key: bytes) -> str:
    """Dekripsi. Auto-detect Fernet vs XOR fallback."""
    if data.startswith(b"XOR:"):
        raw = base64.b64decode(data[4:])
        k   = key[:32]
        return bytes(b ^ k[i % len(k)] for i, b in enumerate(raw)).decode("utf-8")
    try:
        from cryptography.fernet import Fernet
        return Fernet(key).decrypt(data).decode("utf-8")
    except Exception as e:
        raise Exception(f"Dekripsi gagal: {e}")


def load_config() -> dict:
    cfg = DEFAULT_CONFIG.copy()
    if not os.path.exists(CONFIG_FILE):
        return cfg
    try:
        raw = Path(CONFIG_FILE).read_bytes()
        # Coba dekripsi dulu
        if raw.strip().startswith(b"{"):
            # Plain JSON lama → load dan enkripsi ulang otomatis
            saved = json.loads(raw.decode("utf-8"))
            cfg.update(saved)
            save_config(cfg)  # enkripsi sekarang
        else:
            key   = _get_or_create_key()
            saved = json.loads(_decrypt(raw, key))
            cfg.update(saved)
    except Exception:
        pass
    return cfg


def save_config(cfg: dict):
    key      = _get_or_create_key()
    payload  = json.dumps(cfg, indent=2, ensure_ascii=False)
    encrypted = _encrypt(payload, key)
    Path(CONFIG_FILE).write_bytes(encrypted)
    try:
        os.chmod(CONFIG_FILE, 0o600)
    except Exception:
        pass

# ─────────────────────────────────────────────────────────────
# KONSTANTA
# ─────────────────────────────────────────────────────────────
TAG_FIRST  = "STBA"
TAG_SECOND = "STAT"   # nama file dari API adalah _STAT, bukan _STATS

TIPE_LAYANAN_MAP = {
    "Install"          : "Install",
    "Maintenance"      : "Maintenance",
    "Repair / Service" : "Repair - Service",
    "Take Report"      : "Take Report",
}

HARGA_PER_TIPE = {
    "Take Report"      : 43_000,
    "Maintenance"      : 86_000,
    "Repair - Service" : 119_000,
    "Install"          : 199_000,
}

FILE_KOSONG_FOLDER = "File Kosong"
FALLBACK_FOLDER    = "Lainnya"
LOG_FILE           = "merge_log.txt"

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465

# ─────────────────────────────────────────────────────────────
# UTILITAS PDF
# ─────────────────────────────────────────────────────────────

def extract_key(filename: str, n: int) -> str:
    stem = Path(filename).stem
    # Hapus suffix tipe dokumen agar STBA dan STAT punya key yang sama
    for suffix in ("_STBA", "_STAT", "_STATS"):
        if stem.upper().endswith(suffix):
            stem = stem[:-len(suffix)]
            break
    alnum = re.sub(r"[^A-Za-z0-9]", "", stem)
    return alnum[-n:].upper() if len(alnum) >= n else None

def detect_tag(path: Path) -> str:
    name = path.stem.upper()
    if TAG_FIRST  in name: return "FIRST"
    if TAG_SECOND in name: return "SECOND"
    return None

def find_pdfs(source_dir: str) -> list:
    source = Path(source_dir)
    if not source.exists():
        return []
    pdfs = list(source.glob("*.pdf")) + list(source.glob("*.PDF"))
    seen, unique = set(), []
    for p in pdfs:
        if p not in seen:
            seen.add(p); unique.append(p)
    return sorted(unique)

def extract_stba_info(stba_path: Path) -> tuple:
    """Kembalikan (nama_pelanggan, tipe_layanan_raw, folder_name, serial_number)"""
    nama = "-"; tipe = "-"; serial = "-"
    try:
        reader = PdfReader(str(stba_path))
        for page in reader.pages:
            text = page.extract_text() or ""
            for line in text.splitlines():
                if nama == "-":
                    m = re.search(r"Nama\s+Pelanggan\s*:\s*(.+)", line, re.IGNORECASE)
                    if m: nama = m.group(1).strip()
                if tipe == "-":
                    m = re.search(r"Tipe\s+Layanan\s*:\s*(.+)", line, re.IGNORECASE)
                    if m: tipe = m.group(1).strip()
                if serial == "-":
                    m = re.search(
                        r"(?:Nomor\s+Seri\s+Perangkat|Serial\s*(?:Number|No\.?)|No\.?\s*[Ss]erial|Nomor\s*[Ss]eri(?:al)?)\s*:\s*(.+)",
                        line, re.IGNORECASE)
                    if m: serial = m.group(1).strip()
                if nama != "-" and tipe != "-" and serial != "-":
                    break
            if nama != "-" and tipe != "-" and serial != "-":
                break
    except Exception:
        pass

    folder_name = None
    for pdf_label, folder in TIPE_LAYANAN_MAP.items():
        if tipe.upper() == pdf_label.upper():
            tipe        = pdf_label
            folder_name = folder
            break
    if folder_name is None:
        folder_name = FALLBACK_FOLDER
        if tipe == "-": tipe = FALLBACK_FOLDER

    return nama, tipe, folder_name, serial

def merge_two(first: Path, second: Path, output_path: Path) -> bool:
    writer = PdfWriter()
    try:
        for f in [first, second]:
            reader = PdfReader(str(f))
            for page in reader.pages:
                writer.add_page(page)
        with open(output_path, "wb") as out:
            writer.write(out)
        return True
    except Exception:
        return False

def save_note_txt(txt_path: Path, entries: list):
    with open(txt_path, "w", encoding="utf-8") as f:
        for key, nama, serial in entries:
            f.write(f"{key} - {nama} [{serial}]\n")

def format_rupiah(angka: int) -> str:
    return "Rp {:>13,}".format(angka).replace(",", ".")

def save_ringkasan_total(out_root: Path, summary: dict, file_kosong: list) -> Path:
    total = 0
    lines = ["RINGKASAN TOTAL PER TIPE LAYANAN", "=" * 54, ""]
    urutan = list(TIPE_LAYANAN_MAP.values()) + [FALLBACK_FOLDER]
    sorted_keys = sorted(summary.keys(),
                         key=lambda k: urutan.index(k) if k in urutan else 99)
    for folder_name in sorted_keys:
        entries = summary[folder_name]
        jumlah  = len(entries)
        harga   = HARGA_PER_TIPE.get(folder_name, 0)
        sub     = jumlah * harga
        total  += sub
        lines.append(
            f"  {folder_name:<22} : {jumlah:>3} file  x  "
            f"{format_rupiah(harga)}  =  {format_rupiah(sub)}"
        )
    lines += ["", "-" * 54,
              f"  {'TOTAL KESELURUHAN':<22}                     {format_rupiah(total)}",
              ""]
    if file_kosong:
        lines.append(f"  File Kosong (tidak dihitung) : {len(file_kosong)} file")
        for f in file_kosong:
            lines.append(f"    - {f.name}")
    lines += ["", f"Dibuat otomatis: {datetime.now().strftime('%d %B %Y %H:%M')}"]
    txt_path = out_root / "ringkasan_total.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return txt_path

def save_merge_log(summary: dict, file_kosong: list) -> Path:
    """
    Simpan log merge per tipe layanan ke /sdcard/Documents/log_merge.txt.
    Log bersifat append — tidak bisa dihapus dari GUI, dipakai sebagai recheck.
    Format per baris: YYYY-MM-DD | TIPE | KEY - Nama (Serial)
    """
    log_path = Path("/sdcard/Documents/log_merge.txt")
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        # Fallback ke home dir jika sdcard tidak tersedia
        log_path = Path.home() / "Documents" / "log_merge.txt"
        log_path.parent.mkdir(parents=True, exist_ok=True)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    urutan  = list(TIPE_LAYANAN_MAP.values()) + [FALLBACK_FOLDER]
    sorted_keys = sorted(summary.keys(),
                         key=lambda k: urutan.index(k) if k in urutan else 99)

    lines = [
        "",
        "=" * 60,
        f"  MERGE LOG  —  {now_str}",
        "=" * 60,
    ]
    for tipe in sorted_keys:
        entries = summary[tipe]
        lines.append(f"\n  [{tipe}]  —  {len(entries)} pekerjaan")
        lines.append("  " + "-" * 50)
        for key, nama, serial, _ in entries:
            lines.append(f"  {key}  -  {nama}  ({serial})")
    if file_kosong:
        lines.append(f"\n  [File Kosong]  —  {len(file_kosong)} file")
        for f in file_kosong:
            lines.append(f"    - {f.name}")
    lines.append("")

    with open(log_path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return log_path


def load_processed_keys() -> set:
    """
    Baca log_merge.txt, ekstrak semua key order yang sudah pernah dimerge.
    Dipakai untuk skip duplikat saat merge berikutnya.
    """
    candidates = [
        Path("/sdcard/Documents/log_merge.txt"),
        Path.home() / "Documents" / "log_merge.txt",
    ]
    keys = set()
    for log_path in candidates:
        if not log_path.exists():
            continue
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    # Format baris: "  KEY  -  Nama  (Serial)"
                    # Key adalah bagian pertama sebelum " - "
                    if line and not line.startswith(("[", "=", "-", "/")):
                        parts = line.split("  -  ", 1)
                        if parts:
                            key = parts[0].strip()
                            if key:
                                keys.add(key.upper())
        except Exception:
            pass
        break  # pakai file pertama yang ditemukan
    return keys


def nama_bulan_indonesia(dt: datetime) -> str:
    bulan = ["","Januari","Februari","Maret","April","Mei","Juni",
             "Juli","Agustus","September","Oktober","November","Desember"]
    return f"{bulan[dt.month]} {dt.year}"

def pindah_file_mentah(source_dir: str, moved_pairs: list) -> tuple:
    folder_bulan = nama_bulan_indonesia(datetime.now())
    target_dir   = Path(source_dir) / folder_bulan
    target_dir.mkdir(parents=True, exist_ok=True)
    ok = gagal = skip = 0
    for stba_path, stats_path in moved_pairs:
        for src in [stba_path, stats_path]:
            dst = target_dir / src.name
            if dst.exists():
                # File sudah ada di arsip — hapus sumber saja, tidak buat duplikat
                try:
                    src.unlink()
                    skip += 1
                except Exception:
                    gagal += 1
            else:
                try:
                    shutil.move(str(src), str(dst)); ok += 1
                except Exception:
                    gagal += 1
    return folder_bulan, ok, gagal

# ─────────────────────────────────────────────────────────────
# EMAIL
# ─────────────────────────────────────────────────────────────

class _SafeDict(dict):
    """Dict yang tidak KeyError saat dipakai format_map — placeholder
    yang tidak dikenal akan dibiarkan apa adanya, bukan bikin crash."""
    def __missing__(self, key):
        return "{" + key + "}"


def _safe_format(template: str, **kwargs) -> str:
    """Format string template tanpa KeyError jika ada placeholder
    (mis. {nama_akun}) yang belum disediakan nilainya."""
    try:
        return template.format_map(_SafeDict(**kwargs))
    except Exception:
        return template


def send_email_subfolder(tipe: str, pdf_files: list,
                         daftar_pelanggan: str, cfg: dict) -> tuple:
    """Kirim 1 email. Kembalikan (ok: bool, pesan: str)"""
    to_list  = cfg.get("to", [])
    cc_list  = cfg.get("cc", [])
    bcc_list = cfg.get("bcc", [])
    nama_akun = cfg.get("xea_username") or "Depo"
    subject  = _safe_format(
                    cfg.get("subject_template", "Laporan PDF - {tipe_layanan}"),
                    tipe_layanan=tipe, nama_akun=nama_akun)
    body     = _safe_format(
                    cfg.get("body_template", ""),
                    tipe_layanan=tipe,
                    daftar_pelanggan=daftar_pelanggan,
                    jumlah_file=len(pdf_files),
                    nama_akun=nama_akun)
    msg = MIMEMultipart()
    msg["From"]    = cfg["sender_email"]
    msg["To"]      = ", ".join(to_list)
    msg["Subject"] = subject
    if cc_list: msg["Cc"] = ", ".join(cc_list)
    msg.attach(MIMEText(body, "plain", "utf-8"))
    for pdf_path in pdf_files:
        with open(pdf_path, "rb") as f:
            part = MIMEBase("application", "pdf")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=pdf_path.name)
        msg.attach(part)
    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx) as srv:
            srv.login(cfg["sender_email"], cfg["sender_password"])
            srv.sendmail(cfg["sender_email"],
                         to_list + cc_list + bcc_list, msg.as_bytes())
        return True, f"Email [{tipe}] terkirim ke {', '.join(to_list)}"
    except smtplib.SMTPAuthenticationError:
        return False, "Login gagal — periksa App Password Gmail"
    except Exception as e:
        return False, str(e)

# ─────────────────────────────────────────────────────────────
# FUNGSI UTAMA — run_merge()
# ─────────────────────────────────────────────────────────────

def cleanup_duplicate_files(output_dir: str) -> list:
    """
    Hapus file PDF duplikat hasil merge ganda.
    Target: file dengan pola nama_angka.pdf (misal ABC123_1.pdf, ABC123_2.pdf).
    File tanpa suffix angka dibiarkan.
    Kembalikan list nama file yang dihapus.
    """
    out_root = Path(output_dir)
    if not out_root.exists():
        return []
    deleted = []
    # Scan semua subfolder (Install, Maintenance, dll) + root output
    dirs_to_scan = [out_root] + [d for d in out_root.iterdir() if d.is_dir()]
    for folder in dirs_to_scan:
        for pdf in folder.glob("*.pdf"):
            # Cocokkan pola: diakhiri _angka sebelum .pdf
            if re.search(r"_\d+$", pdf.stem):
                try:
                    pdf.unlink()
                    deleted.append(pdf.name)
                except Exception:
                    pass
    return deleted


def run_merge(source_dir: str, output_dir: str,
              digit_count: int = 6, cb=None) -> dict:
    """
    Jalankan proses merge. cb(event, data) dipanggil untuk setiap kejadian.
    Event: 'scan', 'classify', 'pair_found', 'merge_ok', 'merge_fail',
           'file_kosong', 'arsip', 'txt_saved', 'ringkasan', 'done'
    Kembalikan dict hasil untuk dipakai GUI kirim email.
    """
    def emit(event, data):
        if cb: cb(event, data)

    out_root    = Path(output_dir)
    source_path = Path(source_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    # 0a. Sub-folder bulan hasil (mis. "Agustus 2026") — dibuat berdasarkan
    #     tanggal saat merge dijalankan. Semua output run ini (folder jenis
    #     pekerjaan, File Kosong, ringkasan, log) masuk ke sini.
    bulan_hasil = nama_bulan_indonesia(datetime.now())
    bulan_root  = out_root / bulan_hasil
    bulan_root.mkdir(parents=True, exist_ok=True)

    # 0b. Bersihkan file duplikat (_1, _2, dst) sebelum merge
    deleted = cleanup_duplicate_files(output_dir)
    if deleted:
        emit("cleanup", {"deleted": deleted, "jumlah": len(deleted)})

    # 0c. Muat key yang sudah pernah dimerge dari log_merge.txt
    processed_keys = load_processed_keys()
    if processed_keys:
        emit("log_check", {"total_processed": len(processed_keys)})

    # 1. Scan
    all_pdfs = find_pdfs(source_dir)
    emit("scan", {"total": len(all_pdfs), "source_dir": source_dir})

    # 2. Klasifikasi
    pool = {"FIRST": defaultdict(list), "SECOND": defaultdict(list)}
    unrecognized = []
    for pdf in all_pdfs:
        tag = detect_tag(pdf)
        key = extract_key(pdf.name, digit_count)
        if tag is None or key is None:
            unrecognized.append(pdf); continue
        pool[tag][key].append(pdf)
    emit("classify", {
        "stba" : sum(len(v) for v in pool["FIRST"].values()),
        "stats": sum(len(v) for v in pool["SECOND"].values()),
        "unknown": len(unrecognized),
    })

    # 3. Pasangan
    all_keys    = set(pool["FIRST"]) | set(pool["SECOND"])
    pairs_ok    = sorted(k for k in all_keys if pool["FIRST"].get(k) and pool["SECOND"].get(k))
    only_first  = sorted(k for k in all_keys if pool["FIRST"].get(k) and not pool["SECOND"].get(k))
    only_second = sorted(k for k in all_keys if pool["SECOND"].get(k) and not pool["FIRST"].get(k))
    emit("pair_found", {"pairs": len(pairs_ok),
                        "only_stba": len(only_first),
                        "only_stats": len(only_second)})

    # 4. Merge
    summary     = defaultdict(list)
    txt_entries = defaultdict(list)
    moved_pairs = []
    log_lines   = []
    success = failed = 0

    for key in pairs_ok:
        first_file  = sorted(pool["FIRST"][key])[0]
        second_file = sorted(pool["SECOND"][key])[0]

        # Cek apakah key ini sudah pernah dimerge sebelumnya
        if key.upper() in processed_keys:
            log_lines.append(f"[SKIP] {key} — sudah pernah dimerge (ada di log)")
            emit("merge_skip", {"key": key, "reason": "sudah ada di log_merge.txt"})
            # Pindahkan file mentah ke arsip meski di-skip, agar tidak menumpuk
            moved_pairs.append((first_file, second_file))
            continue

        nama, tipe, folder_name, serial = extract_stba_info(first_file)

        tipe_folder = bulan_root / folder_name
        tipe_folder.mkdir(parents=True, exist_ok=True)

        output_file = tipe_folder / f"{key}.pdf"

        # Jika file sudah ada di output → skip, arsip file mentah, jangan buat duplikat
        if output_file.exists():
            log_lines.append(f"[SKIP] {key} — output sudah ada di {folder_name}/")
            emit("merge_skip", {"key": key, "reason": f"output sudah ada di {folder_name}/"})
            moved_pairs.append((first_file, second_file))
            continue

        ok = merge_two(first_file, second_file, output_file)
        if ok:
            success += 1
            moved_pairs.append((first_file, second_file))
            summary[folder_name].append((key, nama, serial, output_file))
            txt_entries[folder_name].append((key, nama, serial))
            log_lines.append(f"[OK] {output_file}\n     STBA: {first_file}\n     STATS: {second_file}\n     Pelanggan: {nama}  Serial: {serial}  Tipe: {tipe}")
            emit("merge_ok", {"key": key, "nama": nama, "serial": serial,
                              "tipe": tipe, "folder": folder_name,
                              "output": str(output_file)})
        else:
            failed += 1
            log_lines.append(f"[GAGAL] kunci={key}")
            emit("merge_fail", {"key": key})

    # 5. File Kosong
    file_kosong_list = []
    if only_first:
        kosong_folder = bulan_root / FILE_KOSONG_FOLDER
        kosong_folder.mkdir(parents=True, exist_ok=True)
        for k in only_first:
            src = pool["FIRST"][k][0]
            dst = kosong_folder / src.name
            c = 1
            while dst.exists():
                dst = kosong_folder / f"{src.stem}_{c}{src.suffix}"; c += 1
            try:
                shutil.move(str(src), str(dst))
                file_kosong_list.append(dst)
                log_lines.append(f"[KOSONG] {src.name} → File Kosong/")
                emit("file_kosong", {"name": src.name})
            except Exception as e:
                emit("merge_fail", {"key": k, "reason": str(e)})

    # 6. Arsip bulan
    folder_bulan = ""
    if moved_pairs:
        folder_bulan, pindah_ok, pindah_gagal = pindah_file_mentah(source_dir, moved_pairs)
        log_lines.append(f"[ARSIP] {pindah_ok} file mentah dipindah ke [{folder_bulan}]")
        emit("arsip", {"folder": folder_bulan, "jumlah": pindah_ok})

    # 7. Simpan .txt
    for folder_name, entries in sorted(txt_entries.items()):
        tipe_folder = bulan_root / folder_name
        txt_path    = tipe_folder / f"daftar_pelanggan_{folder_name}.txt"
        save_note_txt(txt_path, entries)
        emit("txt_saved", {"path": str(txt_path)})

    # 8. Ringkasan total (txt di dalam sub-folder bulan)
    ringkasan_path = None
    if summary:
        ringkasan_path = save_ringkasan_total(bulan_root, summary, file_kosong_list)
        emit("ringkasan", {"path": str(ringkasan_path)})

    # 8b. Log merge persisten (append ke Documents/log_merge.txt)
    merge_log_path = None
    if summary:
        try:
            merge_log_path = save_merge_log(summary, file_kosong_list)
            emit("merge_log_saved", {"path": str(merge_log_path)})
        except Exception as e:
            emit("merge_log_saved", {"path": "", "error": str(e)})

    # 9. Log
    log_path = bulan_root / LOG_FILE
    with open(log_path, "w", encoding="utf-8") as lf:
        lf.write("MERGE LOG\n")
        lf.write(f"Sumber : {source_dir}\nOutput : {bulan_root}\n\n")
        lf.write("\n".join(log_lines))

    result = {
        "success"         : success,
        "failed"          : failed,
        "file_kosong"     : len(file_kosong_list),
        "only_stats"      : len(only_second),
        "folder_bulan"    : folder_bulan,
        "bulan_hasil"     : bulan_hasil,
        "summary"         : dict(summary),
        "ringkasan_path"  : str(ringkasan_path) if ringkasan_path else "",
        "merge_log_path"  : str(merge_log_path) if merge_log_path else "",
        "log_path"        : str(log_path),
        "output_dir"      : output_dir,
        "output_dir_bulan": str(bulan_root),
    }
    emit("done", result)
    return result

def scan_email_candidates(output_dir: str) -> dict:
    """
    Baca ulang folder output dari disk dan susun struktur summary
    {folder_name: [(key, nama, serial, Path)]} yang siap dikirim lewat
    do_send_emails(). Dipakai oleh tab 'Kirim Email' agar tidak bergantung
    pada hasil merge yang masih tersimpan di memori (mis. setelah server
    di-restart atau browser dibuka ulang di sesi lain).

    Struktur folder saat ini: output_dir / <Bulan Tahun> / <Jenis Pekerjaan>.
    Semua sub-folder bulan ikut dipindai dan digabung per jenis pekerjaan
    (satu email tetap mencakup semua pekerjaan dgn tipe sama, lintas bulan
    — dipakai untuk kasus cut-off pekerjaan di akhir bulan). Folder jenis
    pekerjaan langsung di output_dir (struktur lama, sebelum ada sub-folder
    bulan) tetap dipindai juga agar file lama tidak "hilang".
    """
    out_root = Path(output_dir)
    result = defaultdict(list)
    if not out_root.exists():
        return {}

    known_folders = list(TIPE_LAYANAN_MAP.values()) + [FALLBACK_FOLDER]

    def scan_one(base: Path):
        for folder_name in known_folders:
            folder_path = base / folder_name
            if not folder_path.exists() or not folder_path.is_dir():
                continue

            # Baca daftar_pelanggan_*.txt untuk mapping key -> (nama, serial)
            # Format baris: "KEY - Nama [Serial]"
            info_map = {}
            txt_path = folder_path / f"daftar_pelanggan_{folder_name}.txt"
            if txt_path.exists():
                try:
                    with open(txt_path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line or " - " not in line:
                                continue
                            key_part, rest = line.split(" - ", 1)
                            key = key_part.strip()
                            m = re.match(r"^(.*)\s*\[(.*)\]\s*$", rest.strip())
                            if m:
                                nama, serial = m.group(1).strip(), m.group(2).strip()
                            else:
                                nama, serial = rest.strip(), "-"
                            info_map[key] = (nama, serial)
                except Exception:
                    pass

            for pdf in sorted(folder_path.glob("*.pdf")):
                key = pdf.stem
                nama, serial = info_map.get(key, ("-", "-"))
                result[folder_name].append((key, nama, serial, pdf))

    # Sub-folder bulan (struktur baru), mis. "Agustus 2026"
    for d in sorted(out_root.iterdir()):
        if d.is_dir() and d.name not in known_folders and d.name != FILE_KOSONG_FOLDER:
            scan_one(d)

    # Struktur lama: folder jenis pekerjaan langsung di output_dir
    scan_one(out_root)

    return dict(result)


def do_send_emails(summary: dict, cfg: dict, cb=None) -> dict:
    """
    Kirim email untuk semua Tipe Layanan.
    Kembalikan {"ok": n, "fail": n, "detail": [(tipe, bool, msg)]}
    Events: email_start, email_result, email_done
    """
    def emit(ev, data):
        if cb: cb(ev, data)

    total_tipe = len(summary)
    emit("email_start", {"total": total_tipe})

    ok = fail = 0
    detail = []
    for idx, (tipe, entries) in enumerate(sorted(summary.items()), 1):
        pdf_files  = [e[3] for e in entries]
        # Format: Nomor ST - Nama Pelanggan (Nomor Seri Perangkat)
        daftar_str = "\n".join(
            f"  {k} - {n} ({s})" for k, n, s, _ in entries
        )
        emit("email_sending", {"tipe": tipe, "idx": idx, "total": total_tipe,
                               "jumlah_file": len(pdf_files)})
        success, msg = send_email_subfolder(tipe, pdf_files, daftar_str, cfg)
        detail.append((tipe, success, msg))
        emit("email_result", {"tipe": tipe, "ok": success, "msg": msg,
                              "idx": idx, "total": total_tipe})
        if success: ok += 1
        else:       fail += 1

    emit("email_done", {"ok": ok, "fail": fail})
    return {"ok": ok, "fail": fail, "detail": detail}
