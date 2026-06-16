"""
Расчет 18 метрик: 9 мета-навыков + 9 спортивных
"""
import numpy as np
from typing import List, Dict, Tuple
from scipy import stats
from dataclasses import dataclass


@dataclass
class SkillScores:
    """Контейнер для оценок навыков"""
    meta: Dict[str, float]
    sport: Dict[str, float]
    
    def to_dict(self) -> Dict:
        return {"meta": self.meta, "sport": self.sport}


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def get_eval_drops(analysis: List[Dict], user_color: str) -> List[Tuple[int, float, float]]:
    """
    Возвращает список (индекс_хода, оценка_до, оценка_после)
    Оценки нормализованы относительно пользователя
    """
    drops = []
    for i in range(1, len(analysis) - 1):
        curr = analysis[i]
        prev = analysis[i - 1]
        
        # Ход сделал пользователь?
        if curr["side"] != user_color:
            continue
        
        eval_before = prev["score_cp"]
        eval_after = curr["score_cp"]
        
        # Нормализуем относительно пользователя
        if user_color == "black":
            eval_before = -eval_before
            eval_after = -eval_after
        
        drop = eval_before - eval_after
        drops.append((i, eval_before, eval_after, drop))
    
    return drops


def classify_position_type(analysis: List[Dict], idx: int) -> str:
    """
    Классифицирует тип позиции:
    - 'tactical': есть форсированные варианты с большой разницей
    - 'quiet': спокойная позиция
    - 'ambiguous': неоднозначная (топ-3 хода близки)
    - 'opening': дебют
    - 'endgame': эндшпиль
    """
    pos = analysis[idx]
    
    # Фаза игры
    move_num = idx // 2 + 1
    if move_num <= 10:
        return "opening"
    if pos["piece_count"] <= 8:
        return "endgame"
    
    # Неоднозначность: разница между топ-1 и топ-3
    if len(pos["top_moves"]) >= 3:
        top1 = pos["top_moves"][0]["score_cp"]
        top3 = pos["top_moves"][2]["score_cp"]
        if abs(top1 - top3) < 30:  # В пределах 0.3 пешки
            return "ambiguous"
    
    # Тактика: есть резкие варианты
    if len(pos["top_moves"]) >= 2:
        top1 = pos["top_moves"][0]["score_cp"]
        top2 = pos["top_moves"][1]["score_cp"]
        if abs(top1 - top2) > 150:  # Большая разница - тактика
            return "tactical"
    
    return "quiet"


def get_move_quality(analysis: List[Dict], idx: int, user_color: str) -> str:
    """
    Классифицирует качество хода:
    - 'blunder': потеря >3.0
    - 'mistake': потеря 1.0-3.0
    - 'inaccuracy': потеря 0.3-1.0
    - 'good': потеря <0.3
    - 'best': совпадает с топ-1 движка
    """
    if idx == 0 or idx >= len(analysis) - 1:
        return "unknown"
    
    pos = analysis[idx]
    prev = analysis[idx - 1]
    
    # Ход пользователя?
    if pos["side"] != user_color:
        return "unknown"
    
    # Оценка до и после
    eval_before = prev["score_cp"]
    eval_after = pos["score_cp"]
    
    if user_color == "black":
        eval_before = -eval_before
        eval_after = -eval_after
    
    loss = eval_before - eval_after
    
    # Совпадает с лучшим ходом?
    if pos["top_moves"] and pos["move_uci"] == pos["top_moves"][0]["move"]:
        return "best"
    
    if loss > 300:
        return "blunder"
    elif loss > 100:
        return "mistake"
    elif loss > 30:
        return "inaccuracy"
    else:
        return "good"


# ==================== МЕТА-НАВЫКИ ====================

