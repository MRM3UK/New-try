#!/usr/bin/env python3
"""
FIFA World Cup 2026 Scraper for socolive17.cv
Finds room ID from match pages → builds inplyr.com stream URL
"""

import re
import os
import sys
import json
import time
import base64
import logging
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, parse_qs

import cloudscraper
from bs4 import BeautifulSoup

# ─── Config ──────────────────────────────────────────────────────────────────

BASE_URL = "https://socolive17.cv/truc-tiep/"
SITE_BASE = "https://socolive17.cv"
OUTPUT_FILE = "worldcuptest.m3u"
AUTO_TAG = "auto-added-wc2026"

WORLD_CUP_LOGO = (
    "https://upload.wikimedia.org/wikipedia/en/thumb/1/17/"
    "2026_FIFA_World_Cup_emblem.svg/"
    "330px-2026_FIFA_World_Cup_emblem.svg.png"
)

STREAM_BASE = "https://live.inplyr.com/room/"

# ─── FIFA team slugs (URL) → Display name ────────────────────────────────────

TEAMS = {
    "united-states":"United States","usa":"USA","canada":"Canada",
    "mexico":"Mexico","argentina":"Argentina","brazil":"Brazil",
    "brasil":"Brazil","uruguay":"Uruguay","colombia":"Colombia",
    "ecuador":"Ecuador","paraguay":"Paraguay","chile":"Chile",
    "peru":"Peru","venezuela":"Venezuela","bolivia":"Bolivia",
    "germany":"Germany","france":"France","spain":"Spain",
    "england":"England","portugal":"Portugal","netherlands":"Netherlands",
    "holland":"Netherlands","belgium":"Belgium","italy":"Italy",
    "croatia":"Croatia","serbia":"Serbia","switzerland":"Switzerland",
    "denmark":"Denmark","austria":"Austria","poland":"Poland",
    "ukraine":"Ukraine","turkey":"Turkey","turkiye":"Turkey",
    "sweden":"Sweden","wales":"Wales","scotland":"Scotland",
    "hungary":"Hungary","czech-republic":"Czech Republic",
    "czechia":"Czechia","romania":"Romania","slovakia":"Slovakia",
    "slovenia":"Slovenia","greece":"Greece","norway":"Norway",
    "finland":"Finland","iceland":"Iceland","ireland":"Ireland",
    "bosnia":"Bosnia","bosnia-herzegovina":"Bosnia",
    "albania":"Albania","north-macedonia":"North Macedonia",
    "montenegro":"Montenegro","georgia":"Georgia",
    "luxembourg":"Luxembourg","kosovo":"Kosovo",
    "bulgaria":"Bulgaria","cyprus":"Cyprus","estonia":"Estonia",
    "latvia":"Latvia","lithuania":"Lithuania","belarus":"Belarus",
    "malta":"Malta","moldova":"Moldova","armenia":"Armenia",
    "azerbaijan":"Azerbaijan","kazakhstan":"Kazakhstan",
    "israel":"Israel",
    "morocco":"Morocco","senegal":"Senegal","nigeria":"Nigeria",
    "cameroon":"Cameroon","ghana":"Ghana","egypt":"Egypt",
    "algeria":"Algeria","tunisia":"Tunisia","ivory-coast":"Ivory Coast",
    "south-africa":"South Africa","dr-congo":"DR Congo","mali":"Mali",
    "burkina-faso":"Burkina Faso","mozambique":"Mozambique",
    "tanzania":"Tanzania","uganda":"Uganda","benin":"Benin",
    "zambia":"Zambia","zimbabwe":"Zimbabwe","cape-verde":"Cape Verde",
    "gabon":"Gabon","guinea":"Guinea","congo":"Congo",
    "libya":"Libya","namibia":"Namibia","kenya":"Kenya",
    "angola":"Angola","ethiopia":"Ethiopia","rwanda":"Rwanda",
    "togo":"Togo","sudan":"Sudan",
    "japan":"Japan","south-korea":"South Korea",
    "korea-republic":"South Korea","korea":"South Korea",
    "iran":"Iran","australia":"Australia",
    "saudi-arabia":"Saudi Arabia","qatar":"Qatar","iraq":"Iraq",
    "jordan":"Jordan","uzbekistan":"Uzbekistan","china":"China",
    "china-pr":"China","uae":"UAE",
    "united-arab-emirates":"UAE","oman":"Oman","bahrain":"Bahrain",
    "palestine":"Palestine","vietnam":"Vietnam",
    "viet-nam":"Vietnam","thailand":"Thailand",
    "indonesia":"Indonesia","malaysia":"Malaysia",
    "north-korea":"North Korea","india":"India",
    "kyrgyzstan":"Kyrgyzstan","tajikistan":"Tajikistan",
    "kuwait":"Kuwait","syria":"Syria","lebanon":"Lebanon",
    "myanmar":"Myanmar","philippines":"Philippines",
    "singapore":"Singapore","yemen":"Yemen",
    "costa-rica":"Costa Rica","panama":"Panama",
    "honduras":"Honduras","jamaica":"Jamaica",
    "el-salvador":"El Salvador","guatemala":"Guatemala",
    "trinidad-and-tobago":"Trinidad & Tobago","trinidad":"Trinidad",
    "haiti":"Haiti","curacao":"Curaçao","nicaragua":"Nicaragua",
    "cuba":"Cuba","suriname":"Suriname",
    "new-zealand":"New Zealand","fiji":"Fiji",
    "solomon-islands":"Solomon Islands",
    "papua-new-guinea":"Papua New Guinea","tahiti":"Tahiti",
}

