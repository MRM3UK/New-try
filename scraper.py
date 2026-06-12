#!/usr/bin/env python3
"""
FIFA World Cup 2026 Match Scraper
- Finds WC matches by searching FIFA national team names on socolive
- Preserves manually added channels in worldcuptest.m3u
- Only removes auto-added channels after match ends
"""

import re
import os
import json
import time
import logging
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
import cloudscraper
from bs4 import BeautifulSoup

# ─── Configuration ───────────────────────────────────────────────────────────

BASE_URL = "https://socolive17.cv/truc-tiep/"
MATCH_PAGE_BASE = "https://socolive17.cv"
OUTPUT_FILE = "worldcuptest.m3u"

WORLD_CUP_LOGO = (
    "https://upload.wikimedia.org/wikipedia/en/thumb/1/17/"
    "2026_FIFA_World_Cup_emblem.svg/330px-2026_FIFA_World_Cup_emblem.svg.png"
)

# Tag to identify auto-added entries (invisible to IPTV players)
AUTO_TAG = "auto-added-wc2026"

# ─── ALL FIFA World Cup 2026 Qualified / Likely Teams ────────────────────────
# Using both English and Vietnamese names + common abbreviations

FIFA_TEAMS = [
    # Host nations
    "United States", "USA", "Hoa Kỳ", "Mỹ",
    "Canada", "Ca-na-đa",
    "Mexico", "México", "Mê-hi-cô",

    # South America
    "Argentina", "Ác-hen-ti-na",
    "Brazil", "Brasil", "Bra-xin",
    "Uruguay", "U-ru-guay",
    "Colombia", "Cô-lôm-bi-a",
    "Ecuador", "Ê-cu-a-đo",
    "Paraguay", "Pa-ra-guay",
    "Chile", "Chi-lê",
    "Peru", "Pê-ru",
    "Venezuela", "Vê-nê-zu-ê-la",
    "Bolivia", "Bô-li-vi-a",

    # Europe
    "Germany", "Deutschland", "Đức",
    "France", "Pháp",
    "Spain", "España", "Tây Ban Nha",
    "England", "Anh",
    "Portugal", "Bồ Đào Nha",
    "Netherlands", "Holland", "Hà Lan",
    "Belgium", "Bỉ",
    "Italy", "Italia", "Ý",
    "Croatia", "Hrvatska", "Croatia",
    "Serbia", "Séc-bi-a",
    "Switzerland", "Thụy Sĩ",
    "Denmark", "Danmark", "Đan Mạch",
    "Austria", "Áo",
    "Poland", "Ba Lan",
    "Ukraine", "Ukraina", "U-crai-na",
    "Turkey", "Türkiye", "Thổ Nhĩ Kỳ",
    "Sweden", "Thụy Điển",
    "Wales", "Xứ Wales",
    "Scotland", "Scotland",
    "Hungary", "Hung-ga-ri",
    "Czech Republic", "Czechia", "Séc",
    "Romania", "Ru-ma-ni",
    "Slovakia", "Xlô-va-ki-a",
    "Slovenia", "Xlô-ve-ni-a",
    "Greece", "Hy Lạp",
    "Norway", "Na Uy",
    "Finland", "Phần Lan",
    "Iceland", "Ai-xơ-len",
    "Ireland", "Ai-len",
    "Bosnia", "Bô-xni-a",
    "Albania", "An-ba-ni",
    "North Macedonia", "Bắc Macedonia",
    "Montenegro", "Mông-tê-nê-grô",
    "Georgia", "Gru-di-a",
    "Luxembourg", "Lúc-xăm-bua",
    "Kosovo", "Cô-xô-vô",

    # Africa
    "Morocco", "Maroc", "Ma-rốc",
    "Senegal", "Sê-nê-gan",
    "Nigeria", "Ni-giê-ri-a",
    "Cameroon", "Cameroun", "Ca-mơ-run",
    "Ghana", "Ga-na",
    "Egypt", "Ai Cập",
    "Algeria", "An-giê-ri",
    "Tunisia", "Tuy-ni-di",
    "Ivory Coast", "Côte d'Ivoire", "Bờ Biển Ngà",
    "South Africa", "Nam Phi",
    "DR Congo", "Congo", "Công-gô",
    "Mali", "Ma-li",
    "Burkina Faso",
    "Mozambique", "Mô-dăm-bích",
    "Tanzania", "Tan-da-ni-a",
    "Uganda", "U-gan-đa",
    "Benin", "Bê-nanh",
    "Zambia", "Dăm-bi-a",
    "Zimbabwe", "Dim-ba-bu-ê",
    "Cape Verde",

    # Asia
    "Japan", "Nhật Bản",
    "South Korea", "Korea Republic", "Hàn Quốc",
    "Iran", "I-ran",
    "Australia", "Úc",
    "Saudi Arabia", "Ả Rập Xê Út",
    "Qatar", "Ca-ta",
    "Iraq", "I-rắc",
    "Jordan", "Gioóc-đa-ni",
    "Uzbekistan", "U-dơ-bê-ki-xtan",
    "China", "China PR", "Trung Quốc",
    "UAE", "United Arab Emirates",
    "Oman", "Ô-man",
    "Bahrain", "Ba-ren",
    "Palestine", "Pa-le-xtin",
    "Vietnam", "Việt Nam",
    "Thailand", "Thái Lan",
    "Indonesia", "In-đô-nê-xi-a",
    "Malaysia", "Ma-lay-xi-a",
    "North Korea", "CHDCND Triều Tiên",
    "India", "Ấn Độ",
    "Kyrgyzstan",
    "Tajikistan",
    "Kuwait",

    # North/Central America & Caribbean
    "Costa Rica", "Cốt-xta Ri-ca",
    "Panama", "Pa-na-ma",
    "Honduras", "Hôn-đu-rát",
    "Jamaica", "Gia-mai-ca",
    "El Salvador",
    "Guatemala",
    "Trinidad", "Trinidad and Tobago",
    "Haiti", "Ha-i-ti",
    "Curaçao", "Curacao",
    "Suriname",

    # Oceania
    "New Zealand", "Niu Di-lân",
    "Fiji", "Fi-gi",
    "Solomon Islands",
    "Papua New Guinea",
    "Tahiti",
]