def calc_decision_making(games: List[Dict]) -> float:
    """
    Навык 1: Принятие решений в неопределенности
    Точность в неоднозначных позициях (топ-3 хода близки)
    """
    total_loss = 0
    count = 0
    
    for game in games:
        analysis = game.get("analysis", [])
        user_color = game["user_color"]
        
        for i in range(1, len(analysis) - 1):
            if analysis[i]["side"] != user_color:
                continue
            if classify_position_type(analysis, i - 1) != "ambiguous":
                continue
            
            quality = get_move_quality(analysis, i, user_color)
            if quality == "blunder":
                total_loss += 3.0
            elif quality == "mistake":
                total_loss += 1.5
            elif quality == "inaccuracy":
                total_loss += 0.5
            count += 1
    
    if count == 0:
        return 5.0  # Недостаточно данных
    
    avg_loss = total_loss / count
    score = max(0, min(10, 10 - (avg_loss / 1.5)))
    return round(score, 2)


def calc_multi_level_thinking(games: List[Dict]) -> float:
    """
    Навык 2: Многоуровневое мышление
    Средняя глубина, на которой пользователь находит лучший ход движка
    """
    depths = []
    
    for game in games:
        analysis = game.get("analysis", [])
        user_color = game["user_color"]
        
        for i in range(1, len(analysis) - 1):
            if analysis[i]["side"] != user_color:
                continue
            
            # Смотрим, насколько глубоко в варианте лучший ход совпадает
            pos = analysis[i]
            if not pos["top_moves"]:
                continue
            
            best_move = pos["top_moves"][0]["move"]
            if pos["move_uci"] == best_move:
                # Пользователь нашел лучший ход - считаем глубину
                # Используем piece_count как прокси: чем меньше фигур, тем глубже расчет нужен
                depth_proxy = 32 - pos["piece_count"]
                depths.append(depth_proxy)
    
    if not depths:
        return 5.0
    
    avg_depth = np.mean(depths)
    score = max(0, min(10, avg_depth / 2))
    return round(score, 2)


def calc_pattern_recognition(games: List[Dict]) -> float:
    """
    Навык 3: Распознавание паттернов
    Точность в типичных позициях vs нетипичных
    """
    familiar_accuracy = []
    unfamiliar_accuracy = []
    
    for game in games:
        analysis = game.get("analysis", [])
        user_color = game["user_color"]
        
        for i in range(1, len(analysis) - 1):
            if analysis[i]["side"] != user_color:
                continue
            
            quality = get_move_quality(analysis, i, user_color)
            if quality == "unknown":
                continue
            
            is_good = quality in ["best", "good"]
            
            # "Знакомая" позиция = спокойная, много фигур (типичный миттельшпиль)
            pos_type = classify_position_type(analysis, i - 1)
            if pos_type == "quiet":
                familiar_accuracy.append(is_good)
            elif pos_type in ["tactical", "ambiguous"]:
                unfamiliar_accuracy.append(is_good)
    
    if not familiar_accuracy or not unfamiliar_accuracy:
        return 5.0
    
    familiar_rate = np.mean(familiar_accuracy)
    unfamiliar_rate = np.mean(unfamiliar_accuracy)
    
    # Если в знакомых лучше - паттерны работают
    ratio = familiar_rate / max(0.01, unfamiliar_rate)
    score = max(0, min(10, ratio * 5))
    return round(score, 2)


def calc_emotional_regulation(games: List[Dict]) -> float:
    """
    Навык 4: Эмоциональная регуляция (анти-тильт)
    Количество ошибок в течение 5 ходов после зева
    """
    post_blunder_errors = []
    
    for game in games:
        analysis = game.get("analysis", [])
        user_color = game["user_color"]
        
        for i in range(1, len(analysis) - 1):
            if analysis[i]["side"] != user_color:
                continue
            
            quality = get_move_quality(analysis, i, user_color)
            
            if quality == "blunder":
                # Считаем ошибки в следующих 5 ходах пользователя
                errors_after = 0
                moves_checked = 0
                j = i + 1
                while j < len(analysis) - 1 and moves_checked < 5:
                    if analysis[j]["side"] == user_color:
                        q = get_move_quality(analysis, j, user_color)
                        if q in ["blunder", "mistake"]:
                            errors_after += 1
                        moves_checked += 1
                    j += 1
                
                post_blunder_errors.append(errors_after)
    
    if not post_blunder_errors:
        return 10.0  # Нет зевков - идеальная регуляция
    
    avg_errors = np.mean(post_blunder_errors)
    score = max(0, min(10, 10 - avg_errors * 2))
    return round(score, 2)


