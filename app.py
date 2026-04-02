import socket
import qrcode
import io
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import date, datetime

from config import APP_PIN, USERNAME, PORT
from data_manager import load_sheet, save_bet, update_result, SHEET_GENERAL, SHEET_PERSO
from analytics import (
    compute_stats, stats_by_sport, stats_by_type, stats_by_day, stats_by_hour,
    boost_efficiency, stats_by_odds_range, kelly_by_sport,
    heatmap_sport_day, simulate_kelly_bankroll, trend_stats,
    generate_recommendations, streak_stats, rolling_win_rate,
)

# ── Config ────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Cotes Boostées", page_icon="🎯",
                   layout="wide", initial_sidebar_state="expanded")


# ── Helpers réseau ────────────────────────────────────────────────────────────
def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


def make_qr(url: str):
    qr = qrcode.QRCode(version=1, box_size=4, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#e2e8f0", back_color="#1e1b4b")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


# ── Login ─────────────────────────────────────────────────────────────────────
def login_page():
    st.markdown("""
    <style>
    .login-wrap { max-width:380px; margin:80px auto 0; text-align:center; }
    .login-title { font-size:2.4rem; font-weight:700; color:#818cf8; margin-bottom:.3rem; }
    .login-sub   { color:#64748b; margin-bottom:2rem; }
    </style>
    <div class="login-wrap">
      <p class="login-title">🎯 Cotes Boostées</p>
      <p class="login-sub">Entrez votre PIN pour accéder à l'application</p>
    </div>
    """, unsafe_allow_html=True)

    col = st.columns([1, 2, 1])[1]
    with col:
        pin = st.text_input("PIN", type="password", placeholder="····",
                             label_visibility="collapsed",
                             help="Le PIN est défini dans config.py")
        if st.button("🔓 Se connecter", use_container_width=True):
            if pin == APP_PIN:
                st.session_state["authenticated"] = True
                st.session_state["login_time"] = datetime.now().isoformat()
                st.rerun()
            else:
                st.error("PIN incorrect.")
        st.caption("Première utilisation ? Modifie `APP_PIN` dans `config.py`")

SPORTS = ["Football", "Football (F)", "Tennis", "Basketball", "Basketball (NBA)",
          "Hockey", "Cyclisme", "Ski Alpin", "Tennis de table", "Rugby", "Baseball", "Autre"]

SPORT_ICON = {
    "Football": "⚽", "Football (F)": "⚽", "Tennis": "🎾",
    "Basketball": "🏀", "Basketball (NBA)": "🏀", "Hockey": "🏒",
    "Cyclisme": "🚴", "Ski Alpin": "⛷️", "Tennis de table": "🏓",
    "Rugby": "🏉", "Baseball": "⚾",
}

CHART_THEME = dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#cbd5e1", family="Inter, sans-serif"),
    margin=dict(l=10, r=10, t=45, b=10),
)

# ── Auth gate ─────────────────────────────────────────────────────────────────
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    login_page()
    st.stop()

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family:'Inter',sans-serif; }

