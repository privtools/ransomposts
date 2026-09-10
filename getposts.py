import requests
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup
from datetime import datetime as dt
from datetime import timezone, timedelta
from collections import Counter, defaultdict
import json, os, re, sys, shutil, hashlib, time, html as html_lib
from urllib.parse import quote
import pycountry

env = Environment(
    loader=FileSystemLoader( searchpath="./templates" ),
    autoescape=select_autoescape(),
    trim_blocks=True,
    lstrip_blocks=True,
)
env.filters['num'] = lambda n: f'{n:,}'

# url = "https://ransomwhat.telemetry.ltd/groups"
# r = requests.get(url)
# groups_raw = r.json()
# groups ={}
# for group in groups_raw:
#     groups[group['name']] = None
#     for location in group['locations']:
#         if location['available']:
#             groups[group['name']] = location['fqdn']
#             break


# url = "https://ransomwhat.telemetry.ltd/posts"
# r = requests.get(url)
# template = env.get_template("temp1.html")
# ransoms = r.json()
# ransoms.reverse()

# for ransom in ransoms:
#     try:
#         ransom['group_fqdn'] = groups[ransom['group_name']]
#     except KeyError:
#         ransom['group_fqdn'] = None

# with open('./old.html','w') as f:
#             f.write(template.render(ransoms=ransoms,fecha=dt.now(tz=timezone.utc).strftime('%d-%b-%Y %H:%M %Z')))


RANSOMWARE_LIVE = "https://www.ransomware.live"
SITE = "https://ransom.privtools.eu"

FIRST_YEAR = 2022
MIN_POSTS = 10        # below this a group/country/sector gets no landing page (thin content)
PAGE_ROWS = 100       # latest victims listed on each landing page
TOP_N = 10            # entries in each "most targeted" list
EXPLORE_TOP = 15      # entries per list in the home page "Explore" section
RECENT_DAYS = 30      # window of assets/recent.json, the table's initial load
SNAPSHOT_ROWS = 50    # rows in the home page <noscript> snapshot
FEED_ENTRIES = 50

# Fields the home table renders — the lite JSON files carry only these.
TABLE_FIELDS = ('post_title', 'group_name', 'discovered', 'country', 'country_flag', 'screenshot', 'activity')
# Placeholders rather than sectors worth a page.
EXCLUDED_SECTORS = {'', 'not found', 'other'}
# Outbound links go to victims' sites, leak sites and screenshots: never pass ranking to them.
NOFOLLOW = "rel='nofollow noopener noreferrer' target='_blank'"

# pycountry's official names read badly in titles ("Korea, Republic of").
COUNTRY_NAMES = {
    'KR': 'South Korea', 'KP': 'North Korea', 'RU': 'Russia', 'IR': 'Iran', 'SY': 'Syria',
    'VE': 'Venezuela', 'BO': 'Bolivia', 'TZ': 'Tanzania', 'VN': 'Vietnam', 'LA': 'Laos',
    'MD': 'Moldova', 'TW': 'Taiwan', 'PS': 'Palestine', 'XK': 'Kosovo', 'CD': 'DR Congo',
    'CG': 'Republic of the Congo', 'BN': 'Brunei', 'MK': 'North Macedonia', 'CZ': 'Czechia',
    'TR': 'Turkey', 'CI': "Côte d'Ivoire", 'UK': 'United Kingdom', 'FM': 'Micronesia',
}
# Countries that take "the" in a sentence ("ransomware attacks in the United States").
THE_COUNTRIES = {'US', 'GB', 'UK', 'NL', 'AE', 'PH', 'DO', 'BS', 'GM', 'CG', 'CF', 'KY', 'VG', 'MV', 'SC', 'SB', 'MH'}

KINDS = {
    'group':   {'label': 'Ransomware group', 'icon': 'bi-people', 'column': 'Group', 'hub': 'groups', 'hub_name': 'Groups'},
    'country': {'label': 'Country', 'icon': 'bi-globe-americas', 'column': 'Country', 'hub': 'countries', 'hub_name': 'Countries'},
    'sector':  {'label': 'Industry sector', 'icon': 'bi-building', 'column': 'Sector', 'hub': 'sectors', 'hub_name': 'Sectors'},
}