# Precompile lowercase set for fast lookup
FIFA_TEAMS_LOWER = set()
for team in FIFA_TEAMS:
    FIFA_TEAMS_LOWER.add(team.lower())
    # Also add without diacritics for matching
    clean = team.lower()
    FIFA_TEAMS_LOWER.add(clean)

# Match status keywords that indicate match is ENDED
ENDED_KEYWORDS = [
    "ft", "full time", "fulltime", "kết thúc",
    "ended", "finished", "final", "hết giờ",
    "pen", "aet", "after extra time",
]

# Match status keywords that indicate match is LIVE or UPCOMING
LIVE_KEYWORDS = [
    "live", "trực tiếp", "đang diễn ra", "đang đá",
    "1h", "2h", "ht", "half time", "hiệp 1", "hiệp 2",
    "sắp diễn ra", "chưa bắt đầu", "upcoming",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ─── Existing M3U Parser ────────────────────────────────────────────────────


def parse_existing_m3u(filepath):
    """
    Parse existing worldcuptest.m3u file.
    Returns two lists:
      - manual_entries: channels added by user (to KEEP always)
      - auto_entries: channels added by bot (may be removed if ended)
    Each entry = dict with 'extinf_line' and 'url_line'
    """
    manual_entries = []
    auto_entries = []

    if not os.path.exists(filepath):
        return manual_entries, auto_entries

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        logger.error(f"Error reading {filepath}: {e}")
        return manual_entries, auto_entries

    i = 0
    while i < len(lines):
        line = lines[i].rstrip("\n\r")

        # Skip headers and comments
        if line.startswith("#EXTM3U") or line.startswith("# "):
            i += 1
            continue

        # Skip empty lines
        if not line.strip():
            i += 1
            continue

        # Found an EXTINF line
        if line.startswith("#EXTINF"):
            extinf_line = line
            url_line = ""

            # Next non-empty line should be the URL
            j = i + 1
            while j < len(lines):
                next_line = lines[j].rstrip("\n\r").strip()
                if next_line and not next_line.startswith("#"):
                    url_line = next_line
                    break
                elif next_line.startswith("#EXTINF"):
                    break
                j += 1

            entry = {
                "extinf_line": extinf_line,
                "url_line": url_line,
            }

            # Check if this was auto-added by us
            if AUTO_TAG in extinf_line:
                auto_entries.append(entry)
            else:
                manual_entries.append(entry)

            i = j + 1 if url_line else i + 1
            continue

        i += 1

    logger.info(
        f"Existing M3U: {len(manual_entries)} manual, "
        f"{len(auto_entries)} auto-added entries"
    )
    return manual_entries, auto_entries


# ─── Scraper ─────────────────────────────────────────────────────────────────


def create_scraper_session():
    """Create a cloudscraper session with browser-like headers."""
    scraper = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "windows", "desktop": True}
    )
    scraper.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;"
                "q=0.9,image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
            "Referer": "https://socolive17.cv/",
            "DNT": "1",
            "Connection": "keep-alive",
        }
    )
    return scraper


