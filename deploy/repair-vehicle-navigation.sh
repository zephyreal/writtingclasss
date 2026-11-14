#!/usr/bin/env bash
# Restore the optional racing entry without replacing course files or student data.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo '请在网站服务器root终端执行'; exit 1; }
ROOT=/opt/writing-class
[ -f "$ROOT/gp_mpc_racing/integrated.py" ] || { echo '无人车扩展文件不存在，请重新运行GP-MPC-Racing的deploy/install-course.sh'; exit 1; }
[ -f "$ROOT/course_access.py" ] || { echo '课程权限文件不存在，停止修复'; exit 1; }
install -d -m 700 /root/course-backups
BACKUP=$(mktemp -d /root/course-backups/vehicle-navigation-XXXXXX)
cp -p "$ROOT/course_access.py" "$BACKUP/course_access.py"
OVERRIDE=/etc/systemd/system/writing-class.service.d/vehicle-racing.conf
if [ -f "$OVERRIDE" ]; then cp -p "$OVERRIDE" "$BACKUP/vehicle-racing.conf"; fi
rollback(){
    status=$?
    if [ "$status" -ne 0 ]; then
        cp -p "$BACKUP/course_access.py" "$ROOT/course_access.py"
        if [ -f "$BACKUP/vehicle-racing.conf" ]; then cp -p "$BACKUP/vehicle-racing.conf" "$OVERRIDE"; else rm -f "$OVERRIDE"; fi
        systemctl daemon-reload
        systemctl restart writing-class || true
        echo "修复检查未通过，已恢复原文件。备份：$BACKUP"
    fi
}
trap rollback EXIT
"$ROOT/.venv/bin/python" - <<'PY'
from pathlib import Path
p=Path('/opt/writing-class/course_access.py');s=p.read_text()
needle='def gated_course(path):\n'
assert needle in s, '未识别课程权限版本，停止修改'
rule="    if path=='/courses/design/vehicle/entry.js':return None\n"
if rule not in s:s=s.replace(needle,needle+'    # Public navigation only; course content remains protected.\n'+rule,1)
compile(s,str(p),'exec');p.write_text(s)
PY
install -d -m 755 /etc/systemd/system/writing-class.service.d
cat > "$OVERRIDE" <<'SERVICE'
[Service]
ExecStart=
ExecStart=/opt/writing-class/.venv/bin/uvicorn gp_mpc_racing.integrated:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips=127.0.0.1
SERVICE
systemctl daemon-reload
systemctl restart writing-class
for attempt in 1 2 3 4 5 6 7 8; do
    if "$ROOT/.venv/bin/python" - <<'PY'
import urllib.request, urllib.error
base='http://127.0.0.1:8000'
try:
    with urllib.request.urlopen(base+'/',timeout=3) as r:assert '/courses/design/vehicle/entry.js' in r.read().decode()
    with urllib.request.urlopen(base+'/courses/design/vehicle/entry.js',timeout=3) as r:assert 'views.vehicle' in r.read().decode()
    try:urllib.request.urlopen(base+'/courses/design/vehicle/',timeout=3)
    except urllib.error.HTTPError as e:assert e.code==401
    else:raise AssertionError('课程页面未要求登录')
except Exception:raise SystemExit(1)
PY
    then
        trap - EXIT
        echo "无人车入口已恢复：导航脚本可加载，课程页面仍需登录。请Ctrl+F5后重新登录。备份：$BACKUP"
        exit 0
    fi
    sleep 1
done
exit 1
