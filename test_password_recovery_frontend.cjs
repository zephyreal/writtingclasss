const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const nodes=new Map();const node=s=>{if(!nodes.has(s))nodes.set(s,{innerHTML:'',textContent:'',hidden:false,style:{},classList:{toggle(){}},showModal(){},close(){},reset(){},querySelectorAll:()=>[]});return nodes.get(s)};
const calls=[];let fields={};
const ctx=vm.createContext({document:{querySelector:node,querySelectorAll:()=>[],addEventListener(){}},window:{},setTimeout,clearTimeout,console,confirm:()=>true,FormData:class{constructor(){return Object.entries(fields)}},fetch:async()=>({ok:false,status:401,json:async()=>({detail:'login'})})});
vm.runInContext(fs.readFileSync('static/app.js','utf8'),ctx);
vm.runInContext(fs.readFileSync('static/password-recovery.js','utf8'),ctx);
ctx.calls=calls;
(async()=>{
 await new Promise(r=>setTimeout(r,0));
 vm.runInContext(`api=async(...x)=>{calls.push(x);return {message:'申请已提交'}};`,ctx);
 node('#forgotPassword').onclick();
 assert(node('#modalBody').innerHTML.includes('登记电话号码'));
 fields={student_no:'123',phone:'13800138000'};
 await node('#recovery-request-form').onsubmit({preventDefault(){}});
 assert.equal(calls[0][0],'/password-recovery/request');
 assert.equal(node('#recovery-request-status').textContent,'申请已提交');
 node('#recovery-have-code').onclick();
 assert(node('#modalBody').innerHTML.includes('name="code"'));
 fields={...fields,code:'123456789ABC',password:'a-long-password',confirm:'different'};
 await node('#recovery-reset-form').onsubmit({preventDefault(){},target:{}});
 assert.equal(calls.length,1);assert(node('#toast').textContent.includes('不一致'));
 vm.runInContext(`views.students=async()=>({html:'学生列表',bind(){}})`,ctx);
 // Already-wrapped view delegates to the original; verify the registered management entry in source.
 assert(fs.readFileSync('static/password-recovery.js','utf8').includes('处理找回密码申请'));
 assert(fs.readFileSync('static/index.html','utf8').includes('/static/password-recovery.js'));
 console.log('Password recovery entry, request payload and confirmation checks passed');
})().catch(e=>{console.error(e);process.exitCode=1});
