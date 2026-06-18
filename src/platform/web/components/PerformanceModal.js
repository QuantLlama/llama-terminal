const { useState, useEffect, useMemo } = React;
const {
    AreaChart,
    Area,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer
} = Recharts;
const { format } = dateFns;

const PerformanceModal = ({ isOpen, onClose }) => {
    const [deals, setDeals] = useState([]);
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState('overview');

    useEffect(() => {
        if (isOpen) {
            fetchPerformanceData();
        }
    }, [isOpen]);

    const fetchPerformanceData = async () => {
        setLoading(true);
        try {
            // BUG FIX: se pasa days=9999 para traer todo el historial disponible;
            // el filtrado por período se hace en el cliente.
            const response = await fetch('/api/deals?days=9999');
            const data = await response.json();
            const rawDeals = Array.isArray(data) ? data : (data.deals || []);
            // MT5 retorna solo los deals de cierre con profit; filtramos los de entrada
            const closingDeals = rawDeals.filter((d) => {
                if (d.entry === 1 || d.entry === 2 || d.entry === 3) return true;
                if (d.entry === 0 && d.profit !== 0) return true;
                return false;
            });
            setDeals(closingDeals);
        } catch (error) {
            console.error("Error fetching performance data:", error);
        } finally {
            setLoading(false);
        }
    };

    const metrics = useMemo(() => {
        if (!deals.length) return {
            totalProfit: 0,
            winRate: 0,
            totalTrades: 0,
            winningTrades: 0,
            losingTrades: 0,
            averageProfit: 0
        };

        const totalProfit = deals.reduce((acc, deal) => acc + (deal.profit || 0) + (deal.commission || 0) + (deal.swap || 0), 0);
        const winningTrades = deals.filter(deal => ((deal.profit || 0) + (deal.commission || 0) + (deal.swap || 0)) > 0).length;
        const totalTrades = deals.length;
        const winRate = ((winningTrades / totalTrades) * 100).toFixed(1);
        const averageProfit = totalProfit / totalTrades;

        return {
            totalProfit,
            winRate,
            totalTrades,
            winningTrades,
            losingTrades: totalTrades - winningTrades,
            averageProfit
        };
    }, [deals]);

    const chartData = useMemo(() => {
        let runningProfit = 0;
        return [...deals]
            .sort((a, b) => (a.time || 0) - (b.time || 0))
            .map(deal => {
                runningProfit += (deal.profit || 0) + (deal.commission || 0) + (deal.swap || 0);
                return {
                    date: deal.time ? format(new Date(deal.time * 1000), 'MM/dd') : '—',
                    profit: parseFloat(runningProfit.toFixed(2)),
                    fullDate: deal.time ? format(new Date(deal.time * 1000), 'yyyy-MM-dd HH:mm') : '—'
                };
            });
    }, [deals]);

    if (!isOpen) return null;

    const CustomTooltip = ({ active, payload, label }) => {
        if (active && payload && payload.length) {
            return (
                <div className="bg-zinc-900 border border-white/10 p-3 rounded-xl shadow-2xl backdrop-blur-md">
                    <p className="text-[10px] text-zinc-500 font-bold mb-1">{payload[0].payload.fullDate}</p>
                    <p className="text-sm font-black text-white">
                        Profit: <span className={payload[0].value >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                            ${payload[0].value}
                        </span>
                    </p>
                </div>
            );
        }
        return null;
    };

    const renderOverview = () => {
        return (
            <div className="flex flex-col gap-6">
                <div>
                    <h2 className="text-xl font-bold mb-4">Evolución de Ganancia</h2>
                    <div className="h-64 md:h-80 w-full mb-6 relative">
                        {loading && (
                            <div className="absolute inset-0 bg-black/50 z-10 flex items-center justify-center rounded-lg backdrop-blur-sm">
                                <div className="animate-spin text-accent text-3xl">
                                    <i className="fas fa-circle-notch"></i>
                                </div>
                            </div>
                        )}
                        <ResponsiveContainer width="100%" height="100%">
                            <AreaChart data={chartData}>
                                <defs>
                                    <linearGradient id="colorProfit" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor="var(--color-accent)" stopOpacity={0.3} />
                                        <stop offset="95%" stopColor="var(--color-accent)" stopOpacity={0} />
                                    </linearGradient>
                                </defs>
                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(255,255,255,0.05)" />
                                <XAxis
                                    dataKey="date"
                                    stroke="rgba(255,255,255,0.3)"
                                    tick={{ fontSize: 10 }}
                                    interval="preserveStartEnd"
                                />
                                <YAxis
                                    stroke="rgba(255,255,255,0.3)"
                                    tick={{ fontSize: 10 }}
                                    tickFormatter={(val) => `$${val}`}
                                />
                                <Tooltip content={<CustomTooltip />} />
                                <Area
                                    type="monotone"
                                    dataKey="profit"
                                    stroke="var(--color-accent)"
                                    strokeWidth={3}
                                    fillOpacity={1}
                                    fill="url(#colorProfit)"
                                    animationDuration={1500}
                                />
                            </AreaChart>
                        </ResponsiveContainer>
                    </div>

                    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                        <div className="p-4 rounded-xl bg-white/5 border border-white/5 hover:bg-white/[0.07] transition-all">
                            <span className="text-[10px] text-zinc-500 font-bold uppercase tracking-wider block mb-1">Total Cerrado</span>
                            <div className="text-xl font-black text-white">
                                <span className={metrics.totalProfit >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                                    ${metrics.totalProfit.toFixed(2)}
                                </span>
                            </div>
                        </div>
                        <div className="p-4 rounded-xl bg-white/5 border border-white/5 hover:bg-white/[0.07] transition-all">
                            <span className="text-[10px] text-zinc-500 font-bold uppercase tracking-wider block mb-1">Win Rate</span>
                            <div className="text-xl font-black text-white">
                                {metrics.winRate}%
                            </div>
                            <div className="w-full h-1 bg-white/10 rounded-full mt-2">
                                <div
                                    className="h-full bg-accent rounded-full transition-all duration-1000"
                                    style={{ width: `${metrics.winRate}%` }}
                                />
                            </div>
                        </div>
                        <div className="p-4 rounded-xl bg-white/5 border border-white/5 hover:bg-white/[0.07] transition-all">
                            <span className="text-[10px] text-zinc-500 font-bold uppercase tracking-wider block mb-1">Operaciones</span>
                            <div className="text-xl font-black text-white">
                                {metrics.totalTrades}
                                <span className="ml-2 text-[10px] text-zinc-500 font-medium">({metrics.winningTrades}W / {metrics.losingTrades}L)</span>
                            </div>
                        </div>
                        <div className="p-4 rounded-xl bg-white/5 border border-white/5 hover:bg-white/[0.07] transition-all">
                            <span className="text-[10px] text-zinc-500 font-bold uppercase tracking-wider block mb-1">Promedio / Trade</span>
                            <div className="text-xl font-black text-white">
                                <span className={metrics.averageProfit >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                                    ${metrics.averageProfit.toFixed(2)}
                                </span>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Lista de Operaciones Recientes */}
                <div className="mt-4">
                    <div className="flex items-center justify-between mb-4">
                        <h2 className="text-lg font-bold">Historial Reciente</h2>
                        <span className="text-[10px] text-zinc-500 uppercase font-black tracking-widest bg-white/5 px-2 py-1 rounded">
                            Últimos {deals.slice(0, 10).length} de {deals.length}
                        </span>
                    </div>
                    <div className="overflow-hidden rounded-xl border border-white/5 bg-black/20">
                        <table className="w-full text-left">
                            <thead className="bg-white/5 text-[10px] font-black uppercase tracking-widest text-zinc-400">
                                <tr>
                                    <th className="p-4">Fecha</th>
                                    <th className="p-4">Símbolo</th>
                                    <th className="p-4">Tipo</th>
                                    <th className="p-4 text-right">Volumen</th>
                                    <th className="p-4 text-right">Precio Emisión</th>
                                    <th className="p-4 text-right">Precio Cierre</th>
                                    <th className="p-4 text-right">Profit</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-white/5">
                                {deals.slice(0, 10).map((deal, idx) => (
                                    <tr key={idx} className="hover:bg-white/5 transition-colors group">
                                        <td className="p-4 text-[11px] text-zinc-400">
                                            {deal.time ? format(new Date(deal.time), 'dd/MM HH:mm') : '-'}
                                        </td>
                                        <td className="p-4 font-black text-white">
                                            {deal.symbol}
                                        </td>
                                        <td className="p-4">
                                            <span className={`px-2 py-0.5 rounded text-[9px] font-black uppercase tracking-widest ${deal.type === 'BUY' || deal.type === 0 ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'
                                                }`}>
                                                {deal.type === 0 ? 'BUY' : deal.type === 1 ? 'SELL' : deal.type}
                                            </span>
                                        </td>
                                        <td className="p-4 text-right text-xs text-zinc-300">
                                            {deal.volume?.toFixed(2)}
                                        </td>
                                        <td className="p-4 text-right text-xs text-zinc-300">
                                            {deal.price?.toFixed(2)}
                                        </td>
                                        <td className="p-4 text-right text-xs text-zinc-300">
                                            {deal.price_close?.toFixed(2) || '-'}
                                        </td>
                                        <td className={`p-4 text-right font-bold text-xs ${(deal.profit || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'
                                            }`}>
                                            ${(deal.profit || 0).toFixed(2)}
                                        </td>
                                    </tr>
                                ))}
                                {deals.length === 0 && (
                                    <tr>
                                        <td colSpan="7" className="p-10 text-center text-zinc-500 text-xs italic">
                                            No se encontraron operaciones registradas
                                        </td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        );
    };

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 md:p-8 animate-in fade-in duration-300">
            <div className="absolute inset-0 bg-black/80 backdrop-blur-md" onClick={onClose} />

            <div className="relative w-full max-w-6xl max-h-[90vh] bg-zinc-950 border border-white/10 rounded-3xl shadow-2xl flex flex-col overflow-hidden">
                {/* Header */}
                <div className="p-6 border-b border-white/5 flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <div className="w-12 h-12 rounded-2xl bg-accent/10 flex items-center justify-center">
                            <i className="fas fa-chart-line text-accent text-xl"></i>
                        </div>
                        <div>
                            <h1 className="text-2xl font-black text-white uppercase tracking-tight">Performance Center</h1>
                            <p className="text-xs text-zinc-500 font-medium">Análisis avanzado de rentabilidad y métricas de trading</p>
                        </div>
                    </div>
                    <button
                        onClick={onClose}
                        className="w-10 h-10 rounded-xl hover:bg-white/5 text-zinc-500 hover:text-white transition-all flex items-center justify-center border border-transparent hover:border-white/10"
                    >
                        <i className="fas fa-times"></i>
                    </button>
                </div>

                {/* Tabs */}
                <div className="flex border-b border-white/5 px-6">
                    <button
                        onClick={() => setActiveTab('overview')}
                        className={`px-6 py-4 text-[10px] font-black uppercase tracking-[0.2em] transition-all relative ${activeTab === 'overview' ? 'text-accent' : 'text-zinc-500 hover:text-zinc-300'
                            }`}
                    >
                        General Overview
                        {activeTab === 'overview' && <div className="absolute bottom-0 left-6 right-6 h-0.5 bg-accent shadow-[0_0_10px_var(--color-accent)]" />}
                    </button>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-6 scrollbar-thin scrollbar-thumb-white/10 scrollbar-track-transparent">
                    {renderOverview()}
                </div>

                {/* Footer Status */}
                <div className="px-6 py-3 bg-white/[0.02] border-t border-white/5 flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <div className="flex items-center gap-2">
                            <div className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                            <span className="text-[10px] font-black text-zinc-500 uppercase tracking-widest">Live Feed Connected</span>
                        </div>
                        <div className="flex items-center gap-2">
                            <span className="text-[10px] font-black text-emerald-400 uppercase tracking-widest cursor-pointer hover:underline" onClick={fetchPerformanceData}>
                                <i className="fas fa-sync-alt mr-1"></i> Sync Data
                            </span>
                        </div>
                    </div>
                    <div className="text-[9px] font-bold text-zinc-700 uppercase tracking-[0.3em]">
                        Quantum Llama v1.8.1 - Experimental Analysis
                    </div>
                </div>
            </div>
        </div>
    );
};

window.PerformanceModal = PerformanceModal;
