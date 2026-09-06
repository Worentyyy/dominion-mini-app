# -*- coding: utf-8 -*-
"""
DOMINION 4.0 — single-file Telegram MMORPG bot
Python 3.11+ / aiogram 3.x / SQLite

INSTALL:
    py -m pip install -U aiogram

RUN:
    Set BOT_TOKEN below (or environment variable DOMINION_BOT_TOKEN)
    Set OWNER_ID to your Telegram numeric ID
    Optional: NEWS_CHANNEL_ID to a channel ID where the bot can post
    python dominion.py

IMPORTANT:
    Never publish your real bot token. If a token was previously exposed,
    revoke it in @BotFather and generate a new one.
"""

import asyncio
import html
import logging
import os
import random
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
DB_PATH = "dominion.db"

from aiogram import Bot, Dispatcher, F
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
    BotCommand,
)

# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = "Bot_Token"
OWNER_ID = 7952277527
NEWS_CHANNEL_ID = "@dminionss"
DB_FILE = "dominion.db"

NEWS_CHANNEL_URL = "https://t.me/dminionss"
COMMUNITY_CHAT_URL = "https://t.me/+j0LxEOtavf5kOTgy"

# Server control / maintenance
MAINTENANCE_MODE = False
MAINTENANCE_TEXT = (
    "🛠️ <b>ТЕХНИЧЕСКИЕ РАБОТЫ</b>\n\n"
    "В данный момент DOMINION находится на техническом обслуживании.\n\n"
    "Пожалуйста, следите за обновлениями в нашем новостном канале.\n\n"
    "⚙️ Приносим извинения за неудобства."
)
MAINTENANCE_FINISHED_TEXT = (
    "✅ <b>ТЕХНИЧЕСКИЕ РАБОТЫ ЗАВЕРШЕНЫ</b>\n\n"
    "DOMINION снова полностью доступен.\n"
    "Все игровые системы восстановлены.\n\n"
    "Спасибо за ожидание! ❤️"
)



GAME_NAME = "DOMINION"
GAME_VERSION = "8.0"

START_DCR = 250
START_CRYSTALS = 25
START_POTIONS = 3
START_LEVEL = 1
START_XP = 0

DAILY_TRANSFER_LIMIT = 100_000
SUSPICIOUS_BALANCE = 100_000_000

CRYSTAL_PACKS = {
    100: 70,
    500: 330,
    1000: 670,
    5000: 3330,
    10000: 6660,
}
BATTLE_PASS_STARS = 150

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("dominion")

dp = Dispatcher()
db_lock = asyncio.Lock()
# Кто сейчас пишет сообщение в поддержку / кому отвечает администрация
support_waiting = {}

# ============================================================
# CONSTANTS / DATA
# ============================================================

RARITIES = ["Обычный", "Редкий", "Эпический", "Легендарный", "Мифический", "Демонический"]
RARITY_MULT = {
    "Обычный": 1.0,
    "Редкий": 1.25,
    "Эпический": 1.55,
    "Легендарный": 2.0,
    "Мифический": 2.8,
    "Демонический": 4.0,
}

RANKS = [
    (1, 10, "Новичок"),
    (10, 30, "Стажёр"),
    (30, 50, "Воин"),
    (50, 80, "Элита"),
    (80, 100, "Легенда"),
    (100, 10**9, "Демонический"),
]

PVP_RANKS = [
    (0, 100, "Bronze I", "🥉"),
    (100, 200, "Bronze II", "🥉"),
    (200, 300, "Bronze III", "🥉"),
    (300, 400, "Iron I", "⚙️"),
    (400, 500, "Iron II", "⚙️"),
    (500, 600, "Iron III", "⚙️"),
    (600, 700, "Silver I", "🥈"),
    (700, 800, "Silver II", "🥈"),
    (800, 900, "Silver III", "🥈"),
    (900, 1000, "Gold I", "🥇"),
    (1000, 1100, "Gold II", "🥇"),
    (1100, 1200, "Gold III", "🥇"),
    (1200, 1300, "Platinum I", "💠"),
    (1300, 1400, "Platinum II", "💠"),
    (1400, 2000, "Platinum III", "💠"),
    (2000, 3000, "Ranger", "🦅"),
    (3000, 4000, "Master", "👑"),
    (4000, 5000, "Grandmaster", "🌌"),
    (5000, 6000, "Demonic", "😈"),
    (6000, 10**9, "Divine", "✨"),
]

EQUIPMENT_SLOTS = ("weapon", "armor", "shield")

WEAPONS = [
    ("rusty_sword", "Ржавый меч", "Обычный", 8, 18, 1500),
    ("iron_sword", "Железный меч", "Редкий", 15, 28, 5000),
    ("hunter_blade", "Клинок охотника", "Эпический", 25, 42, 15000),
    ("void_edge", "Грань Пустоты", "Легендарный", 40, 65, 50000),
    ("mythic_fang", "Мифический клык", "Мифический", 60, 90, 100000),
    ("demonic_reaper", "Демонический жнец", "Демонический", 90, 140, 150000),
]

# ============================================================
# ЭФФЕКТЫ ОРУЖИЯ В PVE
# ============================================================

WEAPON_EFFECTS = {
    # Обычные
    "rusty_sword": None,
    "iron_sword": None,

    # Ослабленные эффекты обычных/высоких рангов
    "hunter_blade": {
        "type": "bleed",
        "damage": 7,
        "duration": 3,
        "chance": 0.20,
    },
    "void_edge": {
        "type": "burn",
        "damage": 10,
        "duration": 3,
        "chance": 0.25,
    },
    "mythic_fang": {
        "type": "bleed",
        "damage": 16,
        "duration": 4,
        "chance": 0.30,
    },
    "demonic_reaper": {
        "type": "burn",
        "damage": 22,
        "duration": 4,
        "chance": 0.45,
    },

    # Премиальные / божественные мечи
    "heaven_wrath": {
        "type": "burn",
        "damage": 25,
        "duration": 5,
        "chance": 1.0,
    },
    "soul_eater": {
        "type": "bleed",
        "damage": 22,
        "duration": 5,
        "chance": 0.85,
    },
    "thunderer": {
        "type": "burn",
        "damage": 30,
        "duration": 4,
        "chance": 0.75,
    },
}

ARMORS = [
    ("cloth_armor", "Тканевая броня", "Обычный", 0.02, 35),
    ("iron_armor", "Железная броня", "Редкий", 0.05, 100),
    ("knight_armor", "Броня рыцаря", "Эпический", 0.08, 220),
    ("dragon_armor", "Драконья броня", "Легендарный", 0.10, 500),
    ("mythic_armor", "Мифическая броня", "Мифический", 0.15, 1200),
    ("demonic_armor", "Демоническая броня", "Демонический", 0.20, 3000),
]

SHIELDS = [
    ("wood_shield", "Деревянный щит", "Обычный", 0.00, 0.00, 20),
    ("iron_shield", "Железный щит", "Редкий", 0.08, 0.25, 100),
    ("arcane_shield", "Арканный щит", "Эпический", 0.12, 0.20, 220),
    ("legend_shield", "Щит легенды", "Легендарный", 0.16, 0.16, 500),
    ("mythic_shield", "Мифический щит", "Мифический", 0.20, 0.12, 1200),
    ("demonic_shield", "Демонический щит", "Демонический", 0.25, 0.10, 3000),
]

MATERIALS = [
    ("forest_particle", "Частица леса", "Обычный", 10),
    ("cave_particle", "Частица пещеры", "Редкий", 20),
    ("ruins_particle", "Частица руин", "Эпический", 40),
    ("abyss_particle", "Частица бездны", "Легендарный", 80),
]

LOCATIONS = {
    "forest": {
        "name": "🌲 Тёмный лес",
        "description": "Безопасная стартовая зона. Здесь водятся слабые монстры.",
        "enemies": [
            ("forest_slime", "Лесной слизень", 35, 6, 10, 25, "forest_particle"),
            ("wild_wolf", "Дикий волк", 50, 8, 14, 35, "forest_particle"),
            ("bandit", "Разбойник", 70, 10, 18, 55, "forest_particle"),
        ],
    },
    "cave": {
        "name": "⛏️ Забытые пещеры",
        "description": "Опаснее леса. Враги сильнее, награда выше.",
        "enemies": [
            ("cave_bat", "Пещерная летучая мышь", 90, 14, 23, 80, "cave_particle"),
            ("cave_golem", "Каменный голем", 150, 18, 30, 130, "cave_particle"),
            ("dark_miner", "Тёмный шахтёр", 125, 20, 34, 160, "cave_particle"),
        ],
    },
    "ruins": {
        "name": "🏚️ Древние руины",
        "description": "Эпическая зона с опасными противниками.",
        "enemies": [
            ("ruin_guard", "Страж руин", 220, 25, 40, 300, "ruins_particle"),
            ("cursed_knight", "Проклятый рыцарь", 280, 30, 48, 420, "ruins_particle"),
        ],
    },
    "abyss": {
        "name": "🔥 Бездна",
        "description": "Высокий риск, высокий доход.",
        "enemies": [
            ("abyss_demon", "Демон бездны", 450, 45, 75, 900, "abyss_particle"),
            ("abyss_hunter", "Охотник бездны", 520, 50, 85, 1200, "abyss_particle"),
        ],
    },
}

POTIONS = [
    ("potion_rare", "Зелье восстановления", "Редкий", 0.10, 50, "forest_particle"),
    ("potion_epic", "Большое зелье", "Эпический", 0.20, 100, "cave_particle"),
    ("potion_legendary", "Зелье легенды", "Легендарный", 0.35, 200, "ruins_particle"),
    ("potion_mythic", "Мифическое зелье", "Мифический", 0.60, 400, "abyss_particle"),
    ("potion_demonic", "Демоническое зелье", "Демонический", 1.00, 800, "abyss_particle"),
]


DB_PATH = DB_FILE

def db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def db_execute(query, params=(), fetchone=False, fetchall=False):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        cur = conn.execute(query, params)

        if fetchone:
            return cur.fetchone()

        if fetchall:
            return cur.fetchall()

        conn.commit()
        return None

    finally:
        conn.close()

def db_insert(query, params=()):
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.execute(query, params)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()

def db_script(script):
    conn = sqlite3.connect(DB_PATH)

    try:
        conn.executescript(script)
        conn.commit()
    finally:
        conn.close()


        

def esc(value):
    """HTML-safe text for Telegram HTML parse mode."""
    return html.escape(str(value if value is not None else ""))


def fmt(value):
    try:
        return f"{int(value):,}".replace(",", " ")
    except (TypeError, ValueError):
        return "0"


def get_player(user_id):
    return db_execute("SELECT * FROM players WHERE user_id=?", (int(user_id),), fetchone=True)


def ensure_player(user):
    """Create/update a player without overwriting their economy/progress."""
    user_id = int(user.id)
    username = user.username or ""
    first_name = user.first_name or ""
    row = get_player(user_id)
    if not row:
        now = datetime.now(timezone.utc).isoformat()
        db_execute("""
            INSERT INTO players(user_id,username,first_name,dcr,crystals,level,xp,created_at,last_seen)
            VALUES(?,?,?,?,?,?,?,?,?)
        """, (user_id, username, first_name, START_DCR, START_CRYSTALS,
              START_LEVEL, START_XP, now, now))
        # Give starter equipment row and starter potions through the canonical items table.
        db_execute("INSERT OR IGNORE INTO equipment(user_id) VALUES(?)", (user_id,))
        row = get_player(user_id)
    else:
        db_execute("UPDATE players SET username=?,first_name=?,last_seen=? WHERE user_id=?",
                   (username, first_name, datetime.now(timezone.utc).isoformat(), user_id))
        db_execute("INSERT OR IGNORE INTO equipment(user_id) VALUES(?)", (user_id,))
        row = get_player(user_id)
    return row


def add_dcr(user_id, amount, reason=""):
    amount = int(amount)
    db_execute("UPDATE players SET dcr=dcr+? WHERE user_id=?", (amount, int(user_id)))
    if amount:
        db_execute("INSERT INTO transactions(user_id,currency,amount,reason,created_at) VALUES(?,?,?,?,?)",
                   (int(user_id), "DCR", amount, str(reason)[:500], datetime.now(timezone.utc).isoformat()))
    return get_player(user_id)


def add_crystals(user_id, amount, reason=""):
    amount = int(amount)
    db_execute("UPDATE players SET crystals=crystals+? WHERE user_id=?", (amount, int(user_id)))
    if amount:
        db_execute("INSERT INTO transactions(user_id,currency,amount,reason,created_at) VALUES(?,?,?,?,?)",
                   (int(user_id), "CRYSTALS", amount, str(reason)[:500], datetime.now(timezone.utc).isoformat()))
    return get_player(user_id)


def add_xp(user_id, amount):
    amount = max(0, int(amount))
    p = get_player(user_id)
    if not p:
        return 0
    xp = int(p["xp"] or 0) + amount
    level = int(p["level"] or 1)
    gained = 0
    # Smooth progression; preserves the existing level/rank system.
    while level < 1000:
        need = 100 + (level - 1) * 50
        if xp < need:
            break
        xp -= need
        level += 1
        gained += 1
    db_execute("UPDATE players SET xp=?,level=? WHERE user_id=?", (xp, level, int(user_id)))
    return gained


def rank_for_level(level):
    level = int(level or 1)
    for lo, hi, name in RANKS:
        if lo <= level < hi:
            return name
    return RANKS[-1][2]


def pvp_rank_for_mmr(mmr):
    mmr = int(mmr or 0)
    for lo, hi, name, emoji in PVP_RANKS:
        if lo <= mmr < hi:
            return {"name": name, "emoji": emoji}
    return {"name": PVP_RANKS[-1][2], "emoji": PVP_RANKS[-1][3]}


def get_equipment(user_id):
    """Return one stable equipment row with joined item keys/names."""
    db_execute("INSERT OR IGNORE INTO equipment(user_id) VALUES(?)", (int(user_id),))
    return db_execute("""
        SELECT e.*,
               w.item_key AS weapon_key, w.name AS weapon_name,
               a.item_key AS armor_key, a.name AS armor_name,
               s.item_key AS shield_key, s.name AS shield_name,
               ab.item_key AS ability_key, ab.name AS ability_name,
               pt.item_key AS pet_key, pt.name AS pet_name
        FROM equipment e
        LEFT JOIN items w ON w.item_id=e.weapon_id
        LEFT JOIN items a ON a.item_id=e.armor_id
        LEFT JOIN items s ON s.item_id=e.shield_id
        LEFT JOIN items ab ON ab.item_id=e.ability_id
        LEFT JOIN items pt ON pt.item_id=e.pet_id
        WHERE e.user_id=?
    """, (int(user_id),), fetchone=True)


def player_combat_stats(user_id):
    p = get_player(user_id)
    if not p:
        return {"attack_min": 10, "attack_max": 20, "armor_reduction": 0.0,
                "shield_chance": 0.0, "shield_reduction": 0.0}
    eq = get_equipment(user_id)
    amin, amax = 10, 20
    armor_red = 0.0
    shield_chance = 0.0
    shield_red = 0.0
    if eq:
        if eq["weapon_id"]:
            item = db_execute("SELECT attack_min,attack_max FROM items WHERE item_id=?", (eq["weapon_id"],), fetchone=True)
            if item:
                amin = int(item["attack_min"] or 0) or amin
                amax = int(item["attack_max"] or 0) or amax
        if eq["armor_id"]:
            item = db_execute("SELECT damage_reduction FROM items WHERE item_id=?", (eq["armor_id"],), fetchone=True)
            if item:
                armor_red = float(item["damage_reduction"] or 0)
        if eq["shield_id"]:
            item = db_execute("SELECT shield_chance,shield_reduction FROM items WHERE item_id=?", (eq["shield_id"],), fetchone=True)
            if item:
                shield_chance = float(item["shield_chance"] or 0)
                shield_red = float(item["shield_reduction"] or 0)
    return {"attack_min": amin, "attack_max": amax, "armor_reduction": armor_red,
            "shield_chance": shield_chance, "shield_reduction": shield_red}


def is_owner(user_id):
    return int(user_id) == int(OWNER_ID)


def premium_status_text(p):
    if not p:
        return "Нет"
    now = datetime.now(timezone.utc)
    active = []
    for column, label in (("crown_until", "👑 Корона"), ("vip_until", "⭐ VIP"), ("divine_until", "🌌 Божественный")):
        raw = p[column] if column in p.keys() else None
        if raw:
            try:
                dt = datetime.fromisoformat(str(raw))
                if dt > now:
                    active.append(f"{label} до {dt.astimezone(timezone.utc).strftime('%d.%m.%Y')}")
            except ValueError:
                pass
    return ", ".join(active) if active else "Нет активного статуса"


def admin_log(admin_id, action, target_id=None, details=""):
    try:
        db_execute("INSERT INTO admin_logs(admin_id,action,target_id,details,created_at) VALUES(?,?,?,?,?)",
                   (int(admin_id), str(action), target_id, str(details)[:1000], datetime.now(timezone.utc).isoformat()))
    except sqlite3.Error:
        log.exception("Не удалось записать admin_log")


def init_database():
    db_script("""
    CREATE TABLE IF NOT EXISTS players (
        user_id INTEGER PRIMARY KEY,
        username TEXT DEFAULT '',
        first_name TEXT DEFAULT '',
        dcr INTEGER NOT NULL DEFAULT 250,
        crystals INTEGER NOT NULL DEFAULT 25,
        level INTEGER NOT NULL DEFAULT 1,
        xp INTEGER NOT NULL DEFAULT 0,
        wins INTEGER NOT NULL DEFAULT 0,
        losses INTEGER NOT NULL DEFAULT 0,
        kills INTEGER NOT NULL DEFAULT 0,
        deaths INTEGER NOT NULL DEFAULT 0,
        pvp_rating INTEGER NOT NULL DEFAULT 1000,
        battle_pass INTEGER NOT NULL DEFAULT 0,
        bp_paid INTEGER NOT NULL DEFAULT 0,
        clan_id INTEGER,
        reputation INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        last_seen TEXT NOT NULL,
        blocked INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS items (
        item_id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_key TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        item_type TEXT NOT NULL,
        rarity TEXT NOT NULL,
        attack_min INTEGER DEFAULT 0,
        attack_max INTEGER DEFAULT 0,
        damage_reduction REAL DEFAULT 0,
        shield_chance REAL DEFAULT 0,
        shield_reduction REAL DEFAULT 0,
        price_dcr INTEGER DEFAULT 0,
        particle_type TEXT DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS inventory (
        user_id INTEGER NOT NULL,
        item_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL DEFAULT 1,
        PRIMARY KEY(user_id, item_id),
        FOREIGN KEY(user_id) REFERENCES players(user_id) ON DELETE CASCADE,
        FOREIGN KEY(item_id) REFERENCES items(item_id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS equipment (
        user_id INTEGER PRIMARY KEY,
        weapon_id INTEGER,
        armor_id INTEGER,
        shield_id INTEGER,
        FOREIGN KEY(user_id) REFERENCES players(user_id) ON DELETE CASCADE
    );    

    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        currency TEXT NOT NULL,
        amount INTEGER NOT NULL,
        reason TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS transfers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER NOT NULL,
        receiver_id INTEGER NOT NULL,
        amount INTEGER NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS transfer_daily (
        user_id INTEGER NOT NULL,
        day TEXT NOT NULL,
        amount INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(user_id, day)
    );

    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        text TEXT NOT NULL,
        is_read INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS private_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER NOT NULL,
        receiver_id INTEGER NOT NULL,
        text TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS admin_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER NOT NULL,
        action TEXT NOT NULL,
        target_id INTEGER,
        details TEXT DEFAULT '',
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS security_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        event TEXT NOT NULL,
        details TEXT DEFAULT '',
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS purchases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        telegram_charge_id TEXT,
        product TEXT NOT NULL,
        amount INTEGER NOT NULL,
        stars INTEGER NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS pve_battles (
        user_id INTEGER PRIMARY KEY,
        location TEXT NOT NULL,
        enemy_key TEXT NOT NULL,
        enemy_name TEXT NOT NULL,
        enemy_hp INTEGER NOT NULL,
        enemy_max_hp INTEGER NOT NULL,
        enemy_min_damage INTEGER NOT NULL,
        enemy_max_damage INTEGER NOT NULL,
        reward_dcr INTEGER NOT NULL,
        particle_type TEXT NOT NULL,
        player_hp INTEGER NOT NULL,
        player_max_hp INTEGER NOT NULL,
        started_at TEXT NOT NULL,
        last_action REAL NOT NULL DEFAULT 0,
        stopped INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS world_bosses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        boss_key TEXT NOT NULL,
        name TEXT NOT NULL,
        max_hp INTEGER NOT NULL,
        hp INTEGER NOT NULL,
        reward_pool INTEGER NOT NULL,
        starts_at TEXT NOT NULL,
        ends_at TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1,
        published INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS boss_damage (
        boss_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        damage INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(boss_id, user_id)
    );

    CREATE TABLE IF NOT EXISTS market_lots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_id INTEGER NOT NULL,
        item_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        price INTEGER NOT NULL,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS clans (
        clan_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        leader_id INTEGER NOT NULL,
        crystals_bank INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS clan_members (
        clan_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        role TEXT NOT NULL DEFAULT 'member',
        PRIMARY KEY(clan_id, user_id)
    );

    CREATE TABLE IF NOT EXISTS quests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        quest_key TEXT NOT NULL,
        progress INTEGER NOT NULL DEFAULT 0,
        target INTEGER NOT NULL,
        reward_dcr INTEGER NOT NULL DEFAULT 0,
        reward_xp INTEGER NOT NULL DEFAULT 0,
        completed INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS achievements (
        user_id INTEGER NOT NULL,
        achievement_key TEXT NOT NULL,
        completed INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(user_id, achievement_key)
    );

    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_key TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        starts_at TEXT NOT NULL,
        ends_at TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS transfer_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER NOT NULL,
        receiver_id INTEGER NOT NULL,
        amount INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS pvp_queue (
        user_id INTEGER PRIMARY KEY,
        mode TEXT NOT NULL,
        mmr INTEGER NOT NULL DEFAULT 0,
        joined_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS pvp_matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,

        player1_id INTEGER NOT NULL,
        player2_id INTEGER NOT NULL,

        mode TEXT NOT NULL,

        player1_hp INTEGER NOT NULL,
        player2_hp INTEGER NOT NULL,

        player1_max_hp INTEGER NOT NULL,
        player2_max_hp INTEGER NOT NULL,

        turn_user_id INTEGER,

        status TEXT NOT NULL DEFAULT 'waiting',

        player1_ready INTEGER NOT NULL DEFAULT 0,
        player2_ready INTEGER NOT NULL DEFAULT 0,

        winner_id INTEGER,

        player1_damage INTEGER NOT NULL DEFAULT 0,
        player2_damage INTEGER NOT NULL DEFAULT 0,

        created_at TEXT NOT NULL,
        started_at TEXT,

        player1_message_id INTEGER,
        player2_message_id INTEGER,

        finished_at TEXT
    );

    CREATE TABLE IF NOT EXISTS pvp_invites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,

        sender_id INTEGER NOT NULL,
        receiver_id INTEGER NOT NULL,

        status TEXT NOT NULL DEFAULT 'pending',

        created_at TEXT NOT NULL
    );

     CREATE TABLE IF NOT EXISTS pvp_stats (
        user_id INTEGER PRIMARY KEY,

        mmr INTEGER NOT NULL DEFAULT 0,

        ranked_games INTEGER NOT NULL DEFAULT 0,
        ranked_wins INTEGER NOT NULL DEFAULT 0,
        ranked_losses INTEGER NOT NULL DEFAULT 0,

        calibration_games INTEGER NOT NULL DEFAULT 0,
        calibration_direction TEXT NOT NULL DEFAULT 'normal',

        total_games INTEGER NOT NULL DEFAULT 0,
        total_wins INTEGER NOT NULL DEFAULT 0,
        total_losses INTEGER NOT NULL DEFAULT 0,

        total_damage INTEGER NOT NULL DEFAULT 0,

        current_streak INTEGER NOT NULL DEFAULT 0,
        best_streak INTEGER NOT NULL DEFAULT 0
    );

        CREATE TABLE IF NOT EXISTS pets (
        pet_id INTEGER PRIMARY KEY AUTOINCREMENT,
        pet_key TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        rarity TEXT NOT NULL,
        description TEXT NOT NULL,
        price_dcr INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS player_pets (
        user_id INTEGER NOT NULL,
        pet_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL DEFAULT 1,
        equipped INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(user_id, pet_id),
        FOREIGN KEY(user_id) REFERENCES players(user_id) ON DELETE CASCADE,
        FOREIGN KEY(pet_id) REFERENCES pets(pet_id) ON DELETE CASCADE
    );
    
    """)


    # ========================================================
    # DOMINION 5.0 — ADMIN / MAINTENANCE / CLAN WAR / STORY
    # ========================================================
    db_script("""
    CREATE TABLE IF NOT EXISTS admin_users (
        user_id INTEGER PRIMARY KEY,
        role TEXT NOT NULL DEFAULT 'moderator',
        created_at TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS admin_permissions (
        user_id INTEGER NOT NULL,
        permission TEXT NOT NULL,
        allowed INTEGER NOT NULL DEFAULT 1,
        PRIMARY KEY(user_id, permission)
    );

    CREATE TABLE IF NOT EXISTS server_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS server_announcements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER NOT NULL,
        text TEXT NOT NULL,
        audience TEXT NOT NULL DEFAULT 'all',
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS scheduled_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_type TEXT NOT NULL,
        payload TEXT NOT NULL,
        run_at TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS clan_tournaments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        season TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'registration',
        created_at TEXT NOT NULL,
        started_at TEXT,
        finished_at TEXT
    );

    CREATE TABLE IF NOT EXISTS clan_tournament_entries (
        tournament_id INTEGER NOT NULL,
        clan_id INTEGER NOT NULL,
        seed INTEGER,
        eliminated INTEGER NOT NULL DEFAULT 0,
        wins INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(tournament_id, clan_id)
    );

    CREATE TABLE IF NOT EXISTS clan_tournament_rosters (
        tournament_id INTEGER NOT NULL,
        clan_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        accepted INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(tournament_id, clan_id, user_id)
    );

    CREATE TABLE IF NOT EXISTS clan_war_matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tournament_id INTEGER NOT NULL,
        clan_a INTEGER NOT NULL,
        clan_b INTEGER NOT NULL,
        round_name TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'waiting',
        winner_clan_id INTEGER,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS clan_war_duels (
        match_id INTEGER NOT NULL,
        duel_no INTEGER NOT NULL,
        clan_a_user INTEGER NOT NULL,
        clan_b_user INTEGER NOT NULL,
        winner_user INTEGER,
        status TEXT NOT NULL DEFAULT 'pending',
        PRIMARY KEY(match_id, duel_no)
    );

    CREATE TABLE IF NOT EXISTS story_progress (
        user_id INTEGER PRIMARY KEY,
        chapter INTEGER NOT NULL DEFAULT 1,
        stage INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS story_npcs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        npc_key TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        chapter INTEGER NOT NULL,
        stage INTEGER NOT NULL
    );
    """)

# ============================================================
# PETS — ДОБАВЛЕНИЕ ПИТОМЦЕВ В БАЗУ
# ============================================================

def init_pets():

    # Добавляем недостающие колонки в существующую таблицу
    columns = db_execute(
        "PRAGMA table_info(pets)",
        fetchall=True
    )

    column_names = {
        row["name"]
        for row in columns
    }

    if "description" not in column_names:
        db_execute("""
            ALTER TABLE pets
            ADD COLUMN description TEXT NOT NULL DEFAULT ''
        """)

    if "price_dcr" not in column_names:
        db_execute("""
            ALTER TABLE pets
            ADD COLUMN price_dcr INTEGER NOT NULL DEFAULT 0
        """)

    # Добавляем обычных питомцев
    for key, name, rarity, description, price in PETS:

        db_execute(
            """
            INSERT OR IGNORE INTO pets
            (
                pet_key,
                name,
                rarity,
                description,
                price_dcr
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                key,
                name,
                rarity,
                description,
                price
            )
        )

        # Обновляем описание и цену,
        # если питомец уже существовал в базе
        db_execute(
            """
            UPDATE pets
            SET
                name=?,
                rarity=?,
                description=?,
                price_dcr=?
            WHERE pet_key=?
            """,
            (
                name,
                rarity,
                description,
                price,
                key
            )
        )

    

    # ============================================================
    # ДОБАВЛЯЕМ ПИТОМЦЕВ В МАГАЗИН
    # ============================================================

    for key, name, rarity, description, price in PETS:

        db_execute(
            """
            INSERT OR IGNORE INTO items
            (
                item_key,
                name,
                item_type,
                rarity,
                price_dcr
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                key,
                name,
                "pet",
                rarity,
                price
            )
        )

# ============================================================
# GENERAL HELPERS
# ============================================================

def now_iso():
    return datetime.now(timezone.utc).isoformat()








































# ============================================================
# INVENTORY / EQUIPMENT
# ============================================================









    
# ============================================================
# UI
# ============================================================















# ============================================================
# TEXT SCREENS
# ============================================================







# ============================================================
# START / MENU
# ============================================================











# ============================================================
# GAME / WORLD
# ============================================================





# ============================================================
# PVE
# ============================================================



# ============================================================
# PVE — BATTLE KEYBOARD
# ============================================================



# ============================================================
# PVE — BATTLE TEXT
# ============================================================



# ============================================================
# PVE — OPEN
# ============================================================



# ============================================================
# PVE — START BATTLE
# ============================================================


# ============================================================
# PVE — BATTLE ACTIONS
# ============================================================

@dp.callback_query(F.data.startswith("battle:"))
async def battle_action_callback(call: CallbackQuery):
    user_id = call.from_user.id

    action = call.data.split(":", 1)[1]

    b = db_execute(
        "SELECT * FROM pve_battles WHERE user_id=?",
        (user_id,),
        fetchone=True
    )

    if not b:
        await call.answer(
            "Бой уже завершён.",
            show_alert=True
        )

        await safe_edit(
            call.message,
            "⚔️ Бой завершён.",
            game_menu()
        )

        return


    # ========================================================
    # СДАТЬСЯ
    # ========================================================

    if action == "flee":

        db_execute(
            "DELETE FROM pve_battles WHERE user_id=?",
            (user_id,)
        )

        await call.answer("Ты сдался.")

        await safe_edit(
            call.message,
            "🏳️ <b>Ты покинул бой.</b>",
            game_menu()
        )
        
        clear_pve_effects(user_id)
        pve_ability_uses.pop(user_id, None)

        task = pve_effect_tasks.pop(user_id, None)
        if task:
            task.cancel()

        db_execute(
            "DELETE FROM pve_battle_log WHERE user_id=?",
            (user_id,)
        )
        return


        # ========================================================
    # СПОСОБНОСТЬ
    # ========================================================

    if action == "ability":
        used = get_pve_ability_uses(user_id)
        if used >= 2:
            await call.answer("🌌 Способность уже использована 2 раза за этот бой.", show_alert=True)
            return

        eq = get_equipment(user_id)
        if not eq or not eq["ability_id"]:
            await call.answer("🌌 У тебя нет экипированной способности.", show_alert=True)
            return

        ability_key = str(eq["ability_key"])
        ability_name = eq["ability_name"] or ability_key
        player_hp = int(b["player_hp"])
        max_hp = int(b["player_max_hp"])
        enemy_hp = int(b["enemy_hp"])
        damage = 0
        heal = 0
        extra_text = ""

        # Все обычные способности из магазина имеют здесь реальные эффекты.
        if ability_key == "sacrificial_strike":
            damage = max(1, int(random.randint(35, 55) * 1.75))
            self_damage = max(1, int(max_hp * 0.08))
            player_hp = max(1, player_hp - self_damage)
            extra_text = f"💔 Ты потерял {self_damage} HP."

        elif ability_key in ("rupture",):
            damage = random.randint(55, 75)
            add_pve_effect(user_id, "enemy", "bleed", 18, 3, 1)
            extra_text = "🩸 Наложено кровотечение."

        elif ability_key in ("firestorm", "ability_firestorm"):
            damage = random.randint(75, 100)
            add_pve_effect(user_id, "enemy", "burn", 20, 4, 1)
            extra_text = "🔥 Враг горит."

        elif ability_key == "frost_grip":
            damage = random.randint(65, 90)
            add_pve_effect(user_id, "enemy", "frost", 0, 2, 1)
            extra_text = "🧊 Враг замедлен на 2 хода."

        elif ability_key == "lightning_strike":
            damage = random.randint(100, 135)
            extra_text = "⚡ Молния пробила врага."

        elif ability_key == "last_chance":
            damage = random.randint(45, 65)
            heal = max(1, int(max_hp * 0.20))
            player_hp = min(max_hp, player_hp + heal)
            extra_text = f"🛡️ Восстановлено {heal} HP."

        elif ability_key in ("evasion", "ability_shadow_step"):
            add_pve_effect(user_id, "player", "dodge", 0, 2, 1)
            pve_ability_uses[user_id] = used + 1
            add_pve_log(user_id, f"🌌 «{esc(ability_name)}»: повышен шанс уклонения на 2 хода.")
            await call.answer("🌀 Уклонение активировано!")
            await safe_edit(call.message, battle_row(user_id), battle_keyboard(user_id))
            return

        elif ability_key in ("rebirth", "divine_rebirth"):
            heal = max(1, int(max_hp * 0.50))
            new_hp = min(max_hp, player_hp + heal)
            actual = new_hp - player_hp
            if actual <= 0:
                await call.answer("❤️ У тебя уже максимальное HP.", show_alert=True)
                return
            player_hp = new_hp
            extra_text = f"🩹 Восстановлено {actual} HP."

        elif ability_key == "berserk":
            # +30% к урону на 2 следующие атаки.
            db_execute("INSERT INTO pve_battle_events(user_id,event_type,event_text,active,countdown,created_at) VALUES(?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET event_type=excluded.event_type,event_text=excluded.event_text,active=1,countdown=2,created_at=excluded.created_at", (user_id, "damage_berserk", "😈 Берсерк: +30% к урону — осталось 2 атаки", 1, 2, time.time()))
            pve_ability_uses[user_id] = used + 1
            add_pve_log(user_id, f"😈 «{esc(ability_name)}» активирован: +30% к урону на 2 атаки.")
            await call.answer("😈 Берсерк активирован!")
            await safe_edit(call.message, battle_row(user_id), battle_keyboard(user_id))
            return

        elif ability_key == "wrath_of_heaven":
            damage = 150
            add_pve_effect(user_id, "enemy", "burn", 25, 5, 1)
            extra_text = "🔥 Наложено горение."

        elif ability_key == "ability_vampiric":
            damage = 110
            heal = 70
            player_hp = min(max_hp, player_hp + heal)
            add_pve_effect(user_id, "enemy", "bleed", 16, 4, 1)
            extra_text = f"❤️ Восстановлено {heal} HP."

        else:
            await call.answer("🌌 Неизвестная способность.", show_alert=True)
            return

        if damage > 0:
            # Берсерк/другие боевые модификаторы применяются к способности тоже.
            berserk = db_execute("SELECT countdown,event_type FROM pve_battle_events WHERE user_id=? AND active=1", (user_id,), fetchone=True)
            if berserk and berserk["event_type"] == "damage_berserk":
                damage = max(1, int(damage * 1.30))
                left = max(0, int(berserk["countdown"]) - 1)
                if left <= 0:
                    db_execute("DELETE FROM pve_battle_events WHERE user_id=?", (user_id,))
                else:
                    db_execute("UPDATE pve_battle_events SET countdown=?,event_text=? WHERE user_id=?", (left, f"😈 Берсерк: +30% к урону — осталось {left} атаки", user_id))
            enemy_hp = max(0, enemy_hp - damage)

        db_execute("UPDATE pve_battles SET enemy_hp=?, player_hp=?, last_action=? WHERE user_id=?", (enemy_hp, player_hp, time.time(), user_id))
        pve_ability_uses[user_id] = used + 1
        log = f"🌌 «{esc(ability_name)}»"
        if damage: log += f" нанесла {damage} урона."
        if extra_text: log += f" {extra_text}"
        add_pve_log(user_id, log)

        await call.answer(f"🌌 {ability_name} использована!")

        if enemy_hp <= 0:
            db_execute("DELETE FROM pve_battles WHERE user_id=?", (user_id,))
            clear_pve_effects(user_id)
            task = pve_effect_tasks.pop(user_id, None)
            if task: task.cancel()
            add_dcr(user_id, b["reward_dcr"], f"PvE: {b['enemy_name']}")
            add_xp(user_id, max(20, b["reward_dcr"] // 2))
            pve_ability_uses.pop(user_id, None)
            p = get_player(user_id)
            await safe_edit(call.message, f"🏆 <b>ПОБЕДА!</b>\n\n☠️ {esc(b['enemy_name'])} повержен.\n🌌 «{esc(ability_name)}» нанесла {damage} урона.\n💰 +{fmt(b['reward_dcr'])} DCR\n✨ XP получен\n\n💰 Баланс: {fmt(p['dcr'])} DCR", game_menu())
            return

        if user_id not in pve_effect_tasks:
            pve_effect_tasks[user_id] = asyncio.create_task(pve_effect_loop(user_id, call.message))
        await safe_edit(call.message, battle_row(user_id), battle_keyboard(user_id))
        return

    # ========================================================
    # ЗЕЛЬЕ
    # ========================================================

    if action == "potion":

        # ----------------------------------------------------
        # Кулдаун зелья — 3 секунды
        # ----------------------------------------------------

        now = time.monotonic()

        last_potion_time = (
            pve_potion_cooldowns.get(
                user_id,
                0
            )
        )

        cooldown_left = (
            3.0
            - (now - last_potion_time)
        )

        if cooldown_left > 0:

            await call.answer(
                f"🧪 Подожди {cooldown_left:.1f} сек.",
                show_alert=True
            )

            return


        # ----------------------------------------------------
        # Проверяем наличие зелий
        # ----------------------------------------------------

        potions = [
            x
            for x in get_inventory(user_id)
            if x["item_type"] == "potion"
            and x["quantity"] > 0
        ]

        if not potions:

            await call.answer(
                "🧪 У тебя нет зелий.",
                show_alert=True
            )

            return


        potion = potions[0]


        # ----------------------------------------------------
        # Проверяем HP
        # ----------------------------------------------------

        max_hp = int(
            b["player_max_hp"]
        )

        current_hp = int(
            b["player_hp"]
        )

        if current_hp >= max_hp:

            await call.answer(
                "❤️ У тебя уже полное здоровье.",
                show_alert=True
            )

            return


        # ----------------------------------------------------
        # Размер лечения
        # ----------------------------------------------------

        heal_percent = {
            "Редкий": 0.10,
            "Эпический": 0.20,
            "Легендарный": 0.35,
            "Мифический": 0.60,
            "Демонический": 1.00,
        }.get(
            potion["rarity"],
            0.10
        )

        heal = int(
            max_hp * heal_percent
        )

        heal = max(
            1,
            heal
        )


        # ----------------------------------------------------
        # Новый HP
        # ----------------------------------------------------

        new_hp = min(
            max_hp,
            current_hp + heal
        )

        actual_heal = (
            new_hp - current_hp
        )


        # ----------------------------------------------------
        # Забираем зелье
        # ----------------------------------------------------

        remove_item(
            user_id,
            potion["item_key"],
            1
        )


        # ----------------------------------------------------
        # Сохраняем HP
        # ----------------------------------------------------

        db_execute(
            """
            UPDATE pve_battles
            SET player_hp=?
            WHERE user_id=?
            """,
            (
                new_hp,
                user_id
            )
        )


        # ----------------------------------------------------
        # Запускаем кулдаун
        # ----------------------------------------------------

        pve_potion_cooldowns[user_id] = (
            time.monotonic()
        )


        # ----------------------------------------------------
        # Получаем свежий бой
        # ----------------------------------------------------

        b = db_execute(
            "SELECT * FROM pve_battles WHERE user_id=?",
            (user_id,),
            fetchone=True
        )

        if not b:

            await call.answer(
                "Бой уже завершён.",
                show_alert=True
            )

            return


        await call.answer(
            f"🧪 +{actual_heal} HP"
        )

        await safe_edit(
            call.message,
            battle_row(user_id),
            battle_keyboard(user_id)
        )

        return

    # ====================================================
    # АТАКА
    # ====================================================

    if action == "attack":

        # ------------------------------------------------
        # Кулдаун атаки — 1.5 секунды
        # ------------------------------------------------

        if (
            time.time()
            - float(b["last_action"])
            < 1.5
        ):

            await call.answer(
                "⚔️ Слишком быстро. Подожди немного.",
                show_alert=True
            )

            return

        # ------------------------------------------------
        # Статы игрока
        # ------------------------------------------------

        stats = player_combat_stats(user_id)

        # ------------------------------------------------
        # Урон игрока
        # ------------------------------------------------

        damage = random.randint(
            stats["attack_min"],
            stats["attack_max"]
        )

        # "Опустошение": 2 charges = 2 player attacks.
        boost_event = db_execute(
            "SELECT countdown,event_type FROM pve_battle_events WHERE user_id=? AND active=1",
            (user_id,), fetchone=True
        )
        if boost_event and boost_event["event_type"] == "damage_boost":
            damage = max(1, int(damage * 1.05))
            update_pve_effect_countdowns(user_id)
        elif boost_event and boost_event["event_type"] == "damage_berserk":
            damage = max(1, int(damage * 1.30))
            update_pve_effect_countdowns(user_id)

        enemy_hp = max(
            0,
            int(b["enemy_hp"]) - damage
        )

        # ------------------------------------------------
        # Сохраняем HP врага
        # ------------------------------------------------

        db_execute(
            """
            UPDATE pve_battles
            SET
                enemy_hp=?,
                last_action=?
            WHERE user_id=?
            """,
            (
                enemy_hp,
                time.time(),
                user_id
            )
        )

        # ====================================================
        # ЭФФЕКТ ОРУЖИЯ
        # ====================================================

        weapon_effect_text = ""

        eq = get_equipment(user_id)

        if eq and eq["weapon_key"]:

            weapon_effect = WEAPON_EFFECTS.get(
                eq["weapon_key"]
            )

            if (
                weapon_effect
                and random.random() < weapon_effect["chance"]
            ):

                add_pve_effect(
                    user_id=user_id,
                    target="enemy",
                    effect_type=weapon_effect["type"],
                    damage=weapon_effect["damage"],
                    duration=weapon_effect["duration"],
                    tick_interval=1.0
                )

                if weapon_effect["type"] == "burn":

                    weapon_effect_text = (
                        f"🔥 Горение наложено на "
                        f"{weapon_effect['duration']} сек. "
                        f"({weapon_effect['damage']} урона/сек.)"
                    )

                elif weapon_effect["type"] == "bleed":

                    weapon_effect_text = (
                        f"🩸 Кровотечение наложено на "
                        f"{weapon_effect['duration']} сек. "
                        f"({weapon_effect['damage']} урона/сек.)"
                    )

                add_pve_log(
                    user_id,
                    weapon_effect_text
                )

        # ====================================================
        # ЗАПУСК ЦИКЛА ЭФФЕКТОВ
        # ====================================================

        if user_id not in pve_effect_tasks:

            task = asyncio.create_task(
                pve_effect_loop(
                    user_id,
                    call.message
                )
            )

            pve_effect_tasks[user_id] = task

        # ====================================================
        # ПОБЕДА
        # ====================================================

        if enemy_hp <= 0:

            db_execute(
                "DELETE FROM pve_battles WHERE user_id=?",
                (user_id,)
            )

            clear_pve_effects(user_id)

            task = pve_effect_tasks.pop(
                user_id,
                None
            )

            if task:
                task.cancel()

            add_dcr(
                user_id,
                b["reward_dcr"],
                f"PvE: {b['enemy_name']}"
            )

            add_xp(
                user_id,
                max(
                    20,
                    b["reward_dcr"] // 2
                )
            )

            # PvE победа учитывается в профиле.
            db_execute(
                "UPDATE players SET wins=wins+1 WHERE user_id=?",
                (user_id,)
            )

            # Продвигаем сюжет, если это сюжетный бой.
            if str(b["location"]).startswith("story:"):
                try:
                    story_stage = int(str(b["location"]).split(":", 1)[1])
                    db_execute("""
                        INSERT INTO story_progress(user_id,chapter,stage,updated_at)
                        VALUES(?,?,?,?)
                        ON CONFLICT(user_id) DO UPDATE SET
                            stage=excluded.stage,
                            updated_at=excluded.updated_at
                    """, (user_id, 1, story_stage + 1, now_iso()))
                except Exception:
                    log.exception("Ошибка обновления сюжетного прогресса")

            # ------------------------------------------------
            # Шанс выпадения частиц
            # ------------------------------------------------

            enemy_ratio = min(
                0.18,
                0.04 + b["reward_dcr"] / 12000
            )

            particle_drop = (
                random.random()
                < enemy_ratio
            )

            if particle_drop:

                add_item(
                    user_id,
                    b["particle_type"],
                    random.randint(1, 3)
                )

            p = get_player(user_id)

            msg = (
                f"🏆 <b>ПОБЕДА!</b>\n\n"
                f"☠️ {esc(b['enemy_name'])} повержен.\n"
                f"⚔️ Урон: {damage}\n"
                f"💰 +{fmt(b['reward_dcr'])} DCR\n"
                f"✨ XP получен\n"
            )

            if particle_drop:

                msg += "🧩 Частицы получены\n"

            if weapon_effect_text:

                msg += (
                    f"\n{weapon_effect_text}\n"
                )

            msg += (
                f"\n💰 Баланс: "
                f"{fmt(p['dcr'])} DCR"
            )

            await call.answer(
                "🏆 Победа!"
            )

            await safe_edit(
                call.message,
                msg,
                game_menu()
            )

            return

        # ====================================================
        # ВРАГ АТАКУЕТ
        # ====================================================

        incoming = random.randint(
            b["enemy_min_damage"],
            b["enemy_max_damage"]
        )

        dodge_event = db_execute("SELECT active,event_type,countdown FROM pve_battle_events WHERE user_id=?", (user_id,), fetchone=True)
        if dodge_event and int(dodge_event["active"]) == 1 and dodge_event["event_type"] == "dodge" and random.random() < 0.45:
            left = max(0, int(dodge_event["countdown"]) - 1)
            db_execute("UPDATE pve_battle_events SET countdown=?,active=? WHERE user_id=?", (left, 0 if left == 0 else 1, user_id))
            add_pve_log(user_id, "👻 Ты уклонился от атаки врага!")
            await call.answer("👻 Уклонение!")
            await safe_edit(call.message, battle_row(user_id), battle_keyboard(user_id))
            return

        shield_text = ""

        # ------------------------------------------------
        # Щит
        # ------------------------------------------------

        if random.random() < stats["shield_chance"]:

            incoming = int(
                incoming
                * (
                    1
                    - stats["shield_reduction"]
                )
            )

            shield_text = (
                " 🔰 Щит сработал!"
            )

        # ------------------------------------------------
        # Броня
        # ------------------------------------------------

        incoming = max(
            1,
            int(
                incoming
                * (
                    1
                    - stats["armor_reduction"]
                )
            )
        )

        player_hp = max(
            0,
            int(b["player_hp"]) - incoming
        )

        # ------------------------------------------------
        # Сохраняем результат хода
        # ------------------------------------------------

        db_execute(
            """
            UPDATE pve_battles
            SET
                enemy_hp=?,
                player_hp=?,
                last_action=?
            WHERE user_id=?
            """,
            (
                enemy_hp,
                player_hp,
                time.time(),
                user_id
            )
        )

        # ====================================================
        # ПОРАЖЕНИЕ
        # ====================================================

        if player_hp <= 0:

            db_execute(
                "DELETE FROM pve_battles WHERE user_id=?",
                (user_id,)
            )

            clear_pve_effects(user_id)

            task = pve_effect_tasks.pop(
                user_id,
                None
            )

            if task:
                task.cancel()

            db_execute(
                """
                UPDATE players
                SET
                    losses=losses+1,
                    deaths=deaths+1
                WHERE user_id=?
                """,
                (user_id,)
            )

            await call.answer(
                "Ты проиграл."
            )

            await safe_edit(
                call.message,
                (
                    f"💀 <b>ПОРАЖЕНИЕ</b>\n\n"
                    f"Тебя победил: "
                    f"{esc(b['enemy_name'])}\n"
                    f"💥 Получено урона: "
                    f"{incoming}"
                    f"{shield_text}"
                ),
                game_menu()
            )

            return

        # ====================================================
        # ОБНОВЛЯЕМ БОЙ
        # ====================================================

        await call.answer(
            f"⚔️ -{damage} HP врагу"
        )

        battle_text = battle_row(user_id)

        if weapon_effect_text:

            battle_text += (
                "\n\n"
                + weapon_effect_text
            )

        log_text = pve_battle_log_text(user_id)

        if log_text:

            battle_text += (
                "\n\n"
                + log_text
            )

        effects_text = pve_effects_text(user_id)

        if effects_text:

            battle_text += (
                "\n\n"
                + effects_text
            )

        await safe_edit(
            call.message,
            battle_text,
            battle_keyboard(user_id)
        )

        return
    
# ============================================================
# PVE — EFFECT LOOP
# ============================================================

async def pve_effect_loop(user_id, message):
    """Единый фоновой цикл PvE-эффектов. HP и ACTIVE EFFECTS обновляются в одном сообщении."""
    try:
        while True:
            battle = db_execute(
                "SELECT * FROM pve_battles WHERE user_id=?",
                (user_id,), fetchone=True
            )
            if not battle:
                clear_pve_effects(user_id)
                return

            now = time.time()
            effects = get_pve_effects(user_id)
            changed = False

            for effect in effects:
                effect_id = effect["id"]
                expires_at = float(effect["expires_at"])
                next_tick = float(effect["next_tick"])

                if now >= expires_at:
                    db_execute("DELETE FROM pve_effects WHERE id=?", (effect_id,))
                    changed = True
                    continue

                if now >= next_tick:
                    damage = max(0, int(effect["damage"]))
                    current_battle = db_execute(
                        "SELECT enemy_hp, player_hp FROM pve_battles WHERE user_id=?",
                        (user_id,), fetchone=True
                    )
                    if not current_battle:
                        clear_pve_effects(user_id)
                        return

                    if effect["target"] == "enemy":
                        new_hp = max(0, int(current_battle["enemy_hp"]) - damage)
                        db_execute(
                            "UPDATE pve_battles SET enemy_hp=? WHERE user_id=?",
                            (new_hp, user_id)
                        )
                        changed = True

                        if new_hp <= 0:
                            reward_dcr = int(battle["reward_dcr"])
                            add_dcr(user_id, reward_dcr, f"PvE: {battle['enemy_name']}")
                            xp_amount = max(20, reward_dcr // 2)
                            add_xp(user_id, xp_amount)
                            db_execute("UPDATE players SET wins=wins+1 WHERE user_id=?", (user_id,))

                            enemy_ratio = min(0.18, 0.04 + reward_dcr / 12000)
                            particle_drop = random.random() < enemy_ratio
                            if particle_drop:
                                add_item(user_id, battle["particle_type"], random.randint(1, 3))

                            db_execute("DELETE FROM pve_battles WHERE user_id=?", (user_id,))
                            clear_pve_effects(user_id)
                            p = get_player(user_id)
                            msg = (
                                "🏆 <b>ПОБЕДА!</b>\n\n"
                                f"☠️ {esc(battle['enemy_name'])} повержен.\n"
                                "🔥 Враг погиб от эффекта.\n"
                                f"⚔️ Урон последнего тика: {damage}\n"
                                f"💰 +{fmt(reward_dcr)} DCR\n"
                                f"✨ +{xp_amount} XP\n"
                                "🎫 Battle Pass: опыт начислен\n"
                            )
                            if particle_drop:
                                msg += "🧩 Частицы получены\n"
                            msg += f"\n💰 Баланс: {fmt(p['dcr'])} DCR"
                            await safe_edit(message, msg, game_menu())
                            return

                    # Tick scheduling is based on the current time, preventing runaway catch-up.
                    db_execute(
                        "UPDATE pve_effects SET next_tick=? WHERE id=?",
                        (now + max(0.5, float(effect.get("tick_interval", 1.0) if hasattr(effect, "get") else 1.0)), effect_id)
                    )

            current = db_execute(
                "SELECT * FROM pve_battles WHERE user_id=?",
                (user_id,), fetchone=True
            )
            if not current:
                clear_pve_effects(user_id)
                return

            effects_text = pve_effects_text(user_id)
            log_text = pve_battle_log_text(user_id)
            text = battle_row(user_id)
            if effects_text:
                text += "\n\n" + effects_text
            if log_text:
                text += "\n\n" + log_text
            await safe_edit(message, text, battle_keyboard(user_id))

            # If nothing changed, still refresh often enough for the countdown to move.
            await asyncio.sleep(0.5 if changed else 0.75)

    except asyncio.CancelledError:
        return
    except Exception:
        logging.exception("Ошибка PVE effect loop для %s", user_id)
    finally:
        if pve_effect_tasks.get(user_id) is asyncio.current_task():
            pve_effect_tasks.pop(user_id, None)



@dp.callback_query(F.data == "pve_potions")
async def pve_potions_callback(call: CallbackQuery):
    user_id = call.from_user.id
    if not db_execute("SELECT 1 FROM pve_battles WHERE user_id=?", (user_id,), fetchone=True):
        await call.answer("Бой уже завершён.", show_alert=True)
        return
    inv = [x for x in get_inventory(user_id) if x["item_type"] == "potion" and int(x["quantity"]) > 0]
    rows = []
    for item in inv:
        key = item["item_key"]
        name = item["name"]
        qty = int(item["quantity"])
        if key == "potion_void": desc = "+5% урона на 2 атаки"
        elif key == "potion_regen": desc = "+30% HP"
        elif key == "potion_invisibility": desc = "45% уклонения на 2 хода"
        else: desc = f"Лечение: {int({'Редкий':10,'Эпический':20,'Легендарный':35,'Мифический':60,'Демонический':100}.get(item['rarity'],10))}% HP"
        rows.append([InlineKeyboardButton(text=f"{name} ×{qty} — {desc}", callback_data=f"pve_potion:{key}")])
    if not rows:
        rows.append([InlineKeyboardButton(text="🧪 Зелий нет", callback_data="potion_unavailable")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="pve")])
    await call.answer()
    await safe_edit(call.message, "🧪 <b>ЗЕЛЬЯ В БОЮ</b>\n\nЗдесь отображаются все зелья из твоего инвентаря:", InlineKeyboardMarkup(inline_keyboard=rows))

@dp.callback_query(F.data == "potion_unavailable")
async def potion_unavailable_callback(call: CallbackQuery):
    await call.answer("🧪 У тебя нет зелий.", show_alert=True)

def update_pve_effect_countdowns(user_id):
    row = db_execute("SELECT countdown,event_type FROM pve_battle_events WHERE user_id=? AND active=1", (user_id,), fetchone=True)
    if not row:
        return 0
    c = max(0, int(row["countdown"] or 0) - 1)
    if c <= 0:
        db_execute("DELETE FROM pve_battle_events WHERE user_id=?", (user_id,))
        return 0
    if row["event_type"] == "damage_boost":
        text = f"🕳️ Опустошение: +5% к урону — осталось {c} атаки"
    elif row["event_type"] == "dodge":
        text = f"👻 Невидимость: шанс уклонения — осталось {c} ход"
    else:
        text = None
    if text:
        db_execute("UPDATE pve_battle_events SET countdown=?,event_text=? WHERE user_id=?", (c, text, user_id))
    else:
        db_execute("UPDATE pve_battle_events SET countdown=? WHERE user_id=?", (c, user_id))
    return c

@dp.callback_query(F.data.startswith("pve_potion:"))
async def pve_potion_use_callback(call: CallbackQuery):
    user_id = call.from_user.id
    key = call.data.split(":", 1)[1]
    battle = db_execute("SELECT * FROM pve_battles WHERE user_id=?", (user_id,), fetchone=True)
    if not battle:
        await call.answer("Бой завершён.", show_alert=True)
        return
    item = db_execute("SELECT * FROM items WHERE item_key=? AND item_type='potion'", (key,), fetchone=True)
    if not item:
        await call.answer("Зелье не найдено в базе.", show_alert=True)
        return
    inv = db_execute("SELECT quantity FROM inventory WHERE user_id=? AND item_id=?", (user_id, item["item_id"]), fetchone=True)
    if not inv or int(inv["quantity"]) <= 0:
        await call.answer("Такого зелья нет в инвентаре.", show_alert=True)
        return
    if not remove_item(user_id, key, 1):
        await call.answer("Не удалось использовать зелье.", show_alert=True)
        return

    if key == "potion_void":
        db_execute("INSERT INTO pve_battle_events(user_id,event_type,event_text,active,countdown,created_at) VALUES(?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET event_type=excluded.event_type,event_text=excluded.event_text,active=1,countdown=2,created_at=excluded.created_at", (user_id,"damage_boost","🕳️ Опустошение: +5% к урону — осталось 2 атаки",1,2,time.time()))
        text = "🕳️ Опустошение активировано — +5% урона на 2 атаки."
    elif key == "potion_regen":
        heal = max(1, int(int(battle["player_max_hp"]) * 0.30))
        new_hp = min(int(battle["player_max_hp"]), int(battle["player_hp"]) + heal)
        actual = new_hp - int(battle["player_hp"])
        db_execute("UPDATE pve_battles SET player_hp=? WHERE user_id=?", (new_hp, user_id))
        text = f"❤️ Регенерация — восстановлено {actual} HP."
    elif key == "potion_invisibility":
        db_execute("INSERT INTO pve_battle_events(user_id,event_type,event_text,active,countdown,created_at) VALUES(?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET event_type=excluded.event_type,event_text=excluded.event_text,active=1,countdown=2,created_at=excluded.created_at", (user_id,"dodge","👻 Невидимость: шанс уклонения — осталось 2 хода",1,2,time.time()))
        text = "👻 Невидимость активирована — 45% уклонения на 2 хода."
    else:
        percent = int({"Редкий":10,"Эпический":20,"Легендарный":35,"Мифический":60,"Демонический":100}.get(item["rarity"],10))
        max_hp = int(battle["player_max_hp"])
        current = int(battle["player_hp"])
        heal = max(1, int(max_hp * percent / 100))
        new_hp = min(max_hp, current + heal)
        actual = new_hp - current
        if actual <= 0:
            add_item(user_id, key, 1)
            await call.answer("❤️ У тебя уже максимальное HP.", show_alert=True)
            return
        db_execute("UPDATE pve_battles SET player_hp=? WHERE user_id=?", (new_hp, user_id))
        text = f"🧪 {esc(item['name'])} — восстановлено {actual} HP."

    add_pve_log(user_id, text)
    await call.answer("🧪 Зелье использовано")
    await safe_edit(call.message, battle_row(user_id), battle_keyboard(user_id))


# ============================================================
# INVENTORY / EQUIPMENT
# ============================================================

def add_item(user_id, item_key, quantity=1):
    item = db_execute("SELECT item_id FROM items WHERE item_key=?", (item_key,), fetchone=True)
    if not item:
        return False
    db_execute("""
    INSERT INTO inventory(user_id,item_id,quantity) VALUES(?,?,?)
    ON CONFLICT(user_id,item_id) DO UPDATE SET quantity=quantity+excluded.quantity
    """, (user_id, item["item_id"], quantity))
    return True


def remove_item(user_id, item_key, quantity=1):
    row = db_execute("""
    SELECT i.item_id, inv.quantity
    FROM inventory inv JOIN items i ON i.item_id=inv.item_id
    WHERE inv.user_id=? AND i.item_key=?
    """, (user_id, item_key), fetchone=True)
    if not row or row["quantity"] < quantity:
        return False
    if row["quantity"] == quantity:
        db_execute("DELETE FROM inventory WHERE user_id=? AND item_id=?", (user_id, row["item_id"]))
    else:
        db_execute("""
        UPDATE inventory SET quantity=quantity-? WHERE user_id=? AND item_id=?
        """, (quantity, user_id, row["item_id"]))
    return True


def get_inventory(user_id):
    return db_execute("""
    SELECT i.*, inv.quantity
    FROM inventory inv JOIN items i ON i.item_id=inv.item_id
    WHERE inv.user_id=? AND inv.quantity>0
    ORDER BY i.item_type, i.rarity, i.name
    """, (user_id,), fetchall=True)


def equip_item(user_id, item_key):
    item = db_execute(
        "SELECT * FROM items WHERE item_key=?",
        (item_key,),
        fetchone=True
    )

    if not item:
        return False, "Предмет не найден."

    # Какие предметы можно экипировать
    equipment_columns = {
        "weapon": "weapon_id",
        "armor": "armor_id",
        "shield": "shield_id",
        "ability": "ability_id",
        "pet": "pet_id",
    }

    item_type = item["item_type"]

    if item_type not in equipment_columns:
        return False, "Этот предмет нельзя экипировать."

    # Проверяем наличие предмета в инвентаре
    inv = db_execute(
        """
        SELECT quantity
        FROM inventory
        WHERE user_id=? AND item_id=?
        """,
        (user_id, item["item_id"]),
        fetchone=True
    )

    if not inv or inv["quantity"] <= 0:
        return False, "Предмет отсутствует в инвентаре."

    column = equipment_columns[item_type]

    # Автоматически экипируем предмет
    db_execute(
        f"UPDATE equipment SET {column}=? WHERE user_id=?",
        (item["item_id"], user_id)
    )

    return True, f"Экипирован: {esc(item['name'])}"


# ============================================================
# UI
# ============================================================

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 ИГРАТЬ", callback_data="game")],
        [
            InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
            InlineKeyboardButton(text="💰 Баланс", callback_data="balance"),
        ],
        [
            InlineKeyboardButton(text="🛒 Магазин", callback_data="shop"),
            InlineKeyboardButton(text="🎒 Инвентарь", callback_data="inventory"),
        ],
        [InlineKeyboardButton(text="📂 Прочее", callback_data="other")],
    ])


def back_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")]
    ])


def game_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚔️ PvE", callback_data="pve"), InlineKeyboardButton(text="🏆 PvP", callback_data="pvp")],
        [InlineKeyboardButton(text="📖 Сюжет", callback_data="story"), InlineKeyboardButton(text="🔥 Мировой босс", callback_data="boss")],
        [InlineKeyboardButton(text="🗺️ Мир", callback_data="world")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")],
    ])

def shop_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="⚔️ Оружие",
                callback_data="shop_weapons"
            ),
            InlineKeyboardButton(
                text="🛡️ Броня",
                callback_data="shop_armor"
            )
        ],
        [
            InlineKeyboardButton(
                text="🧪 Зелья",
                callback_data="shop_potions"
            ),
            InlineKeyboardButton(
                text="🎁 Кейсы",
                callback_data="shop_cases"
            )
        ],
        [
            InlineKeyboardButton(
                text="🐾 Питомцы",
                callback_data="shop_pets"
            ),
            InlineKeyboardButton(
                text="🌌 Способности",
                callback_data="shop_abilities"
            )
        ],
        [
            InlineKeyboardButton(
                text="💎 Премиальные предметы",
                callback_data="shop_premium"
            )
        ],
        [
            InlineKeyboardButton(
                text="💎 Купить кристаллы",
                callback_data="shop_crystals"
            )
        ],
        [
            InlineKeyboardButton(
                text="🎫 Battle Pass",
                callback_data="shop_bp"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data="menu"
            )
        ],
    ])

def inventory_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="⚔️ Экипировка",
                callback_data="equipment"
            )
        ],
        [
            InlineKeyboardButton(
                text="🧪 Зелья",
                callback_data="inv_potions"
            )
        ],
        [
            InlineKeyboardButton(
                text="🧩 Материалы",
                callback_data="inv_materials"
            )
        ],
        [
            InlineKeyboardButton(
                text="🌌 Способности",
                callback_data="inv_abilities"
            )
        ],
        [
            InlineKeyboardButton(
                text="🐾 Питомцы",
                callback_data="inv_pets"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data="menu"
            )
        ],
    ])

def equipment_keyboard(user_id):
    rows = []

    equipment_types = (
        "weapon",
        "armor",
        "shield",
        "ability",
        "pet",
    )

    for item in get_inventory(user_id):
        if item["item_type"] in equipment_types:
            rows.append([
                InlineKeyboardButton(
                    text=f"{item['name']} ×{item['quantity']}",
                    callback_data=f"equip:{item['item_key']}"
                )
            ])

    rows.append([
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data="inventory"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)

async def safe_edit(message, text, reply_markup=None):
    try:
        await message.edit_text(text, reply_markup=reply_markup)
        return True
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            return True
        try:
            await message.delete()
        except Exception:
            pass
        try:
            await message.answer(text, reply_markup=reply_markup)
            return True
        except Exception:
            log.exception("safe_edit failed")
            return False
    except Exception:
        log.exception("safe_edit failed")
        return False


# ============================================================
# TEXT SCREENS
# ============================================================

def xp_needed(level: int) -> int:
    """Количество XP, необходимое для перехода на следующий уровень."""
    level = max(1, int(level))
    return 100 + (level - 1) * 50

def profile_text(user_id):
    p = get_player(user_id)
    eq = get_equipment(user_id)
    s = get_pvp_stats(user_id)

    # Обычный ранг персонажа — зависит от уровня
    level_rank = rank_for_level(p["level"])

    # PvP-данные
    mmr = int(s["mmr"])
    ranked_games = int(s["ranked_games"])
    ranked_wins = int(s["ranked_wins"])
    ranked_losses = int(s["ranked_losses"])
    calibration_games = int(s["calibration_games"])

    # Обычные PvP-матчи = все PvP-матчи минус рейтинговые
    normal_wins = max(
        0,
        int(s["total_wins"]) - ranked_wins
    )

    normal_losses = max(
        0,
        int(s["total_losses"]) - ranked_losses
    )

    # Пока титулы отдельно не реализованы,
    # используем базовый титул.
    title = "Новичок"

    # PvP-ранг появляется только после калибровки
    if calibration_games < 5:
        pvp_rank_text = "🧪 Калибровка"
        pvp_rank_status = f"{calibration_games}/5"
    else:
        pvp_rank = pvp_rank_for_mmr(mmr)
        pvp_rank_text = f"{pvp_rank['emoji']} {pvp_rank['name']}"
        pvp_rank_status = "Завершена"

    return (
        f"👤 <b>{esc(p['first_name'] or p['username'] or user_id)}</b>\n\n"

        f"⭐ Уровень: <b>{p['level']}</b>\n"
        f"🎖 Ранг: <b>{esc(level_rank)}</b>\n"
        f"🏷 Титул: <b>{esc(title)}</b>\n"
        f"✨ XP: <b>{p['xp']}/{xp_needed(p['level'])}</b>\n"
        f"🎫 Battle Pass: <b>{int(p['bp_level'])}/100</b>\n"
        f"💰 DCR: <b>{fmt(p['dcr'])}</b>\n"
        f"💎 Кристаллы: <b>{fmt(p['crystals'])}</b>\n\n"

        f"⚔️ <b>PvE</b>\n"
        f"Победы: <b>{p['wins']}</b>\n"
        f"Поражения: <b>{p['losses']}</b>\n\n"

        f"🎮 <b>Обычные матчи</b>\n"
        f"Победы: <b>{normal_wins}</b>\n"
        f"Поражения: <b>{normal_losses}</b>\n\n"

        f"🏆 <b>Рейтинговые матчи</b>\n"
        f"Ранг: <b>{pvp_rank_text}</b>\n"
        f"MMR: <b>{mmr}</b>\n"
        f"Калибровка: <b>{pvp_rank_status}</b>\n"
        f"Победы: <b>{ranked_wins}</b>\n"
        f"Поражения: <b>{ranked_losses}</b>\n\n"

        f"⚔️ <b>Экипировка</b>\n"
        f"Оружие: <b>{esc(eq['weapon_name']) if eq and eq['weapon_name'] else '—'}</b>\n"
        f"Броня: <b>{esc(eq['armor_name']) if eq and eq['armor_name'] else '—'}</b>\n"
        f"Щит: <b>{esc(eq['shield_name']) if eq and eq['shield_name'] else '—'}</b>\n"
        f"🌌 Способность: <b>{esc(eq['ability_name']) if eq and eq['ability_name'] else '—'}</b>\n"
        f"🐾 Питомец: <b>{esc(eq['pet_name']) if eq and eq['pet_name'] else '—'}</b>"
    )

def inventory_text(user_id, item_type=None):
    items = get_inventory(user_id)

    if item_type:
        items = [x for x in items if x["item_type"] == item_type]

    if not items:
        return "🎒 <b>Инвентарь</b>\n\nПока здесь пусто."

    lines = ["🎒 <b>Инвентарь</b>\n"]

    for x in items:
        extra = ""

        if x["item_type"] == "weapon":
            extra = f" ⚔️ {x['attack_min']}-{x['attack_max']}"

        elif x["item_type"] == "armor":
            extra = (
                f" 🛡️ -"
                f"{int((x['damage_reduction'] or 0) * 100)}%"
            )

        elif x["item_type"] == "shield":
            extra = (
                f" 🔰 "
                f"{int((x['shield_chance'] or 0) * 100)}%"
            )

        elif x["item_type"] == "ability":
            extra = " 🌌"

        elif x["item_type"] == "pet":
            extra = " 🐾"

        lines.append(
            f"• {esc(x['name'])} "
            f"[{x['rarity']}] "
            f"×{x['quantity']}{extra}"
        )

    return "\n".join(lines)

def balance_text(user_id):
    p = get_player(user_id)
    return f"💰 <b>Баланс</b>\n\nDCR: <b>{fmt(p['dcr'])}</b>\n💎 Кристаллы: <b>{fmt(p['crystals'])}</b>"


# ============================================================
# START / MENU
# ============================================================

@dp.message(CommandStart())
async def start_handler(message: Message):
    ensure_player(message.from_user)
    text = (
        f"👑 <b>{GAME_NAME}</b>\n"
        f"<i>Версия {GAME_VERSION}</i>\n\n"
        "Добро пожаловать в мир DOMINION.\n"
        "Развивай персонажа, сражайся, добывай DCR, "
        "создавай предметы, вступай в кланы и участвуй в мировых событиях.\n\n"
        "Выбирай действие ниже:"
    )
    await message.answer(text, reply_markup=main_menu())


@dp.message(Command("menu"))
async def menu_command(message: Message):
    ensure_player(message.from_user)
    await message.answer("🏰 <b>Главное меню</b>", reply_markup=main_menu())


@dp.callback_query(F.data == "menu")
async def menu_callback(call: CallbackQuery):
    ensure_player(call.from_user)
    await call.answer()
    await safe_edit(call.message, "🏰 <b>Главное меню DOMINION</b>", main_menu())


@dp.callback_query(F.data == "profile")
async def profile_callback(call: CallbackQuery):
    ensure_player(call.from_user)
    await call.answer()
    await safe_edit(call.message, profile_text(call.from_user.id), back_menu())


@dp.callback_query(F.data == "balance")
async def balance_callback(call: CallbackQuery):
    ensure_player(call.from_user)
    await call.answer()
    await safe_edit(call.message, balance_text(call.from_user.id), back_menu())


# ============================================================
# GAME / WORLD
# ============================================================

@dp.callback_query(F.data == "game")
async def game_callback(call: CallbackQuery):
    await call.answer()
    await safe_edit(
        call.message,
        "🎮 <b>Играть</b>\n\nВыбери режим:",
        game_menu()
    )


@dp.callback_query(F.data == "world")
async def world_callback(call: CallbackQuery):
    await call.answer()
    rows = []
    text = "🗺️ <b>МИР DOMINION</b>\n\n"
    for key, loc in LOCATIONS.items():
        text += f"{loc['name']}\n{loc['description']}\n\n"
        rows.append([InlineKeyboardButton(
            text=loc["name"], callback_data=f"location:{key}"
        )])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="game")])
    await safe_edit(call.message, text, InlineKeyboardMarkup(inline_keyboard=rows))

# ============================================================
# PVE — ABILITIES & ACTIVE EFFECTS
# ============================================================

# Запущенные фоновые задачи эффектов.
# Один user_id = одна задача.
pve_effect_tasks = {}


def get_pve_effects(user_id):
    return db_execute("""
        SELECT *
        FROM pve_effects
        WHERE user_id=?
        ORDER BY created_at ASC
    """, (user_id,), fetchall=True)


def clear_pve_effects(user_id):
    db_execute(
        "DELETE FROM pve_effects WHERE user_id=?",
        (user_id,)
    )


def add_pve_effect(
    user_id,
    target,
    effect_type,
    damage,
    duration,
    tick_interval=1.0
):
    now = time.time()

    db_execute("""
        INSERT INTO pve_effects
        (
            user_id,
            target,
            effect_type,
            damage,
            expires_at,
            next_tick,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        target,
        effect_type,
        damage,
        now + duration,
        now + tick_interval,
        now
    ))


def pve_effects_text(user_id):
    effects = get_pve_effects(user_id)

    if not effects:
        return ""

    now = time.time()
    lines = ["🔥 <b>АКТИВНЫЕ ЭФФЕКТЫ</b>"]

    for effect in effects:
        remaining = max(
            0,
            int(effect["expires_at"] - now + 0.999)
        )

        if remaining <= 0:
            continue

        if effect["target"] == "enemy":
            target_text = "на враге"
        else:
            target_text = "на тебе"

        if effect["effect_type"] == "burn":
            icon = "🔥"
            name = "Горение"
        elif effect["effect_type"] == "bleed":
            icon = "🩸"
            name = "Кровотечение"
        else:
            icon = "✨"
            name = effect["effect_type"]

        lines.append(
            f"{icon} <b>{name}</b> — {remaining} сек. "
            f"({effect['damage']} урона/сек.) — {target_text}"
        )

    return "\n".join(lines)


def add_pve_log(user_id, message):
    db_execute("""
        INSERT INTO pve_battle_log
        (user_id, message, created_at)
        VALUES (?, ?, ?)
    """, (
        user_id,
        message,
        time.time()
    ))


def get_pve_log(user_id, limit=8):
    return db_execute("""
        SELECT message
        FROM pve_battle_log
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT ?
    """, (user_id, limit), fetchall=True)


def pve_battle_log_text(user_id):
    logs = get_pve_log(user_id)
    if not logs:
        return ""

    # Тики/наложение эффектов показываются только в ACTIVE EFFECTS.
    # Поэтому после окончания эффекта они исчезают из единого UI автоматически.
    transient = ("🔥 Горение", "🩸 Кровотечение", "✨", "🔥 На врага", "🩸 На врага")
    visible = [r["message"] for r in logs if not str(r["message"]).startswith(transient)]
    if not visible:
        return ""

    lines = ["📜 <b>БОЕВОЙ ЛОГ</b>"]
    for message in reversed(visible[-8:]):
        lines.append(f"• {message}")
    return "\n".join(lines)

# ============================================================
# PVE — ABILITY USES
# ============================================================

pve_ability_uses = {}


def get_pve_ability_uses(user_id):
    return pve_ability_uses.get(user_id, 0)


def reset_pve_ability_uses(user_id):
    pve_ability_uses[user_id] = 0

# ============================================================
# PVE
# ============================================================
pve_potion_cooldowns = {}

def pve_locations_keyboard():
    rows = []
    for key, loc in LOCATIONS.items():
        rows.append([InlineKeyboardButton(text=loc["name"], callback_data=f"pve_loc:{key}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="game")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def battle_keyboard(user_id):
    used = get_pve_ability_uses(user_id)
    eq = get_equipment(user_id)
    ability_name = eq["ability_name"] if eq and eq["ability_name"] else "Нет способности"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚔️ АТАКОВАТЬ", callback_data="battle:attack")],
        [InlineKeyboardButton(text="🧪 ЗЕЛЬЯ", callback_data="pve_potions"), InlineKeyboardButton(text=f"🌌 {ability_name} ({used}/2)", callback_data="battle:ability")],
        [InlineKeyboardButton(text="🏳️ СДАТЬСЯ", callback_data="battle:flee")]
    ])

def hp_bar(current, maximum, length=10):
    if maximum <= 0:
        return "░" * length

    current = max(0, min(current, maximum))
    filled = int((current / maximum) * length)

    return "█" * filled + "░" * (length - filled)


def _hp_bar(current, maximum, length=18):
    maximum = max(1, int(maximum))
    current = max(0, min(maximum, int(current)))
    filled = int((current / maximum) * length)
    return "█" * filled + "░" * (length - filled)


def battle_row(user_id):
    b = db_execute(
        "SELECT * FROM pve_battles WHERE user_id=?",
        (user_id,),
        fetchone=True
    )
    if not b:
        return "Бой не найден."

    stats = player_combat_stats(user_id)
    enemy_hp = max(0, int(b["enemy_hp"]))
    player_hp = max(0, int(b["player_hp"]))
    enemy_max = max(1, int(b["enemy_max_hp"]))
    player_max = max(1, int(b["player_max_hp"]))

    return (
        f"⚔️ <b>БОЙ</b>\n\n"
        f"👹 <b>{esc(b['enemy_name'])}</b>\n"
        f"❤️ {enemy_hp}/{enemy_max}  {_hp_bar(enemy_hp, enemy_max)}\n\n"
        f"👤 <b>Ты</b>\n"
        f"❤️ {player_hp}/{player_max}  {_hp_bar(player_hp, player_max)}\n\n"
        f"⚔️ Атака: <b>{stats['attack_min']}-{stats['attack_max']}</b>\n"
        f"🛡️ Броня: <b>-{int(stats['armor_reduction'] * 100)}%</b>\n"
        f"🔰 Щит: <b>{int(stats['shield_chance'] * 100)}%</b>"
        + (f"\n\n{db_execute("SELECT event_text FROM pve_battle_events WHERE user_id=? AND active=1", (user_id,), fetchone=True)["event_text"]}" if db_execute("SELECT event_text FROM pve_battle_events WHERE user_id=? AND active=1", (user_id,), fetchone=True) else "")
    )


@dp.callback_query(F.data == "pve")
async def pve_callback(call: CallbackQuery):
    await call.answer()
    existing = db_execute("SELECT 1 FROM pve_battles WHERE user_id=?", (call.from_user.id,), fetchone=True)
    if existing:
        await safe_edit(call.message, battle_row(call.from_user.id), battle_keyboard(call.from_user.id))
        return
    await safe_edit(
        call.message,
        "⚔️ <b>PvE</b>\n\nВыбери локацию:",
        pve_locations_keyboard()
    )


@dp.callback_query(F.data.startswith("pve_loc:"))
async def pve_location_callback(call: CallbackQuery):
    user_id = call.from_user.id
    ensure_player(call.from_user)
    location = call.data.split(":", 1)[1]
    if location not in LOCATIONS:
        await call.answer("Локация не найдена", show_alert=True)
        return

    old = db_execute("SELECT 1 FROM pve_battles WHERE user_id=?", (user_id,), fetchone=True)
    if old:
        await call.answer("У тебя уже идёт бой.", show_alert=True)
        await safe_edit(call.message, battle_row(user_id), battle_keyboard(user_id))
        return

    enemy = random.choice(LOCATIONS[location]["enemies"])
    key, name, hp, dmin, dmax, reward, particle = enemy
    stats = player_combat_stats(user_id)
    player_hp = 100 + (get_player(user_id)["level"] - 1) * 8

    db_execute("""
        INSERT INTO pve_battles
        (user_id,location,enemy_key,enemy_name,enemy_hp,enemy_max_hp,
         enemy_min_damage,enemy_max_damage,reward_dcr,particle_type,
         player_hp,player_max_hp,started_at,last_action)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        user_id, location, key, name, hp, hp, dmin, dmax, reward, particle,
        player_hp, player_hp, now_iso(), 0
    ))

    # Сбрасываем способности и эффекты для нового боя
    reset_pve_ability_uses(user_id)
    clear_pve_effects(user_id)

    # Очищаем старый боевой лог
    db_execute(
        "DELETE FROM pve_battle_log WHERE user_id=?",
        (user_id,)
    )

    # Добавляем первую запись нового боя
    add_pve_log(
        user_id,
        "⚔️ Бой начался."
    )

    await call.answer("Бой начался!")

    await safe_edit(
        call.message,
        battle_row(user_id),
        battle_keyboard(user_id)
    )



# ============================================================
# INVENTORY
# ============================================================

@dp.callback_query(F.data == "inventory")
async def inventory_callback(call: CallbackQuery):
    await call.answer()
    await safe_edit(call.message, inventory_text(call.from_user.id), inventory_menu())


@dp.callback_query(F.data == "equipment")
async def equipment_callback(call: CallbackQuery):
    await call.answer()
    await safe_edit(
        call.message,
        "⚔️ <b>Экипировка</b>\n\nВыбери предмет:",
        equipment_keyboard(call.from_user.id)
    )


@dp.callback_query(F.data.startswith("equip:"))
async def equip_callback(call: CallbackQuery):
    key = call.data.split(":", 1)[1]
    ok, text = equip_item(call.from_user.id, key)
    await call.answer("Готово" if ok else text, show_alert=not ok)
    await safe_edit(
        call.message,
        "⚔️ <b>Экипировка</b>\n\n" + text,
        equipment_keyboard(call.from_user.id)
    )


@dp.callback_query(F.data == "inv_potions")
async def inv_potions_callback(call: CallbackQuery):
    await call.answer()
    await safe_edit(call.message, inventory_text(call.from_user.id, "potion"), inventory_menu())

# ============================================================
# INVENTORY — ABILITIES
# ============================================================

@dp.callback_query(F.data == "inv_abilities")
async def inventory_abilities_callback(call: CallbackQuery):
    items = get_inventory(call.from_user.id)

    abilities = [
        x for x in items
        if x["item_type"] == "ability"
    ]

    rows = []

    if not abilities:
        text = (
            "🌌 <b>СПОСОБНОСТИ</b>\n\n"
            "У тебя пока нет способностей."
        )
    else:
        lines = [
            "🌌 <b>СПОСОБНОСТИ</b>\n"
        ]

        for x in abilities:
            lines.append(
                f"• {esc(x['name'])} "
                f"[{x['rarity']}] ×{x['quantity']}"
            )

            rows.append([
                InlineKeyboardButton(
                    text=f"🌌 Экипировать {x['name']}",
                    callback_data=f"equip:{x['item_key']}"
                )
            ])

        text = "\n".join(lines)

    rows.append([
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data="inventory"
        )
    ])

    await call.answer()

    await safe_edit(
        call.message,
        text,
        InlineKeyboardMarkup(inline_keyboard=rows)
    )
    
# ============================================================
# INVENTORY — PETS
# ============================================================

@dp.callback_query(F.data == "inv_pets")
async def inventory_pets_callback(call: CallbackQuery):
    items = get_inventory(call.from_user.id)

    pets = [
        x for x in items
        if x["item_type"] == "pet"
    ]

    rows = []

    if not pets:
        text = (
            "🐾 <b>ПИТОМЦЫ</b>\n\n"
            "У тебя пока нет питомцев."
        )
    else:
        lines = [
            "🐾 <b>ПИТОМЦЫ</b>\n"
        ]

        for x in pets:
            lines.append(
                f"• {esc(x['name'])} "
                f"[{x['rarity']}] ×{x['quantity']}"
            )

            rows.append([
                InlineKeyboardButton(
                    text=f"🐾 Экипировать {x['name']}",
                    callback_data=f"equip:{x['item_key']}"
                )
            ])

        text = "\n".join(lines)

    rows.append([
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data="inventory"
        )
    ])

    await call.answer()

    await safe_edit(
        call.message,
        text,
        InlineKeyboardMarkup(inline_keyboard=rows)
    )
    
# ============================================================
# SHOP
# ============================================================

@dp.callback_query(F.data == "shop")
async def shop_callback(call: CallbackQuery):
    await call.answer()

    text = (
        "🛒 <b>МАГАЗИН DOMINION</b>\n\n"
        "Выбери категорию:"
    )

    rows = [
        [
            InlineKeyboardButton(
                text="⚔️ Оружие",
                callback_data="shop_weapons"
            ),
            InlineKeyboardButton(
                text="🛡️ Броня",
                callback_data="shop_armor"
            )
        ],
        [
            InlineKeyboardButton(
                text="🧪 Зелья",
                callback_data="shop_potions"
            ),
            InlineKeyboardButton(
                text="🎁 Кейсы",
                callback_data="shop_cases"
            )
        ],
        [
            InlineKeyboardButton(
                text="🐾 Питомцы",
                callback_data="shop_pets"
            ),
            InlineKeyboardButton(
                text="🌌 Способности",
                callback_data="shop_abilities"
            )
        ],
        [
            InlineKeyboardButton(
                text="💎 Премиальные предметы",
                callback_data="shop_premium"
            )
        ],
        [
            InlineKeyboardButton(
                text="💎 Купить кристаллы",
                callback_data="shop_crystals"
            )
        ],
        [
            InlineKeyboardButton(
                text="🎫 Battle Pass",
                callback_data="shop_bp"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data="menu"
            )
        ]
    ]

    await safe_edit(
        call.message,
        text,
        InlineKeyboardMarkup(inline_keyboard=rows)
    )


# ============================================================
# WEAPONS
# ============================================================

@dp.callback_query(F.data == "shop_weapons")
async def shop_weapons_callback(call: CallbackQuery):
    rows = []
    lines = ["⚔️ <b>ОБЫЧНОЕ ОРУЖИЕ</b>", "", "Премиальные и божественные мечи находятся отдельно.", ""]
    owned = {x["item_key"]: int(x["quantity"]) for x in get_inventory(call.from_user.id)}
    for key, name, rarity, amin, amax, price in WEAPONS:
        qty = owned.get(key, 0)
        lines.append(f"• {esc(name)} [{rarity}] — ⚔️ {amin}–{amax} — 💰 {fmt(price)} DCR")
        if qty:
            lines.append(f"  🎒 Уже есть: {qty}")
        if qty == 0:
            rows.append([InlineKeyboardButton(text=f"Купить {name} — {fmt(price)} DCR", callback_data=f"buy:{key}")])
        else:
            rows.append([InlineKeyboardButton(text=f"✅ {name} уже куплен", callback_data="noop")])
    rows.append([InlineKeyboardButton(text="🌌 Премиальные предметы", callback_data="shop_premium")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="shop")])
    await call.answer()
    await safe_edit(call.message, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows))

@dp.callback_query(F.data == "noop")
async def noop_callback(call: CallbackQuery):
    await call.answer("Этот предмет уже есть у тебя.", show_alert=True)


# ============================================================
# ARMOR
# ============================================================

@dp.callback_query(F.data == "shop_armor")
async def shop_armor_callback(call: CallbackQuery):
    rows = []

    text = (
        "🛡️ <b>БРОНЯ И ЩИТЫ</b>\n\n"
    )

    if ARMORS:
        text += "<b>🛡️ Броня</b>\n\n"

        for key, name, rarity, red, price in ARMORS:
            text += (
                f"• {name} [{rarity}]\n"
                f"  🛡️ Снижение урона: {int(red * 100)}%\n"
                f"  💰 {fmt(price)} DCR\n\n"
            )

            rows.append([
                InlineKeyboardButton(
                    text=f"Купить {name} — {fmt(price)} DCR",
                    callback_data=f"buy:{key}"
                )
            ])

    if SHIELDS:
        text += "<b>🛡️ Щиты</b>\n\n"

        for key, name, rarity, sred, chance, price in SHIELDS:
            text += (
                f"• {name} [{rarity}]\n"
                f"  🛡️ Снижение: {int(sred * 100)}%\n"
                f"  🎲 Шанс активации: {int(chance * 100)}%\n"
                f"  💰 {fmt(price)} DCR\n\n"
            )

            rows.append([
                InlineKeyboardButton(
                    text=f"Купить {name} — {fmt(price)} DCR",
                    callback_data=f"buy:{key}"
                )
            ])

    rows.append([
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data="shop"
        )
    ])

    await call.answer()

    await safe_edit(
        call.message,
        text,
        InlineKeyboardMarkup(inline_keyboard=rows)
    )


# ============================================================
# POTIONS
# ============================================================

@dp.callback_query(F.data == "shop_potions")
async def shop_potions_callback(call: CallbackQuery):
    rows = []

    text = (
        "🧪 <b>ЗЕЛЬЯ</b>\n\n"
    )

    for key, name, rarity, heal, price, particle in POTIONS:
        text += (
            f"• {name} [{rarity}]\n"
            f"  ❤️ Восстановление: {int(heal * 100)}%\n"
            f"  💰 {fmt(price)} DCR\n\n"
        )

        rows.append([
            InlineKeyboardButton(
                text=f"Купить {name} — {fmt(price)} DCR",
                callback_data=f"buy:{key}"
            )
        ])

    rows.append([
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data="shop"
        )
    ])

    await call.answer()

    await safe_edit(
        call.message,
        text,
        InlineKeyboardMarkup(inline_keyboard=rows)
    )

# ============================================================
# Обычные питомцы
# ============================================================

PETS = [
    ("wolf", "🐺 Волк", "Обычный",
     "Верный хищник, который помогает своему хозяину в бою.", 500),

    ("fox", "🦊 Лисица", "Обычный",
     "Хитрый и ловкий питомец, способный находить слабые места врага.", 600),

    ("bear", "🐻 Медведь", "Обычный",
     "Могучий зверь, который помогает хозяину выдерживать удары.", 750),

    ("hawk", "🦅 Ястреб", "Обычный",
     "Быстрый хищник с острым зрением.", 900),

    ("scorpion", "🦂 Скорпион", "Обычный",
     "Опасный питомец с ядовитым жалом.", 1000),

    ("snake", "🐍 Змея", "Обычный",
     "Коварный питомец, использующий яд против врагов.", 850),

    ("boar", "🐗 Кабан", "Обычный",
     "Выносливый зверь, способный выдержать тяжёлый бой.", 700),

    ("owl", "🦉 Сова", "Обычный",
     "Наблюдательный питомец с прекрасным зрением.", 650),

    ("panther", "🐆 Пантера", "Обычный",
     "Стремительный хищник, атакующий врага внезапно.", 1200),
]

# ============================================================
# PETS — МАГАЗИН
# ============================================================

@dp.callback_query(F.data == "shop_pets")
async def shop_pets_callback(call: CallbackQuery):

    level = get_player(call.from_user.id)["level"]

    # Питомцы открываются с 25 уровня
    if level < 25:

        text = (
            "🐾 <b>ПИТОМЦЫ</b>\n\n"
            "🔒 Питомцы открываются с <b>25 уровня</b>.\n\n"
            f"📊 Твой уровень: <b>{level}</b>"
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⬅️ Назад",
                        callback_data="shop"
                    )
                ]
            ]
        )

        await call.answer(
            "🐾 Питомцы открываются с 25 уровня.",
            show_alert=True
        )

        await safe_edit(
            call.message,
            text,
            keyboard
        )

        return

    # ========================================================
    # СПИСОК ПИТОМЦЕВ
    # ========================================================

    text = "🐾 <b>ПИТОМЦЫ</b>\n\n"

    rows = []

    for key, name, rarity, description, price in PETS:

        text += (
            f"{name} [{rarity}] — {description}   "
            f"💰 <b>{fmt(price)} DCR</b>\n\n"
        )

        rows.append([
            InlineKeyboardButton(
                text=f"Купить {name} — {fmt(price)} DCR",
                callback_data=f"buy:{key}"
            )
        ])

    # ========================================================
    # НАЗАД
    # ========================================================

    rows.append([
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data="shop"
        )
    ])

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=rows
    )

    await call.answer()

    await safe_edit(
        call.message,
        text,
        keyboard
    )
    
# ============================================================
# CASES IN SHOP
# ============================================================

@dp.callback_query(F.data == "shop_cases")
async def shop_cases_callback(call: CallbackQuery):
    await call.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚔️ Оружейный кейс — 100 💎", callback_data="case:weapon")],
        [InlineKeyboardButton(text="🧩 Кейс частиц — скоро", callback_data="noop")],
        [InlineKeyboardButton(text="🧪 Кейс зелий — скоро", callback_data="noop")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="shop")],
    ])
    await safe_edit(call.message,
        "🎁 <b>КЕЙСЫ</b>\n\nОткрывай кейсы за 💎 и получай случайную награду.", kb)

# ============================================================
# ABILITIES
# ============================================================

@dp.callback_query(F.data == "shop_abilities")
async def shop_abilities_callback(call: CallbackQuery):
    p=get_player(call.from_user.id)
    level=int(p["level"]) if p else 0
    if level < 50:
        kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад",callback_data="shop")]])
        await call.answer("🌌 Способности открываются с 50 уровня.",show_alert=True)
        await safe_edit(call.message,f"🌌 <b>СПОСОБНОСТИ</b>\n\n🔒 Открываются с <b>50 уровня</b>.\n📊 Твой уровень: <b>{level}</b>",kb)
        return
    text="🌌 <b>СПОСОБНОСТИ</b>\n\nОбычные способности покупаются за DCR.\n\n"
    rows=[]
    for key,name,rarity,price in ORDINARY_ABILITIES:
        owned=db_execute("SELECT inv.quantity FROM inventory inv JOIN items i ON i.item_id=inv.item_id WHERE inv.user_id=? AND i.item_key=?",(call.from_user.id,key),fetchone=True)
        if owned and int(owned["quantity"])>0:
            text+=f"{name} <i>[{rarity}]</i> — <b>✅ Куплено</b>\n"
            rows.append([InlineKeyboardButton(text=f"✅ {name} — уже куплено",callback_data=f"ability_owned:{key}")])
        else:
            text+=f"{name} <i>[{rarity}]</i> — <b>{fmt(price)} DCR</b>\n"
            rows.append([InlineKeyboardButton(text=f"Купить {name} — {fmt(price)} DCR",callback_data=f"buy_ability:{key}")])
    text+="\n⚙️ После покупки способность появится в инвентаре и её можно будет экипировать."
    rows.append([InlineKeyboardButton(text="⬅️ Назад",callback_data="shop")])
    await call.answer(); await safe_edit(call.message,text,InlineKeyboardMarkup(inline_keyboard=rows))

@dp.callback_query(F.data.startswith("ability_owned:"))
async def ability_owned_callback(call: CallbackQuery):
    await call.answer("Эта способность уже есть у тебя.",show_alert=True)

@dp.callback_query(F.data.startswith("buy_ability:"))
async def buy_ability_callback(call: CallbackQuery):
    key=call.data.split(":",1)[1]
    data=next((x for x in ORDINARY_ABILITIES if x[0]==key),None)
    if not data: await call.answer("Способность не найдена.",show_alert=True); return
    _,name,_,price=data
    p=get_player(call.from_user.id)
    if not p: await call.answer("Игрок не найден.",show_alert=True); return
    if int(p["level"])<50: await call.answer("Нужен 50 уровень.",show_alert=True); return
    item=db_execute("SELECT item_id FROM items WHERE item_key=? AND item_type='ability'",(key,),fetchone=True)
    if not item: await call.answer("Способность отсутствует в базе.",show_alert=True); return
    owned=db_execute("SELECT quantity FROM inventory WHERE user_id=? AND item_id=?",(p["user_id"],item["item_id"]),fetchone=True)
    if owned and int(owned["quantity"])>0: await call.answer("⚠️ У тебя уже есть эта способность.",show_alert=True); return
    if int(p["dcr"] or 0)<price: await call.answer(f"❌ Недостаточно DCR. Нужно {fmt(price)} DCR.",show_alert=True); return
    add_dcr(p["user_id"], -price, f"Покупка способности {name}")
    if not add_item(p["user_id"],key,1):
        add_dcr(p["user_id"],price,f"Возврат за несостоявшуюся покупку способности {name}")
        await call.answer("❌ Не удалось добавить способность в инвентарь.",show_alert=True); return
    p=get_player(p["user_id"])
    await call.answer("✅ Способность куплена!")
    await safe_edit(call.message,f"🛒 <b>Покупка совершена</b>\n\n{name} добавлена в инвентарь.\n💰 Потрачено: <b>{fmt(price)} DCR</b>\n💰 Осталось: <b>{fmt(p['dcr'])} DCR</b>",shop_menu())

# ============================================================
# PREMIUM
# ============================================================

@dp.callback_query(F.data == "shop_premium")
async def shop_premium_callback(call: CallbackQuery):
    text = (
        "💎 <b>ПРЕМИАЛЬНЫЕ ПРЕДМЕТЫ</b>\n\n"
        "Редкие предметы DOMINION.\n"
        "Покупаются за 💎 кристаллы.\n\n"
        "⚔️ Божественные мечи — <b>2 500 💎</b>\n"
        "🌌 Божественные способности — <b>1 500 💎</b>\n"
        "🐾 Божественные питомцы — <b>1 000 💎</b>\n"
        "👑 Эксклюзивы — особая категория"
    )

    rows = [
        [
            InlineKeyboardButton(
                text="⚔️ Божественные мечи",
                callback_data="shop_divine_weapons"
            )
        ],
        [
            InlineKeyboardButton(
                text="🌌 Божественные способности",
                callback_data="shop_divine_abilities"
            )
        ],
        [
            InlineKeyboardButton(
                text="🐾 Божественные питомцы",
                callback_data="shop_divine_pets"
            )
        ],
        [
            InlineKeyboardButton(
                text="👑 Эксклюзивы",
                callback_data="shop_exclusives"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data="shop"
            )
        ]
    ]

    await call.answer()

    await safe_edit(
        call.message,
        text,
        InlineKeyboardMarkup(inline_keyboard=rows)
    )


# ============================================================
# DIVINE WEAPONS
# ============================================================

@dp.callback_query(F.data == "shop_divine_weapons")
async def shop_divine_weapons_callback(call: CallbackQuery):
    text = (
        "⚔️ <b>БОЖЕСТВЕННЫЕ МЕЧИ</b>\n\n"
        "💎 Цена каждого: <b>2 500 💎</b>\n\n"

        "⚔️ <b>Небесный гнев</b>\n"
        "Урон: 100–300\n"
        "🔥 Горение + 🩸 кровотечение\n\n"

        "🌑 <b>Пожиратель душ</b>\n"
        "Урон: 80–260\n"
        "🩸 Похищение здоровья\n\n"

        "⚡ <b>Громовержец</b>\n"
        "Урон: 120–280\n"
        "⚡ Молния после удара\n\n"

        "⚔️ Все мечи работают в PvE и PvP."
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚔️ Небесный гнев — 2 500 💎",
                    callback_data="buy_divine_weapon:heaven_wrath"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🌑 Пожиратель душ — 2 500 💎",
                    callback_data="buy_divine_weapon:soul_eater"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⚡ Громовержец — 2 500 💎",
                    callback_data="buy_divine_weapon:thunderer"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="shop_premium"
                )
            ]
        ]
    )

    await call.answer()

    await safe_edit(
        call.message,
        text,
        keyboard
    )


# ============================================================
# DIVINE ABILITIES
# ============================================================

@dp.callback_query(F.data == "shop_divine_abilities")
async def shop_divine_abilities_callback(call: CallbackQuery):
    text = (
        "🌌 <b>БОЖЕСТВЕННЫЕ СПОСОБНОСТИ</b>\n\n"
        "💎 Цена каждой: <b>1 500 💎</b>\n\n"

        "☀️ <b>Гнев небес</b>\n"
        "Следующая атака становится значительно сильнее "
        "и частично игнорирует броню.\n\n"

        "🕊️ <b>Божественное возрождение</b>\n"
        "Восстанавливает 50% HP.\n\n"

        "🔓 <b>Уровень не требуется.</b>\n"
        "⚔️ Работают в PvE и PvP."
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="☀️ Купить — 1 500 💎",
                    callback_data="buy_divine_ability:wrath_of_heaven"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🕊️ Купить — 1 500 💎",
                    callback_data="buy_divine_ability:divine_rebirth"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="shop_premium"
                )
            ]
        ]
    )

    await call.answer()

    await safe_edit(
        call.message,
        text,
        keyboard
    )

# ============================================================
# BUY DIVINE ABILITY
# ============================================================

@dp.callback_query(F.data.startswith("buy_divine_ability:"))
async def buy_divine_ability_callback(call: CallbackQuery):
    ability_key = call.data.split(":", 1)[1]

    divine_abilities = {
        "wrath_of_heaven": "☀️ Гнев небес",
        "divine_rebirth": "🕊️ Божественное возрождение",
    }

    ability_name = divine_abilities.get(ability_key)

    if not ability_name:
        await call.answer(
            "Способность не найдена.",
            show_alert=True
        )
        return

    user_id = call.from_user.id
    price = 1500

    p = get_player(user_id)

    if not p:
        await call.answer(
            "Игрок не найден.",
            show_alert=True
        )
        return

    if p["crystals"] < price:
        await call.answer(
            "💎 Недостаточно кристаллов.",
            show_alert=True
        )
        return

    # Проверяем, нет ли уже этой способности
    item = db_execute(
        "SELECT item_id FROM items WHERE item_key = ?",
        (ability_key,),
        fetchone=True
    )

    if not item:
        await call.answer(
            "Предмет не найден в базе.",
            show_alert=True
        )
        return

    owned = db_execute(
        """
        SELECT quantity
        FROM inventory
        WHERE user_id = ? AND item_id = ?
        """,
        (user_id, item["item_id"]),
        fetchone=True
    )

    if owned:
        await call.answer(
            "⚠️ У тебя уже есть эта способность.",
            show_alert=True
        )
        return

    # Списываем кристаллы
    db_execute(
        """
        UPDATE players
        SET crystals = crystals - ?
        WHERE user_id = ?
        """,
        (price, user_id)
    )

    # Выдаём способность
    add_item(user_id, ability_key, 1)

    p = get_player(user_id)

    await call.answer("✅ Способность куплена!")

    await safe_edit(
        call.message,
        (
            "🌌 <b>Покупка совершена!</b>\n\n"
            f"✨ Ты получил: <b>{esc(ability_name)}</b>\n"
            "💎 Потрачено: <b>1 500 💎</b>\n\n"
            f"💎 Осталось: <b>{p['crystals']:,}</b>"
        ),
        shop_menu()
    )

# ============================================================
# DIVINE PETS
# ============================================================

@dp.callback_query(F.data == "shop_divine_pets")
async def shop_divine_pets_callback(call: CallbackQuery):
    text = (
        "🐾 <b>БОЖЕСТВЕННЫЕ ПИТОМЦЫ</b>\n\n"
        "💎 Цена каждого: <b>1 000 💎</b>\n\n"

        "🐉 <b>Небесный дракон</b>\n"
        "Пассивно: +8% к обычному урону.\n\n"

        "🦅 <b>Божественный Феникс</b>\n"
        "Пассивно: при HP ниже 20% "
        "получаем на 15% меньше урона.\n\n"

        "🔓 <b>Уровень не требуется.</b>\n"
        "⚔️ Работают в PvE и PvP."
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🐉 Купить — 1 000 💎",
                    callback_data="buy_divine_pet:sky_dragon"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🦅 Купить — 1 000 💎",
                    callback_data="buy_divine_pet:divine_phoenix"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="shop_premium"
                )
            ]
        ]
    )

    await call.answer()

    await safe_edit(
        call.message,
        text,
        keyboard
    )

# ============================================================
# BUY DIVINE PET
# ============================================================

@dp.callback_query(F.data.startswith("buy_divine_pet:"))
async def buy_divine_pet_callback(call: CallbackQuery):
    pet_key = call.data.split(":", 1)[1]

    divine_pets = {
        "sky_dragon": "🐉 Небесный дракон",
        "divine_phoenix": "🦅 Божественный Феникс",
    }

    pet_name = divine_pets.get(pet_key)

    if not pet_name:
        await call.answer(
            "Питомец не найден.",
            show_alert=True
        )
        return

    user_id = call.from_user.id
    price = 1000

    p = get_player(user_id)

    if not p:
        await call.answer(
            "Игрок не найден.",
            show_alert=True
        )
        return

    if p["crystals"] < price:
        await call.answer(
            "💎 Недостаточно кристаллов.",
            show_alert=True
        )
        return

    # Проверяем наличие предмета в базе
    item = db_execute(
        "SELECT item_id FROM items WHERE item_key = ?",
        (pet_key,),
        fetchone=True
    )

    if not item:
        await call.answer(
            "Предмет не найден в базе.",
            show_alert=True
        )
        return

    # Проверяем, куплен ли уже питомец
    owned = db_execute(
        """
        SELECT quantity
        FROM inventory
        WHERE user_id = ? AND item_id = ?
        """,
        (user_id, item["item_id"]),
        fetchone=True
    )

    if owned:
        await call.answer(
            "⚠️ У тебя уже есть этот питомец.",
            show_alert=True
        )
        return

    # Списываем кристаллы
    db_execute(
        """
        UPDATE players
        SET crystals = crystals - ?
        WHERE user_id = ?
        """,
        (price, user_id)
    )

    # Выдаём питомца
    add_item(user_id, pet_key, 1)

    p = get_player(user_id)

    await call.answer("✅ Питомец куплен!")

    await safe_edit(
        call.message,
        (
            "🐾 <b>Покупка совершена!</b>\n\n"
            f"Ты получил: <b>{esc(pet_name)}</b>\n"
            "💎 Потрачено: <b>1 000 💎</b>\n\n"
            f"💎 Осталось: <b>{p['crystals']:,}</b>"
        ),
        shop_menu()
    )

# ============================================================
# EXCLUSIVES
# ============================================================

@dp.callback_query(F.data == "shop_exclusives")
async def shop_exclusives_callback(call: CallbackQuery):
    p = get_player(call.from_user.id)
    text = (
        "👑 <b>ЭКСКЛЮЗИВЫ</b>\n\n"
        "Статусы оформляются на 30 дней.\n\n"
        "👑 Корона — 150 ⭐/мес.\n"
        "⭐ VIP — 300 ⭐/мес.\n"
        "🌌 Божественный статус — 600 ⭐/мес.\n\n"
        f"Текущий статус: {premium_status_text(p)}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👑 Корона — 150 ⭐", callback_data="premium_buy:crown")],
        [InlineKeyboardButton(text="⭐ VIP — 300 ⭐", callback_data="premium_buy:vip")],
        [InlineKeyboardButton(text="🌌 Божественный — 600 ⭐", callback_data="premium_buy:divine")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="shop_premium")],
    ])
    await call.answer()
    await safe_edit(call.message, text, kb)

# ============================================================
# ORDINARY ITEM PURCHASE
# ============================================================

@dp.callback_query(F.data.startswith("buy:"))
async def buy_item_callback(call: CallbackQuery):
    """Покупка обычных предметов из магазина.

    Раньше общий callback принимал только оружие, поэтому кнопки брони,
    зелий и питомцев доходили сюда, но всегда получали «Предмет не найден».
    Теперь здесь единая обработка всех обычных товарных категорий.
    """
    key = call.data.split(":", 1)[1]
    user_id = call.from_user.id

    item = db_execute(
        "SELECT * FROM items WHERE item_key=?",
        (key,),
        fetchone=True
    )
    p = get_player(user_id)

    if not p:
        await call.answer("❌ Игрок не найден.", show_alert=True)
        return

    if not item:
        await call.answer("❌ Предмет не найден в базе.", show_alert=True)
        return

    # Эти категории продаются за DCR в обычном магазине.
    allowed_types = {"weapon", "armor", "shield", "potion", "pet"}
    item_type = str(item["item_type"])
    if item_type not in allowed_types:
        await call.answer("❌ Этот предмет нельзя купить здесь.", show_alert=True)
        return

    price = int(item["price_dcr"] or 0)
    if price < 0:
        await call.answer("❌ Некорректная цена предмета.", show_alert=True)
        return

    owned = db_execute(
        "SELECT quantity FROM inventory WHERE user_id=? AND item_id=?",
        (user_id, item["item_id"]),
        fetchone=True
    )
    owned_qty = int(owned["quantity"]) if owned else 0

    # Зелья можно покупать повторно и складывать в инвентаре.
    # Оружие/броня/щиты/питомцы — по одному экземпляру.
    if item_type != "potion" and owned_qty > 0:
        category_names = {
            "weapon": "оружие",
            "armor": "броню",
            "shield": "щит",
            "pet": "питомца",
        }
        await call.answer(
            f"⚠️ У тебя уже есть {category_names.get(item_type, 'этот предмет')}.",
            show_alert=True
        )
        return

    balance = int(p["dcr"] or 0)
    if balance < price:
        await call.answer(
            f"❌ Недостаточно DKR.\nНужно: {fmt(price)} DKR\nУ тебя: {fmt(balance)} DKR",
            show_alert=True
        )
        return

    # Сначала проверяем, что предмет реально добавляется в инвентарь.
    # Если добавление не удалось, деньги не списываем.
    if not add_item(user_id, key, 1):
        await call.answer(
            "❌ Не удалось добавить предмет в инвентарь.",
            show_alert=True
        )
        return

    add_dcr(user_id, -price, f"Покупка {item['name']}")

    p = get_player(user_id)
    type_icons = {
        "weapon": "⚔️",
        "armor": "🛡️",
        "shield": "🛡️",
        "potion": "🧪",
        "pet": "🐾",
    }
    icon = type_icons.get(item_type, "📦")
    quantity_text = "\n🎒 Количество: <b>{}</b>".format(
        int(owned_qty) + 1
    ) if item_type == "potion" else ""

    await call.answer("✅ Покупка совершена!")
    await safe_edit(
        call.message,
        (
            "🛒 <b>Покупка совершена!</b>\n\n"
            f"{icon} Ты получил: <b>{esc(item['name'])}</b>"
            f"{quantity_text}\n\n"
            f"💰 Потрачено: <b>{fmt(price)} DKR</b>\n"
            f"💰 Осталось: <b>{fmt(int(p['dcr']))} DKR</b>"
        ),
        shop_menu()
    )


# ============================================================
# DIVINE WEAPON PURCHASE
# ============================================================

@dp.callback_query(F.data.startswith("buy_divine_weapon:"))
async def buy_divine_weapon_callback(call: CallbackQuery):
    weapon_key = call.data.split(":", 1)[1]

    divine_weapons = {
        "heaven_wrath": {
            "name": "⚔️ Небесный гнев",
            "damage_min": 100,
            "damage_max": 300,
        },
        "soul_eater": {
            "name": "🌑 Пожиратель душ",
            "damage_min": 80,
            "damage_max": 260,
        },
        "thunderer": {
            "name": "⚡ Громовержец",
            "damage_min": 120,
            "damage_max": 280,
        },
    }

    weapon = divine_weapons.get(weapon_key)

    if not weapon:
        await call.answer(
            "Оружие не найдено.",
            show_alert=True
        )
        return

    user_id = call.from_user.id
    price = 2500

    p = get_player(user_id)

    if not p:
        await call.answer(
            "Профиль не найден.",
            show_alert=True
        )
        return

    if p["crystals"] < price:
        await call.answer(
            f"❌ Недостаточно кристаллов.\n"
            f"Нужно: {fmt(price)} 💎\n"
            f"У тебя: {fmt(p['crystals'])} 💎",
            show_alert=True
        )
        return

    item_row = db_execute("SELECT item_id FROM items WHERE item_key=?", (weapon_key,), fetchone=True)
    owned = db_execute("SELECT quantity FROM inventory WHERE user_id=? AND item_id=?", (user_id, item_row["item_id"]), fetchone=True) if item_row else None
    if owned and int(owned["quantity"]) > 0:
        await call.answer("⚠️ У тебя уже есть этот меч.", show_alert=True)
        return

    # Списываем кристаллы
    db_execute(
        "UPDATE players SET crystals = crystals - ? WHERE user_id = ?",
        (price, user_id)
    )

    # Выдаём божественное оружие
    add_item(
        user_id,
        weapon_key,
        1
    )

    p = get_player(user_id)

    await call.answer(
        "✅ Божественное оружие куплено!"
    )

    await safe_edit(
        call.message,
        (
            f"🌌 <b>Покупка совершена!</b>\n\n"
            f"⚔️ Ты получил: <b>{esc(weapon['name'])}</b>\n"
            f"💎 Стоимость: {fmt(price)} 💎\n\n"
            f"💎 Кристаллов осталось: <b>{fmt(p['crystals'])}</b>"
        ),
        shop_menu()
    )

# ============================================================
# CRYSTALS
# ============================================================

@dp.callback_query(F.data == "shop_crystals")
async def shop_crystals_callback(call: CallbackQuery):
    rows = []

    text = (
        "💎 <b>КРИСТАЛЛЫ</b>\n\n"
        "Здесь можно приобрести 💎 кристаллы.\n"
        "Оплата самих кристаллов — Telegram Stars."
    )

    for crystals, stars in CRYSTAL_PACKS.items():
        rows.append([
            InlineKeyboardButton(
                text=f"💎 {fmt(crystals)} — ⭐ {fmt(stars)}",
                callback_data=f"crystals:{crystals}"
            )
        ])

    rows.append([
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data="shop"
        )
    ])

    await call.answer()

    await safe_edit(
        call.message,
        text,
        InlineKeyboardMarkup(inline_keyboard=rows)
    )


# ============================================================
# CRYSTAL PURCHASE
# ============================================================

@dp.callback_query(F.data.startswith("crystals:"))
async def crystal_purchase_callback(
    call: CallbackQuery,
    bot: Bot
):
    crystals = int(
        call.data.split(":", 1)[1]
    )

    stars = CRYSTAL_PACKS.get(crystals)

    if not stars:
        await call.answer(
            "Пакет не найден.",
            show_alert=True
        )
        return

    payload = f"crystals:{crystals}"

    await bot.send_invoice(
        chat_id=call.from_user.id,
        title=f"{GAME_NAME}: {crystals} Crystals",
        description=f"Покупка {crystals} 💎 кристаллов",
        payload=payload,
        currency="XTR",
        prices=[
            LabeledPrice(
                label=f"{crystals} Crystals",
                amount=stars
            )
        ],
    )

    await call.answer()


# ============================================================
# BATTLE PASS
# ============================================================

@dp.callback_query(F.data == "shop_bp")
async def shop_bp_callback(
    call: CallbackQuery,
    bot: Bot
):
    await call.answer()

    await bot.send_invoice(
        chat_id=call.from_user.id,
        title=f"{GAME_NAME}: Battle Pass",
        description="Платный Battle Pass DOMINION",
        payload="battle_pass",
        currency="XTR",
        prices=[
            LabeledPrice(
                label="Battle Pass",
                amount=BATTLE_PASS_STARS
            )
        ],
    )


# ============================================================
# TELEGRAM PAYMENT
# ============================================================

@dp.pre_checkout_query()
async def pre_checkout(
    query: PreCheckoutQuery
):
    await query.answer(
        ok=True
    )


@dp.message(F.successful_payment)
async def successful_payment(
    message: Message
):
    payment = message.successful_payment
    user_id = message.from_user.id
    payload = payment.invoice_payload

    if payload.startswith("crystals:"):
        crystals = int(
            payload.split(":", 1)[1]
        )

        add_crystals(
            user_id,
            crystals,
            "Telegram Stars: покупка кристаллов"
        )

        product = f"crystals:{crystals}"

        stars = CRYSTAL_PACKS.get(
            crystals,
            payment.total_amount
        )

        db_execute(
            """
            INSERT INTO purchases(
                user_id,
                telegram_charge_id,
                product,
                amount,
                stars,
                created_at
            )
            VALUES(?,?,?,?,?,?)
            """,
            (
                user_id,
                payment.telegram_payment_charge_id,
                product,
                crystals,
                stars,
                now_iso()
            )
        )

        await message.answer(
            f"✅ <b>Оплата прошла!</b>\n\n"
            f"💎 Начислено: "
            f"<b>{fmt(crystals)} 💎</b>"
        )

    elif payload.startswith("premium:"):
        kind=payload.split(":",1)[1]
        products={"crown":("Корона","crown_until"),"vip":("VIP","vip_until"),"divine":("Божественный статус","divine_until")}
        if kind not in products:
            await message.answer("❌ Неизвестный статус."); return
        name,column=products[kind]
        until=(utc_now_dt()+timedelta(days=30)).isoformat()
        db_execute(f"UPDATE players SET {column}=? WHERE user_id=?",(until,user_id))
        await message.answer(f"👑 <b>{esc(name)}</b> активирован на 30 дней.")

    elif payload == "battle_pass":
        db_execute(
            """
            UPDATE players
            SET bp_paid=1
            WHERE user_id=?
            """,
            (user_id,)
        )

        db_execute(
            """
            INSERT INTO purchases(
                user_id,
                telegram_charge_id,
                product,
                amount,
                stars,
                created_at
            )
            VALUES(?,?,?,?,?,?)
            """,
            (
                user_id,
                payment.telegram_payment_charge_id,
                "battle_pass",
                1,
                BATTLE_PASS_STARS,
                now_iso()
            )
        )

        await message.answer(
            "🎫 <b>Battle Pass активирован!</b>"
        )


# ============================================================
# PvP
# ============================================================

class PvPChallengeState(StatesGroup):
    waiting_username = State()
    

@dp.callback_query(F.data == "pvp_challenge")
async def pvp_challenge_callback(
    call: CallbackQuery
):
    await call.answer()

    await safe_edit(
        call.message,
        "🤝 <b>ВЫЗВАТЬ ИГРОКА</b>\n\n"
        "Выбери способ поиска:",
        InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔎 Поиск по username",
                        callback_data="pvp_challenge_username"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="👥 Список игроков",
                        callback_data="pvp_challenge_list"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ Назад",
                        callback_data="pvp"
                    )
                ]
            ]
        )
    )

@dp.callback_query(F.data == "pvp_challenge_list")
async def pvp_challenge_list_callback(call: CallbackQuery):
    await call.answer()

    current_user_id = call.from_user.id

    players = db_execute("""
        SELECT user_id, username, first_name
        FROM players
        WHERE user_id != ?
        ORDER BY first_name COLLATE NOCASE, username COLLATE NOCASE
        LIMIT 20
    """, (current_user_id,), fetchall=True)

    if not players:
        await safe_edit(
            call.message,
            "👥 <b>СПИСОК ИГРОКОВ</b>\n\n"
            "Пока других зарегистрированных игроков нет.",
            InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="⬅️ Назад",
                            callback_data="pvp_challenge"
                        )
                    ]
                ]
            )
        )
        return

    buttons = []

    for player in players:
        name = (
            player["first_name"]
            or player["username"]
            or f"Игрок {player['user_id']}"
        )

        username = player["username"]

        if username:
            button_text = f"👤 {name}  @{username}"
        else:
            button_text = f"👤 {name}"

        buttons.append([
            InlineKeyboardButton(
                text=button_text[:64],
                callback_data=f"pvp_challenge_player:{player['user_id']}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="🔎 Поиск по username",
            callback_data="pvp_challenge_username"
        )
    ])

    buttons.append([
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data="pvp_challenge"
        )
    ])

    await safe_edit(
        call.message,
        "👥 <b>СПИСОК ИГРОКОВ</b>\n\n"
        "Выбери игрока, которого хочешь вызвать:",
        InlineKeyboardMarkup(
            inline_keyboard=buttons
        )
    )



@dp.callback_query(F.data == "pvp_challenge_username")
async def pvp_challenge_username_callback(
    call: CallbackQuery,
    state: FSMContext
):
    await call.answer()

    await state.set_state(
        PvPChallengeState.waiting_username
    )

    await safe_edit(
        call.message,
        "🔎 <b>ПОИСК ИГРОКА</b>\n\n"
        "Введи username игрока.\n\n"
        "Например: <code>@Player123</code>",
        InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="❌ Отмена",
                        callback_data="pvp_challenge"
                    )
                ]
            ]
        )
    )


@dp.message(PvPChallengeState.waiting_username)
async def pvp_challenge_username_search(
    message: Message,
    state: FSMContext
):
    username = (message.text or "").strip()

    if not username:
        await message.answer(
            "❌ Введи username игрока."
        )
        return

    username = username.lstrip("@").strip()

    if not username:
        await message.answer(
            "❌ Введи корректный username."
        )
        return

    player = db_execute("""
        SELECT *
        FROM players
        WHERE LOWER(username)=LOWER(?)
        LIMIT 1
    """, (username,), fetchone=True)

    if not player:
        await message.answer(
            "❌ Игрок с таким username не найден.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔎 Попробовать снова",
                            callback_data="pvp_challenge_username"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="⬅️ Назад",
                            callback_data="pvp_challenge"
                        )
                    ]
                ]
            )
        )
        return

    if int(player["user_id"]) == int(message.from_user.id):
        await message.answer(
            "❌ Нельзя вызвать самого себя.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔎 Другой игрок",
                            callback_data="pvp_challenge_username"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="⬅️ Назад",
                            callback_data="pvp_challenge"
                        )
                    ]
                ]
            )
        )
        return

    await state.clear()

    target_id = int(player["user_id"])

    target_name = (
        player["first_name"]
        or player["username"]
        or f"Игрок {target_id}"
    )

    await message.answer(
        "👤 <b>ИГРОК НАЙДЕН</b>\n\n"
        f"👤 {esc(target_name)}\n"
        f"🔗 @{esc(player['username'])}\n\n"
        "Хочешь вызвать этого игрока на дуэль?",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⚔️ Вызвать на дуэль",
                        callback_data=f"pvp_challenge_send:{target_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🔎 Другой игрок",
                        callback_data="pvp_challenge_username"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ Назад",
                        callback_data="pvp_challenge"
                    )
                ]
            ]
        )
    )
    
    # ============================================================
# PvP — MENU ACTIONS
# ============================================================





@dp.callback_query(F.data == "pvp_leaderboard_ranked")
async def pvp_leaderboard_ranked_callback(call: CallbackQuery):
    await call.answer()

    rows = db_execute("""
        SELECT
            p.user_id,
            p.username,
            p.first_name,
            s.mmr,
            s.ranked_games,
            s.ranked_wins,
            s.ranked_losses,
            s.calibration_games
        FROM pvp_stats s
        LEFT JOIN players p
            ON p.user_id = s.user_id
        WHERE s.ranked_games > 0
        ORDER BY s.mmr DESC, s.ranked_wins DESC
        LIMIT 100
    """, fetchall=True)

    text = "🏆 <b>РЕЙТИНГОВЫЙ PVP — ТОП 100</b>\n\n"

    if not rows:
        text += "Пока нет игроков в рейтинге."
    else:
        medals = ["🥇", "🥈", "🥉"]

        for i, row in enumerate(rows, start=1):
            if i <= 3:
                place = medals[i - 1]
            else:
                place = f"{i}."

            name = (
                row["first_name"]
                or row["username"]
                or f"Игрок {row['user_id']}"
            )

            mmr = int(row["mmr"])
            calibration_games = int(row["calibration_games"])

            if calibration_games < CALIBRATION_GAMES:
                rank_text = (
                    f"🧪 Калибровка "
                    f"{calibration_games}/{CALIBRATION_GAMES}"
                )
            else:
                rank = pvp_rank_for_mmr(mmr)
                rank_text = (
                    f"{rank['emoji']} {rank['name']}"
                )

            text += (
                f"{place} <b>{esc(name)}</b>\n"
                f"   🏆 {mmr} MMR • {rank_text}\n"
                f"   ⚔️ {row['ranked_wins']} побед / "
                f"{row['ranked_losses']} поражений\n\n"
            )

    await safe_edit(
        call.message,
        text,
        InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🏆 Рейтинговый PvP",
                        callback_data="pvp_leaderboard_ranked"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⚔️ Обычный PvP",
                        callback_data="pvp_leaderboard_normal"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ Назад",
                        callback_data="pvp"
                    )
                ]
            ]
        )
    )


@dp.callback_query(F.data == "pvp_leaderboard_normal")
async def pvp_leaderboard_normal_callback(call: CallbackQuery):
    await call.answer()

    rows = db_execute("""
        SELECT
            p.user_id,
            p.username,
            p.first_name,
            s.total_wins,
            s.total_losses,
            s.total_games
        FROM pvp_stats s
        LEFT JOIN players p
            ON p.user_id = s.user_id
        WHERE s.total_games > 0
        ORDER BY s.total_wins DESC, s.total_games DESC
        LIMIT 100
    """, fetchall=True)

    text = "⚔️ <b>ОБЫЧНЫЙ PVP — ТОП 100</b>\n\n"

    if not rows:
        text += "Пока нет игроков в обычном PvP."
    else:
        medals = ["🥇", "🥈", "🥉"]

        for i, row in enumerate(rows, start=1):
            if i <= 3:
                place = medals[i - 1]
            else:
                place = f"{i}."

            name = (
                row["first_name"]
                or row["username"]
                or f"Игрок {row['user_id']}"
            )

            text += (
                f"{place} <b>{esc(name)}</b>\n"
                f"   ⚔️ {row['total_wins']} побед / "
                f"{row['total_losses']} поражений\n\n"
            )

    await safe_edit(
        call.message,
        text,
        InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🏆 Рейтинговый PvP",
                        callback_data="pvp_leaderboard_ranked"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⚔️ Обычный PvP",
                        callback_data="pvp_leaderboard_normal"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ Назад",
                        callback_data="pvp"
                    )
                ]
            ]
        )
    )

@dp.callback_query(F.data == "pvp_ranked")
async def pvp_ranked_callback(call: CallbackQuery):
    await call.answer()

    user_id = call.from_user.id

    # Уже идёт бой
    active = pvp_active_match(user_id)

    if active:
        await safe_edit(
            call.message,
            "⚔️ <b>У тебя уже есть активный PvP-бой.</b>\n\n"
            "Сначала закончи текущий бой.",
            InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="⚔️ Вернуться в бой",
                            callback_data=f"pvp_match:{active['id']}"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="⬅️ Назад",
                            callback_data="pvp"
                        )
                    ]
                ]
            )
        )
        return

    stats = get_pvp_stats(user_id)

    pvp_remove_from_queue(user_id)

    db_execute("""
        INSERT OR REPLACE INTO pvp_queue (
            user_id,
            mode,
            mmr,
            joined_at
        )
        VALUES (?, 'ranked', ?, ?)
    """, (
        user_id,
        stats["mmr"],
        now_iso()
    ))

    await safe_edit(
        call.message,
        "🏆 <b>РЕЙТИНГОВЫЙ ПОИСК</b>\n\n"
        "🔎 Ищем соперника...\n\n"
        f"🏆 Твой MMR: <b>{stats['mmr']}</b>\n"
        f"🎖 Ранг: <b>{'🧪 Калибровка' if int(stats['calibration_games']) < CALIBRATION_GAMES else pvp_rank_for_mmr(int(stats['mmr']))['emoji'] + ' ' + pvp_rank_for_mmr(int(stats['mmr']))['name']}</b>\n\n"
        "Как только найдётся соперник, "
        "оба игрока должны будут подтвердить бой.",
        InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="❌ Отменить поиск",
                        callback_data="pvp_cancel_queue"
                    )
                ]
            ]
        )
    )





# ============================================================
# PVP — FULL SYSTEM
# ============================================================

import random


# ============================================================
# PVP DATABASE HELPERS
# ============================================================





def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))

CALIBRATION_GAMES = 5

def pvp_in_calibration(user_id):
    stats = get_pvp_stats(user_id)
    return int(stats["calibration_games"]) < CALIBRATION_GAMES


def calibration_mmr_delta(player_mmr, opponent_mmr, won):
    """
    MMR во время первых 5 рейтинговых игр.

    Чем сильнее противник относительно игрока,
    тем больше MMR за победу и меньше потеря за поражение.
    """

    diff = int(opponent_mmr) - int(player_mmr)

    if won:
        if diff >= 300:
            return 150
        elif diff >= 250:
            return 120
        elif diff >= 200:
            return 100
        elif diff >= 150:
            return 80
        elif diff >= 100:
            return 60
        elif diff >= 50:
            return 40
        else:
            return 20

    # Проигрыш:
    # сильному противнику теряем меньше,
    # слабому — больше.
    if diff >= 300:
        return -5
    elif diff >= 200:
        return -5
    elif diff >= 150:
        return -10
    elif diff >= 100:
        return -10
    elif diff >= 50:
        return -15
    elif diff >= 0:
        return -20
    elif diff >= -50:
        return -25
    else:
        return -30


def ranked_mmr_delta(player_mmr, opponent_mmr, won):
    """
    Обычная рейтинговая система после калибровки.

    Победа над более сильным = больше MMR.
    Поражение от более сильного = меньше потери.
    """

    diff = int(opponent_mmr) - int(player_mmr)

    if won:
        bonus = clamp((diff // 50) * 5, -10, 30)
        return max(5, 20 + bonus)

    reduction = clamp((diff // 50) * 5, -15, 15)
    return -max(5, 20 - reduction)


def calculate_ranked_mmr_delta(
    player_mmr,
    opponent_mmr,
    won,
    calibration
):
    if calibration:
        return calibration_mmr_delta(
            player_mmr,
            opponent_mmr,
            won
        )

    return ranked_mmr_delta(
        player_mmr,
        opponent_mmr,
        won
    )

    ensure_pvp_stats(user_id)

    return db_execute("""
        SELECT *
        FROM pvp_stats
        WHERE user_id=?
    """, (user_id,), fetchone=True)


def pvp_get_match(match_id: int):
    return db_execute("""
        SELECT *
        FROM pvp_matches
        WHERE id=?
    """, (match_id,), fetchone=True)










def pvp_player_name(user_id: int):
    player = get_player(user_id)

    if not player:
        return f"Игрок {user_id}"

    return (
        player["first_name"]
        or player["username"]
        or f"Игрок {user_id}"
    )


# ============================================================
# PVP STATS / RATING
# ============================================================





def pvp_calculate_damage(user_id: int):
    base_damage = pvp_attack_damage(user_id)

    minimum = max(
        1,
        int(base_damage * 0.80)
    )

    maximum = max(
        minimum,
        int(base_damage * 1.20)
    )

    return random.randint(
        minimum,
        maximum
    )





# ============================================================
# PVP — ABILITIES / EFFECTS / EVENTS
# ============================================================

pvp_ability_uses = {}
pvp_effect_tasks = {}
pvp_event_tasks = {}


def pvp_effect_rows(match_id, user_id=None):
    if user_id is None:
        return db_execute("SELECT * FROM pvp_effects WHERE match_id=? ORDER BY id", (match_id,), fetchall=True)
    return db_execute("SELECT * FROM pvp_effects WHERE match_id=? AND user_id=? ORDER BY id", (match_id,user_id), fetchall=True)


def add_pvp_effect(match_id, user_id, effect_type, damage, duration):
    now=time.time()
    db_execute("INSERT INTO pvp_effects(match_id,user_id,effect_type,damage,expires_at,next_tick,created_at) VALUES(?,?,?,?,?,?,?)", (match_id,user_id,effect_type,damage,now+duration,now+1,now))


def pvp_effect_text(match_id, user_id):
    rows=pvp_effect_rows(match_id,user_id)
    now=time.time()
    out=[]
    for r in rows:
        left=max(0,int(float(r["expires_at"])-now+0.999))
        if left<=0: continue
        icon={"burn":"🔥","bleed":"🩸","dodge":"👻"}.get(r["effect_type"],"✨")
        out.append(f"{icon} {r['effect_type']} {left}с")
    return " • ".join(out)


def pvp_apply_weapon_effect(match_id, attacker_id, target_id):
    eq=get_equipment(attacker_id)
    if not eq or not eq["weapon_key"]: return (0, "")
    effect=WEAPON_EFFECTS.get(eq["weapon_key"])
    if not effect or random.random()>float(effect.get("chance",0)): return (0, "")
    extra=int(effect["damage"])
    if effect["type"] in ("burn","bleed"):
        add_pvp_effect(match_id,target_id,effect["type"],extra,int(effect["duration"]))
        icon="🔥" if effect["type"]=="burn" else "🩸"
        return extra,f"{icon} {effect['type'].capitalize()} наложено"
    return 0,""


def pvp_shield_reduce(target_id, damage):
    stats=player_combat_stats(target_id)
    if random.random() < float(stats.get("shield_chance",0) or 0):
        reduced=max(1,int(damage*(1-float(stats.get("shield_reduction",0) or 0))))
        return reduced,"🛡️ Щит сработал"
    return damage,""


async def pvp_effect_loop(bot, match_id):
    try:
        while True:
            match=pvp_get_match(match_id)
            if not match or match["status"]!="active":
                db_execute("DELETE FROM pvp_effects WHERE match_id=?",(match_id,))
                return
            now=time.time()
            rows=pvp_effect_rows(match_id)
            for r in rows:
                if now>=float(r["expires_at"]):
                    db_execute("DELETE FROM pvp_effects WHERE id=?",(r["id"],)); continue
                if now<float(r["next_tick"]): continue
                if r["effect_type"] in ("burn","bleed"):
                    target=int(r["user_id"])
                    damage=max(1,int(r["damage"]))
                    if target==int(match["player1_id"]):
                        hp=max(0,int(match["player1_hp"])-damage)
                        db_execute("UPDATE pvp_matches SET player1_hp=? WHERE id=? AND status='active'",(hp,match_id))
                    else:
                        hp=max(0,int(match["player2_hp"])-damage)
                        db_execute("UPDATE pvp_matches SET player2_hp=? WHERE id=? AND status='active'",(hp,match_id))
                    db_execute("UPDATE pvp_effects SET next_tick=? WHERE id=?",(now+1,r["id"]))
            match=pvp_get_match(match_id)
            if not match or match["status"]!="active": return
            if int(match["player1_hp"])<=0 or int(match["player2_hp"])<=0:
                winner=int(match["player1_id"]) if int(match["player2_hp"])<=0 else int(match["player2_id"])
                db_execute("UPDATE pvp_matches SET status='finished',winner_id=?,finished_at=? WHERE id=? AND status='active'",(winner,now_iso(),match_id))
                await pvp_finish_match(bot,match_id,winner)
                return
            await pvp_update_player_message(bot,match,int(match["player1_id"]))
            await pvp_update_player_message(bot,match,int(match["player2_id"]))
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        return
    except Exception:
        log.exception("PvP effect loop failed")


async def pvp_random_event(bot, match_id):
    if random.random() > 0.15 or match_id in pvp_event_tasks:
        return

    events = [
        ("🌫️ <b>МОРОК</b>", "Каждую секунду в течение 5 секунд оба игрока получают 5 урона.", "damage_all"),
        ("🔥 <b>ПЛАМЯ АРЕНЫ</b>", "Следующая атака каждого игрока нанесёт на 15% больше урона.", "damage_boost"),
        ("👻 <b>ТЕНЬ АРЕНЫ</b>", "Оба игрока получают 35% шанс уклониться от следующей атаки.", "dodge"),
    ]
    title, description, event_type = random.choice(events)

    async def run():
        try:
            match = pvp_get_match(match_id)
            if not match or match["status"] != "active":
                return

            if event_type == "damage_all":
                await pvp_update_player_message(bot, match, int(match["player1_id"]), extra_text=f"\n\n{title}\n{description}")
                await pvp_update_player_message(bot, match, int(match["player2_id"]), extra_text=f"\n\n{title}\n{description}")
                for _ in range(5):
                    match = pvp_get_match(match_id)
                    if not match or match["status"] != "active":
                        return
                    db_execute("UPDATE pvp_matches SET player1_hp=max(0,player1_hp-5), player2_hp=max(0,player2_hp-5) WHERE id=? AND status='active'", (match_id,))
                    match = pvp_get_match(match_id)
                    if not match:
                        return
                    await pvp_update_player_message(bot, match, int(match["player1_id"]))
                    await pvp_update_player_message(bot, match, int(match["player2_id"]))
                    await asyncio.sleep(1)
            elif event_type == "damage_boost":
                add_pvp_effect(match_id, int(match["player1_id"]), "damage_boost", 15, 2)
                add_pvp_effect(match_id, int(match["player2_id"]), "damage_boost", 15, 2)
                match = pvp_get_match(match_id)
                if match:
                    await pvp_update_player_message(bot, match, int(match["player1_id"]), extra_text=f"\n\n{title}\n{description}")
                    await pvp_update_player_message(bot, match, int(match["player2_id"]), extra_text=f"\n\n{title}\n{description}")
            else:
                add_pvp_effect(match_id, int(match["player1_id"]), "dodge", 0, 2)
                add_pvp_effect(match_id, int(match["player2_id"]), "dodge", 0, 2)
                match = pvp_get_match(match_id)
                if match:
                    await pvp_update_player_message(bot, match, int(match["player1_id"]), extra_text=f"\n\n{title}\n{description}")
                    await pvp_update_player_message(bot, match, int(match["player2_id"]), extra_text=f"\n\n{title}\n{description}")
        finally:
            pvp_event_tasks.pop(match_id, None)

    pvp_event_tasks[match_id] = asyncio.create_task(run())


# ============================================================
# PVP MENUS
# ============================================================

def pvp_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🏆 Рейтинговый бой",
                    callback_data="pvp_ranked"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⚔️ Обычный режим",
                    callback_data="pvp_unranked"
                )
            ],
            [
                InlineKeyboardButton(
                    text="👤 Вызвать игрока",
                    callback_data="pvp_challenge"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📊 Мой рейтинг",
                    callback_data="pvp_rating"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏆 Таблица PvP",
                    callback_data="pvp_leaderboard"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="game"
                )
            ]
        ]
    )

def pvp_battle_keyboard(user_id: int, match):
    my_turn = (
    int(match["turn_user_id"]) == int(user_id)
)

    attack_text = (
        "⚔️ Атаковать"
        if my_turn
        else "⏳ Ход соперника"
    )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=attack_text,
                    callback_data=f"pvp_attack:{match['id']}"
                )
            ],
            [
                InlineKeyboardButton(text="🌌 Способность", callback_data=f"pvp_ability:{match['id']}"),
                InlineKeyboardButton(text="🧪 Зелье", callback_data=f"pvp_potions:{match['id']}")
            ],
            [
                InlineKeyboardButton(
                    text="🏳️ Сдаться",
                    callback_data=f"pvp_surrender:{match['id']}"
                )
            ]
        ]
    )


# ============================================================
# PVP BATTLE TEXT
# ============================================================

def pvp_match_text(match, user_id: int):
    opponent_id = pvp_opponent(
        match,
        user_id
    )

    if match["player1_id"] == user_id:

        my_hp = match["player1_hp"]
        my_max_hp = match["player1_max_hp"]

        enemy_hp = match["player2_hp"]
        enemy_max_hp = match["player2_max_hp"]

    else:

        my_hp = match["player2_hp"]
        my_max_hp = match["player2_max_hp"]

        enemy_hp = match["player1_hp"]
        enemy_max_hp = match["player1_max_hp"]

    my_name = pvp_player_name(user_id)
    enemy_name = pvp_player_name(opponent_id)

    if match["turn_user_id"] == user_id:
        turn_text = "⚔️ <b>ТВОЙ ХОД!</b>"
    else:
        turn_text = "⏳ <b>Ход соперника...</b>"

    mode_text = (
        "🏆 Рейтинговый"
        if match["mode"] == "ranked"
        else "🎮 Обычный"
    )

    return (
        "⚔️ <b>PVP БОЙ</b>\n\n"

        f"{mode_text}\n\n"

        f"👤 <b>{my_name}</b>\n"
        f"❤️ {my_hp}/{my_max_hp}\n\n"

        "        🆚\n\n"

        f"👤 <b>{enemy_name}</b>\n"
        f"❤️ {enemy_hp}/{enemy_max_hp}\n\n"

        f"{turn_text}\n\n"

        f"💥 Твоя атака: <b>~{pvp_attack_damage(user_id)}</b> урона\n"
        f"🔥 Эффекты: <b>{pvp_effect_text(match['id'], user_id) or 'нет'}</b>\n"
        f"🎯 На сопернике: <b>{pvp_effect_text(match['id'], opponent_id) or 'нет'}</b>"
    )


# ============================================================
# PVP MATCH CREATION
# ============================================================

def pvp_create_match(
    player1_id: int,
    player2_id: int,
    mode: str
):
    pvp_remove_from_queue(player1_id)
    pvp_remove_from_queue(player2_id)

    hp1 = pvp_max_hp(player1_id)
    hp2 = pvp_max_hp(player2_id)

    first_player = random.choice([
        player1_id,
        player2_id
    ])

    if mode == "ranked":
        status = "pending"
        player1_ready = 0
        player2_ready = 0
        started_at = None
    else:
        status = "active"
        player1_ready = 1
        player2_ready = 1
        started_at = now_iso()

    db_execute("""
        INSERT INTO pvp_matches (
            player1_id,
            player2_id,
            mode,
            player1_hp,
            player2_hp,
            player1_max_hp,
            player2_max_hp,
            turn_user_id,
            status,
            player1_ready,
            player2_ready,
            created_at,
            started_at,
            player1_message_id,
            player2_message_id
        )
        VALUES (
            ?, ?, ?,
            ?, ?,
            ?, ?,
            ?,
            ?,
            ?, ?,
            ?,
            ?,
            NULL,
            NULL
        )
    """, (
        player1_id,
        player2_id,
        mode,
        hp1,
        hp2,
        hp1,
        hp2,
        first_player,
        status,
        player1_ready,
        player2_ready,
        now_iso(),
        started_at
    ))

    match = db_execute("""
        SELECT *
        FROM pvp_matches
        WHERE player1_id=?
          AND player2_id=?
        ORDER BY id DESC
        LIMIT 1
    """, (
        player1_id,
        player2_id
    ), fetchone=True)

    if not match:
        return None

    return match["id"]

# ============================================================
# PVP RANKED CONFIRMATION
# ============================================================

def pvp_ranked_confirm_text(match, user_id: int):
    opponent_id = pvp_opponent(match, user_id)

    if opponent_id is None:
        opponent_id = 0

    opponent_stats = get_pvp_stats(opponent_id)

    opponent_name = esc(
        pvp_player_name(opponent_id)
    )

    opponent_mmr = int(
        opponent_stats["mmr"]
    )

    calibration = (
        int(opponent_stats["calibration_games"])
        < CALIBRATION_GAMES
    )

    if calibration:
        opponent_rank = "🧪 Калибровка"
    else:
        rank = pvp_rank_for_mmr(opponent_mmr)
        opponent_rank = (
            f"{rank['emoji']} {rank['name']}"
        )

    return (
        "⚔️ <b>СОПЕРНИК НАЙДЕН!</b>\n\n"

        f"👤 <b>{opponent_name}</b>\n"
        f"🏆 MMR: <b>{opponent_mmr}</b>\n"
        f"🎖 Ранг: <b>{esc(opponent_rank)}</b>\n\n"

        "🏆 <b>Рейтинговый бой</b>\n\n"

        "Оба игрока должны подтвердить начало боя."
    )


def pvp_ranked_confirm_keyboard(match_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Принять бой",
                    callback_data=f"pvp_ranked_confirm:{match_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отказаться",
                    callback_data=f"pvp_ranked_decline:{match_id}"
                )
            ]
        ]
    )

def pvp_result_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🏠 В меню",
                    callback_data="menu"
                )
            ]
        ]
    )

@dp.callback_query(
    F.data.startswith("pvp_ranked_confirm:")
)
async def pvp_ranked_confirm_callback(
    call: CallbackQuery
):
    user_id = int(call.from_user.id)

    try:
        match_id = int(
            call.data.split(":")[1]
        )
    except (ValueError, IndexError):
        await call.answer(
            "Ошибка матча.",
            show_alert=True
        )
        return

    match = pvp_get_match(match_id)

    if not match:
        await call.answer(
            "Матч не найден.",
            show_alert=True
        )
        return

    player1_id = int(match["player1_id"])
    player2_id = int(match["player2_id"])

    if user_id not in (
        player1_id,
        player2_id
    ):
        await call.answer(
            "Ты не участник этого боя.",
            show_alert=True
        )
        return

    if match["status"] != "pending":
        await call.answer(
            "Этот матч уже обработан.",
            show_alert=True
        )
        return

    if user_id == player1_id:
        result = db_execute("""
            UPDATE pvp_matches
            SET player1_ready=1
            WHERE id=?
              AND status='pending'
              AND player1_ready=0
        """, (match_id,))
    else:
        result = db_execute("""
            UPDATE pvp_matches
            SET player2_ready=1
            WHERE id=?
              AND status='pending'
              AND player2_ready=0
        """, (match_id,))

    if hasattr(result, "rowcount"):
        if result.rowcount == 0:
            await call.answer(
                "Ты уже подтвердил бой."
            )
            return

    match = pvp_get_match(match_id)

    if not match:
        await call.answer(
            "Ошибка матча.",
            show_alert=True
        )
        return

    await call.answer(
        "✅ Бой подтверждён!"
    )

    # --------------------------------------------------------
    # Оба игрока подтвердили
    # --------------------------------------------------------

    if (
        int(match["player1_ready"]) == 1
        and int(match["player2_ready"]) == 1
    ):
        db_execute("""
            UPDATE pvp_matches
            SET
                status='active',
                started_at=?
            WHERE id=?
              AND status='pending'
              AND player1_ready=1
              AND player2_ready=1
        """, (
            now_iso(),
            match_id
        ))

        match = pvp_get_match(match_id)

        if not match:
            return

        # Обновляем сообщения обоим игрокам
        await pvp_update_player_message(
            call.bot,
            match,
            player1_id
        )

        await pvp_update_player_message(
            call.bot,
            match,
            player2_id
        )

        # Запускаем таймер первого хода
        pvp_start_turn_timer(
            call.bot,
            match_id,
            int(match["turn_user_id"])
        )

        return

    # --------------------------------------------------------
    # Пока ждём второго игрока
    # --------------------------------------------------------

    opponent_id = (
        player2_id
        if user_id == player1_id
        else player1_id
    )

    if user_id == player1_id:
        own_ready = int(match["player1_ready"])
        opponent_ready = int(match["player2_ready"])
    else:
        own_ready = int(match["player2_ready"])
        opponent_ready = int(match["player1_ready"])

    status_text = (
        "⏳ <b>Ожидаем подтверждение соперника...</b>"
        if opponent_ready == 0
        else "⚔️ <b>Соперник уже подтвердил бой!</b>"
    )

    try:
        await call.message.edit_text(
            "🏆 <b>РЕЙТИНГОВЫЙ БОЙ</b>\n\n"
            "✅ Ты подтвердил бой.\n\n"
            f"{status_text}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[]
            )
        )
    except Exception:
        pass


@dp.callback_query(
    F.data.startswith("pvp_ranked_decline:")
)
async def pvp_ranked_decline_callback(
    call: CallbackQuery
):
    user_id = int(call.from_user.id)

    try:
        match_id = int(
            call.data.split(":")[1]
        )
    except (ValueError, IndexError):
        await call.answer(
            "Ошибка матча.",
            show_alert=True
        )
        return

    match = pvp_get_match(match_id)

    if not match:
        await call.answer(
            "Матч не найден.",
            show_alert=True
        )
        return

    player1_id = int(match["player1_id"])
    player2_id = int(match["player2_id"])

    if user_id not in (
        player1_id,
        player2_id
    ):
        await call.answer(
            "Ты не участник этого боя.",
            show_alert=True
        )
        return

    if match["status"] != "pending":
        await call.answer(
            "Этот матч уже обработан.",
            show_alert=True
        )
        return

    opponent_id = (
        player2_id
        if user_id == player1_id
        else player1_id
    )

    db_execute("""
        UPDATE pvp_matches
        SET
            status='finished',
            winner_id=?,
            finished_at=?
        WHERE id=?
          AND status='pending'
    """, (
        opponent_id,
        now_iso(),
        match_id
    ))

    pvp_remove_from_queue(
        player1_id
    )

    pvp_remove_from_queue(
        player2_id
    )

    await call.answer(
        "❌ Ты отказался от боя."
    )

    try:
        await call.message.edit_text(
            "❌ <b>РЕЙТИНГОВЫЙ БОЙ ОТМЕНЁН</b>\n\n"
            "Ты отказался от матча."
        )
    except Exception:
        pass

    try:
        await call.bot.send_message(
            opponent_id,
            "❌ <b>Соперник отказался от рейтингового боя.</b>"
        )
    except Exception:
        log.exception(
            "Failed to notify ranked opponent about decline"
        )

# ============================================================
# PVP START MATCH
# ============================================================

async def pvp_start_match(
    bot: Bot,
    player1_id: int,
    player2_id: int,
    mode: str
):
    match_id = pvp_create_match(
        player1_id,
        player2_id,
        mode
    )

    if not match_id:
        log.error(
            "Failed to create PvP match: %s vs %s",
            player1_id,
            player2_id
        )
        return None

    # ========================================================
    # RANKED — ПОДТВЕРЖДЕНИЕ БОЯ
    # ========================================================

    if mode == "ranked":


        match = pvp_get_match(match_id)

        if not match:
            return None

        msg1 = await bot.send_message(
            player1_id,
            pvp_ranked_confirm_text(
                match,
                player1_id
            ),
            reply_markup=pvp_ranked_confirm_keyboard(
                match_id
            )
        )

        msg2 = await bot.send_message(
            player2_id,
            pvp_ranked_confirm_text(
                match,
                player2_id
            ),
            reply_markup=pvp_ranked_confirm_keyboard(
                match_id
            )
        )

        db_execute("""
            UPDATE pvp_matches
            SET
                player1_message_id=?,
                player2_message_id=?
            WHERE id=?
        """, (
            msg1.message_id,
            msg2.message_id,
            match_id
        ))

        return match_id

    # ========================================================
    # UNRANKED — СРАЗУ В БОЙ
    # ========================================================

    match = pvp_get_match(match_id)

    if not match:
        return None

    msg1 = await bot.send_message(
        player1_id,
        pvp_match_text(
            match,
            player1_id
        ),
        reply_markup=pvp_battle_keyboard(
            player1_id,
            match
        )
    )

    msg2 = await bot.send_message(
        player2_id,
        pvp_match_text(
            match,
            player2_id
        ),
        reply_markup=pvp_battle_keyboard(
            player2_id,
            match
        )
    )

    db_execute("""
        UPDATE pvp_matches
        SET
            player1_message_id=?,
            player2_message_id=?
        WHERE id=?
    """, (
        msg1.message_id,
        msg2.message_id,
        match_id
    ))

           # Запускаем таймер первого хода
    pvp_start_turn_timer(
        bot,
        match_id,
        int(match["turn_user_id"])
    )
    
    return match_id


# ============================================================
# PVP UPDATE PLAYER MESSAGE
# ============================================================

async def pvp_update_player_message(
    bot: Bot,
    match,
    user_id: int,
    extra_text: str = ""
):
    if user_id == match["player1_id"]:
        message_id = match["player1_message_id"]

    elif user_id == match["player2_id"]:
        message_id = match["player2_message_id"]

    else:
        return

    if not message_id:
        return

    try:
        await bot.edit_message_text(
            chat_id=user_id,
            message_id=message_id,
            text=pvp_match_text(
                match,
                user_id
            ) + extra_text,
            reply_markup=pvp_battle_keyboard(
                user_id,
                match
            )
        )

    except Exception:
        log.exception(
            "Failed to update PvP message for %s",
            user_id
        )
        
# ============================================================
# PVP MAIN PAGE
# ============================================================

@dp.callback_query(F.data == "pvp")
async def pvp_callback(call: CallbackQuery):
    await call.answer()

    stats = get_pvp_stats(
        call.from_user.id
    )

    await safe_edit(
        call.message,

        "👥 <b>PVP</b>\n\n"

        f"🏆 MMR: <b>{stats['mmr']}</b>\n"
        f"🎖 Ранг: <b>{pvp_rank_name(stats['mmr'])}</b>\n\n"

        f"⚔️ Рейтинговых игр: "
        f"{stats['ranked_games']}\n"

        f"🏆 Побед: "
        f"{stats['ranked_wins']}\n"

        f"💀 Поражений: "
        f"{stats['ranked_losses']}\n\n"

        f"🎯 Калибровка: "
        f"{min(5, stats['calibration_games'])}/5",

        pvp_menu()
    )


# ============================================================
# PVP RATING
# ============================================================

@dp.callback_query(F.data == "pvp_rating")
async def pvp_rating_callback(call: CallbackQuery):
    user_id = call.from_user.id

    await call.answer()

    ensure_pvp_stats(user_id)

    stats = get_pvp_stats(user_id)

    mmr = int(stats["mmr"])
    calibration = int(stats["calibration_games"])

    ranked_games = int(stats["ranked_games"])
    ranked_wins = int(stats["ranked_wins"])
    ranked_losses = int(stats["ranked_losses"])

    if calibration < CALIBRATION_GAMES:
        rank_text = "🧪 <b>Калибровка</b>"
        calibration_text = (
            f"🎯 Калибровка: "
            f"<b>{calibration}/{CALIBRATION_GAMES}</b>"
        )
    else:
        rank = pvp_rank_for_mmr(mmr)

        rank_text = (
            f"{rank['emoji']} "
            f"<b>{rank['name']}</b>"
        )

        calibration_text = (
            "🎯 Калибровка: <b>завершена</b>"
        )

    await safe_edit(
        call.message,

        "📊 <b>МОЙ PVP РЕЙТИНГ</b>\n\n"

        f"🏆 MMR: <b>{mmr}</b>\n"
        f"🎖 Ранг: {rank_text}\n\n"

        f"{calibration_text}\n\n"

        f"⚔️ Рейтинговых игр: "
        f"<b>{ranked_games}</b>\n"

        f"🏆 Побед: "
        f"<b>{ranked_wins}</b>\n"

        f"💀 Поражений: "
        f"<b>{ranked_losses}</b>\n\n"

        f"🔥 Текущая серия: "
        f"<b>{stats['current_streak']}</b>\n"

        f"🏅 Лучшая серия: "
        f"<b>{stats['best_streak']}</b>\n\n"

        f"💥 Общий урон: "
        f"<b>{stats['total_damage']}</b>",

        InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⬅️ Назад",
                        callback_data="pvp"
                    )
                ]
            ]
        )
    )

# ============================================================
# PVP LEADERBOARD
# ============================================================

@dp.callback_query(F.data == "pvp_leaderboard")
async def pvp_leaderboard_callback(
    call: CallbackQuery
):
    await call.answer()

    rows = db_execute("""
        SELECT
            p.mmr,
            p.ranked_games,
            p.ranked_wins,
            pl.first_name,
            pl.username
        FROM pvp_stats p
        LEFT JOIN players pl
            ON pl.user_id=p.user_id
        ORDER BY p.mmr DESC
        LIMIT 10
    """, fetchall=True)

    text = "🏆 <b>ТОП PVP</b>\n\n"

    if not rows:
        text += "Пока нет игроков в рейтинге."
    else:
        for index, row in enumerate(
            rows,
            start=1
        ):
            name = (
                row["first_name"]
                or row["username"]
                or "Игрок"
            )

            text += (
                f"<b>{index}.</b> "
                f"{name}\n"
                f"   🏆 {row['mmr']} MMR\n"
                f"   🎖 {pvp_rank_name(row['mmr'])}\n"
                f"   ⚔️ {row['ranked_games']} игр\n\n"
            )

    await safe_edit(
        call.message,
        text,
        InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⬅️ Назад",
                        callback_data="pvp"
                    )
                ]
            ]
        )
    )


# ============================================================
# PVP UNRANKED QUEUE
# ============================================================

@dp.callback_query(F.data == "pvp_unranked")
async def pvp_unranked_callback(
    call: CallbackQuery
):
    user_id = call.from_user.id

    await call.answer()

    active = pvp_active_match(
        user_id
    )

    if active:

        await safe_edit(
            call.message,

            "⚔️ <b>У тебя уже идёт PvP-бой.</b>\n\n"
            "Сначала закончи текущий бой.",

            InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="⚔️ Вернуться в бой",
                            callback_data=(
                                f"pvp_match:{active['id']}"
                            )
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="⬅️ Назад",
                            callback_data="pvp"
                        )
                    ]
                ]
            )
        )

        return

    # Если уже ищем — просто показываем поиск
    if pvp_is_in_queue(user_id):

        await safe_edit(
            call.message,

            "🎮 <b>ОБЫЧНЫЙ БОЙ</b>\n\n"
            "🔎 <b>Ищем соперника...</b>\n\n"
            "Как только игрок найдётся — "
            "бой начнётся автоматически.\n\n"
            "🏆 MMR не изменяется.",

            InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="❌ Отменить поиск",
                            callback_data=(
                                "pvp_cancel_queue"
                            )
                        )
                    ]
                ]
            )
        )

        return

    db_execute("""
        INSERT INTO pvp_queue (
            user_id,
            mode,
            mmr,
            joined_at
        )
        VALUES (?, 'unranked', 0, ?)
    """, (
        user_id,
        now_iso()
    ))

    await safe_edit(
        call.message,

        "🎮 <b>ОБЫЧНЫЙ БОЙ</b>\n\n"

        "🔎 <b>Ищем соперника...</b>\n\n"

        "Как только игрок найдётся — "
        "<b>бой начнётся сразу.</b>\n\n"

        "🏆 MMR не изменяется.",

        InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="❌ Отменить поиск",
                        callback_data=(
                            "pvp_cancel_queue"
                        )
                    )
                ]
            ]
        )
    )


# ============================================================
# PVP CANCEL QUEUE
# ============================================================

@dp.callback_query(F.data == "pvp_cancel_queue")
async def pvp_cancel_queue_callback(
    call: CallbackQuery
):
    await call.answer()

    pvp_remove_from_queue(
        call.from_user.id
    )

    await safe_edit(
        call.message,

        "❌ <b>Поиск отменён.</b>\n\n"
        "Ты вышел из очереди PvP.",

        InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="👥 PvP",
                        callback_data="pvp"
                    )
                ]
            ]
        )
    )


# ============================================================
# PVP RETURN TO ACTIVE MATCH
# ============================================================

@dp.callback_query(F.data.startswith("pvp_match:"))
async def pvp_match_callback(
    call: CallbackQuery
):
    user_id = call.from_user.id

    try:
        match_id = int(
            call.data.split(":")[1]
        )
    except (ValueError, IndexError):
        await call.answer(
            "Ошибка матча.",
            show_alert=True
        )
        return

    match = pvp_get_match(
        match_id
    )

    if not match:
        await call.answer(
            "Матч не найден.",
            show_alert=True
        )
        return

    if user_id not in (
        match["player1_id"],
        match["player2_id"]
    ):
        await call.answer(
            "Ты не участник этого боя.",
            show_alert=True
        )
        return

    if match["status"] != "active":
        await call.answer(
            "Этот бой уже закончен.",
            show_alert=True
        )
        return

    await call.answer()

    await safe_edit(
        call.message,
        pvp_match_text(
            match,
            user_id
        ),
        pvp_battle_keyboard(
            user_id,
            match
        )
    )


# ============================================================
# PVP ATTACK
# ============================================================
async def pvp_turn_timeout(
    bot: Bot,
    match_id: int,
    expected_turn_user_id: int
):
    try:
        await asyncio.sleep(PVP_TURN_TIMEOUT)

        match = pvp_get_match(match_id)

        if not match:
            return

        if match["status"] != "active":
            return

        # Если за 15 секунд ход уже сменился —
        # этот таймер больше ничего не делает.
        if int(match["turn_user_id"]) != int(expected_turn_user_id):
            return

        loser_id = expected_turn_user_id

        winner_id = pvp_opponent(
            match,
            loser_id
        )

        result = db_execute("""
            UPDATE pvp_matches
            SET
                status='finished',
                winner_id=?,
                finished_at=?
            WHERE id=?
              AND status='active'
              AND turn_user_id=?
        """, (
            winner_id,
            now_iso(),
            match_id,
            loser_id
        ))

        if not result:
            return

        try:
            await bot.send_message(
                loser_id,
                "⏰ <b>ВРЕМЯ ВЫШЛО!</b>\n\n"
                "Ты не сделал ход за 15 секунд.\n"
                "💀 Тебе засчитано поражение."
            )
        except Exception:
            log.exception(
                "Failed to send timeout message to loser"
            )

        try:
            await bot.send_message(
                winner_id,
                "🏆 <b>ПОБЕДА!</b>\n\n"
                "Соперник не сделал ход за 15 секунд.\n"
                "💥 Тебе засчитана победа."
            )
        except Exception:
            log.exception(
                "Failed to send timeout message to winner"
            )

        await pvp_finish_match(
            bot=bot,
            match_id=match_id,
            winner_id=winner_id
        )

    except asyncio.CancelledError:
        return

    except Exception:
        log.exception(
            "PvP turn timeout error: match=%s",
            match_id
        )

    finally:
        current_task = pvp_turn_tasks.get(match_id)

        if current_task is asyncio.current_task():
            pvp_turn_tasks.pop(match_id, None)


def pvp_start_turn_timer(
    bot: Bot,
    match_id: int,
    turn_user_id: int
):
    old_task = pvp_turn_tasks.get(match_id)

    if old_task:
        old_task.cancel()

    task = asyncio.create_task(
        pvp_turn_timeout(
            bot,
            match_id,
            turn_user_id
        )
    )

    pvp_turn_tasks[match_id] = task
    
@dp.callback_query(F.data.startswith("pvp_attack:"))
async def pvp_attack_callback(
    call: CallbackQuery
):
    user_id = call.from_user.id

    try:
        match_id = int(
            call.data.split(":")[1]
        )
    except (ValueError, IndexError):
        await call.answer(
            "Ошибка матча.",
            show_alert=True
        )
        return

    match = pvp_get_match(match_id)

    if not match:
        await call.answer(
            "Матч не найден.",
            show_alert=True
        )
        return

    if match["status"] != "active":
        await call.answer(
            "Бой уже закончен.",
            show_alert=True
        )
        return

    if user_id not in (
        match["player1_id"],
        match["player2_id"]
    ):
        await call.answer(
            "Ты не участник этого боя.",
            show_alert=True
        )
        return

    if match["turn_user_id"] != user_id:
        await call.answer(
            "⏳ Сейчас ход соперника!",
            show_alert=True
        )
        return

    # Отменяем старый таймер этого хода
    old_task = pvp_turn_tasks.get(match_id)

    if old_task:
        old_task.cancel()
        pvp_turn_tasks.pop(match_id, None)

    opponent_id = pvp_opponent(
        match,
        user_id
    )

    damage = pvp_calculate_damage(user_id)
    boost_rows = pvp_effect_rows(match_id, user_id)
    for boost in boost_rows:
        if boost["effect_type"] == "damage_boost" and float(boost["expires_at"]) > time.time():
            pct = float(boost["damage"] or 15) / 100.0
            damage = max(1, int(damage * (1.0 + pct)))
            charges = 1 if float(boost["damage"] or 15) == 5 else 0
            if charges:
                # PvP potion uses two attacks. Store remaining charges in damage as 5% marker via created_at timestamp convention is avoided: use row id and count from next_tick.
                left = max(0, int(boost["next_tick"] or 2) - 1)
                if left <= 0:
                    db_execute("DELETE FROM pvp_effects WHERE id=?", (boost["id"],))
                else:
                    db_execute("UPDATE pvp_effects SET next_tick=? WHERE id=?", (left, boost["id"]))
            else:
                db_execute("DELETE FROM pvp_effects WHERE id=?", (boost["id"],))
            break
    dodge_rows = pvp_effect_rows(match_id, opponent_id)
    if any(r["effect_type"]=="dodge" and float(r["expires_at"])>time.time() for r in dodge_rows) and random.random()<0.45:
        db_execute("DELETE FROM pvp_effects WHERE match_id=? AND user_id=? AND effect_type='dodge'",(match_id,opponent_id))
        await call.answer("👻 Соперник уклонился!")
        db_execute("UPDATE pvp_matches SET turn_user_id=? WHERE id=?",(opponent_id,match_id))
        pvp_start_turn_timer(call.bot,match_id,opponent_id)
        await pvp_update_player_message(call.bot,pvp_get_match(match_id),int(match["player1_id"]))
        await pvp_update_player_message(call.bot,pvp_get_match(match_id),int(match["player2_id"]))
        return
    damage, shield_text = pvp_shield_reduce(opponent_id, damage)
    extra_effect, effect_text = pvp_apply_weapon_effect(match_id, user_id, opponent_id)
    damage += extra_effect
    if pvp_effect_rows(match_id) and match_id not in pvp_effect_tasks:
        pvp_effect_tasks[match_id] = asyncio.create_task(pvp_effect_loop(call.bot, match_id))
    await pvp_random_event(call.bot, match_id)

    # ========================================================
    # ИГРОК 1 АТАКУЕТ
    # ========================================================

    if match["player1_id"] == user_id:

        new_hp = max(
            0,
            match["player2_hp"] - damage
        )

        db_execute("""
            UPDATE pvp_matches
            SET
                player2_hp=?,
                player1_damage=player1_damage+?,
                turn_user_id=?
            WHERE id=?
              AND status='active'
              AND turn_user_id=?
        """, (
            new_hp,
            damage,
            opponent_id,
            match_id,
            user_id
        ))

    # ========================================================
    # ИГРОК 2 АТАКУЕТ
    # ========================================================

    else:

        new_hp = max(
            0,
            match["player1_hp"] - damage
        )

        db_execute("""
            UPDATE pvp_matches
            SET
                player1_hp=?,
                player2_damage=player2_damage+?,
                turn_user_id=?
            WHERE id=?
              AND status='active'
              AND turn_user_id=?
        """, (
            new_hp,
            damage,
            opponent_id,
            match_id,
            user_id
        ))

    match = pvp_get_match(match_id)

    if not match:
        await call.answer(
            "Ошибка матча.",
            show_alert=True
        )
        return

    # ========================================================
    # ПОБЕДА
    # ========================================================

    if (
        match["player1_hp"] <= 0
        or match["player2_hp"] <= 0
    ):

        winner_id = user_id

        db_execute("""
            UPDATE pvp_matches
            SET
                status='finished',
                winner_id=?,
                finished_at=?
            WHERE id=?
              AND status='active'
        """, (
            winner_id,
            now_iso(),
            match_id
        ))

        # На всякий случай отменяем таймер
        task = pvp_turn_tasks.pop(match_id, None)

        if task:
            task.cancel()

        await call.answer(
            f"💥 -{damage} HP"
        )

        await pvp_finish_match(
            bot=call.bot,
            match_id=match_id,
            winner_id=winner_id
        )

        return

    # ========================================================
    # ЗАПУСКАЕМ 15 СЕКУНД ДЛЯ СОПЕРНИКА
    # ========================================================

    pvp_start_turn_timer(
        call.bot,
        match_id,
        int(match["turn_user_id"])
    )

    # ========================================================
    # ОБНОВЛЕНИЕ ЭКРАНОВ
    # ========================================================

    await pvp_update_player_message(
        call.bot,
        match,
        int(match["player1_id"])
    )

    await pvp_update_player_message(
        call.bot,
        match,
        int(match["player2_id"])
    )

    await call.answer(
        f"💥 -{damage} HP"
    )

@dp.callback_query(F.data.startswith("pvp_ability:"))
async def pvp_ability_callback(call: CallbackQuery):
    user_id=int(call.from_user.id)
    match_id=int(call.data.split(":",1)[1])
    match=pvp_get_match(match_id)
    if not match or match["status"]!="active":
        await call.answer("Бой уже закончен.",show_alert=True); return
    if int(match["turn_user_id"])!=user_id:
        await call.answer("⏳ Сейчас ход соперника.",show_alert=True); return
    used=pvp_ability_uses.get((match_id,user_id),0)
    if used>=2:
        await call.answer("🌌 Способность уже использована 2 раза.",show_alert=True); return
    eq=get_equipment(user_id)
    if not eq or not eq["ability_key"]:
        await call.answer("У тебя нет способности.",show_alert=True); return
    opponent=pvp_opponent(match,user_id)
    key=eq["ability_key"]
    if key in ("wrath_of_heaven","ability_firestorm"):
        damage=150 if key=="wrath_of_heaven" else 95
        damage,shield_text=pvp_shield_reduce(opponent,damage)
        if match["player1_id"]==user_id:
            hp=max(0,int(match["player2_hp"])-damage)
            db_execute("UPDATE pvp_matches SET player2_hp=?,turn_user_id=?,player1_damage=player1_damage+? WHERE id=?",(hp,opponent,damage,match_id))
        else:
            hp=max(0,int(match["player1_hp"])-damage)
            db_execute("UPDATE pvp_matches SET player1_hp=?,turn_user_id=?,player2_damage=player2_damage+? WHERE id=?",(hp,opponent,damage,match_id))
        add_pvp_effect(match_id,opponent,"burn",18 if key=="ability_firestorm" else 25,4)
        text=f"🌌 {eq['ability_name']} • -{damage} HP"
    elif key in ("divine_rebirth","ability_vampiric"):
        if match["player1_id"]==user_id:
            cur=int(match["player1_hp"]); mx=int(match["player1_max_hp"])
            new=min(mx,cur+int(mx*(0.5 if key=="divine_rebirth" else 0.3)))
            db_execute("UPDATE pvp_matches SET player1_hp=?,turn_user_id=? WHERE id=?",(new,opponent,match_id))
            heal=new-cur
        else:
            cur=int(match["player2_hp"]); mx=int(match["player2_max_hp"])
            new=min(mx,cur+int(mx*(0.5 if key=="divine_rebirth" else 0.3)))
            db_execute("UPDATE pvp_matches SET player2_hp=?,turn_user_id=? WHERE id=?",(new,opponent,match_id))
            heal=new-cur
        text=f"🌌 {eq['ability_name']} • +{heal} HP"
    else:
        add_pvp_effect(match_id,user_id,"dodge",0,3)
        db_execute("UPDATE pvp_matches SET turn_user_id=? WHERE id=?",(opponent,match_id))
        text=f"🌑 {eq['ability_name']} • уклонение активировано"
    pvp_ability_uses[(match_id,user_id)]=used+1
    await pvp_update_player_message(call.bot,pvp_get_match(match_id),int(match["player1_id"]))
    await pvp_update_player_message(call.bot,pvp_get_match(match_id),int(match["player2_id"]))
    pvp_start_turn_timer(call.bot,match_id,opponent)
    await call.answer(text)

pvp_potion_cooldowns = {}

@dp.callback_query(F.data.startswith("pvp_potions:"))
async def pvp_potions_menu_callback(call: CallbackQuery):
    try:
        match_id = int(call.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await call.answer("Ошибка матча.", show_alert=True); return
    match = pvp_get_match(match_id)
    if not match or match["status"] != "active":
        await call.answer("Бой уже закончен.", show_alert=True); return
    user_id = call.from_user.id
    rows=[]
    for key,name,desc in [
        ("potion_void","🕳️ Опустошение","+5% урона на 2 твои атаки"),
        ("potion_regen","❤️ Регенерация","+30% HP"),
        ("potion_invisibility","👻 Невидимость","45% уклонения на 2 твоих хода")]:
        item=db_execute("SELECT item_id FROM items WHERE item_key=? AND item_type='potion'",(key,),fetchone=True)
        inv=db_execute("SELECT quantity FROM inventory WHERE user_id=? AND item_id=?",(user_id,item["item_id"] if item else -1),fetchone=True)
        qty=int(inv["quantity"]) if inv else 0
        rows.append([InlineKeyboardButton(text=f"{name} ×{qty} — {desc}",callback_data=f"pvp_potion:{match_id}:{key}" if qty>0 else "potion_unavailable")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад",callback_data=f"pvp_back:{match_id}")])
    await call.answer()
    await safe_edit(call.message,"🧪 <b>ЗЕЛЬЯ В БОЮ</b>\n\nВыбери зелье:",InlineKeyboardMarkup(inline_keyboard=rows))

@dp.callback_query(F.data.startswith("pvp_back:"))
async def pvp_back_callback(call: CallbackQuery):
    match_id=int(call.data.split(":",1)[1]); match=pvp_get_match(match_id)
    if match: await call.answer(); await safe_edit(call.message,pvp_match_text(match,call.from_user.id),pvp_battle_keyboard(call.from_user.id,match))

@dp.callback_query(F.data.startswith("pvp_potion:"))
async def pvp_potion_callback(call: CallbackQuery):
    parts=call.data.split(":")
    if len(parts)!=3:
        await call.answer("Ошибка зелья.",show_alert=True); return
    try: match_id=int(parts[1])
    except ValueError: await call.answer("Ошибка матча.",show_alert=True); return
    key=parts[2]; user_id=int(call.from_user.id); match=pvp_get_match(match_id)
    if not match or match["status"]!="active": await call.answer("Бой уже закончен.",show_alert=True); return
    if user_id not in (int(match["player1_id"]),int(match["player2_id"])): await call.answer("Ты не участник этого боя.",show_alert=True); return
    item=db_execute("SELECT * FROM items WHERE item_key=? AND item_type='potion'",(key,),fetchone=True)
    inv=db_execute("SELECT quantity FROM inventory WHERE user_id=? AND item_id=?",(user_id,item["item_id"] if item else -1),fetchone=True)
    if not item or not inv or int(inv["quantity"])<=0: await call.answer("Такого зелья нет.",show_alert=True); return
    if key=="potion_regen":
        if int(match["turn_user_id"])!=user_id: await call.answer("⏳ Сейчас ход соперника.",show_alert=True); return
        max_hp=int(match["player1_max_hp"] if int(match["player1_id"])==user_id else match["player2_max_hp"]); cur=int(match["player1_hp"] if int(match["player1_id"])==user_id else match["player2_hp"])
        if cur>=max_hp: await call.answer("❤️ HP уже полное.",show_alert=True); return
        new=min(max_hp,cur+max(1,int(max_hp*.30))); remove_item(user_id,key,1)
        if int(match["player1_id"])==user_id: db_execute("UPDATE pvp_matches SET player1_hp=? WHERE id=?",(new,match_id))
        else: db_execute("UPDATE pvp_matches SET player2_hp=? WHERE id=?",(new,match_id))
        await call.answer(f"❤️ +{new-cur} HP")
    elif key=="potion_void":
        remove_item(user_id,key,1)
        # damage stores remaining attacks; 5 means +5 percent
        db_execute("DELETE FROM pvp_effects WHERE match_id=? AND user_id=? AND effect_type='damage_boost'",(match_id,user_id))
        add_pvp_effect(match_id,user_id,"damage_boost",5,999999)
        db_execute("UPDATE pvp_effects SET next_tick=2 WHERE match_id=? AND user_id=? AND effect_type='damage_boost'",(match_id,user_id))
        await call.answer("🕳️ Опустошение активировано — +5% на 2 атаки")
    elif key=="potion_invisibility":
        remove_item(user_id,key,1)
        db_execute("DELETE FROM pvp_effects WHERE match_id=? AND user_id=? AND effect_type='dodge'",(match_id,user_id))
        add_pvp_effect(match_id,user_id,"dodge",2,999999)
        await call.answer("👻 Невидимость активирована — на 2 хода")
    else:
        await call.answer("Неизвестное зелье.",show_alert=True); return
    match=pvp_get_match(match_id)
    if match:
        await pvp_update_player_message(call.bot,match,int(match["player1_id"]))
        await pvp_update_player_message(call.bot,match,int(match["player2_id"]))

@dp.callback_query(F.data.startswith("pvp_potion:"))
async def pvp_potion_legacy_unreachable(call: CallbackQuery):
    await call.answer("Открой меню зелий заново.", show_alert=True)

async def pvp_potion_callback(call: CallbackQuery):
    user_id = int(call.from_user.id)

    try:
        match_id = int(call.data.split(":")[1])
    except (ValueError, IndexError):
        await call.answer(
            "Ошибка матча.",
            show_alert=True
        )
        return

    match = pvp_get_match(match_id)

    if not match:
        await call.answer(
            "Матч не найден.",
            show_alert=True
        )
        return

    if match["status"] != "active":
        await call.answer(
            "Бой уже закончен.",
            show_alert=True
        )
        return

    player1_id = int(match["player1_id"])
    player2_id = int(match["player2_id"])

    if user_id not in (player1_id, player2_id):
        await call.answer(
            "Ты не участник этого боя.",
            show_alert=True
        )
        return

    # ========================================================
    # КУЛДАУН ЗЕЛЬЯ — 3 СЕКУНДЫ
    # ========================================================

    import time

    now = time.monotonic()
    last_potion_time = pvp_potion_cooldowns.get(user_id, 0)
    cooldown_left = 3.0 - (now - last_potion_time)

    if cooldown_left > 0:
        await call.answer(
            f"🧪 Подожди {cooldown_left:.1f} сек.",
            show_alert=True
        )
        return

    player = get_player(user_id)

    if not player:
        await call.answer(
            "Игрок не найден.",
            show_alert=True
        )
        return

    potions = int(player["potions"])

    if potions <= 0:
        await call.answer(
            "🧪 У тебя нет зелий.",
            show_alert=True
        )
        return

    # ========================================================
    # ОПРЕДЕЛЯЕМ HP ИГРОКА
    # ========================================================

    if player1_id == user_id:
        max_hp = int(match["player1_max_hp"])
        current_hp = int(match["player1_hp"])
    else:
        max_hp = int(match["player2_max_hp"])
        current_hp = int(match["player2_hp"])

    if current_hp >= max_hp:
        await call.answer(
            "❤️ У тебя уже полное здоровье.",
            show_alert=True
        )
        return

    heal = max(
        1,
        int(max_hp * 0.30)
    )

    new_hp = min(
        max_hp,
        current_hp + heal
    )

    actual_heal = new_hp - current_hp

    if actual_heal <= 0:
        await call.answer(
            "❤️ У тебя уже полное здоровье.",
            show_alert=True
        )
        return

    # ========================================================
    # ЗАБИРАЕМ ЗЕЛЬЕ
    # ========================================================

    db_execute("""
        UPDATE players
        SET potions = potions - 1
        WHERE user_id = ?
          AND potions > 0
    """, (user_id,))

    # ========================================================
    # ОБНОВЛЯЕМ HP
    # ВАЖНО: ХОД НЕ МЕНЯЕМ
    # ========================================================

    if player1_id == user_id:

        db_execute("""
            UPDATE pvp_matches
            SET player1_hp = ?
            WHERE id = ?
              AND status = 'active'
        """, (
            new_hp,
            match_id
        ))

    else:

        db_execute("""
            UPDATE pvp_matches
            SET player2_hp = ?
            WHERE id = ?
              AND status = 'active'
        """, (
            new_hp,
            match_id
        ))

    # Запоминаем момент успешного использования
    pvp_potion_cooldowns[user_id] = time.monotonic()

    # Получаем свежий матч
    match = pvp_get_match(match_id)

    if not match:
        await call.answer(
            "Ошибка матча.",
            show_alert=True
        )
        return

    # Обновляем интерфейс боя у обоих игроков
    await pvp_update_player_message(
        call.bot,
        match,
        player1_id
    )

    await pvp_update_player_message(
        call.bot,
        match,
        player2_id
    )

    await call.answer(
        f"🧪 +{actual_heal} HP"
    )
    
@dp.callback_query(F.data.startswith("pvp_surrender:"))
async def pvp_surrender_callback(
    call: CallbackQuery
):
    user_id = call.from_user.id

    try:
        match_id = int(
            call.data.split(":")[1]
        )
    except (ValueError, IndexError):
        await call.answer(
            "Ошибка матча.",
            show_alert=True
        )
        return

    match = pvp_get_match(match_id)

    if not match:
        await call.answer(
            "Матч не найден.",
            show_alert=True
        )
        return

    if match["status"] != "active":
        await call.answer(
            "Бой уже закончен.",
            show_alert=True
        )
        return

    if user_id not in (
        match["player1_id"],
        match["player2_id"]
    ):
        await call.answer(
            "Ты не участник этого боя.",
            show_alert=True
        )
        return

    winner_id = pvp_opponent(
        match,
        user_id
    )

    if winner_id is None:
        await call.answer(
            "Ошибка соперника.",
            show_alert=True
        )
        return

    # ========================================================
    # ЗАВЕРШАЕМ БОЙ
    # ========================================================

    db_execute("""
        UPDATE pvp_matches
        SET
            status='finished',
            winner_id=?,
            finished_at=?
        WHERE id=?
          AND status='active'
    """, (
        winner_id,
        now_iso(),
        match_id
    ))

    # Проверяем, действительно ли матч завершился
    updated_match = pvp_get_match(match_id)

    if not updated_match:
        await call.answer(
            "Ошибка матча.",
            show_alert=True
        )
        return

    if updated_match["status"] != "finished":
        await call.answer(
            "Бой уже завершён.",
            show_alert=True
        )
        return

    if int(updated_match["winner_id"]) != int(winner_id):
        await call.answer(
            "Бой уже завершён.",
            show_alert=True
        )
        return

    # ========================================================
    # ОТМЕНЯЕМ ТАЙМЕР
    # ========================================================

    task = pvp_turn_tasks.pop(
        match_id,
        None
    )

    if task:
        task.cancel()

    # ========================================================
    # СООБЩЕНИЯ
    # ========================================================

    await call.answer(
        "🏳️ Ты сдался."
    )

    try:
        await call.bot.send_message(
            user_id,
            "🏳️ <b>ТЫ СДАЛСЯ</b>\n\n"
            "💀 Тебе засчитано поражение."
        )
    except Exception:
        log.exception(
            "Failed to send surrender message"
        )

    try:
        await call.bot.send_message(
            winner_id,
            "🏆 <b>ПОБЕДА!</b>\n\n"
            "🏳️ Соперник сдался.\n"
            "Тебе засчитана победа."
        )
    except Exception:
        log.exception(
            "Failed to send surrender winner message"
        )

    # ========================================================
    # НАГРАДЫ / СТАТИСТИКА / MMR
    # ========================================================

    await pvp_finish_match(
        bot=call.bot,
        match_id=match_id,
        winner_id=winner_id
    )

# ============================================================
# PVP FINISH
# ============================================================

# ============================================================
# PVP FINISH
# ============================================================

async def pvp_finish_match(
    bot: Bot,
    match_id: int,
    winner_id: int
):
    match = pvp_get_match(match_id)

    if not match:
        return

    # Матч должен быть завершён
    if match["status"] != "finished":
        return

    player1_id = int(match["player1_id"])
    player2_id = int(match["player2_id"])
    pvp_ability_uses.pop((match_id, player1_id), None)
    pvp_ability_uses.pop((match_id, player2_id), None)
    db_execute("DELETE FROM pvp_effects WHERE match_id=?", (match_id,))
    task = pvp_effect_tasks.pop(match_id, None)
    if task: task.cancel()
    task = pvp_event_tasks.pop(match_id, None)
    if task: task.cancel()

    if winner_id not in (player1_id, player2_id):
        return

    # ========================================================
    # УДАЛЯЕМ СТАРЫЕ СООБЩЕНИЯ PVP
    # ========================================================

    player1_message_id = match["player1_message_id"]
    player2_message_id = match["player2_message_id"]

    for user_id, message_id in (
        (player1_id, player1_message_id),
        (player2_id, player2_message_id)
    ):
        if not message_id:
            continue

        try:
            await bot.delete_message(
                chat_id=user_id,
                message_id=int(message_id)
            )
        except Exception:
            log.warning(
                "Не удалось удалить PvP-сообщение: user_id=%s, message_id=%s",
                user_id,
                message_id
            )

    loser_id = (
        player2_id
        if winner_id == player1_id
        else player1_id
    )

    winner_damage = (
        int(match["player1_damage"])
        if winner_id == player1_id
        else int(match["player2_damage"])
    )

    loser_damage = (
        int(match["player2_damage"])
        if winner_id == player1_id
        else int(match["player1_damage"])
    )

    ensure_pvp_stats(winner_id)
    ensure_pvp_stats(loser_id)

    # ========================================================
    # ОБЫЧНЫЙ БОЙ
    # ========================================================

    if match["mode"] == "unranked":

        db_execute("""
            UPDATE pvp_stats
            SET
                total_games = total_games + 1,
                total_wins = total_wins + 1,
                total_damage = total_damage + ?,
                current_streak = current_streak + 1,
                best_streak = CASE
                    WHEN current_streak + 1 > best_streak
                    THEN current_streak + 1
                    ELSE best_streak
                END
            WHERE user_id = ?
        """, (
            winner_damage,
            winner_id
        ))

        db_execute("""
            UPDATE pvp_stats
            SET
                total_games = total_games + 1,
                total_losses = total_losses + 1,
                total_damage = total_damage + ?,
                current_streak = 0
            WHERE user_id = ?
        """, (
            loser_damage,
            loser_id
        ))

        reward_dcr = 100
        reward_xp = 50

        # ВАЖНО:
        # wins/losses больше НЕ трогаем здесь.
        # Это статистика PvE.

        db_execute("""
            UPDATE players
            SET
                dcr = dcr + ?,
                xp = xp + ?
            WHERE user_id = ?
        """, (
            reward_dcr,
            reward_xp,
            winner_id
        ))

        try:
            await bot.send_message(
    winner_id,
    "🏆 <b>ПОБЕДА!</b>\n\n"
    f"💰 Награда: <b>+{reward_dcr} DCR</b>\n"
    f"⭐ XP: <b>+{reward_xp}</b>\n"
    f"💥 Урон: <b>{winner_damage}</b>",
    reply_markup=pvp_result_keyboard()
)
        except Exception:
            log.exception(
                "Failed to send unranked winner message"
            )

        try:
            await bot.send_message(
    loser_id,
    "💀 <b>ПОРАЖЕНИЕ</b>\n\n"
    f"💥 Урон: <b>{loser_damage}</b>\n\n"
    "Не сдавайся — следующий бой может быть твоим.",
    reply_markup=pvp_result_keyboard()
)
        except Exception:
            log.exception(
                "Failed to send unranked loser message"
            )

        return

    # ========================================================
    # РЕЙТИНГОВЫЙ БОЙ
    # ========================================================

    if match["mode"] != "ranked":
        return

    winner_stats = get_pvp_stats(winner_id)
    loser_stats = get_pvp_stats(loser_id)

    winner_mmr_before = int(winner_stats["mmr"])
    loser_mmr_before = int(loser_stats["mmr"])

    winner_calibration = (
        int(winner_stats["calibration_games"])
        < CALIBRATION_GAMES
    )

    loser_calibration = (
        int(loser_stats["calibration_games"])
        < CALIBRATION_GAMES
    )

    # MMR считаем на основании рейтинга ДО боя
    winner_delta = calculate_ranked_mmr_delta(
        winner_mmr_before,
        loser_mmr_before,
        True,
        winner_calibration
    )

    loser_delta = calculate_ranked_mmr_delta(
        loser_mmr_before,
        winner_mmr_before,
        False,
        loser_calibration
    )

    new_winner_mmr = max(
        0,
        winner_mmr_before + winner_delta
    )

    new_loser_mmr = max(
        0,
        loser_mmr_before + loser_delta
    )

    # ========================================================
    # ПОБЕДИТЕЛЬ
    # ========================================================

    db_execute("""
        UPDATE pvp_stats
        SET
            mmr = ?,
            ranked_games = ranked_games + 1,
            ranked_wins = ranked_wins + 1,
            calibration_games = calibration_games + ?,
            total_games = total_games + 1,
            total_wins = total_wins + 1,
            total_damage = total_damage + ?,
            current_streak = current_streak + 1,
            best_streak = CASE
                WHEN current_streak + 1 > best_streak
                THEN current_streak + 1
                ELSE best_streak
            END
        WHERE user_id = ?
    """, (
        new_winner_mmr,
        1 if winner_calibration else 0,
        winner_damage,
        winner_id
    ))

    # ========================================================
    # ПРОИГРАВШИЙ
    # ========================================================

    db_execute("""
        UPDATE pvp_stats
        SET
            mmr = ?,
            ranked_games = ranked_games + 1,
            ranked_losses = ranked_losses + 1,
            calibration_games = calibration_games + ?,
            total_games = total_games + 1,
            total_losses = total_losses + 1,
            total_damage = total_damage + ?,
            current_streak = 0
        WHERE user_id = ?
    """, (
        new_loser_mmr,
        1 if loser_calibration else 0,
        loser_damage,
        loser_id
    ))

    # ========================================================
    # НАГРАДА
    # ========================================================

    db_execute("""
        UPDATE players
        SET
            dcr = dcr + 100,
            xp = xp + 50
        WHERE user_id = ?
    """, (winner_id,))

    # ========================================================
    # КАЛИБРОВКА ЗАВЕРШЕНА
    # ========================================================

    winner_after = get_pvp_stats(winner_id)
    loser_after = get_pvp_stats(loser_id)

    if (
        winner_calibration
        and int(winner_after["calibration_games"])
        >= CALIBRATION_GAMES
    ):
        rank = pvp_rank_for_mmr(new_winner_mmr)

        try:
            await bot.send_message(
                winner_id,
                "🎉 <b>КАЛИБРОВКА ЗАВЕРШЕНА!</b>\n\n"
                f"🏆 Ранг: <b>{rank['emoji']} {rank['name']}</b>\n"
                f"📊 MMR: <b>{new_winner_mmr}</b>"
            )
        except Exception:
            log.exception(
                "Failed to send winner calibration message"
            )

    if (
        loser_calibration
        and int(loser_after["calibration_games"])
        >= CALIBRATION_GAMES
    ):
        rank = pvp_rank_for_mmr(new_loser_mmr)

        try:
            await bot.send_message(
                loser_id,
                "🎉 <b>КАЛИБРОВКА ЗАВЕРШЕНА!</b>\n\n"
                f"🏆 Ранг: <b>{rank['emoji']} {rank['name']}</b>\n"
                f"📊 MMR: <b>{new_loser_mmr}</b>"
            )
        except Exception:
            log.exception(
                "Failed to send loser calibration message"
            )

    # ========================================================
    # ИНФОРМАЦИЯ О РЕЗУЛЬТАТЕ
    # ========================================================

    try:
       await bot.send_message(
    winner_id,
    "🏆 <b>РЕЙТИНГОВАЯ ПОБЕДА!</b>\n\n"
    f"📈 MMR: <b>{winner_mmr_before} → {new_winner_mmr}</b>\n"
    f"⚡ Изменение: <b>+{winner_delta}</b>\n"
    f"💥 Урон: <b>{winner_damage}</b>",
    reply_markup=pvp_result_keyboard()
)
    except Exception:
        log.exception(
            "Failed to send ranked winner message"
        )

    try:
        await bot.send_message(
    loser_id,
    "💀 <b>РЕЙТИНГОВОЕ ПОРАЖЕНИЕ</b>\n\n"
    f"📉 MMR: <b>{loser_mmr_before} → {new_loser_mmr}</b>\n"
    f"⚡ Изменение: <b>{loser_delta}</b>\n"
    f"💥 Урон: <b>{loser_damage}</b>",
    reply_markup=pvp_result_keyboard()
)
    except Exception:
        log.exception(
            "Failed to send ranked loser message"
        )


# ============================================================
# PVP MATCHMAKING — UNRANKED
# ============================================================

def pvp_find_unranked_opponent(user_id: int):
    rows = db_execute("""
        SELECT user_id, mode, mmr, joined_at
        FROM pvp_queue
        WHERE mode='unranked'
        ORDER BY joined_at ASC
    """, fetchall=True)

    log.info(
        "PVP QUEUE: %s | ищем соперника для %s",
        [
            {
                "user_id": row["user_id"],
                "mode": row["mode"],
                "joined_at": row["joined_at"],
            }
            for row in rows
        ],
        user_id
    )

    for row in rows:
        if row["user_id"] != user_id:
            log.info(
                "PVP OPPONENT FOUND: %s -> %s",
                user_id,
                row["user_id"]
            )
            return row

    log.info(
        "PVP OPPONENT NOT FOUND for %s",
        user_id
    )

    return None

# ============================================================
# PVP MATCHMAKING — RANKED
# ============================================================

def pvp_find_ranked_opponent(user_id: int):
    stats = get_pvp_stats(user_id)

    player_mmr = int(
        stats["mmr"]
    )

    calibration_games = int(
        stats["calibration_games"]
    )

    calibration = (
        calibration_games < CALIBRATION_GAMES
    )

    direction = stats["calibration_direction"]

    rows = db_execute("""
        SELECT
            q.user_id,
            q.mode,
            q.mmr,
            q.joined_at
        FROM pvp_queue q
        WHERE q.mode='ranked'
          AND q.user_id != ?
        ORDER BY q.joined_at ASC
    """, (
        user_id,
    ), fetchall=True)

    candidates = []

    for row in rows:
        opponent_id = int(
            row["user_id"]
        )

        if pvp_active_match(opponent_id):
            pvp_remove_from_queue(
                opponent_id
            )
            continue

        opponent_stats = get_pvp_stats(
            opponent_id
        )

        opponent_mmr = int(
            opponent_stats["mmr"]
        )

        opponent_calibration = (
            int(
                opponent_stats["calibration_games"]
            )
            < CALIBRATION_GAMES
        )

        mmr_diff = abs(
            player_mmr - opponent_mmr
        )

        candidates.append({
            "row": row,
            "mmr": opponent_mmr,
            "diff": mmr_diff,
            "calibration": opponent_calibration
        })

    if not candidates:
        return None

    # --------------------------------------------------------
    # Во время калибровки стараемся учитывать направление.
    #
    # После победы ищем более сильного.
    # После поражения — более слабого.
    # --------------------------------------------------------

    preferred = []

    if calibration:

        if direction == "stronger":
            preferred = [
                candidate
                for candidate in candidates
                if candidate["mmr"] > player_mmr
            ]

        elif direction == "weaker":
            preferred = [
                candidate
                for candidate in candidates
                if candidate["mmr"] < player_mmr
            ]

    if preferred:
        preferred.sort(
            key=lambda candidate: (
                candidate["diff"],
                candidate["row"]["joined_at"]
            )
        )

        return preferred[0]["row"]

    # --------------------------------------------------------
    # Если подходящего соперника нет —
    # берём ближайшего по MMR.
    # --------------------------------------------------------

    candidates.sort(
        key=lambda candidate: (
            candidate["diff"],
            candidate["row"]["joined_at"]
        )
    )

    opponent = candidates[0]["row"]

    log.info(
        "RANKED OPPONENT FOUND: %s -> %s | MMR %s vs %s",
        user_id,
        opponent["user_id"],
        player_mmr,
        opponent["mmr"]
    )

    return opponent


# ============================================================
# PVP MATCHMAKING — ALL MODES
# ============================================================

async def pvp_matchmaking_loop(bot: Bot):

    while True:

        try:

            # =================================================
            # RANKED
            # =================================================

            ranked_rows = db_execute("""
                SELECT *
                FROM pvp_queue
                WHERE mode='ranked'
                ORDER BY joined_at ASC
            """, fetchall=True)

            ranked_used = set()

            for row in ranked_rows:

                player1_id = int(
                    row["user_id"]
                )

                if player1_id in ranked_used:
                    continue

                # Игрок уже в бою
                if pvp_active_match(player1_id):

                    pvp_remove_from_queue(
                        player1_id
                    )

                    continue

                opponent = pvp_find_ranked_opponent(
                    player1_id
                )

                if not opponent:
                    continue

                player2_id = int(
                    opponent["user_id"]
                )

                if player2_id in ranked_used:
                    continue

                if pvp_active_match(player2_id):

                    pvp_remove_from_queue(
                        player2_id
                    )

                    continue

                ranked_used.add(
                    player1_id
                )

                ranked_used.add(
                    player2_id
                )

                log.info(
                    "RANKED MATCH FOUND: %s vs %s",
                    player1_id,
                    player2_id
                )

                await pvp_start_match(
                    bot,
                    player1_id,
                    player2_id,
                    "ranked"
                )

            # =================================================
            # UNRANKED
            # =================================================

            unranked_rows = db_execute("""
                SELECT *
                FROM pvp_queue
                WHERE mode='unranked'
                ORDER BY joined_at ASC
            """, fetchall=True)

            unranked_used = set()

            for row in unranked_rows:

                player1_id = int(
                    row["user_id"]
                )

                if player1_id in unranked_used:
                    continue

                if pvp_active_match(player1_id):

                    pvp_remove_from_queue(
                        player1_id
                    )

                    continue

                opponent = pvp_find_unranked_opponent(
                    player1_id
                )

                if not opponent:
                    continue

                player2_id = int(
                    opponent["user_id"]
                )

                if player2_id in unranked_used:
                    continue

                if pvp_active_match(player2_id):

                    pvp_remove_from_queue(
                        player2_id
                    )

                    continue

                unranked_used.add(
                    player1_id
                )

                unranked_used.add(
                    player2_id
                )

                log.info(
                    "UNRANKED MATCH FOUND: %s vs %s",
                    player1_id,
                    player2_id
                )

                await pvp_start_match(
                    bot,
                    player1_id,
                    player2_id,
                    "unranked"
                )

        except Exception:
            log.exception(
                "PvP matchmaking error"
            )

        await asyncio.sleep(2)
        
# ============================================================
# OTHER: TRANSFERS / CLANS / QUESTS / MARKET / ADMIN
# ============================================================

@dp.callback_query(F.data == "other")
async def other_callback(call: CallbackQuery):
    await call.answer()

    await safe_edit(
        call.message,
        "📂 <b>ПРОЧЕЕ</b>\n\nВыбери нужный раздел:",
        other_menu(call.from_user.id)
    )


def other_menu(user_id=None):
    rows = [
        [InlineKeyboardButton(text="🏰 Кланы", callback_data="clans"), InlineKeyboardButton(text="📜 Квесты", callback_data="quests")],
        [InlineKeyboardButton(text="📖 Бестиарий", callback_data="bestiary"), InlineKeyboardButton(text="🎫 Battle Pass", callback_data="bp")],
        [InlineKeyboardButton(text="🛒 Живой рынок", callback_data="market"), InlineKeyboardButton(text="💸 Перевод DCR", callback_data="transfer")],
        [InlineKeyboardButton(text="🤝 Друзья", callback_data="friends"), InlineKeyboardButton(text="🏆 Рейтинг", callback_data="rating")],
        [InlineKeyboardButton(text="🟢 Онлайн", callback_data="online"), InlineKeyboardButton(text="👥 Сообщество", callback_data="community")],
        [InlineKeyboardButton(text="🔨 Крафт", callback_data="craft"), InlineKeyboardButton(text="⬆️ Улучшение", callback_data="upgrade")],
        [InlineKeyboardButton(text="🎰 Казино", callback_data="casino")],
    ]
    if user_id is not None and is_admin(user_id):
        rows.append([InlineKeyboardButton(text="👑 Админ-панель", callback_data="admin")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def transfer_menu_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Выбрать игрока",callback_data="transfer_players")],
        [InlineKeyboardButton(text="⬅️ Назад",callback_data="other")],
    ])

@dp.callback_query(F.data == "transfer")
async def transfer_callback(
    call: CallbackQuery,
    state: FSMContext
):
    await call.answer()
    await state.clear()

    await safe_edit(
        call.message,
        "💸 <b>ПЕРЕВОД DCR</b>\n\n"
        "Выбери игрока, которому хочешь отправить DCR.",
        transfer_menu_keyboard()
    )


@dp.callback_query(F.data == "transfer_players")
async def transfer_players_callback(
    call: CallbackQuery,
    state: FSMContext
):
    await call.answer()
    await state.clear()

    players = db_execute(
        """
        SELECT user_id, username, first_name
        FROM players
        WHERE user_id != ?
        ORDER BY first_name COLLATE NOCASE, username COLLATE NOCASE
        LIMIT 50
        """,
        (call.from_user.id,),
        fetchall=True
    )

    if not players:
        await safe_edit(
            call.message,
            "👥 <b>ИГРОКИ</b>\n\n"
            "❌ Пока нет других игроков.",
            transfer_menu_keyboard()
        )
        return

    buttons = []

    for player in players:
        user_id = player["user_id"]
        username = player["username"]
        first_name = player["first_name"]

        name = first_name or username or str(user_id)

        if username:
            button_text = f"👤 {name} (@{username})"
        else:
            button_text = f"👤 {name}"

        buttons.append([
            InlineKeyboardButton(
                text=button_text[:60],
                callback_data=f"transfer_user:{user_id}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data="transfer"
        )
    ])

    await safe_edit(
        call.message,
        "👥 <b>ВЫБЕРИ ИГРОКА</b>\n\n"
        "Кому отправить DCR?",
        InlineKeyboardMarkup(
            inline_keyboard=buttons
        )
    )


@dp.callback_query(F.data.startswith("transfer_user:"))
async def transfer_user_callback(
    call: CallbackQuery,
    state: FSMContext
):
    await call.answer()

    try:
        target_id = int(call.data.split(":")[1])
    except (ValueError, IndexError):
        await call.message.answer(
            "❌ Ошибка выбора игрока."
        )
        return

    if target_id == call.from_user.id:
        await call.answer(
            "❌ Нельзя переводить DCR самому себе.",
            show_alert=True
        )
        return

    player = db_execute(
        """
        SELECT user_id, username, first_name
        FROM players
        WHERE user_id = ?
        """,
        (target_id,),
        fetchone=True
    )

    if not player:
        await call.answer(
            "❌ Игрок не найден.",
            show_alert=True
        )
        return

    name = (
        player["first_name"]
        or player["username"]
        or str(target_id)
    )

    sender = db_execute(
        """
        SELECT dcr
        FROM players
        WHERE user_id = ?
        """,
        (call.from_user.id,),
        fetchone=True
    )

    if not sender:
        await call.answer(
            "❌ Твой профиль не найден.",
            show_alert=True
        )
        return

    balance = sender["dcr"] or 0

    await state.update_data(
        target_id=target_id,
        target_name=name,
        screen_chat_id=call.message.chat.id,
        screen_message_id=call.message.message_id
    )

    await state.set_state(
        TransferState.waiting_amount
    )

    await safe_edit(
        call.message,
        "💸 <b>СУММА ПЕРЕВОДА</b>\n\n"
        f"👤 Получатель: <b>{html.escape(name)}</b>\n"
        f"💰 Твой баланс: <b>{balance:,} DCR</b>\n\n"
        "✏️ Введи количество DCR:"
    )

class TransferState(StatesGroup):
    waiting_target = State()
    waiting_amount = State()
    confirming = State()

@dp.message(TransferState.waiting_amount)
async def transfer_amount_message(
    message: Message,
    state: FSMContext
):
    text = (message.text or "").strip().replace(" ", "")
    try:
        amount = int(text)
    except ValueError:
        try:
            await message.delete()
        except Exception:
            pass
        return

    try:
        await message.delete()
    except Exception:
        pass

    if amount <= 0:
        return

    data = await state.get_data()
    target_id = data.get("target_id")
    target_name = data.get("target_name", "Игрок")
    if not target_id:
        await state.clear()
        return

    sender = db_execute(
        "SELECT dcr FROM players WHERE user_id = ?",
        (message.from_user.id,),
        fetchone=True
    )
    if not sender:
        await state.clear()
        return

    balance = int(sender["dcr"] or 0)
    if amount > balance:
        chat_id = data.get("screen_chat_id")
        msg_id = data.get("screen_message_id")
        if chat_id and msg_id:
            try:
                await message.bot.edit_message_text(
                    chat_id=chat_id, message_id=msg_id,
                    text=f"❌ <b>Недостаточно DCR.</b>\n\nТвой баланс: <b>{balance:,} DCR</b>",
                    reply_markup=transfer_menu_keyboard()
                )
            except Exception:
                pass
        return

    await state.update_data(amount=amount)
    await state.set_state(TransferState.confirming)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data="transfer_confirm")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="transfer_cancel")]
    ])
    text = (
        "⚠️ <b>ПОДТВЕРДИТЬ ПЕРЕВОД?</b>\n\n"
        f"👤 Получатель: <b>{html.escape(str(target_name))}</b>\n"
        f"💰 Сумма: <b>{amount:,} DCR</b>\n\n"
        "Проверь данные перед подтверждением."
    )
    chat_id = data.get("screen_chat_id")
    msg_id = data.get("screen_message_id")
    if chat_id and msg_id:
        try:
            await message.bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=text, reply_markup=keyboard)
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=keyboard)


@dp.callback_query(F.data == "transfer_cancel")
async def transfer_cancel_callback(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer("Перевод отменён.")
    await safe_edit(call.message, "❌ <b>ПЕРЕВОД ОТМЕНЁН</b>", transfer_menu_keyboard())

@dp.callback_query(F.data == "transfer_confirm")
async def transfer_confirm_callback(
    call: CallbackQuery,
    state: FSMContext
):
    await call.answer("Заявка отправляется...")

    data = await state.get_data()

    target_id = data.get("target_id")
    target_name = data.get("target_name")
    amount = data.get("amount")

    if not target_id or not amount:
        await state.clear()
        await safe_edit(
            call.message,
            "❌ Данные перевода потеряны.\n"
            "Попробуй начать перевод заново.",
            transfer_menu_keyboard()
        )
        return

    sender = db_execute(
        "SELECT user_id, dcr FROM players WHERE user_id = ?",
        (call.from_user.id,),
        fetchone=True
    )

    if not sender:
        await state.clear()
        await safe_edit(
            call.message,
            "❌ Твой профиль не найден.",
            transfer_menu_keyboard()
        )
        return

    balance = sender["dcr"] or 0

    if amount > balance:
        await state.clear()
        await safe_edit(
            call.message,
            f"❌ Недостаточно DCR.\n\n"
            f"Твой баланс: <b>{balance:,} DCR</b>",
            transfer_menu_keyboard()
        )
        return

    # Создаём заявку
    # Создаём заявку
    request_id = db_insert(
        """
        INSERT INTO transfer_requests
        (sender_id, receiver_id, amount, status)
        VALUES (?, ?, ?, 'pending')
        """,
        (
            call.from_user.id,
            target_id,
            amount
        )
    )

    await state.clear()

    await safe_edit(
        call.message,
        "✅ <b>Заявка на перевод отправлена!</b>\n\n"
        f"👤 Получатель: <b>{html.escape(str(target_name))}</b>\n"
        f"💰 Сумма: <b>{amount:,} DCR</b>\n\n"
        "Ожидаем подтверждения получателя.",
        transfer_menu_keyboard()
    )

    # Кнопки для получателя
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Получить",
                    callback_data=f"transfer_accept:{request_id}"
                ),
                InlineKeyboardButton(
                    text="❌ Отказать",
                    callback_data=f"transfer_decline:{request_id}"
                )
            ]
        ]
    )

    await call.bot.send_message(
        target_id,
        "💸 <b>ВХОДЯЩИЙ ПЕРЕВОД</b>\n\n"
        f"👤 Отправитель: "
        f"<b>{html.escape(call.from_user.full_name)}</b>\n"
        f"💰 Сумма: <b>{amount:,} DCR</b>\n\n"
        "Ты хочешь получить этот перевод?",
        reply_markup=keyboard
    )


# ============================================================
# ПРИНЯТЬ ПЕРЕВОД
# ============================================================

@dp.callback_query(F.data.startswith("transfer_accept:"))
async def transfer_accept_callback(call: CallbackQuery):
    try:
        request_id = int(call.data.split(":")[1])
    except (ValueError, IndexError):
        await call.answer("❌ Ошибка заявки.", show_alert=True)
        return

    request = db_execute(
        """
        SELECT id, sender_id, receiver_id, amount, status
        FROM transfer_requests
        WHERE id = ?
        """,
        (request_id,),
        fetchone=True
    )

    if not request:
        await call.answer("❌ Заявка не найдена.", show_alert=True)
        return

    if request["receiver_id"] != call.from_user.id:
        await call.answer(
            "❌ Эта заявка предназначена не тебе.",
            show_alert=True
        )
        return

    if request["status"] != "pending":
        await call.answer(
            "❌ Эта заявка уже обработана.",
            show_alert=True
        )
        return

    sender_id = request["sender_id"]
    receiver_id = request["receiver_id"]
    amount = request["amount"]

    # Атомарно обрабатываем перевод
    with db_connection() as con:

        # Сначала пытаемся "забрать" заявку себе.
        # Это защищает от двойного нажатия на кнопку.
        cur = con.execute(
            """
            UPDATE transfer_requests
            SET status = 'processing'
            WHERE id = ?
              AND receiver_id = ?
              AND status = 'pending'
            """,
            (
                request_id,
                receiver_id
            )
        )

        if cur.rowcount != 1:
            await call.answer(
                "❌ Заявка уже обработана.",
                show_alert=True
            )
            return

        # Снимаем DCR у отправителя
        cur = con.execute(
            """
            UPDATE players
            SET dcr = dcr - ?
            WHERE user_id = ?
              AND dcr >= ?
            """,
            (
                amount,
                sender_id,
                amount
            )
        )

        if cur.rowcount != 1:
            con.execute(
                """
                UPDATE transfer_requests
                SET status = 'cancelled'
                WHERE id = ?
                """,
                (request_id,)
            )

            await call.answer(
                "❌ У отправителя недостаточно DCR.",
                show_alert=True
            )

            await safe_edit(
                call.message,
                "❌ <b>ПЕРЕВОД ОТМЕНЁН</b>\n\n"
                "У отправителя недостаточно DCR."
            )
            return

        # Начисляем получателю
        cur = con.execute(
            """
            UPDATE players
            SET dcr = dcr + ?
            WHERE user_id = ?
            """,
            (
                amount,
                receiver_id
            )
        )

        if cur.rowcount != 1:
            # Теоретически получатель мог быть удалён
            raise RuntimeError(
                "Получатель не найден при зачислении DCR"
            )

        # Завершаем заявку
        con.execute(
            """
            UPDATE transfer_requests
            SET status = 'accepted'
            WHERE id = ?
              AND status = 'processing'
            """,
            (request_id,)
        )

    await call.answer("Перевод получен ✅")

    # Убираем кнопки
    await safe_edit(
        call.message,
        "✅ <b>ПЕРЕВОД ПОЛУЧЕН</b>\n\n"
        f"💰 Тебе переведено: <b>{amount:,} DCR</b>"
    )

    # Уведомляем отправителя
    try:
        await call.bot.send_message(
            sender_id,
            "✅ <b>ПЕРЕВОД ПРИНЯТ</b>\n\n"
            f"👤 Получатель: "
            f"<b>{html.escape(call.from_user.full_name)}</b>\n"
            f"💰 Сумма: <b>{amount:,} DCR</b>\n\n"
            "Игрок принял перевод."
        )
    except Exception as e:
        logging.warning(
            "Не удалось отправить уведомление: %s",
            e
        )


# ============================================================
# ОТКЛОНИТЬ ПЕРЕВОД
# ============================================================

@dp.callback_query(F.data.startswith("transfer_decline:"))
async def transfer_decline_callback(call: CallbackQuery):
    try:
        request_id = int(call.data.split(":")[1])
    except (ValueError, IndexError):
        await call.answer("❌ Ошибка заявки.", show_alert=True)
        return

    request = db_execute(
        """
        SELECT sender_id, receiver_id, amount, status
        FROM transfer_requests
        WHERE id = ?
        """,
        (request_id,),
        fetchone=True
    )

    if not request:
        await call.answer(
            "❌ Заявка не найдена.",
            show_alert=True
        )
        return

    if request["receiver_id"] != call.from_user.id:
        await call.answer(
            "❌ Эта заявка не для тебя.",
            show_alert=True
        )
        return

    if request["status"] != "pending":
        await call.answer(
            "❌ Заявка уже обработана.",
            show_alert=True
        )
        return

    # Отклоняем заявку
    cur = db_execute(
        """
        UPDATE transfer_requests
        SET status = 'declined'
        WHERE id = ?
          AND receiver_id = ?
          AND status = 'pending'
        """,
        (
            request_id,
            call.from_user.id
        )
    )

    await call.answer("Перевод отклонён ❌")

    # Убираем кнопки
    await safe_edit(
        call.message,
        "❌ <b>ПЕРЕВОД ОТКЛОНЁН</b>\n\n"
        f"💰 Сумма: <b>{request['amount']:,} DCR</b>"
    )

    # Уведомляем отправителя
    try:
        await call.bot.send_message(
            request["sender_id"],
            "❌ <b>ПЕРЕВОД ОТКЛОНЁН</b>\n\n"
            f"👤 Получатель: "
            f"<b>{html.escape(call.from_user.full_name)}</b>\n"
            f"💰 Сумма: <b>{request['amount']:,} DCR</b>\n\n"
            "Получатель отказался от перевода."
        )
    except Exception as e:
        logging.warning(
            "Не удалось отправить уведомление: %s",
            e
        )


# ============================================================
# 👥 СООБЩЕСТВО
# ============================================================

@dp.callback_query(F.data == "community")
async def community_callback(call: CallbackQuery):
    await call.answer()

    await safe_edit(
        call.message,
        "👥 <b>СООБЩЕСТВО DOMINION</b>\n\n"
        "📢 <b>Канал</b> — новости и обновления.\n"
        "💬 <b>Чат</b> — общение с игроками.\n"
        "🛠 <b>Администрация</b> — помощь и сообщения о проблемах.",
        community_menu()
    )

# ============================================================
# COMMUNITY / SUPPORT
# ============================================================

def community_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📢 Канал DOMINION",
                url=NEWS_CHANNEL_URL
            )
        ],
        [
            InlineKeyboardButton(
                text="💬 Чат сообщества",
                url=COMMUNITY_CHAT_URL
            )
        ],
        [
            InlineKeyboardButton(
                text="🛠 Связь с администрацией",
                callback_data="contact_admin"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data="other"
            )
        ],
    ])




@dp.callback_query(F.data == "contact_admin")
async def contact_admin_callback(call: CallbackQuery):
    await call.answer()


    await call.message.answer(
    "🛠 <b>СВЯЗЬ С АДМИНИСТРАЦИЕЙ</b>\n\n"
    "Напиши одним сообщением, что случилось, "
    "и оно будет отправлено администрации.\n\n"
    "Например:\n"
    "🐛 Ошибка или баг\n"
    "💰 Проблема с покупкой\n"
    "❓ Вопрос по игре\n"
    "🚨 Жалоба на игрока"
)






@dp.callback_query(F.data == "transfer_help")
async def transfer_help(call: CallbackQuery):
    await call.answer()
    await safe_edit(
        call.message,
        "💸 <b>Переводы</b>\n\n"
        "Команда:\n"
        "<code>/pay ID СУММА</code>\n\n"
        f"Лимит отправителя в сутки: <b>{fmt(DAILY_TRANSFER_LIMIT)} DCR</b>.",
        back_menu()
    )


@dp.message(Command("pay"))
async def pay_command(message: Message):
    ensure_player(message.from_user)
    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("Использование: <code>/pay USER_ID AMOUNT</code>")
        return

    try:
        receiver = int(parts[1])
        amount = int(parts[2])
    except ValueError:
        await message.answer("ID и сумма должны быть числами.")
        return

    if receiver == message.from_user.id or amount <= 0:
        await message.answer("Некорректный перевод.")
        return

    sender = get_player(message.from_user.id)
    target = get_player(receiver)
    if not target:
        await message.answer("Получатель не найден.")
        return
    if sender["blocked"] or target["blocked"]:
        await message.answer("Перевод невозможен.")
        return

    day = today_key()
    row = db_execute("""
    SELECT amount FROM transfer_daily WHERE user_id=? AND day=?
    """, (message.from_user.id, day), fetchone=True)
    sent_today = row["amount"] if row else 0

    if sent_today + amount > DAILY_TRANSFER_LIMIT:
        await message.answer("Превышен дневной лимит переводов.")
        return
    if sender["dcr"] < amount:
        await message.answer("Недостаточно DCR.")
        return

    add_dcr(message.from_user.id, -amount, f"Перевод {receiver}")
    add_dcr(receiver, amount, f"Получение от {message.from_user.id}")

    db_execute("""
    INSERT INTO transfers(sender_id,receiver_id,amount,created_at)
    VALUES(?,?,?,?)
    """, (message.from_user.id, receiver, amount, now_iso()))

    db_execute("""
    INSERT INTO transfer_daily(user_id,day,amount) VALUES(?,?,?)
    ON CONFLICT(user_id,day) DO UPDATE SET amount=amount+excluded.amount
    """, (message.from_user.id, day, amount))

    await message.answer(f"✅ Переведено <b>{fmt(amount)} DCR</b> пользователю <code>{receiver}</code>.")


@dp.callback_query(F.data == "rating")
async def rating_callback(call: CallbackQuery):
    rows = db_execute("""
    SELECT user_id,username,first_name,level,dcr,pvp_rating
    FROM players WHERE blocked=0
    ORDER BY level DESC,pvp_rating DESC,dcr DESC LIMIT 10
    """, fetchall=True)
    text = "🏆 <b>РЕЙТИНГ DOMINION</b>\n\n"
    for i, row in enumerate(rows, 1):
        name = row["first_name"] or row["username"] or str(row["user_id"])
        text += f"{i}. {esc(name)} — Lv.{row['level']} • PvP {row['pvp_rating']}\n"
    await call.answer()
    await safe_edit(call.message, text, back_menu())


@dp.callback_query(F.data == "bestiary")
async def bestiary_callback(call: CallbackQuery):
    text = "📖 <b>БЕСТИАРИЙ</b>\n\n"
    for loc in LOCATIONS.values():
        for e in loc["enemies"]:
            text += f"👹 {e[1]} — ❤️ {e[2]} — ⚔️ {e[3]}-{e[4]}\n"
    await call.answer()
    await safe_edit(call.message, text, back_menu())


# ---------------- CLANS ----------------

class ClanCreateState(StatesGroup):
    waiting_name = State()

class ClanActionState(StatesGroup):
    waiting_user = State()
    waiting_amount = State()
    waiting_announcement = State()


def clan_role(user_id, clan_id):
    row = db_execute("SELECT role FROM clan_members WHERE clan_id=? AND user_id=?", (clan_id,user_id), fetchone=True)
    return row["role"] if row else None

def clan_can_manage(user_id, clan_id):
    return clan_role(user_id, clan_id) in ("leader","deputy","admin")

def clan_can_manage_leadership(user_id, clan_id):
    return clan_role(user_id, clan_id) == "leader"

def clan_display_name(row):
    return row["first_name"] or ("@" + row["username"] if row["username"] else str(row["user_id"]))

def clan_info(clan_id):
    return db_execute("SELECT * FROM clans WHERE clan_id=?", (clan_id,), fetchone=True)

def clan_members(clan_id):
    return db_execute("""
        SELECT p.user_id,p.username,p.first_name,p.level,p.pvp_rating,cm.role
        FROM clan_members cm JOIN players p ON p.user_id=cm.user_id
        WHERE cm.clan_id=?
        ORDER BY CASE cm.role WHEN 'leader' THEN 0 WHEN 'deputy' THEN 1 WHEN 'admin' THEN 2 WHEN 'officer' THEN 3 ELSE 4 END,p.level DESC
    """, (clan_id,), fetchall=True)

def clan_power(clan_id):
    return sum(max(1,int(m["level"]))*100 + max(0,int(m["pvp_rating"])-1000) for m in clan_members(clan_id))

def clan_menu(user_id):
    p=get_player(user_id)
    if not p or not p["clan_id"]:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏰 Создать клан",callback_data="clan_create")],
            [InlineKeyboardButton(text="🔎 Найти клан",callback_data="clan_find")],
            [InlineKeyboardButton(text="⚔️ Турнир",callback_data="clan_tournament")],
            [InlineKeyboardButton(text="⬅️ Назад",callback_data="other")]
        ])
    ensure_clan_progress(p["clan_id"])
    rows=[
        [InlineKeyboardButton(text="👥 Участники",callback_data="clan_members"),InlineKeyboardButton(text="📋 Мой клан",callback_data="clan_info")],
        [InlineKeyboardButton(text="⚔️ Клановые бои",callback_data="clan_war"),InlineKeyboardButton(text="🏆 Турнир",callback_data="clan_tournament")],
        [InlineKeyboardButton(text="📊 Мощность",callback_data="clan_power"),InlineKeyboardButton(text="🏗️ Развитие",callback_data="clan_upgrade")],
        [InlineKeyboardButton(text="🏦 Казна",callback_data="clan_treasury"),InlineKeyboardButton(text="📜 История",callback_data="clan_history")],
        [InlineKeyboardButton(text="📢 Объявления",callback_data="clan_announcements")]
    ]
    role=clan_role(user_id,p["clan_id"])
    if role in ("leader","deputy","admin"):
        rows.append([InlineKeyboardButton(text="⚙️ Управление кланом",callback_data="clan_admin")])
    rows += [
        [InlineKeyboardButton(text="🚪 Выйти из клана",callback_data="clan_leave")],
        [InlineKeyboardButton(text="⬅️ Назад",callback_data="other")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

def clan_admin_menu(user_id):
    p=get_player(user_id); role=clan_role(user_id,p["clan_id"]) if p and p["clan_id"] else None
    rows=[]
    if role in ("leader","deputy","admin"):
        rows += [[InlineKeyboardButton(text="➕ Пригласить игрока",callback_data="clan_invite")],
                 [InlineKeyboardButton(text="📩 Заявки",callback_data="clan_requests")],
                 [InlineKeyboardButton(text="📢 Создать объявление",callback_data="clan_announce_create")]]
    if role in ("leader","deputy"):
        rows += [[InlineKeyboardButton(text="👥 Управление участниками",callback_data="clan_manage_members")],
                 [InlineKeyboardButton(text="🏗️ Управление развитием",callback_data="clan_upgrade")]]
    if role == "leader":
        rows += [[InlineKeyboardButton(text="🔐 Роли и права",callback_data="clan_roles")],
                 [InlineKeyboardButton(text="🗑️ Расформировать клан",callback_data="clan_disband")]]
    rows += [[InlineKeyboardButton(text="⬅️ Назад",callback_data="clans")]]
    return InlineKeyboardMarkup(inline_keyboard=rows)

@dp.callback_query(F.data == "clans")
async def clans_callback(call: CallbackQuery):
    p=get_player(call.from_user.id)
    if not p or not p["clan_id"]:
        text="🏰 <b>КЛАНЫ</b>\n\nСоздай свой клан или участвуй в ежемесячном турнире 5×5."
    else:
        c=clan_info(p["clan_id"])
        prog=ensure_clan_progress(p["clan_id"])
        text=(f"🏰 <b>{esc(c['name'])}</b>\n\n👥 Участников: {len(clan_members(p['clan_id']))}\n"
              f"⚡ Мощность: {fmt(clan_power(p['clan_id']))}\n🏰 Уровень клана: <b>{prog['level']}</b>\n🏯 Штаб: <b>{prog['headquarters_level']}</b>")
    await call.answer(); await safe_edit(call.message,text,clan_menu(call.from_user.id))

@dp.callback_query(F.data == "clan_find")
async def clan_find_callback(call: CallbackQuery):
    rows=db_execute("SELECT c.clan_id,c.name,c.leader_id,COUNT(cm.user_id) members FROM clans c LEFT JOIN clan_members cm ON cm.clan_id=c.clan_id GROUP BY c.clan_id ORDER BY members DESC LIMIT 20",fetchall=True)
    kb=[]; text="🔎 <b>ПОИСК КЛАНА</b>\n\n"
    for r in rows:
        text+=f"🏰 <b>{esc(r['name'])}</b> — 👥 {r['members']}\n"
        kb.append([InlineKeyboardButton(text=f"📩 Подать заявку: {r['name']}",callback_data=f"clan_apply:{r['clan_id']}")])
    if not rows: text+="Кланов пока нет."
    kb.append([InlineKeyboardButton(text="⬅️ Назад",callback_data="clans")]); await call.answer(); await safe_edit(call.message,text,InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("clan_apply:"))
async def clan_apply_callback(call: CallbackQuery):
    p=get_player(call.from_user.id); cid=int(call.data.split(":")[1])
    if not p or p["clan_id"]: await call.answer("Ты уже состоишь в клане.",show_alert=True); return
    c=clan_info(cid)
    if not c: await call.answer("Клан не найден.",show_alert=True); return
    db_execute("INSERT OR REPLACE INTO clan_join_requests(clan_id,user_id,status,created_at) VALUES(?,?,?,?)",(cid,p["user_id"],"pending",now_iso()))
    await call.answer("Заявка отправлена!",show_alert=True)

@dp.callback_query(F.data == "clan_create")
async def clan_create_callback(call: CallbackQuery, state: FSMContext):
    p=get_player(call.from_user.id)
    if p and p["clan_id"]: await call.answer("Ты уже в клане.",show_alert=True); return
    if not p or int(p["crystals"] or 0)<500: await call.answer("Нужно 500 💎.",show_alert=True); return
    await state.set_state(ClanCreateState.waiting_name)
    await call.answer(); await call.message.answer("🏰 Введи название клана (3–24 символа):")

@dp.message(ClanCreateState.waiting_name)
async def clan_create_name(message: Message, state: FSMContext):
    p=ensure_player(message.from_user); name=(message.text or "").strip()
    if p["clan_id"]: await state.clear(); return
    if not 3<=len(name)<=24: await message.answer("❌ Название должно быть от 3 до 24 символов."); return
    if int(p["crystals"] or 0)<500: await state.clear(); await message.answer("❌ Нужно 500 💎."); return
    try: clan_id=db_insert("INSERT INTO clans(name,leader_id,created_at) VALUES(?,?,?)",(name,message.from_user.id,now_iso()))
    except sqlite3.IntegrityError: await message.answer("❌ Такое название уже занято."); return
    add_crystals(message.from_user.id,-500,"Создание клана")
    db_execute("INSERT INTO clan_members(clan_id,user_id,role) VALUES(?,?,?)",(clan_id,message.from_user.id,"leader"))
    db_execute("UPDATE players SET clan_id=? WHERE user_id=?",(clan_id,message.from_user.id)); ensure_clan_progress(clan_id); await state.clear()
    await message.answer(f"🏰 Клан <b>{esc(name)}</b> создан!",reply_markup=clan_menu(message.from_user.id))

@dp.callback_query(F.data == "clan_info")
async def clan_info_callback(call: CallbackQuery):
    p=get_player(call.from_user.id)
    if not p or not p["clan_id"]: await call.answer("Ты не состоишь в клане.",show_alert=True); return
    c=clan_info(p["clan_id"]); prog=ensure_clan_progress(p["clan_id"])
    await call.answer(); await safe_edit(call.message,f"🏰 <b>{esc(c['name'])}</b>\n\n👑 Глава: <code>{c['leader_id']}</code>\n👥 Участников: {len(clan_members(p['clan_id']))}\n⚡ Мощность: <b>{fmt(clan_power(p['clan_id']))}</b>\n🏰 Уровень: {prog['level']}\n🏯 Штаб: {prog['headquarters_level']}",clan_menu(call.from_user.id))

@dp.callback_query(F.data == "clan_members")
async def clan_members_callback(call: CallbackQuery):
    p=get_player(call.from_user.id)
    if not p or not p["clan_id"]: await call.answer("Нет клана.",show_alert=True); return
    rows=clan_members(p["clan_id"]); kb=[]
    text="👥 <b>УЧАСТНИКИ КЛАНА</b>\n\n"
    for r in rows:
        text+=f"• {esc(clan_display_name(r))} — <b>{esc(r['role'])}</b> — Lv.{r['level']}\n"
        if clan_can_manage(call.from_user.id,p["clan_id"]) and r["user_id"]!=call.from_user.id:
            kb.append([InlineKeyboardButton(text=f"⚙️ {clan_display_name(r)}",callback_data=f"clan_member:{r['user_id']}")])
    kb.append([InlineKeyboardButton(text="➕ Пригласить",callback_data="clan_invite")])
    kb.append([InlineKeyboardButton(text="⬅️ Назад",callback_data="clans")])
    await call.answer(); await safe_edit(call.message,text,InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("clan_member:"))
async def clan_member_action(call: CallbackQuery):
    p=get_player(call.from_user.id); uid=int(call.data.split(":",1)[1]); role=clan_role(call.from_user.id,p["clan_id"])
    target=clan_role(uid,p["clan_id"])
    if role not in ("leader","deputy","admin") or not target or uid==call.from_user.id: await call.answer("Недостаточно прав.",show_alert=True); return
    if target=="leader" or (target=="deputy" and role!="leader"): await call.answer("Нельзя управлять этой ролью.",show_alert=True); return
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬆️ Повысить",callback_data=f"clan_promote:{uid}"),InlineKeyboardButton(text="⬇️ Понизить",callback_data=f"clan_demote:{uid}")],[InlineKeyboardButton(text="🚫 Исключить",callback_data=f"clan_kick:{uid}")],[InlineKeyboardButton(text="⬅️ Назад",callback_data="clan_members")]])
    await call.answer(); await safe_edit(call.message,f"👤 <b>УПРАВЛЕНИЕ УЧАСТНИКОМ</b>\n\nID: <code>{uid}</code>\nРоль: <b>{target}</b>",kb)

@dp.callback_query(F.data == "clan_admin")
async def clan_admin_callback(call: CallbackQuery):
    p=get_player(call.from_user.id); r=clan_role(call.from_user.id,p["clan_id"]) if p and p["clan_id"] else None
    if r not in ("leader","deputy","admin"): await call.answer("Нет доступа.",show_alert=True); return
    await call.answer(); await safe_edit(call.message,"⚙️ <b>ПАНЕЛЬ УПРАВЛЕНИЯ КЛАНОМ</b>\n\nУправление участниками, заявками, казной, объявлениями и развитием.",clan_admin_menu(call.from_user.id))

@dp.callback_query(F.data == "clan_invite")
async def clan_invite_callback(call: CallbackQuery,state:FSMContext):
    p=get_player(call.from_user.id)
    if not p or not p["clan_id"] or not clan_can_manage(call.from_user.id,p["clan_id"]): await call.answer("Нет доступа.",show_alert=True); return
    await state.set_state(ClanActionState.waiting_user); await state.update_data(action="invite"); await call.answer(); await call.message.answer("👤 Введи username (с @ или без) или Telegram ID игрока:")

@dp.message(ClanActionState.waiting_user)
async def clan_user_input(message:Message,state:FSMContext):
    data=await state.get_data(); action=data.get("action"); p=get_player(message.from_user.id)
    if not p or not p["clan_id"]: await state.clear(); return
    raw=(message.text or "").strip().lstrip("@"); target=None
    if raw.isdigit(): target=get_player(int(raw))
    else: target=db_execute("SELECT * FROM players WHERE lower(username)=lower(?)",(raw,),fetchone=True)
    if not target: await message.answer("❌ Игрок не найден."); return
    if action=="invite":
        if target["clan_id"]: await message.answer("❌ Игрок уже состоит в клане."); return
        db_execute("INSERT INTO clan_invites(clan_id,inviter_id,target_id,invitee_id,status,created_at) VALUES(?,?,?,?,?,?)",(p["clan_id"],message.from_user.id,target["user_id"],target["user_id"],"pending",now_iso()))
        await state.clear(); await message.answer("✅ Приглашение отправлено.")
        try: await message.bot.send_message(target["user_id"],f"🏰 Тебя приглашают в клан <b>{esc(clan_info(p['clan_id'])['name'])}</b>.",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Вступить",callback_data=f"clan_accept_invite:{p['clan_id']}"),InlineKeyboardButton(text="❌ Отклонить",callback_data=f"clan_decline_invite:{p['clan_id']}")]]))
        except Exception: pass
    else: await state.clear()

@dp.callback_query(F.data.startswith("clan_accept_invite:"))
async def clan_accept_invite(call:CallbackQuery):
    cid=int(call.data.split(":")[1]); p=get_player(call.from_user.id)
    inv=db_execute("SELECT * FROM clan_invites WHERE clan_id=? AND target_id=? AND status='pending' ORDER BY id DESC LIMIT 1",(cid,call.from_user.id),fetchone=True)
    if not inv or not p or p["clan_id"]: await call.answer("Приглашение недействительно.",show_alert=True); return
    db_execute("UPDATE clan_invites SET status='accepted' WHERE id=?",(inv["id"],)); db_execute("INSERT OR IGNORE INTO clan_members(clan_id,user_id,role) VALUES(?,?,?)",(cid,p["user_id"],"member")); db_execute("UPDATE players SET clan_id=? WHERE user_id=?",(cid,p["user_id"])); await call.answer("Добро пожаловать в клан!"); await safe_edit(call.message,"🏰 Ты вступил в клан!",clan_menu(call.from_user.id))

@dp.callback_query(F.data.startswith("clan_decline_invite:"))
async def clan_decline_invite(call:CallbackQuery):
    cid=int(call.data.split(":")[1]); db_execute("UPDATE clan_invites SET status='declined' WHERE clan_id=? AND target_id=? AND status='pending'",(cid,call.from_user.id)); await call.answer("Приглашение отклонено.",show_alert=True)

@dp.callback_query(F.data == "clan_requests")
async def clan_requests_callback(call:CallbackQuery):
    p=get_player(call.from_user.id)
    if not p or not p["clan_id"] or not clan_can_manage(call.from_user.id,p["clan_id"]): await call.answer("Нет доступа.",show_alert=True); return
    rows=db_execute("SELECT r.id,p.user_id,p.username,p.first_name,p.level FROM clan_join_requests r JOIN players p ON p.user_id=r.user_id WHERE r.clan_id=? AND r.status='pending' ORDER BY r.id DESC",(p["clan_id"],),fetchall=True)
    kb=[]; text="📩 <b>ЗАЯВКИ В КЛАН</b>\n\n"
    for r in rows: text+=f"• {esc(clan_display_name(r))} — Lv.{r['level']}\n"; kb.append([InlineKeyboardButton(text=f"✅ {clan_display_name(r)}",callback_data=f"clan_accept_request:{r['id']}"),InlineKeyboardButton(text="❌",callback_data=f"clan_reject_request:{r['id']}")])
    if not rows:text+="Заявок нет."
    kb.append([InlineKeyboardButton(text="⬅️ Назад",callback_data="clan_admin")]); await call.answer(); await safe_edit(call.message,text,InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("clan_accept_request:"))
async def clan_accept_request(call:CallbackQuery):
    p=get_player(call.from_user.id); rid=int(call.data.split(":")[1]); r=db_execute("SELECT * FROM clan_join_requests WHERE id=? AND clan_id=? AND status='pending'",(rid,p["clan_id"]),fetchone=True)
    if not r or not clan_can_manage(call.from_user.id,p["clan_id"]): await call.answer("Заявка недействительна.",show_alert=True); return
    db_execute("UPDATE clan_join_requests SET status='accepted' WHERE id=?",(rid,)); db_execute("INSERT OR IGNORE INTO clan_members(clan_id,user_id,role) VALUES(?,?,?)",(p["clan_id"],r["user_id"],"member")); db_execute("UPDATE players SET clan_id=? WHERE user_id=?",(p["clan_id"],r["user_id"])); await call.answer("Игрок принят!"); await clan_requests_callback(call)

@dp.callback_query(F.data.startswith("clan_reject_request:"))
async def clan_reject_request(call:CallbackQuery):
    p=get_player(call.from_user.id); rid=int(call.data.split(":")[1]); db_execute("UPDATE clan_join_requests SET status='rejected' WHERE id=? AND clan_id=?",(rid,p["clan_id"])); await call.answer("Отклонено."); await clan_requests_callback(call)

@dp.callback_query(F.data.startswith("clan_promote:"))
async def clan_promote(call:CallbackQuery):
    p=get_player(call.from_user.id); uid=int(call.data.split(":")[1]); r=clan_role(call.from_user.id,p["clan_id"]); tr=clan_role(uid,p["clan_id"])
    if r not in ("leader","deputy") or not tr: await call.answer("Нет доступа.",show_alert=True); return
    nxt={"member":"officer","officer":"admin","admin":"deputy"}.get(tr)
    if nxt=="deputy" and r!="leader": nxt=None
    if not nxt: await call.answer("Нельзя повысить дальше.",show_alert=True); return
    db_execute("UPDATE clan_members SET role=? WHERE clan_id=? AND user_id=?",(nxt,p["clan_id"],uid)); await call.answer("Роль повышена!"); await clan_members_callback(call)

@dp.callback_query(F.data.startswith("clan_demote:"))
async def clan_demote(call:CallbackQuery):
    p=get_player(call.from_user.id); uid=int(call.data.split(":")[1]); r=clan_role(call.from_user.id,p["clan_id"]); tr=clan_role(uid,p["clan_id"])
    if r not in ("leader","deputy") or tr in (None,"leader") or (tr=="deputy" and r!="leader"): await call.answer("Нет доступа.",show_alert=True); return
    prev={"deputy":"admin","admin":"officer","officer":"member"}.get(tr)
    if prev: db_execute("UPDATE clan_members SET role=? WHERE clan_id=? AND user_id=?",(prev,p["clan_id"],uid))
    await call.answer("Роль изменена!"); await clan_members_callback(call)

@dp.callback_query(F.data.startswith("clan_kick:"))
async def clan_kick(call:CallbackQuery):
    p=get_player(call.from_user.id); uid=int(call.data.split(":")[1]); r=clan_role(call.from_user.id,p["clan_id"]); tr=clan_role(uid,p["clan_id"])
    if r not in ("leader","deputy","admin") or tr=="leader" or (tr=="deputy" and r!="leader"): await call.answer("Нет доступа.",show_alert=True); return
    db_execute("DELETE FROM clan_members WHERE clan_id=? AND user_id=?",(p["clan_id"],uid)); db_execute("UPDATE players SET clan_id=NULL WHERE user_id=?",(uid,)); await call.answer("Игрок исключён."); await clan_members_callback(call)

@dp.callback_query(F.data == "clan_treasury")
async def clan_treasury_callback(call:CallbackQuery):
    p=get_player(call.from_user.id); c=ensure_clan_progress(p["clan_id"]) if p and p["clan_id"] else None
    if not c: await call.answer("Нет клана.",show_alert=True); return
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💰 Внести DCR",callback_data="clan_deposit:DCR"),InlineKeyboardButton(text="💎 Внести кристаллы",callback_data="clan_deposit:CRYSTALS")],[InlineKeyboardButton(text="📜 История",callback_data="clan_history")],[InlineKeyboardButton(text="⬅️ Назад",callback_data="clans")]])
    await call.answer(); await safe_edit(call.message,f"🏦 <b>КЛАНОВАЯ КАЗНА</b>\n\n💰 DCR: <b>{fmt(c['treasury_dcr'])}</b>\n💎 Кристаллы: <b>{fmt(c['treasury_crystals'])}</b>\n\nВнесение средств доступно всем участникам.",kb)

@dp.callback_query(F.data.startswith("clan_deposit:"))
async def clan_deposit_callback(call:CallbackQuery,state:FSMContext):
    p=get_player(call.from_user.id)
    if not p or not p["clan_id"]: await call.answer("Нет клана.",show_alert=True); return
    currency=call.data.split(":")[1]
    await state.set_state(ClanActionState.waiting_amount)
    await state.update_data(action="deposit",currency=currency)
    await call.answer()
    prompt=await call.message.answer(f"💰 Введите сумму {currency}:")
    await state.update_data(prompt_message_id=prompt.message_id,prompt_chat_id=prompt.chat.id)

@dp.message(ClanActionState.waiting_amount)
async def clan_amount_input(message: Message, state: FSMContext):
    data=await state.get_data(); p=get_player(message.from_user.id)
    prompt_id=data.get("prompt_message_id"); prompt_chat=data.get("prompt_chat_id", message.chat.id)
    try: await message.delete()
    except Exception: pass
    try:
        if prompt_id: await message.bot.delete_message(prompt_chat,prompt_id)
    except Exception: pass
    if data.get("action")!="deposit" or not p or not p["clan_id"]:
        await state.clear(); return
    try: amount=int((message.text or "").replace(" ",""))
    except (ValueError,TypeError):
        await state.clear(); return
    if amount<=0:
        await state.clear(); return
    cur=data.get("currency")
    balance=int(p["dcr"] or 0) if cur=="DCR" else int(p["crystals"] or 0)
    if balance<amount:
        await state.clear(); return
    if cur=="DCR": add_dcr(p["user_id"],-amount,"Взнос в клановую казну")
    else: add_crystals(p["user_id"],-amount,"Взнос в клановую казну")
    clan_treasury_add(p["clan_id"],p["user_id"],cur,amount,"Взнос участника")
    await state.clear()
    result=await message.answer(f"✅ Внесено {fmt(amount)} {cur} в клановую казну.")
    await asyncio.sleep(2)
    try: await result.delete()
    except Exception: pass

@dp.callback_query(F.data == "clan_announcements")
async def clan_announcements_callback(call:CallbackQuery):
    p=get_player(call.from_user.id); rows=db_execute("SELECT * FROM clan_announcements WHERE clan_id=? ORDER BY id DESC LIMIT 10",(p["clan_id"],),fetchall=True)
    text="📢 <b>ОБЪЯВЛЕНИЯ</b>\n\n"+('\n\n'.join(f"• {esc(r['text'])}" for r in rows) or "Пока объявлений нет.")
    kb=[[InlineKeyboardButton(text="➕ Создать объявление",callback_data="clan_announce_create")]] if clan_can_manage(call.from_user.id,p["clan_id"]) else []
    kb.append([InlineKeyboardButton(text="⬅️ Назад",callback_data="clans")]); await call.answer(); await safe_edit(call.message,text,InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "clan_announce_create")
async def clan_announce_create(call:CallbackQuery,state:FSMContext):
    p=get_player(call.from_user.id)
    if not p or not clan_can_manage(call.from_user.id,p["clan_id"]): await call.answer("Нет доступа.",show_alert=True); return
    await state.set_state(ClanActionState.waiting_announcement); await call.answer(); await call.message.answer("📢 Введи текст объявления:")

@dp.message(ClanActionState.waiting_announcement)
async def clan_announce_save(message:Message,state:FSMContext):
    data = await state.get_data()
    prompt_id = data.get("prompt_message_id")
    p = get_player(message.from_user.id)
    text = (message.text or "").strip()

    # Не оставляем введённый текст в чате.
    try:
        await message.delete()
    except Exception:
        pass
    if prompt_id:
        try:
            await message.bot.delete_message(message.chat.id, prompt_id)
        except Exception:
            pass

    if not p or not p["clan_id"] or not clan_can_manage(message.from_user.id,p["clan_id"]):
        await state.clear()
        return
    if not text or len(text)>1000:
        await state.clear()
        result = await message.bot.send_message(message.chat.id, "❌ Текст должен быть от 1 до 1000 символов.")
        await asyncio.sleep(2)
        try: await result.delete()
        except Exception: pass
        return

    # В актуальной схеме author_id существует; migration в upgrade_database
    # добавляет его и для старых БД.
    db_execute(
        "INSERT INTO clan_announcements(clan_id,author_id,text,created_at) VALUES(?,?,?,?)",
        (p["clan_id"], p["user_id"], text, now_iso())
    )
    await state.clear()

    result = await message.bot.send_message(
        message.chat.id,
        "📢 <b>Объявление опубликовано!</b>",
        reply_markup=clan_menu(message.from_user.id)
    )
    await asyncio.sleep(2)
    try: await result.delete()
    except Exception: pass

@dp.callback_query(F.data == "clan_leave")
async def clan_leave_callback(call:CallbackQuery):
    p=get_player(call.from_user.id)
    if not p or not p["clan_id"]: await call.answer("Ты не в клане.",show_alert=True); return
    r=clan_role(call.from_user.id,p["clan_id"])
    if r=="leader": await call.answer("❌ Глава не может выйти. Передай лидерство или расформируй клан.",show_alert=True); return
    db_execute("DELETE FROM clan_members WHERE clan_id=? AND user_id=?",(p["clan_id"],p["user_id"])); db_execute("UPDATE players SET clan_id=NULL WHERE user_id=?",(p["user_id"],)); await call.answer("Ты вышел из клана.",show_alert=True); await safe_edit(call.message,"🚪 Ты вышел из клана.",clan_menu(call.from_user.id))

@dp.callback_query(F.data == "clan_manage_members")
async def clan_manage_members(call:CallbackQuery): await clan_members_callback(call)

@dp.callback_query(F.data == "clan_roles")
async def clan_roles(call:CallbackQuery):
    p=get_player(call.from_user.id)
    if not p or clan_role(call.from_user.id,p["clan_id"])!="leader": await call.answer("Только лидер.",show_alert=True); return
    text="🔐 <b>РОЛИ КЛАНА</b>\n\n👑 Лидер — полный доступ\n🛡️ Заместитель — управление участниками, заявками, казной и развитием\n⚔️ Администратор — приглашения, заявки и объявления\n🎖️ Офицер — обычная старшая роль\n👤 Участник — базовые функции"
    await call.answer(); await safe_edit(call.message,text,clan_admin_menu(call.from_user.id))

@dp.callback_query(F.data == "clan_disband")
async def clan_disband(call:CallbackQuery):
    p=get_player(call.from_user.id)
    if not p or clan_role(call.from_user.id,p["clan_id"])!="leader": await call.answer("Только лидер.",show_alert=True); return
    cid=p["clan_id"]; db_execute("UPDATE players SET clan_id=NULL WHERE clan_id=?",(cid,)); db_execute("DELETE FROM clan_members WHERE clan_id=?",(cid,)); db_execute("DELETE FROM clans WHERE clan_id=?",(cid,)); await call.answer("Клан расформирован.",show_alert=True); await safe_edit(call.message,"🗑️ Клан расформирован.",clan_menu(call.from_user.id))


@dp.callback_query(F.data == "clan_power")
async def clan_power_callback(call: CallbackQuery):
    p=get_player(call.from_user.id)
    if not p or not p["clan_id"]: await call.answer("Нет клана.",show_alert=True); return
    await call.answer(); await safe_edit(call.message,f"⚡ <b>МОЩНОСТЬ КЛАНА</b>\n\n<b>{fmt(clan_power(p['clan_id']))}</b>",clan_menu(call.from_user.id))

@dp.callback_query(F.data == "clan_upgrade")
async def clan_upgrade_callback(call: CallbackQuery):
    p=get_player(call.from_user.id)
    if not p or not p["clan_id"]: await call.answer("Нет клана.",show_alert=True); return
    c=ensure_clan_progress(p["clan_id"])
    text=f"🏗️ <b>РАЗВИТИЕ КЛАНА</b>\n\n🏰 Клан: <b>{c['level']}</b> ур. • XP {fmt(c['xp'])}\n🏯 Штаб: <b>{c['headquarters_level']}</b>\n⚔️ Арсенал: <b>{c['arsenal_level']}</b>\n🏥 Лазарет: <b>{c['infirmary_level']}</b>\n🔬 Лаборатория: <b>{c['laboratory_level']}</b>\n🏪 Магазин: <b>{c['shop_level']}</b>\n\nУлучшения оплачиваются из казны."
    kb=InlineKeyboardMarkup(inline_keyboard=[
      [InlineKeyboardButton(text=f"🏯 Штаб — {fmt(clan_upgrade_cost(c['headquarters_level'],'headquarters'))} DCR",callback_data="clan_upgrade:headquarters")],
      [InlineKeyboardButton(text=f"⚔️ Арсенал — {fmt(clan_upgrade_cost(c['arsenal_level'],'arsenal'))} DCR",callback_data="clan_upgrade:arsenal")],
      [InlineKeyboardButton(text=f"🏥 Лазарет — {fmt(clan_upgrade_cost(c['infirmary_level'],'infirmary'))} DCR",callback_data="clan_upgrade:infirmary")],
      [InlineKeyboardButton(text=f"🔬 Лаборатория — {fmt(clan_upgrade_cost(c['laboratory_level'],'laboratory'))} DCR",callback_data="clan_upgrade:laboratory")],
      [InlineKeyboardButton(text=f"🏪 Магазин — {fmt(clan_upgrade_cost(c['shop_level'],'shop'))} DCR",callback_data="clan_upgrade:shop")],
      [InlineKeyboardButton(text="⬅️ Назад",callback_data="clans")]])
    await call.answer(); await safe_edit(call.message,text,kb)

@dp.callback_query(F.data.startswith("clan_upgrade:"))
async def clan_upgrade_do_callback(call: CallbackQuery):
    p=get_player(call.from_user.id)
    if not p or not p["clan_id"]: await call.answer("Нет клана.",show_alert=True); return
    role=clan_role(call.from_user.id,p["clan_id"])
    if role not in ("leader","deputy"): await call.answer("Только глава или заместитель.",show_alert=True); return
    kind=call.data.split(":",1)[1]; c=ensure_clan_progress(p["clan_id"])
    col={"headquarters":"headquarters_level","arsenal":"arsenal_level","infirmary":"infirmary_level","laboratory":"laboratory_level","shop":"shop_level"}.get(kind)
    if not col: await call.answer("Неизвестное улучшение.",show_alert=True); return
    level=int(c[col]); cost=clan_upgrade_cost(level,kind)
    cur=db_execute("SELECT treasury_dcr FROM clan_progress WHERE clan_id=?",(p["clan_id"],),fetchone=True)
    if not cur or int(cur["treasury_dcr"])<cost: await call.answer(f"В казне недостаточно DCR. Нужно {fmt(cost)}.",show_alert=True); return
    db_execute(f"UPDATE clan_progress SET treasury_dcr=treasury_dcr-?, {col}={col}+1 WHERE clan_id=? AND treasury_dcr>=?",(cost,p["clan_id"],cost))
    db_execute("INSERT INTO clan_treasury_log(clan_id,user_id,currency,amount,reason,created_at) VALUES(?,?,?,?,?,?)",(p["clan_id"],p["user_id"],"DCR",-cost,f"Улучшение {kind}",now_iso()))
    await call.answer("🏗️ Улучшение завершено!"); await clan_upgrade_callback(call)

@dp.callback_query(F.data == "clan_history")
async def clan_history_callback(call: CallbackQuery):
    p=get_player(call.from_user.id)
    if not p or not p["clan_id"]: await call.answer("Нет клана.",show_alert=True); return
    rows=db_execute("SELECT * FROM clan_treasury_log WHERE clan_id=? ORDER BY id DESC LIMIT 15",(p["clan_id"],),fetchall=True)
    text="📜 <b>ИСТОРИЯ КАЗНЫ</b>\n\n"+("\n".join(f"• {r['amount']:+,} {r['currency']} — {esc(r['reason'])}" for r in rows) or "Пока пусто.")
    await call.answer(); await safe_edit(call.message,text,clan_menu(call.from_user.id))

# ---------------- QUESTS ----------------

@dp.callback_query(F.data == "quests")
async def quests_callback(call: CallbackQuery):
    p = get_player(call.from_user.id)
    text = (
        "📜 <b>КВЕСТЫ</b>\n\n"
        "Ежедневные задания обновляются автоматически.\n\n"
        "⚔️ Победи 5 врагов — награда DCR + XP\n"
        "💰 Заработай 1 000 DCR — награда DCR + XP\n"
        "🔥 Нанеси 10 000 урона мировому боссу — награда DCR + XP"
    )
    await call.answer()
    await safe_edit(call.message, text, back_menu())

    # ============================================================
#                         PVP SYSTEM
# ============================================================


import asyncio
import random

PVP_TURN_TIMEOUT = 15

pvp_turn_tasks = {}

def ensure_pvp_stats(user_id: int):
    db_execute("""
        INSERT OR IGNORE INTO pvp_stats (
            user_id,
            mmr,
            ranked_games,
            ranked_wins,
            ranked_losses,
            calibration_games,
            total_games,
            total_wins,
            total_losses,
            total_damage,
            current_streak,
            best_streak
        )
        VALUES (?, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    """, (user_id,))


def get_pvp_stats(user_id: int):
    ensure_pvp_stats(user_id)

    return db_execute("""
        SELECT *
        FROM pvp_stats
        WHERE user_id=?
    """, (user_id,), fetchone=True)

def pvp_max_hp(user_id: int):
    player = get_player(user_id)

    if not player:
        return 100

    level = max(1, int(player["level"]))

    # +5 HP за каждый уровень после первого
    return 100 + (level - 1) * 5


def pvp_attack_damage(user_id: int):
    player = get_player(user_id)

    if not player:
        return 10

    level = max(1, int(player["level"]))

    # Базовая атака.
    # Позже сюда подключим оружие.
    return 15 + (level - 1) * 2


def pvp_is_in_queue(user_id: int):
    row = db_execute("""
        SELECT user_id
        FROM pvp_queue
        WHERE user_id=?
    """, (user_id,), fetchone=True)

    return row is not None


def pvp_active_match(user_id: int):
    return db_execute("""
        SELECT *
        FROM pvp_matches
        WHERE status IN ('waiting', 'active')
          AND (player1_id=? OR player2_id=?)
        ORDER BY id DESC
        LIMIT 1
    """, (user_id, user_id), fetchone=True)


def pvp_remove_from_queue(user_id: int):
    db_execute("""
        DELETE FROM pvp_queue
        WHERE user_id=?
    """, (user_id,))


def pvp_leave_queue(user_id: int):
    pvp_remove_from_queue(user_id)


def pvp_opponent(match, user_id: int):
    if match["player1_id"] == user_id:
        return match["player2_id"]

    if match["player2_id"] == user_id:
        return match["player1_id"]

    return None


def pvp_match_player_slot(match, user_id: int):
    if match["player1_id"] == user_id:
        return 1

    if match["player2_id"] == user_id:
        return 2

    return None


def pvp_rank_name(mmr: int):
    mmr = max(0, int(mmr))

    if mmr < 100:
        return "🥉 Bronze III"

    if mmr < 200:
        return "🥉 Bronze II"

    if mmr < 300:
        return "🥉 Bronze I"

    if mmr < 400:
        return "⚙️ Iron III"

    if mmr < 500:
        return "⚙️ Iron II"

    if mmr < 600:
        return "⚙️ Iron I"

    if mmr < 700:
        return "🥈 Silver III"

    if mmr < 800:
        return "🥈 Silver II"

    if mmr < 900:
        return "🥈 Silver I"

    if mmr < 1000:
        return "🥇 Gold III"

    if mmr < 1100:
        return "🥇 Gold II"

    if mmr < 1200:
        return "🥇 Gold I"

    if mmr < 1300:
        return "💠 Platinum III"

    if mmr < 1400:
        return "💠 Platinum II"

    if mmr < 1500:
        return "💠 Platinum I"

    if mmr < 1600:
        return "💎 Diamond III"

    if mmr < 1700:
        return "💎 Diamond II"

    if mmr < 1800:
        return "💎 Diamond I"

    if mmr < 1900:
        return "👑 Master III"

    if mmr < 2000:
        return "👑 Master II"

    if mmr < 2100:
        return "👑 Master I"

    return "🔥 Demonic"


def pvp_mmr_change(stats, won: bool):
    """
    Обычный рейтинговый бой после калибровки.
    Пока используем простую систему:
    победа +25
    поражение -25

    Во время калибровки расчёт будет отдельным.
    """

    if int(stats["calibration_games"]) < 5:
        return 0

    return 25 if won else -25



# ============================================================
# SCHEDULER
# ============================================================

# ============================================================
# SCHEDULER
# ============================================================

async def scheduler(bot: Bot):
    while True:
        try:
            now = utc_now_dt()

            # =========================================================
            # ЗАКРЫВАЕМ ИСТЁКШИХ БОССОВ
            # =========================================================

            db_execute(
                """
                UPDATE world_bosses
                SET active=0
                WHERE active=1
                  AND ends_at<=?
                """,
                (now.isoformat(),)
            )

            # =========================================================
            # АВТОМАТИЧЕСКИЕ БОССЫ
            # =========================================================

            for boss_type in ("daily", "weekly", "monthly"):

                # Если босс этого типа уже активен —
                # ничего не создаём
                if active_boss(boss_type):
                    continue

                # Последний созданный босс этого типа
                latest = db_execute(
                    """
                    SELECT *
                    FROM world_bosses
                    WHERE boss_type=?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (boss_type,),
                    fetchone=True
                )

                # =====================================================
                # ПЕРВОЕ ПОЯВЛЕНИЕ
                # =====================================================

                if latest is None:

                    # Только ежедневный босс создаётся
                    # автоматически при первом запуске
                    if boss_type == "daily":
                        await spawn_world_boss(
                            bot,
                            "daily"
                        )

                    continue

                # =====================================================
                # ПРОВЕРЯЕМ ОКОНЧАНИЕ ПОСЛЕДНЕГО БОССА
                # =====================================================

                try:
                    ends_at = datetime.fromisoformat(
                        latest["ends_at"]
                    )

                except Exception:
                    log.exception(
                        "Некорректный ends_at у босса %s",
                        latest["id"]
                    )
                    continue

                # =====================================================
                # НОВЫЙ ЦИКЛ
                # =====================================================

                if now >= ends_at:

                    await spawn_world_boss(
                        bot,
                        boss_type
                    )

            # =========================================================
            # ЗАКРЫВАЕМ ИСТЁКШИЕ ИГРОВЫЕ СОБЫТИЯ
            # =========================================================

            db_execute(
                """
                UPDATE events
                SET active=0
                WHERE active=1
                  AND ends_at<=?
                """,
                (now.isoformat(),)
            )

            # =========================================================
            # КЛАНОВЫЙ ТУРНИР
            # =========================================================

            get_or_create_tournament()

            await advance_clan_tournament(bot)

        except Exception:
            log.exception("Scheduler error")

        await asyncio.sleep(60)

# ============================================================
# ERROR HANDLER
# ============================================================

@dp.errors()
async def global_error(event):
    log.exception("Unhandled update error: %s", event.exception)
    return True



# ============================================================
# DOMINION 5.0 — CONTROL / CLANS / STORY EXTENSION
# ============================================================

ADMIN_ROLES = {
    "owner": "👑 Владелец",
    "chief_admin": "🛡️ Главный администратор",
    "admin": "🔨 Администратор",
    "moderator": "🆘 Модератор",
    "support": "💬 Саппорт",
}

ADMIN_PERMISSIONS = {
    "server": "🖥️ Управление сервером",
    "players": "👥 Игроки",
    "economy": "💰 Экономика",
    "items": "🎁 Предметы",
    "bosses": "👹 Боссы",
    "clans": "🏰 Кланы",
    "story": "📖 Сюжет",
    "broadcast": "📢 Рассылки",
    "database": "🗄️ База данных",
    "logs": "📜 Логи",
}

ROLE_DEFAULT_PERMISSIONS = {
    "owner": set(ADMIN_PERMISSIONS),
    "chief_admin": {"server","players","economy","items","bosses","clans","story","broadcast","logs"},
    "admin": {"players","economy","items","bosses","clans","story","broadcast"},
    "moderator": {"players","clans","logs"},
    "support": {"players"},
}

MAINTENANCE_FINISHED_TEXT = (
    "✅ <b>ТЕХНИЧЕСКИЕ РАБОТЫ ЗАВЕРШЕНЫ</b>\n\n"
    "DOMINION снова полностью доступен.\n"
    "Все игровые системы восстановлены.\n\n"
    "Спасибо за ожидание! ❤️"
)

def is_admin(user_id):
    if user_id == OWNER_ID and OWNER_ID != 0:
        return True
    row = db_execute(
        "SELECT 1 FROM admin_users WHERE user_id=? AND active=1",
        (user_id,), fetchone=True
    )
    return bool(row)

def admin_role(user_id):
    if user_id == OWNER_ID and OWNER_ID != 0:
        return "owner"
    row = db_execute(
        "SELECT role FROM admin_users WHERE user_id=? AND active=1",
        (user_id,), fetchone=True
    )
    return row["role"] if row else None

def has_admin_permission(user_id, permission):
    role = admin_role(user_id)
    if not role:
        return False
    if role == "owner":
        return True
    explicit = db_execute(
        "SELECT allowed FROM admin_permissions WHERE user_id=? AND permission=?",
        (user_id, permission), fetchone=True
    )
    if explicit is not None:
        return bool(explicit["allowed"])
    return permission in ROLE_DEFAULT_PERMISSIONS.get(role, set())

def maintenance_enabled():
    row = db_execute(
        "SELECT value FROM server_settings WHERE key='maintenance'",
        fetchone=True
    )
    return bool(row and row["value"] == "1")

def set_maintenance(enabled):
    db_execute("""
        INSERT INTO server_settings(key,value)
        VALUES('maintenance',?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
    """, ("1" if enabled else "0",))

def mark_seen(user_id):
    db_execute(
        "UPDATE players SET last_seen=? WHERE user_id=?",
        (now_iso(), user_id)
    )

def online_count(seconds=180):
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    # last_seen is ISO text generated by now_iso().
    return int(db_execute(
        "SELECT COUNT(*) AS c FROM players WHERE last_seen>=?",
        (cutoff.isoformat(),), fetchone=True
    )["c"])

class DominionMaintenanceMiddleware:
    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if user:
            mark_seen(user.id)
            if maintenance_enabled() and not is_admin(user.id):
                msg = MAINTENANCE_TEXT
                if isinstance(event, CallbackQuery):
                    await event.answer("🛠️ Технические работы.", show_alert=True)
                    try:
                        await safe_edit(event.message, msg, None)
                    except Exception:
                        pass
                elif isinstance(event, Message):
                    await event.answer(msg)
                return
        return await handler(event, data)

def admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Администраторы", callback_data="adm:admins"),
         InlineKeyboardButton(text="🔐 Права", callback_data="adm:permissions")],
        [InlineKeyboardButton(text="🖥️ Сервер", callback_data="adm:server"),
         InlineKeyboardButton(text="📊 Статистика", callback_data="adm:stats")],
        [InlineKeyboardButton(text="👥 Игроки", callback_data="adm:players"),
         InlineKeyboardButton(text="💰 Экономика", callback_data="adm:economy")],
        [InlineKeyboardButton(text="👹 Боссы", callback_data="adm:bosses"),
         InlineKeyboardButton(text="🏰 Кланы", callback_data="adm:clans")],
        [InlineKeyboardButton(text="🎫 Battle Pass", callback_data="adm:bp"),
         InlineKeyboardButton(text="📡 Мониторинг", callback_data="adm:monitor")],
        [InlineKeyboardButton(text="📖 Сюжет", callback_data="adm:story"),
         InlineKeyboardButton(text="📢 Рассылка", callback_data="adm:broadcast")],
        [InlineKeyboardButton(text="📜 Логи", callback_data="adm:logs"),
         InlineKeyboardButton(text="🗄️ БД", callback_data="adm:db")],
        [InlineKeyboardButton(text="➕ Добавить админа", callback_data="admin_add_ui"), InlineKeyboardButton(text="💰 Выдать DCR", callback_data="admin_give_dcr_ui")],
        [InlineKeyboardButton(text="💎 Выдать кристаллы", callback_data="admin_give_crystals_ui"), InlineKeyboardButton(text="✨ Выдать XP", callback_data="admin_give_xp_ui")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="other")],
    ])

@dp.callback_query(F.data == "admin")
async def dominion_admin_root(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа.", show_alert=True)
        return
    await call.answer()
    role = admin_role(call.from_user.id)
    await safe_edit(
        call.message,
        f"👑 <b>АДМИН-ПАНЕЛЬ DOMINION</b>\n\n"
        f"Твоя роль: <b>{ADMIN_ROLES.get(role, role)}</b>",
        admin_keyboard()
    )

@dp.callback_query(F.data.startswith("adm:"))
async def dominion_admin_sections(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    if not is_admin(user_id):
        await call.answer("Нет доступа.", show_alert=True)
        return
    section = call.data.split(":",1)[1]

    required = {
        "server":"server", "stats":"server", "admins":"server",
        "permissions":"server", "players":"players", "economy":"economy",
        "bosses":"bosses", "clans":"clans", "story":"story",
        "bp":"server", "monitor":"server",
        "broadcast":"broadcast", "logs":"logs", "db":"database",
    }.get(section, "server")
    if not has_admin_permission(user_id, required):
        await call.answer("Недостаточно прав.", show_alert=True)
        return

    await call.answer()

        # =========================================================
    # СОЗДАНИЕ МИРОВОГО БОССА
    # =========================================================

    if section.startswith("boss_spawn:"):
        boss_type = section.split(":", 1)[1]

        if boss_type not in BOSS_TYPES:
            await call.answer(
                "❌ Неизвестный тип босса.",
                show_alert=True
            )
            return

        # Проверяем, нет ли уже активного босса этого типа
        existing = active_boss(boss_type)

        if existing:
            type_names = {
                "daily": "🔥 Ежедневный",
                "weekly": "⚡ Недельный",
                "monthly": "☠️ Ежемесячный",
            }

            await call.answer(
                f"⚠️ {type_names.get(boss_type, boss_type)} уже активен.",
                show_alert=True
            )
            return

        # Создаём босса
        boss = await spawn_world_boss(
            bot,
            boss_type
        )

        if not boss:
            await call.answer(
                "❌ Не удалось создать босса.",
                show_alert=True
            )
            return

        type_names = {
            "daily": "🔥 Ежедневный",
            "weekly": "⚡ Недельный",
            "monthly": "☠️ Ежемесячный",
        }

        type_name = type_names.get(
            boss_type,
            boss_type
        )

        admin_log(
            user_id,
            "boss_spawn",
            target_id=boss["id"],
            details=f"type={boss_type}"
        )

        await call.answer(
            "✅ Босс успешно создан!"
        )

        await safe_edit(
            call.message,
            (
                "✅ <b>БОСС СОЗДАН</b>\n\n"
                f"{type_name}\n"
                f"👹 <b>{esc(boss['name'])}</b>\n\n"
                f"❤️ HP: <b>{fmt(boss['hp'])}/"
                f"{fmt(boss['max_hp'])}</b>\n"
                f"💰 Призовой фонд: "
                f"<b>{fmt(boss['reward_pool'])} DCR</b>\n\n"
                "📢 Информация опубликована в новостном канале."
            ),
            InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="👹 Управление боссами",
                            callback_data="adm:bosses"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="⬅️ Админ-панель",
                            callback_data="admin"
                        )
                    ],
                ]
            )
        )
        return

    if section == "admins":
        rows = db_execute(
            "SELECT user_id, role, active FROM admin_users ORDER BY created_at",
            fetchall=True
        )
        text = "👥 <b>АДМИНИСТРАТОРЫ</b>\n\n"
        text += f"👑 {OWNER_ID} — Владелец\n"
        for r in rows:
            text += f"• <code>{r['user_id']}</code> — {ADMIN_ROLES.get(r['role'], r['role'])}\n"
        text += "\nДобавление: <code>/admin_add USER_ID ROLE</code>"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin")]
        ])
        await safe_edit(call.message, text, kb)
        return

    if section == "permissions":
        text = (
            "🔐 <b>ПРАВА ДОСТУПА</b>\n\n"
            "Роли:\n"
            "👑 Владелец — всё\n"
            "🛡️ Главный администратор — почти всё\n"
            "🔨 Администратор — игроки/экономика/предметы/кланы\n"
            "🆘 Модератор — игроки/кланы/логи\n"
            "💬 Саппорт — игроки\n\n"
            "Изменить: <code>/admin_perm USER_ID permission 0|1</code>"
        )
        await safe_edit(call.message, text, admin_keyboard())
        return

    if section == "server":
        status = "🛠️ ТЕХНИЧЕСКИЙ РЕЖИМ" if maintenance_enabled() else "🟢 РАБОТАЕТ"
        text = (
            "🖥️ <b>УПРАВЛЕНИЕ СЕРВЕРОМ</b>\n\n"
            f"Статус: {status}\n"
            f"🟢 Онлайн: <b>{online_count()}</b>\n\n"
            "Команды:\n"
            "<code>/maintenance on</code> — включить\n"
            "<code>/maintenance off</code> — выключить\n"
            "<code>/broadcast Текст</code> — объявление\n"
            "<code>/clan_tournament</code> — месячный турнир"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛠️ Включить", callback_data="adm:maintenance_on"),
             InlineKeyboardButton(text="✅ Выключить", callback_data="adm:maintenance_off")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin")]
        ])
        await safe_edit(call.message, text, kb)
        return

    if section == "stats":
        total = db_execute("SELECT COUNT(*) c FROM players", fetchone=True)["c"]
        active_battles = db_execute("SELECT COUNT(*) c FROM pve_battles", fetchone=True)["c"]
        clans = db_execute("SELECT COUNT(*) c FROM clans", fetchone=True)["c"]
        dcr = db_execute("SELECT COALESCE(SUM(dcr),0) c FROM players", fetchone=True)["c"]
        crystals = db_execute("SELECT COALESCE(SUM(crystals),0) c FROM players", fetchone=True)["c"]
        text = (
            "📊 <b>СТАТИСТИКА СЕРВЕРА</b>\n\n"
            f"👥 Игроков: {total}\n"
            f"🟢 Онлайн: {online_count()}\n"
            f"⚔️ Активных PvE: {active_battles}\n"
            f"🏰 Кланов: {clans}\n"
            f"💰 DCR в экономике: {fmt(dcr)}\n"
            f"💎 Кристаллов: {fmt(crystals)}"
        )
        await safe_edit(call.message, text, admin_keyboard())
        return

    if section == "players":
        rows = db_execute("""
            SELECT user_id, username, first_name, level, dcr, crystals, blocked, wins, losses
            FROM players ORDER BY last_seen DESC LIMIT 20
        """, fetchall=True)
        text = "👥 <b>ПОСЛЕДНИЕ ИГРОКИ</b>\n\n"
        for r in rows:
            name = r["first_name"] or r["username"] or str(r["user_id"])
            text += (
                f"• {esc(name)} <code>{r['user_id']}</code> "
                f"Lv.{r['level']} | {fmt(r['dcr'])} DCR | "
                f"PvE {r['wins']}/{r['losses']}\n"
            )
        await safe_edit(call.message, text, admin_keyboard())
        return

    if section == "economy":
        await safe_edit(
            call.message,
            "💰 <b>ЭКОНОМИКА</b>\n\n"
            "<code>/give_dcr USER_ID AMOUNT</code>\n"
            "<code>/give_crystals USER_ID AMOUNT</code>",
            admin_keyboard()
        )
        return

    if section == "bosses":
        bosses = db_execute(
            """
            SELECT id, name, hp, max_hp, reward_pool, active,
                   starts_at, ends_at, boss_type
            FROM world_bosses
            ORDER BY id DESC
            LIMIT 10
            """,
            fetchall=True
        )

        type_names = {
            "daily": "🔥 Ежедневный",
            "weekly": "⚡ Недельный",
            "monthly": "☠️ Ежемесячный",
        }

        text = "👹 <b>УПРАВЛЕНИЕ МИРОВЫМИ БОССАМИ</b>\n\n"

        if not bosses:
            text += "📭 <b>Боссов пока нет.</b>\n\n"
        else:
            for b in bosses:
                boss_type = b["boss_type"] or "daily"
                type_name = type_names.get(
                    boss_type,
                    boss_type
                )

                status = (
                    "🟢 АКТИВЕН"
                    if int(b["active"]) == 1
                    else "⚪ Завершён"
                )

                text += (
                    f"{type_name}\n"
                    f"👹 <b>{esc(b['name'])}</b>\n"
                    f"❤️ HP: <b>{fmt(b['hp'])}/{fmt(b['max_hp'])}</b>\n"
                    f"💰 Призовой фонд: "
                    f"<b>{fmt(b['reward_pool'])} DCR</b>\n"
                    f"📊 {status}\n"
                    f"🆔 ID: <code>{b['id']}</code>\n"
                    f"🕐 Начало: <code>{esc(str(b['starts_at']))}</code>\n"
                    f"⏳ Конец: <code>{esc(str(b['ends_at']))}</code>\n\n"
                )

        text += (
            "━━━━━━━━━━━━━━━━━━\n"
            "🔥 <b>Ежедневный</b>\n"
            "❤️ 100 000 HP • 💰 20 000 DCR\n\n"
            "⚡ <b>Недельный</b>\n"
            "❤️ 1 000 000 HP • 💰 250 000 DCR\n\n"
            "☠️ <b>Ежемесячный</b>\n"
            "❤️ 10 000 000 HP • 💰 3 000 000 DCR\n\n"
            "Выбери тип босса для ручного запуска."
        )

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔥 Создать ежедневного",
                        callback_data="adm:boss_spawn:daily"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⚡ Создать недельного",
                        callback_data="adm:boss_spawn:weekly"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="☠️ Создать ежемесячного",
                        callback_data="adm:boss_spawn:monthly"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🔄 Обновить",
                        callback_data="adm:bosses"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ Назад",
                        callback_data="admin"
                    )
                ],
            ]
        )

        await safe_edit(
            call.message,
            text,
            kb
        )
        return

    if section == "clans":
        rows = db_execute("""
            SELECT c.clan_id,c.name,c.leader_id,COUNT(cm.user_id) members
            FROM clans c LEFT JOIN clan_members cm ON cm.clan_id=c.clan_id
            GROUP BY c.clan_id ORDER BY members DESC
        """, fetchall=True)
        text = "🏰 <b>УПРАВЛЕНИЕ КЛАНАМИ</b>\n\n"
        if not rows:
            text += "Кланов пока нет."
        for r in rows:
            text += f"• <b>{esc(r['name'])}</b> — {r['members']} чел. | глава <code>{r['leader_id']}</code>\n"
        text += "\nУдалить: <code>/clan_delete CLAN_ID</code>"
        await safe_edit(call.message, text, admin_keyboard())
        return

    if section == "story":
        await safe_edit(
            call.message,
            "📖 <b>СЮЖЕТ</b>\n\n"
            "Добавлены тяжёлые сюжетные этапы с NPC.\n"
            "Запуск игроком: 📖 Сюжет в меню.",
            admin_keyboard()
        )
        return

    if section == "bp":
        pcount = db_execute("SELECT COUNT(*) c FROM players", fetchone=True)["c"]
        paid = db_execute("SELECT COUNT(*) c FROM players WHERE bp_paid=1", fetchone=True)["c"]
        avg = db_execute("SELECT COALESCE(AVG(bp_level),0) a FROM players", fetchone=True)["a"]
        await safe_edit(
            call.message,
            "🎫 <b>УПРАВЛЕНИЕ BATTLE PASS</b>\n\n"
            f"👥 Игроков: <b>{pcount}</b>\n"
            f"💎 Премиум активирован: <b>{paid}</b>\n"
            f"📊 Средний уровень: <b>{avg:.1f}</b>\n\n"
            "Новый сезон/награды редактируются через таблицу bp_rewards.\n"
            "Игровой прогресс выдаётся автоматически за XP.",
            admin_keyboard()
        )
        return

    if section == "monitor":
        db_ok = False
        try:
            db_execute("SELECT 1", fetchone=True)
            db_ok = True
        except Exception:
            pass
        text = (
            "📡 <b>МОНИТОРИНГ DOMINION</b>\n\n"
            f"{'🟢' if db_ok else '🔴'} База данных\n"
            f"🟢 Telegram Bot\n"
            f"🟢 PvE\n"
            f"🟢 PvP\n"
            f"🟢 Кланы\n"
            f"🟢 Battle Pass\n"
            f"🟢 Рассылки\n"
            f"🟢 Боссы\n\n"
            f"👥 Онлайн: <b>{online_count()}</b>"
        )
        await safe_edit(call.message, text, admin_keyboard())
        return

    if section.startswith("boss_spawn:"):
        boss_type = section.split(":", 1)[1]

        if boss_type not in BOSS_TYPES:
            await call.answer(
                "❌ Неизвестный тип босса.",
                show_alert=True
            )
            return

        existing = active_boss(boss_type)

        if existing:
            type_names = {
                "daily": "🔥 Ежедневный",
                "weekly": "⚡ Недельный",
                "monthly": "☠️ Ежемесячный",
            }

            await call.answer(
                f"⚠️ {type_names.get(boss_type, boss_type)} уже активен.",
                show_alert=True
            )
            return

        boss = await spawn_world_boss(
            bot,
            boss_type
        )

        if not boss:
            await call.answer(
                "❌ Не удалось создать босса.",
                show_alert=True
            )
            return

        type_names = {
            "daily": "🔥 Ежедневный",
            "weekly": "⚡ Недельный",
            "monthly": "☠️ Ежемесячный",
        }

        type_name = type_names.get(
            boss_type,
            boss_type
        )

        admin_log(
            user_id,
            "boss_spawn",
            target_id=boss["id"],
            details=f"type={boss_type}"
        )

        await call.answer(
            "✅ Босс успешно создан!"
        )

        await safe_edit(
            call.message,
            (
                "✅ <b>БОСС СОЗДАН</b>\n\n"
                f"{type_name}\n"
                f"👹 <b>{esc(boss['name'])}</b>\n\n"
                f"❤️ HP: <b>{fmt(boss['hp'])}/"
                f"{fmt(boss['max_hp'])}</b>\n"
                f"💰 Призовой фонд: "
                f"<b>{fmt(boss['reward_pool'])} DCR</b>\n\n"
                "📢 Информация опубликована в новостном канале."
            ),
            InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="👹 Управление боссами",
                            callback_data="adm:bosses"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="⬅️ Админ-панель",
                            callback_data="admin"
                        )
                    ],
                ]
            )
        )
        return
    
    if section == "broadcast":
        await safe_edit(
            call.message,
            "📢 <b>РАССЫЛКА</b>\n\n"
            "Используй:\n<code>/broadcast Текст</code>\n\n"
            "Перед массовой отправкой бот покажет предпросмотр в ответе.",
            admin_keyboard()
        )
        return

    if section == "logs":
        rows = db_execute(
            "SELECT admin_id,action,target_id,details,created_at FROM admin_logs ORDER BY id DESC LIMIT 15",
            fetchall=True
        )
        text = "📜 <b>ИСТОРИЯ ДЕЙСТВИЙ</b>\n\n"
        for r in rows:
            text += f"• {r['created_at']} — <code>{r['admin_id']}</code> — {esc(r['action'])}\n"
        await safe_edit(call.message, text or "Лог пуст.", admin_keyboard())
        return

    if section == "db":
        text = "🗄️ <b>БАЗА ДАННЫХ</b>\n\nРезервная копия и восстановление доступны владельцу через команды."
        await safe_edit(call.message, text, admin_keyboard())
        return

    if section == "maintenance_on":
        set_maintenance(True)
        admin_log(user_id, "maintenance_on", details="Technical mode enabled")
        await safe_edit(call.message, MAINTENANCE_TEXT, admin_keyboard())
        try:
            await bot.send_message(NEWS_CHANNEL_ID, MAINTENANCE_TEXT)
        except Exception:
            log.exception("Не удалось опубликовать начало техработ")
        return

    if section == "maintenance_off":
        set_maintenance(False)
        admin_log(user_id, "maintenance_off", details="Technical mode disabled")
        await safe_edit(call.message, MAINTENANCE_FINISHED_TEXT, main_menu())
        try:
            await bot.send_message(NEWS_CHANNEL_ID, MAINTENANCE_FINISHED_TEXT)
        except Exception:
            log.exception("Не удалось опубликовать завершение техработ")
        return

@dp.message(Command("admin_add"))
async def admin_add_command(message: Message):
    if not is_admin(message.from_user.id) or not has_admin_permission(message.from_user.id, "server"):
        return
    if admin_role(message.from_user.id) != "owner":
        await message.answer("Только владелец может назначать администраторов.")
        return
    parts = message.text.split()
    if len(parts) != 3 or parts[2] not in ADMIN_ROLES or parts[2] == "owner":
        await message.answer("Использование: /admin_add USER_ID chief_admin|admin|moderator|support")
        return
    target, role = int(parts[1]), parts[2]
    db_execute("""
        INSERT INTO admin_users(user_id,role,created_at,active)
        VALUES(?,?,?,1)
        ON CONFLICT(user_id) DO UPDATE SET role=excluded.role, active=1
    """, (target, role, now_iso()))
    admin_log(message.from_user.id, "admin_add", target, role)
    await message.answer(f"✅ <code>{target}</code> назначен: {ADMIN_ROLES[role]}")

@dp.message(Command("admin_perm"))
async def admin_perm_command(message: Message):
    if admin_role(message.from_user.id) != "owner":
        return
    parts = message.text.split()
    if len(parts) != 4 or parts[2] not in ADMIN_PERMISSIONS or parts[3] not in ("0","1"):
        await message.answer("Использование: /admin_perm USER_ID permission 0|1")
        return
    target, perm, allowed = int(parts[1]), parts[2], int(parts[3])
    db_execute("""
        INSERT INTO admin_permissions(user_id,permission,allowed)
        VALUES(?,?,?)
        ON CONFLICT(user_id,permission) DO UPDATE SET allowed=excluded.allowed
    """, (target, perm, allowed))
    admin_log(message.from_user.id, "admin_perm", target, f"{perm}={allowed}")
    await message.answer("✅ Права обновлены.")

@dp.message(Command("maintenance"))
async def maintenance_command(message: Message, bot: Bot):
    if not has_admin_permission(message.from_user.id, "server"):
        return
    parts = message.text.split()
    if len(parts) != 2 or parts[1] not in ("on","off"):
        await message.answer("Использование: /maintenance on|off")
        return
    enabled = parts[1] == "on"
    set_maintenance(enabled)
    admin_log(message.from_user.id, "maintenance", details=parts[1])
    text = MAINTENANCE_TEXT if enabled else MAINTENANCE_FINISHED_TEXT
    await message.answer(text, reply_markup=admin_keyboard())
    if NEWS_CHANNEL_ID:
        try:
            await bot.send_message(NEWS_CHANNEL_ID, text)
        except Exception:
            log.exception("Публикация в NEWS_CHANNEL_ID не удалась")

@dp.message(Command("broadcast"))
async def broadcast_command(message: Message, bot: Bot):
    if not has_admin_permission(message.from_user.id, "broadcast"):
        return
    text = message.text.partition(" ")[2].strip()
    if not text:
        await message.answer("Использование: /broadcast Текст")
        return
    count = 0
    rows = db_execute("SELECT user_id FROM players WHERE blocked=0", fetchall=True)
    await message.answer(f"📢 Предпросмотр:\n\n{text}\n\nПолучателей: {len(rows)}")
    for r in rows:
        try:
            await bot.send_message(r["user_id"], "📢 <b>DOMINION</b>\n\n" + esc(text))
            count += 1
        except Exception:
            pass
        await asyncio.sleep(0.04)
    db_execute(
        "INSERT INTO server_announcements(admin_id,text,audience,created_at) VALUES(?,?,?,?)",
        (message.from_user.id, text, "all", now_iso())
    )
    admin_log(message.from_user.id, "broadcast", details=f"sent={count}")
    await message.answer(f"✅ Рассылка завершена. Отправлено: {count}")

# ---------------- ONLINE ----------------

@dp.callback_query(F.data == "online")
async def online_callback(call: CallbackQuery):
    await call.answer()
    rows = db_execute("""
        SELECT user_id,username,first_name,last_seen
        FROM players
        WHERE last_seen>=?
        ORDER BY last_seen DESC LIMIT 30
    """, (
        (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat(),
    ), fetchall=True)
    text = f"🟢 <b>ОНЛАЙН</b>\n\nСейчас в игре: <b>{len(rows)}</b>\n\n"
    for r in rows:
        name = r["first_name"] or r["username"] or str(r["user_id"])
        text += f"• {esc(name)}\n"
    await safe_edit(call.message, text, other_menu(call.from_user.id))

# ---------------- CLAN MANAGEMENT ----------------
# ---------------- MONTHLY 5x5 TOURNAMENT ----------------

def tournament_season():
    return datetime.now(timezone.utc).strftime("%Y-%m")

def get_or_create_tournament():
    season = tournament_season()
    t = db_execute(
        "SELECT * FROM clan_tournaments WHERE season=?",
        (season,), fetchone=True
    )
    if t:
        return t
    tid = db_insert(
        "INSERT INTO clan_tournaments(season,status,created_at) VALUES(?,?,?)",
        (season, "registration", now_iso())
    )
    return db_execute(
        "SELECT * FROM clan_tournaments WHERE id=?",
        (tid,), fetchone=True
    )

@dp.callback_query(F.data == "clan_tournament")
async def clan_tournament_callback(call: CallbackQuery):
    t = get_or_create_tournament()
    entries = db_execute("""
        SELECT e.clan_id,c.name,e.wins,e.eliminated
        FROM clan_tournament_entries e JOIN clans c ON c.clan_id=e.clan_id
        WHERE e.tournament_id=?
        ORDER BY e.wins DESC, c.name
    """, (t["id"],), fetchall=True)
    text = (
        "🏆 <b>ЕЖЕМЕСЯЧНЫЙ КЛАНОВЫЙ ТУРНИР</b>\n\n"
        f"Сезон: <b>{t['season']}</b>\n"
        f"Статус: <b>{t['status']}</b>\n\n"
        "Формат: <b>5 × 5</b>\n"
        "Глава/заместители выбирают пятёрку.\n"
        "Каждый участник подтверждает участие.\n"
        "После всех дуэлей побеждает клан с большим числом побед.\n\n"
        "Участники:\n"
    )
    for e in entries:
        text += f"• {esc(e['name'])} — побед: {e['wins']}\n"
    p = get_player(call.from_user.id)
    kb_rows = []
    if p and p["clan_id"]:
        kb_rows.append([InlineKeyboardButton(
            text="📝 Подать клан",
            callback_data=f"clan_join_t:{t['id']}"
        )])
    kb_rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="clan_tournament")])
    kb_rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="clans")])
    await call.answer()
    await safe_edit(call.message, text, InlineKeyboardMarkup(inline_keyboard=kb_rows))

@dp.callback_query(F.data.startswith("clan_join_t:"))
async def clan_join_tournament_callback(call: CallbackQuery):
    tid = int(call.data.split(":")[1])
    p = get_player(call.from_user.id)
    if not p or not p["clan_id"]:
        await call.answer("Нужен клан.", show_alert=True); return
    t = db_execute("SELECT * FROM clan_tournaments WHERE id=?", (tid,), fetchone=True)
    if not t or t["status"] != "registration":
        await call.answer("Регистрация закрыта.", show_alert=True); return
    role = db_execute(
        "SELECT role FROM clan_members WHERE clan_id=? AND user_id=?",
        (p["clan_id"], p["user_id"]), fetchone=True
    )
    if not role or role["role"] not in ("leader","deputy"):
        await call.answer("Только глава или заместитель выбирает состав.", show_alert=True); return
    db_execute("""
        INSERT OR IGNORE INTO clan_tournament_entries(tournament_id,clan_id)
        VALUES(?,?)
    """, (tid,p["clan_id"]))
    # SQLite schema doesn't have created_at here in legacy-safe installations.
    # Fallback is handled below by retrying the simple insert.
    await call.answer("Клан зарегистрирован.", show_alert=True)
    await safe_edit(call.message, "🏆 Клан зарегистрирован в турнире.\n\nВыбор пятёрки: используйте /clan_roster.", clan_menu(call.from_user.id))

@dp.message(Command("clan_roster"))
async def clan_roster_command(message: Message):
    p = get_player(message.from_user.id)
    if not p or not p["clan_id"]:
        return
    role = db_execute(
        "SELECT role FROM clan_members WHERE clan_id=? AND user_id=?",
        (p["clan_id"],p["user_id"]), fetchone=True
    )
    if not role or role["role"] not in ("leader","deputy"):
        await message.answer("Только глава или заместитель.")
        return
    t = get_or_create_tournament()
    rows = clan_members(p["clan_id"])
    text = "⚔️ <b>ВЫБОР ПЯТЁРКИ</b>\n\n"
    for i,r in enumerate(rows[:20],1):
        text += f"{i}. {esc(r['first_name'] or r['username'] or str(r['user_id']))} — Lv.{r['level']}\\n"
    text += "\nКоманда: <code>/clan_roster_set ID1 ID2 ID3 ID4 ID5</code>"
    await message.answer(text)

@dp.message(Command("clan_roster_set"))
async def clan_roster_set_command(message: Message):
    p = get_player(message.from_user.id)
    if not p or not p["clan_id"]:
        return
    role = db_execute(
        "SELECT role FROM clan_members WHERE clan_id=? AND user_id=?",
        (p["clan_id"],p["user_id"]), fetchone=True
    )
    if not role or role["role"] not in ("leader","deputy"):
        await message.answer("Только глава или заместитель."); return
    parts = message.text.split()
    if len(parts) != 6:
        await message.answer("Нужно ровно 5 ID: /clan_roster_set ID1 ID2 ID3 ID4 ID5"); return
    ids = list(dict.fromkeys(map(int,parts[1:])))
    if len(ids) != 5:
        await message.answer("Игроки не должны повторяться."); return
    valid = db_execute(
        f"SELECT user_id FROM clan_members WHERE clan_id=? AND user_id IN ({','.join('?'*5)})",
        (p["clan_id"], *ids), fetchall=True
    )
    if len(valid) != 5:
        await message.answer("Все 5 игроков должны быть членами клана."); return
    t = get_or_create_tournament()
    db_execute(
        "DELETE FROM clan_tournament_rosters WHERE tournament_id=? AND clan_id=?",
        (t["id"],p["clan_id"])
    )
    for uid in ids:
        db_execute("""
            INSERT INTO clan_tournament_rosters(tournament_id,clan_id,user_id,accepted)
            VALUES(?,?,?,0)
        """,(t["id"],p["clan_id"],uid))
    await message.answer(
        "✅ Пятёрка сохранена.\n\n"
        "Каждый выбранный игрок должен подтвердить участие командой:\n"
        "<code>/clan_accept</code>"
    )

@dp.message(Command("clan_accept"))
async def clan_accept_command(message: Message):
    t = get_or_create_tournament()
    p = get_player(message.from_user.id)
    if not p: return
    changed = db_execute("""
        UPDATE clan_tournament_rosters SET accepted=1
        WHERE tournament_id=? AND user_id=?
    """,(t["id"],p["user_id"]))
    await message.answer("✅ Участие подтверждено.")

def _duel_power(user_id):
    p = get_player(user_id)
    if not p:
        return 0
    s = player_combat_stats(user_id)
    return int(p["level"])*100 + int(p["pvp_rating"]) + int(s["attack_max"])*10 + int(s["armor_reduction"]*100)

def _fighter_card(user_id):
    p = get_player(user_id)
    if not p:
        return f"<code>{user_id}</code>"
    name = p["first_name"] or p["username"] or str(user_id)
    try:
        eq = get_equipment(user_id)
        weapon = eq["weapon_name"] if eq and eq["weapon_name"] else "—"
        ability = eq["ability_name"] if eq and eq["ability_name"] else "—"
        pet = eq["pet_name"] if eq and eq["pet_name"] else "—"
    except Exception:
        weapon, ability, pet = "—", "—", "—"
    return (
        f"👤 <b>{esc(name)}</b>\n"
        f"⚔️ {esc(str(weapon))}\n"
        f"🌌 {esc(str(ability))}\n"
        f"🐾 {esc(str(pet))}"
    )


async def run_clan_war_match(bot, match_id):
    match = db_execute(
        "SELECT * FROM clan_war_matches WHERE id=?",
        (match_id,), fetchone=True
    )
    if not match:
        return

    a = db_execute("""
        SELECT user_id FROM clan_tournament_rosters
        WHERE tournament_id=? AND clan_id=? AND accepted=1
        ORDER BY user_id LIMIT 5
    """, (match["tournament_id"], match["clan_a"]), fetchall=True)
    b = db_execute("""
        SELECT user_id FROM clan_tournament_rosters
        WHERE tournament_id=? AND clan_id=? AND accepted=1
        ORDER BY user_id LIMIT 5
    """, (match["tournament_id"], match["clan_b"]), fetchall=True)

    if len(a) != 5 or len(b) != 5:
        db_execute(
            "UPDATE clan_war_matches SET status='waiting' WHERE id=?",
            (match_id,)
        )
        return

    random.shuffle(a)
    random.shuffle(b)
    db_execute(
        "UPDATE clan_war_matches SET status='active' WHERE id=?",
        (match_id,)
    )

    wins_a = wins_b = 0

    for i, (ua, ub) in enumerate(zip(a, b), 1):
        ua_id, ub_id = ua["user_id"], ub["user_id"]
        pa, pb = _duel_power(ua_id), _duel_power(ub_id)

        # Случайность оставляет шанс слабейшему игроку, но сила влияет на исход.
        chance_a = pa / max(1, pa + pb)
        winner = ua_id if random.random() < chance_a else ub_id

        if winner == ua_id:
            wins_a += 1
        else:
            wins_b += 1

        db_execute("""
            INSERT OR REPLACE INTO clan_war_duels
            (match_id,duel_no,clan_a_user,clan_b_user,winner_user,status)
            VALUES(?,?,?,?,?,?)
        """, (match_id, i, ua_id, ub_id, winner, "finished"))

        card_a = _fighter_card(ua_id)
        card_b = _fighter_card(ub_id)
        result = "🏆 Победа" if winner == ua_id else "💀 Поражение"

        for uid in (ua_id, ub_id):
            try:
                await bot.send_message(
                    uid,
                    "⚔️ <b>КЛАНОВЫЙ БОЙ 5×5</b>\n\n"
                    f"<b>Дуэль {i}/5</b>\n\n"
                    f"{card_a}\n\n🆚\n\n{card_b}\n\n"
                    f"{result if winner == uid else ('💀 Поражение' if winner != uid else result)}\n"
                    f"📊 Счёт: <b>{wins_a} — {wins_b}</b>"
                )
            except Exception:
                pass

    winner_clan = match["clan_a"] if wins_a > wins_b else match["clan_b"]

    db_execute("""
        UPDATE clan_war_matches
        SET status='finished', winner_clan_id=?
        WHERE id=?
    """, (winner_clan, match_id))

    db_execute("""
        UPDATE clan_tournament_entries
        SET wins=wins+1
        WHERE tournament_id=? AND clan_id=?
    """, (match["tournament_id"], winner_clan))

    loser_clan = (
        match["clan_b"]
        if winner_clan == match["clan_a"]
        else match["clan_a"]
    )
    db_execute("""
        UPDATE clan_tournament_entries
        SET eliminated=1
        WHERE tournament_id=? AND clan_id=?
    """, (match["tournament_id"], loser_clan))

    # Итог матча обеим пятёркам.
    loser = loser_clan
    for clan_id, label in ((winner_clan, "🏆 ВЫ ПОБЕДИЛИ"), (loser, "💀 ВЫ ПРОИГРАЛИ")):
        roster = db_execute("""
            SELECT user_id FROM clan_tournament_rosters
            WHERE tournament_id=? AND clan_id=? AND accepted=1
        """, (match["tournament_id"], clan_id), fetchall=True)
        for r in roster:
            try:
                await bot.send_message(
                    r["user_id"],
                    f"⚔️ <b>ИТОГ КЛАНОВОГО БОЯ</b>\n\n"
                    f"{label}\n"
                    f"📊 Счёт: <b>{wins_a} — {wins_b}</b>\n"
                    f"Раунд: <b>{esc(match['round_name'])}</b>"
                )
            except Exception:
                pass


async def advance_clan_tournament(bot):
    t = get_or_create_tournament()
    if t["status"] == "finished":
        return

    entries = db_execute("""
        SELECT e.clan_id,e.wins,e.eliminated
        FROM clan_tournament_entries e
        WHERE e.tournament_id=? AND e.eliminated=0
        ORDER BY e.wins DESC, e.clan_id
    """, (t["id"],), fetchall=True)

    if len(entries) < 2:
        return

    # Все заявки должны иметь подтверждённые пятёрки.
    ready = []
    for e in entries:
        c = db_execute("""
            SELECT COUNT(*) c FROM clan_tournament_rosters
            WHERE tournament_id=? AND clan_id=? AND accepted=1
        """, (t["id"], e["clan_id"]), fetchone=True)
        if c["c"] == 5:
            ready.append(e["clan_id"])

    if len(ready) < 2:
        return

    active = db_execute("""
        SELECT COUNT(*) c FROM clan_war_matches
        WHERE tournament_id=? AND status IN ('waiting','active')
    """, (t["id"],), fetchone=True)["c"]
    if active:
        return

    # Если остался один клан — финалист/победитель.
    if len(ready) == 1:
        winner = ready[0]
        db_execute(
            "UPDATE clan_tournaments SET status='finished',finished_at=? WHERE id=?",
            (now_iso(), t["id"])
        )
        c = clan_info(winner)
        log.info("Clan tournament %s winner: %s", t["season"], c["name"] if c else winner)
        return

    round_name = "1/2 финала" if len(ready) == 2 else "Раунд"
    random.shuffle(ready)

    # Создаём следующий пакет матчей, избегая повторного создания уже завершённых пар.
    for i in range(0, len(ready)-1, 2):
        ca, cb = ready[i], ready[i+1]
        exists = db_execute("""
            SELECT 1 FROM clan_war_matches
            WHERE tournament_id=? AND status='finished'
              AND ((clan_a=? AND clan_b=?) OR (clan_a=? AND clan_b=?))
        """, (t["id"],ca,cb,cb,ca), fetchone=True)
        if exists:
            continue
        mid = db_insert("""
            INSERT INTO clan_war_matches
            (tournament_id,clan_a,clan_b,round_name,status,created_at)
            VALUES(?,?,?,?,?,?)
        """, (t["id"],ca,cb,round_name,"waiting",now_iso()))
        await run_clan_war_match(bot, mid)

    # Нечётный клан получает автоматический проход.
    if len(ready) % 2:
        bye = ready[-1]
        db_execute("""
            UPDATE clan_tournament_entries
            SET wins=wins+1
            WHERE tournament_id=? AND clan_id=?
        """, (t["id"],bye))

    db_execute(
        "UPDATE clan_tournaments SET status='active',started_at=COALESCE(started_at,?) WHERE id=?",
        (now_iso(),t["id"])
    )

@dp.callback_query(F.data == "clan_war")
async def clan_war_callback(call: CallbackQuery):
    p=get_player(call.from_user.id)
    if not p or not p["clan_id"]:
        await call.answer("Нет клана.",show_alert=True); return
    rows=db_execute("""
        SELECT id,round_name,status,winner_clan_id FROM clan_war_matches
        WHERE clan_a=? OR clan_b=? ORDER BY id DESC LIMIT 10
    """,(p["clan_id"],p["clan_id"]),fetchall=True)
    text="⚔️ <b>КЛАНОВЫЕ БОИ</b>\n\n"
    if not rows: text+="Твой клан ещё не проводил боёв."
    for r in rows:
        text+=f"• #{r['id']} — {esc(r['round_name'])} — {r['status']}\n"
    text+="\n🏆 Ежемесячный турнир проходит по системе 5×5."
    await call.answer()
    await safe_edit(call.message,text,clan_menu(call.from_user.id))

# ---------------- STORY / NPC ----------------

STORY_NPCS = [
    {
        "key":"old_woman_forest","name":"Бабушка Эльза","title":"Последняя жительница Тёмного леса",
        "chapter":1,"stage":0,
        "description":"Её деревню окружили монстры. Она просит тебя спасти людей."
    },
    {
        "key":"ruins_keeper","name":"Смотритель Арден","title":"Хранитель древних руин",
        "chapter":1,"stage":1,
        "description":"Он просит остановить проклятого рыцаря, который пробудил древнее зло."
    },
    {
        "key":"abyss_priestess","name":"Жрица Лира","title":"Голос Бездны",
        "chapter":1,"stage":2,
        "description":"Она знает, кто стоит за вторжением, но сначала требует доказать твою силу."
    },
]

@dp.callback_query(F.data == "story")
async def story_callback(call: CallbackQuery):
    p=get_player(call.from_user.id)
    row=db_execute("SELECT * FROM story_progress WHERE user_id=?",(p["user_id"],),fetchone=True)
    stage=int(row["stage"]) if row else 0
    npc=STORY_NPCS[min(stage,len(STORY_NPCS)-1)]
    text=(
        "📖 <b>СЮЖЕТ DOMINION</b>\n\n"
        f"👤 <b>{npc['name']}</b>\n"
        f"«{esc(npc['description'])}»\n\n"
        "⚠️ Эти сюжетные бои значительно сложнее обычных PvE.\n"
        "Победа открывает следующий этап."
    )
    kb=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚔️ Принять задание",callback_data="story_start")],
        [InlineKeyboardButton(text="⬅️ Назад",callback_data="other")]
    ])
    await call.answer(); await safe_edit(call.message,text,kb)

@dp.callback_query(F.data == "story_start")
async def story_start_callback(call: CallbackQuery):
    user_id=call.from_user.id
    p=get_player(user_id)
    row=db_execute("SELECT * FROM story_progress WHERE user_id=?",(user_id,),fetchone=True)
    stage=int(row["stage"]) if row else 0
    npc=STORY_NPCS[min(stage,len(STORY_NPCS)-1)]
    if db_execute("SELECT 1 FROM pve_battles WHERE user_id=?",(user_id,),fetchone=True):
        await call.answer("Сначала закончи текущий бой.",show_alert=True); return

    enemies=[
        ("story_wolves","Стая проклятых волков",420,38,58,700,"forest_particle"),
        ("story_knight","Проклятый рыцарь Ардена",900,65,95,1500,"ruins_particle"),
        ("story_abyss","Страж Бездны",1500,90,130,2800,"abyss_particle"),
    ]
    e=enemies[min(stage,2)]
    stats=player_combat_stats(user_id)
    max_hp=max(1, int(180+stats["attack_max"]*2+int(stats["armor_reduction"]*100)))
    db_execute("""
        INSERT OR REPLACE INTO pve_battles
        (user_id,location,enemy_key,enemy_name,enemy_hp,enemy_max_hp,enemy_min_damage,enemy_max_damage,
         reward_dcr,particle_type,player_hp,player_max_hp,started_at,last_action,stopped)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)
    """,(user_id,f"story:{stage}",e[0],e[1],e[2],e[2],e[3],e[4],e[5],e[6],max_hp,max_hp,now_iso(),time.time()))
    await call.answer("⚔️ Сюжетный бой начался!")
    await safe_edit(call.message,battle_row(user_id),battle_keyboard(user_id))

# ---------------- EXPANDED CLAN ECONOMY ----------------

db_script("""
CREATE TABLE IF NOT EXISTS clan_progress (
    clan_id INTEGER PRIMARY KEY,
    level INTEGER NOT NULL DEFAULT 1,
    xp INTEGER NOT NULL DEFAULT 0,
    treasury_dcr INTEGER NOT NULL DEFAULT 0,
    treasury_crystals INTEGER NOT NULL DEFAULT 0,
    headquarters_level INTEGER NOT NULL DEFAULT 1,
    arsenal_level INTEGER NOT NULL DEFAULT 1,
    infirmary_level INTEGER NOT NULL DEFAULT 1,
    laboratory_level INTEGER NOT NULL DEFAULT 1,
    shop_level INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS clan_treasury_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, clan_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
    currency TEXT NOT NULL, amount INTEGER NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS clan_announcements (
    id INTEGER PRIMARY KEY AUTOINCREMENT, clan_id INTEGER NOT NULL, author_id INTEGER NOT NULL,
    text TEXT NOT NULL, created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS clan_invites (
    id INTEGER PRIMARY KEY AUTOINCREMENT, clan_id INTEGER NOT NULL, inviter_id INTEGER NOT NULL,
    target_id INTEGER, invitee_id INTEGER, status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS clan_join_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT, clan_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL,
    UNIQUE(clan_id,user_id)
);
""")

def ensure_clan_progress(clan_id):
    db_execute("INSERT OR IGNORE INTO clan_progress(clan_id) VALUES(?)",(clan_id,))
    return db_execute("SELECT * FROM clan_progress WHERE clan_id=?",(clan_id,),fetchone=True)

def clan_treasury_add(clan_id,user_id,currency,amount,reason):
    amount=int(amount)
    if amount<=0:return False
    ensure_clan_progress(clan_id)
    col="treasury_dcr" if currency=="DCR" else "treasury_crystals"
    db_execute(f"UPDATE clan_progress SET {col}={col}+? WHERE clan_id=?",(amount,clan_id))
    db_execute("INSERT INTO clan_treasury_log(clan_id,user_id,currency,amount,reason,created_at) VALUES(?,?,?,?,?,?)",(clan_id,user_id,currency,amount,reason,now_iso()))
    return True

def clan_upgrade_cost(level,kind):
    base={"headquarters":500_000,"arsenal":750_000,"infirmary":600_000,"laboratory":900_000,"shop":1_000_000}.get(kind,500_000)
    return base*(int(level)**2)

# ---------------- ADMIN CLAN COMMANDS ----------------

@dp.message(Command("clan_delete"))
async def clan_delete_command(message: Message):
    if admin_role(message.from_user.id) != "owner":
        return
    parts=message.text.split()
    if len(parts)!=2: return
    cid=int(parts[1])
    db_execute("UPDATE players SET clan_id=NULL WHERE clan_id=?",(cid,))
    db_execute("DELETE FROM clan_members WHERE clan_id=?",(cid,))
    db_execute("DELETE FROM clans WHERE clan_id=?",(cid,))
    admin_log(message.from_user.id,"clan_delete",cid)
    await message.answer("🗑 Клан удалён.")

# ---------------- HOOKS ----------------

def install_dominion_5_hooks():
    try:
        dp.callback_query.outer_middleware(DominionMaintenanceMiddleware())
        dp.message.outer_middleware(DominionMaintenanceMiddleware())
    except Exception:
        log.exception("Не удалось установить maintenance middleware")



# ============================================================
# DOMINION 7.0 — FINAL SYSTEM UPGRADES
# ============================================================

def upgrade_database():
    """Safe idempotent migrations for existing dominion.db files."""
    migrations = {
        "players": [
            ("bp_xp", "INTEGER NOT NULL DEFAULT 0"),
            ("bp_level", "INTEGER NOT NULL DEFAULT 0"),
            ("vip_until", "TEXT"),
            ("divine_until", "TEXT"),
            ("crown_until", "TEXT"),
        ],
        "world_bosses": [
            ("boss_type", "TEXT NOT NULL DEFAULT 'daily'"),
        ],
    }
    for table, cols in migrations.items():
        existing = {r["name"] for r in db_execute(f"PRAGMA table_info({table})", fetchall=True)}
        for name, definition in cols:
            if name not in existing:
                db_execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

    db_script("""
    CREATE TABLE IF NOT EXISTS clan_invites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        clan_id INTEGER NOT NULL,
        inviter_id INTEGER NOT NULL,
        invitee_id INTEGER,
        target_id INTEGER,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS friends (
        user_id INTEGER NOT NULL,
        friend_id INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'accepted',
        created_at TEXT NOT NULL,
        PRIMARY KEY(user_id, friend_id)
    );
    CREATE TABLE IF NOT EXISTS friend_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER NOT NULL,
        receiver_id INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER NOT NULL,
        receiver_id INTEGER NOT NULL,
        sender_item_id INTEGER,
        sender_qty INTEGER NOT NULL DEFAULT 0,
        receiver_item_id INTEGER,
        receiver_qty INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS bp_rewards (
        level INTEGER PRIMARY KEY,
        free_reward TEXT,
        free_amount INTEGER NOT NULL DEFAULT 0,
        paid_reward TEXT,
        paid_amount INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS boss_claims (
        boss_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        reward INTEGER NOT NULL,
        PRIMARY KEY(boss_id, user_id)
    );
    CREATE TABLE IF NOT EXISTS market_lots_v2 (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_id INTEGER NOT NULL,
        item_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        price_dcr INTEGER NOT NULL DEFAULT 0,
        price_crystals INTEGER NOT NULL DEFAULT 0,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    );
    """)

    # Migrate old clan_invites schemas safely. Never put Python code inside db_script().
    _clan_invite_cols = {r["name"] for r in db_execute("PRAGMA table_info(clan_invites)", fetchall=True)}
    if "invitee_id" not in _clan_invite_cols:
        db_execute("ALTER TABLE clan_invites ADD COLUMN invitee_id INTEGER")
    if "target_id" not in _clan_invite_cols:
        db_execute("ALTER TABLE clan_invites ADD COLUMN target_id INTEGER")
    db_execute("UPDATE clan_invites SET invitee_id=target_id WHERE invitee_id IS NULL AND target_id IS NOT NULL")
    db_execute("UPDATE clan_invites SET target_id=invitee_id WHERE target_id IS NULL AND invitee_id IS NOT NULL")

    # Migrate legacy clan_announcements tables. Older versions could have
    # clan_id/text/created_at but no author_id. CREATE TABLE IF NOT EXISTS
    # does not modify an existing SQLite table, so explicitly add the column.
    _announcement_cols = {r["name"] for r in db_execute("PRAGMA table_info(clan_announcements)", fetchall=True)}
    if "author_id" not in _announcement_cols:
        db_execute("ALTER TABLE clan_announcements ADD COLUMN author_id INTEGER")

    # Migrate old clan_announcements schemas too.
    _announcement_cols = {r["name"] for r in db_execute("PRAGMA table_info(clan_announcements)", fetchall=True)}
    if "author_id" not in _announcement_cols:
        db_execute("ALTER TABLE clan_announcements ADD COLUMN author_id INTEGER NOT NULL DEFAULT 0")
    if "created_at" not in _announcement_cols:
        db_execute("ALTER TABLE clan_announcements ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")

    # Starter BP reward track. Idempotent.
    rewards = [
        (1, "dcr", 250, None, 0), (5, "crystals", 5, None, 0),
        (10, "dcr", 750, None, 0), (15, "crystals", 15, None, 0),
        (20, "dcr", 1500, None, 0), (25, "crystals", 30, None, 0),
        (30, "item:epic_weapon", 1, "item:epic_weapon", 1),
        (40, "crystals", 50, None, 0), (50, "item:legendary_weapon", 1, "item:legendary_weapon", 1),
        (60, "crystals", 75, None, 0), (75, "dcr", 10000, None, 0),
        (100, "item:demonic_reaper", 1, "item:demonic_reaper", 1),
    ]
    for level, fr, fa, pr, pa in rewards:
        db_execute("INSERT OR IGNORE INTO bp_rewards(level,free_reward,free_amount,paid_reward,paid_amount) VALUES(?,?,?,?,?)", (level,fr,fa,pr,pa))



# ============================================================
# DOMINION 8.0 — ECONOMY / EFFECTS / CRAFT / CASES / CASINO
# ============================================================

def ensure_legacy_runtime_schema():
    """Create/migrate runtime tables only after init_database() has created the base schema."""
    db_script("""
    CREATE TABLE IF NOT EXISTS pve_effects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        target TEXT NOT NULL,
        effect_type TEXT NOT NULL,
        damage INTEGER NOT NULL DEFAULT 0,
        expires_at REAL NOT NULL,
        next_tick REAL NOT NULL,
        created_at REAL NOT NULL
    );
    CREATE TABLE IF NOT EXISTS pve_battle_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        message TEXT NOT NULL,
        created_at REAL NOT NULL
    );
    CREATE TABLE IF NOT EXISTS pve_battle_events (
        user_id INTEGER PRIMARY KEY,
        event_type TEXT,
        event_text TEXT,
        active INTEGER NOT NULL DEFAULT 0,
        countdown INTEGER NOT NULL DEFAULT 0,
        created_at REAL
    );
    """)
    eq_cols = {r["name"] for r in db_execute("PRAGMA table_info(equipment)", fetchall=True)}
    for col in ("ability_id", "pet_id"):
        if col not in eq_cols:
            db_execute(f"ALTER TABLE equipment ADD COLUMN {col} INTEGER")
    # These columns are already present in current pvp schema, but migrate old DBs safely.
    pvp_cols = {r["name"] for r in db_execute("PRAGMA table_info(pvp_matches)", fetchall=True)}
    for col in ("player1_message_id", "player2_message_id"):
        if col not in pvp_cols:
            db_execute(f"ALTER TABLE pvp_matches ADD COLUMN {col} INTEGER")
    stats_cols = {r["name"] for r in db_execute("PRAGMA table_info(pvp_stats)", fetchall=True)}
    if "calibration_direction" not in stats_cols:
        db_execute("ALTER TABLE pvp_stats ADD COLUMN calibration_direction TEXT NOT NULL DEFAULT 'normal'")
    # Seed divine items after the base items table definitely exists.
    seeds = [
        ("heaven_wrath", "Небесный гнев", "weapon", "Божественный", 100, 300, 0),
        ("soul_eater", "Пожиратель душ", "weapon", "Божественный", 80, 260, 0),
        ("thunderer", "Громовержец", "weapon", "Божественный", 120, 280, 0),
        ("wrath_of_heaven", "Гнев небес", "ability", "Божественный", 0, 0, 0),
        ("divine_rebirth", "Божественное возрождение", "ability", "Божественный", 0, 0, 0),
        ("sky_dragon", "Небесный дракон", "pet", "Божественный", 0, 0, 0),
        ("divine_phoenix", "Божественный Феникс", "pet", "Божественный", 0, 0, 0),
    ]
    for key,name,itype,rarity,amin,amax,price in seeds:
        db_execute("""INSERT OR IGNORE INTO items(item_key,name,item_type,rarity,attack_min,attack_max,price_dcr)
                       VALUES(?,?,?,?,?,?,?)""", (key,name,itype,rarity,amin,amax,price))
        db_execute("UPDATE items SET name=?,item_type=?,rarity=?,attack_min=?,attack_max=?,price_dcr=? WHERE item_key=?",
                   (name,itype,rarity,amin,amax,price,key))


def ensure_base_items():
    for key,name,rarity,amin,amax,price in WEAPONS:
        db_execute("INSERT OR IGNORE INTO items(item_key,name,item_type,rarity,attack_min,attack_max,price_dcr) VALUES(?,?,?,?,?,?,?)",(key,name,"weapon",rarity,amin,amax,price))
        db_execute("UPDATE items SET name=?,rarity=?,attack_min=?,attack_max=?,price_dcr=? WHERE item_key=?",(name,rarity,amin,amax,price,key))
    for key,name,rarity,reduction,price in ARMORS:
        db_execute("INSERT OR IGNORE INTO items(item_key,name,item_type,rarity,damage_reduction,price_dcr) VALUES(?,?,?,?,?,?)",(key,name,"armor",rarity,reduction,price))
        db_execute("UPDATE items SET name=?, item_type='armor', rarity=?, damage_reduction=?, price_dcr=? WHERE item_key=?",(name,rarity,reduction,price,key))
    for key,name,rarity,chance,reduction,price in SHIELDS:
        db_execute("INSERT OR IGNORE INTO items(item_key,name,item_type,rarity,shield_chance,shield_reduction,price_dcr) VALUES(?,?,?,?,?,?,?)",(key,name,"shield",rarity,chance,reduction,price))
        db_execute("UPDATE items SET name=?, item_type='shield', rarity=?, shield_chance=?, shield_reduction=?, price_dcr=? WHERE item_key=?",(name,rarity,chance,reduction,price,key))
    for key,name,rarity,price in MATERIALS:
        db_execute("INSERT OR IGNORE INTO items(item_key,name,item_type,rarity,price_dcr) VALUES(?,?,?,?,?)",(key,name,"material",rarity,price))
    for key,name,rarity,heal,price,particle in POTIONS:
        db_execute("INSERT OR IGNORE INTO items(item_key,name,item_type,rarity,price_dcr,particle_type) VALUES(?,?,?,?,?,?)",(key,name,"potion",rarity,price,particle))
        db_execute("UPDATE items SET name=?, item_type='potion', rarity=?, price_dcr=?, particle_type=? WHERE item_key=?",(name,rarity,price,particle,key))
    for key,name,rarity,description,price in PETS:
        db_execute("INSERT OR IGNORE INTO items(item_key,name,item_type,rarity,price_dcr) VALUES(?,?,?,?,?)",(key,name,"pet",rarity,price))
        db_execute("UPDATE items SET name=?, item_type='pet', rarity=?, price_dcr=? WHERE item_key=?",(name,rarity,price,key))

ORDINARY_ABILITIES = [
    ("sacrificial_strike", "💀 Жертвенный удар", "Обычный", 100_000),
    ("rupture", "🩸 Разрыв", "Обычный", 150_000),
    ("firestorm", "🔥 Огненный взрыв", "Редкий", 225_000),
    ("frost_grip", "🧊 Ледяная хватка", "Редкий", 300_000),
    ("lightning_strike", "⚡ Молниеносный удар", "Эпический", 400_000),
    ("last_chance", "🛡️ Последний шанс", "Эпический", 550_000),
    ("evasion", "🌀 Уклонение", "Легендарный", 750_000),
    ("rebirth", "🩹 Перерождение", "Легендарный", 1_000_000),
    ("berserk", "😈 Берсерк", "Мифический", 1_500_000),
]

def ensure_v8_database():
    db_script("""
    CREATE TABLE IF NOT EXISTS pvp_effects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        effect_type TEXT NOT NULL,
        damage INTEGER NOT NULL DEFAULT 0,
        expires_at REAL NOT NULL,
        next_tick REAL NOT NULL,
        created_at REAL NOT NULL
    );
    CREATE TABLE IF NOT EXISTS craft_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        recipe_key TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS casino_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        currency TEXT NOT NULL,
        bet INTEGER NOT NULL,
        result INTEGER NOT NULL,
        multiplier REAL NOT NULL,
        symbols TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS admin_action_requests (
        user_id INTEGER PRIMARY KEY,
        action TEXT NOT NULL,
        target_id INTEGER,
        amount INTEGER,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS player_upgrades (
        user_id INTEGER NOT NULL,
        item_id INTEGER NOT NULL,
        level INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(user_id, item_id)
    );
    CREATE TABLE IF NOT EXISTS case_openings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        case_key TEXT NOT NULL,
        reward_key TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """)

    player_cols = {r["name"] for r in db_execute("PRAGMA table_info(players)", fetchall=True)}
    if "potions" not in player_cols:
        db_execute("ALTER TABLE players ADD COLUMN potions INTEGER NOT NULL DEFAULT 3")

    # Existing boss databases from older versions may not have boss_type.
    cols = {r["name"] for r in db_execute("PRAGMA table_info(world_bosses)", fetchall=True)}
    if "boss_type" not in cols:
        db_execute("ALTER TABLE world_bosses ADD COLUMN boss_type TEXT NOT NULL DEFAULT 'daily'")

    # New item families.
    seed = [
        ("potion_void", "🕳️ Зелье опустошения", "potion", "Редкий", 0, 0, 0, 0, 0, 250, ""),
        ("potion_regen", "❤️ Зелье регенерации", "potion", "Обычный", 0, 0, 0, 0, 0, 120, "forest_particle"),
        ("potion_invisibility", "👻 Зелье невидимости", "potion", "Эпический", 0, 0, 0, 0, 0, 650, "cave_particle"),
        ("ability_firestorm", "🔥 Огненный шторм", "ability", "Эпический", 0, 0, 0, 0, 0, 1800, ""),
        ("ability_vampiric", "🩸 Кровавый ритуал", "ability", "Легендарный", 0, 0, 0, 0, 0, 5000, ""),
        ("ability_shadow_step", "🌑 Теневой шаг", "ability", "Мифический", 0, 0, 0, 0, 0, 15000, ""),
    ]
    for row in seed:
        db_execute("""
            INSERT OR IGNORE INTO items
            (item_key,name,item_type,rarity,attack_min,attack_max,damage_reduction,shield_chance,shield_reduction,price_dcr,particle_type)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)
        """, row)
    # Guarantee all ordinary shop abilities exist on old databases too.
    for key, name, rarity, price in ORDINARY_ABILITIES:
        db_execute("""
            INSERT OR IGNORE INTO items (item_key,name,item_type,rarity,price_dcr)
            VALUES(?,?,?,?,?)
        """, (key, name, "ability", rarity, price))
        db_execute("UPDATE items SET name=?, rarity=?, price_dcr=? WHERE item_key=? AND item_type='ability'", (name, rarity, price, key))

def utc_now_dt():
    return datetime.now(timezone.utc)


def add_bp_xp(user_id, amount):
    p = get_player(user_id)
    if not p:
        return 0, 0
    amount = max(0, int(amount))
    xp = int(p["bp_xp"]) + amount
    level = int(p["bp_level"])
    gained = 0
    while level < 100 and xp >= 100 + level * 25:
        xp -= 100 + level * 25
        level += 1
        gained += 1
    db_execute("UPDATE players SET bp_xp=?,bp_level=? WHERE user_id=?", (xp, level, user_id))
    return level, gained


def bp_text(user_id):
    p = get_player(user_id)
    level = int(p["bp_level"])
    xp = int(p["bp_xp"])
    need = 100 + level * 25
    paid = bool(p["bp_paid"])
    rewards = db_execute("SELECT * FROM bp_rewards WHERE level>? ORDER BY level LIMIT 3", (level,), fetchall=True)
    text = (
        "🎫 <b>BATTLE PASS</b>\n\n"
        f"Уровень: <b>{level}/100</b>\n"
        f"Опыт: <b>{xp}/{need}</b>\n"
        f"Премиальный путь: {'✅ активен' if paid else '❌ не куплен'}\n\n"
        "Награды впереди:\n"
    )
    for r in rewards:
        text += f"• {r['level']} уровень — {esc(r['free_reward'] or '—')}\n"
    return text


@dp.callback_query(F.data == "bp")
async def bp_callback(call: CallbackQuery):
    await call.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎫 Купить премиальный Battle Pass", callback_data="shop_bp")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="other")],
    ])
    await safe_edit(call.message, bp_text(call.from_user.id), kb)


# ---------------- WORLD BOSSES ----------------

BOSS_TYPES = {
    "daily": {"name": "Ежедневный босс", "hp": 100_000, "reward": 20_000, "hours": 24},
    "weekly": {"name": "Недельный босс", "hp": 1_000_000, "reward": 250_000, "hours": 24 * 7},
    "monthly": {"name": "Ежемесячный босс", "hp": 10_000_000, "reward": 3_000_000, "hours": 24 * 30},
}


def active_boss(boss_type=None):
    if boss_type:
        return db_execute("SELECT * FROM world_bosses WHERE active=1 AND boss_type=? ORDER BY id DESC LIMIT 1", (boss_type,), fetchone=True)
    return db_execute("SELECT * FROM world_bosses WHERE active=1 ORDER BY id DESC LIMIT 1", fetchone=True)


async def publish_news(bot, text):
    if not NEWS_CHANNEL_ID:
        return False
    try:
        await bot.send_message(NEWS_CHANNEL_ID, text)
        return True
    except Exception:
        log.exception("Публикация в NEWS_CHANNEL_ID не удалась")
        return False


async def spawn_world_boss(bot, boss_type="daily"):
    spec = BOSS_TYPES[boss_type]
    existing = active_boss(boss_type)
    if existing:
        return existing
    now = utc_now_dt()
    ends = now + timedelta(hours=spec["hours"])
    bid = db_insert("""
        INSERT INTO world_bosses(boss_key,name,max_hp,hp,reward_pool,starts_at,ends_at,active,published,boss_type)
        VALUES(?,?,?,?,?,?,?,1,1,?)
    """, (boss_type, spec["name"], spec["hp"], spec["hp"], spec["reward"], now.isoformat(), ends.isoformat(), boss_type))
    boss = db_execute("SELECT * FROM world_bosses WHERE id=?", (bid,), fetchone=True)
    await publish_news(bot, f"🔥 <b>{esc(spec['name'])} появился!</b>\n\n❤️ HP: <b>{fmt(spec['hp'])}</b>\n💰 Общий призовой фонд: <b>{fmt(spec['reward'])} DCR</b>\n\nУспейте нанести урон до окончания события!")
    return boss


def boss_screen(user_id, boss_type=None):
    if boss_type:
        boss = active_boss(boss_type)

        type_names = {
            "daily": "🔥 ЕЖЕДНЕВНЫЙ БОСС",
            "weekly": "⚡ НЕДЕЛЬНЫЙ БОСС",
            "monthly": "☠️ ЕЖЕМЕСЯЧНЫЙ БОСС",
        }

        title = type_names.get(
            boss_type,
            "👹 МИРОВОЙ БОСС"
        )

        if not boss:
            spec = BOSS_TYPES.get(boss_type)

            if not spec:
                return "❌ Неизвестный тип босса."

            return (
                f"{title}\n\n"
                "📭 <b>Сейчас не активен</b>\n\n"
                f"❤️ Максимальное HP: <b>{fmt(spec['hp'])}</b>\n"
                f"💰 Призовой фонд: <b>{fmt(spec['reward'])} DCR</b>\n\n"
                "Следующее появление произойдёт автоматически."
            )

        hp = max(0, int(boss["hp"]))
        mx = max(1, int(boss["max_hp"]))

        rows = db_execute(
            """
            SELECT user_id, damage
            FROM boss_damage
            WHERE boss_id=?
            ORDER BY damage DESC
            LIMIT 5
            """,
            (boss["id"],),
            fetchall=True
        )

        text = (
            f"{title}\n\n"
            f"👹 <b>{esc(boss['name'])}</b>\n\n"
            f"❤️ HP: <b>{fmt(hp)}/{fmt(mx)}</b>\n"
            f"{_hp_bar(hp, mx, 20)}\n\n"
            f"💰 Призовой фонд: "
            f"<b>{fmt(boss['reward_pool'])} DCR</b>\n\n"
            "🏆 <b>ТОП УРОНА</b>\n"
        )

        if not rows:
            text += "\n📭 Пока никто не нанёс урон."
        else:
            medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]

            for i, r in enumerate(rows, 1):
                medal = medals[i - 1]
                text += (
                    f"{medal} <code>{r['user_id']}</code>"
                    f" — <b>{fmt(r['damage'])}</b> урона\n"
                )

        return text

    # =========================================================
    # ОБЩИЙ ЭКРАН МИРОВЫХ БОССОВ
    # =========================================================

    bosses = []

    for current_type in ("daily", "weekly", "monthly"):
        boss = active_boss(current_type)

        if boss:
            bosses.append(boss)

    text = "🔥 <b>МИРОВЫЕ БОССЫ</b>\n\n"

    if not bosses:
        return (
            text +
            "📭 Сейчас активных боссов нет.\n\n"
            "Следующее появление произойдёт автоматически."
        )

    type_names = {
        "daily": "🔥 Ежедневный",
        "weekly": "⚡ Недельный",
        "monthly": "☠️ Ежемесячный",
    }

    for boss in bosses:
        current_type = boss["boss_type"] or "daily"

        hp = max(0, int(boss["hp"]))
        mx = max(1, int(boss["max_hp"]))

        text += (
            f"{type_names.get(current_type, current_type)}\n"
            f"👹 <b>{esc(boss['name'])}</b>\n"
            f"❤️ <b>{fmt(hp)}/{fmt(mx)}</b>\n"
            f"{_hp_bar(hp, mx, 18)}\n"
            f"💰 <b>{fmt(boss['reward_pool'])} DCR</b>\n\n"
        )

    text += (
        "Выберите босса ниже, чтобы посмотреть его участников "
        "и атаковать его."
    )

    return text

@dp.callback_query(F.data == "boss")
async def boss_callback(call: CallbackQuery):
    await call.answer()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🔥 Ежедневный",
                callback_data="boss_type:daily"
            )
        ],
        [
            InlineKeyboardButton(
                text="⚡ Недельный",
                callback_data="boss_type:weekly"
            )
        ],
        [
            InlineKeyboardButton(
                text="☠️ Ежемесячный",
                callback_data="boss_type:monthly"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data="game"
            )
        ],
    ])

    await safe_edit(
        call.message,
        boss_screen(call.from_user.id),
        kb
    )
    
@dp.callback_query(F.data.startswith("boss_type:"))
async def boss_type_callback(call: CallbackQuery):
    boss_type = call.data.split(":", 1)[1]

    if boss_type not in BOSS_TYPES:
        await call.answer(
            "❌ Неизвестный тип босса.",
            show_alert=True
        )
        return

    await call.answer()

    boss = active_boss(boss_type)

    type_names = {
        "daily": "🔥 ЕЖЕДНЕВНЫЙ БОСС",
        "weekly": "⚡ НЕДЕЛЬНЫЙ БОСС",
        "monthly": "☠️ ЕЖЕМЕСЯЧНЫЙ БОСС",
    }

    title = type_names.get(
        boss_type,
        "👹 МИРОВОЙ БОСС"
    )

    # =========================================================
    # БОСС НЕ АКТИВЕН
    # =========================================================

    if not boss:
        spec = BOSS_TYPES[boss_type]

        text = (
            f"{title}\n\n"
            "📭 <b>Сейчас не активен</b>\n\n"
            f"❤️ Максимальное HP: "
            f"<b>{fmt(spec['hp'])}</b>\n"
            f"💰 Призовой фонд: "
            f"<b>{fmt(spec['reward'])} DCR</b>\n\n"
            "⏳ Следующее появление произойдёт автоматически."
        )

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔄 Обновить",
                        callback_data=f"boss_type:{boss_type}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ К боссам",
                        callback_data="boss"
                    )
                ],
            ]
        )

        await safe_edit(
            call.message,
            text,
            kb
        )
        return

    # =========================================================
    # БОСС АКТИВЕН
    # =========================================================

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚔️ Атаковать босса",
                    callback_data=f"boss_attack:{boss['id']}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Обновить",
                    callback_data=f"boss_type:{boss_type}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ К боссам",
                    callback_data="boss"
                )
            ],
        ]
    )

    await safe_edit(
        call.message,
        boss_screen(
            call.from_user.id,
            boss_type
        ),
        kb
    )


async def apply_weapon_effect_to_boss(bot, boss_id, user_id, damage):
    eq = get_equipment(user_id)
    if not eq or not eq["weapon_key"]:
        return ""
    effect = WEAPON_EFFECTS.get(eq["weapon_key"])
    if not effect or random.random() > float(effect.get("chance", 0)):
        return ""
    effect_type = effect["type"]
    extra = int(effect["damage"])
    hp_row = db_execute("SELECT hp FROM world_bosses WHERE id=? AND active=1", (boss_id,), fetchone=True)
    if not hp_row:
        return ""
    new_hp = max(0, int(hp_row["hp"]) - extra)
    db_execute("UPDATE world_bosses SET hp=? WHERE id=?", (new_hp, boss_id))
    icon = "🔥" if effect_type == "burn" else "🩸"
    return f"{icon} {effect_type.capitalize()} сработало: -{extra} HP"


@dp.callback_query(F.data.startswith("boss_attack:"))
async def boss_attack_callback(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id

    try:
        boss_id = int(call.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await call.answer("❌ Ошибка босса.", show_alert=True)
        return

    boss = db_execute(
        "SELECT * FROM world_bosses WHERE id=? AND active=1",
        (boss_id,),
        fetchone=True
    )

    if not boss:
        await call.answer(
            "👹 Этот босс уже не активен.",
            show_alert=True
        )

        await safe_edit(
            call.message,
            boss_screen(user_id),
            InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔄 Обновить",
                        callback_data="boss"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ Назад",
                        callback_data="game"
                    )
                ],
            ])
        )
        return

    stats = player_combat_stats(user_id)

    damage = random.randint(
        int(stats["attack_min"]),
        int(stats["attack_max"])
    )
    boost = db_execute("SELECT countdown,event_type FROM pve_battle_events WHERE user_id=? AND active=1", (user_id,), fetchone=True)
    if boost and boost["event_type"] == "damage_boost":
        damage = max(1, int(damage * 1.05))
        left = max(0, int(boost["countdown"]) - 1)
        db_execute("UPDATE pve_battle_events SET countdown=?,active=? WHERE user_id=?", (left, 0 if left == 0 else 1, user_id))

    hp = max(
        0,
        int(boss["hp"]) - damage
    )

    db_execute(
        "UPDATE world_bosses SET hp=? WHERE id=?",
        (hp, boss_id)
    )
    effect_text = await apply_weapon_effect_to_boss(bot, boss_id, user_id, damage)
    boss_after_effect = db_execute("SELECT hp FROM world_bosses WHERE id=?", (boss_id,), fetchone=True)
    if boss_after_effect:
        hp = int(boss_after_effect["hp"])

    db_execute(
        """
        INSERT INTO boss_damage(boss_id,user_id,damage)
        VALUES(?,?,?)
        ON CONFLICT(boss_id,user_id)
        DO UPDATE SET damage=damage+excluded.damage
        """,
        (boss_id, user_id, damage)
    )

    # Обычный Battle Pass XP за атаку босса
    add_bp_xp(
        user_id,
        max(5, damage // 2)
    )

    # Босс побеждён
    if hp <= 0:

        total_row = db_execute(
            """
            SELECT COALESCE(SUM(damage),0) AS s
            FROM boss_damage
            WHERE boss_id=?
            """,
            (boss_id,),
            fetchone=True
        )

        total = int(total_row["s"] or 0)

        participants = db_execute(
            """
            SELECT user_id, damage
            FROM boss_damage
            WHERE boss_id=?
            ORDER BY damage DESC
            """,
            (boss_id,),
            fetchall=True
        )

        for r in participants:
            player_damage = int(r["damage"])

            if total > 0:
                reward = int(
                    int(boss["reward_pool"])
                    * player_damage
                    / total
                )
            else:
                reward = 0

            if reward > 0:
                add_dcr(
                    r["user_id"],
                    reward,
                    f"Мировой босс: {boss['name']}"
                )

                db_execute(
                    """
                    INSERT OR REPLACE INTO boss_claims
                    (boss_id,user_id,reward)
                    VALUES(?,?,?)
                    """,
                    (
                        boss_id,
                        r["user_id"],
                        reward
                    )
                )

        db_execute(
            """
            UPDATE world_bosses
            SET active=0, hp=0
            WHERE id=?
            """,
            (boss_id,)
        )

        await publish_news(
            bot,
            f"🏆 <b>{esc(boss['name'])} повержен!</b>\n\n"
            "💰 Награды распределены между участниками пропорционально нанесённому урону.\n"
            f"👑 Последний удар: <b>{esc(pvp_player_name(user_id) if 'pvp_player_name' in globals() else str(user_id))}</b>"
        )

        await call.answer(
            "🏆 Босс повержен!"
        )

    else:
        feedback = f"⚔️ -{damage} HP"
        if effect_text:
            feedback += f"\n{effect_text}"
        await call.answer(feedback)

    # Получаем актуальное состояние босса
    updated_boss = db_execute(
        "SELECT * FROM world_bosses WHERE id=?",
        (boss_id,),
        fetchone=True
    )

    if updated_boss and int(updated_boss["active"]) == 1:

        await safe_edit(
            call.message,
            boss_screen(user_id, updated_boss["boss_type"]),
            InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⚔️ Атаковать босса",
                        callback_data=f"boss_attack:{boss_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🔄 Обновить",
                        callback_data=f"boss_view:{boss_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ Назад",
                        callback_data="boss"
                    )
                ],
            ])
        )

    else:

        await safe_edit(
            call.message,
            "🏆 <b>БОСС ПОВЕРЖЕН!</b>\n\n"
            f"👹 {esc(boss['name'])}\n\n"
            "💰 Награды распределены между участниками "
            "пропорционально нанесённому урону.",
            InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="👹 К мировым боссам",
                        callback_data="boss"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ Назад",
                        callback_data="game"
                    )
                ],
            ])
        )

@dp.callback_query(F.data.startswith("boss_view:"))
async def boss_view_callback(call: CallbackQuery):
    try:
        boss_id = int(call.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await call.answer("❌ Ошибка босса.", show_alert=True)
        return

    boss = db_execute(
        """
        SELECT *
        FROM world_bosses
        WHERE id=? AND active=1
        """,
        (boss_id,),
        fetchone=True
    )

    if not boss:
        await call.answer(
            "👹 Этот босс уже не активен.",
            show_alert=True
        )

        await safe_edit(
            call.message,
            boss_screen(call.from_user.id),
            InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="👹 К мировым боссам",
                        callback_data="boss"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ Назад",
                        callback_data="game"
                    )
                ],
            ])
        )
        return

    await call.answer()

    boss_type = boss["boss_type"] or "daily"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="⚔️ Атаковать босса",
                callback_data=f"boss_attack:{boss_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔄 Обновить",
                callback_data=f"boss_view:{boss_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ К боссам",
                callback_data="boss"
            )
        ],
    ])

    await safe_edit(
        call.message,
        boss_screen(
            call.from_user.id,
            boss_type
        ),
        kb
    )
    
# ---------------- CLAN MANAGEMENT ----------------

CLAN_LEADERS = {"leader", "deputy"}

def clan_can_manage(user_id, clan_id):
    row = db_execute("SELECT role FROM clan_members WHERE clan_id=? AND user_id=?", (clan_id,user_id), fetchone=True)
    return bool(row and row["role"] in ("leader", "deputy", "admin"))


def clan_full_text(user_id):
    p=get_player(user_id)
    if not p or not p["clan_id"]:
        return "🏰 <b>КЛАНЫ</b>\n\nТы пока не состоишь в клане."
    c=clan_info(p["clan_id"]); members=clan_members(p["clan_id"])
    text=f"🏰 <b>{esc(c['name'])}</b>\n\n👑 Глава: <code>{c['leader_id']}</code>\n👥 Участников: <b>{len(members)}</b>\n⚡ Мощность: <b>{fmt(clan_power(p['clan_id']))}</b>\n\n"
    for m in members:
        text += f"• {esc(m['first_name'] or m['username'] or m['user_id'])} — {esc(m['role'])} — Lv.{m['level']}\n"
    return text


@dp.callback_query(F.data == "clan_manage")
async def clan_manage_callback(call: CallbackQuery):
    p=get_player(call.from_user.id)
    if not p or not p["clan_id"] or not clan_can_manage(call.from_user.id,p["clan_id"]):
        await call.answer("Только глава или заместитель.",show_alert=True); return
    kb=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Пригласить",callback_data="clan_invite_help")],
        [InlineKeyboardButton(text="👥 Участники",callback_data="clan_members")],
        [InlineKeyboardButton(text="⚔️ Турнир 5×5",callback_data="clan_tournament")],
        [InlineKeyboardButton(text="⬅️ Назад",callback_data="clans")],
    ])
    await call.answer(); await safe_edit(call.message,clan_full_text(call.from_user.id),kb)


@dp.callback_query(F.data == "clan_invite_help")
async def clan_invite_help(call: CallbackQuery):
    await call.answer()
    await call.message.answer("Используй: <code>/clan_invite USER_ID</code>")


@dp.message(Command("clan_invite"))
async def clan_invite_command(message: Message, bot: Bot):
    p=ensure_player(message.from_user)
    if not p["clan_id"] or not clan_can_manage(message.from_user.id,p["clan_id"]): return
    parts=message.text.split()
    if len(parts)!=2 or not parts[1].isdigit(): await message.answer("Использование: /clan_invite USER_ID"); return
    target=int(parts[1]); tp=get_player(target)
    if not tp: await message.answer("Игрок не найден."); return
    if tp["clan_id"]: await message.answer("Игрок уже состоит в клане."); return
    cid=p["clan_id"]
    db_execute("INSERT INTO clan_invites(clan_id,inviter_id,target_id,invitee_id,status,created_at) VALUES(?,?,?,?,?,?)",(cid,message.from_user.id,target,target,"pending",now_iso()))
    c=clan_info(cid)
    try:
        await bot.send_message(target,f"🏰 Тебя приглашают в клан <b>{esc(c['name'])}</b>.",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Принять",callback_data=f"clan_invite_accept:{cid}"),InlineKeyboardButton(text="❌ Отклонить",callback_data=f"clan_invite_decline:{cid}")]]))
    except Exception: pass
    await message.answer("✅ Приглашение отправлено.")


@dp.callback_query(F.data.startswith("clan_invite_accept:"))
async def clan_invite_accept(call: CallbackQuery):
    cid=int(call.data.split(":")[1]); p=get_player(call.from_user.id)
    inv=db_execute("SELECT id FROM clan_invites WHERE clan_id=? AND target_id=? AND status='pending' ORDER BY id DESC LIMIT 1",(cid,call.from_user.id),fetchone=True)
    if not inv or p["clan_id"]: await call.answer("Приглашение недействительно.",show_alert=True); return
    db_execute("UPDATE clan_invites SET status='accepted' WHERE id=?",(inv["id"],))
    db_execute("INSERT OR IGNORE INTO clan_members(clan_id,user_id,role) VALUES(?,?,?)",(cid,call.from_user.id,"member"))
    db_execute("UPDATE players SET clan_id=? WHERE user_id=?",(cid,call.from_user.id))
    await call.answer("🏰 Ты вступил в клан!"); await safe_edit(call.message,clan_full_text(call.from_user.id),clan_menu(call.from_user.id))


@dp.callback_query(F.data.startswith("clan_invite_decline:"))
async def clan_invite_decline(call: CallbackQuery):
    cid=int(call.data.split(":")[1]); db_execute("UPDATE clan_invites SET status='declined' WHERE clan_id=? AND target_id=? AND status='pending'",(cid,call.from_user.id)); await call.answer("Приглашение отклонено."); await safe_edit(call.message,"❌ Приглашение отклонено.",other_menu(call.from_user.id))


# ---------------- SIMPLE FRIENDS ----------------

@dp.callback_query(F.data == "friends")
async def friends_callback(call: CallbackQuery):
    rows=db_execute("SELECT friend_id FROM friends WHERE user_id=?",(call.from_user.id,),fetchall=True)
    text="🤝 <b>ДРУЗЬЯ</b>\n\n"
    if not rows: text += "Список друзей пуст.\nИспользуй /friend USER_ID для добавления."
    for r in rows: text += f"• <code>{r['friend_id']}</code>\n"
    await call.answer(); await safe_edit(call.message,text,other_menu(call.from_user.id))


@dp.message(Command("friend"))
async def friend_command(message: Message):
    parts=message.text.split()
    if len(parts)!=2 or not parts[1].isdigit(): await message.answer("Использование: /friend USER_ID"); return
    target=int(parts[1])
    if target==message.from_user.id or not get_player(target): await message.answer("Игрок не найден."); return
    db_execute("INSERT OR IGNORE INTO friends(user_id,friend_id,created_at) VALUES(?,?,?)",(message.from_user.id,target,now_iso()))
    db_execute("INSERT OR IGNORE INTO friends(user_id,friend_id,created_at) VALUES(?,?,?)",(target,message.from_user.id,now_iso()))
    await message.answer("🤝 Друг добавлен.")


# ---------------- MARKET ----------------

class MarketState(StatesGroup):
    waiting_price = State()

MARKET_CATEGORIES = {
    "weapon": "⚔️ Оружие",
    "armor": "🛡️ Броня",
    "pet": "🐾 Питомцы",
    "ability": "🌌 Способности",
    "material": "🧩 Частицы",
    "case": "🎁 Кейсы",
}

MARKET_COMMISSION = 0.05


def market_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚔️ Оружие", callback_data="market_cat:weapon"), InlineKeyboardButton(text="🛡️ Броня", callback_data="market_cat:armor")],
        [InlineKeyboardButton(text="🐾 Питомцы", callback_data="market_cat:pet"), InlineKeyboardButton(text="🌌 Способности", callback_data="market_cat:ability")],
        [InlineKeyboardButton(text="🧩 Частицы", callback_data="market_cat:material"), InlineKeyboardButton(text="🎁 Кейсы", callback_data="market_cat:case")],
        [InlineKeyboardButton(text="➕ Выставить предмет", callback_data="market_sell")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="other")],
    ])


def market_category_keyboard(category):
    rows = []
    if category == "case":
        rows.append([InlineKeyboardButton(text="🎁 Оружейный кейс — 100 💎", callback_data="case:weapon")])
    else:
        lots = db_execute("""
            SELECT l.*, i.name
            FROM market_lots_v2 l
            JOIN items i ON i.item_id=l.item_id
            WHERE l.active=1 AND i.item_type=?
            ORDER BY l.id DESC LIMIT 20
        """, (category,), fetchall=True)
        for l in lots:
            price = int(l["price_dcr"] or l["price_crystals"] or 0)
            currency = "DCR" if l["price_dcr"] else "💎"
            rows.append([InlineKeyboardButton(text=f"🛒 #{l['id']} • {l['name']} ×{l['quantity']} — {fmt(price)} {currency}", callback_data=f"market_buy:{l['id']}")])
        if not lots:
            rows.append([InlineKeyboardButton(text="📭 Нет предложений", callback_data="noop")])
    rows.append([InlineKeyboardButton(text="➕ Выставить предмет", callback_data=f"market_sell_cat:{category}")])
    rows.append([InlineKeyboardButton(text="⬅️ К категориям", callback_data="market")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@dp.callback_query(F.data == "market")
async def market_callback(call: CallbackQuery):
    await call.answer()
    await safe_edit(call.message, "🛒 <b>ЖИВОЙ РЫНОК</b>\n\nВыбери категорию:", market_main_keyboard())


@dp.callback_query(F.data.startswith("market_cat:"))
async def market_category_callback(call: CallbackQuery):
    await call.answer()
    category = call.data.split(":", 1)[1]
    title = MARKET_CATEGORIES.get(category, "Рынок")
    await safe_edit(call.message, f"🛒 <b>{title.upper()}</b>\n\nАктивные предложения:", market_category_keyboard(category))


@dp.callback_query(F.data == "market_sell")
async def market_sell_callback(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()
    rows = []
    for category, label in MARKET_CATEGORIES.items():
        if category == "case":
            continue
        rows.append([InlineKeyboardButton(text=label, callback_data=f"market_sell_cat:{category}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="market")])
    await safe_edit(call.message, "➕ <b>ВЫСТАВИТЬ ПРЕДМЕТ</b>\n\nВыбери категорию предмета:", InlineKeyboardMarkup(inline_keyboard=rows))


@dp.callback_query(F.data.startswith("market_sell_cat:"))
async def market_sell_category_callback(call: CallbackQuery, state: FSMContext):
    await call.answer()
    category = call.data.split(":", 1)[1]
    items = [x for x in get_inventory(call.from_user.id) if x["item_type"] == category and int(x["quantity"]) > 0]
    rows = []
    for item in items:
        rows.append([InlineKeyboardButton(text=f"{item['name']} ×{item['quantity']}", callback_data=f"market_sell_item:{item['item_key']}")])
    if not rows:
        rows.append([InlineKeyboardButton(text="📭 В этой категории нет предметов", callback_data="noop")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="market_sell")])
    await safe_edit(call.message, "📦 <b>ВЫБОР ПРЕДМЕТА</b>\n\nНажми на предмет, который хочешь выставить:", InlineKeyboardMarkup(inline_keyboard=rows))


@dp.callback_query(F.data.startswith("market_sell_item:"))
async def market_sell_item_callback(call: CallbackQuery, state: FSMContext):
    await call.answer()
    key = call.data.split(":", 1)[1]
    item = db_execute("SELECT * FROM items WHERE item_key=?", (key,), fetchone=True)
    inv = db_execute("SELECT quantity FROM inventory WHERE user_id=? AND item_id=?", (call.from_user.id, item["item_id"] if item else -1), fetchone=True)
    if not item or not inv or int(inv["quantity"]) <= 0:
        await call.answer("Предмет больше недоступен.", show_alert=True)
        return
    await state.set_state(MarketState.waiting_price)
    await state.update_data(
        item_key=key,
        item_id=int(item["item_id"]),
        item_name=item["name"],
        screen_chat_id=call.message.chat.id,
        screen_message_id=call.message.message_id,
    )
    await safe_edit(call.message, f"💰 <b>ЦЕНА ПРЕДМЕТА</b>\n\n{esc(item['name'])}\n\nОтправь одним сообщением цену в DCR.", InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Отмена", callback_data="market")]]))


@dp.message(MarketState.waiting_price)
async def market_price_message(message: Message, state: FSMContext):
    data = await state.get_data()
    try:
        price = int(message.text.strip())
    except (ValueError, AttributeError):
        await message.delete()
        return
    await message.delete()
    if price <= 0:
        await message.answer("❌ Цена должна быть больше нуля.")
        return
    item = db_execute("SELECT * FROM items WHERE item_id=?", (data["item_id"],), fetchone=True)
    inv = db_execute("SELECT quantity FROM inventory WHERE user_id=? AND item_id=?", (message.from_user.id, data["item_id"]), fetchone=True)
    if not item or not inv or int(inv["quantity"]) <= 0:
        await state.clear()
        return
    await state.update_data(price=price)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, выставить", callback_data="market_sell_confirm")],
        [InlineKeyboardButton(text="❌ Нет", callback_data="market_sell_cancel")]
    ])
    text = (
        f"📋 <b>ПОДТВЕРЖДЕНИЕ</b>\n\n"
        f"Предмет: <b>{esc(data['item_name'])}</b>\n"
        f"Цена: <b>{fmt(price)} DCR</b>\n"
        f"Комиссия рынка: <b>{int(price * MARKET_COMMISSION)} DCR</b>\n"
        f"Получишь после продажи: <b>{fmt(price - int(price * MARKET_COMMISSION))} DCR</b>\n\n"
        "Выставить предмет?"
    )
    screen_chat_id = data.get("screen_chat_id")
    screen_message_id = data.get("screen_message_id")
    if screen_chat_id and screen_message_id:
        try:
            await message.bot.edit_message_text(
                chat_id=screen_chat_id,
                message_id=screen_message_id,
                text=text,
                reply_markup=kb
            )
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=kb)


@dp.callback_query(F.data == "market_sell_cancel")
async def market_sell_cancel_callback(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()
    await safe_edit(call.message, "🛒 <b>ЖИВОЙ РЫНОК</b>\n\nВыставление отменено.", market_main_keyboard())


@dp.callback_query(F.data == "market_sell_confirm")
async def market_sell_confirm_callback(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    item = db_execute("SELECT * FROM items WHERE item_id=?", (data.get("item_id", 0),), fetchone=True)
    inv = db_execute("SELECT quantity FROM inventory WHERE user_id=? AND item_id=?", (call.from_user.id, data.get("item_id", 0)), fetchone=True)
    price = int(data.get("price", 0))
    if not item or not inv or int(inv["quantity"]) <= 0 or price <= 0:
        await state.clear()
        await call.answer("Предмет уже недоступен.", show_alert=True)
        return
    remove_item(call.from_user.id, item["item_key"], 1)
    lid = db_insert("INSERT INTO market_lots_v2(seller_id,item_id,quantity,price_dcr,price_crystals,active,created_at) VALUES(?,?,?,?,?,?,?)", (call.from_user.id, item["item_id"], 1, price, 0, 1, now_iso()))
    await state.clear()
    await call.answer("✅ Предмет выставлен!")
    await safe_edit(call.message, f"🛒 <b>ЛОТ #{lid} ВЫСТАВЛЕН</b>\n\n{esc(item['name'])}\n💰 {fmt(price)} DCR\n\nПокупатель получит предмет, а с продажи будет удержана комиссия рынка.", market_category_keyboard(item["item_type"]))


@dp.callback_query(F.data.startswith("market_buy:"))
async def market_buy_callback(call: CallbackQuery):
    lid = int(call.data.split(":", 1)[1])
    lot = db_execute("SELECT l.*,i.item_key,i.name,i.item_type FROM market_lots_v2 l JOIN items i ON i.item_id=l.item_id WHERE l.id=? AND l.active=1", (lid,), fetchone=True)
    if not lot:
        await call.answer("Лот уже продан или снят.", show_alert=True)
        return
    if int(lot["seller_id"]) == call.from_user.id:
        await call.answer("Нельзя купить собственный лот.", show_alert=True)
        return
    price = int(lot["price_dcr"] or 0)
    buyer = get_player(call.from_user.id)
    if not buyer or int(buyer["dcr"]) < price:
        await call.answer("Недостаточно DCR.", show_alert=True)
        return
    commission = max(1, int(price * MARKET_COMMISSION))
    net = price - commission
    changed = db_execute("UPDATE market_lots_v2 SET active=0 WHERE id=? AND active=1", (lid,))
    if not changed:
        await call.answer("Лот уже купили.", show_alert=True)
        return
    add_dcr(call.from_user.id, -price, f"Покупка на рынке #{lid}")
    add_dcr(lot["seller_id"], net, f"Продажа на рынке #{lid} (-{commission} DCR комиссия)")
    add_item(call.from_user.id, lot["item_key"], int(lot["quantity"]))
    await call.answer("✅ Покупка завершена!")
    await safe_edit(call.message, f"✅ <b>ПОКУПКА ЗАВЕРШЕНА</b>\n\n{esc(lot['name'])} ×{lot['quantity']} получен в инвентарь.\n💰 Списано: {fmt(price)} DCR", market_category_keyboard(lot["item_type"]))


# ---------------- TRADE ----------------

@dp.message(Command("trade"))
async def trade_command(message: Message):
    parts=message.text.split()
    if len(parts)!=4 or not parts[1].isdigit() or not parts[3].isdigit(): await message.answer("Использование: /trade USER_ID ITEM_KEY QUANTITY"); return
    receiver=int(parts[1]); key=parts[2]; qty=int(parts[3]); sender=message.from_user.id
    item=db_execute("SELECT item_id,name FROM items WHERE item_key=?",(key,),fetchone=True)
    if not item or receiver==sender or not get_player(receiver) or qty<=0: await message.answer("Данные сделки неверны."); return
    inv=db_execute("SELECT quantity FROM inventory WHERE user_id=? AND item_id=?",(sender,item["item_id"]),fetchone=True)
    if not inv or int(inv["quantity"])<qty: await message.answer("У тебя нет нужного количества предмета."); return
    tid=db_insert("INSERT INTO trades(sender_id,receiver_id,sender_item_id,sender_qty,status,created_at) VALUES(?,?,?,?,?,?)",(sender,receiver,item["item_id"],qty,"pending",now_iso()))
    await message.answer(f"🤝 Предложение сделки #{tid}: {esc(item['name'])} ×{qty}. Ожидается подтверждение получателя.")


# ---------------- ADMIN ECONOMY / XP ----------------

@dp.message(Command("give_xp"))
async def give_xp_command(message: Message):
    if admin_role(message.from_user.id)!="owner": return
    parts=message.text.split()
    if len(parts)!=3 or not parts[1].isdigit() or not parts[2].lstrip('-').isdigit(): await message.answer("Использование: /give_xp USER_ID AMOUNT"); return
    target=int(parts[1]); amount=int(parts[2])
    if not get_player(target): await message.answer("Игрок не найден."); return
    add_xp(target,amount); admin_log(message.from_user.id,"give_xp",target,str(amount)); await message.answer("✅ XP изменён.")


@dp.message(Command("take_dcr"))
async def take_dcr_command(message: Message):
    if admin_role(message.from_user.id)!="owner": return
    parts=message.text.split();
    if len(parts)!=3 or not parts[1].isdigit() or not parts[2].isdigit(): await message.answer("Использование: /take_dcr USER_ID AMOUNT"); return
    target=int(parts[1]); amount=int(parts[2]); p=get_player(target)
    if not p: await message.answer("Игрок не найден."); return
    amount=min(amount,int(p["dcr"])); add_dcr(target,-amount,f"Изъятие администратором {message.from_user.id}"); admin_log(message.from_user.id,"take_dcr",target,str(amount)); await message.answer("✅ DCR изъяты.")


@dp.message(Command("take_crystals"))
async def take_crystals_command(message: Message):
    if admin_role(message.from_user.id)!="owner": return
    parts=message.text.split();
    if len(parts)!=3 or not parts[1].isdigit() or not parts[2].isdigit(): await message.answer("Использование: /take_crystals USER_ID AMOUNT"); return
    target=int(parts[1]); amount=int(parts[2]); p=get_player(target)
    if not p: await message.answer("Игрок не найден."); return
    amount=min(amount,int(p["crystals"])); add_crystals(target,-amount,f"Изъятие администратором {message.from_user.id}"); admin_log(message.from_user.id,"take_crystals",target,str(amount)); await message.answer("✅ Кристаллы изъяты.")



# ============================================================
# DOMINION 8.0 — CRAFT / UPGRADE / CASES / CASINO / ADMIN UI
# ============================================================

class AdminUIState(StatesGroup):
    waiting_user = State()
    waiting_amount = State()

class CasinoState(StatesGroup):
    waiting_bet = State()


def particle_amount(user_id, key):
    row = db_execute("SELECT quantity FROM inventory i JOIN items x ON x.item_id=i.item_id WHERE i.user_id=? AND x.item_key=?", (user_id, key), fetchone=True)
    return int(row["quantity"]) if row else 0


@dp.callback_query(F.data == "craft")
async def craft_callback(call: CallbackQuery):
    await call.answer()
    text = (
        "🔨 <b>КРАФТ</b>\n\n"
        "🧪 Зелье опустошения — 30 частиц бездны\n"
        "❤️ Зелье регенерации — 15 частиц леса\n"
        "👻 Зелье невидимости — 20 частиц пещеры\n\n"
        "Частицы редкие: добываются только за победы в PvE."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🕳️ Опустошение", callback_data="craft:potion_void")],
        [InlineKeyboardButton(text="❤️ Регенерация", callback_data="craft:potion_regen")],
        [InlineKeyboardButton(text="👻 Невидимость", callback_data="craft:potion_invisibility")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="other")],
    ])
    await safe_edit(call.message, text, kb)


@dp.callback_query(F.data.startswith("craft:"))
async def craft_item_callback(call: CallbackQuery):
    recipe = call.data.split(":", 1)[1]
    recipes = {
        "potion_void": ("abyss_particle", 30, "potion_void"),
        "potion_regen": ("forest_particle", 15, "potion_regen"),
        "potion_invisibility": ("cave_particle", 20, "potion_invisibility"),
    }
    if recipe not in recipes:
        await call.answer("Рецепт не найден.", show_alert=True)
        return
    material, cost, reward = recipes[recipe]
    have = particle_amount(call.from_user.id, material)
    if have < cost:
        await call.answer(f"Не хватает частиц: {have}/{cost}.", show_alert=True)
        return
    remove_item(call.from_user.id, material, cost)
    add_item(call.from_user.id, reward, 1)
    db_execute("INSERT INTO craft_log(user_id,recipe_key,created_at) VALUES(?,?,?)", (call.from_user.id, recipe, now_iso()))
    await call.answer("✅ Создано!")
    await safe_edit(call.message, "🔨 <b>КРАФТ ЗАВЕРШЁН</b>\n\nПредмет добавлен в инвентарь.", InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔨 Ещё крафт", callback_data="craft")],[InlineKeyboardButton(text="⬅️ Назад", callback_data="other")]]))


@dp.callback_query(F.data == "upgrade")
async def upgrade_callback(call: CallbackQuery):
    await call.answer()
    items = [x for x in get_inventory(call.from_user.id) if x["item_type"] in ("weapon", "armor", "shield", "ability")]
    rows = []
    for x in items[:30]:
        rows.append([InlineKeyboardButton(text=f"⬆️ {x['name']} ×{x['quantity']}", callback_data=f"upgrade_item:{x['item_key']}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="other")])
    await safe_edit(call.message, "⬆️ <b>УЛУЧШЕНИЕ</b>\n\nКаждый уровень требует 100 частиц соответствующего типа. Улучшение небольшое, чтобы экономика не ломалась.", InlineKeyboardMarkup(inline_keyboard=rows))


@dp.callback_query(F.data.startswith("upgrade_item:"))
async def upgrade_item_callback(call: CallbackQuery):
    key = call.data.split(":", 1)[1]
    item = db_execute("SELECT * FROM items WHERE item_key=?", (key,), fetchone=True)
    if not item:
        await call.answer("Предмет не найден.", show_alert=True)
        return
    material = item["particle_type"] or "forest_particle"
    have = particle_amount(call.from_user.id, material)
    if have < 100:
        await call.answer(f"Нужно 100 частиц. Сейчас: {have}.", show_alert=True)
        return
    remove_item(call.from_user.id, material, 100)
    db_execute("INSERT INTO player_upgrades(user_id,item_id,level) VALUES(?,?,1) ON CONFLICT(user_id,item_id) DO UPDATE SET level=level+1", (call.from_user.id, item["item_id"]))
    level = db_execute("SELECT level FROM player_upgrades WHERE user_id=? AND item_id=?", (call.from_user.id, item["item_id"]), fetchone=True)["level"]
    await call.answer("⬆️ Улучшено!")
    await safe_edit(call.message, f"⬆️ <b>{esc(item['name'])}</b>\n\nНовый уровень улучшения: <b>+{level}</b>\n🧩 Потрачено: 100 частиц.", InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬆️ Улучшить ещё", callback_data=f"upgrade_item:{key}")],[InlineKeyboardButton(text="⬅️ К улучшениям", callback_data="upgrade")]]))


@dp.callback_query(F.data == "cases")
async def cases_callback(call: CallbackQuery):
    await shop_cases_callback(call)


@dp.callback_query(F.data == "case:weapon")
async def weapon_case_callback(call: CallbackQuery):
    p = get_player(call.from_user.id)
    if not p or int(p["crystals"]) < 100:
        await call.answer("Нужно 100 💎.", show_alert=True)
        return
    add_crystals(call.from_user.id, -100, "Открытие оружейного кейса")
    pool = [
        ("rusty_sword", 40), ("iron_sword", 28), ("hunter_blade", 18),
        ("void_edge", 9), ("mythic_fang", 4), ("demonic_reaper", 1)
    ]
    roll = random.randint(1, 100)
    acc = 0
    reward = pool[-1][0]
    for key, chance in pool:
        acc += chance
        if roll <= acc:
            reward = key
            break
    add_item(call.from_user.id, reward, 1)
    db_execute("INSERT INTO case_openings(user_id,case_key,reward_key,created_at) VALUES(?,?,?,?)", (call.from_user.id, "weapon", reward, now_iso()))
    item = db_execute("SELECT name FROM items WHERE item_key=?", (reward,), fetchone=True)
    await call.answer("🎁 Кейс открыт!")
    await safe_edit(call.message, f"🎁 <b>ОРУЖЕЙНЫЙ КЕЙС</b>\n\nВыпало:\n⚔️ <b>{esc(item['name'])}</b>\n\n💎 Потрачено: 100", InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎁 Открыть ещё", callback_data="case:weapon")],[InlineKeyboardButton(text="⬅️ К кейсам", callback_data="shop_cases")]]))


@dp.callback_query(F.data == "casino")
async def casino_callback(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Играть за DCR", callback_data="casino_currency:dcr")],
        [InlineKeyboardButton(text="💎 Играть за кристаллы", callback_data="casino_currency:crystals")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="other")],
    ])
    await safe_edit(call.message, "🎰 <b>КАЗИНО DOMINION</b>\n\nТри барабана. 7️⃣7️⃣7️⃣ — главный джекпот.\n\nВыбери валюту ставки:", kb)


@dp.callback_query(F.data.startswith("casino_currency:"))
async def casino_currency_callback(call: CallbackQuery, state: FSMContext):
    currency = call.data.split(":", 1)[1]
    await state.set_state(CasinoState.waiting_bet)
    await state.update_data(
        currency=currency,
        screen_chat_id=call.message.chat.id,
        screen_message_id=call.message.message_id,
    )
    await call.answer()
    label = "DCR" if currency == "dcr" else "💎 кристаллов"
    await safe_edit(call.message, f"🎰 <b>СТАВКА</b>\n\nВведи сумму ставки в {label}.", InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Отмена", callback_data="casino")]]))


@dp.message(CasinoState.waiting_bet)
async def casino_bet_message(message: Message, state: FSMContext):
    data = await state.get_data()
    try:
        bet = int((message.text or "").strip())
    except (ValueError, AttributeError):
        try:
            await message.delete()
        except Exception:
            pass
        return

    try:
        await message.delete()
    except Exception:
        pass

    if bet <= 0:
        screen_chat_id = data.get("screen_chat_id")
        screen_message_id = data.get("screen_message_id")
        if screen_chat_id and screen_message_id:
            try:
                await message.bot.edit_message_text(
                    chat_id=screen_chat_id,
                    message_id=screen_message_id,
                    text="❌ <b>Неверная ставка</b>\n\nСтавка должна быть больше нуля.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="casino")]])
                )
                return
            except Exception:
                pass
        return

    currency = data.get("currency", "dcr")
    p = get_player(message.from_user.id)
    if not p:
        await state.clear()
        return
    balance = int(p["dcr"] if currency == "dcr" else p["crystals"])
    if bet > balance:
        screen_chat_id = data.get("screen_chat_id")
        screen_message_id = data.get("screen_message_id")
        text = "❌ <b>Недостаточно средств.</b>"
        if screen_chat_id and screen_message_id:
            try:
                await message.bot.edit_message_text(
                    chat_id=screen_chat_id,
                    message_id=screen_message_id,
                    text=text,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="casino")]])
                )
                return
            except Exception:
                pass
        await state.clear()
        return

    screen_chat_id = data.get("screen_chat_id", message.chat.id)
    screen_message_id = data.get("screen_message_id")
    await state.clear()

    if currency == "dcr":
        add_dcr(message.from_user.id, -bet, "Казино")
    else:
        add_crystals(message.from_user.id, -bet, "Казино")

    reels = ["🍒", "🍋", "🔔", "💎", "7️⃣", "⭐"]
    if random.random() < 0.015:
        final = ["7️⃣", "7️⃣", "7️⃣"]
    else:
        final = [random.choice(reels) for _ in range(3)]
        if final[0] != final[1] and final[1] != final[2] and final[0] != final[2] and random.random() < 0.18:
            final[1] = final[0]

    target = None
    if screen_chat_id and screen_message_id:
        target = (screen_chat_id, screen_message_id)

    async def render(text, kb=None):
        if target:
            try:
                await message.bot.edit_message_text(chat_id=target[0], message_id=target[1], text=text, reply_markup=kb)
                return True
            except Exception:
                return False
        return False

    await render("🎰 <b>СТАВКА ПРИНЯТА</b>\n\n⏳ Барабан запускается...")
    for _ in range(6):
        frame = [random.choice(reels) for _ in range(3)]
        if not await render("🎰 <b>КРУТИМ...</b>\n\n" + " │ ".join(frame)):
            break
        await asyncio.sleep(0.45)

    symbols = " │ ".join(final)
    if final == ["7️⃣", "7️⃣", "7️⃣"]:
        mult = 10.0
    elif final[0] == final[1] == final[2]:
        mult = 4.0
    elif final[0] == final[1] or final[1] == final[2] or final[0] == final[2]:
        mult = 1.5
    else:
        mult = 0.0

    result = int(bet * mult)
    if result:
        if currency == "dcr":
            add_dcr(message.from_user.id, result, "Выигрыш в казино")
        else:
            add_crystals(message.from_user.id, result, "Выигрыш в казино")

    db_execute(
        "INSERT INTO casino_log(user_id,currency,bet,result,multiplier,symbols,created_at) VALUES(?,?,?,?,?,?,?)",
        (message.from_user.id, currency, bet, result, mult, symbols, now_iso())
    )

    title = "💰 ДЖЕКПОТ!" if mult >= 10 else ("🎉 ВЫИГРЫШ!" if result else "💀 ПРОИГРЫШ")
    label = "DCR" if currency == "dcr" else "💎"
    final_text = (
        f"🎰 <b>{title}</b>\n\n{symbols}\n\n"
        f"💵 Ставка: <b>{fmt(bet)} {label}</b>\n"
        f"📈 Множитель: <b>x{mult:g}</b>\n"
        f"🏆 Результат: <b>{fmt(result)} {label}</b>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 Ещё раз", callback_data="casino")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="other")]
    ])
    if not await render(final_text, kb):
        await message.answer(final_text, reply_markup=kb)


@dp.callback_query(F.data == "admin_add_ui")
async def admin_add_ui_callback(call: CallbackQuery, state: FSMContext):
    if not is_owner(call.from_user.id):
        await call.answer("Нет доступа.", show_alert=True)
        return
    await state.set_state(AdminUIState.waiting_user)
    await state.update_data(action="add_admin", screen_chat_id=call.message.chat.id, screen_message_id=call.message.message_id)
    await call.answer()
    await safe_edit(call.message, "➕ <b>ДОБАВИТЬ АДМИНИСТРАТОРА</b>\n\nОтправь Telegram ID пользователя.", InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin")]]))


@dp.callback_query(F.data.in_( {"admin_give_dcr_ui", "admin_give_crystals_ui", "admin_give_xp_ui"} ))
async def admin_give_ui_callback(call: CallbackQuery, state: FSMContext):
    if not is_owner(call.from_user.id):
        await call.answer("Нет доступа.", show_alert=True)
        return
    action = call.data.replace("_ui", "")
    await state.set_state(AdminUIState.waiting_user)
    await state.update_data(action=action, screen_chat_id=call.message.chat.id, screen_message_id=call.message.message_id)
    await call.answer()
    labels = {"admin_give_dcr": "💰 DCR", "admin_give_crystals": "💎 кристаллы", "admin_give_xp": "✨ XP"}
    await safe_edit(call.message, f"{labels[action]}\n\nОтправь Telegram ID игрока.", InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin")]]))


@dp.message(AdminUIState.waiting_user)
async def admin_ui_user_message(message: Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        await state.clear(); return
    try:
        target = int((message.text or "").strip())
    except (ValueError, AttributeError):
        try: await message.delete()
        except Exception: pass
        return
    try: await message.delete()
    except Exception: pass
    data = await state.get_data()
    action = data.get("action")
    chat_id = data.get("screen_chat_id")
    msg_id = data.get("screen_message_id")
    if action == "add_admin":
        if not get_player(target):
            if chat_id and msg_id:
                try:
                    await message.bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text="❌ <b>Игрок не найден.</b>", reply_markup=admin_keyboard())
                    await state.clear(); return
                except Exception: pass
            await state.clear(); return
        db_execute("INSERT INTO admin_users(user_id,role,created_at,active) VALUES(?,?,?,1) ON CONFLICT(user_id) DO UPDATE SET active=1", (target,"admin",now_iso()))
        admin_log(message.from_user.id,"admin_add",target,"role=admin")
        await state.clear()
        if chat_id and msg_id:
            try:
                await message.bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text="✅ <b>Администратор добавлен.</b>", reply_markup=admin_keyboard())
                return
            except Exception: pass
        return
    await state.update_data(target_id=target)
    await state.set_state(AdminUIState.waiting_amount)
    if chat_id and msg_id:
        try:
            labels = {"admin_give_dcr":"💰 DCR", "admin_give_crystals":"💎 кристаллы", "admin_give_xp":"✨ XP"}
            await message.bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=f"{labels.get(action, '💵 Значение')}\n\nОтправь количество.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin")]]))
            return
        except Exception: pass


@dp.message(AdminUIState.waiting_amount)
async def admin_ui_amount_message(message: Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        await state.clear(); return
    try:
        amount = int((message.text or "").strip())
    except (ValueError, AttributeError):
        try: await message.delete()
        except Exception: pass
        return
    try: await message.delete()
    except Exception: pass
    data = await state.get_data()
    target = int(data.get("target_id", 0))
    action = data.get("action")
    chat_id = data.get("screen_chat_id")
    msg_id = data.get("screen_message_id")
    if not get_player(target):
        await state.clear(); return
    if action == "admin_give_dcr": add_dcr(target, amount, f"Админ {message.from_user.id}")
    elif action == "admin_give_crystals": add_crystals(target, amount, f"Админ {message.from_user.id}")
    elif action == "admin_give_xp": add_xp(target, amount)
    else:
        await state.clear(); return
    admin_log(message.from_user.id, action, target, str(amount))
    await state.clear()
    if chat_id and msg_id:
        try:
            await message.bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text="✅ <b>Изменение применено.</b>", reply_markup=admin_keyboard())
            return
        except Exception: pass


# ---------------- COMMAND MENU ----------------

async def configure_bot_commands(bot: Bot):
    await bot.set_my_commands([
        BotCommand(command="start", description="Открыть DOMINION"),
    ])

# ============================================================
# MAIN
# ============================================================

async def main():
    if not BOT_TOKEN or BOT_TOKEN == "PASTE_YOUR_NEW_BOT_TOKEN_HERE":
        raise RuntimeError(
            "BOT_TOKEN не указан. Вставь токен бота от @BotFather в переменную BOT_TOKEN."
        )

    if OWNER_ID == 0:
        log.warning("OWNER_ID=0: админ-панель будет недоступна.")

    init_database()
    ensure_legacy_runtime_schema()
    upgrade_database()
    ensure_v8_database()
    ensure_base_items()
    init_pets()
    db_execute("""
        INSERT INTO admin_users(user_id,role,created_at,active)
        VALUES(?,?,?,1)
        ON CONFLICT(user_id) DO UPDATE SET role='owner', active=1
    """, (OWNER_ID, "owner", now_iso()))
    install_dominion_5_hooks()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    await configure_bot_commands(bot)

    scheduler_task = asyncio.create_task(
        scheduler(bot)
    )

    pvp_matchmaking_task = asyncio.create_task(
        pvp_matchmaking_loop(bot)
    )

    try:
        await dp.start_polling(bot)

    finally:
        scheduler_task.cancel()
        pvp_matchmaking_task.cancel()

        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass

        try:
            await pvp_matchmaking_task
        except asyncio.CancelledError:
            pass

        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
