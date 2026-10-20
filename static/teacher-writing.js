'use strict';
views.access=async()=>{
 const d=await api('/teacher/access'),p=d.policy;
 return {html:heading('注册与额度','学生凭邀请码注册；已有账号继续使用。每日额度按北京时间重置。')+`<div class="card"><h3>模型请求额度</h3><p>今日已发起 ${d.calls} 次请求。缓存复用不计，失败尝试计入，防止反复重试。</p><form id="access-policy"><label>允许邀请码注册<select name="registration_open"><option value="true" ${p.registration_open?'selected':''}>开放</option><option value="false" ${!p.registration_open?'selected':''}>暂停注册</option></select></label><label>每名学生每日上限<input name="student_daily_limit" type="number" min="0" max="100" required value="${p.student_daily_limit}"></label><label>教师账号每日上限<input name="teacher_daily_limit" type="number" min="0" max="1000" required value="${p.teacher_daily_limit}"></label><label>全站每日上限<input name="site_daily_limit" type="number" min="0" max="5000" required value="${p.site_daily_limit}"></label><p class="small muted">0代表暂停新的外部请求，缓存仍可读取。论文批改计入稿件所属学生，即使由教师发起也不能绕过额度。覆盖共享文本/图文API，实时语音仍使用英语模块自身限制。请求次数不等于金额预算，实际费用以服务商账单为准。</p><button class="primary">保存额度</button></form></div><section class="card" style="margin-top:20px"><h3>生成课程邀请码</h3><form id="invite-form"><label>用途 / 班级<input name="label" required maxlength="80" value="论文写作课程"></label><label>可注册人数<input name="max_uses" type="number" min="1" max="1000" value="30" required></label><label>有效天数<input name="valid_days" type="number" min="1" max="365" value="30" required></label><button>生成邀请码</button></form><div id="new-invite" hidden><label>请复制并发给学生（仅本次显示）<input id="invite-code" readonly></label><p>刷新后无法再次查看原码；遗失时可停用旧码并重新生成。</p></div><div class="table-wrap"><table><thead><tr><th>用途</th><th>已用 / 名额</th><th>到期时间</th><th>操作</th></tr></thead><tbody>${d.invites.map(i=>`<tr><td>${esc(i.label)}</td><td>${i.uses} / ${i.max_uses}</td><td>${esc(new Date(i.expires*1000).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'}))}</td><td>${i.revoked?'已停用':`<button data-revoke-invite="${i.id}">停用</button>`}</td></tr>`).join('')}</tbody></table></div></section>`,bind(){
  $('#access-policy').onsubmit=busy(async e=>{const f=new FormData(e.target);await api('/teacher/access','POST',{registration_open:f.get('registration_open')==='true',student_daily_limit:Number(f.get('student_daily_limit')),teacher_daily_limit:Number(f.get('teacher_daily_limit')),site_daily_limit:Number(f.get('site_daily_limit'))});toast('额度已保存');await show('access')});
  $('#invite-form').onsubmit=busy(async e=>{const f=new FormData(e.target);const r=await api('/teacher/invites','POST',{label:f.get('label'),max_uses:Number(f.get('max_uses')),valid_days:Number(f.get('valid_days'))});$('#new-invite').hidden=false;$('#invite-code').value=r.code;toast('邀请码已生成，请复制后再离开此页')});
  document.querySelectorAll('[data-revoke-invite]').forEach(b=>b.onclick=busy(async()=>{await api('/teacher/invites/'+b.dataset.revokeInvite,'DELETE');toast('邀请码已停用，已有账号不受影响');await show('access')}));
 }};
};
function openAssignmentEditor(a=null){
 const rubric=a?.rubric||[{name:'研究问题与论证',max:30},{name:'结构与表达',max:20},{name:'图表引文与规范',max:20},{name:'修改质量与反馈回应',max:30}];
 modal(a?'编辑作业与评分要求':'发布作业',`<form id="assignmentEditor"><label style="display:flex;gap:10px;align-items:center"><input style="width:auto" type="checkbox" name="workflow" ${a&&!a.workflow?'':'checked'}>四轮递进写作（前三轮意见，第四轮评分）</label><label>作业名称<input name="title" required maxlength="150" value="${esc(a?.title||'')}"></label><label>给学生的作业要求（四轮任务可留空，系统按大题目生成）<textarea name="instructions" maxlength="10000" rows="6">${esc(a?.instructions||'')}</textarea></label><label>截止时间（北京时间，可不填）<input type="datetime-local" name="deadline" value="${esc(a?.deadline||'')}"></label><label>评分维度与满分（每行：名称 | 分值，总计100分）<textarea name="rubric_lines" required rows="6">${esc(rubric.map(r=>r.name+' | '+r.max).join('\n'))}</textarea></label><label>给 AI 的评分说明（学生也能看到）<textarea name="grading_instructions" maxlength="8000" rows="5" placeholder="例如：本次仅评价引言，不要求实验结果；重点看研究空白、文献比较和问题明确性。">${esc(a?.grading_instructions||'')}</textarea></label><p class="note">AI按本次要求和评分维度给出建议分，最终分数由教师复核发布。修改不自动覆盖已有提交、AI结果或教师评分；旧结果会保留评分依据。正在批改时暂不能编辑。</p><button class="primary">${a?'保存修改':'发布作业'}</button></form>`);
 $('#assignmentEditor').onsubmit=busy(async e=>{
  const f=new FormData(e.target),rubric=String(f.get('rubric_lines')).split('\n').filter(x=>x.trim()).map(line=>{const split=line.lastIndexOf('|');if(split<1)throw Error('评分维度请按“名称 | 分值”每行填写');return {name:line.slice(0,split).trim(),max:Number(line.slice(split+1).trim())}});
  if(!rubric.length||rubric.length>10||rubric.some(r=>!r.name||!Number.isFinite(r.max)||r.max<=0)||Math.abs(rubric.reduce((n,r)=>n+r.max,0)-100)>.001)throw Error('请填写1–10个评分维度，分值为正且合计100分');
  const data={title:f.get('title'),instructions:f.get('instructions'),deadline:f.get('deadline'),grading_instructions:f.get('grading_instructions'),rubric,workflow:f.get('workflow')==='on'};
  if(a)data.expected_revision=a.revision;
  await api(a?'/assignments/'+a.id:'/assignments',a?'PUT':'POST',data);$('#modal').close();toast(a?'作业要求已更新，已有评分保留':'作业已发布');await show('assignments');
 });
}

const writingDate=stamp=>new Date(stamp*1000).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false});
views.review=async()=>{
 const [ss,jobs,assignments]=await Promise.all([api('/teacher/submissions'),api('/teacher/review-jobs'),api('/assignments')]);
 const state={pending:'等待执行',running:'批改中',completed:'已完成',failed:'未完成',cancelled:'已取消'};
 return {html:heading('作业批改','AI按作业要求与量表给建议分，教师复核后发布。评分引擎：'+(jobs.review_version||'旧版，请升级服务'),'<button id="refreshReview">刷新状态</button>')+
 `<section class="card" style="margin-bottom:20px"><h3>批量与定时批改</h3><form id="batchReviewForm"><label>批改范围<select id="batchAssignment"><option value="">全部作业</option>${assignments.map(a=>`<option value="${a.id}">${esc(a.title)}</option>`).join('')}</select></label><div class="actions"><button type="button" class="primary" id="batchReviewNow">一键批改未评作业</button><button type="button" id="openReviewSettings">自动批改设置</button></div><label>指定开始时间（北京时间）<input id="batchReviewTime" type="datetime-local"></label><button>安排定时批改</button><p class="small muted">仅加入尚无AI结果、未退回、未发布且没有教师评分草稿的提交；跳过已有结果及重复任务。任务在服务器保存，逐份批改，刷新或关闭网页不影响。取消排队请见下方任务列表。</p></form><p class="note">DeepSeek价格核对于2026-10-19：工作日09:00–12:00、14:00–18:00高峰，其余时段、周末和法定节假日空闲，空闲价为高峰的一半。可在设置中勾选避开普通工作日高峰；价格以服务商实时规则和账单为准。</p></section>`+
 `<div class="card table-wrap">${ss.length?`<table><thead><tr><th>学生</th><th>作业</th><th>状态</th><th>AI建议分</th><th>教师分数</th><th>操作</th></tr></thead><tbody>${ss.map(s=>`<tr><td>${esc(s.name)}<small>${esc(s.student_no)}</small></td><td>${esc(s.title)}<small>${esc(s.created)}</small></td><td><span class="badge ${s.published?'':'warn'}">${esc(s.status)}</span>${s.ai?.scoring_basis&&s.ai.scoring_basis.revision!==s.assignment_revision?'<small class="warning">要求已更新，AI结果采用旧版标准</small>':''}</td><td>${s.workflow&&(s.ai?.round_no||1)<4?'本轮仅提意见':s.ai?.score??(s.ai?'未生成分数':'尚未批改')}</td><td>${s.score??'—'}</td><td><button class="text-btn" data-review="${s.id}">打开批改 →</button></td></tr>`).join('')}</tbody></table>`:'<div class="empty">还没有学生提交作业。</div>'}</div>`+
 `<section class="card table-wrap" style="margin-top:20px"><h3>服务器批改队列</h3><p class="small muted">等待 ${jobs.counts.pending||0} · 执行中 ${jobs.counts.running||0} · 完成 ${jobs.counts.completed||0} · 未完成 ${jobs.counts.failed||0}。最多展示最近100项；失败不自动重试扣费，检查原因后手动重新批改。</p><table><thead><tr><th>学生 / 作业</th><th>最早开始时间（北京时间）</th><th>状态</th><th>操作</th></tr></thead><tbody>${jobs.jobs.map(j=>`<tr><td>${esc(j.name||'提交已移除')}<br><small>${esc(j.title)}</small></td><td>${esc(writingDate(j.run_at))}</td><td>${state[j.state]||esc(j.state)}${j.error?`<small>${esc(j.error)}</small>`:''}</td><td>${j.state==='pending'?`<button class="text-btn danger" data-cancel-review="${j.id}">取消排队</button>`:''}</td></tr>`).join('')}</tbody></table></section>`,bind(){
  $('#refreshReview').onclick=()=>show('review');$('#openReviewSettings').onclick=()=>show('settings');
  document.querySelectorAll('[data-review]').forEach(b=>b.onclick=()=>openReview(ss.find(s=>s.id===Number(b.dataset.review))));
  async function batch(run_at=''){
   if(!confirm(run_at?'将符合条件的作业安排在指定时间后逐份批改，会消耗API额度，继续吗？':'将符合条件的所有未评作业加入AI队列，会消耗API额度，继续吗？'))return;
   const assignment_id=$('#batchAssignment').value;const r=await api('/teacher/reviews/batch','POST',{assignment_id:assignment_id?Number(assignment_id):null,run_at});
   toast(`已加入 ${r.queued} 份，跳过 ${r.skipped} 份${r.off_peak_only?'；已启用避开高峰':''}`);await show('review');
  }
  $('#batchReviewNow').onclick=busy(async()=>{const b=$('#batchReviewNow');b.disabled=true;try{await batch()}finally{b.disabled=false}});
  $('#batchReviewForm').onsubmit=busy(async()=>{const time=$('#batchReviewTime').value;if(!time)throw Error('请先选择未来的北京时间');await batch(time)});
  document.querySelectorAll('[data-cancel-review]').forEach(b=>b.onclick=busy(async()=>{await api('/teacher/review-jobs/'+b.dataset.cancelReview,'DELETE');toast('已取消尚未开始的任务');await show('review')}));
 }};
};

