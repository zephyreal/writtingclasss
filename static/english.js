 'use strict';
// Shared platform login; API credentials never enter this file or browser storage.
let englishSession=null,englishData=null,englishCall=null,englishEpoch=0,englishMicDevice='';
const englishDate=x=>x?new Date(typeof x==='number'?x*1000:x).toLocaleString():'尚未同步';
function englishStatus(text){const el=$('#englishLiveStatus');if(el)el.textContent=text}
function englishCleanup(){
 englishEpoch++;
 const call=englishCall;englishCall=null;
 if(!call)return;
 call.closed=true;clearInterval(call.timer);clearTimeout(call.timeout);call.abort?.abort();
 call.stream?.getTracks().forEach(t=>t.stop());
 call.pc?.close();call.audio?.pause();if(call.audio)call.audio.srcObject=null;
 // Close even during SDP exchange; backend rejects a connection that was cancelled.
 fetch('/api/english/realtime/'+call.sid+'/close',{method:'POST',credentials:'same-origin',keepalive:true,headers:{'X-App-Request':'1'}}).catch(()=>{});
}
if(typeof window!=='undefined'){
 window.addEventListener?.('pagehide',englishCleanup);
 window.addEventListener?.('pageshow',()=>{if(englishCall&&Date.now()>englishCall.expires)englishStopCall('本次练习时间已到')});
}
async function englishStopCall(message='本次练习已结束'){
 const call=englishCall;
 englishCleanup();englishStatus(message);
 const start=$('#englishStartCall');if(start){start.disabled=true;start.textContent='通话已结束'}
 const end=$('#englishStopCall');if(end)end.disabled=true;
 const mute=$('#englishMute');if(mute)mute.disabled=true;
 if(call){try{await call.queue;await api('/english/realtime/'+call.sid+'/close','POST')}catch{toast('对话记录未完全保存，请稍后查看对话记录')}}
}
async function englishMicrophones(){
 if(!navigator.mediaDevices?.enumerateDevices)return;
 try{const rows=await navigator.mediaDevices.enumerateDevices();const select=$('#englishMicrophone');if(!select)return;
 select.innerHTML='<option value="">系统默认麦克风</option>'+rows.filter(d=>d.kind==='audioinput'&&d.deviceId).map((d,i)=>`<option value="${esc(d.deviceId)}">${esc(d.label||'麦克风 '+(i+1))}</option>`).join('');select.value=englishMicDevice;
 }catch{}
}
function englishCaption(call,role,id,text,done=false){
 if(!text)return;
 const key=role+':'+id;let item=call.captions.get(key);
 if(!item){item={role,text:''};call.captions.set(key,item)}
 item.text=done?text:item.text+text;
 const transcript=$('#englishCaptions');if(transcript){transcript.innerHTML=Array.from(call.captions.values()).slice(-40).map(t=>`<p><b>${t.role==='student'?'我':'AI'}</b> ${esc(t.text)}</p>`).join('');transcript.scrollTop=transcript.scrollHeight}
 if(done&&!call.saved.has(key)){
  call.saved.add(key);
  call.queue=call.queue.then(()=>api('/english/realtime/'+call.sid+'/transcript','POST',{item_id:String(id).slice(0,150),role,text:text.slice(0,4000)})).catch(()=>{const note=$('#englishSaveNote');if(note)note.textContent='部分对话文字未保存；语音通话仍可继续。'});
 }
}
function englishSafeDiagnostic(value){
 return String(value??'').slice(0,4000)
  .replace(/\bsk-[A-Za-z0-9._-]+/gi,'[密钥已隐藏]')
  .replace(/\bBearer\s+[^\s,;]+/gi,'Bearer [已隐藏]')
  .replace(/((?:api[_ -]?key|authorization|access[_ -]?token|secret|password)["']?\s*[:=]\s*)["']?[^,\s"}]+/gi,'$1[已隐藏]')
  .replace(/https?:\/\/[^\s]+/gi,'[地址已隐藏]').slice(0,700);
}
function englishSend(call,event){
 if(call.channel?.readyState!=='open')return;
 const id='event_'+Date.now().toString(36)+'_'+Math.random().toString(36).slice(2,10);
 call.phase=event.type;
 if(event.type==='response.cancel')call.cancelEvent=id;
 call.channel.send(JSON.stringify({event_id:id,...event}));
}
function englishLiveFailure(call,error={},stage){
 if(englishCall!==call||call.closed)return;
 const code=englishSafeDiagnostic(error.code||error.type||'unknown_error');
 const message=englishSafeDiagnostic(error.message||'千问未提供详细错误说明');
 const param=englishSafeDiagnostic(error.param||'');
 // A VAD/cancel race is recoverable. A generic invalid_request_error alone is NOT.
 const noActive=/no active response|no response.*(?:cancel|progress)|response.*(?:already.*(?:cancel|complete)|not.*(?:active|progress))/i.test(String(error.message||''));
 const cancelCode=/^(?:response_cancel_not_active|no_active_response|response_cancel_not_in_progress)$/i.test(String(error.code||''));
 if(call.cancelEvent&&(noActive||cancelCode)){call.cancelEvent=null;call.responding=false;englishStatus('正在听你说…');return}
 // Some deployments require a real user turn even for an explicit opening task.
 // Keep the live microphone open; never retry paid generations in a loop.
 const emptyOpening=/cannot create response without input, history, or instructions/i.test(String(error.message||''));
 if(call.ready&&call.openingPending&&emptyOpening){
  call.openingPending=false;call.responding=false;
  englishStatus('已连接，请先说一句 Hello 开始对话');
  return;
 }
 const details=['阶段：'+(stage||call.phase||'建立会话'),'错误码：'+code,param?'参数：'+param:'','说明：'+message].filter(Boolean).join('\n');
 const box=$('#englishDiagnostic');
 if(box&&user?.role==='teacher'){box.hidden=false;box.textContent=details}
 englishStopCall('通话未完成（'+code+'）'+(user?.role==='teacher'?'，请查看下方错误详情':'，请联系教师'));
}

function englishEvent(call,event,channel){
 if(englishCall!==call||call.closed)return;
 let data;try{data=JSON.parse(event.data)}catch{return}
 if(data.type==='session.created'){
  if(call.configured)return;call.configured=true;call.channel=channel;
  const configure=()=>englishSend(call,{type:'session.update',session:call.config});
  if(channel.readyState==='open')configure();else channel.addEventListener('open',configure,{once:true});
 }else if(data.type==='session.updated'&&!call.ready){
  call.ready=true;clearTimeout(call.timeout);
  call.sender.replaceTrack(call.track).then(()=>{if(englishCall===call&&!call.closed){call.track.enabled=true;englishStatus('已连接，AI 先开口');call.openingPending=true;englishSend(call,{type:'response.create',response:{instructions:'Begin this English practice now. Greet the student briefly and ask ONE simple opening question about the topic in the session context. Say only the greeting and question; do not describe these instructions.'}})}}).catch(()=>englishStopCall('麦克风连接失败，请重新开始'));
  $('#englishStopCall').disabled=false;$('#englishMute').disabled=false;
 }else if(data.type==='input_audio_buffer.speech_started'){
  englishStatus('正在听你说…');
  if(call.responding){call.responding=false;englishSend(call,{type:'response.cancel'})}
 }else if(data.type==='input_audio_buffer.speech_stopped')englishStatus('正在回应…');
 else if(data.type==='response.created'){call.openingPending=false;call.responding=true;englishStatus('AI 正在说，可以直接插话')}
 else if(data.type==='response.done'){
  call.responding=false;
  if(data.response?.status==='failed'){englishLiveFailure(call,data.response.status_details?.error||{code:'response_failed'},'response.done');return}
  englishStatus(data.response?.status==='cancelled'?'正在听你说…':'轮到你了，慢慢说');
 }
 else if(data.type==='conversation.item.input_audio_transcription.completed')englishCaption(call,'student',data.item_id||data.event_id,data.transcript||data.text,true);
 else if(data.type==='response.audio_transcript.delta')englishCaption(call,'assistant',data.item_id||data.response_id,data.delta);
 else if(data.type==='response.audio_transcript.done')englishCaption(call,'assistant',data.item_id||data.response_id,data.transcript||data.text,true);
 else if(data.type==='error')englishLiveFailure(call,data.error||data);
}
async function englishIce(pc,call){
 if(pc.iceGatheringState==='complete')return;
 await new Promise((resolve,reject)=>{
  const done=()=>{clearTimeout(timer);pc.removeEventListener('icegatheringstatechange',changed);call.abort.signal.removeEventListener('abort',cancel)};
  const changed=()=>{if(pc.iceGatheringState==='complete'){done();resolve()}};
  const cancel=()=>{done();reject(Error('通话已取消'))};
  const timer=setTimeout(()=>{done();reject(Error('语音连接准备超时，请检查网络后重试'))},12000);
  pc.addEventListener('icegatheringstatechange',changed);call.abort.signal.addEventListener('abort',cancel,{once:true});changed();
 });
}
async function englishStartCall(){
 if(englishCall)return;
 const epoch=++englishEpoch,sid=englishSession.id;
 const call={sid,closed:false,queue:Promise.resolve(),captions:new Map(),saved:new Set(),abort:new AbortController(),expires:Infinity};englishCall=call;
 const button=$('#englishStartCall');button.disabled=true;englishStatus('正在连接麦克风…');$('#englishStopCall').disabled=false;
 try{
  const stream=await navigator.mediaDevices.getUserMedia({audio:{...(englishMicDevice?{deviceId:{exact:englishMicDevice}}:{}),echoCancellation:true,noiseSuppression:true,autoGainControl:true}});
  if(epoch!==englishEpoch||englishCall!==call){stream.getTracks().forEach(t=>t.stop());return}
  call.stream=stream;call.track=stream.getAudioTracks()[0];call.track.enabled=false;
  englishMicrophones();$('#englishMicrophone').disabled=true;
  const pc=new RTCPeerConnection({iceServers:[]});call.pc=pc;
  pc.addTrack(call.track,stream);call.sender=pc.getSenders().find(s=>s.track?.kind==='audio');await call.sender.replaceTrack(null);
  call.audio=$('#englishRemoteAudio');
  pc.ontrack=e=>{if(englishCall!==call)return;call.audio.srcObject=e.streams[0]||new MediaStream([e.track]);call.audio.play().catch(()=>{$('#englishPlayAudio').hidden=false})};
  const bind=channel=>{channel.onmessage=event=>englishEvent(call,event,channel)};
  bind(pc.createDataChannel('oai-events'));pc.ondatachannel=e=>bind(e.channel);
  pc.onconnectionstatechange=()=>{if(englishCall===call&&['failed','closed','disconnected'].includes(pc.connectionState))englishStopCall('连接已断开，请重新选择话题开始')};
  await pc.setLocalDescription(await pc.createOffer());await englishIce(pc,call);
  if(epoch!==englishEpoch)return;
  englishStatus('正在连接英语伙伴…');
  const response=await fetch('/api/english/realtime/'+sid+'/connect',{method:'POST',credentials:'same-origin',headers:{'X-App-Request':'1','Content-Type':'application/json'},body:JSON.stringify({sdp:pc.localDescription.sdp}),signal:call.abort.signal});
  const result=await response.json();if(!response.ok)throw Error(result.detail||'实时语音连接失败');
  if(epoch!==englishEpoch)return;
  call.config=result.session;call.expires=result.expires*1000;
  call.timer=setInterval(()=>{if(Date.now()>=call.expires){englishStopCall('本次练习时间已到，已保存对话');return}const clock=$('#englishClock');if(clock){const n=Math.max(0,Math.ceil((call.expires-Date.now())/1000));clock.textContent=Math.floor(n/60)+':'+String(n%60).padStart(2,'0')}},1000);
  call.timeout=setTimeout(()=>englishStopCall('语音服务未能就绪，请检查接口配置或网络'),25000);
  const sdp=String(result.sdp).trim().replace(/\r?\n/g,'\r\n')+'\r\n';
  await pc.setRemoteDescription({type:'answer',sdp});
 }catch(e){
  if(epoch!==englishEpoch)return;
  const message=({NotAllowedError:'请在浏览器站点权限中允许麦克风',NotFoundError:'未找到麦克风，请检查连接',OverconstrainedError:'所选麦克风不可用，请选择默认设备'})[e.name]||e.message;
  await englishStopCall(message);toast(message);
 }
}
views.english=async()=>{
 englishCleanup();const [d,p]=await Promise.all([api('/english/topics'),api('/english/profile')]);englishData=d;
 return {html:heading('用英语，聊聊你感兴趣的事','选一个话题，和 AI 连续对话。')+
 `<section class="english-welcome"><div><span class="eyebrow">LET’S TALK</span><h2>今天，你想聊什么？</h2><p>${esc(p.recommendation)}</p></div><button id="englishProfile">我的兴趣</button></section>`+
 (!d.realtime?.configured?`<p class="note">教师配置千问实时语音后即可开始。${user.role==='teacher'?'<button id="englishConfigure">配置语音 API</button>':''}</p>`:'')+
 `<div class="english-filters"><button class="primary" data-english-filter="all">全部</button>${Object.entries(d.categories).map(([id,title])=>`<button data-english-filter="${id}">${esc(title)}</button>`).join('')}${user.role==='teacher'?'<button id="refreshEnglishNews">更新话题</button>':''}</div>`+
 `<div class="course-grid english-topics">${d.topics.map(t=>`<article class="card english-topic" data-english-category="${esc(t.category)}"><span class="small muted">${esc(d.categories[t.category])}${t.kind==='news'?' · 近期话题':''}</span><h3>${esc(t.title)}</h3>${t.kind==='news'?`<a class="small muted" href="${esc(t.url)}" target="_blank" rel="noopener noreferrer">${esc(t.source)} · ${esc(englishDate(t.published))} ↗</a>`:'<p class="small muted">短句交流，AI 先开口</p>'}<button class="primary start-english" data-topic="${esc(t.id)}" ${d.realtime?.configured?'':'disabled'}>进入练习 →</button></article>`).join('')}</div>`+
 `<details class="english-news-note"><summary>话题来源与更新</summary><p class="small muted">最近同步：${esc(englishDate(d.news.updated))}。${esc(d.news.error||'')} 新闻仅提供标题和来源，讨论观点时不代表已核实全文。${d.news.stale?'当前新闻缓存尚未更新，可先练习常用情景。':''}</p></details>`,bind(){
 $('#englishProfile').onclick=()=>show('englishProfile');if($('#englishConfigure'))$('#englishConfigure').onclick=()=>show('englishSettings');
 document.querySelectorAll('[data-english-filter]').forEach(b=>b.onclick=()=>{document.querySelectorAll('[data-english-filter]').forEach(x=>x.classList.toggle('primary',x===b));document.querySelectorAll('[data-english-category]').forEach(x=>x.hidden=b.dataset.englishFilter!=='all'&&x.dataset.englishCategory!==b.dataset.englishFilter)});
 document.querySelectorAll('[data-topic]').forEach(b=>b.onclick=busy(async()=>{b.disabled=true;try{const s=await api('/english/realtime/sessions','POST',{topic_id:b.dataset.topic});if(page!=='english')return;englishSession=s;await show('englishChat')}finally{b.disabled=false}}));
 if($('#refreshEnglishNews'))$('#refreshEnglishNews').onclick=busy(async()=>{await api('/english/news/refresh','POST');await show('english')});
 }};
};
views.englishChat=async()=>{
 englishCleanup();if(!englishSession)return views.englishHistory();
 const s=await api('/english/sessions/'+englishSession.id);englishSession=s;
 const usable=s.transport==='realtime'&&!s.ended&&s.live_state?.state==='new';
 return {html:heading(esc(s.topic.title),'简单说一两句，慢慢来。','<button id="englishBack">← 换个话题</button>')+
 `<section class="card english-call"><div class="english-voice-orb" aria-hidden="true">En</div><h2 id="englishLiveStatus" role="status">${usable?'准备好了，就开始吧':'本次练习记录'}</h2><p class="muted">${usable?'AI 先开口 · 可以随时插话':'选择一个话题，开始新的语音练习'}</p><span id="englishClock" class="english-clock"></span><audio id="englishRemoteAudio" autoplay></audio><button id="englishPlayAudio" hidden>播放 AI 声音</button>`+
 (usable?`<div class="english-call-actions"><button class="primary" id="englishStartCall">开始对话</button><button id="englishMute" disabled>静音</button><button id="englishStopCall" disabled>结束</button><button id="englishHint">给我提示</button></div><p id="englishHintText" class="small" hidden></p><details class="english-device"><summary>麦克风设置</summary><label>录音设备<select id="englishMicrophone"><option value="">系统默认麦克风</option></select></label></details><p id="englishMicNote" class="small warning"></p>`:'<button id="englishNewTopic">选择话题</button>')+
 `<details class="english-transcript"><summary>对话文字</summary><div id="englishCaptions">${s.turns.map(t=>`<p><b>${t.role==='student'?'我':'AI'}</b> ${esc(t.text)}</p>`).join('')}</div></details><p id="englishSaveNote" class="small muted"></p><pre id="englishDiagnostic" class="english-diagnostic" hidden></pre><p class="small muted">语音将发送至阿里云千问处理；本站保存对话文字用于学习记录，不保存录音。请勿在对话中提供个人隐私。</p></section>`,bind(){
 $('#englishBack').onclick=()=>show('english');
 if(!usable){$('#englishNewTopic').onclick=()=>show('english');return}
 const secure=typeof window!=='undefined'&&window.isSecureContext;
 const supported=typeof RTCPeerConnection!=='undefined'&&navigator.mediaDevices?.getUserMedia;
 if(!secure||!supported){$('#englishStartCall').disabled=true;$('#englishMicNote').textContent=!secure?'请通过 HTTPS 打开网站并允许麦克风。':'当前浏览器不支持实时语音，请使用新版 Chrome 或 Edge。'}
 $('#englishStartCall').onclick=busy(englishStartCall);$('#englishStopCall').onclick=busy(()=>englishStopCall());
 $('#englishMute').onclick=()=>{const call=englishCall;if(!call?.track||!call.ready)return;call.track.enabled=!call.track.enabled;$('#englishMute').textContent=call.track.enabled?'静音':'取消静音';englishStatus(call.track.enabled?'正在听你说…':'已静音')};
 $('#englishPlayAudio').onclick=busy(async()=>{await $('#englishRemoteAudio').play();$('#englishPlayAudio').hidden=true});
 $('#englishHint').onclick=busy(async()=>{const r=await api('/english/sessions/'+s.id+'/hint','POST');$('#englishHintText').textContent=r.hint;$('#englishHintText').hidden=false});
 $('#englishMicrophone').onchange=e=>englishMicDevice=e.target.value;englishMicrophones();
 }};
};
views.englishHistory=async()=>{
 englishCleanup();const rows=await api('/english/sessions');
 return {html:heading('我的对话记录','回看练习文字，下一次继续进步。')+`<section class="card table-wrap"><table><thead><tr><th>话题</th><th>时间</th><th>回答轮数</th><th></th></tr></thead><tbody>${rows.map(s=>`<tr><td>${esc(s.topic.title)}</td><td>${esc(englishDate(s.created))}</td><td>${s.turns}</td><td><button data-resume-english="${s.id}">查看 →</button></td></tr>`).join('')}</tbody></table>${!rows.length?'<p class="empty">还没有练习记录，选个话题开始吧。</p>':''}</section>`,bind(){document.querySelectorAll('[data-resume-english]').forEach(b=>b.onclick=busy(async()=>{englishSession={id:Number(b.dataset.resumeEnglish)};await show('englishChat')}))}};
};
views.englishSettings=async()=>{
 englishCleanup();const s=await api('/teacher/english/realtime-settings');
 return {html:heading('英语实时语音 API','千问负责连续语音对话，论文批改接口在原设置中单独管理。')+
 `<section class="card english-api-settings"><span class="badge">${s.configured?'已保存配置':'待配置'}</span><h3>阿里云百炼 · 千问实时语音</h3><form id="englishApiForm"><label>模型<input value="${esc(s.model)}" readonly></label><label>地域<select name="region"><option value="cn-beijing" ${s.region==='cn-beijing'?'selected':''}>华北2（北京）</option><option value="ap-southeast-1" ${s.region==='ap-southeast-1'?'selected':''}>新加坡</option></select></label><label>业务空间 ID（Workspace ID）<input name="workspace_id" required maxlength="80" pattern="[A-Za-z0-9_-]+" value="${esc(s.workspace_id)}" placeholder="填写百炼业务空间 ID"></label><label>API Key<input name="key" type="password" autocomplete="new-password" maxlength="500" placeholder="${s.configured?'已保存，留空保留原密钥':'填写所选地域和业务空间的 API Key'}"></label><label>音色<input name="voice" required value="${esc(s.voice)}" maxlength="100" pattern="[A-Za-z0-9_-]+"></label><label>单次练习上限（分钟）<input name="minutes" type="number" required min="1" max="15" value="${s.minutes}"></label><p class="small muted">API Key 只保存在服务器。学生每天最多尝试连接6次，教师调试最多60次；网页到时或离开时关闭通话。模型费用按实际用量计费，费用上限请同时在百炼控制台管理。</p><button class="primary">保存语音配置</button><button type="button" id="englishTestCall">去试一次对话</button><details><summary>清除密钥</summary><label><input type="checkbox" name="clear_key">保存时清除现有密钥并停用新通话</label></details></form><p class="small muted">业务空间 ID、API Key 和模型权限必须属于所选地域。默认音色 Tina，可填写该模型官方支持的其他音色标识。试聊会产生实际模型费用。</p></section>`,bind(){
 $('#englishApiForm').onsubmit=busy(async e=>{const body=Object.fromEntries(new FormData(e.target));body.minutes=Number(body.minutes);body.clear_key=body.clear_key==='on';await api('/teacher/english/realtime-settings','POST',body);toast('实时语音配置已保存');await show('englishSettings')});
 $('#englishTestCall').onclick=()=>show('english');
 }};
};
function englishProfileHtml(p){
 const rates=p.recent_speech.filter(m=>m.speech_rate_wpm!=null);
 return `<div class="stats"><div class="stat"><span>有效对话样本</span><strong>${p.completed_samples}<small> 次</small></strong></div><div class="stat"><span>回答 / 语音回答</span><strong>${p.practice_turns}<small> / ${p.spoken_turns}</small></strong></div><div class="stat"><span>平均回答词数</span><strong>${p.average_words??'—'}</strong></div></div><div class="card"><h3>下一次怎么练？</h3><p>${esc(p.recommendation)}</p><p class="small muted">${esc(p.measurement_note)}</p><p>近期常练兴趣：${p.inferred_interests.map(x=>esc(p.categories[x])).join('、')||'样本积累中'}</p></div><div class="card table-wrap" style="margin-top:20px"><h3>最近语音记录</h3><p class="small muted">历史录音的时间戳统计；实时通话只保存对话文字。不同话题、录音条件和识别误差都会影响指标。</p>${rates.length?`<table><thead><tr><th>时间</th><th>识别词数</th><th>语速（词/分）</th><th>停顿占比</th></tr></thead><tbody>${rates.map(m=>`<tr><td>${esc(englishDate(m.created))}</td><td>${m.word_count}</td><td>${m.speech_rate_wpm}</td><td>${m.pause_ratio==null?'—':Math.round(m.pause_ratio*100)+'%'}</td></tr>`).join('')}</tbody></table>`:'<p class="muted">还没有可测量的语音样本。实时对话不生成语速、停顿或发音分数。</p>'}</div>`;
}
views.englishProfile=async()=>{
 englishCleanup();const p=await api('/english/profile');
 return {html:heading('我的英语画像','根据真实练习记录安排内容；不会推断你的身份、性格或正式英语等级。')+englishProfileHtml(p)+`<form id="englishInterests" class="card" style="margin-top:20px"><h3>告诉我，你喜欢聊什么？</h3><div class="english-interest-options">${Object.entries(p.categories).map(([id,title])=>`<label><input type="checkbox" name="interest" value="${id}" ${p.interests.includes(id)?'checked':''}>${esc(title)}</label>`).join('')}</div><button class="primary">保存兴趣</button><button type="button" id="englishChooseTopic">去选话题 →</button></form>`,bind(){
 $('#englishInterests').onsubmit=busy(async e=>{await api('/english/profile','POST',{interests:new FormData(e.target).getAll('interest')});toast('兴趣已保存，话题会优先展示你感兴趣的内容')});$('#englishChooseTopic').onclick=()=>show('english');
 }};
};
views.englishStudents=async()=>{englishCleanup();const rows=await api('/teacher/english/students');return {html:heading('英语练习档案','查看参与记录和下一步练习建议，口语模块暂不生成正式成绩。')+`<section class="card table-wrap"><table><thead><tr><th>姓名 / 学号</th><th>有效样本</th><th>回答 / 语音</th><th>下次练习建议</th></tr></thead><tbody>${rows.map(s=>`<tr><td>${esc(s.name)}<br><small>${esc(s.student_no)}</small></td><td>${s.profile.completed_samples}</td><td>${s.profile.practice_turns} / ${s.profile.spoken_turns}</td><td>${esc(s.profile.recommendation)}</td></tr>`).join('')}</tbody></table>${!rows.length?'<p class="empty">暂无学生英语练习记录。</p>':''}</section>`}};
