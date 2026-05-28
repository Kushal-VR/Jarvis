import csv
import os
import logging
import urllib.parse
from jarvis.web.browser import PlaywrightBrowserManager
from jarvis.web.search import WebSearch

class GoogleMapsScraper:
    def __init__(self, browser_manager: PlaywrightBrowserManager, searcher: WebSearch):
        self.browser = browser_manager
        self.searcher = searcher
        self.logger = logging.getLogger("Jarvis.MapsScraper")

    def collect_leads(self, search_query: str, location: str, output_file: str = "google_maps_leads.csv") -> str:
        self.logger.info(f"Starting Google Maps leads collection for '{search_query}' in '{location}'")
        
        # 1. Construct Google Maps search URL
        query = f"{search_query} in {location}"
        encoded_query = urllib.parse.quote_plus(query)
        url = f"https://www.google.com/maps/search/{encoded_query}"
        
        try:
            self.browser.navigate(url)
            page = self.browser.get_page()
            
            # Wait for results to load
            page.wait_for_timeout(5000)
            
            # Scroll the left sidebar to load more results
            self.logger.info("Scrolling results sidebar...")
            try:
                # Scroll multiple times to get a good number of results
                for i in range(8):
                    page.mouse.wheel(0, 5000)
                    page.wait_for_timeout(1500)
            except Exception as e:
                self.logger.warning(f"Error scrolling results: {e}")

            # Extract place links
            place_elements = page.query_selector_all('a[href*="/maps/place/"]')
            self.logger.info(f"Found {len(place_elements)} place links on Google Maps.")
            
            leads = []
            visited_urls = set()
            
            # Scrape details for each place
            for idx, el in enumerate(place_elements):
                try:
                    # Get the link URL
                    href = el.get_attribute("href")
                    if not href or href in visited_urls:
                        continue
                    visited_urls.add(href)
                    
                    self.logger.info(f"Scraping place {idx+1}/{len(place_elements)}...")
                    
                    # Click on the element to open details panel
                    el.click()
                    page.wait_for_timeout(2500) # Wait for details panel to load
                    
                    # Extract Name
                    name_el = page.query_selector('h1')
                    name = name_el.text_content().strip() if name_el else ""
                    if not name:
                        continue
                    
                    # Extract Website
                    website_el = page.query_selector('a[data-item-id="authority"]')
                    website = website_el.get_attribute("href") if website_el else None
                    
                    # Skip if it has a website
                    if website:
                        self.logger.info(f"Skipping '{name}' because it has a website: {website}")
                        continue
                    
                    # Extract Phone
                    phone = None
                    phone_el = page.query_selector('button[data-item-id*="phone:tel:"]')
                    if phone_el:
                        phone = phone_el.get_attribute("data-item-id").replace("phone:tel:", "").strip()
                    if not phone:
                        phone_link = page.query_selector('a[href^="tel:"]')
                        if phone_link:
                            phone = phone_link.get_attribute("href").replace("tel:", "").strip()
                    
                    # Extract Address
                    address = None
                    address_el = page.query_selector('button[data-item-id="address"]')
                    if address_el:
                        address = address_el.text_content().strip()
                    if not address:
                        # Fallback selector for addresses in Google Maps details pane
                        address_el = page.query_selector('div[class*="Io6YTe"]')
                        if address_el:
                            address = address_el.text_content().strip()
                    
                    # Search for Social Media links
                    social_links = self.find_social_media(name, location)
                    
                    leads.append({
                        "Name": name,
                        "Phone Number": phone or "N/A",
                        "Address": address or "N/A",
                        "Social Media": social_links or "None",
                        "Google Maps Link": href
                    })
                    self.logger.info(f"Collected lead: {name} | Phone: {phone} | Address: {address}")
                    
                except Exception as e:
                    self.logger.error(f"Error scraping place details: {e}")
                    continue
            
            if not leads:
                return "No leads found matching the criteria (no website)."
                
            # Write to CSV in workspace
            workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            resolved_workspace = os.path.abspath(os.path.join(workspace_dir, "workspace"))
            output_path = os.path.join(resolved_workspace, output_file)
            
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            keys = ["Name", "Phone Number", "Address", "Social Media", "Google Maps Link"]
            with open(output_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                writer.writerows(leads)
                
            return f"Successfully collected {len(leads)} leads and saved to {output_path}."
            
        except Exception as e:
            self.logger.error(f"Google Maps Lead Scraping failed: {e}")
            return f"Failed to scrape Google Maps: {e}"

    def find_social_media(self, name: str, location: str) -> str:
        """Helper to find social media links using Web Search."""
        query = f"{name} {location} facebook instagram twitter linkedin"
        try:
            results = self.searcher.search(query, max_results=5)
            socials = []
            for r in results:
                url = r.get("url", "").lower()
                for platform in ["facebook.com/", "instagram.com/", "twitter.com/", "x.com/", "linkedin.com/"]:
                    if platform in url:
                        socials.append(r.get("url"))
                        break
            return ", ".join(list(set(socials))) if socials else ""
        except Exception as e:
            self.logger.error(f"Failed to find social media for {name}: {e}")
            return ""