def calc_resource_management(games: List[Dict]) -> float:
    """
    Навык 6: Управление ресурсами
    Эффективность: соотношение качества хода к сложности позиции
    """
    efficiencies = []
    
    for game in games:
        analysis = game.get("analysis", [])
        user_color = game["user_color"]
        
        for i in range(1, len(analysis) - 1):
            if analysis[i]["side"] != user_color:
                continue
            
            quality = get_move_quality(analysis, i, user_color)
            if quality == "unknown":
                continue
            
            # Сложность позиции = разница между топ-1 и топ-3
            pos = analysis[i - 1]
            if len(pos["top_moves"]) >= 3:
                complexity = abs(pos["top_moves"][0]["score_cp"] - 
                                pos["top_moves"][2]["score_cp"]) / 100
            else:
                complexity = 0.5
            
            # Качество хода
            quality_score = {
                "best": 1.0, "good": 0.8, "inaccuracy": 0.4,
                "mistake": 0.1, "blunder": 0.0
            }.get(quality, 0.5)
            
            # Эффективность = качество / сложность
            if complexity > 0:
                efficiencies.append(quality_score / max(0.1, complexity))
    
    if not efficiencies:
        return 5.0
    
    avg_eff = np.mean(efficiencies)
    score = max(0, min(10, avg_eff * 5))
    return round(score, 2)


def calc_adaptability(games: List[Dict]) -> float:
    """
    Навык 7: Адаптивность
    Точность после резких изменений оценки (когда соперник сделал сильный ход)
    """
    post_change_quality = []
    
    for game in games:
        analysis = game.get("analysis", [])
        user_color = game["user_color"]
        
        for i in range(2, len(analysis) - 1):
            if analysis[i]["side"] != user_color:
                continue
            
            # Резкое изменение оценки на ходе соперника
            prev_eval = analysis[i - 2]["score_cp"]
            curr_eval = analysis[i - 1]["score_cp"]
            
            if user_color == "black":
                prev_eval = -prev_eval
                curr_eval = -curr_eval
            
            change = abs(curr_eval - prev_eval)
            
            if change > 100:  # Резкое изменение
                quality = get_move_quality(analysis, i, user_color)
                if quality != "unknown":
                    post_change_quality.append(quality in ["best", "good", "inaccuracy"])
    
    if not post_change_quality:
        return 5.0
    
    score = np.mean(post_change_quality) * 10
    return round(score, 2)


def calc_patience(games: List[Dict]) -> float:
    """
    Навык 8: Терпение и проактивность
    Точность в спокойных позициях (без тактики)
    """
    quiet_quality = []
    
    for game in games:
        analysis = game.get("analysis", [])
        user_color = game["user_color"]
        
        for i in range(1, len(analysis) - 1):
            if analysis[i]["side"] != user_color:
                continue
            
            pos_type = classify_position_type(analysis, i - 1)
            if pos_type != "quiet":
                continue
            
            quality = get_move_quality(analysis, i, user_color)
            if quality != "unknown":
                quiet_quality.append(quality in ["best", "good"])
    
    if not quiet_quality:
        return 5.0
    
    score = np.mean(quiet_quality) * 10
    return round(score, 2)


