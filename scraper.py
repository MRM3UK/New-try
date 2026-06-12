#!/usr/bin/env python3
"""
FIFA World Cup 2026 Match Scraper
Scrapes live/upcoming World Cup 2026 matches from socolive
and generates worldcuptest.m3u playlist file.
"""

import re
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

WORLD_CUP_LOGO = "https://upload.wikimedia.org/wikipedia/en/thumb/1/17/2026_FIFA_World_Cup_emblem.svg/330px-2026_FIFA_World_Cup_emblem.svg.png"

# Keywords to identify World Cup 2026 matches (case-insensitive)
WORLD_CUP_KEYWORDS = [
    "world cup 2026",
    "fifa world cup 2026",
    "wc 2026",
    "world cup",
    "vòng loại world cup",
    "wcq 2026",
    "vl world cup",
    "fifa 2026",
    "world cup qualifier",
    "wc qualifier",
    "2026 world cup",
    "fifa wc 2026",
    "world cup qualifying",
    "wcq",
    "vòng loại wc",
    "world cup 26",
]

# Alternative stream domains to try
STREAM_DOMAINS = [
    "live.inplyr.com",
    "live2.inplyr.com",
    "rfrfrf.xyz",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ─── Helper Functions ────────────────────────────────────────────────────────


def create_scraper_session():
    """Create a cloudscraper session with browser-like headers."""
    scraper = cloudscraper.create_scraper(
        browser={
            "browser": "chrome",
            "platform": "windows",
            "desktop": True,
        }
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
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://socolive17.cv/",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
    )
    return scraper


def is_world_cup_match(text):
    """Check if the text contains World Cup 2026 related keywords."""
    text_lower = text.lower().strip()
    for keyword in WORLD_CUP_KEYWORDS:
        if keyword.lower() in text_lower:
            return True
    return False


def extract_room_id(url):
    """Extract room/match ID from a socolive URL."""
    # Try patterns like /truc-tiep/match-name-12345.html or /12345
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
    """
    Visit the individual match page and extract the actual .m3u8 stream URL.
    """
    try:
        logger.info(f"  → Fetching match page: {match_url}")
        resp = scraper.get(match_url, timeout=15)
        resp.raise_for_status()

        page_content = resp.text

        # ── Method 1: Direct .m3u8 URL in page source ──
        m3u8_patterns = [
            r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)',
            r'source\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
            r'file\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
            r'src\s*=\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
            r'url\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
            r'video_url\s*=\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
            r'stream_url\s*[=:]\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
            r'hlsUrl\s*[=:]\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
            r'playUrl\s*[=:]\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
        ]

        for pattern in m3u8_patterns:
            matches = re.findall(pattern, page_content, re.IGNORECASE)
            for m3u8_url in matches:
                if "m3u8" in m3u8_url and "example" not in m3u8_url:
                    logger.info(f"  ✓ Found stream URL: {m3u8_url}")
                    return m3u8_url

        # ── Method 2: Look for embedded iframe with stream ──
        soup = BeautifulSoup(page_content, "lxml")
        iframes = soup.find_all("iframe")
        for iframe in iframes:
            iframe_src = iframe.get("src", "")
            if iframe_src:
                if not iframe_src.startswith("http"):
                    iframe_src = urljoin(match_url, iframe_src)
                try:
                    logger.info(f"  → Checking iframe: {iframe_src}")
                    iframe_resp = scraper.get(iframe_src, timeout=10)
                    iframe_content = iframe_resp.text
                    for pattern in m3u8_patterns:
                        matches = re.findall(
                            pattern, iframe_content, re.IGNORECASE
                        )
                        for m3u8_url in matches:
                            if "m3u8" in m3u8_url:
                                logger.info(
                                    f"  ✓ Found stream in iframe: {m3u8_url}"
                                )
                                return m3u8_url
                except Exception as e:
                    logger.debug(f"  ✗ iframe error: {e}")

        # ── Method 3: Look for room ID and construct stream URL ──
        room_id = extract_room_id(match_url)

        # Also try to find room ID in page content
        room_patterns = [
            r'room[_\s]*(?:id|Id|ID)\s*[=:]\s*["\']?(\d+)',
            r'roomId\s*[=:]\s*["\']?(\d+)',
            r'match[_\s]*id\s*[=:]\s*["\']?(\d+)',
            r'"id"\s*:\s*(\d+)',
            r'data-id\s*=\s*["\'](\d+)',
            r'/room/(\d+)',
            r'/live/(\d+)',
        ]

        for pattern in room_patterns:
            match = re.search(pattern, page_content, re.IGNORECASE)
            if match:
                found_id = match.group(1)
                if len(found_id) >= 4:
                    room_id = found_id
                    logger.info(f"  ✓ Found room ID in page: {room_id}")
                    break

        if room_id:
            stream_url = f"https://live.inplyr.com/room/{room_id}.m3u8"
            logger.info(f"  ✓ Constructed stream URL: {stream_url}")
            return stream_url

        # ── Method 4: Look for JSON data in script tags ──
        scripts = soup.find_all("script")
        for script in scripts:
            script_text = script.string or ""
            # Look for JSON objects with match/stream data
            json_patterns = [
                r'var\s+\w+\s*=\s*({[^;]+})',
                r'window\.\w+\s*=\s*({[^;]+})',
                r'JSON\.parse\(["\']({.+?})["\']\)',
            ]
            for jp in json_patterns:
                json_matches = re.findall(jp, script_text)
                for json_str in json_matches:
                    try:
                        data = json.loads(json_str)
                        # Recursively search for m3u8 URLs
                        m3u8_url = find_m3u8_in_dict(data)
                        if m3u8_url:
                            logger.info(
                                f"  ✓ Found stream in JSON: {m3u8_url}"
                            )
                            return m3u8_url
                    except (json.JSONDecodeError, TypeError):
                        pass

        logger.warning(f"  ✗ No stream URL found for: {match_url}")
        return None

    except Exception as e:
        logger.error(f"  ✗ Error fetching match page: {e}")
        return None


