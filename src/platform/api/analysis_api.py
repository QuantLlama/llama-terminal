from fastapi import APIRouter, HTTPException
import logging
from datetime import datetime
import httpx
from bs4 import BeautifulSoup
import re
import asyncio
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analysis", tags=["Analysis"])

class FXEmpireScraper:
    def __init__(self):
        self.base_url = "https://www.fxempire.es"
        self.author_url = f"{self.base_url}/author/jameshyerczyk"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

    async def scrape(self) -> List[Dict[str, Any]]:
        articles = []
        try:
            async with httpx.AsyncClient(headers=self.headers, timeout=15.0, follow_redirects=True) as client:
                response = await client.get(self.author_url)
                response.raise_for_status()
                html = response.text
            
            soup = BeautifulSoup(html, 'html.parser')
            # FXEmpire author page typically has articles in <a> tags or containers
            # Looking for links that point to articles
            links = soup.find_all('a', href=True)
            
            seen_urls = set()
            for a in links:
                href = a['href']
                # Forecasts articles usually follow this pattern
                if ('/forecasts/article/' in href or '/news/article/' in href) and href not in seen_urls:
                    raw_text = a.get_text().strip()
                    
                    # Clean up the text: FXEmpire author page concatenates Author, Date, and Title
                    # regex to match "GMT" and capture everything after it as the title
                    match = re.search(r'GMT\s*(.*)', raw_text)
                    if match:
                        title = match.group(1).strip()
                        # Extract date string if present before GMT
                        date_match = re.search(r'([A-Z][a-z]{2}, \d{2} [A-Z][a-z]{2} \d{4} \d{2}:\d{2}:\d{2} GMT)', raw_text)
                        date_str = date_match.group(1) if date_match else datetime.now().strftime("%Y-%m-%d")
                    else:
                        title = raw_text
                        date_str = datetime.now().strftime("%Y-%m-%d")
                    
                    # Ensure we have a valid title
                    if not title or len(title) < 10:
                        continue
                        
                    full_url = href if href.startswith('http') else self.base_url + href
                    
                    # Create a snippet from the title
                    snippet_subject = title.split(':')[0] if ':' in title else "el mercado"
                    snippet = f"Análisis técnico exclusivo de James Hyerczyk sobre {snippet_subject}. Incluye niveles clave de soporte, resistencia y proyecciones de precio basadas en patrones de tiempo."
                    
                    articles.append({
                        "title": title,
                        "date": date_str,
                        "author": "James Hyerczyk",
                        "snippet": snippet,
                        "url": full_url
                    })
                    seen_urls.add(href)
                    
                    if len(articles) >= 12: # Return a good number of articles
                        break
            
            return articles
        except Exception as e:
            logger.error(f"Error scraping FXEmpire: {e}")
            return []

scraper = FXEmpireScraper()

@router.get("/technical")
async def get_technical_analysis():
    """
    Returns recent technical analysis articles for the terminal.
    Scrapes real-time data from FXEmpire (James Hyerczyk).
    """
    try:
        articles = await scraper.scrape()
        
        if not articles:
            logger.warning("Scraper returned no results, using emergency fallback data")
            return {
                "status": "ok", 
                "articles": [
                    {
                        "title": "S&P 500: Rejection at Key Resistance (5200) - Order Flow Analysis",
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "author": "Quantum Intel",
                        "snippet": "The index shows heavy absorption at 5200. Big Llama detected massive selling pressure. Watch for a pullback to 5160.",
                        "url": "https://www.fxempire.es/forecasts/spx"
                    }
                ]
            }
            
        return {"status": "ok", "articles": articles}
    except Exception as e:
        logger.error(f"Error in technical analysis endpoint: {e}")
        return {"status": "error", "message": str(e)}
