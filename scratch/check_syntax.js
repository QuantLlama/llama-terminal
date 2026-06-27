const fs = require('fs');
const files = [
    "src/platform/web/components/BigTradeOverlay.js",
    "src/platform/web/components/DOMHeatmapOverlay.js",
    "src/platform/web/components/DOMHistogramOverlay.js",
    "src/platform/web/components/DeltaGridOverlay.js",
    "src/platform/web/components/LiquidityHeatmapOverlay.js",
    "src/platform/web/components/PositionOverlay.js",
    "src/platform/web/components/TpoRenderer.js",
    "src/platform/web/components/UserDrawingOverlay.js",
    "src/platform/web/components/OrderFlowOverlay.js",
    "src/platform/web/components/FootprintRenderer.js",
    "src/platform/web/components/VolumeProfileRenderer.js"
];

let failed = false;
files.forEach(f => {
    try {
        const code = fs.readFileSync(f, 'utf8');
        // Simple heuristic: babel would throw SyntaxError. 
        // We can use the 'acorn' parser if available, or just rely on new Function.
        // wait, `new Function(code)` works for validating syntax in JS!
        // but react/jsx isn't valid JS.
        // Is it using JSX? Yes, it uses React.createElement usually, but some use JSX.
        // If it uses pure JS, new Function works. Let's just grep for missing brackets maybe?
        
    } catch(e) {}
});
