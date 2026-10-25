import os
import threading
import logging
from datetime import datetime
from typing import Optional
from src.services.active_tenant import get_active_user_id, note_missing_active_user
logger = logging.getLogger(__name__)
def log_diag(msg):
    try:
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
        diag_file = os.path.join(root_dir, "mirror_diagnostics.txt")
        with open(diag_file, "a") as f:
            f.write(f"{datetime.now()} | {msg}\n")
    except Exception as e:
        logger.error(f"Failed to write to mirror_diagnostics: {e}")
def replicate_to_nt8_sync(
    symbol, action, volume, sl_dist=None, tp_dist=None, price=0, entry_price=0, sl=0, tp=0, order_type="MKT"
):
    if not symbol:
        return
    # A mirrored order belongs to the account its owner is trading. This runs in a
    # thread with no request context, so it reads the active tenant and does
    # nothing at all while nobody has selected one.
    user_id = get_active_user_id()
    if not user_id:
        note_missing_active_user("nt8-replication", logger)
        return
    try:
        from src.services.ninjatrader_manager import get_nt8_manager
        manager = get_nt8_manager()
        nt8_accounts = manager.get_accounts(user_id=user_id)
        if not nt8_accounts:
            return
        norm_symbol = symbol.split(".")[0].split("_")[0]
        if len(norm_symbol) > 3 and norm_symbol[-1].isdigit():
            if norm_symbol[-2].isdigit():
                norm_symbol = norm_symbol[:-3]
            else:
                norm_symbol = norm_symbol[:-2]
        final_abs_sl = -1.0 
        final_abs_tp = -1.0 
        if sl is not None and sl != 0:
            final_abs_sl = float(sl)
        elif sl_dist is not None:
            if sl_dist == -2.0:
                final_abs_sl = -2.0
            elif sl_dist > 0:
                ref = entry_price or price
                if ref > 0:
                    if "BUY" in action:
                        final_abs_sl = ref - sl_dist
                    else:
                        final_abs_sl = ref + sl_dist
        if tp is not None and tp != 0:
            final_abs_tp = float(tp)
        elif tp_dist is not None:
            if tp_dist == -2.0:
                final_abs_tp = -2.0
            elif tp_dist > 0:
                ref = entry_price or price
                if ref > 0:
                    if "BUY" in action:
                        final_abs_tp = ref + tp_dist
                    else:
                        final_abs_tp = ref - tp_dist
        final_sl_dist = sl_dist if sl_dist is not None else (-2.0 if sl == 0 else (-1.0 if sl is None else abs(float(sl) - (entry_price or price or float(sl)))))
        final_tp_dist = tp_dist if tp_dist is not None else (-2.0 if tp == 0 else (-1.0 if tp is None else abs(float(tp) - (entry_price or price or float(tp)))))
        if final_abs_sl > 0: log_diag(f"SYNC-LOG: {action} SL Absolute={final_abs_sl}")
        if final_abs_tp > 0: log_diag(f"SYNC-LOG: {action} TP Absolute={final_abs_tp}")
        nt8_action = action
        if action == "MODIFY":
            nt8_action = "MODIFY"
        elif order_type and action not in ("CANCEL", "CLOSE", "FLAT"):
            u_type = order_type.upper()
            if "LIMIT" in u_type or "LMT" in u_type:
                nt8_action = f"{action}_LMT"
            elif "STOP" in u_type or "STP" in u_type:
                nt8_action = f"{action}_STP"
        command = f"{nt8_action}|{norm_symbol}|{volume}|{final_sl_dist}|{final_tp_dist}|{price}|{order_type}|{final_abs_sl}|{final_abs_tp}"
        for acc in nt8_accounts:
            if not acc.get("mirror_trading", True):
                continue
            ex_dir = acc.get("exchange_dir")
            if not ex_dir or not os.path.exists(ex_dir):
                log_diag(f"[REPLICATOR] Error: Exchange dir not found for {acc.get('name')}")
                continue
            cmd_file = os.path.join(ex_dir, "commands.txt")
            try:
                with open(cmd_file, "a") as f:
                    f.write(command + "\n")
                log_diag(f"[REPLICATOR] Command sent to {acc.get('name')}: {command}")
            except Exception as e:
                log_diag(f"[REPLICATOR] Write failed for {acc.get('name')}: {e}")
    except Exception as e:
        log_diag(f"[REPLICATOR] Critical Failure: {e}")
def replicate_to_nt8_background(*args, **kwargs):
    threading.Thread(target=replicate_to_nt8_sync, args=args, kwargs=kwargs, daemon=True).start()