def _best_location(locations):
    """Pick the most representative leak site for a group.

    Prefers a reachable data-leak site, then any reachable location, then any
    location the API still has enabled. Returns the location dict, or None.
    """
    for matches in (
        lambda l: l.get('available') and l.get('type') == 'DLS',
        lambda l: l.get('available'),
        lambda l: l.get('enabled'),
        lambda l: True,
    ):
        for location in locations:
            if matches(location):
                return location
    return None


def _location_url(location):
    """A few slugs come back as a bare host — give them a scheme."""
    url = (location.get('slug') or location.get('fqdn') or '').strip()
    if url and not re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', url):
        url = 'http://' + url
    return url


def get_json(url, timeout, attempts=3):
    """GET a JSON document, backing off on failures — the API rate-limits with HTTP 429."""
    for attempt in range(1, attempts + 1):
        try:
            r = requests.get(url, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as exc:
            if attempt == attempts:
                raise
            print(f"WARNING: {url} attempt {attempt} failed ({exc}) — retrying")
            time.sleep(30 * attempt)


def fetch_groups():
    """Index the /v1/groups endpoint by name and altname (both lowercased).

    Returns an empty index if the endpoint is unreachable so the daily run
    degrades to plain ransomware.live links instead of failing outright.
    """
    try:
        raw = get_json("https://api.ransomware.live/v1/groups", timeout=60)
    except (requests.RequestException, ValueError) as exc:
        print(f"WARNING: could not fetch groups ({exc}) — falling back to post links")
        return {}

    index = {}
    for group in raw:
        location = _best_location(group.get('locations') or [])
        entry = {
            'profile': group.get('url') or '',
            'altname': (group.get('altname') or '').strip(),
            'leak_site': _location_url(location) if location else '',
            'leak_online': bool(location.get('available')) if location else False,
            'leak_type': (location.get('type') or '') if location else '',
            'description': (group.get('description') or '').strip(),
        }
        for key in (group.get('name'), group.get('altname')):
            if key:
                index.setdefault(str(key).strip().lower(), entry)

    print(f"{len(raw)} groups indexed under {len(index)} names")
    return index


def fetch_victims():
    """All victims from FIRST_YEAR to now, newest first.

    Any failed year aborts the run before anything is written: a partial
    dataset would silently drop landing pages from the site and the sitemap.
    """
    victims = []
    for year in range(dt.now(tz=timezone.utc).year, FIRST_YEAR - 1, -1):
        print(year)
        try:
            victims += get_json(f"https://api.ransomware.live/v1/victims/{year}", timeout=180)
        except (requests.RequestException, ValueError) as exc:
            sys.exit(f"ERROR: could not fetch {year} victims ({exc}) — nothing written")
    if not victims:
        sys.exit("ERROR: the API returned no victims — nothing written")
    victims.sort(key=lambda v: v.get('discovered') or '', reverse=True)
    return victims


def group_link(name, post_url, groups, page_url=''):
    """Render the group cell.

    Groups with a landing page link to it. The rest link to their leak site —
    most are .onion addresses, so the link only resolves in Tor. The
    ransomware.live profile is kept in the tooltip as the reachable alternative,
    and is used as the href for the few groups with no known location.
    """
    label = html_lib.escape(name or '')
    info = groups.get((name or '').strip().lower())

    tooltip = []
    href = page_url
    if info:
        profile = info['profile'] or f"{RANSOMWARE_LIVE}/group/{quote(str(name or ''), safe='')}"
        href = href or info['leak_site'] or profile
        if info['altname'] and info['altname'].lower() != (name or '').lower():
            tooltip.append(f"aka {info['altname']}")
        if info['leak_site']:
            kind = info['leak_type'] or 'Leak site'
            state = 'online' if info['leak_online'] else 'offline'
            onion = ' — needs Tor' if '.onion' in info['leak_site'] else ''
            tooltip.append(f"{kind} ({state}){onion}")
            tooltip.append(f"Profile: {profile}")
        if info['description']:
            summary = info['description'].split('\n')[0]
            tooltip.append(summary[:197] + '…' if len(summary) > 200 else summary)
    elif not href:
        # Unknown group: keep the previous behaviour, but absolute so it resolves.
        if not post_url:
            return label
        href = post_url if post_url.startswith('http') else RANSOMWARE_LIVE + post_url

    title = html_lib.escape(' · '.join(tooltip), quote=True) if tooltip else ''
    title_attr = f" title='{title}'" if title else ''
    rel = '' if page_url else ' ' + NOFOLLOW

    return f"<a href='{html_lib.escape(href, quote=True)}'{rel}{title_attr}>{label}</a>"


# ── Small helpers ──────────────────────────────────────────────────────────

def slugify(text):
    slug = re.sub(r'[^a-z0-9]+', '-', (text or '').lower()).strip('-')
    return slug or 'x' + hashlib.sha1((text or '').encode('utf-8')).hexdigest()[:8]


def clean_text(s):
    """Collapse whitespace and drop control characters (they are invalid in XML)."""
    return re.sub(r'\s+', ' ', re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', s or '')).strip()


def parse_ts(value):
    try:
        ts = dt.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def long_date(date):
    return dt.strptime(date, '%Y-%m-%d').strftime('%-d %B %Y') if date else ''


def month_year(date):
    return dt.strptime(date, '%Y-%m-%d').strftime('%B %Y') if date else ''


def human_list(names):
    names = list(names)
    if len(names) <= 1:
        return ''.join(names)
    return ', '.join(names[:-1]) + ' and ' + names[-1]


def country_name(code):
    if code in COUNTRY_NAMES:
        return COUNTRY_NAMES[code]
    country = pycountry.countries.get(alpha_2=code)
    if not country:
        return code
    return getattr(country, 'common_name', None) or country.name


def group_display_name(key, items):
    """Most common spelling; the API's all-lowercase names ("akira") get a capital for titles."""
    name = Counter(r['group'] for r in items).most_common(1)[0][0]
    return name[:1].upper() + name[1:] if name.islower() else name


def fit_title(title):
    """Drop the site suffix when a title would be truncated in search results anyway."""
    return title.replace(' | RansomPosts', '') if len(title) > 65 else title


def short_group_name(name):
    """"Vexy Ransomware" → "Vexy", so sentences don't say "ransomware" twice."""
    return re.sub(r'\s*ransomware\s*$', '', name, flags=re.I) or name


def write_if_changed(path, content):
    """Write only when the content differs, so unchanged pages stay out of the daily commit."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    try:
        with open(path, encoding='utf-8') as f:
            if f.read() == content:
                return False
    except FileNotFoundError:
        pass
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    return True


def json_lines(records):
    """A JSON array with one compact record per line: small, yet diffs line by line."""
    body = ',\n'.join(json.dumps(r, ensure_ascii=False, separators=(',', ':')) for r in records)
    return '[\n' + body + '\n]\n'


def replace_block(page, name, content):
    # A function replacement, so backslashes in victim names are not read as group references.
    return re.sub(
        rf'<!-- {name}-START -->.*?<!-- {name}-END -->',
        lambda m: f'<!-- {name}-START -->\n{content}\n    <!-- {name}-END -->',
        page,
        flags=re.DOTALL,
    )


def page_jsonld(path, name, description, date_modified, crumbs):
    url = SITE + path
    data = {
        '@context': 'https://schema.org',
        '@graph': [
            {
                '@type': 'CollectionPage',
                '@id': url,
                'url': url,
                'name': name,
                'description': description,
                'dateModified': date_modified,
                'inLanguage': 'en',
                'isPartOf': {'@type': 'WebSite', '@id': SITE + '/#website', 'name': 'RansomPosts', 'url': SITE + '/'},
            },
            {
                '@type': 'BreadcrumbList',
                'itemListElement': [
                    {'@type': 'ListItem', 'position': i, 'name': crumb, 'item': SITE + href}
                    for i, (crumb, href) in enumerate(crumbs, start=1)
                ],
            },
        ],
    }
    return Markup(json.dumps(data, ensure_ascii=False, indent=2).replace('</', '<\\/'))


# ── Entities: groups, countries and sectors ────────────────────────────────

def group_key(row):
    return row['group_key']


def country_key(row):
    return row['country']


def sector_key(row):
    return '' if row['sector_key'] in EXCLUDED_SECTORS else row['sector_key']


def most_common_spelling(field):
    return lambda key, items: Counter(r[field] for r in items).most_common(1)[0][0]


def build_entities(rows, key_of, kind, name_of):
    """Bucket rows by key. Entities with MIN_POSTS or more get a landing page URL."""
    buckets = defaultdict(list)
    for row in rows:
        key = key_of(row)
        if key:
            buckets[key].append(row)

    entities, taken = {}, set()
    for key, items in sorted(buckets.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        slug = base = slugify(key)
        n = 2
        while slug in taken:
            slug, n = f'{base}-{n}', n + 1
        taken.add(slug)
        dates = [r['date'] for r in items if r['date']]
        entities[key] = {
            'key': key,
            'name': name_of(key, items),
            'slug': slug,
            'rows': items,
            'count': len(items),
            'first': min(dates) if dates else '',
            'last': max(dates) if dates else '',
            'url': f'/{kind}/{slug}/' if len(items) >= MIN_POSTS else '',
        }
    return entities


def breakdown(items, key_of, entities, limit=TOP_N, flags=False):
    counts = Counter(k for k in map(key_of, items) if k)
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
    top = ranked[0][1] if ranked else 1
    return [
        {
            'name': entities[key]['name'],
            'url': entities[key]['url'],
            'count': n,
            'pct': max(1, round(100 * n / top)),
            'code': key if flags else '',
        }
        for key, n in ranked
    ]


def yearly(items):
    counts = Counter(r['date'][:4] for r in items if r['date'])
    if not counts:
        return []
    top = max(counts.values())
    return [
        {'year': year, 'count': counts.get(str(year), 0), 'pct': round(100 * counts.get(str(year), 0) / top)}
        for year in range(int(min(counts)), int(max(counts)) + 1)
    ]


def table_row(row, index):
    group = index['group'].get(row['group_key'])
    country = index['country'].get(row['country'])
    sector = index['sector'].get(sector_key(row))
    return {
        'title': row['title'],
        'date': row['date'],
        'group': group['name'] if group else row['group'],
        'group_url': group['url'] if group else '',
        'country': row['country'],
        'country_name': country['name'] if country else '',
        'country_url': country['url'] if country else '',
        'sector': sector['name'] if sector else ('' if row['sector_key'] in ('', 'not found') else row['sector']),
        'sector_url': sector['url'] if sector else '',
    }


def group_about(name, info):
    """Description and reference links for a group page, from the /v1/groups data."""
    if not info:
        return None
    text = html_lib.unescape(re.sub(r'<[^>]+>', ' ', info['description']))
    paragraphs, length = [], 0
    for paragraph in text.split('\n'):
        paragraph = clean_text(paragraph)
        if not paragraph:
            continue
        if paragraphs and length + len(paragraph) > 1200:
            break
        paragraphs.append(paragraph)
        length += len(paragraph)

    facts = []
    if info['altname'] and info['altname'].lower() != name.lower():
        facts.append({'label': 'Also known as', 'text': info['altname'], 'url': ''})
    if info['leak_site']:
        tor = ' (Tor)' if '.onion' in info['leak_site'] else ''
        facts.append({'label': 'Leak site' + tor, 'text': info['leak_site'], 'url': info['leak_site'], 'nofollow': True})
    if info['profile']:
        facts.append({'label': 'Profile', 'text': 'ransomware.live', 'url': info['profile']})
    return {'paragraphs': paragraphs, 'facts': facts} if paragraphs or facts else None


def entity_page(kind, entity, index, groups):
    items, name, count = entity['rows'], entity['name'], entity['count']
    first, last = entity['first'], entity['last']
    since = f"since {month_year(first)}"
    top = {
        'group': breakdown(items, group_key, index['group']),
        'country': breakdown(items, country_key, index['country'], flags=True),
        'sector': breakdown(items, sector_key, index['sector']),
    }

    def top_names(axis, n=3):
        return human_list(e['name'] for e in top[axis][:n])

    stats = [
        {'label': 'Total posts', 'value': f'{count:,}', 'icon': 'bi-file-earmark-post', 'tint': 'danger'},
        {'label': 'First seen', 'value': first, 'icon': 'bi-calendar-event', 'tint': 'violet', 'small': True},
        {'label': 'Latest post', 'value': last, 'icon': 'bi-activity', 'tint': 'amber', 'small': True},
    ]
    about = None

    if kind == 'group':
        short = short_group_name(name)
        countries_hit = len({r['country'] for r in items if r['country']})
        stats.append({'label': 'Countries hit', 'value': f'{countries_hit:,}', 'icon': 'bi-globe-americas', 'tint': 'accent'})
        h1 = f"{short} ransomware: victims and leak site activity"
        title = f"{short} Ransomware Victims ({count:,} posts) | RansomPosts"
        lede = f"The {short} ransomware group has listed {count:,} victims on its leak site {since}; its latest post is from {long_date(last)}."
        description = f"{short} ransomware: {count:,} victims listed on its leak site {since}."
        if top['country']:
            lede += f" Most affected countries: {top_names('country')}."
            description += f" Top targets: {top_names('country')}."
        if top['sector']:
            lede += f" Most targeted sector: {top['sector'][0]['name']}."
        description += " Latest victims, sectors and yearly activity."
        sections = [('Most targeted countries', 'country'), ('Most targeted sectors', 'sector')]
        years_title = f"{short} victims per year"
        about = group_about(name, groups.get(entity['key']))
    elif kind == 'country':
        where = f'the {name}' if entity['key'] in THE_COUNTRIES else name
        active_groups = len({r['group_key'] for r in items})
        stats.append({'label': 'Groups', 'value': f'{active_groups:,}', 'icon': 'bi-people', 'tint': 'accent'})
        h1 = f"Ransomware attacks in {where}"
        title = f"Ransomware Attacks in {name} — {count:,} Victims | RansomPosts"
        lede = (f"Ransomware groups have listed {count:,} organisations from {where} on their leak sites {since}; "
                f"the latest post is from {long_date(last)}. Most active groups: {top_names('group')}.")
        if top['sector']:
            lede += f" Most affected sector: {top['sector'][0]['name']}."
        description = (f"{count:,} ransomware victims in {where} listed on leak sites {since}. "
                       f"Most active groups: {top_names('group')}. Latest victims, sectors and yearly trend.")
        sections = [('Most active groups', 'group'), ('Most targeted sectors', 'sector')]
        years_title = f"Ransomware victims in {where} per year"
    else:
        active_groups = len({r['group_key'] for r in items})
        stats.append({'label': 'Groups', 'value': f'{active_groups:,}', 'icon': 'bi-people', 'tint': 'accent'})
        h1 = f"Ransomware attacks on the {name} sector"
        title = f"{name} Ransomware Attacks — {count:,} Victims | RansomPosts"
        lede = (f"Ransomware groups have listed {count:,} {name} organisations on their leak sites {since}; "
                f"the latest post is from {long_date(last)}. Most active groups: {top_names('group')}.")
        if top['country']:
            lede += f" Most affected countries: {top_names('country')}."
        description = (f"{count:,} ransomware victims in the {name} sector {since}. "
                       f"Most active groups: {top_names('group')}. Latest victims, countries and yearly trend.")
        sections = [('Most active groups', 'group'), ('Most affected countries', 'country')]
        years_title = f"{name} ransomware victims per year"

    meta = KINDS[kind]
    crumbs = [('Home', '/'), (meta['hub_name'], f"/{meta['hub']}/"), (name, entity['url'])]
    table = [table_row(r, index) for r in items[:PAGE_ROWS]]
    page = {
        'title': fit_title(title),
        'description': description,
        'path': entity['url'],
        'h1': h1,
        'lede': lede,
        'crumbs': crumbs,
        'section': meta['hub'],
        'years_title': years_title,
        'table_title': f"Latest {len(table)} victims" if count > len(table) else f"All {count} victims",
        'jsonld': page_jsonld(entity['url'], h1, description, last, crumbs),
    }
    return env.get_template('entity.html').render(
        site=SITE,
        page=page,
        kind=meta,
        entity=entity,
        stats=stats,
        about=about,
        breakdowns=[
            {
                'title': heading,
                'entries': top[axis],
                'flags': axis == 'country',
                'more_url': f"/{KINDS[axis]['hub']}/",
                'more_text': f"All {KINDS[axis]['hub_name'].lower()}",
            }
            for heading, axis in sections
        ],
        years=yearly(items),
        table=table,
        columns={axis: axis != kind for axis in KINDS},
    )


def hub_page(kind, entities, last_date):
    meta = KINDS[kind]
    ordered = sorted(entities.values(), key=lambda e: (-e['count'], e['name'].lower()))
    entries = [
        {
            'name': e['name'], 'url': e['url'], 'count': e['count'],
            'first': e['first'], 'last': e['last'], 'code': e['key'] if kind == 'country' else '',
        }
        for e in ordered
    ]
    n, linked = len(entries), sum(1 for e in entries if e['url'])

    if kind == 'group':
        h1 = "Ransomware groups and their victims"
        title = f"Ransomware Groups — {n} Gangs and Their Victims | RansomPosts"
        lede = (f"{n} ransomware groups have published victims on their leak sites since {FIRST_YEAR}. "
                f"The {linked} groups with at least {MIN_POSTS} posts have their own page with targeted countries, "
                f"sectors, yearly activity and latest victims.")
        description = (f"All {n} ransomware groups tracked since {FIRST_YEAR}, ranked by victims posted on their "
                       f"leak sites, with first and latest post dates.")
    elif kind == 'country':
        h1 = "Ransomware victims by country"
        title = f"Ransomware Victims by Country — {n} Countries | RansomPosts"
        lede = (f"Organisations from {n} countries have appeared on ransomware leak sites since {FIRST_YEAR}. "
                f"The {linked} countries with at least {MIN_POSTS} victims have their own page with the most "
                f"active groups, targeted sectors and latest victims.")
        description = (f"Ransomware victims in {n} countries since {FIRST_YEAR}, ranked by leak site posts, "
                       f"with the most active groups in each country.")
    else:
        h1 = "Ransomware victims by industry sector"
        title = f"Ransomware Victims by Sector — {n} Industries | RansomPosts"
        lede = (f"Ransomware victims since {FIRST_YEAR} grouped into {n} industry sectors. Each sector page "
                f"lists the most active groups, the most affected countries and the latest victims.")
        description = (f"Ransomware victims in {n} industry sectors since {FIRST_YEAR}, from healthcare to "
                       f"manufacturing, with the most active groups in each.")

    path = f"/{meta['hub']}/"
    crumbs = [('Home', '/'), (meta['hub_name'], path)]
    page = {
        'title': fit_title(title), 'description': description, 'path': path, 'h1': h1, 'lede': lede,
        'crumbs': crumbs, 'section': meta['hub'],
        'jsonld': page_jsonld(path, h1, description, last_date, crumbs),
    }
    return env.get_template('hub.html').render(site=SITE, page=page, kind=meta, entries=entries)


def sync_pages(kind, entities, render):
    """Write every landing page of a kind and delete the ones no longer wanted."""
    prefix = f'./{kind}'
    wanted = set()
    for entity in entities.values():
        if entity['url']:
            wanted.add(entity['slug'])
            write_if_changed(f"{prefix}/{entity['slug']}/index.html", render(entity))
    if os.path.isdir(prefix):
        for name in os.listdir(prefix):
            path = os.path.join(prefix, name)
            if name not in wanted and os.path.isdir(path):
                shutil.rmtree(path)  # fell below MIN_POSTS or vanished from the API
    return len(wanted)


def atom_ts(ts):
    return ts.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


# ── Fetch ──────────────────────────────────────────────────────────────────

groups = fetch_groups()
ransoms = fetch_victims()
now = dt.now(tz=timezone.utc)

# Plain-text view of each record, taken before the HTML enrichment below.
rows = []
for ransom in ransoms:
    ts = parse_ts(ransom.get('discovered') or ransom.get('published'))
    group = clean_text(ransom.get('group_name'))
    sector = clean_text(ransom.get('activity'))
    code = (ransom.get('country') or '').strip().upper()
    rows.append({
        'title': clean_text(ransom.get('post_title')),
        'group': group,
        'group_key': group.lower(),
        'country': code if re.fullmatch(r'[A-Z]{2}', code) else '',
        'sector': sector,
        'sector_key': sector.lower(),
        'ts': ts,
        'date': ts.strftime('%Y-%m-%d') if ts else '',
    })

last_date = max(r['date'] for r in rows if r['date'])

index = {
    'group': build_entities(rows, group_key, 'group', group_display_name),
    'country': build_entities(rows, country_key, 'country', lambda key, items: country_name(key)),
    'sector': build_entities(rows, sector_key, 'sector', most_common_spelling('sector')),
}

# ── Enrich records for the web table ───────────────────────────────────────

for ransom, row in zip(ransoms, rows):
    title = html_lib.escape(row['title'], quote=False)
    website = (ransom.get('website') or '').strip()
    if website:
        href = website if re.match(r'^https?://', website, flags=re.I) else 'https://' + website
        ransom['post_title'] = f"<a href='{html_lib.escape(href, quote=True)}' {NOFOLLOW}>{title}</a>"
    else:
        ransom['post_title'] = title

    group = index['group'].get(row['group_key'])
    ransom['group_name'] = group_link(row['group'], ransom.get('post_url'), groups, group['url'] if group else '')

    screenshot = (ransom.get('screenshot') or '').strip()
    ransom['screenshot'] = f"<a href='{html_lib.escape(screenshot, quote=True)}' {NOFOLLOW}>🖵</a>" if screenshot else ""

    code = row['country']
    flag = f"<span class='fi fi-{code.lower()} fis'></span> <span>{code}</span>" if code else ""
    country = index['country'].get(code)
    if country and country['url']:
        label = html_lib.escape(f"Ransomware victims in {country['name']}", quote=True)
        flag = f"<a href='{country['url']}' title='{label}'>{flag}</a>"
    ransom['country_flag'] = flag

write_if_changed('./assets/victims.json', json.dumps(ransoms, ensure_ascii=False, indent=4))

cutoff = now - timedelta(days=RECENT_DAYS)
write_if_changed('./assets/recent.json', json_lines(
    {k: ransom.get(k) for k in TABLE_FIELDS}
    for ransom, row in zip(ransoms, rows) if row['ts'] and row['ts'] >= cutoff
))
write_if_changed('./assets/victims-lite.json', json_lines({k: ransom.get(k) for k in TABLE_FIELDS} for ransom in ransoms))

# ── Landing pages, hubs and 404 ────────────────────────────────────────────

for kind, entities in index.items():
    pages = sync_pages(kind, entities, lambda entity, kind=kind: entity_page(kind, entity, index, groups))
    write_if_changed(f"./{KINDS[kind]['hub']}/index.html", hub_page(kind, entities, last_date))
    print(f"{kind}: {len(entities)} total, {pages} landing pages")

write_if_changed('./404.html', env.get_template('404.html').render(
    site=SITE,
    page={'title': 'Page not found | RansomPosts', 'description': 'This page does not exist.',
          'h1': 'Page not found', 'robots': 'noindex, follow'},
))

# ── Sitemap and feed ───────────────────────────────────────────────────────

urls = [{'path': '/', 'lastmod': last_date}]
urls += [{'path': f"/{meta['hub']}/", 'lastmod': last_date} for meta in KINDS.values()]
for entities in index.values():
    urls += [{'path': e['url'], 'lastmod': e['last']} for e in entities.values() if e['url']]
write_if_changed('./sitemap.xml', env.get_template('sitemap.xml').render(site=SITE, urls=urls))

entries = []
for row in rows[:FEED_ENTRIES]:
    group = index['group'].get(row['group_key'])
    country = index['country'].get(row['country'])
    group_name = group['name'] if group else row['group']
    uid = hashlib.sha1(f"{row['group_key']}|{row['title']}|{row['date']}".encode('utf-8')).hexdigest()[:16]
    summary = f"{group_name} listed {row['title']}" + (f" ({country['name']})" if country else '') + " on its leak site."
    if sector_key(row):
        summary += f" Sector: {row['sector']}."
    entries.append({
        'title': f"{row['title']} — {group_name}",
        'link': SITE + (group['url'] if group and group['url'] else '/'),
        'id': f"tag:ransom.privtools.eu,{row['date'] or FIRST_YEAR}:{uid}",
        'updated': atom_ts(row['ts']) if row['ts'] else f'{last_date}T00:00:00Z',
        'summary': summary,
        'group': group_name,
    })
write_if_changed('./feed.xml', env.get_template('feed.xml').render(
    site=SITE, entries=entries, updated=entries[0]['updated'] if entries else f'{last_date}T00:00:00Z',
))

# ── Home page: stats, explore links, snapshot and dateModified ─────────────

stats = {
    'total': f'{len(ransoms):,}',
    'groups': f"{len(index['group']):,}",
    'countries': f"{len(index['country']):,}",
    'recent': f"{sum(1 for r in rows if r['ts'] and r['ts'] >= now - timedelta(days=7)):,}",
}

explore = env.get_template('explore.html').render(
    groups=breakdown(rows, group_key, index['group'], limit=EXPLORE_TOP),
    countries=breakdown(rows, country_key, index['country'], limit=EXPLORE_TOP, flags=True),
    sectors=breakdown(rows, sector_key, index['sector'], limit=EXPLORE_TOP),
    totals={kind: len(entities) for kind, entities in index.items()},
)

snapshot_rows = []
for row in rows[:SNAPSHOT_ROWS]:
    cells = (row['title'], row['group'], row['date'], row['country'])
    snapshot_rows.append('    <tr>' + ''.join(f'<td>{html_lib.escape(c)}</td>' for c in cells) + '</tr>')

snapshot = (
    '    <noscript>\n'
    '<table id="static-snapshot">\n'
    '<caption>Recent ransomware victim posts — static snapshot</caption>\n'
    '<thead><tr><th>Organization</th><th>Group</th><th>Date</th><th>Country</th></tr></thead>\n'
    '<tbody>\n' + '\n'.join(snapshot_rows) + '\n'
    '</tbody>\n</table>\n</noscript>'
)

with open('./index.html', 'r', encoding='utf-8') as f:
    page = f.read()

page = re.sub(r'"dateModified": "[^"]*"', f'"dateModified": "{last_date}"', page, count=1)
for stat_id, value in stats.items():
    page = re.sub(
        rf'(<span class="stat-num" id="stat-{stat_id}">)[^<]*(</span>)',
        lambda m, value=value: m.group(1) + value + m.group(2),
        page,
    )
page = replace_block(page, 'STATIC-SNAPSHOT', snapshot)
page = replace_block(page, 'EXPLORE', explore.rstrip('\n'))

write_if_changed('./index.html', page)
print(f"{len(ransoms)} victims written, latest {last_date}")
