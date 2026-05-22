import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import json
import uuid
class OrderSource(str, Enum):
    MANUAL = "MANUAL"  
    ALGO = "ALGO"      
class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
class OrderType(str, Enum):
    MARKET = "MKT"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"
class OrderStatus(str, Enum):
    PENDING_VALIDATION = "PENDING_VALIDATION"  
    VALIDATED = "VALIDATED"                     
    REJECTED = "REJECTED"                       
    SENT = "SENT"                               
    FILLED = "FILLED"                           
    PARTIAL = "PARTIAL"                         
    CANCELLED = "CANCELLED"                     
    FAILED = "FAILED"                           
class RejectionReason(str, Enum):
    RISK_MAX_POSITION_SIZE = "MAX_POSITION_SIZE_EXCEEDED"
    RISK_MAX_DAILY_LOSS = "MAX_DAILY_LOSS_EXCEEDED"
    RISK_MAX_ORDERS = "MAX_ORDERS_EXCEEDED"
    RISK_PRICE_DEVIATION = "PRICE_DEVIATION_TOO_HIGH"
    RISK_INSUFFICIENT_MARGIN = "INSUFFICIENT_MARGIN"
    RISK_SYMBOL_NOT_ALLOWED = "SYMBOL_NOT_ALLOWED"
    RISK_OUTSIDE_TRADING_HOURS = "OUTSIDE_TRADING_HOURS"
    VALIDATION_INVALID_PRICE = "INVALID_PRICE"
    VALIDATION_INVALID_SIZE = "INVALID_SIZE"
    VALIDATION_INVALID_SYMBOL = "INVALID_SYMBOL"
    FEED_OFFLINE = "MARKET_DATA_FEED_OFFLINE"
    CONNECTOR_ERROR = "BROKER_CONNECTOR_ERROR"
    UNKNOWN = "UNKNOWN_ERROR"
class MarketSession(str, Enum):
    PRE_MARKET = "PRE_MARKET"           
    REGULAR = "REGULAR"                 
    AFTER_HOURS = "AFTER_HOURS"         
    ASIAN = "ASIAN"                     
    LONDON = "LONDON"                   
    NEW_YORK = "NEW_YORK"               
    CLOSED = "CLOSED"                   
@dataclass
class OrderRequest:
    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType = OrderType.MARKET
    price: float = 0.0           
    stop_price: float = 0.0      
    sl: float = 0.0              
    tp: float = 0.0              
    source: OrderSource = OrderSource.MANUAL  
    platform: str = "mt5"        
    account_id: Optional[str] = None 
    client_order_id: str = ""    
    comment: str = ""            
    timestamp: float = field(default_factory=time.time)
    def __post_init__(self):
        if not self.client_order_id:
            self.client_order_id = f"{self.source.value}_{uuid.uuid4().hex[:8]}"
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side.value if isinstance(self.side, OrderSide) else self.side,
            "quantity": self.quantity,
            "order_type": self.order_type.value if isinstance(self.order_type, OrderType) else self.order_type,
            "price": self.price,
            "stop_price": self.stop_price,
            "sl": self.sl,
            "tp": self.tp,
            "source": self.source.value if isinstance(self.source, OrderSource) else self.source,
            "platform": self.platform,
            "account_id": self.account_id,
            "client_order_id": self.client_order_id,
            "comment": self.comment,
            "timestamp": self.timestamp
        }
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'OrderRequest':
        data = data.copy()
        if 'side' in data and isinstance(data['side'], str):
            data['side'] = OrderSide(data['side'])
        if 'order_type' in data and isinstance(data['order_type'], str):
            data['order_type'] = OrderType(data['order_type'])
        if 'source' in data and isinstance(data['source'], str):
            data['source'] = OrderSource(data['source'])
        return cls(**data)
