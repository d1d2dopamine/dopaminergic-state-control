(()=>{
const canvas=document.getElementById('brain-canvas'); if(!canvas)return;
const status=document.getElementById('viewer-status');
const gl=canvas.getContext('webgl2',{antialias:true,alpha:false,powerPreference:'high-performance'});
if(!gl){status.textContent='WebGL2 unavailable';return;}

let CENTER=[376352,313268,538304], SCALE=1e-4, BASE_DISTANCE=150;
const vs=`#version 300 es
in vec3 aPos; uniform mat4 uMVP; void main(){ gl_Position=uMVP*vec4(aPos,1.0); }`;
const fs=`#version 300 es
precision highp float; uniform vec4 uColor; out vec4 outColor; void main(){ outColor=uColor; }`;
function shader(t,s){const x=gl.createShader(t);gl.shaderSource(x,s);gl.compileShader(x);if(!gl.getShaderParameter(x,gl.COMPILE_STATUS))throw new Error(gl.getShaderInfoLog(x));return x;}
const prog=gl.createProgram();gl.attachShader(prog,shader(gl.VERTEX_SHADER,vs));gl.attachShader(prog,shader(gl.FRAGMENT_SHADER,fs));gl.linkProgram(prog);if(!gl.getProgramParameter(prog,gl.LINK_STATUS))throw new Error(gl.getProgramInfoLog(prog));gl.useProgram(prog);
const aPos=gl.getAttribLocation(prog,'aPos'),uMVP=gl.getUniformLocation(prog,'uMVP'),uColor=gl.getUniformLocation(prog,'uColor');

function perspective(fovy,aspect,near,far){const f=1/Math.tan(fovy/2),nf=1/(near-far);return new Float32Array([f/aspect,0,0,0,0,f,0,0,0,0,(far+near)*nf,-1,0,0,2*far*near*nf,0]);}
function lookAt(e,c,u){let zx=e[0]-c[0],zy=e[1]-c[1],zz=e[2]-c[2];let zl=Math.hypot(zx,zy,zz);zx/=zl;zy/=zl;zz/=zl;let xx=u[1]*zz-u[2]*zy,xy=u[2]*zx-u[0]*zz,xz=u[0]*zy-u[1]*zx;let xl=Math.hypot(xx,xy,xz);xx/=xl;xy/=xl;xz/=xl;let yx=zy*xz-zz*xy,yy=zz*xx-zx*xz,yz=zx*xy-zy*xx;return new Float32Array([xx,yx,zx,0,xy,yy,zy,0,xz,yz,zz,0,-(xx*e[0]+xy*e[1]+xz*e[2]),-(yx*e[0]+yy*e[1]+yz*e[2]),-(zx*e[0]+zy*e[1]+zz*e[2]),1]);}
function mul(a,b){const o=new Float32Array(16);for(let c=0;c<4;c++)for(let r=0;r<4;r++)o[c*4+r]=a[r]*b[c*4]+a[4+r]*b[c*4+1]+a[8+r]*b[c*4+2]+a[12+r]*b[c*4+3];return o;}
function transformedPositions(raw,start,count){const out=new Float32Array(count*3);for(let i=0;i<count;i++){out[i*3]=(raw.getFloat32(start+i*12,true)-CENTER[0])*SCALE;out[i*3+1]=(raw.getFloat32(start+i*12+1,true)-CENTER[1])*SCALE;out[i*3+2]=(raw.getFloat32(start+i*12+2,true)-CENTER[2])*SCALE;}return out;}
function makeObject(positions,indices,mode,color,role='region'){const vao=gl.createVertexArray();gl.bindVertexArray(vao);const vb=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,vb);gl.bufferData(gl.ARRAY_BUFFER,positions,gl.STATIC_DRAW);gl.enableVertexAttribArray(aPos);gl.vertexAttribPointer(aPos,3,gl.FLOAT,false,0,0);const ib=gl.createBuffer();gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,ib);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,indices,gl.STATIC_DRAW);gl.bindVertexArray(null);return{vao,count:indices.length,mode,color,vb,ib,role};}
function dropObject(o){if(!o)return;gl.deleteBuffer(o.vb);gl.deleteBuffer(o.ib);gl.deleteVertexArray(o.vao);}
function parseMesh(buf){const v=new DataView(buf),n=v.getUint32(0,true),triBytes=buf.byteLength-4-n*12;if(triBytes<0||triBytes%12)throw new Error('invalid MaleCNS mesh');const pos=transformedPositions(v,4,n),idx=new Uint32Array(buf.slice(4+n*12));return makeObject(pos,idx,gl.TRIANGLES,[0.30,0.30,0.30,0.050],'region');}
function parseSkeleton(buf,color,role){const v=new DataView(buf),n=v.getUint32(0,true),e=v.getUint32(4,true),need=8+n*12+e*8;if(buf.byteLength!==need)throw new Error('invalid MaleCNS skeleton');const pos=transformedPositions(v,8,n),idx=new Uint32Array(buf.slice(8+n*12));return makeObject(pos,idx,gl.LINES,color,role);}

