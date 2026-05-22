from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from random import Random

import pandas as pd
from googleapiclient.discovery import build


def _load_runtime_dependencies():
    import sys

    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from config import load_settings
    from data_processing import SHEETS_WRITE_SCOPES, get_google_credentials

    return load_settings, SHEETS_WRITE_SCOPES, get_google_credentials


@dataclass
class SimulationResult:
    clientes: pd.DataFrame
    articulos: pd.DataFrame
    facturas: pd.DataFrame
    lineas: pd.DataFrame


def _weighted_choice(rng: Random, items: list[str], weights: list[float]) -> str:
    point = rng.random() * sum(weights)
    acc = 0.0
    for item, weight in zip(items, weights, strict=False):
        acc += weight
        if point <= acc:
            return item
    return items[-1]


def _generate_clients(count: int, rng: Random, base_date: date) -> pd.DataFrame:
    first_names = [
        "Lucia",
        "Mateo",
        "Sofia",
        "Martin",
        "Valeria",
        "Hugo",
        "Irene",
        "Leo",
        "Alba",
        "Daniel",
    ]
    last_names = [
        "Garcia",
        "Lopez",
        "Martinez",
        "Sanchez",
        "Perez",
        "Gonzalez",
        "Ruiz",
        "Fernandez",
        "Jimenez",
        "Romero",
    ]
    cities = ["Madrid", "Barcelona", "Valencia", "Sevilla", "Bilbao", "Malaga", "A Coruna", "Vigo"]
    provinces = {
        "Madrid": "Madrid",
        "Barcelona": "Barcelona",
        "Valencia": "Valencia",
        "Sevilla": "Sevilla",
        "Bilbao": "Bizkaia",
        "Malaga": "Malaga",
        "A Coruna": "A Coruna",
        "Vigo": "Pontevedra",
    }
    segmentos = ["Retail", "Mayorista", "Premium", "Corporativo"]
    comerciales = ["Ruben", "Clara", "Aitana", "Diego", "Nora"]
    canales = ["Online", "Tienda", "Distribuidor"]

    rows: list[dict] = []
    for idx in range(1, count + 1):
        city = rng.choice(cities)
        nombre = f"{rng.choice(first_names)} {rng.choice(last_names)}"
        rows.append(
            {
                "id_cliente": f"CLI-{idx:04d}",
                "nombre_cliente": nombre,
                "email": f"cliente{idx:04d}@correo.es",
                "telefono": f"6{rng.randint(10000000, 99999999)}",
                "segmento": _weighted_choice(rng, segmentos, [0.55, 0.2, 0.15, 0.1]),
                "canal_preferente": _weighted_choice(rng, canales, [0.48, 0.32, 0.2]),
                "ciudad": city,
                "provincia": provinces[city],
                "pais": "España",
                "comercial": rng.choice(comerciales),
                "fecha_alta": (base_date - timedelta(days=rng.randint(30, 900))).isoformat(),
                "estado_cliente": _weighted_choice(rng, ["Activo", "Inactivo"], [0.88, 0.12]),
            }
        )

    return pd.DataFrame(rows)


def _generate_articles(count: int, rng: Random) -> pd.DataFrame:
    categorias = {
        "Textil": ["Camiseta", "Sudadera", "Pantalon", "Chaqueta"],
        "Accesorios": ["Gorra", "Mochila", "Pulsera", "Cinturon"],
        "Hogar": ["Lampara", "Cuadro", "Jarron", "Manta"],
        "Papeleria": ["Cuaderno", "Agenda", "Boligrafo", "Carpeta"],
        "Decoracion": ["Figura", "Espejo", "Marco", "Velador"],
    }

    rows: list[dict] = []
    cat_names = list(categorias.keys())
    for idx in range(1, count + 1):
        categoria = _weighted_choice(rng, cat_names, [0.28, 0.2, 0.18, 0.16, 0.18])
        base_name = rng.choice(categorias[categoria])
        coste = round(rng.uniform(4.0, 45.0), 2)
        margen = rng.uniform(1.35, 2.4)
        precio = round(coste * margen, 2)
        stock = rng.randint(0, 260)

        rows.append(
            {
                "id_articulo": f"ART-{idx:04d}",
                "nombre_articulo": f"{base_name} {idx:03d}",
                "categoria": categoria,
                "coste_unitario": coste,
                "precio_base": precio,
                "stock_actual": stock,
                "estado_articulo": "Activo" if stock > 0 else "Bajo_stock",
            }
        )

    return pd.DataFrame(rows)