def find_teams_in_text(text):
    """
    Find FIFA national team names in text.
    Returns list of matched team names.
    """
    text_lower = text.lower()
    found = []
    for team in FIFA_TEAMS:
        team_lower = team.lower()
        # Word boundary check to avoid partial matches
        # e.g., "Jordan" shouldn't match "Jordans shoes"
        pattern = r'(?:^|[\s,\-\.\(\)\[\]\/])' + re.escape(team_lower) + r'(?:$|[\s,\-\.\(\)\[\]\/])'
        if re.search(pattern, text_lower):
            found.append(team)
        elif team_lower in text_lower:
            # Fallback: simple substring (for Vietnamese names with spaces)
            found.append(team)

    # Deduplicate (keep longest match if overlapping)
    if len(found) > 2:
        # Sort by length descending, keep unique
        found.sort(key=len, reverse=True)
        cleaned = []
        used_positions = set()
        for team in found:
            pos = text_lower.find(team.lower())
            if pos >= 0:
                team_range = set(range(pos, pos + len(team)))
                if not team_range & used_positions:
                    cleaned.append(team)
                    used_positions.update(team_range)
        found = cleaned

    return found[:2]  # Max 2 teams per match


def is_match_ended(element_text):
    """Check if match status indicates it has ended."""
    text_lower = element_text.lower().strip()
    for keyword in ENDED_KEYWORDS:
        if keyword in text_lower:
            return True

    # Check for final score pattern like "2 - 1 (FT)" or "2-1 FT"
    if re.search(r'\d+\s*[-:]\s*\d+\s*\(?ft\)?', text_lower):
        return True

    return False


def is_match_live_or_upcoming(element_text):
    """Check if match is live or upcoming."""
    text_lower = element_text.lower()
    for keyword in LIVE_KEYWORDS:
        if keyword in text_lower:
            return True

    # Time pattern like "21:00" or "19h30"
    if re.search(r'\d{1,2}[h:]\d{2}', text_lower):
        return True

    return False


