const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert');
const nodes=new Map(),groups=new Map();let values={};
function node(s){if(!nodes.has(s))nodes.set(s,{textContent:'',innerHTML:'',hidden:false,value:'',style:{},listeners:{},addEventListener(k,f){this.listeners[k]=f},showModal(){},close(){}});return nodes.get(s)}
class Form extends Map{constructor(){super(Object.entries(values))}getAll(k){return [].concat(this.get(k)||[])}}
const ctx=vm.createContext({window:{addEventListener(){}},document:{querySelector:node,querySelectorAll:s=>groups.get(s)||[],addEventListener(){}},fetch:async()=>({ok:false,status:401,json:async()=>({})}),FormData:Form,setTimeout,clearTimeout,console,confirm:()=>false});
for(const f of ['app.js','english.js','teacher-writing.js','writing-workflow.js','adaptive-practice.js','course-admin.js'])vm.runInContext(fs.readFileSync(__dirname+'/static/'+f,'utf8'),ctx);
ctx.students=[{id:5,name:'同名 <script>',student_no:'2026005',phone:'13800138000',courses:[{course_id:'writing',ppt_presented:1,ppt_date:'2026-11-10',ppt_topic:'图表 <x>'}],submitted:2},{id:6,name:'同名',student_no:'2026006',phone:'13800138000',courses:[{course_id:'english',ppt_presented:0,ppt_date:'',ppt_topic:''}],submitted:0}];
ctx.requests=[];
vm.runInContext("user={role:'teacher'};api=async(p,m,d)=>{if(!m)return students;requests.push({p,m,d});return {ok:true}};show=async()=>{}",ctx);

vm.runInContext(fs.readFileSync(__dirname+'/static/course-messages.js','utf8'),ctx);
(async()=>{
 for(const cid of ['writing','english','equipment','design']){
  vm.runInContext(`activeCourse='${cid}';user={role:'teacher'};renderNavigation()`,ctx);
  assert(node('#nav').innerHTML.includes('学生管理'));
  assert.equal((node('#nav').innerHTML.match(/data-page="students"/g)||[]).length,1);
  assert(node('#nav').innerHTML.includes('学生留言'));
  vm.runInContext(`user={role:'student'};renderNavigation()`,ctx);
  assert(!node('#nav').innerHTML.includes('学生管理'));assert(node('#nav').innerHTML.includes('学生留言'));
 }
 vm.runInContext("activeCourse='writing';user={role:'teacher'};api=async(p,m,d)=>{if(!m)return students;requests.push({p,m,d});return {students:1,added:1}}",ctx);
 let v=await vm.runInContext('views.students()',ctx);
 assert(v.html.includes('<th>序号</th>')&&v.html.includes('data-student-number>1'));
 assert(v.html.includes('批量授予课程权限'));
 const row={hidden:false,dataset:{studentSearch:'示例 2026005'}};
 const box={checked:false,dataset:{studentSelect:'5'},closest:()=>row};
 const number={textContent:1};row.querySelector=s=>s==='[data-student-select]'?box:number;
 groups.set('[data-student-select]',[box]);groups.set('[data-student-search]',[row]);
 v.bind();node('#student-select-all').onchange({target:{checked:true}});
 assert(box.checked);assert(!node('#student-batch-grant').disabled);
 node('#student-batch-grant').onclick();assert(node('#modalBody').innerHTML.includes('保留已有课程权限'));
 values={courses:['english']};await node('#batch-course-form').onsubmit({target:{},preventDefault(){}});
 assert.equal(ctx.requests.at(-1).p,'/teacher/students/batch-courses');
 assert.deepEqual([...ctx.requests.at(-1).d.student_ids],[5]);assert.deepEqual([...ctx.requests.at(-1).d.courses],['english']);
 node('#student-search').oninput({target:{value:'no-match'}});assert(row.hidden&&!box.checked);assert(node('#student-batch-grant').disabled);
 for(const cid of ['english','equipment','design']){
  vm.runInContext(`activeCourse='${cid}'`,ctx);v=await vm.runInContext('views.students()',ctx);
  assert(!v.html.includes('data-profile=')&&!v.html.includes('data-student-practice='));
 }
 ctx.payload={items:[{id:1,author:'<img src=x>',body:'<script>alert(1)</script>',created:'2026-11-21',teacher:false,can_delete:true,replies:0}],next:null};
 vm.runInContext("activeCourse='design';api=async()=>payload",ctx);v=await vm.runInContext('views.messages()',ctx);
 assert(v.html.includes('&lt;script&gt;')&&!v.html.includes('<script>'));assert(v.html.includes('&lt;img src=x&gt;'));assert(v.html.includes('发布留言'));
 console.log('All-course navigation, roster numbers, safe batch selection and escaped message board passed');
})().catch(e=>{console.error(e);process.exitCode=1});
