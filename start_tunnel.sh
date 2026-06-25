#!/data/data/com.termux/files/usr/bin/bash
# ╔══════════════════════════════════════════════════════════╗
# ║  start_tunnel.sh — Cloudflare Tunnel untuk XEA Tools   ║
# ║  File ini terpisah dari aplikasi utama.                 ║
# ║  Jalankan SETELAH merge_web.py sudah berjalan.          ║
# ╚══════════════════════════════════════════════════════════╝

GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'
RED='\033[0;31m'; RESET='\033[0m'

LOCAL_PORT=5000
LOG_FILE="$HOME/xeatools/tunnel.log"

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
  # Deteksi URL tunnel — harus ada huruf dan angka random sebelum .trycloudflare.com
  # Exclude: api.trycloudflare.com (bukan URL tunnel)
  if echo "$line" | grep -qE "https://[a-z0-9]+-[a-z0-9]+-[a-z0-9-]+\.trycloudflare\.com"; then
    URL=$(echo "$line" | grep -oE "https://[a-z0-9]+-[a-z0-9]+-[a-z0-9-]+\.trycloudflare\.com")
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
done