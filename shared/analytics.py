from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from shared.insights import pick_category_col, pick_date_col, pick_main_metric


@dataclass
class KPIItem:
    name: str
    value: float | int
    previous_value: float | int | None
    delta_pct: float | None
    semantic: str | None



def _delta_pct(current: float | int, previous: float | int | None) -> float | None:
    if previous is None:
        return None
    try:
        prev = float(previous)
        cur = float(current)
    except (TypeError, ValueError):
        return None
    if prev == 0:
        return None
    return ((cur - prev) / prev) * 100.0



def build_kpis(
    current_df: pd.DataFrame,
    previous_df: pd.DataFrame,
    semantics: dict[str, str],
) -> list[KPIItem]:
    kpis: list[KPIItem] = []

    current_count = len(current_df)
    previous_count = len(previous_df) if previous_df is not None else None
    kpis.append(
        KPIItem(
            name="Registros",
            value=current_count,
            previous_value=previous_count,
            delta_pct=_delta_pct(current_count, previous_count),
            semantic=None,
        )
    )

    metric_col = pick_main_metric(current_df, semantics)
    if metric_col and metric_col in current_df.columns:
        semantic = semantics.get(metric_col)
        current_total = float(current_df[metric_col].sum(skipna=True))
        previous_total = (
            float(previous_df[metric_col].sum(skipna=True))
            if previous_df is not None and metric_col in previous_df.columns
            else None
        )
        current_mean = float(current_df[metric_col].mean(skipna=True))
        previous_mean = (
            float(previous_df[metric_col].mean(skipna=True))
            if previous_df is not None and metric_col in previous_df.columns
            else None
        )

        kpis.append(
            KPIItem(
                name=f"Total {metric_col}",
                value=current_total,
                previous_value=previous_total,
                delta_pct=_delta_pct(current_total, previous_total),
                semantic=semantic,
            )
        )
        kpis.append(
            KPIItem(
                name=f"Media {metric_col}",
                value=current_mean,
                previous_value=previous_mean,
                delta_pct=_delta_pct(current_mean, previous_mean),
                semantic=semantic,
            )
        )

    return kpis



def infer_frequency(date_series: pd.Series) -> str:
    if date_series.empty:
        return "MS"
    total_days = max((date_series.max() - date_series.min()).days, 1)
    if total_days >= 365 * 2:
        return "QS"
    if total_days >= 90:
        return "MS"
    if total_days >= 30:
        return "W"
    return "D"



def build_time_series(
    frame: pd.DataFrame,
    semantics: dict[str, str],
    frequency: str | None = None,
) -> pd.DataFrame:
    date_col = pick_date_col(frame, semantics)
    metric_col = pick_main_metric(frame, semantics)

    if not date_col or not metric_col or frame.empty:
        return pd.DataFrame(columns=["periodo", "valor"])

    source = frame[[date_col, metric_col]].dropna().copy()
    if source.empty:
        return pd.DataFrame(columns=["periodo", "valor"])

    freq = frequency or infer_frequency(source[date_col])
    timeline = (
        source.set_index(date_col)
        .sort_index()
        .resample(freq)[metric_col]
        .sum()
        .reset_index()
    )
    timeline.columns = ["periodo", "valor"]
    return timeline



def build_category_ranking(
    frame: pd.DataFrame,
    semantics: dict[str, str],
    limit: int = 12,
) -> pd.DataFrame:
    category_col = pick_category_col(frame, semantics)
    metric_col = pick_main_metric(frame, semantics)

    if not category_col or frame.empty:
        return pd.DataFrame(columns=["categoria", "valor"])

    if metric_col and metric_col in frame.columns:
        ranking = (
            frame.groupby(category_col, dropna=False)[metric_col]
            .sum()
            .sort_values(ascending=False)
            .head(limit)
            .reset_index()
        )
        ranking.columns = ["categoria", "valor"]
        return ranking

    ranking = frame[category_col].value_counts(dropna=False).head(limit).reset_index()
    ranking.columns = ["categoria", "valor"]
    return ranking



def select_detail_columns(frame: pd.DataFrame, semantics: dict[str, str], limit: int = 8) -> list[str]:
    priority = [
        "fecha",
        "cliente",
        "producto",
        "categoria",
        "canal",
        "estado",
        "importe_monetario",
        "metrica_numerica",
    ]

    selected: list[str] = []
    for semantic in priority:
        for col, col_semantic in semantics.items():
            if col_semantic == semantic and col in frame.columns and col not in selected:
                selected.append(col)
            if len(selected) >= limit:
                return selected

    for col in frame.columns:
        if col not in selected:
            selected.append(col)
        if len(selected) >= limit:
            break

    return selected
