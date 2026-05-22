from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from googleapiclient.discovery import build

from config import Settings

SHEETS_READ_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
SHEETS_WRITE_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
DRIVE_RW_SCOPES = ["https://www.googleapis.com/auth/drive"]
DOCS_RW_SCOPES = ["https://www.googleapis.com/auth/documents"]


@dataclass
class SheetProfile:
    sheet_name: str
    rows: int
    cols: int
    numeric_cols: int
    date_cols: int
    category_cols: int


@dataclass
class DataBundle:
    source_method: str
    workbook_title: str
    sheet_frames: dict[str, pd.DataFrame]
    cleaned_frames: dict[str, pd.DataFrame]
    normalization_maps: dict[str, dict[str, str]]
    semantics: dict[str, dict[str, str]]
    quality: dict[str, dict[str, Any]]
    profiles: dict[str, SheetProfile]
    primary_sheet: str


def get_google_credentials(settings: Settings, scopes: list[str]) -> Credentials | ServiceAccountCredentials | None:
    if settings.service_account_file and settings.service_account_file.exists():
        return ServiceAccountCredentials.from_service_account_file(
            str(settings.service_account_file),
            scopes=scopes,
        )

    if settings.oauth_token_file and settings.oauth_token_file.exists():
        creds = Credentials.from_authorized_user_file(
            str(settings.oauth_token_file),
            scopes=scopes,
        )
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return creds

    return None


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def normalize_col_name(name: str) -> str:
    text = _strip_accents(str(name)).strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "col"


