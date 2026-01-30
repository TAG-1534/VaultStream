import os
from flask import Flask, render_template_string, send_from_directory

app = Flask(__name__)

# These match the volumes in your docker-compose.yml
PATHS = {
    'movies': '/movies',
    'tv': '/tv',
    'music': '/music'
}

BASE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>VaultStream</title>
    <style>
        :root { --primary: #007bff; --bg: #0a0a0a; --card-bg: #1a1a1a; --text: #e0e0e0; }
        body { background: var(--bg); color: var(--text); font-family: 'Helvetica Neue', Arial, sans-serif; margin: 0; }
        nav { background: rgba(0,0,0,0.9); padding: 15px 40px; display: flex; align-items: center; position: sticky; top: 0; z-index: 100; border-bottom: 1px solid #333; }
        .logo { color: white; font-size: 1.8rem; font-weight: bold; text-decoration: none; margin-right: 40px; }
        .logo span { color: var(--primary); }
        .nav-links a { color: #bbb; text-decoration: none; margin-right: 25px; font-weight: 500; transition: 0.3s; }
        .nav-links a:hover { color: white; }
        .active { color: white !important; border-bottom: 2px solid var(--primary); padding-bottom: 5px; }
        .container { padding: 40px; }
        h2 { margin-bottom: 20px; font-size: 1.5rem; text-transform: uppercase; letter-spacing: 1px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 25px; }
        .card { background: var(--card-bg); border-radius: 8px; overflow: hidden; transition: 0.3s; border: 1px solid #222; }
        .card:hover { transform: scale(1.03); border-color: var(--primary); }
        video, audio { width: 100%; background: #000; display: block; }
        .info { padding: 15px; text-align: center; font-size: 0.9rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    </style>
</head>
<body>
    <nav>
        <a href="/" class="logo">Vault<span>Stream</span></a>
        <div class="nav-links">
            <a href="/" class="{{ 'active' if page == 'home' }}">Home</a>
            <a href="/movies" class="{{ 'active' if page == 'movies' }}">Movies</a>
            <a href="/tv" class="{{ 'active' if page == 'tv' }}">TV Shows</a>
            <a href="/music" class="{{ 'active' if page == 'music' }}">Music</a>
        </div>
    </nav>
    <div class="container">
        {{ content | safe }}
    </div>
</body>
</html>
"""

def get_files(path, extensions):
    if not os.path.exists(path): return []
    return sorted([f for f in os.listdir(path) if f.endswith(extensions)])

@app.route('/')
def home():
    content = "<h2>Featured</h2><p>Welcome to VaultStream. Your library is ready.</p>"
    return render_template_string(BASE_HTML, content=content, page='home')

@app.route('/movies')
def movies_page():
    files = get_files(PATHS['movies'], ('.mp4', '.mkv', '.webm'))
    cards = "".join([f'<div class="card"><video controls preload="metadata"><source src="/stream/movies/{f}"></video><div class="info">{f}</div></div>' for f in files])
    return render_template_string(BASE_HTML, content=f"<h2>Movies</h2><div class='grid'>{cards}</div>", page='movies')

@app.route('/tv')
def tv_page():
    files = get_files(PATHS['tv'], ('.mp4', '.mkv', '.webm'))
    cards = "".join([f'<div class="card"><video controls preload="metadata"><source src="/stream/tv/{f}"></video><div class="info">{f}</div></div>' for f in files])
    return render_template_string(BASE_HTML, content=f"<h2>TV Shows</h2><div class='grid'>{cards}</div>", page='tv')

@app.route('/music')
def music_page():
    files = get_files(PATHS['music'], ('.mp3', '.wav', '.flac'))
    cards = "".join([f'<div class="card"><audio controls><source src="/stream/music/{f}"></audio><div class="info">{f}</div></div>' for f in files])
    return render_template_string(BASE_HTML, content=f"<h2>Music</h2><div class='grid'>{cards}</div>", page='music')

@app.route('/stream/<category>/<path:filename>')
def stream(category, filename):
    return send_from_directory(PATHS.get(category), filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True)