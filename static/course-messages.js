'use strict';
let messageCourse=null,messageCursor=0,messageDialogVersion=0;
function messageCard(m,reply=false,thread=false){return `<article class="card course-message"><div class="card-top"><b>${esc(m.author)}${m.teacher?' · 教师':''}</b><small>${esc(m.created)}</small></div><p class="prewrap">${esc(m.body)}</p><div class="actions">${reply||thread?'':`<button class="text-btn" data-message-open="${m.id}">查看 / 回复（${m.replies}）</button>`}${m.can_delete?`<button class="text-btn danger" data-message-delete="${m.id}">删除${reply?'回复':'留言'}</button>`:''}</div></article>`}
function messageForm(parent=null){return `<form id="course-message-form"><label>${parent?'回复留言':'我要留言'}<textarea name="body" required maxlength="2000" rows="4" placeholder="写下课程问题、学习建议或需要的帮助"></textarea></label><p class="small muted">本课程师生可见。请勿填写电话、密码或其他个人敏感信息。</p><button class="primary">${parent?'发布回复':'发布留言'}</button></form>`}
function bindMessageActions(root,cid,parent=null){
 const actor=user,stillHere=()=>user===actor&&activeCourse===cid&&page==='messages';
 root.querySelectorAll('[data-message-open]').forEach(b=>b.onclick=busy(()=>openMessage(cid,Number(b.dataset.messageOpen))));
 root.querySelectorAll('[data-message-delete]').forEach(b=>b.onclick=busy(async()=>{
  if(!confirm(parent&&Number(b.dataset.messageDelete)!==parent?'确定删除这条回复？':'确定删除这条留言？其回复也将从留言板移除。'))return;
  b.disabled=true;try{await api(`/courses/${cid}/messages/${b.dataset.messageDelete}`,'DELETE');if(stillHere()){toast('已删除');if(parent&&Number(b.dataset.messageDelete)!==parent)await openMessage(cid,parent);else{$('#modal').close();await show('messages')}}}finally{b.disabled=false}
 }));
 const form=root.querySelector('#course-message-form');if(form)form.onsubmit=busy(async e=>{
  const body=new FormData(e.target).get('body').trim();if(!body)throw Error('请输入留言内容');
  await api(`/courses/${cid}/messages`,'POST',{body,parent_id:parent});
  if(stillHere()){toast(parent?'回复已发布':'留言已发布');if(parent)await openMessage(cid,parent);else{messageCursor=0;await show('messages')}}
 });
}
views.messages=async()=>{
 const cid=activeCourse;if(!cid)return {html:heading('学生留言','请先选择课程。')};
 if(messageCourse!==cid){messageCourse=cid;messageCursor=0}
 const data=await api(`/courses/${cid}/messages?before=${messageCursor}`);
 return {html:heading('学生留言',`${COURSES.find(c=>c.id===cid)?.title||''} · 本课程师生共同交流。`,'<button id="messages-refresh">刷新留言</button>')+`<section class="card">${messageForm()}</section><div class="stack" style="margin-top:20px">${data.items.map(m=>messageCard(m)).join('')||'<section class="card empty">还没有留言，欢迎提出你的课程问题。</section>'}</div><div class="actions"><button id="messages-first" ${messageCursor?'':'disabled'}>最新留言</button><button id="messages-next" ${data.next?'':'disabled'}>更早留言</button></div>`,bind(){
  bindMessageActions($('#content'),cid);
  $('#messages-refresh').onclick=()=>show('messages');
  $('#messages-first').onclick=()=>{messageCursor=0;show('messages')};
  $('#messages-next').onclick=()=>{messageCursor=data.next||0;show('messages')};
 }};
};
async function openMessage(cid,id,before=0){
 const actor=user,version=++messageDialogVersion;
 modal('留言与回复','<p>正在加载…</p>');
 const dialogVersion=typeof studioModalVersion==='number'?studioModalVersion:null;
 const d=await api(`/courses/${cid}/messages?parent_id=${id}&before=${before}`);
 if(user!==actor||activeCourse!==cid||page!=='messages'||version!==messageDialogVersion||(dialogVersion!==null&&studioModalVersion!==dialogVersion)||!$('#modal').open)return;
 modal('留言与回复',messageCard(d.parent,false,true)+`<h3>回复（由新到旧）</h3><div class="stack">${d.items.map(m=>messageCard(m,true)).join('')||'<p>暂时没有回复。</p>'}</div><div class="actions"><button id="reply-first" ${before?'':'disabled'}>最新回复</button><button id="reply-next" ${d.next?'':'disabled'}>更早回复</button></div>`+messageForm(id));
 bindMessageActions($('#modalBody'),cid,id);
 $('#reply-first').onclick=busy(()=>openMessage(cid,id));$('#reply-next').onclick=busy(()=>openMessage(cid,id,d.next));
}
