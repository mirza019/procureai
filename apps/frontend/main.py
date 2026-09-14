from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import plotly.graph_objects as go
from design import (
    PURPLE,
    SEMANTIC,
    chart_header,
    compact_euro,
    install_design_system,
    polish_chart,
)
from nicegui import app, ui

from procureai.ai.orchestrator import AgentOrchestrator
from procureai.db.models import ProcurementAction, Report, ReportSchedule, Role
from procureai.db.session import SessionLocal
from procureai.reporting.intelligent import (
    generate_report,
    monthly_period,
    role_sections,
)
from procureai.schemas.agents import AgentRequest
from procureai.schemas.reporting import ReportRequest, ReportType
from procureai.services.analytics import (
    alerts,
    category_spend,
    cost_anomalies,
    dashboard_kpis,
    dashboard_period,
    delivery_summary,
    delivery_trend,
    executive_dashboard,
    invoice_summary,
    monthly_spend,
    pipeline_runs,
    quality_summary,
    risk_distribution,
    sourcing_rank,
    supplier_scorecards,
    top_suppliers_by_spend,
)
from procureai.services.projections import procurement_projections

advisor_orchestrator = AgentOrchestrator()
STATIC_DIR = Path(__file__).with_name("static")
app.add_static_files("/assets", STATIC_DIR)

NAV = {
    "Overview": [
        ("/", "Executive", "dashboard_customize"),
        ("/procurement", "Procurement", "shopping_bag"),
    ],
    "Intelligence": [
        ("/suppliers", "Suppliers", "domain"),
        ("/spend", "Spend", "query_stats"),
        ("/cost", "Cost & Value", "savings"),
        ("/delivery", "Delivery", "local_shipping"),
        ("/quality", "Quality", "workspace_premium"),
        ("/risk", "Risk Center", "gpp_maybe"),
    ],
    "AI": [
        ("/projections", "Projections", "insights"),
        ("/advisor", "ProcureAI Advisor", "psychology"),
        ("/sourcing", "Strategic Sourcing", "hub"),
    ],
    "Operations": [
        ("/pipelines", "Pipeline", "schema"),
        ("/reports", "Reports", "summarize"),
    ],
}

install_design_system()


def euro(value: float) -> str:
    if abs(value) >= 1_000_000:
        return f"€{value / 1_000_000:,.2f}M"
    if abs(value) >= 1_000:
        return f"€{value / 1_000:,.0f}K"
    return f"€{value:,.0f}"


def pct(value: float) -> str:
    return f"{value:.1%}"


def taulack_chatbox() -> None:
    session_id = f"taulack-{uuid.uuid4().hex[:12]}"
    panel = ui.card().classes("taulack-panel")
    panel.set_visibility(False)

    with panel:
        with ui.row().classes("taulack-header w-full items-center gap-3"):
            ui.image("/assets/taulack.png").classes("taulack-header-avatar")
            with ui.column().classes("gap-0"):
                ui.label("Ask Taulack").classes("text-base font-bold")
                ui.label("Procurement Intelligence Assistant").classes("text-xs opacity-90")
            ui.space()
            ui.button(icon="close", on_click=lambda: panel.set_visibility(False)).props(
                'flat round dense color="white" aria-label="Close Ask Taulack"'
            )

        messages = ui.column().classes("taulack-messages w-full")
        with messages:
            with ui.row().classes("taulack-message-row bot-row w-full items-start"):
                ui.image("/assets/taulack.png").classes("taulack-message-avatar")
                ui.label(
                    "Ask questions across procurement data, analytics and ML insights."
                ).classes("taulack-message bot")

        suggestions = ui.row().classes("taulack-suggestions w-full gap-1")

        with ui.row().classes("taulack-composer w-full items-center gap-2"):
            prompt = (
                ui.input(
                    placeholder="Ask Taulack about suppliers, spend, cost, quality, delivery, risk, contracts or sourcing..."
                )
                .props('borderless dense aria-label="Message Ask Taulack"')
                .classes("grow")
            )

            async def send_message() -> None:
                question = (prompt.value or "").strip()
                if not question:
                    return
                prompt.set_value("")
                with messages:
                    with ui.row().classes("taulack-message-row user-row w-full items-start"):
                        ui.label(question).classes("taulack-message user")
                        ui.avatar("DA", color="primary", text_color="white").classes(
                            "taulack-message-avatar"
                        )
                    with ui.row().classes(
                        "taulack-message-row bot-row w-full items-start"
                    ) as thinking_row:
                        ui.image("/assets/taulack.png").classes("taulack-message-avatar")
                        thinking = ui.label(
                            "Understanding your question · checking verified procurement data…"
                        ).classes("taulack-message bot pulse-soft")
                send_button.disable()
                try:
                    with SessionLocal() as db:
                        response = await advisor_orchestrator.execute(
                            db,
                            AgentRequest(question=question, session_id=session_id),
                            role=Role.PROCUREMENT_MANAGER,
                        )
                    thinking_row.delete()
                    answer = response.interpretation.strip()
                    with messages:
                        with ui.row().classes("taulack-message-row bot-row w-full items-start"):
                            ui.image("/assets/taulack.png").classes("taulack-message-avatar")
                            with ui.column().classes("taulack-message bot gap-2"):
                                ui.markdown(answer).classes("taulack-answer")
                                if response.verified_facts:
                                    ui.label("VERIFIED FROM PROCUREAI").classes(
                                        "taulack-evidence-title"
                                    )
                                    with ui.element("div").classes("taulack-evidence-grid"):
                                        for fact in response.verified_facts[:4]:
                                            with ui.element("div").classes("taulack-evidence-item"):
                                                ui.label(fact.label).classes(
                                                    "taulack-evidence-label"
                                                )
                                                ui.label(fact.value).classes(
                                                    "taulack-evidence-value"
                                                )
                                ui.label(
                                    "Based on current ProcureAI records and deterministic analytics"
                                ).classes("taulack-answer-meta")
                    suggestions.clear()
                    with suggestions:
                        for suggestion in response.suggested_followups[:3]:
                            ui.button(
                                suggestion,
                                on_click=lambda _, value=suggestion: submit_suggestion(value),
                            ).props("outline rounded dense no-caps")
                except (RuntimeError, ValueError, KeyError, PermissionError, httpx.HTTPError):
                    thinking.set_text(
                        "I couldn't complete a verified procurement query for that question. Please add a supplier, material, metric, or time period."
                    )
                    thinking.classes(remove="pulse-soft")
                finally:
                    send_button.enable()

            send_button = ui.button(icon="arrow_upward", on_click=send_message).props(
                'round unelevated color="primary" aria-label="Send message to Ask Taulack"'
            )
            prompt.on("keydown.enter", send_message)

            async def submit_suggestion(value: str) -> None:
                prompt.set_value(value)
                await send_message()

        with suggestions:
            for suggestion in (
                "Which suppliers require immediate attention?",
                "Where can we reduce sourcing risk?",
                "What actions are overdue?",
            ):
                ui.button(
                    suggestion, on_click=lambda _, value=suggestion: submit_suggestion(value)
                ).props("outline rounded dense no-caps")

    with (
        ui.button(on_click=lambda: panel.set_visibility(not panel.visible))
        .props('round unelevated aria-label="Open Ask Taulack"')
        .classes("taulack-launcher")
    ):
        ui.html('<img src="/assets/taulack.png" alt="Ask Taulack" class="taulack-avatar">')
    ui.element("span").classes("taulack-online")


