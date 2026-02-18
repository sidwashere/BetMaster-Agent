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
        self.app.router.add_post('/api/recheck_login', self.handle_recheck)
        self.app.router.add_post('/api/strategy', self.handle_strategy)
        
        self.data = {
            "games": [],
            "recommendations": {},
            "history": [],
            "stats": {"pnl": 0, "win_rate": 0, "total_bets": 0},
            "status": "Starting up...",
            "scraper_statuses": {},
            "strategy": {
                "mode": "conservative",
                "stats": {}
            }
        }
        
        # Callbacks
        self.on_manual_bet = None
        self.on_auto_bet_toggle = None
        self.on_force_refresh = None
        self.on_recheck_login = None
        self.on_strategy_change = None
        
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

    def update_scraper_statuses(self, statuses):
        self.data["scraper_statuses"] = statuses

    def update_strategy_stats(self, strategy_stats):
        self.data["strategy"]["stats"] = strategy_stats

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
        # Add game info into the flat dict for easier access on frontend
        if hasattr(r, 'game'):
            d['game_id'] = r.game.game_id
            d['home_team'] = r.game.home_team
            d['away_team'] = r.game.away_team
            d['home_score'] = r.game.home_score
            d['away_score'] = r.game.away_score
            d['minute'] = r.game.minute
            d['league'] = r.game.league
            d['site'] = r.game.site
        
        if 'game' in d:
            del d['game'] # Don't nest the whole game object again
        return d

    async def handle_index(self, request):
        html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SoccerBot | AI Betting Intelligence</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/lucide@latest"></script>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>
        body { 
            font-family: 'Outfit', sans-serif; 
            background: radial-gradient(circle at top right, #1e293b, #0f172a); 
            color: #f8fafc; 
            min-height: 100vh;
        }
        .glass { 
            background: rgba(30, 41, 59, 0.4); 
            backdrop-filter: blur(12px); 
            border: 1px solid rgba(255, 255, 255, 0.1); 
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
        }
        .glass-bright {
             background: rgba(51, 65, 85, 0.5);
             backdrop-filter: blur(8px);
             border: 1px solid rgba(255, 255, 255, 0.15);
        }
        .card-hover { transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); }
        .card-hover:hover { 
            transform: translateY(-4px); 
            background: rgba(30, 41, 59, 0.6);
            border-color: rgba(59, 130, 246, 0.5);
        }
        .status-pulse { animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: .5; } }
        .glow-blue { box-shadow: 0 0 15px rgba(59, 130, 246, 0.3); }
        .glow-green { box-shadow: 0 0 15px rgba(16, 185, 129, 0.3); }
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #334155; border-radius: 10px; }
        ::-webkit-scrollbar-thumb:hover { background: #475569; }
    </style>
</head>
<body class="p-4 md:p-8">
    <div class="max-w-7xl mx-auto">
        <!-- Header -->
        <header class="flex flex-col md:flex-row justify-between items-center mb-10 gap-6">
            <div class="flex items-center gap-4">
                <div class="p-3 bg-blue-600 rounded-2xl glow-blue">
                    <i data-lucide="shield-check" class="w-8 h-8 text-white"></i>
                </div>
                <div>
                    <h1 class="text-3xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white to-slate-400">
                        SoccerBot <span class="text-blue-500">Intelligence</span>
                    </h1>
                    <div class="flex items-center gap-2 mt-1">
                        <span class="w-2 h-2 rounded-full bg-emerald-500 status-pulse"></span>
                        <p class="text-slate-400 text-sm font-medium" id="status-text">Connecting to engine...</p>
                    </div>
                </div>
            </div>
            
            <div class="flex items-center gap-3">
                <button onclick="forceRefresh()" class="p-2.5 glass rounded-xl hover:bg-slate-700 transition-colors" title="Force Refresh">
                    <i data-lucide="refresh-cw" class="w-5 h-5 text-slate-300"></i>
                </button>
                <div class="h-10 w-px bg-slate-700 mx-2"></div>
                <button onclick="toggleAutoBet()" id="auto-btn" class="flex items-center gap-3 px-6 py-2.5 rounded-xl font-semibold transition-all shadow-lg bg-slate-800 border border-slate-700 hover:border-blue-500 group">
                    <div class="w-3 h-3 rounded-full bg-slate-600 group-hover:bg-slate-500" id="auto-indicator"></div>
                    <span id="auto-text">Auto-Bet: OFF</span>
                </button>
            </div>
        </header>

        <!-- Connection Alerts -->
        <div id="connection-alerts" class="mb-8 space-y-4"></div>

        <!-- Stats Overview -->
        <section class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 mb-10">
            <div class="glass p-6 rounded-3xl relative overflow-hidden group">
                <div class="absolute -right-4 -bottom-4 opacity-10 transition-transform group-hover:scale-110">
                    <i data-lucide="trending-up" class="w-24 h-24"></i>
                </div>
                <p class="text-slate-400 text-sm font-medium uppercase tracking-wider mb-2">Total Profit/Loss</p>
                <h2 class="text-3xl font-bold text-emerald-400" id="stat-pnl">KES 0</h2>
                <div class="mt-2 text-xs text-slate-500 font-mono">LIFETIME ROI: 0%</div>
            </div>
            
            <div class="glass p-6 rounded-3xl relative overflow-hidden group">
                <div class="absolute -right-4 -bottom-4 opacity-10 transition-transform group-hover:scale-110">
                    <i data-lucide="target" class="w-24 h-24"></i>
                </div>
                <p class="text-slate-400 text-sm font-medium uppercase tracking-wider mb-2">Success Rate</p>
                <h2 class="text-3xl font-bold text-blue-400" id="stat-winrate">0%</h2>
                <div class="mt-2 text-xs text-slate-500 font-mono" id="stat-total-bets">0 SETTLED BETS</div>
            </div>

            <div class="glass p-6 rounded-3xl relative overflow-hidden group">
                <div class="absolute -right-4 -bottom-4 opacity-10 transition-transform group-hover:scale-110">
                    <i data-lucide="activity" class="w-24 h-24"></i>
                </div>
                <p class="text-slate-400 text-sm font-medium uppercase tracking-wider mb-2">Active Games</p>
                <h2 class="text-3xl font-bold text-white" id="stat-games">0</h2>
                <div class="mt-2 text-xs text-slate-500 font-mono">REAL-TIME FEEDS</div>
            </div>

            <div class="glass p-6 rounded-3xl relative overflow-hidden group border-blue-500/20">
                <div class="absolute -right-4 -bottom-4 opacity-10 transition-transform group-hover:scale-110">
                    <i data-lucide="cpu" class="w-24 h-24 text-blue-500"></i>
                </div>
                <p class="text-slate-400 text-sm font-medium uppercase tracking-wider mb-2">Local AI Analysis</p>
                <div class="flex items-center gap-2">
                    <h2 class="text-3xl font-bold text-blue-400">Ollama</h2>
                    <span class="px-2 py-0.5 rounded text-[10px] bg-blue-500/20 text-blue-400 font-bold border border-blue-500/30">ACTIVE</span>
                </div>
                <div class="mt-2 text-xs text-slate-500 font-mono">LLAMA-3 INFUSED</div>
            </div>
        </section>

        <!-- Main Dashboard -->
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <!-- Opportunities List -->
            <div class="lg:col-span-2">
                <div class="flex items-center justify-between mb-6">
                    <h3 class="text-xl font-bold flex items-center gap-3">
                        <i data-lucide="zap" class="w-6 h-6 text-yellow-400"></i>
                        Live Betting Opportunities
                    </h3>
                    <div class="text-xs font-mono text-slate-500 px-3 py-1 glass rounded-full" id="last-update">
                        LAST SCAN: JUST NOW
                    </div>
                </div>
                
                <div id="game-list" class="space-y-6">
                    <!-- Placeholder Loading State -->
                    <div class="glass p-12 rounded-3xl text-center">
                        <div class="inline-block p-4 rounded-full bg-slate-800 mb-4 animate-bounce">
                            <i data-lucide="search" class="w-8 h-8 text-blue-500"></i>
                        </div>
                        <h4 class="text-xl font-semibold mb-2">Scanning Global Markets</h4>
                        <p class="text-slate-400 max-w-sm mx-auto">Connecting to 1XBet and SportPesa feeds to identify high-value opportunities...</p>
                    </div>
                </div>
            </div>

            <!-- Side Panels -->
            <div class="space-y-8">
                <!-- Recent History -->
                <div class="glass rounded-3xl overflow-hidden">
                    <div class="p-6 border-b border-slate-700/50 flex justify-between items-center bg-slate-800/30">
                        <h3 class="font-bold flex items-center gap-3">
                            <i data-lucide="history" class="w-5 h-5 text-purple-400"></i>
                            Recent Performance
                        </h3>
                        <a href="#" class="text-xs text-blue-400 hover:text-blue-300 font-semibold uppercase tracking-wider">Expand</a>
                    </div>
                    <div class="overflow-x-auto">
                        <table class="w-full text-sm">
                            <tbody id="history-body">
                                <!-- History injected here -->
                            </tbody>
                        </table>
                    </div>
                    <div id="history-empty" class="p-8 text-center text-slate-500 hidden italic">
                        No bets recorded yet.
                    </div>
                </div>

                <!-- Tips & Warning -->
                <div class="glass-bright p-6 rounded-3xl border-l-4 border-yellow-500/50">
                    <div class="flex items-start gap-4">
                        <div class="p-2 bg-yellow-500/20 rounded-lg">
                            <i data-lucide="alert-triangle" class="w-5 h-5 text-yellow-500"></i>
                        </div>
                        <div>
                            <h4 class="font-bold text-yellow-500 mb-1">Risk Management</h4>
                            <p class="text-xs text-slate-400 leading-relaxed">
                                AI predictions are probabilistic. Never bet more than you can afford to lose. 
                                Set a daily loss limit in <span class="text-slate-200">config.py</span>.
                            </p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <footer class="mt-16 pt-8 border-t border-slate-800 text-center text-slate-500 text-xs tracking-widest uppercase">
            &copy; 2026 SoccerBot AI Terminal | Proprietary Intelligence System
        </footer>
    </div>

    <!-- Notification system -->
    <div id="notification-area" class="fixed bottom-6 right-6 z-50 flex flex-col gap-3 pointer-events-none"></div>

    <script>
        let isAutoBetEnabled = false;

        async function updateDashboard() {
            try {
                const res = await fetch('/api/data');
                const data = await res.json();
                
                // Update text
                document.getElementById('status-text').innerText = data.status;
                document.getElementById('stat-pnl').innerText = `KES ${data.stats.pnl || 0}`;
                document.getElementById('stat-winrate').innerText = `${data.stats.win_rate || 0}%`;
                document.getElementById('stat-games').innerText = data.games.length;
                document.getElementById('stat-total-bets').innerText = `${data.stats.settled_bets || 0} SETTLED BETS`;
                document.getElementById('last-update').innerText = `LAST SCAN: ${new Date().toLocaleTimeString()}`;

                // Update connection alerts
                const alertsDiv = document.getElementById('connection-alerts');
                let alertsHtml = '';
                for (const [site, status] of Object.entries(data.scraper_statuses || {})) {
                    if (status === 'WAITING_FOR_USER') {
                        alertsHtml += `
                            <div class="glass-bright p-4 rounded-2xl border-l-4 border-yellow-500 animate-pulse flex justify-between items-center">
                                <div class="flex items-center gap-3">
                                    <i data-lucide="shield-alert" class="text-yellow-500"></i>
                                    <div>
                                        <p class="font-bold text-yellow-500">Action Required: ${site}</p>
                                        <p class="text-xs text-slate-400">2FA or Manual Login required in browser window.</p>
                                        <button onclick="recheckLogin()" class="mt-2 text-[10px] font-bold bg-yellow-500 text-slate-900 px-3 py-1.5 rounded-lg hover:bg-yellow-400 transition-colors">I'VE LOGGED IN MANUALLY</button>
                                    </div>
                                </div>
                                <span class="text-[10px] font-bold bg-yellow-500/20 text-yellow-500 px-2 py-1 rounded">2FA PENDING</span>
                            </div>
                        `;
                    } else if (status === 'ERROR') {
                        alertsHtml += `
                            <div class="glass-bright p-4 rounded-2xl border-l-4 border-red-500 flex justify-between items-center">
                                <div class="flex items-center gap-3">
                                    <i data-lucide="x-circle" class="text-red-500"></i>
                                    <p class="font-bold text-red-500">Connection Error: ${site}</p>
                                </div>
                                <button onclick="forceRefresh()" class="text-[10px] font-bold bg-red-500/20 text-red-500 px-2 py-1 rounded">RETRY</button>
                            </div>
                        `;
                    }
                }
                alertsDiv.innerHTML = alertsHtml;

                // Update Games
                const list = document.getElementById('game-list');
                const fragment = document.createDocumentFragment();
                
                if (data.games.length === 0) {
                    list.innerHTML = `
                         <div class="glass p-12 rounded-3xl text-center">
                            <i data-lucide="moon" class="w-12 h-12 text-slate-600 mx-auto mb-4"></i>
                            <h4 class="text-xl font-semibold mb-2">Quiet Markets</h4>
                            <p class="text-slate-400">No live games meet the criteria right now. Check back in a few minutes.</p>
                        </div>
                    `;
                } else {
                    data.games.forEach(game => {
                        const recs = data.recommendations[game.game_id] || [];
                        const card = document.createElement('div');
                        card.className = 'glass p-6 rounded-3xl card-hover relative overflow-hidden';
                        
                        let recsHtml = '';
                        recs.forEach((r, idx) => {
                            const isHigh = r.confidence >= 85;
                            const colorClass = isHigh ? 'emerald' : 'blue';
                            const borderClass = isHigh ? 'border-emerald-500/50' : 'border-blue-500/30';
                            const bgClass = isHigh ? 'bg-emerald-500/5' : 'bg-blue-500/5';
                            
                            recsHtml += `
                                <div class="mt-6 p-5 rounded-2xl ${bgClass} border ${borderClass} relative group/rec">
                                    <div class="flex justify-between items-start">
                                        <div>
                                            <div class="flex items-center gap-2 mb-1">
                                                <span class="text-xs font-bold text-${colorClass}-400 uppercase tracking-widest">Recommended Bet</span>
                                                ${isHigh ? '<span class="px-2 py-0.5 rounded-full bg-emerald-500 text-white text-[10px] font-bold">TOP PICK</span>' : ''}
                                            </div>
                                            <h4 class="text-2xl font-bold">${r.bet_label} <span class="text-slate-500 text-lg">@ ${r.odds}</span></h4>
                                            <p class="text-sm text-slate-400 mt-2 flex items-center gap-2">
                                                <i data-lucide="info" class="w-4 h-4 text-slate-500"></i>
                                                ${r.reasons[0] || 'Statistical edge detected'}
                                            </p>
                                        </div>
                                        <div class="text-right">
                                            <div class="text-3xl font-bold text-${colorClass}-400">${r.confidence}%</div>
                                            <div class="text-[10px] uppercase font-bold text-slate-500 tracking-tighter">AI Confidence</div>
                                        </div>
                                    </div>
                                    <div class="mt-4 pt-4 border-t border-slate-700/30 flex flex-wrap gap-4 items-center">
                                         <button onclick="placeManualBet('${game.game_id}', '${r.bet_type}', ${r.recommended_stake}, ${r.odds})" 
                                                 class="flex-1 bg-gradient-to-r from-${colorClass}-600 to-${colorClass}-500 hover:from-${colorClass}-500 hover:to-${colorClass}-400 text-white px-6 py-2.5 rounded-xl text-sm font-bold shadow-lg shadow-${colorClass}-900/20 transition-all active:scale-95">
                                            Place KES ${r.recommended_stake} Bet
                                         </button>
                                         <div class="px-4 py-2 bg-slate-800/80 rounded-xl text-xs font-mono border border-slate-700">
                                            <span class="text-slate-500">EDGE:</span> <span class="text-${r.edge > 0 ? 'emerald' : 'red'}-400">${(r.edge*100).toFixed(1)}%</span>
                                         </div>
                                         <div class="px-4 py-2 bg-slate-800/80 rounded-xl text-xs font-mono border border-slate-700">
                                            <span class="text-slate-500">KELLY:</span> ${(r.kelly_fraction*100).toFixed(1)}%
                                         </div>
                                    </div>
                                </div>
                            `;
                        });

                        card.innerHTML = `
                            <div class="flex justify-between items-center mb-4">
                                <div class="flex items-center gap-3">
                                    <span class="text-[10px] font-bold px-3 py-1 rounded-full bg-slate-800 text-slate-300 border border-slate-700 tracking-widest uppercase">${game.league}</span>
                                    <div class="flex items-center gap-1.5 px-3 py-1 rounded-full bg-red-500/10 border border-red-500/20 text-red-500 text-[10px] font-bold">
                                        <span class="w-1.5 h-1.5 bg-red-500 rounded-full status-pulse"></span>
                                        LIVE ${game.minute}'
                                    </div>
                                </div>
                                <div class="text-xs font-bold text-slate-500 uppercase tracking-widest">${game.site}</div>
                            </div>
                            <div class="flex items-center gap-6">
                                <div class="flex-1 text-center md:text-left">
                                    <h5 class="text-xl font-bold tracking-tight">${game.home_team}</h5>
                                </div>
                                <div class="px-6 py-2 glass-bright rounded-2xl flex flex-col items-center min-w-[100px]">
                                    <div class="text-2xl font-bold tracking-tighter">${game.home_score} : ${game.away_score}</div>
                                    <div class="text-[9px] text-slate-500 font-bold uppercase tracking-widest">Score</div>
                                </div>
                                <div class="flex-1 text-center md:text-right">
                                    <h5 class="text-xl font-bold tracking-tight">${game.away_team}</h5>
                                </div>
                            </div>
                            ${recsHtml || `
                                <div class="mt-6 flex items-center justify-center p-8 border-2 border-dashed border-slate-700/50 rounded-2xl">
                                    <p class="text-slate-500 text-sm italic">Engine is assessing live momentum and value...</p>
                                </div>
                            `}
                        `;
                        fragment.appendChild(card);
                    });
                    list.innerHTML = '';
                    list.appendChild(fragment);
                }

                // Update History
                const tbody = document.getElementById('history-body');
                const emptyHistory = document.getElementById('history-empty');
                if (data.history && data.history.length > 0) {
                    emptyHistory.classList.add('hidden');
                    tbody.innerHTML = '';
                    data.history.slice(0, 8).forEach(h => {
                        const tr = document.createElement('tr');
                        tr.className = 'border-b border-slate-700/30 last:border-0 hover:bg-slate-700/20 transition-colors cursor-default group';
                        
                        const pnlColor = (h.pnl > 0) ? 'emerald-400' : (h.pnl < 0 ? 'red-400' : 'slate-400');
                        const pnlText = h.pnl > 0 ? `+${h.pnl}` : (h.pnl || '-');
                        
                        tr.innerHTML = `
                            <td class="px-6 py-4">
                                <div class="font-bold text-slate-200">
                                    ${h.match.split(' vs ')[0]}
                                    <span class="text-[10px] text-slate-500 mx-1">v</span>
                                    ${h.match.split(' vs ')[1]}
                                </div>
                                <div class="text-[10px] text-slate-500 uppercase tracking-tighter mt-0.5">${h.timestamp.split('T')[1].substring(0,5)} | ${h.site}</div>
                            </td>
                            <td class="px-4 py-4">
                                <span class="px-2 py-1 bg-slate-800 rounded-lg text-xs font-medium text-slate-300">${h.bet}</span>
                            </td>
                            <td class="px-6 py-4 text-right">
                                <span class="font-mono font-bold text-${pnlColor}">${pnlText}</span>
                            </td>
                        `;
                        tbody.appendChild(tr);
                    });
                } else {
                    tbody.innerHTML = '';
                    emptyHistory.classList.remove('hidden');
                }

                lucide.createIcons();
            } catch (e) { console.error('Dashboard Update Error:', e); }
        }

        async function toggleAutoBet() {
            const newState = !isAutoBetEnabled;
            
            if (newState) {
                const confirmed = confirm("⚠️ ENABLE AUTO-BETTING?\\n\\nReal funds will be risked based on AI confidence (>85%).\\n\\nAre you sure?");
                if (!confirmed) return;
            }

            try {
                const res = await fetch('/api/toggle_auto', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({enabled: newState})
                });
                const result = await res.json();
                
                if (result.status === 'ok') {
                    isAutoBetEnabled = newState;
                    updateAutoUI();
                    showNotification(`Auto-Betting ${newState ? 'Enabled 🤖' : 'Disabled 🛑'}`, newState ? 'success' : 'info');
                }
            } catch (e) {
                showNotification("Failed to toggle auto-bet", "error");
            }
        }

        function updateAutoUI() {
            const btn = document.getElementById('auto-btn');
            const text = document.getElementById('auto-text');
            const indicator = document.getElementById('auto-indicator');
            
            if (isAutoBetEnabled) {
                btn.classList.add('border-emerald-500/50', 'bg-emerald-500/5');
                text.innerText = "Auto-Bet: ACTIVE";
                text.classList.add('text-emerald-400');
                indicator.classList.remove('bg-slate-600');
                indicator.classList.add('bg-emerald-500', 'status-pulse');
            } else {
                btn.classList.remove('border-emerald-500/50', 'bg-emerald-500/5');
                text.innerText = "Auto-Bet: OFF";
                text.classList.remove('text-emerald-400');
                indicator.classList.add('bg-slate-600');
                indicator.classList.remove('bg-emerald-500', 'status-pulse');
            }
        }

        async function placeManualBet(gameId, betType, stake, odds) {
            try {
                const res = await fetch('/api/bet', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ game_id: gameId, bet_type: betType })
                });
                const result = await res.json();
                if (result.status === 'ok') {
                    showNotification(`Bet Recorded: KES ${stake} @ ${odds}`, 'success');
                    updateDashboard();
                } else {
                    showNotification(result.message || "Failed to record bet", "error");
                }
            } catch (e) {
                showNotification("Connection error", "error");
            }
        }

        async function forceRefresh() {
            showNotification("Scan triggered manually...", "info");
            // No direct API for this yet, but we'll implement it
            await fetch('/api/toggle_auto', { method: 'POST', body: JSON.stringify({refresh: true}) }).catch(() => {});
            setTimeout(updateDashboard, 1000);
        }

        async function recheckLogin() {
            showNotification("Checking login status...", "info");
            await fetch('/api/recheck_login', { method: 'POST' }).catch(() => {});
            setTimeout(updateDashboard, 2000);
        }

        function showNotification(message, type = 'info') {
            const area = document.getElementById('notification-area');
            const note = document.createElement('div');
            note.className = `glass px-6 py-4 rounded-2xl shadow-2xl transition-all duration-500 transform translate-x-full pointer-events-auto border-l-4 ${
                type === 'success' ? 'border-emerald-500' : (type === 'error' ? 'border-red-500' : 'border-blue-500')
            }`;
            note.innerHTML = `
                <div class="flex items-center gap-3">
                    <i data-lucide="${type === 'success' ? 'check-circle' : (type === 'error' ? 'alert-circle' : 'info')}" class="w-5 h-5 ${
                        type === 'success' ? 'text-emerald-400' : (type === 'error' ? 'text-red-400' : 'text-blue-400')
                    }"></i>
                    <p class="font-bold text-sm text-slate-200">${message}</p>
                </div>
            `;
            area.appendChild(note);
            setTimeout(() => note.classList.remove('translate-x-full'), 100);
            setTimeout(() => {
                note.classList.add('opacity-0', 'scale-95');
                setTimeout(() => note.remove(), 500);
            }, 4000);
            lucide.createIcons();
        }

        setInterval(updateDashboard, 5000);
        setTimeout(updateDashboard, 500);
        lucide.createIcons();
    </script>
