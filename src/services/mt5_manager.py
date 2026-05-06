import os
import json
import hashlib
import subprocess
from typing import Dict, List, Optional
from datetime import datetime
from cryptography.fernet import Fernet
import logging
logger = logging.getLogger(__name__)
from .security import CredentialManager
from src.utils.paths import get_data_path

class MT5AccountManager:
    def __init__(self, accounts_file: str = "src/config/mt5_accounts.json"):
        self.accounts_file = get_data_path(accounts_file)
        self.credential_manager = CredentialManager()
        self.accounts = self._load_accounts()
        self.instances_dir = get_data_path("mt5_instances")
        os.makedirs(self.instances_dir, exist_ok=True)
        self.brokers_file = get_data_path("src/config/brokers.json")
        self.brokers = self._load_brokers()
        self.scanned_servers = self._scan_local_servers()
        self._merge_scanned_servers()
    def _scan_local_servers(self) -> List[Dict]:
        found_servers = []
        try:
            base_paths = []
            appdata = os.getenv('APPDATA')
            if appdata:
                terminal_path = os.path.join(appdata, "MetaQuotes", "Terminal")
                if os.path.exists(terminal_path):
                    for item in os.listdir(terminal_path):
                        bases_dir = os.path.join(terminal_path, item, "bases")
                        if os.path.isdir(bases_dir):
                            base_paths.append(bases_dir)
            for bases_dir in base_paths:
                if os.path.exists(bases_dir):
                    for folder in os.listdir(bases_dir):
                        folder_path = os.path.join(bases_dir, folder)
                        if os.path.isdir(folder_path):
                            server_name = folder
                            parts = server_name.split('-')
                            raw_broker = parts[0]
                            broker_name = raw_broker
                            found_servers.append({
                                "broker": broker_name, 
                                "server": server_name,
                                "source": "local_scan"
                            })
        except Exception as e:
            logger.error(f"Error scanning local servers: {e}")
        return found_servers
    def _merge_scanned_servers(self):
        broker_map = {b["name"]: b for b in self.brokers}
        for s in self.scanned_servers:
            b_name = s["broker"]
            s_name = s["server"]
            if b_name not in broker_map:
                new_broker = {"name": b_name, "servers": [s_name]}
                self.brokers.append(new_broker)
                broker_map[b_name] = new_broker
            else:
                if s_name not in broker_map[b_name]["servers"]:
                    broker_map[b_name]["servers"].append(s_name)
        self.brokers.sort(key=lambda x: x["name"])
    def _load_brokers(self) -> List[Dict]:
        from src.utils.paths import sync_config
        # Sync the internal brokers.json to the external one if needed
        sync_config(os.path.join("src", "config", "brokers.json"))
        data = self._load_from_path(self.brokers_file)
        
        # Handle the {"brokers": [...]} wrapper
        if isinstance(data, dict) and "brokers" in data:
            brokers = data["brokers"]
        elif isinstance(data, list):
            brokers = data
        else:
            brokers = []
            
        logger.info(f"[MT5Manager] Loaded {len(brokers)} brokers from {self.brokers_file}")
        return brokers

    def _load_from_path(self, path: str) -> List[Dict]:
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading brokers from {path}: {e}")
        return []
    def get_broker_names(self) -> List[str]:
        return sorted([b["name"] for b in self.brokers])
    def search_servers(self, query: str) -> List[Dict]:
        clean_query = query.lower().replace(" ", "")
        results = []
        for broker in self.brokers:
            b_name = broker["name"]
            clean_b_name = b_name.lower().replace(" ", "")
            if clean_query in clean_b_name:
                for server in broker["servers"]:
                    results.append({"broker": b_name, "server": server})
            else:
                for server in broker["servers"]:
                    clean_server = server.lower().replace(" ", "")
                    if clean_query in clean_server:
                        results.append({"broker": b_name, "server": server})
        seen = set()
        unique_results = []
        for r in results:
            if r["server"] not in seen:
                seen.add(r["server"])
                unique_results.append(r)
        return sorted(unique_results, key=lambda x: x["server"])
    def _load_accounts(self) -> Dict:
        if os.path.exists(self.accounts_file):
            try:
                with open(self.accounts_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading accounts: {e}")
                return {}
        return {}
    def _save_accounts(self):
        os.makedirs(os.path.dirname(self.accounts_file), exist_ok=True)
        with open(self.accounts_file, 'w') as f:
            json.dump(self.accounts, f, indent=4)
    def add_account(self, name: str, broker: str, server: str, login: str, 
                   password: str, account_type: str = "demo") -> Dict:
        account_id = hashlib.md5(f"{broker}_{login}".encode()).hexdigest()[:8]
        encrypted_password = self.credential_manager.encrypt(password)
        account_data = {
            "id": account_id,
            "name": name,
            "broker": broker,
            "server": server,
            "login": login,
            "password": encrypted_password,
            "account_type": account_type,
            "created_at": datetime.now().isoformat(),
            "status": "inactive",
            "is_master": False,
            "instance_path": None
        }
        self.accounts[account_id] = account_data
        self._save_accounts()
        logger.info(f"Account added: {name} ({broker} - {login})")
        return self._sanitize_account(account_data)
    def update_account(self, account_id: str, update_data: Dict) -> Optional[Dict]:
        if account_id not in self.accounts:
            return None
        account = self.accounts[account_id]
        if "name" in update_data:
            account["name"] = update_data["name"]
        if "account_type" in update_data:
            account["account_type"] = update_data["account_type"]
        if "password" in update_data and update_data["password"]:
            account["password"] = self.credential_manager.encrypt(update_data["password"])
            if self.accounts[account_id].get("status") == "active":
                try:
                    self.generate_config_ini(account_id)
                except:
                    pass
        self.accounts[account_id] = account
        self._save_accounts()
        logger.info(f"MT5 Account updated: {account_id}")
        return self._sanitize_account(account)
    def set_master_account(self, account_id: str) -> bool:
        if account_id not in self.accounts:
            return False
        changed = False
        for acc_id, acc in self.accounts.items():
            was_master = acc.get("is_master", False)
            should_be_master = (acc_id == account_id)
            if was_master != should_be_master:
                acc["is_master"] = should_be_master
                if not should_be_master:
                    acc["status"] = "inactive" 
                changed = True
        if changed:
            self._save_accounts()
            try:
                self.start_instance(account_id)
            except Exception as e:
                logger.error(f"Auto-connect to master failed: {e}")
        return True
    def remove_account(self, account_id: str) -> bool:
        if account_id in self.accounts:
            self.stop_instance(account_id)
            instance_path = self.accounts[account_id].get("instance_path")
            if instance_path and os.path.exists(instance_path):
                import shutil
                shutil.rmtree(instance_path, ignore_errors=True)
            del self.accounts[account_id]
            self._save_accounts()
            logger.info(f"Account removed: {account_id}")
            return True
        return False
    def get_accounts(self) -> List[Dict]:
        self.accounts = self._load_accounts()
        return [self._sanitize_account(acc) for acc in self.accounts.values()]
    def get_account(self, account_id: str) -> Optional[Dict]:
        if account_id in self.accounts:
            return self._sanitize_account(self.accounts[account_id])
        return None
    def _sanitize_account(self, account: Dict) -> Dict:
        sanitized = account.copy()
        if "password" in sanitized:
            sanitized["password"] = "***"
        if "is_master" not in sanitized:
            sanitized["is_master"] = False
        return sanitized
    def generate_config_ini(self, account_id: str) -> str:
        if account_id not in self.accounts:
            raise ValueError(f"Account {account_id} not found")
        account = self.accounts[account_id]
        password = self.credential_manager.decrypt(account["password"])
        instance_path = os.path.join(self.instances_dir, f"mt5_{account_id}")
        os.makedirs(instance_path, exist_ok=True)
        self.accounts[account_id]["instance_path"] = instance_path
        self._save_accounts()
        config_content = f"""[Common]
Login={account["login"]}
Password={password}
Server={account["server"]}
AutoConfiguration=1
DataPath={os.path.abspath(instance_path)}\\data
"""
        config_path = os.path.join(instance_path, "config.ini")
        with open(config_path, 'w') as f:
            f.write(config_content)
        logger.info(f"Config generated for {account_id}: {config_path}")
        return config_path
    def start_instance(self, account_id: str, mt5_exe_path: str = None) -> bool:
        if account_id not in self.accounts:
            logger.error(f"Account {account_id} not found")
            return False
        try:
            import MetaTrader5 as mt5
            if not mt5.initialize():
                logger.error("MT5 no está corriendo. El usuario debe abrir MT5 manualmente.")
                return False
            account_info = mt5.account_info()
            if account_info:
                logger.info(f"MT5 está corriendo con cuenta: {account_info.login}")
                if str(account_info.login) == self.accounts[account_id]["login"]:
                    logger.info(f"Ya conectado a la cuenta {account_id}")
                    self.accounts[account_id]["status"] = "active"
                    self._save_accounts()
                    return True
                else:
                    password = self.credential_manager.decrypt(
                        self.accounts[account_id]["password"]
                    )
                    authorized = mt5.login(
                        login=int(self.accounts[account_id]["login"]),
                        password=password,
                        server=self.accounts[account_id]["server"]
                    )
                    if authorized:
                        logger.info(f"Conectado a cuenta {account_id}")
                        self.accounts[account_id]["status"] = "active"
                        self._save_accounts()
                        return True
                    else:
                        logger.error(f"No se pudo conectar a cuenta {account_id}")
                        return False
            else:
                logger.error("MT5 está corriendo pero no hay cuenta conectada")
                return False
        except Exception as e:
            logger.error(f"Error verificando MT5: {e}")
            return False
    def stop_instance(self, account_id: str) -> bool:
        if account_id not in self.accounts:
            return False
        account = self.accounts[account_id]
        pid = account.get("pid")
        if pid:
            try:
                import psutil
                process = psutil.Process(pid)
                process.terminate()
                process.wait(timeout=5)
                self.accounts[account_id]["status"] = "inactive"
                self.accounts[account_id]["pid"] = None
                self._save_accounts()
                logger.info(f"MT5 instance stopped for {account_id}")
                return True
            except Exception as e:
                logger.error(f"Failed to stop MT5 instance: {e}")
                return False
        return False
    def test_connection(self, account_id: str) -> Dict:
        if account_id not in self.accounts:
            return {"success": False, "error": "Account not found"}
        account = self.accounts[account_id]
        try:
            import MetaTrader5 as mt5
            if not mt5.initialize():
                return {
                    "success": False,
                    "error": "MT5 no está corriendo. Por favor, abre MT5 manualmente primero."
                }
            password = self.credential_manager.decrypt(account["password"])
            authorized = mt5.login(
                login=int(account["login"]),
                password=password,
                server=account["server"]
            )
            if authorized:
                account_info = mt5.account_info()
                result = {
                    "success": True,
                    "balance": account_info.balance if account_info else 0,
                    "equity": account_info.equity if account_info else 0,
                    "server": account_info.server if account_info else account["server"],
                    "currency": account_info.currency if account_info else "USD",
                    "login": account_info.login if account_info else account["login"],
                    "name": account_info.name if account_info else "N/A"
                }
                logger.info(f"Connection test successful for {account_id}")
                return result
            else:
                error = mt5.last_error()
                mt5.shutdown()
                logger.error(f"Login failed for {account_id}: {error}")
                return {"success": False, "error": f"Login failed: {error}"}
        except Exception as e:
            logger.error(f"Connection test error for {account_id}: {e}")
            return {"success": False, "error": str(e)}
    def get_available_servers(self, broker_search: str = "") -> List[str]:
        common_servers = {
            "AMP": [
                "AMPGlobalUSA-Demo", "AMPGlobalUSA-Live",
                "AMPGlobal-Demo", "AMPGlobal-Live",
                "AMPFUTURES-Demo", "AMPFUTURES-Live"
            ],
            "AVA": [
                "AvaTrade-Demo", "AvaTrade-Live",
                "AvaTradeGO-Demo", "AvaTradeGO-Live",
                "AvaTradeMarkets-Demo", "AvaTradeMarkets-Live"
            ],
            "PEPPERSTONE": [
                "Pepperstone-Demo", "Pepperstone-Live",
                "PepperstoneUK-Demo", "PepperstoneUK-Live"
            ],
            "OANDA": [
                "OANDA-Demo", "OANDA-Live",
                "OANDAv20-Demo", "OANDAv20-Live"
            ],
            "FPMARKETS": [
                "FPMarketsLLC-Demo", "FPMarketsLLC-Live",
                "FPMarketsSC-Demo", "FPMarketsSC-Live"
            ]
        }
        if broker_search:
            broker_upper = broker_search.upper()
            for broker_key, servers in common_servers.items():
                if broker_upper in broker_key:
                    return servers
        all_servers = []
        for servers in common_servers.values():
            all_servers.extend(servers)
        return sorted(list(set(all_servers)))
    def get_instance_status(self, account_id: str) -> Dict:
        if account_id not in self.accounts:
            return {"status": "unknown", "error": "Account not found"}
        account = self.accounts[account_id]
        pid = account.get("pid")
        if not pid:
            return {"status": "inactive"}
        try:
            import psutil
            process = psutil.Process(pid)
            if process.is_running():
                return {
                    "status": "active",
                    "pid": pid,
                    "cpu_percent": process.cpu_percent(),
                    "memory_mb": process.memory_info().rss / 1024 / 1024
                }
            else:
                self.accounts[account_id]["status"] = "inactive"
                self.accounts[account_id]["pid"] = None
                self._save_accounts()
                return {"status": "inactive"}
        except Exception as e:
            return {"status": "error", "error": str(e)}
_manager = None
def get_manager() -> MT5AccountManager:
    global _manager
    if _manager is None:
        _manager = MT5AccountManager()
    return _manager