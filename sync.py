import os
import requests
import sqlite3
import re
from config import TMDB_API_KEY, DB_PATH, PATHS
from helpers import clean_filename, extract_tv_info

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

        # Identify Show/Movie Folder
        series_folder = path_parts[0] if len(path_parts) > 1 else fname_no_ext
        
        # Identify Season
        s_num = 1
        if len(path_parts) > 2:
            s_match = re.search(r'(\d+)', path_parts[1])
            s_num = int(s_match.group(1)) if s_match else 1
            if "special" in path_parts[1].lower(): s_num = 0

        # --- REFINED SEARCH LOGIC ---
        # 1. Try to find a year in the folder name (e.g., "Deadpool (2016)")
        year_match = re.search(r'\b(19|20)\d{2}\b', series_folder)
        search_year = year_match.group(0) if year_match else None
        
        # 2. Clean the folder name for searching
        search_query = clean_filename(series_folder)
        
        display_title = clean_filename(fname_no_ext)
        series_title = search_query
        main_poster = f"https://via.placeholder.com/500x750?text={series_title}"
        season_poster = main_poster
        desc = ""

        try:
            search_type = "tv" if cat == "tv" else "movie"
            url = f"https://api.themoviedb.org/3/search/{search_type}?query={search_query}"
            if search_year:
                url += f"&year={search_year}" if cat == "movie" else f"&first_air_date_year={search_year}"
            
            r = requests.get(url, headers=headers).json()
            
            if r.get('results'):
                # We take the first result, which is much more likely to be correct now
                res = r['results'][0]
                tid = res['id']
                series_title = res.get('name') or res.get('title')
                main_poster = f"https://image.tmdb.org/t/p/w500{res.get('poster_path')}"
                
                if cat == "tv":
                    # Get Season Poster
                    s_r = requests.get(f"https://api.themoviedb.org/3/tv/{tid}/season/{s_num}", headers=headers).json()
                    if s_r.get('poster_path'):
                        season_poster = f"https://image.tmdb.org/t/p/w500{s_r.get('poster_path')}"

                    # Get Episode Detail
                    s_idx, e_idx = extract_tv_info(f)
                    if s_idx is not None:
                        ep_r = requests.get(f"https://api.themoviedb.org/3/tv/{tid}/season/{s_idx}/episode/{e_idx}", headers=headers).json()
                        if 'id' in ep_r:
                            display_title = f"{series_title} - S{s_idx:02d}E{e_idx:02d} - {ep_r.get('name')}"
                            desc = ep_r.get('overview')
                            if ep_r.get('still_path'):
                                main_poster = f"https://image.tmdb.org/t/p/w500{ep_r.get('still_path')}"
                            else:
                                main_poster = season_poster
                        else:
                            display_title = f"{series_title} - S{s_idx:02d}E{e_idx:02d}"
                            main_poster = season_poster
        except Exception as e:
            print(f"Error syncing {f}: {e}")

        conn.execute('INSERT OR REPLACE INTO metadata VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', 
                    (fname_no_ext, cat, rel_path, display_title, main_poster, "", desc, series_title, s_num, season_poster))
        conn.commit()
        status_dict["current"] += 1
    
    conn.close()
    status_dict["active"] = False
