import requests
from jinja2 import Environment, FileSystemLoader, select_autoescape
from datetime import datetime as dt
from datetime import timezone
import json, codecs

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

with open('./old.html','w') as f:
            f.write(template.render(ransoms=ransoms,fecha=dt.now(tz=timezone.utc).strftime('%d-%b-%Y %H:%M %Z')))


ransoms = []

for year in range(dt.now().year,2021,-1):
    url = "https://api.ransomware.live/victims/" + str(year)
    r = requests.get(url)
    yearly_ransoms = r.json()
    yearly_ransoms.reverse()
    for ransom in yearly_ransoms:
        ransom['post_title'] = "<a href='https://" + ransom['website'] + "'>" + ransom['post_title'] + "</a>" if ransom['website'] else ransom['post_title'] 
        ransom['group_name'] = "<a href='" + ransom['post_url'] + "'>" + ransom['group_name'] + "</a>" if ransom['post_url']  else "<a href='http://" + groups.get(ransom['group_name']) + "'>" + ransom['group_name'] + "</a>" if groups.get(ransom['group_name']) else ransom['group_name'] 
        ransom['screenshot'] = "<a href='" + ransom['screenshot'] +"'>🖵</a>" if ransom['screenshot'] else ""
        ransom['country_flag'] = "<span class='fi fi-" + ransom['country'].lower() + " fis'></span> <span>" + ransom['country'] + "</span>"
    ransoms+=yearly_ransoms

with codecs.open('./assets/victims.json','w', encoding='utf-8') as f:
            json.dump(ransoms, f, ensure_ascii=False, indent=4)