'use strict';
$('#forgotPassword').onclick=()=>openPasswordRecovery();
function openPasswordRecovery(identity={}){
 modal('学生找回密码',`<p>填写注册时的学号和电话，联系教师核实身份并领取一次性重置码，再设置新密码。无需重新注册。</p><form id="recovery-request-form"><label>学号<input name="student_no" required maxlength="30" autocomplete="username" value="${esc(identity.student_no||'')}"></label><label>登记电话号码<input name="phone" required type="tel" minlength="7" maxlength="30" autocomplete="tel" value="${esc(identity.phone||'')}"></label><button class="primary">提交找回申请</button><button type="button" id="recovery-have-code">已有重置码</button><p id="recovery-request-status" role="status"></p></form><p class="small muted">教师账号请联系服务器管理员。电话未登记或已更换，请联系教师核对。</p>`);
 const values=()=>Object.fromEntries(new FormData($('#recovery-request-form')));
 $('#recovery-request-form').onsubmit=busy(async()=>{const r=await api('/password-recovery/request','POST',values());$('#recovery-request-status').textContent=r.message});
 $('#recovery-have-code').onclick=()=>openRecoveryReset(values());
}
function openRecoveryReset(identity){
 modal('设置新密码',`<form id="recovery-reset-form"><label>学号<input name="student_no" required maxlength="30" autocomplete="username" value="${esc(identity.student_no||'')}"></label><label>登记电话号码<input name="phone" type="tel" required minlength="7" maxlength="30" value="${esc(identity.phone||'')}"></label><label>教师提供的重置码<input name="code" required maxlength="64" autocomplete="one-time-code" placeholder="30分钟内有效，仅可使用一次"></label><label>新密码（至少10位）<input name="password" type="password" required minlength="10" maxlength="128" autocomplete="new-password"></label><label>再次输入新密码<input name="confirm" type="password" required minlength="10" maxlength="128" autocomplete="new-password"></label><button class="primary">修改密码并返回登录</button><button id="recovery-back" type="button">返回申请</button></form>`);
 $('#recovery-back').onclick=()=>openPasswordRecovery(identity);
 $('#recovery-reset-form').onsubmit=busy(async e=>{const x=Object.fromEntries(new FormData(e.target));if(x.password!==x.confirm)throw Error('两次输入的密码不一致');delete x.confirm;await api('/password-recovery/reset','POST',x);$('#modal').close();loginRole='student';reg=false;renderAuth();$('#loginForm').reset();toast('密码已重置，请使用新密码登录')});
}
const recoveryStudentsBase=views.students;
views.students=async()=>{
 const v=await recoveryStudentsBase();v.html=`<div class="actions"><button id="student-recovery-requests">处理找回密码申请</button></div>`+v.html;
 const bind=v.bind;v.bind=()=>{bind?.();$('#student-recovery-requests').onclick=busy(openRecoveryRequests)};return v;
};
async function openRecoveryRequests(){
 const actor=user,rows=await api('/teacher/password-recovery');if(user!==actor||user?.role!=='teacher')return;
 modal('找回密码申请',`<p>以下为全平台学生申请。请通过登记电话或当面核实本人身份，再生成重置码并单独告知该学生。</p><div class="table-wrap"><table><thead><tr><th>序号</th><th>学生 / 学号</th><th>登记电话</th><th>申请时间</th><th>操作</th></tr></thead><tbody>${rows.map((s,i)=>`<tr><td>${i+1}</td><td>${esc(s.name)}<small>${esc(s.student_no)}</small></td><td>${esc(s.phone)}</td><td>${esc(new Date(s.requested*1000).toLocaleString('zh-CN'))}</td><td><button data-recovery-approve="${s.id}">${s.issued?'重新生成重置码':'核实并生成重置码'}</button><button class="text-btn" data-recovery-dismiss="${s.id}">关闭申请</button></td></tr>`).join('')||'<tr><td colspan="5">暂无待处理申请</td></tr>'}</tbody></table></div>`);
 document.querySelectorAll('[data-recovery-approve]').forEach(b=>b.onclick=busy(async()=>{
  const s=rows.find(x=>x.id===Number(b.dataset.recoveryApprove));
  if(!confirm(`已通过登记电话 ${s.phone} 或当面核实 ${s.name}（${s.student_no}）的身份？生成新码会使原码失效。`))return;
  const r=await api('/teacher/password-recovery/'+s.id+'/approve','POST',{verified:true});
  modal('一次性重置码',`<p>${esc(s.name)} · ${esc(s.student_no)}</p><label>复制后单独告知已核实的学生<input readonly value="${esc(r.code)}" aria-label="一次性重置码"></label><p>30分钟内有效，仅可使用一次；关闭后无法再次查看，可重新生成。请学生在登录页点击“忘记密码”→“已有重置码”，自行设置新密码。</p>`);
 }));
 document.querySelectorAll('[data-recovery-dismiss]').forEach(b=>b.onclick=busy(async()=>{if(!confirm('关闭此申请？已发出的重置码也将失效。'))return;await api('/teacher/password-recovery/'+b.dataset.recoveryDismiss,'DELETE');await openRecoveryRequests()}));
}
