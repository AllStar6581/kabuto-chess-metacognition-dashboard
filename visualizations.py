"""
Визуализации: радары, спарклайны, heatmap
"""
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np
from typing import List, Dict


# Русские названия навыков
META_NAMES = {
    "decision_making": "Принятие решений",
    "multi_level_thinking": "Многоуровневое мышление",
    "pattern_recognition": "Распознавание паттернов",
    "emotional_regulation": "Эмоц. регуляция",
    "metacognition": "Метакогниция",
    "resource_management": "Управление ресурсами",
    "adaptability": "Адаптивность",
    "patience": "Терпение",
    "focus": "Фокус",
}

SPORT_NAMES = {
    "tactics": "Тактика",
    "calculation": "Расчет",
    "positional": "Позиционное",
    "opening": "Дебют",
    "endgame": "Эндшпиль",
    "time_management": "Контроль времени",
    "converting_wins": "Реализация",
    "defense": "Защита",
    "opponent_adaptation": "Адаптация к сопернику",
}


def plot_radar(scores: Dict, category: str, title: str = None) -> go.Figure:
    """Строит радарную диаграмму для одной категории навыков"""
    if category == "meta":
        names = META_NAMES
        data = scores["meta"]
        color = "#2E86AB"
    else:
        names = SPORT_NAMES
        data = scores["sport"]
        color = "#A23B72"
    
    categories_list = list(data.keys())
    values = [data[k] for k in categories_list]
    labels = [names[k] for k in categories_list]
    
    # Замыкаем круг
    values_closed = values + [values[0]]
    labels_closed = labels + [labels[0]]
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatterpolar(
        r=values_closed,
        theta=labels_closed,
        fill='toself',
        name='Текущий уровень',
        fillcolor=color,
        opacity=0.4,
        line=dict(color=color, width=2),
        marker=dict(size=8),
    ))
    
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 10], tickvals=[2, 4, 6, 8, 10]),
            angularaxis=dict(tickfont=dict(size=11)),
        ),
        showlegend=False,
        title=dict(text=title or f"{category.title()} навыки", x=0.5),
        height=600,
    )
    
    return fig


def plot_radar_comparison(current: Dict, previous: Dict, 
                          category: str, title: str = None) -> go.Figure:
    """Сравнивает два периода на одном радаре"""
    if category == "meta":
        names = META_NAMES
        color_curr = "#2E86AB"
        color_prev = "#F18F01"
    else:
        names = SPORT_NAMES
        color_curr = "#A23B72"
        color_prev = "#C73E1D"
    
    data_curr = current[category]
    data_prev = previous[category]
    
    categories_list = list(data_curr.keys())
    labels = [names[k] for k in categories_list]
    
    values_curr = [data_curr[k] for k in categories_list] + [data_curr[categories_list[0]]]
    values_prev = [data_prev[k] for k in categories_list] + [data_prev[categories_list[0]]]
    labels_closed = labels + [labels[0]]
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatterpolar(
        r=values_prev,
        theta=labels_closed,
        fill='toself',
        name='Предыдущий период',
        fillcolor=color_prev,
        opacity=0.2,
        line=dict(color=color_prev, width=2, dash='dash'),
    ))
    
    fig.add_trace(go.Scatterpolar(
        r=values_curr,
        theta=labels_closed,
        fill='toself',
        name='Текущий период',
        fillcolor=color_curr,
        opacity=0.4,
        line=dict(color=color_curr, width=2),
    ))
    
    # Добавляем дельты как аннотации
    annotations = []
    for i, skill in enumerate(categories_list):
        delta = data_curr[skill] - data_prev[skill]
        if abs(delta) >= 0.3:
            color = "#28A745" if delta > 0 else "#DC3545"
            sign = "+" if delta > 0 else ""
            # Позиция аннотации - чуть дальше от центра
            angle = 2 * np.pi * i / len(categories_list)
            r = max(values_curr[i], values_prev[i]) + 1.0
            x = r * np.cos(angle - np.pi/2)
            y = r * np.sin(angle - np.pi/2)
            annotations.append(dict(
                x=x, y=y,
                text=f"<b>{sign}{delta:.1f}</b>",
                showarrow=False,
                font=dict(color=color, size=12),
            ))
    
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 11]),
            angularaxis=dict(tickfont=dict(size=11)),
        ),
        title=dict(text=title or f"Динамика: {category} навыки", x=0.5),
        height=650,
        annotations=annotations,
        legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5),
    )
    
    return fig


