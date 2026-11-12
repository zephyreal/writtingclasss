const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert');
const nodes=new Map(),groups=new Map();let values={};
function node(s){if(!nodes.has(s))nodes.set(s,{innerHTML:'',textContent:'',value:'',hidden:false,disabled:false,style:{},listeners:{},addEventListener(k,f){this.listeners[k]=f},showModal(){},close(){},scrollIntoView(){}});return nodes.get(s)}
class Form extends Map{constructor(){super(Object.entries(values))}}
const ctx=vm.createContext({window:{addEventListener(){}},document:{querySelector:node,querySelectorAll:s=>groups.get(s)||[],addEventListener(){}},fetch:async()=>({ok:false,status:401,json:async()=>({})}),FormData:Form,setTimeout,clearTimeout,console,confirm:()=>false});
for(const f of ['app.js','english.js','teacher-writing.js','writing-workflow.js','adaptive-practice.js','course-admin.js','writing-studio.js','design-arena.js'])vm.runInContext(fs.readFileSync(__dirname+'/static/'+f,'utf8'),ctx);
ctx.competition={id:1,title:'班级赛 <script>',instructions:'测试 <x>',mode:'practice',state:'open',published:true,deadline:'',baseline_hash:'a'.repeat(64),config:{pairs:20,simulations:16,move_ms:2000,job_seconds:1800,daily_limit:2}};
ctx.data={competition:ctx.competition,entries:[],worker:{online:false,message:'评测机未连接'}};
vm.runInContext("user={id:3,role:'student'};api=async p=>p==='/arena/competitions'?{competitions:[competition]}:p.endsWith('entries')?data:{sealed:false,rows:[]}",ctx);
(async()=>{
 let view=await vm.runInContext('views.arena()',ctx);
 assert(view.html.includes('20MB')&&view.html.includes('5MB')&&view.html.includes('只运行ONNX'));
 assert(view.html.includes('评测机未就绪')&&view.html.includes('尚无完成全部评测'));
 assert(view.html.includes('&lt;script&gt;')&&!view.html.includes('<script>'));
 assert(!view.html.includes('配置独立评测机'));
 view.bind();ctx.calls=[];vm.runInContext('api=async(p,m,d)=>{calls.push({p,m,d});return {ok:true}};show=async()=>{}',ctx);
 values={model:{name:'m.onnx',size:20_000_001},alias:'test'};
 await node('#arena-submit').listeners.submit({target:{},preventDefault(){}});assert(ctx.calls.length===0&&node('#toast').textContent.includes('20MB'));
 values={model:{name:'m.ONNX',size:100},alias:'test'};
 await node('#arena-submit').listeners.submit({target:{},preventDefault(){}});assert(ctx.calls[0].p==='/arena/competitions/1/entries'&&ctx.calls[0].d.get('share_replay')==='false');
 ctx.replay={games:[{student_color:1,winner:1,opening_length:2,moves:[112,113,114],fault:''}]};vm.runInContext('api=async()=>replay',ctx);
 await vm.runInContext('arenaReplay(5)',ctx);assert(node('#arena-replay-board').innerHTML.match(/arena-cell/g).length===225);
 node('#arena-step-next').onclick();assert(node('#arena-replay-board').innerHTML.includes('black last'));
 let resolve;ctx.waiting=new Promise(r=>resolve=r);vm.runInContext('api=async()=>waiting',ctx);node('#modalBody').innerHTML='unchanged';const wait=vm.runInContext('arenaReplay(5)',ctx);vm.runInContext("user={id:4,role:'student'}",ctx);resolve(ctx.replay);await wait;assert(node('#modalBody').innerHTML==='unchanged');
 vm.runInContext("user={id:1,role:'teacher'};api=async p=>p==='/arena/competitions'?{competitions:[competition]}:p.endsWith('entries')?data:{sealed:true,rows:[]}",ctx);
 view=await vm.runInContext('views.arena()',ctx);assert(view.html.includes('配置独立评测机')&&view.html.includes('成绩尚未开放'));
 vm.runInContext('arenaCreate()',ctx);assert(node('#modalBody').innerHTML.includes('发布后冻结')&&node('#modalBody').innerHTML.includes('结课赛'));
 console.log('Model arena: upload bounds, safe rendering, worker readiness, private roles, replay stepping and late-response privacy passed');
})().catch(e=>{console.error(e);process.exitCode=1});
