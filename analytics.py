import pandas as pd
import numpy as np


# ── Helpers ───────────────────────────────────────────────────────────────────

def _benefice(g: pd.DataFrame) -> float:
    gains     = g.loc[g["Validé ?"] == "✅", "Gains possible"].sum()
    mise_wins = g.loc[g["Validé ?"] == "✅", "Misé"].sum()
    mise_lost = g.loc[g["Validé ?"] == "❌", "Misé"].sum()
    return round(float(gains - mise_wins - mise_lost), 2)


def _roi(g: pd.DataFrame) -> float:
    mise = g["Misé"].sum()
    return _benefice(g) / mise if mise > 0 else 0.0


def _win_rate(g: pd.DataFrame) -> float:
    played = g[g["Validé ?"].isin(["✅", "❌"])]
    if played.empty:
        return 0.0
    return (played["Validé ?"] == "✅").sum() / len(played)


# ── Global KPIs ───────────────────────────────────────────────────────────────

def compute_stats(df: pd.DataFrame) -> dict:
    played = df[df["Validé ?"].isin(["✅", "❌"])]
    wins    = int((played["Validé ?"] == "✅").sum())
    losses  = int((played["Validé ?"] == "❌").sum())
    total   = wins + losses
    pending = int((df["Validé ?"] == "?").sum())

    win_rate   = wins / total if total > 0 else 0.0
    total_mise = float(played["Misé"].sum()) if not played.empty else 0.0
    benefice   = _benefice(played)
    roi        = benefice / total_mise if total_mise > 0 else 0.0

    avg_boost_pct = float(
        ((df["Cote boostée"] - df["Cote initiale"]) / df["Cote initiale"] * 100)
        .replace([np.inf, -np.inf], np.nan).mean()
    ) if not df.empty else 0.0

    avg_cote = float(df["Cote boostée"].mean()) if not df.empty else 0.0
    ev_moyen = (win_rate * avg_cote - 1) if avg_cote > 0 else 0.0

    streak_val, streak_type = _current_streak(played)

    return {
        "wins": wins, "losses": losses, "total": total, "pending": pending,
        "win_rate": win_rate,
        "benefice": round(benefice, 2),
        "roi": roi,
        "total_mise": round(total_mise, 2),
        "avg_boost_pct": round(avg_boost_pct, 1),
        "avg_cote": round(avg_cote, 2),
        "ev_moyen": round(ev_moyen, 3),
        "streak_val": streak_val,
        "streak_type": streak_type,
    }


# ── Streaks ───────────────────────────────────────────────────────────────────

def _current_streak(played: pd.DataFrame):
    if played.empty:
        return 0, "N/A"
    results = played["Validé ?"].tolist()
    last    = results[-1]
    count   = sum(1 for _ in (r for r in reversed(results) if r == last)
                  for _ in [None] if True)
    # simpler loop:
    count = 0
    for r in reversed(results):
        if r == last:
            count += 1
        else:
            break
    return count, "✅" if last == "✅" else "❌"


def streak_stats(df: pd.DataFrame) -> dict:
    played = df[df["Validé ?"].isin(["✅", "❌"])].copy()
    if played.empty:
        return {"current_val": 0, "current_type": "—", "best_win": 0, "best_loss": 0}

    results   = played["Validé ?"].tolist()
    best_win  = best_loss = cur_win = cur_loss = 0
    for r in results:
        if r == "✅":
            cur_win  += 1
            cur_loss  = 0
        else:
            cur_loss += 1
            cur_win   = 0
        best_win  = max(best_win,  cur_win)
        best_loss = max(best_loss, cur_loss)

    cv, ct = _current_streak(played)
    return {"current_val": cv, "current_type": ct, "best_win": best_win, "best_loss": best_loss}


# ── Trend: last N days ────────────────────────────────────────────────────────

def trend_stats(df: pd.DataFrame, days: int) -> dict:
    """Stats for the last `days` days among played bets."""
    played = df[df["Validé ?"].isin(["✅", "❌"])].copy()
    if played.empty or played["Date"].isna().all():
        return compute_stats(pd.DataFrame(columns=df.columns))
    cutoff = played["Date"].max() - pd.Timedelta(days=days)
    recent = played[played["Date"] >= cutoff]
    return compute_stats(recent)


# ── By sport ──────────────────────────────────────────────────────────────────

