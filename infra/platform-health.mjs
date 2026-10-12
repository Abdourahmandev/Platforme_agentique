// Operator CLI: read-only local observations, then the reviewed agent-written classifier.
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {assessHealth} from './health-report.mjs';
try{
  const observations=JSON.parse(execFileSync('python',['-X','utf8',fileURLToPath(new URL('./diagnose-platform.py',import.meta.url)),'--json'],
    {encoding:'utf8',windowsHide:true,timeout:60000,maxBuffer:1024*1024}));
  const report={...assessHealth(observations),observedAt:observations.observedAt,services:observations.services,
    backup:observations.backup,limitations:observations.limitations};
  console.log(JSON.stringify(report,null,2));
  if(report.status!=='ok')process.exitCode=report.status==='degraded'?1:2;
}catch{
  console.log(JSON.stringify({status:'unknown',issues:['Diagnostic local indisponible; aucun succes presume.']}));
  process.exitCode=2;
}
