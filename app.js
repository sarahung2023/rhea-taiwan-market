'use strict';
let dashboard={status:'awaiting_data',days:[],dates:[]};
let kind='custom';
let selected=null;
let lastFetchError='';
let alerts={items:{},errors:{}};let alertKind='disposal';let lastRun=null;
const $=id=>document.getElementById(id);
const escapeHTML=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=(v,d=2)=> Number(v).toFixed(d);
const sign=v=>v>0?'+':'';
const cssVal=v=>v>=0?'pos':'neg';
function getGroups(){let out=new Map();for(const day of dashboard.days||[])for(const [id,g] of Object.entries(day.sectors||{})){if(g.type===kind)out.set(id,{id,name:g.name,type:kind,n:g.n})}return [...out.values()];}
function rankCount(id){return (dashboard.days||[]).filter(d=>d.sectors?.[id]?.rank<=5).length;}
function latest(id){return dashboard.days?.at(-1)?.sectors?.[id];}
function fmtDate(s){return s? (s.startsWith('示例')?s:s.slice(5).replace('-','/')): '—';}
function render(){
 const demo=dashboard.demo;
 $('mode').className='pill '+(demo?'demo':dashboard.status==='ok'?'':'muted');
 $('mode').textContent=demo?'DEMO｜虛構資料':dashboard.status==='ok'?'官方歷史已載入':'資料待建立';
 $('notice').className='notice '+(demo?'demo':'');
 $('notice').textContent=demo?'這是版面功能示範；全部數字都是虛構假資料，不能作行情分析或交易依據。':dashboard.status==='ok'?'資料日：'+dashboard.dates.at(-1)+'；每日以兩市同一個有效交易日入庫。自訂族群為代表股觀察籃，不能代表全體產業。':'尚無雙市場同日驗證成功的官方歷史。部署GitHub排程後才會累積真實資料；不足5個交易日會顯示實際已累積日數。';
 if(lastFetchError && !demo) $('notice').textContent+='｜最新更新未通過驗證，保留先前資料（詳情見狀態）';
 if(lastRun?.state==='stale'&&!demo)$('notice').textContent+='｜官方資料日期落後於執行日。';
 if(lastRun?.at&&!demo)$('notice').textContent+='｜最近檢查 '+lastRun.at.slice(0,16).replace('T',' ');
 const days=dashboard.days||[];const latestDay=days.at(-1);
 $('latestDate').textContent=demo?'DEMO':latestDay?.date||'—';
 $('countDays').textContent=`${days.length} / 5`;
 const topCustom=latestDay?Object.values(latestDay.sectors||{}).filter(x=>x.type==='custom').sort((a,b)=>b.avg-a.avg)[0]:null;
 $('topTheme').textContent=topCustom?.name||'—';
 $('coverage').textContent=demo?'測試':'—';
 if(!demo && latestDay?.coverage) $('coverage').textContent=`${latestDay.coverage.TWSE}＋${latestDay.coverage.TPEx}`;
 document.querySelectorAll('#tabs button').forEach(b=>b.classList.toggle('active',b.dataset.kind===kind));
 const dates=dashboard.dates||[];
 $('head').innerHTML='<tr><th>族群 / 樣本</th>'+dates.map(x=>'<th>'+escapeHTML(fmtDate(x))+'</th>').join('')+'<th>前5名出現</th><th>日均漲幅</th></tr>';
 if(!days.length){$('body').innerHTML='<tr><td colspan="8" class="blank">尚無正式資料。點右上可預覽虛構示意畫面。</td></tr>';$('topList').innerHTML='<div class="empty">等待官方收盤資料</div>';$('detail').innerHTML='<div class="empty">尚無資料</div>';return;}
 let groups=getGroups();const search=$('filter').value.trim().toLowerCase();groups=groups.filter(g=>g.name.toLowerCase().includes(search)||g.id.toLowerCase().includes(search));
 function rotation(id){const r=days.map(d=>d.sectors?.[id]?.rank<=5);if(r.length<2)return '';if(r.at(-1)&&r.at(-2))return '持續在榜';if(r.at(-1)&&!r.at(-2))return '新入榜';if(!r.at(-1)&&r.slice(0,-1).some(Boolean))return '已退榜';return '';}
 function mean(id){let r=days.map(d=>d.sectors?.[id]?.avg).filter(x=>typeof x==='number');return r.length?r.reduce((a,b)=>a+b,0)/r.length:-999;}
 const sort=$('sort').value;
 groups.sort((a,b)=>sort==='appear'?(rankCount(b.id)-rankCount(a.id)||((latest(a.id)?.rank??999)-(latest(b.id)?.rank??999))):sort==='latest'?((latest(a.id)?.rank??999)-(latest(b.id)?.rank??999)):mean(b.id)-mean(a.id));
 $('body').innerHTML=groups.map(g=>{
 const a=days.map(d=>{const x=d.sectors?.[g.id];return x?`<td><div class="cell"><span class="v ${cssVal(x.avg)}">${sign(x.avg)}${num(x.avg)}%</span>${x.rank<=5?'<span class="star">★</span>':''}</div></td>`:'<td class="none">—</td>'}).join('');
 return `<tr class="${selected===g.id?'selected':''}" data-id="${escapeHTML(g.id)}"><td>${escapeHTML(g.name)}${rotation(g.id)?'<span class="n">'+rotation(g.id)+'</span>':''}<span class="n">最新有效 ${latest(g.id)?.n??'—'} 檔 · ${kind==='custom'?'觀察籃':'官方分類'}</span></td>${a}<td><span class="badge-num">${rankCount(g.id)}/${days.length}</span></td><td class="${cssVal(mean(g.id))}">${sign(mean(g.id))}${num(mean(g.id))}%</td></tr>`;
 }).join('')||'<tr><td colspan="8" class="blank">此分類沒有符合條件的有效樣本</td></tr>';
 document.querySelectorAll('#body tr[data-id]').forEach(el=>el.addEventListener('click',()=>{selected=el.dataset.id;render()}));
 const todays=Object.entries(latestDay.sectors).filter(([_,g])=>g.type===kind).sort((a,b)=>b[1].avg-a[1].avg).slice(0,5);
 $('dayTitle').textContent=latestDay.date+' · '+(kind==='custom'?'自訂觀察籃':'官方大類');
 $('topList').innerHTML=todays.map(([id,g],i)=>`<div class="leader" role="button" tabindex="0" data-id="${escapeHTML(id)}"><span class="rank">${i+1}</span><div class="l-name">${escapeHTML(g.name)}<small>${g.n} 檔｜上漲${g.up}/${g.n}｜上漲占比${g.breadth}%</small></div><b class="${cssVal(g.avg)}">${sign(g.avg)}${num(g.avg)}%</b></div>`).join('');
 document.querySelectorAll('.leader[data-id]').forEach(el=>{const f=()=>{selected=el.dataset.id;render()};el.onclick=f;el.onkeydown=e=>{if(e.key==='Enter')f()}});
 const info=latest(selected);if(!info||info.type!==kind){$('detail').innerHTML='<div class="empty">點選族群查看最新日成員漲跌</div>';return;}
 $('detail').innerHTML=`<div class="info"><b>${escapeHTML(info.name)}</b><div>最新日均漲幅 ${sign(info.avg)}${num(info.avg)}%，上漲 ${info.up}/${info.n} 檔；這是等權平均，不代表每支股票都強。${kind==='custom'?' 本籃預設'+info.basket_n+'檔。':''}</div></div>${kind==='custom'?'<div class="warning">自訂族群屬人工固定的代表股觀察籃，非完整產業。成員類別與涵蓋率尚需逐檔人工核對。</div>':''}${(info.members||[]).map(s=>`<div class="member"><span><small>${escapeHTML(s.code)}</small>${escapeHTML(s.name)}</span><b class="${cssVal(s.pct)}">${sign(s.pct)}${num(s.pct)}%</b></div>`).join('')}`;
}
function fake(){
 const groups=[['LED（觀察籃）','custom'],['PCB製造（觀察籃）','custom'],['工具機（觀察籃）','custom'],['機殼／外觀件（觀察籃）','custom'],['面板（觀察籃）','custom'],['偏光板（觀察籃）','custom'],['官方產業 24','official'],['官方產業 25','official'],['官方產業 26','official'],['官方產業 27','official'],['官方產業 28','official'],['官方產業 29','official']];
 const vals=[[0.8,1.2,0.4,-0.3,1.5],[2.1,1.6,2.2,-0.4,0.2],[-0.3,0.8,1.9,2.5,1.8],[1.5,-0.7,0.2,1.6,-0.4],[0.2,0.6,-0.3,0.4,0.7],[0.4,0.1,0.8,-0.2,1.1],[1.6,1.0,-0.1,0.9,0.3],[0.5,0.2,0.9,-0.6,1.3],[-0.4,1.4,1.6,-0.2,0.3],[0.3,-0.2,0.1,1.7,1.9],[1.1,0.5,-0.8,0.1,0.9],[-0.2,0.3,0.7,1.0,0.5]];
 const dates=['示例-1','示例-2','示例-3','示例-4','示例-5'];
 let days=dates.map((date,d)=>({date,coverage:{TWSE:0,TPEx:0},sectors:Object.fromEntries(groups.map(([name,type],i)=>[`${type}-${i}`,{name,type,n:type==='custom'?4:100,up:3,breadth:75,avg:vals[i][d],members:[{code:'示例',name:'假資料',pct:vals[i][d]}]}]))}));
 for(const day of days)for(const type of ['custom','official'])Object.values(day.sectors).filter(g=>g.type===type).sort((a,b)=>b.avg-a.avg).forEach((g,i)=>g.rank=i+1);
 dashboard={status:'ok',demo:true,days,dates};selected=null;render();renderAlerts();
}
function renderAlerts(){
 document.querySelectorAll('#alertTabs button').forEach(b=>b.classList.toggle('active',b.dataset.alert===alertKind));
 if(dashboard.demo){$('alertStamp').textContent='DEMO模式不顯示虛構公告';$('alertList').innerHTML='<div class="empty">示意模式下停用官方公告面板</div>';return;}
 $('alertStamp').textContent=alerts.as_of_fetch?'來源最近查詢：'+alerts.as_of_fetch.slice(0,16).replace('T',' ')+'（公告生效日期需查官方）':'官方公告尚未擷取';
 let cards=[];
 for(const m of ['TWSE','TPEx']){
 const id=m+'_'+alertKind; const entry=alerts.items?.[id];
 if(!entry){cards.push('<div class="alert-box">'+(m==='TWSE'?'上市':'上櫃')+'：尚無可用公告快照（請到官方網站查詢）</div>');continue;}
 if(!entry.rows?.length){cards.push('<div class="alert-box">'+(m==='TWSE'?'上市':'上櫃')+'：未解析出可用公告代號；不代表當天沒有公告。 <a href="'+escapeHTML(entry.source)+'" target="_blank" rel="noopener">查原文</a></div>');continue;}
 cards.push(...entry.rows.slice(0,12).map(r=>'<div class="alert-box"><span class="chip">'+(r.market==='TWSE'?'上市':'上櫃')+'</span><b>'+escapeHTML(r.code)+' '+escapeHTML(r.name||'')+'</b><small>官方欄位日期：'+escapeHTML(r.raw_date||'未提供／未解析')+'</small><a href="'+escapeHTML(entry.source)+'" target="_blank" rel="noopener">核對官方公告及生效期間</a></div>'));
 }
 $('alertList').innerHTML=cards.join('');
}
document.querySelectorAll('#alertTabs button').forEach(b=>b.onclick=()=>{alertKind=b.dataset.alert;renderAlerts()});
document.querySelectorAll('#tabs button').forEach(b=>b.onclick=()=>{kind=b.dataset.kind;selected=null;render()});$('filter').oninput=render;$('sort').onchange=render;$('demoBtn').onclick=fake;
(async()=>{try{const r=await fetch('./data/dashboard.json?ts='+Date.now(),{cache:'no-store'});if(r.ok){const j=await r.json();if(j.status==='ok'&&j.days?.length)dashboard=j;}const st=await fetch('./data/status.json?ts='+Date.now(),{cache:'no-store'});if(st.ok){const v=await st.json();lastRun=v;if(v.ok===false && v.error)lastFetchError=v.error;}
 const a=await fetch('./data/alerts.json?ts='+Date.now(),{cache:'no-store'});if(a.ok)alerts=await a.json();}catch(e){/* file:// offline preview: use demo button */}render();renderAlerts()})();
