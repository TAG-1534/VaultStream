import os
import threading
from flask import Flask, render_template_string, send_from_directory, request, jsonify
from config import DB_PATH, PATHS
from sync import sync_worker, get_db

app = Flask(__name__)
sync_status = {"total": 0, "current": 0, "active": False}

def init_db():
    if not os.path.exists('/config'): os.makedirs('/config', exist_ok=True)
    conn = get_db()
    conn.execute('CREATE TABLE IF NOT EXISTS progress (filename TEXT PRIMARY KEY, seconds REAL)')
    conn.execute('''CREATE TABLE IF NOT EXISTS metadata 
                    (filename TEXT PRIMARY KEY, category TEXT, path TEXT, title TEXT, 
                     poster TEXT, backdrop TEXT, desc TEXT, series_title TEXT, 
                     season INTEGER, season_poster TEXT)''')
    conn.close()

init_db()

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
        .back-btn { display: inline-block; margin-bottom: 20px; color: var(--primary); text-decoration: none; }
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
        
        let lastCount = 0;
        setInterval(() => {
            fetch('/api/count').then(r => r.json()).then(data => {
                if (lastCount > 0 && data.count > lastCount) { location.reload(); }
                lastCount = data.count;
            });
        }, 5000);
    </script>
</body>
</html>
"""

@app.route('/')
@app.route('/category/<cat>')
def home(cat='movies'):
    conn = get_db()
    if cat == 'tv':
        rows = conn.execute('SELECT series_title, MAX(poster) FROM metadata WHERE category="tv" GROUP BY series_title').fetchall()
    else:
        rows = conn.execute('SELECT filename, path, title, poster FROM metadata WHERE category="movies"').fetchall()
    conn.close()

    grid = '<div class="grid">'
    for r in rows:
        if cat == 'tv':
            grid += f'<a href="/series/{r[0]}" class="card"><img src="{r[1]}"><div class="card-info"><span class="card-title">{r[0]}</span></div></a>'
        else:
            grid += f'<a href="/play/movies/{r[1]}" class="card"><img src="{r[3]}"><div class="card-info"><span class="card-title">{r[2]}</span></div></a>'
    return render_template_string(BASE_HTML, body_content=grid + '</div>')

@app.route('/series/<path:series_name>')
def series_view(series_name):
    conn = get_db()
    seasons = conn.execute('SELECT season, MAX(season_poster) FROM metadata WHERE series_title = ? GROUP BY season ORDER BY season ASC', (series_name,)).fetchall()
    conn.close()
    html = f'<a href="/category/tv" class="back-btn">← Back</a><h1>{series_name}</h1><div class="grid">'
    for s_num, s_poster in seasons:
        label = f"Season {s_num}" if s_num > 0 else "Specials"
        html += f'<a href="/series/{series_name}/season/{s_num}" class="card"><img src="{s_poster}"><div class="card-info"><span class="card-title">{label}</span></div></a>'
    return render_template_string(BASE_HTML, body_content=html + '</div>')

@app.route('/series/<path:series_name>/season/<int:s_num>')
def season_view(series_name, s_num):
    conn = get_db()
    eps = conn.execute('SELECT filename, path, title, poster FROM metadata WHERE series_title = ? AND season = ?', (series_name, s_num)).fetchall()
    conn.close()
    html = f'<a href="/series/{series_name}" class="back-btn">← Back</a><h1>{series_name} - Season {s_num}</h1><div class="grid tv-grid">'
    for e in eps:
        html += f'<a href="/play/tv/{e[1]}" class="card tv-card"><img src="{e[3]}"><div class="card-info"><span class="card-title">{e[2]}</span></div></a>'
    return render_template_string(BASE_HTML, body_content=html + '</div>')

@app.route('/api/count')
def get_count():
    conn = get_db()
    count = conn.execute('SELECT COUNT(*) FROM metadata').fetchone()[0]
    conn.close()
    return jsonify(count=count)

@app.route('/sync')
def sync():
    if not sync_status["active"]:
        threading.Thread(target=sync_worker, args=(sync_status,)).start()
    return jsonify(status="started")

@app.route('/sync_progress')
def get_progress():
    return jsonify(sync_status)

@app.route('/play/<cat>/<path:filename>')
def play(cat, filename):
    return render_template_string(BASE_HTML, body_content=f'<video controls autoplay style="width:100%"><source src="/stream/{cat}/{filename}"></video>')

@app.route('/stream/<cat>/<path:filename>')
def stream(cat, filename):
    return send_from_directory(PATHS.get(cat), filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
