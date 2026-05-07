import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from typing import Tuple, Optional
from src.services.auth import supabase

def get_machine_id() -> str:
    """
    Obtiene un identificador único para el hardware (Windows).
    Utiliza el UUID de la placa base/sistema.
    """
    try:
        if sys.platform == "win32":
            cmd = "wmic csproduct get uuid"
            output = subprocess.check_output(cmd, shell=True).decode().split('\n')[1].strip()
            if output:
                return output
        
        # Fallback para otros sistemas o si wmic falla
        import socket
        return socket.gethostname()
    except Exception:
        return "unknown_machine_id"

async def validate_license(user_id: Optional[str] = None, user_role: str = "user") -> Tuple[bool, str]:
    """
    Valida la licencia del dispositivo contra Supabase.
    Retorna (is_allowed, reason).
    """
    if user_role == "admin":
        return True, "admin_access"

    machine_id = get_machine_id()
    
    if not supabase:
        return True, "offline_fallback"

    try:
        # 1. Buscar el dispositivo en la tabla trial_machines
        res = supabase.table("trial_machines").select("*").eq("machine_id", machine_id).execute()
        
        now = datetime.now(timezone.utc)
        
        if not res.data:
            # Es la primera vez que se ve este hardware. Registrarlo.
            new_device = {
                "machine_id": machine_id,
                "user_id": user_id,
                "first_seen_at": now.isoformat(),
                "last_seen_at": now.isoformat(),
                "trial_expired": False
            }
            supabase.table("trial_machines").insert(new_device).execute()
            return True, "trial_started"
        
        device = res.data[0]
        
        # Actualizar last_seen_at
        supabase.table("trial_machines").update({"last_seen_at": now.isoformat()}).eq("machine_id", machine_id).execute()

        if device.get("trial_expired"):
            return False, "manually_expired"

        # 2. Verificar suscripción premium del usuario si existe
        # Nota: La lógica de Auth ya determina si el usuario es premium.
        # Aquí consolidamos con el tiempo del trial.
        
        first_seen = datetime.fromisoformat(device["first_seen_at"].replace('Z', '+00:00'))
        days_passed = (now - first_seen).days

        # Lógica de días
        limit_days = 90 if user_role == "premium" else 14
        
        if days_passed > limit_days:
            return False, f"expired_days_{days_passed}_limit_{limit_days}"

        return True, "valid_license"

    except Exception as e:
        print(f"[License] Error validando licencia: {e}")
        # En caso de error de conexión, permitimos acceso temporal para no bloquear al usuario legítimo
        return True, "error_fallback"

if __name__ == "__main__":
    # Test local
    print(f"Machine ID: {get_machine_id()}")
