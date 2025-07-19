#!/usr/bin/env python3
"""
🦚 Peacock Memory - Proxy Manager
Manages mobile/residential proxies with 60-second IP rotation
"""

import requests
import time
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import json
from enum import Enum

class ProxyType(Enum):
    MOBILE = "mobile"
    RESIDENTIAL = "residential"
    LOCAL = "local"

class ProxyManager:
    """Manages proxy rotation and health checking"""
    
    def __init__(self):
        # Mobile proxies (60-second rotation)
        self.mobile_proxies = [
            "52fb2fcd77ccbf54b65c:5a02792bf800a049@gw.dataimpulse.com:823"
        ] * 3  # You had 3 identical entries
        
        # Residential proxies
        self.residential_proxies = [
            "0aa180faa467ad67809b__cr.us:6dc612d4a08ca89d@gw.dataimpulse.com:823"
        ] * 3  # You had 3 identical entries
        
        self.current_proxy: Optional[str] = None
        self.current_proxy_type: Optional[ProxyType] = None
        self.proxy_health: Dict[str, dict] = {}
        self.last_rotation_time: Optional[datetime] = None
        self.rotation_interval = 60  # 60 seconds for IP rotation
        
        self.initialize_proxy_health()
    
    def initialize_proxy_health(self):
        """Initialize health tracking for all proxies"""
        all_proxies = self.mobile_proxies + self.residential_proxies
        
        for proxy in set(all_proxies):  # Remove duplicates
            self.proxy_health[proxy] = {
                'healthy': True,
                'last_check': None,
                'response_time': None,
                'error_count': 0,
                'last_error': None,
                'success_rate': 100.0
            }
    
    def format_proxy_for_requests(self, proxy_string: str) -> Dict[str, str]:
        """Convert proxy string to requests format"""
        if not proxy_string:
            return {}
        
        # Format: username:password@host:port
        auth_part, host_part = proxy_string.split('@')
        username, password = auth_part.split(':')
        host, port = host_part.split(':')
        
        proxy_url = f"http://{username}:{password}@{host}:{port}"
        
        return {
            'http': proxy_url,
            'https': proxy_url
        }
    
    def check_proxy_health(self, proxy: str, timeout: int = 10) -> bool:
        """Check if proxy is healthy"""
        try:
            proxy_dict = self.format_proxy_for_requests(proxy)
            start_time = time.time()
            
            # Test with a simple HTTP request
            response = requests.get(
                'http://httpbin.org/ip',
                proxies=proxy_dict,
                timeout=timeout
            )
            
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                # Update health stats
                self.proxy_health[proxy]['healthy'] = True
                self.proxy_health[proxy]['last_check'] = datetime.now()
                self.proxy_health[proxy]['response_time'] = response_time
                self.proxy_health[proxy]['error_count'] = 0
                
                proxy_short = proxy.split('@')[1]  # Just host:port for display
                print(f"✅ Proxy healthy: {proxy_short} ({response_time:.2f}s)")
                return True
            else:
                raise Exception(f"HTTP {response.status_code}")
                
        except Exception as e:
            # Update error stats
            self.proxy_health[proxy]['healthy'] = False
            self.proxy_health[proxy]['last_check'] = datetime.now()
            self.proxy_health[proxy]['error_count'] += 1
            self.proxy_health[proxy]['last_error'] = str(e)
            
            proxy_short = proxy.split('@')[1] if '@' in proxy else proxy
            print(f"❌ Proxy failed: {proxy_short} - {e}")
            return False
    
    def get_best_proxy(self, proxy_type: ProxyType = ProxyType.MOBILE) -> Optional[str]:
        """Get the best available proxy of specified type"""
        if proxy_type == ProxyType.LOCAL:
            return None  # No proxy for local IP
        
        # Select proxy pool
        proxy_pool = []
        if proxy_type == ProxyType.MOBILE:
            proxy_pool = self.mobile_proxies
        elif proxy_type == ProxyType.RESIDENTIAL:
            proxy_pool = self.residential_proxies
        
        # Remove duplicates and get unique proxies
        unique_proxies = list(set(proxy_pool))
        
        # Check if we need to rotate (60 seconds for mobile proxies)
        if (proxy_type == ProxyType.MOBILE and 
            self.last_rotation_time and 
            datetime.now() - self.last_rotation_time < timedelta(seconds=self.rotation_interval)):
            
            # Still within rotation window, use current proxy if healthy
            if self.current_proxy and self.proxy_health.get(self.current_proxy, {}).get('healthy'):
                return self.current_proxy
        
        # Find healthiest proxy
        best_proxy = None
        best_score = -1
        
        for proxy in unique_proxies:
            if self.check_proxy_health(proxy):
                # Score based on response time and error count
                health_data = self.proxy_health[proxy]
                response_time = health_data.get('response_time', 999)
                error_count = health_data.get('error_count', 0)
                
                # Lower response time and error count = higher score
                score = 100 - (response_time * 10) - (error_count * 5)
                
                if score > best_score:
                    best_score = score
                    best_proxy = proxy
        
        if best_proxy:
            self.current_proxy = best_proxy
            self.current_proxy_type = proxy_type
            self.last_rotation_time = datetime.now()
            
            proxy_short = best_proxy.split('@')[1]
            print(f"🎯 Selected {proxy_type.value} proxy: {proxy_short}")
        
        return best_proxy
    
    def get_proxy_for_request(self, prefer_type: ProxyType = ProxyType.MOBILE) -> Dict[str, str]:
        """Get proxy configuration for requests"""
        if prefer_type == ProxyType.LOCAL:
            print("🏠 Using local IP (no proxy)")
            return {}
        
        proxy = self.get_best_proxy(prefer_type)
        if proxy:
            return self.format_proxy_for_requests(proxy)
        
        # Fallback to other proxy type
        fallback_type = ProxyType.RESIDENTIAL if prefer_type == ProxyType.MOBILE else ProxyType.MOBILE
        print(f"⚠️ Falling back to {fallback_type.value} proxy")
        
        fallback_proxy = self.get_best_proxy(fallback_type)
        if fallback_proxy:
            return self.format_proxy_for_requests(fallback_proxy)
        
        # Ultimate fallback - no proxy
        print("⚠️ All proxies failed, using local IP")
        return {}
    
    def force_rotation(self):
        """Force immediate proxy rotation"""
        self.last_rotation_time = None
        print("🔄 Forced proxy rotation")
    
    def get_proxy_status(self) -> dict:
        """Get current proxy status"""
        return {
            'current_proxy': self.current_proxy.split('@')[1] if self.current_proxy else None,
            'current_type': self.current_proxy_type.value if self.current_proxy_type else None,
            'last_rotation': self.last_rotation_time.isoformat() if self.last_rotation_time else None,
            'health_summary': {
                proxy.split('@')[1]: {
                    'healthy': data['healthy'],
                    'response_time': data.get('response_time'),
                    'error_count': data['error_count']
                }
                for proxy, data in self.proxy_health.items()
            }
        }

# Example usage and testing
if __name__ == "__main__":
    proxy_manager = ProxyManager()
    
    print("\n🧪 Testing proxy selection:")
    
    # Test mobile proxy
    mobile_config = proxy_manager.get_proxy_for_request(ProxyType.MOBILE)
    print(f"Mobile proxy config: {bool(mobile_config)}")
    
    # Test residential proxy  
    residential_config = proxy_manager.get_proxy_for_request(ProxyType.RESIDENTIAL)
    print(f"Residential proxy config: {bool(residential_config)}")
    
    # Test local IP
    local_config = proxy_manager.get_proxy_for_request(ProxyType.LOCAL)
    print(f"Local IP config: {bool(local_config)}")
    
    print(f"\n📊 Proxy Status: {proxy_manager.get_proxy_status()}")
