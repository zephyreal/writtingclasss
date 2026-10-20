'use strict';
/* Timers render from the server deadline; a completed batch is the only record. */
let timedPractice=null, timedTicker=null, timedBusy=false, timedSequence=0;
const practiceDate=value=>new Date(value*1000).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false});
const practiceSource=value=>({random:'首次随机',ai:'AI安排',rules:'自动调整'}[value]||'自动调整');
function practiceStop(abandon=true){
 clearInterval(timedTicker);timedTicker=null;timedSequence++;
 const token=timedPractice?.token;timedPractice=null;timedBusy=false;
 if(abandon&&token)fetch('/api/practice/session/'+encodeURIComponent(token),{method:'DELETE',credentials:'same-origin',headers:{'X-App-Request':'1'},keepalive:true}).catch(()=>{});
}
window.addEventListener('pagehide',()=>practiceStop());
const practiceShowBase=show;
show=async function(id){practiceStop();return practiceShowBase(id)};
const practiceLogoutBase=$('#logout').onclick;
$('#logout').onclick=async e=>{practiceStop();return practiceLogoutBase(e)};

function practiceReviewHtml(r){
 return `<div class="practice-result-head"><strong>${r.correct}<small> / 30 题正确</small></strong><p>${r.timeouts?`${r.timeouts}题超时未答。`:''}${r.focus?.length?'下一轮重点：'+esc(r.focus.join('、'))+'。':'下一轮会继续覆盖各单元，巩固已有表现。'}</p></div><div class="practice-reviews">${r.items.map((q,i)=>`<details class="practice-review ${q.correct?'is-correct':'is-wrong'}"><summary><span>${q.correct?'✓':q.timed_out?'超时':'✕'}</span> ${i+1}. ${esc(q.stem)}</summary><div><p>你的选择：${q.choice===null?'未作答':esc(q.options[q.choice])}<br>正确答案：${esc(q.options[q.answer])}</p><p>${esc(q.explanation)}</p><small class="muted">${esc(q.topic_name)}</small>${PRACTICE_SOURCES[q.source]?` · <a href="${esc(PRACTICE_SOURCES[q.source][1])}" target="_blank" rel="noopener">参考资料 ↗</a>`:''}</div></details>`).join('')}</div>`;
}
const PRACTICE_SOURCES={
 question:['GMU','https://writingcenter.gmu.edu/writing-resources/research-based-writing/how-to-write-a-research-question'],
 review:['Purdue','https://owl.purdue.edu/owl/research_and_citation/conducting_research/writing_a_literature_review.html'],
 search:['Cornell','https://guides.library.cornell.edu/public-health/how-to-search-for-resources'],
 structure:['GMU','https://writingcenter.gmu.edu/writing-resources/imrad/imrad-results-discussion'],
 abstract:['UNC','https://writingcenter.unc.edu/tips-and-tools/abstracts/'],methods:['PLOS','https://journals.plos.org/plosone/s/submission-guidelines'],
 leakage:['scikit-learn','https://scikit-learn.org/stable/common_pitfalls.html'],figures:['UNC','https://writingcenter.unc.edu/tips-and-tools/figures-and-charts/'],
 errors:['Nature','https://www.nature.com/articles/nmeth.2659'],quote:['Purdue','https://owl.purdue.edu/owl/research_and_citation/using_research/quoting_paraphrasing_and_summarizing/index.html'],
 revision:['UNC','https://writingcenter.unc.edu/tips-and-tools/revising-drafts/'],ai:['COPE','https://doi.org/10.24318/cCVRZBms']
};
function practiceQuestion(active){
 if(page!=='practice'||!$('#practice-stage'))return;
 clearInterval(timedTicker);timedPractice=active;timedBusy=false;const serial=++timedSequence;
 const end=performance.now()+Math.max(0,active.deadline-active.server_now)*1000;
 const q=active.question;
 $('#practice-stage').innerHTML=`<article class="card practice-question"><div class="practice-top"><span>第 ${active.position+1} / 30 题 <small>· 第${q.chapter_id}单元</small></span><span id="practice-clock" class="practice-clock" aria-label="剩余作答时间">10秒</span></div><div class="bar practice-time"><i id="practice-time-bar"></i></div><h2 id="practice-stem">${esc(q.stem)}</h2><div class="practice-options" role="group" aria-labelledby="practice-stem">${q.options.map((o,i)=>`<button data-practice-choice="${i}"><span>${q.kind==='boolean'?(i===0?'✓':'✕'):'ABC'[i]}</span>${esc(o)}</button>`).join('')}</div><div class="practice-question-footer"><small class="muted">点击选项进入下一题</small><button id="practice-exit" class="text-btn">退出本轮</button></div><p id="practice-network" role="status" class="small muted"></p></article>`;
 let submittedChoice=null;
 async function send(choice,retry=false){
  if(serial!==timedSequence||timedBusy)return;
  timedBusy=true;submittedChoice=choice;
  $('#practice-stage')?.querySelectorAll('[data-practice-choice]').forEach(b=>{b.disabled=true;b.classList.toggle('selected',Number(b.dataset.practiceChoice)===choice)});
  try{
   const r=await api('/practice/session/'+encodeURIComponent(active.token)+'/answer','POST',{position:active.position,choice});
   if(serial!==timedSequence)return;
   clearInterval(timedTicker);
   if(r.finished){timedPractice=null;timedSequence++;practiceFinished(r.result)}else practiceQuestion(r.active);
  }catch(e){
   if(serial!==timedSequence)return;
   timedBusy=false;
   // Replaying the same position is idempotent, including the final commit.
   $('#practice-network').innerHTML=`${esc(e.message)} <button class="text-btn" id="practice-retry">重试提交</button>`;
   $('#practice-retry').onclick=()=>send(submittedChoice,true);
   if(!retry&&performance.now()<end){
    $('#practice-stage').querySelectorAll('[data-practice-choice]').forEach(b=>b.disabled=false);
   }
  }
 }
 $('#practice-stage').querySelectorAll('[data-practice-choice]').forEach(b=>b.onclick=()=>send(Number(b.dataset.practiceChoice)));
 $('#practice-exit').onclick=busy(async()=>{if(confirm('退出后，本轮不会计入练习记录。确定退出吗？')){await api('/practice/session/'+encodeURIComponent(active.token),'DELETE');practiceStop(false);show('practice')}});
 function tick(){
  if(serial!==timedSequence)return;
  const left=Math.max(0,(end-performance.now())/1000);
  $('#practice-clock').textContent=Math.ceil(left)+'秒';$('#practice-clock').classList.toggle('urgent',left<=3);
  $('#practice-time-bar').style.width=Math.min(100,left*10)+'%';
  if(left<=0&&!timedBusy&&!$('#practice-retry'))send(null);
 }
 timedTicker=setInterval(tick,100);tick();
}
function practiceFinished(r){
 $('#practice-stage').innerHTML=`<article class="card practice-results"><span class="unit">本轮已完成 · 已记录</span>${practiceReviewHtml(r)}<div class="practice-finish-actions"><button class="primary" id="practice-again">继续练习 →</button><button id="practice-back" class="text-btn">返回记录</button></div></article>`;
 $('#practice-again').onclick=busy(async e=>{e.target.disabled=true;try{practiceQuestion(await api('/practice/session','POST'))}finally{e.target.disabled=false}});
 $('#practice-back').onclick=()=>show('practice');
}
async function practiceStudentView(){
 const d=await api('/practice/session'),s=d.summary;
 return {html:heading('写作练习','每轮30题 · 每题10秒')+`<div class="practice-shell" id="practice-stage"><article class="card practice-welcome"><span class="eyebrow">ACADEMIC WRITING</span><h2>${s.rounds?'继续，把反馈练成方法。':'从一次小练习开始。'}</h2><p>${s.rounds?'根据已完成练习，自动调整后续题目。':'首轮随机覆盖八个单元，之后按你的答题情况调整。'}</p><button class="primary" id="practice-start">${d.active?'继续本轮':'开始30题练习'} →</button><small class="muted practice-rule">整轮完成才记录；超时未答计错，中途退出不记录。</small></article>${d.records.length?`<section class="practice-history"><h3>已完成 ${s.rounds} 轮</h3>${d.records.map(r=>`<button data-practice-record="${r.id}"><span>${esc(practiceDate(r.completed))}</span><span>${r.correct} / 30 <small>查看反馈 →</small></span></button>`).join('')}</section>`:''}</div>`,bind(){
  $('#practice-start').onclick=busy(async e=>{e.target.disabled=true;try{practiceQuestion(await api('/practice/session','POST'))}finally{e.target.disabled=false}});
  document.querySelectorAll('[data-practice-record]').forEach(b=>b.onclick=busy(async()=>{const r=await api('/practice/records/'+b.dataset.practiceRecord);modal('练习反馈',practiceReviewHtml(r))}));
 }};
}
async function practiceTeacherView(){
 const ss=await api('/teacher/practice/students');
 return {html:heading('练习记录','仅显示完成全部30题的练习。')+`<div class="card"><label class="practice-search-label">查找学生<input id="practice-search" placeholder="姓名或学号" autocomplete="off"></label><div class="table-wrap"><table><thead><tr><th>学生</th><th>已完成</th><th>累计正确率</th><th>最近练习</th><th>操作</th></tr></thead><tbody>${ss.map(s=>`<tr data-practice-student-search="${esc(s.name+' '+s.student_no)}"><td><b>${esc(s.name)}</b><small>${esc(s.student_no)}</small></td><td>${s.practice.rounds}轮</td><td>${s.practice.accuracy===null?'—':s.practice.accuracy+'%'}</td><td>${s.practice.latest?esc(practiceDate(s.practice.latest.completed)):'—'}</td><td><button class="text-btn" data-practice-student="${s.id}">查看记录</button></td></tr>`).join('')||'<tr><td colspan="5">尚无学生</td></tr>'}</tbody></table></div><p class="small muted">正确率用于安排练习，正式课程成绩仍由教师决定。累计正确率不用于学生排名。</p></div>`,bind(){
 $('#practice-search').oninput=e=>{const text=e.target.value.trim().toLowerCase();document.querySelectorAll('[data-practice-student-search]').forEach(tr=>tr.hidden=!tr.dataset.practiceStudentSearch.toLowerCase().includes(text))};
 document.querySelectorAll('[data-practice-student]').forEach(b=>b.onclick=busy(()=>practiceManageStudent(b.dataset.practiceStudent)));
 }};
}
async function practiceManageStudent(uid){
 const d=await api('/teacher/practice/students/'+uid);
 modal(esc(d.student.name)+' · 练习记录',`<p class="muted">${esc(d.student.student_no)} · 完成${d.summary.rounds}轮${d.summary.rounds>200?' · 下方显示最近200轮':''}</p><div class="practice-admin-records">${d.records.map(r=>`<div><span>${esc(practiceDate(r.completed))}<small>${r.correct}/30正确 · ${r.timeouts}题超时 · ${practiceSource(r.source)}</small></span><button class="text-btn" data-admin-practice="${r.id}">查看</button><button class="text-btn danger" data-delete-practice="${r.id}">删除</button></div>`).join('')||'<p>没有已完成记录</p>'}</div><div class="practice-admin-reset"><button id="practice-reset" class="danger">重置该生30题练习</button><p class="small muted">重置会删除本模块的全部记录与推荐依据，并结束正在进行的本轮；之后恢复首次随机。保留账号、论文作业、英语记录和旧版成绩。</p></div>`);
 document.querySelectorAll('[data-admin-practice]').forEach(b=>b.onclick=busy(async()=>{const r=await api('/teacher/practice/records/'+b.dataset.adminPractice);modal('练习详情',`<button class="text-btn" id="practice-manage-back">← 返回记录</button>${practiceReviewHtml(r)}`);$('#practice-manage-back').onclick=()=>practiceManageStudent(uid)}));
 function managementForm(action,id){
  const reset=action==='reset';modal(reset?'重置练习记录':'删除本轮记录',`<form id="practice-manage-form"><p>${reset?'删除该生所有30题练习，恢复首次随机。':'删除本轮，并按剩余记录重新安排后续练习。'}此操作不能撤销。</p><label>操作原因<input name="reason" required minlength="2" maxlength="300" placeholder="例如：教师安排重新诊断"></label><button class="danger">${reset?'确认重置':'确认删除'}</button><button type="button" id="practice-manage-cancel">取消</button></form>`);
  $('#practice-manage-cancel').onclick=()=>practiceManageStudent(uid);
  $('#practice-manage-form').onsubmit=busy(async e=>{const reason=new FormData(e.target).get('reason');await api(reset?'/teacher/practice/students/'+uid+'/reset':'/teacher/practice/records/'+id,reset?'POST':'DELETE',{reason});toast(reset?'已重置，下次从随机练习开始':'已删除，后续推荐将重新计算');if(user.role==='teacher'&&['practice','students'].includes(page)){const view=await views[page]();$('#content').innerHTML=view.html;view.bind?.()}await practiceManageStudent(uid)});
 }
 document.querySelectorAll('[data-delete-practice]').forEach(b=>b.onclick=()=>managementForm('delete',b.dataset.deletePractice));$('#practice-reset').onclick=()=>managementForm('reset');
}
views.practice=async()=>user.role==='teacher'?practiceTeacherView():practiceStudentView();
const practiceStudentsBase=views.students;
views.students=async()=>{
 const v=await practiceStudentsBase();v.html=v.html.replace(/(<button class="text-btn" data-profile="(\d+)">)/g,'<button class="text-btn" data-student-practice="$2">练习记录</button>　$1');
 const baseBind=v.bind;v.bind=()=>{baseBind?.();document.querySelectorAll('[data-student-practice]').forEach(b=>b.onclick=busy(()=>practiceManageStudent(b.dataset.studentPractice)))};return v;
};
views.overview=async()=>{
 const [chapters,p,assignments]=await Promise.all([api('/chapters'),api('/practice/session'),api('/assignments')]);const s=p.summary;
 return {html:heading('学习概览','把反馈带回下一次写作。')+`<div class="hero"><div><span class="eyebrow">RESEARCH WRITING</span><h2>${esc(user.name)}，继续你的写作练习。</h2><p>从练习到论文修改，一步一步把方法用起来。</p><button class="primary" id="startPractice">${user.role==='teacher'?'查看练习记录':'开始30题练习'} →</button></div><div class="hero-mark">Aa</div></div><div class="stats"><div class="stat"><span>课程单元</span><strong>8<small> / 640道练习题</small></strong></div><div class="stat"><span>已完成练习</span><strong>${s.rounds}<small>轮</small></strong><small>整轮完成才记录</small></div><div class="stat"><span>课程作业</span><strong>${assignments.length}<small>项</small></strong><small>按要求上传，逐轮修改</small></div></div><div class="section-title"><h3>课程路径</h3><button class="text-btn" id="allCourse">查看课件 →</button></div><div class="grid">${chapters.map(c=>`<article class="card"><span class="unit">UNIT ${String(c.id).padStart(2,'0')}</span><h3>${esc(c.title)}</h3><p>${esc(c.objective)}</p></article>`).join('')}</div>`,bind(){$('#startPractice').onclick=()=>show('practice');$('#allCourse').onclick=()=>show('course')}};
};
views.grades=async()=>{
 const [d,p,assignments]=await Promise.all([api('/practice/session'),api('/progress'),api('/assignments')]);const s=d.summary;
 return {html:heading('练习记录与作业成绩','练习用于改进；论文成绩以教师发布为准。')+`<div class="stats"><div class="stat"><span>已完成练习</span><strong>${s.rounds}<small>轮</small></strong></div><div class="stat"><span>最近一轮正确</span><strong>${s.latest?s.latest.correct:'—'}<small> / 30</small></strong></div><div class="stat"><span>已发布作业成绩</span><strong>${assignments.filter(a=>a.submission?.published).length}<small>项</small></strong></div></div><div class="card"><h3>练习记录</h3><p class="muted">每轮题目会调整，正确率用于反馈，不用于学生排名。</p>${d.records.map(r=>`<button class="text-btn" data-grade-practice="${r.id}">${esc(practiceDate(r.completed))} · ${r.correct}/30 · 查看反馈 →</button><br>`).join('')||'<p>完成全部30题后会显示在这里。</p>'}</div>${p.done?`<details class="card"><summary>保留的旧版24题成绩</summary><p>已完成${p.done}/${p.total}题 · 原成绩${p.score}/100</p></details>`:''}<div class="section-title"><h3>作业成绩</h3></div><div class="stack">${assignments.map(a=>`<article class="card"><h3>${esc(a.title)}</h3>${a.submission?.published?`<b>${a.submission.score} / 100</b><p class="prewrap">${esc(a.submission.feedback)}</p>`:`<p>${a.submission?'待教师发布':'尚未提交'}</p>`}</article>`).join('')}</div>`,bind(){document.querySelectorAll('[data-grade-practice]').forEach(b=>b.onclick=busy(async()=>modal('练习反馈',practiceReviewHtml(await api('/practice/records/'+b.dataset.gradePractice)))))} };
};
const practiceProfileBase=profileHTML;
profileHTML=function(p,privateView=false){
 if(!p.timed_practice)return practiceProfileBase(p,privateView);
 const s=p.timed_practice,units=p.timed_practice_units||[];
 return `<div class="stats"><div class="stat"><span>已完成练习</span><strong>${s.rounds}<small>轮</small></strong></div><div class="stat"><span>累计正确率</span><strong>${s.accuracy??'—'}<small>${s.accuracy===null?'':'%'}</small></strong></div><div class="stat"><span>已记录题数</span><strong>${s.answered}<small>题</small></strong></div></div><article class="card"><h3>近期练习表现</h3><p class="small muted">按最近8轮更新。小样本仅供选择后续练习；超时单独显示，不直接视为不理解，也不形成能力标签。</p><div class="table-wrap"><table><thead><tr><th>单元</th><th>正确 / 题数</th><th>超时未答</th></tr></thead><tbody>${units.map(u=>`<tr><td>${esc(u.title)}</td><td>${u.questions?u.correct+' / '+u.questions:'尚无记录'}</td><td>${u.timeouts}</td></tr>`).join('')}</tbody></table></div></article><article class="card" style="margin-top:18px"><h3>论文写作反馈</h3>${p.writing_reviews?.length?p.writing_reviews.map(w=>`<div class="review-issue"><b>${esc(w.title)}</b><small class="muted"> · ${esc(w.source)}</small>${w.formal_check?formalBlock(w.formal_check):''}${(w.dimensions||[]).map(d=>`<p>${esc(d.name)}：${d.score}/${d.max}<br>${esc(d.comment)}</p>`).join('')}</div>`).join(''):'<p class="muted">教师发布作业反馈后，相关建议会补充到这里。</p>'}</article>${p.assessment?.done?`<details class="card" style="margin-top:18px"><summary>保留的旧版练习成绩</summary><p>${p.assessment.done}/${p.assessment.total}题 · ${p.assessment.score}/100</p></details>`:''}`;
};
