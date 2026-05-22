from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import streamlit as st

from config import load_settings
from shared.analytics import build_category_ranking, build_kpis, build_time_series
from shared.data_loader import apply_runtime_filters, get_sheet_frame, load_data_bundle
from shared.insights import generate_insights, pick_date_col, pick_main_metric


st.set_page_config(
    page_title="Panel BI Artes Buho",
    page_icon="📊",
    layout="wide",
)


@st.cache_data(ttl=900, show_spinner=False)
def get_data_bundle():
    settings = load_settings()
    bundle = load_data_bundle(settings)
    return settings, bundle



def _fmt_number(value: float | int) -> str:
    if value is None or pd.isna(value):
        return "n/d"
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")



def _fmt_money(value: float | int) -> str:
    if value is None or pd.isna(value):
        return "n/d"
    return f"{_fmt_number(value)} €"



def _fmt_metric(value: float | int, semantic: str | None) -> str:
    if semantic == "porcentaje":
        if value is None or pd.isna(value):
            return "n/d"
        return f"{float(value) * 100:.2f}%"
    if semantic == "importe_monetario":
        return _fmt_money(value)
    return _fmt_number(value)



def _delta_label(delta: float | None) -> str | None:
    if delta is None or pd.isna(delta):
        return None
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta:.1f}% vs periodo anterior"



def _build_sidebar_filters(df: pd.DataFrame, semantics: dict[str, str]) -> tuple[tuple[pd.Timestamp, pd.Timestamp] | None, dict[str, list]]:
    date_range: tuple[pd.Timestamp, pd.Timestamp] | None = None

    date_col = pick_date_col(df, semantics)
    if date_col and date_col in df.columns:
        parsed = pd.to_datetime(df[date_col], errors="coerce").dropna()
        if not parsed.empty:
            min_date = parsed.min().date()
            max_date = parsed.max().date()
            selected = st.sidebar.date_input(
                "Rango de fechas",
                value=(min_date, max_date),
                min_value=min_date,
                max_value=max_date,
            )
            if isinstance(selected, tuple) and len(selected) == 2:
                date_range = (
                    pd.Timestamp(selected[0]),
                    pd.Timestamp(selected[1]) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1),
                )

    semantic_filter_types = {
        "categoria",
        "estado",
        "dimension_geografica",
        "canal",
        "producto",
        "cliente",
        "comercial",
        "origen",
    }
    filters: dict[str, list] = {}

    candidate_cols = [
        col
        for col, semantic in semantics.items()
        if semantic in semantic_filter_types and col in df.columns
    ]

    for col in candidate_cols:
        cardinality = int(df[col].nunique(dropna=True))
        if cardinality < 2 or cardinality > 30:
            continue

        options = sorted([value for value in df[col].dropna().unique()], key=lambda value: str(value))
        selected = st.sidebar.multiselect(
            f"Filtrar {col}",
            options=options,
            default=options,
        )
        if len(selected) != len(options):
            filters[col] = selected

    return date_range, filters



def _show_kpis(current_df: pd.DataFrame, previous_df: pd.DataFrame, semantics: dict[str, str]):
    kpis = build_kpis(current_df, previous_df, semantics)

    cols = st.columns(4)
    for idx in range(4):
        if idx < len(kpis):
            item = kpis[idx]
            cols[idx].metric(
                item.name,
                _fmt_metric(item.value, item.semantic),
                _delta_label(item.delta_pct),
            )
        else:
            cols[idx].metric("-", "-")



