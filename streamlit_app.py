"""
Главное Streamlit-приложение: Система личного развития через шахматы
"""
import streamlit as st
import os
from datetime import datetime

from api_clients import load_games
from analyzer import PositionAnalyzer
from metrics import calculate_all_skills, calculate_dynamics
from visualizations import (
    plot_radar, plot_radar_comparison, plot_sparklines,
    plot_heatmap, plot_progress_gauge, META_NAMES, SPORT_NAMES
)
from storage import Storage


# ==================== НАСТРОЙКИ ====================
# Укажите свои никнеймы здесь
LICHESS_USERNAME = "AlastarKr"  # Например: "your_lichess_nick"
CHESSCOM_USERNAME = "AlastarKr"  # Например: "your_chesscom_nick"

STOCKFISH_PATH = None  # None = автопоиск, или укажите путь явно
MAX_GAMES_TO_LOAD = 1  # Для первой загрузки
WINDOW_SIZE = 30  # Размер скользящего окна для динамики


# ==================== ИНИЦИАЛИЗАЦИЯ ====================
st.set_page_config(
    page_title="Шахматная система развития",
    page_icon="♟️",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def get_storage():
    return Storage()


@st.cache_resource
def get_analyzer():
    try:
        return PositionAnalyzer(stockfish_path=STOCKFISH_PATH)
    except Exception as e:
        st.error(f"Ошибка инициализации Stockfish: {e}")
        return None


def main():
    st.title("♟️ Система личного развития через шахматы")
    st.markdown("""
    Эта система анализирует ваши партии с **Lichess** и **Chess.com**, 
    рассчитывает **9 мета-навыков** и **9 спортивных навыков**, 
    отслеживает динамику и помогает вам развиваться как в шахматах, так и в жизни.
    """)
    
    storage = get_storage()
    
    # ==================== САЙДБАР ====================
    with st.sidebar:
        st.header("⚙️ Настройки")
        
        # Никнеймы
        lichess_user = st.text_input("Lichess username", value=LICHESS_USERNAME)
        chesscom_user = st.text_input("Chess.com username", value=CHESSCOM_USERNAME)
        
        st.divider()
        
        # Действия
        st.header("📥 Данные")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Загрузить партии", use_container_width=True):
                load_and_analyze_games(lichess_user, chesscom_user, storage)
        
        with col2:
            if st.button("📊 Пересчитать метрики", use_container_width=True):
                recalculate_metrics(storage)
        
        st.divider()
        
        # Статистика
        st.header("📈 Статистика")
        stats = storage.get_stats()
        st.metric("Партий в базе", stats["games_count"])
        st.metric("Измерений", stats["measurements_count"])
        
        if stats["date_range"][0]:
            st.caption(f"Период: {stats['date_range'][0][:10]} — {stats['date_range'][1][:10]}")
    
    # ==================== ОСНОВНОЙ КОНТЕНТ ====================
    
    # Проверяем наличие данных
    games = storage.load_games()
    
    if not games:
        st.warning("⚠️ Нет данных. Загрузите партии через боковую панель.")
        show_instructions()
        return
    
    # Вкладки
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🎯 Обзор",
        "🧠 Мета-навыки",
        "♟️ Спортивные навыки",
        "📈 Динамика",
        "🎮 Партии",
    ])
    
    with tab1:
        show_overview(storage, games)
    
    with tab2:
        show_meta_skills(storage, games)
    
    with tab3:
        show_sport_skills(storage, games)
    
    with tab4:
        show_dynamics(storage)
    
    with tab5:
        show_games_list(games)


