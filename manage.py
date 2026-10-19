import argparse,getpass
from app import db,pwdhash
p=argparse.ArgumentParser();p.add_argument('command',choices=['create-teacher']);p.add_argument('--account',default='teacher');p.add_argument('--name',default='张老师');a=p.parse_args()
x=getpass.getpass('设置教师密码（至少10位，输入不显示）: ')
y=getpass.getpass('再次输入教师密码: ')
if x!=y or len(x)<10 or len(x)>128:raise SystemExit('密码不一致或长度不符合要求')
with db() as c:
    old=c.execute('SELECT role FROM users WHERE student_no=?',(a.account,)).fetchone()
    if old:raise SystemExit('账号已存在；为避免覆盖，不执行修改')
    from app import now
    c.execute("INSERT INTO users(name,student_no,password,role,created) VALUES(?,?,?,'teacher',?)",(a.name,a.account,pwdhash(x),now()))
print('教师账号已创建：'+a.account)
