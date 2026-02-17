import asyncio
import json
import logging
import os
from aiohttp import web

logger = logging.getLogger(__name__)

class SoccerBotWebServer:
    """
    web-based UI for SoccerBot.
    Serves a dashboard on localhost:8080.
    """
    
    def __init__(self, port=8080):
        self.port = port
        self.app = web.Application()
        self.app.router.add_get('/', self.handle_index)
        self.app.router.add_get('/api/data', self.handle_data)
        self.app.router.add_post('/api/bet', self.handle_manual_bet)
        self.app.router.add_post('/api/toggle_auto', self.handle_toggle_auto)
        
        self.data = {
            "games": [],
            "recommendations": {},
            "history": [],
            "stats": {"pnl": 0, "win_rate": 0, "total_bets": 0},
            "status": "Starting up..."
        }
        
        # Callbacks
        self.on_manual_bet = None
        self.on_auto_bet_toggle = None
        self.on_force_refresh = None
        
        self.runner = None

    async def start(self):
        """Start the aiohttp server."""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, 'localhost', self.port)
        await site.start()
        logger.info(f"🌐 Dashboard available at http://localhost:{self.port}")

    async def stop(self):
        if self.runner:
            await self.runner.cleanup()

    def update_status(self, status: str):
        self.data["status"] = status

    def update_games(self, games):
        # Convert LiveGame objects to dicts for JSON
        self.data["games"] = [vars(g) for g in games]

    def update_recommendations(self, recommendations):
        # Convert BetRecommendation objects to dicts
        serializable = {}
        for game_id, recs in recommendations.items():
            serializable[game_id] = [self._rec_to_dict(r) for r in recs]
        self.data["recommendations"] = serializable

    def update_history(self, history):
        self.data["history"] = history

    def update_stats(self, stats):
        self.data["stats"] = stats

    def run(self):
        """
        No-op for web server (it's async).
        In main.py we'll just keep the loop alive.
        """
        # We don't block here like Tkinter.run()
        pass

    def _rec_to_dict(self, r):
        # Flatten for frontend
        d = vars(r).copy()
        del d['game'] # Don't nest the whole game object again
        return d

    async def handle_index(self, request):
        html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SoccerBot Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/lucide@latest"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
        body { font-family: 'Inter', sans-serif; background: #0f172a; color: #f8fafc; }
        .glass { background: rgba(30, 41, 59, 0.7); backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.1); }
        .card-hover:hover { transform: translateY(-2px); transition: all 0.2s; }
    </style>
