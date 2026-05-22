from __future__ import annotations

from typing import Any

import pandas as pd

from config import Settings, load_settings
from data_processing import (
    DataBundle,
    apply_filters,
    load_dataset_bundle,
)



def load_data_bundle(settings: Settings | None = None) -> DataBundle:
    runtime_settings = settings or load_settings()
    return load_dataset_bundle(runtime_settings)



def get_sheet_frame(bundle: DataBundle, sheet_name: str | None = None) -> tuple[str, pd.DataFrame, dict[str, str]]:
    target_sheet = sheet_name or bundle.primary_sheet
    if target_sheet not in bundle.cleaned_frames:
        target_sheet = bundle.primary_sheet

    frame = bundle.cleaned_frames[target_sheet].copy()
    semantics = bundle.semantics.get(target_sheet, {})
    return target_sheet, frame, semantics



def apply_runtime_filters(
    frame: pd.DataFrame,
    semantics: dict[str, str],
    date_range: tuple[pd.Timestamp, pd.Timestamp] | None,
    category_filters: dict[str, list[Any]] | None,
) -> pd.DataFrame:
    return apply_filters(
        frame=frame,
        semantics=semantics,
        date_range=date_range,
        category_filters=category_filters,
    )
