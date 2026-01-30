import os
import requests
import random
import sqlite3
from flask import Flask, render_template_string, send_from_directory, request, jsonify

app = Flask(__name__)

# --- CONFIGURATION ---
TMDB_API_KEY = "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiJiMTE3OWQ4YTVlZGM4NWI4ZGE5M2E1MTBkOTI2NTc5OCIsIm5iZiI6MTc2OTc1MjI0OC40MjgsInN1YiI6IjY5N2M0NmI4ZWFlYzRiMGRhZmY5NWQ3YSIsInNjb3BlcyI6WyJhcGlfcmVhZCJdLCJ2ZXJzaW9uIjoxfQ.eGjm5dKGiOOAVXA4MK80q4z0Bb8Dyo0ZW-w-q6F_erQ" 
DB_PATH = '/config/vaultstream.db'
PATHS = {'movies': '/movies', 'tv': '/tv'}

def init_db():
    if not os.path.exists('/config'): os.makedirs('/config')
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS progress (filename TEXT PRIMARY KEY, seconds REAL)')
init_db()

# --- MODERN CINEMATIC UI ---
BASE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VaultStream</title>
    <style>
        :root { --primary: #e50914; --bg: #080808; --card-bg: #141414; --text: #ffffff; --nav-bg: rgba(8, 8, 8, 0.9); }
        body { background: var(--bg); color: var(--text); font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; margin: 0; padding: 0; overflow-x: hidden; }
        
        /* Navigation */
        nav { background: var(--nav-bg); height: 70px; display: flex; align-items: center; padding: 0 4%; position: fixed; width: 100%; z-index: 1000; transition: background 0.3s; box-sizing: border-box;}
        .logo { color: var(--primary); font-size: 1.8rem; font-weight: bold; text-decoration: none; margin-right: 40px; letter-spacing: 1px; }
        .nav-links { display: flex; gap: 20px; flex-grow: 1; }
        .nav-links a { color: #e5e5e5; text-decoration: none; font-size: 0.9rem; transition: color 0.3s; }
        .nav-links a:hover { color: #b3b3b3; }
        
        .search-container { display: flex; align-items: center; background: rgba(255,255,255,0.1); border: 1px solid #333; padding: 5px 15px; border-radius: 20px; }
        .search-container input { background: transparent; border: none; color: white; outline: none; padding: 5px; width: 150px; }

        /* Hero Banner */
        .hero { height: 85vh; background-size: cover; background-position: center top; display: flex; align-items: center; position: relative; padding: 0 4%; }
        .hero-overlay { position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: linear-gradient(to right, var(--bg) 10%, transparent 60%), linear-gradient(to top, var(--bg) 5%, transparent 40%); }
        .hero-content { position: relative; z-index: 2; max-width: 650px; }
        .hero-title { font-size: 4.5rem; margin: 0; font-weight: bold; line-height: 1.1; }
        .hero-desc { font-size: 1.2rem; margin: 25px 0; color: #d2d2d2; line-height: 1.5; text-shadow: 1px 1px 2px black; }
        .btn-play { background: white; color: black; padding: 12px 35px; border-radius: 4px; font-weight: bold; text-decoration: none; font-size: 1.1rem; display: inline-flex; align-items: center; gap: 10px; }
        .btn-play:hover { background: rgba(255,255,255,0.75); }

        /* Rows & Grids */
        .row { padding: 40px 4% 0 4%; }
        .row-title { font-size: 1.4rem; font-weight: bold; margin-bottom: 20px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 15px; }
        .card { position: relative; aspect-ratio: 2/3; border-radius: 4px; overflow: hidden; transition: transform 0.4s ease; cursor: pointer; background: #222; }
        .card:hover { transform: scale(1.08); z-index: 10; box-shadow: 0 10px 20px rgba(0,0,0,0.5); }
        .card img { width: 100%; height: 100%; object-fit: cover; }
        
        /* Video Player Wrapper */
        .player-container { padding-top: 80px; width: 90%; margin: 0 auto; text-align: center; }
        video { width: 100%; border-radius: 8px; box-shadow: 0 0 50px rgba(0,0,0,0.8); background: black; }
    </style>
</head>
<body>
    <nav>
        <a href="/" class="logo">VAULTSTREAM</a>
        <div class="nav-links">
            <a href="/category/movies">Movies</a>
            <a href="/category/tv">TV Shows</a>
        </div>
        <form action="/" method="GET" class="search-container">
            <input type="text" name="search" placeholder="Titles, genres...">
        </form>
    </nav>
    {{ body_content | safe }}
</body>
</html>
"""

def fetch_metadata(name):
    url = f"https://api.themoviedb.org/3/search/multi?query={name}"
    headers = {"Authorization": f"Bearer {TMDB_API_KEY}", "accept": "application/json"}
    try:
        r = requests.get(url, headers=headers).json()
        if r.get('results'):
            res = r['results'][0]
            return {
                'title': res.get('title') or res.get('name'),
                'poster': f"https://image.tmdb.org/t/p/w500{res.get('poster_path')}" if res.get('poster_path') else "",
                'backdrop': f"https://image.tmdb.org/t/p/original{res.get('backdrop_path')}" if res.get('backdrop_path') else "",
                'desc': res.get('overview', 'Explore this title in your private vault.')
            }
    except Exception as e: print(f"Meta Error: {e}")
    return {'title': name, 'poster': '', 'backdrop': '', 'desc': 'No description available.'}

def scan_files(path):
    results = []
    if not os.path.exists(path): return []
    for root, _, files in os.walk(path):
        for f in files:
            if f.endswith(('.mp4', '.mkv', '.webm')):
                rel = os.path.relpath(os.path.join(root, f), path)
                results.append({'name': os.path.splitext(f)[0], 'path': rel})
    return results

@app.route('/')
@app.route('/category/<cat>')
def home(cat='movies'):
    search_query = request.args.get('search', '').lower()
    
    # Define which folder to scan
    scan_path = PATHS.get(cat, PATHS['movies'])
    all_media = scan_files(scan_path)
    
    if search_query:
        all_media = [m for m in all_media if search_query in m['name'].lower()]

    # Pick Hero Movie (Random from filtered list)
    featured = random.choice(all_media) if all_media else None
    meta = fetch_metadata(featured['name']) if featured else {}
    
    hero_html = ""
    if featured and not search_query:
        hero_html = f"""
        <div class="hero" style="background-image: url('{meta.get('backdrop')}');">
            <div class="hero-overlay"></div>
            <div class="hero-content">
                <h1 class="hero-title">{meta.get('title')}</h1>
                <p class="hero-desc">{meta.get('desc')}</p>
                <a href="/play/{cat}/{featured['path']}" class="btn-play"><span>▶</span> Play Now</a>
            </div>
        </div>
        """
    
    # Build Grid
    grid_title = "Browse All" if not search_query else f"Results for '{search_query}'"
    grid_html = f'<div class="row"><div class="row-title">{grid_title}</div><div class="grid">'
    for m in all_media:
        m_meta = fetch_metadata(m['name'])
        grid_html += f"""
        <a href="/play/{cat}/{m['path']}" class="card">
            <img src="{m_meta['poster']}" alt="{m['name']}">
        </a>"""
    grid_html += '</div></div>'

    return render_template_string(BASE_HTML, body_content=hero_html + grid_html)

@app.route('/play/<cat>/<path:filename>')
def play(cat, filename):
    saved_time = 0
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute('SELECT seconds FROM progress WHERE filename = ?', (filename,)).fetchone()
        if row: saved_time = row[0]

    content = f"""
    <div class="player-container">
        <video id="v" controls autoplay>
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
    </script>
    """
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
