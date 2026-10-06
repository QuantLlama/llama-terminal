/**
 * @jest-environment jsdom
 */
import React from 'react';
import { render } from '@testing-library/react';
import fs from 'fs';
import path from 'path';

// Load the component source into the global scope (same pattern as the other
// overlay tests: the script attaches itself to window.TpoRenderer).
const componentCode = fs.readFileSync(
    path.resolve(__dirname, '../TpoRenderer.js'),
    'utf-8'
);

global.React = React;
eval(componentCode);

const TpoRenderer = window.TpoRenderer;

// The component drives its canvas from requestAnimationFrame. Owning the clock
// keeps the assertions deterministic instead of timing dependent.
let pendingFrames;
let frameSeq;
const realRequestAnimationFrame = global.requestAnimationFrame;
const realCancelAnimationFrame = global.cancelAnimationFrame;

const flushFrames = (count = 1) => {
    for (let i = 0; i < count; i++) {
        const batch = Array.from(pendingFrames.entries());
        pendingFrames.clear();
        batch.forEach(([, callback]) => callback(16));
    }
};

class ErrorBoundary extends React.Component {
    constructor(props) {
        super(props);
        this.state = { error: null };
    }

    static getDerivedStateFromError(error) {
        return { error };
    }

    componentDidCatch(error) {
        this.props.onError(error);
    }

    render() {
        return this.state.error ? null : this.props.children;
    }
}

const candles = (base) => ([
    { time: base, open: 100, high: 100.5, low: 100, close: 100.4 },
    { time: base + 600, open: 100.4, high: 100.7, low: 100.1, close: 100.6 }
]);

const tpoSettings = {
    indicators: { tpo: { sessionPeriod: '1d', blockPeriod: 30, rowSize: 0.5 } }
};

describe('TpoRenderer', () => {
    let ctx;
    let chart;
    let series;
    let logicalRange;

    beforeEach(() => {
        pendingFrames = new Map();
        frameSeq = 0;
        global.requestAnimationFrame = (callback) => {
            frameSeq += 1;
            pendingFrames.set(frameSeq, callback);
            return frameSeq;
        };
        global.cancelAnimationFrame = (id) => {
            pendingFrames.delete(id);
        };

        ctx = {
            clearRect: jest.fn(),
            setTransform: jest.fn(),
            fillRect: jest.fn(),
            fillText: jest.fn(),
            beginPath: jest.fn(),
            moveTo: jest.fn(),
            lineTo: jest.fn(),
            stroke: jest.fn(),
            save: jest.fn(),
            restore: jest.fn(),
            fillStyle: '',
            strokeStyle: '',
            lineWidth: 1,
            font: '',
            textBaseline: '',
            textAlign: '',
            globalAlpha: 1
        };

        HTMLCanvasElement.prototype.getContext = jest.fn(() => ctx);
        HTMLCanvasElement.prototype.getBoundingClientRect = jest.fn(() => ({
            width: 800, height: 400, top: 0, left: 0, right: 800, bottom: 400, x: 0, y: 0,
            toJSON: () => ({})
        }));

        logicalRange = { from: 0, to: 50 };
        chart = {
            timeScale: () => ({
                getVisibleLogicalRange: () => logicalRange,
                timeToCoordinate: () => 100,
                subscribeVisibleLogicalRangeChange: jest.fn(),
                unsubscribeVisibleLogicalRangeChange: jest.fn(),
                subscribeVisibleTimeRangeChange: jest.fn(),
                unsubscribeVisibleTimeRangeChange: jest.fn()
            }),
            subscribeCrosshairMove: jest.fn(),
            unsubscribeCrosshairMove: jest.fn()
        };
        series = { priceToCoordinate: () => 200 };
    });

    afterEach(() => {
        global.requestAnimationFrame = realRequestAnimationFrame;
        global.cancelAnimationFrame = realCancelAnimationFrame;
    });

    it('keeps drawing when the profile set changes and the effect re-runs', () => {
        const errors = [];
        const onError = (error) => errors.push(error);
        const props = { chart, series, settings: tpoSettings, visible: true };

        const { container, rerender } = render(
            <ErrorBoundary onError={onError}>
                <TpoRenderer {...props} data={candles(1700000000)} />
            </ErrorBoundary>
        );
        flushFrames(2);

        // A new data array recomputes `profiles`, which re-runs the drawing
        // effect and therefore executes the previous effect cleanup first.
        rerender(
            <ErrorBoundary onError={onError}>
                <TpoRenderer {...props} data={candles(1700000000)} />
            </ErrorBoundary>
        );
        flushFrames(2);

        expect(errors.map((error) => error.message)).toEqual([]);
        expect(container.querySelector('canvas')).not.toBeNull();
        expect(ctx.fillRect).toHaveBeenCalled();
    });

    it('stops its animation loop when it unmounts', () => {
        series = { priceToCoordinate: () => null };
        logicalRange = null;

        const { unmount } = render(
            <TpoRenderer
                chart={chart}
                series={series}
                data={candles(1700000000)}
                settings={tpoSettings}
                visible={false}
            />
        );
        flushFrames(3);

        const framesWhileMounted = ctx.clearRect.mock.calls.length;
        expect(framesWhileMounted).toBeGreaterThan(1);

        unmount();
        flushFrames(3);

        expect(pendingFrames.size).toBe(0);
        expect(ctx.clearRect.mock.calls.length).toBe(framesWhileMounted);
    });
});