@contextmanager
def shell(title: str, subtitle: str):
    with ui.header().classes("procure-header items-center"):
        with ui.element("div").classes("brand-mark flex items-center justify-center"):
            ui.icon("insights").classes("text-xl")
        ui.html("Procure<span>AI</span>").classes("brand-name")
        ui.space()
        ui.input(placeholder="Search suppliers, materials, orders…").props(
            'dense outlined aria-label="Global search"'
        ).classes("w-72 desktop-context")
        ui.button(icon="notifications_none").props('flat round aria-label="Notifications"')
        ui.button(
            icon="dark_mode",
            on_click=lambda: ui.run_javascript("window.ProcureAITheme.toggle()"),
        ).props(
            'flat round data-theme-toggle aria-label="Switch to dark theme" title="Switch to dark theme"'
        ).classes("theme-toggle")
        ui.label("Procurement Manager").classes("context-chip desktop-context")
        ui.avatar("DA", color="primary", text_color="white").classes("ml-1")
    with ui.left_drawer(value=True).props("width=250 breakpoint=1024").classes("procure-drawer"):
        for section, items in NAV.items():
            ui.label(section).classes("nav-section")
            for path, label, icon in items:
                ui.button(
                    label, icon=icon, on_click=lambda target=path: ui.navigate.to(target)
                ).props('flat no-caps align="left"').classes("nav-btn")
        ui.space()
        ui.separator().classes("my-3")
        with ui.row().classes("items-center px-3 pb-2 gap-2"):
            ui.icon("verified_user").classes("text-primary")
            with ui.column().classes("gap-0"):
                ui.label("Demo workspace").classes("text-xs font-semibold")
                ui.label("Synthetic procurement data").classes("text-[11px] text-gray-500")
    with ui.column().classes("page-wrap page-enter w-full"):
        with ui.row().classes("w-full items-end mb-1"):
            with ui.column().classes("gap-0"):
                ui.label(title).classes("page-title")
                ui.label(subtitle).classes("page-subtitle")
            ui.space()
            with ui.row().classes("items-center gap-2 desktop-context"):
                ui.icon("sync", size="16px").classes("text-primary")
                ui.label("Updated from local pipeline").classes("text-xs text-gray-500")
        yield
        with ui.element("footer").classes("app-footer w-full"):
            ui.label("Developed by Mirza Shaheen Iqubal")
    taulack_chatbox()


def kpi(
    title: str,
    value: str,
    note: str,
    icon: str,
    color: str = "neutral",
    tooltip: str | None = None,
):
    with ui.card().classes(f"kpi-card grow trend-{color}"):
        with ui.row().classes("w-full items-center"):
            ui.label(title).classes("kpi-label")
            ui.space()
            with ui.element("div").classes("kpi-icon"):
                ui.icon(icon, size="19px")
        ui.label(value).classes("kpi-value")
        ui.label(note).classes("kpi-note")
        if tooltip:
            ui.tooltip(tooltip)


def table(columns: list[dict], rows: list[dict], *, pagination: int = 10):
    for column in columns:
        field = column.get("field", "")
        if any(
            term in field
            for term in (
                "spend",
                "exposure",
                "cost",
                "price",
                "quantity",
                "score",
                "risk",
                "otd",
                "duration",
                "records",
                "impact",
                "actual",
                "expected",
            )
        ):
            column.setdefault("align", "right")
        column.setdefault("sortable", True)
    with ui.column().classes("w-full gap-2"):
        search = (
            ui.input(placeholder="Search all table cells…")
            .props('outlined dense clearable debounce="250" aria-label="Search table"')
            .classes("table-search")
        )
        data_table = (
            ui.table(columns=columns, rows=rows, pagination=pagination)
            .props('flat rows-per-page-label="Rows per page"')
            .classes("w-full table-shell")
        )
        data_table.bind_filter_from(search, "value")
    return data_table


def agent_link(label: str = "Investigate with ProcureAI"):
    return ui.button(label, icon="auto_awesome", on_click=lambda: ui.navigate.to("/advisor")).props(
        "outline no-caps"
    )


@ui.page("/")
def executive_page():
    with shell(
        "Procurement Overview",
        f"Good morning — here's what requires attention across the portfolio · {datetime.now(UTC).strftime('%d %B %Y')}",
    ):
        with SessionLocal() as db:
            runs = pipeline_runs(db)
        updated = runs[0]["started"] if runs else "No completed pipeline run"
        with ui.row().classes("dashboard-toolbar w-full items-center"):
            with ui.column().classes("gap-0"):
                ui.label("EXECUTIVE CONTROL TOWER").classes("eyebrow")
                ui.label(f"Updated from local pipeline · {updated}").classes("freshness-label")
            ui.space()
            period = (
                ui.select(
                    {
                        3: "Last 3 months",
                        6: "Last 6 months",
                        12: "Last 12 months",
                        0: "All history",
                    },
                    value=12,
                )
                .props("outlined dense options-dense aria-label='Executive reporting period'")
                .classes("w-44")
            )
            agent_link("Open AI insights")

        @ui.refreshable
        def content():
            months = period.value or None
            with SessionLocal() as db:
                data = dashboard_kpis(db, months)
                start, end = dashboard_period(db, months)
                trend = monthly_spend(db, start, end)
                risks = risk_distribution(db)
                current_alerts = alerts(db)[:5]
            with ui.row().classes("executive-kpi-grid w-full"):
                kpi(
                    "Total Spend",
                    euro(data["total_spend"]),
                    "Selected reporting period",
                    "payments",
                    tooltip="Approved purchase-order value in the selected period.",
                )
                kpi(
                    "Savings Opportunity",
                    euro(data["savings_opportunity"]),
                    "Deterministic price variance",
                    "savings",
                    "positive",
                    "Estimated addressable savings identified through deterministic price, benchmark, contract, and sourcing analytics.",
                )
                kpi(
                    "High-Risk Exposure",
                    euro(data["risk_exposure"]),
                    f"{data['critical_suppliers']} critical suppliers",
                    "crisis_alert",
                    "negative",
                    "Financial exposure associated with currently open High or Critical alerts.",
                )
                kpi(
                    "On-Time Delivery",
                    f"{data['on_time_delivery']:.1%}",
                    "Across completed deliveries",
                    "local_shipping",
                    "positive",
                    "Deliveries received on or before their planned delivery date.",
                )
                kpi(
                    "Quality Cost",
                    euro(data["quality_cost"]),
                    "Cost of poor quality",
                    "verified",
                    "negative",
                    "Estimated financial impact recorded against quality incidents.",
                )
                kpi(
                    "Active Suppliers",
                    str(data["active_suppliers"]),
                    f"Across {data['supplier_countries']} countries",
                    "factory",
                    tooltip="Distinct suppliers with purchase activity in the selected period.",
                )
                kpi(
                    "Contract Coverage",
                    f"{data['contract_coverage']:.1%}",
                    "Share of spend under contract",
                    "contract",
                    "positive",
                    "Percentage of procurement spend associated with an active contract reference during the selected period.",
                )
                kpi(
                    "Single-Source Materials",
                    str(data["single_source_materials"]),
                    f"{data['critical_single_source_materials']} critical",
                    "link_off",
                    "negative",
                    "Active materials identified as single-source in the material master.",
                )
            with ui.element("div").classes("executive-analytics-grid w-full"):
                with ui.card().classes("chart-card analytics-card"):
                    chart_header(
                        "Monthly Procurement Spend",
                        f"Total spend across categories · through {data['period_end']}",
                    )
                    fig = go.Figure(
                        go.Scatter(
                            x=[r["month"] for r in trend],
                            y=[r["spend"] for r in trend],
                            fill="tozeroy",
                            line={"color": PURPLE, "width": 2.5},
                            fillcolor="rgba(139,108,232,.10)",
                            mode="lines+markers",
                            hovertemplate="%{x}<br>Spend: <b>€%{y:,.0f}</b><extra></extra>",
                        )
                    )
                    polish_chart(fig, height=310, x_title="Month", y_title="Spend (€)")
                    fig.update_yaxes(tickprefix="€", tickformat="~s")
                    ui.plotly(fig).classes("w-full")
                with ui.card().classes("chart-card analytics-card"):
                    chart_header(
                        "Supplier Risk Distribution", "Number of suppliers by current risk level"
                    )
                    fig = go.Figure(
                        go.Bar(
                            x=[r["level"].title() for r in risks],
                            y=[r["count"] for r in risks],
                            marker_color=[SEMANTIC[r["level"]] for r in risks],
                            text=[r["count"] for r in risks],
                            textposition="outside",
                            customdata=[r["spend"] for r in risks],
                            hovertemplate="%{x}<br>Suppliers: <b>%{y}</b><br>Associated spend: €%{customdata:,.0f}<extra></extra>",
                        )
                    )
                    polish_chart(fig, height=310, x_title="Risk level", y_title="Supplier count")
                    ui.plotly(fig).classes("w-full")
                with ui.card().classes("chart-card analytics-card alerts-panel"):
                    chart_header("Top Procurement Alerts", "Highest-priority open issues")
                    for alert in current_alerts:
                        with ui.row().classes("alert-list-item w-full items-start"):
                            ui.icon(
                                "warning_amber",
                                color="negative" if alert["severity"] == "CRITICAL" else "warning",
                            )
                            with ui.column().classes("gap-0 grow"):
                                with ui.row().classes("items-center gap-2"):
                                    ui.badge(alert["severity"]).classes(f"risk-{alert['severity']}")
                                    ui.label(alert["type"].replace("_", " ").title()).classes(
                                        "alert-type"
                                    )
                                ui.label(alert["description"]).classes(
                                    "alert-evidence line-clamp-2"
                                )
                                ui.label(
                                    f"{alert['supplier']} · {euro(alert['exposure'])} exposure"
                                ).classes("alert-meta")
                    ui.button("View all", on_click=lambda: ui.navigate.to("/risk")).props(
                        "flat no-caps icon-right=arrow_forward"
                    ).classes("self-start")

        content()
        period.on_value_change(lambda: content.refresh())


