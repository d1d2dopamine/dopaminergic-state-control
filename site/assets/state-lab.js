(()=>{
const root=document.getElementById('lab-app'); if(!root)return;
const $=id=>document.getElementById(id);
const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
const sigmoid=x=>1/(1+Math.exp(-x));
const median=a=>{const b=[...a].sort((x,y)=>x-y);const n=b.length;return n? (n%2?b[(n-1)/2]:(b[n/2-1]+b[n/2])/2):0;};
const fmt=(v,d=3)=>Number.isFinite(Number(v))?Number(v).toFixed(d).replace(/0+$/,'').replace(/\.$/,''):'—';
let data=null,runMeta=null,committedRuns=[],baseline=null,current=null,frame=0,playing=false,timer=null;

function params(){
  return {
    mode:$('lab-mode').value,
    candidate:$('lab-candidate').value,
    candidate_gain:Number($('lab-gain').value),
    stimulus:$('lab-stimulus').value,
    stimulus_strength:Number($('lab-stimulus-strength').value),
    pulse_start_ms:Number($('lab-pulse-start').value),
    pulse_duration_ms:Number($('lab-pulse-duration').value),
    dopamine_tone:Number($('lab-tone').value),
    dat_clearance:Number($('lab-dat').value),
    receptor_gains:{Dop1R1:Number($('lab-dop1r1').value),Dop1R2:Number($('lab-dop1r2').value),Dop2R:Number($('lab-dop2r').value)}
  };
}
function selectedIds(p){return p.candidate==='pair'?data.candidate_ids.slice(0,2).map(Number):[Number(p.candidate)];}
function copyMatrix(channels){return channels.map(ch=>ch.weights.map(Number));}
function seededShuffle(values,seed){const a=[...values];let s=(seed>>>0)||1;for(let i=a.length-1;i>0;i--){s=(1664525*s+1013904223)>>>0;const j=s%(i+1);[a[i],a[j]]=[a[j],a[i]];}return a;}
function interventionMatrix(p){
  const matrix=copyMatrix(data.input_channels); if(p.mode==='real')return {matrix,off:new Set()};
  const ids=selectedIds(p),off=new Set(); const bodyIndex=new Map(data.cells.map((c,i)=>[Number(c.body_id),i]));
  const medByChannel=matrix.map(row=>median(row));
  for(const id of ids){const ci=bodyIndex.get(id);if(ci===undefined)continue;
    if(p.mode==='knockout'){off.add(ci);continue;}
    if(p.mode==='medianize'){
      const total=matrix.reduce((s,row)=>s+row[ci],0), medTotal=medByChannel.reduce((s,v)=>s+v,0)||1;
      matrix.forEach((row,ri)=>row[ci]=medByChannel[ri]/medTotal*total);
    }else if(p.mode==='amplify'){
      let best=0;for(let ri=1;ri<matrix.length;ri++)if(matrix[ri][ci]>matrix[best][ci])best=ri;
      matrix[best][ci]*=p.candidate_gain;
    }else if(p.mode==='shuffle'){
      const values=matrix.map(row=>row[ci]);const shuffled=seededShuffle(values,id);matrix.forEach((row,ri)=>row[ci]=shuffled[ri]);
    }
  }
  return {matrix,off};
}
function simulate(p,forceReal=false){
  const model=data.model; const dt=Number(model.dt_ms||20),duration=Number(model.duration_ms||3000),steps=Math.floor(duration/dt)+1;
  const mode=forceReal?'real':p.mode; const effective={...p,mode}; const mod=interventionMatrix(effective); const W=mod.matrix;
  const outW=copyMatrix(data.output_channels),n=data.cells.length;
  const inputTotals=Array.from({length:n},(_,i)=>W.reduce((s,row)=>s+row[i],0));
  const outputTotals=Array.from({length:n},(_,i)=>outW.reduce((s,row)=>s+row[i],0));
  const medIn=median(inputTotals.filter(x=>x>0))||1,medOut=median(outputTotals.filter(x=>x>0))||1;
  const stimIndex=Math.max(0,data.input_channels.findIndex(ch=>ch.name===p.stimulus));
  const a=new Array(n).fill(0),traces={time:[],dopamine:[],Dop1R1:[],Dop1R2:[],Dop2R:[],coupling:[],cells:[],outputs:[]}; let dopamine=0;
  const slope=Number(model.activation_slope||8),threshold=Number(model.activation_threshold||.34),tau=Number(model.cell_tau_ms||120),tauD=Number(model.dopamine_tau_ms||380),base=Number(model.baseline_input||.08);
  const rec=model.receptors||{};
  for(let step=0;step<steps;step++){
    const t=step*dt, pulse=t>=p.pulse_start_ms&&t<(p.pulse_start_ms+p.pulse_duration_ms);
    for(let i=0;i<n;i++){
      const total=inputTotals[i]||1,share=W[stimIndex]?.[i]/total||0,capacity=clamp(Math.sqrt(total/medIn),.45,1.8);
      const drive=base+capacity*share*(pulse?p.stimulus_strength:0);
      const target=mod.off.has(i)?0:sigmoid(slope*(drive-threshold));
      a[i]+=clamp(dt/tau,0,1)*(target-a[i]);
    }
    const release=a.reduce((s,v,i)=>s+v*clamp(Math.sqrt((outputTotals[i]||1)/medOut),.45,1.8),0)/Math.max(1,n);
    dopamine+=clamp(dt/tauD,0,1)*((p.dopamine_tone+release)-p.dat_clearance*dopamine);dopamine=Math.max(0,dopamine);
    const receptor={};for(const name of ['Dop1R1','Dop1R2','Dop2R']){const r=rec[name]||{},half=Number(r.half_activation||.4),gain=Number(p.receptor_gains[name]??r.gain??1);receptor[name]=gain*dopamine/(half+dopamine+1e-9);}
    const coupling=['Dop1R1','Dop1R2','Dop2R'].reduce((sum,name)=>sum+receptor[name]*Number(rec[name]?.coupling_prior||0),0);
    const outputs=outW.map(row=>{let num=0,den=0;for(let i=0;i<n;i++){num+=a[i]*row[i];den+=row[i];}return den?num/den:0;});
    traces.time.push(t);traces.dopamine.push(dopamine);traces.Dop1R1.push(receptor.Dop1R1);traces.Dop1R2.push(receptor.Dop1R2);traces.Dop2R.push(receptor.Dop2R);traces.coupling.push(coupling);traces.cells.push([...a]);traces.outputs.push(outputs);
  }
  traces.params=effective; return traces;
}
function peak(arr){return arr.length?Math.max(...arr):0;}
function run(){const p=params();baseline=simulate(p,true);current=simulate(p,false);frame=0;$('lab-time').value='0';renderAll();}
function setLabels(){
  $('lab-gain-value').textContent=`${Number($('lab-gain').value).toFixed(1)}×`;
  $('lab-stimulus-value').textContent=Number($('lab-stimulus-strength').value).toFixed(2);
  $('lab-pulse-start-value').textContent=`${$('lab-pulse-start').value} ms`;$('lab-pulse-duration-value').textContent=`${$('lab-pulse-duration').value} ms`;
  $('lab-tone-value').textContent=Number($('lab-tone').value).toFixed(2);$('lab-dat-value').textContent=`${Number($('lab-dat').value).toFixed(2)}×`;
  for(const id of ['dop1r1','dop1r2','dop2r'])$(`lab-${id}-value`).textContent=`${Number($(`lab-${id}`).value).toFixed(2)}×`;
}
function summary(){
  const p=params(),ids=selectedIds(p);const maxDA=peak(current.dopamine),baseDA=peak(baseline.dopamine),delta=maxDA-baseDA;
  const cells=ids.map(id=>data.cells.findIndex(c=>Number(c.body_id)===id)).filter(i=>i>=0);const maxA=cells.length?Math.max(...cells.map(i=>Math.max(...current.cells.map(row=>row[i])))):0;
  $('lab-summary').innerHTML=`<div><dt>scenario</dt><dd>${p.mode}</dd></div><div><dt>candidate</dt><dd>${p.candidate}</dd></div><div><dt>peak DA</dt><dd>${fmt(maxDA)}</dd></div><div><dt>Δ peak DA</dt><dd>${delta>=0?'+':''}${fmt(delta)}</dd></div><div><dt>candidate peak</dt><dd>${fmt(maxA)}</dd></div>`;
}
function renderCells(){
  const cur=current.cells[frame],base=baseline.cells[frame],cand=new Set(selectedIds(params()));
  $('lab-cell-grid').innerHTML=data.cells.map((c,i)=>`<div class="cell-row ${cand.has(Number(c.body_id))?'candidate':''}"><a href="network.html?focus=${c.body_id}" title="open in 3D">${c.body_id}</a><span class="cell-side">${c.side||'—'}</span><div class="cell-bar"><i style="width:${clamp(base[i]*100,0,100)}%"></i><b style="width:${clamp(cur[i]*100,0,100)}%"></b></div><span>${fmt(cur[i],2)}</span></div>`).join('');
}
function drawTrace(){
  const canvas=$('lab-trace-canvas'),ctx=canvas.getContext('2d'),d=Math.min(devicePixelRatio||1,1.5),w=Math.max(400,Math.floor(canvas.clientWidth*d)),h=Math.floor(330*d);if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}ctx.clearRect(0,0,w,h);ctx.fillStyle='#0d0d0d';ctx.fillRect(0,0,w,h);
  const pad=34*d,ww=w-pad*2,hh=h-pad*1.6,maxY=Math.max(1.2,...current.Dop1R1,...current.Dop1R2,...current.Dop2R,...current.coupling.map(Math.abs));ctx.strokeStyle='#303030';ctx.lineWidth=1;for(let k=0;k<=4;k++){const y=pad+hh*k/4;ctx.beginPath();ctx.moveTo(pad,y);ctx.lineTo(pad+ww,y);ctx.stroke();}
  const series=[['dopamine',1],['Dop1R1',.88],['Dop1R2',.72],['Dop2R',.56],['coupling',.98]];
  function line(arr,alpha,dash){ctx.globalAlpha=alpha;ctx.strokeStyle='#f0f0f0';ctx.lineWidth=(dash?1:1.5)*d;ctx.setLineDash(dash?[5*d,5*d]:[]);ctx.beginPath();arr.forEach((v,i)=>{const x=pad+ww*i/(arr.length-1),y=pad+hh*(1-(v+0.15)/(maxY+0.3));i?ctx.lineTo(x,y):ctx.moveTo(x,y);});ctx.stroke();}
  for(const [name,alpha] of series){line(baseline[name],alpha*.35,true);line(current[name],alpha,false);}ctx.setLineDash([]);ctx.globalAlpha=1;
  const x=pad+ww*frame/(current.time.length-1);ctx.strokeStyle='#888';ctx.lineWidth=1*d;ctx.beginPath();ctx.moveTo(x,pad);ctx.lineTo(x,pad+hh);ctx.stroke();
  ctx.fillStyle='#888';ctx.font=`${10*d}px monospace`;ctx.fillText('normalized',4*d,12*d);ctx.fillText(`${current.time.at(-1)} ms`,w-72*d,h-7*d);
}
function renderDossier(){
  const p=params(),id=selectedIds(p)[0],c=data.cells.find(x=>Number(x.body_id)===id)||data.cells[0];if(!c)return;
  const m=c.metrics||{},rob=c.robustness;let html=`<dl class="kv lab-kv"><dt>body</dt><dd>${c.body_id} (${c.side})</dd><dt>max input share</dt><dd>${fmt(m.max_input_share)} · z ${fmt(m.max_input_share_z)}</dd><dt>input strength</dt><dd>${fmt(m.in_strength,0)}</dd><dt>input partners</dt><dd>${fmt(m.in_partner_count,0)}</dd><dt>discovery</dt><dd>${c.candidate_status||'not in review queue'}</dd><dt>thresholds</dt><dd>${rob?`${rob.passed_thresholds}/${rob.available_thresholds}`:'—'}</dd></dl>`;
  html+=`<div class="lab-subhead">strongest inputs</div><table class="compact"><thead><tr><th>type</th><th>body</th><th>w</th><th>share</th></tr></thead><tbody>${c.top_inputs.slice(0,8).map(x=>`<tr><td>${x.type}</td><td>${x.body_id}</td><td>${x.weight}</td><td>${(x.share*100).toFixed(1)}%</td></tr>`).join('')}</tbody></table>`;
  html+=`<div class="lab-subhead">strongest outputs</div><table class="compact"><thead><tr><th>type</th><th>body</th><th>w</th><th>share</th></tr></thead><tbody>${c.top_outputs.slice(0,8).map(x=>`<tr><td>${x.type}</td><td>${x.body_id}</td><td>${x.weight}</td><td>${(x.share*100).toFixed(1)}%</td></tr>`).join('')}</tbody></table>`;
  html+=`<p><a href="network.html?focus=${c.body_id}">open ${c.body_id} in 3D</a></p>`;$('lab-candidate-dossier').innerHTML=html;
}
function renderOutputs(){
  const cur=current.outputs[frame],base=baseline.outputs[frame];const rows=data.output_channels.map((ch,i)=>({name:ch.name,cur:cur[i],base:base[i],delta:cur[i]-base[i]})).sort((a,b)=>b.cur-a.cur).slice(0,10);
  $('lab-output-table').innerHTML=`<table class="compact"><thead><tr><th>target type</th><th>real</th><th>current</th><th>Δ</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${r.name}</td><td>${fmt(r.base,2)}</td><td>${fmt(r.cur,2)}</td><td>${r.delta>=0?'+':''}${fmt(r.delta,2)}</td></tr>`).join('')}</tbody></table>`;
}
function renderDistribution(){
  const max=Math.max(...data.distribution.cells.map(x=>x.value),.001),cands=new Set(data.candidate_ids.map(Number));$('lab-distribution').innerHTML=data.distribution.cells.map(x=>`<div class="dist-row ${cands.has(Number(x.body_id))?'candidate':''}"><span>${x.body_id}</span><span>${x.side}</span><div><i style="width:${x.value/max*100}%"></i></div><span>${(x.value*100).toFixed(1)}%</span><span>z ${fmt(x.robust_z,2)}</span></div>`).join('');
}
function renderFrame(){if(!current||!baseline)return;const t=current.time[frame];$('lab-time-value').textContent=`${t} ms`;$('lab-time').value=String(Math.round(frame/(current.time.length-1)*100));renderCells();renderOutputs();drawTrace();const r={Dop1R1:current.Dop1R1[frame],Dop1R2:current.Dop1R2[frame],Dop2R:current.Dop2R[frame]},da=current.dopamine[frame],ci=current.coupling[frame];$('lab-cell-note').textContent=`DA ${fmt(da)} · Dop1R1 ${fmt(r.Dop1R1)} · Dop1R2 ${fmt(r.Dop1R2)} · Dop2R ${fmt(r.Dop2R)} · assumed coupling ${fmt(ci)}`;}
function renderAll(){setLabels();summary();renderDossier();renderDistribution();renderFrame();}
function stop(){playing=false;if(timer){clearInterval(timer);timer=null;}$('lab-play').textContent='play';}
function play(){if(!current)run();if(playing){stop();return;}playing=true;$('lab-play').textContent='pause';timer=setInterval(()=>{frame++;if(frame>=current.time.length){frame=current.time.length-1;stop();}renderFrame();},40);}
function reset(){stop();frame=0;$('lab-time').value='0';renderFrame();}
function copyState(){const p=params(),u=new URL(location.href);Object.entries({mode:p.mode,candidate:p.candidate,input:p.stimulus,strength:p.stimulus_strength,start:p.pulse_start_ms,duration:p.pulse_duration_ms,tone:p.dopamine_tone,dat:p.dat_clearance,r1:p.receptor_gains.Dop1R1,r2:p.receptor_gains.Dop1R2,d2:p.receptor_gains.Dop2R,gain:p.candidate_gain}).forEach(([k,v])=>u.searchParams.set(k,String(v)));navigator.clipboard?.writeText(u.toString());$('lab-copy-url').textContent='copied';setTimeout(()=>$('lab-copy-url').textContent='copy state URL',1000);}
function exportRun(){const p=params(),payload={experiment:data.experiment_id,dataset:data.dataset,exported_at:new Date().toISOString(),source_run:runMeta?{commit:runMeta.git_sha||runMeta.git?.commit||runMeta.git_commit||null,dataset:runMeta.dataset||null,counts:runMeta.counts||null,effective_analysis:runMeta.effective_analysis||null}:null,parameters:p,model:data.model,assumptions:data.assumptions,summary:{baseline_peak_dopamine:peak(baseline.dopamine),intervention_peak_dopamine:peak(current.dopamine),delta_peak_dopamine:peak(current.dopamine)-peak(baseline.dopamine)}};const blob=new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=`pam04-${p.mode}-${Date.now()}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),500);}

