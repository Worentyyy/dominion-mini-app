const state = {
  crystals: 1250,
  prices: {
    crystals100: ["100 ✦", 70],
    crystals500: ["500 ✦", 330],
    crystals1000: ["1 000 ✦", 670],
    crystals5000: ["5 000 ✦", 3330],
    crystals10000: ["10 000 ✦", 6660],
    vip: ["VIP на 30 дней", 100],
    crown: ["Корона на 30 дней", 150],
    divine: ["Божественная на 30 дней", 300],
    battlepass: ["Battle Pass Premium", 799],
    starter: ["Набор новичка", 330]
  }
};

const screens = [...document.querySelectorAll(".screen")];
const navs = [...document.querySelectorAll(".nav")];
const toast = document.getElementById("toast");

function showScreen(name){
  screens.forEach(s => s.classList.toggle("active", s.id === name));
  navs.forEach(n => n.classList.toggle("active", n.dataset.action === name));
  window.scrollTo({top:0, behavior:"smooth"});
}

function notify(text){
  toast.textContent = text;
  toast.classList.add("show");
  clearTimeout(window.__toast);
  window.__toast = setTimeout(()=>toast.classList.remove("show"), 2200);
}

function buy(key){
  const item = state.prices[key];
  if(!item) return;
  const [name, stars] = item;
  // В реальном Telegram Mini App здесь будет Telegram.WebApp + invoice URL,
  // который создаёт твой Python-бот. Сейчас это безопасная визуальная заглушка.
  notify(`${name} · ${stars} ★ — готово к оплате`);
}

document.addEventListener("click", e=>{
  const el = e.target.closest("[data-action],[data-buy]");
  if(!el) return;
  if(el.dataset.action) {
    const action = el.dataset.action;
    if(["home","pass","crystals","privileges"].includes(action)) showScreen(action);
  }
  if(el.dataset.buy) buy(el.dataset.buy);
});

function renderBalance(){
  const text = state.crystals.toLocaleString("ru-RU");
  document.getElementById("crystalBalance").textContent = text;
  document.getElementById("crystalBalanceLarge").textContent = text;
}
renderBalance();
