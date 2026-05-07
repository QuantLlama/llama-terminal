import time
import threading
import logging
import random
import numpy as np
import os
import json
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
logger = logging.getLogger(__name__)
@dataclass
class Genome:
    params: Dict[str, Any]
    fitness: float = 0.0
    id: int = field(default_factory=lambda: random.randint(1000, 9999))
class EvolutionaryEngine(ABC):
    def __init__(self, engine_name: str, pop_size: int = 10):
        self._name = engine_name
        self._active = False
        self._market_data_engine = None
        self._symbols_config: Dict[str, Dict] = {} 
        self._pop_size = pop_size
        self._populations: Dict[str, List[Genome]] = {} 
        self._should_stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._update_callbacks: List[Callable[[str, Dict], None]] = []
        logger.info(f"{self._name} initialized")
    def set_market_data_engine(self, engine):
        self._market_data_engine = engine
    def set_active(self, active: bool):
        self._active = active
        if active and (not self._thread or not self._thread.is_alive()):
            self.start()
        elif not active:
            self.stop()
        logger.info(f"{self._name} status: {'ACTIVE' if active else 'INACTIVE'}")
    def start(self):
        self._should_stop.clear()
        self._thread = threading.Thread(target=self._evolution_loop, name=f"{self._name}_Evolution", daemon=True)
        self._thread.start()
        logger.info(f"{self._name} evolution loop started")
    def stop(self):
        self._should_stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info(f"{self._name} evolution loop stopped")
    def subscribe_to_updates(self, callback: Callable[[str, Dict], None]):
        if callback not in self._update_callbacks:
            self._update_callbacks.append(callback)
    def _evolution_loop(self):
        while not self._should_stop.is_set():
            if not self._active or not self._market_data_engine:
                time.sleep(1)
                continue
            symbols = self._market_data_engine.metrics.symbols_subscribed
            for symbol in symbols:
                self._process_symbol(symbol)
            time.sleep(5) 
    def _process_symbol(self, symbol: str):
        if symbol not in self._populations:
            self._init_population(symbol)
        pop = self._populations[symbol]
        data = self._get_evaluation_data(symbol)
        if not data:
            return
        self._evaluate_fitness(symbol, pop, data)
        pop.sort(key=lambda g: g.fitness, reverse=True)
        best = pop[0]
        self._notify_best(symbol, best)
        self._populations[symbol] = self._evolve(pop)
    @abstractmethod
    def _init_population(self, symbol: str):
        pass
    @abstractmethod
    def _get_evaluation_data(self, symbol: str) -> Optional[Any]:
        pass
    @abstractmethod
    def _evaluate_fitness(self, symbol: str, population: List[Genome], data: Any):
        pass
    @abstractmethod
    def _evolve(self, pop: List[Genome]) -> List[Genome]:
        pass
    def _notify_best(self, symbol: str, best: Genome):
        params = {
            **best.params,
            "fitness": round(best.fitness, 3),
            "mode": "intelligent",
            "llama_type": self._name.lower().replace("engine", "")
        }
        self._symbols_config[symbol] = params
        for cb in self._update_callbacks:
            try:
                cb(symbol, params)
            except:
                pass
    def get_params(self, symbol: str) -> Dict:
        return self._symbols_config.get(symbol, {})
