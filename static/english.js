'use strict';
// Loaded after app.js; the main app owns authentication and course navigation.
let englishSession=null, englishData=null, englishRecorder=null, englishStream=null, englishTimer=null, englishTranscription='', englishChunks=[], englishSending=false, englishAutoplay=true, englishAudioUrl=null, englishAudioContext=null, englishLevelTimer=null, englishMicDevice='';
const englishDate=x=>x?new Date(typeof x==='number'?x*1000:x).toLocaleString():'尚未同步';
function englishCleanup(){
 if(englishRecorder?.state==='recording'){englishRecorder.onstop=null;englishRecorder.stop()}
 englishRecorder=null;englishStream?.getTracks().forEach(t=>t.stop());englishStream=null;
 clearTimeout(englishTimer);englishTranscription='';englishStopMeter();
 if(englishAudioUrl){$('#englishPlayback')?.pause?.();URL.revokeObjectURL(englishAudioUrl);englishAudioUrl=null}
 if(typeof speechSynthesis!=='undefined')speechSynthesis.cancel();
}
function englishStopMeter(){
 if(englishLevelTimer!==null){clearInterval(englishLevelTimer);englishLevelTimer=null}
 if(englishAudioContext){englishAudioContext.close().catch(()=>{});englishAudioContext=null}
}
async function englishMicrophones(){
 if(typeof navigator==='undefined'||!navigator.mediaDevices?.enumerateDevices)return;
 try{const devices=await navigator.mediaDevices.enumerateDevices();const select=$('#englishMicrophone');if(!select||page!=='englishChat')return;
 select.innerHTML='<option value="">系统默认麦克风</option>'+devices.filter(d=>d.kind==='audioinput'&&d.deviceId).map((d,i)=>`<option value="${esc(d.deviceId)}">${esc(d.label||'麦克风 '+(i+1))}</option>`).join('');select.value=englishMicDevice;
 }catch{}
}
function englishStartMeter(stream){
 englishStopMeter();const C=typeof window!=='undefined'&&(window.AudioContext||window.webkitAudioContext);if(!C)return;
 try{const context=new C();englishAudioContext=context;context.resume().catch(()=>{});const analyser=context.createAnalyser();analyser.fftSize=1024;context.createMediaStreamSource(stream).connect(analyser);const values=new Float32Array(analyser.fftSize);
 englishLevelTimer=setInterval(()=>{analyser.getFloatTimeDomainData(values);const rms=Math.sqrt(values.reduce((n,v)=>n+v*v,0)/values.length);const meter=$('#englishMicLevel');if(meter)meter.value=Math.max(0,Math.min(100,(20*Math.log10(Math.max(rms,1e-8))+60)/60*100))},150);
 }catch{englishStopMeter()}
}
function englishAudioPreview(file){
 if(typeof URL==='undefined'||!URL.createObjectURL)return;
 if(englishAudioUrl)URL.revokeObjectURL(englishAudioUrl);englishAudioUrl=URL.createObjectURL(file);
 const audio=$('#englishPlayback');if(audio)audio.src=englishAudioUrl;const preview=$('#englishRecordingPreview');if(preview)preview.hidden=false;
}
function englishSpeak(text){
 if(typeof speechSynthesis==='undefined'||typeof SpeechSynthesisUtterance==='undefined'){toast('此浏览器不支持朗读，可以换用 Chrome 或 Edge');return}
 speechSynthesis.cancel();const speech=new SpeechSynthesisUtterance(text);speech.lang='en-US';speech.rate=.85;
 const voice=speechSynthesis.getVoices().find(v=>/^en[-_]/i.test(v.lang));if(voice)speech.voice=voice;
 speech.onerror=()=>toast('朗读未成功，请检查设备声音或重试');speechSynthesis.speak(speech);
}
function englishMetrics(speech){
 if(!speech)return '<span class="small muted">文字回答 · 未测量语速、停顿或发音</span>';
 const m=speech.metrics;
 return `<div class="speech-metrics"><span>识别词数 <b>${esc(m.word_count)}</b></span><span>语速 <b>${m.speech_rate_wpm==null?'未测得':esc(m.speech_rate_wpm)+' 词/分'}</b></span><span>停顿占比 <b>${m.pause_ratio==null?'未测得':Math.round(m.pause_ratio*100)+'%'}</b></span></div><small class="muted">按原始识别时间戳统计 · 停顿阈值 300ms${speech.transcript_edited?' · 文字已修改，语音指标仍对应原识别结果':''}</small>`;
}
views.english=async()=>{
 englishCleanup();const [d,p]=await Promise.all([api('/english/topics'),api('/english/profile')]);englishData=d;
 return {html:heading('开口聊一点，英语近一点','从一个感兴趣的话题开始。每次说一两句，也是在进步。')+
 `<section class="english-banner"><div><span class="eyebrow">SPEAK · LISTEN · TRY AGAIN</span><h2>今天，你想聊什么？</h2><p>${esc(p.recommendation)}</p><button id="englishProfile">设置我的兴趣 →</button></div><div class="english-orbit" aria-hidden="true">“ Hello. ”</div></section>`+
 `<div class="english-status"><span class="badge ${d.ai_configured?'':'warn'}">${d.ai_configured?'AI 对话接口已配置':'固定问答演示 · 待教师配置 AI'}</span><span class="badge ${d.speech_enabled?'':'warn'}">${d.speech_enabled?'本地语音识别已启用':'语音识别待启用 · 可先文字练习'}</span></div>`+
 `<div class="section-title"><div><h3>选一个话题，AI 先开口</h3><p class="small muted">近期话题来自新闻标题，适合聊想法；常用情景随时可练。</p></div>${user.role==='teacher'?'<button id="refreshEnglishNews">更新近期话题</button>':''}</div>`+
 `<div class="card news-status"><b>近期话题</b><p class="small">最近成功同步：${esc(englishDate(d.news.updated))} · 最近尝试：${esc(englishDate(d.news.checked))}</p>${d.news.stale?'<p class="small warning">同步已超过24小时或尚未同步，请留意新闻发布日期。</p>':''}${d.news.error?`<p class="small muted">${esc(d.news.error)}</p>`:''}<small class="muted">只读取标题和来源，不代表已阅读或核实新闻全文。不是热搜排行榜。</small></div>`+
 `<div class="english-filters" role="group" aria-label="话题分类"><button class="primary" data-english-filter="all">全部话题</button>${Object.entries(d.categories).map(([id,title])=>`<button data-english-filter="${id}">${esc(title)}</button>`).join('')}</div><div class="course-grid english-topics">${d.topics.map(t=>`<article class="card english-topic" data-english-category="${esc(t.category)}"><div class="card-top"><span class="badge ${t.kind==='news'?'':'warn'}">${t.kind==='news'?'近期话题':'常用情景'}</span><span class="small muted">${esc(d.categories[t.category])}</span></div><h3>${esc(t.title)}</h3>${t.english_title?`<p class="small muted">${esc(t.english_title)}</p>`:''}${t.kind==='news'?`<p class="small muted">${esc(t.source)} · ${esc(englishDate(t.published))}</p><a class="small" href="${esc(t.url)}" target="_blank" rel="noopener noreferrer">查看新闻来源 ↗</a>`:'<p class="small muted">短句问答 · 可随时查看句首提示</p>'}<button class="primary start-english" data-topic="${esc(t.id)}">开始聊聊 →</button></article>`).join('')}</div>`,bind(){
 $('#englishProfile').onclick=()=>show('englishProfile');
 document.querySelectorAll('[data-english-filter]').forEach(b=>b.onclick=()=>{document.querySelectorAll('[data-english-filter]').forEach(x=>x.classList.toggle('primary',x===b));document.querySelectorAll('[data-english-category]').forEach(x=>x.hidden=b.dataset.englishFilter!=='all'&&x.dataset.englishCategory!==b.dataset.englishFilter)});
 document.querySelectorAll('[data-topic]').forEach(b=>b.onclick=busy(async()=>{b.disabled=true;try{englishSession=await api('/english/sessions','POST',{topic_id:b.dataset.topic});if(page!=='english')return;await show('englishChat');if(page==='englishChat'&&englishAutoplay&&typeof speechSynthesis!=='undefined')englishSpeak(englishSession.turns[0].text)}finally{b.disabled=false}}));
 if($('#refreshEnglishNews'))$('#refreshEnglishNews').onclick=busy(async()=>{const b=$('#refreshEnglishNews');b.disabled=true;b.textContent='正在同步…';try{await api('/english/news/refresh','POST');await show('english')}finally{b.disabled=false;b.textContent='更新近期话题'}});
 }};
};
views.englishChat=async()=>{
 englishCleanup();if(!englishSession)return views.englishHistory();
 englishSession=await api('/english/sessions/'+englishSession.id);
 if(!englishData)englishData=await api('/english/topics');
 const s=englishSession,ended=!!s.ended;
 return {html:heading(esc(s.topic.title),`第 ${s.student_turns} / 20 轮 · ${s.mode==='stretch'?'尝试补充理由或例子':'简短问答，慢慢来'}`,`<button id="englishBack">← 话题列表</button>`)+
 `<div class="chat-layout"><section class="card english-chat" aria-label="英语对话记录">${s.turns.map(t=>`<article class="chat-turn ${t.role==='student'?'mine':'partner'}"><div class="chat-speaker">${t.role==='student'?'我':'AI 练习伙伴'}${t.role==='assistant'?`<button class="text-btn" data-speak-turn="${t.id}" aria-label="朗读这条回复">▶ 慢速朗读</button>`:''}</div><p class="chat-text">${esc(t.text)}</p>${t.role==='assistant'?`${t.details.notice?`<p class="small warning">${esc(t.details.notice)}</p>`:''}${(t.details.corrections||[]).length?`<details class="english-corrections"><summary>表达建议（AI，供参考）</summary>${t.details.corrections.map(c=>`<blockquote>${esc(c.quote)}</blockquote><p>${esc(c.suggestion)}</p><small>${esc(c.reason)}</small>`).join('')}</details>`:''}`:englishMetrics(t.details.speech)}</article>`).join('')}</section><aside class="card english-coach"><span class="eyebrow">YOUR PRACTICE SPACE</span><h3>先表达，再完善</h3><label class="english-auto-read"><input type="checkbox" id="englishAutoRead" ${englishAutoplay?'checked':''}>收到回复后自动慢速朗读</label><p>回答一两句就好。不知道怎么说时，试试句首提示。</p>${!ended?'<button id="englishHint">给我一点提示</button><div id="englishHintText" class="feedback" hidden></div>':''}<hr><p class="small muted">语速和停顿由识别时间戳计算，受转写误差影响。这里不生成发音分数，也不计入正式课程成绩。</p><p class="small muted">录音用于本地识别，处理后不保存音频。确认发送的文字、话题和近期对话会发给教师配置的 AI 接口；朗读由浏览器语音服务提供。</p></aside></div>`+
 (ended?'<div class="card"><h3>本次练习已结束</h3><p>完成至少3轮问答的对话会成为画像样本。</p><button id="englishReport">查看我的学习画像 →</button></div>':`<form id="englishTurnForm" class="card english-composer"><label for="englishAnswer">你的英语回答 <small>先转写确认，也可以直接输入</small></label><textarea id="englishAnswer" name="text" required maxlength="2000" rows="3" placeholder="I think… / In my project…"></textarea><div class="actions"><label>录音设备<select id="englishMicrophone"><option value="">系统默认麦克风</option></select></label><span class="small">输入音量（非评分）<meter id="englishMicLevel" min="0" max="100" value="0"></meter></span><button type="button" id="englishRecord">● 录一句（最多60秒）</button><label class="audio-upload">上传音频<input id="englishAudio" type="file" accept="audio/*,.webm,.m4a,.mp3,.wav,.ogg"></label><button class="primary" id="englishSend" type="submit" ${s.student_turns>=20?'disabled':''}>确认并发送 →</button><button type="button" id="englishEnd">结束本次练习</button></div><div id="englishRecordingPreview" hidden><p class="small">回听刚才的录音，确认能清楚听到自己的声音。</p><audio id="englishPlayback" controls preload="metadata" style="max-width:100%;width:100%"></audio></div><p id="englishAudioStatus" class="small muted" role="status">音频不超过5 MB。识别结果可以修改，发送前请确认。</p><p id="englishMicNote" class="small warning" hidden></p></form>`),bind(){
 $('#englishBack').onclick=()=>show('english');$('#englishAutoRead').onchange=e=>{englishAutoplay=e.target.checked;if(!englishAutoplay&&typeof speechSynthesis!=='undefined')speechSynthesis.cancel()};
 document.querySelectorAll('[data-speak-turn]').forEach(b=>b.onclick=()=>englishSpeak(s.turns.find(t=>String(t.id)===b.dataset.speakTurn).text));
 if(ended){$('#englishReport').onclick=()=>show('englishProfile');return}
 $('#englishHint').onclick=busy(async()=>{const r=await api('/english/sessions/'+s.id+'/hint','POST');$('#englishHintText').textContent=r.hint;$('#englishHintText').hidden=false});
 $('#englishEnd').onclick=busy(async()=>{if(englishRecorder?.state==='recording'){toast('请先结束录音');return}if(englishSending){toast('请等待识别或当前回复完成');return}await api('/english/sessions/'+s.id+'/end','POST');toast('练习已保存');await show('englishProfile')});
 $('#englishTurnForm').onsubmit=busy(async e=>{if(englishRecorder?.state==='recording'){toast('请先结束录音并确认转写');return}if(englishSending)return;englishSending=true;$('#englishSend').disabled=true;
  const body={text:$('#englishAnswer').value,transcription_id:englishTranscription,expected_turns:s.student_turns,request_id:typeof crypto!=='undefined'&&crypto.randomUUID?crypto.randomUUID():Date.now().toString(36)+Math.random().toString(36).slice(2)};
  try{const updated=await api('/english/sessions/'+s.id+'/turn','POST',body);if(page==='englishChat'&&englishSession?.id===s.id){englishSession=updated;await show('englishChat');if(englishAutoplay&&typeof speechSynthesis!=='undefined')englishSpeak(updated.turns[updated.turns.length-1].text)}}finally{englishSending=false;const b=$('#englishSend');if(b)b.disabled=false}
 });
 const secure=typeof window!=='undefined'&&window.isSecureContext;
 const available=typeof navigator!=='undefined'&&navigator.mediaDevices?.getUserMedia&&typeof MediaRecorder!=='undefined';
 if(!englishData.speech_enabled||!secure||!available){$('#englishRecord').disabled=true;$('#englishMicNote').hidden=false;$('#englishMicNote').textContent=!englishData.speech_enabled?'教师需先启用服务器语音识别。当前可以文字练习。':!secure?'当前公网 HTTP 页面不能调用麦克风。启用 HTTPS 后可直接录音；现在可上传已有音频。':'此浏览器不支持网页录音，请上传已有音频。'}
 if(!englishData.speech_enabled)$('#englishAudio').disabled=true;
 $('#englishMicrophone').onchange=e=>englishMicDevice=e.target.value;englishMicrophones();
 $('#englishAudio').onchange=busy(async e=>{const f=e.target.files[0];if(f)await englishUploadAudio(f,s.id);e.target.value=''});
 $('#englishRecord').onclick=busy(async()=>{
  if(englishRecorder?.state==='recording'){englishRecorder.stop();return}
  if(englishSending)return;
  $('#englishRecord').disabled=true;
  if(typeof speechSynthesis!=='undefined')speechSynthesis.cancel();$('#englishPlayback')?.pause?.();
  let stream;try{stream=await navigator.mediaDevices.getUserMedia({audio:{...(englishMicDevice?{deviceId:{exact:englishMicDevice}}:{}),echoCancellation:true,noiseSuppression:true,autoGainControl:true}})}catch(e){throw Error(({NotAllowedError:'浏览器未允许麦克风，请在该站点权限中选择允许。',NotFoundError:'没有找到可用麦克风，请检查设备连接。',OverconstrainedError:'所选麦克风不可用，请切换到系统默认麦克风。'})[e.name]||e.message)}finally{if($('#englishRecord'))$('#englishRecord').disabled=false}
  // Navigation during the permission dialog must not leave an open microphone.
  if(page!=='englishChat'||englishSession?.id!==s.id){stream.getTracks().forEach(t=>t.stop());return}
  englishStream=stream;englishStartMeter(stream);englishMicrophones();$('#englishMicrophone').disabled=true;
  try{
   const type=['audio/webm;codecs=opus','audio/mp4','audio/webm'].find(t=>MediaRecorder.isTypeSupported(t));
   const recorder=new MediaRecorder(englishStream,type?{mimeType:type}:{});englishRecorder=recorder;englishChunks=[];
   recorder.ondataavailable=e=>{if(e.data.size)englishChunks.push(e.data)};
   recorder.onerror=()=>{englishCleanup();toast('录音失败，请检查麦克风权限')};
   recorder.onstop=async()=>{clearTimeout(englishTimer);englishStopMeter();if($('#englishMicrophone'))$('#englishMicrophone').disabled=false;englishStream?.getTracks().forEach(t=>t.stop());englishStream=null;englishRecorder=null;const b=$('#englishRecord');if(b)b.textContent='● 录一句（最多60秒）';try{await englishUploadAudio(new Blob(englishChunks,{type:recorder.mimeType}),s.id)}catch(e){toast(e.message)}};
   recorder.start(1000);$('#englishRecord').textContent='■ 结束录音并转写';$('#englishAudioStatus').textContent='录音中…当前设备：'+(stream.getAudioTracks()[0]?.label||'默认麦克风')+'。说话时输入音量条应有变化。';englishTimer=setTimeout(()=>{if(recorder.state==='recording')recorder.stop()},60000);
  }catch(e){englishCleanup();throw e}
 });
 $('#englishAnswer').focus?.();
 }};
};
async function englishUploadAudio(file,sid){
 if(englishSending)return;if(englishRecorder?.state==='recording')throw Error('请先结束当前录音');if(file.size>5000000)throw Error('音频不能超过5 MB');
 englishAudioPreview(file);englishTranscription='';englishSending=true;const status=$('#englishAudioStatus'),send=$('#englishSend'),record=$('#englishRecord'),recordDisabled=record?.disabled;
 if(send)send.disabled=true;if(record)record.disabled=true;if(status)status.textContent='正在本地识别…请稍候，先不要发送。';
 try{const form=new FormData();form.append('file',file,'answer.audio');const r=await api('/english/transcribe','POST',form);
  if(page!=='englishChat'||englishSession?.id!==sid)return;
  englishTranscription=r.transcription_id;$('#englishAnswer').value=r.text;$('#englishAudioStatus').textContent='识别完成。请检查文字后点击“确认并发送”；修改文字不会改写原录音指标。'+(r.warnings?.length?' '+r.warnings.join(' '):'');
 }catch(e){if(status)status.textContent=e.message+' 请先用上面的播放器回听这段录音。';throw e}
 finally{englishSending=false;if(send)send.disabled=false;if(record)record.disabled=recordDisabled}
}
views.englishHistory=async()=>{
 englishCleanup();const rows=await api('/english/sessions');
 return {html:heading('我的对话记录','继续未完成的练习，或回看以前的表达。')+`<section class="card table-wrap"><table><thead><tr><th>话题</th><th>开始时间</th><th>回答轮数</th><th>状态</th><th></th></tr></thead><tbody>${rows.map(s=>`<tr><td>${esc(s.topic.title)}</td><td>${esc(englishDate(s.created))}</td><td>${s.turns}</td><td>${s.ended?'已结束':'可继续'}</td><td><button data-resume-english="${s.id}">${s.ended?'回看':'继续'} →</button></td></tr>`).join('')}</tbody></table>${!rows.length?'<div class="empty">还没有练习记录，从一个简单话题开始吧。</div>':''}</section>`,bind(){document.querySelectorAll('[data-resume-english]').forEach(b=>b.onclick=busy(async()=>{englishSession={id:Number(b.dataset.resumeEnglish)};await show('englishChat')}))}};
};
function englishProfileHtml(p){
 const rates=p.recent_speech.filter(m=>m.speech_rate_wpm!=null);
 return `<div class="stats"><div class="stat"><span>有效对话样本</span><strong>${p.completed_samples}<small> 次</small></strong></div><div class="stat"><span>回答 / 语音回答</span><strong>${p.practice_turns}<small> / ${p.spoken_turns}</small></strong></div><div class="stat"><span>平均回答词数</span><strong>${p.average_words??'—'}</strong></div></div><div class="card"><h3>下一次怎么练？</h3><p>${esc(p.recommendation)}</p><p class="small muted">${esc(p.measurement_note)}</p><p>近期常练兴趣：${p.inferred_interests.map(x=>esc(p.categories[x])).join('、')||'样本积累中'}</p></div><div class="card table-wrap" style="margin-top:20px"><h3>最近语音记录</h3><p class="small muted">按每段识别语音统计；更快不代表更好。不同话题、录音条件和识别误差都会影响指标。</p>${rates.length?`<table><thead><tr><th>时间</th><th>识别词数</th><th>语速（词/分）</th><th>停顿占比</th></tr></thead><tbody>${rates.map(m=>`<tr><td>${esc(englishDate(m.created))}</td><td>${m.word_count}</td><td>${m.speech_rate_wpm}</td><td>${m.pause_ratio==null?'—':Math.round(m.pause_ratio*100)+'%'}</td></tr>`).join('')}</tbody></table>`:'<p class="muted">还没有可测量的语音样本。文字练习不产生语速或停顿数据。</p>'}</div>`;
}
views.englishProfile=async()=>{
 englishCleanup();const p=await api('/english/profile');
 return {html:heading('我的英语画像','根据真实练习记录安排内容；不会推断你的身份、性格或正式英语等级。')+englishProfileHtml(p)+`<form id="englishInterests" class="card" style="margin-top:20px"><h3>告诉我，你喜欢聊什么？</h3><div class="english-interest-options">${Object.entries(p.categories).map(([id,title])=>`<label><input type="checkbox" name="interest" value="${id}" ${p.interests.includes(id)?'checked':''}>${esc(title)}</label>`).join('')}</div><button class="primary">保存兴趣</button><button type="button" id="englishChooseTopic">去选话题 →</button></form>`,bind(){
 $('#englishInterests').onsubmit=busy(async e=>{await api('/english/profile','POST',{interests:new FormData(e.target).getAll('interest')});toast('兴趣已保存，话题会优先展示你感兴趣的内容')});$('#englishChooseTopic').onclick=()=>show('english');
 }};
};
views.englishStudents=async()=>{englishCleanup();const rows=await api('/teacher/english/students');return {html:heading('英语练习档案','查看参与记录和下一步练习建议，口语模块暂不生成正式成绩。')+`<section class="card table-wrap"><table><thead><tr><th>姓名 / 学号</th><th>有效样本</th><th>回答 / 语音</th><th>下次练习建议</th></tr></thead><tbody>${rows.map(s=>`<tr><td>${esc(s.name)}<br><small>${esc(s.student_no)}</small></td><td>${s.profile.completed_samples}</td><td>${s.profile.practice_turns} / ${s.profile.spoken_turns}</td><td>${esc(s.profile.recommendation)}</td></tr>`).join('')}</tbody></table>${!rows.length?'<p class="empty">暂无学生英语练习记录。</p>':''}</section>`}};