def plot_sparklines(measurements: List[Dict], category: str) -> go.Figure:
    """Строит спарклайны для всех навыков категории"""
    if category == "meta":
        names = META_NAMES
    else:
        names = SPORT_NAMES
    
    data = [m[category] for m in measurements]
    dates = [m["date"] for m in measurements]
    
    skills = list(data[0].keys())
    
    # Создаем subplot для каждого навыка
    fig = make_subplots(rows=3, cols=3, subplot_titles=[names[s] for s in skills])
    
    for i, skill in enumerate(skills):
        row = i // 3 + 1
        col = i % 3 + 1
        
        values = [d[skill] for d in data]
        
        # Линия тренда
        x_numeric = np.arange(len(values))
        if len(values) > 1:
            slope, intercept = np.polyfit(x_numeric, values, 1)
            trend = slope * x_numeric + intercept
        else:
            trend = values
        
        fig.add_trace(
            go.Scatter(
                x=dates, y=values,
                mode='lines+markers',
                line=dict(color='#2E86AB', width=2),
                marker=dict(size=6),
                name=names[skill],
                showlegend=False,
            ),
            row=row, col=col
        )
        
        fig.add_trace(
            go.Scatter(
                x=dates, y=trend,
                mode='lines',
                line=dict(color='red', width=2, dash='dash'),
                name='Тренд',
                showlegend=False,
            ),
            row=row, col=col
        )
        
        fig.update_yaxes(range=[0, 10], row=row, col=col)
    
    fig.update_layout(
        height=800,
        title_text=f"Динамика: {category} навыки",
        title_x=0.5,
    )
    
    return fig


def make_subplots(rows, cols, subplot_titles=None):
    """Хелпер для создания subplot"""
    from plotly.subplots import make_subplots as _make_subplots
    return _make_subplots(rows=rows, cols=cols, subplot_titles=subplot_titles)


def plot_heatmap(measurements: List[Dict], category: str) -> go.Figure:
    """Тепловая карта навыков во времени"""
    if category == "meta":
        names = META_NAMES
    else:
        names = SPORT_NAMES
    
    data = [m[category] for m in measurements]
    dates = [m["date"].strftime('%Y-%m-%d') if m["date"] else f"#{i}" 
             for i, m in enumerate(measurements)]
    
    skills = list(data[0].keys())
    skill_labels = [names[s] for s in skills]
    
    # Матрица значений
    z = []
    for skill in skills:
        z.append([d[skill] for d in data])
    
    fig = go.Figure(data=go.Heatmap(
        z=z,
        x=dates,
        y=skill_labels,
        colorscale='RdYlGn',
        zmin=0, zmax=10,
        text=[[f"{v:.1f}" for v in row] for row in z],
        texttemplate="%{text}",
        textfont={"size": 10},
        colorbar=dict(title="Score"),
    ))
    
    fig.update_layout(
        title=dict(text=f"Тепловая карта: {category} навыки", x=0.5),
        height=500,
        xaxis_title="Период",
        yaxis_title="Навык",
    )
    
    return fig


def plot_progress_gauge(current_scores: Dict, category: str) -> go.Figure:
    """Круговой индикатор общего прогресса"""
    data = current_scores[category]
    avg_score = np.mean(list(data.values()))
    
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=avg_score,
        domain={'x': [0, 1], 'y': [0, 1]},
        title={'text': f"Средний score: {category}"},
        delta={'reference': 5, 'increasing': {'color': "green"}},
        gauge={
            'axis': {'range': [0, 10]},
            'bar': {'color': "#2E86AB" if category == "meta" else "#A23B72"},
            'steps': [
                {'range': [0, 3], 'color': "#FFB3B3"},
                {'range': [3, 6], 'color': "#FFE5B3"},
                {'range': [6, 8], 'color': "#B3FFB3"},
                {'range': [8, 10], 'color': "#66FF66"},
            ],
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.75,
                'value': 9,
            },
        },
    ))
    
    fig.update_layout(height=300)
    return fig


def plot_skill_evolution_animation(measurements: List[Dict], category: str):
    """Возвращает данные для анимации (для использования в Streamlit)"""
    if category == "meta":
        names = META_NAMES
    else:
        names = SPORT_NAMES
    
    frames_data = []
    for m in measurements:
        data = m[category]
        skills = list(data.keys())
        values = [data[s] for s in skills]
        labels = [names[s] for s in skills]
        
        frames_data.append({
            "date": m["date"].strftime('%Y-%m-%d') if m["date"] else "",
            "skills": labels,
            "values": values + [values[0]],
            "games_count": m["games_count"],
        })
    
    return frames_data