def calc_focus(games: List[Dict]) -> float:
    """
    Навык 9: Фокус (Deep Work)
    Консистентность качества на протяжении партии
    """
    consistencies = []
    
    for game in games:
        analysis = game.get("analysis", [])
        user_color = game["user_color"]
        
        qualities = []
        for i in range(1, len(analysis) - 1):
            if analysis[i]["side"] != user_color:
                continue
            quality = get_move_quality(analysis, i, user_color)
            if quality != "unknown":
                q_score = {
                    "best": 4, "good": 3, "inaccuracy": 2,
                    "mistake": 1, "blunder": 0
                }.get(quality, 2)
                qualities.append(q_score)
        
        if len(qualities) >= 10:
            # Коэффициент вариации: чем ниже, тем стабильнее
            cv = np.std(qualities) / max(0.01, np.mean(qualities))
            consistencies.append(1 - min(1, cv))
    
    if not consistencies:
        return 5.0
    
    score = np.mean(consistencies) * 10
    return round(score, 2)


def calc_metacognition(games: List[Dict]) -> float:
    """
    Навык 5: Метакогниция
    Прокси-метрика: способность избегать повторяющихся ошибок одного типа
    (настоящая метакогниция требует журнала, но это хорошая аппроксимация)
    """
    if len(games) < 10:
        return 5.0
    
    # Разделяем на первую и вторую половину
    mid = len(games) // 2
    first_half = games[:mid]
    second_half = games[mid:]
    
    def get_error_distribution(game_subset):
        errors = {"tactical": 0, "positional": 0, "opening": 0, "endgame": 0, "total": 0}
        for game in game_subset:
            analysis = game.get("analysis", [])
            user_color = game["user_color"]
            for i in range(1, len(analysis) - 1):
                if analysis[i]["side"] != user_color:
                    continue
                quality = get_move_quality(analysis, i, user_color)
                if quality in ["blunder", "mistake"]:
                    errors["total"] += 1
                    pos_type = classify_position_type(analysis, i - 1)
                    if pos_type == "tactical":
                        errors["tactical"] += 1
                    elif pos_type == "quiet":
                        errors["positional"] += 1
                    elif pos_type == "opening":
                        errors["opening"] += 1
                    elif pos_type == "endgame":
                        errors["endgame"] += 1
        return errors
    
    first_errors = get_error_distribution(first_half)
    second_errors = get_error_distribution(second_half)
    
    if first_errors["total"] == 0:
        return 10.0
    
    # Если во второй половине ошибок меньше - метакогниция работает
    reduction = (first_errors["total"] - second_errors["total"]) / first_errors["total"]
    
    score = max(0, min(10, 5 + reduction * 10))
    return round(score, 2)


# ==================== СПОРТИВНЫЕ НАВЫКИ ====================

def calc_tactics(games: List[Dict]) -> float:
    """Спортивный навык 1: Тактическое зрение"""
    tactical_blunders = 0
    tactical_positions = 0
    
    for game in games:
        analysis = game.get("analysis", [])
        user_color = game["user_color"]
        
        for i in range(1, len(analysis) - 1):
            if analysis[i]["side"] != user_color:
                continue
            if classify_position_type(analysis, i - 1) != "tactical":
                continue
            
            tactical_positions += 1
            quality = get_move_quality(analysis, i, user_color)
            if quality in ["blunder", "mistake"]:
                tactical_blunders += 1
    
    if tactical_positions == 0:
        return 5.0
    
    score = (1 - tactical_blunders / tactical_positions) * 10
    return round(max(0, min(10, score)), 2)


def calc_calculation(games: List[Dict]) -> float:
    """Спортивный навык 2: Расчет вариантов"""
    # Прокси: точность в сложных тактических позициях
    return calc_tactics(games)  # Упрощенно, но коррелирует


def calc_positional(games: List[Dict]) -> float:
    """Спортивный навык 3: Позиционное понимание"""
    quiet_losses = 0
    quiet_moves = 0
    
    for game in games:
        analysis = game.get("analysis", [])
        user_color = game["user_color"]
        
        for i in range(1, len(analysis) - 1):
            if analysis[i]["side"] != user_color:
                continue
            if classify_position_type(analysis, i - 1) != "quiet":
                continue
            
            quiet_moves += 1
            quality = get_move_quality(analysis, i, user_color)
            if quality in ["inaccuracy", "mistake", "blunder"]:
                quiet_losses += 1
    
    if quiet_moves == 0:
        return 5.0
    
    score = (1 - quiet_losses / quiet_moves) * 10
    return round(max(0, min(10, score)), 2)


