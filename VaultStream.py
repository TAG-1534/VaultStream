import os
import requests
import random
import sqlite3
from flask import Flask, render_template_string, send_from_directory, request, jsonify

app = Flask(__name__)

# CONFIGURATION
TMDB_API_KEY = "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiJiMTE3OWQ4YTVlZGM4NWI4ZGE5M2E1MTBkOTI2NTc5OCIsIm5iZiI6MTc2OTc1MjI0OC40MjgsInN1YiI6IjY5N2M0NmI4ZWFlYzRiMGRhZmY5NWQ3YSIsInNjb3BlcyI6WyJhcGlfcmVhZCJdLCJ2ZXJzaW9uIjoxfQ.eGjm5dKGiOOAVXA4MK80q4z0Bb8Dyo0ZW-w-q6F_erQ" 
DB_PATH = '/config/vaultstream.db'
PATHS = {'movies': '/movies', 'tv': '/tv', 'music': '/music'}

# Initialize SQLite Database for progress tracking
def init_db():
    if not os.path.exists('/config'):
        os.makedirs('/config')
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS progress (filename TEXT PRIMARY KEY, seconds REAL)')

init_db()

BASE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>VaultStream</title>
    <style>
        :root { --primary: #e50914; --bg: #141414; --card-bg: #1a1a1a; --text: #fff; }
        body { background: var(--bg); color: var(--text); font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; margin: 0; overflow-x: hidden; }
        nav { background: linear-gradient(to bottom, rgba(0,0,0,0.8), transparent); padding: 20px 50px; display: flex; align-items: center; position: fixed; width: 100%; z-index: 1000; box-sizing: border-box; }
        .logo { color: var(--primary); font-size: 1.8rem; font-weight: bold; text-decoration: none; margin-right: 30px; }
        .nav-links a { color: #e5e5e5; text-decoration: none; margin-right: 20px; font-size: 0.9rem; }
        
        /* Hero Section */
        .hero { height: 70vh; background-size: cover; background-position: center; display: flex; align-items: flex-end; padding: 50px; position: relative; }
        .hero-overlay { position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: linear-gradient(7deg, var(--bg) 10%, transparent 50%); }
        .hero-content { position: relative; z-index: 2; max-width: 800px; }
        .hero-title { font-size: 4rem; margin: 0; text-shadow: 2px 2px 4px rgba(0,0,0,0.5); }
        .hero-desc { font-size: 1.2rem; margin: 20px 0; color: #ccc; line-height: 1.4; }
        .btn-play { background: white; color: black; padding: 12px 30px; border-radius: 4px; font-weight: bold; text-decoration: none; display: inline-block; transition: 0.2s; }
        .btn-play:hover { background: #e6e6e6; }

        .container { padding: 40px 50px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 20px; }
        .card { transition: transform 0.3s; border-radius: 4px; overflow: hidden; cursor: pointer; text-decoration: none; color: inherit; background: var(--card-bg); }
        .card:hover { transform: scale(1.05); z-index: 10; }
        .poster { width: 100%; aspect-ratio: 2/3; object-fit: cover; }
        .info { padding: 10px; font-size: 0.8rem; }
    </style>
</head>
<body>
    <nav>
        <a href="/" class="logo">VAULTSTREAM</a>
        <div class="nav-links">
            <a href="/movies">Movies</a>
            <a href="/tv">TV Shows</a>
        </div>
    </nav>
    {{ body_content | safe }}
</body>
</html>
"""

def fetch_metadata(name):
    url = f"https://api.themoviedb.org/3/search/multi?query={name}&api_key={TMDB_API_KEY}"
    try:
        r = requests.get(url).json()
        if r['results']:
            res = r['results'][0]
            return {
                'title': res.get('title') or res.get('name'),
                'poster': f"https://image.tmdb.org/t/p/w500{res.get('poster_path')}",
                'backdrop': f"https://image.tmdb.org/t/p/original{res.get('backdrop_path')}",
                'desc': res.get('overview', 'No description available.')
            }
    except: pass
    return {'title': name, 'poster': '', 'backdrop': '', 'desc': ''}

@app.route('/')
def home():
    all_movies = []
    for root, dirs, files in os.walk(PATHS['movies']):
        for f in files:
            if f.endswith(('.mp4', '.mkv')):
                rel = os.path.relpath(os.path.join(root, f), PATHS['movies'])
                all_movies.append({'name': os.path.splitext(f)[0], 'path': rel})
    
    featured = random.choice(all_movies) if all_movies else None
    meta = fetch_metadata(featured['name']) if featured else {}
    
    hero_html = ""
    if featured:
        hero_html = f"""
        <div class="hero" style="background-image: url('{meta.get('backdrop')}');">
            <div class="hero-overlay"></div>
            <div class="hero-content">
                <h1 class="hero-title">{meta.get('title')}</h1>
                <p class="hero-desc">{meta.get('desc')}</p>
                <a href="/play/movies/{featured['path']}" class="btn-play">▶ Play</a>
            </div>
        </div>
        """
    
    grid_html = '<div class="container"><h2>Library</h2><div class="grid">'
    for m in all_movies:
        m_meta = fetch_metadata(m['name'])
        grid_html += f'<a href="/play/movies/{m["path"]}" class="card"><img class="poster" src="{m_meta["poster"]}"><div class="info">{m_meta["title"]}</div></a>'
    grid_html += '</div></div>'

    return render_template_string(BASE_HTML, body_content=hero_html + grid_html)

@app.route('/play/<cat>/<path:filename>')
def play(cat, filename):
    # Get saved progress
    saved_time = 0
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute('SELECT seconds FROM progress WHERE filename = ?', (filename,))
        row = cur.fetchone()
        if row: saved_time = row[0]

    video_player = f"""
    <div class="container" style="padding-top:100px;">
        <video id="videoPlayer" width="100%" controls autoplay>
            <source src="/stream/{cat}/{filename}" type="video/mp4">
        </video>
        <h3>Currently Playing: {filename}</h3>
    </div>
    <script>
        const video = document.getElementById('videoPlayer');
        const filename = "{filename}";
        
        // Resume from saved time
        video.currentTime = {saved_time};

        // Save progress every 5 seconds
        setInterval(() => {{
            if (!video.paused) {{
                fetch('/save_progress', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ filename: filename, seconds: video.currentTime }})
                }});
            }}
        }}, 5000);
    </script>
    """
    return render_template_string(BASE_HTML, body_content=video_player)

@app.route('/save_progress', methods=['POST'])
def save_progress():
    data = request.json
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('INSERT OR REPLACE INTO progress VALUES (?, ?)', (data['filename'], data['seconds']))
    return jsonify(success=True)

@app.route('/stream/<cat>/<path:filename>')
def stream(cat, filename):
    return send_from_directory(PATHS.get(cat), filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True)