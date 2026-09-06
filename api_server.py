"""Read-only DOMINION Mini App profile API, plus avatar selection.

Run this next to the Mini App. It imports the existing bot module without
starting polling, so the bot and this API use the same SQLite database.
"""
from __future__ import annotations

import hashlib
import hmac
import importlib
import json
import os
import sqlite3
import sys
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


AVATAR_KEYS = {"mage", "warrior", "shadow", "blood", "hunter", "lord", "demon", "celestial"}
BASE_DIR = Path(__file__).resolve().parent
BOT_SOURCE_DIR = os.getenv("DOMINION_BOT_SOURCE_DIR")
if BOT_SOURCE_DIR:
    sys.path.insert(0, BOT_SOURCE_DIR)

# The original bot's ``if __name__ == '__main__'`` guard prevents polling here.
bot_core = importlib.import_module(os.getenv("DOMINION_BOT_MODULE", "dominion"))
DB_PATH = Path(os.getenv("DOMINION_DB_PATH", str(bot_core.DB_PATH))).expanduser().resolve()
BOT_TOKEN = os.getenv("DOMINION_BOT_TOKEN")
MAX_INIT_DATA_AGE = int(os.getenv("DOMINION_INIT_DATA_MAX_AGE", "86400"))
_schema_lock = threading.Lock()

if not BOT_TOKEN:
    raise RuntimeError("DOMINION_BOT_TOKEN must be set in the API environment.")

app = FastAPI(title="DOMINION Mini App API", docs_url=None, redoc_url=None)
origins = [origin.strip() for origin in os.getenv("DOMINION_MINI_APP_ORIGINS", "").split(",") if origin.strip()]
if origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Telegram-Init-Data"],
    )


class AvatarRequest(BaseModel):
    avatar_key: str = Field(pattern="^(mage|warrior|shadow|blood|hunter|lord|demon|celestial)$")


def db_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def telegram_user_from_init_data(init_data: str) -> dict[str, Any]:
    """Verify Telegram Web App initData and return its signed user object."""
    if not init_data:
        raise HTTPException(status_code=401, detail="Telegram authorization data is missing.")
    try:
        data = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
        received_hash = data.pop("hash")
        auth_date = int(data["auth_date"])
        user = json.loads(data["user"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid Telegram authorization data.") from exc

    if auth_date <= 0 or time.time() - auth_date > MAX_INIT_DATA_AGE:
        raise HTTPException(status_code=401, detail="Telegram authorization data has expired.")
    check_string = "\n".join(f"{key}={value}" for key, value in sorted(data.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode("utf-8"), hashlib.sha256).digest()
    expected_hash = hmac.new(secret, check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash):
        raise HTTPException(status_code=401, detail="Telegram authorization signature is invalid.")
    if not isinstance(user.get("id"), int) or user["id"] <= 0:
        raise HTTPException(status_code=401, detail="Telegram user is invalid.")
    return user


def authorized_user(x_telegram_init_data: str | None) -> dict[str, Any]:
    return telegram_user_from_init_data(x_telegram_init_data or "")


def has_avatar_column(connection: sqlite3.Connection) -> bool:
    return any(row["name"] == "avatar_key" for row in connection.execute("PRAGMA table_info(players)"))


def ensure_avatar_column() -> None:
    """Small idempotent migration; does not touch any economy or combat data."""
    with _schema_lock, db_connection() as connection:
        if not has_avatar_column(connection):
            connection.execute("ALTER TABLE players ADD COLUMN avatar_key TEXT")
            connection.commit()


def profile_for(user_id: int) -> dict[str, Any]:
    with db_connection() as connection:
        avatar_expression = "p.avatar_key" if has_avatar_column(connection) else "NULL"
        row = connection.execute(
            f"""
            SELECT p.user_id, p.username, p.first_name, p.level, p.xp, p.dcr, p.crystals,
                   p.bp_level, p.bp_xp, p.bp_paid, p.vip_until, p.crown_until, p.divine_until,
                   {avatar_expression} AS avatar_key,
                   COALESCE(s.mmr, 0) AS mmr,
                   COALESCE(s.total_wins, 0) AS total_wins,
                   COALESCE(s.total_losses, 0) AS total_losses,
                   COALESCE(s.current_streak, 0) AS current_streak,
                   w.name AS weapon_name, a.name AS armor_name, sh.name AS shield_name,
                   ab.name AS ability_name, pet.name AS pet_name
            FROM players p
            LEFT JOIN pvp_stats s ON s.user_id = p.user_id
            LEFT JOIN equipment e ON e.user_id = p.user_id
            LEFT JOIN items w ON w.item_id = e.weapon_id
            LEFT JOIN items a ON a.item_id = e.armor_id
            LEFT JOIN items sh ON sh.item_id = e.shield_id
            LEFT JOIN items ab ON ab.item_id = e.ability_id
            LEFT JOIN items pet ON pet.item_id = e.pet_id
            WHERE p.user_id = ?
            """,
            (user_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Игрок не найден. Сначала запусти бота командой /start.")

    level = int(row["level"])
    xp = int(row["xp"])
    next_level_xp = bot_core.xp_needed(level)
    pvp_rank = bot_core.pvp_rank_for_mmr(int(row["mmr"]))
    # This is the original bot's status logic, including expiry checks.
    privilege = bot_core.premium_status_text(row)
    return {
        "name": row["first_name"] or row["username"] or str(user_id),
        "avatar_key": row["avatar_key"] if row["avatar_key"] in AVATAR_KEYS else None,
        "level": level,
        "level_rank": bot_core.rank_for_level(level),
        "xp": {
            "current": xp,
            "next_level": next_level_xp,
            "progress_percent": round(min(100, max(0, xp / next_level_xp * 100)), 2),
        },
        "dcr": int(row["dcr"]),
        "crystals": int(row["crystals"]),
        "pvp": {
            "mmr": int(row["mmr"]),
            "rank": pvp_rank,
            "wins": int(row["total_wins"]),
            "losses": int(row["total_losses"]),
            "current_streak": int(row["current_streak"]),
        },
        "battle_pass": {
            "level": int(row["bp_level"]),
            "xp": int(row["bp_xp"]),
            "next_level_xp": 100 + int(row["bp_level"]) * 25,
            "premium": bool(row["bp_paid"]),
        },
        "privilege": privilege,
        "equipment": {
            "weapon": row["weapon_name"], "armor": row["armor_name"], "shield": row["shield_name"],
            "ability": row["ability_name"], "pet": row["pet_name"],
        },
    }


@app.get("/api/me/profile")
async def get_my_profile(x_telegram_init_data: str | None = Header(default=None)) -> dict[str, Any]:
    user = authorized_user(x_telegram_init_data)
    return profile_for(user["id"])


@app.post("/api/me/avatar")
async def set_my_avatar(payload: AvatarRequest, x_telegram_init_data: str | None = Header(default=None)) -> dict[str, Any]:
    user = authorized_user(x_telegram_init_data)
    ensure_avatar_column()
    with db_connection() as connection:
        cursor = connection.execute("UPDATE players SET avatar_key=? WHERE user_id=?", (payload.avatar_key, user["id"]))
        connection.commit()
    if cursor.rowcount != 1:
        raise HTTPException(status_code=404, detail="Игрок не найден. Сначала запусти бота командой /start.")
    return profile_for(user["id"])


# Serving the Mini App from this process keeps browser/API requests same-origin.
mini_app_dir = Path(os.getenv("DOMINION_MINI_APP_DIR", str(BASE_DIR))).resolve()
app.mount("/", StaticFiles(directory=mini_app_dir, html=True), name="mini-app")
