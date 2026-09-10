import requests
from jinja2 import Environment, FileSystemLoader, select_autoescape
from datetime import datetime as dt
from datetime import timezone
import json, codecs, re, html as html_lib
from urllib.parse import quote

env = Environment(
    loader=FileSystemLoader( searchpath="./templates" ),
    autoescape=select_autoescape()
)

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


def fetch_groups():
    """Index the /v1/groups endpoint by name and altname (both lowercased).

    Returns an empty index if the endpoint is unreachable so the daily run
    degrades to plain ransomware.live links instead of failing outright.
    """
    try:
        r = requests.get("https://api.ransomware.live/v1/groups", timeout=60)
        r.raise_for_status()
        raw = r.json()
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


def group_link(name, post_url, groups):
    """Render the group cell: a link to the group's leak site.

    Most leak sites are .onion addresses, so the link only resolves in Tor. The
    ransomware.live profile is kept in the tooltip as the reachable alternative,
    and is used as the href for the few groups with no known location.
    """
    label = html_lib.escape(name or '')
    info = groups.get((name or '').strip().lower())

    if not info:
        # Unknown group: keep the previous behaviour, but absolute so it resolves.
        if not post_url:
            return label
        href = post_url if post_url.startswith('http') else RANSOMWARE_LIVE + post_url
        return f"<a href='{html_lib.escape(href, quote=True)}'>{label}</a>"

    profile = info['profile'] or f"{RANSOMWARE_LIVE}/group/{quote(str(name or ''), safe='')}"
    href = info['leak_site'] or profile

    tooltip = []
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

    title = html_lib.escape(' · '.join(tooltip), quote=True) if tooltip else ''
    title_attr = f" title='{title}'" if title else ''

    return f"<a href='{html_lib.escape(href, quote=True)}'{title_attr}>{label}</a>"


groups = fetch_groups()

ransoms = []

for year in range(dt.now().year,2022,-1):
    print(year)
    url = "https://api.ransomware.live/v1/victims/" + str(year)
    r = requests.get(url)
    yearly_ransoms = r.json()
    #yearly_ransoms.reverse()
    for ransom in yearly_ransoms:
        ransom['post_title'] = "<a href='https://" + ransom['website'] + "'>" + ransom['post_title'] + "</a>" if ransom['website'] else ransom['post_title']
        ransom['group_name'] = group_link(ransom['group_name'], ransom.get('post_url'), groups)
        ransom['screenshot'] = "<a href='" + ransom['screenshot'] +"'>🖵</a>" if ransom['screenshot'] else ""
        ransom['country_flag'] = "<span class='fi fi-" + ransom['country'].lower() + " fis'></span> <span>" + ransom['country'] + "</span>"
    ransoms+=yearly_ransoms

with codecs.open('./assets/victims.json','w', encoding='utf-8') as f:
            json.dump(ransoms, f, ensure_ascii=False, indent=4)

# ── Post-write: update sitemap lastmod and inject static snapshot ──────────

def _strip_tags(s):
    return re.sub(r'<[^>]+>', '', s or '')

now_date = dt.now(tz=timezone.utc).strftime('%Y-%m-%d')

# Update sitemap.xml lastmod
with open('./sitemap.xml', 'r', encoding='utf-8') as f:
    sitemap = f.read()
sitemap = re.sub(r'<lastmod>[^<]*</lastmod>', f'<lastmod>{now_date}</lastmod>', sitemap)
with open('./sitemap.xml', 'w', encoding='utf-8') as f:
    f.write(sitemap)

# Build static snapshot table (200 most recent records)
rows = []
for r in ransoms[:200]:
    org     = html_lib.escape(_strip_tags(r.get('post_title') or ''))
    group   = html_lib.escape(_strip_tags(r.get('group_name') or ''))
    date    = html_lib.escape((r.get('discovered') or r.get('published') or '')[:10])
    country = html_lib.escape((r.get('country') or '').upper())
    rows.append(f'    <tr><td>{org}</td><td>{group}</td><td>{date}</td><td>{country}</td></tr>')

snapshot = (
    '<noscript>\n'
    '<table id="static-snapshot">\n'
    '<caption>Recent ransomware victim posts — static snapshot</caption>\n'
    '<thead><tr><th>Organization</th><th>Group</th><th>Date</th><th>Country</th></tr></thead>\n'
    '<tbody>\n' + '\n'.join(rows) + '\n'
    '</tbody>\n</table>\n</noscript>'
)

# Inject snapshot and update last-modified in index.html
with open('./index.html', 'r', encoding='utf-8') as f:
    page = f.read()

page = re.sub(
    r'<meta name="last-modified" content="[^"]*">',
    f'<meta name="last-modified" content="{now_date}">',
    page
)
page = re.sub(
    r'<!-- STATIC-SNAPSHOT-START -->.*?<!-- STATIC-SNAPSHOT-END -->',
    f'<!-- STATIC-SNAPSHOT-START -->\n    {snapshot}\n    <!-- STATIC-SNAPSHOT-END -->',
    page,
    flags=re.DOTALL
)

with open('./index.html', 'w', encoding='utf-8') as f:
    f.write(page)