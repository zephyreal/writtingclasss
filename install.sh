#!/usr/bin/env bash
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then echo '请在root终端执行'; exit 1; fi
cd "$(dirname "$0")"
SOURCE_DIR="$PWD"
if [ -e /opt/writing-class/app.py ]; then echo '/opt/writing-class 已有安装；本脚本不会覆盖。请按README更新步骤操作。'; exit 1; fi
if [ -e /etc/nginx/sites-enabled/writing-class ]; then echo '已有同名Nginx配置，请先检查'; exit 1; fi
apt-get update
apt-get install -y python3-venv python3-pip nginx curl libreoffice-writer fonts-noto-cjk
id writingclass >/dev/null 2>&1 || useradd --system --home /var/lib/writing-class --shell /usr/sbin/nologin writingclass
install -d -m 755 /opt/writing-class
cp -r "$SOURCE_DIR/adaptive_practice.py" "$SOURCE_DIR/practice_bank.py" "$SOURCE_DIR/question_bank" "$SOURCE_DIR/writing_workflow.py" "$SOURCE_DIR/writing_slides.py" "$SOURCE_DIR/app.py" "$SOURCE_DIR/review_pipeline.py" "$SOURCE_DIR/paper_queue.py" "$SOURCE_DIR/english_course.py" "$SOURCE_DIR/english_speech.py" "$SOURCE_DIR/vendor" "$SOURCE_DIR/seed.py" "$SOURCE_DIR/manage.py" "$SOURCE_DIR/static" "$SOURCE_DIR/course_assets" "$SOURCE_DIR/requirements.txt" /opt/writing-class/
python3 -m venv /opt/writing-class/.venv
/opt/writing-class/.venv/bin/pip install -r /opt/writing-class/requirements.txt
install -d -o writingclass -g writingclass -m 700 /var/lib/writing-class
cd /opt/writing-class
runuser -u writingclass -- env DATA_DIR=/var/lib/writing-class TZ=Asia/Shanghai /opt/writing-class/.venv/bin/python manage.py create-teacher --account teacher
install -m 644 "$SOURCE_DIR/deploy/writing-class.service" /etc/systemd/system/writing-class.service
install -m 644 "$SOURCE_DIR/deploy/nginx.conf" /etc/nginx/sites-available/writing-class
if [ -e /etc/nginx/sites-enabled/default ]; then cp -L /etc/nginx/sites-enabled/default "/etc/nginx/default.backup.$(date +%Y%m%d%H%M%S)"; rm /etc/nginx/sites-enabled/default; fi
ln -s /etc/nginx/sites-available/writing-class /etc/nginx/sites-enabled/writing-class
if ! nginx -t; then
    rm /etc/nginx/sites-enabled/writing-class
    [ ! -f /etc/nginx/sites-available/default ] || ln -s /etc/nginx/sites-available/default /etc/nginx/sites-enabled/default
    echo 'Nginx校验失败，已撤回新站点链接，请检查其他配置'; exit 1
fi
systemctl daemon-reload
systemctl enable --now writing-class
systemctl reload nginx
for attempt in 1 2 3 4 5; do
    if curl -fsS http://127.0.0.1:8000/healthz; then echo; echo '课程平台已启动。浏览器打开服务器HTTP地址。教师账号：teacher'; exit 0; fi
    sleep 1
done
echo '启动检查未通过，请执行 journalctl -u writing-class -n 60 --no-pager'; exit 1
