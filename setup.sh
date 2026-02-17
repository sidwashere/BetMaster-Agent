#!/bin/bash
# setup.sh — One-time SoccerBot setup

echo "⚽ SoccerBot Setup"
echo "=================="

# Check Python version
python3 --version || { echo "❌ Python 3 required"; exit 1; }

# Install Python deps
echo "📦 Installing Python dependencies..."
pip install -r requirements.txt

# Install Playwright browsers
echo "🌐 Installing Playwright Chromium browser..."
python3 -m playwright install chromium

# Create data directories
mkdir -p data logs

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Edit config.py — add your betting site credentials"
echo "  2. (Optional) Get free API key at football-data.org and add to config.py"
echo "  3. Run: python main.py"
echo ""
echo "⚠️  Bet responsibly. Only bet what you can afford to lose."
