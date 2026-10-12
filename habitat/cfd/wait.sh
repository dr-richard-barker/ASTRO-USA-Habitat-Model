#!/bin/sh
# Block until a case finishes: exits 0 on DONE, 1 on FAILED or if the driver process vanished without a verdict.
case_dir="$1"
while :; do
  s=$(head -1 "$case_dir/STATUS" 2>/dev/null)
  case "$s" in
    DONE*) echo "DONE"; exit 0 ;;
    FAILED*) echo "$s"; exit 1 ;;
    RUNNING*) pid=${s#RUNNING }; kill -0 "$pid" 2>/dev/null || { echo "DRIVER DIED (pid $pid) without a verdict"; exit 1; } ;;
  esac
  sleep 30
done
