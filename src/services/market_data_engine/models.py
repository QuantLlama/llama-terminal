import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
import json
class FeedStatus(str, Enum):
    ONLINE = "ONLINE"       
    DEGRADED = "DEGRADED"   
    OFFLINE = "OFFLINE"     
    CONNECTING = "CONNECTING"  
    RECONNECTING = "RECONNECTING"  
class OrderSource(str, Enum):
    MANUAL = "MANUAL"  
    ALGO = "ALGO"      
class OrderType(str, Enum):
    MARKET = "MKT"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"
class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
@dataclass
class MarketDataEvent:
    symbol: str
    timestamp: float = field(default_factory=time.time)  
    event_type: str = "QUOTE"  
    bid: float = 0.0
    ask: float = 0.0
    last: float = 0.0
    bid_size: float = 0.0
    ask_size: float = 0.0
    last_size: float = 0.0
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: float = 0.0
    delta: float = 0.0  
    bids: List[Dict[str, Any]] = field(default_factory=list)
    asks: List[Dict[str, Any]] = field(default_factory=list)
    midpoint: float = 0.0
    spread: float = 0.0
    sequence_num: int = 0
    latency_ms: float = 0.0
    source: str = ""  
    side: str = ""    
    flags: int = 0    
    def to_dict(self) -> Dict[str, Any]:
        d = {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "bid": self.bid,
            "ask": self.ask,
            "last": self.last,
            "bid_size": self.bid_size,
            "ask_size": self.ask_size,
            "last_size": self.last_size,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "delta": self.delta,
            "sequence_num": self.sequence_num,
            "latency_ms": self.latency_ms,
            "source": self.source,
            "side": self.side,
            "flags": self.flags
        }
        if self.event_type in ("BOOK", "BOOK_UPDATE") or self.bids or self.asks:
            d["bids"] = self.bids
            d["asks"] = self.asks
            d["midpoint"] = self.midpoint
            d["spread"] = self.spread
            
        return d
    def to_json(self) -> str:
        return json.dumps(self.to_dict())
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MarketDataEvent':
        return cls(**data)
@dataclass
class BookLevel:
    price: float
    size: float
    count: int = 1  
@dataclass
class OrderBookSnapshot:
    symbol: str
    timestamp: float = field(default_factory=time.time)
    bids: List[BookLevel] = field(default_factory=list)  
    asks: List[BookLevel] = field(default_factory=list)  
    def best_bid(self) -> Optional[BookLevel]:
        return self.bids[0] if self.bids else None
    def best_ask(self) -> Optional[BookLevel]:
        return self.asks[0] if self.asks else None
    def spread(self) -> float:
        bb = self.best_bid()
        ba = self.best_ask()
        if bb and ba:
            return ba.price - bb.price
        return 0.0
    def to_dict(self) -> Dict[str, Any]:
        bb = self.best_bid()
        ba = self.best_ask()
        spread = ba.price - bb.price if bb and ba else 0.0
        midpoint = (ba.price + bb.price) / 2 if bb and ba else 0.0
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "spread": spread,
            "midpoint": midpoint,
            "bids": [{"price": b.price, "size": b.size, "count": b.count} for b in self.bids],
            "asks": [{"price": a.price, "size": a.size, "count": a.count} for a in self.asks]
        }
@dataclass
class TradeEvent:
    symbol: str
    timestamp: float = field(default_factory=time.time)
    price: float = 0.0
    size: float = 0.0
    side: str = ""  
    trade_id: str = ""
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "price": self.price,
            "size": self.size,
            "side": self.side,
            "trade_id": self.trade_id
        }
@dataclass
class OrderRequest:
    symbol: str
    side: Side
    quantity: float
    order_type: OrderType = OrderType.MARKET
    price: float = 0.0  
    stop_price: float = 0.0  
    sl: float = 0.0
    tp: float = 0.0
    source: OrderSource = OrderSource.MANUAL
    client_order_id: str = ""
    comment: str = ""
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity": self.quantity,
            "order_type": self.order_type.value,
            "price": self.price,
            "stop_price": self.stop_price,
            "sl": self.sl,
            "tp": self.tp,
            "source": self.source.value,
            "client_order_id": self.client_order_id,
            "comment": self.comment
        }
@dataclass  
class OrderResponse:
    success: bool
    order_id: str = ""
    client_order_id: str = ""
    symbol: str = ""
    filled_qty: float = 0.0
    avg_price: float = 0.0
    status: str = ""  
    error_code: str = ""
    error_message: str = ""
    timestamp: float = field(default_factory=time.time)
    latency_ms: float = 0.0
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "order_id": self.order_id,
            "client_order_id": self.client_order_id,
            "symbol": self.symbol,
            "filled_qty": self.filled_qty,
            "avg_price": self.avg_price,
            "status": self.status,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "timestamp": self.timestamp,
            "latency_ms": self.latency_ms
        }
@dataclass
class FeedMetrics:
    status: FeedStatus = FeedStatus.OFFLINE
    connected_since: float = 0.0
    last_message_time: float = 0.0
    messages_received: int = 0
    avg_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    min_latency_ms: float = float('inf')
    reconnect_count: int = 0
    errors_count: int = 0
    symbols_subscribed: List[str] = field(default_factory=list)
    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "connected_since": self.connected_since,
            "last_message_time": self.last_message_time,
            "messages_received": self.messages_received,
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "max_latency_ms": round(self.max_latency_ms, 2),
            "min_latency_ms": round(self.min_latency_ms, 2) if self.min_latency_ms != float('inf') else 0.0,
            "reconnect_count": self.reconnect_count,
            "errors_count": self.errors_count,
            "symbols_subscribed": self.symbols_subscribed
        }