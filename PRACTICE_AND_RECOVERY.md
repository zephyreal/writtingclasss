# 写作练习设置与账号找回

## 教师操作

- 学术论文写作 → 写作练习 → 练习时间设置：每题5—300秒，默认保留10秒，建议初学者30—60秒。只影响新开始的一轮；正在作答的轮次保留原时限，重启后设置保留。
- 任一课程 → 学生管理 → 处理找回密码申请：显示全平台学生申请。通过登记电话或当面核实本人身份后生成一次性重置码，单独告知该学生。重置码30分钟有效，重新生成使旧码失效；关闭申请也会作废重置码。
- 学术论文写作 → 学生留言：课程内发帖和回复，教师可删除不适当内容；其他课程留言独立。

## 学生操作

- 登录页 → 忘记密码：填写注册学号与登记电话提交申请，联系教师领取重置码。
- 忘记密码 → 已有重置码：输入学号、电话、重置码、新密码及确认密码。成功后重新登录。
- 未登记或更换了电话号码，请直接联系教师核对；教师仍可从学生管理执行现有的密码重置操作。教师账号由服务器管理员处理。
- 本版本没有接入短信服务，不会自动发送短信。电话和学号只用于定位账号，不能单独授权修改密码。

## 修复说明

原先后台会打乱判断题选项，前端却固定给第一项配✓、第二项配✕，可能显示“✓ 错误 / ✕ 正确”。新轮次固定判断题顺序为“正确 / 错误”，前端统一显示A/B选项编号，因此旧会话即使保留相反顺序也不会产生符号矛盾。评分仍使用该轮保存的答案索引，不篡改历史作答记录。

核查了题库640题的结构、重复题干、答案映射与192道判断题的题干/答案/解析对应关系。本次修复针对选项显示与顺序，未改写题库或历史成绩。

## 接口

所有写请求仍需 `X-App-Request: 1`，同源校验沿用现有设置。

| 接口 | 权限与内容 |
|---|---|
| GET/PUT `/api/teacher/practice/settings` | 教师；PUT `{ "seconds": 60 }`，整数5—300 |
| POST `/api/password-recovery/request` | 登录前；`student_no`、`phone`，存在与不存在账号均返回同样的受理提示 |
| GET `/api/teacher/password-recovery` | 教师；未过期申请列表，不返回密码或码的哈希 |
| POST `/api/teacher/password-recovery/{uid}/approve` | 教师；核实身份后提交 `{ "verified": true }`，仅生成时返回重置码 |
| DELETE `/api/teacher/password-recovery/{uid}` | 教师；关闭申请及作废码 |
| POST `/api/password-recovery/reset` | 登录前；`student_no`、`phone`、`code`、`password`，密码至少10位 |

申请保留7天；码仅存哈希，绑定申请时账号密码及电话版本。密码或电话变化、账号删除、码过期均使其失效。重置在事务内完成并撤销该账号所有登录会话，记录审计；按IP与学号限制尝试次数。其他账号及课程资料保留。

## 升级

使用仓库现有 `upgrade.sh`，自动备份并迁移数据库。升级后Ctrl+F5刷新；无需重新安装无人车模块。

## 验证

```bash
python -m pytest -q test_adaptive_practice.py test_password_recovery.py test_course_community.py test_course_admin.py test_login_roles.py test_vehicle_navigation_access.py
node test_practice_frontend.cjs
node test_password_recovery_frontend.cjs
node test_course_community_frontend.cjs
node test_course_admin_frontend.cjs
node test_login_entry_frontend.cjs
```