def _allocate_lines_per_invoice(total_invoices: int, total_lines: int, rng: Random) -> list[int]:
    base = [1] * total_invoices
    remaining = max(total_lines - total_invoices, 0)

    for _ in range(remaining):
        target = rng.randint(0, total_invoices - 1)
        if base[target] < 10:
            base[target] += 1
        else:
            retry = rng.randint(0, total_invoices - 1)
            base[retry] += 1

    return base


def _generate_invoices_and_lines(
    clients: pd.DataFrame,
    articles: pd.DataFrame,
    invoices_count: int,
    lines_count: int,
    rng: Random,
    today: date,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    estado_factura_choices = ["Pagada", "Pendiente", "Impagada"]
    estado_factura_weights = [0.78, 0.16, 0.06]

    payment_methods = ["Tarjeta", "Transferencia", "Bizum", "Efectivo"]
    payment_weights = [0.45, 0.35, 0.12, 0.08]

    article_ids = articles["id_articulo"].tolist()
    article_weights = [max(1, 300 - idx) for idx in range(len(article_ids))]
    article_lookup = articles.set_index("id_articulo").to_dict("index")
    client_records = clients.to_dict("records")

    line_allocations = _allocate_lines_per_invoice(invoices_count, lines_count, rng)

    invoice_rows: list[dict] = []
    line_rows: list[dict] = []
    line_id = 1

    for invoice_idx in range(1, invoices_count + 1):
        client = client_records[rng.randint(0, len(client_records) - 1)]
        invoice_date = today - timedelta(days=rng.randint(0, 364))
        due_date = invoice_date + timedelta(days=30)
        invoice_status = _weighted_choice(rng, estado_factura_choices, estado_factura_weights)

        subtotal = 0.0
        line_count = line_allocations[invoice_idx - 1]

        for _ in range(line_count):
            article_id = _weighted_choice(rng, article_ids, article_weights)
            article = article_lookup[article_id]

            quantity = rng.randint(1, 6)
            base_price = float(article["precio_base"])
            unit_price = round(base_price * rng.uniform(0.92, 1.18), 2)
            discount_pct = round(rng.choice([0, 0, 0, 5, 10, 15]), 2)
            gross_amount = quantity * unit_price
            net_amount = round(gross_amount * (1 - discount_pct / 100.0), 2)
            subtotal += net_amount

            line_rows.append(
                {
                    "id_linea": f"LIN-{line_id:06d}",
                    "id_factura": f"FAC-{invoice_idx:05d}",
                    "fecha_factura": invoice_date.isoformat(),
                    "id_cliente": client["id_cliente"],
                    "id_articulo": article_id,
                    "nombre_articulo": article["nombre_articulo"],
                    "categoria_producto": article["categoria"],
                    "cantidad": quantity,
                    "precio_unitario": unit_price,
                    "descuento_pct_linea": discount_pct,
                    "importe_linea": net_amount,
                    "canal": client["canal_preferente"],
                    "comercial": client["comercial"],
                }
            )
            line_id += 1

        discount_pct_invoice = rng.choice([0, 0, 0, 2, 5])
        iva_pct = rng.choice([21, 21, 21, 10])
        subtotal_after_discount = round(subtotal * (1 - discount_pct_invoice / 100.0), 2)
        tax_amount = round(subtotal_after_discount * (iva_pct / 100.0), 2)
        total_amount = round(subtotal_after_discount + tax_amount, 2)

        if invoice_status == "Impagada" and (today - invoice_date).days < 60:
            invoice_status = "Pendiente"

        invoice_rows.append(
            {
                "id_factura": f"FAC-{invoice_idx:05d}",
                "fecha_factura": invoice_date.isoformat(),
                "fecha_vencimiento": due_date.isoformat(),
                "id_cliente": client["id_cliente"],
                "nombre_cliente": client["nombre_cliente"],
                "segmento_cliente": client["segmento"],
                "canal": client["canal_preferente"],
                "comercial": client["comercial"],
                "estado_factura": invoice_status,
                "metodo_pago": _weighted_choice(rng, payment_methods, payment_weights),
                "subtotal": round(subtotal, 2),
                "descuento_pct": float(discount_pct_invoice),
                "iva_pct": float(iva_pct),
                "total_factura": total_amount,
            }
        )

    facturas = pd.DataFrame(invoice_rows).sort_values("fecha_factura").reset_index(drop=True)
    lineas = pd.DataFrame(line_rows).sort_values("fecha_factura").reset_index(drop=True)

    return facturas, lineas


def build_simulated_data(settings) -> SimulationResult:
    rng = Random(settings.simulation_seed)
    today = date.today()

    clients = _generate_clients(settings.simulation_clients, rng, today)
    articles = _generate_articles(settings.simulation_articles, rng)
    invoices, lines = _generate_invoices_and_lines(
        clients=clients,
        articles=articles,
        invoices_count=settings.simulation_invoices,
        lines_count=settings.simulation_lines,
        rng=rng,
        today=today,
    )

    return SimulationResult(
        clientes=clients,
        articulos=articles,
        facturas=invoices,
        lineas=lines,
    )


def _ensure_sheet_exists(service, spreadsheet_id: str, sheet_name: str) -> None:
    metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    existing = {
        sheet["properties"]["title"]
        for sheet in metadata.get("sheets", [])
        if "properties" in sheet and "title" in sheet["properties"]
    }

    if sheet_name in existing:
        return

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": sheet_name}}}]},
    ).execute()


