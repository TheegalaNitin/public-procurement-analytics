"""
Procurement Anomaly Detector — Streamlit Dashboard
Rechnungshof Bremen · Vergabe-Analyse
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st
import duckdb
import pandas as pd
from datetime import date

from licence.verify import verify_licence, LicenceStatus
from config.settings import DB_PATH

# ── Page config ────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Vergabe-Anomalien · Bremen",
    page_icon="🗝️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Licence check ──────────────────────────────────────────────────────
try:
    token_from_secrets = st.secrets.get("LICENCE_TOKEN", None)
except Exception:
    token_from_secrets = None

lic = verify_licence(token_str=token_from_secrets)

if lic.status == LicenceStatus.LOCKED:
    col_lock, _ = st.columns([1, 3])
    with col_lock:
        wappen_path = Path(__file__).parent / "wappen_bremen.png"
        if wappen_path.exists():
            st.image(str(wappen_path), width=90)
    st.error("🔒  Zugriff gesperrt")
    st.markdown(f"**{lic.message}**")
    st.markdown("Bitte wenden Sie sich an den Anbieter zur Lizenzverlängerung.")
    st.markdown("📧 support@yourtool.de")
    st.stop()

if lic.status == LicenceStatus.GRACE:
    st.warning(
        f"⚠️  {lic.message}  —  Nur-Lese-Modus. "
        f"Neue Daten werden erst nach Lizenzverlängerung geladen."
    )

# ── Database connection ────────────────────────────────────────────────
@st.cache_resource
def get_con():
    return duckdb.connect(str(DB_PATH), read_only=True)

con = get_con()

# ── Sidebar ────────────────────────────────────────────────────────────
wappen_path = Path(__file__).parent / "wappen_bremen.png"

with st.sidebar:
    # Coat of arms centred at top of sidebar
    if wappen_path.exists():
        col_l, col_c, col_r = st.columns([1, 2, 1])
        with col_c:
            st.image(str(wappen_path), width=110)
    st.markdown(
        "<div style='text-align:center; font-size:13px; font-weight:600;"
        "color:#CC0000; margin-top:4px; margin-bottom:12px;'>"
        "Freie Hansestadt Bremen</div>",
        unsafe_allow_html=True,
    )
    st.markdown("### Vergabe-Anomalien")
    st.caption(f"Lizenz: **{lic.customer}**")
    st.caption(f"Gültig bis: {lic.expires}")
    st.divider()

    st.markdown("**Filter**")
    risk_filter = st.selectbox("Risikolevel", ["Alle", "HIGH", "MED", "LOW"])
    rule_filter = st.selectbox(
        "Regel",
        ["Alle", "R-01 Stückelung", "R-02 Preisausreißer",
         "R-03 Sole-Source", "R-04 Wiederholung"],
    )
    dept_options = ["Alle"] + [
        r[0] for r in con.execute(
            "SELECT DISTINCT buyer_dept FROM contracts ORDER BY 1"
        ).fetchall()
    ]
    dept_filter = st.selectbox("Behörde", dept_options)
    search = st.text_input("Lieferant suchen…", placeholder="z.B. BauWerk")
    st.divider()

    last_run = con.execute(
        "SELECT MAX(ingested_at)::DATE FROM contracts"
    ).fetchone()[0]
    st.caption(f"📅 Datenstand: {last_run or 'Noch kein Lauf'}")

# ── Main header ────────────────────────────────────────────────────────
col_logo, col_title = st.columns([1, 9])
with col_logo:
    if wappen_path.exists():
        st.image(str(wappen_path), width=90)
with col_title:
    st.markdown("## Vergabe-Anomalien · Freie Hansestadt Bremen")
    st.caption(
        "Rechnungshof Bremen  ·  Automatische Erkennung von Stückelung, "
        "Preisausreißern, Sole-Source-Konzentration und Wiederholungsvergaben."
    )

st.divider()

# ── KPI cards ──────────────────────────────────────────────────────────
total_contracts = con.execute(
    "SELECT COUNT(*) FROM contracts"
).fetchone()[0]

total_flags = con.execute(
    "SELECT COUNT(*) FROM anomalies WHERE outcome='open'"
).fetchone()[0]

high_flags = con.execute(
    "SELECT COUNT(*) FROM anomalies WHERE outcome='open' AND severity='HIGH'"
).fetchone()[0]

total_risk = con.execute(
    "SELECT COALESCE(SUM(risk_eur),0) FROM anomalies WHERE outcome='open'"
).fetchone()[0]

col1, col2, col3, col4 = st.columns(4)
col1.metric("Geprüfte Vergaben", f"{total_contracts:,}")
col2.metric(
    "Offene Auffälligkeiten", f"{total_flags}",
    delta=f"{high_flags} HIGH" if high_flags else None,
    delta_color="inverse",
)
col3.metric("Finanzielles Risiko", f"€ {total_risk:,.0f}")
col4.metric("Höchste Priorität", "HIGH" if high_flags > 0 else "Keine")

st.divider()

# ── Filters → query ────────────────────────────────────────────────────
rule_map = {
    "R-01 Stückelung":     "R-01",
    "R-02 Preisausreißer": "R-02",
    "R-03 Sole-Source":    "R-03",
    "R-04 Wiederholung":   "R-04",
}

where = ["a.outcome = 'open'"]
params = []

if risk_filter != "Alle":
    where.append("a.severity = ?")
    params.append(risk_filter)
if rule_filter != "Alle":
    where.append("a.rule_id = ?")
    params.append(rule_map[rule_filter])
if dept_filter != "Alle":
    where.append("c.buyer_dept = ?")
    params.append(dept_filter)
if search:
    where.append("c.vendor_name ILIKE ?")
    params.append(f"%{search}%")

where_sql = " AND ".join(where)

query = f"""
    SELECT
        a.id,
        a.rule_id                AS Regel,
        a.severity               AS Risiko,
        c.buyer_dept             AS Behörde,
        c.vendor_name            AS Lieferant,
        c.cpv_label              AS Leistungsart,
        ROUND(c.amount_eur)      AS "Betrag (EUR)",
        ROUND(a.risk_eur)        AS "Risikobetrag (EUR)",
        c.procedure_type         AS Verfahren,
        c.award_date::VARCHAR    AS Auftragsdatum,
        c.contract_id            AS Notiz_ID,
        'https://ted.europa.eu/en/notice/-/detail/' || c.contract_id AS TED_Link,
        a.description            AS Beschreibung
        
        
    FROM anomalies a
    JOIN contracts c ON c.contract_id = a.contract_id
    WHERE {where_sql}
    ORDER BY
        CASE a.severity WHEN 'HIGH' THEN 1 WHEN 'MED' THEN 2 ELSE 3 END,
        a.risk_eur DESC
    LIMIT 200
