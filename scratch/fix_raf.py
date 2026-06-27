import os
import re

directory = "src/platform/web/components"

for filename in os.listdir(directory):
    if not filename.endswith(".js"): continue
    filepath = os.path.join(directory, filename)
    
    with open(filepath, 'r') as f:
        content = f.read()
        
    orig_content = content
    
    # For BigTradeOverlay.js, DeltaGridOverlay.js, TpoRenderer.js, UserDrawingOverlay.js, DOMHeatmapOverlay.js, DOMHistogramOverlay.js, FootprintRenderer.js
    # Find: `rafId = requestAnimationFrame(render);` or `rafId = requestAnimationFrame(() => {`
    
    content = re.sub(
        r'let rafId\s*=\s*null;\s*const scheduleRender\s*=\s*\(\)\s*=>\s*\{\s*if\s*\(rafId\s*===\s*null\)\s*\{\s*rafId\s*=\s*requestAnimationFrame\(\(\)\s*=>\s*\{\s*rafId\s*=\s*null;\s*([a-zA-Z0-9_]+)\(\);\s*\}\);\s*\}\s*\};',
        r'const scheduleRender = () => { \1(); };',
        content
    )

    content = re.sub(
        r'let rafId\s*=\s*null;\s*const scheduleRender\s*=\s*\(\)\s*=>\s*\{\s*if\s*\(rafId\s*===\s*null\)\s*\{\s*rafId\s*=\s*requestAnimationFrame\(([a-zA-Z0-9_]+)\);\s*\}\s*\};',
        r'const scheduleRender = () => { \1(); };',
        content
    )
    
    content = re.sub(
        r'let fid\s*=\s*null;\s*(const ctx.*?const draw\s*=\s*\(\)\s*=>\s*\{.*?\};\s*)const scheduleRender\s*=\s*\(\)\s*=>\s*\{\s*if\s*\(fid\s*===\s*null\)\s*\{\s*fid\s*=\s*requestAnimationFrame\(\(\)\s*=>\s*\{\s*fid\s*=\s*null;\s*draw\(\);\s*\}\);\s*\}\s*\};',
        r'let fid = null;\n    \1const scheduleRender = () => { draw(); };',
        content,
        flags=re.DOTALL
    )

    # For OrderFlowOverlay
    content = re.sub(
        r'let renderPending\s*=\s*false;\s*const onEventDraw\s*=\s*\(\)\s*=>\s*\{\s*if\s*\(!renderPending\)\s*\{\s*renderPending\s*=\s*true;\s*Promise\.resolve\(\)\.then\(\(\)\s*=>\s*\{\s*draw\(\);\s*renderPending\s*=\s*false;\s*\}\);\s*\}\s*\};',
        r'const onEventDraw = () => { draw(); };',
        content
    )
    
    # For LiquidityHeatmapOverlay
    content = re.sub(
        r'let renderPending\s*=\s*false;\s*const onEventDraw\s*=\s*\(\)\s*=>\s*\{\s*if\s*\(!renderPending\)\s*\{\s*renderPending\s*=\s*true;\s*Promise\.resolve\(\)\.then\(\(\)\s*=>\s*\{\s*draw\(\);\s*renderPending\s*=\s*false;\s*\}\);\s*\}\s*\};',
        r'const onEventDraw = () => { draw(); };',
        content
    )

    # For PositionOverlay
    content = re.sub(
        r'animFrameRef\.current\s*=\s*requestAnimationFrame\(\(\)\s*=>\s*\{\s*if\s*\(isMounted\)\s*draw\(\);\s*\}\);',
        r'if (isMounted) draw();',
        content
    )

    content = re.sub(
        r'animFrameRef\.current\s*=\s*requestAnimationFrame\(\(\)\s*=>\s*\{\s*draw\(\);\s*\}\);',
        r'draw();',
        content
    )
    
    # In VolumeProfileRenderer.js:
    content = re.sub(
        r'this\._rafId\s*=\s*requestAnimationFrame\(this\._drawScheduled\);',
        r'this._drawScheduled();',
        content
    )

    if content != orig_content:
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"Fixed {filename}")

