import urllib.request
from bs4 import BeautifulSoup

url = "https://www.fxempire.es/forecasts/article/sp500-y-nasdaq-100-las-acciones-tecnologicas-suben-mientras-amd-impulsa-los-indices-de-ee-uu-298564"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
html = urllib.request.urlopen(req).read()
soup = BeautifulSoup(html, 'html.parser')

print(f"Title: {soup.title.string}")
# Find all divs that might contain text
paras = soup.find_all('p')
print(f"Found {len(paras)} paragraphs")
for i, p in enumerate(paras[:5]):
    print(f"P{i}: {p.get_text()[:100]}")
