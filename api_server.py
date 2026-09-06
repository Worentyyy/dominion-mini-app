"""DOMINION Mini App API

Read-first synchronization layer for the existing DOMINION bot.
The bot and this API use the same SQLite database; the Mini App never talks to
SQLite directly.

Production requirements:
- DOMINION_BOT_TOKEN: same bot token as the running bot
- DOMINION_DB: path to the same dominion.db used by the bot
- CORS_ORIGINS: comma-separated allowed origins (optional; default '*')
- DEV_ALLOW_UNVERIFIED=1 may be used ONLY for local development.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

BOT_TOKEN = os.getenv("DOMINION_BOT_TOKEN", "").strip()
DB_PATH = os.getenv("DOMINION_DB", os.path.join(os.path.dirname(__file__), "dominion.db"))
DEV_ALLOW_UNVERIFIED = os.getenv("DEV_ALLOW_UNVERIFIED", "0") == "1"
AUTH_MAX_AGE = int(os.getenv("TELEGRAM_INITDATA_MAX_AGE", "86400"))

RANKS = [
    (1, 10, "Новичок"), (10, 30, "Стажёр"), (30, 50, "Воин"),
    (50, 80, "Элита"), (80, 100, "Легенда"), (100, 10**9, "Демонический"),
]
PVP_RANKS = [
    (0, 100, "Bronze I", "🥉"), (100, 200, "Bronze II", "🥉"),
    (200, 300, "Bronze III", "🥉"), (300, 400, "Iron I", "⚙️"),
    (400, 500, "Iron II", "⚙️"), (500, 600, "Iron III", "⚙️"),
    (600, 700, "Silver I", "🥈"), (700, 800, "Silver II", "🥈"),
    (800, 900, "Silver III", "🥈"), (900, 1000, "Gold I", "🥇"),
    (1000, 1100, "Gold II", "🥇"), (1100, 1200, "Gold III", "🥇"),
    (1200, 1300, "Platinum I", "💠"), (1300, 1400, "Platinum II", "💠"),
    (1400, 2000, "Platinum III", "💠"), (2000, 3000, "Ranger", "🦅"),
    (3000, 4000, "Master", "👑"), (4000, 5000, "Grandmaster", "🌌"),
    (5000, 6000, "Demonic", "😈"), (6000, 10**9, "Divine", "✨"),
]

app = FastAPI(title="DOMINION API", version="3.0.0")
origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "*").split(",") if x.strip()]
allow_credentials = origins != ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=allow_credentials,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Telegram-Init-Data"],
)


def now_ts() -> int:
    return int(time.time())


def xp_needed(level: int) -> int:
    return 100 + (max(1, int(level)) - 1) * 50


def rank_for_level(level: int) -> str:
    level = int(level or 1)
    for lo, hi, name in RANKS:
        if lo <= level < hi:
            return name
    return RANKS[-1][2]


def pvp_rank_for_mmr(mmr: int) -> dict[str, Any]:
    mmr = int(mmr or 0)
    for lo, hi, name, emoji in PVP_RANKS:
        if lo <= mmr < hi:
            return {"name": name, "emoji": emoji}
    return {"name": PVP_RANKS[-1][2], "emoji": PVP_RANKS[-1][3]}


def db_conn() -> sqlite3.Connection:
    candidates = [DB_PATH, os.path.join(os.path.dirname(__file__), "dominion.db"), "dominion.db"]
    for path in candidates:
        if os.path.exists(path):
            con = sqlite3.connect(path, timeout=10)
            con.row_factory = sqlite3.Row
            return con
    raise HTTPException(503, "DOMINION database not found")


def rows(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    with db_conn() as con:
        return [dict(r) for r in con.execute(sql, params).fetchall()]


def row(sql: str, params: tuple = ()) -> dict[str, Any] | None:
    with db_conn() as con:
        r = con.execute(sql, params).fetchone()
        return dict(r) if r else None


def table_exists(con: sqlite3.Connection, name: str) -> bool:
    return bool(con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())


def columns(con: sqlite3.Connection, table: str) -> set[str]:
    if not table_exists(con, table):
        return set()
    return {r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}


def telegram_secret() -> bytes:
    if not BOT_TOKEN:
        raise HTTPException(503, "DOMINION_BOT_TOKEN is not configured on the API server")
    return hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()


def validate_init_data(init_data: str) -> dict[str, Any]:
    """Validate Telegram Mini App initData and return the authenticated user."""
    if not init_data:
        raise HTTPException(401, "Telegram initData is required")
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    except Exception as exc:
        raise HTTPException(401, "Invalid initData") from exc
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise HTTPException(401, "Missing initData hash")
    check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    calculated = hmac.new(telegram_secret(), check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, received_hash):
        raise HTTPException(401, "Invalid Telegram initData signature")
    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError as exc:
        raise HTTPException(401, "Invalid auth_date") from exc
    if auth_date <= 0 or now_ts() - auth_date > AUTH_MAX_AGE:
        raise HTTPException(401, "Telegram initData expired")
    try:
        user = json.loads(pairs.get("user", "{}"))
        uid = int(user["id"])
    except Exception as exc:
        raise HTTPException(401, "Invalid Telegram user data") from exc
    return {"id": uid, **user}


def current_user(request: Request) -> dict[str, Any]:
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    if init_data:
        return validate_init_data(init_data)
    if DEV_ALLOW_UNVERIFIED:
        raw = request.query_params.get("user_id")
        if raw and raw.isdigit():
            return {"id": int(raw), "first_name": "DEV"}
    raise HTTPException(401, "Open the Mini App from Telegram")


def require_player(uid: int) -> dict[str, Any]:
    p = row("SELECT * FROM players WHERE user_id=?", (uid,))
    if not p:
        raise HTTPException(404, "Player not found. Open the bot and use /start first.")
    return p


def equipment(uid: int) -> dict[str, Any]:
    with db_conn() as con:
        if not table_exists(con, "equipment"):
            return {}
        eq = con.execute("SELECT * FROM equipment WHERE user_id=?", (uid,)).fetchone()
        if not eq:
            return {}
        d = dict(eq)
        for slot, key in (("weapon", "weapon_id"), ("armor", "armor_id"), ("shield", "shield_id"), ("ability", "ability_id"), ("pet", "pet_id")):
            iid = d.get(key)
            if iid is None:
                d[slot] = None
                continue
            table = "pets" if slot == "pet" else ("abilities" if slot == "ability" else "items")
            idcol = "pet_id" if slot == "pet" else ("ability_id" if slot == "ability" else "item_id")
            r = con.execute(f"SELECT * FROM {table} WHERE {idcol}=?", (iid,)).fetchone()
            d[slot] = dict(r) if r else None
        return d


def int_str(value: Any) -> str:
    return str(int(value or 0))


def build_profile(uid: int) -> dict[str, Any]:
    p = require_player(uid)
    ps = row("SELECT * FROM pvp_stats WHERE user_id=?", (uid,)) or {}
    level = int(p.get("level") or 1)
    xp = int(p.get("xp") or 0)
    need = xp_needed(level)
    clan = None
    with db_conn() as con:
        if table_exists(con, "clans") and p.get("clan_id"):
            cr = con.execute("SELECT * FROM clans WHERE clan_id=?", (p["clan_id"],)).fetchone()
            if cr:
                clan = dict(cr)
        eq = equipment(uid)
    mmr = int(ps.get("mmr") or 0)
    return {
        "user": {"id": uid, "username": p.get("username") or "", "first_name": p.get("first_name") or "Игрок"},
        "player": {
            "first_name": p.get("first_name") or "Игрок",
            "username": p.get("username") or "",
            "level": level,
            "xp": int_str(xp),
            "xp_needed": int_str(need),
            "xp_progress": min(100, int(xp / need * 100)) if need else 0,
            "rank": rank_for_level(level),
            "dcr": int_str(p.get("dcr")),
            "crystals": int_str(p.get("crystals")),
            "wins": int_str(p.get("wins")),
            "losses": int_str(p.get("losses")),
            "kills": int_str(p.get("kills")),
            "deaths": int_str(p.get("deaths")),
            "battle_pass": int_str(p.get("battle_pass")),
            "bp_level": int_str(p.get("bp_level")),
            "bp_xp": int_str(p.get("bp_xp")),
            "bp_paid": int(p.get("bp_paid") or 0),
            "vip_until": p.get("vip_until"),
            "crown_until": p.get("crown_until"),
            "divine_until": p.get("divine_until"),
            "reputation": int_str(p.get("reputation")),
            "potions": int_str(p.get("potions")),
            "avatar_key": p.get("avatar_key") or "🧙",
        },
        "pvp": {
            "mmr": mmr,
            "rank": pvp_rank_for_mmr(mmr),
            "ranked_games": int_str(ps.get("ranked_games")),
            "ranked_wins": int_str(ps.get("ranked_wins")),
            "ranked_losses": int_str(ps.get("ranked_losses")),
            "total_games": int_str(ps.get("total_games")),
            "total_wins": int_str(ps.get("total_wins")),
            "total_losses": int_str(ps.get("total_losses")),
            "total_damage": int_str(ps.get("total_damage")),
            "current_streak": int_str(ps.get("current_streak")),
            "best_streak": int_str(ps.get("best_streak")),
            "calibration_games": int_str(ps.get("calibration_games")),
        },
        "clan": clan,
        "equipment": {
            "weapon": eq.get("weapon"), "armor": eq.get("armor"), "shield": eq.get("shield"),
            "ability": eq.get("ability"), "pet": eq.get("pet"),
        },
    }


def build_inventory(uid: int) -> list[dict[str, Any]]:
    return rows("""
        SELECT i.item_id, i.item_key, i.name, i.item_type, i.rarity,
               i.attack_min, i.attack_max, i.damage_reduction,
               i.shield_chance, i.shield_reduction, i.price_dcr,
               inv.quantity
        FROM inventory inv
        JOIN items i ON i.item_id=inv.item_id
        WHERE inv.user_id=? AND inv.quantity>0
        ORDER BY CASE i.rarity
          WHEN 'Демонический' THEN 6 WHEN 'Мифический' THEN 5 WHEN 'Легендарный' THEN 4
          WHEN 'Эпический' THEN 3 WHEN 'Редкий' THEN 2 ELSE 1 END DESC, i.name
    """, (uid,))


def build_clan(uid: int) -> dict[str, Any] | None:
    p = require_player(uid)
    clan_id = p.get("clan_id")
    if not clan_id:
        return None
    with db_conn() as con:
        c = con.execute("SELECT * FROM clans WHERE clan_id=?", (clan_id,)).fetchone()
        if not c:
            return None
        result = dict(c)
        result["members"] = [dict(x) for x in con.execute("""
            SELECT cm.user_id, cm.role, p.username, p.first_name, p.level, p.xp
            FROM clan_members cm JOIN players p ON p.user_id=cm.user_id
            WHERE cm.clan_id=? ORDER BY CASE cm.role WHEN 'leader' THEN 0 WHEN 'officer' THEN 1 ELSE 2 END, p.level DESC
        """, (clan_id,)).fetchall()]
        if table_exists(con, "clan_progress"):
            r = con.execute("SELECT * FROM clan_progress WHERE clan_id=?", (clan_id,)).fetchone()
            result["progress"] = dict(r) if r else None
        if table_exists(con, "clan_state"):
            r = con.execute("SELECT * FROM clan_state WHERE clan_id=?", (clan_id,)).fetchone()
            result["state"] = dict(r) if r else None
        if table_exists(con, "clan_upgrades"):
            result["upgrades"] = [dict(x) for x in con.execute("SELECT * FROM clan_upgrades WHERE clan_id=? ORDER BY upgrade_key", (clan_id,)).fetchall()]
        return result


def build_pve(uid: int) -> dict[str, Any]:
    battle = row("SELECT * FROM pve_battles WHERE user_id=?", (uid,))
    effects = rows("SELECT * FROM pve_effects WHERE user_id=? ORDER BY id", (uid,)) if table_exists_safe("pve_effects") else []
    return {"active_battle": battle, "effects": effects}


def table_exists_safe(name: str) -> bool:
    with db_conn() as con:
        return table_exists(con, name)


def build_pvp(uid: int) -> dict[str, Any]:
    queue = row("SELECT * FROM pvp_queue WHERE user_id=?", (uid,))
    match = row("""
        SELECT * FROM pvp_matches
        WHERE player1_id=? OR player2_id=?
        ORDER BY id DESC LIMIT 1
    """, (uid, uid))
    return {"queue": queue, "match": match}


def build_world(uid: int) -> dict[str, Any]:
    active_boss = row("SELECT * FROM world_bosses WHERE active=1 ORDER BY id DESC LIMIT 1")
    if active_boss:
        damage = row("SELECT * FROM boss_damage WHERE boss_id=? AND user_id=?", (active_boss["id"], uid))
        active_boss["my_damage"] = int((damage or {}).get("damage") or 0)
    return {
        "events": rows("SELECT * FROM events WHERE active=1 ORDER BY starts_at") if table_exists_safe("events") else [],
        "world_boss": active_boss,
    }


def build_social(uid: int) -> dict[str, Any]:
    friends = rows("""
        SELECT f.friend_id AS user_id, p.username, p.first_name, p.level
        FROM friends f JOIN players p ON p.user_id=f.friend_id
        WHERE f.user_id=? AND f.status='accepted'
    """, (uid,)) if table_exists_safe("friends") else []
    requests = rows("""
        SELECT fr.id, fr.sender_id, p.username, p.first_name, fr.status, fr.created_at
        FROM friend_requests fr JOIN players p ON p.user_id=fr.sender_id
        WHERE fr.receiver_id=? AND fr.status='pending' ORDER BY fr.id DESC
    """, (uid,)) if table_exists_safe("friend_requests") else []
    return {"friends": friends, "friend_requests": requests}


def build_progress(uid: int) -> dict[str, Any]:
    return {
        "quests": rows("SELECT * FROM quests WHERE user_id=? ORDER BY completed, id DESC", (uid,)) if table_exists_safe("quests") else [],
        "achievements": rows("SELECT * FROM achievements WHERE user_id=? ORDER BY achievement_key", (uid,)) if table_exists_safe("achievements") else [],
        "story": row("SELECT * FROM story_progress WHERE user_id=?", (uid,)) if table_exists_safe("story_progress") else None,
    }


def build_market() -> list[dict[str, Any]]:
    with db_conn() as con:
        if table_exists(con, "market_lots_v2"):
            return [dict(x) for x in con.execute("""
                SELECT m.*, i.item_key, i.name AS item_name, i.rarity, i.item_type
                FROM market_lots_v2 m JOIN items i ON i.item_id=m.item_id
                WHERE m.active=1 ORDER BY m.id DESC LIMIT 100
            """).fetchall()]
        if table_exists(con, "market_lots"):
            return [dict(x) for x in con.execute("""
                SELECT m.*, i.item_key, i.name AS item_name, i.rarity, i.item_type
                FROM market_lots m JOIN items i ON i.item_id=m.item_id
                WHERE m.active=1 ORDER BY m.id DESC LIMIT 100
            """).fetchall()]
    return []


def build_battle_pass() -> dict[str, Any]:
    return {"rewards": rows("SELECT * FROM bp_rewards ORDER BY level", ()) if table_exists_safe("bp_rewards") else []}


@app.get("/api/health")
def health() -> dict[str, Any]:
    exists = any(os.path.exists(p) for p in [DB_PATH, os.path.join(os.path.dirname(__file__), "dominion.db"), "dominion.db"])
    return {"ok": True, "db_exists": exists, "api_version": app.version, "time": datetime.now(timezone.utc).isoformat()}


@app.get("/api/me")
def me(request: Request) -> dict[str, Any]:
    u = current_user(request)
    return build_profile(int(u["id"]))


@app.get("/api/me/profile")
def profile(request: Request) -> dict[str, Any]:
    u = current_user(request)
    return build_profile(int(u["id"]))


@app.get("/api/me/inventory")
def inventory(request: Request) -> dict[str, Any]:
    u = current_user(request)
    return {"items": build_inventory(int(u["id"]))}


@app.get("/api/me/clan")
def clan(request: Request) -> dict[str, Any]:
    u = current_user(request)
    return {"clan": build_clan(int(u["id"]))}


@app.get("/api/me/pve")
def pve(request: Request) -> dict[str, Any]:
    u = current_user(request)
    return build_pve(int(u["id"]))


@app.get("/api/me/pvp")
def pvp(request: Request) -> dict[str, Any]:
    u = current_user(request)
    return build_pvp(int(u["id"]))


@app.get("/api/me/progress")
def progress(request: Request) -> dict[str, Any]:
    u = current_user(request)
    return build_progress(int(u["id"]))


@app.get("/api/me/social")
def social(request: Request) -> dict[str, Any]:
    u = current_user(request)
    return build_social(int(u["id"]))


@app.get("/api/market")
def market(request: Request) -> dict[str, Any]:
    current_user(request)
    return {"lots": build_market()}


@app.get("/api/world")
def world(request: Request) -> dict[str, Any]:
    u = current_user(request)
    return build_world(int(u["id"]))


@app.get("/api/battle-pass")
def battle_pass(request: Request) -> dict[str, Any]:
    current_user(request)
    return build_battle_pass()


@app.get("/api/me/bootstrap")
def bootstrap(request: Request) -> dict[str, Any]:
    """Single read-only snapshot for the Mini App.

    It intentionally contains only server-derived state. No client-provided
    balance, XP, clan membership, item ownership or battle result is trusted.
    """
    u = current_user(request)
    uid = int(u["id"])
    return {
        "server_time": datetime.now(timezone.utc).isoformat(),
        "profile": build_profile(uid),
        "inventory": build_inventory(uid),
        "clan": build_clan(uid),
        "pve": build_pve(uid),
        "pvp": build_pvp(uid),
        "progress": build_progress(uid),
        "social": build_social(uid),
        "market": build_market(),
        "world": build_world(uid),
        "battle_pass": build_battle_pass(),
    }


# Static Mini App
frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
