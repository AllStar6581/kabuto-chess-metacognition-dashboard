"""
Клиенты для загрузки партий с Lichess и Chess.com
"""
import requests
import time
import io
import chess.pgn
from typing import List, Dict, Optional
from datetime import datetime


class LichessClient:
    """Клиент для Lichess API (открытый, без ключа)"""
    
    BASE_URL = "https://lichess.org/api"
    
    def __init__(self, username: str):
        self.username = username
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/x-chess-pgn",
            "User-Agent": f"ChessDevelopmentSystem/1.0 user:{username}"
        })
    
    def get_all_games(self, max_games: Optional[int] = None, 
                      since: Optional[int] = None,
                      until: Optional[int] = None) -> List[Dict]:
        """
        Загружает все партии пользователя в PGN формате
        since/until - timestamp в миллисекундах
        """
        url = f"{self.BASE_URL}/games/user/{self.username}"
        params = {
            "perfType": "blitz,rapid,classical",  # Исключаем bullet для качественного анализа
            "analysed": "false",  # Загружаем все, даже без анализа
            "sort": "dateAsc",
        }
        if since:
            params["since"] = since
        if until:
            params["until"] = until
        if max_games:
            params["max"] = max_games
        
        response = self.session.get(url, params=params, stream=True)
        response.raise_for_status()
        
        games = []
        pgn_text = response.text
        
        # Разделяем PGN на отдельные партии
        pgn_io = io.StringIO(pgn_text)
        while True:
            game = chess.pgn.read_game(pgn_io)
            if game is None:
                break
            
            parsed = self._parse_game(game)
            if parsed:
                games.append(parsed)
            
            if max_games and len(games) >= max_games:
                break
        
        return games
    
    def _parse_game(self, game) -> Optional[Dict]:
        """Парсит PGN-партию в структурированный dict"""
        headers = game.headers
        
        # Получаем дату
        date_str = headers.get("UTCDate", "")
        try:
            date = datetime.strptime(date_str, "%Y.%m.%d")
        except:
            date = None
        
        # Время контроля
        time_control = headers.get("TimeControl", "-")
        
        # Собираем ходы с позициями
        moves = []
        board = game.board()
        node = game
        
        while node.variations:
            next_node = node.variation(0)
            move = next_node.move
            uci = move.uci()
            
            moves.append({
                "move_number": (len(moves) // 2) + 1,
                "side": "white" if len(moves) % 2 == 0 else "black",
                "uci": uci,
                "san": board.san(move),
                "fen_before": board.fen(),
            })
            
            board.push(move)
            node = next_node
        
        # Результат
        result = headers.get("Result", "*")
        
        # Игрок (белые/черные)
        white_player = headers.get("White", "").lower()
        user_color = "white" if white_player == self.username.lower() else "black"
        
        return {
            "source": "lichess",
            "game_id": headers.get("Site", "").split("/")[-1],
            "date": date,
            "white": headers.get("White", ""),
            "black": headers.get("Black", ""),
            "user_color": user_color,
            "result": result,
            "time_control": time_control,
            "white_elo": headers.get("WhiteElo", ""),
            "black_elo": headers.get("BlackElo", ""),
            "moves": moves,
            "final_fen": board.fen(),
        }


class ChessComClient:
    """
    Клиент для Chess.com API
    Chess.com требует обхода Cloudflare, используем их публичный API
    """
    
    BASE_URL = "https://api.chess.com/pub"
    
    def __init__(self, username: str):
        self.username = username
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": f"ChessDevelopmentSystem/1.0 (contact: your@email.com)"
        })
    
    def get_all_games(self, max_games: Optional[int] = None) -> List[Dict]:
        """Загружает все партии через архивы"""
        # Сначала получаем список доступных архивов (по месяцам)
        archives_url = f"{self.BASE_URL}/player/{self.username}/games/archives"
        response = self.session.get(archives_url)
        response.raise_for_status()
        
        archives = response.json().get("archives", [])
        
        all_games = []
        
        # Загружаем каждый архив
        for archive_url in archives:
            try:
                time.sleep(0.5)  # Rate limiting
                response = self.session.get(archive_url)
                response.raise_for_status()
                
                games_data = response.json().get("games", [])
                
                for game_data in games_data:
                    parsed = self._parse_game(game_data)
                    if parsed:
                        all_games.append(parsed)
                    
                    if max_games and len(all_games) >= max_games:
                        return all_games
            except Exception as e:
                print(f"Error loading archive {archive_url}: {e}")
                continue
        
        return all_games
    
    def _parse_game(self, game_data: Dict) -> Optional[Dict]:
        """Парсит JSON-партию с Chess.com"""
        try:
            # PGN в ответе
            pgn_text = game_data.get("pgn", "")
            if not pgn_text:
                return None
            
            pgn_io = io.StringIO(pgn_text)
            game = chess.pgn.read_game(pgn_io)
            if not game:
                return None
            
            headers = game.headers
            date_str = headers.get("UTCDate", "")
            try:
                date = datetime.strptime(date_str, "%Y.%m.%d")
            except:
                date = None
            
            # Собираем ходы
            moves = []
            board = game.board()
            node = game
            
            while node.variations:
                next_node = node.variation(0)
                move = next_node.move
                
                moves.append({
                    "move_number": (len(moves) // 2) + 1,
                    "side": "white" if len(moves) % 2 == 0 else "black",
                    "uci": move.uci(),
                    "san": board.san(move),
                    "fen_before": board.fen(),
                })
                
                board.push(move)
                node = next_node
            
            white_player = headers.get("White", "").lower()
            user_color = "white" if white_player == self.username.lower() else "black"
            
            return {
                "source": "chesscom",
                "game_id": game_data.get("url", "").split("/")[-1],
                "date": date,
                "white": headers.get("White", ""),
                "black": headers.get("Black", ""),
                "user_color": user_color,
                "result": headers.get("Result", "*"),
                "time_control": game_data.get("time_control", ""),
                "white_elo": headers.get("WhiteElo", ""),
                "black_elo": headers.get("BlackElo", ""),
                "moves": moves,
                "final_fen": board.fen(),
            }
        except Exception as e:
            print(f"Error parsing game: {e}")
            return None


def load_games(lichess_user: Optional[str] = None, 
               chesscom_user: Optional[str] = None,
               max_games_per_source: Optional[int] = None) -> List[Dict]:
    """Универсальная функция загрузки с обоих сайтов"""
    all_games = []
    
    if lichess_user:
        print(f"Загрузка партий с Lichess для {lichess_user}...")
        client = LichessClient(lichess_user)
        games = client.get_all_games(max_games=max_games_per_source)
        all_games.extend(games)
        print(f"Загружено {len(games)} партий с Lichess")
    
    if chesscom_user:
        print(f"Загрузка партий с Chess.com для {chesscom_user}...")
        client = ChessComClient(chesscom_user)
        games = client.get_all_games(max_games=max_games_per_source)
        all_games.extend(games)
        print(f"Загружено {len(games)} партий с Chess.com")
    
    # Сортируем по дате
    all_games.sort(key=lambda g: g.get("date") or datetime.min)
    
    return all_games