@dataclass
class OrderResponse:
    success: bool
    order_id: str = ""
    client_order_id: str = ""
    symbol: str = ""
    side: str = ""
    quantity: float = 0.0
    filled_qty: float = 0.0
    avg_price: float = 0.0
    status: OrderStatus = OrderStatus.PENDING_VALIDATION
    source: OrderSource = OrderSource.MANUAL
    rejection_reason: Optional[RejectionReason] = None
    error_message: str = ""
    timestamp: float = field(default_factory=time.time)
    validation_latency_ms: float = 0.0
    execution_latency_ms: float = 0.0
    total_latency_ms: float = 0.0
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "order_id": self.order_id,
            "client_order_id": self.client_order_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "filled_qty": self.filled_qty,
            "avg_price": self.avg_price,
            "status": self.status.value if isinstance(self.status, OrderStatus) else self.status,
            "source": self.source.value if isinstance(self.source, OrderSource) else self.source,
            "rejection_reason": self.rejection_reason.value if self.rejection_reason else None,
            "error_message": self.error_message,
            "timestamp": self.timestamp,
            "validation_latency_ms": round(self.validation_latency_ms, 2),
            "execution_latency_ms": round(self.execution_latency_ms, 2),
            "total_latency_ms": round(self.total_latency_ms, 2)
        }
    def to_json(self) -> str:
        return json.dumps(self.to_dict())
@dataclass
class ValidationResult:
    is_valid: bool
    rejection_reason: Optional[RejectionReason] = None
    message: str = ""
    warnings: List[str] = field(default_factory=list)
    adjusted_quantity: Optional[float] = None  
    adjusted_price: Optional[float] = None     
    current_session: Optional[str] = None      
    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "rejection_reason": self.rejection_reason.value if self.rejection_reason else None,
            "message": self.message,
            "warnings": self.warnings,
            "adjusted_quantity": self.adjusted_quantity,
            "adjusted_price": self.adjusted_price,
            "current_session": self.current_session
        }
@dataclass
class RiskLimits:
    max_position_size: float = 10.0          
    max_daily_loss: float = 500.0            
    max_orders_per_day: int = 50             
    max_orders_per_minute: int = 10          
    max_price_deviation_pct: float = 1.0     
    allowed_symbols: List[str] = field(default_factory=list)  
    trading_start_hour: str = "00:00"        
    trading_end_hour: str = "23:59"          
    min_order_size: float = 0.00001             
    algo_max_position_size: float = 5.0      
    algo_max_orders_per_day: int = 20        
    manual_require_confirmation: bool = False 
    allow_extended_hours: bool = True        
    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_position_size": self.max_position_size,
            "max_daily_loss": self.max_daily_loss,
            "max_orders_per_day": self.max_orders_per_day,
            "max_orders_per_minute": self.max_orders_per_minute,
            "max_price_deviation_pct": self.max_price_deviation_pct,
            "allowed_symbols": self.allowed_symbols,
            "trading_start_hour": self.trading_start_hour,
            "trading_end_hour": self.trading_end_hour,
            "min_order_size": self.min_order_size,
            "algo_max_position_size": self.algo_max_position_size,
            "algo_max_orders_per_day": self.algo_max_orders_per_day,
            "manual_require_confirmation": self.manual_require_confirmation,
            "allow_extended_hours": self.allow_extended_hours
        }
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RiskLimits':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
@dataclass
class GatewayMetrics:
    total_orders_received: int = 0
    orders_validated: int = 0
    orders_rejected: int = 0
    orders_executed: int = 0
    orders_failed: int = 0
    manual_orders: int = 0
    algo_orders: int = 0
    avg_validation_latency_ms: float = 0.0
    avg_execution_latency_ms: float = 0.0
    avg_total_latency_ms: float = 0.0
    orders_per_second: float = 0.0
    last_order_time: float = 0.0
    daily_pnl: float = 0.0
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_orders_received": self.total_orders_received,
            "orders_validated": self.orders_validated,
            "orders_rejected": self.orders_rejected,
            "orders_executed": self.orders_executed,
            "orders_failed": self.orders_failed,
            "manual_orders": self.manual_orders,
            "algo_orders": self.algo_orders,
            "avg_validation_latency_ms": round(self.avg_validation_latency_ms, 2),
            "avg_execution_latency_ms": round(self.avg_execution_latency_ms, 2),
            "avg_total_latency_ms": round(self.avg_total_latency_ms, 2),
            "orders_per_second": round(self.orders_per_second, 2),
            "last_order_time": self.last_order_time,
            "daily_pnl": round(self.daily_pnl, 2)
        }