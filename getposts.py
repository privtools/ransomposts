import requests
from jinja2 import Environment, FileSystemLoader, select_autoescape
from datetime import datetime as dt
from datetime import timezone
import json

env = Environment(
    loader=FileSystemLoader( searchpath="./templates" ),
    autoescape=select_autoescape()
)

url = "https://ransomwhat.telemetry.ltd/groups"
r = requests.get(url)
groups_raw = r.json()
groups ={}
for group in groups_raw:
    groups[group['name']] = None
    for location in group['locations']:
        if location['available']:
            groups[group['name']] = location['fqdn']
            break
    

url = "https://ransomwhat.telemetry.ltd/posts"
r = requests.get(url)
template = env.get_template("temp1.html")
ransoms = r.json()
ransoms.reverse()

for ransom in ransoms:
    try:
        ransom['group_fqdn'] = groups[ransom['group_name']]
    except KeyError:
        ransom['group_fqdn'] = None

with open('./index.html','w') as f:
            f.write(template.render(ransoms=ransoms,fecha=dt.now(tz=timezone.utc).strftime('%d-%b-%Y %H:%M %Z')))


url = "https://api.ransomware.live/victims/2024"
r = requests.get(url)
ransoms = r.json()
ransoms.reverse()
for ransom in ransoms:
    ransom['post_title'] = "<a href='https://" + ransom['website'] +"'>" + ransom['post_title'] + "</a>"
    ransom['group_name'] = "<a href='" + ransom['post_url'] +"'>" + ransom['group_name'] + "</a>"
    ransom['screenshot'] = "<a href='" + ransom['screenshot'] +"'>🖵</a>"
        
with open('./assets/victims.json','w', encoding='utf-8') as f:
            json.dump(ransoms, f, ensure_ascii=False, indent=4)