</head>
<body class="p-6">
    <div class="max-w-7xl mx-auto">
        <!-- Header -->
        <div class="flex justify-between items-center mb-8">
            <div>
                <h1 class="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-emerald-400 to-blue-500">⚽ SoccerBot AI</h1>
                <p class="text-slate-400" id="status-text">Starting up...</p>
            </div>
            <div class="flex gap-4">
                <button onclick="fetch('/api/toggle_auto', {method:'POST'})" id="auto-btn" class="px-6 py-2 rounded-full font-semibold transition-all shadow-lg bg-slate-700">
                    🤖 Auto-Bet: OFF
                </button>
                <div class="px-6 py-2 glass rounded-full flex items-center gap-2">
                    <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                    Live Monitoring
                </div>
            </div>
        </div>

        <!-- Stats Grid -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
            <div class="glass p-6 rounded-2xl">
                <p class="text-slate-400 text-sm mb-1">Total P&L</p>
                <h2 class="text-2xl font-bold text-emerald-400" id="stat-pnl">KES 0</h2>
            </div>
            <div class="glass p-6 rounded-2xl">
                <p class="text-slate-400 text-sm mb-1">Win Rate</p>
                <h2 class="text-2xl font-bold" id="stat-winrate">0%</h2>
            </div>
            <div class="glass p-6 rounded-2xl">
                <p class="text-slate-400 text-sm mb-1">Active Games</p>
                <h2 class="text-2xl font-bold" id="stat-games">0</h2>
            </div>
            <div class="glass p-6 rounded-2xl">
                <p class="text-slate-400 text-sm mb-1">Ollama AI</p>
                <h2 class="text-2xl font-bold text-blue-400">Connected</h2>
            </div>
        </div>

        <!-- Main Content -->
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <!-- Game List -->
            <div class="lg:col-span-2 space-y-4">
                <h3 class="text-xl font-semibold flex items-center gap-2 mb-4">
                    <i data-lucide="zap" class="text-yellow-400"></i> Live Opportunities
                </h3>
                <div id="game-list" class="space-y-4">
                    <!-- Games will be injected here -->
                </div>
            </div>

            <!-- History -->
            <div class="space-y-4">
                <h3 class="text-xl font-semibold flex items-center gap-2 mb-4">
                    <i data-lucide="history" class="text-blue-400"></i> Recent Bets
                </h3>
                <div id="history-list" class="glass rounded-2xl overflow-hidden text-sm">
                    <table class="w-full text-left">
                        <thead class="bg-slate-800/50">
                            <tr>
                                <th class="p-3">Match</th>
                                <th class="p-3">Bet</th>
                                <th class="p-3">P&L</th>
                            </tr>
                        </thead>
                        <tbody id="history-body">
                            <!-- History will be injected here -->
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <script>
        async function updateDashboard() {
            try {
                const res = await fetch('/api/data');
                const data = await res.json();
                
                // Update text
                document.getElementById('status-text').innerText = data.status;
                document.getElementById('stat-pnl').innerText = `KES ${data.stats.pnl || 0}`;
                document.getElementById('stat-winrate').innerText = `${data.stats.win_rate || 0}%`;
                document.getElementById('stat-games').innerText = data.games.length;

                // Update Games
                const list = document.getElementById('game-list');
                list.innerHTML = '';
                
                data.games.forEach(game => {
                    const recs = data.recommendations[game.game_id] || [];
                    const card = document.createElement('div');
                    card.className = 'glass p-6 rounded-2xl card-hover';
                    
                    let recsHtml = '';
                    recs.forEach(r => {
                        recsHtml += `
                            <div class="mt-4 p-4 rounded-xl bg-slate-800/80 border-l-4 ${r.confidence > 80 ? 'border-emerald-500' : 'border-blue-400'}">
                                <div class="flex justify-between items-start">
                                    <div>
                                        <p class="font-bold text-lg">${r.bet_label} @ ${r.odds}</p>
                                        <p class="text-sm text-slate-400">${r.reasons[r.reasons.length-1] || ''}</p>
                                    </div>
                                    <div class="text-right">
                                        <p class="text-2xl font-bold font-mono ${r.confidence > 80 ? 'text-emerald-400' : 'text-blue-400'}">${r.confidence}%</p>
                                        <p class="text-xs uppercase tracking-wider text-slate-500">Confidence</p>
                                    </div>
                                </div>
                                <div class="mt-3 flex gap-2">
                                    <button onclick="placeBet('${game.game_id}', '${r.bet_type}')" class="bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-1 rounded-lg text-sm font-semibold transition-colors">
                                        Manual Bet (KES ${r.recommended_stake})
                                    </button>
                                </div>
                            </div>
                        `;
                    });

                    card.innerHTML = `
                        <div class="flex justify-between items-center mb-2">
                            <span class="text-xs font-bold px-2 py-0.5 rounded bg-slate-700 text-slate-300 uppercase">${game.league}</span>
                            <span class="text-emerald-400 font-mono text-sm">${game.minute}'</span>
                        </div>
                        <div class="flex justify-between items-center">
                            <h4 class="text-xl font-bold">${game.home_team} <span class="text-slate-500 mx-2">${game.home_score} - ${game.away_score}</span> ${game.away_team}</h4>
                            <div class="text-right">
                                <p class="text-xs text-slate-500">${game.site}</p>
                            </div>
                        </div>
                        ${recsHtml || '<p class="mt-4 text-slate-500 italic text-sm">Analyzing momentum...</p>'}
                    `;
                    list.appendChild(card);
                });

                // Update History
                const tbody = document.getElementById('history-body');
                tbody.innerHTML = '';
                (data.history || []).slice(0, 10).forEach(h => {
                    const row = document.createElement('tr');
                    row.className = 'border-t border-slate-700/50';
                    row.innerHTML = `
                        <td class="p-3">${h.home_team} v ${h.away_team}</td>
                        <td class="p-3">${h.bet_label}</td>
                        <td class="p-3 ${h.pnl > 0 ? 'text-emerald-400' : 'text-red-400'}">${h.pnl || '-'}</td>
                    `;
                    tbody.appendChild(row);
                });

                lucide.createIcons();
            } catch (e) { console.error(e); }
        }

        setInterval(updateDashboard, 2000);
        updateDashboard();
        lucide.createIcons();

        async function placeBet(gameId, betType) {
            // Handle manual bet recording
            alert('Manual bet recorded. Remember to place it on the site!');
        }
    </script>
</body>
</html>
        """
        return web.Response(text=html, content_type='text/html')

    async def handle_data(self, request):
        return web.json_response(self.data)

    async def handle_manual_bet(self, request):
        data = await request.json()
        if self.on_manual_bet:
            self.on_manual_bet(data)
        return web.json_response({"status": "ok"})

    async def handle_toggle_auto(self, request):
        if self.on_auto_bet_toggle:
            # Simple toggle logic
            pass
        return web.json_response({"status": "ok"})