def load_and_analyze_games(lichess_user: str, chesscom_user: str, storage: Storage):
    """Загружает и анализирует партии"""
    if not lichess_user and not chesscom_user:
        st.error("Укажите хотя бы один никнейм!")
        return
    
    analyzer = get_analyzer()
    if not analyzer:
        st.error("Stockfish не доступен. Невозможно анализировать партии.")
        return
    
    progress = st.progress(0)
    status = st.empty()
    
    try:
        # Шаг 1: Загрузка
        status.text("📥 Загрузка партий...")
        progress.progress(10)
        
        games = load_games(
            lichess_user=lichess_user or None,
            chesscom_user=chesscom_user or None,
            max_games_per_source=MAX_GAMES_TO_LOAD,
        )
        
        if not games:
            st.error("Не удалось загрузить партии. Проверьте никнеймы.")
            return
        
        progress.progress(30)
        
        # Фильтруем уже проанализированные
        existing_ids = {g["id"] for g in storage.load_games()}
        new_games = [g for g in games if f"{g['source']}_{g['game_id']}" not in existing_ids]
        
        if not new_games:
            st.info("Все партии уже загружены.")
            progress.progress(100)
            return
        
        status.text(f"🔍 Анализ {len(new_games)} новых партий через Stockfish...")
        
        # Шаг 2: Анализ
        analyzed_games = []
        for i, game in enumerate(new_games):
            try:
                analyzed = analyzer.analyze_game(game)
                analyzed_games.append(analyzed)
                progress.progress(30 + int(60 * (i + 1) / len(new_games)))
            except Exception as e:
                st.warning(f"Ошибка анализа партии {game['game_id']}: {e}")
        
        # Шаг 3: Сохранение
        status.text("💾 Сохранение в базу...")
        storage.save_games(analyzed_games)
        
        progress.progress(100)
        st.success(f"✅ Загружено и проанализировано {len(analyzed_games)} партий!")
        
        # Автоматически пересчитываем метрики
        recalculate_metrics(storage)
        
    except Exception as e:
        st.error(f"Ошибка: {e}")
        import traceback
        st.code(traceback.format_exc())
    finally:
        progress.empty()
        status.empty()


def recalculate_metrics(storage: Storage):
    """Пересчитывает все метрики и сохраняет измерения"""
    games = storage.load_games()
    
    if len(games) < 10:
        st.warning("Нужно минимум 10 партий для расчета метрик.")
        return
    
    progress = st.progress(0)
    status = st.empty()
    
    try:
        status.text("📊 Расчет метрик...")
        
        # Считаем по скользящему окну
        measurements = calculate_dynamics(games, window_size=WINDOW_SIZE, step=10)
        
        # Сохраняем все измерения
        for i, m in enumerate(measurements):
            storage.save_measurement(m)
            progress.progress((i + 1) / len(measurements))
        
        # Также считаем текущие метрики на всех партиях
        current_scores = calculate_all_skills(games)
        storage.save_measurement({
            "date": datetime.now(),
            "games_count": len(games),
            "meta": current_scores.meta,
            "sport": current_scores.sport,
        })
        
        st.success(f"✅ Рассчитано {len(measurements) + 1} измерений!")
        
    except Exception as e:
        st.error(f"Ошибка расчета: {e}")
        import traceback
        st.code(traceback.format_exc())
    finally:
        progress.empty()
        status.empty()


def show_overview(storage: Storage, games):
    """Вкладка 'Обзор'"""
    st.header("🎯 Общий обзор")
    
    measurements = storage.load_measurements()
    
    if not measurements:
        st.info("Метрики еще не рассчитаны. Нажмите 'Пересчитать метрики' в боковой панели.")
        return
    
    # Текущие значения (последнее измерение)
    current = measurements[-1]
    previous = measurements[-2] if len(measurements) > 1 else None
    
    # Два радара рядом
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🧠 Мета-навыки")
        fig = plot_radar(current, "meta")
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.subheader("♟️ Спортивные навыки")
        fig = plot_radar(current, "sport")
        st.plotly_chart(fig, use_container_width=True)
    
    st.divider()
    
    # Общие индикаторы
    col1, col2 = st.columns(2)
    
    with col1:
        fig = plot_progress_gauge(current, "meta")
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        fig = plot_progress_gauge(current, "sport")
        st.plotly_chart(fig, use_container_width=True)
    
    # Топ-3 сильных и слабых навыков
    st.subheader("🔍 Ключевые наблюдения")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 💪 Сильные стороны")
        meta_sorted = sorted(current["meta"].items(), key=lambda x: x[1], reverse=True)
        for skill, score in meta_sorted[:3]:
            st.success(f"**{META_NAMES[skill]}**: {score:.1f}/10")
    
    with col2:
        st.markdown("#### 🎯 Точки роста")
        meta_sorted = sorted(current["meta"].items(), key=lambda x: x[1])
        for skill, score in meta_sorted[:3]:
            st.warning(f"**{META_NAMES[skill]}**: {score:.1f}/10")
    
    # Если есть предыдущее измерение - показываем изменения
    if previous:
        st.divider()
        st.subheader("📈 Изменения с прошлого измерения")
        
        from metrics import check_significant_changes
        changes = check_significant_changes(previous, current)
        
        if changes:
            for key, change in changes.items():
                category, skill = key.split(".")
                name = META_NAMES.get(skill, SPORT_NAMES.get(skill, skill))
                if "↑" in change:
                    st.success(f"**{name}**: {change}")
                else:
                    st.error(f"**{name}**: {change}")
        else:
            st.info("Значимых изменений не обнаружено.")


