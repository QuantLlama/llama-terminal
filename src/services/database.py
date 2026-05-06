import json
import os
import sys
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional
import platform as py_platform

def get_db_path():
    # If running as a PyInstaller bundle, use APPDATA for persistence
    if getattr(sys, 'frozen', False):
        app_data = os.environ.get('APPDATA') or os.path.expanduser('~')
        db_dir = os.path.join(app_data, "Quantum Llama", "data")
    else:
        # Development mode
        db_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config"
        )
    
    os.makedirs(db_dir, exist_ok=True)
    return os.path.join(db_dir, "quantum_llama.db")

def get_outputs_dir():
    if getattr(sys, 'frozen', False):
        docs_dir = os.path.join(os.path.expanduser('~'), 'Documents')
        out_dir = os.path.join(docs_dir, "Quantum Llama", "outputs")
    else:
        out_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "outputs"
        )
    os.makedirs(out_dir, exist_ok=True)
    return out_dir

def get_logs_dir():
    if getattr(sys, 'frozen', False):
        app_data = os.environ.get('APPDATA') or os.path.expanduser('~')
        log_dir = os.path.join(app_data, "Quantum Llama", "logs")
    else:
        log_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs"
        )
    os.makedirs(log_dir, exist_ok=True)
    return log_dir

DB_PATH = get_db_path()
DB_DIR = os.path.dirname(DB_PATH)
@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row  
    try:
        yield conn
    finally:
        conn.close()