def stats_by_sport(df: pd.DataFrame) -> pd.DataFrame:
    played = df[df["Validé ?"].isin(["✅", "❌"])].copy()
    if played.empty:
        return pd.DataFrame()

    def agg(g):
        wins      = (g["Validé ?"] == "✅").sum()
        total     = len(g)
        avg_boost = ((g["Cote boostée"] - g["Cote initiale"]) / g["Cote initiale"] * 100).mean()
        return pd.Series({
            "Paris":        total,
            "Gagnés":       int(wins),
            "Win Rate %":   wins / total * 100,
            "Bénéfice (€)": _benefice(g),
            "ROI %":        _roi(g) * 100,
            "Cote moy.":    round(float(g["Cote boostée"].mean()), 2),
            "Boost moy. %": round(float(avg_boost), 1),
            "Misé (€)":     round(float(g["Misé"].sum()), 2),
        })

    result = played.groupby("Sport").apply(agg).reset_index()
    return result.sort_values("ROI %", ascending=False)


# ── By bet category ───────────────────────────────────────────────────────────

_CATEGORIES = [
    ("Buteur / Marqueur",    ["buteur", "marque", "but"]),
    ("Résultat / Victoire",  ["gagne", "victoire", "winner", "remporte"]),
    ("Points / Score",       ["points", "pts", "score"]),
    ("Sets / Jeux",          ["jeux", "sets", "set"]),
    ("Passes décisives",     ["passe", "assist"]),
    ("Over / Under",         ["plus de", "moins de", "over", "under", "au moins"]),
    ("Podium",               ["podium"]),
    ("Performance combinée", ["et ", "+"]),
]

def _categorize(pari: str) -> str:
    p = str(pari).lower()
    for name, kws in _CATEGORIES:
        if any(k in p for k in kws):
            return name
    return "Autre"


def stats_by_type(df: pd.DataFrame) -> pd.DataFrame:
    played = df[df["Validé ?"].isin(["✅", "❌"])].copy()
    if played.empty:
        return pd.DataFrame()
    played["Catégorie"] = played["Pari"].apply(_categorize)

    def agg(g):
        wins  = (g["Validé ?"] == "✅").sum()
        total = len(g)
        return pd.Series({
            "Paris":        total,
            "Gagnés":       int(wins),
            "Win Rate %":   wins / total * 100,
            "Bénéfice (€)": _benefice(g),
            "ROI %":        _roi(g) * 100,
        })

    return played.groupby("Catégorie").apply(agg).reset_index().sort_values("ROI %", ascending=False)


# ── By day of week ────────────────────────────────────────────────────────────

_DAYS_FR = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]

def stats_by_day(df: pd.DataFrame) -> pd.DataFrame:
    played = df[df["Validé ?"].isin(["✅", "❌"])].copy()
    if played.empty or played["Date"].isna().all():
        return pd.DataFrame()
    played["Jour"]     = played["Date"].dt.dayofweek.map(lambda x: _DAYS_FR[x])
    played["Jour_num"] = played["Date"].dt.dayofweek

    def agg(g):
        wins  = (g["Validé ?"] == "✅").sum()
        total = len(g)
        return pd.Series({
            "Paris":        total,
            "Win Rate %":   wins / total * 100,
            "Bénéfice (€)": _benefice(g),
            "ROI %":        _roi(g) * 100,
            "_order":       g["Jour_num"].iloc[0],
        })

    result = played.groupby("Jour").apply(agg).reset_index()
    return result.sort_values("_order").drop(columns="_order")


# ── By hour slot ──────────────────────────────────────────────────────────────

def stats_by_hour(df: pd.DataFrame) -> pd.DataFrame:
    """Group by time-of-day slot (Matin/Après-midi/Soir/Nuit)."""
    played = df[df["Validé ?"].isin(["✅", "❌"])].copy()
    if played.empty:
        return pd.DataFrame()

    def parse_hour(h):
        if pd.isna(h) or str(h).strip() in ("", "None"):
            return None
        try:
            if hasattr(h, "hour"):
                return h.hour
            parts = str(h).replace("h", ":").split(":")
            return int(parts[0])
        except Exception:
            return None

    played["_hour"] = played["Heure"].apply(parse_hour)
    played = played.dropna(subset=["_hour"])
    if played.empty:
        return pd.DataFrame()

    def slot(h):
        h = int(h)
        if 6  <= h < 12: return "Matin (6h-12h)"
        if 12 <= h < 18: return "Après-midi (12h-18h)"
        if 18 <= h < 23: return "Soir (18h-23h)"
        return "Nuit (23h-6h)"

    _ORDER = {"Matin (6h-12h)": 0, "Après-midi (12h-18h)": 1, "Soir (18h-23h)": 2, "Nuit (23h-6h)": 3}
    played["Créneau"] = played["_hour"].apply(slot)

    def agg(g):
        wins  = (g["Validé ?"] == "✅").sum()
        total = len(g)
        return pd.Series({
            "Paris":        total,
            "Win Rate %":   wins / total * 100,
            "Bénéfice (€)": _benefice(g),
            "ROI %":        _roi(g) * 100,
            "_order":       _ORDER.get(g.name, 9),
        })

    result = played.groupby("Créneau").apply(agg).reset_index()
    return result.sort_values("_order").drop(columns="_order")


