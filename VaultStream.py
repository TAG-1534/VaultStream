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
    # Structure: filename, category, path, title, poster, backdrop, desc, series_title, season
    conn.execute('''CREATE TABLE IF NOT EXISTS metadata 
                    (filename TEXT PRIMARY KEY, category TEXT, path TEXT, title TEXT, 
                     poster TEXT, backdrop TEXT, desc TEXT, series_title TEXT, season INTEGER)''')
    conn.close()

init_db()

# --- HELPERS ---
def clean_filename(name):
    name = name.lower()
    name = re.sub(r'\(.*?\)|\[.*?\]', '', name)
    junk = [ r'1080p', r'720p', r'4k', r'2160p', r'bluray', r'bdrip', r'brrip', r'dvdrip', r'webrip', r'web-rip', r'hdtv', r'remux', r'sd', r'hd', r'480p', r'576p', r'web-dl', r'webdl', r'pdtv', r'x264', r'x265', r'h264', r'h265', r'hevc', r'10bit', r'avc', r'vc1', r'xvid', r'divx', r'aac', r'dts', r'dd5\.1', r'ac3', r'dts-hd', r'truehd', r'atmos', r'eac3', r'mp3', r'dual-audio', r'multi', r'dubbed', r'subbed', r'ddp5\.1', r'ddp2\.0', r'flac', r'opus', r'yify', r'yts', r'rarbg', r'psa', r'galaxyrg', r'tgx', r'evo', r'tigole', r'qxr', r'sartre', r'ion10', r'ettv', r'juggs', r'vppv', r'ozlem', r'nitro', r'amiable', r'megusta', r'amzn', r'netflix', r'nf', r'dnp', r'dsnp', r'hmax', r'hbo', r'atvp', r'apple tv', r'itunes', r'hulu', r'repack', r'proper', r'extended', r'unrated', r'directors cut', r'hc', r'korsub', r'sub', r'internal', r'limited', r'retail', r'hdr', r'dv', r'dovi', r'gaz' ]
    for word in junk:
        name = re.sub(fr'\b{word}\b', '', name)
    if '-' in name:
        parts = re.split(r'-(?=[^-]*$)', name)
        if len(parts[0].strip()) > 2: name = parts[0]
    name = re.sub(r'[\._-]', ' ', name)
    name = re.sub(r'\b(19|20)\d{2}\b', '', name)
    return re.sub(r'\s+', ' ', name).strip().title()

def extract_tv_info(filename):
    # 1. Standard s00e00 notation
    standard = re.search(r'[sS](\d+)[eE](\d+)', filename)
    if standard:
        return int(standard.group(1)), int(standard.group(2))
    
    # 2. Date-based notation (YYYY-MM-DD or DD-MM-YYYY)
    date_match = re.search(r'(\d{4}[.\-\s]\d{2}[.\-\s]\d{2})|(\d{2}[.\-\s]\d{2}[.\-\s]\d{4})', filename)
    if date_match:
        # For date-based, we return a hash or dummy episode ID to keep it unique
        return None, date_match.group(0) 

    # 3. Multi-episode notation (s01e01-e02) -> identifies as the first episode
    multi = re.search(r'[sS](\d+)[eE](\d+)-[eE](\d+)', filename)
    if multi:
        return int(multi.group(1)), int(multi.group(2))

    return None, None