// Delegated controls work in both the legacy and four-round assignment lists.
document.addEventListener('click',e=>{
 if(user?.role!=='teacher'||!e.target.closest('[data-delete-assignment],[data-deleted-assignments],[data-restore-assignment]'))return;
 return busy(async e=>{
 if(user?.role!=='teacher')return;
 const remove=e.target.closest('[data-delete-assignment]');
 if(remove){
  if(!confirm('删除这项作业？学生将无法继续提交，排队的AI任务会取消。历史稿件和成绩保留，可在“已删除作业”中恢复。'))return;
  remove.disabled=true;
  try{await api('/assignments/'+remove.dataset.deleteAssignment,'DELETE');toast('作业已删除，历史记录保留，可恢复');await show('assignments')}finally{remove.disabled=false}
  return;
 }
 const deleted=e.target.closest('[data-deleted-assignments]');
 if(deleted){
  const rows=await api('/teacher/assignments/deleted');
  modal('已删除作业',rows.length?'<p class="small muted">删除后从作业和成绩统计中移除；恢复后原稿件、成绩和四轮进度重新可见，取消的AI排队任务不会自动恢复。</p>'+rows.map(a=>`<article class="card" style="margin-bottom:12px"><h3>${esc(a.title)}</h3><p>删除时间：${esc(a.deleted_at)} · ${a.submissions}份学生提交</p><button data-restore-assignment="${a.id}">恢复作业</button></article>`).join(''):'<div class="empty">没有已删除的作业。</div>');
  return;
 }
 const restore=e.target.closest('[data-restore-assignment]');
 if(restore){restore.disabled=true;try{await api('/teacher/assignments/'+restore.dataset.restoreAssignment+'/restore','POST');$('#modal').close();toast('作业已恢复');await show('assignments')}finally{restore.disabled=false}}
})(e);
});