# ── Heatmap Sport × Jour ──────────────────────────────────────────────────────

def heatmap_sport_day(df: pd.DataFrame) -> pd.DataFrame:
    """Returns pivot table: rows=Sport, cols=Jour, values=Win Rate %."""
    played = df[df["Validé ?"].isin(["✅", "❌"])].copy()
    if played.empty or played["Date"].isna().all():
        return pd.DataFrame()
    played["Jour"] = played["Date"].dt.dayofweek.map(lambda x: _DAYS_FR[x])

    pivot = played.groupby(["Sport", "Jour"]).apply(
        lambda g: round((g["Validé ?"] == "✅").sum() / len(g) * 100, 0)
    ).unstack("Jour")

    # Reorder columns to Mon→Sun
    present = [d for d in _DAYS_FR if d in pivot.columns]
    pivot   = pivot[present]
    return pivot


# ── Boost efficiency ──────────────────────────────────────────────────────────

def boost_efficiency(df: pd.DataFrame) -> pd.DataFrame:
    played = df[df["Validé ?"].isin(["✅", "❌"])].copy()
    if played.empty:
        return pd.DataFrame()
    played["Boost %"] = ((played["Cote boostée"] - played["Cote initiale"]) / played["Cote initiale"] * 100).round(1)
    played["Tranche boost"] = pd.cut(
        played["Boost %"],
        bins=[0, 10, 20, 35, 60, 200],
        labels=["0-10%", "10-20%", "20-35%", "35-60%", ">60%"],
    )

    def agg(g):
        wins  = (g["Validé ?"] == "✅").sum()
        total = len(g)
        return pd.Series({
            "Paris":        total,
            "Win Rate %":   wins / total * 100,
            "ROI %":        _roi(g) * 100,
            "Bénéfice (€)": _benefice(g),
        })

    return played.groupby("Tranche boost", observed=True).apply(agg).reset_index()


# ── Odds range ────────────────────────────────────────────────────────────────

def stats_by_odds_range(df: pd.DataFrame) -> pd.DataFrame:
    played = df[df["Validé ?"].isin(["✅", "❌"])].copy()
    if played.empty:
        return pd.DataFrame()
    played["Tranche cote"] = pd.cut(
        played["Cote boostée"],
        bins=[1, 1.5, 2, 2.5, 3, 4, 20],
        labels=["1.0-1.5", "1.5-2.0", "2.0-2.5", "2.5-3.0", "3.0-4.0", ">4.0"],
    )

    def agg(g):
        wins  = (g["Validé ?"] == "✅").sum()
        total = len(g)
        ev    = (wins / total) * g["Cote boostée"].mean() - 1 if total > 0 else 0
        return pd.Series({
            "Paris":        total,
            "Win Rate %":   wins / total * 100,
            "ROI %":        _roi(g) * 100,
            "EV moyen":     round(float(ev), 3),
        })

    return played.groupby("Tranche cote", observed=True).apply(agg).reset_index()


# ── Kelly criterion ───────────────────────────────────────────────────────────

def kelly_by_sport(df: pd.DataFrame, bankroll: float = 100.0) -> pd.DataFrame:
    played = df[df["Validé ?"].isin(["✅", "❌"])].copy()
    if played.empty:
        return pd.DataFrame()

    rows = []
    for sport, g in played.groupby("Sport"):
        if len(g) < 3:
            continue
        wins  = (g["Validé ?"] == "✅").sum()
        total = len(g)
        p     = wins / total
        q     = 1 - p
        b     = g["Cote boostée"].mean() - 1
        kelly = (p * b - q) / b if b > 0 else 0
        kelly_half    = max(kelly / 2, 0)
        mise_suggeree = round(bankroll * kelly_half, 2)
        rows.append({
            "Sport":       sport,
            "Paris":       total,
            "Win Rate %":  round(p * 100, 1),
            "Kelly %":     round(kelly * 100, 1),
            "Kelly /2 %":  round(kelly_half * 100, 1),
            f"Mise suggérée ({bankroll:.0f}€)": mise_suggeree,
        })

    result = pd.DataFrame(rows)
    return result.sort_values("Kelly /2 %", ascending=False) if not result.empty else result