def make_unique(names: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out: list[str] = []
    for name in names:
        current = seen.get(name, 0)
        if current == 0:
            out.append(name)
        else:
            out.append(f"{name}_{current + 1}")
        seen[name] = current + 1
    return out


def _coerce_row_length(row: list[Any], target_len: int) -> list[Any]:
    row = list(row)
    if len(row) < target_len:
        row.extend([""] * (target_len - len(row)))
    return row[:target_len]


def _looks_like_empty(series: pd.Series) -> bool:
    if series.isna().all():
        return True
    text = series.astype(str).str.strip().str.lower()
    return text.isin({"", "none", "null", "nan"}).all()


def _parse_number_series(series: pd.Series) -> pd.Series:
    text = series.astype(str).str.strip()
    text = text.replace({r"^\s*$": np.nan, r"(?i)none|null|nan": np.nan}, regex=True)

    text = text.str.replace("%", "", regex=False)
    text = text.str.replace(r"[€$£]", "", regex=True)
    text = text.str.replace(r"\s", "", regex=True)

    both_mask = text.str.contains(r"\.", regex=True) & text.str.contains(",", regex=False)
    comma_decimal_mask = both_mask & (text.str.rfind(",") > text.str.rfind("."))

    text.loc[comma_decimal_mask] = (
        text.loc[comma_decimal_mask].str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    )
    text.loc[both_mask & ~comma_decimal_mask] = text.loc[both_mask & ~comma_decimal_mask].str.replace(",", "", regex=False)
    text.loc[~both_mask] = text.loc[~both_mask].str.replace(",", ".", regex=False)

    return pd.to_numeric(text, errors="coerce")


def _looks_like_date_text(series: pd.Series) -> bool:
    sample = series.dropna().astype(str).str.strip().head(200)
    if sample.empty:
        return False

    pattern = (
        r"^\d{1,4}[-/]\d{1,2}[-/]\d{1,4}$"
        r"|^\d{1,2}\s+[A-Za-z]{3,}"
        r"|^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\s+\d{1,2}:\d{2}"
    )
    ratio = float(sample.str.match(pattern).mean())
    return ratio >= 0.5


def _parse_date_series(series: pd.Series) -> pd.Series:
    dayfirst_try = pd.to_datetime(series, errors="coerce", dayfirst=True, format="mixed")
    default_try = pd.to_datetime(series, errors="coerce", dayfirst=False, format="mixed")

    dayfirst_ratio = float(dayfirst_try.notna().mean())
    default_ratio = float(default_try.notna().mean())

    if default_ratio > dayfirst_ratio + 0.05:
        return default_try
    return dayfirst_try


def _convert_column(series: pd.Series, col_name: str) -> pd.Series:
    lowered = col_name.lower()
    raw = series.copy()

    if pd.api.types.is_numeric_dtype(raw):
        return raw

    percent_hint = any(key in lowered for key in ["pct", "porcentaje", "ratio", "tasa", "%"])
    date_hint = any(key in lowered for key in ["fecha", "date", "dia", "mes", "ano", "year"])

    numeric_try = _parse_number_series(raw)
    numeric_ratio = float(numeric_try.notna().mean())
    if numeric_ratio >= 0.85:
        if percent_hint:
            return (numeric_try / 100.0).round(6)
        return numeric_try

    should_try_date = date_hint or _looks_like_date_text(raw)
    if should_try_date:
        date_try = _parse_date_series(raw)
        date_ratio = float(date_try.notna().mean())
        if date_hint and date_ratio >= 0.5:
            return date_try
        if date_ratio >= 0.9:
            return date_try

    text = raw.astype(str).str.strip().replace({"": np.nan})
    lowered_text = text.str.lower()
    bool_map = {
        "si": True,
        "sí": True,
        "yes": True,
        "true": True,
        "1": True,
        "no": False,
        "false": False,
        "0": False,
    }
    if float(lowered_text.isin(bool_map.keys()).mean()) >= 0.95:
        return lowered_text.map(bool_map)

    return text


def infer_semantic_type(series: pd.Series, col_name: str) -> str:
    name = col_name.lower()
    unique_ratio = series.nunique(dropna=True) / max(len(series), 1)

    if pd.api.types.is_datetime64_any_dtype(series):
        return "fecha"

    if pd.api.types.is_numeric_dtype(series):
        if any(token in name for token in ["id", "codigo", "numero", "n_", "num_"]) and unique_ratio > 0.9:
            return "identificador"
        if any(token in name for token in ["pct", "porcentaje", "ratio", "tasa", "%"]):
            return "porcentaje"
        if any(token in name for token in ["importe", "total", "venta", "facturacion", "precio", "coste", "margen"]):
            return "importe_monetario"
        return "metrica_numerica"

    if any(token in name for token in ["estado", "status", "situacion"]):
        return "estado"
    if any(token in name for token in ["pais", "provincia", "ciudad", "region", "zona"]):
        return "dimension_geografica"
    if any(token in name for token in ["canal", "channel"]):
        return "canal"
    if any(token in name for token in ["producto", "articulo", "sku", "referencia"]):
        return "producto"
    if any(token in name for token in ["cliente", "customer"]):
        return "cliente"
    if any(token in name for token in ["comercial", "vendedor", "sales_rep"]):
        return "comercial"
    if any(token in name for token in ["origen", "source", "fuente"]):
        return "origen"
    if any(token in name for token in ["id", "codigo"]) and unique_ratio > 0.9:
        return "identificador"

    avg_text_len = series.dropna().astype(str).str.len().mean() if series.notna().any() else 0
    if avg_text_len > 45:
        return "texto_libre"

    return "categoria"


def _drop_fully_duplicated_columns(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    duplicated = df.T.duplicated(keep="first")
    removed = int(duplicated.sum())
    if removed == 0:
        return df, 0
    return df.loc[:, ~duplicated], removed


def clean_and_profile(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, str], dict[str, str], dict[str, Any], SheetProfile]:
    original_names = [str(col) for col in df.columns]
    normalized_names = make_unique([normalize_col_name(col) for col in original_names])
    mapping = dict(zip(original_names, normalized_names, strict=False))

    clean_df = df.copy()
    clean_df.columns = normalized_names

    rows_before = len(clean_df)
    cols_before = len(clean_df.columns)

    clean_df = clean_df.replace(r"^\s*$", np.nan, regex=True)
    clean_df = clean_df.dropna(axis=0, how="all")
    clean_df = clean_df.dropna(axis=1, how="all")

    removed_empty_rows = rows_before - len(clean_df)
    removed_empty_cols = cols_before - len(clean_df.columns)

    for col in list(clean_df.columns):
        if _looks_like_empty(clean_df[col]):
            clean_df = clean_df.drop(columns=[col])
            removed_empty_cols += 1

    clean_df, removed_duplicated_columns = _drop_fully_duplicated_columns(clean_df)

    semantic_map: dict[str, str] = {}
    for col in clean_df.columns:
        clean_df[col] = _convert_column(clean_df[col], col)
        semantic_map[col] = infer_semantic_type(clean_df[col], col)

    profile = SheetProfile(
        sheet_name="",
        rows=len(clean_df),
        cols=len(clean_df.columns),
        numeric_cols=int(sum(pd.api.types.is_numeric_dtype(clean_df[col]) for col in clean_df.columns)),
        date_cols=int(sum(pd.api.types.is_datetime64_any_dtype(clean_df[col]) for col in clean_df.columns)),
        category_cols=int(sum(semantic_map[col] == "categoria" for col in clean_df.columns)),
    )

    quality = {
        "rows_before": rows_before,
        "rows_after": len(clean_df),
        "cols_before": cols_before,
        "cols_after": len(clean_df.columns),
        "removed_empty_rows": removed_empty_rows,
        "removed_empty_cols": removed_empty_cols,
        "removed_duplicated_columns": removed_duplicated_columns,
        "duplicated_rows": int(clean_df.duplicated().sum()),
        "null_cells_after_cleaning": int(clean_df.isna().sum().sum()),
    }

    return clean_df, mapping, semantic_map, quality, profile


def _load_public_csv_candidate(spreadsheet_id: str, gid: str) -> pd.DataFrame | None:
    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv&gid={gid}"
    response = requests.get(url, timeout=20)
    if response.status_code != 200:
        return None

    content_type = response.headers.get("content-type", "").lower()
    if "text/csv" not in content_type and "application/octet-stream" not in content_type:
        return None

    body = response.text.strip()
    if not body or body.startswith("<!DOCTYPE"):
        return None

    frame = pd.read_csv(io.StringIO(body))
    if frame.empty and len(frame.columns) <= 1:
        return None

    return frame


def try_public_csv(spreadsheet_id: str, gid_candidates: list[str]) -> tuple[dict[str, pd.DataFrame], str]:
    for gid in gid_candidates:
        try:
            frame = _load_public_csv_candidate(spreadsheet_id, gid)
            if frame is not None:
                return {f"gid_{gid}": frame}, "public_csv"
        except Exception:
            continue

    return {}, "public_csv_unavailable"


def load_sheets_via_api(settings: Settings, creds: Credentials | ServiceAccountCredentials) -> tuple[str, dict[str, pd.DataFrame]]:
    service = build("sheets", "v4", credentials=creds, cache_discovery=False)
    metadata = service.spreadsheets().get(spreadsheetId=settings.spreadsheet_id).execute()
    workbook_title = metadata.get("properties", {}).get("title", "Google Sheets")

    frames: dict[str, pd.DataFrame] = {}
    for sheet in metadata.get("sheets", []):
        sheet_name = sheet.get("properties", {}).get("title", "")
        if not sheet_name:
            continue

        values_response = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=settings.spreadsheet_id, range=f"'{sheet_name}'!A:ZZZ")
            .execute()
        )
        values = values_response.get("values", [])
        if not values:
            continue

        header = [str(value).strip() for value in values[0]]
        if not any(header):
            continue

        header = [name if name else f"col_{idx + 1}" for idx, name in enumerate(header)]
        rows = [_coerce_row_length(row, len(header)) for row in values[1:]]
        frame = pd.DataFrame(rows, columns=header)
        if frame.empty and len(frame.columns) == 0:
            continue

        frames[sheet_name] = frame

    return workbook_title, frames