def find_m3u8_in_dict(data, depth=0):
    """Recursively search for .m3u8 URLs in a dictionary/list structure."""
    if depth > 10:
        return None

    if isinstance(data, str):
        if ".m3u8" in data:
            return data
    elif isinstance(data, dict):
        for key, value in data.items():
            result = find_m3u8_in_dict(value, depth + 1)
            if result:
                return result
    elif isinstance(data, list):
        for item in data:
            result = find_m3u8_in_dict(item, depth + 1)
            if result:
                return result
    return None


def scrape_matches():
    """
    Scrape the main socolive page for FIFA World Cup 2026 matches.
    Returns a list of dicts with match info.
    """
    scraper = create_scraper_session()
    matches = []

    try:
        logger.info(f"Fetching main page: {BASE_URL}")
        response = scraper.get(BASE_URL, timeout=20)
        response.raise_for_status()
        logger.info(f"Page fetched successfully (status {response.status_code})")

        soup = BeautifulSoup(response.text, "lxml")

        # ── Strategy 1: Look for match containers ──
        # Common CSS selectors for match listings on sports sites
        match_selectors = [
            ".match-item",
            ".match-card",
            ".game-item",
            ".event-item",
            ".fixture-item",
            ".live-match",
            ".truc-tiep-item",
            ".schedule-item",
            "div[class*='match']",
            "div[class*='game']",
            "div[class*='event']",
            "div[class*='fixture']",
            "li[class*='match']",
            "tr[class*='match']",
            "a[class*='match']",
        ]

        match_elements = []
        for selector in match_selectors:
            found = soup.select(selector)
            if found:
                logger.info(
                    f"Found {len(found)} elements with selector: {selector}"
                )
                match_elements.extend(found)

        # Deduplicate
        seen_texts = set()
        unique_elements = []
        for elem in match_elements:
            text = elem.get_text(strip=True)
            if text and text not in seen_texts:
                seen_texts.add(text)
                unique_elements.append(elem)
        match_elements = unique_elements

        logger.info(f"Total unique match elements found: {len(match_elements)}")

        # ── Strategy 2: If no match containers found, look for links ──
        if not match_elements:
            logger.info("No match containers found, searching all links...")
            all_links = soup.find_all("a", href=True)
            for link in all_links:
                text = link.get_text(strip=True)
                href = link.get("href", "")
                parent_text = ""
                if link.parent:
                    parent_text = link.parent.get_text(strip=True)

                combined_text = f"{text} {parent_text}"
                if is_world_cup_match(combined_text):
                    match_elements.append(link)
                    logger.info(f"Found WC link: {text} → {href}")

        # ── Process each match element ──
        for element in match_elements:
            full_text = element.get_text(separator=" ", strip=True)

            # Check all text including parent elements
            parent = element.parent
            parent_text = ""
            grandparent_text = ""
            if parent:
                parent_text = parent.get_text(separator=" ", strip=True)
                if parent.parent:
                    grandparent_text = parent.parent.get_text(
                        separator=" ", strip=True
                    )

            combined_text = f"{full_text} {parent_text} {grandparent_text}"

            if not is_world_cup_match(combined_text):
                continue

            logger.info(f"\n{'='*60}")
            logger.info(f"World Cup match found: {full_text[:100]}")

            # Extract match link
            match_link = None
            if element.name == "a" and element.get("href"):
                match_link = element.get("href")
            else:
                link_elem = element.find("a", href=True)
                if link_elem:
                    match_link = link_elem.get("href")

            if match_link and not match_link.startswith("http"):
                match_link = urljoin(MATCH_PAGE_BASE, match_link)

            # Extract team names
            teams = extract_team_names(element, full_text)

            # Extract match time
            match_time = extract_match_time(element, full_text)

            # Build title
            if teams:
                title = f"⚽ {teams}"
            else:
                # Clean up the text for title
                title = clean_title(full_text)

            if match_time:
                title += f" ({match_time})"

            title = f"🏆 FIFA World Cup 2026 - {title}"

            # Get stream URL
            stream_url = None
            if match_link:
                time.sleep(1)  # Be respectful
                stream_url = extract_stream_from_match_page(
                    scraper, match_link
                )

            if not stream_url:
                # Try constructing from room ID
                room_id = extract_room_id(match_link or "")
                if room_id:
                    stream_url = (
                        f"https://live.inplyr.com/room/{room_id}.m3u8"
                    )

            if stream_url:
                match_info = {
                    "title": title,
                    "stream_url": stream_url,
                    "logo": WORLD_CUP_LOGO,
                    "match_link": match_link,
                }
                matches.append(match_info)
                logger.info(f"  ✓ Added match: {title}")
                logger.info(f"    Stream: {stream_url}")
            else:
                logger.warning(f"  ✗ No stream found for: {title}")

        # ── Strategy 3: Deep scan - check all page links for WC content ──
        if not matches:
            logger.info("\nDeep scanning all page links for World Cup content...")
            all_links = soup.find_all("a", href=True)
            checked_urls = set()

            for link in all_links:
                href = link.get("href", "")
                if not href or href == "#" or href.startswith("javascript"):
                    continue

                full_url = (
                    href
                    if href.startswith("http")
                    else urljoin(MATCH_PAGE_BASE, href)
                )

                if full_url in checked_urls:
                    continue
                if "truc-tiep" not in full_url and "live" not in full_url:
                    continue

                checked_urls.add(full_url)

                link_text = link.get_text(strip=True)
                if is_world_cup_match(link_text) or is_world_cup_match(href):
                    logger.info(f"Deep scan hit: {link_text} → {full_url}")
                    time.sleep(1)
                    stream_url = extract_stream_from_match_page(
                        scraper, full_url
                    )

                    if stream_url:
                        title = clean_title(link_text)
                        title = f"🏆 FIFA World Cup 2026 - {title}"
                        matches.append(
                            {
                                "title": title,
                                "stream_url": stream_url,
                                "logo": WORLD_CUP_LOGO,
                                "match_link": full_url,
                            }
                        )
                        logger.info(f"  ✓ Deep scan match: {title}")

    except Exception as e:
        logger.error(f"Error scraping main page: {e}")
        import traceback
        traceback.print_exc()

    return matches