# ── Kelly bankroll simulation ─────────────────────────────────────────────────

def simulate_kelly_bankroll(df: pd.DataFrame, initial_bankroll: float = 100.0) -> pd.DataFrame:
    """Simulate what the bankroll would have been using fractional Kelly (per-bet)."""
    played = df[df["Validé ?"].isin(["✅", "❌"])].reset_index(drop=True).copy()
    if played.empty:
        return pd.DataFrame()

    bankroll_kelly  = initial_bankroll
    bankroll_actual = initial_bankroll
    rows = []

    for i, row in played.iterrows():
        cote = row["Cote boostée"]
        b    = cote - 1

        # Estimate win prob: use sport-level win rate from data up to this point
        prev = played.iloc[:i]
        sport_prev = prev[prev["Sport"] == row["Sport"]]
        if len(sport_prev) >= 2:
            p = (sport_prev["Validé ?"] == "✅").sum() / len(sport_prev)
        else:
            p = (prev["Validé ?"] == "✅").sum() / len(prev) if len(prev) > 0 else 0.4

        q     = 1 - p
        kelly = max((p * b - q) / b, 0) / 2 if b > 0 else 0
        mise_kelly = round(bankroll_kelly * kelly, 2)

        won = row["Validé ?"] == "✅"
        if won:
            bankroll_kelly  += mise_kelly * b
        else:
            bankroll_kelly  -= mise_kelly
        bankroll_kelly = max(bankroll_kelly, 0)

        # Actual bankroll
        bankroll_actual += row["Gain réel"]

        rows.append({
            "N":               i + 1,
            "Bankroll Kelly":  round(bankroll_kelly, 2),
            "Bankroll réelle": round(bankroll_actual, 2),
            "Résultat":        "✅" if won else "❌",
        })

    return pd.DataFrame(rows)


# ── Recommendations ───────────────────────────────────────────────────────────

def generate_recommendations(df: pd.DataFrame) -> list[dict]:
    recs   = []
    played = df[df["Validé ?"].isin(["✅", "❌"])]
    if len(played) < 5:
        return [{"level": "info", "text": "Ajoute au moins 5 paris pour débloquer les recommandations."}]

    stats = compute_stats(df)
    s     = streak_stats(df)

    if s["current_val"] >= 3 and s["current_type"] == "❌":
        recs.append({"level": "danger",  "text": f"🔥 Série de **{s['current_val']} défaites** consécutives. Pause recommandée ou réduction de mise."})
    elif s["current_val"] >= 3 and s["current_type"] == "✅":
        recs.append({"level": "success", "text": f"🚀 Série de **{s['current_val']} victoires** ! Reste discipliné, ne surexpose pas ta bankroll."})

    by_sport = stats_by_sport(df)
    if not by_sport.empty:
        filtered = by_sport[by_sport["Paris"] >= 3]
        if not filtered.empty:
            best  = filtered.sort_values("ROI %", ascending=False).iloc[0]
            worst = filtered.sort_values("ROI %").iloc[0]
            recs.append({"level": "success", "text": f"✅ Meilleur sport : **{best['Sport']}** — {best['Win Rate %']:.0f}% win rate, ROI {best['ROI %']:.1f}%."})
            if float(worst["ROI %"]) < -15:
                recs.append({"level": "warning", "text": f"⚠️ **{worst['Sport']}** est négatif ({worst['ROI %']:.1f}% ROI). Évite ou réduis les mises."})

    combos  = played[played["Pari"].str.count(" et ") >= 1]
    simples = played[played["Pari"].str.count(" et ") == 0]
    if len(combos) >= 3 and len(simples) >= 3:
        wr_c = (combos["Validé ?"]  == "✅").mean() * 100
        wr_s = (simples["Validé ?"] == "✅").mean() * 100
        if wr_c < wr_s - 10:
            recs.append({"level": "warning", "text": f"🔗 Combos : {wr_c:.0f}% vs simples : {wr_s:.0f}%. Préfère les paris simples."})
        else:
            recs.append({"level": "info",    "text": f"🔗 Tes combos ({wr_c:.0f}%) performent comme tes simples ({wr_s:.0f}%)."})

    odds_df = stats_by_odds_range(df)
    if not odds_df.empty:
        best_range = odds_df[odds_df["Paris"] >= 3].sort_values("ROI %", ascending=False)
        if not best_range.empty:
            br = best_range.iloc[0]
            recs.append({"level": "info", "text": f"💡 Plage de cotes la plus rentable : **{br['Tranche cote']}** (ROI {br['ROI %']:.1f}%, {br['Win Rate %']:.0f}% win rate)."})

    if stats["ev_moyen"] > 0:
        recs.append({"level": "success", "text": f"📊 EV moyen positif : **{stats['ev_moyen']:+.3f}** — avantage mathématique sur tes paris."})
    elif stats["ev_moyen"] < -0.05:
        recs.append({"level": "warning", "text": f"📊 EV moyen négatif ({stats['ev_moyen']:+.3f}). Concentre-toi sur les sports à fort win rate historique."})

    by_type = stats_by_type(df)
    if not by_type.empty:
        best_type = by_type[by_type["Paris"] >= 3].sort_values("ROI %", ascending=False)
        if not best_type.empty:
            bt = best_type.iloc[0]
            recs.append({"level": "info", "text": f"📌 Catégorie la plus rentable : **{bt['Catégorie']}** (ROI {bt['ROI %']:.1f}%, {bt['Gagnés']}/{bt['Paris']} gagnés)."})

    by_day = stats_by_day(df)
    if not by_day.empty:
        best_day = by_day[by_day["Paris"] >= 3].sort_values("ROI %", ascending=False)
        if not best_day.empty:
            bd = best_day.iloc[0]
            recs.append({"level": "info", "text": f"📅 Meilleur jour : **{bd['Jour']}** (ROI {bd['ROI %']:.1f}%, {bd['Win Rate %']:.0f}% win rate)."})

    by_hour = stats_by_hour(df)
    if not by_hour.empty:
        best_hour = by_hour[by_hour["Paris"] >= 3].sort_values("ROI %", ascending=False)
        if not best_hour.empty:
            bh = best_hour.iloc[0]
            recs.append({"level": "info", "text": f"🕐 Meilleur créneau : **{bh['Créneau']}** (ROI {bh['ROI %']:.1f}%, {bh['Win Rate %']:.0f}% win rate)."})

    if not recs:
        recs.append({"level": "info", "text": "Continue à alimenter tes données pour des recommandations plus précises."})
    return recs


