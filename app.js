const API_BASE = document.querySelector('meta[name="dominion-api-base"]')?.content?.replace(/\/$/, '') || '';
const AVATARS = {mage:'🧙',warrior:'⚔️',shadow:'🥷',blood:'🧛',hunter:'🐺',lord:'👑',demon:'👹',celestial:'🪽'};
const DEFAULT_AVATAR_KEY = 'mage';
const state = {crystals:1250, avatarKey:DEFAULT_AVATAR_KEY, profile:null, prices:{crystals100:['100 ✦',70],crystals500:['500 ✦',330],crystals1000:['1 000 ✦',670],crystals5000:['5 000 ✦',3330],crystals10000:['10 000 ✦',6660],vip:['VIP на 30 дней',100],crown:['Корона на 30 дней',150],divine:['Божественная на 30 дней',300],battlepass:['Battle Pass Premium',799],starter:['Набор новичка',330]}};
const screens = [...document.querySelectorAll('.screen')];
const navs = [...document.querySelectorAll('.nav')];
const toast = document.getElementById('toast');
const $ = id => document.getElementById(id);

function telegramInitData(){ return window.Telegram?.WebApp?.initData || ''; }
function showScreen(name){
  screens.forEach(s=>s.classList.toggle('active',s.id===name));
  navs.forEach(n=>n.classList.toggle('active',n.dataset.action===name));
  window.scrollTo({top:0,behavior:'smooth'});
  if(name==='profile') loadProfile();
}
function notify(text){ toast.textContent=text; toast.classList.add('show'); clearTimeout(window.__toast); window.__toast=setTimeout(()=>toast.classList.remove('show'),2200); }
function buy(key){ const item=state.prices[key]; if(item) notify(`${item[0]} · ${item[1]} ★ — готово к оплате`); }
function number(value){ return Number(value || 0).toLocaleString('ru-RU'); }
function avatarEmoji(key){ return AVATARS[key] || AVATARS[DEFAULT_AVATAR_KEY]; }
function setAvatarVisual(key){
  state.avatarKey = AVATARS[key] ? key : DEFAULT_AVATAR_KEY;
  const emoji = avatarEmoji(state.avatarKey);
  ['profileAvatar','homeAvatar','previewAvatar','miniAvatar','battlePlayerAvatar'].forEach(id=>{ const el=$(id); if(el) el.textContent=emoji; });
  document.querySelectorAll('[data-avatar-key]').forEach(button=>button.classList.toggle('selected',button.dataset.avatarKey===state.avatarKey));
}
function setProfileState(kind, message=''){
  const loading=$('profileLoading'); const content=$('profileContent');
  loading.hidden = kind==='ready'; content.hidden = kind!=='ready';
  if(kind!=='ready') loading.innerHTML = kind==='error' ? `<b>Не удалось загрузить профиль</b><small>${message}</small><button class="retry-profile" data-action="retryProfile">Повторить</button>` : 'Пробуждаем данные героя…';
}
async function api(path, options={}){
  const initData = telegramInitData();
  if(!initData) throw new Error('Открой Mini App внутри Telegram.');
  const headers = new Headers(options.headers || {});
  headers.set('X-Telegram-Init-Data', initData);
  if(options.body) headers.set('Content-Type','application/json');
  const response = await fetch(`${API_BASE}${path}`, {...options,headers});
  const payload = await response.json().catch(()=>({detail:'Сервер вернул некорректный ответ.'}));
  if(!response.ok) throw new Error(payload.detail || 'Ошибка API.');
  return payload;
}
function itemName(value){ return value || 'Не экипировано'; }
function applyProfile(profile){
  state.profile=profile; state.crystals=profile.crystals; setAvatarVisual(profile.avatar_key || DEFAULT_AVATAR_KEY);
  $('profileName').textContent=profile.name; $('profileNameHome').textContent=profile.name;
  $('profileLevelRank').textContent=`Уровень ${profile.level} · ${profile.level_rank}`;
  $('profileXpProgress').style.width=`${profile.xp.progress_percent}%`;
  $('profileXpText').textContent=`${number(profile.xp.current)} / ${number(profile.xp.next_level)} XP`;
  $('profileDcr').textContent=number(profile.dcr); $('profileCrystals').textContent=number(profile.crystals);
  $('profileMmr').textContent=number(profile.pvp.mmr); $('profilePvpRank').textContent=profile.pvp.rank.name;
  $('profilePvpRankIcon').textContent=profile.pvp.rank.emoji; $('profileRecord').textContent=`${number(profile.pvp.wins)} / ${number(profile.pvp.losses)}`;
  $('profileStreak').textContent=number(profile.pvp.current_streak);
  $('profileBattlePass').textContent=`Уровень ${profile.battle_pass.level} / 100 · ${number(profile.battle_pass.xp)} / ${number(profile.battle_pass.next_level_xp)} XP`;
  $('profileBattlePassPremium').textContent=profile.battle_pass.premium ? 'PREMIUM' : 'БАЗОВЫЙ';
  $('profileBattlePassPremium').classList.toggle('active',profile.battle_pass.premium);
  $('profilePrivilege').textContent=profile.privilege;
  $('equipmentWeapon').textContent=itemName(profile.equipment.weapon); $('equipmentArmor').textContent=itemName(profile.equipment.armor);
  $('equipmentShield').textContent=itemName(profile.equipment.shield); $('equipmentAbility').textContent=itemName(profile.equipment.ability); $('equipmentPet').textContent=itemName(profile.equipment.pet);
  renderBalance(); setProfileState('ready');
}
async function loadProfile(){ setProfileState('loading'); try { applyProfile(await api('/api/me/profile')); } catch(error) { setProfileState('error',error.message); } }
function openAvatarModal(){ if(!state.profile) return; $('avatarModal').classList.add('open'); $('avatarModal').setAttribute('aria-hidden','false'); }
function closeAvatarModal(){ $('avatarModal').classList.remove('open'); $('avatarModal').setAttribute('aria-hidden','true'); }
async function saveAvatar(key){
  if(!AVATARS[key]) return;
  try { const profile = await api('/api/me/avatar',{method:'POST',body:JSON.stringify({avatar_key:key})}); applyProfile(profile); closeAvatarModal(); notify('Аватар сохранён'); }
  catch(error) { notify(error.message); }
}

