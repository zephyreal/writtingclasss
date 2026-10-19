const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert');
const nodes=new Map();
function node(s){if(!nodes.has(s))nodes.set(s,{textContent:'',innerHTML:'',value:'',hidden:false,disabled:false,style:{},addEventListener(){},showModal(){},close(){},focus(){},querySelectorAll(){return []}});return nodes.get(s)}
class Form{constructor(){this.rows=[]}append(...args){this.rows.push(args)}getAll(){return []}}
const ctx=vm.createContext({document:{querySelector:node,querySelectorAll:()=>[],addEventListener(){}},window:{isSecureContext:false},navigator:{mediaDevices:{getUserMedia(){throw Error('Should never invoke without permission')}}},fetch:async()=>({ok:false,status:401,json:async()=>({})}),setTimeout,clearTimeout,console,FormData:Form});
vm.runInContext(fs.readFileSync(__dirname+'/static/app.js','utf8'),ctx);
vm.runInContext(fs.readFileSync(__dirname+'/static/english.js','utf8'),ctx);
const profile={categories:{engineering:'机械与制造'},recommendation:'先练短句',measurement_note:'识别时间戳统计',interests:['engineering'],inferred_interests:[],recent_speech:[],completed_samples:0,practice_turns:0,spoken_turns:0,average_words:null};
const topics={topics:[{id:'engineering-my-project',title:'<unsafe>',category:'engineering',kind:'scenario'}],news:{updated:null,checked:null,error:'未同步',stale:true},categories:profile.categories,ai_configured:true,speech_enabled:true};
const session={id:1,topic:{title:'My project'},mode:'support',created:1,ended:null,student_turns:0,turns:[{id:1,role:'assistant',text:'Hello! What is your project?',details:{hint:'I work on…',corrections:[]}}]};
ctx.fixtureProfile=profile;ctx.fixtureTopics=topics;ctx.fixtureSession=session;
vm.runInContext(`user={role:'student',name:'学生'};api=async p=>p==='/english/profile'?fixtureProfile:p==='/english/topics'?fixtureTopics:p==='/english/transcribe'?{text:'I make robots.',transcription_id:'server-ticket'}:fixtureSession`,ctx);
(async()=>{
 let result=await vm.runInContext('views.english()',ctx);
 assert(result.html.includes('&lt;unsafe&gt;')&&!result.html.includes('<unsafe>'));
 assert(result.html.includes('未同步')&&result.html.includes('开始聊聊'));
 vm.runInContext('englishSession=fixtureSession;page="englishChat"',ctx);
 result=await vm.runInContext('views.englishChat()',ctx);result.bind();
 assert(result.html.includes('慢速朗读')&&result.html.includes('确认并发送'));
 assert(node('#englishRecord').disabled);
 assert(node('#englishMicNote').textContent.includes('HTTP'));
 await vm.runInContext('englishUploadAudio({size:100},1)',ctx);
 assert(node('#englishRecord').disabled,'上传完音频后，HTTP页面仍不能启用麦克风');
 assert(node('#englishAnswer').value==='I make robots.');
 assert(vm.runInContext('englishTranscription',ctx)==='server-ticket');
 const typed=vm.runInContext('englishMetrics(null)',ctx);
 assert(typed.includes('未测量')&&!typed.includes('词/分'));
 ctx.stopped=0;ctx.tracksStopped=0;
 vm.runInContext('englishRecorder={state:"recording",stop(){stopped++}};englishStream={getTracks(){return [{stop(){tracksStopped++}}]}};englishCleanup()',ctx);
 assert(ctx.stopped===1&&ctx.tracksStopped===1);
 result=await vm.runInContext('views.englishProfile()',ctx);
 assert(result.html.includes('还没有可测量的语音样本')&&result.html.includes('英语等级'));
 console.log('English UI escaping, HTTP mic gate, upload confirmation, cleanup and profile checks passed');
})().catch(e=>{console.error(e);process.exitCode=1});