# ── Pending bets analysis ─────────────────────────────────────────────────────

def analyse_pending(df: pd.DataFrame) -> pd.DataFrame:
    """For each pending bet, estimate EV using sport-level historical win rate."""
    pending = df[df["Validé ?"] == "?"].copy()
    if pending.empty:
        return pd.DataFrame()

    played = df[df["Validé ?"].isin(["✅", "❌"])]
    global_wr  = float((played["Validé ?"] == "✅").mean()) if not played.empty else 0.40
    global_n   = len(played)

    rows = []
    for _, row in pending.iterrows():
        sport        = row["Sport"]
        sport_played = played[played["Sport"] == sport]
        n_sport      = len(sport_played)

        if n_sport >= 3:
            wr      = float((sport_played["Validé ?"] == "✅").mean())
            wr_src  = f"{sport} ({n_sport} paris)"
        elif global_n > 0:
            wr      = global_wr
            wr_src  = f"Global ({global_n} paris)"
        else:
            wr      = 0.40
            wr_src  = "Estimation (données insuffisantes)"

        cote       = float(row["Cote boostée"])
        mise       = float(row["Misé"])
        ev         = round(wr * cote - 1, 3)
        gain       = round(mise * (cote - 1), 2)
        esperance  = round(mise * ev, 2)

        rows.append({
            "Date":               row["Date"],
            "Sport":              sport,
            "Événement":          row["Événement"],
            "Pari":               str(row["Pari"])[:60],
            "Cote":               cote,
            "Mise (€)":           mise,
            "Gain si ✅ (€)":     gain,
            "Win Rate sport %":   round(wr * 100, 1),
            "EV estimé":          ev,
            "Espérance (€)":      esperance,
            "_wr_src":            wr_src,
        })

    return pd.DataFrame(rows)


# ── Rolling win rate ──────────────────────────────────────────────────────────

def rolling_win_rate(df: pd.DataFrame, window: int = 5) -> pd.DataFrame:
    """Rolling win rate over the last `window` bets + global expanding mean."""
    played = df[df["Validé ?"].isin(["✅", "❌"])].reset_index(drop=True).copy()
    if len(played) < window:
        return pd.DataFrame()
    played["N"]   = range(1, len(played) + 1)
    played["Won"] = (played["Validé ?"] == "✅").astype(int)
    col_roll = f"Win Rate roulant ({window} paris) %"
    played[col_roll]             = (played["Won"].rolling(window, min_periods=window).mean() * 100).round(1)
    played["Win Rate global %"]  = (played["Won"].expanding().mean() * 100).round(1)
    return played[["N", col_roll, "Win Rate global %"]].dropna(subset=[col_roll])
