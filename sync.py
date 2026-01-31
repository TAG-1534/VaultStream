import os
import requests
import sqlite3
import re
from config import TMDB_API_KEY, DB_PATH, PATHS
from helpers import clean_filename, extract_tv_info, extract_year

def get_db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def sync_worker(status_dict):
    status_dict["active"] = True
    status_dict["current"] = 0
    all_files = []
    
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
        fname_no_ext = os.path.splitext(f)[0]
        rel_path = os.path.relpath(os.path.join(root, f), base_path)
        path_parts = rel_path.split(os.sep)

        # 1. Identify Series/Movie (The Top Level Folder)
        series_folder = path_parts[0] if len(path_parts) > 1 else fname_no_ext
        search_year = extract_year(series_folder)
        search_query = clean_filename(series_folder)
        
        # 2. Extract S/E from FILENAME (Priority over folders)
        s_idx, e_idx = extract_tv_info(f)
        
        # Fallback to folder if filename doesn't have S00E00
        if s_idx is not None:
            s_num = s_idx
        else:
            parent_folder = path_parts[-2] if len(path_parts) > 1 else ""
            s_match = re.search(r'(\d+)', parent_folder)
            s_num = int(s_match.group(1)) if s_match else 1
            if "special" in parent_folder.lower(): s_num = 0

        # Defaults
        display_title = clean_filename(fname_no_ext)
        series_title = search_query
        main_poster = f"https://via.placeholder.com/500x750?text={series_title}"
        season_poster = main_poster
        desc = ""

        try:
            # Map 'movies' category to 'movie' for TMDB search
            tmdb_cat = "movie" if cat == "movies" else "tv"
            url = f"https://api.themoviedb.org/3/search/{tmdb_cat}?query={search_query}"
            if search_year:
                url += f"&year={search_year}" if tmdb_cat == "movie" else f"&first_air_date_year={search_year}"
            
            r = requests.get(url, headers=headers).json()
            
            if r.get('results'):
                res = r['results'][0]
                tid = res['id']
                series_title = res.get('name') or res.get('title')
                
                if res.get('poster_path'):
                    main_poster = f"https://image.tmdb.org/t/p/w500{res.get('poster_path')}"
                    season_poster = main_poster

                if cat == "tv":
                    # Get Season Poster
                    s_r = requests.get(f"https://api.themoviedb.org/3/tv/{tid}/season/{s_num}", headers=headers).json()
                    if s_r.get('poster_path'):
                        season_poster = f"https://image.tmdb.org/t/p/w500{s_r.get('poster_path')}"

                    # Final Rename if S/E found
                    if s_idx is not None:
                        ep_r = requests.get(f"https://api.themoviedb.org/3/tv/{tid}/season/{s_idx}/episode/{e_idx}", headers=headers).json()
                        if 'id' in ep_r:
                            display_title = f"{series_title} - S{s_idx:02d}E{e_idx:02d} - {ep_r.get('name')}"
                            desc = ep_r.get('overview')
                            main_poster = f"https://image.tmdb.org/t/p/w500{ep_r.get('still_path')}" if ep_r.get('still_path') else season_poster
                        else:
                            display_title = f"{series_title} - S{s_idx:02d}E{e_idx:02d}"
                            main_poster = season_poster
        except: pass

        conn.execute('INSERT OR REPLACE INTO metadata VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', 
                    (fname_no_ext, cat, rel_path, display_title, main_poster, "", desc, series_title, s_num, season_poster))
        conn.commit()
        status_dict["current"] += 1
    
    conn.close()
    status_dict["active"] = False
