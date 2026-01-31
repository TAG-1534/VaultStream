import os
import requests
import sqlite3
import re
from config import TMDB_API_KEY, DB_PATH, PATHS
from helpers import clean_filename, extract_tv_info, extract_year

def get_db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    """Helper to create the table structure after deletion"""
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS metadata (
            filename TEXT PRIMARY KEY,
            category TEXT,
            path TEXT,
            title TEXT,
            poster TEXT,
            backdrop TEXT,
            description TEXT,
            series_title TEXT,
            season INTEGER,
            season_poster TEXT
        )
    ''')
    conn.commit()
    conn.close()

def sync_worker(status_dict):
    # --- NEW: DELETE OLD DATABASE ---
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
            print(">>> Database deleted for fresh sync.")
        except Exception as e:
            print(f">>> Could not delete database: {e}")
    
    # Re-initialize the table structure
    init_db()
    
    status_dict["active"] = True
    status_dict["current"] = 0
    all_files = []
    
    # (Rest of your file scanning logic)
    for cat, base_path in PATHS.items():
        if os.path.exists(base_path):
            for root, _, files in os.walk(base_path):
                for f in files:
                    if f.lower().endswith(('.mp4', '.mkv', '.webm', '.avi')):
                        all_files.append((cat, base_path, root, f))
    
    status_dict["total"] = len(all_files)
    headers = {"Authorization": f"Bearer {TMDB_API_KEY}", "accept": "application/json"}
    conn = get_db()

    for cat, base_path, root, f in all_files:
       for cat, base_path, root, f in all_files:
        fname_no_ext = os.path.splitext(f)[0]
        # Calculate the path relative to the category root (e.g., /tv/)
        rel_path = os.path.relpath(os.path.join(root, f), base_path)
        path_parts = rel_path.split(os.sep)

        # Default state variables
        display_title = clean_filename(fname_no_ext)
        main_poster = ""
        series_main_poster = ""
        season_poster = ""
        desc = ""
        s_num = 1
        series_title = "Unknown"

        # --- MOVIE LOGIC (Search by Filename) ---
        if cat == "movies":
            search_year = extract_year(fname_no_ext)
            search_query = clean_filename(fname_no_ext)
            series_title = search_query
            
            try:
                url = f"https://api.themoviedb.org/3/search/movie?query={search_query}"
                if search_year: url += f"&year={search_year}"
                
                r = requests.get(url, headers=headers).json()
                if r.get('results'):
                    res = r['results'][0]
                    display_title = res.get('title')
                    series_title = display_title
                    main_poster = f"https://image.tmdb.org/t/p/w500{res.get('poster_path')}"
                    series_main_poster = main_poster
                    season_poster = main_poster
            except: pass

        # --- TV LOGIC ---
        else:
            series_title_folder = path_parts[0] 
            series_query = clean_filename(series_title_folder)
            
            try:
                s_search = requests.get(f"https://api.themoviedb.org/3/search/tv?query={series_query}", headers=headers).json()
                
                if s_search.get('results'):
                    s_res = s_search['results'][0]
                    tid = s_res['id']
                    series_title = s_res.get('name') 
                    series_main_poster = f"https://image.tmdb.org/t/p/w500{s_res.get('poster_path')}"
                    
                    # 1. Capture S/E from that specific filename example
                    s_idx, e_idx = extract_tv_info(f)
                    
                    # 2. Logic: If filename has S03, s_num is 3. 
                    # If not, check folder. If not, default to 1.
                    if s_idx is not None:
                        s_num = s_idx
                    else:
                        parent_folder = path_parts[-2] if len(path_parts) > 1 else ""
                        folder_match = re.search(r'Season\s*(\d+)', parent_folder, re.I)
                        s_num = int(folder_match.group(1)) if folder_match else 1

                    # WATCH YOUR TERMINAL: It should now say "Detected Season: 3"
                    print(f">>> {series_title} | S{s_num} | E{e_idx} | File: {f}")

                    # 3. Fetch Tier 2 & 3 Metadata
                    s_r = requests.get(f"https://api.themoviedb.org/3/tv/{tid}/season/{s_num}", headers=headers).json()
                    season_poster = f"https://image.tmdb.org/t/p/w500{s_r.get('poster_path')}" if s_r.get('poster_path') else series_main_poster
                    
                    if s_idx is not None and e_idx is not None:
                        ep_r = requests.get(f"https://api.themoviedb.org/3/tv/{tid}/season/{s_idx}/episode/{e_idx}", headers=headers).json()
                        if 'id' in ep_r:
                            display_title = f"{series_title} - S{s_idx:02d}E{e_idx:02d} - {ep_r.get('name')}"
                            desc = ep_r.get('overview')
                            main_poster = f"https://image.tmdb.org/t/p/w500{ep_r.get('still_path')}" if ep_r.get('still_path') else season_poster
                        else:
                            display_title = f"{series_title} - S{s_idx:02d}E{e_idx:02d}"
                            main_poster = season_poster
                    else:
                        main_poster = season_poster
                else:
                    series_title = series_query
            except Exception as e:
                print(f"TV Sync Error: {e}")

        # Final safety checks for image URLs
        if not main_poster: main_poster = f"https://via.placeholder.com/500x750?text={series_title}"
        if not series_main_poster: series_main_poster = main_poster
        if not season_poster: season_poster = main_poster

        conn.execute('INSERT OR REPLACE INTO metadata VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', 
                    (fname_no_ext, cat, rel_path, display_title, main_poster, series_main_poster, desc, series_title, s_num, season_poster))
        conn.commit()
        status_dict["current"] += 1
        
    conn.close()
    status_dict["active"] = False
