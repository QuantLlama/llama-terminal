import os
from supabase import create_client, Client
from fastapi import Request, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
load_dotenv()

# Built-in defaults (protected by PyArmor in production builds)
_DEFAULT_URL = ""
_DEFAULT_KEY = ""

SUPABASE_URL = os.getenv("SUPABASE_URL", _DEFAULT_URL)
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", _DEFAULT_KEY)
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY) if SUPABASE_URL and SUPABASE_ANON_KEY else None
except Exception as e:
    print(f"WARNING: Supabase client init failed: {e}. Auth features disabled.")
    supabase = None
security = HTTPBearer()
async def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)):
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase not configured")
    token = credentials.credentials
    try:
        user = supabase.auth.get_user(token)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
        return user
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")
async def check_subscription(user_id: str, token: str = None):
    if not supabase:
        print("[Auth] Supabase client not initialized")
        return False, "supabase_not_initialized"
    
    try:
        local_client = supabase
        if token:
            try:
                local_client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
                local_client.postgrest.auth(token)
            except Exception as ce:
                print(f"[Auth] Failed to create token client: {ce}. Using default.")
                local_client = supabase
        
        try:
            profile_res = local_client.table("profiles").select("role, is_pro").eq("user_id", user_id).single().execute()
        except Exception as pe:
            print(f"[Auth] CRITICAL: Table 'profiles' access failed for {user_id}: {pe}")
            return True, "supabase_unreachable_fallback"
        
        if not profile_res.data:
            print(f"[Auth] Profile NOT FOUND for user_id: {user_id}")
            return False, "profile_not_found"
            
        profile = profile_res.data
        role = profile.get("role")
        is_pro = profile.get("is_pro", False)
        
        # ADMIN HAS NO RESTRICTIONS
        if role == "admin":
            print(f"[Auth] Admin user detected: {user_id}. Granting full access.")
            return True, "admin"

        print(f"[Auth] Profile found: role={role}, is_pro={is_pro}")
        if not is_pro and role != "premium":
            return False, f"not_premium_role={role}_is_pro={is_pro}"
        try:
            sub_res = local_client.table("subscriptions").select("current_period_end, status").eq("user_id", user_id).execute()
        except Exception as se:
            print(f"[Auth] Table 'subscriptions' access failed: {se}")
            return True, "is_pro_db_fallback"
        if sub_res.data:
            active_subs = [s for s in sub_res.data if s.get("status") == "active"]
            sub_end_str = None
            if active_subs:
                sub_end_str = active_subs[-1].get("current_period_end")
            if sub_end_str:
                from datetime import datetime, timezone
                try:
                    clean_date = sub_end_str.replace(' ', 'T').replace('Z', '+00:00')
                    sub_end = datetime.fromisoformat(clean_date)
                    now = datetime.now(timezone.utc)
                    if sub_end > now:
                        return True, "active_subscription"
                    else:
                        print(f"[Auth] EXPIRED on {sub_end} for {user_id}")
                        return False, f"subscription_expired_{sub_end}"
                except Exception as date_err:
                    print(f"[Auth] Error parsing date {sub_end_str}: {date_err}")
                    return True, "date_parse_fallback"
        if is_pro:
            return True, "is_pro_flag"
        return False, "no_active_subscription"
    except Exception as e:
        print(f"[Auth] Critical error checking permissions for {user_id}: {e}")
        import traceback
        traceback.print_exc()
        return True, f"critical_error_fallback: {str(e)}"