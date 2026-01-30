import os
import requests
import random
import sqlite3
import re
from flask import Flask, render_template_string, send_from_directory, request, jsonify, redirect, url_for

app = Flask(__name__)

# --- CONFIGURATION ---
TMDB_API_KEY = "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiJiMTE3OWQ4YTVlZGM4NWI4ZGE5M2E1MTBkOTI2NTc5OCIsIm5iZiI6MTc2OTc1MjI0OC40MjgsInN1YiI6IjY5N2M0NmI4ZWFlYzRiMGRhZmY5NWQ3YSIsInNjb3BlcyI6WyJhcGlfcmVhZCJdLCJ2ZXJzaW9uIjoxfQ.eGjm5dKGiOOAVXA4MK80q4z0Bb8Dyo0ZW-w-q6F_erQ" 
DB_PATH = '/config/vaultstream.db'
PATHS = {'movies': '/movies', 'tv': '/tv'}

# Initialize Database for Progress and Metadata Caching
def init_db():
    if not os.path.exists('/config'): os.makedirs('/config')
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS progress (filename TEXT PRIMARY KEY, seconds REAL)')
        conn.execute('''CREATE TABLE IF NOT EXISTS metadata 
                        (filename TEXT PRIMARY KEY, title TEXT, poster TEXT, backdrop TEXT, desc TEXT)''')
init_db()

# --- HELPER FUNCTIONS ---
def clean_filename(name):
    name = re.sub(r'\(.*?\)|\[.*?\]', '', name)
    junk = ['1080p', '720p', '4k', 'bluray', 'x264', 'x265', 'h264', 'webrip', 'dvdrip', 'multi']
    for word in junk:
        name = re.sub(f'(?i){word}', '', name)
    return name.replace('.', ' ').replace('_', ' ').strip()

def get_cached_metadata(filename):
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute('SELECT title, poster, backdrop, desc FROM metadata WHERE filename = ?', (filename,)).fetchone()
        if row:
            return {'title': row[0], 'poster': row[1], 'backdrop': row[2], 'desc': row[3]}
    
    # Fetch and Cache if not found
    clean_name = clean_filename(filename)
    url = f"https://api.themoviedb.org/3/search/multi?query={clean_name}"
    headers = {"Authorization": f"Bearer {TMDB_API_KEY}", "accept": "application/json"}
    meta = {'title': filename, 'poster': "https://via.placeholder.com/500x750?text=No+Poster", 'backdrop': '', 'desc': 'No description available.'}
    
    try:
        r = requests.get(url, headers=headers, timeout=3).json()
        if r.get('results'):
            res = r['results'][0]
            meta = {
                'title': res.get('title') or res.get('name') or filename,
                'poster': f"https://image.tmdb.org/t/p/w500{res.get('poster_path')}" if res.get('poster_path') else meta['poster'],
                'backdrop': f"https://image.tmdb.org/t/p/original{res.get('backdrop_path')}" if res.get('backdrop_path') else "",
                'desc': res.get('overview', meta['desc'])
            }
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute('INSERT OR REPLACE INTO metadata VALUES (?, ?, ?, ?, ?)', 
                             (filename, meta['title'], meta['poster'], meta['backdrop'], meta['desc']))
    except: pass
    return meta

def scan_files(path):
    results = []
    if not os.path.exists(path): return []
    for root, _, files in os.walk(path):
        for f in files:
            if f.lower().endswith(('.mp4', '.mkv', '.webm')):
                rel = os.path.relpath(os.path.join(root, f), path)
                results.append({'name': os.path.splitext(f)[0], 'path': rel})
    return results

