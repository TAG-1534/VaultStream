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

sync_status = {"total": 0, "current": 0, "active": False}

def get_db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    if not os.path.exists('/config'): os.makedirs('/config', exist_ok=True)
    conn = get_db()
    conn.execute('CREATE TABLE IF NOT EXISTS progress (filename TEXT PRIMARY KEY, seconds REAL)')
    conn.execute('''CREATE TABLE IF NOT EXISTS metadata 
                    (filename TEXT PRIMARY KEY, category TEXT, path TEXT, title TEXT, poster TEXT, backdrop TEXT, desc TEXT)''')
    conn.close()

init_db()

# --- HELPERS ---
def clean_filename(name):
    name = re.sub(r'\(.*?\)|\[.*?\]', '', name.lower())
    junk = [r'1080p', r'720p', r'4k', r'2160p', r'bluray', r'bdrip', r'brrip', r'x264', r'x265', r'h264', r'hevc', r'webrip', r'web-rip', r'dvdrip', 'yify','aac', 'amzn','webrip',''1x264-galaxyrg]
    for word in junk: name = re.sub(fr'\b{word}\b', '', name)
    name = re.sub(r'[\._-]', ' ', name)
    name = re.sub(r'\b(19|20)\d{2}\b', '', name)
    return re.sub(r'\s+', ' ', name).strip().title()

def extract_tv_info(filename):
    match = re.search(r'[sS](\d+)[eE](\d+)|(\d+)x(\d+)', filename)
    return (int(match.group(1) or match.group(3)), int(match.group(2) or match.group(4))) if match else (None, None)

