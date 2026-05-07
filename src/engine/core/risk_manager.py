from ..utils.logger import setup_logger
from ..utils import calculate_contracts, calculate_position_risk, CONFIG
from typing import Dict, List

logger = setup_logger('RiskManager')


class RiskManager:
    def __init__(self, account_balance: float):
        self.account_balance = account_balance
        self.daily_pnl = 0
        self.daily_trades = 0
        self.consecutive_losses = 0
        self.max_consecutive_losses = 3
        
    def check_daily_limits(self) -> bool:
        """Verifica límites diarios."""
        max_drawdown_pct = CONFIG['RISK']['MAX_DAILY_DRAWDOWN_PCT']
        max_daily_drawdown = self.account_balance * max_drawdown_pct
        
        if abs(self.daily_pnl) > max_daily_drawdown:
            logger.warning(f"Límite de drawdown diario alcanzado: ${self.daily_pnl:.2f}")
            return False
        
        return True
    
    def check_trade_risk(self, entry_price: float, stop_loss: float) -> bool:
        """Verifica que el riesgo por trade esté dentro de límites."""
        max_risk_pct = CONFIG['RISK']['MAX_TRADE_RISK_PCT']
        max_risk = self.account_balance * max_risk_pct
        
        risk_per_contract = calculate_position_risk(entry_price, stop_loss, 1)
        
        if risk_per_contract > max_risk:
            logger.warning(f"Riesgo por contrato muy alto: ${risk_per_contract:.2f}")
            return False
        
        return True
    
    def calculate_position_size(self, entry_price: float, stop_loss: float) -> int:
        """Calcula tamaño de posición basado en riesgo."""
        risk_pct = CONFIG['RISK']['MAX_TRADE_RISK_PCT']
        contracts = calculate_contracts(
            self.account_balance, risk_pct, entry_price, stop_loss
        )
        
        max_concurrent = CONFIG['RISK']['MAX_CONCURRENT_TRADES']
        contracts = min(contracts, max_concurrent)
        
        logger.info(f"Posición calculada: {contracts} contratos")
        return contracts
    
    def update_pnl(self, pnl: float):
        """Actualiza PnL diario."""
        self.daily_pnl += pnl
        
        if pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
        
        logger.info(f"PnL diario actualizado: ${self.daily_pnl:.2f}")
    
    def should_stop_trading(self) -> bool:
        """Determina si se debe detener el trading."""
        if not self.check_daily_limits():
            return True
        
        if self.consecutive_losses >= self.max_consecutive_losses:
            logger.warning(f"Máximo de pérdidas consecutivas alcanzado: {self.consecutive_losses}")
            return True
        
        return False
    
    def update_balance(self, new_balance: float):
        """Actualiza balance de cuenta."""
        self.account_balance = new_balance
        logger.info(f"Balance actualizado: ${self.account_balance:.2f}")
