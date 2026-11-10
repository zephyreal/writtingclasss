const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert');
const nodes=new Map(),groups=new Map();let values={};
function node(s){if(!nodes.has(s))nodes.set(s,{textContent:'',innerHTML:'',hidden:false,value:'',style:{},listeners:{},addEventListener(k,f){this.listeners[k]=f},showModal(){},close(){}});return nodes.get(s)}
class Form extends Map{constructor(){super(Object.entries(values))}getAll(k){return [].concat(this.get(k)||[])}}
const ctx=vm.createContext({window:{addEventListener(){}},document:{querySelector:node,querySelectorAll:s=>groups.get(s)||[],addEventListener(){}},fetch:async()=>({ok:false,status:401,json:async()=>({})}),FormData:Form,setTimeout,clearTimeout,console,confirm:()=>false});
for(const f of ['app.js','english.js','teacher-writing.js','writing-workflow.js','adaptive-practice.js','course-admin.js'])vm.runInContext(fs.readFileSync(__dirname+'/static/'+f,'utf8'),ctx);
ctx.students=[{id:5,name:'同名 <script>',student_no:'2026005',phone:'13800138000',courses:[{course_id:'writing',ppt_presented:1,ppt_date:'2026-11-10',ppt_topic:'图表 <x>'}],submitted:2},{id:6,name:'同名',student_no:'2026006',phone:'13800138000',courses:[{course_id:'english',ppt_presented:0,ppt_date:'',ppt_topic:''}],submitted:0}];
ctx.requests=[];
vm.runInContext("user={role:'teacher'};api=async(p,m,d)=>{if(!m)return students;requests.push({p,m,d});return {ok:true}};show=async()=>{}",ctx);
(async()=>{
 const deletion={dataset:{deleteStudent:'5'}},ppt={dataset:{pptStudent:'5',pptCourse:'writing'}};
 groups.set('[data-delete-student]',[deletion]);groups.set('[data-ppt-student]',[ppt]);
 let page=await vm.runInContext('views.students()',ctx);
 assert(page.html.includes('2026005')&&!page.html.includes('2026006'));
 assert(page.html.includes('电话重复')&&page.html.includes('已分享')&&page.html.includes('&lt;script&gt;')&&!page.html.includes('<script>'));
 page.bind();deletion.onclick();
 assert(node('#modalBody').innerHTML.includes('归档保留')&&node('#modalBody').innerHTML.includes('重新输入该生学号'));
 values={student_no:'2026005',reason:'重复注册'};
 await node('#delete-student-form').onsubmit({target:{},preventDefault(){}});
 assert(ctx.requests.at(-1).p==='/teacher/students/5'&&ctx.requests.at(-1).m==='DELETE'&&ctx.requests.at(-1).d.student_no==='2026005');
 ppt.onclick();values={presented:'on',date:'2026-11-10',topic:'科研画图'};
 await node('#student-ppt-form').onsubmit({target:{},preventDefault(){}});
 assert(ctx.requests.at(-1).p==='/teacher/students/5/presentation/writing'&&ctx.requests.at(-1).d.presented);
 vm.runInContext("studentCourseFilter=''",ctx);page=await vm.runInContext('views.students()',ctx);assert(page.html.includes('2026006'));
 ctx.detail={name:'学生',status:'本轮意见与建议分已生成',published:false,score:null,feedback:'',assignment:{title:'科研写作'},grading:{weights:[10,20,30,40],total:84},rounds:[{id:11,round_no:4,filename:'终稿.docx',teacher_score:90,teacher_feedback:'已确认',grade_published:1,review:{score:85,summary:'反馈',issues:[],strengths:[],tracking:[],next_actions:[],dimensions:[]}}]};
 vm.runInContext('api=async()=>detail',ctx);await vm.runInContext('openWritingReview(1)',ctx);
 assert(node('#modalBody').innerHTML.includes('第1轮 10%')&&node('#modalBody').innerHTML.includes('教师确认分数')&&node('#modalBody').innerHTML.includes('readonly'));
 vm.runInContext("user={role:'student',phone:'13800138000',courses:['writing']};api=async()=>[{id:'writing',enrolled:true},{id:'english',enrolled:false}]",ctx);
 page=await vm.runInContext('views.portal()',ctx);assert(page.html.includes('邀请码加入'));
 vm.runInContext("openJoinCourse('english')",ctx);assert(node('#modalBody').innerHTML.includes('无须重复注册'));
 console.log('Course-scoped student management, escaped account details, delete confirmation, PPT mark, weighted grade and join-course UI checks passed');
})().catch(e=>{console.error(e);process.exitCode=1});
