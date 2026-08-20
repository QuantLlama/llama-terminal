/**
 * @jest-environment jsdom
 */
import React from 'react';
import { render } from '@testing-library/react';
import fs from 'fs';
import path from 'path';

// Load the component source into the global scope
const componentCode = fs.readFileSync(
    path.resolve(__dirname, '../ChartComponent.js'),
    'utf-8'
);

// Setup globals required by the script
global.React = React;
// Mock dependencies loaded via window
global.window.PositionOverlay = () => null;
global.window.BigTradeOverlay = () => null;
global.window.UserDrawingOverlay = () => null;
global.window.CurrentPriceLineOverlay = () => null;
global.window.FourierOverlay = () => null;
global.window.DOMHistogramOverlay = () => null;
global.detectPlatformType = () => 'crypto';
global.getPlatformConfig = () => ({});
global.getTimeframeSeconds = () => 60;
global.getAdjustedRange = () => [];
global.useTradeStream = () => ({ trades: [] });
global.window.DOMHeatmapOverlay = () => null;
global.PriceSmoothingOverlay = () => null;
global.window.getDefaultChartSettings = () => {
    const defaultSettings = {
        indicators: {
            liquidity_heatmap: { enabled: true },
            orderflow: { enabled: false },
            volumeProfile: { params: {} }
        },
        overlays: {
            orderFlow: { enabled: false }
        }
    };
    return new Proxy(defaultSettings, {
        get(target, prop) {
            if (prop === 'indicators') {
                return new Proxy(target.indicators, {
                    get(indTarget, indProp) {
                        return indProp in indTarget ? indTarget[indProp] : { real: {}, cumulative: {} };
                    }
                });
            }
            return prop in target ? target[prop] : {};
        }
    });
};
global.window.ChartSettingsModal = () => null;
global.window.OrderFlowOverlay = () => null;
global.window.LiquidityHeatmapOverlay = () => null;
global.window.PriceChangeIndicator = () => null;
global.window.getUniversalSymbol = (s) => s;
global.window.formatPrice = (p) => p;
global.window.formatTime = (t) => t;
global.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
};
global.window.LightweightCharts = {
    CrosshairMode: { Magnet: 1, Normal: 0 },
    LineStyle: { Solid: 0, Dotted: 1, Dashed: 2, LargeDashed: 3, SparseDotted: 4 },
    PriceScaleMode: { Normal: 0, Logarithmic: 1, Percentage: 2, IndexedTo100: 3 },
    ColorType: { Solid: "solid", VerticalGradient: "gradient" },
    LineType: { Simple: 0, WithSteps: 1 },
    createChart: () => {
        const makeInfiniteProxy = () => {
            const proxyInstance = new Proxy(() => {}, {
                get(target, prop) {
                    if (prop === 'then') return undefined;
                    return makeInfiniteProxy();
                },
                apply(target, thisArg, argumentsList) {
                    return makeInfiniteProxy();
                }
            });
            return proxyInstance;
        };
        const chartInstance = {
            applyOptions: () => {},
            subscribeCrosshairMove: () => {},
            unsubscribeCrosshairMove: () => {},
            timeScale: () => {
                const tsInstance = {
                    subscribeVisibleTimeRangeChange: () => {},
                    unsubscribeVisibleTimeRangeChange: () => {},
                    getVisibleRange: () => ({ from: 0, to: 0 }),
                    setVisibleRange: () => {},
                    fitContent: () => {}
                };
                return new Proxy(tsInstance, {
                    get(t, p) {
                        return p in t ? t[p] : () => makeInfiniteProxy();
                    }
                });
            },
            remove: () => {},
            subscribeClick: () => {},
            unsubscribeClick: () => {}
        };
        return new Proxy(chartInstance, {
            get(target, prop) {
                if (prop in target) {
                    return target[prop];
                }
                if (typeof prop === 'string') {
                    if (prop.startsWith('add') || prop.startsWith('create') || prop === 'priceScale' || prop === 'priceLine') {
                        return () => makeInfiniteProxy();
                    }
                }
                return () => {};
            }
        });
    }
};

eval(componentCode);

// The component doesn't attach to window, it's defined as a const. 
// For testability we can evaluate a module export wrapper or just rely on the test file architecture.
// To expose ChartComponent, we can modify the eval code slightly or append an export.

const exposedCode = componentCode + '\nwindow.ChartComponentTest = ChartComponent;\nwindow.useTradeStream = () => ({ trades: [] });';
eval(exposedCode);
const ChartComponent = window.ChartComponentTest;

describe('ChartComponent', () => {
    beforeEach(() => {
        global.fetch = jest.fn(() =>
            Promise.resolve({
                ok: true,
                json: () => Promise.resolve({
                    indicators: {
                        liquidity_heatmap: { data: [{ time: 1, close: 10 }] }
                    }
                }),
            })
        );
    });

    afterEach(() => {
        jest.clearAllMocks();
    });

    it('fetches heatmap data with limit=10000 on load and limit=200 on localLastCandleTime updates', async () => {
        const { rerender } = render(
            <ChartComponent 
                activeSymbol="BTC/USD"
                activeTimeframe="1m"
                chartSettings={{ indicators: { liquidity_heatmap: { enabled: true }, order_flow: { enabled: false } } }}
                localLastCandleTime={null}
            />
        );

        // Let the useEffect run
        await new Promise(process.nextTick);

        // Verify initial fetch with limit=10000
        expect(global.fetch).toHaveBeenCalledWith(
            expect.stringContaining('limit=10000')
        );

        global.fetch.mockClear();

        // Simulate a candle close update
        rerender(
            <ChartComponent 
                activeSymbol="BTC/USD"
                activeTimeframe="1m"
                chartSettings={{ indicators: { liquidity_heatmap: { enabled: true }, order_flow: { enabled: false } } }}
                localLastCandleTime={Date.now()}
            />
        );

        await new Promise(process.nextTick);

        // Verify subsequent fetch with limit=200
        expect(global.fetch).toHaveBeenCalledWith(
            expect.stringContaining('limit=200')
        );
    });
});
