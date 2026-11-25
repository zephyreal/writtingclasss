'use strict';
/* Public, illustrative content only. No student/course API data or embedded engines. */
const GUEST_PAGES={
 writing:[['overview','学习概览'],['course','课程课件'],['practice','写作练习'],['assignments','课程作业'],['grades','学习成绩'],['profile','学习档案'],['messages','学生留言']],
 english:[['english','话题对话'],['englishHistory','记录与成绩'],['englishProfile','英语画像'],['messages','学生留言']],
 equipment:[['placeholder','课程介绍'],['messages','学生留言']],
 design:[['design','课程介绍'],['arena','五子棋算法竞赛'],['vehicle','无人车竞赛'],['messages','学生留言']]
};
const GUEST_FEATURES={
 overview:['学术论文写作','把论文写作拆成可练习、可反馈的步骤。',['阅读课程资料','完成短题练习','提交论文并逐轮修改'],'进入学习'],
 course:['课程课件','课程资料按主题组织，登录并加入课程后可查看和下载。',['文献检索与阅读','论文结构与学术表达','图表、投稿与修改'],'查看课程资料'],
 practice:['写作练习','每轮30道短题；完成后查看答案解析，后续练习根据已完成记录调整。',['阅读题目并选择答案','在教师设定的时限内完成一轮','查看错题解析并继续练习'],'开始练习'],
 assignments:['课程作业','查看教师要求，上传论文，结合反馈逐轮修改。具体轮次和截止时间以教师发布为准。',['阅读任务与评分要求','上传Word或文字型PDF','查看反馈并提交修改稿'],'查看并提交作业'],
 grades:['学习成绩','登录后查看自己的练习记录和教师发布的作业成绩。',['查看已完成练习','阅读分项反馈','跟踪论文修改表现'],'查看我的成绩'],
 profile:['学习档案','把学习过程和反馈放在一起，帮助确定下一步练什么、改什么。',['填写研究方向与学习目标','回顾练习表现','整理论文修改建议'],'查看我的档案'],
 english:['话题对话','选择工程或日常话题，与AI开展英语口语练习。',['选择话题与角色','允许麦克风并开始对话','结束后查看记录与反馈'],'开始口语对话'],
 englishHistory:['记录与成绩','回看已完成的口语练习及评价。',['查看练习记录','回顾表达与反馈','继续练习薄弱内容'],'查看我的记录'],
 englishProfile:['英语画像','根据自己的练习记录了解表达中的优点与可改进之处。',['积累对话记录','查看学习反馈','规划下一次练习'],'查看我的画像'],
 placeholder:['智能装备基础','课程内容正在建设中。已加入课程的学生可使用课程留言与教师交流。',['了解课程安排','关注教师发布内容','在课程留言中提问'],'登录查看课程'],
 design:['智能制造课程设计','从五子棋与无人车案例学习智能决策。学生在自己电脑上改进核心函数，上传后等待评测。',['下载示例并理解函数接口','本地修改、测试核心算法','上传核心代码，等待评测与回放'],'进入课程'],
 arena:['五子棋算法竞赛','编写落子决策核心函数，由平台在统一规则下评测。无需上传整个工程。',['学习棋盘输入与落子输出','在本地改进核心函数','上传代码，查看评测结果与棋谱'],'上传五子棋代码'],
 vehicle:['无人车竞赛','在统一车辆模型与地图下优化控制函数，与教师基线比较。',['学习状态输入与控制量输出','在本地优化循迹与速度控制','上传核心代码，排队计算并查看回放'],'上传无人车代码'],
 messages:['学生留言','在课程内提问、交流和查看教师回复。游客仅显示示例，不展示真实师生留言。',['进入已加入的课程','发布与课程相关的问题','查看回复或继续讨论'],'发布留言']
};
$('#guestEnter').onclick=()=>{
 if(user)return;
 guestMode=true;renderVersion++;$('#auth').hidden=true;$('#workspace').hidden=false;
 $('#userName').textContent='游客';$('#userRole').textContent='仅浏览 · 未登录';$('#avatar').textContent='客';
 $('#passwordBtn').hidden=true;$('#httpNotice').hidden=true;
 $('#logout').textContent='登录';$('#logout').title='登录或注册';
 selectGuestCourse(null);
};
const guestLogoutBase=$('#logout').onclick;
$('#logout').onclick=e=>guestMode?guestLogin():guestLogoutBase(e);
function guestLogin(){
 guestMode=false;renderVersion++;$('#modal').close();$('#workspace').hidden=true;$('#auth').hidden=false;
 $('#passwordBtn').hidden=false;$('#logout').textContent='↗';$('#logout').title='退出';
 reg=false;loginRole='student';renderAuth();
 $('#authDesc').textContent='登录后即可使用已加入课程的功能。新同学请使用教师提供的邀请码注册。';
}
function renderGuestNavigation(){
 const course=COURSES.find(c=>c.id===activeCourse);
 const items=[['portal','全部课程'],...(GUEST_PAGES[activeCourse]||[])];
 $('#nav').innerHTML=items.map(([id,label])=>`<button data-page="${id}">${esc(label)}</button>`).join('');
 $('#nav').onclick=e=>{const b=e.target.closest('[data-page]');if(!b)return;b.dataset.page==='portal'?selectGuestCourse(null):showGuestPage(b.dataset.page)};
 $('#courseSelector').value=activeCourse||'';$('#courseSelector').onchange=e=>selectGuestCourse(e.target.value||null);
 $('#headerCourse').textContent=course?.title||'课程教学平台';$('#sideCaption').textContent='游客浏览 · 登录后参与学习';
}
function selectGuestCourse(cid,target){
 activeCourse=COURSES.some(c=>c.id===cid)?cid:null;
 renderGuestNavigation();
 if(typeof history!=='undefined')history.replaceState(null,'',activeCourse?'#'+activeCourse:'#courses');
 showGuestPage(target||GUEST_PAGES[activeCourse]?.[0][0]||'portal');
}
function guestIllustration(id){
 if(id==='practice')return '<div class="guest-example"><span class="badge">题目示例 · 不计分</span><h3>判断：结论应回应引言提出的研究问题。</h3><div class="actions"><button data-guest-login>A　正确</button><button data-guest-login>B　错误</button></div><p class="small muted">登录后开始正式练习；作答时限由教师设置。</p></div>';
 if(id==='messages')return '<div class="guest-example"><span class="badge">虚构留言示例</span><p><b>示例学生：</b>第一次参加课程，应从哪里开始？</p><p><b>示例教师：</b>先阅读课程说明，再按照任务步骤完成练习；遇到问题可以在这里提问。</p></div>';
 if(id==='arena')return '<div class="guest-example"><span class="badge">评测流程示意 · 非真实成绩</span><div class="guest-stages"><span>核心函数</span><span>排队评测</span><span>对局结果</span><span>棋谱复盘</span></div><p>输入棋盘状态 → 函数决定落子位置。排行榜与个人评测记录在登录后查看。</p></div>';
 if(id==='vehicle')return '<div class="guest-example"><span class="badge">评测流程示意 · 非实时仿真</span><div class="guest-stages"><span>控制函数</span><span>统一地图</span><span>离线计算</span><span>流畅回放</span></div><p>读取车辆状态 → 输出控制量。通过回放比较路线和运行表现，逐步改进算法。</p></div>';
 if(id==='english')return '<div class="guest-example"><span class="badge">虚构对话示例</span><p><b>AI：</b>Could you describe how a robotic arm works?</p><p><b>学习目标：</b>用简单英语说明设备的组成与动作。</p><p class="muted small">游客模式不会启用麦克风或发起AI对话。</p></div>';
 if(id==='assignments')return '<div class="guest-example"><span class="badge">作业界面示例</span><h3>论文草稿与修改</h3><p>任务要求 → 提交文件 → 阅读反馈 → 修改后提交</p><button data-guest-login>选择并上传文件</button><p class="small muted">实际题目、截止时间和评分要求登录后查看。</p></div>';
 return '<div class="guest-example"><span class="badge">功能预览</span><p>登录后显示与你的课程和账号对应的内容。游客页面不展示真实学生档案、作业或成绩。</p></div>';
}
function showGuestPage(id){
 if(!guestMode)return;
 if(id!=='portal'&&!(GUEST_PAGES[activeCourse]||[]).some(x=>x[0]===id))id='portal';
 page=id;renderVersion++;
 $('#nav').querySelectorAll('[data-page]').forEach(b=>b.classList.toggle('active',b.dataset.page===id));
 const banner='<section class="guest-banner"><div><b>游客浏览</b><span>了解课程界面与学习流程；参与练习、提交和交流需登录并加入课程。</span></div><button class="primary" data-guest-login>登录 / 注册</button></section>';
 let html;
 if(id==='portal'){
  $('#breadcrumb').textContent='游客浏览 / 全部课程';
  html=heading('先了解课程，再开始学习','四门课程，一个学习空间。点击课程即可浏览功能介绍。')+`<div class="course-grid">${COURSES.map(c=>`<article class="course-tile"><span class="course-icon">${esc(c.icon)}</span><h3>${esc(c.title)}</h3><p>${esc(c.description)}</p>${c.state==='planned'?'<span class="badge warn">内容建设中</span>':''}<button class="primary" data-guest-course="${c.id}">浏览课程 →</button></article>`).join('')}</div>`;
 }else{
  const [title,description,steps,action]=GUEST_FEATURES[id];
  $('#breadcrumb').textContent=(COURSES.find(c=>c.id===activeCourse)?.title||'课程')+' / '+title+' · 游客';
  html=heading(esc(title),esc(description))+`<div class="guest-layout"><article class="card"><span class="eyebrow">LEARNING PATH</span><h3>登录后，怎样使用？</h3><ol class="guest-steps">${steps.map(x=>`<li>${esc(x)}</li>`).join('')}</ol><button class="primary" data-guest-login>${esc(action)} · 需登录</button></article><article class="card">${guestIllustration(id)}</article></div>`;
  if(id==='design')html+='<div class="actions"><button data-guest-page="arena">浏览五子棋竞赛 →</button><button data-guest-page="vehicle">浏览无人车竞赛 →</button></div>';
 }
 $('#content').innerHTML=banner+html;
 $('#content').querySelectorAll('[data-guest-login]').forEach(b=>b.onclick=guestLogin);
 $('#content').querySelectorAll('[data-guest-course]').forEach(b=>b.onclick=()=>selectGuestCourse(b.dataset.guestCourse));
 $('#content').querySelectorAll('[data-guest-page]').forEach(b=>b.onclick=()=>showGuestPage(b.dataset.guestPage));
}
