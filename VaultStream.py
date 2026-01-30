import os
import requests
import sqlite3
import re
import threading
from flask import Flask, render_template_string, send_from_directory, request, jsonify, redirect, url_for

app = Flask(__name__)

# --- CONFIGURATION ---
TMDB_API_KEY = "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiJiMTE3OWQ4YTVlZGM4NWI4ZGE5M2E1MTBkOTI2NTc5OCIsIm5iZiI6MTc2OTc1MjI0OC40MjgsInN1YiI6IjY5N2M0NmI4ZWFlYzRiMGRhZmY5NWQ3YSIsInNjb3BlcyI6WyJhcGlfcmVhZCJdLCJ2ZXJzaW9uIjoxfQ.eGjm5dKGiOOAVXA4MK80q4z0Bb8Dyo0ZW-w-q6F_erQ" 
DB_PATH = '/config/vaultstream.db'
PATHS = {'movies': '/movies', 'tv': '/tv'}

# Global Sync Status
sync_status = {"total": 0, "current": 0, "active": False}

def init_db():
    if not os.path.exists('/config'): os.makedirs('/config', exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS progress (filename TEXT PRIMARY KEY, seconds REAL)')
        conn.execute('''CREATE TABLE IF NOT EXISTS metadata 
                        (filename TEXT PRIMARY KEY, category TEXT, path TEXT, title TEXT, poster TEXT, backdrop TEXT, desc TEXT)''')
init_db()

# --- HELPERS ---
def clean_filename(name):
    name = re.sub(r'\(.*?\)|\[.*?\]', '', name.lower())
    junk = ['1080p', '720p', '4k', '2160p', 'bluray', 'x264', 'x265', 'h264', 'webrip', 'dvdrip']
    for word in junk: name = re.sub(fr'\b{word}\b', '', name)
    return re.sub(r'[\._-]', ' ', name).strip().title()

def extract_tv_info(filename):
    match = re.search(r'[sS](\d+)[eE](\d+)|(\d+)x(\d+)', filename)
    return (int(match.group(1) or match.group(3)), int(match.group(2) or match.group(4))) if match else (None, None)

def sync_worker():
    global sync_status
    sync_status["active"] = True
    sync_status["current"] = 0
    
    # Pre-scan to count total files
    all_files = []
    for cat, base_path in PATHS.items():
        if os.path.exists(base_path):
            for root, _, files in os.walk(base_path):
                for f in files:
                    if f.lower().endswith(('.mp4', '.mkv', '.webm')):
                        all_files.append((cat, base_path, root, f))
    
    sync_status["total"] = len(all_files)
    headers = {"Authorization": f"Bearer {TMDB_API_KEY}", "accept": "application/json"}

    for cat, base_path, root, f in all_files:
        fname_no_ext = os.path.splitext(f)[0]
        rel_path = os.path.relpath(os.path.join(root, f), base_path)
        
        # Check if exists
        with sqlite3.connect(DB_PATH) as conn:
            if not conn.execute('SELECT 1 FROM metadata WHERE filename = ?', (fname_no_ext,)).fetchone():
                clean_name = clean_filename(fname_no_ext)
                season, episode = extract_tv_info(f)
                try:
                    r = requests.get(f"https://api.themoviedb.org/3/search/multi?query={clean_name}", headers=headers).json()
                    if r.get('results'):
                        res = r['results'][0]
                        t, p, b, d = (res.get('title') or res.get('name')), f"https://image.tmdb.org/t/p/w500{res.get('poster_path')}", f"https://image.tmdb.org/t/p/original{res.get('backdrop_path')}", res.get('overview')
                        if res.get('media_type') == 'tv' and season:
                            ep = requests.get(f"https://api.themoviedb.org/3/tv/{res['id']}/season/{season}/episode/{episode}", headers=headers).json()
                            if 'id' in ep:
                                t = f"{t} - S{season:02d}E{episode:02d}"
                                if ep.get('still_path'): p = f"https://image.tmdb.org/t/p/w500{ep.get('still_path')}"
                        
                        with sqlite3.connect(DB_PATH) as conn:
                            conn.execute('INSERT OR REPLACE INTO metadata VALUES (?, ?, ?, ?, ?, ?, ?)', (fname_no_ext, cat, rel_path, t, p, b, d))
                except: pass
        
        sync_status["current"] += 1

    sync_status["active"] = False

# --- UI ---
BASE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>VaultStream</title>
    <style>
        :root { --primary: #e50914; --bg: #080808; --text: #fff; }
        body { background: var(--bg); color: var(--text); font-family: 'Helvetica Neue', Arial, sans-serif; margin: 0; }
        nav { background: rgba(0,0,0,0.95); height: 70px; display: flex; align-items: center; padding: 0 4%; position: fixed; width: 100%; z-index: 1000; border-bottom: 1px solid #222; box-sizing: border-box;}
        .logo { color: var(--primary); font-size: 1.8rem; font-weight: bold; text-decoration: none; margin-right: 40px; }
        .nav-links a { color: #e5e5e5; text-decoration: none; margin-right: 25px; font-size: 0.9rem; }
        .btn-sync { background: var(--primary); color: white; border: none; padding: 8px 20px; border-radius: 4px; cursor: pointer; text-decoration: none; margin-left: auto; font-weight: bold;}
        
        #progress-container { position: fixed; top: 70px; left: 0; width: 100%; height: 5px; background: #222; display: none; z-index: 1001; }
        #progress-bar { height: 100%; width: 0%; background: var(--primary); transition: width 0.3s; }
        #sync-text { position: fixed; top: 80px; right: 4%; font-size: 0.7rem; color: #aaa; display: none; z-index: 1001; }

        .container { padding: 100px 4% 40px 4%; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 20px; }
        .tv-grid { grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); }
        .card { border-radius: 8px; overflow: hidden; transition: 0.3s; cursor: pointer; text-decoration: none; color: inherit; background: #141414; border: 1px solid #222; }
        .card:hover { transform: scale(1.05); border-color: #444; }
        .card img { width: 100%; aspect-ratio: 2/3; object-fit: cover; }
        .tv-card img { aspect-ratio: 16/9; }
        .card-info { padding: 10px; }
        .card-title { font-weight: bold; font-size: 0.85rem; display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    </style>
</head>
<body>
    <nav>
        <a href="/" class="logo">VAULTSTREAM</a>
        <div class="nav-links">
            <a href="/category/movies">Movies</a>
            <a href="/category/tv">TV Shows</a>
            <button onclick="startSync()" class="btn-sync" id="syncBtn">Sync Library</button>
        </div>
    </nav>
    <div id="progress-container"><div id="progress-bar"></div></div>
    <div id="sync-text">Syncing: <span id="sync-count">0</span> / <span id="sync-total">0</span></div>

    <div class="container">{{ body_content | safe }}</div>

    <script>
        function startSync() {
            fetch('/sync').then(() => checkProgress());
        }

        function checkProgress() {
            const container = document.getElementById('progress-container');
            const bar = document.getElementById('progress-bar');
            const text = document.getElementById('sync-text');
            const count = document.getElementById('sync-count');
            const total = document.getElementById('sync-total');

            setInterval(() => {
                fetch('/sync_progress').then(r => r.json()).then(data => {
                    if (data.active) {
                        container.style.display = 'block';
                        text.style.display = 'block';
                        let percent = (data.current / data.total) * 100;
                        bar.style.width = percent + '%';
                        count.innerText = data.current;
                        total.innerText = data.total;
                    } else {
                        if (container.style.display === 'block') location.reload();
                        container.style.display = 'none';
                        text.style.display = 'none';
                    }
                });
            }, 1000);
        }
        // Auto-check on page load in case sync is already running
        checkProgress();
    </script>
</body>
</html>
"""

@app.route('/')
@app.route('/category/<cat>')
def home(cat='movies'):
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute('SELECT filename, path, title, poster FROM metadata WHERE category = ?', (cat,)).fetchall()
    
    if not rows:
        return render_template_string(BASE_HTML, body_content="<h2>No media found. Click 'Sync Library'.</h2>")

    grid_class = "grid tv-grid" if cat == 'tv' else "grid"
    card_class = "card tv-card" if cat == 'tv' else "card"
    
    grid_html = f'<div class="{grid_class}">'
    for r in rows:
        grid_html += f'<a href="/play/{cat}/{r[1]}" class="{card_class}"><img src="{r[3]}"><div class="card-info"><span class="card-title">{r[2]}</span></div></a>'
    grid_html += '</div>'
    return render_template_string(BASE_HTML, body_content=grid_html)

@app.route('/sync')
def sync():
    if not sync_status["active"]:
        threading.Thread(target=sync_worker).start()
    return jsonify(status="started")

@app.route('/sync_progress')
def get_progress():
    return jsonify(sync_status)

@app.route('/play/<cat>/<path:filename>')
def play(cat, filename):
    fname = os.path.splitext(os.path.basename(filename))[0]
    saved_time = 0
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute('SELECT seconds FROM progress WHERE filename = ?', (fname,)).fetchone()
        if row: saved_time = row[0]

    player_html = f"""
    <div style="text-align:center;">
        <video id="v" style="width:100%; max-height:85vh; background: #000;" controls autoplay><source src="/stream/{cat}/{filename}"></video>
    </div>
    <script>
        const v = document.getElementById('v');
        v.currentTime = {saved_time};
        setInterval(() => {{
            if (!v.paused) {{
                fetch('/save_progress', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ filename: "{fname}", seconds: v.currentTime }})
                }});
            }}
        }}, 5000);
    </script>"""
    return render_template_string(BASE_HTML, body_content=player_html)

@app.route('/save_progress', methods=['POST'])
def save_progress():
    d = request.json
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('INSERT OR REPLACE INTO progress VALUES (?, ?)', (d['filename'], d['seconds']))
    return jsonify(success=True)

@app.route('/stream/<cat>/<path:filename>')
def stream(cat, filename):
    return send_from_directory(PATHS.get(cat), filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True)