def _remove_legacy_sheets(service, spreadsheet_id: str) -> None:
    metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    targets = []
    for sheet in metadata.get("sheets", []):
        props = sheet.get("properties", {})
        title = str(props.get("title", "")).lower()
        sheet_id = props.get("sheetId")
        if sheet_id is None:
            continue
        if title.startswith("looker_") or "datastudio" in title or "lookerstudio" in title:
            targets.append(sheet_id)

    if not targets:
        return

    requests = [{"deleteSheet": {"sheetId": sheet_id}} for sheet_id in targets]
    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": requests},
    ).execute()


def _frame_to_values(frame: pd.DataFrame) -> list[list]:
    frame = frame.copy()
    for col in frame.columns:
        if pd.api.types.is_datetime64_any_dtype(frame[col]):
            frame[col] = frame[col].dt.strftime("%Y-%m-%d")

    frame = frame.fillna("")
    values = [frame.columns.tolist()] + frame.values.tolist()
    return values


def _upload_frame(service, spreadsheet_id: str, sheet_name: str, frame: pd.DataFrame) -> None:
    _ensure_sheet_exists(service, spreadsheet_id, sheet_name)

    service.spreadsheets().values().clear(
        spreadsheetId=spreadsheet_id,
        range=f"'{sheet_name}'!A:ZZZ",
        body={},
    ).execute()

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"'{sheet_name}'!A1",
        valueInputOption="RAW",
        body={"values": _frame_to_values(frame)},
    ).execute()


def main() -> None:
    load_settings, sheets_write_scopes, get_google_credentials = _load_runtime_dependencies()
    settings = load_settings()
    creds = get_google_credentials(settings, sheets_write_scopes)
    if creds is None:
        raise RuntimeError(
            "No hay credenciales para escribir en Google Sheets. Configura GOOGLE_CREDENTIALS_FILE o GOOGLE_OAUTH_TOKEN_FILE."
        )

    simulation = build_simulated_data(settings)

    service = build("sheets", "v4", credentials=creds, cache_discovery=False)
    _remove_legacy_sheets(service, settings.spreadsheet_id)

    uploads = {
        "hoja_clientes": simulation.clientes,
        "hoja_facturas": simulation.facturas,
        "hoja_lineas": simulation.lineas,
        "hoja_articulos": simulation.articulos,
    }

    for sheet_name, frame in uploads.items():
        _upload_frame(service, settings.spreadsheet_id, sheet_name, frame)

    print("Simulación completada y subida a Google Sheets.")
    print(f"Clientes: {len(simulation.clientes)}")
    print(f"Facturas: {len(simulation.facturas)}")
    print(f"Lineas: {len(simulation.lineas)}")
    print(f"Articulos: {len(simulation.articulos)}")


if __name__ == "__main__":
    main()
