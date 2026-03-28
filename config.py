import streamlit as st

# ── Configuration de l'application ───────────────────────────────────────────
# PIN d'accès sécurisé via secrets
try:
    APP_PIN = str(st.secrets["app"]["pin"])
except Exception:
    APP_PIN = "1234"

# Nom d'utilisateur affiché
USERNAME = "Maxime"

# Port de l'application local
PORT = 8501