def extract_room_id(url):
    """Extract room/match ID from a socolive URL."""
    patterns = [
        r"-(\d+)\.html",
        r"/(\d+)\.html",
        r"/(\d+)/?$",
        r"[-/](\d{4,})(?:\.html)?",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def extract_stream_from_match_page(scraper, match_url):
    """Visit match page and extract .m3u8 stream URL."""
    try:
        logger.info(f"  → Fetching match page: {match_url}")
        resp = scraper.get(match_url, timeout=15)
        resp.raise_for_status()
        page_content = resp.text

        # Method 1: Direct .m3u8 URL in page source
        m3u8_patterns = [
            r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)',
            r'source\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
            r'file\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
            r'src\s*=\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
            r'url\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
            r'stream_url\s*[=:]\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
            r'hlsUrl\s*[=:]\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
            r'playUrl\s*[=:]\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
        ]

        for pattern in m3u8_patterns:
            matches = re.findall(pattern, page_content, re.IGNORECASE)
            for m3u8_url in matches:
                if "m3u8" in m3u8_url and "example" not in m3u8_url:
                    logger.info(f"  ✓ Found stream: {m3u8_url}")
                    return m3u8_url

        # Method 2: Check iframes
        soup = BeautifulSoup(page_content, "lxml")
        iframes = soup.find_all("iframe")
        for iframe in iframes:
            iframe_src = iframe.get("src", "")
            if iframe_src:
                if not iframe_src.startswith("http"):
                    iframe_src = urljoin(match_url, iframe_src)
                try:
                    iframe_resp = scraper.get(iframe_src, timeout=10)
                    iframe_content = iframe_resp.text
                    for pattern in m3u8_patterns:
                        found = re.findall(pattern, iframe_content, re.IGNORECASE)
                        for m3u8_url in found:
                            if "m3u8" in m3u8_url:
                                logger.info(f"  ✓ Found in iframe: {m3u8_url}")
                                return m3u8_url
                except Exception:
                    pass

        # Method 3: Find room ID and construct URL
        room_id = extract_room_id(match_url)

        room_patterns = [
            r'room[_\s]*(?:id|Id|ID)\s*[=:]\s*["\']?(\d+)',
            r'roomId\s*[=:]\s*["\']?(\d+)',
            r'/room/(\d+)',
            r'/live/(\d+)',
            r'data-id\s*=\s*["\'](\d+)',
            r'"id"\s*:\s*(\d{4,})',
        ]

        for pattern in room_patterns:
            match = re.search(pattern, page_content, re.IGNORECASE)
            if match:
                found_id = match.group(1)
                if len(found_id) >= 4:
                    room_id = found_id
                    break

        if room_id:
            stream_url = f"https://live.inplyr.com/room/{room_id}.m3u8"
            logger.info(f"  ✓ Constructed stream: {stream_url}")
            return stream_url

        # Method 4: Search JSON in scripts
        scripts = soup.find_all("script")
        for script in scripts:
            script_text = script.string or ""
            json_strs = re.findall(r'({[^{}]{50,}})', script_text)
            for json_str in json_strs:
                try:
                    data = json.loads(json_str)
                    result = find_m3u8_in_dict(data)
                    if result:
                        logger.info(f"  ✓ Found in JSON: {result}")
                        return result
                except (json.JSONDecodeError, TypeError):
                    pass

        logger.warning(f"  ✗ No stream found for: {match_url}")
        return None

    except Exception as e:
        logger.error(f"  ✗ Error fetching match page: {e}")
        return None


def find_m3u8_in_dict(data, depth=0):
    """Recursively search for .m3u8 URLs in dict/list."""
    if depth > 10:
        return None
    if isinstance(data, str):
        if ".m3u8" in data:
            return data
    elif isinstance(data, dict):
        for value in data.values():
            result = find_m3u8_in_dict(value, depth + 1)
            if result:
                return result
    elif isinstance(data, list):
        for item in data:
            result = find_m3u8_in_dict(item, depth + 1)
            if result:
                return result
    return None


