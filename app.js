
const tg = window.Telegram?.WebApp;
if (tg) { tg.ready(); tg.expand(); }

const state = {
  crystals: 0,
  avatar: "🧙",
  profile: null,
  prices: { starter: ["Набор новичка",330] }
};

const screens = [...document.querySelectorAll('.screen')];
const navs = [...document.querySelectorAll('.nav')];
const toastEl = document.getElementById('toast');

function showScreen(name){
  screens.forEach(s=>s.classList.toggle('active', s.id===name));
  navs.forEach(n=>n.classList.toggle('active', n.dataset.action===name));
  window.scrollTo({top:0, behavior:'smooth'});
}

function notify(text){
  toastEl.textContent = text;
  toastEl.classList.add('show');
  clearTimeout(window.__toast);
  window.__toast = setTimeout(()=> toastEl.classList.remove('show'), 2400);
}

function getInitData(){
  // Telegram WebApp initData
  if (tg && tg.initData) return tg.initData;
  // fallback for local testing - use query param or localStorage
  const urlParams = new URLSearchParams(window.location.search);
  return urlParams.get('initData') || urlParams.get('tgWebAppData') || localStorage.getItem('initData') || "";
}

async function apiFetch(path, options={}){
  const initData = getInitData();
  const headers = options.headers || {};
  if (initData) {
    headers['X-Telegram-Init-Data'] = initData;
    headers['Authorization'] = initData;
  }
  headers['Content-Type'] = 'application/json';
  const url = path.startsWith('/api/') ? path + (path.includes('?') ? '&' : '?') + 'initData=' + encodeURIComponent(initData) : path;
  const res = await fetch(url, {...options, headers});
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(txt || res.statusText);
  }
  return res.json();
}