def init_db():
    os.makedirs(DB_DIR, exist_ok=True)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT DEFAULT 'default_user' UNIQUE,
                platform TEXT DEFAULT 'mt5',
                theme TEXT DEFAULT 'dark',
                show_grid INTEGER DEFAULT 1,
                show_watermark INTEGER DEFAULT 1,
                one_click_trading INTEGER DEFAULT 0,
                timer_enabled INTEGER DEFAULT 1,
                timer_position TEXT DEFAULT 'bottom',
                timer_size TEXT DEFAULT 'medium',
                timer_color TEXT DEFAULT '#fbbf24',
                timer_show_progress INTEGER DEFAULT 1,
                last_active_workspace TEXT DEFAULT 'session_mt5',
                extra_settings TEXT DEFAULT '{}',
                chart_candle_up TEXT DEFAULT '#10b981',
                chart_candle_down TEXT DEFAULT '#ef4444',
                chart_bg_color TEXT DEFAULT '#111111',
                chart_candle_border_visible INTEGER DEFAULT 0,
                chart_candle_border_color TEXT DEFAULT '#ffffff',
                risk_max_daily_loss REAL DEFAULT 500.0,
                risk_max_contracts INTEGER DEFAULT 1,
                risk_emotional_guard INTEGER DEFAULT 0,
                risk_locked_until TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workspaces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT DEFAULT 'default_user',
                session_name TEXT NOT NULL,
                layout TEXT DEFAULT 'single',
                charts TEXT DEFAULT '[]',
                active_chart_id INTEGER DEFAULT 1,
                symbol TEXT DEFAULT 'MNQ',
                timeframe TEXT DEFAULT '1m',
                show_tape INTEGER DEFAULT 1,
                show_order_entry INTEGER DEFAULT 1,
                drawings TEXT DEFAULT '[]',
                panel_sizes TEXT DEFAULT '{}',
                symbol_settings TEXT DEFAULT '{}',
                indicator_settings TEXT DEFAULT '{}',
                visibility_settings TEXT DEFAULT '{}',
                show_dom INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, session_name)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT DEFAULT 'default_user',
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                skill TEXT,
                agent_actions TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS algolab_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT DEFAULT 'default_user' UNIQUE,
                open_files TEXT DEFAULT '[]',
                file_contents TEXT DEFAULT '{}',
                active_file_path TEXT,
                is_chat_open BOOLEAN DEFAULT 0,
                chat_width INTEGER DEFAULT 350,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            INSERT OR IGNORE INTO user_settings (user_id) VALUES ('default_user')
        """)
        conn.commit()
        try:
            cursor.execute("PRAGMA table_info(algolab_state)")
            columns = [col[1] for col in cursor.fetchall()]
            if "is_chat_open" not in columns:
                cursor.execute(
                    "ALTER TABLE algolab_state ADD COLUMN is_chat_open BOOLEAN DEFAULT 0"
                )
            if "chat_width" not in columns:
                cursor.execute(
                    "ALTER TABLE algolab_state ADD COLUMN chat_width INTEGER DEFAULT 350"
                )
            conn.commit()
        except:
            pass
        try:
            cursor.execute("PRAGMA table_info(workspaces)")
            columns = [col[1] for col in cursor.fetchall()]
            if "show_dom" not in columns:
                cursor.execute(
                    "ALTER TABLE workspaces ADD COLUMN show_dom INTEGER DEFAULT 0"
                )
            conn.commit()
        except:
            pass
        try:
            cursor.execute("PRAGMA table_info(user_settings)")
            columns = [col[1] for col in cursor.fetchall()]
            if "extra_settings" not in columns:
                cursor.execute(
                    "ALTER TABLE user_settings ADD COLUMN extra_settings TEXT DEFAULT '{}'"
                )
            new_cols = {
                "chart_candle_up": "TEXT DEFAULT '#10b981'",
                "chart_candle_down": "TEXT DEFAULT '#ef4444'",
                "chart_bg_color": "TEXT DEFAULT '#111111'",
                "chart_candle_border_visible": "INTEGER DEFAULT 0",
                "chart_candle_border_color": "TEXT DEFAULT '#ffffff'",
                "risk_max_daily_loss": "REAL DEFAULT 500.0",
                "risk_max_contracts": "INTEGER DEFAULT 1",
                "risk_emotional_guard": "INTEGER DEFAULT 0",
                "risk_locked_until": "TEXT"
            }
            for col, definition in new_cols.items():
                if col not in columns:
                    cursor.execute(f"ALTER TABLE user_settings ADD COLUMN {col} {definition}")
            conn.commit()
        except:
            pass
        print(f"[DATABASE] Inicializada en: {DB_PATH}")
def get_settings(user_id: str = "default_user") -> Dict[str, Any]:
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM user_settings WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "platform": row["platform"],
                    "theme": row["theme"],
                    "show_grid": bool(row["show_grid"]),
                    "show_watermark": bool(row["show_watermark"]),
                    "one_click_trading": bool(row["one_click_trading"]),
                    "timer_enabled": bool(row["timer_enabled"]),
                    "timer_position": row["timer_position"],
                    "timer_size": row["timer_size"],
                    "timer_color": row["timer_color"],
                    "timer_show_progress": bool(row["timer_show_progress"]),
                    "last_active_workspace": row["last_active_workspace"],
                    "chart_candle_up": row["chart_candle_up"],
                    "chart_candle_down": row["chart_candle_down"],
                    "chart_bg_color": row["chart_bg_color"],
                    "chart_candle_border_visible": bool(row["chart_candle_border_visible"]),
                    "chart_candle_border_color": row["chart_candle_border_color"],
                    "risk_max_daily_loss": row["risk_max_daily_loss"],
                    "risk_max_contracts": row["risk_max_contracts"],
                    "risk_emotional_guard": bool(row["risk_emotional_guard"]),
                    "risk_locked_until": row["risk_locked_until"],
                    "updated_at": row["updated_at"],
                }
    except Exception as e:
        print(f"[DATABASE] Error loading settings: {e}")
    return {
        "platform": "mt5",
        "theme": "dark",
        "show_grid": True,
        "show_watermark": True,
        "one_click_trading": False,
        "timer_enabled": True,
        "timer_position": "bottom",
        "timer_size": "medium",
        "timer_color": "#fbbf24",
        "timer_show_progress": True,
        "last_active_workspace": "session_mt5",
        "chart_candle_up": "#10b981",
        "chart_candle_down": "#ef4444",
        "chart_bg_color": "#111111",
        "chart_candle_border_visible": False,
        "chart_candle_border_color": "#ffffff",
        "risk_max_daily_loss": 500.0,
        "risk_max_contracts": 1,
        "risk_emotional_guard": False,
        "risk_locked_until": None,
    }
def save_settings(data: Dict[str, Any], user_id: str = "default_user") -> bool:
    current = get_settings(user_id)
    with get_connection() as conn:
        cursor = conn.cursor()
        def to_int(val):
            if isinstance(val, bool): return 1 if val else 0
            return val
        values = {
            "user_id": user_id,
            "platform": data.get("platform", current.get("platform", "mt5")),
            "theme": data.get("theme", current.get("theme", "dark")),
            "show_grid": to_int(data.get("show_grid", current.get("show_grid", True))),
            "show_watermark": to_int(data.get("show_watermark", current.get("show_watermark", True))),
            "one_click_trading": to_int(data.get("one_click_trading", current.get("one_click_trading", False))),
            "timer_enabled": to_int(data.get("timer_enabled", current.get("timer_enabled", True))),
            "timer_position": data.get("timer_position", current.get("timer_position", "bottom")),
            "timer_size": data.get("timer_size", current.get("timer_size", "medium")),
            "timer_color": data.get("timer_color", current.get("timer_color", "#fbbf24")),
            "timer_show_progress": to_int(data.get("timer_show_progress", current.get("timer_show_progress", True))),
            "last_active_workspace": data.get("last_active_workspace", current.get("last_active_workspace", "session_mt5")),
            "chart_candle_up": data.get("chart_candle_up", current.get("chart_candle_up", "#10b981")),
            "chart_candle_down": data.get("chart_candle_down", current.get("chart_candle_down", "#ef4444")),
            "chart_bg_color": data.get("chart_bg_color", current.get("chart_bg_color", "#111111")),
            "chart_candle_border_visible": to_int(data.get("chart_candle_border_visible", current.get("chart_candle_border_visible", False))),
            "chart_candle_border_color": data.get("chart_candle_border_color", current.get("chart_candle_border_color", "#ffffff")),
            "risk_max_daily_loss": data.get("risk_max_daily_loss", current.get("risk_max_daily_loss", 500.0)),
            "risk_max_contracts": data.get("risk_max_contracts", current.get("risk_max_contracts", 1)),
            "risk_emotional_guard": to_int(data.get("risk_emotional_guard", current.get("risk_emotional_guard", False))),
            "risk_locked_until": data.get("risk_locked_until", current.get("risk_locked_until", None)),
            "updated_at": datetime.now().isoformat(),
        }
        cursor.execute(
            """
            INSERT INTO user_settings (
                user_id, platform, theme, show_grid, show_watermark,
                one_click_trading, timer_enabled, timer_position, timer_size,
                timer_color, timer_show_progress, last_active_workspace,
                chart_candle_up, chart_candle_down, chart_bg_color,
                chart_candle_border_visible, chart_candle_border_color,
                risk_max_daily_loss, risk_max_contracts, risk_emotional_guard,
                risk_locked_until, updated_at
            ) VALUES (
                :user_id, :platform, :theme, :show_grid, :show_watermark,
                :one_click_trading, :timer_enabled, :timer_position, :timer_size,
                :timer_color, :timer_show_progress, :last_active_workspace,
                :chart_candle_up, :chart_candle_down, :chart_bg_color,
                :chart_candle_border_visible, :chart_candle_border_color,
                :risk_max_daily_loss, :risk_max_contracts, :risk_emotional_guard,
                :risk_locked_until, :updated_at
            )
            ON CONFLICT(user_id) DO UPDATE SET
                platform = excluded.platform,
                theme = excluded.theme,
                show_grid = excluded.show_grid,
                show_watermark = excluded.show_watermark,
                one_click_trading = excluded.one_click_trading,
                timer_enabled = excluded.timer_enabled,
                timer_position = excluded.timer_position,
                timer_size = excluded.timer_size,
                timer_color = excluded.timer_color,
                timer_show_progress = excluded.timer_show_progress,
                last_active_workspace = excluded.last_active_workspace,
                chart_candle_up = excluded.chart_candle_up,
                chart_candle_down = excluded.chart_candle_down,
                chart_bg_color = excluded.chart_bg_color,
                chart_candle_border_visible = excluded.chart_candle_border_visible,
                chart_candle_border_color = excluded.chart_candle_border_color,
                risk_max_daily_loss = excluded.risk_max_daily_loss,
                risk_max_contracts = excluded.risk_max_contracts,
                risk_emotional_guard = excluded.risk_emotional_guard,
                risk_locked_until = excluded.risk_locked_until,
                updated_at = excluded.updated_at
        """,
            values,
        )
        conn.commit()
        return True
def get_workspace(
    session_name: str, user_id: str = "default_user"
) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM workspaces WHERE user_id = ? AND session_name = ?",
            (user_id, session_name),
        )
        row = cursor.fetchone()
        if row:
            row_panel_sizes = json.loads(row["panel_sizes"]) if row["panel_sizes"] else {}
            return {
                "session_name": row["session_name"],
                "layout": row["layout"],
                "charts": json.loads(row["charts"]) if row["charts"] else [],
                "active_chart_id": row["active_chart_id"],
                "symbol": row["symbol"],
                "timeframe": row["timeframe"],
                "show_tape": bool(row["show_tape"]),
                "show_order_entry": bool(row["show_order_entry"]),
                "drawings": json.loads(row["drawings"]) if row["drawings"] else [],
                "panel_sizes": row_panel_sizes,
                "symbol_settings": json.loads(row["symbol_settings"])
                if row["symbol_settings"]
                else {},
                "indicator_settings": json.loads(row["indicator_settings"])
                if row["indicator_settings"]
                else {},
                "visibility_settings": json.loads(row["visibility_settings"])
                if row["visibility_settings"]
                else {},
                "show_dom": bool(row["show_dom"]),
                "updated_at": row["updated_at"],
                "tapeWidth": row_panel_sizes.get("tapeWidth"),
                "orderEntryWidth": row_panel_sizes.get("orderEntryWidth"),
                "domWidth": row_panel_sizes.get("domWidth"),
                "tape1Height": row_panel_sizes.get("tape1Height"),
                "tape2Height": row_panel_sizes.get("tape2Height"),
            }
        return None
def save_workspace(
    session_name: str, data: Dict[str, Any], user_id: str = "default_user"
) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        values = {
            "user_id": user_id,
            "session_name": session_name,
            "layout": data.get("layout", "single"),
            "charts": json.dumps(data.get("charts", [])),
            "active_chart_id": data.get("active_chart_id", 1),
            "symbol": data.get("symbol", "MNQ"),
            "timeframe": data.get("timeframe", "1m"),
            "show_tape": 1 if data.get("show_tape", True) else 0,
            "show_order_entry": 1 if data.get("show_order_entry", True) else 0,
            "drawings": json.dumps(data.get("drawings", [])),
            "panel_sizes": json.dumps(data.get("panel_sizes", {})),
            "symbol_settings": json.dumps(data.get("symbol_settings", {})),
            "indicator_settings": json.dumps(data.get("indicator_settings", {})),
            "visibility_settings": json.dumps(data.get("visibility_settings", {})),
            "show_dom": 1 if data.get("show_dom", False) or data.get("showDom", False) else 0,
            "updated_at": datetime.now().isoformat(),
        }
        cursor.execute(
            """
            INSERT INTO workspaces (
                user_id, session_name, layout, charts, active_chart_id,
                symbol, timeframe, show_tape, show_order_entry, drawings,
                panel_sizes, symbol_settings, indicator_settings,
                visibility_settings, show_dom, updated_at
            ) VALUES (
                :user_id, :session_name, :layout, :charts, :active_chart_id,
                :symbol, :timeframe, :show_tape, :show_order_entry, :drawings,
                :panel_sizes, :symbol_settings, :indicator_settings,
                :visibility_settings, :show_dom, :updated_at
            )
            ON CONFLICT(user_id, session_name) DO UPDATE SET
                layout = excluded.layout,
                charts = excluded.charts,
                active_chart_id = excluded.active_chart_id,
                symbol = excluded.symbol,
                timeframe = excluded.timeframe,
                show_tape = excluded.show_tape,
                show_order_entry = excluded.show_order_entry,
                drawings = excluded.drawings,
                panel_sizes = excluded.panel_sizes,
                symbol_settings = excluded.symbol_settings,
                indicator_settings = excluded.indicator_settings,
                visibility_settings = excluded.visibility_settings,
                show_dom = excluded.show_dom,
                updated_at = excluded.updated_at
        """,
            values,
        )
        conn.commit()
        print(f"[DATABASE] Workspace '{session_name}' guardado para usuario: {user_id}")
        return True
def get_last_active_workspace(user_id: str = "default_user") -> str:
    settings = get_settings(user_id)
    return settings.get("last_active_workspace", "session_mt5")
def set_last_active_workspace(session_name: str, user_id: str = "default_user") -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE user_settings
            SET last_active_workspace = ?, updated_at = ?
            WHERE user_id = ?
            """,
            (session_name, datetime.now().isoformat(), user_id),
        )
        conn.commit()
        print(f"[DATABASE] Último workspace activo: {session_name}")
        return cursor.rowcount > 0
