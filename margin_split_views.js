/* Public market financing; estimated ratios, descriptive only. */
(()=>{'use strict';const $=id=>document.getElementById(id);if(!$('marginSplitPanel'))return;
const f=(x,d=2)=>Number.isFinite(x)?x.toLocaleString('zh-TW',{minimumFractionDigits:d,maximumFractionDigits:d}):'—';
const ch=(x,u)=>Number.isFinite(x)?(x>0?'+':'')+f(x)+u:'—';
const ratio=r=>Number.isFinite(r?.maintenance_pct)?f(r.maintenance_pct)+'%'+(r.reference_prices?.length?'*':''):'—';
const money=x=>Number.isFinite(x)?f(x/1e8):'—';
function paint(x){const rows=x.rows||[],r=rows.at(-1);$('marginSplitStatus').textContent=x.state==='ok'?'已取得 · 推算值':'WAIT DATA · 部分資料';$('marginSplitClock').textContent='市場日期：'+(x.market_date||'—')+'｜最新資料：'+(x.latest_date||'—')+'｜檢查：'+(x.checked_at||'—')+'｜累積 '+(x.history_count||0)+' 日'+(x.errors?.length?'｜'+x.errors.join('；'):'');
for(const k of ['TSE','OTC']){const m=r?.markets?.[k];$(k+'Ratio').textContent=ratio(m);$(k+'Balance').textContent=money(m?.balance_yuan)+' 億';$(k+'Change').textContent='日增減 '+(Number.isFinite(m?.change_yuan)?ch(m.change_yuan/1e8,'億'):'—')+' / '+ch(m?.balance_change_pct,'%');}
const body=$('marginSplitRows');body.replaceChildren();for(const row of rows.slice().reverse()){const tr=body.insertRow();let cols=[row.date];for(const k of ['TSE','OTC']){let m=row.markets?.[k];cols.push(ratio(m),ch(m?.maintenance_change_pp,'pp'),money(m?.balance_yuan),Number.isFinite(m?.change_yuan)?ch(m.change_yuan/1e8,''):'—',ch(m?.balance_change_pct,'%'));}for(const c of cols)tr.insertCell().textContent=c;}
if(!rows.length){const td=body.insertRow().insertCell();td.colSpan=11;td.textContent='等待官方資料';}
const m=r?.markets?.OTC;$('marginSplitNotes').textContent='* 無當日收盤價時，以櫃買次日參考價估值，非官方直接公布維持率。最新 OTC 參考價 '+(m?.reference_prices?.length??'—')+' 檔；仍缺價 '+(m?.missing_prices?.length??'—')+' 檔。缺價則維持率留白。TSE 金額精度千元、OTC 官方圖表精度0.01億。';}
async function load(){try{const r=await fetch('./data/margin_split.json?t='+Date.now(),{cache:'no-store'});if(!r.ok)throw Error('feed');const x=await r.json();if(x.version!=='margin-split-v1')throw Error('schema');paint(x);}catch(e){$('marginSplitStatus').textContent='WAIT DATA';}}load();setInterval(load,120000);
})();