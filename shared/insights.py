from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd


@dataclass
class InsightContext:
    date_col: str | None
    main_metric: str | None
    category_col: str | None



def pick_main_metric(df: pd.DataFrame, semantics: dict[str, str]) -> str | None:
    monetary = [
        col
        for col, semantic in semantics.items()
        if semantic == "importe_monetario" and col in df.columns and pd.api.types.is_numeric_dtype(df[col])
    ]
    if monetary:
        return monetary[0]

    numeric = [
        col
        for col, semantic in semantics.items()
        if semantic in {"metrica_numerica", "porcentaje"}
        and col in df.columns
        and pd.api.types.is_numeric_dtype(df[col])
    ]
    return numeric[0] if numeric else None



def pick_date_col(df: pd.DataFrame, semantics: dict[str, str]) -> str | None:
    date_cols = [col for col, semantic in semantics.items() if semantic == "fecha" and col in df.columns]
    return date_cols[0] if date_cols else None



def pick_category_col(df: pd.DataFrame, semantics: dict[str, str]) -> str | None:
    candidates = [
        col
        for col, semantic in semantics.items()
        if semantic
        in {
            "categoria",
            "estado",
            "dimension_geografica",
            "canal",
            "producto",
            "cliente",
            "comercial",
            "origen",
        }
        and col in df.columns
    ]

    scored: list[tuple[int, str]] = []
    for col in candidates:
        cardinality = int(df[col].nunique(dropna=True))
        if 2 <= cardinality <= 25:
            scored.append((cardinality, col))

    if not scored:
        return None

    scored.sort(key=lambda item: item[0])
    return scored[0][1]



def _format_number(value: float | int) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "n/d"

    abs_value = abs(float(value))
    if abs_value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if abs_value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")



def _period_frequency(total_days: int) -> str:
    if total_days >= 365 * 2:
        return "QS"
    if total_days >= 90:
        return "MS"
    if total_days >= 30:
        return "W"
    return "D"



def build_context(df: pd.DataFrame, semantics: dict[str, str]) -> InsightContext:
    return InsightContext(
        date_col=pick_date_col(df, semantics),
        main_metric=pick_main_metric(df, semantics),
        category_col=pick_category_col(df, semantics),
    )



def generate_insights(df: pd.DataFrame, semantics: dict[str, str]) -> list[str]:
    if df.empty:
        return ["No hay datos tras aplicar los filtros actuales."]

    context = build_context(df, semantics)
    insights: list[str] = []

    if context.main_metric and context.main_metric in df.columns:
        metric = context.main_metric
        total = float(df[metric].sum(skipna=True))
        mean_value = float(df[metric].mean(skipna=True))
        insights.append(
            f"La metrica principal ({metric}) suma {_format_number(total)} y su media es {_format_number(mean_value)}."
        )

    if context.date_col and context.main_metric:
        date_col = context.date_col
        metric = context.main_metric
        date_df = df[[date_col, metric]].dropna().copy()
        if not date_df.empty:
            min_date = date_df[date_col].min()
            max_date = date_df[date_col].max()
            total_days = max((max_date - min_date).days, 1)
            freq = _period_frequency(total_days)

            series = (
                date_df.set_index(date_col)
                .sort_index()
                .resample(freq)[metric]
                .sum()
                .dropna()
            )
            if len(series) >= 2:
                current = float(series.iloc[-1])
                previous = float(series.iloc[-2])
                delta_pct = ((current - previous) / previous * 100.0) if previous != 0 else float("nan")
                if not math.isnan(delta_pct):
                    trend = "crece" if delta_pct >= 0 else "cae"
                    insights.append(
                        f"En el ultimo periodo, {metric} {trend} {abs(delta_pct):.1f}% frente al periodo anterior."
                    )

                rolling_mean = float(series.mean())
                rolling_std = float(series.std(ddof=0)) if len(series) > 2 else 0.0
                if rolling_std > 0:
                    z_score = (current - rolling_mean) / rolling_std
                    if abs(z_score) >= 2.0:
                        direction = "por encima" if z_score > 0 else "por debajo"
                        insights.append(
                            f"Se detecta anomalia simple: el ultimo periodo esta {direction} de lo habitual (z-score {z_score:.2f})."
                        )

    if context.category_col:
        category_col = context.category_col
        grouped = df.groupby(category_col, dropna=False)

        if context.main_metric:
            metric = context.main_metric
            summary = grouped[metric].sum().sort_values(ascending=False)
            if len(summary) >= 1:
                leader = summary.index[0]
                leader_value = float(summary.iloc[0])
                share = float(leader_value / summary.sum() * 100.0) if summary.sum() != 0 else float("nan")
                insights.append(
                    f"La categoria lider es {leader} con {_format_number(leader_value)} acumulado."
                )
                if not math.isnan(share) and share >= 50:
                    insights.append(
                        f"Existe concentracion alta: {leader} representa {share:.1f}% del total de {metric}."
                    )
        else:
            counts = grouped.size().sort_values(ascending=False)
            if len(counts) >= 1:
                leader = counts.index[0]
                leader_count = int(counts.iloc[0])
                share = float(leader_count / counts.sum() * 100.0) if counts.sum() else float("nan")
                insights.append(
                    f"La categoria mas frecuente es {leader} con {leader_count} registros."
                )
                if not math.isnan(share) and share >= 50:
                    insights.append(
                        f"La distribucion esta concentrada: {leader} supone {share:.1f}% de los registros."
                    )

    if len(insights) > 8:
        return insights[:8]

    if not insights:
        return ["No se detectan patrones solidos adicionales con la estructura actual de datos."]

    return insights