</body>
</html>
        """
        return web.Response(text=html, content_type='text/html')

    async def handle_data(self, request):
        return web.json_response(self.data)

    async def handle_manual_bet(self, request):
        try:
            data = await request.json()
            game_id = data.get("game_id")
            bet_type = data.get("bet_type")
            
            # Find the recommendation object
            rec = None
            if game_id in self.data["recommendations"]:
                for r in self.data["recommendations"][game_id]:
                    if r['bet_type'] == bet_type:
                        # Reconstruct a shell object for the record_bet method
                        # Since we transformed it to dict, we need to pass something back
                        # that the controller expects.
                        # For simplicity, we'll let the controller handle the dict or find the object.
                        rec = r
                        break
            
            if rec and self.on_manual_bet:
                # We need the original BetRecommendation object ideally, 
                # but we'll pass the dict and let the handler deal with it.
                self.on_manual_bet(rec)
                return web.json_response({"status": "ok", "message": "Bet recorded"})
            
            return web.json_response({"status": "error", "message": "Recommendation not found"}, status=404)
        except Exception as e:
            logger.error(f"Error handling manual bet: {e}")
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    async def handle_toggle_auto(self, request):
        try:
            # Get current state from the request or just toggle
            data = await request.json()
            enabled = data.get("enabled")
            
            if enabled is None:
                # If not provided, toggle the current state (we'd need to track it)
                # For now, we assume the frontend sends the desired state
                return web.json_response({"status": "error", "message": "enabled state required"}, status=400)

            if self.on_auto_bet_toggle:
                self.on_auto_bet_toggle(enabled)
                return web.json_response({"status": "ok", "enabled": enabled})
            
            return web.json_response({"status": "error", "message": "Callback not registered"}, status=500)
        except Exception as e:
            logger.error(f"Error toggling auto-bet: {e}")
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    async def handle_recheck(self, request):
        try:
            if self.on_recheck_login:
                await self.on_recheck_login()
                return web.json_response({"status": "ok"})
            return web.json_response({"status": "error", "message": "Callback not registered"}, status=500)
        except Exception as e:
            logger.error(f"Error handling recheck: {e}")
            return web.json_response({"status": "error", "message": str(e)}, status=500)

