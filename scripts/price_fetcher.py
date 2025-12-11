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
        self.defillama_url = "https://coins.llama.fi/prices/current"
        self.price_cache = {}

        # Contract addresses for tokens not on CoinGecko (fetch from DeFiLlama)
        self.defillama_tokens = {
            'PT-USDe-27NOV2025': '0x62c6e813b9589c3631ba0cdb013acdb8544038b7',
            'PT-USDe-5FEB2026': '0x1f84a51296691320478c98b8d77f2bbd17d34350',
            'PT-sUSDE-27NOV2025': '0xe6a934089bbee34f832060ce98848359883749b3',
            'PT-sUSDE-5FEB2026': '0xe8483517077afa11a9b07f849cee2552f040d7b2',
            'eUSDe': '0x90d2af7d622ca3141efa4d8f1f24d86e5974cc8f',
            # Add more PT tokens as needed
            'PT-USDe-31JUL2025': '0x917459337aabc2b2f2e30876a8a3e8a7b1e1e8b8',
            'PT-sUSDE-31JUL2025': '0x3e034304c4dcc9b7f5768b1b8a1b58fd7f8e4d8f',
            'PT-sUSDE-25SEP2025': '0x9c07627d105b82f9c2c77e4b3e6e8f7a8f9d1e2c',
            'PT-USDe-25SEP2025': '0x8d5127ab6221f7c99a29294ac5f6a09ed322ac1e',
        }

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

    def get_defillama_prices(self, symbols: list) -> Dict[str, float]:
        """Fetch prices from DeFiLlama for tokens not on CoinGecko (like PT-* tokens)"""
        # Filter to only tokens we have DeFiLlama addresses for
        tokens_to_fetch = {s: self.defillama_tokens[s] for s in symbols if s in self.defillama_tokens}

        if not tokens_to_fetch:
            return {}

        try:
            # Build DeFiLlama query string
            addresses = ','.join([f'ethereum:{addr}' for addr in tokens_to_fetch.values()])
            url = f"{self.defillama_url}/{addresses}"

            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            result = {}
            for symbol, addr in tokens_to_fetch.items():
                key = f'ethereum:{addr}'
                if key in data.get('coins', {}):
                    price = data['coins'][key].get('price', 0)
                    if price > 0:
                        result[symbol] = price
                        print(f"  DeFiLlama: {symbol} = ${price:.4f}")

            return result

        except Exception as e:
            print(f"Error fetching DeFiLlama prices: {e}")
            return {}

    def get_prices_batch_with_fallback(self, symbols: list) -> Dict[str, float]:
        """Get prices for multiple symbols, using DeFiLlama as fallback for missing tokens"""
        # First try CoinGecko
        result = self.get_prices_batch(symbols)

        # Find symbols with price = 0 that might be on DeFiLlama
        missing_symbols = [s for s in symbols if result.get(s, 0) == 0]

        if missing_symbols:
            defillama_prices = self.get_defillama_prices(missing_symbols)
            result.update(defillama_prices)

        return result
