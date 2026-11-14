"""启用模型示例前备份学生代码；失败不覆盖。"""
import subprocess, sys, shutil
from datetime import datetime
from pathlib import Path
root=Path(__file__).resolve().parent
subprocess.run([sys.executable,'-m','pip','install','-r',str(root/'requirements.txt')],check=True)
# 验证本场模型可加载，成功后才切换示例。
import gomoku_model
backup=root/'output'/('code-backup-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
backup.mkdir(parents=True)
shutil.copy2(root/'agent.py',backup/'agent.py')
shutil.copy2(root/'agent_model_example.py',root/'agent.py')
print('已启用进阶示例。原代码备份：',backup/'agent.py')
print('运行START.bat试跑；最后仍只上传agent.py。')
