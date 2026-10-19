const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert');
const nodes=new Map();let formValues={};
function node(s){if(!nodes.has(s))nodes.set(s,{textContent:'',innerHTML:'',value:'',hidden:false,disabled:false,style:{},addEventListener(){},showModal(){},close(){},querySelectorAll(){return []}});return nodes.get(s)}
class Form{get(k){return formValues[k]}}
const ctx=vm.createContext({document:{querySelector:node,querySelectorAll:()=>[],addEventListener(){}},fetch:async()=>({ok:false,status:401,json:async()=>({})}),FormData:Form,setTimeout,clearTimeout,console,confirm:()=>false});
for(const file of ['app.js','english.js','teacher-writing.js'])vm.runInContext(fs.readFileSync(__dirname+'/static/'+file,'utf8'),ctx);
ctx.assignment={id:7,revision:3,title:'引言练习 <x>',instructions:'只写引言',grading_instructions:'重点评价研究空白',deadline:'',rubric:[{name:'研究问题',max:60},{name:'表达',max:40}]};
vm.runInContext('user={name:"教师",role:"teacher"};api=async()=>[assignment]',ctx);
(async()=>{
 let r=await vm.runInContext('views.assignments()',ctx);
 assert(r.html.includes('data-edit-assignment="7"')&&r.html.includes('重点评价研究空白')&&r.html.includes('&lt;x&gt;'));
 vm.runInContext('openAssignmentEditor(assignment)',ctx);
 assert(node('#modalBody').innerHTML.includes('研究问题 | 60')&&node('#modalBody').innerHTML.includes('name="grading_instructions"'));
 vm.runInContext('api=async(path,method,data)=>{lastRequest={path,method,data};return {ok:true}};show=async id=>{lastPage=id}',ctx);
 formValues={title:'修改后的作业',instructions:'补充问题',deadline:'',grading_instructions:'只评价引言',rubric_lines:'研究问题 | 70\n表达 | 30'};
 await node('#assignmentEditor').onsubmit({target:{},preventDefault(){}});
 const req=vm.runInContext('lastRequest',ctx);
 assert(req.path==='/assignments/7'&&req.method==='PUT'&&req.data.expected_revision===3&&req.data.rubric[0].max===70);
 ctx.jobs={counts:{pending:1},jobs:[{id:2,run_at:1,state:'pending',name:'学生',title:'引言',error:''}]};
 ctx.submissions=[{id:9,title:'引言',name:'学生',student_no:'100',created:'今天',status:'待复核',score:null,ai:{score:82,scoring_basis:{revision:1}},assignment_revision:2}];
 vm.runInContext("api=async p=>p==='/teacher/submissions'?submissions:p==='/teacher/review-jobs'?jobs:[assignment]",ctx);
 r=await vm.runInContext('views.review()',ctx);
 assert(r.html.includes('一键批改未评作业')&&r.html.includes('安排定时批改')&&r.html.includes('data-cancel-review="2"'));
 assert(r.html.includes('82')&&r.html.includes('旧版标准'));
 ctx.settings={base_url:'https://api.deepseek.com',model:'deepseek-flash',configured:true,review_mode:'scheduled',review_time:'00:30',off_peak_only:true,error_threshold:5,formal_standard:'学术规范要求'};
 vm.runInContext('api=async()=>settings',ctx);
 r=await vm.runInContext('views.settings()',ctx);
 assert(r.html.includes('name="review_time"')&&r.html.includes('name="off_peak_only"')&&r.html.includes('线上练习不能可靠阻止AI代答'));

 ctx.reviewRecord={id:9,name:'学生',status:'形式预审通过，待教师评阅',assignment_revision:1,published:false,returned:false,score:null,feedback:'',ai:{score:null,summary:'仅形式审核',dimensions:[],issues:[],reference_note:'未核实',triage:{recommendation:'review',reasons:[],required_changes:[],evidence:[],evidence_matches:[]}}};
 vm.runInContext('openReview(reviewRecord)',ctx);
 assert(node('#modalBody').innerHTML.includes('补评分 / 重新AI批改')&&node('#modalBody').innerHTML.includes('旧版只做形式审核'));
 ctx.reviewRecord.ai.score=80;ctx.reviewRecord.ai.dimensions=[{name:'表达',score:80,max:100,comment:'评分意见',quote:'未匹配的引用',quote_verified:false}];
 vm.runInContext('openReview(reviewRecord)',ctx);
 assert(node('#modalBody').innerHTML.includes('评分依据待人工核对')&&node('#modalBody').innerHTML.includes('AI建议分 80'));
 console.log('Paper editing, rubric submission, scoring basis, batch scheduling and settings UI checks passed');
})().catch(e=>{console.error(e);process.exitCode=1});
