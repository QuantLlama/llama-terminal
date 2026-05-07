from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from pathlib import Path
from typing import Optional

Base = declarative_base()


class Trade(Base):
    __tablename__ = 'trades'
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String)
    direction = Column(String)
    entry_price = Column(Float)
    exit_price = Column(Float)
    contracts = Column(Integer)
    pnl = Column(Float)
    entry_time = Column(DateTime)
    exit_time = Column(DateTime)
    strategy_params = Column(String)


class Tick(Base):
    __tablename__ = 'ticks'
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String)
    timestamp = Column(DateTime)
    bid = Column(Float)
    ask = Column(Float)
    last = Column(Float)
    volume = Column(Integer)


class DBManager:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            base_dir = Path(__file__).resolve().parent.parent
            db_path = str(base_dir / 'data' / 'trading.db')
        
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f'sqlite:///{db_path}')
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
    
    def save_trade(self, trade_data: dict):
        session = self.Session()
        trade = Trade(**trade_data)
        session.add(trade)
        session.commit()
        session.close()
    
    def save_tick(self, tick_data: dict):
        session = self.Session()
        tick = Tick(**tick_data)
        session.add(tick)
        session.commit()
        session.close()
    
    def get_trades(self, symbol: Optional[str] = None) -> list:
        session = self.Session()
        query = session.query(Trade)
        if symbol:
            query = query.filter(Trade.symbol == symbol)
        trades = query.all()
        session.close()
        return trades