def get_all_workspaces(user_id: str = "default_user") -> Dict[str, Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM workspaces WHERE user_id = ?", (user_id,))
        rows = cursor.fetchall()
        workspaces = {}
        for row in rows:
            workspaces[row["session_name"]] = {
                "layout": row["layout"],
                "charts": json.loads(row["charts"]) if row["charts"] else [],
                "active_chart_id": row["active_chart_id"],
                "symbol": row["symbol"],
                "timeframe": row["timeframe"],
                "show_tape": bool(row["show_tape"]),
                "show_order_entry": bool(row["show_order_entry"]),
                "drawings": json.loads(row["drawings"]) if row["drawings"] else [],
                "panel_sizes": json.loads(row["panel_sizes"])
                if row["panel_sizes"]
                else {},
                "symbol_settings": json.loads(row["symbol_settings"])
                if row["symbol_settings"]
                else {},
                "indicator_settings": json.loads(row["indicator_settings"])
                if row["indicator_settings"]
                else {},
                "visibility_settings": json.loads(row["visibility_settings"])
                if row["visibility_settings"]
                else {},
                "updated_at": row["updated_at"],
            }
        return workspaces

def delete_workspace(session_name: str, user_id: str = "default_user") -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM workspaces WHERE user_id = ? AND session_name = ?",
            (user_id, session_name),
        )
        conn.commit()
        return cursor.rowcount > 0
