"""
Анализ партий через Stockfish
"""
import chess
from stockfish import Stockfish
from typing import List, Dict, Optional
import os


class PositionAnalyzer:
    """Анализатор позиций через Stockfish"""
    
    def __init__(self, stockfish_path: Optional[str] = None, 
                 threads: int = 4, hash_size: int = 1024, depth: int = 18):
        """
        stockfish_path: путь к бинарнику Stockfish. Если None - ищет в системе
        threads: количество потоков
        hash_size: размер хеш-таблицы в МБ
        depth: глубина анализа (18 - оптимально для скорости/качества)
        """
        if stockfish_path is None:
            # Пробуем найти Stockfish в системе
            stockfish_path = self._find_stockfish()
        
        self.sf = Stockfish(
            path=stockfish_path,
            parameters={
                "Threads": threads,
                "Hash": hash_size,
                "MultiPV": 3,  # Топ-3 хода для анализа неоднозначности
            }
        )
        self.depth = depth
        self._enable_tablebases()
    
    def _find_stockfish(self) -> str:
        """Ищет Stockfish в системе"""
        possible_paths = [
            "stockfish",  # В PATH
            "/usr/bin/stockfish",
            "/usr/local/bin/stockfish",
            "C:/Program Files/Stockfish/stockfish.exe",
            os.path.expanduser("~/stockfish/stockfish"),
        ]
        
        for path in possible_paths:
            try:
                sf = Stockfish(path=path)
                sf.get_parameters()  # Проверяем работоспособность
                return path
            except:
                continue
        
        raise FileNotFoundError(
            "Stockfish не найден. Установите его и укажите путь явно.\n"
            "Linux: sudo apt install stockfish\n"
            "Mac: brew install stockfish\n"
            "Windows: скачайте с https://stockfishchess.org/download/"
        )
    
    def _enable_tablebases(self):
        """Включает tablebases для точного эндшпиля (если есть)"""
        # Опционально: если скачаны tablebases
        tb_paths = [
            os.path.expanduser("~/syzygy"),
            "/usr/share/stockfish/syzygy",
        ]
        for path in tb_paths:
            if os.path.exists(path):
                try:
                    self.sf.set_depth(self.depth)
                    # Stockfish автоматически использует tablebases если они в PATH
                except:
                    pass
    
    def analyze_position(self, fen: str) -> Dict:
        """Анализирует одну позицию"""
        self.sf.set_fen_position(fen)
        
        # Основная оценка
        eval_dict = self.sf.get_evaluation()
        
        # Топ-3 хода
        top_moves = self.sf.get_top_moves(3)
        
        # Определяем тип оценки
        if eval_dict["type"] == "mate":
            score_cp = 10000 - abs(eval_dict["value"])  # Мат = очень высокая оценка
            if eval_dict["value"] < 0:
                score_cp = -score_cp
        else:
            score_cp = eval_dict["value"]
        
        # Нормализуем относительно стороны
        board = chess.Board(fen)
        if board.turn == chess.BLACK:
            score_cp = -score_cp
        
        return {
            "fen": fen,
            "score_cp": score_cp,
            "score_display": self._format_score(score_cp),
            "top_moves": [
                {
                    "move": m["Move"],
                    "score_cp": self._normalize_move_score(m, board.turn),
                }
                for m in top_moves
            ],
            "is_tablebase": self._is_tablebase_position(fen),
            "piece_count": len(board.piece_map()),
        }
    
    def _normalize_move_score(self, move_data: Dict, turn) -> int:
        """Нормализует оценку хода относительно белых"""
        # Stockfish возвращает оценки в формате "cp X" или "mate X"
        # Нужно распарсить
        score_str = str(move_data.get("Centipawn", 0))
        try:
            cp = int(score_str)
        except:
            cp = 0
        
        if turn == chess.BLACK:
            cp = -cp
        return cp
    
    def _format_score(self, cp: int) -> str:
        """Форматирует оценку для отображения"""
        if abs(cp) > 9000:
            # Мат
            moves_to_mate = (10000 - abs(cp)) // 2
            sign = "+" if cp > 0 else "-"
            return f"{sign}M{moves_to_mate}"
        else:
            return f"{cp / 100:+.2f}"
    
    def _is_tablebase_position(self, fen: str) -> bool:
        """Проверяет, есть ли позиция в tablebase (≤7 фигур)"""
        board = chess.Board(fen)
        return len(board.piece_map()) <= 7
    
    def analyze_game(self, game: Dict, progress_callback=None) -> Dict:
        """
        Анализирует всю партию
        Возвращает игру с добавленным полем 'analysis'
        """
        analysis = []
        moves = game["moves"]
        
        for i, move_data in enumerate(moves):
            fen = move_data["fen_before"]
            pos_analysis = self.analyze_position(fen)
            pos_analysis["move_index"] = i
            pos_analysis["move_uci"] = move_data["uci"]
            pos_analysis["move_san"] = move_data["san"]
            pos_analysis["side"] = move_data["side"]
            analysis.append(pos_analysis)
            
            if progress_callback and i % 5 == 0:
                progress_callback(i / len(moves))
        
        # Анализируем финальную позицию
        final_analysis = self.analyze_position(game["final_fen"])
        analysis.append({
            **final_analysis,
            "move_index": len(moves),
            "is_final": True,
        })
        
        game["analysis"] = analysis
        return game
    
    def analyze_batch(self, games: List[Dict], progress_callback=None) -> List[Dict]:
        """Анализирует несколько партий с прогресс-баром"""
        analyzed = []
        total = len(games)
        
        for i, game in enumerate(games):
            def game_progress(p):
                if progress_callback:
                    overall = (i + p) / total
                    progress_callback(overall)
            
            analyzed.append(self.analyze_game(game, game_progress))
        
        return analyzed