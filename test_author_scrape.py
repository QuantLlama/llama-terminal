import urllib.request
from bs4 import BeautifulSoup
import json

url = "https://www.fxempire.es/author/jameshyerczyk"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'})
try:
    html = urllib.request.urlopen(req).read()
    soup = BeautifulSoup(html, 'html.parser')
    
    # Buscamos links
    links = soup.find_all('a', href=True)
    articles = []
    
    # Filtramos los que parezcan artículos (generalmente tienen /forecasts/article/ en fxempire)
    for a in links:
        href = a['href']
        if '/forecasts/article/' in href and href not in [x['url'] for x in articles]:
            title = a.get_text().strip()
            if title and len(title) > 10:
                articles.append({'title': title, 'url': href if href.startswith('http') else 'https://www.fxempire.es' + href})
                
    print(f"Encontrados {len(articles)} articulos del autor.")
    for art in articles[:3]:
        print(f"- {art['title']}")
except Exception as e:
    print(f"Error: {e}")