def calc_opening(games: List[Dict]) -> float:
    """Спортивный навык 4: Дебютная подготовка"""
    opening_losses = []
    
    for game in games:
        analysis = game.get("analysis", [])
        user_color = game["user_color"]
        
        for i in range(1, min(21, len(analysis) - 1)):  # Первые 10 ходов
            if analysis[i]["side"] != user_color:
                continue
            
            quality = get_move_quality(analysis, i, user_color)
            if quality != "unknown":
                loss = {"best": 0, "good": 0.1, "inaccuracy": 0.5, 
                        "mistake": 1.5, "blunder": 3.0}.get(quality, 0.5)
                opening_losses.append(loss)
    
    if not opening_losses:
        return 5.0
    
    avg_loss = np.mean(opening_losses)
    score = max(0, min(10, 10 - avg_loss * 2))
    return round(score, 2)


def calc_endgame(games: List[Dict]) -> float:
    """Спортивный навык 5: Техника эндшпиля"""
    endgame_quality = []
    
    for game in games:
        analysis = game.get("analysis", [])
        user_color = game["user_color"]
        
        for i in range(1, len(analysis) - 1):
            if analysis[i]["side"] != user_color:
                continue
            if classify_position_type(analysis, i - 1) != "endgame":
                continue
            
            quality = get_move_quality(analysis, i, user_color)
            if quality != "unknown":
                endgame_quality.append(quality in ["best", "good"])
    
    if not endgame_quality:
        return 5.0
    
    score = np.mean(endgame_quality) * 10
    return round(score, 2)


def calc_time_management(games: List[Dict]) -> float:
    """Спортивный навык 6: Контроль времени"""
    late_errors = []
    early_errors = []
    
    for game in games:
        analysis = game.get("analysis", [])
        user_color = game["user_color"]
        
        # Безопасный доступ через .get()
        total_user_moves = sum(1 for a in analysis if a.get("side") == user_color)
        
        for i in range(1, len(analysis) - 1):
            # Безопасный доступ
            if analysis[i].get("side") != user_color:
                continue
            
            quality = get_move_quality(analysis, i, user_color)
            if quality in ["blunder", "mistake"]:
                move_num = i // 2 + 1
                if move_num > total_user_moves * 0.7:
                    late_errors.append(1)
                else:
                    early_errors.append(1)
    
    if not late_errors and not early_errors:
        return 10.0
    
    late_rate = len(late_errors) / max(1, len(late_errors) + len(early_errors))
    score = max(0, min(10, 10 - late_rate * 10))
    return round(score, 2)


def calc_converting_wins(games: List[Dict]) -> float:
    """Спортивный навык 7: Реализация преимущества"""
    converted = 0
    total_winning = 0
    
    for game in games:
        analysis = game.get("analysis", [])
        user_color = game["user_color"]
        
        had_winning = False
        for pos in analysis:
            score = pos["score_cp"]
            if user_color == "black":
                score = -score
            if score > 200:
                had_winning = True
                break
        
        if had_winning:
            total_winning += 1
            if game["result"] == "1-0" and user_color == "white":
                converted += 1
            elif game["result"] == "0-1" and user_color == "black":
                converted += 1
    
    if total_winning == 0:
        return 5.0
    
    score = (converted / total_winning) * 10
    return round(score, 2)


def calc_defense(games: List[Dict]) -> float:
    """Спортивный навык 8: Защита худших позиций"""
    saved = 0
    total_losing = 0
    
    for game in games:
        analysis = game.get("analysis", [])
        user_color = game["user_color"]
        
        had_losing = False
        for pos in analysis:
            score = pos["score_cp"]
            if user_color == "black":
                score = -score
            if score < -200:
                had_losing = True
                break
        
        if had_losing:
            total_losing += 1
            if game["result"] == "1/2-1/2":
                saved += 1
    
    if total_losing == 0:
        return 5.0
    
    score = (saved / total_losing) * 10
    return round(score, 2)


