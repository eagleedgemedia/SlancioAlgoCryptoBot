"""
Slancio Crypto Algo Treding Engine — Position Sizing & Risk Management
=========================================================
Calculates optimal position sizes based on current capital,
maximum risk percentage, and exchange specifications.
"""

from __future__ import annotations

import math
from loguru import logger
from core.config import get_settings
from core.exchange.client import DeltaExchangeClient


class PositionSizer:
    def __init__(self, client: DeltaExchangeClient = None):
        self.settings = get_settings()
        self.client = client
        
        # We will cache the contract size for the symbol to avoid repeated API calls
        self._contract_size: float = None

    def _get_contract_size(self, symbol: str) -> float:
        """
        Fetch the contract size (contract_value) for the trading pair from the exchange.
        e.g., For BTCUSD, 1 contract might be 1 USD or 0.001 BTC.
        """
        if self._contract_size is not None:
            return self._contract_size
            
        if not self.client:
            logger.warning("No client provided to PositionSizer, defaulting contract size to 1.0")
            return 1.0
            
        try:
            product = self.client.get_product_by_symbol(symbol)
            # Delta specifies contract value in the product details
            contract_value = float(product.get("contract_value", 1.0))
            self._contract_size = contract_value
            return contract_value
        except Exception as e:
            logger.error(f"Failed to fetch contract size for {symbol}: {e}")
            return 1.0

    def calculate_position_size(
        self, 
        symbol: str, 
        current_price: float, 
        available_balance: float
    ) -> int:
        """
        Calculate how many contracts to buy/sell to meet the max position percentage.
        
        Logic:
            1. Total exposure allowed = available_balance * max_position_pct
            2. Leveraged exposure = Total exposure allowed * max_leverage
            3. Quantity = Leveraged exposure / current_price
            4. Contracts = Quantity / contract_size
            
        Args:
            symbol: Trading pair (e.g., BTCUSD)
            current_price: Current market price
            available_balance: Total available wallet balance in settlement currency (USDT)
            
        Returns:
            Number of contracts (integer)
        """
        max_pct = self.settings.max_position_pct  # e.g. 0.02 (2%)
        leverage = self.settings.max_leverage      # e.g. 10
        
        # 1. How much of our own capital we are willing to use for margin
        margin_allowed = available_balance * max_pct
        
        # 2. Total buying power with leverage
        buying_power = margin_allowed * leverage
        
        # 3. How much underlying crypto that buys
        quantity_crypto = buying_power / current_price
        
        # 4. Convert to exchange contracts
        contract_size = self._get_contract_size(symbol)
        contracts_raw = quantity_crypto / contract_size
        
        # Always floor the contracts to be safe
        contracts = math.floor(contracts_raw)
        
        # Fallback to minimum 1 contract if math results in 0 but we have *some* balance
        if contracts == 0 and available_balance > 0:
            logger.warning(f"Calculated 0 contracts for balance {available_balance}. Defaulting to 1 contract if within risk limits.")
            # Verify 1 contract doesn't exceed our absolute risk limits
            cost_of_one = (1 * contract_size * current_price) / leverage
            if cost_of_one <= margin_allowed:
                contracts = 1
                
        logger.info(
            f"⚖️ Position Sizing | Bal: {available_balance:.2f} | "
            f"Risk: {max_pct*100}% | Lev: {leverage}x | "
            f"Power: {buying_power:.2f} | Contracts: {contracts}"
        )
        return contracts
