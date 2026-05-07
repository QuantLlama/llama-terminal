const LoginModal = ({ onLogin, updateInfo }) => {
  const { useState, useEffect } = React;
  const [email, setEmail] = useState(() => localStorage.getItem('ql_email') || '');
  const [password, setPassword] = useState(() => localStorage.getItem('ql_password') || '');
  const [rememberMe, setRememberMe] = useState(() => localStorage.getItem('ql_remember') === 'true');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const handleAuth = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const result = await window.supabase.auth.signInWithPassword({ email, password });
      if (result.error) throw result.error;
      if (rememberMe) {
        localStorage.setItem('ql_email', email);
        localStorage.setItem('ql_password', password);
        localStorage.setItem('ql_remember', 'true');
      } else {
        localStorage.removeItem('ql_email');
        localStorage.removeItem('ql_password');
        localStorage.setItem('ql_remember', 'false');
      }
      try {
        const sRes = await fetch('/api/auth/session', {
          headers: { 'Authorization': `Bearer ${result.data.session.access_token}` }
        });
        if (sRes.ok) {
          const sData = await sRes.json();
          if (!sData.is_subscribed) {
            const reason = sData.reason || 'unknown';
            console.warn('[Login] Access denied. Reason:', reason);
            setError(`Restricted access. PREMIUM account required. (${reason})`);
            await window.supabase.auth.signOut();
            return;
          }
        } else {
          console.warn('[Login] Subscription endpoint returned', sRes.status, '- allowing login');
        }
      } catch (subErr) {
        console.warn('Subscription check network error:', subErr, '- allowing login');
      }
      onLogin(result.data.session);
    } catch (err) {
      console.error('[Login] Supabase Auth Error:', err);
      setError(err.message === 'Invalid login credentials' ? 'Invalid credentials' : err.message);
    } finally {
      setLoading(false);
    }
  };
  return (
    React.createElement("div", { className: "fixed inset-0 z-[10000] bg-black/60 backdrop-blur-[2px] animate-fadeIn grid place-items-center text-center" },
    React.createElement("div", { className: "w-[280px] h-fit p-6 glass-panel rounded-xl shadow-2xl border border-white/5 animate-slideUp" },
    React.createElement("div", { className: "flex flex-col items-center mb-6" },
    React.createElement("img", { src: "/images/QuantumLLama.png", alt: "Logo", className: "w-20 h-20 mb-3 drop-shadow-[0_0_12px_rgba(180,83,9,0.25)] opacity-95" }),
    React.createElement("h2", { className: "text-[11px] font-bold text-white/75 tracking-[0.3em] uppercase" }, "Quantum Llama Professional")
    ),
    updateInfo?.update_required &&
    React.createElement("div", { className: "mb-4 p-1.5 bg-white/5 border border-amber-900/30 rounded text-[9px] text-amber-500/80 flex items-center justify-center gap-2" },
    React.createElement("i", { className: "fas fa-info-circle" }),
    React.createElement("p", null, "v", updateInfo.stable_version, " available")
    ),
    React.createElement("form", { onSubmit: handleAuth, className: "space-y-2.5 text-left" },
    React.createElement("input", {
      type: "email",
      required: true,
      className: "w-full bg-black/40 border border-white/5 focus:border-white/20 text-white text-[10px] p-2 rounded outline-none transition-all placeholder:text-gray-700",
      placeholder: "Email",
      value: email,
      onChange: (e) => setEmail(e.target.value) }
    ),
    React.createElement("input", {
      type: "password",
      required: true,
      className: "w-full bg-black/40 border border-white/5 focus:border-white/20 text-white text-[10px] p-2 rounded outline-none transition-all placeholder:text-gray-700",
      placeholder: "Password",
      value: password,
      onChange: (e) => setPassword(e.target.value) }
    ),
    React.createElement("div", { className: "flex items-center gap-2 px-1 py-1" },
    React.createElement("input", {
      type: "checkbox",
      className: "w-3 h-3 accent-amber-800/60 rounded border-white/10 bg-black/40",
      checked: rememberMe,
      onChange: (e) => setRememberMe(e.target.checked) }
    ),
    React.createElement("label", { className: "text-[9px] text-muted select-none cursor-pointer hover:text-white transition-colors" }, "Remember credentials"
    )
    ),
    error &&
    React.createElement("div", { className: "text-danger text-[9px] text-center p-1.5 bg-danger/5 border border-danger/10 rounded" },
    error
    ),
    React.createElement("div", { className: "flex justify-center pt-1" },
    React.createElement("button", {
      type: "submit",
      disabled: loading,
      className: "w-2/3 bg-amber-900/40 hover:bg-amber-800/60 text-white/80 font-bold text-[10px] py-1.5 rounded transition-all active:scale-[0.98] border border-white/5 disabled:opacity-50 flex items-center justify-center gap-2" },
    loading ? React.createElement("i", { className: "fas fa-circle-notch animate-spin" }) : 'SIGN IN'
    )
    )
    ),
    React.createElement("div", { className: "mt-5 pt-4 border-t border-white/5" },
    React.createElement("p", { className: "text-[9px] text-muted/60 mb-2" }, "No access?"),
    React.createElement("a", {
      href: "https://llamaterminal.nbmsystemas.com/#pricing",
      target: "_blank",
      rel: "noopener noreferrer",
      className: "text-[9px] text-muted hover:text-amber-700/80 transition-colors font-bold tracking-widest decoration-dotted underline underline-offset-4" },
    "PREMIUM PLANS"
    )
    )
    )
    ));
};
window.LoginModal = LoginModal;