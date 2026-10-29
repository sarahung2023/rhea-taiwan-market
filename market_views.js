/* Public external market views v1.1: two distinct clocks, no private trading inputs. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, v => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[v]));
  const fmt = v => typeof v === 'number' && Number.isFinite(v) ? (v>0?'+':'')+v.toFixed(2)+'%' : '—';
  const cls = v => v>0?'pos':v<0?'neg':'';
  let history=null, intraday=null, category='custom', focus='all', selected=null;
  const rows = day => Object.entries(day?.sectors || {}).filter(([id,g]) => g && g.type===category && Number.isFinite(g.avg));
  const byStrength = day => rows(day).sort((a,b)=>b[1].avg-a[1].avg);
  const byWeakness = day => rows(day).sort((a,b)=>a[1].avg-b[1].avg);
  const cacheFetch = async path => {
    const r=await fetch(path+'?r='+Date.now(),{cache:'no-store'});
    if(!r.ok) throw Error('資料檔無法載入');
    return r.json();
  };
  function badge(g,kind) {
    const n=g?.n??0;
    const label=(g?.type==='custom'?'觀察籃':'官方分類');
    return esc(label)+' · '+n+'檔';
  }
  function paintIntraday(){
    const state=$('liveStatus'), moment=$('liveStamp'), up=$('liveStrong'), dn=$('liveWeak'), detail=$('liveMembers');
    if(!state) return;
    const good=intraday?.status==='ok' && intraday?.time && intraday?.date && intraday?.sectors &&
      Object.keys(intraday.sectors).length>=10 && intraday?.coverage?.TWSE>=800 && intraday?.coverage?.TPEx>=600;
    if(!good){
      state.textContent='尚未連接合法的雙市場盤中逐股資料源';
      state.className='pill muted';
      moment.textContent='盤中介面已建立，資料尚未啟用；不得把昨日收盤排行當作即時盤中強弱。';
      up.innerHTML=dn.innerHTML='<div class="empty">等待授權盤中資料源及實際驗收</div>';
      detail.innerHTML='<div class="empty">盤中股票清單尚無經驗證數據</div>';
      return;
    }
    const t=new Date(intraday.time);
    const age=(Date.now()-t.getTime())/60000;
    const validClock=Number.isFinite(age) && age>=-3 && age<=30;
    const currentTPE=new Date().toLocaleDateString('sv-SE',{timeZone:'Asia/Taipei'});
    const fresh=validClock && intraday.date===currentTPE;
    state.className='pill '+(fresh?'':'muted');
    state.textContent=fresh?'盤中快照｜非逐秒即時':'盤中快照已過期';
    moment.textContent='報價時間：'+esc(intraday.time.replace('T',' '))+'｜涵蓋上市'+intraday.coverage.TWSE+'檔＋上櫃'+intraday.coverage.TPEx+'檔｜'+(fresh?'':'此快照不得作今日盤中判讀')+'｜來源：'+esc(intraday.source_label||'授權行情來源');
    if(!fresh){
      up.innerHTML=dn.innerHTML='<div class="empty">盤中資料已過期，停止顯示排名</div>';
      detail.innerHTML='<div class="empty">僅呈現有效且未逾時的資料</div>';
      return;
    }
    const all=Object.entries(intraday.sectors).filter(([id,g])=>g.type===category && Number.isFinite(g.avg));
    const winners=[...all].sort((a,b)=>b[1].avg-a[1].avg).slice(0,7);
    const losers=[...all].sort((a,b)=>a[1].avg-b[1].avg).slice(0,7);
    function entries(items,side){
      return items.map(([id,g],i)=>'<button class="mv-pick" data-sector="'+esc(id)+'"><span class="mv-rank">'+(i+1)+'</span><span class="mv-itemname">'+esc(g.name)+'<small>'+badge(g,category)+'</small></span><strong class="'+cls(g.avg)+'">'+fmt(g.avg)+'</strong></button>').join('');
    }
    up.innerHTML=entries(winners,'strong');
    dn.innerHTML=entries(losers,'weak');
    document.querySelectorAll('#intradayPanel .mv-pick').forEach(b=>b.addEventListener('click',()=>{
      selected=b.dataset.sector;paintMembers();
    }));
    if(!selected || !intraday.sectors[selected] || intraday.sectors[selected].type!==category) selected=winners[0]?.[0]||null;
    paintMembers();
  }
  function paintMembers(){
    const detail=$('liveMembers'), sector=intraday?.sectors?.[selected];
    if(!detail || !sector){if(detail)detail.innerHTML='<div class="empty">點選盤中族群查看成員</div>';return;}
    const members=[...(sector.members||[])].sort((a,b)=>b.pct-a.pct);
    const make=(stocks)=>stocks.map(s=>'<div class="mv-stock"><span>'+esc(s.code)+' '+esc(s.name)+' <small>'+esc(s.market||'')+'</small></span><strong class="'+cls(s.pct)+'">'+fmt(s.pct)+'</strong></div>').join('');
    detail.innerHTML='<div class="mv-membertitle">'+esc(sector.name)+'｜'+sector.n+'檔 · '+fmt(sector.avg)+' 等權</div>'+
      '<div class="mv-stockcols"><div><b>族群內較強個股</b>'+make(members.slice(0,8))+'</div><div><b>族群內較弱個股</b>'+make([...members].reverse().slice(0,8))+'</div></div>';
  }
  function paintFiveDay(){
    const head=$('mvHead'),body=$('mvBody'),strong=$('mvTodayStrong'),weak=$('mvTodayWeak'),desc=$('mvFiveDesc');
    if(!body)return;
    const days=history?.status==='ok' ? (history.days||[]) : [];
    if(!days.length){
      head.innerHTML='';body.innerHTML='<tr><td class="blank">尚無已核驗盤後行情</td></tr>';
      strong.innerHTML=weak.innerHTML='<div class="empty">等待盤後官方資料</div>';return;
    }
    const streakStrong=$('mvStrongStreak'), streakWeak=$('mvWeakStreak');
    if(streakStrong && streakWeak){
      const groups=new Map();
      for(const d of days) for(const [id,g] of rows(d)) groups.set(id,g.name);
      const ranked=days.map(d=>byStrength(d));
      const leaders=ranked.map(arr=>new Set(arr.slice(0,5).map(([id])=>id)));
      const laggards=days.map(d=>new Set(byWeakness(d).slice(0,5).map(([id])=>id)));
      const runs=(sets)=>[...groups].map(([id,name])=>{
        let n=0;
        for(let i=sets.length-1;i>=0&&sets[i].has(id);--i)n++;
        return {id,name,n,latest:days[days.length-1].sectors?.[id]?.avg};
      }).filter(x=>x.n>=2).sort((a,b)=>b.n-a.n || (sets===leaders?b.latest-a.latest:a.latest-b.latest));
      const show=items=>items.length?items.slice(0,12).map(g=>'<div class="mv-minirank"><span>'+esc(g.name)+' <small>連續 '+g.n+' 個已收錄交易日</small></span><b class="'+cls(g.latest)+'">'+fmt(g.latest)+'</b></div>').join(''):'<div class="empty">'+(days.length<2?'目前只有 '+days.length+' 個已收錄交易日，尚不能判定連續性':'目前沒有連續2個已收錄交易日入榜的族群')+'</div>';
      streakStrong.innerHTML=show(runs(leaders));
      streakWeak.innerHTML=show(runs(laggards));
    }
    const latest=days[days.length-1];
    desc.textContent='已建立 '+days.length+'/5 個有效盤後交易日｜最新 '+latest.date+'｜連續天數依現有完整交易日計算';
    const highs=days.map(d=>new Set(byStrength(d).slice(0,5).map(([id])=>id)));
    const lows=days.map(d=>new Set(byWeakness(d).slice(0,5).map(([id])=>id)));
    const groups=new Map(); for(const d of days)for(const [id,g] of rows(d))groups.set(id,{id,name:g.name,n:g.n});
    let values=[...groups.values()].map(g=>{
      const gains=highs.reduce((n,s)=>n+Number(s.has(g.id)),0);
      const losses=lows.reduce((n,s)=>n+Number(s.has(g.id)),0);
      const streak=(records)=>{let n=0;for(let i=records.length-1;i>=0&&records[i].has(g.id);i--)n++;return n;};
      const today=latest.sectors[g.id]?.avg;
      return {...g,gains,losses,upStreak:streak(highs),downStreak:streak(lows),today};
    }).filter(g=>focus==='all'||(focus==='strong'?(g.gains>0):(g.losses>0)));
    values.sort((a,b)=>focus==='weak'?b.losses-a.losses||b.downStreak-a.downStreak||a.today-b.today:
      b.gains-a.gains||b.upStreak-a.upStreak||b.today-a.today);
    const dates=days.map(d=>'<th>'+esc(d.date.slice(5))+'</th>').join('');
    head.innerHTML='<tr><th>族群 / 有效檔數</th>'+dates+'<th>強榜次數</th><th>弱榜次數</th><th>連續強</th><th>連續弱</th></tr>';
    body.innerHTML=values.map(g=>'<tr><td><b>'+esc(g.name)+'</b><span class="n">'+esc(g.n)+'檔 · '+(category==='custom'?'代表股':'官方類別')+'</span></td>'+
      days.map((d,i)=>{const s=d.sectors?.[g.id];return '<td class="'+cls(s?.avg)+'">'+fmt(s?.avg)+(highs[i].has(g.id)?' <span class="star" title="強榜前五">★</span>':'')+(lows[i].has(g.id)?' <span class="mv-down" title="弱榜後五">▼</span>':'')+'</td>';}).join('')+
      '<td>'+g.gains+'/'+days.length+'</td><td>'+g.losses+'/'+days.length+'</td><td>'+g.upStreak+'</td><td>'+g.downStreak+'</td></tr>').join('');
    const mini=(items,isStrong)=>items.slice(0,5).map(([id,g])=>'<div class="mv-minirank"><span>'+esc(g.name)+' <small>('+esc(g.n)+'檔)</small></span><b class="'+cls(g.avg)+'">'+fmt(g.avg)+'</b></div>').join('');
    strong.innerHTML=mini(byStrength(latest),true);
    weak.innerHTML=mini(byWeakness(latest),false);
  }
  async function refresh(){
    try {history=await cacheFetch('./data/dashboard.json');}catch(e){}
    try {intraday=await cacheFetch('./data/intraday.json');}catch(e){intraday={status:'awaiting_authorized_feed'};}
    paintFiveDay();paintIntraday();
  }
  document.querySelectorAll('[data-mv-category]').forEach(btn=>btn.addEventListener('click',()=>{
    category=btn.dataset.mvCategory;selected=null;
    document.querySelectorAll('[data-mv-category]').forEach(x=>x.classList.toggle('active',x.dataset.mvCategory===category));
    paintFiveDay();paintIntraday();
  }));
  document.querySelectorAll('[data-mv-focus]').forEach(btn=>btn.addEventListener('click',()=>{
    focus=btn.dataset.mvFocus;
    document.querySelectorAll('[data-mv-focus]').forEach(x=>x.classList.toggle('active',x.dataset.mvFocus===focus));
    paintFiveDay();
  }));
  refresh();
  setInterval(refresh,120000);
})();