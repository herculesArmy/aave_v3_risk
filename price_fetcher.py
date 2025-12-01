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

        # Mapping of common Aave assets to CoinGecko IDs
        self.asset_mapping = {
            'WETH': 'weth',
            'ETH': 'ethereum',
            'USDC': 'usd-coin',
            'USDT': 'tether',
            'DAI': 'dai',
            'WBTC': 'wrapped-bitcoin',
            'LINK': 'chainlink',
            'AAVE': 'aave',
            'UNI': 'uniswap',
            'MATIC': 'matic-network',
            'CRV': 'curve-dao-token',
            'SUSHI': 'sushi',
            'BAL': 'balancer',
            'YFI': 'yearn-finance',
            'SNX': 'havven',
            'MKR': 'maker',
            'ENS': 'ethereum-name-service',
            'FRAX': 'frax',
            'LUSD': 'liquity-usd',
            'sUSD': 'nusd',
            'TUSD': 'true-usd',
            'BUSD': 'binance-usd',
            'rETH': 'rocket-pool-eth',
            'stETH': 'staked-ether',
            'cbETH': 'coinbase-wrapped-staked-eth',
            'wstETH': 'wrapped-steth',
            'RPL': 'rocket-pool',
            'cbBTC': 'coinbase-wrapped-btc',
            'EURC': 'euro-coin',
            'USDe': 'ethena-usde',
            'USDtb': 'usdtb',
            'weETH': 'wrapped-eeth',
            'STG': 'stargate-finance',
            'LDO': 'lido-dao',
            '1INCH': '1inch',
            'RLUSD': 'ripple-usd',
            'GHO': 'gho',
            'PYUSD': 'paypal-usd',
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
