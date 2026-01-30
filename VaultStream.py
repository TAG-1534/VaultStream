import os
from flask import Flask, render_template_string, send_from_directory

app = Flask(__name__)
MOVIES_DIR = '/movies'

# Premium VaultStream UI
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VaultStream | Private Collection</title>
    <style>
        body { background-color: #0a0a0a; color: #e0e0e0; font-family: 'Segoe UI', Roboto, Helvetica, sans-serif; margin: 0; padding: 40px; }
        header { border-bottom: 2px solid #333; margin-bottom: 30px; padding-bottom: 10px; }
        h1 { color: #ffffff; font-size: 2.5rem; letter-spacing: 2px; text-transform: uppercase; margin: 0; }
        span.brand { color: #007bff; } /* A subtle blue 'Vault' accent */
        .movie-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 30px; }
        .vault-card { background: #1a1a1a; border: 1px solid #333; border-radius: 12px; overflow: hidden; transition: all 0.3s ease; }
        .vault-card:hover { transform: translateY(-10px); border-color: #007bff; box-shadow: 0 10px 20px rgba(0,0,0,0.5); }
        video { width: 100%; display: block; background: #000; }
        .metadata { padding: 15px; background: #1a1a1a; font-size: 0.9rem; font-weight: 500; text-align: center; }
    </style>
</head>
<body>
    <header>
        <h1>Vault<span class="brand">Stream</span></h1>
    </header>
    <div class="movie-grid">
        {% for movie in movies %}
        <div class="vault-card">
            <video controls preload="metadata">
                <source src="/stream/{{ movie }}" type="video/mp4">
            </video>
            <div class="metadata">{{ movie }}</div>
        </div>
        {% endfor %}
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    files = [f for f in os.listdir(MOVIES_DIR) if f.endswith(('.mp4', '.mkv', '.webm'))]
    return render_template_string(HTML_TEMPLATE, movies=files)

@app.route('/stream/<path:filename>')
def stream_video(filename):
    return send_from_directory(MOVIES_DIR, filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True)