import React, {useEffect, useState} from 'react';
export default function CameraView({running, faceFresh}){
  const [url,setUrl]=useState('');
  useEffect(()=>{
    let dead=false,timer,previous='',controller=new AbortController();
    setUrl('');
    async function next(){
      try{
        const r=await fetch('/api/frame.jpg',{signal:controller.signal});
        if(r.ok && r.status===200){
          const blob=await r.blob();
          if(!dead){const nextUrl=URL.createObjectURL(blob);setUrl(nextUrl);if(previous)URL.revokeObjectURL(previous);previous=nextUrl;}
        }
      }catch(e){if(e.name!=='AbortError'&&!dead)setUrl('');}
      if(!dead)timer=setTimeout(next,200);
    }
    if(running)next();
    return ()=>{dead=true;clearTimeout(timer);controller.abort();if(previous)URL.revokeObjectURL(previous);};
  },[running]);
  return <div className="visual camera">{running&&url?<><img src={url} alt="本机摄像头实时镜像画面"/><span className="camera-status">{faceFresh?'检测到人脸':'未检测到人脸'} · 镜像预览</span></>:<div className="camera-empty"><svg viewBox="0 0 48 48" width="46" height="46" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="M6 15h10l4-6h9l4 6h9v26H6z"/><circle cx="24" cy="27" r="8"/></svg><p>{running?'正在等待摄像头画面…':'点击开始，画面仅在本机显示'}</p></div>}</div>;
}
