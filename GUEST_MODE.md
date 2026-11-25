# 游客浏览

登录页点击“先逛逛 · 游客浏览”，无须账号即可浏览四门课程的功能介绍与示例界面。游客使用相同的课程切换、侧边导航和页面布局，不创建匿名账号或会话。

- 写作：概览、课件说明、练习示例、作业流程、成绩/档案说明、留言示例。
- 英语：话题对话示例、记录与反馈说明。
- 智能装备基础：标明内容建设中，展示课程与留言说明。
- 智能制造课程设计：五子棋和无人车核心函数提交流程、评测与回放说明。

示例明确标注为功能预览或虚构示例，不查询真实课程数据、不启动计时练习、不加载竞赛引擎iframe、不启用麦克风或AI服务。点击操作按钮转到学生登录页，可选择学生注册或教师登录；登录后仍需相应课程权限，教师管理入口保持原逻辑。

本次没有放开任何受保护API或课程资产。即使绕过前端，未登录访问练习、作业、师生资料、课程留言、英语接口及竞赛内容仍返回401。游客页面只包含公开介绍，任何人都可查看其静态内容。

升级沿用 `upgrade.sh`，无需数据库迁移或额外配置；升级后Ctrl+F5刷新。

验证：

```bash
node test_guest_mode_frontend.cjs
node test_login_entry_frontend.cjs
node test_course_community_frontend.cjs
node test_practice_frontend.cjs
python -m pytest -q test_guest_access.py test_course_community.py test_login_roles.py test_vehicle_navigation_access.py
```

前端回归覆盖四门课全部游客页面、无受保护数据请求、无人车扩展视图拦截、转登录及恢复正式学生/教师视图。后端回归覆盖公开预览文件与受保护接口的匿名拒绝、原课程留言与导航权限。
