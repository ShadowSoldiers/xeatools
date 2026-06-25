#!/usr/bin/env python3
"""
galva_download.py — Download dokumen STAT & STBA dari API Galva XEA.
Bisa dijalankan CLI maupun dipanggil sebagai modul dari merge_web.py.
"""

import requests
import base64
import json
import os
from pathlib import Path
from datetime import datetime

BASE_URL = "https://api.galva.co.id"

TRIGGER_MAP = {
    "INST": ["CL"],       # Install
    "MAIN": ["CL"],       # Maintenance
    "TKRP": ["CL"],       # Take Report
    "SERV": ["FN", "CL"], # Repair / Service
    # PLOT (Pull Out) tidak diunduh — tidak ada hitungan nilai
}

TARGET_DOCS = ["STAT", "STBA"]

LOGIN_HEADERS = {
    "user-agent"     : "Dart/3.7 (dart:io)",
    "accept"         : "application/json",
    "accept-encoding": "gzip",
    "authorization"  : "Basic Z2FsdmFfYmU6YXBpQGJlMjAyMTAxMTQ=",
    "content-type"   : "application/json; charset=utf-8",
}


def get_token(username: str, password: str) -> str:
    resp = requests.post(
        f"{BASE_URL}/xsyst/api/ldap/xea",
        headers=LOGIN_HEADERS,
        json={"user_name": username, "user_password": password},
        timeout=15,
    )
    resp.raise_for_status()
    data  = resp.json()
    token = (data.get("data", {}) or {}).get("jwt_token")
    if not token:
        raise Exception(f"Token tidak ditemukan di response: {list(data.keys())}")
    return token


def decode_jwt_payload(token: str) -> dict:
    """Decode JWT payload, return dict claims."""
    try:
        payload_b64  = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        return json.loads(base64.b64decode(payload_b64).decode("utf-8"))
    except Exception as e:
        raise Exception(f"Gagal decode JWT: {e}")

def decode_key_user_id(token: str) -> int:
    return int(decode_jwt_payload(token)["keyuserId"])

def decode_account_name(token: str) -> str:
    return decode_jwt_payload(token).get("name", "")


def make_headers(token: str) -> dict:
    return {
        "user-agent"   : "Dart/3.7 (dart:io)",
        "accept"       : "application/json",
        "authorization": f"Bearer {token}",
        "content-type" : "application/json",
    }


def fetch_orders(headers: dict, key_user_id: int, is_finish: bool,
                 date_from=None, date_to=None) -> list:
    """
    Ambil daftar order. date_from/date_to dalam format 'YYYY-MM-DD' 
    untuk filter di server agar response lebih kecil dan tidak timeout.
    """
    # Format tanggal untuk API: MM/DD/YYYY
    start_date = ""
    end_date   = ""
    if date_from:
        try:
            from datetime import datetime as _dt
            d = _dt.strptime(str(date_from), "%Y-%m-%d")
            start_date = d.strftime("%m/%d/%Y")
            end_date   = _dt.strptime(str(date_to), "%Y-%m-%d").strftime("%m/%d/%Y") if date_to else start_date
        except Exception:
            pass

    for attempt in range(3):
        try:
            resp = requests.get(
                f"{BASE_URL}/xsyst/api/engineer-service-orders",
                params={
                    "keyUserId"            : key_user_id,
                    "isFinish"             : "true" if is_finish else "false",
                    "onlyMyTask"           : "true",
                    "serviceOrderNumber"   : "",
                    "userTicketInboxNumber": "",
                    "supportTypeCode"      : "",
                    "serialNumber"         : "",
                    "customerDetailName"   : "",
                    "engineerKeyuserId"    : "",
                    "ticketStatusCode"     : "",
                    "startDate"            : start_date,
                    "endDate"              : end_date,
                },
                headers=headers,
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json().get("data", [])
        except requests.exceptions.Timeout:
            if attempt < 2:
                import time
                time.sleep(3)  # jeda 3 detik sebelum retry
                continue
            raise Exception("Koneksi timeout setelah 3 percobaan. Periksa jaringan.")
        except Exception as e:
            raise e


def fetch_order_detail(headers: dict, key_user_id: int, order_id) -> dict:
    resp = requests.get(
        f"{BASE_URL}/xsyst/api/engineer-service-order",
        params={"keyUserId": key_user_id, "serviceOrderId": order_id},
        headers=headers,
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json().get("data", {})


def parse_date(date_str: str):
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str).date()
    except Exception:
        return None


def should_download(type_code: str, status_code: str) -> bool:
    triggers = TRIGGER_MAP.get(type_code)
    return bool(triggers) and status_code in triggers


def decode_base64(raw: str) -> bytes:
    padded = raw + "=" * (-len(raw) % 4)
    try:
        return base64.b64decode(padded, validate=True)
    except Exception:
        url_safe = raw.replace("-", "+").replace("_", "/")
        padded2  = url_safe + "=" * (-len(url_safe) % 4)
        return base64.b64decode(padded2)



def _read_jpeg_dimensions(data: bytes):
    """Baca lebar dan tinggi dari header JPEG dengan parsing SOF marker yang benar."""
    i = 2 if data[:2] == b'\xff\xd8' else 0
    while i < len(data) - 3:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i+1]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                      0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            if i + 8 < len(data):
                h = (data[i+5] << 8) | data[i+6]
                w = (data[i+7] << 8) | data[i+8]
                if w > 0 and h > 0:
                    return w, h
            break
        elif marker in (0xD8, 0xD9) or (0xD0 <= marker <= 0xD7) or marker == 0x01:
            i += 2
        else:
            if i + 3 >= len(data): break
            length = (data[i+2] << 8) | data[i+3]
            i += 2 + length
    return None, None


