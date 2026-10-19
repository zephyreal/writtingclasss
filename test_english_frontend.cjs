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
 for(const old of ['上传音频','确认并发送','录一句','慢速朗读','type="file"'])assert(!result.html.includes(old));
 assert(node('#englishStartCall').disabled&&node('#englishMicNote').textContent.includes('HTTPS'));
 ctx.tracksStopped=0;ctx.closed=0;
 vm.runInContext(`englishCall={sid:1,stream:{getTracks(){return [{stop(){tracksStopped++}}]}},pc:{close(){closed++}},audio:{pause(){}},queue:Promise.resolve()};englishCleanup()`,ctx);
 assert(ctx.tracksStopped===1&&ctx.closed===1);
 vm.runInContext(`testCall={sid:1,queue:Promise.resolve(),captions:new Map(),saved:new Set()};englishCaption(testCall,'student','item_1','<script>',true);englishCaption(testCall,'student','item_1','<script>',true)`,ctx);
 assert(node('#englishCaptions').innerHTML.includes('&lt;script&gt;'));
 assert(vm.runInContext('testCall.saved.size',ctx)===1);
 // Exercise the complete RTC handshake and session gating with a simulated cloud.
 const sent=[];let track={kind:'audio',enabled:true,stop(){}};
 ctx.navigator.mediaDevices.getUserMedia=async()=>({getTracks:()=>[track],getAudioTracks:()=>[track]});
 class Peer{
  constructor(){this.iceGatheringState='complete';this.connectionState='new';this.channel={readyState:'open',send:raw=>{const event=JSON.parse(raw);sent.push(event);if(event.type==='session.update')this.channel.onmessage({data:JSON.stringify({type:'session.updated'})})}}}
  addTrack(t){this.sender={track:t,replaceTrack:async value=>{this.sender.track=value}}}
  getSenders(){return [this.sender]}
  createDataChannel(){return this.channel}
  async createOffer(){return {type:'offer',sdp:'v=0\r\nm=audio 9'}}
  async setLocalDescription(value){this.localDescription=value}
  async setRemoteDescription(value){assert(!track.enabled,'microphone gated before session.created');this.channel.onmessage({data:JSON.stringify({type:'session.created'})})}
  close(){this.connectionState='closed'}
 }
 ctx.RTCPeerConnection=Peer;
 ctx.fetch=async url=>({ok:true,json:async()=>url.endsWith('/connect')?{sdp:'v=0\r\nm=audio 9',expires:Date.now()/1000+300,session:{instructions:'Test configuration',modalities:['text','audio']}}:{ok:true}});
 await vm.runInContext('englishStartCall()',ctx);await Promise.resolve();
 assert(sent[0].type==='session.update'&&sent[1].type==='response.create');assert(track.enabled);
 vm.runInContext('englishCleanup()',ctx);
 // Permission dialog resolved after navigation: no open mic, no cloud connection.
 let release;ctx.lateStream={getTracks(){return [{stop(){ctx.tracksStopped++}}]}};
 ctx.navigator.mediaDevices.getUserMedia=()=>new Promise(resolve=>{release=resolve});
 const pending=vm.runInContext('englishStartCall()',ctx);
 vm.runInContext('englishCleanup()',ctx);release(ctx.lateStream);await pending;
 assert(ctx.tracksStopped===2);
 result=await vm.runInContext('views.englishProfile()',ctx);
 assert(result.html.includes('实时对话不生成')&&result.html.includes('英语等级'));
 console.log('Realtime UI: no uploads/TTS, HTTPS gate, transcript escaping/idempotence, navigation and late-permission cleanup passed');
})().catch(e=>{console.error(e);process.exitCode=1});
