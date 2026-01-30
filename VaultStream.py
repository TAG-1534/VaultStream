import os
import threading
import sqlite3
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

# --- INSERT BASE_HTML HERE (Same as your provided code) ---
BASE_HTML = """...""" # Copy your BASE_HTML string here

@app.route('/')
@app.route('/category/<cat>')
def home(cat='movies'):
    conn = get_db()
    if cat == 'tv':
        rows = conn.execute('SELECT series_title, MAX(poster) FROM metadata WHERE category="tv" GROUP BY series_title').fetchall()
    else:
        rows = conn.execute('SELECT filename, path, title, poster FROM metadata WHERE category="movies"').fetchall()
    conn.close()
    # (Rest of home logic remains the same...)

@app.route('/sync')
def sync():
    if not sync_status["active"]:
        threading.Thread(target=sync_worker, args=(sync_status,)).start()
    return jsonify(status="started")

# (Rest of the routes: /series, /season, /api/count, /play, /stream, etc.)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
