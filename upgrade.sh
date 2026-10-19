#!/usr/bin/env bash
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then echo '请在root终端执行'; exit 1; fi
cd "$(dirname "$0")"
UPDATE_SOURCE="$PWD"
if [ ! -f /opt/writing-class/app.py ] || [ ! -d /opt/writing-class/.venv ]; then echo '未找到旧版安装，请先完成初次安装'; exit 1; fi
/opt/writing-class/.venv/bin/python -m py_compile "$UPDATE_SOURCE/app.py" "$UPDATE_SOURCE/review_pipeline.py"
echo '正在安装Word分页和PDF图像处理组件，首次安装可能需要数分钟'
apt-get update
apt-get install -y --no-install-recommends libreoffice-writer fonts-noto-cjk
/opt/writing-class/.venv/bin/pip install -r "$UPDATE_SOURCE/requirements.txt"
install -d -m 700 /root/course-backups
UPDATE_BACKUP="/root/course-backups/before-v1.2-$(date +%Y%m%d-%H%M%S).tar.gz"
systemctl stop writing-class
trap 'systemctl start writing-class || true' EXIT
backup_paths=(opt/writing-class/app.py opt/writing-class/seed.py opt/writing-class/manage.py opt/writing-class/static opt/writing-class/requirements.txt var/lib/writing-class)
if [ -f /opt/writing-class/review_pipeline.py ]; then backup_paths+=(opt/writing-class/review_pipeline.py); fi
tar -czf "$UPDATE_BACKUP" -C / "${backup_paths[@]}"
chmod 600 "$UPDATE_BACKUP"
cp "$UPDATE_SOURCE/app.py" "$UPDATE_SOURCE/review_pipeline.py" "$UPDATE_SOURCE/seed.py" "$UPDATE_SOURCE/requirements.txt" /opt/writing-class/
cp -r "$UPDATE_SOURCE/static/." /opt/writing-class/static/
cd /opt/writing-class
if ! runuser -u writingclass -- env DATA_DIR=/var/lib/writing-class TZ=Asia/Shanghai .venv/bin/python -c 'import app; print("数据库升级完成，已有账号、课件、作业和成绩已保留")'; then
    echo '迁移失败，恢复升级前代码和数据'
    tar -xzf "$UPDATE_BACKUP" -C /
    exit 1
fi
systemctl start writing-class
for attempt in 1 2 3 4 5 6 7 8; do
    if curl -fsS http://127.0.0.1:8000/healthz; then
        echo; echo 'v1.2升级成功，请Ctrl+F5刷新。教师账号和密码不变。'
        echo "升级前备份：$UPDATE_BACKUP"
        trap - EXIT
        exit 0
    fi
    sleep 1
done
echo '启动检查失败，自动恢复升级前版本'
systemctl stop writing-class
tar -xzf "$UPDATE_BACKUP" -C /
systemctl start writing-class
exit 1
