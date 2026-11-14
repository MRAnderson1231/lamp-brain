import React, {useEffect, useRef, useState} from 'react';
import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';

// This is the exported Blender rig, driven by the runtime's actual pose channels.
// The browser does not choose actions or play an independent animation clip.
export default function LampView({pose}) {
  const host = useRef(null), current = useRef(pose), [error, setError] = useState('');
  current.current = pose;
  useEffect(() => {
    const el = host.current;
    let renderer;
    try { renderer = new THREE.WebGLRenderer({antialias: true}); }
    catch { setError('此浏览器无法创建 3D 视图，请使用支持 WebGL 的浏览器。'); return; }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    el.appendChild(renderer.domElement);
    const scene = new THREE.Scene(); scene.background = new THREE.Color('#eef0f1');
    const camera = new THREE.PerspectiveCamera(32, 1, .01, 20);
    camera.position.set(.70, .49, 1.05); camera.lookAt(.12, .23, 0);
    scene.add(new THREE.HemisphereLight(0xffffff, 0x989f9f, 2.6));
    const key = new THREE.DirectionalLight(0xffffff, 3); key.position.set(-1, 2, 2); key.castShadow = true;
    key.shadow.mapSize.set(1024,1024); key.shadow.camera.left=-1;key.shadow.camera.right=1; key.shadow.camera.top=1;key.shadow.camera.bottom=-1;
    key.shadow.bias=-.0006;key.shadow.normalBias=.012;
    scene.add(key);
    const floor = new THREE.Mesh(new THREE.PlaneGeometry(8,8), new THREE.MeshStandardMaterial({color: '#dfe3e4', roughness:.9}));
    floor.rotation.x=-Math.PI/2; floor.position.y=-.002; floor.receiveShadow=true; scene.add(floor);
    const tablet=new THREE.Mesh(new THREE.BoxGeometry(.19,.009,.25),new THREE.MeshStandardMaterial({color:'#72797b',roughness:.3}));
    tablet.position.set(.33,.005,.07);tablet.rotation.y=-.15;tablet.castShadow=true;scene.add(tablet);
    const screen=new THREE.Mesh(new THREE.PlaneGeometry(.174,.232),new THREE.MeshStandardMaterial({color:'#f7f7f6',roughness:.7}));
    screen.rotation.x=-Math.PI/2;screen.rotation.z=-.15;screen.position.set(.33,.010,.07);scene.add(screen);
    let rig=null, dead=false;
    const rest = {};
    const loader = new GLTFLoader();
    loader.load('/lamp.glb', gltf => {
      if (dead) return;
      rig=gltf.scene;
      for (const n of ['root','swivel','lower','upper','head']) {
        const b=rig.getObjectByName(n);
        if (!b) {setError(`模型缺少骨骼：${n}`);return;}
        rest[n]={node:b,q:b.quaternion.clone(),p:b.position.clone(),s:b.scale.clone()};
      }
      rig.traverse(o=>{if(o.isMesh){o.castShadow=true;o.receiveShadow=true;}});
      scene.add(rig);
    }, undefined, () => setError('台灯模型加载失败，请重试。'));
    function resize(){const w=el.clientWidth,h=el.clientHeight;renderer.setSize(w,h);camera.aspect=w/h;camera.updateProjectionMatrix();}
    const observer=new ResizeObserver(resize);observer.observe(el);resize();
    const rad=THREE.MathUtils.degToRad;
    renderer.setAnimationLoop(()=>{
      const p=current.current || {};
      if (rig && rest.head) {
        const rotations={swivel:[0,rad(p.yaw||0),0],lower:[rad(p.low||0),0,0],upper:[rad(p.up||0),0,0],head:[rad(p.nod||0),0,-rad(p.turn||0)]};
        for(const [n,a] of Object.entries(rotations)){
          const b=rest[n];
          b.node.quaternion.copy(b.q).multiply(new THREE.Quaternion().setFromEuler(new THREE.Euler(...a,'ZYX')));
        }
        const r=rest.root, s=Math.max(.1,1+(p.squash||0));
        r.node.position.copy(r.p);r.node.position.y+=p.hop||0;
        r.node.scale.copy(r.s).multiply(new THREE.Vector3(1/Math.sqrt(s),s,1/Math.sqrt(s)));
        rig.traverse(o=>{if(o.isMesh){
          for(const m of (Array.isArray(o.material)?o.material:[o.material])){
            if(m.name.includes('Bulb') || m.name.includes('Inner')){
              m.emissive=new THREE.Color('#e4efff').lerp(new THREE.Color('#ffd69a'),Math.max(0,Math.min(1,p.warmth??.75)));
              m.emissiveIntensity=Math.max(0,p.glow??1);
            }
          }
        }});
      }
      renderer.render(scene,camera);
    });
    return ()=>{dead=true;observer.disconnect();renderer.setAnimationLoop(null);scene.traverse(o=>{o.geometry?.dispose();if(o.material){for(const m of Array.isArray(o.material)?o.material:[o.material])m.dispose();}});renderer.dispose();renderer.domElement.remove();};
  },[]);
  return <div className="visual lamp" ref={host} role="img" aria-label="由运行时姿态驱动的三维台灯">{error&&<div className="view-error">{error}</div>}</div>;
}
