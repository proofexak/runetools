"""
Hover over the TOP-LEFT and BOTTOM-RIGHT of a clear patch of game world
(avoid minimap, inventory, chat, and other UI panels).
A 400-600px wide central area works well.
"""
import pyautogui

input("Hover over the TOP-LEFT of the movement region, then press Enter...")
x1, y1 = pyautogui.position()

input("Hover over the BOTTOM-RIGHT of the movement region, then press Enter...")
x2, y2 = pyautogui.position()

print(f"\nPaste this into bot.py:")
print(f"MOVEMENT_REGION = ({x1}, {y1}, {x2 - x1}, {y2 - y1})")