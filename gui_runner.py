# gui_runner.py
import tkinter as tk
from tkinter import filedialog, messagebox
import Holdemluck

def run_analysis():
    folder_path = filedialog.askdirectory(title="핸드히스토리 폴더 선택")
    if not folder_path:
        return

    try:
        Holdemluck.main(folder_path)
        messagebox.showinfo("완료", "핸드 분석이 완료되었습니다!")
    except Exception as e:
        messagebox.showerror("오류", str(e))

root = tk.Tk()
root.title("GGpoker MTT Luck 분석기")
root.geometry("300x120")

label = tk.Label(root, text="핸드히스토리 폴더를 선택하세요.")
label.pack(pady=10)

button = tk.Button(root, text="분석 시작", command=run_analysis)
button.pack(pady=5)

root.mainloop()
