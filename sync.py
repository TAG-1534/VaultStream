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

        # --- TV LOGIC (Refined Hierarchy) ---
        else:
            # The first folder inside your /tv/ directory is the Series Name
            series_title_folder = path_parts[0] 
            series_query = clean_filename(series_title_folder)
            
            try:
                # 1. Search TMDB for the Series
                s_search = requests.get(f"https://api.themoviedb.org/3/search/tv?query={series_query}", headers=headers).json()
                
                if s_search.get('results'):
                    s_res = s_search['results'][0]
                    tid = s_res['id']
                    series_title = s_res.get('name') 
                    series_main_poster = f"https://image.tmdb.org/t/p/w500{s_res.get('poster_path')}"
                    
                    # 2. Identify Season & Episode
                    s_idx, e_idx = extract_tv_info(f)
                    
                    # PRIORITY: Filename (S01E01) > Folder Name (Season 1)
                    if s_idx is not None:
                        s_num = s_idx
                    else:
                        # Look at the folder containing the file
                        parent_folder = path_parts[-2] if len(path_parts) > 1 else ""
                        s_match = re.search(r'(\d+)', parent_folder)
                        s_num = int(s_match.group(1)) if s_match else 1
                        if "special" in parent_folder.lower(): s_num = 0

                    # 3. Get Season Poster
                    s_url = f"https://api.themoviedb.org/3/tv/{tid}/season/{s_num}"
                    s_r = requests.get(s_url, headers=headers).json()
                    season_poster = f"https://image.tmdb.org/t/p/w500{s_r.get('poster_path')}" if s_r.get('poster_path') else series_main_poster
                    
                    # 4. Get Episode Detail
                    if s_idx is not None and e_idx is not None:
                        ep_url = f"https://api.themoviedb.org/3/tv/{tid}/season/{s_idx}/episode/{e_idx}"
                        ep_r = requests.get(ep_url, headers=headers).json()
                        if 'id' in ep_r:
                            display_title = f"{series_title} - S{s_idx:02d}E{e_idx:02d} - {ep_r.get('name')}"
                            desc = ep_r.get('overview')
                            main_poster = f"https://image.tmdb.org/t/p/w500{ep_r.get('still_path')}" if ep_r.get('still_path') else season_poster
                        else:
                            display_title = f"{series_title} - S{s_idx:02d}E{e_idx:02d}"
                            main_poster = season_poster
                    else:
                        display_title = f"{series_title} - {clean_filename(fname_no_ext)}"
                        main_poster = season_poster
                else:
                    # Fallback if TMDB fails
                    series_title = series_query
            except Exception as e:
                print(f"TV Sync Error for {series_query}: {e}")

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
