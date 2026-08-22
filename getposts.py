import requests
from jinja2 import Environment, FileSystemLoader, select_autoescape
from datetime import datetime as dt
from datetime import timezone
import json, codecs, re, html as html_lib

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


ransoms = []

def _safe_attr(value):
    """Escape a value used as the text of an HTML fragment / interpolated
    into attribute position so it can never break out of or inject into the
    surrounding markup."""
    if value is None:
        return ''
    return html_lib.escape(str(value))

for year in range(dt.now().year,2022,-1):
    print(year)
    url = "https://api.ransomware.live/v1/victims/" + str(year)
    r = requests.get(url, timeout=30)
    yearly_ransoms = r.json()
    #yearly_ransoms.reverse()
    for ransom in yearly_ransoms:
        # Escape every field before wrapping in HTML. post_title / group_name /
        # country come from the upstream ransomware.live API and are rendered
        # unescaped by the <noscript> snapshot and (for group/country) by the
        # main table, so a malicious value could inject markup (XSS/deface).
        title = _safe_attr(ransom['post_title'])
        group = _safe_attr(ransom['group_name'])
        country = _safe_attr(ransom['country'])
        website = _safe_attr(ransom['website'])
        post_url = _safe_attr(ransom['post_url'])
        screenshot = _safe_attr(ransom['screenshot'])
        ransom['post_title'] = "<a href='https://" + website + "'>" + title + "</a>" if ransom['website'] else ransom['post_title']
        ransom['group_name'] = "<a href='" + post_url + "'>" + group + "</a>" if ransom['post_url']  else ransom['group_name']
        ransom['screenshot'] = "<a href='" + screenshot +"'>🖵</a>" if ransom['screenshot'] else ""
        ransom['country_flag'] = "<span class='fi fi-" + country.lower() + " fis'></span> <span>" + country + "</span>"
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