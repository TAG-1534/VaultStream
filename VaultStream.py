import os
import requests
import random
import sqlite3
import re
from flask import Flask, render_template_string, send_from_directory, request, jsonify, redirect, url_for

app = Flask(__name__)

# --- CONFIGURATION ---
# Use the same TMDB Token you've been using
TMDB_API_KEY = "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiJiMTE3OWQ4YTVlZGM4NWI4ZGE5M2E1MTBkOTI2NTc5OCIsIm5iZiI6MTc2OTc1MjI0OC40MjgsInN1YiI6IjY5N2M0NmI4ZWFlYzRiMGRhZmY5NWQ3YSIsInNjb3BlcyI6WyJhcGlfcmVhZCJdLCJ2ZXJzaW9uIjoxfQ.eGjm5dKGiOOAVXA4MK80q4z0Bb8Dyo0ZW-w-q6F_erQ" 
DB_PATH = '/config/vaultstream.db'
PATHS = {'movies': '/movies', 'tv': '/tv'}

# Global cache to speed up the UI
media_cache = {'movies': [], 'tv': []}

def init_db():
    if not os.path.exists('/config'): os.makedirs('/config')
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS progress (filename TEXT PRIMARY KEY, seconds REAL)')
init_db()

def clean_filename(name):
    name = re.sub(r'\(.*?\)|\[.*?\]', '', name)
    junk = ['1080p', '720p', '4k', 'bluray', 'x264', 'x265', 'h264', 'webrip', 'dvdrip', 'multi']
    for word in junk:
        name = re.sub(f'(?i){word}', '', name)
    return name.replace('.', ' ').replace('_', ' ').strip()

def fetch_metadata(name):
    clean_name = clean_filename(name)
    url = f"https://api.themoviedb.org/3/search/multi?query={clean_name}"
    headers = {"Authorization": f"Bearer {TMDB_API_KEY}", "accept": "application/json"}
    
    try:
        r = requests.get(url, headers=headers, timeout=5).json()
        if r.get('results'):
            res = r['results'][0]
            return {
                'title': res.get('title') or res.get('name') or name,
                'poster': f"https://image.tmdb.org/t/p/w500{res.get('poster_path')}" if res.get('poster_path') else "https://via.placeholder.com/500x750?text=No+Poster",
                'backdrop': f"https://image.tmdb.org/t/p/original{res.get('backdrop_path')}" if res.get('backdrop_path') else "",
                'desc': res.get('overview', 'No description available.')
            }
    except Exception: pass
    return {'title': name, 'poster': "https://via.placeholder.com/500x750?text=No+Metadata", 'backdrop': '', 'desc': ''}

def scan_files(path):
    results = []
    if not os.path.exists(path): return []
    for root, _, files in os.walk(path):
        for f in files:
            if f.lower().endswith(('.mp4', '.mkv', '.webm', '.avi')):
                rel = os.path.relpath(os.path.join(root, f), path)
                results.append({'name': os.path.splitext(f)[0], 'path': rel})
    return results

# --- REFRESH LOGIC ---
@app.route('/rescan')
def rescan():
    # This clears the internal cache and redirects back home
    global media_cache
    media_cache['movies'] = scan_files(PATHS['movies'])
    media_cache['tv'] = scan_files(PATHS['tv'])
    return redirect(url_for('home'))

