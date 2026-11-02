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
   const n=d.days_observed||0, ready=n===5 && d.status==='ok' && d.version==='high-turnover-v1-20261102';
   status.textContent=ready?'5/5交易日已累積':('WAIT DATA · '+n+'/5');
   status.className='pill '+(ready?'':'muted');
   $('overnightRate').textContent=ready?fmt(d.high_density_pct):'WAIT DATA';
   $('overnightDays').textContent=ready?((d.very_high_count??0)+'筆'):'—';
   $('overnightCoverage').textContent=ready?((d.cohort_count??0)+'筆'):'—';
   $('overnightBaseline').textContent=ready?fmt(d.fade_pct):'WAIT DATA';
   $('overnightDescription').textContent='截至 '+(d.latest_date||'尚無有效日期')+'｜'+
     (ready?'高週轉股池 '+d.cohort_count+' 股票日／有效跨日配對 '+d.matched+
        '筆；開高走低 '+fmt(d.fade_pct)+'、開高續強 '+fmt(d.continuation_pct)+
        '；前20日事件基準 '+(d.baseline_ready?fmt(d.previous_20day_event_pct):'WAIT DATA')+'。':
        '近5日資料尚未齊全，不能報出密集度或強弱比例。');
   const bars=(d.days||[]).map(r=>{
    const pct=r.matched?100*(r.fades||0)/r.matched:0;
    const width=Math.max(0,Math.min(100,pct));
    return '<div class="overnight-line"><span>'+String(r.date).replace(/-/g,'/')+
      '</span><div class="track"><div class="fill" style="width:'+width+'%"></div></div><span>'+
      '開高走低 '+(r.fades||0)+'/'+(r.matched||0)+' · '+pct.toFixed(2)+'%</span></div>';
   });
   $('overnightBars').innerHTML=ready?bars.join(''):'<div class="empty">資料未滿5日，等待高週轉股池跨日配對</div>';
  }catch(e){
   status.textContent='WAIT DATA';
   $('overnightDescription').textContent='目前尚無可驗證的官方開盤價及跨日逐檔配對，不能計算隔日沖密度。';
   $('overnightBars').innerHTML='<div class="empty">資料尚未建立；原有公開族群排名仍可正常查看</div>';
  }
 }
 load();
 setInterval(load,120000);
})();