let enemy=72;
function attack(skill=false){
  const damage=skill?720:347; enemy=Math.max(0,enemy-(skill?8:5)); const bar=$('enemyHp'); bar.style.width=enemy+'%';
  $('enemyHpText').textContent=`${Math.round(enemy/100*10000).toLocaleString('ru-RU')} / 10 000 HP`;
  const log=$('combatLog'); log.classList.remove('hit'); void log.offsetWidth; log.classList.add('hit'); log.textContent=skill?`✨ РАЗРЫВ! Критический эффект · −${damage} HP`:`⚔️ Атака нанесла −${damage} HP`;
  navigator.vibrate?.(skill?[40,30,80]:25);
  if(enemy===0){ log.textContent='🏆 ХРАНИТЕЛЬ ПОВЕРЖЕН! +1 240 DKR · +380 XP'; enemy=100; setTimeout(()=>{$('enemyHp').style.width='100%';$('enemyHpText').textContent='10 000 / 10 000 HP';},900); }
}
document.addEventListener('click',event=>{
  const avatar=event.target.closest('[data-avatar-key]'); if(avatar){ saveAvatar(avatar.dataset.avatarKey); return; }
  const element=event.target.closest('[data-action],[data-buy]'); if(!element) return;
  const action=element.dataset.action;
  if(action){
    if(['profile','home','pass','crystals','privileges','battle'].includes(action)) showScreen(action);
    if(action==='demoBattle') showScreen('battle'); if(action==='attack') attack(false); if(action==='skill') attack(true);
    if(action==='retryProfile') loadProfile(); if(action==='closeAvatarModal') closeAvatarModal();
  }
  if(element.dataset.buy) buy(element.dataset.buy);
});
$('avatarTrigger')?.addEventListener('click',openAvatarModal);
function renderBalance(){ const text=number(state.crystals); $('crystalBalance').textContent=text; $('crystalBalanceLarge').textContent=text; }
window.Telegram?.WebApp?.ready(); window.Telegram?.WebApp?.expand(); renderBalance();
