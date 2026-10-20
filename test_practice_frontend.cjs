const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const nodes=new Map();function node(s){if(!nodes.has(s))nodes.set(s,{textContent:'',innerHTML:'',hidden:false,style:{},classList:{toggle(){}},addEventListener(){},showModal(){},close(){},querySelectorAll(){return[]}});return nodes.get(s)}
const events={};const ctx=vm.createContext({document:{querySelector:node,querySelectorAll:()=>[],addEventListener(){}},window:{addEventListener:(n,f)=>events[n]=f},fetch:async()=>({ok:false,status:401,json:async()=>({detail:'请登录'})}),setTimeout,clearTimeout,setInterval,clearInterval,performance:{now:()=>1000},console,FormData:class{},confirm:()=>true});
vm.runInContext(fs.readFileSync('static/app.js','utf8'),ctx);
vm.runInContext(fs.readFileSync('static/adaptive-practice.js','utf8'),ctx);
(async()=>{
 await new Promise(r=>setTimeout(r,0));
 vm.runInContext(`user={name:'测试学生',role:'student'};api=async()=>({active:null,records:[],summary:{rounds:0}})`,ctx);
 let v=await vm.runInContext('views.practice()',ctx);
 assert(v.html.includes('每轮30题')&&v.html.includes('每题10秒')&&v.html.includes('首轮随机覆盖八个单元'));
 assert(!v.html.includes('生成 AI')&&!v.html.includes('练习范围')&&!v.html.includes('24题'));
 vm.runInContext(`user={role:'teacher'};api=async()=>[{id:7,name:'<script>坏名字</script>',student_no:'1234',practice:{rounds:2,accuracy:60,latest:{completed:1800000000}}}]`,ctx);
 v=await vm.runInContext('views.practice()',ctx);
 assert(v.html.includes('data-practice-student="7"')&&v.html.includes('仅显示完成全部30题'));
 assert(!v.html.includes('<script>坏名字</script>')&&v.html.includes('&lt;script&gt;'));
 ctx.fixture={correct:1,timeouts:1,focus:['引用'],items:[{correct:false,timed_out:true,stem:'<img onerror="x">',choice:null,options:['正确','错误'],answer:1,explanation:'<script>x</script>',topic_name:'引用',source:'quote'}]};
 const html=vm.runInContext('practiceReviewHtml(fixture)',ctx);
 assert(html.includes('超时')&&html.includes('未作答')&&html.includes('参考资料'));
 assert(!html.includes('<img')&&!html.includes('<script>'));
 vm.runInContext(`page='practice';timedPractice={token:'one'};`,ctx);
 const before=vm.runInContext('timedSequence',ctx);vm.runInContext('practiceStop(false)',ctx);
 assert.equal(vm.runInContext('timedPractice',ctx),null);assert(vm.runInContext('timedSequence',ctx)>before);
 assert.equal(typeof events.pagehide,'function');
 console.log('Timed practice: minimal views, teacher entry, escaping and timer cleanup passed');
})().catch(e=>{console.error(e);process.exitCode=1});
