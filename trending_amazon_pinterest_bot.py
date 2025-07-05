#!/usr/bin/env python3
"""
Trending Amazon Pinterest Bot
Complete automation script that:
1. Fetches trending products from Amazon
2. Generates affiliate links
3. Creates Pinterest pins automatically

Author: Your Name
Version: 1.0
"""

import requests
from bs4 import BeautifulSoup
import json
import logging
import time
import random
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse, quote_plus
from typing import Dict, List, Optional, Tuple
import re
import os
from fake_useragent import UserAgent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trending_amazon_pinterest.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class TrendingAmazonPinterestBot:
    def __init__(self, pinterest_token: str, amazon_tag: str):
        """
        Initialize the complete automation bot
        
        Args:
            pinterest_token: Pinterest API access token
            amazon_tag: Amazon Associates affiliate tag
        """
        self.pinterest_token = pinterest_token
        self.amazon_tag = amazon_tag
        self.pinterest_base_url = "https://api.pinterest.com/v5"
        self.ua = UserAgent()
        
        # Pinterest API headers
        self.pinterest_headers = {
            "Authorization": f"Bearer {pinterest_token}",
            "Content-Type": "application/json"
        }
        
        # Session for web scraping
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': self.ua.random,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive'
        })
        
        # Amazon trending categories and search terms
        self.trending_categories = {
            'electronics': [
                'best sellers electronics',
                'new releases electronics',
                'movers and shakers electronics'
            ],
            'home': [
                'best sellers home kitchen',
                'new releases home',
                'trending home decor'
            ],
            'fashion': [
                'best sellers clothing',
                'trending fashion accessories',
                'new releases shoes'
            ],
            'health': [
                'best sellers health personal care',
                'trending supplements',
                'new releases beauty'
            ],
            'books': [
                'best sellers books',
                'new releases kindle books',
                'trending audiobooks'
            ],
            'sports': [
                'best sellers sports outdoors',
                'trending fitness equipment',
                'new releases sports'
            ]
        }
        
        # Default hashtags for categories
        self.category_hashtags = {
            'electronics': ['tech', 'gadgets', 'electronics', 'innovation', 'deals', 'amazon', 'shopping'],
            'home': ['home', 'homedecor', 'interior', 'lifestyle', 'design', 'homeimprovement'],
            'fashion': ['fashion', 'style', 'outfit', 'shopping', 'trendy', 'accessories'],
            'health': ['health', 'wellness', 'selfcare', 'fitness', 'lifestyle', 'beauty'],
            'books': ['books', 'reading', 'bookworm', 'education', 'learning', 'kindle'],
            'sports': ['sports', 'fitness', 'outdoor', 'active', 'exercise', 'workout']
        }

    def get_trending_products(self, category: str = 'electronics', max_products: int = 10) -> List[Dict]:
        """
        Fetch trending products from Amazon for a specific category
        
        Args:
            category: Product category to search
            max_products: Maximum number of products to fetch
            
        Returns:
            List of product dictionaries
        """
        logger.info(f"Fetching trending products for category: {category}")
        products = []
        
        try:
            # Get trending search terms for the category
            search_terms = self.trending_categories.get(category, ['best sellers'])
            
            for search_term in search_terms:
                if len(products) >= max_products:
                    break
                    
                # Search Amazon for trending products
                search_results = self._search_amazon_products(search_term, max_products // len(search_terms))
                products.extend(search_results)
                
                # Add delay between searches
                time.sleep(random.uniform(2, 5))
            
            # Remove duplicates and limit results
            unique_products = self._remove_duplicate_products(products)
            final_products = unique_products[:max_products]
            
            logger.info(f"Found {len(final_products)} trending products")
            return final_products
            
        except Exception as e:
            logger.error(f"Error fetching trending products: {e}")
            return []

    def _search_amazon_products(self, search_term: str, max_results: int = 5) -> List[Dict]:
        """
        Search Amazon for products using a search term
        
        Args:
            search_term: Term to search for
            max_results: Maximum results to return
            
        Returns:
            List of product dictionaries
        """
        products = []
        
        try:
            # Rotate user agent
            self.session.headers.update({'User-Agent': self.ua.random})
            
            # Construct search URL
            search_url = f"https://www.amazon.com/s?k={quote_plus(search_term)}&ref=sr_pg_1"
            
            response = self.session.get(search_url, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find product containers
            product_containers = soup.find_all('div', {'data-component-type': 's-search-result'})
            
            for container in product_containers[:max_results]:
                try:
                    product_data = self._extract_product_from_search(container)
                    if product_data:
                        products.append(product_data)
                except Exception as e:
                    logger.warning(f"Error extracting product from container: {e}")
                    continue
            
            return products
            
        except Exception as e:
            logger.error(f"Error searching Amazon for '{search_term}': {e}")
            return []

    def _extract_product_from_search(self, container) -> Optional[Dict]:
        """
        Extract product information from search result container
        
        Args:
            container: BeautifulSoup element containing product info
            
        Returns:
            Product dictionary or None
        """
        try:
            # Extract title
            title_elem = container.find('h2', class_='a-size-mini') or container.find('span', class_='a-size-medium')
            title = title_elem.get_text(strip=True) if title_elem else None
            
            # Extract URL
            link_elem = container.find('h2', class_='a-size-mini').find('a') if container.find('h2', class_='a-size-mini') else None
            if not link_elem:
                link_elem = container.find('a', class_='a-link-normal')
            
            product_url = None
            if link_elem and link_elem.get('href'):
                product_url = urljoin('https://www.amazon.com', link_elem['href'])
            
            # Extract price
            price = self._extract_price_from_search(container)
            
            # Extract image
            img_elem = container.find('img', class_='s-image')
            image_url = img_elem.get('src') if img_elem else None
            
            # Extract rating
            rating = self._extract_rating_from_search(container)
            
            # Extract ASIN
            asin = container.get('data-asin')
            
            if title and product_url and asin:
                return {
                    'title': title,
                    'url': product_url,
                    'asin': asin,
                    'price': price,
                    'image_url': image_url,
                    'rating': rating,
                    'search_rank': len(container.find_all_previous_siblings()) + 1
                }
            
            return None
            
        except Exception as e:
            logger.warning(f"Error extracting product data: {e}")
            return None

    def _extract_price_from_search(self, container) -> Optional[str]:
        """Extract price from search result container"""
        price_selectors = [
            '.a-price .a-offscreen',
            '.a-price-whole',
            '.a-price-current .a-offscreen'
        ]
        
        for selector in price_selectors:
            price_elem = container.select_one(selector)
            if price_elem:
                return price_elem.get_text(strip=True)
        return None

    def _extract_rating_from_search(self, container) -> Optional[str]:
        """Extract rating from search result container"""
        rating_elem = container.find('span', class_='a-icon-alt')
        if rating_elem:
            rating_text = rating_elem.get_text(strip=True)
            if 'out of 5' in rating_text:
                return rating_text
        return None

    def _remove_duplicate_products(self, products: List[Dict]) -> List[Dict]:
        """Remove duplicate products based on ASIN"""
        seen_asins = set()
        unique_products = []
        
        for product in products:
            asin = product.get('asin')
            if asin and asin not in seen_asins:
                seen_asins.add(asin)
                unique_products.append(product)
        
        return unique_products

    def get_detailed_product_info(self, product_url: str) -> Optional[Dict]:
        """
        Get detailed product information from Amazon product page
        
        Args:
            product_url: Full Amazon product URL
            
        Returns:
            Detailed product information dictionary
        """
        try:
            # Rotate user agent
            self.session.headers.update({'User-Agent': self.ua.random})
            
            response = self.session.get(product_url, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            product_info = {
                'title': self._get_detailed_title(soup),
                'price': self._get_detailed_price(soup),
                'description': self._get_detailed_description(soup),
                'features': self._get_detailed_features(soup),
                'images': self._get_detailed_images(soup),
                'rating': self._get_detailed_rating(soup),
                'reviews_count': self._get_detailed_reviews_count(soup),
                'availability': self._get_detailed_availability(soup),
                'category': self._get_detailed_category(soup)
            }
            
            # Filter out None values
            return {k: v for k, v in product_info.items() if v is not None}
            
        except Exception as e:
            logger.error(f"Error getting detailed product info for {product_url}: {e}")
            return None

    def _get_detailed_title(self, soup) -> Optional[str]:
        """Extract detailed product title"""
        selectors = ['#productTitle', '.product-title', 'h1.a-size-large']
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                return elem.get_text(strip=True)
        return None

    def _get_detailed_price(self, soup) -> Optional[str]:
        """Extract detailed product price"""
        selectors = [
            '.a-price.a-text-price.a-size-medium.apexPriceToPay .a-offscreen',
            '.a-price .a-offscreen',
            '#priceblock_dealprice',
            '#priceblock_ourprice'
        ]
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                price = elem.get_text(strip=True)
                if '$' in price:
                    return price
        return None

    def _get_detailed_description(self, soup) -> Optional[str]:
        """Extract product description"""
        # Try feature bullets first
        feature_bullets = soup.select('#feature-bullets li')
        if feature_bullets:
            descriptions = []
            for bullet in feature_bullets[:3]:
                text = bullet.get_text(strip=True)
                if text and len(text) > 15 and not text.startswith('Make sure'):
                    descriptions.append(text)
            if descriptions:
                return ' '.join(descriptions)
        
        # Try product description
        desc_elem = soup.select_one('#productDescription p')
        if desc_elem:
            return desc_elem.get_text(strip=True)[:200]
        
        return None

    def _get_detailed_features(self, soup) -> List[str]:
        """Extract product features"""
        features = []
        feature_bullets = soup.select('#feature-bullets li')
        
        for bullet in feature_bullets:
            text = bullet.get_text(strip=True)
            if text and len(text) > 15 and not text.startswith('Make sure'):
                features.append(text)
        
        return features[:5]

    def _get_detailed_images(self, soup) -> List[str]:
        """Extract product images"""
        images = []
        
        # Main image
        main_img = soup.select_one('#landingImage')
        if main_img and main_img.get('src'):
            images.append(main_img['src'])
        
        # Alternative images
        alt_images = soup.select('.a-dynamic-image')
        for img in alt_images:
            if img.get('src') and img['src'] not in images:
                images.append(img['src'])
        
        return images[:3]

    def _get_detailed_rating(self, soup) -> Optional[str]:
        """Extract product rating"""
        rating_elem = soup.select_one('.a-icon-alt')
        if rating_elem:
            rating = rating_elem.get_text(strip=True)
            if 'out of 5' in rating:
                return rating
        return None

    def _get_detailed_reviews_count(self, soup) -> Optional[str]:
        """Extract reviews count"""
        reviews_elem = soup.select_one('#acrCustomerReviewText')
        if reviews_elem:
            return reviews_elem.get_text(strip=True)
        return None

    def _get_detailed_availability(self, soup) -> Optional[str]:
        """Extract availability"""
        avail_elem = soup.select_one('#availability span')
        if avail_elem:
            return avail_elem.get_text(strip=True)
        return None

    def _get_detailed_category(self, soup) -> Optional[str]:
        """Extract product category"""
        breadcrumbs = soup.select('#wayfinding-breadcrumbs_feature_div a')
        if breadcrumbs:
            categories = [a.get_text(strip=True) for a in breadcrumbs]
            return ' > '.join(categories)
        return None

    def create_affiliate_link(self, amazon_url: str) -> str:
        """
        Create Amazon affiliate link
        
        Args:
            amazon_url: Original Amazon URL
            
        Returns:
            Affiliate link with tag
        """
        try:
            # Extract ASIN
            if '/dp/' in amazon_url:
                asin = amazon_url.split('/dp/')[1].split('/')[0].split('?')[0]
            elif '/gp/product/' in amazon_url:
                asin = amazon_url.split('/gp/product/')[1].split('/')[0].split('?')[0]
            else:
                return amazon_url
            
            # Create clean affiliate link
            affiliate_link = f"https://www.amazon.com/dp/{asin}?tag={self.amazon_tag}"
            logger.info(f"Created affiliate link for ASIN {asin}")
            return affiliate_link
            
        except Exception as e:
            logger.error(f"Error creating affiliate link: {e}")
            return amazon_url

    def generate_pin_content(self, product: Dict, category: str) -> Dict:
        """
        Generate Pinterest pin content from product data
        
        Args:
            product: Product information dictionary
            category: Product category
            
        Returns:
            Pin content dictionary
        """
        # Generate engaging title
        title = self._generate_pin_title(product)
        
        # Generate description with features and hashtags
        description = self._generate_pin_description(product, category)
        
        # Get best image
        image_url = self._get_best_image(product)
        
        return {
            'title': title,
            'description': description,
            'image_url': image_url,
            'affiliate_link': self.create_affiliate_link(product['url'])
        }

    def _generate_pin_title(self, product: Dict) -> str:
        """Generate engaging Pinterest title"""
        title = product.get('title', 'Amazing Product')
        
        # Shorten title if too long
        if len(title) > 100:
            title = title[:97] + '...'
        
        # Add engaging elements
        engaging_prefixes = [
            '🔥 TRENDING: ',
            '⭐ TOP RATED: ',
            '💯 MUST-HAVE: ',
            '🎯 BEST SELLER: ',
            '✨ AMAZING: '
        ]
        
        # Add prefix if title is short enough
        if len(title) < 80:
            prefix = random.choice(engaging_prefixes)
            title = prefix + title
        
        return title

    def _generate_pin_description(self, product: Dict, category: str) -> str:
        """Generate Pinterest description with hashtags and disclosure"""
        parts = []
        
        # Add product description
        description = product.get('description', '')
        if description:
            parts.append(description[:150])
        
        # Add price
        price = product.get('price')
        if price:
            parts.append(f"💰 Price: {price}")
        
        # Add rating
        rating = product.get('rating')
        if rating:
            parts.append(f"⭐ Rating: {rating}")
        
        # Add key features
        features = product.get('features', [])
        if features:
            parts.append("✨ Features:")
            for feature in features[:2]:
                parts.append(f"• {feature[:50]}")
        
        # Add category hashtags
        hashtags = self.category_hashtags.get(category, ['shopping', 'deals'])
        hashtag_string = ' '.join([f'#{tag}' for tag in hashtags[:8]])
        parts.append(f"\n{hashtag_string}")
        
        # Add affiliate disclosure
        parts.append("\n📢 This pin contains affiliate links. I may earn a commission at no extra cost to you.")
        
        return '\n'.join(parts)

    def _get_best_image(self, product: Dict) -> str:
        """Get the best available image for the product"""
        images = product.get('images', [])
        if images:
            return images[0]
        
        # Fallback to search result image
        return product.get('image_url', '')

    def get_pinterest_boards(self) -> List[Dict]:
        """Get user's Pinterest boards"""
        try:
            url = f"{self.pinterest_base_url}/boards"
            response = requests.get(url, headers=self.pinterest_headers)
            
            if response.status_code == 200:
                boards = response.json().get('items', [])
                logger.info(f"Retrieved {len(boards)} Pinterest boards")
                return boards
            else:
                logger.error(f"Failed to get Pinterest boards: {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"Error getting Pinterest boards: {e}")
            return []

    def create_pinterest_pin(self, board_id: str, pin_content: Dict) -> Optional[Dict]:
        """
        Create a Pinterest pin
        
        Args:
            board_id: Pinterest board ID
            pin_content: Pin content dictionary
            
        Returns:
            Created pin data or None
        """
        try:
            url = f"{self.pinterest_base_url}/pins"
            
            payload = {
                "board_id": board_id,
                "media_source": {
                    "source_type": "image_url",
                    "url": pin_content['image_url']
                },
                "title": pin_content['title'],
                "description": pin_content['description'],
                "link": pin_content['affiliate_link']
            }
            
            response = requests.post(url, headers=self.pinterest_headers, json=payload)
            
            if response.status_code == 201:
                pin_info = response.json()
                logger.info(f"Successfully created Pinterest pin: {pin_info.get('id')}")
                return pin_info
            else:
                logger.error(f"Failed to create Pinterest pin: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error creating Pinterest pin: {e}")
            return None

    def run_complete_automation(self, category: str = 'electronics', max_products: int = 5, 
                              board_id: Optional[str] = None, post_interval: int = 300) -> Dict:
        """
        Run complete automation: fetch trending products and create Pinterest pins
        
        Args:
            category: Product category to focus on
            max_products: Maximum products to process
            board_id: Pinterest board ID (if None, uses first available board)
            post_interval: Seconds between posts
            
        Returns:
            Summary of automation results
        """
        logger.info(f"Starting complete automation for category: {category}")
        
        results = {
            'products_found': 0,
            'pins_created': 0,
            'errors': 0,
            'success_rate': 0,
            'created_pins': []
        }
        
        try:
            # Get Pinterest boards if board_id not provided
            if not board_id:
                boards = self.get_pinterest_boards()
                if not boards:
                    logger.error("No Pinterest boards available")
                    return results
                board_id = boards[0]['id']
                logger.info(f"Using board: {boards[0]['name']}")
            
            # Fetch trending products
            logger.info("Fetching trending products...")
            trending_products = self.get_trending_products(category, max_products)
            results['products_found'] = len(trending_products)
            
            if not trending_products:
                logger.warning("No trending products found")
                return results
            
            # Process each product
            for i, product in enumerate(trending_products):
                try:
                    logger.info(f"Processing product {i+1}/{len(trending_products)}: {product.get('title', 'Unknown')}")
                    
                    # Get detailed product information
                    detailed_info = self.get_detailed_product_info(product['url'])
                    if detailed_info:
                        product.update(detailed_info)
                    
                    # Generate pin content
                    pin_content = self.generate_pin_content(product, category)
                    
                    # Create Pinterest pin
                    pin_result = self.create_pinterest_pin(board_id, pin_content)
                    
                    if pin_result:
                        results['pins_created'] += 1
                        results['created_pins'].append({
                            'product_title': product.get('title'),
                            'pin_id': pin_result.get('id'),
                            'pin_url': pin_result.get('url')
                        })
                        logger.info(f"✅ Successfully created pin for: {product.get('title')}")
                    else:
                        results['errors'] += 1
                        logger.error(f"❌ Failed to create pin for: {product.get('title')}")
                    
                    # Wait between posts to avoid rate limiting
                    if i < len(trending_products) - 1:
                        logger.info(f"Waiting {post_interval} seconds before next post...")
                        time.sleep(post_interval)
                    
                except Exception as e:
                    logger.error(f"Error processing product {i+1}: {e}")
                    results['errors'] += 1
                    continue
            
            # Calculate success rate
            total_attempts = results['pins_created'] + results['errors']
            if total_attempts > 0:
                results['success_rate'] = (results['pins_created'] / total_attempts) * 100
            
            logger.info(f"Automation completed: {results['pins_created']} pins created, {results['errors']} errors")
            
        except Exception as e:
            logger.error(f"Error in complete automation: {e}")
        
        return results

def main():
    """Main function for testing and demonstration"""
    # Configuration
    PINTEREST_ACCESS_TOKEN = "your_pinterest_access_token_here"
    AMAZON_ASSOCIATE_TAG = "your_amazon_associate_tag_here"
    
    # Initialize bot
    bot = TrendingAmazonPinterestBot(PINTEREST_ACCESS_TOKEN, AMAZON_ASSOCIATE_TAG)
    
    print("🤖 Trending Amazon Pinterest Bot")
    print("=" * 50)
    
    # Test configuration
    if PINTEREST_ACCESS_TOKEN == "your_pinterest_access_token_here":
        print("⚠️  Please update your Pinterest access token in the script")
        return
    
    if AMAZON_ASSOCIATE_TAG == "your_amazon_associate_tag_here":
        print("⚠️  Please update your Amazon associate tag in the script")
        return
    
    # Get available boards
    boards = bot.get_pinterest_boards()
    if boards:
        print("\n📌 Available Pinterest Boards:")
        for i, board in enumerate(boards[:5]):
            print(f"{i+1}. {board['name']} (ID: {board['id']})")
    
    # Run automation for different categories
    categories = ['electronics', 'home', 'fashion']
    
    for category in categories:
        print(f"\n🔥 Running automation for category: {category}")
        
        # Run automation with 3 products max for testing
        results = bot.run_complete_automation(
            category=category,
            max_products=3,
            post_interval=60  # 1 minute between posts for testing
        )
        
        print(f"📊 Results for {category}:")
        print(f"   Products found: {results['products_found']}")
        print(f"   Pins created: {results['pins_created']}")
        print(f"   Errors: {results['errors']}")
        print(f"   Success rate: {results['success_rate']:.1f}%")
        
        # Display created pins
        for pin in results['created_pins']:
            print(f"   ✅ Created: {pin['product_title'][:50]}...")
        
        # Wait between categories
        time.sleep(120)  # 2 minutes between categories

if __name__ == "__main__":
    main()