def extract_team_names(element, text):
    """Try to extract team names from match element."""
    # Look for specific team containers
    team_selectors = [
        ".team-name",
        ".team",
        ".home-team",
        ".away-team",
        ".team-a",
        ".team-b",
        "[class*='team']",
        ".name",
    ]

    teams = []
    for selector in team_selectors:
        team_elements = element.select(selector)
        for te in team_elements:
            name = te.get_text(strip=True)
            if name and len(name) > 1 and len(name) < 50:
                teams.append(name)

    if len(teams) >= 2:
        return f"{teams[0]} vs {teams[1]}"

    # Try to extract from text using "vs" or "-" pattern
    vs_patterns = [
        r"(.+?)\s+vs\.?\s+(.+?)(?:\s*[\(\[]|$)",
        r"(.+?)\s*-\s*(.+?)(?:\s*[\(\[]|$)",
        r"(.+?)\s+v\s+(.+?)(?:\s*[\(\[]|$)",
    ]

    for pattern in vs_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            team1 = match.group(1).strip()[:30]
            team2 = match.group(2).strip()[:30]
            if len(team1) > 1 and len(team2) > 1:
                return f"{team1} vs {team2}"

    return ""


def extract_match_time(element, text):
    """Try to extract match time."""
    time_selectors = [
        ".time",
        ".match-time",
        ".kick-off",
        ".schedule-time",
        "[class*='time']",
        ".date",
    ]

    for selector in time_selectors:
        time_elem = element.select_one(selector)
        if time_elem:
            time_text = time_elem.get_text(strip=True)
            if time_text:
                return time_text

    # Try regex for time patterns
    time_patterns = [
        r"(\d{1,2}:\d{2})",
        r"(\d{1,2}h\d{2})",
        r"(LIVE|Live|Trực tiếp|Đang diễn ra)",
        r"(FT|HT|1H|2H)",
    ]

    for pattern in time_patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)

    return ""


