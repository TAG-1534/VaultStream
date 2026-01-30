import os
import requests
import random
import sqlite3
import re
import threading # New: For background scanning
from flask import Flask, render_template_string, send_from_directory, request, jsonify, redirect, url_for

app = Flask(__name__)

# --- CONFIGURATION ---
TMDB_API_KEY = "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiJiMTE3OWQ4YTVlZGM4NWI4ZGE5M2E1MTBkOTI2NTc5OCIsIm5iZiI6MTc2OTc1MjI0OC40MjgsInN1YiI6IjY5N2M0NmI4ZWFlYzRiMGRhZmY5NWQ3YSIsInNjb3BlcyI6WyJhcGlfcmVhZCJdLCJ2ZXJzaW9uIjoxfQ.eGjm5dKGiOOAVXA4MK80q4z0Bb8Dyo0ZW-w-q6F_erQ" 
DB_PATH = '/config/vaultstream.db'
PATHS = {'movies': '/movies', 'tv': '/tv'}

def init_db():
    if not os.path.exists('/config'): os.makedirs('/config')
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS progress (filename TEXT PRIMARY KEY, seconds REAL)')
        conn.execute('''CREATE TABLE IF NOT EXISTS metadata 
                        (filename TEXT PRIMARY KEY, category TEXT, path TEXT, title TEXT, poster TEXT, backdrop TEXT, desc TEXT)''')
init_db()

# --- THE CLEANERS ---
def clean_filename(name):
    name = re.sub(r'\(.*?\)|\[.*?\]', '', name.lower())
    junk = ['1080p', '720p', '4k', 'bluray', 'x264', 'x265', 'h264', 'webrip', 'dvdrip', 'multi']
    for word in junk: name = re.sub(f'(?i){word}', '', name)
    return re.sub(r'[\._-]', ' ', name).strip().title()

def extract_tv_info(filename):
    match = re.search(r'[sS](\d+)[eE](\d+)|(\d+)x(\d+)', filename)
    if match:
        s = int(match.group(1) or match.group(3))
        e = int(match.group(2) or match.group(4))
        return s, e
    return None, None

# --- BACKGROUND SYNC PROCESS ---
def sync_worker():
    print("Started Background Sync...")
    headers = {"Authorization": f"Bearer {TMDB_API_KEY}", "accept": "application/json"}
    
    for cat, base_path in PATHS.items():
        if not os.path.exists(base_path): continue
        
        for root, _, files in os.walk(base_path):
            for f in files:
                if f.lower().endswith(('.mp4', '.mkv', '.webm')):
                    filename = os.path.splitext(f)[0]
                    rel_path = os.path.relpath(os.path.join(root, f), base_path)
                    
                    # Check if already in DB to save API calls
                    with sqlite3.connect(DB_PATH) as conn:
                        exists = conn.execute('SELECT 1 FROM metadata WHERE filename = ?', (filename,)).fetchone()
                        if exists: continue

                    # Fetch New Meta
                    clean_name = clean_filename(filename)
                    season, episode = extract_tv_info(f)
                    
                    try:
                        search_url = f"https://api.themoviedb.org/3/search/multi?query={clean_name}"
                        search_data = requests.get(search_url, headers=headers).json()
                        
                        if search_data.get('results'):
                            res = search_data['results'][0]
                            tmdb_id = res['id']
                            media_type = res.get('media_type', 'movie')
                            title, poster, backdrop, desc = (res.get('title') or res.get('name')), f"https://image.tmdb.org/t/p/w500{res.get('poster_path')}", f"https://image.tmdb.org/t/p/original{res.get('backdrop_path')}", res.get('overview')

                            if media_type == 'tv' and season:
                                ep_url = f"https://api.themoviedb.org/3/tv/{tmdb_id}/season/{season}/episode/{episode}"
                                ep = requests.get(ep_url, headers=headers).json()
                                if 'id' in ep:
                                    title = f"{title} - S{season:02d}E{episode:02d}"
                                    if ep.get('still_path'): poster = f"https://image.tmdb.org/t/p/w500{ep.get('still_path')}"

                            with sqlite3.connect(DB_PATH) as conn:
                                conn.execute('INSERT OR REPLACE INTO metadata VALUES (?, ?, ?, ?, ?, ?, ?)', 
                                             (filename, cat, rel_path, title, poster, backdrop, desc))
                    except Exception as e: print(f"Error syncing {filename}: {e}")
    print("Sync Complete!")