function renderProfile(data){
  state.profile = data;
  const p = data.player;
  const pvp = data.pvp;
  const priv = data.privilege;

  // avatar everywhere
  const avatar = p.avatar_key || data.user?.first_name?.[0] || "🧙";
  state.avatar = avatar;
  ['profileAvatar','homeAvatar','previewAvatar','miniAvatar','battlePlayerAvatar'].forEach(id=>{
    const el=document.getElementById(id); if(el) el.textContent = avatar;
  });
  document.querySelectorAll('.avatar-choice').forEach(b=>{
    b.classList.toggle('selected', b.dataset.avatar===avatar);
  });

  // home
  document.getElementById('profileNameHome').textContent = p.first_name || data.user.first_name || "Игрок";
  document.getElementById('profileSubHome').textContent = `Уровень ${p.level} · ${p.rank}`;
  document.getElementById('homeLevel').textContent = `LVL ${p.level}`;
  document.getElementById('homeXpBar').style.width = `${p.xp_progress}%`;
  document.getElementById('homeXpText').textContent = `${p.xp.toLocaleString('ru-RU')} / ${p.xp_needed.toLocaleString('ru-RU')} XP`;
  document.getElementById('bpLevelHome').textContent = p.bp_level || 0;
  document.getElementById('bpBarHome').style.width = `${Math.min(100, (p.bp_level||0))}%`;
  document.getElementById('bpPercent').textContent = `${p.bp_level||0}%`;

  // crystal balances
  const cryst = p.crystals;
  state.crystals = cryst;
  document.getElementById('crystalBalance').textContent = cryst.toLocaleString('ru-RU');
  document.getElementById('crystalBalanceLarge').textContent = cryst.toLocaleString('ru-RU');
  document.getElementById('crystalSub').textContent = `${cryst.toLocaleString('ru-RU')} на балансе`;

  // profile screen
  document.getElementById('profileName').textContent = p.first_name;
  document.getElementById('profileRank').textContent = `Уровень ${p.level} · ${p.rank}`;
  document.getElementById('xpBar').style.width = `${p.xp_progress}%`;
  document.getElementById('xpText').textContent = `${p.xp.toLocaleString('ru-RU')} / ${p.xp_needed.toLocaleString('ru-RU')} XP`;

  document.getElementById('statDcr').textContent = p.dcr.toLocaleString('ru-RU');
  document.getElementById('statCrystals').textContent = cryst.toLocaleString('ru-RU');
  document.getElementById('statMmr').textContent = pvp.mmr;
  document.getElementById('statMmrRank').textContent = `${pvp.rank.emoji} ${pvp.rank.name}`;
  document.getElementById('statWl').textContent = `${pvp.ranked_wins} / ${pvp.ranked_losses}`;
  document.getElementById('statStreak').textContent = pvp.win_streak ? `Серия: ${pvp.win_streak}` : '';

  const privBadge = document.getElementById('privBadge');
  const privUntilEl = document.getElementById('privUntil');
  if (priv) {
    privBadge.textContent = `${priv.icon} ${priv.name} активна`;
    privBadge.classList.add('active');
    privUntilEl.textContent = `до ${new Date(priv.until).toLocaleDateString('ru-RU')}`;
    document.getElementById('privSub').textContent = `${priv.name} до ${new Date(priv.until).toLocaleDateString('ru-RU')}`;
  } else {
    privBadge.textContent = "Нет активной привилегии";
    privBadge.classList.remove('active');
    privUntilEl.textContent = "—";
  }

  // equipment
  const equipList = document.getElementById('equipList');
  const eq = data.equipment;
  equipList.innerHTML = `
    <div>⚔️ <span>${eq.weapon.name}</span><b>${eq.weapon.key||''}</b></div>
    <div>🛡️ <span>${eq.armor.name}</span><b>${eq.armor.key||''}</b></div>
    <div>🛡️ <span>${eq.shield.name}</span><b>${eq.shield.key||''}</b></div>
    <div>✨ <span>${eq.ability.name}</span><b>${eq.ability.key||''}</b></div>
    <div>🐺 <span>${eq.pet.name}</span><b>${eq.pet.key||''}</b></div>
  `;

  // battle
  document.getElementById('battleName').textContent = (p.first_name||'ИГРОК').toUpperCase();
  document.getElementById('battleLvl').textContent = `LVL ${p.level}`;
  document.getElementById('combatLog').textContent = `Бой готов. Твой MMR: ${pvp.mmr} (${pvp.rank.name}). Нажми атаку.`;

  // BP screen
  document.getElementById('bpLevel').textContent = p.bp_level || 0;
  document.getElementById('bpHint').textContent = `XP: ${p.bp_xp || 0} · ${p.bp_level ? 'до след. уровня' : 'начни играть'}`;
  // simple rewards mock based on level
  const rewardsEl = document.getElementById('bpRewards');
  if (rewardsEl) {
    rewardsEl.innerHTML = '';
    for(let i=1;i<=6;i++){
      const claimed = i <= (p.bp_level||0)/10;
      rewardsEl.innerHTML += `<div class="reward ${claimed?'claimed':''}"><span>✦</span><b>${i*50}</b><small>LVL ${i*15}</small></div>`;
    }
  }
}

async function loadProfile(){
  try {
    const data = await apiFetch('/api/me/profile');
    renderProfile(data);
    loadConfig();
  } catch(e){
    console.error(e);
    // fallback to mock if ALLOW_UNVERIFIED not set and no initData (local dev)
    if (location.hostname === 'localhost' || location.hostname === '127.0.0.1') {
      notify('Локальный режим: нет initData, включи ALLOW_UNVERIFIED=1');
    } else {
      notify('Открой Mini App через Telegram');
    }
    // show demo values
    document.getElementById('combatLog').textContent = 'Ошибка загрузки профиля: ' + e.message;
  }
}

