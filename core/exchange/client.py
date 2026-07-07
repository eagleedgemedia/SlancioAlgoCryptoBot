"""
Slancio Crypto Algo Treding Engine — Delta Exchange REST API Client
======================================================
Handles authentication (HMAC-SHA256 signing), rate limiting,
and all HTTP communication with the Delta Exchange v2 API.

Authentication flow:
    1. Construct message = METHOD + TIMESTAMP + PATH + QUERY_STRING + BODY
    2. Sign with HMAC-SHA256 using API Secret
    3. Attach headers: api-key, timestamp, signature

Usage:
    from core.exchange.client import DeltaExchangeClient
    
    client = DeltaExchangeClient(api_key="...", api_secret="...")
    products = client.get_products()
    candles = client.get_candles("BTCUSDT", "1h", start=..., end=...)
"""

from __future__ import annotations

import hmac
import hashlib
import json
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import requests
from loguru import logger

from core.config import get_settings, ENDPOINTS


class DeltaExchangeError(Exception):
    """Custom exception for Delta Exchange API errors."""

    def __init__(self, message: str, status_code: int = None, response: dict = None):
        self.status_code = status_code
        self.response = response
        super().__init__(message)


class DeltaExchangeClient:
    """
    Low-level REST API client for Delta Exchange v2.
    
    Supports both authenticated (private) and unauthenticated (public) endpoints.
    All API responses are validated and errors are raised as DeltaExchangeError.
    
    Args:
        api_key: Delta Exchange API key (optional for public endpoints)
        api_secret: Delta Exchange API secret (optional for public endpoints)
        base_url: Override the default base URL from settings
        timeout: HTTP request timeout in seconds
    """

    def __init__(
        self,
        api_key: str = None,
        api_secret: str = None,
        base_url: str = None,
        timeout: int = 30,
    ):
        settings = get_settings()
        self.api_key = api_key or settings.delta_api_key
        self.api_secret = api_secret or settings.delta_api_secret
        self.base_url = (base_url or settings.base_url).rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        
        # Set default headers
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "KSL-AlgoCryptoBot/1.0",
        })

        logger.info(
            f"DeltaExchangeClient initialized | "
            f"Region: {settings.delta_exchange_region.value} | "
            f"Base URL: {self.base_url}"
        )

    # ═══════════════════════════════════════════════════
    # Authentication & Signing
    # ═══════════════════════════════════════════════════

    def _generate_signature(
        self,
        method: str,
        path: str,
        timestamp: int,
        query_string: str = "",
        body: str = "",
    ) -> str:
        """
        Generate HMAC-SHA256 signature for request authentication.
        
        Delta Exchange signature format:
            message = METHOD + TIMESTAMP + PATH + QUERY_STRING + BODY
            signature = HMAC-SHA256(api_secret, message)
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            path: API endpoint path (e.g., /v2/orders)
            timestamp: Current epoch timestamp in seconds
            query_string: URL query string (without '?')
            body: JSON request body string
            
        Returns:
            Hexadecimal signature string
        """
        message = f"{method}{timestamp}{path}"
        if query_string:
            message += f"?{query_string}"
        if body:
            message += body

        signature = hmac.new(
            key=self.api_secret.encode("utf-8"),
            msg=message.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

        return signature

    def _get_auth_headers(
        self,
        method: str,
        path: str,
        query_string: str = "",
        body: str = "",
    ) -> Dict[str, str]:
        """
        Build authenticated request headers.
        
        Returns:
            Dictionary with api-key, timestamp, and signature headers
        """
        timestamp = int(time.time())
        signature = self._generate_signature(
            method=method,
            path=path,
            timestamp=timestamp,
            query_string=query_string,
            body=body,
        )

        return {
            "api-key": self.api_key,
            "timestamp": str(timestamp),
            "signature": signature,
        }

    # ═══════════════════════════════════════════════════
    # HTTP Request Methods
    # ═══════════════════════════════════════════════════

    def _request(
        self,
        method: str,
        path: str,
        params: Dict[str, Any] = None,
        data: Dict[str, Any] = None,
        authenticated: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute an HTTP request to the Delta Exchange API.
        
        Args:
            method: HTTP method
            path: API endpoint path
            params: URL query parameters
            data: JSON request body
            authenticated: Whether to include auth headers
            
        Returns:
            Parsed JSON response dictionary
            
        Raises:
            DeltaExchangeError: On API errors or network failures
        """
        url = f"{self.base_url}{path}"
        query_string = urlencode(params) if params else ""
        body_str = json.dumps(data) if data else ""

        headers = {}
        if authenticated:
            if not self.api_key or not self.api_secret:
                raise DeltaExchangeError(
                    "API key and secret are required for authenticated endpoints. "
                    "Set DELTA_API_KEY and DELTA_API_SECRET in your .env file."
                )
            headers = self._get_auth_headers(
                method=method.upper(),
                path=path,
                query_string=query_string,
                body=body_str,
            )

        try:
            logger.debug(f"API Request: {method.upper()} {url} | Params: {params}")

            response = self.session.request(
                method=method.upper(),
                url=url,
                params=params,
                json=data,
                headers=headers,
                timeout=self.timeout,
            )

            # Parse response
            try:
                result = response.json()
            except ValueError:
                raise DeltaExchangeError(
                    f"Invalid JSON response from API: {response.text[:500]}",
                    status_code=response.status_code,
                )

            # Check for API-level errors
            if response.status_code >= 400:
                error_msg = result.get("error", {}).get("message", response.text[:200])
                raise DeltaExchangeError(
                    f"API Error ({response.status_code}): {error_msg}",
                    status_code=response.status_code,
                    response=result,
                )

            # Delta API wraps successful responses in {"success": true, "result": ...}
            if isinstance(result, dict) and "success" in result:
                if not result.get("success"):
                    error_info = result.get("error", "Unknown error")
                    raise DeltaExchangeError(
                        f"API returned success=false: {error_info}",
                        response=result,
                    )
                return result.get("result", result)

            return result

        except requests.exceptions.Timeout:
            raise DeltaExchangeError(f"Request timed out after {self.timeout}s: {method} {path}")
        except requests.exceptions.ConnectionError as e:
            raise DeltaExchangeError(f"Connection error: {e}")
        except DeltaExchangeError:
            raise
        except Exception as e:
            raise DeltaExchangeError(f"Unexpected error: {e}")

    def get(self, path: str, params: dict = None, authenticated: bool = False) -> Any:
        """Execute a GET request."""
        return self._request("GET", path, params=params, authenticated=authenticated)

    def post(self, path: str, data: dict = None, authenticated: bool = True) -> Any:
        """Execute a POST request (authenticated by default)."""
        return self._request("POST", path, data=data, authenticated=authenticated)

    def put(self, path: str, data: dict = None, authenticated: bool = True) -> Any:
        """Execute a PUT request (authenticated by default)."""
        return self._request("PUT", path, data=data, authenticated=authenticated)

    def delete(self, path: str, data: dict = None, authenticated: bool = True) -> Any:
        """Execute a DELETE request (authenticated by default)."""
        return self._request("DELETE", path, data=data, authenticated=authenticated)

    # ═══════════════════════════════════════════════════
    # Public API Methods (No Authentication Required)
    # ═══════════════════════════════════════════════════

    def get_products(self) -> List[Dict]:
        """
        Fetch all available trading products.
        
        Returns:
            List of product dictionaries with id, symbol, description, etc.
        """
        logger.info("Fetching product list from Delta Exchange")
        return self.get(ENDPOINTS["products"])

    def get_product_by_symbol(self, symbol: str) -> Dict:
        """
        Fetch a specific product by its trading symbol.
        
        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            
        Returns:
            Product dictionary with id, symbol, specs, etc.
        """
        path = ENDPOINTS["product_by_symbol"].format(symbol=symbol)
        return self.get(path)

    def get_ticker(self, symbol: str) -> Dict:
        """
        Get the current ticker for a product.
        
        Args:
            symbol: Trading pair symbol
            
        Returns:
            Ticker dict with mark_price, last_price, volume, etc.
        """
        path = ENDPOINTS["ticker"].format(symbol=symbol)
        return self.get(path)

    def get_candles(
        self,
        symbol: str,
        resolution: str,
        start: int = None,
        end: int = None,
    ) -> List[Dict]:
        """
        Fetch historical OHLC candle data.
        
        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            resolution: Candle timeframe (e.g., "1h", "5m", "1d")
            start: Start timestamp (Unix epoch seconds)
            end: End timestamp (Unix epoch seconds)
            
        Returns:
            List of candle dicts with keys: time, open, high, low, close, volume
            
        Note:
            Maximum 2000 candles per request. For larger datasets,
            use DataFeed.fetch_historical_candles() which handles pagination.
        """
        params = {
            "resolution": resolution,
            "symbol": symbol,
        }
        if start is not None:
            params["start"] = str(start)
        if end is not None:
            params["end"] = str(end)

        logger.info(
            f"Fetching candles | Symbol: {symbol} | Resolution: {resolution} | "
            f"Start: {start} | End: {end}"
        )

        return self.get(ENDPOINTS["candles"], params=params)

    def get_orderbook(self, symbol: str) -> Dict:
        """
        Get L2 orderbook for a product.
        
        Args:
            symbol: Trading pair symbol
            
        Returns:
            Orderbook dict with buy and sell arrays
        """
        path = ENDPOINTS["l2_orderbook"].format(symbol=symbol)
        return self.get(path)

    # ═══════════════════════════════════════════════════
    # Private API Methods (Authentication Required)
    # ═══════════════════════════════════════════════════

    def get_wallet_balances(self) -> List[Dict]:
        """Get wallet balances for all assets."""
        return self.get(ENDPOINTS["wallet_balances"], authenticated=True)

    def get_positions(self, product_id: int = None) -> Any:
        """
        Get current open positions.
        
        Args:
            product_id: Optional product ID to filter positions
            
        Returns:
            Position data (list or single position dict)
        """
        params = {}
        if product_id is not None:
            params["product_id"] = product_id
        return self.get(ENDPOINTS["position"], params=params, authenticated=True)

    def get_margined_positions(self) -> List[Dict]:
        """Get all margined (open) positions."""
        return self.get(ENDPOINTS["positions_margined"], authenticated=True)

    def place_order(
        self,
        product_id: int,
        size: int,
        side: str,
        order_type: str = "market_order",
        limit_price: float = None,
        stop_price: float = None,
        stop_order_type: str = None,
        reduce_only: bool = False,
        client_order_id: str = None,
    ) -> Dict:
        """
        Place a new order on Delta Exchange.
        
        Args:
            product_id: Product ID (integer, from get_products)
            size: Number of contracts
            side: "buy" or "sell"
            order_type: "market_order" or "limit_order"
            limit_price: Required for limit orders
            stop_price: Stop trigger price
            stop_order_type: "stop_loss_order" or "take_profit_order"
            reduce_only: If True, only reduces existing position
            client_order_id: Custom order identifier
            
        Returns:
            Order confirmation dictionary
        """
        payload = {
            "product_id": product_id,
            "size": size,
            "side": side,
            "order_type": order_type,
        }

        if limit_price is not None:
            payload["limit_price"] = str(limit_price)
        if stop_price is not None:
            payload["stop_price"] = str(stop_price)
        if stop_order_type is not None:
            payload["stop_order_type"] = stop_order_type
        if reduce_only:
            payload["reduce_only"] = True
        if client_order_id is not None:
            payload["client_order_id"] = client_order_id

        logger.info(
            f"Placing order | Product: {product_id} | Side: {side} | "
            f"Size: {size} | Type: {order_type}"
        )

        return self.post(ENDPOINTS["place_order"], data=payload)

    def cancel_order(self, order_id: int, product_id: int) -> Dict:
        """Cancel an active order."""
        payload = {
            "id": order_id,
            "product_id": product_id,
        }
        return self.delete(ENDPOINTS["cancel_order"], data=payload)

    def set_leverage(self, product_id: int, leverage: int) -> Dict:
        """
        Set leverage for a product.
        
        Args:
            product_id: Product ID
            leverage: Desired leverage (1-20x)
        """
        path = ENDPOINTS["order_leverage"].format(product_id=product_id)
        return self.post(path, data={"leverage": leverage})

    def get_order_history(
        self,
        product_id: int = None,
        page_size: int = 100,
        after: str = None,
    ) -> List[Dict]:
        """Get order history (cancelled and closed orders)."""
        params = {"page_size": page_size}
        if product_id:
            params["product_id"] = product_id
        if after:
            params["after"] = after
        return self.get(ENDPOINTS["order_history"], params=params, authenticated=True)

    # ═══════════════════════════════════════════════════
    # Connection Testing
    # ═══════════════════════════════════════════════════

    def test_connection(self) -> bool:
        """
        Test API connectivity by fetching product list.
        
        Returns:
            True if connection is successful
        """
        try:
            products = self.get_products()
            logger.info(f"✅ Connection successful! {len(products)} products available.")
            return True
        except DeltaExchangeError as e:
            logger.error(f"❌ Connection failed: {e}")
            return False

    def test_auth(self) -> bool:
        """
        Test authenticated API access by fetching wallet balances.
        
        Returns:
            True if authentication is successful
        """
        try:
            balances = self.get_wallet_balances()
            logger.info(f"✅ Authentication successful! Wallet balances retrieved.")
            return True
        except DeltaExchangeError as e:
            logger.error(f"❌ Authentication failed: {e}")
            return False


# ═══════════════════════════════════════════════════
# Module-level convenience function
# ═══════════════════════════════════════════════════

def create_client(
    api_key: str = None,
    api_secret: str = None,
    base_url: str = None,
) -> DeltaExchangeClient:
    """
    Factory function to create a DeltaExchangeClient instance.
    
    Uses settings from .env if api_key/api_secret are not provided.
    """
    return DeltaExchangeClient(
        api_key=api_key,
        api_secret=api_secret,
        base_url=base_url,
    )