section[data-testid="stSidebar"] {
    background: linear-gradient(180deg,#0f172a 0%,#1e1b4b 100%);
    border-right: 1px solid rgba(99,102,241,.2);
}
.kpi {
    background: linear-gradient(135deg,rgba(255,255,255,.06),rgba(255,255,255,.02));
    border: 1px solid rgba(255,255,255,.1);
    border-radius: 16px; padding: 20px 24px; text-align: center;
    backdrop-filter: blur(10px); transition: transform .2s;
}
.kpi:hover { transform: translateY(-2px); }
.kpi-val { font-size:2rem; font-weight:700; margin:0; line-height:1.2; }
.kpi-lbl { font-size:.78rem; color:#94a3b8; margin:4px 0 0; text-transform:uppercase; letter-spacing:.05em; }
.kpi-sub { font-size:.72rem; color:#64748b; margin:2px 0 0; }

.green  { color:#4ade80; } .red    { color:#f87171; }
.blue   { color:#818cf8; } .yellow { color:#fbbf24; }
.purple { color:#c084fc; } .cyan   { color:#22d3ee; }

.rec-success { background:rgba(74,222,128,.1);  border-left:4px solid #4ade80; border-radius:8px; padding:12px 16px; margin:6px 0; }
.rec-warning { background:rgba(251,191,36,.1);  border-left:4px solid #fbbf24; border-radius:8px; padding:12px 16px; margin:6px 0; }
.rec-danger  { background:rgba(248,113,113,.1); border-left:4px solid #f87171; border-radius:8px; padding:12px 16px; margin:6px 0; }
.rec-info    { background:rgba(129,140,248,.1); border-left:4px solid #818cf8; border-radius:8px; padding:12px 16px; margin:6px 0; }

.section-title {
    font-size:1.05rem; font-weight:600; color:#e2e8f0;
    border-bottom:1px solid rgba(255,255,255,.08);
    padding-bottom:7px; margin:18px 0 12px;
}
hr { border-color:rgba(255,255,255,.07) !important; }
.trend-up   { color:#4ade80; font-weight:600; }
.trend-down { color:#f87171; font-weight:600; }

/* ── Mobile responsive ── */
@media (max-width: 768px) {
    .kpi { padding:14px 10px; }
    .kpi-val { font-size:1.4rem; }
    .kpi-lbl { font-size:.68rem; }
    .block-container { padding:1rem .5rem !important; }
}
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

@st.cache_data(ttl=5)
def get_data(sheet):
    return load_sheet(sheet)

def refresh():
    st.cache_data.clear()
    st.rerun()

def kpi(label, value, color="blue", sub=None, help_text=None):
    sub_html  = f'<p class="kpi-sub">{sub}</p>' if sub else ""
    title_attr = f'title="{help_text}"' if help_text else ""
    return f'<div class="kpi" {title_attr}><p class="kpi-val {color}">{value}</p><p class="kpi-lbl">{label}</p>{sub_html}</div>'

def rec_card(level, text):
    return f'<div class="rec-{level}">{text}</div>'

def sport_label(s):
    return f"{SPORT_ICON.get(s,'🎲')} {s}"

def _chart(**kw):
    cfg = {**CHART_THEME}
    cfg.update(kw)
    return cfg

def section_header(title: str, tooltip: str):
    """Render a section title with an inline ℹ️ popover."""
    c1, c2 = st.columns([11, 1])
    with c1:
        st.markdown(f'<p class="section-title">{title}</p>', unsafe_allow_html=True)
    with c2:
        with st.popover("ℹ️", use_container_width=False):
            st.markdown(tooltip)

def export_button(df: pd.DataFrame, filename: str, label: str = "📥 Exporter CSV"):
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(label, csv, filename, "text/csv", use_container_width=True)

def trend_delta(current: float, reference: float, suffix="") -> str:
    if reference == 0:
        return ""
    diff = current - reference
    cls  = "trend-up" if diff >= 0 else "trend-down"
    sign = "+" if diff >= 0 else ""
    return f'<span class="{cls}">({sign}{diff:.1f}{suffix})</span>'


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    local_ip  = get_local_ip()
    phone_url = f"http://{local_ip}:{PORT}"

    st.markdown(f"## 🎯 Cotes Boostées")
    st.caption(f"Connecté en tant que **{USERNAME}**")
    st.divider()

    page = st.radio("Navigation", [
        "🏠 Dashboard", "📋 Catalogue général", "👤 Mes paris",
        "📈 Analyses", "💡 Recommandations",
    ], label_visibility="collapsed")

    st.divider()

    st.markdown("**⚙️ Paramètres**")
    bankroll = st.number_input(
        "Bankroll (€)", min_value=10.0, value=100.0, step=10.0,
        key="bankroll_global",
        help="Ta bankroll totale dédiée aux paris. Utilisée pour le calcul Kelly.",
    )
    goal = st.number_input(
        "Objectif mensuel (€)", min_value=0.0, value=50.0, step=5.0,
        key="monthly_goal",
        help="Objectif de bénéfice mensuel. Une barre de progression s'affiche sur le dashboard.",
    )
    loss_limit = st.number_input(
        "Limite de perte journalière (€)", min_value=0.0, value=20.0, step=5.0,
        key="loss_limit",
        help="Si tu dépasses cette perte sur une journée, une alerte s'affiche.",
    )

    st.divider()

    target = st.radio(
        "Analyser :", ["Catalogue général", "Mes paris (Maxime)"],
        help="Choisis quelle source analyser dans Analyses et Recommandations.",
    )

    st.divider()

    # ── Accès mobile ─────────────────────────────────────────────────────────
    with st.expander("📱 Accès téléphone", expanded=False):
        st.caption(f"**Sur le même WiFi**, ouvre :")
        st.code(phone_url, language=None)
        try:
            qr_buf = make_qr(phone_url)
            st.image(qr_buf, caption="Scanner avec ton téléphone", use_container_width=True)
        except Exception:
            st.caption("(qrcode non disponible)")
        st.caption("⚠️ Ton Mac doit rester allumé avec l'app active.")

    st.divider()

    # ── Déconnexion ───────────────────────────────────────────────────────────
    if st.button("🔒 Se déconnecter", use_container_width=True):
        st.session_state["authenticated"] = False
        st.rerun()

    st.caption("Données : `cotes_boostees.xlsx`")


# ── Load data ─────────────────────────────────────────────────────────────────
df_gen      = get_data(SHEET_GENERAL)
df_me       = get_data(SHEET_PERSO)

# Ensure Date columns are always datetime (safety net for varied Google Sheets formats)
def _ensure_datetime(df):
    if "Date" in df.columns:
        if not pd.api.types.is_datetime64_any_dtype(df["Date"]):
            df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    return df

df_gen = _ensure_datetime(df_gen)
df_me  = _ensure_datetime(df_me)

df_analysis = df_gen if target == "Catalogue général" else df_me

# ── Sidebar data summary (injected after data load) ───────────────────────────
_sg = compute_stats(df_gen)
_sm = compute_stats(df_me)
st.sidebar.markdown(
    f"<div style='font-size:.75rem;color:#64748b;line-height:1.8'>"
    f"📋 <b>Catalogue</b> : {len(df_gen)} paris · {_sg['total']} terminés<br>"
    f"👤 <b>Mes paris</b>  : {len(df_me)} paris · {_sm['total']} terminés"
    f"</div>",
    unsafe_allow_html=True,
)


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
if page == "🏠 Dashboard":
    today_str = date.today().strftime("%A %d %B %Y").capitalize()
    st.markdown(f"# 🏠 Dashboard")
    st.caption(f"📅 {today_str} · Bienvenue, **{USERNAME}** 👋")

    stats_g = compute_stats(df_gen)
    stats_m = compute_stats(df_me)
    streaks = streak_stats(df_gen)

    # ── Résumé du jour ────────────────────────────────────────────────────────
    today_bets_gen = df_gen[df_gen["Date"].dt.date == date.today()]
    today_bets_me  = df_me[df_me["Date"].dt.date  == date.today()]
    today_pending  = today_bets_gen[today_bets_gen["Validé ?"] == "?"]
    today_played   = today_bets_gen[today_bets_gen["Validé ?"].isin(["✅","❌"])]
    today_pnl      = float(today_played["Gain réel"].sum()) if not today_played.empty else 0.0

    with st.container():
        st.markdown("### 📆 Aujourd'hui")
        d1, d2, d3, d4 = st.columns(4)
        with d1:
            st.metric("Paris du jour (catalogue)", len(today_bets_gen),
                       help="Nombre de paris enregistrés dans le catalogue pour aujourd'hui.")
        with d2:
            st.metric("Mes paris aujourd'hui", len(today_bets_me),
                       help="Tes paris personnels pour aujourd'hui.")
        with d3:
            label = "⏳ En attente" if not today_pending.empty else "✅ Tout validé"
            st.metric("En attente", len(today_pending),
                       help="Paris d'aujourd'hui dont le résultat n'a pas encore été saisi.")
        with d4:
            color = "normal" if today_pnl == 0 else ("normal" if today_pnl > 0 else "inverse")
            st.metric("P&L du jour", f"{today_pnl:+.2f} €",
                       help="Gain ou perte net(te) de la journée sur les paris terminés.")

        if not today_pending.empty:
            with st.expander(f"⏳ {len(today_pending)} pari(s) en attente de résultat aujourd'hui", expanded=True):
                for _, r in today_pending.iterrows():
                    c1, c2 = st.columns([6, 1])
                    with c1:
                        st.markdown(f"**{r['Événement']}** — {str(r['Pari'])[:60]}")
                        st.caption(f"{r['Sport']} · Cote {r['Cote boostée']:.2f} · Mise {r['Misé']:.2f} €")
                    with c2:
                        if st.button("✏️", key=f"quick_upd_{r['Événement'][:15]}",
                                      help="Aller mettre à jour ce pari"):
                            st.session_state["quick_update_target"] = r["Événement"]

    st.divider()

    # ── Alerte perte journalière ──────────────────────────────────────────────
    today_loss = today_pnl
    if loss_limit > 0 and today_loss < -loss_limit:
        st.error(f"⛔ Alerte : tu as perdu **{abs(today_loss):.2f} €** aujourd'hui, ce qui dépasse ta limite de {loss_limit:.0f} €. Arrête-toi là pour aujourd'hui.")

    # ── Objectif mensuel ──────────────────────────────────────────────────────
    if goal > 0:
        this_month = df_gen[
            (df_gen["Date"].dt.month == date.today().month) &
            (df_gen["Date"].dt.year  == date.today().year)
        ]
        month_ben = float(this_month["Gain réel"].sum()) if not this_month.empty else 0.0
        pct = min(max(month_ben / goal * 100, 0), 100)
        color_bar = "#4ade80" if month_ben >= 0 else "#f87171"
        st.markdown(
            f"**🎯 Objectif mensuel : {month_ben:+.2f} € / {goal:.0f} €**",
            help="Progression de ton objectif de bénéfice pour ce mois."
        )
        st.markdown(
            f'<div style="background:rgba(255,255,255,.07);border-radius:99px;height:10px;overflow:hidden">'
            f'<div style="height:10px;border-radius:99px;width:{pct:.1f}%;background:{color_bar};transition:width .4s"></div></div>'
            f'<small style="color:#64748b">{pct:.0f}% de l\'objectif atteint ce mois</small>',
            unsafe_allow_html=True,
        )
        st.markdown("")

    # ── KPIs ──────────────────────────────────────────────────────────────────
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1: st.markdown(kpi("Paris joués", stats_g["total"], "blue",
        f"{stats_g['wins']}W / {stats_g['losses']}L",
        "Nombre total de paris joués (gagnés + perdus). Les paris en attente ne sont pas comptés."),
        unsafe_allow_html=True)
    with c2:
        wr = stats_g["win_rate"]*100
        st.markdown(kpi("Win Rate", f"{wr:.1f}%", "green" if wr>=40 else "red",
            help_text="Pourcentage de paris gagnés sur le total des paris terminés. 50% = équilibre théorique."),
            unsafe_allow_html=True)
    with c3:
        b = stats_g["benefice"]
        st.markdown(kpi("Bénéfice", f"{b:+.2f} €", "green" if b>=0 else "red",
            f"ROI {stats_g['roi']*100:.1f}%",
            "Gains nets après déduction des mises perdues. ROI = Bénéfice / Total misé × 100."),
            unsafe_allow_html=True)
    with c4: st.markdown(kpi("Cote moy.", f"{stats_g['avg_cote']:.2f}", "yellow",
        f"Boost +{stats_g['avg_boost_pct']:.1f}%",
        "Cote boostée moyenne de tous tes paris. Le boost est l'augmentation en % par rapport à la cote initiale."),
        unsafe_allow_html=True)
    with c5:
        ev = stats_g["ev_moyen"]
        st.markdown(kpi("EV moyen", f"{ev:+.3f}", "green" if ev>0 else "red",
            help_text="Espérance de valeur : p × cote - 1. Positif = avantage mathématique théorique. Négatif = jouer contre toi sur le long terme."),
            unsafe_allow_html=True)
    with c6:
        sc = "green" if streaks["current_type"]=="✅" else "red"
        st.markdown(kpi("Série en cours", f"{streaks['current_type']} ×{streaks['current_val']}", sc,
            f"Record: {streaks['best_win']}W / {streaks['best_loss']}L",
            "Nombre de résultats identiques consécutifs. Les séries de défaites sont un signal pour réduire les mises."),
            unsafe_allow_html=True)

    st.divider()

    # ── Tendances 7 / 30 jours ────────────────────────────────────────────────
    section_header("Tendances récentes",
        "Comparaison de tes performances sur les 7 et 30 derniers jours par rapport à l'ensemble de l'historique. "
        "Les flèches colorées indiquent l'évolution par rapport à la moyenne globale.")

    period = st.radio("Période", ["7 jours", "30 jours"], horizontal=True,
                       help="Choisis la fenêtre de temps pour les tendances.")
    days   = 7 if period == "7 jours" else 30
    tr     = trend_stats(df_gen, days)

    tc1, tc2, tc3, tc4 = st.columns(4)
    with tc1: st.metric("Paris joués", tr["total"],
                         help="Nombre de paris terminés sur la période sélectionnée.")
    with tc2: st.metric("Win Rate",  f"{tr['win_rate']*100:.1f}%",
                         delta=f"{(tr['win_rate']-stats_g['win_rate'])*100:+.1f}%",
                         help="Win rate sur la période vs win rate global.")
    with tc3: st.metric("Bénéfice", f"{tr['benefice']:+.2f} €",
                         delta=None,
                         help="Bénéfice net sur la période.")
    with tc4: st.metric("ROI",      f"{tr['roi']*100:.1f}%",
                         delta=f"{(tr['roi']-stats_g['roi'])*100:+.1f}%",
                         help="ROI sur la période vs ROI global. Positif = tu t'améliores.")

    st.divider()

    # ── Charts ────────────────────────────────────────────────────────────────
    col_l, col_r = st.columns([3, 2])

    with col_l:
        section_header("Courbe de bénéfice cumulé",
            "Chaque point représente un pari terminé. La courbe monte quand tu gagnes, descend quand tu perds. "
            "Les points verts sont des victoires, les croix rouges des défaites.")
        played_g = df_gen[df_gen["Validé ?"].isin(["✅","❌"])].reset_index(drop=True)
        if not played_g.empty:
            played_g["N"]    = range(1, len(played_g)+1)
            played_g["Cumul"] = played_g["Gain réel"].cumsum()
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=played_g["N"], y=played_g["Cumul"],
                mode="lines", line=dict(color="#818cf8",width=2.5),
                fill="tozeroy", fillcolor="rgba(129,140,248,.1)",
                hovertemplate="Pari #%{x}<br><b>%{y:+.2f} €</b><extra></extra>"))
            w2 = played_g[played_g["Validé ?"]=="✅"]
            l  = played_g[played_g["Validé ?"]=="❌"]
            fig.add_trace(go.Scatter(x=w2["N"], y=w2["Cumul"], mode="markers",
                marker=dict(color="#4ade80",size=6), name="Gagné",
                hovertemplate="%{y:+.2f} €<extra>✅</extra>"))
            fig.add_trace(go.Scatter(x=l["N"], y=l["Cumul"], mode="markers",
                marker=dict(color="#f87171",size=6,symbol="x"), name="Perdu",
                hovertemplate="%{y:+.2f} €<extra>❌</extra>"))
            fig.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,.2)")
            fig.update_layout(**_chart(height=280, showlegend=True,
                                        legend=dict(orientation="h",y=1.15)))
            st.plotly_chart(fig, use_container_width=True)

    with col_r:
        section_header("Répartition des résultats",
            "Donut chart de la répartition globale. Le chiffre central est ton win rate. "
            "Les paris en attente (⏳) ne sont pas encore joués ou en cours.")
        fig_d = go.Figure(go.Pie(
            labels=["Gagnés","Perdus","En attente"],
            values=[stats_g["wins"],stats_g["losses"],stats_g["pending"]],
            hole=0.65, marker=dict(colors=["#4ade80","#f87171","#fbbf24"]),
            textinfo="percent",
            hovertemplate="<b>%{label}</b><br>%{value} paris (%{percent})<extra></extra>",
        ))
        fig_d.add_annotation(text=f"<b>{stats_g['win_rate']*100:.0f}%</b><br>win rate",
            x=0.5,y=0.5,font=dict(size=16,color="#e2e8f0"),showarrow=False)
        fig_d.update_layout(**_chart(height=280, showlegend=True,
                                      legend=dict(orientation="h",y=-0.1)))
        st.plotly_chart(fig_d, use_container_width=True)

    st.divider()

    # ── Comparatif Général vs Perso ───────────────────────────────────────────
    section_header("Comparatif Catalogue vs Mes paris",
        "Compare les performances du catalogue général (toutes les cotes disponibles) "
        "avec tes propres sélections. Si tes résultats sont meilleurs que le catalogue, "
        "tu as un bon sens de la sélection.")
    c1,c2,c3,c4 = st.columns(4)
    for col, label, vg, vm in zip([c1,c2,c3,c4],
        ["Paris","Win Rate","Bénéfice","ROI"],
        [stats_g["total"], f"{stats_g['win_rate']*100:.1f}%", f"{stats_g['benefice']:+.2f} €", f"{stats_g['roi']*100:.1f}%"],
        [stats_m["total"], f"{stats_m['win_rate']*100:.1f}%", f"{stats_m['benefice']:+.2f} €", f"{stats_m['roi']*100:.1f}%"]):
        with col:
            st.metric(f"📋 {label}", vg)
            st.metric(f"👤 {label}", vm)

    st.divider()

    section_header("Derniers paris — Catalogue",
        "Les 12 derniers paris enregistrés dans le catalogue général, du plus récent au plus ancien.")
    recent = df_gen.tail(12).copy()
    recent["Date"]  = recent["Date"].dt.strftime("%d/%m").fillna("")
    recent["Sport"] = recent["Sport"].apply(lambda s: sport_label(str(s)) if pd.notna(s) else "")
    st.dataframe(recent[["Date","Sport","Événement","Pari","Cote boostée","Validé ?","Gain réel"]],
        hide_index=True, use_container_width=True,
        column_config={
            "Cote boostée": st.column_config.NumberColumn(format="%.2f"),
            "Gain réel":    st.column_config.NumberColumn(format="%.2f €"),
        })


# ══════════════════════════════════════════════════════════════════════════════
# CATALOGUE GÉNÉRAL
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📋 Catalogue général":
    st.markdown("# 📋 Catalogue général")
    st.caption("Toutes les cotes boostées disponibles. C'est ici que tu (ou quelqu'un d'autre) enregistres les offres du jour.")

    sub = st.tabs(["📄 Voir / Mettre à jour", "➕ Ajouter un pari"])

    with sub[0]:
        cf1,cf2,cf3,cf4 = st.columns([2,2,2,1])
        with cf1:
            sf = st.selectbox("Sport", ["Tous"]+sorted(df_gen["Sport"].dropna().unique().tolist()),
                               key="g_sport", help="Filtre les paris par sport.")
        with cf2:
            dates = sorted(df_gen["Date"].dropna().unique().tolist(), reverse=True)
            dl = ["Toutes"]+[pd.Timestamp(d).strftime("%d/%m/%Y") for d in dates]
            df_f = st.selectbox("Date", dl, key="g_date",
                                 help="Filtre par date. Les dates les plus récentes sont en premier.")
        with cf3:
            sf2 = st.selectbox("Statut", ["Tous","✅ Gagné","❌ Perdu","⏳ En attente"],
                                key="g_status", help="Filtre par résultat du pari.")
        with cf4:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🔄", help="Recharger les données depuis le fichier Excel."):
                refresh()

        dv = df_gen.copy()
        if sf2 == "✅ Gagné":        dv = dv[dv["Validé ?"] == "✅"]
        elif sf2 == "❌ Perdu":      dv = dv[dv["Validé ?"] == "❌"]
        elif sf2 == "⏳ En attente": dv = dv[dv["Validé ?"] == "?"]
        if sf != "Tous":             dv = dv[dv["Sport"] == sf]
        if df_f != "Toutes":
            sd = pd.to_datetime(df_f, format="%d/%m/%Y")
            dv = dv[dv["Date"].dt.date == sd.date()]

        colinfo, colexp = st.columns([8,2])
        with colinfo: st.caption(f"{len(dv)} paris affichés")
        with colexp:  export_button(dv, "catalogue.csv", "📥 CSV")

        disp = dv[["Date","Heure","Sport","Événement","Pari","Cote initiale","Cote boostée","Validé ?","Misé","Gain réel"]].copy()
        disp = disp.sort_values("Date", ascending=False)
        disp["Date"] = disp["Date"].dt.strftime("%d/%m").fillna("")
        st.dataframe(disp, hide_index=True, use_container_width=True,
            column_config={
                "Cote initiale": st.column_config.NumberColumn(format="%.2f"),
                "Cote boostée":  st.column_config.NumberColumn(format="%.2f"),
                "Misé":          st.column_config.NumberColumn(format="%.2f €"),
                "Gain réel":     st.column_config.NumberColumn(format="%.2f €"),
            })

        st.divider()
        st.markdown("#### ✏️ Mettre à jour un résultat",
                     help="Sélectionne un pari en attente pour y entrer le résultat final.")
        pending = df_gen[df_gen["Validé ?"]=="?"]
        if pending.empty:
            st.info("Aucun pari en attente de résultat.")
        else:
            opts = [f"{pd.Timestamp(r['Date']).strftime('%d/%m') if pd.notna(r['Date']) else '?'} | {r['Sport']} | {r['Événement']} — {str(r['Pari'])[:45]}"
                    for _,r in pending.iterrows()]
            si = st.selectbox("Sélectionne le pari", range(len(opts)),
                               format_func=lambda i:opts[i], key="g_upd_sel",
                               help="Liste des paris dont le résultat n'a pas encore été saisi.")
            sr = pending.iloc[si]
            cu1,cu2,cu3 = st.columns([2,2,1])
            with cu1: nr = st.radio("Résultat",["✅ Gagné","❌ Perdu"],horizontal=True,key="g_res_r")
            with cu2: nm = st.number_input("Mise (€)",value=float(sr["Misé"]) if pd.notna(sr["Misé"]) else 5.0,
                               min_value=0.01,step=0.5,key="g_mise_u",
                               help="Mise effectivement jouée sur ce pari.")
            with cu3:
                st.markdown("<br>",unsafe_allow_html=True)
                if st.button("💾 Sauvegarder",key="g_save"):
                    update_result(SHEET_GENERAL,sr["Événement"],sr["Pari"],sr["Date"],
                                  "✅" if "Gagné" in nr else "❌",nm)
                    st.toast("Résultat enregistré !", icon="💾")
                    st.success("Mis à jour !")
                    refresh()

    with sub[1]:
        st.markdown("#### Ajouter une nouvelle cote boostée")
        st.caption("Enregistre ici une offre de cote boostée proposée par ton bookmaker.")
        with st.form("form_add_gen"):
            c1,c2,c3 = st.columns(3)
            with c1:
                fd = st.date_input("Date", value=date.today(),
                                    help="Date de l'événement sportif.")
                fh = st.text_input("Heure (ex: 20:45)",
                                    help="Heure de début de l'événement.")
                fs = st.selectbox("Sport", SPORTS,
                                   help="Type de sport concerné.")
            with c2:
                fe = st.text_input("Événement",
                                    help="Nom du match ou de la compétition. Ex: PSG - Real Madrid")
                fp = st.text_area("Description du pari", height=80,
                                   help="Décris précisément le pari. Ex: Mbappé buteur et PSG gagne")
            with c3:
                fci = st.number_input("Cote initiale",  min_value=1.01, step=0.05, value=2.0,
                                       help="Cote d'origine avant le boost du bookmaker.")
                fcb = st.number_input("Cote boostée",   min_value=1.01, step=0.05, value=2.5,
                                       help="Cote après boost. Doit être supérieure à la cote initiale.")
                fm  = st.number_input("Mise suggérée (€)", min_value=0.5, step=0.5, value=5.0,
                                       help="Mise recommandée pour ce pari dans le catalogue général.")
                fr  = st.selectbox("Résultat", ["?","✅","❌"],
                                    help="? = en attente. Tu pourras mettre à jour plus tard.")
            if st.form_submit_button("➕ Ajouter au catalogue", use_container_width=True):
                if not fe or not fp:
                    st.error("Événement et pari sont obligatoires.")
                else:
                    save_bet(SHEET_GENERAL,{"Date":datetime.combine(fd,datetime.min.time()),
                        "Heure":fh,"Sport":fs,"Événement":fe,"Pari":fp,
                        "Cote initiale":fci,"Cote boostée":fcb,"Misé":fm,"Validé ?":fr})
                    st.toast(f"✅ Pari ajouté : {fe}", icon="✅")
                    st.success(f"✅ Ajouté : {fe}")
                    refresh()


# ══════════════════════════════════════════════════════════════════════════════
# MES PARIS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "👤 Mes paris":
    st.markdown("# 👤 Mes paris — Maxime")
    st.caption("Tes paris personnels avec tes mises réelles. Distinct du catalogue général qui contient toutes les offres disponibles.")

    stats_m = compute_stats(df_me)
    streaks_m = streak_stats(df_me)

    c1,c2,c3,c4,c5 = st.columns(5)
    with c1: st.markdown(kpi("Paris joués",stats_m["total"],"blue",
        f"{stats_m['wins']}W / {stats_m['losses']}L",
        "Nombre de tes paris personnels terminés."), unsafe_allow_html=True)
    with c2:
        wr=stats_m["win_rate"]*100
        st.markdown(kpi("Win Rate",f"{wr:.1f}%","green" if wr>=40 else "red",
        help_text="Ton taux de réussite personnel. Compare-le au catalogue pour évaluer ta sélection."),unsafe_allow_html=True)
    with c3:
        b=stats_m["benefice"]
        st.markdown(kpi("Bénéfice",f"{b:+.2f} €","green" if b>=0 else "red",
        f"ROI {stats_m['roi']*100:.1f}%",
        "Tes gains nets personnels. ROI = Bénéfice / Total misé."),unsafe_allow_html=True)
    with c4: st.markdown(kpi("Misé total",f"{stats_m['total_mise']:.2f} €","yellow",
        help_text="Somme de toutes tes mises personnelles."),unsafe_allow_html=True)
    with c5:
        sc="green" if streaks_m["current_type"]=="✅" else "red"
        st.markdown(kpi("Série",f"{streaks_m['current_type']} ×{streaks_m['current_val']}",sc,
        f"Record: {streaks_m['best_win']}W / {streaks_m['best_loss']}L",
        "Ta série en cours. Une longue série de défaites est un signal d'alerte."),unsafe_allow_html=True)

    st.divider()
    sub_me = st.tabs(["📄 Historique","➕ Ajouter","✏️ Mettre à jour"])

    with sub_me[0]:
        cf1,cf2,col_exp = st.columns([3,3,2])
        with cf1:
            sf_me = st.selectbox("Sport",["Tous"]+sorted(df_me["Sport"].dropna().unique().tolist()),
                                  key="me_sp", help="Filtre par sport.")
        with cf2:
            st_me = st.selectbox("Statut",["Tous","✅ Gagné","❌ Perdu","⏳ En attente"],
                                  key="me_st", help="Filtre par résultat.")
        with col_exp:
            st.markdown("<br>",unsafe_allow_html=True)
            export_button(df_me,"mes_paris.csv","📥 Exporter CSV")

        dm = df_me.copy()
        if sf_me!="Tous": dm=dm[dm["Sport"]==sf_me]
        if st_me=="✅ Gagné":        dm=dm[dm["Validé ?"]=="✅"]
        elif st_me=="❌ Perdu":      dm=dm[dm["Validé ?"]=="❌"]
        elif st_me=="⏳ En attente": dm=dm[dm["Validé ?"]=="?"]

        dd = dm[["Date","Sport","Événement","Pari","Cote boostée","Validé ?","Misé","Gain réel","Bénéfice cumulé"]].copy()
        dd["Date"] = dd["Date"].dt.strftime("%d/%m").fillna("")
        st.dataframe(dd, hide_index=True, use_container_width=True,
            column_config={
                "Cote boostée":    st.column_config.NumberColumn(format="%.2f"),
                "Misé":            st.column_config.NumberColumn(format="%.2f €"),
                "Gain réel":       st.column_config.NumberColumn(format="%.2f €"),
                "Bénéfice cumulé": st.column_config.NumberColumn(format="%.2f €"),
            })

        played_me = df_me[df_me["Validé ?"].isin(["✅","❌"])].reset_index(drop=True)
        if not played_me.empty:
            played_me["N"]    = range(1,len(played_me)+1)
            played_me["Cumul"] = played_me["Gain réel"].cumsum()
            fig_me = go.Figure()
            fig_me.add_trace(go.Scatter(x=played_me["N"],y=played_me["Cumul"],
                mode="lines+markers",line=dict(color="#22d3ee",width=2),
                fill="tozeroy",fillcolor="rgba(34,211,238,.1)",
                hovertemplate="Pari #%{x}: %{y:+.2f} €<extra></extra>"))
            fig_me.add_hline(y=0,line_dash="dash",line_color="rgba(255,255,255,.2)")
            fig_me.update_layout(**_chart(height=220,title="Bénéfice cumulé — mes paris"))
            st.plotly_chart(fig_me,use_container_width=True)

    with sub_me[1]:
        mode = st.radio("Mode d'ajout",["Depuis le catalogue général","Saisie manuelle"],
                         horizontal=True,
                         help="Depuis le catalogue = tu choisis parmi les paris du catalogue. Saisie manuelle = tu entres un pari qui n'est pas dans le catalogue.")
        if mode=="Depuis le catalogue général":
            all_gen = df_gen.copy()
            og = [f"{pd.Timestamp(r['Date']).strftime('%d/%m') if pd.notna(r['Date']) else '?'} | {r['Sport']} | {r['Événement']} — {str(r['Pari'])[:50]}"
                  for _,r in all_gen.iterrows()]
            if not og:
                st.info("Aucun pari dans le catalogue.")
            else:
                sg = st.selectbox("Sélectionne un pari du catalogue",range(len(og)),
                                   format_func=lambda i:og[i],key="me_fg",
                                   help="Liste des paris du catalogue général à importer dans tes paris personnels.")
                sr = all_gen.iloc[sg]
                cm1,cm2 = st.columns(2)
                with cm1:
                    st.info(f"**{sr['Événement']}**\n\n{sr['Pari']}")
                    bp = (sr["Cote boostée"]-sr["Cote initiale"])/sr["Cote initiale"]*100
                    st.caption(f"Cote : {sr['Cote initiale']} → **{sr['Cote boostée']}** (+{bp:.1f}%)")
                with cm2:
                    mp = st.number_input("Ma mise réelle (€)",min_value=0.1,step=0.5,value=5.0,
                                          key="me_mg",
                                          help="La mise que tu as effectivement jouée sur ce pari.")
                    rp = st.selectbox("Résultat",["?","✅","❌"],key="me_rg",
                                       help="? si le résultat n'est pas encore connu.")
                    _heure = sr.get("Heure", "")
                    hp = str(_heure) if pd.notna(_heure) else ""
                if st.button("✅ Ajouter à mes paris",use_container_width=True,key="me_ag"):
                    try:
                        save_bet(SHEET_PERSO,{"Date":sr["Date"],"Heure":hp,"Sport":sr["Sport"],
                            "Événement":sr["Événement"],"Pari":sr["Pari"],
                            "Cote initiale":sr["Cote initiale"],"Cote boostée":sr["Cote boostée"],
                            "Misé":mp,"Validé ?":rp})
                        st.toast(f"✅ Ajouté à mes paris : {sr['Événement']}", icon="✅")
                        st.success("✅ Pari ajouté avec succès !")
                        st.cache_data.clear()
                    except Exception as e:
                        st.error(f"Erreur lors de l'ajout : {e}")
        else:
            with st.form("form_add_me"):
                c1,c2,c3 = st.columns(3)
                with c1:
                    fmd=st.date_input("Date",value=date.today())
                    fmh=st.text_input("Heure")
                    fms=st.selectbox("Sport",SPORTS)
                with c2:
                    fme=st.text_input("Événement")
                    fmp=st.text_area("Pari",height=80)
                with c3:
                    fmci=st.number_input("Cote initiale",min_value=1.01,step=0.05,value=2.0)
                    fmcb=st.number_input("Cote boostée",min_value=1.01,step=0.05,value=2.5)
                    fmm=st.number_input("Ma mise (€)",min_value=0.1,step=0.5,value=5.0,
                                         help="Mise réelle jouée.")
                    fmr=st.selectbox("Résultat",["?","✅","❌"])
                if st.form_submit_button("➕ Ajouter",use_container_width=True):
                    if not fme or not fmp: st.error("Événement et pari obligatoires.")
                    else:
                        save_bet(SHEET_PERSO,{"Date":datetime.combine(fmd,datetime.min.time()),
                            "Heure":fmh,"Sport":fms,"Événement":fme,"Pari":fmp,
                            "Cote initiale":fmci,"Cote boostée":fmcb,"Misé":fmm,"Validé ?":fmr})
                        st.success("Ajouté !")
                        refresh()

    with sub_me[2]:
        pm = df_me[df_me["Validé ?"]=="?"]
        if pm.empty:
            st.info("Aucun pari en attente de résultat.")
        else:
            om = [f"{pd.Timestamp(r['Date']).strftime('%d/%m') if pd.notna(r['Date']) else '?'} | {r['Événement']} — {str(r['Pari'])[:45]}"
                  for _,r in pm.iterrows()]
            sm = st.selectbox("Pari à mettre à jour",range(len(om)),
                               format_func=lambda i:om[i],key="me_us",
                               help="Sélectionne le pari dont tu veux entrer le résultat.")
            smr = pm.iloc[sm]
            u1,u2,u3 = st.columns([2,2,1])
            with u1: nrm=st.radio("Résultat",["✅ Gagné","❌ Perdu"],horizontal=True,key="me_rr")
            with u2: nmm=st.number_input("Mise réelle (€)",value=float(smr["Misé"]) if pd.notna(smr["Misé"]) else 5.0,
                               min_value=0.1,step=0.5,key="me_mu",
                               help="Tu peux ajuster la mise si tu l'as modifiée.")
            with u3:
                st.markdown("<br>",unsafe_allow_html=True)
                if st.button("💾 Sauvegarder",key="me_sv"):
                    update_result(SHEET_PERSO,smr["Événement"],smr["Pari"],smr["Date"],
                                  "✅" if "Gagné" in nrm else "❌",nmm)
                    st.toast("Résultat enregistré !", icon="💾")
                    st.success("Mis à jour !")
                    refresh()


# ══════════════════════════════════════════════════════════════════════════════
# ANALYSES
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📈 Analyses":
    st.markdown("# 📈 Analyses")

    # ── Sélecteur de source ───────────────────────────────────────────────────
    col_src, col_exp_btn = st.columns([4, 2])
    with col_src:
        src = st.radio(
            "Source de données",
            ["📋 Catalogue général", "👤 Mes paris (Maxime)"],
            horizontal=True,
            key="analyses_source",
            help="Le catalogue contient toutes les cotes disponibles. 'Mes paris' = uniquement tes sélections avec tes mises réelles.",
        )
    df_a    = df_gen if "Catalogue" in src else df_me
    played  = df_a[df_a["Validé ?"].isin(["✅","❌"])]
    src_lbl = "Catalogue général" if "Catalogue" in src else "Mes paris"
    with col_exp_btn:
        st.markdown("<br>", unsafe_allow_html=True)
        export_button(played, f"analyse_{src_lbl.replace(' ','_')}.csv", "📥 Exporter CSV")

    if len(played) < 3:
        st.warning("Pas assez de données. Valide au moins 3 paris pour voir les analyses.")
        st.stop()

    # ── KPIs rapides ──────────────────────────────────────────────────────────
    stats_a  = compute_stats(df_a)
    streaks_a = streak_stats(df_a)
    st.divider()
    kc1,kc2,kc3,kc4,kc5 = st.columns(5)
    with kc1: st.markdown(kpi("Paris joués", stats_a["total"], "blue",
        f"{stats_a['wins']}W / {stats_a['losses']}L",
        "Nombre total de paris terminés dans cette source."), unsafe_allow_html=True)
    with kc2:
        wr_a = stats_a["win_rate"]*100
        st.markdown(kpi("Win Rate", f"{wr_a:.1f}%", "green" if wr_a>=40 else "red",
        help_text="Pourcentage de paris gagnés parmi les paris terminés."), unsafe_allow_html=True)
    with kc3:
        b_a = stats_a["benefice"]
        st.markdown(kpi("Bénéfice", f"{b_a:+.2f} €", "green" if b_a>=0 else "red",
        f"ROI {stats_a['roi']*100:.1f}%",
        "Gains nets totaux. ROI = Bénéfice / Mises totales × 100."), unsafe_allow_html=True)
    with kc4:
        ev_a = stats_a["ev_moyen"]
        st.markdown(kpi("EV moyen", f"{ev_a:+.3f}", "green" if ev_a>0 else "red",
        help_text="Espérance de valeur : p × cote - 1. Positif = avantage mathématique."), unsafe_allow_html=True)
    with kc5:
        sc_a = "green" if streaks_a["current_type"]=="✅" else "red"
        st.markdown(kpi("Série en cours", f"{streaks_a['current_type']} ×{streaks_a['current_val']}", sc_a,
        f"Record: {streaks_a['best_win']}W / {streaks_a['best_loss']}L",
        "Série de résultats identiques consécutifs."), unsafe_allow_html=True)

    st.divider()

    # ── Courbe de bénéfice + Donut ────────────────────────────────────────────
    section_header("Courbe de bénéfice cumulé",
        "Évolution de ton bénéfice au fil des paris. Chaque point = un pari terminé. "
        "Les marqueurs verts = victoires, les croix rouges = défaites. "
        "Une courbe qui monte régulièrement indique une stratégie solide.")
    col_curve, col_donut = st.columns([3, 2])
    with col_curve:
        pl_sorted = played.reset_index(drop=True).copy()
        pl_sorted["N"]     = range(1, len(pl_sorted)+1)
        pl_sorted["Cumul"] = pl_sorted["Gain réel"].cumsum()
        fig_curve = go.Figure()
        fig_curve.add_trace(go.Scatter(x=pl_sorted["N"], y=pl_sorted["Cumul"],
            mode="lines", line=dict(color="#818cf8", width=2.5),
            fill="tozeroy", fillcolor="rgba(129,140,248,.1)",
            hovertemplate="Pari #%{x}<br><b>%{y:+.2f} €</b><extra></extra>", name="Bénéfice"))
        w2 = pl_sorted[pl_sorted["Validé ?"]=="✅"]
        l2 = pl_sorted[pl_sorted["Validé ?"]=="❌"]
        fig_curve.add_trace(go.Scatter(x=w2["N"], y=w2["Cumul"], mode="markers",
            marker=dict(color="#4ade80", size=6), name="Gagné",
            hovertemplate="%{y:+.2f} €<extra>✅</extra>"))
        fig_curve.add_trace(go.Scatter(x=l2["N"], y=l2["Cumul"], mode="markers",
            marker=dict(color="#f87171", size=6, symbol="x"), name="Perdu",
            hovertemplate="%{y:+.2f} €<extra>❌</extra>"))
        fig_curve.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,.2)")
        fig_curve.update_layout(**_chart(height=280, showlegend=True,
                                          legend=dict(orientation="h", y=1.15)))
        st.plotly_chart(fig_curve, use_container_width=True)
    with col_donut:
        fig_dn = go.Figure(go.Pie(
            labels=["Gagnés","Perdus","En attente"],
            values=[stats_a["wins"], stats_a["losses"], stats_a["pending"]],
            hole=0.65, marker=dict(colors=["#4ade80","#f87171","#fbbf24"]),
            textinfo="percent",
            hovertemplate="<b>%{label}</b><br>%{value} paris (%{percent})<extra></extra>"))
        fig_dn.add_annotation(text=f"<b>{wr_a:.0f}%</b><br>win rate",
            x=0.5, y=0.5, font=dict(size=16, color="#e2e8f0"), showarrow=False)
        fig_dn.update_layout(**_chart(height=280, showlegend=True,
                                       legend=dict(orientation="h", y=-0.1)))
        st.plotly_chart(fig_dn, use_container_width=True)

    st.divider()

    # ── Win Rate roulant ──────────────────────────────────────────────────────
    rw_window = 5
    rw_df = rolling_win_rate(df_a, window=rw_window)
    if not rw_df.empty:
        col_roll = f"Win Rate roulant ({rw_window} paris) %"
        section_header(f"Win Rate roulant ({rw_window} paris)",
            f"Chaque point = win rate calculé sur les **{rw_window} derniers paris**. "
            "Permet de voir si tu es en forme ou en difficulté en ce moment. "
            "**Ligne pointillée** = win rate global depuis le début. "
            "Une courbe qui monte = amélioration de la sélection.")
        fig_rw = go.Figure()
        fig_rw.add_trace(go.Scatter(
            x=rw_df["N"], y=rw_df[col_roll],
            mode="lines+markers", name=f"Win Rate roulant ({rw_window})",
            line=dict(color="#818cf8", width=2.5),
            marker=dict(size=5),
            hovertemplate="Pari #%{x}<br>Win Rate roulant : <b>%{y:.1f}%</b><extra></extra>"))
        fig_rw.add_trace(go.Scatter(
            x=rw_df["N"], y=rw_df["Win Rate global %"],
            mode="lines", name="Win Rate global",
            line=dict(color="#fbbf24", width=1.5, dash="dot"),
            hovertemplate="Pari #%{x}<br>Win Rate global : %{y:.1f}%<extra></extra>"))
        fig_rw.add_hline(y=50, line_dash="dash", line_color="rgba(255,255,255,.15)",
                          annotation_text="50%", annotation_font_color="#64748b")
        fig_rw.update_layout(**_chart(height=260, showlegend=True,
                                       legend=dict(orientation="h", y=1.15),
                                       yaxis=dict(ticksuffix="%", range=[0, 105])))
        st.plotly_chart(fig_rw, use_container_width=True)
        st.divider()

    # ── P&L mensuel ───────────────────────────────────────────────────────────
    section_header("P&L mensuel",
        "**Barres** = bénéfice net du mois (vert = profitable, rouge = en perte). "
        "**Ligne cyan** = Win Rate du mois (axe droit). "
        "Permet de voir si tes performances s'améliorent avec le temps.")
    if not played["Date"].isna().all():
        monthly = played.copy()
        monthly["Mois"] = monthly["Date"].dt.to_period("M").astype(str)
        monthly_pnl = monthly.groupby("Mois").apply(
            lambda g: pd.Series({
                "Bénéfice": round(float(g["Gain réel"].sum()), 2),
                "Paris": len(g),
                "Win Rate %": round((g["Validé ?"]=="✅").sum() / len(g) * 100, 1),
            })
        ).reset_index()
        if not monthly_pnl.empty:
            fig_monthly = go.Figure()
            fig_monthly.add_trace(go.Bar(
                x=monthly_pnl["Mois"], y=monthly_pnl["Bénéfice"],
                name="Bénéfice (€)",
                marker_color=monthly_pnl["Bénéfice"].apply(lambda x: "#4ade80" if x >= 0 else "#f87171"),
                text=monthly_pnl["Bénéfice"].apply(lambda x: f"{x:+.2f} €"),
                textposition="outside",
                hovertemplate="<b>%{x}</b><br>Bénéfice : %{y:+.2f} €<br>%{customdata[0]} paris<extra></extra>",
                customdata=monthly_pnl[["Paris"]].values,
            ))
            fig_monthly.add_trace(go.Scatter(
                x=monthly_pnl["Mois"], y=monthly_pnl["Win Rate %"],
                name="Win Rate %", yaxis="y2", mode="lines+markers",
                line=dict(color="#22d3ee", width=2), marker=dict(size=7),
                hovertemplate="%{x}<br>Win Rate : %{y:.0f}%<extra></extra>"))
            fig_monthly.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,.2)")
            fig_monthly.update_layout(**_chart(height=280, title="Bénéfice net et Win Rate par mois",
                yaxis2=dict(overlaying="y", side="right", title="Win Rate %",
                            color="#22d3ee", showgrid=False, ticksuffix="%", range=[0, 105]),
                legend=dict(orientation="h", y=1.15)))
            st.plotly_chart(fig_monthly, use_container_width=True)

    st.divider()

    # ── Par sport ─────────────────────────────────────────────────────────────
    section_header("Performance par sport",
        "**Win Rate** = % de paris gagnés. **ROI** = rentabilité nette (bénéfice / total misé × 100). "
        "**Boost moy.** = augmentation moyenne de cote offerte par le bookmaker sur ce sport.")
    sp_df = stats_by_sport(df_a)
    if not sp_df.empty:
        ca, cb = st.columns([5, 4])
        with ca:
            dsp = sp_df[["Sport","Paris","Gagnés","Win Rate %","Bénéfice (€)","ROI %","Cote moy.","Boost moy. %"]].copy()
            dsp["Win Rate %"]   = dsp["Win Rate %"].apply(lambda x: f"{x:.0f}%")
            dsp["ROI %"]        = dsp["ROI %"].apply(lambda x: f"{x:+.1f}%")
            dsp["Boost moy. %"] = dsp["Boost moy. %"].apply(lambda x: f"+{x:.1f}%")
            st.dataframe(dsp, hide_index=True, use_container_width=True)
        with cb:
            fig_sp = px.bar(sp_df, x="Sport", y="ROI %", color="ROI %",
                color_continuous_scale=["#f87171","#fbbf24","#4ade80"],
                text=sp_df["ROI %"].apply(lambda x: f"{x:+.1f}%"), title="ROI par sport")
            fig_sp.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,.3)")
            fig_sp.update_traces(textposition="outside")
            fig_sp.update_layout(**_chart(height=300, coloraxis_showscale=False))
            st.plotly_chart(fig_sp, use_container_width=True)

    st.divider()

    # ── Heatmap Sport × Jour ──────────────────────────────────────────────────
    section_header("Heatmap Sport × Jour de la semaine",
        "Chaque cellule = win rate (%) pour ce sport ce jour-là. "
        "**Vert** = bon win rate, **Rouge** = mauvais, **Gris** = aucun pari ce jour pour ce sport. "
        "Exemple : si le Basketball le lundi est vert, c'est ton meilleur combo sport/jour.")
    hm = heatmap_sport_day(df_a)
    if not hm.empty:
        fig_hm = go.Figure(go.Heatmap(
            z=hm.values, x=hm.columns.tolist(), y=hm.index.tolist(),
            colorscale=[[0,"#f87171"],[0.5,"#fbbf24"],[1,"#4ade80"]],
            zmin=0, zmax=100,
            text=[[f"{v:.0f}%" if not pd.isna(v) else "" for v in row] for row in hm.values],
            texttemplate="%{text}",
            hovertemplate="<b>%{y}</b> — %{x}<br>Win Rate : %{z:.0f}%<extra></extra>",
            colorbar=dict(title="Win Rate %", ticksuffix="%"),
        ))
        fig_hm.update_layout(**_chart(height=max(250, len(hm)*50+60), title="Win Rate % par sport et jour"))
        st.plotly_chart(fig_hm, use_container_width=True)
    else:
        st.info("Pas assez de données avec des dates pour afficher la heatmap.")

    st.divider()

    # ── Catégorie + Jour côte à côte ──────────────────────────────────────────
    col_t, col_d = st.columns(2)
    with col_t:
        section_header("Par catégorie de pari",
            "**Buteur/Marqueur** = pari sur un joueur qui marque. "
            "**Over/Under** = pari sur le total de points/buts. "
            "**Performance combinée** = pari impliquant plusieurs conditions ('et'). "
            "Identifie les types de paris où tu excelles vraiment.")
        ty = stats_by_type(df_a)
        if not ty.empty:
            fig_ty = px.bar(ty, x="Catégorie", y="ROI %", color="Win Rate %",
                color_continuous_scale=["#f87171","#fbbf24","#4ade80"],
                text=ty["ROI %"].apply(lambda x: f"{x:+.1f}%"),
                title="ROI par catégorie",
                hover_data={"Paris": True, "Gagnés": True, "Bénéfice (€)": True})
            fig_ty.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,.2)")
            fig_ty.update_traces(textposition="outside")
            fig_ty.update_layout(**_chart(height=300, coloraxis_showscale=False,
                                           xaxis=dict(tickangle=-25)))
            st.plotly_chart(fig_ty, use_container_width=True)
            dty = ty[["Catégorie","Paris","Gagnés","Win Rate %","ROI %","Bénéfice (€)"]].copy()
            dty["Win Rate %"] = dty["Win Rate %"].apply(lambda x: f"{x:.0f}%")
            dty["ROI %"]      = dty["ROI %"].apply(lambda x: f"{x:+.1f}%")
            st.dataframe(dty, hide_index=True, use_container_width=True)

    with col_d:
        section_header("Par jour de la semaine",
            "Win rate et ROI selon le jour où tu as parié. "
            "Certains jours sont meilleurs car les compétitions diffèrent "
            "(ex: Champions League mercredi, NBA quotidien, matchs du week-end). "
            "La couleur = ROI, la hauteur = win rate.")
        day_df = stats_by_day(df_a)
        if not day_df.empty:
            fig_day = px.bar(day_df, x="Jour", y="Win Rate %", color="ROI %",
                color_continuous_scale=["#f87171","#fbbf24","#4ade80"],
                text=day_df["Win Rate %"].apply(lambda x: f"{x:.0f}%"),
                title="Win rate & ROI par jour",
                hover_data={"Paris": True, "Bénéfice (€)": True})
            fig_day.update_traces(textposition="outside")
            fig_day.update_layout(**_chart(height=300, coloraxis_showscale=False))
            st.plotly_chart(fig_day, use_container_width=True)
            dday = day_df[["Jour","Paris","Win Rate %","ROI %","Bénéfice (€)"]].copy()
            dday["Win Rate %"] = dday["Win Rate %"].apply(lambda x: f"{x:.0f}%")
            dday["ROI %"]      = dday["ROI %"].apply(lambda x: f"{x:+.1f}%")
            st.dataframe(dday, hide_index=True, use_container_width=True)

    st.divider()

    # ── Créneau horaire ───────────────────────────────────────────────────────
    section_header("Par créneau horaire",
        "**Matin** = 6h-12h, **Après-midi** = 12h-18h, **Soir** = 18h-23h, **Nuit** = 23h-6h. "
        "Montre si tu analyses mieux à certaines heures, ou si les compétitions du soir sont plus prévisibles.")
    hr_df = stats_by_hour(df_a)
    if not hr_df.empty:
        col_h1, col_h2 = st.columns([3, 2])
        with col_h1:
            dhr = hr_df[["Créneau","Paris","Win Rate %","ROI %","Bénéfice (€)"]].copy()
            dhr["Win Rate %"] = dhr["Win Rate %"].apply(lambda x: f"{x:.0f}%")
            dhr["ROI %"]      = dhr["ROI %"].apply(lambda x: f"{x:+.1f}%")
            st.dataframe(dhr, hide_index=True, use_container_width=True)
        with col_h2:
            fig_hr = px.bar(hr_df, x="Créneau", y="Win Rate %", color="ROI %",
                color_continuous_scale=["#f87171","#fbbf24","#4ade80"],
                text=hr_df["Win Rate %"].apply(lambda x: f"{x:.0f}%"),
                title="Win rate par créneau",
                hover_data={"Paris": True, "Bénéfice (€)": True})
            fig_hr.update_traces(textposition="outside")
            fig_hr.update_layout(**_chart(height=260, coloraxis_showscale=False))
            st.plotly_chart(fig_hr, use_container_width=True)
    else:
        st.info("Heures non renseignées pour suffisamment de paris.")

    st.divider()

    # ── Boost + Plage de cote ─────────────────────────────────────────────────
    col_b, col_o = st.columns(2)
    with col_b:
        section_header("Efficacité par tranche de boost",
            "Groupe tes paris selon l'ampleur du boost. "
            "Ex : cote 2.00 → 2.50 = boost +25% → tranche '20-35%'. "
            "Un gros boost ne signifie pas un pari plus facile. "
            "Cette analyse révèle si les gros boosts sont rentables ou du marketing.")
        boost_df = boost_efficiency(df_a)
        if not boost_df.empty:
            boost_df["label"] = boost_df.apply(
                lambda r: f"{r['Win Rate %']:.0f}%\n({int(r['Paris'])} paris)", axis=1)
            fig_boost = px.bar(boost_df, x="Tranche boost", y="Win Rate %", color="ROI %",
                color_continuous_scale=["#f87171","#fbbf24","#4ade80"],
                text="label", title="Win rate par tranche de boost",
                hover_data={"Paris": True, "ROI %": ":.1f", "Bénéfice (€)": True, "label": False})
            fig_boost.update_traces(textposition="outside")
            fig_boost.update_layout(**_chart(height=300, coloraxis_showscale=False))
            st.plotly_chart(fig_boost, use_container_width=True)

    with col_o:
        section_header("Performance par plage de cote boostée",
            "**Barre** = win rate (axe gauche). **Ligne cyan** = ROI (axe droit). "
            "Un bon win rate avec un ROI faible = les gains ne compensent pas les mises. "
            "Cherche les plages avec les deux indicateurs élevés.")
        odds_df = stats_by_odds_range(df_a)
        if not odds_df.empty:
            fig_odds = go.Figure()
            fig_odds.add_trace(go.Bar(x=odds_df["Tranche cote"], y=odds_df["Win Rate %"],
                name="Win Rate %", marker_color="#818cf8",
                text=odds_df["Win Rate %"].apply(lambda x: f"{x:.0f}%"), textposition="outside",
                hovertemplate="%{x}<br>Win Rate : %{y:.0f}%<br>%{customdata} paris<extra></extra>",
                customdata=odds_df["Paris"]))
            fig_odds.add_trace(go.Scatter(x=odds_df["Tranche cote"], y=odds_df["ROI %"],
                name="ROI %", yaxis="y2", mode="lines+markers",
                line=dict(color="#22d3ee", width=2), marker=dict(size=8),
                hovertemplate="%{x}<br>ROI : %{y:.1f}%<extra></extra>"))
            fig_odds.update_layout(**_chart(height=300, title="Win rate & ROI par plage de cote",
                yaxis2=dict(overlaying="y", side="right", title="ROI %", color="#22d3ee", showgrid=False),
                legend=dict(orientation="h", y=1.15)))
            st.plotly_chart(fig_odds, use_container_width=True)

    st.divider()

    # ── Scatter cote vs gain + Distribution des mises ─────────────────────────
    col_sc, col_hist = st.columns([3, 2])
    with col_sc:
        section_header("Cote boostée vs Gain réel",
            "Chaque bulle = un pari. **Taille** = mise. **Vert** = gagné, **Rouge** = perdu. "
            "Idéalement : bulles vertes en haut à droite (grosse cote + gros gain), "
            "rouges en bas à gauche (petite mise perdue).")
        played2 = played.copy()
        played2["Résultat"] = played2["Validé ?"].map({"✅":"Gagné","❌":"Perdu"})
        fig_sc = px.scatter(played2, x="Cote boostée", y="Gain réel", color="Résultat",
            color_discrete_map={"Gagné":"#4ade80","Perdu":"#f87171"},
            size="Misé", size_max=18,
            hover_data=["Événement","Pari","Sport","Date"],
            title="Chaque bulle = un pari (taille = mise)")
        fig_sc.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,.2)")
        fig_sc.update_layout(**_chart(height=340))
        st.plotly_chart(fig_sc, use_container_width=True)

    with col_hist:
        section_header("Distribution des mises",
            "Histogramme de la répartition de tes mises. "
            "Montre si tu mises de façon homogène ou si tu varies beaucoup. "
            "Une gestion de bankroll saine implique des mises régulières et limitées.")
        if "Misé" in played.columns and played["Misé"].notna().any():
            mise_data = played["Misé"].dropna()
            fig_hist = go.Figure(go.Histogram(
                x=mise_data,
                nbinsx=min(15, len(mise_data)),
                marker_color="#818cf8",
                marker_line=dict(color="#1e1b4b", width=1),
                hovertemplate="Mise %{x:.1f} € : <b>%{y} paris</b><extra></extra>",
            ))
            mean_mise = mise_data.mean()
            fig_hist.add_vline(x=mean_mise, line_dash="dash", line_color="#fbbf24",
                               annotation_text=f"Moy. {mean_mise:.1f} €",
                               annotation_font_color="#fbbf24")
            fig_hist.update_layout(**_chart(height=340, title="Répartition des mises (€)",
                                            xaxis_title="Mise (€)", yaxis_title="Nombre de paris"))
            st.plotly_chart(fig_hist, use_container_width=True)

            m1, m2, m3 = st.columns(3)
            with m1: st.metric("Mise min", f"{mise_data.min():.2f} €")
            with m2: st.metric("Mise moy.", f"{mean_mise:.2f} €")
            with m3: st.metric("Mise max", f"{mise_data.max():.2f} €")

    st.divider()

    # ── Palmarès ──────────────────────────────────────────────────────────────
    section_header("Palmarès — Meilleurs & Pires paris",
        "**Top 5 gains** = tes paris les plus rentables (gain net le plus élevé). "
        "**Pires 5** = les paris qui t'ont le plus coûté. "
        "Utile pour identifier les types de paris à répéter (ou éviter).")
    col_top, col_flop = st.columns(2)
    with col_top:
        st.markdown('<p style="color:#4ade80;font-weight:600;margin-bottom:6px">🏆 Top 5 — Meilleurs gains</p>', unsafe_allow_html=True)
        top5 = played.nlargest(5, "Gain réel")[["Date","Sport","Événement","Pari","Cote boostée","Misé","Gain réel","Validé ?"]].copy()
        top5["Date"] = top5["Date"].dt.strftime("%d/%m").fillna("")
        top5["Pari"] = top5["Pari"].apply(lambda x: str(x)[:40])
        st.dataframe(top5, hide_index=True, use_container_width=True,
            column_config={
                "Cote boostée": st.column_config.NumberColumn(format="%.2f"),
                "Misé":         st.column_config.NumberColumn(format="%.2f €"),
                "Gain réel":    st.column_config.NumberColumn(format="%.2f €"),
            })
    with col_flop:
        st.markdown('<p style="color:#f87171;font-weight:600;margin-bottom:6px">💔 Pires 5 — Plus grosses pertes</p>', unsafe_allow_html=True)
        flop5 = played.nsmallest(5, "Gain réel")[["Date","Sport","Événement","Pari","Cote boostée","Misé","Gain réel","Validé ?"]].copy()
        flop5["Date"] = flop5["Date"].dt.strftime("%d/%m").fillna("")
        flop5["Pari"] = flop5["Pari"].apply(lambda x: str(x)[:40])
        st.dataframe(flop5, hide_index=True, use_container_width=True,
            column_config={
                "Cote boostée": st.column_config.NumberColumn(format="%.2f"),
                "Misé":         st.column_config.NumberColumn(format="%.2f €"),
                "Gain réel":    st.column_config.NumberColumn(format="%.2f €"),
            })

    st.divider()

    # ── Comparatif Catalogue vs Mes Paris ─────────────────────────────────────
    section_header("Comparatif Catalogue général vs Mes paris",
        "Compare tes résultats personnels avec l'ensemble du catalogue. "
        "Si ton win rate personnel est supérieur au catalogue, tu as un bon sens de la sélection — "
        "tu choisis mieux que la moyenne des cotes disponibles.")
    stats_cat = compute_stats(df_gen)
    stats_perso = compute_stats(df_me)
    comp_data = {
        "Source":      ["Catalogue général", "Mes paris"],
        "Paris":       [stats_cat["total"], stats_perso["total"]],
        "Win Rate %":  [round(stats_cat["win_rate"]*100,1), round(stats_perso["win_rate"]*100,1)],
        "ROI %":       [round(stats_cat["roi"]*100,1), round(stats_perso["roi"]*100,1)],
        "Bénéfice (€)":[stats_cat["benefice"], stats_perso["benefice"]],
        "EV moyen":    [stats_cat["ev_moyen"], stats_perso["ev_moyen"]],
    }
    comp_df = pd.DataFrame(comp_data)
    cc1, cc2, cc3 = st.columns(3)
    metrics_comp = [
        ("Win Rate %",   "%",  True),
        ("ROI %",        "%",  True),
        ("Bénéfice (€)", "€",  True),
    ]
    for col, (metric, unit, higher_better) in zip([cc1, cc2, cc3], metrics_comp):
        with col:
            v_cat   = comp_df.loc[comp_df["Source"]=="Catalogue général", metric].values[0]
            v_perso = comp_df.loc[comp_df["Source"]=="Mes paris", metric].values[0]
            delta   = v_perso - v_cat
            delta_str = f"{delta:+.1f}{unit}"
            st.metric(f"📋 {metric}", f"{v_cat:.1f}{unit}")
            st.metric(f"👤 {metric}", f"{v_perso:.1f}{unit}",
                       delta=delta_str,
                       delta_color="normal" if higher_better else "inverse",
                       help=f"Delta = Mes paris − Catalogue. Positif = tu sélectionnes mieux que le catalogue.")

    fig_comp = go.Figure()
    for i, row in comp_df.iterrows():
        color = "#818cf8" if "Catalogue" in row["Source"] else "#22d3ee"
        fig_comp.add_trace(go.Bar(
            name=row["Source"],
            x=["Win Rate %", "ROI %"],
            y=[row["Win Rate %"], row["ROI %"]],
            marker_color=color,
            text=[f"{row['Win Rate %']:.1f}%", f"{row['ROI %']:+.1f}%"],
            textposition="outside",
        ))
    fig_comp.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,.2)")
    fig_comp.update_layout(**_chart(height=280, barmode="group",
                                     title="Catalogue vs Mes paris",
                                     legend=dict(orientation="h", y=1.12)))
    st.plotly_chart(fig_comp, use_container_width=True)

    st.divider()

    # ── Simulation Kelly ──────────────────────────────────────────────────────
    section_header("Simulation : Kelly vs mise réelle",
        "Simule ce qu'aurait été ta bankroll en appliquant le **critère de Kelly fractionnel** "
        "depuis le début. Kelly calcule la mise optimale selon le win rate historique par sport. "
        "**Kelly/2** = version conservatrice qui limite le risque de ruine. "
        f"Bankroll initiale simulée : {bankroll:.0f} €.")
    sim_df = simulate_kelly_bankroll(df_a, initial_bankroll=bankroll)
    if not sim_df.empty:
        fig_sim = go.Figure()
        fig_sim.add_trace(go.Scatter(x=sim_df["N"], y=sim_df["Bankroll réelle"],
            mode="lines", line=dict(color="#22d3ee", width=2), name="Mise réelle",
            hovertemplate="Pari #%{x}<br>Bankroll réelle : %{y:.2f} €<extra></extra>"))
        fig_sim.add_trace(go.Scatter(x=sim_df["N"], y=sim_df["Bankroll Kelly"],
            mode="lines", line=dict(color="#fbbf24", width=2, dash="dash"), name="Kelly /2 (simulé)",
            hovertemplate="Pari #%{x}<br>Kelly simulé : %{y:.2f} €<extra></extra>"))
        fig_sim.add_hline(y=bankroll, line_dash="dot", line_color="rgba(255,255,255,.2)",
                           annotation_text=f"Bankroll initiale ({bankroll:.0f}€)")
        fig_sim.update_layout(**_chart(height=300, title="Évolution de bankroll : Réel vs Kelly",
                                        legend=dict(orientation="h", y=1.12)))
        st.plotly_chart(fig_sim, use_container_width=True)

    # ── Kelly par sport ───────────────────────────────────────────────────────
    section_header("Critère de Kelly par sport",
        "**Kelly %** = fraction théorique optimale de la bankroll à miser. "
        "**Kelly /2 %** = version fractionnelle recommandée (réduit le risque de ruine). "
        f"**Mise suggérée** = montant pour une bankroll de {bankroll:.0f} €. "
        "Kelly négatif ou nul = ne pas miser sur ce sport selon l'historique.")
    kelly_df = kelly_by_sport(df_a, bankroll=bankroll)
    if not kelly_df.empty:
        st.caption(f"Bankroll : **{bankroll:.0f} €** — modifiable dans la sidebar.")
        st.dataframe(kelly_df, hide_index=True, use_container_width=True,
            column_config={
                f"Mise suggérée ({bankroll:.0f}€)": st.column_config.NumberColumn(format="%.2f €"),
            })
    else:
        st.info("Minimum 3 paris par sport requis pour calculer Kelly.")


# ══════════════════════════════════════════════════════════════════════════════
# RECOMMANDATIONS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "💡 Recommandations":
    st.markdown("# 💡 Recommandations")

    # Sélecteur source propre à la page
    col_rsrc, _ = st.columns([4, 4])
    with col_rsrc:
        rec_src = st.radio(
            "Analyser :",
            ["📋 Catalogue général", "👤 Mes paris (Maxime)"],
            horizontal=True,
            key="rec_source",
            help="Choisis la source pour générer les recommandations.",
        )
    df_rec = df_gen if "Catalogue" in rec_src else df_me
    st.caption("Recommandations générées à partir de tes données réelles uniquement, sans modèle externe.")
    st.divider()

    recs = generate_recommendations(df_rec)
    order = {"danger": 0, "warning": 1, "success": 2, "info": 3}
    for r in sorted(recs, key=lambda r: order.get(r["level"], 4)):
        st.markdown(rec_card(r["level"], r["text"]), unsafe_allow_html=True)

    st.divider()

    # ── Résumé stats + Gauge ──────────────────────────────────────────────────
    section_header("Résumé statistique",
        "Vue d'ensemble des métriques clés pour la source sélectionnée.")
    stats_r = compute_stats(df_rec)
    s_r     = streak_stats(df_rec)

    rc1, rc2, rc3, rc4 = st.columns(4)
    with rc1:
        st.metric("Paris joués", stats_r["total"],
                   help="Nombre de paris terminés (gagnés ou perdus).")
        st.metric("En attente", stats_r["pending"],
                   help="Paris dont le résultat n'a pas encore été saisi.")
    with rc2:
        st.metric("Win Rate", f"{stats_r['win_rate']*100:.1f}%",
                   help="% de paris gagnés. 50% = équilibre théorique.")
        st.metric("ROI", f"{stats_r['roi']*100:.1f}%",
                   help="Retour sur investissement = Bénéfice / Total misé × 100.")
    with rc3:
        st.metric("Bénéfice cumulé", f"{stats_r['benefice']:+.2f} €",
                   help="Gains nets totaux depuis le premier pari.")
        st.metric("EV moyen", f"{stats_r['ev_moyen']:+.3f}",
                   help="Espérance de valeur : p × cote - 1. Positif = avantage mathématique.")
    with rc4:
        st.metric("Meilleure série victoires", f"{s_r['best_win']} consécutives",
                   help="Plus longue série de victoires d'affilée.")
        st.metric("Plus longue série défaites", f"{s_r['best_loss']} consécutives",
                   help="Plus longue série de défaites. Signal pour réduire les mises.")

    st.divider()

    # Gauge win rate
    rcol1, rcol2 = st.columns([1, 1])
    with rcol1:
        wr_r = stats_r["win_rate"] * 100
        fig_g = go.Figure(go.Indicator(
            mode="gauge+number+delta", value=wr_r,
            delta={"reference": 50, "valueformat": ".1f", "suffix": "%"},
            number={"suffix": "%", "font": {"size": 36, "color": "#e2e8f0"}},
            gauge={
                "axis": {"range": [0, 100], "tickcolor": "#475569"},
                "bar":  {"color": "#818cf8", "thickness": .3},
                "bgcolor": "rgba(0,0,0,0)", "borderwidth": 0,
                "steps": [
                    {"range": [0, 33],   "color": "rgba(248,113,113,.15)"},
                    {"range": [33, 50],  "color": "rgba(251,191,36,.15)"},
                    {"range": [50, 100], "color": "rgba(74,222,128,.15)"},
                ],
                "threshold": {"line": {"color": "#fbbf24", "width": 3}, "value": 50},
            },
            title={"text": "Win Rate global", "font": {"color": "#94a3b8", "size": 14}},
        ))
        fig_g.update_layout(**_chart(height=260))
        with st.popover("ℹ️ Comment lire cette jauge ?"):
            st.markdown("""
- **0–33%** 🔴 Win rate très faible.
- **33–50%** 🟡 En dessous de l'équilibre théorique.
- **50%+** 🟢 Tu gagnes plus souvent que tu ne perds.

Le triangle jaune à 50% est le seuil d'équilibre. Avec des cotes >2.0, tu peux être rentable même sous 50%.
""")
        st.plotly_chart(fig_g, use_container_width=True)

    with rcol2:
        # Tendances 7j vs 30j
        section_header("Tendances récentes",
            "Compare tes performances récentes au global. "
            "Delta positif (vert) = tu t'améliores. Delta négatif (rouge) = attention.")
        tr7  = trend_stats(df_rec, 7)
        tr30 = trend_stats(df_rec, 30)
        trend_rows = [
            ("Win Rate 7j",  f"{tr7['win_rate']*100:.1f}%",  f"{(tr7['win_rate']-stats_r['win_rate'])*100:+.1f}%"),
            ("Win Rate 30j", f"{tr30['win_rate']*100:.1f}%", f"{(tr30['win_rate']-stats_r['win_rate'])*100:+.1f}%"),
            ("ROI 7j",       f"{tr7['roi']*100:.1f}%",       f"{(tr7['roi']-stats_r['roi'])*100:+.1f}%"),
            ("ROI 30j",      f"{tr30['roi']*100:.1f}%",      f"{(tr30['roi']-stats_r['roi'])*100:+.1f}%"),
        ]
        t1, t2 = st.columns(2)
        for i, (label, val, delta) in enumerate(trend_rows):
            with (t1 if i % 2 == 0 else t2):
                st.metric(label, val, delta=delta,
                           help=f"Valeur sur les derniers {label[-2:]} jours. Delta vs moyenne globale.")