let yaw=-0.55,pitch=0.15,distance=BASE_DISTANCE,drag=false,last=[0,0],regionsVisible=true,relatedVisible=true;
let regions=[],skeletons=[];let geometry=null,currentFinding=null,skeletonGeneration=0;
function reset(){yaw=-0.55;pitch=0.15;distance=BASE_DISTANCE;}
function resize(){const d=Math.min(devicePixelRatio||1,2),w=Math.max(1,Math.floor(canvas.clientWidth*d)),h=Math.max(1,Math.floor(canvas.clientHeight*d));if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;gl.viewport(0,0,w,h);}}
function mvp(){const eye=[distance*Math.cos(pitch)*Math.sin(yaw),distance*Math.sin(pitch),distance*Math.cos(pitch)*Math.cos(yaw)];return mul(perspective(Math.PI/4,canvas.width/canvas.height,0.1,2000),lookAt(eye,[0,0,0],[0,1,0]));}
let renderQueued=false; function requestRender(){if(renderQueued)return;renderQueued=true;requestAnimationFrame(draw);}
function draw(){renderQueued=false;resize();gl.clearColor(.035,.035,.035,1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.useProgram(prog);gl.uniformMatrix4fv(uMVP,false,mvp());gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);if(regionsVisible){gl.disable(gl.DEPTH_TEST);for(const o of regions){gl.bindVertexArray(o.vao);gl.uniform4fv(uColor,o.color);gl.drawElements(o.mode,o.count,gl.UNSIGNED_INT,0);}}gl.disable(gl.DEPTH_TEST);for(const o of skeletons){if(o.role==='related'&&!relatedVisible)continue;gl.bindVertexArray(o.vao);gl.uniform4fv(uColor,o.color);gl.drawElements(o.mode,o.count,gl.UNSIGNED_INT,0);}}
requestRender();

canvas.addEventListener('pointerdown',e=>{drag=true;last=[e.clientX,e.clientY];canvas.setPointerCapture(e.pointerId)});canvas.addEventListener('pointerup',()=>drag=false);canvas.addEventListener('pointercancel',()=>drag=false);canvas.addEventListener('pointermove',e=>{if(!drag)return;const dx=e.clientX-last[0],dy=e.clientY-last[1];last=[e.clientX,e.clientY];yaw-=dx*.006;pitch=Math.max(-1.45,Math.min(1.45,pitch-dy*.006));requestRender();});canvas.addEventListener('wheel',e=>{e.preventDefault();distance=Math.max(15,Math.min(600,distance*Math.exp(e.deltaY*.001)));requestRender();},{passive:false});
const resetBtn=document.getElementById('reset-camera'), regionBtn=document.getElementById('toggle-regions'), relatedBtn=document.getElementById('toggle-related');
if(resetBtn)resetBtn.onclick=()=>{reset();requestRender();};
if(regionBtn)regionBtn.onclick=e=>{regionsVisible=!regionsVisible;e.currentTarget.textContent=`regions: ${regionsVisible?'on':'off'}`;requestRender();};
if(relatedBtn)relatedBtn.onclick=e=>{relatedVisible=!relatedVisible;e.currentTarget.textContent=`context: ${relatedVisible?'on':'off'}`;requestRender();};

