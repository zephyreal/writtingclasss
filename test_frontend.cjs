const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert');
const nodes=new Map(),listeners={};
function node(s){if(!nodes.has(s))nodes.set(s,{textContent:'',innerHTML:'',hidden:false,style:{},addEventListener(){},showModal(){},close(){},querySelectorAll(){return []}});return nodes.get(s)}
const ctx=vm.createContext({document:{querySelector:node,addEventListener:(name,fn)=>listeners[name]=fn},fetch:async()=>({ok:false,status:401,json:async()=>({detail:'请登录'})}),setTimeout,clearTimeout,console,FormData:class{},confirm:()=>false});
vm.runInContext(fs.readFileSync(__dirname+'/static/app.js','utf8'),ctx);
(async()=>{
 await new Promise(r=>setTimeout(r,0));
 vm.runInContext(`user={name:'测试学生',role:'student'};api=async()=>[{id:1,title:'论文作业',instructions:'要求',deadline:'',rubric:[],submission:{id:3,returned:1,return_reason:'补充实验参数',returned_at:'2026-10-19',filename:'旧稿.docx'}}]`,ctx);
 let result=await vm.runInContext('views.assignments()',ctx);
 assert(result.html.includes('提交修改稿')&&result.html.includes('补充实验参数'));
 const profile={research_area:'激光焊接',writing_stage:'初稿写作',goal:'补充证据',total_attempts:2,assessment:{score:0},modules:[{id:1,title:'研究问题',mastery:32.5,first_accuracy:0,recent_accuracy:50,recent_sample:2,recommended_level:2}],weak_topics:['研究问题'],recommendations:[{chapter_id:1,title:'研究问题',level:2,reason:'近期表现'}],recent_mistakes:[],writing_reviews:[]};
 ctx.fixtureProfile=profile;
 vm.runInContext('api=async()=>fixtureProfile',ctx);
 result=await vm.runInContext('views.profile()',ctx);
 assert(result.html.includes('32.5')&&result.html.includes('data-practice-chapter="1"'));
 let prevented=false;await listeners.click({target:{closest:()=>null},preventDefault(){prevented=true}});
 assert(!prevented,'普通点击不应被档案按钮处理器阻止');
 const triage=vm.runInContext(`triageBlock({recommendation:'return',reasons:['需补充实验'],required_changes:['写明参数'],evidence:['原文'],evidence_matches:[true]})`,ctx);
 assert(triage.includes('需教师确认')&&triage.includes('写明参数'));
 console.log('Frontend rendering and event smoke checks passed');
})().catch(e=>{console.error(e);process.exitCode=1});
