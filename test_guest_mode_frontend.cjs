const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const nodes=new Map();function node(s){if(!nodes.has(s))nodes.set(s,{innerHTML:'',textContent:'',value:'',hidden:false,style:{},classList:{toggle(){}},setAttribute(){},querySelector(){return {required:false}},querySelectorAll(){return []},addEventListener(){},close(){},showModal(){}});return nodes.get(s)}
const ctx=vm.createContext({console,document:{querySelector:node,querySelectorAll:()=>[],addEventListener(){}},window:{addEventListener(){}},history:{replaceState(){}},location:{hash:'#design'},fetch:async()=>{throw Error('Guest must not fetch private data')},FormData:class{},setTimeout,clearTimeout,setInterval,clearInterval});
for(const f of ['app.js','english.js','teacher-writing.js','writing-workflow.js','adaptive-practice.js','course-admin.js','writing-studio.js','design-arena.js','course-messages.js','password-recovery.js','guest-mode.js'])vm.runInContext(fs.readFileSync('static/'+f,'utf8'),ctx);
(async()=>{
 node('#guestEnter').onclick();
 assert(vm.runInContext('guestMode',ctx));assert.equal(vm.runInContext('user',ctx),undefined);
 assert.equal(node('#workspace').hidden,false);assert(node('#content').innerHTML.includes('游客浏览'));
 for(const cid of ['writing','english','equipment','design']){
  await vm.runInContext(`selectCourse('${cid}')`,ctx);
  const pages=vm.runInContext(`GUEST_PAGES['${cid}'].map(x=>x[0])`,ctx);
  for(const id of pages){
   await vm.runInContext(`show('${id}')`,ctx);
   const html=node('#content').innerHTML;
   assert(html.includes('data-guest-login'),id);
   assert(!/<iframe|type="file"|href="\/api/.test(html),id);
   assert(!node('#nav').innerHTML.includes('学生管理'));
  }
 }
 await vm.runInContext(`show('vehicle')`,ctx);
 assert(node('#content').innerHTML.includes('无人车竞赛'));
 // Late-loaded vehicle extension must route through the preview, never its iframe view.
 vm.runInContext(`views.vehicle=async()=>{throw Error('private vehicle view called')}`,ctx);
 await vm.runInContext(`show('vehicle')`,ctx);
 assert(node('#content').innerHTML.includes('非实时仿真'));
 await vm.runInContext(`selectCourse('writing','messages')`,ctx);
 assert(node('#content').innerHTML.includes('虚构留言示例'));
 vm.runInContext('guestLogin()',ctx);
 assert(!vm.runInContext('guestMode',ctx));assert.equal(node('#auth').hidden,false);assert.equal(node('#workspace').hidden,true);
 assert.equal(node('#passwordBtn').hidden,false);
 // Once authenticated, original private views are used again.
 vm.runInContext(`user={role:'student',name:'测试',student_no:'123',secure:true,courses:['writing']};views.practice=async()=>({html:'PRIVATE PRACTICE'})`,ctx);
 await vm.runInContext(`selectCourse('writing','practice')`,ctx);
 assert.equal(node('#content').innerHTML,'PRIVATE PRACTICE');
 // Teacher navigation is preserved and cannot enter guest mode while logged in.
 vm.runInContext(`user={role:'teacher'};renderNavigation()`,ctx);
 assert(node('#nav').innerHTML.includes('学生管理'));
 node('#guestEnter').onclick();assert(!vm.runInContext('guestMode',ctx));
 console.log('Guest previews: all course pages, no private fetches/iframes, login transition and authenticated views passed');
})().catch(e=>{console.error(e);process.exitCode=1});