"""

df = con.execute(query, params).df()

# ── Flag table ─────────────────────────────────────────────────────────
def colour_severity(val):
    colours = {
        "HIGH": "background-color:#FCEBEB;color:#A32D2D;font-weight:500",
        "MED":  "background-color:#FAEEDA;color:#854F0B;font-weight:500",
        "LOW":  "background-color:#EAF3DE;color:#3B6D11;font-weight:500",
    }
    return colours.get(val, "")

st.markdown(f"### Auffälligkeiten  ({len(df)} Treffer)")

display_cols = [c for c in df.columns if c != "id"]
styled = (
    df[display_cols]
    .style
    .map(colour_severity, subset=["Risiko"])
)
st.dataframe(
    styled,
    use_container_width=True,
    hide_index=True,
    column_config={
        "TED_Link": st.column_config.LinkColumn(
            "TED Quelle",
            display_text="Notiz öffnen ↗",
        ),
    },
)
st.divider()

# ── Case detail + review ───────────────────────────────────────────────
st.markdown("### Fall im Detail prüfen")

if df.empty:
    st.info("Keine Auffälligkeiten mit den gewählten Filtern.")
else:
    selected = st.selectbox(
        "Fall auswählen",
        df["Lieferant"] + "  ·  " + df["Regel"] + "  ·  " + df["Risiko"],
    )
    idx = (
        df["Lieferant"] + "  ·  " + df["Regel"] + "  ·  " + df["Risiko"]
    ).tolist().index(selected)
    row = df.iloc[idx]

    c1, c2, c3 = st.columns(3)
    c1.markdown(f"**Regel:** {row['Regel']}")
    c1.markdown(f"**Risiko:** {row['Risiko']}")
    c1.markdown(f"**Verfahren:** {row['Verfahren']}")
    c2.markdown(f"**Behörde:** {row['Behörde']}")
    c2.markdown(f"**Lieferant:** {row['Lieferant']}")
    c2.markdown(f"**Leistungsart:** {row['Leistungsart']}")
    c3.markdown(f"**Betrag:** € {row['Betrag (EUR)']:,.0f}")
    c3.markdown(f"**Risikobetrag:** € {row['Risikobetrag (EUR)']:,.0f}")
    c3.markdown(f"**Auftragsdatum:** {row['Auftragsdatum']}")

    st.info(f"📋 {row['Beschreibung']}")

    vendor_history = con.execute("""
        SELECT award_date::VARCHAR AS Datum,
               buyer_dept          AS Behörde,
               procedure_type      AS Verfahren,
               cpv_label           AS Leistung,
               ROUND(amount_eur)   AS "Betrag (EUR)"
        FROM contracts
        WHERE vendor_name = ?
        ORDER BY award_date DESC
        LIMIT 20
    """, [row["Lieferant"]]).df()

    with st.expander(
        f"📂 Alle Vergaben an {row['Lieferant']} "
        f"({len(vendor_history)} Einträge)"
    ):
        st.dataframe(vendor_history, use_container_width=True, hide_index=True)
# Comparable contracts in the same CPV category — puts the outlier in context
    comparables = con.execute("""
        SELECT
            vendor_name        AS Lieferant,
            ROUND(amount_eur)  AS "Betrag (EUR)",
            procedure_type     AS Verfahren,
            num_bidders        AS Bieter,
            award_date::VARCHAR AS Datum
        FROM contracts
        WHERE cpv_label = (
            SELECT cpv_label FROM contracts WHERE vendor_name = ? LIMIT 1
        )
        AND jurisdiction = 'bremen_state'
        AND amount_eur > 0
        ORDER BY amount_eur DESC
        LIMIT 10
    """, [row["Lieferant"]]).df()

    st.markdown("**Vergleichbare Vergaben derselben Leistungsart**")
    st.caption(
        "So lässt sich einordnen, ob der markierte Betrag wirklich "
        "außergewöhnlich ist — im Vergleich zu ähnlichen Aufträgen in Bremen."
    )
    st.dataframe(comparables, use_container_width=True, hide_index=True)
    st.markdown("**Prüfvermerk**")
    if True:  # review writing disabled — dashboard is read-only
        st.info(
            "📋 Prüfvermerke sind in dieser Ansicht deaktiviert. "
            "Die Fälle werden über die Pipeline verwaltet."
        )
    else:
        note = st.text_area(
            "Notiz (optional)",
            placeholder="z.B. Vergabe geprüft — sachlich gerechtfertigt wegen …",
        )
        btn1, btn2, btn3 = st.columns(3)
        flag_id = row["id"]

        if btn1.button("✅  Bestätigt — Verstoß", type="primary"):
            write_con = duckdb.connect(str(DB_PATH))
            write_con.execute(
                "UPDATE anomalies SET reviewed=true, outcome='confirmed',"
                " reviewer_note=? WHERE id=?",
                [note, flag_id],
            )
            write_con.close()
            st.cache_resource.clear()
            st.success("Als Verstoß markiert.")
            st.rerun()

        if btn2.button("❌  Falsch positiv"):
            write_con = duckdb.connect(str(DB_PATH))
            write_con.execute(
                "UPDATE anomalies SET reviewed=true, outcome='false_positive',"
                " reviewer_note=? WHERE id=?",
                [note, flag_id],
            )
            write_con.close()
            st.cache_resource.clear()
            st.warning("Als falsch positiv markiert.")
            st.rerun()

        if btn3.button("🔁  Zurücksetzen"):
            write_con = duckdb.connect(str(DB_PATH))
            write_con.execute(
                "UPDATE anomalies SET reviewed=false, outcome='open',"
                " reviewer_note=NULL WHERE id=?",
                [flag_id],
            )
            write_con.close()
            st.cache_resource.clear()
            st.info("Fall zurückgesetzt.")
            st.rerun()

st.divider()

# ── Reviewed cases ─────────────────────────────────────────────────────
st.markdown("### Bearbeitete Fälle")

reviewed = con.execute("""
    SELECT
        a.rule_id        AS Regel,
        a.outcome        AS Ergebnis,
        c.vendor_name    AS Lieferant,
        c.buyer_dept     AS Behörde,
        ROUND(a.risk_eur) AS "Risikobetrag (EUR)",
        a.reviewer_note  AS Notiz
    FROM anomalies a
    JOIN contracts c ON c.contract_id = a.contract_id
    WHERE a.reviewed = true
    ORDER BY a.rule_id