function renderCommittedRuns(){
  const host=$('lab-committed-runs');if(!host)return;if(!committedRuns.length){host.textContent='No committed State Lab scenarios were reproduced in this build.';return;}
  host.innerHTML=`<table class="compact"><thead><tr><th>run</th><th>mode</th><th>candidate</th><th>stimulus</th><th>Δ peak DA</th></tr></thead><tbody>${committedRuns.map(r=>`<tr><td>${r.name}</td><td>${r.parameters?.mode||'—'}</td><td>${r.parameters?.candidate||'—'}</td><td>${r.parameters?.stimulus||'—'}</td><td>${fmt(r.summary?.delta_peak_dopamine||0,4)}</td></tr>`).join('')}</tbody></table>`;
}
function loadURL(){const q=new URLSearchParams(location.search),set=(id,key)=>{if(q.has(key))$(id).value=q.get(key);};set('lab-mode','mode');set('lab-candidate','candidate');set('lab-stimulus','input');set('lab-stimulus-strength','strength');set('lab-pulse-start','start');set('lab-pulse-duration','duration');set('lab-tone','tone');set('lab-dat','dat');set('lab-dop1r1','r1');set('lab-dop1r2','r2');set('lab-dop2r','d2');set('lab-gain','gain');}
async function init(){
  const [r,runResponse,runsResponse]=await Promise.all([fetch('data/experiments/001_pam04.json'),fetch('data/run.json').catch(()=>null),fetch('data/experiments/runs/index.json').catch(()=>null)]);if(!r.ok)throw new Error(`experiment data: ${r.status}`);data=await r.json();if(runResponse?.ok)runMeta=await runResponse.json();if(runsResponse?.ok)committedRuns=await runsResponse.json();if(!data.available){$('lab-unavailable').hidden=false;$('lab-unavailable').textContent=data.reason||'PAM04 experiment unavailable in this snapshot.';return;}root.hidden=false;
  const candidates=data.candidate_ids.length?data.candidate_ids:data.cells.slice(0,2).map(c=>c.body_id);$('lab-candidate').innerHTML=candidates.map(id=>`<option value="${id}">${id}</option>`).join('')+(candidates.length>1?'<option value="pair">bilateral candidate pair</option>':'');
  $('lab-stimulus').innerHTML=data.input_channels.filter(ch=>ch.name!=='other').map(ch=>`<option value="${ch.name}">${ch.name} · w=${Math.round(ch.total_weight)}</option>`).join('');
  const first=data.cells.find(c=>Number(c.body_id)===Number(candidates[0]));if(first?.top_inputs?.length){const preferred=first.top_inputs[0].type;if(data.input_channels.some(ch=>ch.name===preferred))$('lab-stimulus').value=preferred;}
  $('lab-assumptions').innerHTML=data.assumptions.map(x=>`<li>${x}</li>`).join('');renderCommittedRuns();loadURL();
  document.querySelectorAll('.lab-controls input,.lab-controls select').forEach(el=>el.addEventListener('input',()=>{setLabels();if(el.id==='lab-candidate'){if(el.value!=='pair'){const cell=data.cells.find(c=>String(c.body_id)===el.value),preferred=cell?.top_inputs?.[0]?.type;if(preferred&&data.input_channels.some(ch=>ch.name===preferred))$('lab-stimulus').value=preferred;}renderDossier();}}));
  $('lab-run').onclick=()=>{stop();run();};$('lab-play').onclick=play;$('lab-reset').onclick=reset;$('lab-copy-url').onclick=copyState;$('lab-export').onclick=exportRun;$('lab-time').oninput=()=>{stop();frame=Math.round(Number($('lab-time').value)/100*(current.time.length-1));renderFrame();};
  window.addEventListener('resize',()=>drawTrace());run();
}
init().catch(err=>{$('lab-unavailable').hidden=false;$('lab-unavailable').textContent=`State Lab failed: ${err.message}`;console.error(err);});
})();