def extract_match_time(element, text):
    """Extract match time from element."""
    time_selectors = [
        ".time", ".match-time", ".kick-off",
        "[class*='time']", ".date", ".status",
    ]
    for selector in time_selectors:
        time_elem = element.select_one(selector)
        if time_elem:
            t = time_elem.get_text(strip=True)
            if t:
                return t

    # Regex for time
    time_patterns = [
        r"(\d{1,2}:\d{2})",
        r"(\d{1,2}h\d{2})",
        r"(LIVE|Live|Trực tiếp|Đang diễn ra)",
        r"(HT|1H|2H|Hiệp \d)",
    ]
    for pattern in time_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def scrape_world_cup_matches():
    """
    Scrape socolive for matches containing FIFA national team names.
    No World Cup category exists — we find matches by team name matching.
    """
    scraper = create_scraper_session()
    matches = []

    try:
        logger.info(f"Fetching: {BASE_URL}")
        response = scraper.get(BASE_URL, timeout=20)
        response.raise_for_status()
        logger.info(f"Status: {response.status_code}")

        soup = BeautifulSoup(response.text, "lxml")

        # ── Find all match containers ──
        match_selectors = [
            ".match-item", ".match-card", ".game-item",
            ".event-item", ".fixture-item", ".live-match",
            ".schedule-item", ".truc-tiep-item",
            "div[class*='match']", "div[class*='game']",
            "div[class*='event']", "div[class*='fixture']",
            "li[class*='match']", "tr[class*='match']",
            "a[class*='match']",
            ".item", ".list-item",
        ]

        match_elements = []
        for selector in match_selectors:
            found = soup.select(selector)
            if found:
                logger.info(f"  Selector '{selector}': {len(found)} elements")
                match_elements.extend(found)

        # Deduplicate by text content
        seen = set()
        unique = []
        for elem in match_elements:
            text = elem.get_text(strip=True)[:200]
            if text and text not in seen:
                seen.add(text)
                unique.append(elem)
        match_elements = unique

        # ── Also scan all links as fallback ──
        if not match_elements:
            logger.info("No containers found, scanning all links...")
            all_links = soup.find_all("a", href=True)
            for link in all_links:
                href = link.get("href", "")
                if "truc-tiep" in href or "live" in href:
                    match_elements.append(link)

        logger.info(f"Total elements to check: {len(match_elements)}")

        # ── Check each element for FIFA team names ──
        for element in match_elements:
            full_text = element.get_text(separator=" ", strip=True)

            # Also check parent context
            parent_text = ""
            if element.parent:
                parent_text = element.parent.get_text(separator=" ", strip=True)

            combined_text = f"{full_text} {parent_text}"

            # Find FIFA teams in this text
            teams_found = find_teams_in_text(combined_text)

            if len(teams_found) < 2:
                # Need at least 2 national teams to consider it a WC match
                continue

            # Skip ended matches
            if is_match_ended(combined_text):
                logger.info(f"  ⏹ Match ended, skipping: {teams_found}")
                continue

            logger.info(f"\n{'='*60}")
            logger.info(f"🏆 WC match found: {teams_found[0]} vs {teams_found[1]}")
            logger.info(f"   Text: {full_text[:120]}")

            # Get match link
            match_link = None
            if element.name == "a" and element.get("href"):
                match_link = element.get("href")
            else:
                link_elem = element.find("a", href=True)
                if link_elem:
                    match_link = link_elem.get("href")

            if match_link and not match_link.startswith("http"):
                match_link = urljoin(MATCH_PAGE_BASE, match_link)

            # Get match time
            match_time = extract_match_time(element, full_text)

            # Build title
            title = f"⚽ {teams_found[0]} vs {teams_found[1]}"
            if match_time:
                title += f" ({match_time})"

            # Get stream URL
            stream_url = None
            if match_link:
                time.sleep(1)
                stream_url = extract_stream_from_match_page(scraper, match_link)

            if not stream_url and match_link:
                room_id = extract_room_id(match_link)
                if room_id:
                    stream_url = f"https://live.inplyr.com/room/{room_id}.m3u8"

            if stream_url:
                matches.append({
                    "title": title,
                    "stream_url": stream_url,
                    "logo": WORLD_CUP_LOGO,
                    "teams": teams_found,
                    "match_link": match_link,
                })
                logger.info(f"  ✓ Added: {title}")
                logger.info(f"    Stream: {stream_url}")
            else:
                logger.warning(f"  ✗ No stream: {title}")

        # ── Additional: Scan links text for team pairs ──
        if not matches:
            logger.info("\nDeep scanning all links for team names...")
            all_links = soup.find_all("a", href=True)
            checked = set()

            for link in all_links:
                href = link.get("href", "")
                if not href or href in checked or href == "#":
                    continue
                if "javascript" in href:
                    continue

                full_url = href if href.startswith("http") else urljoin(MATCH_PAGE_BASE, href)
                checked.add(href)

                link_text = link.get_text(strip=True)
                # Also check title attribute
                title_attr = link.get("title", "")
                check_text = f"{link_text} {title_attr} {href}"

                teams = find_teams_in_text(check_text)
                if len(teams) >= 2:
                    if is_match_ended(check_text):
                        continue

                    logger.info(f"  Deep hit: {teams[0]} vs {teams[1]} → {full_url}")
                    time.sleep(1)
                    stream_url = extract_stream_from_match_page(scraper, full_url)

                    if not stream_url:
                        room_id = extract_room_id(full_url)
                        if room_id:
                            stream_url = f"https://live.inplyr.com/room/{room_id}.m3u8"

                    if stream_url:
                        match_time = extract_match_time(link, check_text)
                        title = f"⚽ {teams[0]} vs {teams[1]}"
                        if match_time:
                            title += f" ({match_time})"

                        matches.append({
                            "title": title,
                            "stream_url": stream_url,
                            "logo": WORLD_CUP_LOGO,
                            "teams": teams,
                            "match_link": full_url,
                        })
                        logger.info(f"  ✓ Deep added: {title}")

    except Exception as e:
        logger.error(f"Error scraping: {e}")
        import traceback
        traceback.print_exc()

    return matches