def show_meta_skills(storage: Storage, games):
    """Вкладка 'Мета-навыки'"""
    st.header("🧠 Мета-навыки")
    st.markdown("""
    Эти навыки развиваются через шахматы, но работают везде: в бизнесе, 
    отношениях, принятии решений.
    """)
    
    measurements = storage.load_measurements()
    if not measurements:
        st.info("Метрики еще не рассчитаны.")
        return
    
    current = measurements[-1]
    
    # Детальный разбор каждого навыка
    for skill_key, skill_name in META_NAMES.items():
        with st.expander(f"### {skill_name} — {current['meta'][skill_key]:.1f}/10"):
            score = current['meta'][skill_key]
            
            # Описание
            descriptions = {
                "decision_making": "Способность выбирать оптимальное действие в неоднозначных позициях, где нет единственного правильного ответа.",
                "multi_level_thinking": "Способность просчитывать цепочки причинно-следственных связей на несколько ходов вперед.",
                "pattern_recognition": "Умение видеть знакомые структуры и применять типовые решения.",
                "emotional_regulation": "Способность сохранять качество решений после ошибок (анти-тильт).",
                "metacognition": "Способность анализировать собственное мышление и избегать повторяющихся ошибок.",
                "resource_management": "Эффективность использования времени и энергии в сложных позициях.",
                "adaptability": "Умение менять план, когда ситуация резко изменилась.",
                "patience": "Способность улучшать позицию постепенно, без суеты, в спокойных позициях.",
                "focus": "Консистентность качества на протяжении всей партии.",
            }
            
            st.markdown(f"**Что измеряет:** {descriptions.get(skill_key, '')}")
            
            # Рекомендации
            if score < 5:
                st.error("🔴 Требует внимания. Рекомендую сфокусироваться на этом навыке.")
            elif score < 7:
                st.warning("🟡 Средний уровень. Есть куда расти.")
            else:
                st.success("🟢 Сильный навык. Поддерживайте на этом уровне.")


def show_sport_skills(storage: Storage, games):
    """Вкладка 'Спортивные навыки'"""
    st.header("♟️ Спортивные навыки")
    st.markdown("Навыки, специфичные для игры в шахматы.")
    
    measurements = storage.load_measurements()
    if not measurements:
        st.info("Метрики еще не рассчитаны.")
        return
    
    current = measurements[-1]
    
    for skill_key, skill_name in SPORT_NAMES.items():
        with st.expander(f"### {skill_name} — {current['sport'][skill_key]:.1f}/10"):
            score = current['sport'][skill_key]
            
            if score < 5:
                st.error("🔴 Слабый навык. Нужны целенаправленные тренировки.")
            elif score < 7:
                st.warning("🟡 Средний уровень.")
            else:
                st.success("🟢 Сильный навык.")


def show_dynamics(storage: Storage):
    """Вкладка 'Динамика'"""
    st.header("📈 Динамика навыков")
    
    measurements = storage.load_measurements()
    
    if len(measurements) < 2:
        st.info("Нужно минимум 2 измерения для отображения динамики. Загрузите больше партий и пересчитайте метрики.")
        return
    
    # Выбор категории
    category = st.radio("Категория", ["meta", "sport"], horizontal=True, 
                        format_func=lambda x: "🧠 Мета-навыки" if x == "meta" else "♟️ Спортивные")
    
    # Сравнение периодов
    st.subheader("Сравнение периодов")
    
    col1, col2 = st.columns(2)
    
    prev_idx = max(0, len(measurements) - 2)
    curr_idx = len(measurements) - 1
    
    with col1:
        prev_option = st.selectbox(
            "Предыдущий период",
            range(len(measurements)),
            index=prev_idx,
            format_func=lambda i: f"{measurements[i]['date'].strftime('%Y-%m-%d') if measurements[i]['date'] else 'N/A'} ({measurements[i]['games_count']} партий)"
        )
    
    with col2:
        curr_option = st.selectbox(
            "Текущий период",
            range(len(measurements)),
            index=curr_idx,
            format_func=lambda i: f"{measurements[i]['date'].strftime('%Y-%m-%d') if measurements[i]['date'] else 'N/A'} ({measurements[i]['games_count']} партий)"
        )
    
    if prev_option != curr_option:
        fig = plot_radar_comparison(
            measurements[curr_option], 
            measurements[prev_option],
            category
        )
        st.plotly_chart(fig, use_container_width=True)
    
    st.divider()
    
    # Спарклайны
    st.subheader("Динамика по времени")
    fig = plot_sparklines(measurements, category)
    st.plotly_chart(fig, use_container_width=True)
    
    st.divider()
    
    # Тепловая карта
    st.subheader("Тепловая карта")
    fig = plot_heatmap(measurements, category)
    st.plotly_chart(fig, use_container_width=True)


