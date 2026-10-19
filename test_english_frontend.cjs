const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert');
const nodes=new Map();
function node(s){if(!nodes.has(s))nodes.set(s,{textContent:'',innerHTML:'',value:'',hidden:false,disabled:false,style:{},addEventListener(){},showModal(){},close(){},focus(){},querySelectorAll(){return []},play:async()=>{},pause(){}});return nodes.get(s)}
class Form{constructor(){this.rows=[]}append(...args){this.rows.push(args)}getAll(){return []}}
const ctx=vm.createContext({document:{querySelector:node,querySelectorAll:()=>[],addEventListener(){}},window:{isSecureContext:false,addEventListener(){}},navigator:{mediaDevices:{getUserMedia(){throw Error('Must never invoke without user action')}}},fetch:async()=>({ok:false,status:401,json:async()=>({})}),setTimeout,clearTimeout,setInterval,clearInterval,AbortController,console,FormData:Form});
vm.runInContext(fs.readFileSync(__dirname+'/static/app.js','utf8'),ctx);
vm.runInContext(fs.readFileSync(__dirname+'/static/english.js','utf8'),ctx);
ctx.fixtureProfile={categories:{engineering:'机械与制造'},recommendation:'先练短句',measurement_note:'实时文字仅作学习记录',interests:['engineering'],inferred_interests:[],recent_speech:[],completed_samples:0,practice_turns:0,spoken_turns:0,average_words:null};
ctx.fixtureTopics={topics:[{id:'engineering-my-project',title:'<unsafe>',category:'engineering',kind:'scenario'}],news:{updated:null,checked:null,error:'未同步',stale:true},categories:ctx.fixtureProfile.categories,realtime:{configured:true,minutes:5}};
ctx.fixtureSession={id:1,topic:{title:'My project'},mode:'support',transport:'realtime',live_state:{state:'new'},created:1,ended:null,student_turns:0,turns:[]};
vm.runInContext(`user={role:'student',name:'学生'};api=async p=>p==='/english/profile'?fixtureProfile:p==='/english/topics'?fixtureTopics:fixtureSession`,ctx);
(async()=>{
 let result=await vm.runInContext('views.english()',ctx);
 assert(result.html.includes('&lt;unsafe&gt;')&&!result.html.includes('<unsafe>'));
 assert(result.html.includes('未同步')&&result.html.includes('进入练习'));
 vm.runInContext('englishSession=fixtureSession;page="englishChat"',ctx);
 result=await vm.runInContext('views.englishChat()',ctx);result.bind();
 assert(result.html.includes('开始对话')&&result.html.includes('englishMicrophone'));
 assert(result.html.includes('englishPersonRole')&&result.html.includes('englishPersonVoice'));
 assert(result.html.includes('englishGuide')&&result.html.includes('带我聊'));
 for(const old of ['上传音频','确认并发送','录一句','慢速朗读','type="file"'])assert(!result.html.includes(old));
 assert(node('#englishStartCall').disabled&&node('#englishMicNote').textContent.includes('HTTPS'));
 ctx.tracksStopped=0;ctx.closed=0;
 vm.runInContext(`englishCall={sid:1,stream:{getTracks(){return [{stop(){tracksStopped++}}]}},pc:{close(){closed++}},audio:{pause(){}},queue:Promise.resolve()};englishCleanup()`,ctx);
 assert(ctx.tracksStopped===1&&ctx.closed===1);
 vm.runInContext(`testCall={sid:1,queue:Promise.resolve(),captions:new Map(),saved:new Set()};englishCaption(testCall,'student','item_1','<script>',true);englishCaption(testCall,'student','item_1','<script>',true)`,ctx);
 assert(node('#englishCaptions').innerHTML.includes('&lt;script&gt;'));
 await vm.runInContext('testCall.queue',ctx);assert(vm.runInContext('testCall.saved.size',ctx)===1);
 // Exercise the complete RTC handshake and session gating with a simulated cloud.
 const sent=[];let track={kind:'audio',enabled:true,stop(){}};
 ctx.navigator.mediaDevices.getUserMedia=async()=>({getTracks:()=>[track],getAudioTracks:()=>[track]});
 class Peer{
  constructor(){this.iceGatheringState='complete';this.connectionState='new';this.channel={readyState:'open',send:raw=>{const event=JSON.parse(raw);sent.push(event);if(event.type==='response.create')assert(event.response?.instructions?.trim(),'a first response with no user input must carry an explicit opening task');if(event.type==='session.update')this.channel.onmessage({data:JSON.stringify({type:'session.updated'})})}}}
  addTrack(t){this.sender={track:t,replaceTrack:async value=>{this.sender.track=value}}}
  getSenders(){return [this.sender]}
  createDataChannel(){return this.channel}
  async createOffer(){return {type:'offer',sdp:'v=0\r\nm=audio 9'}}
  async setLocalDescription(value){this.localDescription=value}
  async setRemoteDescription(value){assert(!track.enabled,'microphone gated before session.created');this.channel.onmessage({data:JSON.stringify({type:'session.created'})})}
  close(){this.connectionState='closed'}
 }
 ctx.RTCPeerConnection=Peer;
 ctx.fetch=async (url,init)=>{if(url.endsWith('/connect')){const body=JSON.parse(init.body);assert(body.role==='engineer'&&body.voice==='Jennifer')}return {ok:true,json:async()=>url.endsWith('/connect')?{sdp:'v=0\r\nm=audio 9',expires:Date.now()/1000+300,session:{instructions:'Test configuration',modalities:['text','audio']}}:{ok:true}}};
 node('#englishPersonRole').value='engineer';node('#englishPersonVoice').value='Jennifer';
 await vm.runInContext('englishStartCall()',ctx);await Promise.resolve();
 assert(sent[0].type==='session.update'&&sent[1].type==='response.create');assert(track.enabled);
 // A requested lead creates one assistant turn, with no fabricated learner text.
 const beforeGuide=sent.length;
 vm.runInContext(`englishCall.openingPending=false;englishCall.responding=true;englishGuideCall()`,ctx);
 assert(sent.length===beforeGuide,'guide waits for the current response');
 vm.runInContext(`englishCall.responding=false;englishCall.speaking=true;englishGuideCall()`,ctx);
 assert(sent.length===beforeGuide,'guide never talks over student speech');
 vm.runInContext(`englishCall.speaking=false;englishGuideCall();englishGuideCall()`,ctx);
 assert(sent.length===beforeGuide+1,'one click produces one request until the response arrives');
 assert(sent.at(-1).response.instructions.includes('lead-the-conversation'));
 assert(sent.at(-1).type==='response.create');
 vm.runInContext(`englishEvent(englishCall,{data:JSON.stringify({type:'response.created'})},englishCall.channel);englishEvent(englishCall,{data:JSON.stringify({type:'response.done',response:{status:'completed'}})},englishCall.channel)`,ctx);
 assert(!node('#englishGuide').disabled);
 // Model failures remain visible to the teacher with sensitive strings redacted.
 vm.runInContext(`user={role:'teacher'};englishEvent(englishCall,{data:JSON.stringify({type:'error',error:{code:'invalid_request_error',param:'session.audio.output.voice',message:'Unsupported voice; api_key=sk-FAKE.secret Bearer fake-token'}})},englishCall.channel)`,ctx);
 assert(node('#englishDiagnostic').textContent.includes('invalid_request_error'));
 assert(node('#englishDiagnostic').textContent.includes('session.audio.output.voice'));
 assert(!node('#englishDiagnostic').textContent.includes('sk-FAKE')&&!node('#englishDiagnostic').textContent.includes('fake-token'));
 assert(vm.runInContext('englishCall===null',ctx));
 // A deployment rejecting proactive opening must still permit a real speech turn.
 await vm.runInContext('englishStartCall()',ctx);await Promise.resolve();
 vm.runInContext(`englishEvent(englishCall,{data:JSON.stringify({type:'error',error:{code:'invalid_request_error',param:'response',message:'Cannot create response without input, history, or instructions'}})},englishCall.channel)`,ctx);
 assert(vm.runInContext('englishCall!==null&&englishCall.track.enabled',ctx));
 assert(node('#englishLiveStatus').textContent.includes('Hello'));
 const attempts=sent.filter(x=>x.type==='response.create').length;
 vm.runInContext(`englishEvent(englishCall,{data:JSON.stringify({type:'input_audio_buffer.speech_started'})},englishCall.channel);englishEvent(englishCall,{data:JSON.stringify({type:'response.created'})},englishCall.channel)`,ctx);
 assert(vm.runInContext('englishCall!==null&&englishCall.responding',ctx));
 assert(sent.filter(x=>x.type==='response.create').length===attempts,'no generation retry or artificial user turn');
 vm.runInContext('englishCleanup()',ctx);
 // A cancellation race must keep the microphone/session alive.
 await vm.runInContext('englishStartCall()',ctx);await Promise.resolve();
 vm.runInContext(`englishCall.responding=true;englishEvent(englishCall,{data:JSON.stringify({type:'input_audio_buffer.speech_started'})},englishCall.channel);englishEvent(englishCall,{data:JSON.stringify({type:'error',error:{code:'invalid_request_error',message:'Cancellation failed: no active response found.'}})},englishCall.channel)`,ctx);
 assert(vm.runInContext('englishCall!==null',ctx));
 vm.runInContext(`englishEvent(englishCall,{data:JSON.stringify({type:'response.done',response:{status:'failed',status_details:{error:{code:'insufficient_quota',message:'Quota exceeded'}}}})},englishCall.channel)`,ctx);
 assert(vm.runInContext('englishCall===null',ctx));
 assert(node('#englishDiagnostic').textContent.includes('insufficient_quota'));
 vm.runInContext('englishCleanup()',ctx);
 // Read official final-output snapshots and opaque IDs; retry failed persistence.
 await vm.runInContext('englishStartCall()',ctx);await Promise.resolve();
 const saved=[];let failOnce=true;
 ctx.saveFixture=async(path,method,body)=>{if(path.endsWith('/transcript')){if(failOnce){failOnce=false;throw Error('temporary network failure')}saved.push(body);return {ok:true}}return ctx.fixtureSession};
 vm.runInContext('api=saveFixture',ctx);
 vm.runInContext(`englishEvent(englishCall,{data:JSON.stringify({type:'conversation.item.input_audio_transcription.delta',item_id:'student/+=opaque',text:'I build ',stash:'a robot'})},englishCall.channel);englishEvent(englishCall,{data:JSON.stringify({type:'conversation.item.input_audio_transcription.completed',item_id:'student/+=opaque',transcript:'I build a robot.'})},englishCall.channel);englishEvent(englishCall,{data:JSON.stringify({type:'response.done',response:{status:'completed',output:[{type:'message',id:'assistant/+=opaque',role:'assistant',content:[{type:'audio',transcript:'That sounds useful.'}]}]}})},englishCall.channel)`,ctx);
 await vm.runInContext('englishCall.queue',ctx);
 assert(vm.runInContext('Array.from(englishCall.captions.values()).some(x=>x.failed)',ctx));
 await vm.runInContext('englishFlushRecords(englishCall)',ctx);
 assert(saved.some(x=>x.role==='student'&&x.item_id==='student/+=opaque'&&x.text==='I build a robot.'));
 assert(saved.some(x=>x.role==='assistant'&&x.text==='That sounds useful.'));
 vm.runInContext('englishCleanup()',ctx);
 // Permission dialog resolved after navigation: no open mic, no cloud connection.
 let release;ctx.lateStream={getTracks(){return [{stop(){ctx.tracksStopped++}}]}};
 ctx.navigator.mediaDevices.getUserMedia=()=>new Promise(resolve=>{release=resolve});
 vm.runInContext('englishLastCall=null',ctx);
 const pending=vm.runInContext('englishStartCall()',ctx);
 vm.runInContext('englishCleanup()',ctx);release(ctx.lateStream);await pending;
 assert(ctx.tracksStopped===2);
 vm.runInContext(`api=async p=>p==='/english/profile'?fixtureProfile:p==='/english/grades'?{sessions:[],average:null,published_count:0,basis:'教师发布后计入'}:fixtureSession`,ctx);
 result=await vm.runInContext('views.englishProfile()',ctx);
 assert(result.html.includes('实时对话不生成')&&result.html.includes('英语等级'));
 const scored=vm.runInContext(`englishAssessmentHtml({ended:1,assessment:{published:true,teacher_score:0,teacher_feedback:'<unsafe>',status:'manual',result:{score:0,feedback:'<unsafe>',dimensions:[{name:'回应',score:0,max:40,reason:'<reason>',quote:'<quote>'}]}}})`,ctx);
 assert(scored.includes('0 / 100')&&scored.includes('&lt;unsafe&gt;')&&!scored.includes('<unsafe>'));
 const history=await vm.runInContext('views.englishHistory()',ctx);
 assert(history.html.includes('待发布')&&history.html.includes('教师发布后计入'));
 console.log('Records snapshots, retry, realtime UI: no uploads/TTS, HTTPS gate, transcript escaping/idempotence, navigation and late-permission cleanup passed');
})().catch(e=>{console.error(e);process.exitCode=1});
