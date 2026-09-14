from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from openpyxl import Workbook
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy.orm import Session

from procureai.services.analytics import alerts, executive_dashboard, supplier_scorecards


def executive_pdf(
    db: Session, output: Path = Path("reports/executive_procurement_report.pdf")
) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    data = executive_dashboard(db)
    canvas = Canvas(str(output), pagesize=A4)
    canvas.setTitle("ProcureAI Executive Procurement Report")
    canvas.setFont("Helvetica-Bold", 18)
    canvas.drawString(50, 790, "ProcureAI — Executive Procurement Report")
    canvas.setFont("Helvetica", 9)
    canvas.drawString(
        50, 770, f"Generated {datetime.now(UTC):%Y-%m-%d %H:%M UTC} · Synthetic demo data"
    )
    y = 735
    for label, value in [
        ("Total spend", f"EUR {data['total_spend']:,.0f}"),
        ("Savings opportunity", f"EUR {data['savings_opportunity']:,.0f}"),
        ("High-risk exposure", f"EUR {data['risk_exposure']:,.0f}"),
        ("On-time delivery", f"{data['on_time_delivery']:.1%}"),
        ("Quality cost", f"EUR {data['quality_cost']:,.0f}"),
        ("Contracts expiring", str(data["expiring_contracts"])),
    ]:
        canvas.setFont("Helvetica-Bold", 10)
        canvas.drawString(60, y, label)
        canvas.setFont("Helvetica", 10)
        canvas.drawRightString(520, y, value)
        y -= 24
    y -= 12
    canvas.setFont("Helvetica-Bold", 13)
    canvas.drawString(50, y, "Priority alerts")
    y -= 22
    canvas.setFont("Helvetica", 8)
    for row in alerts(db)[:5]:
        canvas.drawString(60, y, f"[{row['severity']}] {row['description'][:95]}")
        y -= 18
    canvas.setFont("Helvetica-Oblique", 8)
    canvas.drawString(
        50,
        50,
        "KPIs are calculated deterministically. AI is not an authoritative calculation source.",
    )
    canvas.save()
    return output


def supplier_excel(db: Session, output: Path = Path("reports/supplier_scorecards.xlsx")) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Supplier scorecards"
    headers = [
        "Supplier",
        "Name",
        "Country",
        "Spend EUR",
        "OTD",
        "Incidents",
        "Quality",
        "Risk",
        "Risk level",
        "Score",
    ]
    sheet.append(headers)
    for row in supplier_scorecards(db):
        sheet.append(
            [
                row["code"],
                row["name"],
                row["country"],
                row["spend"],
                row["otd"],
                row["incidents"],
                row["quality_score"],
                row["risk"],
                row["risk_level"],
                row["score"],
            ]
        )
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for column in sheet.columns:
        sheet.column_dimensions[column[0].column_letter].width = min(
            42, max(len(str(cell.value or "")) for cell in column) + 2
        )
    workbook.save(output)
    return output
