import os
import csv
import json
import zipfile
import asyncio
import logging
from io import BytesIO
from typing import Set

import httpx  # type: ignore[import]
from config import URLConfig  # type: ignore[import]

logger = logging.getLogger("sentineliq.reputation")

class TrancoCache:
    _top_domains: Set[str] = set()
    _is_ready: bool = False

    @classmethod
    async def initialize(cls, cache_dir: str = "./model_cache") -> None:
        """Fetch or load Tranco Top 10k domains."""
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, URLConfig.TRANCO_CACHE_FILE)

        # 1. Try to load from disk
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        cls._top_domains = set(data)
                        cls._is_ready = True
                        logger.info(f"Loaded {len(cls._top_domains)} Tranco domains from local cache.")
                        return
            except Exception as e:
                logger.warning(f"Failed to read Tranco cache from {cache_path}: {e}")

        # 2. Fetch from Tranco API (or fallback hardcoded fetch mechanism)
        logger.info(f"Fetching Tranco top domains from {URLConfig.TRANCO_TOP_10K_URL}...")
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client: # type: ignore
                resp = await client.get(URLConfig.TRANCO_TOP_10K_URL)
                resp.raise_for_status()
                
                with zipfile.ZipFile(BytesIO(resp.content)) as z:
                    csv_filename = z.namelist()[0]
                    with z.open(csv_filename) as csvfile:
                        content = csvfile.read().decode('utf-8').splitlines()
                        
                        top_10k = []
                        for row in content[:10000]:  # Only grab Top 10k for Tier 1
                            parts = row.strip().split(',')
                            if len(parts) >= 2:
                                top_10k.append(parts[1].strip().lower())
                        
                        cls._top_domains = set(top_10k)
                        cls._is_ready = True
                        
                # Save to cache
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(list(cls._top_domains), f)
                    
                logger.info(f"Successfully loaded {len(cls._top_domains)} domains into Tranco reputation cache.")
        except Exception as e:
            logger.error(f"Failed to fetch Tranco list: {e}")
            cls._top_domains = set()  # Empty fallback
            cls._is_ready = True

    @classmethod
    def is_tier_1_reputation(cls, domain: str) -> bool:
        """
        Check if domain is in Tier 1 Fast Pass.
        Returns False if the domain is in HOSTED_PLATFORMS exception list.
        """
        d = str(domain).lower().strip()
        if not d:
            return False
            
        # 1. Check exception list (e.g. vercel.app, github.io)
        for platform in URLConfig.HOSTED_PLATFORMS:
            if d == platform or d.endswith("." + platform):
                return False
                
        # 2. Check institutional TLDs
        for tld in getattr(URLConfig, "TRUSTED_TLDS", set()):
            if d.endswith(tld):
                return True

        # 3. Check Tranco Top 10k
        if d in cls._top_domains:
            return True
            
        return False