ENDED_KW = ["ft","full time","fulltime","kết thúc","ended","finished","hết giờ"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ─── Helpers ─────────────────────────────────────────────────────────────────


def get_scraper():
    s = cloudscraper.create_scraper(
        browser={"browser":"chrome","platform":"windows","desktop":True}
    )
    s.headers.update({
        "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
        "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language":"en-US,en;q=0.9,vi;q=0.8",
        "Referer":"https://socolive17.cv/",
    })
    return s


def resolve_team(slug):
    """south-korea → South Korea"""
    slug = slug.lower().strip("-/ ")
    if slug in TEAMS:
        return TEAMS[slug]
    parts = slug.split("-")
    for l in range(len(parts), 0, -1):
        c = "-".join(parts[:l])
        if c in TEAMS:
            return TEAMS[c]
    return None


def parse_match_slug(url):
    """
    /truc-tiep/south-korea-vs-czechia-12-06-2026-0900/
    → {team1: South Korea, team2: Czechia, date: 12-06-2026, time: 09:00}
    """
    m = re.search(r'/truc-tiep/([^/]+?)/?$', url)
    if not m:
        return None
    slug = m.group(1).lower()

    if "-vs-" not in slug:
        return None

    # Split on -vs-
    parts = slug.split("-vs-", 1)
    if len(parts) != 2:
        return None

    team1_slug = parts[0]
    rest = parts[1]

    # Extract date-time from end: DD-MM-YYYY-HHMM or DD-MM-YYYY
    date_str = None
    time_str = None

    dt_match = re.search(r'-(\d{2}-\d{2}-\d{4})-(\d{4})$', rest)
    if dt_match:
        date_str = dt_match.group(1)
        time_str = dt_match.group(2)
        team2_slug = rest[:dt_match.start()]
    else:
        dt_match = re.search(r'-(\d{2}-\d{2}-\d{4})$', rest)
        if dt_match:
            date_str = dt_match.group(1)
            team2_slug = rest[:dt_match.start()]
        else:
            team2_slug = rest

    team1 = resolve_team(team1_slug)
    team2 = resolve_team(team2_slug)

    if not team1 or not team2:
        return None

    result = {"team1": team1, "team2": team2}
    if date_str:
        result["date"] = date_str
    if time_str:
        result["time"] = f"{time_str[:2]}:{time_str[2:]}"

    return result


# ─── Room ID Extraction (THE KEY PART) ───────────────────────────────────────


def dig_for_room_id(scraper, url, depth=0, max_depth=4):
    """
    Recursively fetch URL and all iframes inside it,
    searching for the room ID number that maps to
    https://live.inplyr.com/room/XXXXXX.m3u8

    We look for:
    - Direct m3u8 URLs containing /room/NNNN
    - inplyr.com references
    - Numeric IDs in JS variables, data attributes, JSON
    - Base64 encoded strings
    - Query parameters like ?id=NNNN
    """
    if depth > max_depth:
        return None

    indent = "  " * depth
    try:
        log.info(f"{indent}→ GET {url}")
        headers = {"Referer": SITE_BASE + "/"}
        if depth > 0:
            headers["Referer"] = url

        resp = scraper.get(url, timeout=20, headers=headers)
        resp.raise_for_status()
        html = resp.text

        log.info(f"{indent}  Size: {len(html)} chars")

        # ── DUMP first 2000 chars for debugging (only depth 0) ──
        if depth == 0:
            log.info(f"{indent}  === PAGE PREVIEW (first 2000 chars) ===")
            preview = html[:2000].replace('\n', ' ').replace('\r', '')
            log.info(f"{indent}  {preview}")
            log.info(f"{indent}  === END PREVIEW ===")

        # ── 1. Direct inplyr.com/room/NNNN.m3u8 URL ──
        m = re.findall(r'(?:https?:)?//(?:live\d?\.)?inplyr\.com/room/(\d+)', html, re.I)
        if m:
            log.info(f"{indent}  ✓ FOUND room ID (direct inplyr): {m[0]}")
            return m[0]

        # ── 2. Any .m3u8 URL with /room/NNNN ──
        m = re.findall(r'/room/(\d+)\.m3u8', html, re.I)
        if m:
            log.info(f"{indent}  ✓ FOUND room ID (m3u8 path): {m[0]}")
            return m[0]

        # ── 3. Any /room/NNNN reference ──
        m = re.findall(r'/room/(\d{4,})', html, re.I)
        if m:
            log.info(f"{indent}  ✓ FOUND room ID (/room/): {m[0]}")
            return m[0]

        # ── 4. rfrfrf.xyz or similar stream domains ──
        m = re.findall(r'(?:https?:)?//[^\s"\'<>]*rfrfrf[^\s"\'<>]*/(\d+)', html, re.I)
        if m:
            log.info(f"{indent}  ✓ FOUND room ID (rfrfrf): {m[0]}")
            return m[0]

        # ── 5. JS variables: roomId, room_id, channelId, id, etc. ──
        id_patterns = [
            r'room[_\-]?[Ii]d\s*[=:]\s*["\']?(\d{4,})',
            r'channel[_\-]?[Ii]d\s*[=:]\s*["\']?(\d{4,})',
            r'match[_\-]?[Ii]d\s*[=:]\s*["\']?(\d{4,})',
            r'stream[_\-]?[Ii]d\s*[=:]\s*["\']?(\d{4,})',
            r'play[_\-]?[Ii]d\s*[=:]\s*["\']?(\d{4,})',
            r'data-room\s*=\s*["\'](\d{4,})',
            r'data-id\s*=\s*["\'](\d{4,})',
            r'data-stream\s*=\s*["\'](\d{4,})',
            r'data-channel\s*=\s*["\'](\d{4,})',
            r'"room"\s*:\s*"?(\d{4,})',
            r'"roomId"\s*:\s*"?(\d{4,})',
            r'"id"\s*:\s*"?(\d{5,})',
            r'"channel"\s*:\s*"?(\d{4,})',
            r'"stream"\s*:\s*"?(\d{4,})',
            r'var\s+\w*[Ii]d\s*=\s*["\']?(\d{4,})',
            r'let\s+\w*[Ii]d\s*=\s*["\']?(\d{4,})',
            r'const\s+\w*[Ii]d\s*=\s*["\']?(\d{4,})',
        ]
        for pat in id_patterns:
            m = re.search(pat, html, re.I)
            if m:
                log.info(f"{indent}  ✓ FOUND room ID (JS var '{pat[:30]}'): {m.group(1)}")
                return m.group(1)

        # ── 6. Any full m3u8 URL ──
        m3u8_urls = re.findall(r'(https?://[^\s"\'<>\\]+\.m3u8[^\s"\'<>\\]*)', html, re.I)
        for u in m3u8_urls:
            rm = re.search(r'/(\d{4,})', u)
            if rm:
                log.info(f"{indent}  ✓ FOUND room ID (m3u8 URL): {rm.group(1)} from {u}")
                return rm.group(1)

        # ── 7. Base64 encoded strings ──
        b64_matches = re.findall(r'atob\(["\']([A-Za-z0-9+/=]{16,})["\']\)', html)
        for b in b64_matches:
            try:
                decoded = base64.b64decode(b).decode('utf-8', errors='ignore')
                log.info(f"{indent}  Base64 decoded: {decoded[:200]}")
                rm = re.search(r'/room/(\d+)', decoded)
                if rm:
                    log.info(f"{indent}  ✓ FOUND room ID (base64): {rm.group(1)}")
                    return rm.group(1)
                rm = re.search(r'(\d{5,})\.m3u8', decoded)
                if rm:
                    log.info(f"{indent}  ✓ FOUND room ID (base64 m3u8): {rm.group(1)}")
                    return rm.group(1)
            except Exception:
                pass

        # ── 8. URL query params like ?id=434982 ──
        soup = BeautifulSoup(html, "lxml")
        all_urls_in_page = set()

        for tag in soup.find_all(True):
            for attr in ['src', 'data-src', 'href', 'data-url', 'data-stream', 'action']:
                val = tag.get(attr, '')
                if val and ('http' in val or val.startswith('/') or val.startswith('//')):
                    all_urls_in_page.add(val)

        for u in all_urls_in_page:
            parsed = urlparse(u if u.startswith('http') else 'https://dummy.com' + u)
            params = parse_qs(parsed.query)
            for key in ['id', 'room', 'roomId', 'channel', 'stream', 'rid']:
                if key in params:
                    val = params[key][0]
                    if val.isdigit() and len(val) >= 4:
                        log.info(f"{indent}  ✓ FOUND room ID (query ?{key}=): {val}")
                        return val

        # ── 9. Follow iframes recursively ──
        iframes = soup.find_all("iframe")
        log.info(f"{indent}  Found {len(iframes)} iframe(s)")

        for i, iframe in enumerate(iframes):
            src = iframe.get("src", "") or iframe.get("data-src", "")
            if not src or src.startswith("about:") or src.startswith("javascript:"):
                continue

            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                src = urljoin(url, src)
            elif not src.startswith("http"):
                src = urljoin(url, src)

            log.info(f"{indent}  iframe[{i}]: {src}")

            # Check if iframe URL itself contains room ID
            rm = re.search(r'/room/(\d+)', src)
            if rm:
                log.info(f"{indent}  ✓ FOUND room ID (iframe URL): {rm.group(1)}")
                return rm.group(1)

            rm = re.search(r'[?&](?:id|room|rid)=(\d{4,})', src)
            if rm:
                log.info(f"{indent}  ✓ FOUND room ID (iframe param): {rm.group(1)}")
                return rm.group(1)

            # Recursively fetch iframe
            time.sleep(1)
            result = dig_for_room_id(scraper, src, depth + 1, max_depth)
            if result:
                return result

        # ── 10. Follow script src files ──
        scripts = soup.find_all("script", src=True)
        log.info(f"{indent}  Found {len(scripts)} external script(s)")

        for script in scripts:
            src = script.get("src", "")
            if not src:
                continue
            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                src = urljoin(url, src)
            elif not src.startswith("http"):
                src = urljoin(url, src)

            # Only check scripts that might contain stream config
            skip_domains = ['google', 'facebook', 'analytics', 'adsense',
                          'cloudflare', 'jquery', 'bootstrap', 'cdn.js']
            if any(d in src.lower() for d in skip_domains):
                continue

            log.info(f"{indent}  script: {src}")
            try:
                time.sleep(0.5)
                sr = scraper.get(src, timeout=10, headers={"Referer": url})
                js_text = sr.text

                rm = re.search(r'/room/(\d{4,})', js_text)
                if rm:
                    log.info(f"{indent}  ✓ FOUND room ID (ext JS): {rm.group(1)}")
                    return rm.group(1)

                for pat in id_patterns:
                    rm = re.search(pat, js_text, re.I)
                    if rm:
                        log.info(f"{indent}  ✓ FOUND room ID (ext JS var): {rm.group(1)}")
                        return rm.group(1)
            except Exception:
                pass

        # ── 11. Inline script blocks ──
        inline_scripts = soup.find_all("script", src=False)
        for script in inline_scripts:
            text = script.string or ""
            if len(text) < 10:
                continue

            # Log non-trivial scripts
            if len(text) > 50:
                log.info(f"{indent}  inline script ({len(text)} chars): {text[:300].replace(chr(10),' ')}")

            # Look for any 6-digit number that could be room ID
            # especially near keywords like room, stream, channel, play, live
            context_patterns = [
                r'(?:room|stream|channel|play|live|video|source|id)[^\n]{0,30}?(\d{5,7})',
                r'(\d{5,7})[^\n]{0,30}?(?:room|stream|channel|play|live|video|\.m3u8)',
            ]
            for cp in context_patterns:
                cm = re.search(cp, text, re.I)
                if cm:
                    log.info(f"{indent}  ✓ FOUND room ID (inline context): {cm.group(1)}")
                    return cm.group(1)

        log.info(f"{indent}  ✗ No room ID found at depth {depth}")
        return None

    except Exception as e:
        log.error(f"{indent}  ✗ Error: {e}")
        return None


# ─── Main Scraper ────────────────────────────────────────────────────────────


def scrape_matches():
    scraper = get_scraper()
    matches = []

    try:
        log.info(f"Fetching listing: {BASE_URL}")
        resp = scraper.get(BASE_URL, timeout=20)
        resp.raise_for_status()
        log.info(f"Listing page: {resp.status_code}, {len(resp.text)} chars")

        soup = BeautifulSoup(resp.text, "lxml")

        # Find ALL links on the page
        all_links = soup.find_all("a", href=True)
        log.info(f"Total links: {len(all_links)}")

        # Filter: must be /truc-tiep/XXX-vs-YYY pattern
        candidates = []
        seen = set()

        for link in all_links:
            href = link.get("href", "")
            if not href:
                continue

            if href.startswith("/"):
                full_url = urljoin(SITE_BASE, href)
            elif href.startswith("http"):
                full_url = href
            else:
                continue

            if "/truc-tiep/" not in full_url:
                continue
            if "-vs-" not in full_url:
                continue
            if full_url.rstrip("/") == BASE_URL.rstrip("/"):
                continue

            # Deduplicate
            clean = full_url.rstrip("/").lower()
            if clean in seen:
                continue
            seen.add(clean)

            # Parse teams from URL
            parsed = parse_match_slug(full_url)
            if not parsed:
                log.debug(f"  Skip (no teams): {full_url}")
                continue

            # Check if ended
            link_text = link.get_text(strip=True).lower()
            parent_text = ""
            if link.parent:
                parent_text = link.parent.get_text(strip=True).lower()
            all_text = f"{link_text} {parent_text}"

            ended = any(kw in all_text for kw in ENDED_KW)
            if re.search(r'\d+\s*[-:]\s*\d+\s*\(?ft\)?', all_text):
                ended = True

            if ended:
                log.info(f"  ⏹ Ended: {parsed['team1']} vs {parsed['team2']}")
                continue

            candidates.append({"url": full_url, "parsed": parsed})
            log.info(f"  ✓ Candidate: {parsed['team1']} vs {parsed['team2']} → {full_url}")

        log.info(f"\nCandidates: {len(candidates)}")

        # Visit each match page
        for i, c in enumerate(candidates):
            p = c["parsed"]
            url = c["url"]

            log.info(f"\n{'='*60}")
            log.info(f"[{i+1}/{len(candidates)}] {p['team1']} vs {p['team2']}")
            log.info(f"URL: {url}")

            if i > 0:
                time.sleep(2)

            room_id = dig_for_room_id(scraper, url)

            if room_id:
                stream = f"{STREAM_BASE}{room_id}.m3u8"
                title = f"⚽ {p['team1']} vs {p['team2']}"
                if p.get("time"):
                    title += f" ({p['time']})"
                if p.get("date"):
                    title += f" [{p['date']}]"

                matches.append({
                    "title": title,
                    "stream": stream,
                    "room_id": room_id,
                })
                log.info(f"  ✅ ADDED: {title}")
                log.info(f"     Stream: {stream}")
            else:
                log.warning(f"  ❌ No room ID found for {p['team1']} vs {p['team2']}")
                log.warning(f"     You may need to check the page manually: {url}")

    except Exception as e:
        log.error(f"Fatal: {e}")
        import traceback
        traceback.print_exc()

    return matches


# ─── M3U File Handling ───────────────────────────────────────────────────────


def parse_existing_m3u(filepath):
    manual = []
    auto = []
    if not os.path.exists(filepath):
        return manual, auto

    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.read().split("\n")

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#EXTINF"):
            extinf = lines[i].rstrip("\n\r")
            url_line = ""
            j = i + 1
            while j < len(lines):
                nl = lines[j].strip()
                if nl and not nl.startswith("#"):
                    url_line = nl
                    break
                if nl.startswith("#EXTINF"):
                    break
                j += 1

            entry = {"extinf": extinf, "url": url_line}
            if AUTO_TAG in extinf:
                auto.append(entry)
            else:
                manual.append(entry)

            i = j + 1 if url_line else i + 1
        else:
            i += 1

    log.info(f"Existing M3U: {len(manual)} manual, {len(auto)} auto")
    return manual, auto


def write_m3u(manual_entries, new_matches):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    out = []
    out.append("#EXTM3U")
    out.append(f"# FIFA World Cup 2026 Live Streams")
    out.append(f"# Updated: {now}")
    out.append(f"# Manual: {len(manual_entries)} | Auto: {len(new_matches)}")
    out.append("")

    # ── Manual channels (NEVER removed) ──
    if manual_entries:
        out.append("# ═══ MANUALLY ADDED CHANNELS (protected) ═══")
        out.append("")
        for e in manual_entries:
            out.append(e["extinf"])
            if e["url"]:
                out.append(e["url"])
            out.append("")

    # ── Auto channels (refreshed every run) ──
    out.append("# ═══ AUTO-DETECTED WC 2026 MATCHES ═══")
    out.append(f"# Scanned: {now}")
    out.append("")

    if new_matches:
        seen = set()
        for m in new_matches:
            if m["stream"] in seen:
                continue
            seen.add(m["stream"])

            title = f"🏆 FIFA World Cup 2026 - {m['title']}"
            extinf = (
                f'#EXTINF:-1 tvg-id="{AUTO_TAG}" '
                f'tvg-logo="{WORLD_CUP_LOGO}" '
                f'group-title="FIFA World Cup 2026",'
                f'{title}'
            )
            out.append(extinf)
            out.append(m["stream"])
            out.append("")
    else:
        out.append("# No live World Cup 2026 matches found right now.")
        out.append("")

    return "\n".join(out)


# ─── Main ────────────────────────────────────────────────────────────────────


def main():
    log.info("=" * 60)
    log.info("🏆 FIFA World Cup 2026 Scraper")
    log.info("=" * 60)

    # 1. Preserve manual channels
    manual, old_auto = parse_existing_m3u(OUTPUT_FILE)
    log.info(f"Keeping {len(manual)} manual channel(s)")

    # 2. Scrape fresh
    matches = scrape_matches()
    log.info(f"\n{'='*60}")
    log.info(f"Results: {len(matches)} live match(es)")

    # 3. Write M3U
    content = write_m3u(manual, matches)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(content)

    log.info(f"\n✅ {OUTPUT_FILE} written")
    log.info(f"   Manual: {len(manual)} | Auto: {len(matches)}")

    print("\n--- OUTPUT ---")
    print(content)
    print("--- END ---")


if __name__ == "__main__":
    main()
