#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT_DIR="$SCRIPT_DIR"
LOG_DIR="$ROOT_DIR/var/local-logs"

UP_SCRIPT="$ROOT_DIR/up.sh"
JAVA_DIR="$ROOT_DIR"
PY_DIR="$ROOT_DIR/learning-agent-service"
FRONTEND_DIR="$ROOT_DIR/yu-ai-code-mother-frontend"

JAVA_OUT_LOG="$LOG_DIR/java-backend.out.log"
JAVA_ERR_LOG="$LOG_DIR/java-backend.err.log"
PY_OUT_LOG="$LOG_DIR/uvicorn.out.log"
PY_ERR_LOG="$LOG_DIR/uvicorn.err.log"
FRONTEND_OUT_LOG="$LOG_DIR/frontend.out.log"
FRONTEND_ERR_LOG="$LOG_DIR/frontend.err.log"

JAVA_HEALTH_URL="http://127.0.0.1:8123/api/health/"
PY_HEALTH_URL="http://127.0.0.1:9000/health"
FRONTEND_URL="http://127.0.0.1:5173/"
FRONTEND_OPEN_URL="http://localhost:5173/"

mkdir -p "$LOG_DIR"

to_windows_path() {
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -w "$1"
  elif command -v wslpath >/dev/null 2>&1; then
    wslpath -w "$1"
  else
    printf '%s\n' "$1"
  fi
}

wait_for_http() {
  label=$1
  url=$2
  attempts=${3:-60}

  i=0
  while [ "$i" -lt "$attempts" ]; do
    if curl -fsS "$url" >/dev/null 2>&1; then
      printf '%s 已就绪: %s\n' "$label" "$url"
      return 0
    fi
    i=$((i + 1))
    sleep 1
  done

  printf '%s 启动超时，请查看日志。\n' "$label" >&2
  return 1
}

start_detached_cmd() {
  label=$1
  working_dir_win=$2
  command_line=$3
  out_log_win=$4
  err_log_win=$5

  printf '启动 %s...\n' "$label"
  powershell.exe -NoProfile -Command "Start-Process -WindowStyle Hidden -FilePath 'cmd.exe' -WorkingDirectory '$working_dir_win' -ArgumentList @('/c', '$command_line') -RedirectStandardOutput '$out_log_win' -RedirectStandardError '$err_log_win'" >/dev/null 2>&1
}

wait_for_http_bg() {
  label=$1
  url=$2
  attempts=${3:-60}

  wait_for_http "$label" "$url" "$attempts" &
  printf '%s\n' $!
}

open_browser() {
  url=$1
  powershell.exe -NoProfile -Command "Start-Process '$url'" >/dev/null 2>&1 || true
}

JAVA_DIR_WIN=$(to_windows_path "$JAVA_DIR")
PY_DIR_WIN=$(to_windows_path "$PY_DIR")
FRONTEND_DIR_WIN=$(to_windows_path "$FRONTEND_DIR")
JAVA_OUT_LOG_WIN=$(to_windows_path "$JAVA_OUT_LOG")
JAVA_ERR_LOG_WIN=$(to_windows_path "$JAVA_ERR_LOG")
PY_OUT_LOG_WIN=$(to_windows_path "$PY_OUT_LOG")
PY_ERR_LOG_WIN=$(to_windows_path "$PY_ERR_LOG")
FRONTEND_OUT_LOG_WIN=$(to_windows_path "$FRONTEND_OUT_LOG")
FRONTEND_ERR_LOG_WIN=$(to_windows_path "$FRONTEND_ERR_LOG")

if [ ! -f "$UP_SCRIPT" ]; then
  printf '未找到基础启动脚本: %s\n' "$UP_SCRIPT" >&2
  exit 1
fi

printf '第一步: 启动 up.sh 中的基础服务...\n'
sh "$UP_SCRIPT"

printf '第二步: 并发启动 Java 后端、Python uvicorn 和前端...\n'
if curl -fsS "$JAVA_HEALTH_URL" >/dev/null 2>&1; then
  printf 'Java 后端已经在运行: %s\n' "$JAVA_HEALTH_URL"
else
  start_detached_cmd 'Java 后端' "$JAVA_DIR_WIN" 'call .\mvnw.cmd spring-boot:run' "$JAVA_OUT_LOG_WIN" "$JAVA_ERR_LOG_WIN"
fi

if curl -fsS "$PY_HEALTH_URL" >/dev/null 2>&1; then
  printf 'Python uvicorn 已经在运行: %s\n' "$PY_HEALTH_URL"
else
  start_detached_cmd 'Python uvicorn' "$PY_DIR_WIN" 'python -m uvicorn app:app --reload --host 127.0.0.1 --port 9000' "$PY_OUT_LOG_WIN" "$PY_ERR_LOG_WIN"
fi

if curl -fsS "$FRONTEND_URL" >/dev/null 2>&1; then
  printf '前端已经在运行: %s\n' "$FRONTEND_URL"
else
  start_detached_cmd '前端' "$FRONTEND_DIR_WIN" 'npm run dev -- --host 127.0.0.1' "$FRONTEND_OUT_LOG_WIN" "$FRONTEND_ERR_LOG_WIN"
fi

JAVA_WAIT_PID=
PY_WAIT_PID=
FRONTEND_WAIT_PID=

if ! curl -fsS "$JAVA_HEALTH_URL" >/dev/null 2>&1; then
  JAVA_WAIT_PID=$(wait_for_http_bg 'Java 后端' "$JAVA_HEALTH_URL" 180)
fi

if ! curl -fsS "$PY_HEALTH_URL" >/dev/null 2>&1; then
  PY_WAIT_PID=$(wait_for_http_bg 'Python uvicorn' "$PY_HEALTH_URL" 120)
fi

if ! curl -fsS "$FRONTEND_URL" >/dev/null 2>&1; then
  FRONTEND_WAIT_PID=$(wait_for_http_bg '前端' "$FRONTEND_URL" 120)
fi

for wait_pid in "$JAVA_WAIT_PID" "$PY_WAIT_PID" "$FRONTEND_WAIT_PID"; do
  if [ -n "$wait_pid" ]; then
    if ! wait "$wait_pid"; then
      exit 1
    fi
  fi
done

printf '全部启动完成。\n'
printf '前端访问地址: %s\n' "$FRONTEND_OPEN_URL"
open_browser "$FRONTEND_OPEN_URL"
printf '日志目录: %s\n' "$LOG_DIR"
printf 'Java 后端日志: %s / %s\n' "$JAVA_OUT_LOG" "$JAVA_ERR_LOG"
printf 'Python uvicorn 日志: %s / %s\n' "$PY_OUT_LOG" "$PY_ERR_LOG"
printf '前端日志: %s / %s\n' "$FRONTEND_OUT_LOG" "$FRONTEND_ERR_LOG"