def show_games_list(games):
    """Вкладка 'Партии'"""
    st.header("🎮 Ваши партии")
    
    # Фильтры
    col1, col2, col3 = st.columns(3)
    
    with col1:
        source_filter = st.multiselect(
            "Источник",
            ["lichess", "chesscom"],
            default=["lichess", "chesscom"],
            format_func=lambda x: "Lichess" if x == "lichess" else "Chess.com"
        )
    
    with col2:
        result_filter = st.multiselect(
            "Результат",
            ["1-0", "0-1", "1/2-1/2", "*"],
            default=["1-0", "0-1", "1/2-1/2", "*"],
            format_func=lambda x: {"1-0": "Победа белых", "0-1": "Победа черных", 
                                   "1/2-1/2": "Ничья", "*": "Незавершена"}[x]
        )
    
    with col3:
        limit = st.slider("Показать партий", 10, min(100, len(games)), 20)
    
    # Фильтруем
    filtered = [g for g in games 
                if g["source"] in source_filter 
                and g["result"] in result_filter]
    
    # Показываем последние
    filtered = filtered[-limit:]
    
    # Таблица
    data = []
    for g in reversed(filtered):
        user_elo = g.get(f"{g['user_color']}_elo", "?")
        data.append({
            "Дата": g["date"].strftime("%Y-%m-%d") if g["date"] else "?",
            "Источник": "Lichess" if g["source"] == "lichess" else "Chess.com",
            "Цвет": "⚪" if g["user_color"] == "white" else "⚫",
            "Соперник": g["black"] if g["user_color"] == "white" else g["white"],
            "Результат": g["result"],
            "Ходов": len(g["moves"]),
            "Ваш Elo": user_elo,
        })
    
    import pandas as pd
    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True, hide_index=True)


def show_instructions():
    """Показывает инструкции по установке"""
    st.markdown("""
    ## 🚀 Как начать
    
    ### 1. Установите зависимости
    ```bash
    pip install -r requirements.txt
    ```
    
    ### 2. Установите Stockfish
    
    **Linux:**
    ```bash
    sudo apt install stockfish
    ```
    
    **Mac:**
    ```bash
    brew install stockfish
    ```
    
    **Windows:**
    Скачайте с https://stockfishchess.org/download/ и добавьте в PATH
    
    ### 3. Укажите свои никнеймы
    
    Откройте `app.py` и заполните:
    ```python
    LICHESS_USERNAME = "ваш_ник_на_lichess"
    CHESSCOM_USERNAME = "ваш_ник_на_chesscom"
    ```
    
    ### 4. Запустите приложение
    ```bash
    streamlit run app.py
    ```
    
    ### 5. Загрузите партии
    
    В боковой панели нажмите **"Загрузить партии"**
    
    ---
    
    ## 📚 Что дальше?
    
    После загрузки партий система:
    1. Проанализирует каждую позицию через Stockfish
    2. Рассчитает 18 метрик (9 мета + 9 спорт)
    3. Построит радарные диаграммы
    4. Будет отслеживать динамику по мере появления новых партий
    
    ## 💡 Советы
    
    - Играйте с длинным контролем (15+10 или длиннее) для качественного анализа
    - Загружайте новые партии раз в неделю для отслеживания динамики
    - Фокусируйтесь на 1-2 самых слабых навыках за раз
    """)


if __name__ == "__main__":
    main()