# --- HTML STYLES (Wider TV Cards) ---
BASE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>VaultStream</title>
    <style>
        :root { --primary: #e50914; --bg: #080808; --text: #fff; }
        body { background: var(--bg); color: var(--text); font-family: 'Helvetica Neue', Arial; margin: 0; padding: 0; }
        nav { background: rgba(0,0,0,0.95); height: 70px; display: flex; align-items: center; padding: 0 4%; position: fixed; width: 100%; z-index: 1000; box-sizing: border-box; border-bottom: 1px solid #222;}
        .logo { color: var(--primary); font-size: 1.8rem; font-weight: bold; text-decoration: none; margin-right: 40px; }
        .nav-links a { color: #e5e5e5; text-decoration: none; margin-right: 25px; font-size: 0.9rem; }
        .btn-sync { background: var(--primary); color: white; border: none; padding: 8px 20px; border-radius: 4px; cursor: pointer; text-decoration: none; margin-left: auto; font-weight: bold;}
        
        .container { padding: 100px 4% 40px 4%; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 20px; }
        .tv-grid { grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); }
        
        .card { border-radius: 8px; overflow: hidden; transition: 0.4s; cursor: pointer; text-decoration: none; color: inherit; background: #141414; border: 1px solid #222; }
        .card:hover { transform: scale(1.05); border-color: #444; }
        .card img { width: 100%; aspect-ratio: 16/9; object-fit: cover; }
        .movie-card img { aspect-ratio: 2/3; }
        .card-info { padding: 12px; }
        .card-title { font-weight: bold; font-size: 0.9rem; margin-bottom: 5px; display: block; }
        .card-desc { font-size: 0.75rem; color: #aaa; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
    </style>
</head>
<body>
    <nav>
        <a href="/" class="logo">VAULTSTREAM</a>
        <div class="nav-links">
            <a href="/category/movies">Movies</a>
            <a href="/category/tv">TV Shows</a>
            <a href="/sync" class="btn-sync">Sync Library</a>
        </div>
    </nav>
    <div class="container">{{ body_content | safe }}</div>
</body>
</html>
"""

# --- ROUTES ---
@app.route('/')
@app.route('/category/<cat>')
def home(cat='movies'):
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute('SELECT filename, path, title, poster, desc FROM metadata WHERE category = ?', (cat,)).fetchall()
    
    if not rows:
        return render_template_string(BASE_HTML, body_content="<h2>Library is empty. Click 'Sync Library' to begin!</h2>")

    grid_class = "grid tv-grid" if cat == 'tv' else "grid"
    card_class = "card" if cat == 'tv' else "card movie-card"
    
    grid_html = f'<div class="{grid_class}">'
    for r in rows:
        grid_html += f"""
        <a href="/play/{cat}/{r[1]}" class="{card_class}">
            <img src="{r[3]}">
            <div class="card-info">
                <span class="card-title">{r[2]}</span>
                <p class="card-desc">{r[4]}</p>
            </div>
        </a>"""
    grid_html += '</div>'
    return render_template_string(BASE_HTML, body_content=grid_html)

@app.route('/sync')
def sync():
    # Run the worker in a separate thread so the user doesn't wait
    thread = threading.Thread(target=sync_worker)
    thread.start()
    return redirect(url_for('home'))

@app.route('/play/<cat>/<path:filename>')
def play(cat, filename):
    saved_time = 0
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute('SELECT seconds FROM progress WHERE filename = ?', (os.path.splitext(os.path.basename(filename))[0],)).fetchone()
        if row: saved_time = row[0]

    player_html = f"""
    <div style="text-align:center;">
        <video id="v" style="width:100%; max-height: 80vh; background: black;" controls autoplay>
            <source src="/stream/{cat}/{filename}">
        </video>
        <h2 style="margin-top:20px;">{filename}</h2>
        <a href="javascript:history.back()" style="color:var(--primary); text-decoration:none;">← Back to Library</a>
    </div>
    <script>
        const v = document.getElementById('v');
        v.currentTime = {saved_time};
        setInterval(() => {{
            if (!v.paused) {{
                fetch('/save_progress', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ filename: "{os.path.splitext(os.path.basename(filename))[0]}", seconds: v.currentTime }})
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
