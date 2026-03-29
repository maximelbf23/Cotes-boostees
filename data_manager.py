import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, date

SHEET_GENERAL = "Cotes Boostées"
SHEET_PERSO = "Maxime"

COLUMNS = ["Date", "Heure", "Sport", "Événement", "Pari",
           "Cote initiale", "Cote boostée", "Validé ?",
           "Misé", "Gains possible", "Gain réel", "Bénéfice cumulé"]

@st.cache_resource
def get_gspread_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    google_secrets = dict(st.secrets["google"])
    # Handle private key formatting issue
    if "\\n" in google_secrets["private_key"]:
        google_secrets["private_key"] = google_secrets["private_key"].replace("\\n", "\n")
    
    credentials = Credentials.from_service_account_info(
        google_secrets,
        scopes=scopes
    )
    return gspread.authorize(credentials)


def get_worksheet(sheet_name: str):
    client = get_gspread_client()
    url = st.secrets["app"]["spreadsheet_url"]
    sh = client.open_by_url(url)
    return sh.worksheet(sheet_name)


def _empty_df():
    """Return an empty DataFrame with proper dtypes so .dt accessors work."""
    df = pd.DataFrame(columns=COLUMNS)
    df["Date"] = pd.to_datetime(df["Date"])
    return df


def load_sheet(sheet_name: str) -> pd.DataFrame:
    try:
        ws = get_worksheet(sheet_name)
        data_rows = ws.get_all_values()
    except Exception as e:
        import traceback
        print(f"Error loading {sheet_name}: {type(e).__name__}: {e}")
        traceback.print_exc()
        return _empty_df()

    if not data_rows or len(data_rows) == 1: # Empty or header only
        return _empty_df()
    
    # Remove header
    data_rows = data_rows[1:]
    
    # Pad or truncate rows to exactly len(COLUMNS) columns
    # We only care about the first 12 columns anyway
    max_cols = 12
    cleaned_rows = []
    for row in data_rows:
        vals = row[:max_cols]
        while len(vals) < max_cols:
            vals.append(None)
        
        # Determine if row is completely empty (first 5 cols)
        if not any(val for val in vals[:5] if val and str(val).strip()):
            continue
            
        cleaned_rows.append(vals)

    if not cleaned_rows:
        return _empty_df()

    df = pd.DataFrame(cleaned_rows, columns=COLUMNS)

    # Clean types: Google Sheets returns strings
    # Convert empty strings to NaNs
    df.replace("", pd.NA, inplace=True)
    
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    
    # Clean numeric columns: strip currency symbols, spaces, replace comma decimal
    def _clean_numeric(series):
        s = series.astype(str)
        s = s.str.replace("€", "", regex=False)
        s = s.str.replace("\u00a0", "", regex=False)  # non-breaking space
        s = s.str.strip()
        s = s.str.replace(",", ".", regex=False)
        s = s.replace({"nan": pd.NA, "<NA>": pd.NA, "None": pd.NA, "": pd.NA})
        return pd.to_numeric(s, errors="coerce")

    for col in ["Cote initiale", "Cote boostée", "Misé"]:
        df[col] = _clean_numeric(df[col])

    # Recompute derived columns from scratch
    df["Gains possible"] = (df["Misé"] * df["Cote boostée"]).round(2)
    df["Gain réel"] = df.apply(_compute_gain_reel, axis=1)
    df["Bénéfice cumulé"] = df["Gain réel"].cumsum().round(2)

    df = df.dropna(subset=["Événement", "Pari"], how="all")
    df = df.reset_index(drop=True)
    return df


def _compute_gain_reel(row):
    status = str(row["Validé ?"]).strip()
    try:
        mise = float(row["Misé"]) if pd.notna(row["Misé"]) else 0.0
        gains = float(row["Gains possible"]) if pd.notna(row["Gains possible"]) else 0.0
    except ValueError:
        mise = 0.0
        gains = 0.0

    if status == "✅":
        return round(gains - mise, 2)
    elif status == "❌":
        return round(-mise, 2)
    return 0.0