def choose_primary_sheet(frames: dict[str, pd.DataFrame], keywords: list[str]) -> str:
    if not frames:
        raise ValueError("No hay hojas con datos.")

    scores: dict[str, float] = {}
    for sheet_name, frame in frames.items():
        score = float(len(frame) * max(len(frame.columns), 1))
        lowered_name = sheet_name.lower()
        for index, keyword in enumerate(keywords):
            if keyword.lower() in lowered_name:
                score += 100_000 - (index * 500)
        scores[sheet_name] = score

    return max(scores, key=scores.get)


def load_dataset_bundle(settings: Settings) -> DataBundle:
    public_frames, public_status = try_public_csv(settings.spreadsheet_id, settings.public_gid_candidates)

    workbook_title = "Google Sheets"
    source_method = public_status
    raw_frames: dict[str, pd.DataFrame] = {}

    if public_frames:
        raw_frames = public_frames

    if not raw_frames:
        creds = get_google_credentials(settings, SHEETS_READ_SCOPES)
        if creds is None:
            raise RuntimeError(
                "No se pudo leer la hoja por CSV publico y no hay credenciales para API."
            )
        workbook_title, raw_frames = load_sheets_via_api(settings, creds)
        source_method = "google_sheets_api"

    if not raw_frames:
        raise RuntimeError("No se detectaron pestañas con datos.")

    cleaned_frames: dict[str, pd.DataFrame] = {}
    normalization_maps: dict[str, dict[str, str]] = {}
    semantics: dict[str, dict[str, str]] = {}
    quality: dict[str, dict[str, Any]] = {}
    profiles: dict[str, SheetProfile] = {}

    for sheet_name, frame in raw_frames.items():
        cleaned, mapping, semantic_map, quality_info, profile = clean_and_profile(frame)
        profile.sheet_name = sheet_name
        if cleaned.empty:
            continue
        cleaned_frames[sheet_name] = cleaned
        normalization_maps[sheet_name] = mapping
        semantics[sheet_name] = semantic_map
        quality[sheet_name] = quality_info
        profiles[sheet_name] = profile

    if not cleaned_frames:
        raise RuntimeError("Todas las pestañas quedaron vacías tras limpieza.")

    primary_sheet = choose_primary_sheet(cleaned_frames, settings.preferred_sheet_keywords)

    return DataBundle(
        source_method=source_method,
        workbook_title=workbook_title,
        sheet_frames=raw_frames,
        cleaned_frames=cleaned_frames,
        normalization_maps=normalization_maps,
        semantics=semantics,
        quality=quality,
        profiles=profiles,
        primary_sheet=primary_sheet,
    )


def apply_filters(
    frame: pd.DataFrame,
    semantics: dict[str, str],
    date_range: tuple[pd.Timestamp, pd.Timestamp] | None,
    category_filters: dict[str, list[Any]] | None,
) -> pd.DataFrame:
    filtered = frame.copy()

    if date_range:
        date_columns = [col for col, semantic in semantics.items() if semantic == "fecha" and col in filtered.columns]
        if date_columns:
            date_col = date_columns[0]
            start_dt, end_dt = date_range
            filtered = filtered[(filtered[date_col] >= start_dt) & (filtered[date_col] <= end_dt)]

    if category_filters:
        for col, selected_values in category_filters.items():
            if col in filtered.columns and selected_values:
                filtered = filtered[filtered[col].isin(selected_values)]

    return filtered