BASE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>VaultStream</title>
    <style>
        :root { --primary: #e50914; --bg: #080808; --text: #fff; }
        body { background: var(--bg); color: var(--text); font-family: 'Helvetica Neue', Arial; margin: 0; }
        nav { background: rgba(0,0,0,0.9); height: 70px; display: flex; align-items: center; padding: 0 4%; position: fixed; width: 100%; z-index: 1000; box-sizing: border-box; }
        .logo { color: var(--primary); font-size: 1.8rem; font-weight: bold; text-decoration: none; margin-right: 40px; }
        .nav-links { display: flex; align-items: center; flex-grow: 1; }
        .nav-links a { color: #e5e5e5; text-decoration: none; margin-right: 25px; font-size: 1rem; transition: 0.3s; }
        .nav-links a:hover { color: var(--primary); }
        .rescan-btn { margin-left: auto; background: #333; color: white; border: none; padding: 8px 15px; border-radius: 4px; cursor: pointer; text-decoration: none; font-size: 0.8rem; }
        .rescan-btn:hover { background: #555; }
        
        .hero { height: 80vh; background-size: cover; background-position: center; display: flex; align-items: center; position: relative; padding: 0 4%; }
        .hero-overlay { position: absolute; top:0; left:0; width:100%; height:100%; background: linear-gradient(to top, var(--bg), transparent); }
        .hero-content { position: relative; z-index: 2; max-width: 700px; }
        
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 20px; padding: 40px 4%; }
        .card { border-radius: 4px; overflow: hidden; transition: 0.3s; cursor: pointer; text-decoration: none; color: inherit; background: #141414; }
        .card:hover { transform: scale(1.05); }
        .card img { width: 100%; aspect-ratio: 2/3; object-fit: cover; }
        .info { padding: 10px; font-size: 0.9rem; text-align: center; }
    </style>
</head>
<body>
    <nav>
        <a href="/" class="logo">VAULTSTREAM</a>
        <div class="nav-links">
            <a href="/category/movies">Movies</a>
            <a href="/category/tv">TV Shows</a>
            <a href="/rescan" class="rescan-btn">🔄 Re-scan Folders</a>
        </div>
    </nav>
    {{ body_content | safe }}
</body>
</html>
"""

@app.route('/')
@app.route('/category/<cat>')
def home(cat='movies'):
    # Check if we need to scan for the first time
    if not media_cache[cat if cat in media_cache else 'movies']:
        media_cache['movies'] = scan_files(PATHS['movies'])
        media_cache['tv'] = scan_files(PATHS['tv'])
    
    current_list = media_cache.get(cat, media_cache['movies'])
    featured = random.choice(current_list) if current_list else None
    meta = fetch_metadata(featured['name']) if featured else {}
    
    hero_html = ""
    if featured:
        hero_html = f"""
        <div class="hero" style="background-image: url('{meta.get('backdrop')}');">
            <div class="hero-overlay"></div>
            <div class="hero-content">
                <h1 style="font-size: 4rem; margin:0;">{meta.get('title')}</h1>
                <p style="font-size: 1.2rem; margin: 20px 0;">{meta.get('desc')}</p>
                <a href="/play/{cat}/{featured['path']}" style="background:white; color:black; padding:12px 30px; border-radius:4px; font-weight:bold; text-decoration:none;">▶ Play</a>
            </div>
        </div>"""
    
    grid_html = '<div class="grid">'
    for m in current_list:
        m_meta = fetch_metadata(m['name'])
        grid_html += f'<a href="/play/{cat}/{m["path"]}" class="card"><img src="{m_meta["poster"]}"><div class="info">{m_meta["title"]}</div></a>'
    grid_html += '</div>'

    return render_template_string(BASE_HTML, body_content=hero_html + grid_html)

@app.route('/play/<cat>/<path:filename>')
def play(cat, filename):
    saved_time = 0
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute('SELECT seconds FROM progress WHERE filename = ?', (filename,)).fetchone()
        if row: saved_time = row[0]

    content = f"""
    <div style="padding-top: 100px; width: 80%; margin: 0 auto;">
        <video id="v" style="width:100%;" controls autoplay><source src="/stream/{cat}/{filename}"></video>
        <h2>{os.path.basename(filename)}</h2>
    </div>
    <script>
        const v = document.getElementById('v');
        v.currentTime = {saved_time};
        setInterval(() => {{
            if (!v.paused) {{
                fetch('/save_progress', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ filename: "{filename}", seconds: v.currentTime }})
                }});
            }}
        }}, 5000);
    </script>"""
    return render_template_string(BASE_HTML, body_content=content)

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