# ─── M3U Generator ───────────────────────────────────────────────────────────


def generate_m3u(manual_entries, new_auto_matches):
    """
    Generate M3U content:
    - Always keep manual_entries (user-added channels)
    - Add new auto-scraped matches (tagged so we can identify them later)
    - Old auto entries are discarded (replaced by fresh scrape)
    """
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        "#EXTM3U",
        f"# FIFA World Cup 2026 Live Streams",
        f"# Auto-updated: {now_utc}",
        f"# Source: socolive17.cv",
        f"# Manual channels: {len(manual_entries)}",
        f"# Live WC matches: {len(new_auto_matches)}",
        "",
    ]

    # ── 1. Write all manual entries first (NEVER removed) ──
    if manual_entries:
        lines.append("# ══════ MANUALLY ADDED CHANNELS ══════")
        lines.append("")
        for entry in manual_entries:
            lines.append(entry["extinf_line"])
            if entry["url_line"]:
                lines.append(entry["url_line"])
            lines.append("")

    # ── 2. Write auto-scraped World Cup matches ──
    if new_auto_matches:
        lines.append("# ══════ AUTO-DETECTED WORLD CUP 2026 MATCHES ══════")
        lines.append(f"# Last scan: {now_utc}")
        lines.append("")

        seen_streams = set()
        for match in new_auto_matches:
            stream_url = match["stream_url"]
            if stream_url in seen_streams:
                continue
            seen_streams.add(stream_url)

            title = f"🏆 FIFA World Cup 2026 - {match['title']}"
            logo = match.get("logo", WORLD_CUP_LOGO)

            # Include AUTO_TAG in a tvg-id field so we can identify it later
            # IPTV players ignore tvg-id, so it's invisible to users
            extinf = (
                f'#EXTINF:-1 tvg-id="{AUTO_TAG}" '
                f'tvg-logo="{logo}" '
                f'group-title="FIFA World Cup 2026",'
                f"{title}"
            )

            lines.append(extinf)
            lines.append(stream_url)
            lines.append("")
    else:
        lines.append("# ══════ AUTO-DETECTED WORLD CUP 2026 MATCHES ══════")
        lines.append("# No live World Cup 2026 matches found at this time.")
        lines.append(f"# Last checked: {now_utc}")
        lines.append("")

    return "\n".join(lines)


# ─── Main ────────────────────────────────────────────────────────────────────


def main():
    logger.info("=" * 60)
    logger.info("🏆 FIFA World Cup 2026 Scraper Started")
    logger.info("=" * 60)

    # Step 1: Read existing M3U to preserve manual entries
    manual_entries, old_auto_entries = parse_existing_m3u(OUTPUT_FILE)
    logger.info(f"Preserved {len(manual_entries)} manual channel(s)")
    logger.info(f"Found {len(old_auto_entries)} old auto entries (will refresh)")

    # Step 2: Scrape fresh World Cup matches
    new_matches = scrape_world_cup_matches()
    logger.info(f"\nTotal live WC matches found: {len(new_matches)}")

    # Step 3: Generate M3U
    # - Manual entries: KEPT always
    # - Old auto entries: DISCARDED (replaced by fresh data)
    # - If match ended, it won't appear in new scrape → auto removed
    m3u_content = generate_m3u(manual_entries, new_matches)

    # Step 4: Write file
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(m3u_content)

    logger.info(f"\n✓ Written to: {OUTPUT_FILE}")
    logger.info(f"  Manual channels: {len(manual_entries)}")
    logger.info(f"  Auto WC matches: {len(new_matches)}")
    logger.info("=" * 60)

    print("\n--- Generated Playlist ---")
    print(m3u_content)
    print("--- End Playlist ---\n")


if __name__ == "__main__":
    main()