async function loadRegions(){
  try{const r=await fetch('data/geometry.json');if(!r.ok)throw new Error(`${r.status}`);geometry=await r.json();}catch(e){status.textContent='geometry manifest missing; run the real MaleCNS workflow';return;}
  if(Array.isArray(geometry.display_center)&&geometry.display_center.length===3)CENTER=geometry.display_center.map(Number);
  if(Number.isFinite(Number(geometry.display_scale)))SCALE=Number(geometry.display_scale);
  if(geometry.bounds){const lo=geometry.bounds[0],hi=geometry.bounds[1],span=Math.max(hi[0]-lo[0],hi[1]-lo[1],hi[2]-lo[2])*SCALE;BASE_DISTANCE=Math.max(70,span*1.55);distance=BASE_DISTANCE;}
  status.textContent=`loading ${geometry.regions.length} official MaleCNS neuropil meshes…`;
  let done=0,cursor=0;const workers=Array.from({length:6},async()=>{while(cursor<geometry.regions.length){const r=geometry.regions[cursor++];try{const resp=await fetch(r.local_url||r.source_url);if(!resp.ok)throw new Error(`${resp.status}`);regions.push(parseMesh(await resp.arrayBuffer()));requestRender();}catch(err){console.warn('region',r.label,err);}done++;status.textContent=`brain regions ${done}/${geometry.regions.length} · neuron skeletons ${skeletons.length}`;}});await Promise.all(workers);status.textContent=`MaleCNS regions ${regions.length}/${geometry.regions.length} loaded · select a finding`;
  if(currentFinding)loadFindingSkeletons(currentFinding);
}
async function loadFindingSkeletons(f){
  currentFinding=f;if(!geometry)return;const gen=++skeletonGeneration;for(const o of skeletons)dropObject(o);skeletons=[];
  const ids=[Number(f.focus_node),...(f.related_nodes||[]).map(Number)].filter((x,i,a)=>Number.isFinite(x)&&a.indexOf(x)===i).slice(0,18);
  status.textContent=`loading ${ids.length} published neuron skeletons…`;
  const vendored=new Set((geometry.vendored_skeleton_ids||[]).map(Number));
  await Promise.all(ids.map(async(id,i)=>{try{const template=vendored.has(id)&&geometry.local_skeleton_url_template?geometry.local_skeleton_url_template:geometry.source_skeleton_url_template;const url=template.replace('{body_id}',String(id));const r=await fetch(url);if(!r.ok)throw new Error(`${r.status}`);const role=i===0?'focus':'related';const color=role==='focus'?[1,1,1,1]:[.62,.62,.62,.82];const obj=parseSkeleton(await r.arrayBuffer(),color,role);if(gen===skeletonGeneration){skeletons.push(obj);requestRender();}else dropObject(obj);}catch(e){console.warn('skeleton',id,e);}}));
  if(gen===skeletonGeneration){const remote=ids.filter(id=>!vendored.has(id)).length;status.textContent=`MaleCNS real geometry · focus ${f.focus_node} · ${Math.max(0,skeletons.length-1)} context skeletons${remote?` · ${remote} streamed from official source`:''}`;}
}
window.addEventListener('dsc:finding',e=>loadFindingSkeletons(e.detail));
loadRegions().catch(e=>{console.error(e);status.textContent=`3D load failed: ${e.message}`;});
})();
