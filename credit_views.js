/* Official public credit dashboard, descriptive only. */
(()=>{'use strict';
const $=id=>document.getElementById(id);
if(!$('creditPanel'))return;
const num=(x,d=0)=>Number.isFinite(x)?x.toLocaleString('zh-TW',{minimumFractionDigits:d,maximumFractionDigits:d}):'—';
const pct=x=>Number.isFinite(x)?num(x,2)+'%':'—';
const ch=x=>Number.isFinite(x)?(x>0?'+':'')+pct(x):'—';
const txt=(id,s)=>$(id).textContent=s;
function paint(x){
 const rows=Array.isArray(x.rows)?x.rows:[], r=rows.at(-1);
 txt('creditStatus',x.state==='ok'?'已取得 · 研究觀察':x.state==='stale'?'WAIT DATA · 保留前日':'來源異常 · 保留歷史');
 txt('creditClock','市場日期：'+(x.market_date||'—')+'｜最新資料日：'+(x.latest_date||'—')+'｜最近檢查：'+(x.checked_at||'—')+'｜已累積 '+(x.history_count||0)+' 日'+(r?'｜最新資料取得：'+r.observed_at:'')+(x.errors?.length?'｜'+x.errors.join('；'):''));
 if(r){
 txt('creditKeep',pct(r.keepRate));txt('creditMargin',num(r.marginAccNum));txt('creditMarginCh','日變動 '+ch(r.marginAccChangePct));
 txt('creditBelow',num(r.belowAccNum));txt('creditBelowCh','日變動 '+ch(r.belowAccChangePct));
 txt('creditCallExe',num(r.callAccNum)+'／'+num(r.exeAccNum));
 }
 const body=$('creditRows');body.replaceChildren();
 if(!rows.length){const tr=body.insertRow();const td=tr.insertCell();td.colSpan=10;td.textContent='等待資料';return;}
 for(const v of rows.slice().reverse()){
 const tr=body.insertRow();
 for(const s of [v.date,pct(v.keepRate),num(v.marginAccNum),ch(v.marginAccChangePct),num(v.belowAccNum),ch(v.belowAccChangePct),num(v.callAccNum),Number.isFinite(v.callAmt)?num(v.callAmt/1e8,2):'—',num(v.exeAccNum),Number.isFinite(v.exeAmt)?num(v.exeAmt/1e8,2):'—'])tr.insertCell().textContent=s;
 }
}
async function load(){try{const r=await fetch('./data/credit.json?t='+Date.now(),{cache:'no-store'});if(!r.ok)throw Error('feed');const x=await r.json();if(x.version!=='TWSE-credit-all-v1')throw Error('schema');paint(x);}catch(e){txt('creditStatus','WAIT DATA');txt('creditClock','讀取失敗，保留上次畫面；其他市場資訊不受影響。');}}
load();setInterval(load,120000);
})();