@ui.page("/procurement")
def procurement_page():
    with shell(
        "Procurement Operations",
        "Purchase activity, suppliers, deliveries, quality and invoice controls",
    ):
        with SessionLocal() as db:
            category_options = ["All categories", *[r["category"] for r in category_spend(db)]]
            runs = pipeline_runs(db)
        with ui.row().classes("dashboard-toolbar w-full items-center"):
            ui.label(
                f"Updated from local pipeline · {runs[0]['started'] if runs else 'No completed run'}"
            ).classes("freshness-label")
            ui.space()
            period = (
                ui.select(
                    {
                        3: "Last 3 months",
                        6: "Last 6 months",
                        12: "Last 12 months",
                        0: "All history",
                    },
                    value=3,
                )
                .props("outlined dense options-dense")
                .classes("w-44")
            )
            category = (
                ui.select(category_options, value="All categories")
                .props("outlined dense options-dense")
                .classes("w-52")
            )

        @ui.refreshable
        def operations_content():
            months = period.value or None
            selected_category = category.value
            with SessionLocal() as db:
                data = dashboard_kpis(db, months)
                start, end = dashboard_period(db, months)
                delivery = delivery_summary(db, start, end)
                quality = quality_summary(db, start, end)
                invoices = invoice_summary(db, start, end)
                categories = category_spend(db, start, end, selected_category)
                deliveries = delivery_trend(db, start, end)
                suppliers = top_suppliers_by_spend(db, start, end, selected_category)
            with ui.row().classes("operations-kpi-grid w-full"):
                kpi("Spend", euro(data["total_spend"]), "Approved PO value", "payments")
                kpi(
                    "Active Suppliers",
                    str(data["active_suppliers"]),
                    f"Across {data['supplier_countries']} countries",
                    "factory",
                )
                late_rate = delivery["late"] / delivery["total"] if delivery["total"] else 0
                kpi(
                    "Deliveries",
                    f"{delivery['total']:,}",
                    f"{delivery['late']:,} late ({late_rate:.1%})",
                    "local_shipping",
                    "negative",
                )
                kpi(
                    "Quality Incidents",
                    str(quality["incidents"]),
                    f"{euro(quality['cost'])} cost impact",
                    "verified",
                    "negative",
                )
                kpi(
                    "Invoice Mismatches",
                    str(invoices["mismatches"]),
                    f"{invoices['match_rate']:.1%} match rate",
                    "receipt_long",
                    "negative",
                )
            with ui.element("div").classes("operations-analytics-grid w-full"):
                with ui.card().classes("chart-card analytics-card"):
                    chart_header(
                        "Purchase Orders by Category", "PO value · selected reporting period"
                    )
                    top = categories[:5][::-1]
                    total_spend = sum(row["spend"] for row in categories)
                    fig = go.Figure(
                        go.Bar(
                            x=[r["spend"] for r in top],
                            y=[r["category"] for r in top],
                            orientation="h",
                            marker_color=PURPLE,
                            text=[compact_euro(r["spend"]) for r in top],
                            textposition="outside",
                            customdata=[
                                [r["po_count"], r["spend"] / total_spend if total_spend else 0]
                                for r in top
                            ],
                            hovertemplate="%{y}<br>PO value: <b>€%{x:,.0f}</b><br>PO count: %{customdata[0]}<br>Share: %{customdata[1]:.1%}<extra></extra>",
                        )
                    )
                    polish_chart(fig, height=300, x_title="Purchase value (€)", y_title="Category")
                    fig.update_xaxes(tickprefix="€", tickformat="~s")
                    ui.plotly(fig).classes("w-full")
                with ui.card().classes("chart-card analytics-card"):
                    chart_header(
                        "On-Time vs Late Deliveries", "Delivery performance trend · selected period"
                    )
                    fig = go.Figure()
                    fig.add_trace(
                        go.Scatter(
                            x=[r["month"] for r in deliveries],
                            y=[r["on_time"] * 100 for r in deliveries],
                            name="On-time %",
                            line={"color": "#27835e", "width": 2.5},
                            mode="lines+markers",
                            customdata=[r["total"] for r in deliveries],
                            hovertemplate="%{x}<br>On-time: %{y:.1f}%<br>Total deliveries: %{customdata}<extra></extra>",
                        )
                    )
                    fig.add_trace(
                        go.Scatter(
                            x=[r["month"] for r in deliveries],
                            y=[r["late"] * 100 for r in deliveries],
                            name="Late %",
                            line={"color": "#bd3f4b", "width": 2.5},
                            mode="lines+markers",
                            customdata=[r["total"] for r in deliveries],
                            hovertemplate="%{x}<br>Late: %{y:.1f}%<br>Total deliveries: %{customdata}<extra></extra>",
                        )
                    )
                    polish_chart(fig, height=300, x_title="Month", y_title="Delivery share (%)")
                    ui.plotly(fig).classes("w-full")
                with ui.card().classes("chart-card analytics-card supplier-panel"):
                    chart_header("Top 5 Suppliers by Spend", "Performance and current risk")
                    with ui.element("div").classes("supplier-mini-table w-full"):
                        with ui.row().classes("supplier-mini-head w-full"):
                            for label in ("#", "Supplier", "Spend", "OTD", "Quality", "Risk"):
                                ui.label(label)
                        for index, supplier in enumerate(suppliers, 1):
                            with (
                                ui.row()
                                .classes("supplier-mini-row w-full items-center cursor-pointer")
                                .on(
                                    "click",
                                    lambda _, sid=supplier["supplier_id"]: ui.navigate.to(
                                        f"/suppliers/{sid}"
                                    ),
                                )
                            ):
                                ui.label(str(index))
                                ui.label(supplier["code"]).classes("font-semibold")
                                ui.label(euro(supplier["spend"]))
                                ui.label(f"{supplier['otd']:.0%}")
                                ui.label(f"{supplier['quality_score']:.0f}")
                                ui.badge(supplier["risk_level"]).classes(
                                    f"risk-{supplier['risk_level']}"
                                )
                    ui.button("View all", on_click=lambda: ui.navigate.to("/suppliers")).props(
                        "flat no-caps icon-right=arrow_forward"
                    )

        operations_content()
        period.on_value_change(lambda: operations_content.refresh())
        category.on_value_change(lambda: operations_content.refresh())


@ui.page("/suppliers")
def suppliers_page():
    with SessionLocal() as db:
        rows = supplier_scorecards(db)
    with shell(
        "Supplier intelligence",
        "Transparent performance scorecards, peer comparison and risk prioritization",
    ):
        agent_link()
        with ui.row().classes("w-full gap-3"):
            kpi("Suppliers", str(len(rows)), "Active synthetic companies", "factory")
            kpi(
                "Strategic spend",
                euro(sum(r["spend"] for r in rows[:15])),
                "Top 15 suppliers",
                "account_balance",
            )
            kpi(
                "High / critical",
                str(sum(r["risk_level"] in {"HIGH", "CRITICAL"} for r in rows)),
                "Current risk assessment",
                "warning",
                "red",
            )
            kpi(
                "Average score",
                f"{sum(r['score'] for r in rows) / len(rows):.1f}",
                "Quality 25% · Delivery 25%",
                "score",
                "emerald",
            )
        cols = [
            {"name": n, "label": l, "field": n, "sortable": True, "align": "left"}
            for n, l in [
                ("code", "Supplier"),
                ("name", "Name"),
                ("country", "Country"),
                ("spend_display", "Annual/period spend"),
                ("otd_display", "OTD"),
                ("quality_score", "Quality"),
                ("incidents", "Incidents"),
                ("risk", "Risk score"),
                ("risk_level", "Tier"),
                ("score", "Overall"),
            ]
        ]
        table(
            cols,
            [
                {**r, "spend_display": euro(r["spend"]), "otd_display": f"{r['otd']:.1%}"}
                for r in rows
            ],
            pagination=15,
        )
        ui.label(
            "Formula: Quality 25% + Delivery 25% + Cost 20% + inverse Risk 20% + Commercial 10%."
        ).classes("text-xs text-slate-500")
        ui.button(
            "Open SUP-DE-014 portfolio investigation",
            icon="open_in_new",
            on_click=lambda: ui.navigate.to("/suppliers/SUP-DE-014"),
        ).props("outline no-caps")


