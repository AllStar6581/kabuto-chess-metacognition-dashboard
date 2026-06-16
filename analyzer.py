"""
Анализ партий через Stockfish
Оптимизировано для Streamlit Community Cloud
"""
import chess
from stockfish import Stockfish
from typing import List, Dict, Optional
import os
import subprocess
import logging

logger = logging.getLogger(__name__)


class PositionAnalyzer:
    """Анализатор позиций через Stockfish"""
    
    # Путь к Stockfish на Streamlit Cloud (из packages.txt)
    CLOUD_PATH = "/usr/games/stockfish"
    
    def __init__(self, stockfish_path: Optional[str] = None,
                 threads: int = 2, hash_size: int = 256, depth: int = 16):
        """
        stockfish_path: путь к бинарнику. Если None - используется CLOUD_PATH
        threads: 2 (не больше, чтобы не перегружать Streamlit Cloud)
        hash_size: 256 МБ (экономим RAM)
        depth: 16 (оптимально для скорости/качества)
        """
        self.path = stockfish_path or self._find_stockfish()
        self.depth = depth
        
        # Проверяем, что бинарник запускается
        self._verify_binary()
        
        # Создаем Stockfish
        try:
            self.sf = Stockfish(
                path=self.path,
                parameters={
                    "Threads": threads,
                    "Hash": hash_size,
                    "MultiPV": 1,  # Только лучший ход (экономим ресурсы)
                }
            )
            # Проверяем работоспособность
            self.sf.get_engine_parameters()
            logger.info(f"Stockfish initialized: {self.path}")
        except Exception as e:
            logger.error(f"Failed to initialize Stockfish: {e}")
            raise RuntimeError(
                f"Stockfish не запустился по пути {self.path}.\n"
                f"Проверьте, что packages.txt содержит 'stockfish' "
                f"и приложение перезапущено."
            ) from e
    
    def _find_stockfish(self) -> str:
        """Находит Stockfish на Streamlit Cloud или локально"""
        # На Streamlit Cloud Stockfish всегда здесь
        if os.path.exists(self.CLOUD_PATH):
            return self.CLOUD_PATH
        
        # Локальные варианты
        local_paths = [
            "/usr/bin/stockfish",
            "/usr/local/bin/stockfish",
            "stockfish",  # В PATH
            "./stockfish",
        ]
        
        for path in local_paths:
            if os.path.exists(path) or self._is_in_path(path):
                return path
        
        raise FileNotFoundError(
            f"Stockfish не найден. На Streamlit Cloud он должен быть в {self.CLOUD_PATH}.\n"
            f"Убедитесь, что packages.txt содержит 'stockfish' и приложение перезапущено."
        )
    
    def _is_in_path(self, name: str) -> bool:
        """Проверяет, есть ли бинарник в PATH"""
        try:
            result = subprocess.run(
                ["which", name],
                capture_output=True,
                text=True,
                timeout=2
            )
            return result.returncode == 0
        except:
            return False
    
    def _verify_binary(self):
        """Проверяет, что бинарник запускается"""
        if not os.path.exists(self.path):
            # Может быть в PATH
            try:
                result = subprocess.run(
                    [self.path, "--help"],
                    capture_output=True,
                    timeout=5
                )
                # Stockfish не имеет --help, но должен запуститься
                return
            except FileNotFoundError:
                raise FileNotFoundError(f"Stockfish binary not found at {self.path}")
            except Exception as e:
                logger.warning(f"Binary check warning: {e}")
                return
        
        # Проверяем права доступа
        if not os.access(self.path, os.X_OK):
            try:
                os.chmod(self.path, 0o755)
                logger.info(f"Fixed permissions for {self.path}")
            except Exception as e:
                logger.warning(f"Cannot fix permissions: {e}")
    
    def analyze_position(self, fen: str) -> Dict:
        """Анализирует одну позицию"""
        try:
            self.sf.set_fen_position(fen)
            
            # Основная оценка
            eval_dict = self.sf.get_evaluation()
            
            # Определяем тип оценки
            if eval_dict["type"] == "mate":
                score_cp = (10000 - abs(eval_dict["value"]) * 10)
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
                "top_moves": [],  # MultiPV=1, нет топ-3
                "is_tablebase": len(board.piece_map()) <= 7,
                "piece_count": len(board.piece_map()),
            }
        except Exception as e:
            logger.error(f"Error analyzing position {fen}: {e}")
            # Возвращаем нейтральную оценку при ошибке
            return {
                "fen": fen,
                "score_cp": 0,
                "score_display": "0.00",
                "top_moves": [],
                "is_tablebase": False,
                "piece_count": 32,
            }
    
    def _format_score(self, cp: int) -> str:
        """Форматирует оценку для отображения"""
        if abs(cp) > 9000:
            moves_to_mate = (10000 - abs(cp)) // 10
            sign = "+" if cp > 0 else "-"
            return f"{sign}M{moves_to_mate}"
        else:
            return f"{cp / 100:+.2f}"
    
    def analyze_game(self, game: Dict, progress_callback=None) -> Dict:
        """Анализирует всю партию"""
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
        
        # Финальная позиция
        # final_analysis = self.analyze_position(game["final_fen"])
        # analysis.append({
        #     **final_analysis,
        #     "move_index": len(moves),
        #     "is_final": True,
        # })
        # Финальная позиция
        final_analysis = self.analyze_position(game["final_fen"])
        # Определяем сторону: если последний ход был белых, то финальная позиция - ход черных
        last_side = moves[-1]["side"] if moves else "white"
        final_side = "black" if last_side == "white" else "white"

        analysis.append({
            **final_analysis,
            "move_index": len(moves),
            "side": final_side,
            "is_final": True,
        })
        
        game["analysis"] = analysis
        return game
    
    def analyze_batch(self, games: List[Dict], progress_callback=None) -> List[Dict]:
        """Анализирует несколько партий"""
        analyzed = []
        total = len(games)
        
        for i, game in enumerate(games):
            def game_progress(p):
                if progress_callback:
                    overall = (i + p) / total
                    progress_callback(overall)
            
            try:
                analyzed.append(self.analyze_game(game, game_progress))
            except Exception as e:
                logger.error(f"Error analyzing game {game.get('game_id')}: {e}")
                # Продолжаем анализировать остальные партии
        
        return analyzed