async function loadConfig(){
  try {
    const cfg = await apiFetch('/api/config');
    const packsEl = document.getElementById('crystalPacks');
    if (packsEl) {
      packsEl.innerHTML = '';
      Object.entries(cfg.crystal_packs).forEach(([k,v], idx)=>{
        const feat = k==='500' ? 'featured' : '';
        packsEl.innerHTML += `<button class="pack ${feat}" data-buy="crystals${k}"><b>${v.crystals} ✦</b><span>${v.stars} ★</span></button>`;
      });
    }
    const privEl = document.getElementById('privilegesList');
    if (privEl) {
      privEl.innerHTML = '';
      cfg.privileges.forEach(p=>{
        privEl.innerHTML += `<button class="privilege ${p.key}" data-buy="${p.key}"><span class="priv-icon">${p.key==='vip'?'V':p.key==='crown'?'♛':'✧'}</span><div><b>${p.name}</b><small>${p.bonuses.join(' · ')}</small></div><strong>${p.price} ✦</strong></button>`;
      });
    }
  } catch(e){ console.error(e); }
}

async function setAvatar(avatar){
  try {
    const initData = getInitData();
    const res = await apiFetch('/api/me/avatar', {
      method:'POST',
      body: JSON.stringify({initData, avatar_key: avatar})
    });
    state.avatar = res.avatar_key;
    ['profileAvatar','homeAvatar','previewAvatar','miniAvatar','battlePlayerAvatar'].forEach(id=>{
      const el=document.getElementById(id); if(el) el.textContent = avatar;
    });
    document.querySelectorAll('.avatar-choice').forEach(b=>b.classList.toggle('selected', b.dataset.avatar===avatar));
    notify('Аватар сохранён ✓');
  } catch(e){
    notify('Ошибка: ' + e.message);
    // local fallback
    state.avatar = avatar;
    ['profileAvatar','homeAvatar','previewAvatar','miniAvatar','battlePlayerAvatar'].forEach(id=>{
      const el=document.getElementById(id); if(el) el.textContent = avatar;
    });
    document.querySelectorAll('.avatar-choice').forEach(b=>b.classList.toggle('selected', b.dataset.avatar===avatar));
  }
}

// battle demo
let enemy = 72;
function attack(skill=false){
  const damage = skill?720:347;
  enemy = Math.max(0, enemy-(skill?8:5));
  const bar=document.getElementById('enemyHp');
  bar.style.width=enemy+'%';
  document.getElementById('enemyHpText').textContent=`${Math.round(enemy/100*10000).toLocaleString('ru-RU')} / 10 000 HP`;
  const log=document.getElementById('combatLog');
  log.classList.remove('hit'); void log.offsetWidth; log.classList.add('hit');
  log.textContent= skill?`✨ РАЗРЫВ! Критический эффект · −${damage} HP`:`⚔️ Атака нанесла −${damage} HP`;
  navigator.vibrate?.(skill?[40,30,80]:25);
  if(enemy===0){ log.textContent='🏆 ХРАНИТЕЛЬ ПОВЕРЖЕН! +1 240 DKR · +380 XP'; enemy=100; setTimeout(()=>{document.getElementById('enemyHp').style.width='100%';document.getElementById('enemyHpText').textContent='10 000 / 10 000 HP'},900)}
}

function buy(key){
  notify(`${key} — покупка через Stars (в разработке)`);
}

document.addEventListener('click', e=>{
  const avatarBtn = e.target.closest('[data-avatar]');
  if(avatarBtn){ setAvatar(avatarBtn.dataset.avatar); return; }
  const el = e.target.closest('[data-action],[data-buy]');
  if(!el) return;
  const action = el.dataset.action;
  if(action){
    if(['profile','home','pass','crystals','privileges','battle'].includes(action)) showScreen(action);
    if(action==='demoBattle') showScreen('battle');
    if(action==='attack') attack(false);
    if(action==='skill') attack(true);
  }
  if(el.dataset.buy) buy(el.dataset.buy);
});

// init
loadProfile();
