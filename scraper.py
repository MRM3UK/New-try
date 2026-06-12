#!/usr/bin/env python3
"""
FIFA World Cup 2026 Match Scraper
- Finds WC2026 matches by scanning all /truc-tiep/ links
- Matches FIFA team names in URL slugs and page text
- Extracts stream from match page iframes/embeds
- Preserves manually added channels
- Auto-removes ended matches
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

AUTO_TAG = "auto-added-wc2026"

# ─── FIFA Teams: slug form (as appears in URLs) + display name ───────────────
# Key = how it appears in URL slug, Value = display name

FIFA_TEAM_SLUGS = {
    # Hosts
    "united-states": "United States",
    "usa": "United States",
    "us": "United States",
    "canada": "Canada",
    "mexico": "Mexico",

    # South America
    "argentina": "Argentina",
    "brazil": "Brazil",
    "brasil": "Brazil",
    "uruguay": "Uruguay",
    "colombia": "Colombia",
    "ecuador": "Ecuador",
    "paraguay": "Paraguay",
    "chile": "Chile",
    "peru": "Peru",
    "venezuela": "Venezuela",
    "bolivia": "Bolivia",

    # Europe
    "germany": "Germany",
    "france": "France",
    "spain": "Spain",
    "england": "England",
    "portugal": "Portugal",
    "netherlands": "Netherlands",
    "holland": "Netherlands",
    "belgium": "Belgium",
    "italy": "Italy",
    "croatia": "Croatia",
    "serbia": "Serbia",
    "switzerland": "Switzerland",
    "denmark": "Denmark",
    "austria": "Austria",
    "poland": "Poland",
    "ukraine": "Ukraine",
    "turkey": "Turkey",
    "turkiye": "Turkey",
    "sweden": "Sweden",
    "wales": "Wales",
    "scotland": "Scotland",
    "hungary": "Hungary",
    "czech-republic": "Czech Republic",
    "czechia": "Czechia",
    "romania": "Romania",
    "slovakia": "Slovakia",
    "slovenia": "Slovenia",
    "greece": "Greece",
    "norway": "Norway",
    "finland": "Finland",
    "iceland": "Iceland",
    "ireland": "Ireland",
    "republic-of-ireland": "Ireland",
    "bosnia": "Bosnia & Herzegovina",
    "bosnia-herzegovina": "Bosnia & Herzegovina",
    "albania": "Albania",
    "north-macedonia": "North Macedonia",
    "montenegro": "Montenegro",
    "georgia": "Georgia",
    "luxembourg": "Luxembourg",
    "kosovo": "Kosovo",
    "cyprus": "Cyprus",
    "estonia": "Estonia",
    "latvia": "Latvia",
    "lithuania": "Lithuania",
    "belarus": "Belarus",
    "bulgaria": "Bulgaria",
    "malta": "Malta",
    "moldova": "Moldova",
    "armenia": "Armenia",
    "azerbaijan": "Azerbaijan",
    "kazakhstan": "Kazakhstan",
    "israel": "Israel",
    "faroe-islands": "Faroe Islands",

    # Africa
    "morocco": "Morocco",
    "senegal": "Senegal",
    "nigeria": "Nigeria",
    "cameroon": "Cameroon",
    "ghana": "Ghana",
    "egypt": "Egypt",
    "algeria": "Algeria",
    "tunisia": "Tunisia",
    "ivory-coast": "Ivory Coast",
    "cote-divoire": "Ivory Coast",
    "south-africa": "South Africa",
    "dr-congo": "DR Congo",
    "mali": "Mali",
    "burkina-faso": "Burkina Faso",
    "mozambique": "Mozambique",
    "tanzania": "Tanzania",
    "uganda": "Uganda",
    "benin": "Benin",
    "zambia": "Zambia",
    "zimbabwe": "Zimbabwe",
    "cape-verde": "Cape Verde",
    "gabon": "Gabon",
    "guinea": "Guinea",
    "congo": "Congo",
    "libya": "Libya",
    "namibia": "Namibia",
    "niger": "Niger",
    "sudan": "Sudan",
    "kenya": "Kenya",
    "angola": "Angola",
    "ethiopia": "Ethiopia",
    "rwanda": "Rwanda",
    "togo": "Togo",
    "madagascar": "Madagascar",
    "sierra-leone": "Sierra Leone",

    # Asia
    "japan": "Japan",
    "south-korea": "South Korea",
    "korea-republic": "South Korea",
    "korea": "South Korea",
    "iran": "Iran",
    "australia": "Australia",
    "saudi-arabia": "Saudi Arabia",
    "qatar": "Qatar",
    "iraq": "Iraq",
    "jordan": "Jordan",
    "uzbekistan": "Uzbekistan",
    "china": "China",
    "china-pr": "China",
    "uae": "UAE",
    "united-arab-emirates": "UAE",
    "oman": "Oman",
    "bahrain": "Bahrain",
    "palestine": "Palestine",
    "vietnam": "Vietnam",
    "viet-nam": "Vietnam",
    "thailand": "Thailand",
    "indonesia": "Indonesia",
    "malaysia": "Malaysia",
    "north-korea": "North Korea",
    "india": "India",
    "kyrgyzstan": "Kyrgyzstan",
    "tajikistan": "Tajikistan",
    "kuwait": "Kuwait",
    "syria": "Syria",
    "lebanon": "Lebanon",
    "myanmar": "Myanmar",
    "philippines": "Philippines",
    "singapore": "Singapore",
    "turkmenistan": "Turkmenistan",
    "yemen": "Yemen",
    "hong-kong": "Hong Kong",
    "chinese-taipei": "Chinese Taipei",

    # North/Central America & Caribbean
    "costa-rica": "Costa Rica",
    "panama": "Panama",
    "honduras": "Honduras",
    "jamaica": "Jamaica",
    "el-salvador": "El Salvador",
    "guatemala": "Guatemala",
    "trinidad-and-tobago": "Trinidad & Tobago",
    "trinidad": "Trinidad & Tobago",
    "haiti": "Haiti",
    "curacao": "Curaçao",
    "suriname": "Suriname",
    "nicaragua": "Nicaragua",
    "dominican-republic": "Dominican Republic",
    "cuba": "Cuba",

    # Oceania
    "new-zealand": "New Zealand",
    "fiji": "Fiji",
    "solomon-islands": "Solomon Islands",
    "papua-new-guinea": "Papua New Guinea",
    "tahiti": "Tahiti",
}

# Also build a text-based lookup (for page text matching)
FIFA_TEAMS_TEXT = set()
for display_name in FIFA_TEAM_SLUGS.values():
    FIFA_TEAMS_TEXT.add(display_name.lower())

# Match status: ended
ENDED_KEYWORDS = ["ft", "full time", "fulltime", "kết thúc", "ended", "finished", "hết giờ", "pen", "aet"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ─── URL Parsing ─────────────────────────────────────────────────────────────


def parse_match_url(url):
    """
    Parse match URL like:
    /truc-tiep/south-korea-vs-czechia-12-06-2026-0900/

    Returns dict with team1, team2, date, time or None
    """
    # Extract the slug part
    match = re.search(r'/truc-tiep/([^/]+?)/?$', url)
    if not match:
        return None

    slug = match.group(1).lower()
    logger.debug(f"  Parsing slug: {slug}")

    # Try to find "vs" separator
    # Pattern: team1-vs-team2-DD-MM-YYYY-HHMM
    vs_match = re.match(
        r'^(.+?)-vs-(.+?)(?:-(\d{2}-\d{2}-\d{4})-?(\d{4}))?/?$',
        slug
    )

    if not vs_match:
        # Try without date
        vs_match = re.match(r'^(.+?)-vs-(.+?)$', slug)
        if not vs_match:
            return None

    team1_slug = vs_match.group(1).strip('-')
    team2_slug = vs_match.group(2).strip('-')

    # Remove date/time from team2 if it got included
    # e.g., "czechia-12-06-2026-0900" → "czechia"
    team2_slug = re.sub(r'-\d{2}-\d{2}-\d{4}(-\d{4})?$', '', team2_slug)

    date_str = vs_match.group(3) if vs_match.lastindex and vs_match.lastindex >= 3 else None
    time_str = vs_match.group(4) if vs_match.lastindex and vs_match.lastindex >= 4 else None

    # Resolve team names
    team1_name = resolve_team_name(team1_slug)
    team2_name = resolve_team_name(team2_slug)

    if not team1_name or not team2_name:
        return None

    result = {
        "team1": team1_name,
        "team2": team2_name,
        "team1_slug": team1_slug,
        "team2_slug": team2_slug,
        "date": date_str,
        "time": time_str,
        "slug": slug,
    }

    if time_str:
        result["time_formatted"] = f"{time_str[:2]}:{time_str[2:]}"

    if date_str:
        result["date_formatted"] = date_str  # DD-MM-YYYY

    return result


def resolve_team_name(slug):
    """
    Resolve a URL slug to a FIFA team display name.
    e.g., 'south-korea' → 'South Korea'
         'czechia' → 'Czechia'
    """
    slug = slug.lower().strip('-')

    # Direct match
    if slug in FIFA_TEAM_SLUGS:
        return FIFA_TEAM_SLUGS[slug]

    # Try progressively shorter prefixes
    # For cases like "south-korea-u23" → try "south-korea"
    parts = slug.split('-')
    for length in range(len(parts), 0, -1):
        candidate = '-'.join(parts[:length])
        if candidate in FIFA_TEAM_SLUGS:
            return FIFA_TEAM_SLUGS[candidate]

    # Try title case as display name
    # e.g., "czechia" → "Czechia" — check if it's in our text set
    title_name = slug.replace('-', ' ').title()
    if title_name.lower() in FIFA_TEAMS_TEXT:
        return title_name

    logger.debug(f"  Unknown team slug: {slug}")
    return None


# ─── Existing M3U Parser ────────────────────────────────────────────────────


def parse_existing_m3u(filepath):
    """
    Parse existing worldcuptest.m3u.
    Returns:
      manual_entries: channels without AUTO_TAG (NEVER removed)
      auto_entries: channels with AUTO_TAG (refreshed each run)
    """
    manual_entries = []
    auto_entries = []

    if not os.path.exists(filepath):
        return manual_entries, auto_entries

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        logger.error(f"Error reading {filepath}: {e}")
        return manual_entries, auto_entries

    lines = content.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if not line or line.startswith("#EXTM3U") or (line.startswith("# ") and not line.startswith("#EXTINF")):
            i += 1
            continue

        if line.startswith("#EXTINF"):
            extinf_line = lines[i].rstrip('\n\r')
            url_line = ""

            j = i + 1
            while j < len(lines):
                next_line = lines[j].strip()
                if next_line and not next_line.startswith("#"):
                    url_line = next_line
                    break
                elif next_line.startswith("#EXTINF"):
                    break
                j += 1

            entry = {"extinf_line": extinf_line, "url_line": url_line}

            if AUTO_TAG in extinf_line:
                auto_entries.append(entry)
            else:
                manual_entries.append(entry)

            i = j + 1 if url_line else i + 1
            continue

        i += 1

    logger.info(f"Existing: {len(manual_entries)} manual, {len(auto_entries)} auto")
    return manual_entries, auto_entries


# ─── Stream Extractor ────────────────────────────────────────────────────────


def create_scraper_session():
    scraper = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "windows", "desktop": True}
    )
    scraper.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
        "Referer": "https://socolive17.cv/",
        "DNT": "1",
        "Connection": "keep-alive",
    })
    return scraper


def extract_stream_url(scraper, match_url):
    """
    Visit match page and extract .m3u8 stream URL.
    Tries multiple methods: direct regex, iframes, embedded players, room ID.
    """
    try:
        logger.info(f"  → Fetching: {match_url}")
        resp = scraper.get(match_url, timeout=20)
        resp.raise_for_status()
        page = resp.text
        soup = BeautifulSoup(page, "lxml")

        # ── Method 1: Direct m3u8 in page source ──
        m3u8_urls = re.findall(
            r'(https?://[^\s"\'<>\\\)]+\.m3u8[^\s"\'<>\\\)]*)',
            page, re.IGNORECASE
        )
        for url in m3u8_urls:
            if "example" not in url and "schema" not in url:
                logger.info(f"  ✓ Direct m3u8: {url}")
                return url

        # ── Method 2: JS variables containing stream URLs ──
        js_patterns = [
            r'(?:source|file|src|url|stream|hls|play)[_\w]*\s*[=:]\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
            r'(?:source|file|src|url|stream|hls|play)[_\w]*\s*[=:]\s*["\']([^"\']*inplyr[^"\']*)["\']',
            r'(?:source|file|src|url|stream|hls|play)[_\w]*\s*[=:]\s*["\']([^"\']*rfrfrf[^"\']*)["\']',
            r'atob\(["\']([A-Za-z0-9+/=]+)["\']\)',
        ]
        for pattern in js_patterns:
            found = re.findall(pattern, page, re.IGNORECASE)
            for f in found:
                # Check if it's base64 encoded
                if re.match(r'^[A-Za-z0-9+/=]+$', f) and len(f) > 20:
                    try:
                        import base64
                        decoded = base64.b64decode(f).decode('utf-8', errors='ignore')
                        if '.m3u8' in decoded:
                            logger.info(f"  ✓ Base64 decoded: {decoded}")
                            return decoded
                    except Exception:
                        pass
                elif '.m3u8' in f or 'inplyr' in f or 'rfrfrf' in f:
                    if f.startswith('http'):
                        logger.info(f"  ✓ JS variable: {f}")
                        return f

        # ── Method 3: Iframes (primary method for socolive) ──
        iframes = soup.find_all("iframe")
        for iframe in iframes:
            iframe_src = iframe.get("src", "") or iframe.get("data-src", "")
            if not iframe_src:
                continue

            if not iframe_src.startswith("http"):
                iframe_src = urljoin(match_url, iframe_src)

            logger.info(f"  → Checking iframe: {iframe_src}")

            try:
                iframe_resp = scraper.get(iframe_src, timeout=15, headers={
                    "Referer": match_url,
                })
                iframe_page = iframe_resp.text

                # Find m3u8 in iframe content
                iframe_m3u8 = re.findall(
                    r'(https?://[^\s"\'<>\\\)]+\.m3u8[^\s"\'<>\\\)]*)',
                    iframe_page, re.IGNORECASE
                )
                for url in iframe_m3u8:
                    if "example" not in url:
                        logger.info(f"  ✓ iframe m3u8: {url}")
                        return url

                # Check for room ID in iframe
                room_match = re.search(r'/room/(\d+)', iframe_page)
                if room_match:
                    room_id = room_match.group(1)
                    url = f"https://live.inplyr.com/room/{room_id}.m3u8"
                    logger.info(f"  ✓ iframe room: {url}")
                    return url

                # Check for nested iframes
                iframe_soup = BeautifulSoup(iframe_page, "lxml")
                nested_iframes = iframe_soup.find_all("iframe")
                for nested in nested_iframes:
                    nested_src = nested.get("src", "") or nested.get("data-src", "")
                    if not nested_src:
                        continue
                    if not nested_src.startswith("http"):
                        nested_src = urljoin(iframe_src, nested_src)

                    logger.info(f"  → Nested iframe: {nested_src}")
                    try:
                        nested_resp = scraper.get(nested_src, timeout=10, headers={
                            "Referer": iframe_src,
                        })
                        nested_m3u8 = re.findall(
                            r'(https?://[^\s"\'<>\\\)]+\.m3u8[^\s"\'<>\\\)]*)',
                            nested_resp.text, re.IGNORECASE
                        )
                        for url in nested_m3u8:
                            if "example" not in url:
                                logger.info(f"  ✓ nested m3u8: {url}")
                                return url

                        room_match = re.search(r'/room/(\d+)', nested_resp.text)
                        if room_match:
                            url = f"https://live.inplyr.com/room/{room_match.group(1)}.m3u8"
                            logger.info(f"  ✓ nested room: {url}")
                            return url
                    except Exception as e:
                        logger.debug(f"  nested iframe error: {e}")

            except Exception as e:
                logger.debug(f"  iframe error: {e}")

        # ── Method 4: Find room/channel ID in page ──
        room_patterns = [
            r'/room/(\d+)',
            r'room[_\-]?[iI]d\s*[=:]\s*["\']?(\d+)',
            r'roomId\s*[=:]\s*["\']?(\d+)',
            r'channel[_\-]?[iI]d\s*[=:]\s*["\']?(\d+)',
            r'data-room\s*=\s*["\'](\d+)',
            r'data-id\s*=\s*["\'](\d+)',
            r'data-channel\s*=\s*["\'](\d+)',
            r'"room"\s*:\s*"?(\d+)',
            r'"id"\s*:\s*(\d{5,})',
        ]
        for pattern in room_patterns:
            match = re.search(pattern, page, re.IGNORECASE)
            if match:
                room_id = match.group(1)
                if len(room_id) >= 4:
                    url = f"https://live.inplyr.com/room/{room_id}.m3u8"
                    logger.info(f"  ✓ Room ID {room_id}: {url}")
                    return url

        # ── Method 5: Search all script tags for JSON data ──
        scripts = soup.find_all("script")
        for script in scripts:
            text = script.string or ""
            if not text.strip():
                continue

            # Look for any URL containing inplyr or m3u8
            inplyr_urls = re.findall(
                r'(https?://[^\s"\'<>\\]+(?:inplyr|rfrfrf)[^\s"\'<>\\]*)',
                text, re.IGNORECASE
            )
            for url in inplyr_urls:
                logger.info(f"  ✓ Script URL: {url}")
                if '.m3u8' in url:
                    return url
                # Might be base URL, append room ID
                room_match = re.search(r'/room/(\d+)', url)
                if room_match:
                    return f"https://live.inplyr.com/room/{room_match.group(1)}.m3u8"

            # Try JSON parsing
            json_blocks = re.findall(r'(\{[^{}]{20,}\})', text)
            for block in json_blocks:
                try:
                    data = json.loads(block)
                    m3u8 = find_m3u8_in_data(data)
                    if m3u8:
                        logger.info(f"  ✓ JSON data: {m3u8}")
                        return m3u8
                except (json.JSONDecodeError, TypeError):
                    pass

        # ── Method 6: URL slug room ID fallback ──
        slug_id = re.search(r'-(\d{4,})/?$', match_url)
        if slug_id:
            room_id = slug_id.group(1)
            url = f"https://live.inplyr.com/room/{room_id}.m3u8"
            logger.info(f"  ✓ Slug ID fallback: {url}")
            return url

        logger.warning(f"  ✗ No stream found")
        return None

    except Exception as e:
        logger.error(f"  ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def find_m3u8_in_data(data, depth=0):
    if depth > 8:
        return None
    if isinstance(data, str):
        if ".m3u8" in data:
            return data
    elif isinstance(data, dict):
        for v in data.values():
            r = find_m3u8_in_data(v, depth + 1)
            if r:
                return r
    elif isinstance(data, list):
        for item in data:
            r = find_m3u8_in_data(item, depth + 1)
            if r:
                return r
    return None


# ─── Main Scraper ────────────────────────────────────────────────────────────


def scrape_world_cup_matches():
    """
    1. Fetch the main /truc-tiep/ page
    2. Find ALL links matching pattern: /truc-tiep/teamA-vs-teamB-...
    3. Check if both teams are FIFA national teams
    4. Visit each match page to extract stream
    """
    scraper = create_scraper_session()
    matches = []

    try:
        logger.info(f"Fetching main page: {BASE_URL}")
        response = scraper.get(BASE_URL, timeout=20)
        response.raise_for_status()
        logger.info(f"Status: {response.status_code}, Length: {len(response.text)}")

        soup = BeautifulSoup(response.text, "lxml")

        # ── Collect ALL links on the page ──
        all_links = soup.find_all("a", href=True)
        logger.info(f"Total links on page: {len(all_links)}")

        # ── Filter for match links ──
        match_candidates = []
        seen_slugs = set()

        for link in all_links:
            href = link.get("href", "")

            # Normalize URL
            if href.startswith("/"):
                full_url = urljoin(MATCH_PAGE_BASE, href)
            elif href.startswith("http"):
                full_url = href
            else:
                continue

            # Must be a /truc-tiep/ match page
            if "/truc-tiep/" not in full_url:
                continue

            # Skip the main listing page itself
            if full_url.rstrip("/") == BASE_URL.rstrip("/"):
                continue

            # Must contain "vs"
            if "-vs-" not in full_url.lower():
                continue

            # Deduplicate
            slug_match = re.search(r'/truc-tiep/([^/]+)', full_url)
            if not slug_match:
                continue
            slug = slug_match.group(1).lower()
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)

            # Parse the URL to extract teams
            parsed = parse_match_url(full_url)
            if not parsed:
                logger.debug(f"  Skip (no team match): {full_url}")
                continue

            # Check link text and parent for ended status
            link_text = link.get_text(strip=True)
            parent_text = ""
            if link.parent:
                parent_text = link.parent.get_text(strip=True)
            combined = f"{link_text} {parent_text}".lower()

            is_ended = False
            for kw in ENDED_KEYWORDS:
                if kw in combined:
                    is_ended = True
                    break

            # Also check for score with FT
            if re.search(r'\d+\s*[-:]\s*\d+\s*\(?ft\)?', combined):
                is_ended = True

            if is_ended:
                logger.info(f"  ⏹ Ended: {parsed['team1']} vs {parsed['team2']}")
                continue

            match_candidates.append({
                "url": full_url,
                "parsed": parsed,
                "link_text": link_text,
            })

            logger.info(
                f"  ✓ Found: {parsed['team1']} vs {parsed['team2']} "
                f"→ {full_url}"
            )

        logger.info(f"\nMatch candidates: {len(match_candidates)}")

        # ── Visit each match page to get stream ──
        for i, candidate in enumerate(match_candidates):
            parsed = candidate["parsed"]
            url = candidate["url"]

            logger.info(f"\n{'='*60}")
            logger.info(
                f"[{i+1}/{len(match_candidates)}] "
                f"{parsed['team1']} vs {parsed['team2']}"
            )

            # Be respectful with delays
            if i > 0:
                time.sleep(2)

            stream_url = extract_stream_url(scraper, url)

            if stream_url:
                # Build title
                title = f"⚽ {parsed['team1']} vs {parsed['team2']}"
                if parsed.get("time_formatted"):
                    title += f" ({parsed['time_formatted']})"
                if parsed.get("date_formatted"):
                    title += f" [{parsed['date_formatted']}]"

                matches.append({
                    "title": title,
                    "stream_url": stream_url,
                    "logo": WORLD_CUP_LOGO,
                    "match_url": url,
                    "team1": parsed["team1"],
                    "team2": parsed["team2"],
                })
                logger.info(f"  ✓ ADDED: {title}")
                logger.info(f"    Stream: {stream_url}")
            else:
                logger.warning(
                    f"  ✗ No stream: {parsed['team1']} vs {parsed['team2']}"
                )

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()

    return matches


# ─── M3U Generator ───────────────────────────────────────────────────────────


def generate_m3u(manual_entries, new_matches):
    """
    Generate M3U:
    - Manual entries: ALWAYS kept
    - Auto entries: replaced with fresh scrape results
    - Ended matches: won't appear in scrape → auto removed
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        "#EXTM3U",
        f"# FIFA World Cup 2026 Live Streams",
        f"# Auto-updated: {now}",
        f"# Source: socolive17.cv/truc-tiep/",
        f"# Manual channels: {len(manual_entries)} | Live WC matches: {len(new_matches)}",
        "",
    ]

    # ── Manual entries (NEVER touched) ──
    if manual_entries:
        lines.append("# ══════════════════════════════════════════")
        lines.append("# ══════ MANUALLY ADDED CHANNELS ══════════")
        lines.append("# ══════════════════════════════════════════")
        lines.append("")
        for entry in manual_entries:
            lines.append(entry["extinf_line"])
            if entry["url_line"]:
                lines.append(entry["url_line"])
            lines.append("")

    # ── Auto World Cup matches ──
    lines.append("# ══════════════════════════════════════════")
    lines.append("# ══════ AUTO: WORLD CUP 2026 LIVE ════════")
    lines.append("# ══════════════════════════════════════════")
    lines.append(f"# Scanned: {now}")
    lines.append("")

    if new_matches:
        seen = set()
        for match in new_matches:
            stream = match["stream_url"]
            if stream in seen:
                continue
            seen.add(stream)

            title = f"🏆 FIFA World Cup 2026 - {match['title']}"
            logo = match.get("logo", WORLD_CUP_LOGO)

            extinf = (
                f'#EXTINF:-1 tvg-id="{AUTO_TAG}" '
                f'tvg-logo="{logo}" '
                f'group-title="FIFA World Cup 2026",'
                f'{title}'
            )
            lines.append(extinf)
            lines.append(stream)
            lines.append("")
    else:
        lines.append("# No live World Cup 2026 matches at this time.")
        lines.append("")

    return "\n".join(lines)


# ─── Entry Point ─────────────────────────────────────────────────────────────


def main():
    logger.info("=" * 60)
    logger.info("🏆 FIFA World Cup 2026 Scraper")
    logger.info("=" * 60)

    # 1. Preserve manual channels from existing file
    manual_entries, old_auto = parse_existing_m3u(OUTPUT_FILE)
    logger.info(f"Manual channels preserved: {len(manual_entries)}")
    logger.info(f"Old auto entries (will refresh): {len(old_auto)}")

    # 2. Scrape fresh matches
    new_matches = scrape_world_cup_matches()
    logger.info(f"\n{'='*60}")
    logger.info(f"Live World Cup matches: {len(new_matches)}")

    # 3. Generate M3U (manual kept, auto refreshed)
    m3u = generate_m3u(manual_entries, new_matches)

    # 4. Write
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(m3u)

    logger.info(f"\n✅ Written: {OUTPUT_FILE}")
    logger.info(f"   Manual: {len(manual_entries)} | Auto: {len(new_matches)}")
    logger.info("=" * 60)

    print("\n--- Generated Playlist ---")
    print(m3u)
    print("--- End ---")


if __name__ == "__main__":
    main()
