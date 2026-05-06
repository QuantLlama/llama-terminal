from deap import base, creator, tools, algorithms
from ..backtesting.backtester import Backtester
from ..utils.logger import setup_logger
import random
import numpy as np
from typing import Dict, List, Tuple
import json

logger = setup_logger('GeneticOptimizer')


class GeneticOptimizer:
    def __init__(self, backtester: Backtester, param_ranges: Dict = None):
        self.backtester = backtester
        self.param_ranges = param_ranges or self.get_default_param_ranges()
        self.setup_genetic_algorithm()
        
    def setup_genetic_algorithm(self):
        """Configura algoritmo genético con DEAP."""
        if not hasattr(creator, "FitnessMax"):
            creator.create("FitnessMax", base.Fitness, weights=(1.0,))
        if not hasattr(creator, "Individual"):
            creator.create("Individual", list, fitness=creator.FitnessMax)
        
        self.toolbox = base.Toolbox()
        self.toolbox.register("attr_float", random.uniform)
        self.toolbox.register("attr_int", random.randint)
        
        self.toolbox.register("individual", self.create_individual)
        self.toolbox.register("population", tools.initRepeat, list, self.toolbox.individual)
        
        self.toolbox.register("evaluate", self.evaluate_individual)
        self.toolbox.register("mate", tools.cxTwoPoint)
        self.toolbox.register("mutate", self.mutate_individual)
        self.toolbox.register("select", tools.selTournament, tournsize=3)
    
    def create_individual(self) -> list:
        """Crea individuo aleatorio."""
        individual = []
        
        for param, range_values in self.param_ranges.items():
            if isinstance(range_values, dict):
                if range_values['type'] == 'float':
                    value = random.uniform(range_values['min'], range_values['max'])
                elif range_values['type'] == 'int':
                    value = random.randint(range_values['min'], range_values['max'])
                elif range_values['type'] == 'choice':
                    value = random.choice(range_values['options'])
                else:
                    value = random.uniform(range_values['min'], range_values['max'])
            else:
                value = random.uniform(range_values[0], range_values[1])
            
            individual.append(value)
        
        return creator.Individual(individual)
    
    def mutate_individual(self, individual: list, indpb: float = 0.1):
        """Muta individuo."""
        for i in range(len(individual)):
            if random.random() < indpb:
                param_name = list(self.param_ranges.keys())[i]
                range_values = self.param_ranges[param_name]
                
                if isinstance(range_values, dict):
                    if range_values['type'] == 'float':
                        mutation = random.uniform(-0.1, 0.1) * individual[i]
                        individual[i] = max(range_values['min'], min(range_values['max'], individual[i] + mutation))
                    elif range_values['type'] == 'int':
                        mutation = random.randint(-2, 2)
                        individual[i] = max(range_values['min'], min(range_values['max'], int(individual[i]) + mutation))
                    elif range_values['type'] == 'choice':
                        individual[i] = random.choice(range_values['options'])
        
        return individual,
    
    def individual_to_params(self, individual: list) -> Dict:
        """Convierte individuo a diccionario de parámetros."""
        params = {}
        param_names = list(self.param_ranges.keys())
        
        for i, param_name in enumerate(param_names):
            params[param_name] = individual[i]
        
        return params
    
    def evaluate_individual(self, individual: list) -> Tuple[float]:
        """Evalúa fitness del individuo con datos reales de MT5."""
        params = self.individual_to_params(individual)
        
        try:
            results = self.backtester.run(params)
            
            if results.get('total_trades', 0) == 0:
                logger.debug(f"No trades generated | Params: {params}")
                return (0.0,)
            
            total_pnl = results.get('total_pnl', 0)
            sharpe = results.get('sharpe_ratio', 0)
            profit_factor = results.get('profit_factor', 0)
            win_rate = results.get('win_rate', 0)
            max_drawdown = results.get('max_drawdown', 0)
            total_trades = results.get('total_trades', 0)
            
            trade_bonus = min(total_trades / 100.0, 2.0)
            
            drawdown_penalty = 0
            if max_drawdown > 0.15:
                drawdown_penalty = (max_drawdown - 0.15) * 5
            
            pf_penalty = 0
            if profit_factor < 1.2 and profit_factor > 0:
                pf_penalty = (1.2 - profit_factor) * 2
            
            fitness = (
                (total_pnl / 100.0) * 0.40 +
                sharpe * 0.30 +
                min(profit_factor, 3.0) * 0.20 +
                trade_bonus * 0.10
            )
            
            fitness -= (drawdown_penalty + pf_penalty)
            
            logger.info(f"Fitness: {fitness:.4f} | PnL: {total_pnl:.2f} | Trades: {total_trades} | WinRate: {win_rate:.1%}")
            
            return (fitness,)
            
        except Exception as e:
            logger.error(f"Error evaluando individuo: {e}")
            import traceback
            traceback.print_exc()
            return (-10.0,)
    
    def optimize(self, population_size: int = 50, generations: int = 30, 
                 cx_prob: float = 0.8, mut_prob: float = 0.07) -> Dict:
        """Ejecuta optimización genética."""
        logger.info(f"Iniciando optimización genética - Población: {population_size}, Generaciones: {generations}")
        
        population = self.toolbox.population(n=population_size)
        
        fitnesses = list(map(self.toolbox.evaluate, population))
        for ind, fit in zip(population, fitnesses):
            ind.fitness.values = fit
        
        stats = tools.Statistics(lambda ind: ind.fitness.values)
        stats.register("avg", np.mean)
        stats.register("min", np.min)
        stats.register("max", np.max)
        
        algorithms.eaSimple(
            population, self.toolbox, cxpb=cx_prob, 
            mutpb=mut_prob, ngen=generations, 
            stats=stats, verbose=True
        )
        
        best_individual = tools.selBest(population, k=1)[0]
        best_params = self.individual_to_params(best_individual)
        best_fitness = best_individual.fitness.values[0] if best_individual.fitness.valid else -1.0
        
        logger.info(f"Mejor fitness: {best_fitness:.4f}")
        logger.info(f"Mejores parámetros: {json.dumps(best_params, indent=2)}")
        
        return {
            'best_params': best_params,
            'best_fitness': best_fitness,
            'final_population': population
        }
    
    def get_default_param_ranges(self) -> Dict:
        """Rangos de parámetros optimizados para datos reales de MT5."""
        return {
            'delta_threshold': {'type': 'int', 'min': 30, 'max': 150},
            'lookback_period': {'type': 'int', 'min': 3, 'max': 15},
            'imbalance_threshold': {'type': 'float', 'min': 0.6, 'max': 0.9},
            'stop_loss_ticks': {'type': 'int', 'min': 6, 'max': 16},
            'take_profit_ticks': {'type': 'int', 'min': 10, 'max': 30},
            'rr_ratio': {'type': 'float', 'min': 1.0, 'max': 3.0},
            'min_volume': {'type': 'int', 'min': 200, 'max': 800},
            'atr_multiplier': {'type': 'float', 'min': 1.0, 'max': 3.0},
            'timeframe': {'type': 'choice', 'options': ['1T', '5T', '15T']}
        }