# --- MODERN STYLES ---
BASE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>VaultStream</title>
    <style>
        :root { --primary: #e50914; --bg: #080808; --text: #fff; }
        body { background: var(--bg); color: var(--text); font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; margin: 0; padding: 0; overflow-x: hidden; }
        nav { background: rgba(0,0,0,0.9); height: 70px; display: flex; align-items: center; padding: 0 4%; position: fixed; width: 100%; z-index: 1000; box-sizing: border-box; border-bottom: 1px solid #222;}
        .logo { color: var(--primary); font-size: 1.8rem; font-weight: bold; text-decoration: none; margin-right: 40px; }
        .nav-links { display: flex; gap: 20px; flex-grow: 1; align-items: center; }
        .nav-links a { color: #e5e5e5; text-decoration: none; font-size: 0.9rem; transition: 0.3s; }
        .nav-links a:hover { color: var(--primary); }
        .btn-sync { background: #333; color: white; border: none; padding: 8px 15px; border-radius: 4px; cursor: pointer; text-decoration: none; font-size: 0.8rem; margin-left: auto;}
        
        .hero { height: 75vh; background-size: cover; background-position: center top; display: flex; align-items: center; position: relative; padding: 0 4%; }
        .hero-overlay { position: absolute; top:0; left:0; width:100%; height:100%; background: linear-gradient(to top, var(--bg), transparent 70%), linear-gradient(to right, var(--bg) 20%, transparent 80%); }
        .hero-content { position: relative; z-index: 2; max-width: 700px; }
        
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 20px; padding: 40px 4%; }
        .card { border-radius: 4px; overflow: hidden; transition: 0.4s; cursor: pointer; text-decoration: none; color: inherit; background: #141414; position: relative; }
        .card:hover { transform: scale(1.08); z-index: 10; box-shadow: 0 10px 20px rgba(0,0,0,0.8); }
        .card img { width: 100%; aspect-ratio: 2/3; object-fit: cover; }
        .card-info { padding: 10px; font-size: 0.85rem; text-align: center; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;}
    </style>
</head>
<body>
    <nav>
        <a href="/" class="logo">VAULTSTREAM</a>
        <div class="nav-links">
            <a href="/category/movies">Movies</a>
            <a href="/category/tv">TV Shows</a>
            <a href="/rescan" class="btn-sync">🔄 Sync Library</a>
        </div>
    </nav>
    {{ body_content | safe }}
</body>
</html>
"""

# --- ROUTES ---
@app.route('/')
@app.route('/category/<cat>')
def home(cat='movies'):
    all_media = scan_files(PATHS.get(cat, PATHS['movies']))
    
    featured = random.choice(all_media) if all_media else None
    meta = get_cached_metadata(featured['name']) if featured else {}
    
    hero_html = ""
    if featured:
        hero_html = f"""
        <div class="hero" style="background-image: url('{meta.get('backdrop')}');">
            <div class="hero-overlay"></div>
            <div class="hero-content">
                <h1 style="font-size: 4rem; margin:0;">{meta.get('title')}</h1>
                <p style="font-size: 1.1rem; margin: 20px 0; color: #ccc;">{meta.get('desc')}</p>
                <a href="/play/{cat}/{featured['path']}" style="background:white; color:black; padding:12px 35px; border-radius:4px; font-weight:bold; text-decoration:none; font-size: 1.1rem;">▶ Play Now</a>
            </div>
        </div>"""
    
    grid_html = '<div class="grid">'
    for m in all_media:
        m_meta = get_cached_metadata(m['name'])
        grid_html += f'<a href="/play/{cat}/{m["path"]}" class="card"><img src="{m_meta["poster"]}"><div class="card-info">{m_meta["title"]}</div></a>'
    grid_html += '</div>'

    return render_template_string(BASE_HTML, body_content=hero_html + grid_html)

@app.route('/rescan')
def rescan():
    # Clearing metadata cache is optional, but rescanning is the main goal
    return redirect(url_for('home'))

@app.route('/play/<cat>/<path:filename>')
def play(cat, filename):
    saved_time = 0
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute('SELECT seconds FROM progress WHERE filename = ?', (filename,)).fetchone()
        if row: saved_time = row[0]

    content = f"""
    <div style="padding-top: 100px; width: 90%; margin: 0 auto; text-align:center;">
        <video id="v" style="width:100%; border-radius: 8px; background: black;" controls autoplay>
            <source src="/stream/{cat}/{filename}">
        </video>
        <h2 style="margin-top:20px;">{os.path.basename(filename)}</h2>
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
