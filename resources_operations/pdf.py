from io import BytesIO
from xml.sax.saxutils import escape

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle


def inventory_pdf(rows, generated_at):
    buffer = BytesIO()
    styles = getSampleStyleSheet()
    cell_style = styles["BodyText"].clone("InventoryCell", fontSize=9, leading=12)
    header_style = cell_style.clone("InventoryHeader", fontName="Helvetica-Bold", textColor=colors.white)

    def cell(value, style=cell_style):
        return Paragraph(escape(str(value)), style)

    headers = ("Ressource", "Type / Emplacement", "État", "En stock", "Stock libre", "Seuil bas",
               "Coût unitaire", "Unités utilisées", "Risque à 4 semaines")
    table_rows = [[cell(value, header_style) for value in headers]]
    for row in rows:
        resource = row["resource"]
        risk = f'{row["shortage"]} unité(s) manquante(s)' if row["shortage"] else "Aucune rupture détectée"
        table_rows.append([
            cell(resource.name), cell(f"{resource.type} / {resource.location}"),
            cell(resource.get_status_display()), cell(resource.quantity),
            cell(f'{row["free"]} · Stock bas' if row["low"] else row["free"]),
            cell(resource.low_stock_threshold), cell(f"{resource.unit_cost:.2f}"), cell(row["used"]), cell(risk),
        ])
    if not rows:
        table_rows.append([cell("Aucune ressource enregistrée.")] + [""] * (len(headers) - 1))

    table = LongTable(table_rows, colWidths=[130, 149, 88, 54, 63, 48, 66, 66, 100], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#294D62")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EDF2F5")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    if not rows:
        table.setStyle(TableStyle([("SPAN", (0, 1), (-1, 1))]))

    document = SimpleDocTemplate(
        buffer, title="Inventaire FannFlow", author="FannFlow", pagesize=landscape(A4),
        leftMargin=27, rightMargin=27, topMargin=32, bottomMargin=35,
    )
    moment = timezone.localtime(generated_at).strftime("%d/%m/%Y à %H:%M")
    document.build([
        Paragraph("Inventaire des ressources", styles["Title"]),
        Paragraph(f"FannFlow · Export du {moment}", styles["BodyText"]),
        Spacer(1, 8),
        table,
    ])
    buffer.seek(0)
    return buffer
