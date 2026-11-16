const fs=require('fs'),vm=require('vm'),assert=require('assert');
const nodes=new Map();function $(s){if(!nodes.has(s))nodes.set(s,{hidden:false,required:false,attributes:{},querySelector(){return this.input||(this.input={})},setAttribute(k,v){this.attributes[k]=v}});return nodes.get(s)}
const source=fs.readFileSync('static/app.js','utf8');const start=source.indexOf("let loginRole='student'");const end=source.indexOf("$('#loginForm').onsubmit",start);const ctx=vm.createContext({$,reg:false});vm.runInContext(source.slice(start,end),ctx);
$('#teacherLogin').onclick();assert.equal($('#authTitle').textContent,'教师登录');assert($('#authToggle').hidden);assert.equal($('#teacherLogin').attributes['aria-pressed'],'true');
$('#studentLogin').onclick();$('#authToggle').onclick();assert.equal($('#authTitle').textContent,'创建学生账号');assert.equal($('#loginForm [name=password]').minLength,10);assert($('#inviteLabel').querySelector().required);
$('#teacherLogin').onclick();assert($('#inviteLabel').hidden);assert(!$('#inviteLabel').querySelector().required);assert.equal($('#loginForm [name=password]').minLength,1);
console.log('Student/teacher login switching and registration-only required fields passed');
