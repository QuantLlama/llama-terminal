#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Linq;
using System.Text;
using System.Windows;
using System.Windows.Input;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.SuperDom;
using NinjaTrader.Gui.Tools;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.Core.FloatingPoint;
using NinjaTrader.NinjaScript.Indicators;
using NinjaTrader.NinjaScript.DrawingTools;
using System.IO;
#endregion

// ============================================================
//  QuantumGANConnector  v4.3  –  TURBOSYNC BIDIRECTIONAL
//  FIX v4.1: TP orphan cancelado en CLOSE/FLAT por comando
//  FIX v4.2: TP orphan cancelado en cierre MANUAL (OnPositionUpdate)
//  FIX v4.3: EnterLongStopMarket/EnterShortStopMarket (CS0103)
//            o.Instrument.MasterInstrument.Name (CS1061)
// ============================================================
namespace NinjaTrader.NinjaScript.Strategies
{
    public class QuantumGANConnector : Strategy
    {
        [NinjaScriptProperty]
        [Display(Name = "Exchange Directory", Order = 1, GroupName = "QuantumGAN")]
        public string ExchangeDir { get; set; } = @"C:\QuantumGAN\Exchange";

        [NinjaScriptProperty]
        [Display(Name = "DOM Depth", Order = 2, GroupName = "QuantumGAN")]
        public int DomDepth { get; set; } = 20;

        private string commandsFile;
        private string positionsFile;
        private string accountFile;
        private string tradesFile;
        private string domFile;
        private string connectorLog;

        private readonly object domLock = new object();
        private SortedDictionary<double, long> bidBook = new SortedDictionary<double, long>(Comparer<double>.Create((a, b) => b.CompareTo(a)));
        private SortedDictionary<double, long> askBook = new SortedDictionary<double, long>();
        private volatile bool domDirty = false;

        private int currentSLTicks = 0;
        private int currentTPTicks = 0;
        private double currentSLPrice = 0;
        private double currentTPPrice = 0;

