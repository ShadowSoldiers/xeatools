#!/data/data/com.termux/files/usr/bin/bash
# start_merge_web.sh — Auto-start via Termux:Boot dengan restart loop

INSTALL_DIR="$HOME/xeatools"
LOG="$INSTALL_DIR/server.log"

cd "$INSTALL_DIR" || exit 1

echo "[$(date)] Server starting..." >> "$LOG"

while true; do
  python merge_web.py >> "$LOG" 2>&1
  EXIT_CODE=$?

  if [ $EXIT_CODE -eq 42 ]; then
    echo "[$(date)] Restart setelah update (exit 42)" >> "$LOG"
    sleep 2
    continue
  else
    echo "[$(date)] Server berhenti (exit $EXIT_CODE)" >> "$LOG"
    break
  fi
done
