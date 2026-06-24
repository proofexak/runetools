"""
Hover your mouse over the TOP-LEFT and BOTTOM-RIGHT corners of the OSRS
chat box, pressing Enter each time.
"""
import pyautogui

input("Hover over the TOP-LEFT corner of the chat box, then press Enter...")
x1, y1 = pyautogui.position()

input("Hover over the BOTTOM-RIGHT corner of the chat box, then press Enter...")
x2, y2 = pyautogui.position()

print(f"\nPaste this into bot.py:")
print(f"CHAT_REGION = ({x1}, {y1}, {x2 - x1}, {y2 - y1})")