const reviewBeforeIssueQueue=views.review;
views.review=async()=>{
 const base=await reviewBeforeIssueQueue(),pending=await api('/teacher/writing/issues'),issues=pending.issues||[];
 return {html:heading('需要核验的意见',`待处理 ${issues.length} 条。确认或驳回会保留教师理由，不改写原始AI结果或已发布成绩。`)+`<section class="card" style="margin-bottom:20px">${issues.length?issues.map(x=>`<details class="writing-more"><summary>${esc(x.name)} · 第${x.round_no}轮 · ${esc(x.issue.problem)}</summary><p>${esc(x.title)} · ${esc(x.student_no)}</p><a href="/api/writing/rounds/${x.round_id}/file">查看本轮原稿</a><blockquote>${esc(x.issue.quote||'未提供原文')}</blockquote><p>AI建议：${esc(x.issue.suggestion)}</p><p>量规：${esc(x.issue.criterion||'未关联')}</p><button data-issue-review="${x.round_id}" data-issue-id="${esc(x.issue.id)}" data-decision="confirmed">确认有效</button><button data-issue-review="${x.round_id}" data-issue-id="${esc(x.issue.id)}" data-decision="dismissed">驳回意见</button></details>`).join(''):'<p class="muted">当前没有需要核验的意见。</p>'}${pending.rounds_scanned===pending.scan_limit?'<p class="note">当前扫描最近500次检查；更早记录可在对应学生稿件中核查。</p>':''}</section>`+base.html,bind(){
  base.bind?.();
  bindIssueReviewControls();
 }};
};

function bindIssueReviewControls(){
document.querySelectorAll('[data-issue-review]').forEach(b=>b.onclick=()=>{modal(b.dataset.decision==='confirmed'?'确认意见有效':'驳回AI意见',`<form id="issue-decision"><label>核验依据与理由<textarea name="reason" required minlength="5" maxlength="2000" placeholder="说明你核对了什么，为什么确认或驳回"></textarea></label><p class="small muted">原始AI意见保留，学生会看到教师处置。修改核验结果后，本轮讲评需重新确认。</p><button class="primary">保存处置</button></form>`);$('#issue-decision').onsubmit=busy(async e=>{await api('/teacher/writing/rounds/'+b.dataset.issueReview+'/issue-review','POST',{issue_id:b.dataset.issueId,decision:b.dataset.decision,reason:new FormData(e.target).get('reason')});$('#modal').close();toast('核验处置已保存');await show('review')})});
}