def _show_charts(df: pd.DataFrame, semantics: dict[str, str]):
    metric_col = pick_main_metric(df, semantics)

    chart_col_1, chart_col_2 = st.columns(2)

    with chart_col_1:
        st.subheader("Evolucion temporal")
        timeline = build_time_series(df, semantics)
        if not timeline.empty:
            st.line_chart(timeline, x="periodo", y="valor", use_container_width=True)
        else:
            st.info("No hay datos suficientes para serie temporal.")

    with chart_col_2:
        st.subheader("Comparativa por categoria")
        ranking = build_category_ranking(df, semantics)
        if not ranking.empty:
            st.bar_chart(ranking, x="categoria", y="valor", use_container_width=True)
        else:
            st.info("No hay categoria adecuada para ranking.")

    st.subheader("Distribucion de metrica")
    if metric_col and metric_col in df.columns:
        metric_series = df[metric_col].dropna()
        if len(metric_series) > 1:
            bins = min(20, max(5, int(np.sqrt(len(metric_series)))))
            hist, edges = np.histogram(metric_series, bins=bins)
            hist_df = pd.DataFrame(
                {
                    "rango": [f"{edges[idx]:.2f} a {edges[idx + 1]:.2f}" for idx in range(len(hist))],
                    "frecuencia": hist,
                }
            )
            st.bar_chart(hist_df, x="rango", y="frecuencia", use_container_width=True)
        else:
            st.info("No hay suficiente variacion para distribucion.")
    else:
        st.info("No se detecto metrica numerica principal.")



def main() -> None:
    settings = load_settings()

    st.title(settings.panel_name)
    st.caption(
        "Dashboard automatico sobre Google Sheets con limpieza, inferencia semantica y analisis dinamico."
    )

    madrid_now = datetime.now(ZoneInfo(settings.timezone))
    st.write(f"Actualizado: **{madrid_now.strftime('%Y-%m-%d %H:%M:%S')}** ({settings.timezone})")

    st.sidebar.header("Control del panel")
    if st.sidebar.button("Recargar datos"):
        get_data_bundle.clear()

    try:
        runtime_settings, bundle = get_data_bundle()
    except Exception as exc:
        st.error(f"No se pudo cargar el dataset: {exc}")
        st.stop()

    sheet_names = sorted(bundle.cleaned_frames.keys())
    default_index = sheet_names.index(bundle.primary_sheet) if bundle.primary_sheet in sheet_names else 0

    selected_sheet = st.sidebar.selectbox("Pestaña de analisis", options=sheet_names, index=default_index)

    _, frame, semantics = get_sheet_frame(bundle, selected_sheet)

    date_range, category_filters = _build_sidebar_filters(frame, semantics)
    filtered = apply_runtime_filters(frame, semantics, date_range, category_filters)

    date_col = pick_date_col(frame, semantics)
    previous_df = pd.DataFrame(columns=filtered.columns)
    if date_col and date_range:
        period_length = (date_range[1] - date_range[0]).days + 1
        previous_start = date_range[0] - pd.Timedelta(days=period_length)
        previous_end = date_range[0] - pd.Timedelta(seconds=1)
        previous_df = apply_runtime_filters(
            frame,
            semantics,
            (previous_start, previous_end),
            category_filters,
        )

    st.markdown("---")
    _show_kpis(filtered, previous_df, semantics)

    st.subheader("Insights automaticos")
    insights = generate_insights(filtered, semantics)
    for insight in insights:
        st.write(f"- {insight}")

    st.markdown("---")
    _show_charts(filtered, semantics)

    st.markdown("---")
    st.subheader("Tabla de detalle")
    st.dataframe(filtered, use_container_width=True, hide_index=True)

    st.subheader("Calidad del dato")
    quality = bundle.quality.get(selected_sheet, {})
    if quality:
        quality_df = pd.DataFrame([quality]).T.reset_index()
        quality_df.columns = ["indicador", "valor"]
        st.dataframe(quality_df, use_container_width=True, hide_index=True)

    st.subheader("Notas operativas")
    st.write(f"- Fuente: `{runtime_settings.spreadsheet_id}`")
    st.write(f"- Metodo de lectura: `{bundle.source_method}`")
    st.write(f"- Libro: `{bundle.workbook_title}`")
    st.write(f"- Hoja principal detectada: `{bundle.primary_sheet}`")

    with st.expander("Mapa de normalizacion de columnas"):
        mapping = bundle.normalization_maps.get(selected_sheet, {})
        if mapping:
            map_df = pd.DataFrame(list(mapping.items()), columns=["columna_original", "columna_normalizada"])
            st.dataframe(map_df, use_container_width=True, hide_index=True)
        else:
            st.write("No hay mapeo disponible para esta hoja.")


if __name__ == "__main__":
    main()
