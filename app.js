const tg=window.Telegram?.WebApp;
if(tg){tg.ready();tg.expand();}

const state={crystals:0,avatar:"🧙",sync:null};
const screens=[...document.querySelectorAll('.screen')], navs=[...document.querySelectorAll('.nav')], toastEl=document.getElementById('toast');

function showScreen(name){screens.forEach(s=>s.classList.toggle('active',s.id===name)); navs.forEach(n=>n.classList.toggle('active',n.dataset.action===name)); window.scrollTo({top:0,behavior:'smooth'});}
function notify(t){if(!toastEl)return; toastEl.textContent=t; toastEl.classList.add('show'); clearTimeout(window.__toast); window.__toast=setTimeout(()=>toastEl.classList.remove('show'),2400);}

function apiHeaders(){
  const h={'Content-Type':'application/json'};
  const initData=tg?.initData || '';
  if(initData) h['X-Telegram-Init-Data']=initData;
  return h;
}

async function apiFetch(path,opts={}){
  const res=await fetch(path,{...opts,headers:{...apiHeaders(),...(opts.headers||{})}});
  if(!res.ok){const txt=await res.text(); throw new Error(txt||`HTTP ${res.status}`);}
  return res.json();
}

function fmtNum(v){
  try{return BigInt(String(v??0)).toLocaleString('ru-RU');}
  catch{return Number(v||0).toLocaleString('ru-RU');}
}
function renderProfile(data){
  const p=data.player||{}, pvp=data.pvp||{}, avatar=p.avatar_key||"🧙";
  ['profileAvatar','homeAvatar','previewAvatar','miniAvatar','battlePlayerAvatar'].forEach(id=>{const el=document.getElementById(id);if(el)el.textContent=avatar;});
  document.querySelectorAll('.avatar-choice').forEach(b=>b.classList.toggle('selected',b.dataset.avatar===avatar));
  const set=(id,v)=>{const el=document.getElementById(id);if(el)el.textContent=v;};
  set('profileNameHome',p.first_name||'Игрок'); set('profileSubHome',`Уровень ${p.level||1} · ${p.rank||'Новичок'}`);
  set('homeLevel',`LVL ${p.level||1}`); set('homeXpText',`${fmtNum(p.xp)} / ${fmtNum(p.xp_needed)} XP`);
  set('bpLevelHome',p.bp_level||0); set('bpPercent',`${p.bp_level||0}%`); set('crystalBalance',fmtNum(p.crystals));
  const large=document.getElementById('crystalBalanceLarge');if(large)large.textContent=fmtNum(p.crystals);
  set('profileName',p.first_name||'Игрок');set('profileRank',`Уровень ${p.level||1} · ${p.rank||'Новичок'}`);
  set('xpText',`${fmtNum(p.xp)} / ${fmtNum(p.xp_needed)} XP`);
  set('statDcr',fmtNum(p.dcr));set('statCrystals',fmtNum(p.crystals));set('statMmr',pvp.mmr||0);
  set('statMmrRank',`${pvp.rank?.emoji||''} ${pvp.rank?.name||'—'}`);set('statWl',`${pvp.ranked_wins||0} / ${pvp.ranked_losses||0}`);set('statStreak',pvp.current_streak?`Серия: ${pvp.current_streak}`:'');
  const width=Math.min(100,p.xp_progress||0); const hb=document.getElementById('homeXpBar');if(hb)hb.style.width=`${width}%`;const xb=document.getElementById('xpBar');if(xb)xb.style.width=`${width}%`;
  const bb=document.getElementById('bpBarHome');if(bb)bb.style.width=`${Math.min(100,Number(p.bp_level||0))}%`;
  const eq=data.equipment||{};const el=document.getElementById('equipList');if(el)el.innerHTML=`<div>⚔️ <span>${eq.weapon?.name||'Не экипировано'}</span></div><div>🛡️ <span>${eq.armor?.name||'Не экипировано'}</span></div><div>🐺 <span>${eq.pet?.name||'Нет питомца'}</span></div>`;
  set('battleName',(p.first_name||'ИГРОК').toUpperCase());set('battleLvl',`LVL ${p.level||1}`);set('bpLevel',p.bp_level||0);
  const log=document.getElementById('combatLog');if(log)log.textContent=`Синхронизация DOMINION активна · MMR: ${pvp.mmr||0}`;
  state.crystals=p.crystals||0;state.avatar=avatar;
}

async function loadBootstrap(){
  try{
    const data=await apiFetch('/api/me/bootstrap');
    state.sync=data; renderProfile(data.profile);
    notify('DOMINION синхронизирован ✓');
  }catch(e){console.error(e);const log=document.getElementById('combatLog');if(log)log.textContent='Синхронизация: '+e.message;notify('Не удалось подключиться к DOMINION');}
}

async function setAvatar(av){
  // Avatar write endpoint will be enabled after the read-only synchronization layer is verified.
  state.avatar=av;
  document.querySelectorAll('.avatar-choice').forEach(b=>b.classList.toggle('selected',b.dataset.avatar===av));
  ['profileAvatar','homeAvatar','previewAvatar','miniAvatar','battlePlayerAvatar'].forEach(id=>{const el=document.getElementById(id);if(el)el.textContent=av;});
  notify('Выбор аватара подготовлен');
}

let enemy=72;
function attack(skill=false){enemy=Math.max(0,enemy-(skill?8:5));const hp=document.getElementById('enemyHp');if(hp)hp.style.width=enemy+'%';const log=document.getElementById('combatLog');if(log){log.classList.remove('hit');void log.offsetWidth;log.classList.add('hit');log.textContent=skill?'✨ Крит!':'⚔️ Атака';}if(enemy===0){enemy=100;setTimeout(()=>{if(hp)hp.style.width='100%';},900);}}

document.addEventListener('click',e=>{
  const av=e.target.closest('[data-avatar]');if(av){setAvatar(av.dataset.avatar);return;}
  const el=e.target.closest('[data-action]');if(!el)return;const a=el.dataset.action;
  if(['profile','home','pass','crystals','privileges','battle'].includes(a))showScreen(a);
  if(a==='demoBattle')showScreen('battle'); if(a==='attack')attack(false);if(a==='skill')attack(true);
});

loadBootstrap();