@ui.page("/suppliers/{supplier_code}")
def supplier_detail_page(supplier_code: str):
    with SessionLocal() as db:
        suppliers = supplier_scorecards(db)
        supplier = next((row for row in suppliers if row["code"] == supplier_code), suppliers[0])
        current_alerts = [row for row in alerts(db) if row.get("supplier") == supplier["code"]]
    with shell(
        supplier["code"], f"{supplier['name']} · {supplier['country']} · Strategic supplier"
    ):
        with ui.row().classes("w-full items-center"):
            ui.badge(f"● {supplier['risk_level']}").classes(f"risk-{supplier['risk_level']}")
            ui.label("Supplier intelligence / Portfolio / Investigation").classes(
                "text-xs text-gray-500"
            )
            ui.space()
            ui.button(
                "AI Investigation", icon="auto_awesome", on_click=lambda: ui.navigate.to("/advisor")
            ).classes("primary-btn").props("no-caps")
        with ui.row().classes("w-full gap-3"):
            kpi("Annual Spend", euro(supplier["spend"]), "Selected reporting period", "payments")
            kpi(
                "Supplier Score",
                f"{supplier['score']:.0f}/100",
                "Composite performance score",
                "score",
            )
            kpi(
                "Risk Score",
                f"{supplier['risk']:.0f}/100",
                f"{supplier['risk_level']} risk classification",
                "shield",
            )
            kpi("On-Time Delivery", pct(supplier["otd"]), "Completed deliveries", "local_shipping")
            kpi(
                "Quality Score",
                f"{supplier['quality_score']:.0f}/100",
                f"{supplier['incidents']} recorded incidents",
                "verified",
            )
        tabs = ui.tabs().classes("w-full text-primary")
        for label in (
            "Overview",
            "Cost",
            "Delivery",
            "Quality",
            "Risk",
            "Contracts",
            "Orders",
            "AI Investigation",
        ):
            with tabs:
                ui.tab(label)
        with ui.tab_panels(tabs, value="Overview").classes("w-full section-card"):
            with ui.tab_panel("Overview"):
                with ui.row().classes("w-full gap-4 items-stretch"):
                    with ui.card().classes("section-card grow min-w-[420px]"):
                        chart_header("Performance signal", "Current supplier score dimensions")
                        for label, value in (
                            ("Delivery", supplier["otd"] * 100),
                            ("Quality", supplier["quality_score"]),
                            ("Risk resilience", 100 - supplier["risk"]),
                            ("Overall", supplier["score"]),
                        ):
                            ui.label(f"{label} · {value:.0f}/100").classes("text-xs font-semibold")
                            ui.linear_progress(value=value / 100, color="primary").props(
                                "rounded size=8px"
                            )
                    with ui.card().classes("section-card grow min-w-[360px]"):
                        chart_header(
                            "Active attention", "Evidence-based alerts linked to this supplier"
                        )
                        if current_alerts:
                            for alert in current_alerts[:4]:
                                with ui.column().classes("alert-card critical w-full gap-1"):
                                    ui.label(alert["severity"]).classes("eyebrow")
                                    ui.label(alert["description"]).classes("text-sm font-semibold")
                                    ui.label(f"Exposure · {euro(alert['exposure'])}").classes(
                                        "text-xs text-gray-500"
                                    )
                        else:
                            ui.label("No active alerts for the selected supplier.").classes(
                                "page-subtitle"
                            )
            for label in (
                "Cost",
                "Delivery",
                "Quality",
                "Risk",
                "Contracts",
                "Orders",
                "AI Investigation",
            ):
                with ui.tab_panel(label):
                    ui.label(
                        f"{label} evidence is available through portfolio analytics and ProcureAI Advisor."
                    ).classes("page-subtitle")


@ui.page("/spend")
def spend_page():
    with SessionLocal() as db:
        rows = category_spend(db)
        suppliers = supplier_scorecards(db)
        data = executive_dashboard(db)
    with shell("Spend analytics", "Category, supplier, Pareto and concentration analysis"):
        with ui.row().classes("w-full gap-3"):
            kpi(
                "Addressable spend", euro(data["total_spend"]), "PO line reconciliation", "payments"
            )
            kpi(
                "Top supplier share",
                f"{data['top_supplier_share']:.1%}",
                "Concentration indicator",
                "pie_chart",
            )
            kpi("HHI", f"{data['hhi']:,.0f}", "Portfolio concentration index", "analytics")
        with ui.row().classes("w-full gap-4"):
            with ui.card().classes("chart-card wide-chart grow"):
                chart_header("Category spend", "Purchase value by procurement category")
                fig = go.Figure(
                    go.Bar(
                        y=[r["category"] for r in rows[::-1]],
                        x=[r["spend"] for r in rows[::-1]],
                        orientation="h",
                        marker_color=PURPLE,
                        text=[compact_euro(row["spend"]) for row in rows[::-1]],
                        textposition="outside",
                        hovertemplate="%{y}<br><b>€%{x:,.0f}</b><extra></extra>",
                    )
                )
                polish_chart(fig, height=390, x_title="Purchase value (€)", y_title="Category")
                ui.plotly(fig).classes("w-full")
            with ui.card().classes("chart-card wide-chart grow"):
                chart_header("Supplier concentration", "Top 15 suppliers by purchase value")
                top = suppliers[:15]
                fig = go.Figure(
                    go.Bar(
                        x=[r["code"] for r in top],
                        y=[r["spend"] for r in top],
                        marker_color="#a98df5",
                        text=[compact_euro(row["spend"]) for row in top],
                        textposition="outside",
                        hovertemplate="%{x}<br><b>€%{y:,.0f}</b><extra></extra>",
                    )
                )
                polish_chart(fig, height=390, x_title="Supplier", y_title="Purchase value (€)")
                fig.update_xaxes(tickangle=-45)
                ui.plotly(fig).classes("w-full")


@ui.page("/cost")
def cost_page():
    with SessionLocal() as db:
        rows = cost_anomalies(db)
    with shell(
        "Cost intelligence", "Purchase price variance, anomaly evidence and deterministic savings"
    ):
        agent_link("Explain anomalies with ProcureAI")
        total = sum(r["impact"] for r in rows)
        high = sum(r["confidence"] == "HIGH" for r in rows)
        with ui.row().classes("w-full gap-3"):
            kpi(
                "Detected opportunity",
                euro(total),
                "Actual minus expected price",
                "savings",
                "emerald",
            )
            kpi("Flagged lines", str(len(rows)), "Impact greater than €5,000", "flag")
            kpi("High confidence", str(high), "Impact greater than €50,000", "verified", "blue")
        cols = [
            {"name": n, "label": l, "field": n, "sortable": True, "align": "left"}
            for n, l in [
                ("material", "Material"),
                ("description", "Description"),
                ("supplier", "Supplier"),
                ("actual_display", "Actual unit"),
                ("expected_display", "Expected unit"),
                ("quantity", "Quantity"),
                ("impact_display", "Potential excess"),
                ("confidence", "Confidence"),
            ]
        ]
        table(
            cols,
            [
                {
                    **r,
                    "actual_display": f"€{r['actual']:,.2f}",
                    "expected_display": f"€{r['expected']:,.2f}",
                    "impact_display": euro(r["impact"]),
                }
                for r in rows
            ],
            pagination=12,
        )
        ui.label(
            "Authoritative opportunity = quantity × max(actual unit price − expected unit price, 0). AI does not calculate these figures."
        ).classes("text-xs text-slate-500")


@ui.page("/delivery")
def delivery_page():
    with SessionLocal() as db:
        data = delivery_summary(db)
        rows = supplier_scorecards(db)
    with shell(
        "Delivery analytics",
        "On-time delivery, lateness, lead-time variability and supplier ranking",
    ):
        with ui.row().classes("w-full gap-3"):
            kpi(
                "OTD", f"{data['otd']:.1%}", "Actual on/before planned", "local_shipping", "emerald"
            )
            kpi(
                "Late deliveries",
                f"{data['late']:,}",
                f"of {data['total']:,} deliveries",
                "schedule",
                "red",
            )
            kpi(
                "Average lateness",
                f"{data['average_lateness']:.1f} days",
                "Late deliveries only",
                "calendar_month",
                "amber",
            )
        ranked = sorted(rows, key=lambda r: r["otd"])
        fig = go.Figure(
            go.Bar(
                x=[r["otd"] * 100 for r in ranked[:20]],
                y=[r["code"] for r in ranked[:20]],
                orientation="h",
                marker_color=["#dc2626" if r["otd"] < 0.8 else "#f59e0b" for r in ranked[:20]],
                text=[f"{row['otd']:.1%}" for row in ranked[:20]],
                textposition="outside",
                hovertemplate="%{y}<br><b>%{x:.1f}% OTD</b><extra></extra>",
            )
        )
        polish_chart(fig, height=520, x_title="On-time delivery (%)", y_title="Supplier")
        with ui.card().classes("chart-card w-full"):
            chart_header(
                "Supplier delivery ranking",
                "Twenty suppliers with the lowest on-time delivery performance",
            )
            ui.plotly(fig).classes("w-full")


