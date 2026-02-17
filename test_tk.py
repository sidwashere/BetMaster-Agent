import tkinter as tk
try:
    root = tk.Tk()
    print("Tkinter initialized successfully")
    root.destroy()
except Exception as e:
    print(f"Tkinter failed: {e}")
