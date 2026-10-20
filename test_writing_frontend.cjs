const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert');
const nodes=new Map();function node(s){if(!nodes.has(s))nodes.set(s,{textContent:'',innerHTML:'',hidden:false,value:'',style:{},addEventListener(){},showModal(){},close(){}});return nodes.get(s)}
const ctx=vm.createContext({document:{querySelector:node,querySelectorAll:()=>[],addEventListener(){}},fetch:async()=>({ok:false,status:401,json:async()=>({})}),setTimeout,clearTimeout,console,FormData:class{},confirm:()=>false});
for(const file of ['app.js','english.js','teacher-writing.js','writing-workflow.js'])vm.runInContext(fs.readFileSync(__dirname+'/static/'+file,'utf8'),ctx);
ctx.assignment={id:2,title:'研究问题 <script>',instructions:'科研写作',workflow:1,deadline:'',rubric:[]};
vm.runInContext("user={role:'student'};api=async()=>[assignment]",ctx);
(async()=>{
 let result=await vm.runInContext('views.assignments()',ctx);
 assert(result.html.includes('开始第一步')&&result.html.includes('&lt;script&gt;'));
 ctx.data={assignment:ctx.assignment,stages:[1,2,3,4].map(n=>({title:'阶段'+n,goal:'目标',items:['要求']})),rounds:[],can_submit:true,surveys:[],briefings:[]};
 vm.runInContext('api=async()=>data',ctx);await vm.runInContext('openWriting(2)',ctx);
 assert(node('#content').innerHTML.includes('确认提交第 1 轮')&&node('#content').innerHTML.includes('30秒写作信心自评'));
 ctx.data.rounds=[{id:3,round_no:1,filename:'初稿.docx',review:{summary:'只给意见',strengths:[],issues:[{id:'r1-i1',category:'论证结构',problem:'论证问题',suggestion:'限定范围',quote:'原文',needs_review:false}],tracking:[],next_actions:[],practice:{a:'案例A',b:'案例B',question:'比较',analysis:'参考分析'}}}];ctx.data.can_submit=true;
 await vm.runInContext('openWriting(2)',ctx);
 const html=node('#content').innerHTML;
 assert(html.includes('确认提交第 2 轮')&&html.includes('我的决定')&&html.includes('历次文档与反馈'));
 assert(!html.includes('教师确认成绩')&&!html.includes('终稿建议分'));
 vm.runInContext("user={role:'teacher'};api=async()=>[assignment]",ctx);result=await vm.runInContext('views.assignments()',ctx);
 assert(result.html.includes('第1轮讲评')&&result.html.includes('第4轮讲评'));
 console.log('Four-round task rendering, response choices, escaped content and teacher briefing entry checks passed');
})().catch(e=>{console.error(e);process.exitCode=1});
