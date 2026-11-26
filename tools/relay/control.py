"""Small local control window; closing it does not stop the background queue."""
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, ttk

from relay import Relay, lock
from setup_local import setup

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


class Panel:
    def __init__(self):
        self.config = setup()
        self.window = tk.Tk()
        self.window.title("应许之路 · 本地 AI 调度")
        self.window.geometry("860x530")
        self.window.minsize(680, 420)
        self.window.configure(bg="#eee8dc")
        tk.Label(self.window, text="本地 AI 工作队列", font=("Microsoft YaHei", 20, "bold"),
                 bg="#eee8dc").pack(anchor="w", padx=22, pady=(20, 4))
        tk.Label(self.window, text="进度保存在本机。窗口关闭后队列继续；电脑休眠时无法工作。",
                 bg="#eee8dc").pack(anchor="w", padx=22)
        bar = ttk.Frame(self.window)
        bar.pack(fill="x", padx=22, pady=18)
        for title, callback in (("启动 / 继续", self.start), ("停止并保存", self.stop),
                                ("检查接入", self.doctor), ("登录 Antigravity", self.login)):
            ttk.Button(bar, text=title, command=callback).pack(side="left", padx=(0, 8))
        self.tree = ttk.Treeview(self.window, columns=("task", "status", "attempts", "reason"), show="headings")
        for key, title, width in (("task", "任务", 70), ("status", "状态", 90),
                                  ("attempts", "已尝试", 55), ("reason", "说明", 450)):
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width)
        self.tree.pack(fill="both", expand=True, padx=22)
        self.notice = tk.StringVar()
        tk.Label(self.window, textvariable=self.notice, bg="#eee8dc", anchor="w", wraplength=800).pack(fill="x", padx=22, pady=12)
        self.refresh()

    def command(self, action):
        return [sys.executable, str(HERE / "relay.py"), "--root", str(ROOT), "--config", str(self.config), action]

    def start(self):
        try:
            with lock(ROOT / ".relay/runner.lock"), lock(ROOT / ".relay/worker.lock"):
                pass
        except OSError:
            self.notice.set("队列或执行者仍在运行，无需重复启动。")
            return
        (ROOT / ".relay/STOP").unlink(missing_ok=True)
        with (ROOT / ".relay/runner.log").open("ab") as log:
            subprocess.Popen(self.command("run") + ["--watch"], cwd=ROOT, stdout=log, stderr=log,
                             stdin=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        self.notice.set("已启动后台队列。需查看实际任务状态；未登录或缺少执行端时会等待。")

    def stop(self):
        (ROOT / ".relay/STOP").write_text("User requested stop", encoding="utf-8")
        self.notice.set("已请求停止。执行进程将终止，修改与检查点会保留。")

    def doctor(self):
        result = subprocess.run(self.command("doctor"), capture_output=True, text=True, encoding="utf-8",
                                creationflags=subprocess.CREATE_NO_WINDOW)
        messagebox.showinfo("接入检查（未调用模型）", result.stdout or result.stderr)

    def login(self):
        config = json.loads(self.config.read_text(encoding="utf-8"))
        exe = config["providers"]["antigravity"]["command"][0].replace("{root}", str(ROOT))
        if not Path(exe).is_file():
            messagebox.showerror("尚未安装 CLI", "Antigravity 应用与 agy 命令行是两个入口，请先按 README 安装 CLI。")
            return
        # User explicitly clicks an interactive login button; no credentials are read by us.
        subprocess.Popen([exe], cwd=ROOT, creationflags=subprocess.CREATE_NEW_CONSOLE)
        self.notice.set("请在新窗口中完成 Google 登录和项目设置，完成后关闭登录窗口再启动队列。")

    def refresh(self):
        relay = Relay(ROOT, self.config)
        try:
            rows = relay.status()
            self.tree.delete(*self.tree.get_children())
            names = {"ready": "待执行", "waiting": "等待接入/额度", "running": "执行中",
                     "review": "待评审", "done": "已完成", "blocked": "需处理", "interrupted": "已中断"}
            for row in rows:
                self.tree.insert("", "end", values=(row["id"], names.get(row["status"], row["status"]),
                                                    row["attempts"], row["reason"]))
        finally:
            relay.db.close()
        self.window.after(2000, self.refresh)


if __name__ == "__main__":
    Panel().window.mainloop()
