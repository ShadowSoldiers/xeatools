#!/data/data/com.termux/files/usr/bin/bash
# start_manual.sh — Jalankan XEA Tools dengan auto-restart setelah update
# Exit code 42 dari merge_web.py = restart diminta (setelah apply update)
# Exit code lain = stop normal

INSTALL_DIR="$HOME/xeatools"
cd "$INSTALL_DIR" || {
  echo "ERROR: Folder $INSTALL_DIR tidak ditemukan."
  exit 1
}

# Hentikan instance lama jika ada
pkill -f "merge_web.py" 2>/dev/null
sleep 1

# Buka Chrome ke localhost:5000 (setelah server siap)
sleep 3 && termux-open-url http://localhost:5000 &

echo "========================================"
echo "  XEA Tools — Starting..."
echo "  Buka Chrome: http://localhost:5000"
echo "  Tekan Ctrl+C untuk berhenti"
echo "========================================"

while true; do
  python merge_web.py
  EXIT_CODE=$?

  if [ $EXIT_CODE -eq 42 ]; then
    echo ""
    echo "🔄 Update diterapkan — restart server..."
    sleep 2
    echo "▶ Memulai ulang XEA Tools..."
    # Buka ulang Chrome setelah restart
    sleep 3 && termux-open-url http://localhost:5000 &
    continue   # loop → jalankan lagi
  else
    echo ""
    echo "Server berhenti (exit code: $EXIT_CODE)."
    break
  fi
done