@ui.page("/quality")
def quality_page():
    with SessionLocal() as db:
        data = quality_summary(db)
        rows = supplier_scorecards(db)
    with shell(
        "Quality analytics", "Incidents, cost of poor quality, severity and supplier early warning"
    ):
        with ui.row().classes("w-full gap-3"):
            kpi("Incidents", str(data["incidents"]), "Three-year history", "report_problem", "red")
            kpi(
                "Quality cost",
                euro(data["cost"]),
                "Estimated cost of poor quality",
                "payments",
                "violet",
            )
            kpi(
                "Mean resolution",
                f"{data['mean_close_days']:.1f} days",
                "Closed incidents",
                "task_alt",
                "emerald",
            )
        with ui.row().classes("w-full gap-4"):
            with ui.card().classes("chart-card wide-chart grow"):
                chart_header("Incident severity", "Quality incidents grouped by business severity")
                fig = go.Figure(
                    go.Bar(
                        x=[r["severity"] for r in data["by_severity"]],
                        y=[r["count"] for r in data["by_severity"]],
                        marker_color=[
                            SEMANTIC["CRITICAL"],
                            SEMANTIC["HIGH"],
                            SEMANTIC["MEDIUM"],
                            SEMANTIC["LOW"],
                        ],
                        text=[str(row["count"]) for row in data["by_severity"]],
                        textposition="outside",
                        hovertemplate="%{x}<br><b>%{y:,} incidents</b><extra></extra>",
                    )
                )
                polish_chart(fig, height=330, x_title="Severity", y_title="Incident count")
                ui.plotly(fig).classes("w-full")
            with ui.card().classes("section-card grow"):
                ui.label("Supplier early warning").classes("font-semibold")
                cols = [
                    {"name": n, "label": l, "field": n, "sortable": True}
                    for n, l in [
                        ("code", "Supplier"),
                        ("incidents", "Incidents"),
                        ("quality_score", "Quality score"),
                        ("risk_level", "Risk"),
                    ]
                ]
                table(
                    cols,
                    sorted(rows, key=lambda r: r["incidents"], reverse=True)[:15],
                    pagination=8,
                )


@ui.page("/risk")
def risk_page():
    with SessionLocal() as db:
        rows = supplier_scorecards(db)
        current = alerts(db)
    with shell(
        "Risk center", "Supplier, quality, delivery, dependency, contract and commercial risk"
    ):
        agent_link()
        with ui.row().classes("w-full gap-3"):
            for level, color in [
                ("CRITICAL", "red"),
                ("HIGH", "orange"),
                ("MEDIUM", "blue"),
                ("LOW", "emerald"),
            ]:
                kpi(
                    level,
                    str(sum(r["risk_level"] == level for r in rows)),
                    "suppliers",
                    "warning",
                    color,
                )
        exposure = sum(r["spend"] for r in rows if r["risk_level"] in {"HIGH", "CRITICAL"})
        with ui.card().classes("advisor-hero w-full"):
            ui.label("HIGH & CRITICAL SPEND EXPOSURE").classes("eyebrow")
            ui.label(euro(exposure)).classes("text-4xl font-bold tracking-tight")
            ui.label("Annual spend associated with suppliers requiring priority attention").classes(
                "page-subtitle"
            )
        with ui.card().classes("chart-card w-full"):
            chart_header(
                "Supplier risk matrix",
                "Financial exposure plotted against current composite risk score",
            )
            colors = SEMANTIC
            fig = go.Figure()
            for level in colors:
                subset = [r for r in rows if r["risk_level"] == level]
                fig.add_trace(
                    go.Scatter(
                        x=[r["risk"] for r in subset],
                        y=[r["spend"] for r in subset],
                        mode="markers",
                        name=level,
                        text=[r["code"] for r in subset],
                        marker={
                            "color": colors[level],
                            "size": [max(8, min(28, r["spend"] / 200000)) for r in subset],
                        },
                    )
                )
            polish_chart(
                fig, height=400, x_title="Risk score (0–100)", y_title="Financial exposure (€)"
            )
            ui.plotly(fig).classes("w-full")
        cols = [
            {"name": n, "label": l, "field": n, "align": "left"}
            for n, l in [
                ("severity", "Severity"),
                ("type", "Category"),
                ("supplier", "Supplier"),
                ("description", "Reason / evidence"),
                ("exposure_display", "Exposure"),
            ]
        ]
        table(cols, [{**r, "exposure_display": euro(r["exposure"])} for r in current], pagination=8)


