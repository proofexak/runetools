"""
Hover your mouse over the TOP-LEFT and BOTTOM-RIGHT corners of your inventory
and press Enter each time. The script prints the INVENTORY_REGION tuple to paste
into bot.py.
"""
import pyautogui

input("Hover over the TOP-LEFT corner of the inventory, then press Enter...")
x1, y1 = pyautogui.position()
print(f"  Top-left: ({x1}, {y1})")

input("Hover over the BOTTOM-RIGHT corner of the inventory, then press Enter...")
x2, y2 = pyautogui.position()
print(f"  Bottom-right: ({x2}, {y2})")

left   = x1
top    = y1
width  = x2 - x1
height = y2 - y1

print(f"\nPaste this into bot.py:")
print(f"INVENTORY_REGION = ({left}, {top}, {width}, {height})")