def _minimal_jpg_pdf(jpg: bytes) -> bytes:
    """
    Buat PDF minimal yang embed JPG langsung.
    MediaBox disesuaikan dengan dimensi asli gambar sehingga tidak terpotong/miring.
    """
    import io

    w, h = _read_jpeg_dimensions(jpg)
    if not w or not h:
        w, h = 595, 842  # fallback A4 portrait

    img_len = len(jpg)

    # Deteksi color space dari SOF
    color_space = "/DeviceRGB"
    try:
        i = 2
        while i < len(jpg) - 3:
            if jpg[i] != 0xFF: break
            m = jpg[i+1]
            if m in (0xC0, 0xC1, 0xC2):
                components = jpg[i+9] if i+9 < len(jpg) else 3
                if components == 1:   color_space = "/DeviceGray"
                elif components == 4: color_space = "/DeviceCMYK"
                break
            elif m in (0xD8, 0xD9) or (0xD0 <= m <= 0xD7) or m == 0x01:
                i += 2
            else:
                length = (jpg[i+2] << 8) | jpg[i+3]
                i += 2 + length
    except Exception:
        pass

    pdf = io.BytesIO()
    pdf.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []

    offsets.append(pdf.tell())
    pdf.write(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")

    offsets.append(pdf.tell())
    pdf.write(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")

    offsets.append(pdf.tell())
    pdf.write((
        f"3 0 obj\n<< /Type /Page /Parent 2 0 R "
        f"/MediaBox [0 0 {w} {h}] "
        f"/Contents 4 0 R "
        f"/Resources << /XObject << /Im1 5 0 R >> >> "
        f">>\nendobj\n"
    ).encode())

    stream = f"q {w} 0 0 {h} 0 0 cm /Im1 Do Q".encode()
    offsets.append(pdf.tell())
    pdf.write(
        f"4 0 obj\n<< /Length {len(stream)} >>\nstream\n".encode()
        + stream + b"\nendstream\nendobj\n"
    )

    offsets.append(pdf.tell())
    pdf.write((
        f"5 0 obj\n<< /Type /XObject /Subtype /Image "
        f"/Width {w} /Height {h} "
        f"/ColorSpace {color_space} "
        f"/BitsPerComponent 8 /Filter /DCTDecode "
        f"/Length {img_len} >>\nstream\n"
    ).encode())
    pdf.write(jpg)
    pdf.write(b"\nendstream\nendobj\n")

    xref_pos = pdf.tell()
    pdf.write(f"xref\n0 6\n0000000000 65535 f \n".encode())
    for off in offsets:
        pdf.write(f"{off:010d} 00000 n \n".encode())
    pdf.write(
        f"trailer\n<< /Size 6 /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n".encode()
    )
    return pdf.getvalue()

def is_jpg_bytes(data: bytes) -> bool:
    """Cek apakah bytes adalah JPEG."""
    return data[:2] == b'\xff\xd8'


# ─────────────────────────────────────────────────────────────
# LOG DOWNLOAD
# ─────────────────────────────────────────────────────────────

DOWNLOAD_LOG = "/sdcard/Documents/log_download.txt"


def load_download_log() -> set:
    """Baca log_download.txt, return set nama file yang sudah pernah diunduh."""
    filenames = set()
    try:
        log_path = Path(DOWNLOAD_LOG)
        if not log_path.exists():
            return filenames
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(" | ")
                if len(parts) >= 2:
                    filenames.add(parts[1].strip())
    except Exception:
        pass
    return filenames


def append_download_log(filename: str, status: str = "OK"):
    """Tambah entri ke log_download.txt dengan timestamp."""
    try:
        log_path = Path(DOWNLOAD_LOG)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"{timestamp} | {filename} | {status}\n")
    except Exception:
        pass


def cleanup_archive_duplicates(source_dir: str) -> list:
    """Hapus file duplikat (*_1.pdf, *_2.pdf dst) dari subfolder arsip bulan."""
    deleted = []
    try:
        src = Path(source_dir)
        if not src.exists():
            return deleted
        for sub in src.iterdir():
            if not sub.is_dir():
                continue
            for pdf in sub.glob("*.pdf"):
                if re.search(r"_\d+$", pdf.stem):
                    try:
                        pdf.unlink()
                        deleted.append(f"{sub.name}/{pdf.name}")
                    except Exception:
                        pass
    except Exception:
        pass
    return deleted



def save_document(support_number: str, doc: dict, save_dir: str,
                  downloaded_log: set = None) -> str:
    """Simpan dokumen. JPG otomatis dikonversi ke PDF. Return 'ok'|'skip'|'fail'."""
    doc_code = doc.get("document_type_code", "DOC")
    raw      = doc.get("document")
    if not raw:
        return "fail"

    # Nama file selalu .pdf
    filename  = f"{support_number}_{doc_code}.pdf".replace("/", "-")
    filepath  = os.path.join(save_dir, filename)
    stem_base = Path(filename).stem  # misal: SVODR-2604-T09760_STAT

    # Cek di folder sumber
    if os.path.exists(filepath):
        return "skip"

    # Cek di subfolder arsip bulan — cocokkan stem prefix
    # agar SVODR-2604-T09760_STAT_6.pdf juga terdeteksi sebagai duplikat
    try:
        for sub in Path(save_dir).iterdir():
            if not sub.is_dir():
                continue
            # Cek nama persis dulu
            if (sub / filename).exists():
                return "skip"
            # Cek varian dengan suffix angka (misal _1, _2, _7)
            for existing in sub.glob(f"{stem_base}*.pdf"):
                if existing.is_file():
                    return "skip"
    except Exception:
        pass

    try:
        raw_bytes = decode_base64(raw)
    except Exception:
        return "fail"

    try:
        if is_jpg_bytes(raw_bytes):
            raw_bytes = _minimal_jpg_pdf(raw_bytes)
        with open(filepath, "wb") as f:
            f.write(raw_bytes)
        return "ok"
    except Exception:
        return "fail"


# ─────────────────────────────────────────────────────────────
# FUNGSI UTAMA — dipanggil dari merge_web.py
# ─────────────────────────────────────────────────────────────

def search_orders(username: str, password: str,
                  keyword: str, cb=None) -> dict:
    """
    Cari order berdasarkan nama pelanggan dari API Galva.
    Kembalikan list order dengan status download/merge.
    """
    def emit(event, data):
        if cb: cb(event, data)

    emit("login", {"username": username})
    try:
        token        = get_token(username, password)
        key_user_id  = decode_key_user_id(token)
        account_name = decode_account_name(token)
        emit("login_ok", {"key_user_id": key_user_id, "account_name": account_name})
    except Exception as e:
        emit("login_fail", {"msg": str(e)})
        return {"results": []}

    headers = make_headers(token)

    # Load log untuk cek status
    dl_log    = load_download_log()
    try:
        import merge_core as _core
        ml_log = _core.load_processed_keys()
    except Exception:
        ml_log = set()

    results = []
    for is_finish in [False, True]:
        try:
            resp = requests.get(
                f"{BASE_URL}/xsyst/api/engineer-service-orders",
                params={
                    "keyUserId"         : key_user_id,
                    "isFinish"          : "true" if is_finish else "false",
                    "onlyMyTask"        : "true",
                    "customerDetailName": keyword,
                    "startDate"         : "",
                    "endDate"           : "",
                },
                headers=headers, timeout=30,
            )
            orders = resp.json().get("data", []) or []
        except Exception:
            orders = []

        for o in orders:
            number    = o.get("support_number", "")
            customer  = o.get("customer_detail_name", "")
            type_code = o.get("support_type_code", "")
            type_name = o.get("support_type", "")
            status    = o.get("current_status_name", "")
            processed = o.get("latest_processed_date", "")

            stba_file = f"{number}_STBA.pdf".replace("/", "-")
            stat_file = f"{number}_STAT.pdf".replace("/", "-")
            in_dl_log  = stba_file in dl_log or stat_file in dl_log
            in_mg_log  = number.split("/")[-1] in ml_log if number else False

            dl_status = "merged" if in_mg_log else ("downloaded" if in_dl_log else "new")
            results.append({
                "number"   : number,
                "customer" : customer,
                "type_code": type_code,
                "type_name": type_name,
                "status"   : status,
                "processed": processed,
                "dl_status": dl_status,
            })

    return {"results": results}


def run_download(username: str, password: str,
                 date_from, date_to,
                 save_dir: str,
                 type_filter: list = None,
                 cb=None) -> dict:
    """
    Jalankan proses download dengan callback untuk streaming.
    Events: login, login_ok, login_fail, fetch, scan,
            download_ok, download_skip, download_fail, done, error
    """
    def emit(event, data):
        if cb: cb(event, data)

    os.makedirs(save_dir, exist_ok=True)

    # Login
    emit("login", {"username": username})
    try:
        token        = get_token(username, password)
        key_user_id  = decode_key_user_id(token)
        account_name = decode_account_name(token)
        emit("login_ok", {"key_user_id": key_user_id, "account_name": account_name})
    except Exception as e:
        emit("login_fail", {"msg": str(e)})
        return {"success": False, "saved": 0, "skipped": 0, "failed": 0}

    headers        = make_headers(token)
    downloaded_log = load_download_log()
    emit("log_loaded", {"total_logged": len(downloaded_log)})

    # Ambil order
    emit("fetch", {"msg": "Mengambil daftar order..."})
    try:
        orders_active = fetch_orders(headers, key_user_id, is_finish=False,
                                     date_from=date_from, date_to=date_to)
        # isFinish=true mungkin return kosong di versi API terbaru — handle gracefully
        try:
            orders_finished = fetch_orders(headers, key_user_id, is_finish=True,
                                           date_from=date_from, date_to=date_to)
        except Exception:
            orders_finished = []
    except Exception as e:
        emit("error", {"msg": f"Gagal ambil order: {e}"})
        return {"success": False, "saved": 0, "skipped": 0, "failed": 0}

    seen, all_orders = set(), []
    for o in orders_active + orders_finished:
        oid = o.get("service_order_id")
        if oid not in seen:
            seen.add(oid)
            all_orders.append(o)

    qualified = []
    skipped_status = skipped_date = skipped_type = 0
    for order in all_orders:
        type_code = order.get("support_type_code", "")
        # Filter tipe jika ada
        if type_filter and type_code not in type_filter:
            skipped_type += 1
            continue
        if not should_download(type_code, order.get("current_status_code", "")):
            skipped_status += 1
            continue
        processed = parse_date(order.get("latest_processed_date"))
        if not processed or not (date_from <= processed <= date_to):
            skipped_date += 1
            continue
        qualified.append(order)

    emit("scan", {
        "total"         : len(all_orders),
        "qualified"     : len(qualified),
        "skipped_status": skipped_status,
        "skipped_date"  : skipped_date,
        "skipped_type"  : skipped_type,
        "date_from"     : str(date_from),
        "date_to"       : str(date_to),
    })

    # Download
    total_saved = total_skip = total_fail = 0
    for order in qualified:
        order_id  = order.get("service_order_id")
        number    = order.get("support_number", str(order_id))
        customer  = order.get("customer_detail_name", "")
        processed = parse_date(order.get("latest_processed_date"))

        try:
            detail    = fetch_order_detail(headers, key_user_id, order_id)
            documents = detail.get("service_documents", [])
        except Exception as e:
            emit("download_fail", {"number": number, "doc_code": "-", "msg": str(e)})
            total_fail += 1
            continue

        for doc in documents:
            doc_code = doc.get("document_type_code", "")
            if doc_code not in TARGET_DOCS:
                continue
            status_file = save_document(number, doc, save_dir)
            filename    = f"{number}_{doc_code}.pdf"
            cur_status  = order.get("current_status_code", "")
            if status_file == "ok":
                total_saved += 1
                emit("download_ok", {
                    "number"  : number,
                    "doc_code": doc_code,
                    "filename": filename,
                    "customer": customer,
                    "date"    : str(processed) if processed else "",
                })
            elif status_file == "skip":
                total_skip += 1
                # Bedakan: FN→CL (sudah diproses sebelumnya) vs skip biasa
                reason = "sudah diproses saat FN" if cur_status == "CL" and \
                    order.get("support_type_code") == "SERV" else "sudah ada"
                emit("download_skip", {
                    "number"  : number,
                    "doc_code": doc_code,
                    "filename": filename,
                    "reason"  : reason,
                })
            else:
                total_fail += 1
                emit("download_fail", {
                    "number"  : number,
                    "doc_code": doc_code,
                    "msg"     : "Decode gagal / data kosong",
                })

    result = {
        "success"     : True,
        "saved"       : total_saved,
        "skipped"     : total_skip,
        "failed"      : total_fail,
        "save_dir"    : save_dir,
        "account_name": account_name,
    }
    emit("done", result)
    return result


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────

def _input_tanggal(prompt: str):
    while True:
        raw = input(prompt).strip()
        try:
            return datetime.strptime(raw, "%d-%m-%Y").date()
        except ValueError:
            print("  Format salah. Gunakan DD-MM-YYYY (contoh: 01-03-2026)")


def main():
    # Import load_config dari merge_core jika tersedia
    try:
        import merge_core as _core
        cfg      = _core.load_config()
        username = cfg.get("xea_username", "")
        password = cfg.get("xea_password", "")
        save_dir = cfg.get("source_dir", "/storage/emulated/0/Download/galva_docs")
    except ImportError:
        # Fallback jika merge_core tidak tersedia
        username = password = ""
        save_dir = "/storage/emulated/0/Download/galva_docs"

    if not username:
        username = input("Username XEA: ").strip()
    if not password:
        import getpass
        password = getpass.getpass("Password XEA: ")

    print("=" * 50)
    print("  Galva Auto-Download")
    print("=" * 50)

    date_from = _input_tanggal("Dari tanggal  : ")
    date_to   = _input_tanggal("Sampai tanggal: ")
    if date_from > date_to:
        date_from, date_to = date_to, date_from

    def cli_cb(event, data):
        if event == "login":
            print(f"\nLogin sebagai {data['username']}...")
        elif event == "login_ok":
            print(f"Login berhasil! (keyUserId: {data['key_user_id']})")
        elif event == "login_fail":
            print(f"Login gagal: {data['msg']}")
        elif event == "scan":
            print(f"Total: {data['total']}  Diproses: {data['qualified']}  "
                  f"Skip status: {data['skipped_status']}  Skip tanggal: {data['skipped_date']}")
            print(f"Rentang: {data['date_from']} → {data['date_to']}")
            print("=" * 50)
        elif event == "download_ok":
            print(f"  [OK]   {data['filename']}  ({data['customer']})")
        elif event == "download_skip":
            print(f"  [SKIP] {data['filename']}")
        elif event == "download_fail":
            print(f"  [FAIL] {data['number']} — {data.get('msg','')}")
        elif event == "done":
            print(f"\n{'=' * 50}")
            print(f"Selesai! OK:{data['saved']}  Skip:{data['skipped']}  Gagal:{data['failed']}")
            print(f"Lokasi: {data['save_dir']}")

    run_download(username, password, date_from, date_to, save_dir, cli_cb)


if __name__ == "__main__":
    main()
