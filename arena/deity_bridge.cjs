'use strict';
// Trusted browser engine reused offline. No browser ORT, CDN, or network is used.
const fs=require('node:fs'),vm=require('node:vm'),{performance}=require('node:perf_hooks');
let pending=Buffer.alloc(0);
function readLine(){for(;;){const end=pending.indexOf(10);if(end>=0){const line=pending.subarray(0,end).toString('utf8');pending=pending.subarray(end+1);return line}if(pending.length>262144)throw Error('Protocol limit');const chunk=Buffer.alloc(8192),n=fs.readSync(0,chunk,0,chunk.length,null);if(!n)return null;pending=Buffer.concat([pending,chunk.subarray(0,n)])}}
function send(data){fs.writeSync(1,JSON.stringify(data)+'\n')}
const context=vm.createContext({performance,self:{postMessage(){}},importScripts(){throw Error('Network inference disabled')},console:{log(){},warn(){},error(){}}});
vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),context,{filename:'frozen-deity-engine.js'});
context.infer=board=>{send({type:'predict',board:Array.from(board)});const line=readLine();if(line===null)throw Error('Inference disconnected');const value=JSON.parse(line);if(value.error)throw Error('Inference failed');return value};
vm.runInContext('predictRelative=async board=>infer(board)',context);
send({ready:true});
(async()=>{for(;;){const line=readLine();if(line===null)return;const request=JSON.parse(line);context.board=request.board;const result=await vm.runInContext('deitySearch(board,0,DIFFICULTIES.deity)',context);send({type:'move',move:result.move,source:result.source,simulations:result.simulations,vctNodes:result.vctNodes||0})}})().catch(()=>{send({type:'error'});process.exitCode=1});