def clean_title(text):
    """Clean up match title text."""
    # Remove excessive whitespace
    text = re.sub(r"\s+", " ", text).strip()
    # Limit length
    if len(text) > 80:
        text = text[:77] + "..."
    # Remove common noise
    text = re.sub(r"(Xem trực tiếp|Trực tiếp|Live|HD|FHD)\s*", "", text, flags=re.IGNORECASE)
    return text.strip() or "World Cup 2026 Match"


def generate_m3u(matches):
    """Generate M3U playlist content from match list."""
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        "#EXTM3U",
        f"# FIFA World Cup 2026 Live Streams",
        f"# Auto-updated: {now_utc}",
        f"# Source: socolive17.cv",
        f"# Matches found: {len(matches)}",
        "",
    ]

    if not matches:
        # Add a placeholder entry when no matches are live
        lines.append(
            f'#EXTINF:-1 tvg-logo="{WORLD_CUP_LOGO}" '
            f'group-title="FIFA World Cup 2026",'
            f"🏆 No World Cup 2026 matches currently live"
        )
        lines.append(
            "https://upload.wikimedia.org/wikipedia/en/thumb/1/17/"
            "2026_FIFA_World_Cup_emblem.svg/330px-2026_FIFA_World_Cup_emblem.svg.png"
        )
        lines.append("")
    else:
        seen_streams = set()
        for match in matches:
            stream_url = match["stream_url"]

            # Skip duplicates
            if stream_url in seen_streams:
                continue
            seen_streams.add(stream_url)

            title = match["title"]
            logo = match.get("logo", WORLD_CUP_LOGO)

            extinf = (
                f'#EXTINF:-1 tvg-logo="{logo}" '
                f'group-title="FIFA World Cup 2026",'
                f"{title}"
            )

            lines.append(extinf)
            lines.append(stream_url)
            lines.append("")

    return "\n".join(lines)


def main():
    """Main execution function."""
    logger.info("=" * 60)
    logger.info("🏆 FIFA World Cup 2026 Scraper Started")
    logger.info("=" * 60)

    # Scrape matches
    matches = scrape_matches()

    logger.info(f"\n{'='*60}")
    logger.info(f"Total World Cup 2026 matches found: {len(matches)}")

    # Generate M3U
    m3u_content = generate_m3u(matches)

    # Write to file
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(m3u_content)

    logger.info(f"✓ Playlist written to: {OUTPUT_FILE}")
    logger.info(f"{'='*60}")

    # Print the generated playlist for logging
    print("\n--- Generated Playlist ---")
    print(m3u_content)
    print("--- End Playlist ---\n")


if __name__ == "__main__":
    main()
