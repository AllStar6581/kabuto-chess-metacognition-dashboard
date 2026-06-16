"""
Хранение данных в SQLite
"""
import sqlite3
import json
import os
from datetime import datetime
from typing import List, Dict, Optional


class Storage:
    """Управление локальным хранилищем данных"""
    
    def __init__(self, db_path: str = "chess_data.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Инициализирует базу данных"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Таблица партий
        c.execute('''
            CREATE TABLE IF NOT EXISTS games (
                id TEXT PRIMARY KEY,
                source TEXT,
                date TEXT,
                white TEXT,
                black TEXT,
                user_color TEXT,
                result TEXT,
                time_control TEXT,
                white_elo TEXT,
                black_elo TEXT,
                moves_json TEXT,
                analysis_json TEXT,
                final_fen TEXT,
                created_at TEXT
            )
        ''')
        
        # Таблица измерений навыков
        c.execute('''
            CREATE TABLE IF NOT EXISTS measurements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                games_count INTEGER,
                meta_json TEXT,
                sport_json TEXT,
                created_at TEXT
            )
        ''')
        
        # Таблица настроек
        c.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def save_games(self, games: List[Dict]):
        """Сохраняет партии в БД"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        for game in games:
            game_id = f"{game['source']}_{game['game_id']}"
            
            c.execute('''
                INSERT OR REPLACE INTO games 
                (id, source, date, white, black, user_color, result, 
                 time_control, white_elo, black_elo, moves_json, 
                 analysis_json, final_fen, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                game_id,
                game["source"],
                game["date"].isoformat() if game.get("date") else None,
                game["white"],
                game["black"],
                game["user_color"],
                game["result"],
                game.get("time_control", ""),
                game.get("white_elo", ""),
                game.get("black_elo", ""),
                json.dumps(game["moves"], ensure_ascii=False),
                json.dumps(game.get("analysis", []), ensure_ascii=False),
                game.get("final_fen", ""),
                datetime.now().isoformat(),
            ))
        
        conn.commit()
        conn.close()
    
    def load_games(self, source: Optional[str] = None, 
                   limit: Optional[int] = None) -> List[Dict]:
        """Загружает партии из БД"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        query = "SELECT * FROM games"
        params = []
        
        if source:
            query += " WHERE source = ?"
            params.append(source)
        
        query += " ORDER BY date ASC"
        
        if limit:
            query += f" LIMIT {limit}"
        
        c.execute(query, params)
        rows = c.fetchall()
        conn.close()
        
        games = []
        for row in rows:
            game = {
                "id": row[0],
                "source": row[1],
                "date": datetime.fromisoformat(row[2]) if row[2] else None,
                "white": row[3],
                "black": row[4],
                "user_color": row[5],
                "result": row[6],
                "time_control": row[7],
                "white_elo": row[8],
                "black_elo": row[9],
                "moves": json.loads(row[10]) if row[10] else [],
                "analysis": json.loads(row[11]) if row[11] else [],
                "final_fen": row[12],
            }
            games.append(game)
        
        return games
    
    def save_measurement(self, measurement: Dict):
        """Сохраняет измерение навыков"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute('''
            INSERT INTO measurements (date, games_count, meta_json, sport_json, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            measurement["date"].isoformat() if measurement.get("date") else None,
            measurement["games_count"],
            json.dumps(measurement["meta"]),
            json.dumps(measurement["sport"]),
            datetime.now().isoformat(),
        ))
        
        conn.commit()
        conn.close()
    
    def load_measurements(self) -> List[Dict]:
        """Загружает все измерения"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute("SELECT * FROM measurements ORDER BY date ASC")
        rows = c.fetchall()
        conn.close()
        
        measurements = []
        for row in rows:
            m = {
                "id": row[0],
                "date": datetime.fromisoformat(row[1]) if row[1] else None,
                "games_count": row[2],
                "meta": json.loads(row[3]),
                "sport": json.loads(row[4]),
            }
            measurements.append(m)
        
        return measurements
    
    def get_setting(self, key: str, default: str = None) -> Optional[str]:
        """Получает настройку"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = c.fetchone()
        conn.close()
        return row[0] if row else default
    
    def set_setting(self, key: str, value: str):
        """Сохраняет настройку"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''
            INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)
        ''', (key, value))
        conn.commit()
        conn.close()
    
    def get_stats(self) -> Dict:
        """Статистика БД"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute("SELECT COUNT(*) FROM games")
        games_count = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM measurements")
        measurements_count = c.fetchone()[0]
        
        c.execute("SELECT MIN(date), MAX(date) FROM games")
        date_range = c.fetchone()
        
        conn.close()
        
        return {
            "games_count": games_count,
            "measurements_count": measurements_count,
            "date_range": date_range,
        }