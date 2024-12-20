import requests
from jinja2 import Environment, FileSystemLoader, select_autoescape
from datetime import datetime as dt
from datetime import timezone
import json, codecs


def flag(country_code: str) -> str:
    """
    Convert a two-letter country code to a Unicode flag emoji.
    
    Args:
        country_code (str): A two-letter ISO 3166-1 alpha-2 country code
            (e.g. 'US', 'GB', 'FR')
    
    Returns:
        str: Unicode flag emoji for the given country code
    
    Example:
        >>> country_code_to_flag('US')
        '🇺🇸'
        >>> country_code_to_flag('GB')
        '🇬🇧'
    """
    if not isinstance(country_code, str) or len(country_code) != 2:
        return ""

    # Convert country code to uppercase
    country_code = country_code.upper()
    
    # Check if the country code contains only letters
    if not country_code.isalpha():
        return ""
    
    # Convert ASCII letters to regional indicator symbols
    # Each letter is converted to a Unicode regional indicator symbol
    # The offset is calculated from the ASCII value of 'A' to the first regional indicator
    OFFSET = ord('🇦') - ord('A')
    
    # Convert each letter to its corresponding regional indicator symbol
    return ''.join(chr(ord(char) + OFFSET) for char in country_code)


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
    ransom['country'] = flag(ransom['country'])
    ransoms+=yearly_ransoms

with codecs.open('./assets/victims.json','w', encoding='utf-8') as f:
            json.dump(ransoms, f, ensure_ascii=False, indent=4)