class BigLlamaEngine(EvolutionaryEngine):
    _instance = None
    _lock = threading.Lock()
    def __new__(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(BigLlamaEngine, cls).__new__(cls)
                    cls._instance.__init_engine__()
        return cls._instance
    def __init__(self):
        pass
    def __init_engine__(self):
        super().__init__("BigLlamaEngine")
    def _init_population(self, symbol: str):
        pop = []
        for _ in range(self._pop_size):
            pop.append(Genome(params={
                "minVol": random.uniform(5, 500),
                "window": random.randint(200, 3000),
                "absorptionFactor": random.uniform(1.1, 5.0)
            }))
        self._populations[symbol] = pop
    def _get_evaluation_data(self, symbol: str) -> Optional[List[Dict]]:
        trades = self._market_data_engine.get_recent_trades(symbol, n=200)
        return trades if (trades and len(trades) >= 50) else None
    def _evaluate_fitness(self, symbol: str, population: List[Genome], trades: List[Dict]):
        if not trades or len(trades) < 20: 
            for g in population: g.fitness = 0.0
            return
            
        chrono_trades = list(reversed(trades))
        
        for genome in population:
            score = 0
            detected_absorptions = 0
            detected_momentum = 0
            
            min_vol = genome.params["minVol"]
            window_ms = genome.params["window"]
            abs_factor = genome.params["absorptionFactor"]
            
            window_start_idx = 0
            i = 0
            while i < len(chrono_trades) - 10:
                current_time = chrono_trades[i].get('timestamp', 0)
                
                while window_start_idx < i and (current_time - chrono_trades[window_start_idx].get('timestamp', 0)) > window_ms:
                    window_start_idx += 1
                
                window_trades = chrono_trades[window_start_idx:i+1]
                total_vol = sum(t.get('size', 0) for t in window_trades)
                
                if total_vol >= min_vol:
                    prices = [t.get('price', 0) for t in window_trades if t.get('price', 0) > 0]
                    if not prices:
                        i += 1
                        continue
                        
                    min_px = min(prices)
                    max_px = max(prices)
                    entry_price = prices[-1]
                    
                    buy_vol = sum(t.get('size', 0) for t in window_trades if str(t.get('side', '')).upper() == 'BUY')
                    sell_vol = total_vol - buy_vol
                    dominant_side = 'BUY' if buy_vol >= sell_vol else 'SELL'
                    
                    future_price = chrono_trades[i+10].get('price', entry_price)
                    move = (future_price - entry_price) if dominant_side == 'BUY' else (entry_price - future_price)
                    
                    max_distance = entry_price * (abs_factor / 10000.0)
                    is_absorption = (max_px - min_px) <= max_distance
                    
                    if is_absorption:
                        detected_absorptions += 1
                        if move < 0:
                            score += 2.0  
                        else:
                            score -= 1.0
                    else:
                        detected_momentum += 1
                        if move > 0:
                            score += 1.0
                        else:
                            score -= 0.5
                            
                    i += 10 
                else:
                    i += 1
            
            total_detected = detected_absorptions + detected_momentum
            if total_detected == 0:
                genome.fitness = 0.0
            else:
                genome.fitness = score / total_detected
    def _evolve(self, pop: List[Genome]) -> List[Genome]:
        new_pop = pop[:2] 
        while len(new_pop) < self._pop_size:
            p1, p2 = random.sample(pop[:5], 2)
            child = Genome(params={
                "minVol": (p1.params["minVol"] + p2.params["minVol"]) / 2,
                "window": int((p1.params["window"] + p2.params["window"]) / 2),
                "absorptionFactor": (p1.params["absorptionFactor"] + p2.params["absorptionFactor"]) / 2
            })
            if random.random() < 0.2: 
                child.params["minVol"] *= random.uniform(0.8, 1.2)
                child.params["window"] = int(child.params["window"] * random.uniform(0.9, 1.1))
                child.params["absorptionFactor"] *= random.uniform(0.9, 1.1)
            new_pop.append(child)
        return new_pop
class InbalanceLlamaEngine(EvolutionaryEngine):
    _instance = None
    _lock = threading.Lock()
    def __new__(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(InbalanceLlamaEngine, cls).__new__(cls)
                    cls._instance.__init_engine__()
        return cls._instance
    def __init__(self):
        pass
    def __init_engine__(self):
        super().__init__("InbalanceLlamaEngine")
    def _init_population(self, symbol: str):
        pop = []
        for _ in range(self._pop_size):
            pop.append(Genome(params={
                "delta_threshold": random.uniform(0.1, 0.5),
                "volume_multiplier": random.uniform(0.5, 1.5),
                "min_body_ratio": random.uniform(0.2, 0.6)
            }))
        self._populations[symbol] = pop
    def _get_evaluation_data(self, symbol: str) -> Optional[List[Dict]]:
        trades = self._market_data_engine.get_recent_trades(symbol, n=300)
        return trades if (trades and len(trades) >= 100) else None
    def _evaluate_fitness(self, symbol: str, population: List[Genome], trades: List[Dict]):
        """Evalúa fitness basado en delta imbalance (desequilibrio buy/sell).

        Lógica: cuando el delta (buy_vol - sell_vol) excede un umbral relativo
        al volumen total, indica presión institucional. Si el precio se mueve
        en la dirección del delta después, el genoma gana puntos.
        """
        if not trades or len(trades) < 50:
            for g in population: g.fitness = 0.0
            return

        chrono_trades = list(reversed(trades))

        for genome in population:
            score = 0
            signals_found = 0

            delta_thr = genome.params["delta_threshold"]
            vol_mult = genome.params["volume_multiplier"]
            body_ratio = genome.params["min_body_ratio"]

            # Ventana deslizante de 20 trades
            window_size = 20
            i = window_size
            while i < len(chrono_trades) - 10:
                window = chrono_trades[i - window_size:i]

                buy_vol = sum(t.get('size', 0) for t in window
                              if str(t.get('side', '')).upper() == 'BUY')
                sell_vol = sum(t.get('size', 0) for t in window
                               if str(t.get('side', '')).upper() != 'BUY')
                total_vol = buy_vol + sell_vol

                if total_vol <= 0:
                    i += 5
                    continue

                # Calcular delta normalizado
                delta = (buy_vol - sell_vol) / total_vol  # rango [-1, 1]
                avg_vol = total_vol / window_size

                # Filtro: volumen mínimo relativo
                if avg_vol < vol_mult:
                    i += 5
                    continue

                # Filtro: ratio de cuerpo (qué tan unidireccional es el flujo)
                dominant_ratio = max(buy_vol, sell_vol) / total_vol
                if dominant_ratio < body_ratio:
                    i += 5
                    continue

                # ¿Hay imbalance suficiente?
                if abs(delta) >= delta_thr:
                    signals_found += 1
                    entry_price = chrono_trades[i].get('price', 0)
                    future_price = chrono_trades[i + 10].get('price', entry_price)

                    if delta > 0:  # Presión compradora → esperamos subida
                        move = future_price - entry_price
                    else:  # Presión vendedora → esperamos bajada
                        move = entry_price - future_price

                    if move > 0:
                        score += 1.5
                    elif move < 0:
                        score -= 1.0

                    i += 10  # Saltar zona evaluada
                else:
                    i += 5

            genome.fitness = (score / signals_found) if signals_found > 0 else 0.0

    def _evolve(self, pop: List[Genome]) -> List[Genome]:
        new_pop = pop[:2]
        while len(new_pop) < self._pop_size:
            p1, p2 = random.sample(pop[:5], 2)
            child = Genome(params={
                "delta_threshold": (p1.params["delta_threshold"] + p2.params["delta_threshold"]) / 2,
                "volume_multiplier": (p1.params["volume_multiplier"] + p2.params["volume_multiplier"]) / 2,
                "min_body_ratio": (p1.params["min_body_ratio"] + p2.params["min_body_ratio"]) / 2
            })
            if random.random() < 0.2:
                child.params["delta_threshold"] *= random.uniform(0.8, 1.2)
                child.params["volume_multiplier"] *= random.uniform(0.8, 1.2)
                child.params["min_body_ratio"] = max(0.1, min(0.9,
                    child.params["min_body_ratio"] * random.uniform(0.9, 1.1)))
            new_pop.append(child)
        return new_pop

class CazaLlamaEngine(EvolutionaryEngine):
    """Motor evolutivo para detección de niveles swing (soporte/resistencia).

    Busca swing highs/lows en el flujo de trades y evalúa si el precio
    rebota desde esos niveles. Optimiza la distancia de activación y
    la ventana de detección de swings.
    """
    _instance = None
    _lock = threading.Lock()
    def __new__(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(CazaLlamaEngine, cls).__new__(cls)
                    cls._instance.__init_engine__()
        return cls._instance
    def __init__(self):
        pass
    def __init_engine__(self):
        super().__init__("CazaLlamaEngine")
    def _init_population(self, symbol: str):
        pop = []
        for _ in range(self._pop_size):
            pop.append(Genome(params={
                "swing_bars": random.randint(3, 10),
                "dist_ticks": random.randint(20, 100),
                "vida_max": random.randint(10, 50)
            }))
        self._populations[symbol] = pop
    def _get_evaluation_data(self, symbol: str) -> Optional[List[Dict]]:
        trades = self._market_data_engine.get_recent_trades(symbol, n=200)
        return trades if (trades and len(trades) >= 50) else None

    def _evaluate_fitness(self, symbol: str, population: List[Genome], trades: List[Dict]):
        """Evalúa fitness detectando swing levels y midiendo rebotes.

        Lógica: agrupa trades en 'barras' de N trades (swing_bars), detecta
        máximos/mínimos locales, y cuando el precio se acerca a un nivel
        previo (dentro de dist_ticks), evalúa si rebota o lo rompe.
        Un rebote exitoso suma puntos; un fallo resta.
        """
        if not trades or len(trades) < 50:
            for g in population: g.fitness = 0.0
            return

        chrono_trades = list(reversed(trades))
        prices = [t.get('price', 0) for t in chrono_trades if t.get('price', 0) > 0]

        if len(prices) < 50:
            for g in population: g.fitness = 0.0
            return

        for genome in population:
            score = 0
            tests = 0

            swing_n = genome.params["swing_bars"]
            dist = genome.params["dist_ticks"]
            vida = genome.params["vida_max"]

            # Construir barras sintéticas agrupando cada swing_n trades
            bars_high = []
            bars_low = []
            for b in range(0, len(prices) - swing_n, swing_n):
                chunk = prices[b:b + swing_n]
                bars_high.append(max(chunk))
                bars_low.append(min(chunk))

            if len(bars_high) < 5:
                genome.fitness = 0.0
                continue

            # Detectar swing highs/lows (punto más alto/bajo entre vecinos)
            swing_levels = []
            for b in range(1, len(bars_high) - 1):
                if bars_high[b] > bars_high[b-1] and bars_high[b] > bars_high[b+1]:
                    swing_levels.append(('R', bars_high[b], b))  # Resistencia
                if bars_low[b] < bars_low[b-1] and bars_low[b] < bars_low[b+1]:
                    swing_levels.append(('S', bars_low[b], b))   # Soporte

            if not swing_levels:
                genome.fitness = 0.0
                continue

            # Evaluar: ¿el precio futuro rebota desde estos niveles?
            for bar_idx in range(len(bars_high) - 2):
                current_price = (bars_high[bar_idx] + bars_low[bar_idx]) / 2
                future_price = (bars_high[bar_idx + 2] + bars_low[bar_idx + 2]) / 2

                for level_type, level_price, level_bar in swing_levels:
                    # ¿El nivel sigue vivo? (dentro de vida_max barras)
                    age = bar_idx - level_bar
                    if age < 1 or age > vida:
                        continue

                    # ¿El precio está cerca del nivel?
                    distance = abs(current_price - level_price)
                    if distance > dist:
                        continue

                    tests += 1

                    if level_type == 'S':  # Soporte → esperamos rebote arriba
                        if future_price > current_price:
                            score += 1.5
                        else:
                            score -= 0.8
                    else:  # Resistencia → esperamos rebote abajo
                        if future_price < current_price:
                            score += 1.5
                        else:
                            score -= 0.8

            genome.fitness = (score / tests) if tests > 0 else 0.0

    def _evolve(self, pop: List[Genome]) -> List[Genome]:
        new_pop = pop[:2]
        while len(new_pop) < self._pop_size:
            p1, p2 = random.sample(pop[:5], 2)
            child = Genome(params={
                "swing_bars": int((p1.params["swing_bars"] + p2.params["swing_bars"]) / 2),
                "dist_ticks": int((p1.params["dist_ticks"] + p2.params["dist_ticks"]) / 2),
                "vida_max": int((p1.params["vida_max"] + p2.params["vida_max"]) / 2)
            })
            if random.random() < 0.2:
                child.params["swing_bars"] = max(2, int(child.params["swing_bars"] * random.uniform(0.8, 1.2)))
                child.params["dist_ticks"] = max(5, int(child.params["dist_ticks"] * random.uniform(0.8, 1.2)))
                child.params["vida_max"] = max(3, int(child.params["vida_max"] * random.uniform(0.8, 1.2)))
            new_pop.append(child)
        return new_pop
def get_big_llama() -> BigLlamaEngine:
    return BigLlamaEngine()
def get_inbalance_llama() -> InbalanceLlamaEngine:
    return InbalanceLlamaEngine()
def get_caza_llama() -> CazaLlamaEngine:
    return CazaLlamaEngine()