def sync_worker():
    global sync_status
    sync_status["active"] = True
    sync_status["current"] = 0
    all_files = []
    
    for cat, base_path in PATHS.items():
        if os.path.exists(base_path):
            for root, _, files in os.walk(base_path):
                for f in files:
                    if f.lower().endswith(('.mp4', '.mkv', '.webm', '.avi')):
                        all_files.append((cat, base_path, root, f))
    
    sync_status["total"] = len(all_files)
    headers = {"Authorization": f"Bearer {TMDB_API_KEY}", "accept": "application/json"}
    conn = get_db()

    for cat, base_path, root, f in all_files:
        fname_no_ext = os.path.splitext(f)[0]
        rel_path = os.path.relpath(os.path.join(root, f), base_path)
        path_parts = rel_path.split(os.sep)

        # 1. Identify Show and Season from FOLDERS
        # Expecting: ShowName/Season 01/Episode.mkv
        series_folder_name = path_parts[0] if len(path_parts) > 1 else "Unsorted"
        
        # Determine Season Number from folder name
        s_num = 1 # Default
        if len(path_parts) > 2:
            season_folder = path_parts[1].lower()
            if "special" in season_folder:
                s_num = 0
            else:
                s_match = re.search(r'(\d+)', season_folder)
                s_num = int(s_match.group(1)) if s_match else 1

        # 2. Metadata Lookup
        series_title = series_folder_name
        display_title = fname_no_ext
        poster, desc = f"https://via.placeholder.com/500x750?text={series_title}", ""

        try:
            # Search TMDB using the FOLDER name
            search_type = "tv" if cat == "tv" else "movie"
            r = requests.get(f"https://api.themoviedb.org/3/search/{search_type}?query={series_folder_name}", headers=headers).json()
            
            if r.get('results'):
                res = r['results'][0]
                tmdb_id = res['id']
                series_title = res.get('name') or res.get('title')
                poster = f"https://image.tmdb.org/t/p/w500{res.get('poster_path')}"
                
                # Try to get Episode-specific data
                if cat == "tv":
                    s_idx, e_idx = extract_tv_info(f)
                    if s_idx is not None:
                        ep_r = requests.get(f"https://api.themoviedb.org/3/tv/{tmdb_id}/season/{s_idx}/episode/{e_idx}", headers=headers).json()
                        if 'id' in ep_r:
                            display_title = f"S{s_idx:02d}E{e_idx:02d} - {ep_r.get('name')}"
                            desc = ep_r.get('overview')
                            # For episodes, use the 'still_path' as the thumbnail if available
                            if ep_r.get('still_path'):
                                poster = f"https://image.tmdb.org/t/p/w500{ep_r.get('still_path')}"
                    elif isinstance(e_idx, str): # Date-based
                        display_title = f"{e_idx} - {series_title}"
        except:
            pass

        conn.execute('INSERT OR REPLACE INTO metadata VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', 
                    (fname_no_ext, cat, rel_path, display_title, poster, "", desc, series_title, s_num))
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
        .season-folder:hover {
            border-color: #007bff !important;
            background: #222 !important;
            transform: scale(1.05);
            transition: 0.2s;
    }
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
        # GROUP BY series_title ensures only ONE card per show
        rows = conn.execute('''
            SELECT series_title, MAX(poster) 
            FROM metadata 
            WHERE category="tv" 
            GROUP BY series_title
        ''').fetchall()
    else:
        rows = conn.execute('SELECT filename, path, title, poster FROM metadata WHERE category="movies"').fetchall()
    conn.close()

    grid_html = '<div class="grid">'
    for r in rows:
        if cat == 'tv':
            # r[0] is the Series Title (Brooklyn Nine-Nine)
            grid_html += f'''
            <a href="/series/{r[0]}" class="card">
                <img src="{r[1]}" onerror="this.src='https://via.placeholder.com/500x750?text={r[0]}'">
                <div class="card-info"><span class="card-title">{r[0]}</span></div>
            </a>'''
        else:
            grid_html += f'''
            <a href="/play/movies/{r[0]}" class="card">
                <img src="{r[3]}" onerror="this.src='https://via.placeholder.com/500x750?text=Movie'">
                <div class="card-info"><span class="card-title">{r[2]}</span></div>
            </a>'''
    return render_template_string(BASE_HTML, body_content=grid_html + '</div>')

@app.route('/series/<path:series_name>')
def series_view(series_name):
    conn = get_db()
    # Get distinct seasons for this specific series_title
    seasons = conn.execute('SELECT DISTINCT season FROM metadata WHERE series_title = ? ORDER BY season ASC', (series_name,)).fetchall()
    conn.close()
    
    html = f'<a href="/category/tv" class="back-btn">← Back</a><h1>{series_name}</h1>'
    html += '<div class="grid">'
    for s in seasons:
        s_val = s[0]
        label = "Specials" if s_val == 0 else f"Season {s_val}"
        html += f'''
        <a href="/series/{series_name}/season/{s_val}" class="card">
            <div class="season-folder" style="aspect-ratio:2/3; background:#1a1a1a; display:flex; flex-direction:column; align-items:center; justify-content:center; border:2px solid #333; border-radius:10px;">
                <span style="font-size:4rem;">📂</span>
                <span style="margin-top:15px; font-weight:bold;">{label}</span>
            </div>
        </a>'''
    return render_template_string(BASE_HTML, body_content=html + '</div>')

@app.route('/series/<path:series_name>/season/<int:s_num>')
def season_view(series_name, s_num):
    conn = get_db()
    eps = conn.execute('SELECT filename, path, title, poster, desc FROM metadata WHERE series_title = ? AND season = ? AND category = "tv"', (series_name, s_num)).fetchall()
    conn.close()
    
    html = f'<a href="/series/{series_name}" class="back-btn">← Back to Seasons</a><h1>{series_name} - Season {s_num}</h1>'
    html += '<div class="grid tv-grid">'
    for e in sorted(eps, key=lambda x: x[2]):
        html += f'''
        <a href="/play/tv/{e[1]}" class="card tv-card">
            <img src="{e[3]}" onerror="this.src='https://via.placeholder.com/500x280?text=Episode'">
            <div class="card-info">
                <span class="card-title">{e[2]}</span>
            </div>
        </a>'''
    return render_template_string(BASE_HTML, body_content=html + '</div>')
    
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






