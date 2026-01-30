import re

def extract_year(text):
    # Searches for a 4-digit number starting with 19 or 20
    match = re.search(r'\b(19|20)\d{2}\b', text)
    return match.group(0) if match else None

def clean_filename(name):
    year = extract_year(name)
    if year:
        name = name.replace(year, '')
    
    name = name.lower()
    name = re.sub(r'\(.*?\)|\[.*?\]', '', name)
    junk = [r'1080p', r'1400mb', r'720p', r'4k', r'2160p', r'bluray', r'bdrip', r'brrip', r'dvdrip', r'webrip', r'web-rip', r'hdtv', r'remux', r'sd', r'hd', r'480p', r'576p', r'web-dl', r'webdl', r'pdtv', r'x264', r'x265', r'h264', r'h265', r'hevc', r'10bit', r'avc', r'vc1', r'xvid', r'divx', r'aac', r'dts', r'dd5\.1', r'ac3', r'dts-hd', r'truehd', r'atmos', r'eac3', r'mp3', r'dual-audio', r'multi', r'dubbed', r'subbed', r'ddp5\.1', r'ddp2\.0', r'flac', r'opus', r'yify', r'yts', r'rarbg', r'psa', r'galaxyrg', r'tgx', r'evo', r'tigole', r'qxr', r'sartre', r'ion10', r'ettv', r'juggs', r'vppv', r'ozlem', r'nitro', r'amiable', r'megusta', r'amzn', r'netflix', r'nf', r'dnp', r'dsnp', r'hmax', r'hbo', r'atvp', r'apple tv', r'itunes', r'hulu', r'repack', r'proper', r'extended', r'unrated', r'directors cut', r'hc', r'korsub', r'sub', r'internal', r'limited', r'retail', r'hdr', r'dv', r'dovi', r'gaz']
    for word in junk:
        name = re.sub(fr'\b{word}\b', '', name)
    
    name = re.sub(r'[\._-]', ' ', name)
    name = re.sub(r'\b(19|20)\d{2}\b', '', name)
    return re.sub(r'\s+', ' ', name).strip().title()

def extract_tv_info(filename):
    standard = re.search(r'[sS](\d+)[eE](\d+)', filename)
    if standard:
        return int(standard.group(1)), int(standard.group(2))
    
    date_match = re.search(r'(\d{4}[.\-\s]\d{2}[.\-\s]\d{2})|(\d{2}[.\-\s]\d{2}[.\-\s]\d{4})', filename)
    if date_match:
        return None, date_match.group(0) 
    
    multi = re.search(r'[sS](\d+)[eE](\d+)-[eE](\d+)', filename)
    if multi:
        return int(multi.group(1)), int(multi.group(2))
    
    return None, None
