import requests
import time
from typing import Dict

class PriceFetcher:
    def __init__(self, api_key: str = None):
        self.api_key = api_key
        # Use demo API endpoint for demo keys
        if api_key:
            self.base_url = "https://api.coingecko.com/api/v3"
        else:
            self.base_url = "https://api.coingecko.com/api/v3"
        self.price_cache = {}

        # Mapping of Aave V3 assets to CoinGecko IDs
        # Synced with fetch_historical_prices.py (24 assets)
        self.asset_mapping = {
            # Major ETH assets
            'WETH': 'weth',
            'weETH': 'wrapped-eeth',
            'wstETH': 'wrapped-steth',
            # Restaked/Liquid Restaking Tokens (LRTs)
            'rsETH': 'kelp-dao-restaked-eth',
            'ezETH': 'renzo-restaked-eth',
            'osETH': 'stakewise-v3-oseth',
            'ETHx': 'stader-ethx',
            'tETH': 'treehouse-eth',
            # BTC assets
            'WBTC': 'wrapped-bitcoin',
            'cbBTC': 'coinbase-wrapped-btc',
            'LBTC': 'lombard-staked-btc',
            'FBTC': 'ignition-fbtc',
            'eBTC': 'ether-fi-staked-btc',
            # Stablecoins
            'USDC': 'usd-coin',
            'USDT': 'tether',
            'PYUSD': 'paypal-usd',
            'USDe': 'ethena-usde',
            'sUSDe': 'ethena-staked-usde',
            'crvUSD': 'crvusd',
            'sDAI': 'savings-dai',
            # DeFi tokens
            'AAVE': 'aave',
            'FXS': 'frax-share',
            'KNC': 'kyber-network-crystal',
            'XAUt': 'tether-gold',
            # Additional assets (for backwards compatibility)
            'ETH': 'ethereum',
            'DAI': 'dai',
            'LINK': 'chainlink',
            'UNI': 'uniswap',
            'CRV': 'curve-dao-token',
            'BAL': 'balancer',
            'SNX': 'havven',
            'MKR': 'maker',
            'rETH': 'rocket-pool-eth',
            'stETH': 'staked-ether',
            'cbETH': 'coinbase-wrapped-staked-eth',
            'GHO': 'gho',
            'LUSD': 'liquity-usd',
            'FRAX': 'frax',
            'tBTC': 'tbtc',
            'USDS': 'usds',
        }

    def get_price(self, symbol: str) -> float:
        """Get current USD price for a symbol"""
        if symbol in self.price_cache:
            return self.price_cache[symbol]

        try:
            coingecko_id = self.asset_mapping.get(symbol)
            if not coingecko_id:
                print(f"Warning: No CoinGecko mapping for {symbol}, defaulting to 0")
                return 0.0

            # Rate limiting for free tier (50 calls/minute)
            time.sleep(1.2)

            url = f"{self.base_url}/simple/price"
            params = {
                'ids': coingecko_id,
                'vs_currencies': 'usd'
            }
            if self.api_key:
                params['x_cg_demo_api_key'] = self.api_key

            response = requests.get(url, params=params)
            response.raise_for_status()
            price_data = response.json()

            price = price_data.get(coingecko_id, {}).get('usd', 0.0)

            self.price_cache[symbol] = price
            return price

        except Exception as e:
            print(f"Error fetching price for {symbol}: {e}")
            return 0.0

    def get_prices_batch(self, symbols: list) -> Dict[str, float]:
        """Get prices for multiple symbols in one call"""
        unique_symbols = list(set(symbols))
        coingecko_ids = [self.asset_mapping.get(s) for s in unique_symbols if s in self.asset_mapping]

        if not coingecko_ids:
            return {s: 0.0 for s in unique_symbols}

        try:
            # Rate limiting
            time.sleep(1.2)

            url = f"{self.base_url}/simple/price"
            params = {
                'ids': ','.join(coingecko_ids),
                'vs_currencies': 'usd'
            }
            if self.api_key:
                params['x_cg_demo_api_key'] = self.api_key

            response = requests.get(url, params=params)
            response.raise_for_status()
            price_data = response.json()

            result = {}
            for symbol in unique_symbols:
                coingecko_id = self.asset_mapping.get(symbol)
                if coingecko_id and coingecko_id in price_data:
                    result[symbol] = price_data[coingecko_id].get('usd', 0.0)
                else:
                    result[symbol] = 0.0

            self.price_cache.update(result)
            return result

        except Exception as e:
            print(f"Error fetching batch prices: {e}")
            return {s: 0.0 for s in unique_symbols}
