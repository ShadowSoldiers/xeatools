#!/data/data/com.termux/files/usr/bin/bash
# ╔══════════════════════════════════════════════════════════╗
# ║  start_tunnel.sh — Cloudflare Tunnel untuk XEA Tools     ║
# ║  File ini terpisah dari aplikasi utama.                  ║
# ║  Jalankan SETELAH merge_web.py sudah berjalan.           ║
# ╚══════════════════════════════════════════════════════════╝

GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'
RED='\033[0;31m'; RESET='\033[0m'

LOCAL_PORT=5000
LOG_FILE="$HOME/merge_pdf/tunnel.log"

echo -e "${CYAN}══════════════════════════════════════${RESET}"
echo -e "${CYAN}  XEA Tools — Cloudflare Tunnel${RESET}"
echo -e "${CYAN}══════════════════════════════════════${RESET}"

# ── Cek server lokal berjalan ──────────────────────────────
if ! curl -s http://localhost:$LOCAL_PORT > /dev/null 2>&1; then
  echo -e "${RED}✗ Server XEA Tools tidak berjalan di port $LOCAL_PORT${RESET}"
  echo -e "  Jalankan dulu: ${CYAN}bash start_manual.sh${RESET}"
  exit 1
fi
echo -e "${GREEN}✓ Server lokal terdeteksi di port $LOCAL_PORT${RESET}"

# ── Cek Koneksi Internet / DNS ke Cloudflare ───────────────
echo -e "\n${CYAN}Mengecek koneksi ke server Cloudflare...${RESET}"
if ! ping -c 1 api.trycloudflare.com > /dev/null 2>&1; then
  echo -e "${RED}✗ Gagal menghubungi server Cloudflare.${RESET}"
  echo -e "${YELLOW}  Pastikan internet aktif dan DNS Anda tidak diblokir oleh ISP/Firewall.${RESET}"
  exit 1
fi
echo -e "${GREEN}✓ Koneksi ke server Cloudflare stabil${RESET}"

# ── Install cloudflared jika belum ada ────────────────────
if ! command -v cloudflared &> /dev/null; then
  echo -e "\n${CYAN}Install cloudflared...${RESET}"
  # Download binary untuk ARM64 (Android)
  ARCH=$(uname -m)
  if [[ "$ARCH" == "aarch64" ]]; then
    URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64"
  elif [[ "$ARCH" == "armv7l" ]]; then
    URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm"
  else
    URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
  fi

  curl -sSL "$URL" -o "$PREFIX/bin/cloudflared"
  chmod +x "$PREFIX/bin/cloudflared"

  if command -v cloudflared &> /dev/null; then
    echo -e "${GREEN}✓ cloudflared berhasil diinstall${RESET}"
  else
    echo -e "${RED}✗ Gagal install cloudflared${RESET}"
    exit 1
  fi
else
  echo -e "${GREEN}✓ cloudflared sudah terinstall${RESET}"
fi

# ── Hentikan tunnel lama jika ada ─────────────────────────
pkill -f "cloudflared tunnel" 2>/dev/null && echo -e "${YELLOW}⚠ Tunnel lama dihentikan${RESET}"
sleep 1

# ── Jalankan tunnel ────────────────────────────────────────
echo -e "\n${CYAN}Memulai Cloudflare Tunnel...${RESET}"
echo -e "${YELLOW}URL publik akan muncul di bawah dalam beberapa detik.${RESET}"
echo -e "${YELLOW}Tekan Ctrl+C untuk menghentikan tunnel.${RESET}\n"

# Jalankan dan parse URL dari output
cloudflared tunnel --url http://localhost:$LOCAL_PORT --edge-ip-version 4 2>&1 | tee -a "$LOG_FILE" | while IFS= read -r line; do
  echo "$line"
  
  # 1. Deteksi Error Koneksi dari log Cloudflare
  if echo "$line" | grep -q "failed to request quick Tunnel"; then
     echo -e "\n${RED}✗ ERROR: Cloudflare gagal membuat tunnel!${RESET}"
     echo -e "${YELLOW}  - Mungkin ada pemblokiran DNS di jaringan Anda.${RESET}"
     echo -e "${YELLOW}  - Coba ganti koneksi (misal: beralih dari WiFi ke Data Seluler).${RESET}"
  fi

  # 2. Deteksi URL tunnel & Exclude api.trycloudflare.com
 if echo "$line" | grep -qE "https://[a-z0-9]+-[a-z0-9]+-[a-z0-9-]+\.trycloudflare\.com" && ! echo "$line" | grep -q "api.trycloudflare.com"; then
    URL=$(echo "$line" | grep -oE "https://[a-z0-9]+-[a-z0-9]+-[a-z0-9-]+\.trycloudflare\.com" | grep -v "api.trycloudflare.com" | head -n 1)
    
    # Pastikan variabel URL tidak kosong sebelum menampilkannya
    if [ -n "$URL" ]; then
      echo ""
      echo -e "${GREEN}╔══════════════════════════════════════════════╗${RESET}"
      echo -e "${GREEN}║  URL Publik XEA Tools:                       ║${RESET}"
      echo -e "${GREEN}║  ${CYAN}${URL}${GREEN}  ║${RESET}"
      echo -e "${GREEN}╚══════════════════════════════════════════════╝${RESET}"
      echo ""
      echo -e "${YELLOW}⚠ URL ini berubah setiap kali tunnel dijalankan ulang.${RESET}"
      echo -e "${YELLOW}⚠ Bagikan hanya kepada yang berwenang.${RESET}"
      # Kirim notifikasi ke HP
      termux-notification \
        --title "XEA Tools — Tunnel Aktif" \
        --content "$URL" \
        --priority high 2>/dev/null
    fi
  fi
done
