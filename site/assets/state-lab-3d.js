(()=>{
'use strict';
const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
const lerp=(a,b,t)=>a+(b-a)*t;
const vdist=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1],a[2]-b[2]);

function createStateLab3D(canvas, data, options={}){
  const statusEl=options.statusEl||null;
  const gl=canvas?.getContext('webgl2',{antialias:false,alpha:false,powerPreference:'high-performance'});
  if(!canvas||!gl){if(statusEl)statusEl.textContent='WebGL2 unavailable';return null;}

  let CENTER=[376352,313268,538304],SCALE=1e-4,brain=null,geometry=null,synapseManifest=null;
  let target=[0,0,0],yaw=0,pitch=.06,distance=135,brainDistance=135;
  let brainOpacity=.055,followActivity=false,selectedCandidate='';
  let frameState={timeMs:0,cellActivity:[],outputs:[],events:null};
  let generation=0,renderQueued=false,initialFitDone=false,pendingSelection=null;
  const bodies=new Map(),pamIndex=new Map(data.cells.map((c,i)=>[Number(c.body_id),i]));
  const pamIds=new Set(data.cells.map(c=>Number(c.body_id)));
  let inputIds=[],outputIds=[],selectedIds=[];
  let inputSynapses=[],outputSynapses=[];

  const vs=`#version 300 es
  in vec3 aPos; uniform mat4 uMVP; uniform float uPointSize;
  void main(){gl_Position=uMVP*vec4(aPos,1.0);gl_PointSize=uPointSize;}`;
  const fs=`#version 300 es
  precision highp float; uniform vec4 uColor; uniform int uPointMode; out vec4 outColor;
  void main(){if(uPointMode==1){vec2 q=gl_PointCoord-vec2(.5);if(dot(q,q)>.25)discard;}outColor=uColor;}`;
  function shader(type,src){const s=gl.createShader(type);gl.shaderSource(s,src);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw new Error(gl.getShaderInfoLog(s));return s;}
  const prog=gl.createProgram();gl.attachShader(prog,shader(gl.VERTEX_SHADER,vs));gl.attachShader(prog,shader(gl.FRAGMENT_SHADER,fs));gl.linkProgram(prog);if(!gl.getProgramParameter(prog,gl.LINK_STATUS))throw new Error(gl.getProgramInfoLog(prog));
  const aPos=gl.getAttribLocation(prog,'aPos'),uMVP=gl.getUniformLocation(prog,'uMVP'),uColor=gl.getUniformLocation(prog,'uColor'),uPointSize=gl.getUniformLocation(prog,'uPointSize'),uPointMode=gl.getUniformLocation(prog,'uPointMode');
  gl.enable(gl.DEPTH_TEST);gl.depthFunc(gl.LEQUAL);gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);

  function perspective(fovy,aspect,near,far){const f=1/Math.tan(fovy/2),nf=1/(near-far);return new Float32Array([f/aspect,0,0,0,0,f,0,0,0,0,(far+near)*nf,-1,0,0,2*far*near*nf,0]);}
  function lookAt(e,c,u){let zx=e[0]-c[0],zy=e[1]-c[1],zz=e[2]-c[2];let zl=Math.hypot(zx,zy,zz)||1;zx/=zl;zy/=zl;zz/=zl;let xx=u[1]*zz-u[2]*zy,xy=u[2]*zx-u[0]*zz,xz=u[0]*zy-u[1]*zx;let xl=Math.hypot(xx,xy,xz)||1;xx/=xl;xy/=xl;xz/=xl;let yx=zy*xz-zz*xy,yy=zz*xx-zx*xz,yz=zx*xy-zy*xx;return new Float32Array([xx,yx,zx,0,xy,yy,zy,0,xz,yz,zz,0,-(xx*e[0]+xy*e[1]+xz*e[2]),-(yx*e[0]+yy*e[1]+yz*e[2]),-(zx*e[0]+zy*e[1]+zz*e[2]),1]);}
  function mul(a,b){const o=new Float32Array(16);for(let c=0;c<4;c++)for(let r=0;r<4;r++)o[c*4+r]=a[r]*b[c*4]+a[4+r]*b[c*4+1]+a[8+r]*b[c*4+2]+a[12+r]*b[c*4+3];return o;}
  function eye(){return[target[0]+distance*Math.cos(pitch)*Math.sin(yaw),target[1]+distance*Math.sin(pitch),target[2]+distance*Math.cos(pitch)*Math.cos(yaw)];}
  function mvp(){return mul(perspective(Math.PI/4,Math.max(.1,canvas.width/canvas.height),.1,2600),lookAt(eye(),target,[0,1,0]));}
  function canonical(x,y,z){const ex=(x-CENTER[0])*SCALE,ey=(y-CENTER[1])*SCALE,ez=(z-CENTER[2])*SCALE;return[-ex,-ez,ey];}
  function boundsOf(pos){let lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];for(let i=0;i<pos.length;i+=3)for(let k=0;k<3;k++){const v=pos[i+k];if(v<lo[k])lo[k]=v;if(v>hi[k])hi[k]=v;}return{lo,hi,center:lo.map((v,k)=>(v+hi[k])/2),span:Math.max(...lo.map((v,k)=>hi[k]-v))};}
  function makeObject(positions,indices,mode,meta={}){const vao=gl.createVertexArray();gl.bindVertexArray(vao);const vb=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,vb);gl.bufferData(gl.ARRAY_BUFFER,positions,gl.STATIC_DRAW);gl.enableVertexAttribArray(aPos);gl.vertexAttribPointer(aPos,3,gl.FLOAT,false,0,0);let ib=null;if(indices){ib=gl.createBuffer();gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,ib);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,indices,gl.STATIC_DRAW);}gl.bindVertexArray(null);return{vao,vb,ib,positions,indices,count:indices?indices.length:positions.length/3,mode,bounds:boundsOf(positions),path:null,...meta};}
  function drop(o){if(!o)return;gl.deleteBuffer(o.vb);if(o.ib)gl.deleteBuffer(o.ib);gl.deleteVertexArray(o.vao);}
  function transformedPositions(view,start,count,mult=1){const out=new Float32Array(count*3);for(let i=0;i<count;i++){const p=canonical(view.getFloat32(start+i*12,true)*mult,view.getFloat32(start+i*12+4,true)*mult,view.getFloat32(start+i*12+8,true)*mult);out.set(p,i*3);}return out;}
  function transformedTriples(points,mult=1){const out=new Float32Array(points.length*3);for(let i=0;i<points.length;i++)out.set(canonical(points[i][0]*mult,points[i][1]*mult,points[i][2]*mult),i*3);return out;}
  function parseMesh(buf){const v=new DataView(buf),n=v.getUint32(0,true),triBytes=buf.byteLength-4-n*12;if(triBytes<0||triBytes%12)throw new Error('invalid MaleCNS mesh');return makeObject(transformedPositions(v,4,n),new Uint32Array(buf.slice(4+n*12)),gl.TRIANGLES,{role:'brain'});}
  function parseSkeleton(buf,id,role){const v=new DataView(buf),n=v.getUint32(0,true),e=v.getUint32(4,true),need=8+n*12+e*8;if(buf.byteLength!==need)throw new Error('invalid MaleCNS skeleton');return makeObject(transformedPositions(v,8,n),new Uint32Array(buf.slice(8+n*12)),gl.LINES,{bodyId:Number(id),role});}

  function buildDiameterPath(o){if(o.path)return o.path;const n=o.positions.length/3,idx=o.indices;if(!idx||n<2){o.path=[];return o.path;}const adj=Array.from({length:n},()=>[]);for(let i=0;i<idx.length;i+=2){const a=idx[i],b=idx[i+1];if(a<n&&b<n){adj[a].push(b);adj[b].push(a);}}
    const bfs=start=>{const q=new Int32Array(n),dist=new Int32Array(n),parent=new Int32Array(n);dist.fill(-1);parent.fill(-1);let h=0,t=0;q[t++]=start;dist[start]=0;let far=start;while(h<t){const u=q[h++];if(dist[u]>dist[far])far=u;for(const w of adj[u])if(dist[w]<0){dist[w]=dist[u]+1;parent[w]=u;q[t++]=w;}}return{far,parent};};
    const a=bfs(0).far,b=bfs(a),path=[];let u=b.far;while(u>=0){path.push(u);if(u===a)break;u=b.parent[u];}path.reverse();o.path=path;return path;}
  function vertex(o,i){return[o.positions[i*3],o.positions[i*3+1],o.positions[i*3+2]];}
  function nearestPathEnd(o,point){const path=buildDiameterPath(o);if(!path.length||!point)return 0;return vdist(vertex(o,path[0]),point)<=vdist(vertex(o,path[path.length-1]),point)?0:1;}
  function orientPath(o,startPoint,endPoint){let path=buildDiameterPath(o).slice();if(path.length<2)return path;const p0=vertex(o,path[0]),p1=vertex(o,path[path.length-1]);let forward=0,reverse=0;if(startPoint){forward+=vdist(p0,startPoint);reverse+=vdist(p1,startPoint);}if(endPoint){forward+=vdist(p1,endPoint);reverse+=vdist(p0,endPoint);}if(reverse<forward)path.reverse();return path;}
  function pointOnPath(o,progress){const path=o.routePath||buildDiameterPath(o);if(!path.length)return o.bounds.center;const x=clamp(progress,0,1)*(path.length-1),i=Math.floor(x),j=Math.min(path.length-1,i+1),t=x-i,a=vertex(o,path[i]),b=vertex(o,path[j]);return[lerp(a[0],b[0],t),lerp(a[1],b[1],t),lerp(a[2],b[2],t)];}

  async function fetchBuffer(url){const r=await fetch(url);if(!r.ok)throw new Error(`${r.status} ${url}`);return r.arrayBuffer();}
  function skeletonUrl(id){const vendored=new Set((geometry?.vendored_skeleton_ids||[]).map(Number));const template=vendored.has(Number(id))&&geometry?.local_skeleton_url_template?geometry.local_skeleton_url_template:geometry?.source_skeleton_url_template;return template?.replace('{body_id}',String(id));}
  async function loadBody(id,role){id=Number(id);const existing=bodies.get(id);if(existing){if(role!=='pam')existing.role=role;return existing;}const url=skeletonUrl(id);if(!url)return null;try{const o=parseSkeleton(await fetchBuffer(url),id,role);bodies.set(id,o);requestRender();return o;}catch(e){console.warn('State Lab skeleton',id,e);return null;}}

  function centroid(points){if(!points.length)return null;const s=[0,0,0];for(const p of points){s[0]+=p[0];s[1]+=p[1];s[2]+=p[2];}return s.map(v=>v/points.length);}
  function synapseWorld(points,key,scale){return points.filter(p=>Array.isArray(p[key])).map(p=>canonical(p[key][0]*scale,p[key][1]*scale,p[key][2]*scale));}
  function configureRoutes(){const scale=Number(synapseManifest?.coordinate_scale_to_nm||8);for(const id of selectedIds){const o=bodies.get(id);if(!o)continue;const rec=synapseManifest?.candidates?.[String(id)]||{};const inPts=synapseWorld((rec.input_points||[]).filter(p=>inputIds.includes(Number(p.pre))), 'post_xyz',scale);const outPts=synapseWorld((rec.output_points||[]).filter(p=>outputIds.includes(Number(p.post))), 'pre_xyz',scale);o.routePath=orientPath(o,centroid(inPts),centroid(outPts));}
    for(const id of inputIds){const o=bodies.get(id);if(!o)continue;let pts=[];for(const cid of selectedIds){const rec=synapseManifest?.candidates?.[String(cid)]||{};pts.push(...synapseWorld((rec.input_points||[]).filter(p=>Number(p.pre)===id),'pre_xyz',scale));}const end=centroid(pts);const path=buildDiameterPath(o).slice();if(path.length&&nearestPathEnd(o,end)===0)path.reverse();o.routePath=path;}
    for(const id of outputIds){const o=bodies.get(id);if(!o)continue;let pts=[];for(const cid of selectedIds){const rec=synapseManifest?.candidates?.[String(cid)]||{};pts.push(...synapseWorld((rec.output_points||[]).filter(p=>Number(p.post)===id),'post_xyz',scale));}const start=centroid(pts);const path=buildDiameterPath(o).slice();if(path.length&&nearestPathEnd(o,start)===1)path.reverse();o.routePath=path;}
  }

  function refreshSynapses(){inputSynapses=[];outputSynapses=[];const scale=Number(synapseManifest?.coordinate_scale_to_nm||8);for(const cid of selectedIds){const rec=synapseManifest?.candidates?.[String(cid)]||{};for(const p of rec.input_points||[])if(inputIds.includes(Number(p.pre))&&Number(p.post)===cid&&p.post_xyz)inputSynapses.push(canonical(p.post_xyz[0]*scale,p.post_xyz[1]*scale,p.post_xyz[2]*scale));for(const p of rec.output_points||[])if(Number(p.pre)===cid&&outputIds.includes(Number(p.post))&&p.pre_xyz)outputSynapses.push(canonical(p.pre_xyz[0]*scale,p.pre_xyz[1]*scale,p.pre_xyz[2]*scale));}}

  function candidateIdsFrom(value){return value==='pair'?data.candidate_ids.slice(0,2).map(Number):[Number(value)].filter(Number.isFinite);}
  function inputMembers(stimulus,ids){const channel=data.input_channels.find(ch=>ch.name===stimulus);if(!channel)return[];const scored=(channel.members||[]).map(m=>{const w=(m.targets||[]).filter(t=>ids.includes(Number(t.body_id))).reduce((s,t)=>s+Number(t.weight||0),0);return{...m,targetWeight:w};}).filter(m=>m.targetWeight>0).sort((a,b)=>b.targetWeight-a.targetWeight||b.weight-a.weight);return(scored.length?scored:(channel.members||[])).slice(0,4);}
  function outputMembers(ids){const scores=new Map();for(const cid of ids){const c=data.cells.find(x=>Number(x.body_id)===cid);for(const o of c?.top_outputs||[]){const old=scores.get(Number(o.body_id))||{...o,weight:0};old.weight+=Number(o.weight||0);scores.set(Number(o.body_id),old);}}return[...scores.values()].sort((a,b)=>b.weight-a.weight).slice(0,5);}
  function outputTypeForBody(id){for(const cid of selectedIds){const cell=data.cells.find(c=>Number(c.body_id)===cid),rec=(cell?.top_outputs||[]).find(x=>Number(x.body_id)===Number(id));if(rec)return rec.type;}return null;}

  async function setSelection(candidate,stimulus,{fit=false}={}){pendingSelection={candidate,stimulus,fit};selectedCandidate=candidate;selectedIds=candidateIdsFrom(candidate);if(!geometry)return;const myGen=++generation;const inMembers=inputMembers(stimulus,selectedIds),outMembers=outputMembers(selectedIds);inputIds=inMembers.map(x=>Number(x.body_id));outputIds=outMembers.map(x=>Number(x.body_id));
    for(const [id,o] of bodies){if(!pamIds.has(id)&&!inputIds.includes(id)&&!outputIds.includes(id)){drop(o);bodies.delete(id);}else if(pamIds.has(id))o.role='pam';}
    if(statusEl)statusEl.textContent='loading live circuit skeletons...';await Promise.all(selectedIds.map(id=>loadBody(id,'candidate')));if(myGen!==generation)return;await Promise.all(inputIds.map(id=>loadBody(id,'input')));if(myGen!==generation)return;await Promise.all(outputIds.map(id=>loadBody(id,'output')));if(myGen!==generation)return;for(const id of selectedIds){const o=bodies.get(id);if(o)o.role='candidate';}refreshSynapses();configureRoutes();if(fit||!initialFitDone){fitCandidate();initialFitDone=true;}if(statusEl)statusEl.textContent=`live circuit ready · ${inputIds.length} upstream · ${selectedIds.length} PAM04 · ${outputIds.length} downstream · ${inputSynapses.length+outputSynapses.length} real synapse sites`;requestRender();}

  async function loadPamPopulation(){const priority=[...data.candidate_ids.map(Number),...data.cells.map(c=>Number(c.body_id))].filter((x,i,a)=>a.indexOf(x)===i);let cursor=0,done=0;const workers=Array.from({length:3},async()=>{while(cursor<priority.length){const id=priority[cursor++];await loadBody(id,pamIds.has(id)?'pam':'candidate');done++;if(statusEl&&done%6===0)statusEl.textContent=`loading PAM04 anatomy ${done}/${priority.length}`;await new Promise(r=>setTimeout(r,0));}});await Promise.all(workers);}

  const pulseVAO=gl.createVertexArray(),pulseVB=gl.createBuffer();gl.bindVertexArray(pulseVAO);gl.bindBuffer(gl.ARRAY_BUFFER,pulseVB);gl.bufferData(gl.ARRAY_BUFFER,12,gl.DYNAMIC_DRAW);gl.enableVertexAttribArray(aPos);gl.vertexAttribPointer(aPos,3,gl.FLOAT,false,0,0);gl.bindVertexArray(null);
  const synVAO=gl.createVertexArray(),synVB=gl.createBuffer();gl.bindVertexArray(synVAO);gl.bindBuffer(gl.ARRAY_BUFFER,synVB);gl.bufferData(gl.ARRAY_BUFFER,12,gl.DYNAMIC_DRAW);gl.enableVertexAttribArray(aPos);gl.vertexAttribPointer(aPos,3,gl.FLOAT,false,0,0);gl.bindVertexArray(null);
  function drawDynamicPoints(points,size,color,vao,vb){if(!points.length)return;const arr=new Float32Array(points.flat());gl.bindVertexArray(vao);gl.bindBuffer(gl.ARRAY_BUFFER,vb);gl.bufferData(gl.ARRAY_BUFFER,arr,gl.DYNAMIC_DRAW);gl.uniform4fv(uColor,color);gl.uniform1f(uPointSize,size);gl.uniform1i(uPointMode,1);gl.drawArrays(gl.POINTS,0,points.length);}
  function drawObject(o,color,pointSize=1){gl.bindVertexArray(o.vao);gl.uniform4fv(uColor,color);gl.uniform1f(uPointSize,pointSize);gl.uniform1i(uPointMode,o.mode===gl.POINTS?1:0);gl.drawElements(o.mode,o.count,gl.UNSIGNED_INT,0);}
  function resize(){const cssW=Math.max(1,canvas.clientWidth),cssH=Math.max(1,canvas.clientHeight),maxPixels=2100000,scale=Math.min(devicePixelRatio||1,1.45,Math.sqrt(maxPixels/(cssW*cssH))),w=Math.max(1,Math.floor(cssW*scale)),h=Math.max(1,Math.floor(cssH*scale));if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;gl.viewport(0,0,w,h);}}

  function recentEvent(events,time,windowMs){for(let i=events.length-1;i>=0;i--){const age=time-events[i];if(age<0)continue;if(age<=windowMs)return age;if(age>windowMs)break;}return null;}
  function pulsePoints(){const pts=[],t=Number(frameState.timeMs||0),travel=Number(data.model.visual_pulse_travel_ms||260),events=frameState.events||{};
    for(const id of inputIds){const o=bodies.get(id);if(!o)continue;const age=recentEvent(events.upstream||[],t,travel);if(age!==null)pts.push(pointOnPath(o,age/travel));}
    for(const id of selectedIds){const o=bodies.get(id);if(!o)continue;const age=recentEvent(events.cells?.[String(id)]||[],t,travel);if(age!==null)pts.push(pointOnPath(o,age/travel));}
    for(const id of outputIds){const o=bodies.get(id);if(!o)continue;const type=outputTypeForBody(id);const age=recentEvent(events.outputs?.[type]||[],t,travel);if(age!==null)pts.push(pointOnPath(o,age/travel));}
    return pts;
  }
  function synapseFlash(){const t=Number(frameState.timeMs||0),events=frameState.events||{},travel=Number(data.model.visual_pulse_travel_ms||260);const up=recentEvent(events.upstream||[],t,travel+90),cell=selectedIds.map(id=>recentEvent(events.cells?.[String(id)]||[],t,travel+90)).filter(x=>x!==null);return{input:up!==null&&Math.abs(up-travel)<90,output:cell.some(age=>Math.abs(age-travel)<90)};}

  function draw(){renderQueued=false;resize();gl.clearColor(.012,.012,.014,1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.useProgram(prog);gl.uniformMatrix4fv(uMVP,false,mvp());
    if(brain){gl.depthMask(false);gl.enable(gl.CULL_FACE);drawObject(brain,[.42,.44,.48,brainOpacity]);gl.disable(gl.CULL_FACE);gl.depthMask(true);}
    const activities=frameState.cellActivity||[];for(const [id,o] of bodies){let a=.04,color=[.45,.47,.5,.12];if(pamIds.has(id)){a=Number(activities[pamIndex.get(id)]||0);const selected=selectedIds.includes(id);const k=clamp(a,0,1);color=selected?[.95,.97,1,.24+.76*k]:[.55+.35*k,.58+.34*k,.62+.33*k,.08+.48*k];}else if(o.role==='input'){const pulse=frameState.upstreamActive?1:0;color=[.78,.82,.88,.15+.72*pulse];}else if(o.role==='output'){const type=outputTypeForBody(id),oi=data.output_channels.findIndex(ch=>ch.name===type),v=oi>=0?Number(frameState.outputs?.[oi]||0):0;color=[.68+.25*v,.7+.24*v,.74+.22*v,.12+.7*clamp(v,0,1)];}drawObject(o,color,1);if(selectedIds.includes(id)&&a>.04){gl.uniform4fv(uColor,[1,1,1,.25+.7*clamp(a,0,1)]);gl.uniform1f(uPointSize,2.2+3.0*a);gl.uniform1i(uPointMode,1);gl.drawArrays(gl.POINTS,0,o.positions.length/3);}}
    const flash=synapseFlash();drawDynamicPoints(inputSynapses,flash.input?8:3.4,flash.input?[1,1,1,.95]:[.75,.78,.82,.34],synVAO,synVB);drawDynamicPoints(outputSynapses,flash.output?8:3.4,flash.output?[1,1,1,.95]:[.65,.68,.74,.30],synVAO,synVB);
    const p=pulsePoints();drawDynamicPoints(p,11,[1,1,1,.98],pulseVAO,pulseVB);
    if(followActivity&&p.length){const q=p[p.length-1];for(let k=0;k<3;k++)target[k]=lerp(target[k],q[k],.055);requestRender();}
  }
  function requestRender(){if(renderQueued)return;renderQueued=true;requestAnimationFrame(draw);}

  function fitBounds(b,padding=1.8){if(!b)return;target=[...b.center];distance=Math.max(5,Math.min(brainDistance,Math.max(3,b.span)*padding));requestRender();}
  function fitCandidate(){const obs=selectedIds.map(id=>bodies.get(id)).filter(Boolean);if(!obs.length)return;const lo=[0,1,2].map(k=>Math.min(...obs.map(o=>o.bounds.lo[k]))),hi=[0,1,2].map(k=>Math.max(...obs.map(o=>o.bounds.hi[k])));fitBounds(boundsOf(new Float32Array([...lo,...hi])),1.8);}
  function fitBrain(){if(brain)fitBounds(brain.bounds,.8);}
  function setPreset(name){if(name==='anterior'){yaw=0;pitch=0;}else if(name==='posterior'){yaw=Math.PI;pitch=0;}else if(name==='dorsal'){yaw=0;pitch=1.45;}else if(name==='left'){yaw=-Math.PI/2;pitch=0;}else if(name==='right'){yaw=Math.PI/2;pitch=0;}requestRender();}

  let drag=null;canvas.addEventListener('contextmenu',e=>e.preventDefault());canvas.addEventListener('pointerdown',e=>{canvas.setPointerCapture(e.pointerId);drag={x:e.clientX,y:e.clientY,button:e.button,pan:e.shiftKey||e.button===1||e.button===2};});canvas.addEventListener('pointerup',()=>drag=null);canvas.addEventListener('pointermove',e=>{if(!drag)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;drag.x=e.clientX;drag.y=e.clientY;if(drag.pan){const ep=eye(),f=[target[0]-ep[0],target[1]-ep[1],target[2]-ep[2]],fl=Math.hypot(...f)||1;for(let k=0;k<3;k++)f[k]/=fl;const right=[f[2],0,-f[0]],rl=Math.hypot(right[0],right[2])||1;right[0]/=rl;right[2]/=rl;const up=[-f[1]*right[2],f[2]*right[0]-f[0]*right[2],f[1]*right[0]],scale=distance*.0015;for(let k=0;k<3;k++)target[k]+=(-dx*right[k]+dy*up[k])*scale;}else{yaw-=dx*.006;pitch=clamp(pitch-dy*.006,-1.5,1.5);}requestRender();});canvas.addEventListener('wheel',e=>{e.preventDefault();distance=clamp(distance*Math.exp(e.deltaY*.001),2.5,800);requestRender();},{passive:false});canvas.addEventListener('dblclick',fitCandidate);

  async function init(){try{const [gr,sr]=await Promise.all([fetch('data/geometry.json'),fetch('data/experiments/001_pam04_synapses.json').catch(()=>null)]);if(!gr.ok)throw new Error(`geometry ${gr.status}`);geometry=await gr.json();if(sr?.ok)synapseManifest=await sr.json();if(Array.isArray(geometry.display_center)&&geometry.display_center.length===3)CENTER=geometry.display_center.map(Number);if(Number.isFinite(Number(geometry.display_scale)))SCALE=Number(geometry.display_scale);if(geometry.geometry_mode==='major-shell'&&geometry.brain_shell?.local_url){brain=parseMesh(await fetchBuffer(geometry.brain_shell.local_url));brainDistance=Math.max(18,brain.bounds.span/Math.tan(Math.PI/8)*.78);distance=brainDistance;}await loadPamPopulation();if(pendingSelection)await setSelection(pendingSelection.candidate,pendingSelection.stimulus,{fit:pendingSelection.fit});requestRender();if(statusEl&&(!pendingSelection||!inputIds.length))statusEl.textContent='PAM04 live anatomy loaded';}catch(e){console.warn('State Lab 3D init',e);if(statusEl)statusEl.textContent=`3D unavailable: ${e.message}`;}}

  function updateFrame(state){frameState=state||frameState;requestRender();}
  function setFollow(v){followActivity=!!v;}
  function setBrainOpacity(v){brainOpacity=clamp(Number(v),0,.35);requestRender();}
  init();
  return{setSelection,updateFrame,setFollow,setBrainOpacity,fitCandidate,fitBrain,setPreset,requestRender};
}
window.DSCStateLab3D={create:createStateLab3D};
})();