def calc_opponent_adaptation(games: List[Dict]) -> float:
    """Спортивный навык 9: Подготовка к сопернику"""
    # Прокси: точность против более сильных vs более слабых
    vs_stronger = []
    vs_weaker = []
    
    for game in games:
        analysis = game.get("analysis", [])
        user_color = game["user_color"]
        
        try:
            user_elo = int(game.get(f"{user_color}_elo", 0))
            opp_color = "black" if user_color == "white" else "white"
            opp_elo = int(game.get(f"{opp_color}_elo", 0))
        except:
            continue
        
        if user_elo == 0 or opp_elo == 0:
            continue
        
        qualities = []
        for i in range(1, len(analysis) - 1):
            if analysis[i]["side"] != user_color:
                continue
            quality = get_move_quality(analysis, i, user_color)
            if quality != "unknown":
                qualities.append(quality in ["best", "good"])
        
        if qualities:
            accuracy = np.mean(qualities)
            if opp_elo > user_elo + 100:
                vs_stronger.append(accuracy)
            elif opp_elo < user_elo - 100:
                vs_weaker.append(accuracy)
    
    if not vs_stronger or not vs_weaker:
        return 5.0
    
    ratio = np.mean(vs_stronger) / max(0.01, np.mean(vs_weaker))
    score = max(0, min(10, ratio * 10))
    return round(score, 2)


# ==================== АГРЕГАТОР ====================

def calculate_all_skills(games: List[Dict]) -> SkillScores:
    """Рассчитывает все 18 метрик"""
    
    meta = {
        "decision_making": calc_decision_making(games),
        "multi_level_thinking": calc_multi_level_thinking(games),
        "pattern_recognition": calc_pattern_recognition(games),
        "emotional_regulation": calc_emotional_regulation(games),
        "metacognition": calc_metacognition(games),
        "resource_management": calc_resource_management(games),
        "adaptability": calc_adaptability(games),
        "patience": calc_patience(games),
        "focus": calc_focus(games),
    }
    
    sport = {
        "tactics": calc_tactics(games),
        "calculation": calc_calculation(games),
        "positional": calc_positional(games),
        "opening": calc_opening(games),
        "endgame": calc_endgame(games),
        "time_management": calc_time_management(games),
        "converting_wins": calc_converting_wins(games),
        "defense": calc_defense(games),
        "opponent_adaptation": calc_opponent_adaptation(games),
    }
    
    return SkillScores(meta=meta, sport=sport)


def calculate_dynamics(games: List[Dict], window_size: int = 30, 
                       step: int = 10) -> List[Dict]:
    """Рассчитывает динамику навыков по скользящему окну"""
    measurements = []
    
    for i in range(0, max(1, len(games) - window_size + 1), step):
        window = games[i:i + window_size]
        if len(window) < 10:  # Минимум для надежной оценки
            continue
        
        scores = calculate_all_skills(window)
        
        measurements.append({
            "date": window[-1].get("date"),
            "games_count": len(window),
            "meta": scores.meta,
            "sport": scores.sport,
        })
    
    return measurements


def check_significant_change(scores_before: Dict, scores_after: Dict, 
                             threshold: float = 0.5) -> Dict[str, str]:
    """
    Определяет значимые изменения между периодами
    threshold: минимальное изменение для считания значимым
    """
    changes = {}
    
    for category in ["meta", "sport"]:
        for skill in scores_before[category]:
            before = scores_before[category][skill]
            after = scores_after[category][skill]
            delta = after - before
            
            if abs(delta) >= threshold:
                direction = "↑" if delta > 0 else "↓"
                changes[f"{category}.{skill}"] = f"{direction} {delta:+.2f}"
    
    return changes