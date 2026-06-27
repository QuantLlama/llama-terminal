import os
import re

directory = "src/platform/web/components"
overlays = [
    "BigTradeOverlay.js",
    "DOMHeatmapOverlay.js",
    "DOMHistogramOverlay.js",
    "DeltaGridOverlay.js",
    "FootprintRenderer.js",
    "LiquidityHeatmapOverlay.js",
    "OrderFlowOverlay.js",
    "PositionOverlay.js",
    "TpoRenderer.js",
    "UserDrawingOverlay.js",
    "VolumeProfileRenderer.js"
]

throttle_code = """
        let _isDrawing = false;
        let _needsRedraw = false;
        const scheduleRender = () => {
            if (_isDrawing) {
                _needsRedraw = true;
                return;
            }
            _isDrawing = true;
            try { %DRAW_CALL%; } catch(e) {}
            requestAnimationFrame(() => {
                _isDrawing = false;
                if (_needsRedraw) {
                    _needsRedraw = false;
                    scheduleRender();
                }
            });
        };
        
        let _lastPriceCoord = null;
        let _lastTimeCoord = null;
        let _monitorRaf = null;
        const monitorScale = () => {
            if (series) {
                try {
                    const pc = series.priceToCoordinate(0) || series.priceToCoordinate(100);
                    const logicalRange = chart.timeScale().getVisibleLogicalRange();
                    const tc = logicalRange ? logicalRange.from : null;
                    if (pc !== _lastPriceCoord || tc !== _lastTimeCoord) {
                        _lastPriceCoord = pc;
                        _lastTimeCoord = tc;
                        scheduleRender();
                    }
                } catch(e) {}
            }
            _monitorRaf = requestAnimationFrame(monitorScale);
        };
        _monitorRaf = requestAnimationFrame(monitorScale);
"""

# We'll use a safer AST or regex approach to replace the existing `scheduleRender` or `onEventDraw` methods.
# Actually, since I manually replaced them, they look like:
# const scheduleRender = () => { render(); };
# or const scheduleRender = () => { draw(); };
# or const onEventDraw = () => { draw(); };

def process_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()
    orig = content

    # Replace `const scheduleRender = () => { render(); };`
    match = re.search(r'const scheduleRender\s*=\s*\(\)\s*=>\s*\{\s*(render\(\)|draw\(\)|updatePos\(\)|this\._drawFrame\(\)|this\._drawScheduled\(\));\s*\};', content)
    if match:
        draw_call = match.group(1)
        # if it's 'this._drawFrame()', we need to make sure `this` is bound or we are inside the class method.
        # VolumeProfileRenderer has `this.scheduleRender = () => { this._drawScheduled(); };` No, wait. I replaced it with `this._drawScheduled();`
        
        replacement = throttle_code.replace('%DRAW_CALL%', draw_call)
        
        # We need to also clear `_monitorRaf` on unmount.
        # Look for `return () => {`
        cleanup_match = re.search(r'return \(\) => \{', content)
        if cleanup_match:
            content = re.sub(
                r'(return \(\) => \{)',
                r'\1\n            if (_monitorRaf) cancelAnimationFrame(_monitorRaf);',
                content,
                count=1
            )
        
        content = content[:match.start()] + replacement + content[match.end():]
        print("Patched", filepath)
        
        with open(filepath, 'w') as f:
            f.write(content)
        return

    # For OrderFlowOverlay / DOMHeatmap / LiquidityHeatmap
    match2 = re.search(r'const onEventDraw\s*=\s*\(\)\s*=>\s*\{\s*([a-zA-Z0-9_]+\(\));\s*\};', content)
    if match2:
        draw_call = match2.group(1)
        replacement = throttle_code.replace('%DRAW_CALL%', draw_call).replace('scheduleRender', 'onEventDraw')
        
        cleanup_match = re.search(r'return \(\) => \{', content)
        if cleanup_match:
            content = re.sub(
                r'(return \(\) => \{)',
                r'\1\n            if (_monitorRaf) cancelAnimationFrame(_monitorRaf);',
                content,
                count=1
            )
            
        content = content[:match2.start()] + replacement + content[match2.end():]
        print("Patched (onEventDraw)", filepath)
        with open(filepath, 'w') as f:
            f.write(content)
        return

    print("Could not match", filepath)

for overlay in overlays:
    process_file(os.path.join(directory, overlay))

