from PIL import Image, ImageDraw, ImageOps
import os

def create_icon_with_overlay(base_path, output_path, overlay_type=None):
    # Open base image
    base = Image.open(base_path).convert("RGBA")
    
    # Create final image with the same size
    size = base.size
    final = base.copy()
    draw = ImageDraw.Draw(final)
    
    if overlay_type == 'browser':
        # Draw a blue globe-like circle at bottom right
        # Circle size ~1/3 of base
        r = size[0] // 4
        center = (size[0] - r - 10, size[1] - r - 10)
        # Blue circle
        draw.ellipse([center[0]-r, center[1]-r, center[0]+r, center[1]+r], fill=(0, 122, 255, 255), outline=(255, 255, 255, 255), width=5)
        # Simple globe lines (white)
        draw.line([center[0]-r+10, center[1], center[0]+r-10, center[1]], fill=(255, 255, 255, 255), width=3)
        draw.line([center[0], center[1]-r+10, center[0], center[1]+r-10], fill=(255, 255, 255, 255), width=3)
        draw.ellipse([center[0]-r//2, center[1]-r, center[0]+r//2, center[1]+r], outline=(255, 255, 255, 255), width=2)

    elif overlay_type == 'trainer':
        # Draw a gold/orange brain-like or chart shape at bottom right
        r = size[0] // 4
        center = (size[0] - r - 10, size[1] - r - 10)
        # Gold circle
        draw.ellipse([center[0]-r, center[1]-r, center[0]+r, center[1]+r], fill=(255, 170, 0, 255), outline=(255, 255, 255, 255), width=5)
        # Simple chart UP lines (white)
        draw.line([center[0]-r+15, center[1]+r-15, center[0]-5, center[1], center[0]+r-15, center[1]-r+15], fill=(255, 255, 255, 255), width=5)
        # Arrow head
        draw.polygon([center[0]+r-15, center[1]-r+15, center[0]+r-15, center[1]-r+30, center[0]+r-30, center[1]-r+15], fill=(255, 255, 255, 255))

    # Save as ICO with all standard sizes
    # Windows likes: 16, 32, 48, 64, 128, 256
    icon_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    final.save(output_path, format='ICO', sizes=icon_sizes)
    print(f"Created {output_path}")

if __name__ == '__main__':
    base_img = 'images/QuantumLLama.png'
    # 1. Main Terminal Icon (High Quality)
    create_icon_with_overlay(base_img, 'images/QuantumLLama.ico')
    # 2. Browser Icon (Blue Overlay)
    create_icon_with_overlay(base_img, 'images/QuantumLLama_Browser.ico', overlay_type='browser')
    # 3. Trainer Icon (Gold Overlay)
    create_icon_with_overlay(base_img, 'images/QuantumLLama_Trainer.ico', overlay_type='trainer')
