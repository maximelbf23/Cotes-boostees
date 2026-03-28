#!/bin/bash
# ── Lancement de l'app Cotes Boostées ────────────────────────────────────────
cd "$(dirname "$0")"

PORT=8501

# Utiliser le Python du venv si disponible
if [ -f ".venv/bin/python3" ]; then
    PYTHON=".venv/bin/python3"
    PIP=".venv/bin/pip"
    STREAMLIT=".venv/bin/streamlit"
else
    PYTHON="python3"
    PIP="python3 -m pip"
    STREAMLIT="python3 -m streamlit"
fi

# Installer les dépendances manquantes automatiquement
echo "🔍 Vérification des dépendances..."
$PIP install -r requirements.txt --quiet 2>/dev/null

# Détecter l'IP locale
LOCAL_IP=$($PYTHON -c "
import socket
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(('8.8.8.8', 80))
    print(s.getsockname()[0])
    s.close()
except:
    print('localhost')
")

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║         🎯  COTES BOOSTÉES — Démarrage          ║"
echo "╠══════════════════════════════════════════════════╣"
echo "║                                                  ║"
echo "║  💻  Ordinateur : http://localhost:$PORT           ║"
echo "║  📱  Téléphone  : http://$LOCAL_IP:$PORT      ║"
echo "║                                                  ║"
echo "║  ⚠️  Téléphone = même réseau WiFi requis         ║"
echo "║  🔒  PIN requis pour se connecter                ║"
echo "║                                                  ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
echo "  Ctrl+C pour arrêter l'application"
echo ""

$STREAMLIT run app.py --server.port $PORT
