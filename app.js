/* Public market header; independent from ETF and other data panels. */
(() => {
 'use strict';
 const $=id=>document.getElementById(id);
 async function load(){
   const results=await Promise.allSettled(['dashboard','status'].map(async name=>{
     const r=await fetch('./data/'+name+'.json?ts='+Date.now(),{cache:'no-store'});
     if(!r.ok)throw Error(name+' HTTP '+r.status);
     return r.json();
   }));
   const d=results[0].status==='fulfilled'?results[0].value:null;
   const s=results[1].status==='fulfilled'?results[1].value:null;
   const days=(Array.isArray(d?.days)?d.days:[]).filter(x=>x.date&&x.coverage);
   const latest=days.at(-1);
   $('latestDate').textContent=latest?.date||'—';
   $('countDays').textContent=days.length+' / 5';
   $('coverage').textContent=latest?latest.coverage.TWSE+'＋'+latest.coverage.TPEx:'—';
   $('mode').className='pill '+(latest?'':'muted');
   $('mode').textContent=latest?(s?.ok===false?'保留上次核實資料':'官方歷史已載入'):'官方行情待取得';
   $('notice').textContent=(latest?'資料日：'+latest.date+'；兩市同日驗證。各資訊區另列實際資料日及覆蓋率。':'官方行情資料尚未取得；各資訊區獨立更新。')+
    (s?.ok===false?'｜行情更新失敗，保留上次資料。':'')+(s?.state==='stale'?'｜官方行情日期落後於執行日。':'')+
    (s?.at?'｜最近檢查 '+s.at.slice(0,16).replace('T',' '):'');
 }
 load();setInterval(load,120000);
})();
