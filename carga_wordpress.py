import requests, base64
from jinja2 import Environment, FileSystemLoader, select_autoescape
from datetime import datetime as dt
from datetime import timezone
import json, codecs
import os

wordpress_user = "privtools_root"
wordpress_password = os.environ['PRIVTOOLS_API_KEY']
print(os.environ['PRIVTOOLS_API_KEY'])
wordpress_credentials = wordpress_user + ":" + wordpress_password
wordpress_token = base64.b64encode(wordpress_credentials.encode())
wordpress_header = {'Authorization': 'Basic ' + wordpress_token.decode('utf-8')}

ransoms = []

for year in range(dt.now().year,2021,-1):
    url = "https://api.ransomware.live/victims/" + str(year)
    r = requests.get(url)
    yearly_ransoms = r.json()
    yearly_ransoms.reverse()
    ransoms+=yearly_ransoms


def create_wordpress_ransompost(title, content, country, group):
    api_url = 'https://privtools.eu/wp-json/wp/v2/ransomposts'
    data = {
        'title' : title,
        'status': 'draft',
        'content': content,
        'countries': country,
        'groups': group,
    }
    response = requests.post(api_url,headers=wordpress_header, json=data)
    print(data)
    print(response)
    print(response.text)

def read_wordpress_post(id):
    api_url = 'https://privtools.eu/wp-json/wp/v2/posts/' + str(id)
    response = requests.get(api_url)
    response_json = response.json()
    print(response_json)

def read_wordpress_countries():
    countries = dict()
    api_url = 'https://privtools.eu/wp-json/wp/v2/countries'
    response = requests.get(api_url)
    response_json = response.json()
    for country in response_json:
        countries.update({country['name']:country['id']})
    return countries

def create_wordpress_country(name):
    api_url = 'https://privtools.eu/wp-json/wp/v2/countries'
    data = {
        'name' : name
    }
    response = requests.post(api_url,headers=wordpress_header, json=data)
    return response.json().get('id')

def create_wordpress_group(name):
    api_url = 'https://privtools.eu/wp-json/wp/v2/groups'
    data = {
        'name' : name
    }
    response = requests.post(api_url,headers=wordpress_header, json=data)
    return response.json().get('id')


def read_wordpress_groups():
    groups = dict()
    api_url = 'https://privtools.eu/wp-json/wp/v2/groups'
    response = requests.get(api_url)
    response_json = response.json()
    for group in response_json:
        groups.update({group['name']:group['id']})
    return groups



print(ransoms[0].keys())

for ransom in ransoms[0:50]:
    os.environ['PRIVTOOLS_API_KEY']
    content = "<!-- wp:paragraph -->\n<p>" + ransom.get('description') + "</p>\n<!-- /wp:paragraph -->\n\n<!-- wp:image {'sizeSlug':'large'} -->\n" + "<figure class='wp-block-image size-large'><img src='" + ransom.get('screenshot') + "'alt=''/></figure>\n<!-- /wp:image -->"
    if ransom.get('country') not in read_wordpress_countries():
        country = create_wordpress_country(ransom.get('country'))
    else:
        country =  read_wordpress_countries().get(ransom.get('country'))
    
    if ransom.get('group_name') not in read_wordpress_groups():
        group = create_wordpress_group(ransom.get('group_name'))
    else:
        group =  read_wordpress_groups().get(ransom.get('group_name'))

    create_wordpress_ransompost(ransom.get('post_title'), content, country, group)