        private DateTime lastDomExport    = DateTime.MinValue;
        private DateTime lastStatusExport = DateTime.MinValue;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "QuantumGAN v4.3 – TurboSync Bidirectional + All Fixes";
                Name        = "QuantumGANConnector";
                Calculate   = Calculate.OnEachTick;
                EntriesPerDirection          = 1;
                EntryHandling                = EntryHandling.AllEntries;
                IsExitOnSessionCloseStrategy = false;
                BarsRequiredToTrade          = 5;
            }
            else if (State == State.Configure)
            {
                commandsFile  = Path.Combine(ExchangeDir, "commands.txt");
                positionsFile = Path.Combine(ExchangeDir, "positions.csv");
                accountFile   = Path.Combine(ExchangeDir, "account.csv");
                tradesFile    = Path.Combine(ExchangeDir, "trades.csv");
                domFile       = Path.Combine(ExchangeDir, "dom.csv");
                connectorLog  = Path.Combine(ExchangeDir, "connector_log.txt");

                if (!Directory.Exists(ExchangeDir)) Directory.CreateDirectory(ExchangeDir);
            }
            else if (State == State.DataLoaded)
            {
                Log("<<<< VERSION 4.3 - TURBOSYNC BIDIRECTIONAL - ALL FIXES >>>>");
            }
        }

        protected override void OnBarUpdate()
        {
            if (CurrentBar < BarsRequiredToTrade) return;

            CheckCommands();

            if ((DateTime.Now - lastStatusExport).TotalMilliseconds >= 250)
            {
                ExportAccount();
                ExportPositions();
                ExportOHLCV();
                lastStatusExport = DateTime.Now;
            }

            if (domDirty && (DateTime.Now - lastDomExport).TotalMilliseconds >= 100)
            {
                lock (domLock)
                {
                    if (domDirty)
                    {
                        ExportDOM_Locked();
                        domDirty      = false;
                        lastDomExport = DateTime.Now;
                    }
                }
            }
        }

        private void CheckCommands()
        {
            if (!File.Exists(commandsFile)) return;
            string[] lines;
            try
            {
                lines = File.ReadAllLines(commandsFile);
                if (lines.Length == 0) return;
                File.WriteAllText(commandsFile, string.Empty);
            }
            catch { return; }

            foreach (string raw in lines)
            {
                string line = raw.Trim();
                if (string.IsNullOrEmpty(line) || line.StartsWith("#")) continue;

                Log("[CMD] Received: " + line);
                try
                {
                    string[] p = line.Split('|');
                    if (p.Length < 2) continue;

                    string action   = p[0].Trim().ToUpper();
                    string symbol   = p[1].Trim();
                    int    quantity = p.Length > 2 ? (int)double.Parse(p[2].Trim(), System.Globalization.CultureInfo.InvariantCulture) : 1;
                    double slDist   = p.Length > 3 ? double.Parse(p[3].Trim(), System.Globalization.CultureInfo.InvariantCulture) : 0;
                    double tpDist   = p.Length > 4 ? double.Parse(p[4].Trim(), System.Globalization.CultureInfo.InvariantCulture) : 0;
                    double price    = p.Length > 5 ? double.Parse(p[5].Trim(), System.Globalization.CultureInfo.InvariantCulture) : 0;
                    // OrderType is p[6]
                    double absSL    = p.Length > 7 ? double.Parse(p[7].Trim(), System.Globalization.CultureInfo.InvariantCulture) : -1.0;
                    double absTP    = p.Length > 8 ? double.Parse(p[8].Trim(), System.Globalization.CultureInfo.InvariantCulture) : -1.0;

                    if (!SymbolMatches(symbol)) continue;

                    ExecuteCommand(action, quantity, slDist, tpDist, price, absSL, absTP);
                }
                catch (Exception ex) { Log("[ERROR] CMD Parse: " + ex.Message); }
            }
        }

        private bool SymbolMatches(string col)
        {
            if (string.IsNullOrEmpty(col)) return false;
            string cleanInstr  = Instrument.FullName.Replace(" ","").Replace("-","").ToUpper();
            string cleanMaster = Instrument.MasterInstrument.Name.Replace(" ","").Replace("-","").ToUpper();
            string cleanCmd    = col.Replace(" ","").Replace("-","").ToUpper();
            
            // Si el comando contiene el master (ej: MNQ contiene MNQ)
            // O si el master contiene el comando (ej: MNQ contiene MNQH26 - por eso usamos Contains en ambos sentidos)
            return cleanInstr.Contains(cleanCmd) || cleanCmd.Contains(cleanMaster) || cleanMaster.Contains(cleanCmd);
        }

        private void ExecuteCommand(string action, int quantity, double slDist, double tpDist, double price, double absSL = -1.0, double absTP = -1.0)
        {
            // ROUND PRICE TO TICK SIZE - Essential for NinjaTrader 8 to accept orders/modifications
            double roundedPrice = (price > 0) ? Instrument.MasterInstrument.RoundToTickSize(price) : 0;

            // -1 = PRESERVE  |  -2 = REMOVE/DISARM  |  >=0 = UPDATE (0 = Break-even)
            bool slPreserve = (slDist == -1);
            bool slRemove   = (slDist == -2);
            bool tpPreserve = (tpDist == -1);
            bool tpRemove   = (tpDist == -2);

            // Calculation for ticks: if >= 0, we want a valid tick count. 
            // Distance 0 means Break-even -> must be at least 1 tick to be valid in SetStopLoss/SetProfitTarget
            int slTicks = (!slPreserve && !slRemove && slDist >= 0) ? (int)Math.Max(1, Math.Round(slDist / TickSize)) : 0;
            int tpTicks = (!tpPreserve && !tpRemove && tpDist >= 0) ? (int)Math.Max(1, Math.Round(tpDist / TickSize)) : 0;

            // ABSOLUTE PRICE SYNC: If absolute prices are provided, recalculate ticks relative to NT8 entry to avoid slippage drift
            if (absSL > 0)
            {
                double refEntry = (Position.MarketPosition != MarketPosition.Flat) ? Position.AveragePrice : roundedPrice;
                if (refEntry > 0)
                {
                    int recalculatedSL = (int)Math.Max(1, Math.Round(Math.Abs(absSL - refEntry) / TickSize));
                    if (recalculatedSL != slTicks)
                    {
                        Log(string.Format("[SYNC] SL Distance adjusted for entry discrepancy: {0}t -> {1}t (based on AbsPrice {2})", slTicks, recalculatedSL, absSL));
                        slTicks = recalculatedSL;
                    }
                }
            }
            if (absTP > 0)
            {
                double refEntry = (Position.MarketPosition != MarketPosition.Flat) ? Position.AveragePrice : roundedPrice;
                if (refEntry > 0)
                {
                    int recalculatedTP = (int)Math.Max(1, Math.Round(Math.Abs(absTP - refEntry) / TickSize));
                    if (recalculatedTP != tpTicks)
                    {
                        Log(string.Format("[SYNC] TP Distance adjusted for entry discrepancy: {0}t -> {1}t (based on AbsPrice {2})", tpTicks, recalculatedTP, absTP));
                        tpTicks = recalculatedTP;
                    }
                }
            }

            // Safe disarm value (capped to ensure price doesn't go <= 0)
            int disarmTicks = 2000;
            if (roundedPrice > 0) 
            {
                int maxPossibleTicks = (int)Math.Floor(roundedPrice / TickSize) - 10;
                if (maxPossibleTicks < disarmTicks) disarmTicks = Math.Max(100, maxPossibleTicks);
            }

            Log(string.Format("[EXEC] {0} Qty={1} SL={2}({3}t) TP={4}({5}t) Price={6} (Rounded={7})",
                action, quantity, slDist, slTicks, tpDist, tpTicks, price, roundedPrice));

            switch (action)
            {
                // ── MARKET ENTRIES ──────────────────────────────────────────
                case "BUY":
                    if (Position.MarketPosition == MarketPosition.Short && quantity > 0)
                    {
                        Log(string.Format("[EXEC] BUY (ExitShort) Qty={0}", quantity));
                        ExitShort(quantity, "MirrorExit", "MirrorEntry");
                        if (quantity > Position.Quantity)
                            EnterLong(quantity - Position.Quantity, "MirrorEntry");
                    }
                    else
                    {
                        if (absSL > 0) { SetStopLoss(CalculationMode.Price, Instrument.MasterInstrument.RoundToTickSize(absSL)); currentSLPrice = absSL; }
                        else if (slTicks > 0) { SetStopLoss(CalculationMode.Ticks, slTicks); currentSLTicks = slTicks; currentSLPrice = 0; }
                        else { SetStopLoss(CalculationMode.Ticks, disarmTicks); currentSLTicks = 0; currentSLPrice = 0; }

                        if (absTP > 0) { SetProfitTarget("MirrorEntry", CalculationMode.Price, Instrument.MasterInstrument.RoundToTickSize(absTP)); currentTPPrice = absTP; }
                        else if (tpTicks > 0) { SetProfitTarget("MirrorEntry", CalculationMode.Ticks, tpTicks); currentTPTicks = tpTicks; currentTPPrice = 0; }
                        else { SetProfitTarget("MirrorEntry", CalculationMode.Ticks, disarmTicks); currentTPTicks = 0; currentTPPrice = 0; }
                        
                        EnterLong(quantity, "MirrorEntry");
                    }
                    break;

                case "SELL":
                    if (Position.MarketPosition == MarketPosition.Long && quantity > 0)
                    {
                        Log(string.Format("[EXEC] SELL (ExitLong) Qty={0}", quantity));
                        ExitLong(quantity, "MirrorExit", "MirrorEntry");
                        if (quantity > Position.Quantity)
                            EnterShort(quantity - Position.Quantity, "MirrorEntry");
                    }
                    else
                    {
                        if (absSL > 0) { SetStopLoss(CalculationMode.Price, Instrument.MasterInstrument.RoundToTickSize(absSL)); currentSLPrice = absSL; currentSLTicks = 0; }
                        else if (slTicks > 0) { SetStopLoss(CalculationMode.Ticks, slTicks); currentSLTicks = slTicks; currentSLPrice = 0; }
                        else { SetStopLoss(CalculationMode.Ticks, disarmTicks); currentSLTicks = 0; currentSLPrice = 0; }

                        if (absTP > 0) { SetProfitTarget("MirrorEntry", CalculationMode.Price, Instrument.MasterInstrument.RoundToTickSize(absTP)); currentTPPrice = absTP; currentTPTicks = 0; }
                        else if (tpTicks > 0) { SetProfitTarget("MirrorEntry", CalculationMode.Ticks, tpTicks); currentTPTicks = tpTicks; currentTPPrice = 0; }
                        else { SetProfitTarget("MirrorEntry", CalculationMode.Ticks, disarmTicks); currentTPTicks = 0; currentTPPrice = 0; }

                        EnterShort(quantity, "MirrorEntry");
                    }
                    break;

                // ── LIMIT ENTRIES ───────────────────────────────────────────
                case "BUY_LMT":
                    if (Position.MarketPosition == MarketPosition.Short && quantity > 0)
                    {
                        Log(string.Format("[EXEC] BUY_LMT (ExitShortLimit) Qty={0} Price={1}", quantity, roundedPrice));
                        ExitShortLimit(quantity, roundedPrice, "MirrorExit", "MirrorEntry");
                    }
                    else
                    {
                        if (absSL > 0) { SetStopLoss(CalculationMode.Price, Instrument.MasterInstrument.RoundToTickSize(absSL)); currentSLPrice = absSL; currentSLTicks = 0; }
                        else if (slTicks > 0) { SetStopLoss(CalculationMode.Ticks, slTicks); currentSLTicks = slTicks; currentSLPrice = 0; }
                        else { SetStopLoss(CalculationMode.Ticks, disarmTicks); currentSLTicks = 0; currentSLPrice = 0; }

                        if (absTP > 0) { SetProfitTarget("MirrorEntry", CalculationMode.Price, Instrument.MasterInstrument.RoundToTickSize(absTP)); currentTPPrice = absTP; currentTPTicks = 0; }
                        else if (tpTicks > 0) { SetProfitTarget("MirrorEntry", CalculationMode.Ticks, tpTicks); currentTPTicks = tpTicks; currentTPPrice = 0; }
                        else { SetProfitTarget("MirrorEntry", CalculationMode.Ticks, disarmTicks); currentTPTicks = 0; currentTPPrice = 0; }

                        EnterLongLimit(quantity, roundedPrice, "MirrorEntry");
                    }
                    break;

                case "SELL_LMT":
                    if (Position.MarketPosition == MarketPosition.Long && quantity > 0)
                    {
                        Log(string.Format("[EXEC] SELL_LMT (ExitLongLimit) Qty={0} Price={1}", quantity, roundedPrice));
                        ExitLongLimit(quantity, roundedPrice, "MirrorExit", "MirrorEntry");
                    }
                    else
                    {
                        if (absSL > 0) { SetStopLoss(CalculationMode.Price, Instrument.MasterInstrument.RoundToTickSize(absSL)); currentSLPrice = absSL; currentSLTicks = 0; }
                        else if (slTicks > 0) { SetStopLoss(CalculationMode.Ticks, slTicks); currentSLTicks = slTicks; currentSLPrice = 0; }
                        else { SetStopLoss(CalculationMode.Ticks, disarmTicks); currentSLTicks = 0; currentSLPrice = 0; }

                        if (absTP > 0) { SetProfitTarget("MirrorEntry", CalculationMode.Price, Instrument.MasterInstrument.RoundToTickSize(absTP)); currentTPPrice = absTP; currentTPTicks = 0; }
                        else if (tpTicks > 0) { SetProfitTarget("MirrorEntry", CalculationMode.Ticks, tpTicks); currentTPTicks = tpTicks; currentTPPrice = 0; }
                        else { SetProfitTarget("MirrorEntry", CalculationMode.Ticks, disarmTicks); currentTPTicks = 0; currentTPPrice = 0; }

                        EnterShortLimit(quantity, roundedPrice, "MirrorEntry");
                    }
                    break;

                // ── STOP ENTRIES ─────────────────────────────────────────────
                case "BUY_STP":
                    if (Position.MarketPosition == MarketPosition.Short && quantity > 0)
                    {
                        Log(string.Format("[EXEC] BUY_STP (ExitShortStopMarket) Qty={0} Price={1}", quantity, roundedPrice));
                        ExitShortStopMarket(quantity, roundedPrice, "MirrorExit", "MirrorEntry");
                    }
                    else
                    {
                        if (absSL > 0) { SetStopLoss(CalculationMode.Price, Instrument.MasterInstrument.RoundToTickSize(absSL)); currentSLPrice = absSL; currentSLTicks = 0; }
                        else if (slTicks > 0) { SetStopLoss(CalculationMode.Ticks, slTicks); currentSLTicks = slTicks; currentSLPrice = 0; }
                        else { SetStopLoss(CalculationMode.Ticks, disarmTicks); currentSLTicks = 0; currentSLPrice = 0; }

                        if (absTP > 0) { SetProfitTarget("MirrorEntry", CalculationMode.Price, Instrument.MasterInstrument.RoundToTickSize(absTP)); currentTPPrice = absTP; currentTPTicks = 0; }
                        else if (tpTicks > 0) { SetProfitTarget("MirrorEntry", CalculationMode.Ticks, tpTicks); currentTPTicks = tpTicks; currentTPPrice = 0; }
                        else { SetProfitTarget("MirrorEntry", CalculationMode.Ticks, disarmTicks); currentTPTicks = 0; currentTPPrice = 0; }

                        EnterLongStopMarket(quantity, roundedPrice, "MirrorEntry");
                    }
                    break;

                case "SELL_STP":
                    if (Position.MarketPosition == MarketPosition.Long && quantity > 0)
                    {
                        Log(string.Format("[EXEC] SELL_STP (ExitLongStopMarket) Qty={0} Price={1}", quantity, roundedPrice));
                        ExitLongStopMarket(quantity, roundedPrice, "MirrorExit", "MirrorEntry");
                    }
                    else
                    {
                        if (absSL > 0) { SetStopLoss(CalculationMode.Price, Instrument.MasterInstrument.RoundToTickSize(absSL)); currentSLPrice = absSL; currentSLTicks = 0; }
                        else if (slTicks > 0) { SetStopLoss(CalculationMode.Ticks, slTicks); currentSLTicks = slTicks; currentSLPrice = 0; }
                        else { SetStopLoss(CalculationMode.Ticks, disarmTicks); currentSLTicks = 0; currentSLPrice = 0; }

                        if (absTP > 0) { SetProfitTarget("MirrorEntry", CalculationMode.Price, Instrument.MasterInstrument.RoundToTickSize(absTP)); currentTPPrice = absTP; currentTPTicks = 0; }
                        else if (tpTicks > 0) { SetProfitTarget("MirrorEntry", CalculationMode.Ticks, tpTicks); currentTPTicks = tpTicks; currentTPPrice = 0; }
                        else { SetProfitTarget("MirrorEntry", CalculationMode.Ticks, disarmTicks); currentTPTicks = 0; currentTPPrice = 0; }

                        EnterShortStopMarket(quantity, roundedPrice, "MirrorEntry");
                    }
                    break;

                // ── MODIFY ───────────────────────────────────────────────────
                case "MODIFY":
                    bool pendingModified = false;
                    bool entryMoved = (roundedPrice > 0);

                    // 1. Handle Price Move (Atomic Move: Cancel + Re-place)
                    if (entryMoved)
                    {
                        Log(string.Format("[MODIFY] Move requested to {0}. Searching for order...", roundedPrice));
                        try
                        {
                            Order o = Account.Orders.FirstOrDefault(x => 
                                (x.OrderState == OrderState.Working || x.OrderState == OrderState.Accepted)
                                && x.Instrument != null 
                                && SymbolMatches(x.Instrument.MasterInstrument.Name)
                                && (x.Name == "MirrorEntry" || x.Name == "MirrorExit"));

                            if (o == null)
                            {
                                o = Account.Orders.FirstOrDefault(x => 
                                    (x.OrderState == OrderState.Working || x.OrderState == OrderState.Accepted)
                                    && x.Instrument != null 
                                    && SymbolMatches(x.Instrument.MasterInstrument.Name)
                                    && (x.Name.Contains("Limit") || x.Name.Contains("Stop") || x.Name.Contains("Mirror") || x.Name.Contains("Entry")));
                            }

                            if (o != null)
                            {
                                Log(string.Format("[MODIFY] Atomic Move/Update: Cancelling {0} and re-placing at {1}", o.Name, roundedPrice));
                                pendingModified = true;
                                
                                // Update persistent state before re-placing
                                if (!slPreserve) { currentSLTicks = slTicks; currentSLPrice = absSL > 0 ? absSL : 0; }
                                if (!tpPreserve) { currentTPTicks = tpTicks; currentTPPrice = absTP > 0 ? absTP : 0; }

                                CancelOrder(o);

                                // Apply brackets for the new order
                                if (currentSLPrice > 0) SetStopLoss(CalculationMode.Price, Instrument.MasterInstrument.RoundToTickSize(currentSLPrice));
                                else if (currentSLTicks > 0) SetStopLoss(CalculationMode.Ticks, currentSLTicks);
                                else SetStopLoss(CalculationMode.Ticks, disarmTicks);

                                if (currentTPPrice > 0) SetProfitTarget("MirrorEntry", CalculationMode.Price, Instrument.MasterInstrument.RoundToTickSize(currentTPPrice));
                                else if (currentTPTicks > 0) SetProfitTarget("MirrorEntry", CalculationMode.Ticks, currentTPTicks);
                                else SetProfitTarget("MirrorEntry", CalculationMode.Ticks, disarmTicks);

                                // Re-entry
                                if (o.OrderAction == OrderAction.Buy || o.OrderAction == OrderAction.BuyToCover)
                                {
                                    if (o.OrderType == OrderType.Limit) EnterLongLimit(quantity > 0 ? quantity : o.Quantity, roundedPrice, "MirrorEntry");
                                    else if (o.OrderType == OrderType.StopMarket || o.OrderType == OrderType.StopLimit) EnterLongStopMarket(quantity > 0 ? quantity : o.Quantity, roundedPrice, "MirrorEntry");
                                    else EnterLong(quantity > 0 ? quantity : o.Quantity, "MirrorEntry");
                                }
                                else
                                {
                                    if (o.OrderType == OrderType.Limit) EnterShortLimit(quantity > 0 ? quantity : o.Quantity, roundedPrice, "MirrorEntry");
                                    else if (o.OrderType == OrderType.StopMarket || o.OrderType == OrderType.StopLimit) EnterShortStopMarket(quantity > 0 ? quantity : o.Quantity, roundedPrice, "MirrorEntry");
                                    else EnterShort(quantity > 0 ? quantity : o.Quantity, "MirrorEntry");
                                }
                            }
                        }
                        catch (Exception ex) { Log("[MODIFY] Move error: " + ex.Message); }
                    }

                    // 2. Handle SL/TP change for PENDING orders (if not already moved)
                    if (!pendingModified && Position.MarketPosition == MarketPosition.Flat && (!slPreserve || !tpPreserve))
                    {
                        Log("[MODIFY] SL/TP change for pending order. Attempting Re-place for bracket update...");
                        Order o = Account.Orders.FirstOrDefault(x => 
                            (x.OrderState == OrderState.Working || x.OrderState == OrderState.Accepted)
                            && x.Instrument != null && SymbolMatches(x.Instrument.MasterInstrument.Name)
                            && (x.Name == "MirrorEntry" || x.Name.Contains("Limit") || x.Name.Contains("Stop")));

                        if (o != null)
                        {
                            pendingModified = true;
                            double currentPriceForOrder = (o.OrderType == OrderType.Limit || o.OrderType == OrderType.StopLimit) ? o.LimitPrice : o.StopPrice;
                            if (currentPriceForOrder == 0) currentPriceForOrder = o.StopPrice;

                            if (!slPreserve) currentSLTicks = slTicks;
                            if (!tpPreserve) currentTPTicks = tpTicks;

                            CancelOrder(o);
                            
                            if (absSL > 0) SetStopLoss(CalculationMode.Price, Instrument.MasterInstrument.RoundToTickSize(absSL));
                            else if (currentSLTicks > 0) SetStopLoss(CalculationMode.Ticks, currentSLTicks);
                            else SetStopLoss(CalculationMode.Ticks, disarmTicks);

                            if (absTP > 0) SetProfitTarget("MirrorEntry", CalculationMode.Price, Instrument.MasterInstrument.RoundToTickSize(absTP));
                            else if (currentTPTicks > 0) SetProfitTarget("MirrorEntry", CalculationMode.Ticks, currentTPTicks);
                            else SetProfitTarget("MirrorEntry", CalculationMode.Ticks, disarmTicks);

                            if (o.OrderAction == OrderAction.Buy || o.OrderAction == OrderAction.BuyToCover)
                                EnterLongLimit(o.Quantity, currentPriceForOrder, "MirrorEntry");
                            else
                                EnterShortLimit(o.Quantity, currentPriceForOrder, "MirrorEntry");
                        }
                    }

                    // 3. Handle SL/TP change for POSITION (Normal flow)
                    if (!pendingModified)
                    {
                        // SL
                        if (!slPreserve)
                        {
                            if (absSL > 0)
                            {
                                SetStopLoss(CalculationMode.Price, Instrument.MasterInstrument.RoundToTickSize(absSL));
                                currentSLPrice = absSL;
                                Log("[MODIFY] SL Price updated to " + absSL);
                            }
                            else if (slTicks > 0)
                            {
                                SetStopLoss(CalculationMode.Ticks, slTicks);
                                currentSLTicks = slTicks;
                                currentSLPrice = 0;
                                Log("[MODIFY] SL updated to " + slTicks + " ticks");
                            }
                            else if (slRemove)
                            {
                                SetStopLoss(CalculationMode.Ticks, disarmTicks);
                                currentSLTicks = 0;
                                currentSLPrice = 0;
                                Log("[MODIFY] SL disarmed (" + disarmTicks + " ticks)");
                            }
                        }
                        else { Log("[MODIFY] SL preserved"); }

                        // TP
                        if (!tpPreserve)
                        {
                            if (absTP > 0)
                            {
                                SetProfitTarget("MirrorEntry", CalculationMode.Price, Instrument.MasterInstrument.RoundToTickSize(absTP));
                                currentTPPrice = absTP;
                                Log("[MODIFY] TP Price updated to " + absTP);
                            }
                            else if (tpTicks > 0)
                            {
                                SetProfitTarget("MirrorEntry", CalculationMode.Ticks, tpTicks);
                                currentTPTicks = tpTicks;
                                currentTPPrice = 0;
                                Log("[MODIFY] TP updated to " + tpTicks + " ticks");
                            }
                            else if (tpRemove)
                            {
                                SetProfitTarget("MirrorEntry", CalculationMode.Ticks, disarmTicks);
                                currentTPTicks = 0;
                                currentTPPrice = 0;
                                Log("[MODIFY] TP disarmed (" + disarmTicks + " ticks)");
                            }
                        }
                        else { Log("[MODIFY] TP preserved"); }
                    }
                    break;

                // ── CLOSE / FLAT / CANCEL ────────────────────────────────────
                case "CANCEL":
                    Log(string.Format("[EXEC] CANCEL - Scanning for orders to cancel..."));
                    CancelAllOrphanOrders("[CANCEL]");
                    break;

                case "CLOSE":
                case "FLAT":
                    // Si es un FLAT o un CLOSE de toda la posición, alejamos SL/TP
                    bool isFullClose = (action == "FLAT") || (quantity <= 0) || (quantity >= Position.Quantity);

                    if (isFullClose)
                    {
                        try
                        {
                            SetStopLoss(CalculationMode.Ticks, 99999);
                            SetProfitTarget("MirrorEntry", CalculationMode.Ticks, 99999);
                        }
                        catch { }
                    }

                    // Cerrar posición
                    if (Position.MarketPosition == MarketPosition.Long)
                    {
                        if (quantity > 0 && quantity < Position.Quantity)
                            ExitLong(quantity, "MirrorExit", "MirrorEntry");
                        else
                            ExitLong("MirrorExit", "MirrorEntry");
                    }
                    else if (Position.MarketPosition == MarketPosition.Short)
                    {
                        if (quantity > 0 && quantity < Position.Quantity)
                            ExitShort(quantity, "MirrorExit", "MirrorEntry");
                        else
                            ExitShort("MirrorExit", "MirrorEntry");
                    }

                    if (isFullClose)
                    {
                        CancelAllOrphanOrders("[CLOSE]");
                        currentSLTicks = 0;
                        currentTPTicks = 0;
                        Log("[CLOSE] Position closed fully.");
                    }
                    else
                    {
                        Log(string.Format("[CLOSE] Partial closure executed: Qty={0}", quantity));
                    }
                    break;
            }
        }

        // ============================================================
        //  OnPositionUpdate  –  v4.2: cierre MANUAL / SL hit / TP hit
        //  Cuando la posición queda Flat por cualquier motivo,
        //  cancelamos todas las órdenes working huérfanas.
        // ============================================================
        protected override void OnPositionUpdate(Position position, double averagePrice,
                                                  int quantity, MarketPosition marketPosition)
        {
            if (position.Instrument.FullName != Instrument.FullName) return;
            if (marketPosition != MarketPosition.Flat) return;

            Log("[POSUPDATE] Position went FLAT — scanning for orphan orders...");
            CancelAllOrphanOrders("[POSUPDATE]");
            currentSLTicks = 0;
            currentTPTicks = 0;
        }

        // ── Helper compartido: cancela todas las órdenes Working/Accepted ──
        private void CancelAllOrphanOrders(string tag)
        {
            try
            {
                var orphans = Account.Orders
                    .Where(o => o.Instrument != null
                             && SymbolMatches(o.Instrument.MasterInstrument.Name)
                             && (o.OrderState == OrderState.Working
                              || o.OrderState == OrderState.Accepted))
                    .ToArray();

                foreach (var o in orphans)
                {
                    CancelOrder(o);
                    Log(string.Format("{0} Cancelled orphan: {1} @ Limit={2} Stop={3}",
                        tag, o.Name, o.LimitPrice, o.StopPrice));
                }

                if (orphans.Length == 0)
                    Log(tag + " No orphan orders found.");
            }
            catch (Exception ex)
            {
                Log(tag + " Cancel orphan error: " + ex.Message);
            }
        }

        // ============================================================
        //  TURBOSYNC: Export posición + SLPrice + TPPrice reales
        // ============================================================
        private void ExportPositions()
        {
            try
            {
                double currentSL = 0;
                double currentTP = 0;

                try
                {
                    var workingOrders = Account.Orders
                        .Where(o => o.Instrument != null
                                 && o.Instrument.FullName == Instrument.FullName
                                 && o.OrderState == OrderState.Working)
                        .ToArray();

                    foreach (var o in workingOrders)
                    {
                        string nameLower = (o.Name ?? "").ToLower();
                        if (nameLower.Contains("stop loss"))
                            currentSL = o.StopPrice > 0 ? o.StopPrice : o.LimitPrice;
                        if (nameLower.Contains("profit target"))
                            currentTP = o.LimitPrice > 0 ? o.LimitPrice : o.StopPrice;
                    }
                }
                catch { }

                string posStr = "Flat";
                if (Position.MarketPosition == MarketPosition.Long)  posStr = "Long";
                if (Position.MarketPosition == MarketPosition.Short) posStr = "Short";

                double unrealized = 0;
                try { unrealized = Position.GetUnrealizedProfitLoss(PerformanceUnit.Currency, Close[0]); } catch {}

                var sb = new StringBuilder();
                sb.AppendLine("Symbol,MarketPosition,Quantity,AveragePrice,UnrealizedPnL,SLPrice,TPPrice,Timestamp");
                sb.AppendLine(string.Format(
                    System.Globalization.CultureInfo.InvariantCulture,
                    "{0},{1},{2},{3},{4},{5},{6},{7}",
                    Instrument.FullName,
                    posStr,
                    Position.Quantity,
                    Position.AveragePrice,
                    unrealized,
                    currentSL,
                    currentTP,
                    DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss.fff")
                ));

                File.WriteAllText(positionsFile + ".tmp", sb.ToString());
                File.Copy(positionsFile + ".tmp", positionsFile, true);
            }
            catch { }
        }

        private void ExportOHLCV()
        {
            try
            {
                string safe = Instrument.FullName.Replace("=F","").Replace("-","").Replace(" ","");
                string file = Path.Combine(ExchangeDir, "data_" + safe + ".csv");
                var sb = new StringBuilder();
                sb.AppendLine("Time,Open,High,Low,Close,Volume");
                int look = Math.Min(CurrentBar, 50);
                for (int i = look; i >= 0; i--)
                {
                    sb.AppendLine(string.Format(
                        System.Globalization.CultureInfo.InvariantCulture,
                        "{0},{1},{2},{3},{4},{5}",
                        Time[i].ToString("yyyy-MM-dd HH:mm:ss"),
                        Open[i], High[i], Low[i], Close[i], Volume[i]
                    ));
                }
                File.WriteAllText(file + ".tmp", sb.ToString());
                File.Copy(file + ".tmp", file, true);
            }
            catch { }
        }

        private void ExportAccount()
        {
            try
            {
                double cash = Account.Get(AccountItem.CashValue, Currency.UsDollar);
                var sb = new StringBuilder();
                sb.AppendLine("AccountName,CashValue,BuyingPower,Equity,RealizedPnL,UnrealizedPnL,Timestamp");
                sb.AppendLine(string.Format(
                    System.Globalization.CultureInfo.InvariantCulture,
                    "{0},{1},{2},{3},{4},{5},{6}",
                    Account.Name,
                    cash,
                    Account.Get(AccountItem.BuyingPower, Currency.UsDollar),
                    cash + Account.Get(AccountItem.GrossRealizedProfitLoss, Currency.UsDollar),
                    Account.Get(AccountItem.RealizedProfitLoss, Currency.UsDollar),
                    Account.Get(AccountItem.UnrealizedProfitLoss, Currency.UsDollar),
                    DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss")
                ));
                File.WriteAllText(accountFile + ".tmp", sb.ToString());
                File.Copy(accountFile + ".tmp", accountFile, true);
            }
            catch { }
        }

        private void ExportDOM_Locked()
        {
            try
            {
                var sb = new StringBuilder();
                sb.AppendLine("Symbol,Type,Price,Volume");
                int bCount = 0;
                foreach (var kv in bidBook)
                {
                    if (bCount >= DomDepth) break;
                    sb.AppendLine(string.Format(
                        System.Globalization.CultureInfo.InvariantCulture,
                        "{0},BID,{1},{2}", Instrument.FullName, kv.Key, kv.Value));
                    bCount++;
                }
                int aCount = 0;
                foreach (var kv in askBook)
                {
                    if (aCount >= DomDepth) break;
                    sb.AppendLine(string.Format(
                        System.Globalization.CultureInfo.InvariantCulture,
                        "{0},ASK,{1},{2}", Instrument.FullName, kv.Key, kv.Value));
                    aCount++;
                }
                File.WriteAllText(domFile + ".tmp", sb.ToString());
                File.Copy(domFile + ".tmp", domFile, true);
            }
            catch { }
        }

        private void Log(string msg)
        {
            try
            {
                File.AppendAllText(connectorLog,
                    DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss.fff") + " | " + msg + Environment.NewLine);
                Print("[QuantumGAN] " + msg);
            }
            catch { }
        }

        protected override void OnMarketDepth(MarketDepthEventArgs e)
        {
            lock (domLock)
            {
                bool isBid = (e.MarketDataType == MarketDataType.Bid);
                var book   = isBid ? bidBook : askBook;
                if (e.Operation == Operation.Add || e.Operation == Operation.Update)
                    { if (e.Price > 0) book[e.Price] = e.Volume; }
                else if (e.Operation == Operation.Remove)
                    { if (e.Price > 0) book.Remove(e.Price); }
                domDirty = true;
            }
        }
    }
}