@ui.page("/projections")
def projections_page():
    with shell(
        "Procurement Projections",
        "Machine-learning outlook for spend, delivery, supplier risk and price exceptions",
    ):
        with ui.row().classes("dashboard-toolbar w-full items-center"):
            with ui.column().classes("gap-0"):
                ui.label("ML DECISION SUPPORT").classes("eyebrow")
                ui.label(
                    "Predictions are estimates and remain separate from verified historical facts"
                ).classes("freshness-label")
            ui.space()
            horizon = (
                ui.select({3: "Next 3 months", 6: "Next 6 months", 12: "Next 12 months"}, value=6)
                .props("outlined dense options-dense aria-label='Projection horizon'")
                .classes("w-44")
            )

        @ui.refreshable
        def projection_content():
            with SessionLocal() as db:
                data = procurement_projections(db, int(horizon.value))
            risk_rows = data["supplier_risk_outlook"]
            top_risk = risk_rows[0] if risk_rows else None
            projected_spend = sum(item["spend"] for item in data["spend_projection"])
            final_otd = data["delivery_projection"][-1]["otd"] if data["delivery_projection"] else 0
            anomaly_impact = sum(item["impact"] for item in data["price_anomalies"])
            with ui.row().classes("operations-kpi-grid w-full"):
                kpi(
                    "Projected Spend",
                    euro(projected_spend),
                    f"Next {data['horizon_months']} months",
                    "trending_up",
                    tooltip="Linear trend projection fitted to monthly approved purchase-order spend.",
                )
                kpi(
                    "Projected OTD",
                    f"{final_otd:.1f}%",
                    "End-of-horizon estimate",
                    "local_shipping",
                    "positive",
                    "Linear trend projection fitted to monthly on-time delivery share.",
                )
                kpi(
                    "Highest Projected Risk",
                    f"{top_risk['projected']:.1f}" if top_risk else "—",
                    top_risk["supplier"] if top_risk else "Insufficient history",
                    "crisis_alert",
                    "negative",
                    "Supplier risk trend extrapolated from the latest six recorded risk observations.",
                )
                kpi(
                    "Price Anomaly Impact",
                    euro(anomaly_impact),
                    f"Top {len(data['price_anomalies'])} detected exceptions",
                    "price_change",
                    "negative",
                    "Financial impact attached to the highest deterministic price-anomaly evidence.",
                )
            with ui.element("div").classes("projection-chart-grid w-full"):
                with ui.card().classes("chart-card projection-chart"):
                    chart_header(
                        "Spend Forecast", "Historical monthly spend and fitted forward projection"
                    )
                    history = data["spend_history"]
                    forecast = data["spend_projection"]
                    fig = go.Figure()
                    fig.add_trace(
                        go.Scatter(
                            x=[r["month"] for r in history],
                            y=[r["spend"] for r in history],
                            name="Historical",
                            line={"color": PURPLE, "width": 2.5},
                            mode="lines+markers",
                            hovertemplate="%{x}<br>Historical spend: €%{y:,.0f}<extra></extra>",
                        )
                    )
                    if forecast:
                        bridge_x = [history[-1]["month"], *[r["month"] for r in forecast]]
                        bridge_y = [history[-1]["spend"], *[r["spend"] for r in forecast]]
                        fig.add_trace(
                            go.Scatter(
                                x=bridge_x,
                                y=bridge_y,
                                name="ML projection",
                                line={"color": "#d08022", "width": 2.5, "dash": "dash"},
                                mode="lines+markers",
                                hovertemplate="%{x}<br>Projected spend: €%{y:,.0f}<extra></extra>",
                            )
                        )
                    polish_chart(fig, height=315, x_title="Month", y_title="Spend (€)")
                    fig.update_yaxes(tickprefix="€", tickformat="~s")
                    ui.plotly(fig).classes("w-full")
                with ui.card().classes("chart-card projection-chart"):
                    chart_header(
                        "Delivery Outlook", "Historical OTD and projected delivery performance"
                    )
                    delivery_history = data["delivery_history"]
                    delivery_forecast = data["delivery_projection"]
                    fig = go.Figure()
                    fig.add_trace(
                        go.Scatter(
                            x=[r["month"] for r in delivery_history],
                            y=[r["on_time"] * 100 for r in delivery_history],
                            name="Historical OTD",
                            line={"color": "#27835e", "width": 2.5},
                            mode="lines+markers",
                        )
                    )
                    if delivery_forecast:
                        fig.add_trace(
                            go.Scatter(
                                x=[
                                    delivery_history[-1]["month"],
                                    *[r["month"] for r in delivery_forecast],
                                ],
                                y=[
                                    delivery_history[-1]["on_time"] * 100,
                                    *[r["otd"] for r in delivery_forecast],
                                ],
                                name="ML projection",
                                line={"color": "#d08022", "width": 2.5, "dash": "dash"},
                                mode="lines+markers",
                            )
                        )
                    polish_chart(fig, height=315, x_title="Month", y_title="On-time delivery (%)")
                    ui.plotly(fig).classes("w-full")
            with ui.element("div").classes("projection-insight-grid w-full"):
                with ui.card().classes("section-card"):
                    chart_header("Supplier Risk Outlook", "Highest projected supplier risk scores")
                    columns = [
                        {"name": key, "label": label, "field": key}
                        for key, label in [
                            ("supplier", "Supplier"),
                            ("current_display", "Current"),
                            ("projected_display", "Projected"),
                            ("change_display", "Change"),
                            ("confidence_display", "Fit confidence"),
                        ]
                    ]
                    table(
                        columns,
                        [
                            {
                                **row,
                                "current_display": f"{row['current']:.1f}",
                                "projected_display": f"{row['projected']:.1f}",
                                "change_display": f"{row['change']:+.1f}",
                                "confidence_display": f"{row['confidence']:.0%}",
                            }
                            for row in risk_rows
                        ],
                        pagination=8,
                    )
                with ui.card().classes("section-card prediction-panel"):
                    chart_header(
                        "Important Predictions",
                        "Common high-value signals for procurement decisions",
                    )
                    for prediction in data["priority_predictions"]:
                        with ui.row().classes("alert-card w-full items-start"):
                            ui.icon("model_training").classes("text-primary")
                            with ui.column().classes("gap-0 grow"):
                                with ui.row().classes("items-center gap-2"):
                                    ui.badge(prediction["priority"]).classes(
                                        f"risk-{prediction['priority']}"
                                    )
                                    ui.label("ML PREDICTION").classes("eyebrow")
                                ui.label(prediction["title"]).classes("font-semibold")
                                ui.label(prediction["evidence"]).classes("text-xs text-gray-600")
                                ui.label(prediction["model"]).classes("text-[10px] text-gray-400")
                    ui.separator().classes("my-2")
                    ui.label(data["disclaimer"]).classes("text-xs text-gray-500")

        projection_content()
        horizon.on_value_change(lambda: projection_content.refresh())


@ui.page("/sourcing")
def sourcing_page():
    with (
        shell(
            "Strategic sourcing lab",
            "Deterministic qualified-supplier ranking and scenario comparison",
        ),
        ui.card().classes("section-card w-full"),
    ):
        agent_link("Explain ranking with ProcureAI")
        with ui.row().classes("items-end w-full"):
            material = ui.input("Material", value="MAT-0078").props("outlined dense")
            quantity = ui.number("Required quantity", value=1000, min=1).props("outlined dense")
            max_risk = ui.number("Maximum risk", value=80, min=0, max=100).props("outlined dense")
            result = ui.column().classes("w-full")

            def rank():
                result.clear()
                with SessionLocal() as db:
                    rows = sourcing_rank(
                        db, material.value, float(quantity.value), float(max_risk.value)
                    )
                with result:
                    cols = [
                        {"name": n, "label": l, "field": n, "sortable": True}
                        for n, l in [
                            ("code", "Supplier"),
                            ("decision_score", "Decision score"),
                            ("unit_display", "Unit price"),
                            ("cost_display", "Total cost"),
                            ("quality_score", "Quality"),
                            ("otd_display", "OTD"),
                            ("risk", "Risk"),
                        ]
                    ]
                    table(
                        cols,
                        [
                            {
                                **r,
                                "unit_display": f"€{r['unit_price']:,.2f}",
                                "cost_display": euro(r["total_cost"]),
                                "otd_display": f"{r['otd']:.1%}",
                            }
                            for r in rows
                        ],
                        pagination=5,
                    )
                    ui.label(
                        "Ranking: Price 35% + Quality 25% + Delivery 20% + inverse Risk 20%."
                    ).classes("text-xs text-slate-500")

            ui.button("Rank suppliers", icon="analytics", on_click=rank, color="blue-7")
        rank()


@ui.page("/advisor")
def advisor_page():
    session_id = f"ui-{uuid.uuid4().hex[:12]}"
    with shell("ProcureAI Advisor", "Controlled multi-agent procurement decision support"):
        with ui.card().classes("advisor-hero w-full"):
            with ui.row().classes("items-center gap-3"):
                with ui.element("div").classes("brand-mark flex items-center justify-center"):
                    ui.icon("auto_awesome")
                with ui.column().classes("gap-0"):
                    ui.label("Evidence-grounded procurement intelligence").classes(
                        "text-lg font-bold"
                    )
                    ui.label(
                        "Verified analytics first. Gemini explains; procurement decides."
                    ).classes("page-subtitle")
            ui.label("ASK PROCUREMENT INTELLIGENCE").classes("eyebrow mt-4")
            question = (
                ui.input(placeholder="Why does SUP-DE-014 require attention?")
                .props("outlined clearable")
                .classes("w-full text-base")
            )
            ui.label("Suggested investigations").classes("text-xs text-slate-500")
            suggestions = [
                "Why does SUP-DE-014 require attention?",
                "Where is our largest current savings opportunity?",
                "Find alternatives for MAT-0078.",
                "What should procurement management focus on this month?",
            ]
            with ui.row().classes("gap-2"):
                for suggestion in suggestions:
                    ui.button(
                        suggestion, on_click=lambda text=suggestion: question.set_value(text)
                    ).props("outline no-caps dense").classes("text-xs")
            response_area = ui.column().classes("w-full gap-4")

            def create_action(recommendation):
                with SessionLocal() as db:
                    db.add(
                        ProcurementAction(
                            action_type=recommendation.action_type,
                            title=recommendation.title,
                            reason=recommendation.reason,
                            financial_exposure=recommendation.financial_exposure,
                            priority=recommendation.priority,
                            suggested_owner=recommendation.suggested_owner,
                        )
                    )
                    db.commit()
                ui.notify("Internal ProcureAI action created", color="positive")

            async def investigate():
                if not question.value:
                    ui.notify("Enter a procurement question", color="warning")
                    return
                investigate_button.disable()
                response_area.clear()
                with response_area:
                    with ui.card().classes("section-card w-full"):
                        with ui.row().classes("items-center gap-3"):
                            ui.spinner("dots", size="lg", color="primary")
                            with ui.column().classes("gap-0"):
                                ui.label("Checking procurement evidence…").classes("font-semibold")
                                ui.label(
                                    "Reviewing performance, cost, quality and sourcing signals"
                                ).classes("text-xs text-gray-500")
                try:
                    with SessionLocal() as db:
                        result = await advisor_orchestrator.execute(
                            db,
                            AgentRequest(question=question.value, session_id=session_id),
                            role=Role.PROCUREMENT_MANAGER,
                        )
                    response_area.clear()
                    with response_area:
                        with ui.row().classes("w-full items-center"):
                            ui.label("RESPONSE").classes("text-xs font-bold text-slate-500")
                            ui.badge(
                                result.priority or "INFORMATION",
                                color="red" if result.priority in {"HIGH", "CRITICAL"} else "blue",
                            )
                            ui.space()
                            ui.label(f"Agent: {result.agent}").classes("text-xs text-slate-500")
                        with ui.card().classes("section-card evidence-card w-full"):
                            ui.label("VERIFIED EVIDENCE").classes("eyebrow")
                            for fact in result.verified_facts:
                                with ui.row().classes("w-full"):
                                    ui.label(fact.label).classes("text-sm text-slate-600")
                                    ui.space()
                                    ui.label(fact.value).classes("text-sm font-semibold")
                                    ui.badge(
                                        fact.source_tool.replace("get_", ""), color="blue"
                                    ).props("outline")
                        with ui.card().classes("section-card assessment-card w-full"):
                            ui.label("AI ASSESSMENT").classes("eyebrow")
                            ui.markdown(result.interpretation).classes("text-sm")
                            if not result.ai_available:
                                ui.badge("VERIFIED ANALYTICS REMAIN AVAILABLE", color="orange")
                        ui.label("RECOMMENDED ACTIONS").classes(
                            "text-xs font-bold text-emerald-700"
                        )
                        with ui.row().classes("advisor-actions w-full gap-3 items-stretch"):
                            for recommendation in result.recommendations:
                                with ui.card().classes("section-card action-card w-72"):
                                    ui.label(recommendation.title.upper()).classes(
                                        "text-sm font-bold"
                                    )
                                    ui.badge(
                                        recommendation.priority,
                                        color="red"
                                        if recommendation.priority in {"HIGH", "CRITICAL"}
                                        else "blue",
                                    )
                                    ui.label(recommendation.reason).classes(
                                        "text-xs text-slate-600"
                                    )
                                    ui.label(
                                        f"Exposure: {euro(recommendation.financial_exposure)}"
                                    ).classes("text-xs font-semibold")
                                    ui.label(f"Owner: {recommendation.suggested_owner}").classes(
                                        "text-xs"
                                    )
                                    ui.button(
                                        "Create internal action",
                                        on_click=lambda rec=recommendation: create_action(rec),
                                    ).props("outline dense no-caps")
                        ui.label(f"Tools consulted: {', '.join(result.tools_used)}").classes(
                            "text-xs text-slate-500"
                        )
                        ui.label(
                            "Decision support only · No supplier approval or purchasing action was performed."
                        ).classes("text-xs text-slate-500")
                except (
                    RuntimeError,
                    ValueError,
                    KeyError,
                    PermissionError,
                    httpx.HTTPError,
                ) as exc:
                    response_area.clear()
                    with response_area:
                        ui.label("AI explanation is temporarily unavailable.").classes(
                            "font-semibold text-amber-700"
                        )
                        ui.label(str(exc)).classes("text-xs text-slate-500")
                        ui.label("Deterministic analytics remain operational.")
                finally:
                    investigate_button.enable()

            investigate_button = ui.button(
                "Investigate with ProcureAI",
                icon="auto_awesome",
                on_click=investigate,
                color="primary",
            ).props("no-caps")


