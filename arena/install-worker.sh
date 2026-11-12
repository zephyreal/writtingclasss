#!/usr/bin/env bash
# Run only on the dedicated evaluator, never as part of the teaching website upgrade.
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then echo '请在独立评测机的root终端执行'; exit 1; fi
if systemctl is-active --quiet writing-class; then echo '检测到课程网站正在本机运行，请在独立评测机执行此脚本'; exit 1; fi
ARENA_CONFIG_SOURCE="${1:-}"
if [ -z "$ARENA_CONFIG_SOURCE" ] || [ ! -f "$ARENA_CONFIG_SOURCE" ]; then echo '用法：bash arena/install-worker.sh /私有路径/arena-worker.json'; exit 1; fi
ARENA_CONFIG_SOURCE="$(realpath "$ARENA_CONFIG_SOURCE")"
ARENA_SOURCE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
command -v docker >/dev/null || { echo '请先在独立评测机安装Docker'; exit 1; }
command -v python3 >/dev/null || { echo '请先安装Python3与python3-venv'; exit 1; }
getent group docker >/dev/null || { echo '请先配置标准Docker运行环境与docker服务组'; exit 1; }
docker info --format '{{json .Runtimes}}' | python3 -c 'import json,sys;assert "runsc" in json.load(sys.stdin),"缺少gVisor/runsc，不允许降级"'
python3 - "$ARENA_CONFIG_SOURCE" <<'PY'
import json,os,sys
from urllib.parse import urlparse
p=sys.argv[1]
if os.stat(p).st_mode & 0o077:raise SystemExit('凭证文件必须为600权限，请先chmod 600')
c=json.load(open(p));u=urlparse(c['url'])
if u.scheme!='https' or not c.get('token') or not c.get('worker_id'):raise SystemExit('请保存教师网页生成的完整HTTPS评测机配置')
if c.get('image','writing-course-arena:v1')!='writing-course-arena:v1':raise SystemExit('本安装脚本使用writing-course-arena:v1，其他镜像请按说明手动部署')
PY
if systemctl cat course-arena-worker.service >/dev/null 2>&1; then systemctl stop course-arena-worker.service; fi
ARENA_WORKER_ID="$(python3 -c 'import json,sys,re;c=json.load(open(sys.argv[1]));v=c["worker_id"];assert re.fullmatch(r"[A-Za-z0-9_-]{3,60}",v);print(v)' "$ARENA_CONFIG_SOURCE")"
for ARENA_CONTAINER_ID in $(docker ps -aq --filter label=course-arena-managed=1 --filter "name=^/course-arena-$ARENA_WORKER_ID-"); do
    docker rm -f "$ARENA_CONTAINER_ID" >/dev/null
done
id arena-evaluator >/dev/null 2>&1 || useradd --system --home /var/lib/course-arena --shell /usr/sbin/nologin arena-evaluator
usermod -aG docker arena-evaluator
install -d -m 755 /opt/course-arena /opt/course-arena/arena /opt/course-arena/course_assets/gomoku
install -d -o arena-evaluator -g arena-evaluator -m 700 /var/lib/course-arena /etc/course-arena
if [ "$ARENA_SOURCE_ROOT" != /opt/course-arena ]; then
    cp "$ARENA_SOURCE_ROOT/arena_engine.py" /opt/course-arena/
    cp "$ARENA_SOURCE_ROOT/.dockerignore" /opt/course-arena/
    for file in Dockerfile requirements.txt requirements-worker.txt runner.py model_service.py worker.py smoke.py example_model.py train_example.py local_check.py STUDENT.md; do
        cp "$ARENA_SOURCE_ROOT/arena/$file" /opt/course-arena/arena/
    done
    cp "$ARENA_SOURCE_ROOT/course_assets/gomoku/gomoku_uint8_qop_u8u8.onnx" /opt/course-arena/course_assets/gomoku/
fi
python3 -m venv /opt/course-arena/.venv
/opt/course-arena/.venv/bin/pip install -r /opt/course-arena/arena/requirements-worker.txt
if [ "$ARENA_CONFIG_SOURCE" != /etc/course-arena/worker.json ]; then
    install -o arena-evaluator -g arena-evaluator -m 600 "$ARENA_CONFIG_SOURCE" /etc/course-arena/worker.json
else
    chown arena-evaluator:arena-evaluator /etc/course-arena/worker.json
    chmod 600 /etc/course-arena/worker.json
fi
cd /opt/course-arena
docker build -f arena/Dockerfile -t writing-course-arena:v1 .
runuser -u arena-evaluator -- env ARENA_WORK_DIR=/var/lib/course-arena /opt/course-arena/.venv/bin/python -m arena.smoke --image writing-course-arena:v1
# Start only after a genuine two-sandbox acceptance match has passed.
install -m 644 "$ARENA_SOURCE_ROOT/deploy/course-arena-worker.service" /etc/systemd/system/course-arena-worker.service
systemctl daemon-reload
systemctl enable course-arena-worker
systemctl restart course-arena-worker
systemctl status course-arena-worker --no-pager
echo '独立评测机已安装并通过隔离对弈验收；请回到教师网页查看连接状态。'
