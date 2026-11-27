/* AEP public descriptive proxy; no market or trading direction signals. */
(() => {
 'use strict';
 const $=id=>document.getElementById(id);
 if(!$('aepPanel'))return;
 const fmt=(n,s='')=>Number.isFinite(n)?(n>0?'+':'')+n.toFixed(2)+s:'—';
 const val=(n)=>Number.isFinite(n)?String(n):'—';
 const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 let dataset=null,selected=null,chosen=null;
 function reset(){
  for(const id of ['aepBreadth','aepThree','aepFlowRate','aepHoldBreadth'])$(id).textContent='—';
  $('aepFlowAmount').textContent='單位差 × 前日NAV，非實收付';
  $('aepCopy').disabled=true;
  chosen=null;
 }
 function render(){
  reset();
  paintScope();
  paintOfficial();
  paintHoldings();
  const rows=Array.isArray(dataset?.rows)?dataset.rows:[];
  const row=rows.find(x=>x.date===selected)||rows.at(-1);
  $('aepStatus').className='pill muted';
  $('aepStatus').textContent=dataset?.state==='error'?'來源更新失敗 · 保留歷史':!row?'WAIT DATA':row.state==='complete'?'完整 · 研究觀察':'WAIT DATA · 未齊';
  $('aepClock').textContent='本站市場日期：'+(dataset?.market_date||'—')+'｜最近檢查：'+(dataset?.checked_at||'—')+'｜證交所快報與同日PCF（含投信補抓）分列，不混用。'+(dataset?.last_error?'｜'+dataset.last_error:'');
  $('aepRows').innerHTML=rows.length?rows.slice().reverse().map(r=>'<tr><td>'+esc(r.date)+'</td><td>'+esc(r.n)+'/'+esc(r.expected)+'</td><td>'+[r.plus,r.minus,r.flat].map(val).join(' / ')+'</td><td>'+fmt(r.aep1,'pp')+'</td><td>'+fmt(r.flow_100m)+'</td><td>'+fmt(r.hold_breadth,'pp')+'</td><td>'+ (r.locked?'已鎖定':r.state==='complete'?'無盤前快照':'WAIT')+'</td></tr>').join(''):'<tr><td colspan="7" class="blank">等待資料</td></tr>';
  if(!row){$('aepCoverage').textContent='—';$('aepDetail').textContent='尚無可驗證資料。';return;}
  $('aepCoverage').textContent='同日有效 '+row.n+'/'+row.expected+' 檔｜非全市場';
  $('aepMissing').textContent='缺漏：'+(Object.entries(row.missing||{}).map(([k,v])=>k+' '+v).join('；')||'無／尚未建立')+'｜固定排除：00996A；來源其他代號：'+(dataset.extra_codes||[]).join('、');
  if(row.state!=='complete'&&!row.locked){
   $('aepDetail').textContent='未齊，不能發表完整廣度或申贖比。已配對部分：單位增／減／平 '+[row.plus,row.minus,row.flat].map(val).join('/')+'；暫估淨額 '+fmt(row.partial_flow_100m,'億')+'，不可與完整母體比較。';
   $('aepCopyStatus').textContent='未完整，不提供Excel登記列。';
   return;
  }
  const item=row.locked||row;
  chosen=item;
  $('aepBreadth').textContent=fmt(item.aep1,'pp');
  $('aepThree').textContent=fmt(item.aep3,'pp');
  $('aepFlowRate').textContent=fmt(item.flow_pct,'%');
  $('aepFlowAmount').textContent=fmt(item.flow_100m,'億')+'｜估算，非實收付';
  $('aepHoldBreadth').textContent=fmt(item.hold_breadth,'pp');
  $('aepDetail').textContent='資料日 '+item.date+'｜前日 '+item.previous_date+'｜單位增／減／平 '+[item.plus,item.minus,item.flat].join('/')+'｜股數增／減／平 '+[item.hold_up,item.hold_down,item.hold_flat].join('/')+'｜至少2檔ETF同向減股 '+item.sync_reduce+' 股｜取得 '+item.observed_at+'｜'+(row.locked?'08:30前鎖定版（仍是研究資料）':'完整歷史描述（08:30後補齊者不作T+1前向）')+'｜版本數 '+(row.revision_count||1);
  if(row.locked&&row.observed_at!==row.locked.observed_at) $('aepDetail').textContent+='｜表格為最新修訂，卡片及複製為原鎖定版。';
  $('aepCopy').disabled=false;
  $('aepCopyStatus').textContent=row.locked?'複製08:30前原始鎖定版':'複製歷史描述列（不可當T+1前向）';
 }
 function paintOfficial(){
  const el=$('aepOfficial');
  if(!el)return;
  const r=dataset?.official_flow;
  if(!r){el.textContent='證交所申贖快報：等待首次採集。';return;}
  const n=r.n||0;
  const funds=Object.entries(r.details||{}).sort((a,b)=>a[1].estimate-b[1].estimate);
  el.innerHTML='<strong>證交所官方申贖快報｜'+esc(r.date)+'｜'+esc(n)+'/'+esc(r.expected)+'檔</strong><br>'+
   (n?'估算淨申贖 '+fmt(r.state==='complete'?r.flow_100m:r.partial_flow_100m,'億')+'｜贖回 '+fmt(r.redeem_100m,'億')+'｜申購 '+fmt(r.subscribe_100m,'億')+'｜增／減／平 '+[r.plus,r.minus,r.flat].map(val).join('/'):'當日資料未取得')+
   (r.state==='complete'?'｜完整固定母體':'｜部分樣本，非全母體')+
   '<br>前五大贖回：'+(funds.filter(x=>x[1].estimate<0).slice(0,5).map(([k,v])=>esc(k)+' '+fmt(v.estimate/1e8,'億')).join('；')||'—')+
   '<br>來源：<a href="https://mis.twse.com.tw/stock/data/all_etf.txt" target="_blank" rel="noopener">證交所MIS</a>｜取得 '+esc(r.observed_at)+'｜缺漏 '+esc(Object.keys(r.missing||{}).join('、')||'無／未取得')+
   '<br>單位差×前日NAV，非現金實收付；持股與現金水位不由此接口推算。';
 }
 function paintHoldings(){
  const el=$('aepHoldingsExtra');
  if(!el)return;
  const s=dataset?.descriptive;
  if(!s){el.textContent='持股減碼排行：等待首次更新。';return;}
  const funds=(s.funds||[]).filter(x=>x.flow_100m<0).slice(0,5);
  const unknown=(s.funds||[]).reduce((n,x)=>n+(x.unpriced_changes||0),0);
  el.innerHTML='<strong>持股異動觀察｜'+esc(s.date)+'｜'+esc(s.n)+'/'+esc(s.expected)+'檔</strong><br>'+
   'PCF持股與單位變化（非證交所快報、非實際成交）｜'+(s.state==='complete'?'完整配對':'部分配對')+
   '<br>PCF估算贖回前五：'+(funds.map(x=>esc(x.code)+' '+fmt(x.flow_100m,'億')+'（增股估值 '+fmt(x.hold_increase_100m,'億')+'／減股估值 '+fmt(x.hold_decrease_100m,'億')+'）').join('；')||'—')+
   '<br>贖回ETF減股估值前五：'+((s.top_reduced||[]).map(x=>esc(x.code)+' '+esc(x.name)+' '+fmt(x.value_100m,'億')+'（'+x.etfs.length+'檔）').join('；')||'—')+
   '<br>未取得同日股價的異動 '+unknown+' 筆，不納入金額；缺漏 '+esc((s.missing||[]).join('、')||'無')+
   '<br>實際現金水位及贖回支應天數：待官方現金資料；不以非股票比例替代。'+
   '<br>取得 '+esc(s.observed_at)+'｜僅描述，不改原研究序列。'+
   (Object.keys(s.issuer_errors||{}).length?'<br>投信補抓未取得：'+esc(Object.entries(s.issuer_errors).map(([k,v])=>k+' '+v).join('；')):'');
 }
 function paintScope(){
  const el=$('aepScope');
  if(!el)return;
  const s=dataset?.current_scope;
  if(!s){el.textContent='當期來源母體：等待首次自動取得；固定25檔歷史不受影響。';return;}
  const a=(s.added_vs_fixed||[]).join('、')||'無',b=(s.absent_vs_fixed||[]).join('、')||'無';
  const changed=a!=='無'||b!=='無';
  el.textContent='當期來源母體 '+s.expected+' 檔｜有效配對 '+s.n+'/'+s.expected+'｜資料日 '+s.date+'｜名單版本 '+s.roster_id+'｜'+
   (s.state==='complete'?'廣度 '+fmt(s.aep1,'pp')+'、估算淨申贖 '+fmt(s.flow_100m,'億')+'、持股減碼廣度 '+fmt(s.hold_breadth,'pp'):'WAIT DATA（未齊不計）')+
   '｜較固定25檔新增：'+a+'；退出／未追蹤：'+b+(changed?'｜名單變動：待審查，不接續固定歷史':'')+'｜僅描述上游追蹤母體，非全市場，不作T+1前向。';
 }
 async function load(){
  try{
   const res=await fetch('./data/aep.json?t='+Date.now(),{cache:'no-store'});
   if(!res.ok)throw Error('no AEP data');
   const x=await res.json();
   if(x.version!=='AEP-B25-v0.1-20261125')throw Error('version mismatch');
   dataset=x;
   const rows=Array.isArray(x.rows)?x.rows:[];
   if(!rows.some(r=>r.date===selected))selected=rows.at(-1)?.date||null;
   $('aepDate').innerHTML=rows.length?rows.slice().reverse().map(r=>'<option value="'+esc(r.date)+'">'+esc(r.date)+'</option>').join(''):'<option>等待資料</option>';
   $('aepDate').disabled=!rows.length;
   if(selected)$('aepDate').value=selected;
   render();
  }catch(e){$('aepStatus').textContent='WAIT DATA';$('aepClock').textContent='尚無可驗證ETF資料；其他市場資訊照常。';reset();}
 }
 $('aepDate').addEventListener('change',e=>{selected=e.target.value;render();});
 $('aepCopy').addEventListener('click',async()=>{
  if(!chosen)return;
  const x=chosen;
  // Date, version, observed_at, clock status, denominator, direction counts, AEP1/AEP3 (pp), estimated flow, rate, raw holding breadth.
  const t=[x.date,x.version,x.observed_at,x.timely?'PIT_0830':'HIST_ONLY',x.n,x.plus,x.minus,x.flat,x.aep1,x.aep3??'',x.flow_100m,x.flow_pct,x.hold_breadth].join('\t');
  try{await navigator.clipboard.writeText(t);$('aepCopyStatus').textContent='已複製，含資料日期與時間資格。';}
  catch(e){$('aepCopyStatus').textContent='無法存取剪貼簿；可由表格手動抄錄。';}
 });
 load();setInterval(load,120000);
})();
