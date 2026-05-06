import threading
import time
from collections import deque
from typing import Optional, List, Dict, Callable, Any
from dataclasses import dataclass
import json
import logging
from .models import MarketDataEvent, OrderBookSnapshot, TradeEvent
logger = logging.getLogger(__name__)
class CircularBuffer:
    def __init__(self, max_size: int = 10000):
        self._buffer: deque = deque(maxlen=max_size)
        self._lock = threading.RLock()
        self._subscribers: List[Callable[[MarketDataEvent], None]] = []
        self._sequence_num: int = 0
        self._total_events: int = 0
        self._dropped_events: int = 0
        self._last_event_time: float = 0.0
    def push(self, event: MarketDataEvent) -> None:
        with self._lock:
            self._sequence_num += 1
            event.sequence_num = self._sequence_num
            if event.timestamp > 0:
                event.latency_ms = (time.time() - event.timestamp) * 1000
            self._buffer.append(event)
            self._total_events += 1
            self._last_event_time = time.time()
        self._notify_subscribers(event)
    def push_batch(self, events: List[MarketDataEvent]) -> None:
        with self._lock:
            for event in events:
                self._sequence_num += 1
                event.sequence_num = self._sequence_num
                if event.timestamp > 0:
                    event.latency_ms = (time.time() - event.timestamp) * 1000
                self._buffer.append(event)
                self._total_events += 1
            self._last_event_time = time.time()
        for event in events:
            self._notify_subscribers(event)
    def get_latest(self, n: int = 1) -> List[MarketDataEvent]:
        with self._lock:
            if n >= len(self._buffer):
                return list(self._buffer)
            return list(self._buffer)[-n:]
    def get_by_symbol(self, symbol: str, n: int = 100) -> List[MarketDataEvent]:
        with self._lock:
            filtered = [e for e in self._buffer if e.symbol == symbol]
            return filtered[-n:] if len(filtered) > n else filtered
    def get_latest_by_symbol(self, symbol: str) -> Optional[MarketDataEvent]:
        events = self.get_by_symbol(symbol, 1)
        return events[0] if events else None
    def subscribe(self, callback: Callable[[MarketDataEvent], None]) -> None:
        with self._lock:
            if callback not in self._subscribers:
                self._subscribers.append(callback)
    def unsubscribe(self, callback: Callable[[MarketDataEvent], None]) -> None:
        with self._lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)
    def _notify_subscribers(self, event: MarketDataEvent) -> None:
        subscribers_copy = []
        with self._lock:
            subscribers_copy = self._subscribers.copy()
        for callback in subscribers_copy:
            try:
                callback(event)
            except Exception as e:
                logger.error(f"Error notificando suscriptor: {e}")
    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()
    @property
    def size(self) -> int:
        with self._lock:
            return len(self._buffer)
    @property
    def total_events(self) -> int:
        return self._total_events
    @property
    def dropped_events(self) -> int:
        return self._dropped_events
    @property
    def last_event_time(self) -> float:
        return self._last_event_time
    def get_metrics(self) -> Dict[str, Any]:
        with self._lock:
            avg_latency = 0.0
            if self._buffer:
                latencies = [e.latency_ms for e in self._buffer if e.latency_ms > 0]
                if latencies:
                    avg_latency = sum(latencies) / len(latencies)
            return {
                "size": len(self._buffer),
                "max_size": self._buffer.maxlen,
                "total_events": self._total_events,
                "dropped_events": self._dropped_events,
                "subscribers_count": len(self._subscribers),
                "avg_latency_ms": round(avg_latency, 2),
                "last_event_time": self._last_event_time
            }
class SymbolBuffer:
    def __init__(self, history_size: int = 1000):
        self._latest: Dict[str, MarketDataEvent] = {}
        self._history: Dict[str, deque] = {}
        self._history_size = history_size
        self._lock = threading.RLock()
        self._books: Dict[str, OrderBookSnapshot] = {}
    def update(self, event: MarketDataEvent) -> None:
        with self._lock:
            self._latest[event.symbol] = event
            if event.symbol not in self._history:
                self._history[event.symbol] = deque(maxlen=self._history_size)
            self._history[event.symbol].append(event)
    def update_book(self, book: OrderBookSnapshot) -> None:
        with self._lock:
            self._books[book.symbol] = book
    def get_latest(self, symbol: str) -> Optional[MarketDataEvent]:
        with self._lock:
            return self._latest.get(symbol)
    def get_book(self, symbol: str) -> Optional[OrderBookSnapshot]:
        with self._lock:
            return self._books.get(symbol)
    def get_history(self, symbol: str, n: int = 100) -> List[MarketDataEvent]:
        with self._lock:
            history = self._history.get(symbol, deque())
            if n >= len(history):
                return list(history)
            return list(history)[-n:]
    def get_all_symbols(self) -> List[str]:
        with self._lock:
            return list(self._latest.keys())
    def get_snapshot(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            result = {}
            for symbol, event in self._latest.items():
                result[symbol] = {
                    "event": event.to_dict(),
                    "book": self._books.get(symbol, OrderBookSnapshot(symbol)).to_dict()
                }
            return result
    def clear(self) -> None:
        with self._lock:
            self._latest.clear()
            self._history.clear()
            self._books.clear()
class TradeBuffer:
    def __init__(self, max_size: int = 5000):
        self._buffer: deque = deque(maxlen=max_size)
        self._by_symbol: Dict[str, deque] = {}
        self._lock = threading.RLock()
        self._symbol_max_size = 1000
    def push(self, trade: TradeEvent) -> None:
        with self._lock:
            self._buffer.append(trade)
            if trade.symbol not in self._by_symbol:
                self._by_symbol[trade.symbol] = deque(maxlen=self._symbol_max_size)
            self._by_symbol[trade.symbol].append(trade)
    def get_latest(self, n: int = 100) -> List[TradeEvent]:
        with self._lock:
            if n >= len(self._buffer):
                return list(self._buffer)
            return list(self._buffer)[-n:]
    def get_by_symbol(self, symbol: str, n: int = 100) -> List[TradeEvent]:
        with self._lock:
            trades = self._by_symbol.get(symbol, deque())
            if n >= len(trades):
                return list(trades)
            return list(trades)[-n:]
    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()
            self._by_symbol.clear()