def sync_worker():
    global sync_status
    sync_status["active"] = True
    sync_status["current"] = 0
    all_files = []
    for cat, base_path in PATHS.items():
        if os.path.exists(base_path):
            for root, _, files in os.walk(base_path):
                for f in files:
                    if f.lower().endswith(('.mp4', '.mkv', '.webm')):
                        all_files.append((cat, base_path, root, f))
    
    sync_status["total"] = len(all_files)
    headers = {"Authorization": f"Bearer {TMDB_API_KEY}", "accept": "application/json"}
    conn = get_db()

    for cat, base_path, root, f in all_files:
        fname_no_ext = os.path.splitext(f)[0]
        rel_path = os.path.relpath(os.path.join(root, f), base_path)
        if conn.execute('SELECT 1 FROM metadata WHERE filename = ?', (fname_no_ext,)).fetchone():
            sync_status["current"] += 1
            continue

        clean_name = clean_filename(fname_no_ext)
        season, episode = extract_tv_info(f)
        t, p, b, d = clean_name, "https://via.placeholder.com/500x750?text=" + clean_name.replace(" ", "+"), "", ""

        try:
            search_type = "tv" if cat == "tv" else "movie"
            r = requests.get(f"https://api.themoviedb.org/3/search/{search_type}?query={clean_name}", headers=headers, timeout=5).json()
            if r.get('results'):
                res = r['results'][0]
                tmdb_id = res['id']
                t = res.get('name') or res.get('title')
                p = f"https://image.tmdb.org/t/p/w500{res.get('poster_path')}"
                d = res.get('overview')

                if cat == "tv" and season and episode:
                    ep_r = requests.get(f"https://api.themoviedb.org/3/tv/{tmdb_id}/season/{season}/episode/{episode}", headers=headers, timeout=5).json()
                    if 'id' in ep_r:
                        t = f"{t} - S{season:02d}E{episode:02d}: {ep_r.get('name')}"
                        d = ep_r.get('overview') or d
                        if ep_r.get('still_path'): p = f"https://image.tmdb.org/t/p/w500{ep_r.get('still_path')}"

        except: pass

        conn.execute('INSERT OR REPLACE INTO metadata VALUES (?, ?, ?, ?, ?, ?, ?)', (fname_no_ext, cat, rel_path, t, p, b, d))
        conn.commit()
        sync_status["current"] += 1
    
    conn.close()
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
        #progress-container { position: fixed; top: 70px; left: 0; width: 100%; height: 4px; background: #222; display: none; z-index: 1001; }
        #progress-bar { height: 100%; width: 0%; background: var(--primary); transition: width 0.3s; }
        .container { padding: 100px 4% 40px 4%; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 25px; }
        .tv-grid { grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); }
        .card { border-radius: 4px; overflow: hidden; transition: 0.3s; cursor: pointer; text-decoration: none; color: inherit; background: #141414; display: flex; flex-direction: column; border: 1px solid transparent;}
        .card:hover { transform: scale(1.05); border-color: #444; }
        .card img { width: 100%; aspect-ratio: 2/3; object-fit: cover; }
        .tv-card img { aspect-ratio: 16/9; }
        .card-info { padding: 10px; }
        .card-title { font-weight: bold; font-size: 0.85rem; display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .card-desc { font-size: 0.75rem; color: #999; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; margin-top: 5px; }
        h1 { margin-bottom: 30px; }
        .back-btn { display: inline-block; margin-bottom: 20px; color: var(--primary); text-decoration: none; font-size: 0.9rem; }
    </style>
</head>
<body>
    <nav>
        <a href="/" class="logo">VAULTSTREAM</a>
        <div class="nav-links">
            <a href="/category/movies">Movies</a>
            <a href="/category/tv">TV Shows</a>
            <button onclick="startSync()" class="btn-sync">Sync Library</button>
        </div>
    </nav>
    <div id="progress-container"><div id="progress-bar"></div></div>
    <div class="container">{{ body_content | safe }}</div>
    <script>
        function startSync() { fetch('/sync').then(() => checkProgress()); }
        function checkProgress() {
            const container = document.getElementById('progress-container');
            const bar = document.getElementById('progress-bar');
            setInterval(() => {
                fetch('/sync_progress').then(r => r.json()).then(data => {
                    if (data.active) {
                        container.style.display = 'block';
                        bar.style.width = ((data.current / data.total) * 100) + '%';
                    } else if (container.style.display === 'block') { location.reload(); }
                });
            }, 1000);
        }
        checkProgress();
    </script>
</body>
</html>
"""

@app.route('/')
@app.route('/category/<cat>')
def home(cat='movies'):
    conn = get_db()
    if cat == 'tv':
        rows = conn.execute("SELECT DISTINCT REPLACE(SUBSTR(title, 1, INSTR(title, ' - S') - 1), '', title) as series_name, poster FROM metadata WHERE category = 'tv' GROUP BY series_name").fetchall()
    else:
        rows = conn.execute('SELECT filename, path, title, poster FROM metadata WHERE category = "movies"').fetchall()
    conn.close()
    
    if not rows: return render_template_string(BASE_HTML, body_content="<h2>Library empty. Click Sync.</h2>")

    grid_html = '<div class="grid">'
    for r in rows:
        if cat == 'tv':
            grid_html += f'<a href="/series/{r[0]}" class="card"><img src="{r[1]}"><div class="card-info"><span class="card-title">{r[0]}</span></div></a>'
        else:
            grid_html += f'<a href="/play/movies/{r[1]}" class="card"><img src="{r[3]}"><div class="card-info"><span class="card-title">{r[2]}</span></div></a>'
    return render_template_string(BASE_HTML, body_content=grid_html + '</div>')

@app.route('/series/<name>')
def series_view(name):
    conn = get_db()
    eps = conn.execute('SELECT filename, path, title, poster, desc FROM metadata WHERE title LIKE ?', (f"{name}%",)).fetchall()
    conn.close()
    
    seasons = {}
    for e in eps:
        match = re.search(r'S(\d+)', e[2])
        s_num = match.group(1) if match else "01"
        if s_num not in seasons: seasons[s_num] = []
        seasons[s_num].append(e)

    html = f'<a href="/category/tv" class="back-btn">← Back to TV Shows</a><h1>{name}</h1>'
    for s, e_list in sorted(seasons.items()):
        html += f'<h3>Season {s}</h3><div class="grid tv-grid">'
        for e in sorted(e_list, key=lambda x: x[2]):
            html += f'<a href="/play/tv/{e[1]}" class="card tv-card"><img src="{e[3]}"><div class="card-info"><span class="card-title">{e[2]}</span><p class="card-desc">{e[4]}</p></div></a>'
        html += '</div><br><hr style="border:0; border-top:1px solid #222"><br>'
    return render_template_string(BASE_HTML, body_content=html)

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
    conn = get_db()
    row = conn.execute('SELECT seconds FROM progress WHERE filename = ?', (fname,)).fetchone()
    conn.close()
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
    conn = get_db()
    conn.execute('INSERT OR REPLACE INTO progress VALUES (?, ?)', (d['filename'], d['seconds']))
    conn.commit()
    conn.close()
    return jsonify(success=True)

@app.route('/stream/<cat>/<path:filename>')
def stream(cat, filename):
    return send_from_directory(PATHS.get(cat), filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)






