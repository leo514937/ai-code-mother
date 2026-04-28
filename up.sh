#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT_DIR="$SCRIPT_DIR"
LOG_DIR="$ROOT_DIR/var/local-logs"
SERVICE_SCRIPT="$ROOT_DIR/learning-agent-service/scripts/up.sh"
ADMIN_BASH_EXE='C:\Program Files\Git\bin\bash.exe'
POSTGRES_SERVER_DIR='D:\software\PostgreSQL\16\Server'
POSTGRES_DATA_DIR='D:\software\PostgreSQL\16\Data'
POSTGRES_PORT=5432

mkdir -p "$LOG_DIR"

ps_out() {
  powershell.exe -NoProfile -Command "$1" 2>/dev/null | tr -d '\r'
}

to_windows_path() {
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -w "$1"
  elif command -v wslpath >/dev/null 2>&1; then
    wslpath -w "$1"
  else
    printf '%s\n' "$1"
  fi
}

is_admin() {
  ps_out "[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)"
}

relaunch_as_admin() {
  script_win_path=$(to_windows_path "$ROOT_DIR/up.sh")
  root_win_path=$(to_windows_path "$ROOT_DIR")
  powershell.exe -NoProfile -Command "Start-Process -Verb RunAs -FilePath '$ADMIN_BASH_EXE' -ArgumentList @('$script_win_path','--elevated') -WorkingDirectory '$root_win_path'" >/dev/null 2>&1
}

if [ "${1-}" != "--elevated" ] && [ "$(is_admin)" != "True" ]; then
  printf '检测到非管理员权限，正在弹出 UAC 以管理员身份重启脚本...\n'
  if relaunch_as_admin; then
    exit 0
  fi
  printf '自动提权失败，请手动以管理员权限重新运行 bash up.sh\n' >&2
  exit 1
fi

service_exists() {
  service_name=$1
  ps_out "if (Get-Service -Name '$service_name' -ErrorAction SilentlyContinue) { Write-Output '$service_name' }"
}

service_exists_by_pattern() {
  pattern=$1
  ps_out "\$svc = Get-Service | Where-Object { \$_.Name -match '$pattern' -or \$_.DisplayName -match '$pattern' } | Select-Object -First 1; if (\$svc) { Write-Output \$svc.Name }"
}

stop_service() {
  service_name=$1
  printf '停止服务: %s\n' "$service_name"
  powershell.exe -NoProfile -Command "Stop-Service -Name '$service_name' -Force -ErrorAction SilentlyContinue" >/dev/null 2>&1 || true
}

start_service() {
  service_name=$1
  printf '启动服务: %s\n' "$service_name"
  powershell.exe -NoProfile -Command "Start-Service -Name '$service_name' -ErrorAction Stop" >/dev/null 2>&1
}

restart_service_if_present() {
  service_name=$1
  resolved_name=$2

  if [ -z "$resolved_name" ]; then
    printf '未检测到服务，跳过: %s\n' "$service_name" >&2
    return 0
  fi

  stop_service "$resolved_name"
  sleep 1
  start_service "$resolved_name"
  sleep 2
}

postgres_local_bin_exists() {
  [ -x "$POSTGRES_SERVER_DIR/bin/pg_ctl.exe" ]
}

postgres_is_running() {
  powershell.exe -NoProfile -Command "if (Get-NetTCPConnection -LocalPort $POSTGRES_PORT -ErrorAction SilentlyContinue | Select-Object -First 1) { exit 0 } else { exit 1 }" >/dev/null 2>&1
}

start_local_postgres() {
  if postgres_is_running; then
    printf 'PostgreSQL 已经在运行: 127.0.0.1:%s\n' "$POSTGRES_PORT"
    return 0
  fi

  if ! postgres_local_bin_exists; then
    printf '未找到本地 PostgreSQL 二进制目录，跳过: %s\n' "$POSTGRES_SERVER_DIR" >&2
    return 0
  fi

  mkdir -p "$ROOT_DIR/var/local-logs"
  printf '启动 PostgreSQL 本地进程: %s\n' "$POSTGRES_SERVER_DIR/bin/pg_ctl.exe"
  "$POSTGRES_SERVER_DIR/bin/pg_ctl.exe" -D "$POSTGRES_DATA_DIR" -l "$ROOT_DIR/var/local-logs/postgresql.log" start >/dev/null 2>&1 || true

  if postgres_is_running; then
    printf 'PostgreSQL 启动成功: 127.0.0.1:%s\n' "$POSTGRES_PORT"
  else
    printf 'PostgreSQL 启动失败，请查看日志: %s\n' "$ROOT_DIR/var/local-logs/postgresql.log" >&2
    exit 1
  fi
}

stop_local_postgres() {
  if ! postgres_is_running; then
    return 0
  fi

  if ! postgres_local_bin_exists; then
    return 0
  fi

  printf '停止 PostgreSQL 本地进程: 127.0.0.1:%s\n' "$POSTGRES_PORT"
  "$POSTGRES_SERVER_DIR/bin/pg_ctl.exe" -D "$POSTGRES_DATA_DIR" stop -m fast >/dev/null 2>&1 || true
}

printf '检查 MySQL...\n'
MYSQL_SERVICE=$(service_exists mysql || true)
restart_service_if_present 'mysql' "$MYSQL_SERVICE"

printf '检查 PostgreSQL...\n'
POSTGRES_SERVICE=$(service_exists_by_pattern 'postgres|pgsql|postgre' || true)
if [ -n "$POSTGRES_SERVICE" ]; then
  restart_service_if_present 'postgresql' "$POSTGRES_SERVICE"
else
  stop_local_postgres
  start_local_postgres
fi

if [ ! -f "$SERVICE_SCRIPT" ]; then
  printf '未找到子脚本: %s\n' "$SERVICE_SCRIPT" >&2
  exit 1
fi

printf '重启 Redis / Qdrant...\n'
sh "$SERVICE_SCRIPT"

printf '全部完成。日志目录: %s\n' "$LOG_DIR"