@ui.page("/login")
def login_page():
    with ui.element("main").classes("login-surface"):
        with ui.card().classes("login-card page-enter"):
            with ui.row().classes("items-center justify-center w-full gap-2"):
                with ui.element("div").classes("brand-mark flex items-center justify-center"):
                    ui.icon("insights")
                ui.html("Procure<span>AI</span>").classes("brand-name")
            ui.label("Procurement Intelligence Platform").classes(
                "text-xl font-bold text-center mt-4"
            )
            ui.label("Work smarter across suppliers, costs, quality and supply risk.").classes(
                "page-subtitle text-center mx-auto mb-4"
            )
            ui.input("Email", value="demo@procureai.local").props(
                'outlined type="email" autocomplete="username"'
            ).classes("w-full")
            ui.input("Password", password=True, password_toggle_button=True).props(
                'outlined autocomplete="current-password"'
            ).classes("w-full")
            ui.button(
                "Sign in", icon="arrow_forward", on_click=lambda: ui.navigate.to("/")
            ).classes("primary-btn w-full").props("no-caps")
            ui.separator().classes("my-2")
            with ui.row().classes("items-center justify-center w-full gap-2"):
                ui.icon("science", size="16px").classes("text-primary")
                ui.label("Demo environment · Synthetic procurement data").classes(
                    "text-xs text-gray-500"
                )


@ui.page("/pipelines")
def pipeline_page():
    with SessionLocal() as db:
        runs = pipeline_runs(db)
    with shell(
        "Pipeline control center",
        "Traceable ingestion, validation, transformation, analytics and ML execution",
    ):
        with ui.card().classes("section-card w-full"):
            with ui.row().classes("w-full justify-between items-center"):
                for i, step in enumerate(
                    [
                        "INGEST",
                        "VALIDATE",
                        "STAGE",
                        "TRANSFORM",
                        "MERGE",
                        "ANALYTICS",
                        "ML",
                        "COMPLETE",
                    ]
                ):
                    with ui.column().classes("items-center gap-2"):
                        with ui.element("div").classes("pipeline-node"):
                            ui.icon("check", size="22px")
                        ui.label(step).classes("text-xs font-semibold")
                    if i < 7:
                        ui.element("div").classes("pipeline-connector")
        cols = [
            {"name": n, "label": l, "field": n, "align": "left"}
            for n, l in [
                ("run_id", "Run ID"),
                ("pipeline", "Pipeline"),
                ("status", "Status"),
                ("started", "Started"),
                ("records", "Records"),
                ("duration", "Duration sec"),
            ]
        ]
        table(cols, runs, pagination=8)
        ui.label(
            "Schedule controls are intentionally read-only in demo mode. Pipeline writes require ADMIN in the API."
        ).classes("text-xs text-slate-500")


