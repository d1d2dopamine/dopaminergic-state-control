const getJSON = async p => { const r = await fetch(p); if (!r.ok) throw new Error(`${p}: ${r.status}`); return r.json(); };
const getJSONOptional = async p => { try { const r=await fetch(p); return r.ok ? await r.json() : null; } catch { return null; } };
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const page = document.body.dataset.page;

function fmt(v){
  if(v===null || v===undefined) return '—';
  if(typeof v==='number') return Number.isInteger(v) ? v.toLocaleString() : (Math.abs(v)<0.001 && v!==0 ? v.toExponential(2) : v.toFixed(3).replace(/0+$/,'').replace(/\.$/,''));
  return String(v);
}
function robustnessLabel(f){
  const r=f.robustness;if(!r)return '—';
  const pass=r.passed_thresholds??0,avail=r.available_thresholds??0;
  return avail?`${pass}/${avail}`:'—';
}
function nullLabel(f){
  if(f.kind==='dopamine_input_enrichment')return f.null_model==='roi_overlap'?'ROI overlap':'global';
  return 'exact type';
}
function spatialLabel(f,synapses){
  const s=synapses?.findings?.[f.id]?.spatial;if(!s?.available)return '—';
  const eta=Number(s.source_segregation_eta2||0).toFixed(2),q=s.source_label_permutation_q;
  return q===undefined?`η² ${eta}`:`η² ${eta}; q ${fmt(q)}`;
}
function findingRows(findings,synapses=null){
  return `<table><thead><tr><th>rank</th><th>control</th><th>robust</th><th>null</th><th>method</th><th>candidate</th><th>focus</th><th>spatial</th><th></th></tr></thead><tbody>${findings.map(f=>`<tr data-kind="${esc(f.kind)}" data-status="${esc(f.status||'candidate')}" data-search="${esc((f.title+' '+f.summary+' '+f.focus_node+' '+(f.status||'')).toLowerCase())}"><td>${esc(f.review_rank??f.method_rank??'—')}</td><td>${esc((f.status||'candidate').replaceAll('_',' '))}</td><td>${esc(robustnessLabel(f))}</td><td>${esc(nullLabel(f))}</td><td>${esc(f.kind.replaceAll('_',' '))}</td><td>${esc(f.summary)}</td><td>${esc(f.focus_node)}</td><td>${esc(spatialLabel(f,synapses))}</td><td><a href="network.html?finding=${encodeURIComponent(f.id)}">3d</a></td></tr>`).join('')}</tbody></table>`;
}
async function overview(){
  const [findings, reviewQueue, run, synapses, pam04] = await Promise.all([getJSON('data/findings.json'), getJSONOptional('data/review_queue.json'), getJSON('data/run.json'), getJSONOptional('data/synapses.json'), getJSONOptional('data/experiments/001_pam04.json')]);
  const counts=run.counts||{};
  const s = [
    ['dataset',run.dataset],['dopamine core',counts.dopamine_core_nodes??'—'],['snapshot nodes',counts.snapshot_nodes??'—'],['snapshot edges',counts.snapshot_edges??'—'],['manual investigation queue',counts.review_queue??'—']
  ];
  document.querySelector('#summary').innerHTML=s.map(([k,v])=>`<div><dt>${esc(k)}</dt><dd>${esc(fmt(v))}</dd></div>`).join('');
  const review=Array.isArray(reviewQueue)?reviewQueue:[];
  const displayed=review.length?review.slice(0,12):findings.slice(0,12);
  document.querySelector('#top-table').innerHTML=findingRows(displayed,synapses);
  const m=run.snapshot_meta||{},a=m.anatomical_null||{},roi=a.roi_metadata||{},coverage=roi.after?.output_fraction;
  const exp=document.querySelector('#experiment-note');if(exp)exp.innerHTML=pam04?.available?`PAM04 dossier ready: ${esc(pam04.cell_count)} cells; candidates ${esc((pam04.candidate_ids||[]).join(', ')||'none')}. <a href="state-lab.html">open State Lab</a>`:'PAM04 State Lab is unavailable in this snapshot.';
  document.querySelector('#method-note').textContent=`v0.4.2 ${review.length?'manual investigation queue':'no threshold-surviving manual candidates; showing highest raw leads'}; primary threshold ${run.effective_analysis?.min_synapses??'—'}; ROI metadata ${roi.source??'unknown'}${Number.isFinite(Number(coverage))?` (${(Number(coverage)*100).toFixed(1)}% output coverage)`:''}; anatomical pools ${a.snapshot_targets_with_anatomical_pool??0}/${a.snapshot_nodes??0}; robustness thresholds ${(run.effective_analysis?.robustness_thresholds||[]).join(', ')}.`;
}
async function findingsPage(){
  const [findings,synapses]=await Promise.all([getJSON('data/findings.json'),getJSONOptional('data/synapses.json')]);
  const host=document.querySelector('#findings-table'); host.innerHTML=findingRows(findings,synapses);
  const apply=()=>{const q=document.querySelector('#finding-search').value.toLowerCase();const k=document.querySelector('#finding-kind').value;const s=document.querySelector('#finding-status').value;host.querySelectorAll('tbody tr').forEach(r=>r.style.display=((!q||r.dataset.search.includes(q))&&(!k||r.dataset.kind===k)&&(!s||r.dataset.status===s))?'':'none');};
  document.querySelector('#finding-search').addEventListener('input',apply);document.querySelector('#finding-kind').addEventListener('change',apply);document.querySelector('#finding-status').addEventListener('change',apply);
}
async function networkPage(){
  let [findings,synapses]=await Promise.all([getJSON('data/findings.json'),getJSONOptional('data/synapses.json')]); const select=document.querySelector('#network-finding');
  const params=new URLSearchParams(location.search),focus=Number(params.get('focus'));
  if(Number.isFinite(focus)&&focus>0){findings=[{id:`manual-focus-${focus}`,kind:'manual_focus',title:'Manual neuron focus',summary:`Manual 3D focus on neuron ${focus}.`,interpretation:'Viewer-only focus requested from State Lab; this is not a discovery finding.',score:0,focus_node:focus,related_nodes:[],status:'viewer_only'},...findings];}
  select.innerHTML=findings.map(f=>`<option value="${esc(f.id)}">${esc(f.status||'candidate')} · ${esc(f.kind.replaceAll('_',' '))} · ${esc(f.focus_node)}</option>`).join('');
  const requested=params.get('finding'); if(requested&&findings.some(f=>f.id===requested))select.value=requested;else if(Number.isFinite(focus)&&focus>0)select.value=`manual-focus-${focus}`;
  const render=()=>{const f=findings.find(x=>x.id===select.value)||findings[0];if(!f)return;const u=new URL(location.href);if(f.kind==='manual_focus'){u.searchParams.set('focus',String(f.focus_node));u.searchParams.delete('finding');}else{u.searchParams.set('finding',f.id);u.searchParams.delete('focus');}history.replaceState(null,'',u);document.querySelector('#network-detail').textContent=f.summary+' '+f.interpretation;const rows=[['id',f.id],['control status',f.status],['robust thresholds',robustnessLabel(f)],['null',nullLabel(f)],['score',fmt(f.score)],['focus',f.focus_node],['related shown',(f.related_nodes||[]).length]];if(f.q_value!==undefined)rows.push(['BH q',fmt(f.q_value)]);if(f.enrichment!==undefined)rows.push(['enrichment',fmt(f.enrichment)+'x']);if(f.global_enrichment!==undefined&&f.null_model==='roi_overlap')rows.push(['global-only enrichment',fmt(f.global_enrichment)+'x']);if(f.dominant_partner_share!==undefined)rows.push(['dominant partner share',fmt(f.dominant_partner_share)]);const sp=synapses?.findings?.[f.id]?.spatial;if(sp?.available){rows.push(['synapse sites',fmt(sp.points)],['source spatial eta²',fmt(sp.source_segregation_eta2)],['spatial BH q',fmt(sp.source_label_permutation_q)],['spatial pattern',sp.pattern||'—']);}document.querySelector('#network-kv').innerHTML=rows.map(([k,v])=>`<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('');window.dispatchEvent(new CustomEvent('dsc:finding',{detail:f}));};
  select.addEventListener('change',render); render();
}
async function runsPage(){document.querySelector('#run-manifest').textContent=JSON.stringify(await getJSON('data/run.json'),null,2);}
({overview,findings:findingsPage,network:networkPage,runs:runsPage}[page]||(()=>{}))().catch(err=>{console.error(err);document.body.insertAdjacentHTML('beforeend',`<pre>${esc(err)}</pre>`) });
