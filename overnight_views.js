/* Public descriptive overnight reversal study: no proprietary trading signals. */
(() => {
 'use strict';
 const $=id=>document.getElementById(id);
 const fmt=x=>Number.isFinite(x)?x.toFixed(2)+'%':'—';
 async function load(){
  const status=$('overnightStatus');if(!status)return;
  try{
   const response=await fetch('./data/overnight_proxy.json?t='+Date.now(),{cache:'no-store'});
   if(!response.ok)throw Error('no published proxy');
   const d=await response.json();
   const n=d.days_observed||0, ready=n===5;
   status.textContent=ready?'5/5交易日已累積':('WAIT DATA · '+n+'/5');
   status.className='pill '+(ready?'':'muted');
   $('overnightRate').textContent=fmt(d.event_pct);
   $('overnightDays').textContent=(d.event_days??0)+' / '+n+'日';
   $('overnightCoverage').textContent=(d.matched??0)+'筆';
   $('overnightBaseline').textContent=d.baseline_ready?fmt(d.previous_20day_event_pct):'WAIT DATA';
   $('overnightDescription').textContent='截至 '+(d.latest_date||'尚無有效日期')+'｜'+
     '符合 '+(d.events??0)+' / '+(d.matched??0)+' 股票日配對｜前日強勢且隔日跳高之候選 '+(d.eligible??0)+'筆。'+
     (ready?'近5日資料已齊。':'未滿5個完整合格配對日，不提供正式5日評級。');
   const bars=(d.days||[]).map(r=>{
    const pct=Number(r.event_pct)||0;
    const width=Math.max(0,Math.min(100,pct));
    return '<div class="overnight-line"><span>'+String(r.date).replace(/-/g,'/')+
      '</span><div class="track"><div class="fill" style="width:'+width+'%"></div></div><span>'+
      (r.events||0)+'/'+(r.matched||0)+' · '+pct.toFixed(2)+'%</span></div>';
   });
   $('overnightBars').innerHTML=bars.length?bars.join(''):'<div class="empty">等待新的有效跨日配對</div>';
  }catch(e){
   status.textContent='WAIT DATA';
   $('overnightDescription').textContent='目前尚無可驗證的官方開盤價及跨日逐檔配對，不能計算隔日沖密度。';
   $('overnightBars').innerHTML='<div class="empty">資料尚未建立；原有公開族群排名仍可正常查看</div>';
  }
 }
 load();
 setInterval(load,120000);
})();