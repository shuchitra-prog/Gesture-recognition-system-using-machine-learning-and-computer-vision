# database/db_manager.py
# All SQLite interactions centralised here.
# Schema:  users | gestures | settings | stats

import sqlite3
import json
from typing import List, Dict, Optional
from config import DB_PATH
from utils import get_logger

logger = get_logger(__name__)

# ──────────────────────────────────────────────
#  SCHEMA
# ──────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT    NOT NULL UNIQUE,
    created  TEXT    DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS gestures (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    gesture_name TEXT    NOT NULL,
    action_name  TEXT    NOT NULL,
    profile      TEXT    NOT NULL DEFAULT 'Normal',
    params       TEXT    DEFAULT '{}',     -- JSON blob for extra args
    UNIQUE(gesture_name, profile)
);

CREATE TABLE IF NOT EXISTS settings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    key         TEXT    NOT NULL UNIQUE,
    value       TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS stats (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    gesture_name TEXT    NOT NULL,
    action_name  TEXT    NOT NULL,
    timestamp    TEXT    DEFAULT (datetime('now'))
);
"""

# ──────────────────────────────────────────────
#  DEFAULT DATA
# ──────────────────────────────────────────────

_DEFAULT_GESTURES = [
    # (gesture_name, action_name, profile)
    ("INDEX_POINT",   "mouse_move",      "Normal"),
    ("THUMB_INDEX",   "left_click",      "Normal"),
    ("THUMB_MIDDLE",  "right_click",     "Normal"),
    ("THUMB_PINKY",   "double_click",    "Normal"),
    ("FIST_HOLD",     "drag",            "Normal"),
    ("TWO_FINGERS_UP","scroll_up",       "Normal"),
    ("TWO_FINGERS_DOWN","scroll_down",   "Normal"),
    ("OPEN_PALM_HOLD", "screenshot",     "Normal"),
    ("VOLUME_CONTROL", "volume_control", "Normal"),
    ("BRIGHTNESS_CONTROL", "brightness_control", "Normal"),
    # Presentation
    ("SWIPE_LEFT",    "prev_slide",      "Presentation"),
    ("SWIPE_RIGHT",   "next_slide",      "Presentation"),
    ("INDEX_POINT",   "laser_pointer",   "Presentation"),
    # Drawing
    ("INDEX_POINT",   "draw",            "Drawing"),
    # The detector intentionally emits FIST_HOLD for safety, so the drawing
    # eraser must use the same confirmed gesture.
    ("FIST_HOLD",     "eraser",          "Drawing"),
    ("OPEN_PALM_HOLD", "save_drawing",   "Drawing"),
]

_DEFAULT_SETTINGS = [
    ("sensitivity",        "2.5"),
    ("smoothing",          "4"),
    ("pinch_threshold",    "50"),
    ("click_cooldown_ms",  "350"),
    ("camera_width",       "960"),
    ("camera_height",      "540"),
    ("fps_limit",          "30"),
    ("active_profile",     "Normal"),
    ("theme",              "dark"),
]


# ──────────────────────────────────────────────
#  MANAGER CLASS
# ──────────────────────────────────────────────

class DBManager:
    """Thread-safe SQLite wrapper (uses check_same_thread=False)."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._connect()
        self._init_schema()
        self._seed_defaults()

    # ── connection ────────────────────────────

    def _connect(self):
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        logger.debug("Connected to SQLite db at %s", self.db_path)

    def _init_schema(self):
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def _seed_defaults(self):
        """Insert defaults only if tables are empty."""
        cur = self._conn.cursor()

        if cur.execute("SELECT COUNT(*) FROM gestures").fetchone()[0] == 0:
            cur.executemany(
                "INSERT OR IGNORE INTO gestures (gesture_name, action_name, profile) VALUES (?,?,?)",
                _DEFAULT_GESTURES,
            )

        if cur.execute("SELECT COUNT(*) FROM settings").fetchone()[0] == 0:
            cur.executemany(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?,?)",
                _DEFAULT_SETTINGS,
            )

        # Repair only mappings shipped by older builds. User-created mappings
        # are left intact.
        cur.execute("UPDATE gestures SET gesture_name='OPEN_PALM_HOLD' "
                    "WHERE gesture_name='OPEN_PALM' AND action_name='screenshot' AND profile='Normal'")
        cur.execute("UPDATE gestures SET gesture_name='INDEX_POINT' "
                    "WHERE gesture_name='INDEX_DRAW' AND action_name='draw' AND profile='Drawing'")
        cur.execute("UPDATE gestures SET gesture_name='OPEN_PALM_HOLD' "
                    "WHERE gesture_name='OPEN_PALM' AND action_name='save_drawing' AND profile='Drawing'")
        cur.execute("UPDATE gestures SET gesture_name='VOLUME_CONTROL' "
                    "WHERE gesture_name='VOLUME_PINCH' AND action_name='volume_control' AND profile='Normal'")
        cur.execute("UPDATE gestures SET gesture_name='BRIGHTNESS_CONTROL' "
                    "WHERE gesture_name='BRIGHTNESS_SWIPE' AND action_name='brightness_control' AND profile='Normal'")
        cur.execute("UPDATE gestures SET gesture_name='FIST_HOLD' "
                    "WHERE gesture_name='FIST' AND action_name='eraser' AND profile='Drawing'")

        # Migrate old default settings to improved values
        cur.execute("UPDATE settings SET value='50' WHERE key='pinch_threshold' AND value='40'")
        cur.execute("UPDATE settings SET value='350' WHERE key='click_cooldown_ms' AND value='450'")

        self._conn.commit()
        logger.debug("DB seeded with defaults.")

    def close(self):
        if self._conn:
            self._conn.close()

    # ── GESTURES ──────────────────────────────

    def get_gestures(self, profile: str = None) -> List[Dict]:
        sql = "SELECT * FROM gestures"
        params = ()
        if profile:
            sql += " WHERE profile = ?"
            params = (profile,)
        rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def add_gesture(self, gesture_name: str, action_name: str,
                    profile: str = "Normal", params: dict = None) -> bool:
        try:
            self._conn.execute(
                "INSERT INTO gestures (gesture_name, action_name, profile, params) VALUES (?,?,?,?)",
                (gesture_name, action_name, profile, json.dumps(params or {})),
            )
            self._conn.commit()
            return True
        except sqlite3.IntegrityError:
            logger.warning("Gesture '%s' already exists for profile '%s'.", gesture_name, profile)
            return False

    def update_gesture(self, gesture_id: int, gesture_name: str,
                       action_name: str, profile: str) -> bool:
        self._conn.execute(
            "UPDATE gestures SET gesture_name=?, action_name=?, profile=? WHERE id=?",
            (gesture_name, action_name, profile, gesture_id),
        )
        self._conn.commit()
        return True

    def delete_gesture(self, gesture_id: int) -> bool:
        self._conn.execute("DELETE FROM gestures WHERE id=?", (gesture_id,))
        self._conn.commit()
        return True

    def get_action_for_gesture(self, gesture_name: str, profile: str = "Normal") -> Optional[str]:
        row = self._conn.execute(
            "SELECT action_name FROM gestures WHERE gesture_name=? AND profile=?",
            (gesture_name, profile),
        ).fetchone()
        return row["action_name"] if row else None

    # ── SETTINGS ──────────────────────────────

    def get_setting(self, key: str, default=None):
        row = self._conn.execute(
            "SELECT value FROM settings WHERE key=?", (key,)
        ).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value) -> bool:
        self._conn.execute(
            "INSERT INTO settings (key, value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )
        self._conn.commit()
        return True

    def get_all_settings(self) -> Dict[str, str]:
        rows = self._conn.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}

    # ── STATS ─────────────────────────────────

    def log_gesture(self, gesture_name: str, action_name: str):
        self._conn.execute(
            "INSERT INTO stats (gesture_name, action_name) VALUES (?,?)",
            (gesture_name, action_name),
        )
        self._conn.commit()

    def get_stats(self) -> Dict:
        total = self._conn.execute("SELECT COUNT(*) as n FROM stats").fetchone()["n"]
        top = self._conn.execute(
            "SELECT gesture_name, COUNT(*) as cnt FROM stats "
            "GROUP BY gesture_name ORDER BY cnt DESC LIMIT 10"
        ).fetchall()
        return {"total": total, "top_gestures": [dict(r) for r in top]}

    # ── USERS ─────────────────────────────────

    def add_user(self, username: str) -> bool:
        try:
            self._conn.execute("INSERT INTO users (username) VALUES (?)", (username,))
            self._conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_users(self) -> List[Dict]:
        return [dict(r) for r in self._conn.execute("SELECT * FROM users").fetchall()]
