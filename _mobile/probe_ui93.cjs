/* 7.93 验收：用户气泡=AI气泡 / 设置顶栏磨砂 / 思考链时间轴 / #jh-home 样式写入次数
   node _mobile/probe_ui93.cjs
*/
const { chromium } = require('/usr/local/lib/node_modules/playwright');
const OUT='/sdcard/Download/WeiXin/_mobile/shots';
(async()=>{
  const b=await chromium.launch({executablePath:'/root/.cache/ms-playwright/chromium-1248/chrome-linux/chrome',args:['--no-sandbox','--allow-file-access-from-files','--disable-dev-shm-usage']});
  const c=await b.newContext({viewport:{width:430,height:932},deviceScaleFactor:1,isMobile:true,hasTouch:true,userAgent:'Mozilla/5.0 (Linux; Android 14; Pixel 8) Chrome/126 Mobile Safari/537.36'});
  const p=await c.newPage(); const errs=[]; p.on('pageerror',e=>errs.push(e.message));
  await p.goto('http://127.0.0.1:8901/ever.html?phone=1&splash=off',{waitUntil:'load',timeout:120000});
  await p.waitForTimeout(4500);
  for(const fr of p.frames()){try{await fr.evaluate(()=>{try{TEsplash&&TEsplash.dismiss()}catch(e){}})}catch(e){}}
  await p.waitForTimeout(1000);

  // 1) 气泡对比
  await p.evaluate(()=>window.nav('chat')); await p.waitForTimeout(900);
  const r1=await p.evaluate(()=>{
    const body=document.getElementById('chatBody');
    function mk(cls,t){const m=document.createElement('div');m.className='msg '+cls;
      m.innerHTML='<div class="msg-ava"></div><div class="bbl">'+t+'</div>';body.appendChild(m);return m.querySelector('.bbl');}
    const ai=mk('ai','A'), me=mk('me','M');
    const g=el=>{const s=getComputedStyle(el);return {bg:s.backgroundColor,bf:s.backdropFilter||s.webkitBackdropFilter,sh:s.boxShadow,r:s.borderRadius,c:s.color};};
    return {ai:g(ai), me:g(me)};
  });
  console.log('气泡 AI :', JSON.stringify(r1.ai));
  console.log('气泡 用户:', JSON.stringify(r1.me));
  console.log('两者是否一致:', JSON.stringify(r1.ai)===JSON.stringify(r1.me) ? '✅ 一致' : '⚠️ 仍有差异');
  await p.screenshot({path:OUT+'/v93-chat.png'});

  // 2) 设置页顶栏
  await p.evaluate(()=>window.nav('set')); await p.waitForTimeout(900);
  const r2=await p.evaluate(()=>{const e=document.querySelector('#p-set .st2-nav');const s=getComputedStyle(e);
    return {bg:s.backgroundColor,bf:s.backdropFilter||s.webkitBackdropFilter};});
  console.log('设置顶栏:', JSON.stringify(r2));
  await p.screenshot({path:OUT+'/v93-set.png'});

  // 3) 思考链工具时间轴（模拟实时路径）
  await p.evaluate(()=>window.nav('chat')); await p.waitForTimeout(600);
  const r3=await p.evaluate(()=>{
    const b=document.getElementById('chatBody'); b.innerHTML='';
    window.__liveTpId='tTEST';
    b.insertAdjacentHTML('beforeend', thoughtHtml('tTEST'));
    b.insertAdjacentHTML('beforeend','<div class="msg ai"><div class="msg-ava"></div><div class="msg-content"><div class="bbl">回复正文</div></div></div>');
    b.insertAdjacentHTML('beforeend', _toolCallsHtml([
      {type:'mcp', content:'filesystem | read_file', ok:'ok'},
      {type:'post', content:'发了一条动态', ok:'ok'}
    ]));
    tpToggle('tTEST');
    return document.getElementById('tpanelBody').innerHTML.slice(0,700);
  });
  console.log('思考链面板里的时间轴 HTML:', r3.replace(/></g,'>\n<').slice(0,600));
  await p.screenshot({path:OUT+'/v93-thought.png'});
  await p.evaluate(()=>tpPanelClose());

  // 4) #jh-home 样式写入次数（空闲 / 点按）
  await p.evaluate(()=>window.nav('home')); await p.waitForTimeout(1200);
  await p.evaluate(()=>{
    window.__mw=0;
    const el=document.getElementById('jh-home');
    new MutationObserver(ms=>{ window.__mw+=ms.length; }).observe(el,{attributes:true,attributeFilter:['style']});
    window.__mwR=()=>{const n=window.__mw;window.__mw=0;return n;};
  });
  await p.waitForTimeout(2000);
  console.log('空闲 2s 内 #jh-home style 写入次数:', await p.evaluate(()=>window.__mwR()));
  await p.mouse.click(215,420); await p.waitForTimeout(600);
  console.log('点一下桌面后 600ms 内写入次数:', await p.evaluate(()=>window.__mwR()));
  await p.mouse.click(400,500); await p.waitForTimeout(600);
  console.log('再点右侧栏后 600ms 内写入次数:', await p.evaluate(()=>window.__mwR()));
  if(errs.length) console.log('ERR:', [...new Set(errs)].slice(0,5).join(' | '));
  await b.close();
})();
