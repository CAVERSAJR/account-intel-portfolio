import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {pathToFileURL,fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'account-intelligence-verify-'));
try {
 const source=fs.readFileSync(path.join(root,'workspace/domain.ts'),'utf8');
 assert(source.includes("from './types';"));
 fs.writeFileSync(path.join(temp,'domain.ts'),source.replace("from './types';","from './types.ts';"));
 fs.copyFileSync(path.join(root,'workspace/types.ts'),path.join(temp,'types.ts'));
 fs.writeFileSync(path.join(temp,'package.json'),JSON.stringify({type:'module'}));
 const domain=await import(pathToFileURL(path.join(temp,'domain.ts')).href);
 const dataset=JSON.parse(fs.readFileSync(path.join(root,'workspace/data.json'),'utf8'));
 const evidence=JSON.parse(fs.readFileSync(path.join(root,'docs/BUILD_EVIDENCE.json'),'utf8'));
 const response=evidence.live_run.response;
 const state=domain.createInitialState(dataset);
 const account=domain.rankAccounts(dataset,state).find(x=>x.id==='advent_international');
 const plan=domain.validateModelPlan(response,account,dataset,state);
 assert.equal(plan.generatedBy,'deepseek');
 assert(plan.fields.every(x=>x.buyerConfirmed===false));
 assert.throws(()=>domain.validateModelPlan({...response,account_id:'hggc'},account,dataset,state));
 const changed=domain.setSourceActive(state,'advent_international-event',false,dataset);
 const reranked=domain.rankAccounts(dataset,changed).find(x=>x.id===account.id);
 assert.equal(reranked.priority,'P2');
 assert.throws(()=>domain.validateModelPlan(response,reranked,dataset,changed));
 console.log(JSON.stringify({passed:3,live_response_accepted:true,wrong_account_rejected:true,removed_source_rejected:true,fields:plan.fields.length,buyer_confirmation:false}));
} finally {fs.rmSync(temp,{recursive:true,force:true});}