def save_bet(sheet_name: str, bet: dict):
    def _safe_float(val, default=0.0):
        try:
            if pd.isna(val):
                return default
            return float(str(val).replace(",", ".").replace("€", "").strip())
        except (ValueError, TypeError):
            return default

    def _safe_str(val, default=""):
        try:
            if pd.isna(val):
                return default
            return str(val).strip()
        except (ValueError, TypeError):
            return default

    try:
        ws = get_worksheet(sheet_name)
        
        mise = _safe_float(bet.get("Misé", 0))
        cote_b = _safe_float(bet.get("Cote boostée", 0))
        gains_possible = round(mise * cote_b, 2)
        status = _safe_str(bet.get("Validé ?", "?"), "?")
        
        if status == "✅":
            gain_reel = round(gains_possible - mise, 2)
        elif status == "❌":
            gain_reel = round(-mise, 2)
        else:
            gain_reel = 0.0

        # Format date properly
        bet_date = bet.get("Date")
        date_str = ""
        if pd.notna(bet_date) and hasattr(bet_date, "strftime"):
            date_str = bet_date.strftime("%Y-%m-%d %H:%M:%S")
        elif pd.notna(bet_date):
            date_str = str(bet_date)

        row_data = [
            date_str,
            _safe_str(bet.get("Heure", "")),
            _safe_str(bet.get("Sport", "")),
            _safe_str(bet.get("Événement", "")),
            _safe_str(bet.get("Pari", "")),
            _safe_float(bet.get("Cote initiale", 0)),
            cote_b,
            status,
            mise,
            gains_possible,
            gain_reel,
            ""  # Cumul is computed on load
        ]
        
        # gspread expects python primitives
        formatted_row = []
        for x in row_data:
            try:
                if pd.isna(x):
                    formatted_row.append("")
                else:
                    formatted_row.append(str(x))
            except (ValueError, TypeError):
                formatted_row.append(str(x))
                
        ws.append_row(formatted_row, value_input_option='USER_ENTERED')
        print(f"[save_bet] Saved to {sheet_name}: {formatted_row[:5]}...")
    except Exception as e:
        import traceback
        print(f"[save_bet] ERROR saving to {sheet_name}: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise


def update_result(sheet_name: str, event: str, pari: str, bet_date, result: str, mise_reelle: float = None):
    ws = get_worksheet(sheet_name)
    data_rows = ws.get_all_values()
    
    target_date = pd.to_datetime(bet_date, dayfirst=True).date() if bet_date is not None and str(bet_date).strip() else None
    
    # Normalize search strings
    event_clean = str(event).strip()
    pari_clean = str(pari).strip()
    
    target_row_idx = None
    for i, row in enumerate(data_rows):
        if i == 0: continue  # Header
        if len(row) < 5: continue
        
        cell_date, cell_event, cell_pari = row[0], str(row[3]).strip(), str(row[4]).strip()
        
        if cell_event == event_clean and cell_pari == pari_clean:
            if target_date and cell_date:
                try:
                    rd = pd.to_datetime(cell_date, dayfirst=True).date()
                    if rd != target_date:
                        continue
                except Exception:
                    pass  # If date parsing fails, still match on event+pari
            target_row_idx = i + 1  # 1-indexed for gspread
            break
            
    if target_row_idx is None:
        print(f"[update_result] No match found for: event='{event_clean}', pari='{pari_clean}', date='{target_date}'")
        return
        
    print(f"[update_result] Updating row {target_row_idx} -> {result}")
    
    # Update status in column 8 (H)
    ws.update_cell(target_row_idx, 8, result)
    
    if mise_reelle is not None:
        ws.update_cell(target_row_idx, 9, float(mise_reelle))
        
        # Read cote boostée again just to be safe
        row_values = ws.row_values(target_row_idx)
        cote_b_str = row_values[6] if len(row_values) > 6 else "0"
        try:
            cote_b = float(str(cote_b_str).replace(",", ".").replace("€", "").strip())
        except ValueError:
            cote_b = 0.0
            
        gains = round(float(mise_reelle) * cote_b, 2)
        ws.update_cell(target_row_idx, 10, gains)
        
        if result == "✅":
            ws.update_cell(target_row_idx, 11, round(gains - float(mise_reelle), 2))
        elif result == "❌":
            ws.update_cell(target_row_idx, 11, round(-float(mise_reelle), 2))
        else:
             ws.update_cell(target_row_idx, 11, 0.0)