def get_ai_chat_history(
    limit: int = 50, user_id: str = "default_user"
) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM ai_chat_history WHERE user_id = ? ORDER BY id ASC LIMIT ?",
            (user_id, limit),
        )
        rows = cursor.fetchall()
        return [
            {
                "role": row["role"],
                "content": row["content"],
                "skill": row["skill"],
                "agent_actions": json.loads(row["agent_actions"])
                if row["agent_actions"]
                else None,
                "timestamp": row["timestamp"],
            }
            for row in rows
        ]
def save_ai_chat_message(
    role: str,
    content: str,
    skill: str = None,
    agent_actions: Dict = None,
    user_id: str = "default_user",
):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO ai_chat_history (user_id, role, content, skill, agent_actions)
            VALUES (?, ?, ?, ?, ?)
        """,
            (
                user_id,
                role,
                content,
                skill,
                json.dumps(agent_actions) if agent_actions else None,
            ),
        )
        conn.commit()
def clear_ai_chat_history(user_id: str = "default_user"):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM ai_chat_history WHERE user_id = ?", (user_id,))
        conn.commit()
def get_algolab_state(user_id: str = "default_user") -> Dict[str, Any]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM algolab_state WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            res = {
                "open_files": json.loads(row["open_files"])
                if row["open_files"]
                else [],
                "file_contents": json.loads(row["file_contents"])
                if row["file_contents"]
                else {},
                "active_file_path": row["active_file_path"],
            }
            try:
                res["is_chat_open"] = bool(row["is_chat_open"])
                res["chat_width"] = row["chat_width"]
            except:
                res["is_chat_open"] = False
                res["chat_width"] = 350
            return res
        return {
            "open_files": [],
            "file_contents": {},
            "active_file_path": None,
            "is_chat_open": False,
            "chat_width": 350,
        }
def save_algolab_state(state: Dict[str, Any], user_id: str = "default_user"):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO algolab_state (user_id, open_files, file_contents, active_file_path, is_chat_open, chat_width, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                open_files = excluded.open_files,
                file_contents = excluded.file_contents,
                active_file_path = excluded.active_file_path,
                is_chat_open = excluded.is_chat_open,
                chat_width = excluded.chat_width,
                updated_at = excluded.updated_at
        """,
            (
                user_id,
                json.dumps(state.get("open_files", [])),
                json.dumps(state.get("file_contents", {})),
                state.get("active_file_path"),
                1 if state.get("is_chat_open") else 0,
                state.get("chat_width", 350),
                datetime.now().isoformat(),
            ),
        )
        conn.commit()