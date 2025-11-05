# -*- coding: utf-8 -*-
import os, sys, io, time, threading, tempfile, base64, queue, re
import tkinter as tk
from PIL import ImageGrab, Image
import keyboard, pyperclip
from dotenv import load_dotenv
from openai import OpenAI
import pytesseract

# --- Cấu hình ---
if sys.stdout and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

load_dotenv(r"C:\.env")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
LANG = "vie+eng"

# --- Cửa sổ nhỏ có tooltip cuộn ---
class SmallWindow:
    def __init__(self, default_text="", bg="white", fg="red", x=50, y=700, size=15, tooltip_text=""):
        self.root = tk.Toplevel() if tk._default_root else tk.Tk()
        self.root.geometry(f"{size}x{size}+{x}+{y}")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=bg)
        self.label = tk.Label(self.root, text=default_text, bg=bg, fg=fg, font=("Arial", 9))
        self.label.pack(expand=True, fill="both")

        # Tooltip cuộn
        self.tooltip = tk.Toplevel(self.root)
        self.tooltip.withdraw()
        self.tooltip.overrideredirect(True)
        self.tooltip.geometry(f"100x100+{x+20}+{y-110}")

        frame = tk.Frame(self.tooltip)
        frame.pack(expand=True, fill="both")

        self.scroll = tk.Scrollbar(frame, orient="vertical")
        self.text = tk.Text(frame, wrap="word", yscrollcommand=self.scroll.set,
                            bg="lightyellow", font=("Arial", 9), padx=4, pady=4)
        self.scroll.config(command=self.text.yview)
        self.scroll.pack(side="right", fill="y")
        self.text.pack(side="left", expand=True, fill="both")
        self.text.configure(state="disabled")
        self.text.bind("<MouseWheel>", self._on_scroll)
        self.tooltip_visible = False

        # Cho phép di chuyển ô chính
        self.label.bind("<ButtonPress-1>", self.start_move)
        self.label.bind("<B1-Motion>", self.do_move)

    def _on_scroll(self, e): self.text.yview_scroll(int(-1*(e.delta/120)), "units")
    def set_text(self, t): self.label.config(text=t)
    def set_tooltip(self, t):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", t)
        self.text.configure(state="disabled")

    def toggle_tooltip(self):
        if self.tooltip_visible:
            self.tooltip.withdraw()
            self.tooltip_visible = False
        else:
            x = self.root.winfo_x() + 20
            y = self.root.winfo_y() - 110
            self.tooltip.geometry(f"100x100+{x}+{y}")
            self.tooltip.deiconify()
            self.tooltip_visible = True

    def start_move(self, e): self._x, self._y = e.x, e.y
    def do_move(self, e):
        x = self.root.winfo_x() + e.x - self._x
        y = self.root.winfo_y() + e.y - self._y
        self.root.geometry(f"+{x}+{y}")
        if self.tooltip_visible:
            self.tooltip.geometry(f"100x100+{x+20}+{y-110}")

# --- OCR & GPT ---
def ocr_image(path):
    try:
        txt = pytesseract.image_to_string(Image.open(path), lang=LANG)
        print("[DEBUG] OCR:", txt[:100])
        return txt.strip()
    except Exception as e:
        print("[ERROR] OCR:", e)
        return ""

def ask_gpt_text(t):
    try:
        print("[DEBUG] GPT text:", t[:100])
        r = client.responses.create(model="gpt-4.1-mini",
            input=[{"role":"user","content":[{"type":"input_text","text":t}]}])
        out = r.output_text.strip()
        print("[DEBUG] GPT resp:", out[:100])
        return out
    except Exception as e:
        print("[ERROR] GPT:", e)
        return f"Lỗi GPT: {e}"