""").df()

if reviewed.empty:
    st.caption("Noch keine Fälle bearbeitet.")
else:
    st.dataframe(reviewed, use_container_width=True, hide_index=True)

st.divider()

# ── Export ─────────────────────────────────────────────────────────────
st.markdown("### Prüfbericht exportieren")
st.caption("Exportiert alle bestätigten Verstöße — bereit für den Jahresbericht.")

export_df = con.execute("""
    SELECT
        a.rule_id            AS Regel,
        a.severity           AS Risiko,
        c.buyer_dept         AS Behörde,
        c.vendor_name        AS Lieferant,
        c.cpv_label          AS Leistungsart,
        ROUND(c.amount_eur)  AS "Betrag (EUR)",
        ROUND(a.risk_eur)    AS "Risikobetrag (EUR)",
        c.award_date::VARCHAR AS Auftragsdatum,
        a.reviewer_note      AS Prüfvermerk,
        a.flagged_at::VARCHAR AS Erkannt_am
    FROM anomalies a
    JOIN contracts c ON c.contract_id = a.contract_id
    WHERE a.outcome = 'confirmed'
    ORDER BY a.rule_id
""").df()

col_a, col_b = st.columns(2)
col_a.metric("Bestätigte Verstöße", len(export_df))
col_b.metric(
    "Gesamtrisiko (bestätigt)",
    f"€ {export_df['Risikobetrag (EUR)'].sum():,.0f}"
    if not export_df.empty else "€ 0",
)

st.download_button(
    label="📥  Prüfbericht als CSV herunterladen",
    data=export_df.to_csv(
        index=False, sep=";", decimal=","
    ).encode("utf-8-sig"),
    file_name=f"pruefbericht_bremen_{date.today()}.csv",
    mime="text/csv",
    disabled=export_df.empty,
)

if export_df.empty:
    st.caption("Keine bestätigten Verstöße zum Exportieren.")