@ui.page("/reports")
def reports_page():
    today = datetime.now(UTC).date()
    default_start, default_end = monthly_period(today)
    with shell(
        "Intelligent Procurement Reports",
        "Immutable, evidence-grounded weekly and monthly reporting for every procurement role",
    ):
        with ui.row().classes("w-full gap-3"):
            with SessionLocal() as db:
                reports = list(db.query(Report).order_by(Report.generated_at.desc()).all())
                schedules = list(db.query(ReportSchedule).all())
            kpi("Generated Reports", str(len(reports)), "Immutable report versions", "description")
            kpi(
                "Ready",
                str(sum(item.status == "READY" for item in reports)),
                "Available for download",
                "task_alt",
            )
            kpi(
                "Schedules",
                str(sum(item.enabled for item in schedules)),
                "Active recurring reports",
                "schedule",
            )
            kpi(
                "Templates",
                "4 roles",
                "Analyst · Manager · Executive · Admin",
                "dashboard_customize",
            )

        tabs = ui.tabs().classes("w-full text-primary")
        with tabs:
            generate_tab = ui.tab("Generate Report", icon="add_chart")
            generated_tab = ui.tab("Generated Reports", icon="folder_open")
            scheduled_tab = ui.tab("Scheduled Reports", icon="schedule")
            templates_tab = ui.tab("Templates", icon="view_quilt")

        with ui.tab_panels(tabs, value=generate_tab).classes("section-card w-full"):
            with ui.tab_panel(generate_tab):
                ui.label("Generate a procurement intelligence report").classes("chart-title")
                ui.label(
                    "Select the period and audience. Sections are controlled by role permissions."
                ).classes("chart-subtitle")
                with ui.row().classes("w-full items-end gap-4 mt-4"):
                    report_type = ui.select(
                        ["MONTHLY", "WEEKLY"], value="MONTHLY", label="Report Type"
                    ).props("outlined")
                    audience = ui.select(
                        ["PROCUREMENT_ANALYST", "PROCUREMENT_MANAGER", "EXECUTIVE"],
                        value="PROCUREMENT_MANAGER",
                        label="Audience",
                    ).props("outlined")
                    period_start = ui.input("Period Start", value=default_start.isoformat()).props(
                        "outlined type=date"
                    )
                    period_end = ui.input("Period End", value=default_end.isoformat()).props(
                        "outlined type=date"
                    )
                    ai_analysis = ui.checkbox("AI analysis", value=True)
                generation_status = ui.column().classes("w-full mt-3")

                async def create_intelligent_report():
                    generation_status.clear()
                    with generation_status:
                        ui.spinner("dots", color="primary")
                        ui.label("Creating immutable evidence snapshot and report artifacts…")
                    try:
                        payload = ReportRequest(
                            report_type=ReportType(report_type.value),
                            audience_role=Role(audience.value),
                            period_start=date.fromisoformat(period_start.value),
                            period_end=date.fromisoformat(period_end.value),
                            ai_analysis=ai_analysis.value,
                        )
                        with SessionLocal() as db:
                            result = await generate_report(db, payload)
                        generation_status.clear()
                        with generation_status:
                            with ui.card().classes("section-card evidence-card w-full"):
                                ui.label("REPORT READY").classes("eyebrow")
                                ui.label(result.report_id).classes("text-xl font-bold")
                                ui.label(
                                    f"Version {result.version} · {result.template_version}"
                                ).classes("text-sm text-gray-500")
                                ui.label(result.narrative.executive_summary).classes("text-sm")
                                with ui.row().classes("gap-2"):
                                    ui.button(
                                        "Download PDF",
                                        icon="picture_as_pdf",
                                        on_click=lambda: ui.download(result.pdf_location),
                                    ).props("outline no-caps")
                                    ui.button(
                                        "Download Excel",
                                        icon="table_view",
                                        on_click=lambda: ui.download(result.excel_location),
                                    ).props("outline no-caps")
                                for warning in result.warnings:
                                    ui.label(warning).classes("text-xs text-amber-700")
                        ui.notify("Procurement report generated", color="positive")
                    except (ValueError, RuntimeError, httpx.HTTPError) as exc:
                        generation_status.clear()
                        with generation_status:
                            ui.label("Unable to generate report").classes("font-bold text-red-700")
                            ui.label(str(exc)).classes("text-sm text-gray-600")

                ui.button(
                    "Generate Report", icon="auto_awesome", on_click=create_intelligent_report
                ).classes("primary-btn mt-4").props("no-caps")

            with ui.tab_panel(generated_tab):
                ui.label("Generated reports").classes("chart-title")
                ui.label(
                    "Previous versions remain immutable and reproducible from their stored evidence snapshots."
                ).classes("chart-subtitle mb-4")
                columns = [
                    {"name": key, "label": label, "field": key, "sortable": True}
                    for key, label in (
                        ("report_id", "Report"),
                        ("period", "Period"),
                        ("audience", "Audience"),
                        ("generated", "Generated"),
                        ("version", "Version"),
                        ("status", "Status"),
                    )
                ]
                table(
                    columns,
                    [
                        {
                            "report_id": item.report_id,
                            "period": f"{item.period_start:%d %b} - {item.period_end:%d %b %Y}",
                            "audience": item.audience_role.replace("_", " ").title(),
                            "generated": item.generated_at.strftime("%d %b %Y %H:%M"),
                            "version": item.version,
                            "status": item.status,
                        }
                        for item in reports
                    ],
                    pagination=8,
                )
                with ui.row().classes("w-full gap-3 mt-4"):
                    for item in reports[:6]:
                        with ui.card().classes("section-card grow min-w-[280px]"):
                            ui.label(item.report_id).classes("text-sm font-bold")
                            ui.label(
                                f"{item.report_type.title()} · {item.audience_role.replace('_', ' ').title()} · v{item.version}"
                            ).classes("text-xs text-gray-500")
                            with ui.row().classes("gap-2"):
                                ui.button(
                                    "View",
                                    icon="visibility",
                                    on_click=lambda report_id=item.report_id: ui.navigate.to(
                                        f"/reports/{report_id}"
                                    ),
                                ).props("outline dense no-caps")
                                if item.pdf_location:
                                    ui.button(
                                        "PDF",
                                        icon="picture_as_pdf",
                                        on_click=lambda path=item.pdf_location: ui.download(path),
                                    ).props("outline dense no-caps")
                                if item.excel_location:
                                    ui.button(
                                        "Excel",
                                        icon="table_view",
                                        on_click=lambda path=item.excel_location: ui.download(path),
                                    ).props("outline dense no-caps")
                if not reports:
                    ui.label(
                        "No generated reports yet. Use Generate Report to create the first immutable version."
                    ).classes("page-subtitle mt-3")

            with ui.tab_panel(scheduled_tab):
                ui.label("Scheduled reports").classes("chart-title")
                ui.label(
                    "Recommended cadence: Monday morning weekly and first business day monthly."
                ).classes("chart-subtitle")
                with ui.row().classes("w-full gap-4 mt-4"):
                    for title, cadence, audience_name in (
                        (
                            "Weekly Procurement Brief",
                            "Monday · 07:00 Europe/Berlin",
                            "Procurement Manager",
                        ),
                        (
                            "Monthly Performance Report",
                            "First business day · 07:30 Europe/Berlin",
                            "Executive",
                        ),
                    ):
                        with ui.card().classes("section-card grow"):
                            ui.label(title).classes("font-bold")
                            ui.label(cadence).classes("text-sm text-gray-600")
                            ui.label(audience_name).classes("text-xs text-gray-500")
                            ui.badge("CONFIGURABLE", color="primary").props("outline")

            with ui.tab_panel(templates_tab):
                ui.label("Role-specific report templates").classes("chart-title")
                with ui.row().classes("w-full gap-4 mt-4 items-stretch"):
                    for role in (
                        Role.PROCUREMENT_ANALYST,
                        Role.PROCUREMENT_MANAGER,
                        Role.EXECUTIVE,
                        Role.ADMIN,
                    ):
                        with ui.card().classes("section-card grow min-w-[230px]"):
                            ui.label(role.value.replace("_", " ").title()).classes("font-bold")
                            ui.label(f"{len(role_sections(role))} controlled sections").classes(
                                "text-xs text-gray-500"
                            )
                            for section in role_sections(role)[:7]:
                                ui.label(f"• {section.replace('_', ' ').title()}").classes(
                                    "text-sm"
                                )


@ui.page("/reports/{report_id}")
def report_preview_page(report_id: str):
    with SessionLocal() as db:
        report = db.get(Report, report_id)
    if not report:
        with shell("Report not found", "The requested report ID does not exist"):
            ui.button("Back to reports", on_click=lambda: ui.navigate.to("/reports")).props(
                "outline no-caps"
            )
        return
    snapshot = report.snapshot
    with shell(
        "Report Preview",
        f"{report.report_id} · Version {report.version} · Immutable evidence snapshot",
    ):
        with ui.card().classes("advisor-hero w-full"):
            with ui.row().classes("w-full items-start"):
                with ui.column().classes("gap-1"):
                    ui.label("PROCUREMENT INTELLIGENCE REPORT").classes("eyebrow")
                    ui.label(report.report_type.title()).classes("text-2xl font-bold")
                    ui.label(
                        f"{report.period_start:%d %b %Y} – {report.period_end:%d %b %Y} · {report.audience_role.replace('_', ' ').title()}"
                    ).classes("page-subtitle")
                ui.space()
                ui.badge(report.status, color="positive" if report.status == "READY" else "warning")
            ui.label(report.summary or "Narrative unavailable").classes("text-sm mt-3")
            with ui.row().classes("gap-2 mt-2"):
                if report.pdf_location:
                    ui.button(
                        "Download PDF",
                        icon="picture_as_pdf",
                        on_click=lambda: ui.download(report.pdf_location),
                    ).classes("primary-btn").props("no-caps")
                if report.excel_location:
                    ui.button(
                        "Download Excel",
                        icon="table_view",
                        on_click=lambda: ui.download(report.excel_location),
                    ).props("outline no-caps")
        with ui.row().classes("w-full gap-3"):
            for item in snapshot["kpis"][:4]:
                value = (
                    euro(item["current"])
                    if item["unit"] == "EUR"
                    else pct(item["current"])
                    if item["unit"] == "PERCENT"
                    else str(item["current"])
                )
                kpi(item["label"], value, item["status"], "analytics")
        with ui.row().classes("w-full gap-4 items-stretch"):
            with ui.card().classes("section-card grow min-w-[440px]"):
                chart_header(
                    "Priority findings", "Ranked by verified severity and financial exposure"
                )
                for index, finding in enumerate(snapshot["findings"][:5], 1):
                    with ui.row().classes("alert-card w-full items-start"):
                        ui.label(f"{index:02d}").classes("eyebrow")
                        with ui.column().classes("gap-0 grow"):
                            ui.label(finding["title"]).classes("font-bold")
                            ui.label(finding["description"]).classes("text-sm text-gray-600")
                        ui.label(euro(finding["financial_impact"])).classes("font-bold")
            with ui.card().classes("section-card grow min-w-[360px]"):
                chart_header(
                    "ML early warnings", "Predictions are separated from confirmed historical facts"
                )
                for warning in snapshot["ml_warnings"][:6]:
                    ui.label(f"{warning['entity']} · {warning['prediction']}").classes(
                        "font-semibold"
                    )
                    ui.label(f"{warning['confidence']} confidence · {warning['model']}").classes(
                        "text-xs text-gray-500"
                    )


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(title="ProcureAI", port=8080, reload=False, favicon="🔷")