def ask_gpt_image(p):
    try:
        print("[DEBUG] GPT image:", p)
        with open(p,"rb") as f: b64 = base64.b64encode(f.read()).decode()
        r = client.responses.create(
            model="gpt-4.1-mini",
            input=[{"role":"user","content":[
                {"type":"input_text","text":"Phân tích câu hỏi trắc nghiệm, chú ý kỹ xem câu hỏi chọn câu đúng hay câu sai, chọn đáp án phù hợp (A/B/C/D), trả lời xem đáp án nào là đáp án phù hợp rồi ghi lên trước tiên rồi mới giải thích ngắn gọn."},
                {"type":"input_image","image_url":"data:image/png;base64,"+b64}
            ]}])
        out = r.output_text.strip()
        print("[DEBUG] GPT image resp:", out[:100])
        return out
    except Exception as e:
        print("[ERROR] GPT image:", e)
        return f"Lỗi GPT: {e}"

# --- Capture & Clipboard ---
def capture_full_screen():
    t = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    ImageGrab.grab().save(t.name)
    return t.name

def capture_from_clipboard():
    img = ImageGrab.grabclipboard()
    if isinstance(img, Image.Image):
        t = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        img.save(t.name)
        return t.name
    print("[ERROR] Clipboard trống.")
    return None

def get_clipboard_text():
    keyboard.send("ctrl+c"); time.sleep(0.2)
    return pyperclip.paste().strip()

# --- Task handler ---
def handle_task(mode, q):
    def run():
        q.put(("status","?"))
        print("[DEBUG] Mode:", mode)
        if mode == "image":
            ans = ask_gpt_image(capture_full_screen())
        elif mode == "ocr_clip":
            path = capture_from_clipboard()
            if not path:
                q.put(("tooltip_status","Clipboard trống"))
                q.put(("status","X"))
                return
            ans = ask_gpt_text("Chọn đáp án đúng nhất trước rồi giải thích ngắn gọn:\n"+ocr_image(path))
        elif mode == "text":
            ans = ask_gpt_text("Chọn đáp án đúng nhất trước rồi giải thích ngắn gọn:\n"+get_clipboard_text())
        else:
            ans = "Chế độ không hợp lệ."

        m = re.search(r"\b([A-D])\b", ans)
        letter = m.group(1) if m else ""
        symbol = "✓" if "đúng" in ans.lower() else ("X" if "sai" in ans.lower() else "?")

        q.put(("answer", letter))
        q.put(("tooltip_answer", ans))
        q.put(("status", symbol))
        q.put(("tooltip_status","Hoàn thành"))
        print("[DEBUG] Done:", letter, symbol)
    threading.Thread(target=run, daemon=True).start()

# --- Main ---
def main():
    q = queue.Queue()
    root = tk.Tk(); root.withdraw()
    win_answer = SmallWindow("", "white", "red", 50, 700, 15)
    win_status = SmallWindow("", "white", "blue", 70, 700, 15)

    print("ALT+1 = Toàn màn hình\nALT+2 = Win+Shift+S rồi Alt+2 để OCR\nALT+3 = Copy văn bản\nALT = Bật/tắt chú thích đáp án\nESC = Thoát")

    keyboard.add_hotkey("alt+1", lambda: handle_task("image", q))
    keyboard.add_hotkey("alt+2", lambda: handle_task("ocr_clip", q))
    keyboard.add_hotkey("alt+3", lambda: handle_task("text", q))
    keyboard.add_hotkey("alt", lambda: win_answer.toggle_tooltip())  # chỉ đáp án
    keyboard.add_hotkey("esc", lambda: (win_answer.root.destroy(), win_status.root.destroy(), root.destroy()))

    def loop():
        while not q.empty():
            k,v=q.get_nowait()
            if k=="answer": win_answer.set_text(v)
            elif k=="tooltip_answer": win_answer.set_tooltip(v)
            elif k=="status": win_status.set_text(v)
            elif k=="tooltip_status": win_status.set_tooltip(v)
        win_answer.root.after(100, loop)
    win_answer.root.after(100, loop)
    win_answer.root.mainloop()

if __name__=="__main__":
    main()

