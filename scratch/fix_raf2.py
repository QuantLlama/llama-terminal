import os
import re

def fix_file(filepath, replacements):
    with open(filepath, 'r') as f:
        content = f.read()
    orig = content
    for pattern, repl in replacements:
        content = re.sub(pattern, repl, content, flags=re.DOTALL)
    if content != orig:
        with open(filepath, 'w') as f:
            f.write(content)
        print("Fixed", filepath)

fix_file("src/platform/web/components/BigTradeOverlay.js", [
    (r'let rafId\s*=\s*null;\s*const scheduleRender\s*=\s*\(\)\s*=>\s*\{\s*if\s*\(rafId\s*===\s*null\)\s*\{\s*rafId\s*=\s*requestAnimationFrame\(render\);\s*\}\s*\};', 
     r'const scheduleRender = () => { render(); };')
])

fix_file("src/platform/web/components/DeltaGridOverlay.js", [
    (r'let rafId\s*=\s*null;\s*const scheduleRender\s*=\s*\(\)\s*=>\s*\{\s*if\s*\(rafId\s*===\s*null\)\s*\{\s*rafId\s*=\s*requestAnimationFrame\(render\);\s*\}\s*\};', 
     r'const scheduleRender = () => { render(); };')
])

fix_file("src/platform/web/components/OrderFlowOverlay.js", [
    (r'let renderPending = false;\s*const onEventDraw = \(\) => \{\s*if \(!renderPending\) \{\s*renderPending = true;\s*Promise\.resolve\(\)\.then\(\(\) => \{\s*draw\(\);\s*renderPending = false;\s*\}\);\s*\}\s*\};',
     r'const onEventDraw = () => { draw(); };')
])

fix_file("src/platform/web/components/PositionOverlay.js", [
    (r'animFrameRef\.current = requestAnimationFrame\(\(\) => \{\s*if \(isMounted\) draw\(\);\s*\}\);', r'if (isMounted) draw();'),
    (r'animFrameRef\.current = requestAnimationFrame\(\(\) => \{\s*draw\(\);\s*\}\);', r'draw();')
])

fix_file("src/platform/web/components/FootprintRenderer.js", [
    (r'this\._rafId = requestAnimationFrame\(\(\) => \{\s*this\._rafId = null;\s*this\._drawFrame\(\);\s*\}\);', r'this._drawFrame();')
])

fix_file("src/platform/web/components/DOMHeatmapOverlay.js", [
    (r'let animationId = null;\s*const onEventDraw = \(\) => \{\s*if \(!animationId\) \{\s*animationId = requestAnimationFrame\(draw\);\s*\}\s*\};', r'const onEventDraw = () => { draw(); };'),
    (r'if \(!rafPending\) \{\s*rafPending = requestAnimationFrame\(\(\) => \{\s*rafPending = null;\s*onEventDraw\(\);\s*\}\);\s*\}', r'onEventDraw();')
])

