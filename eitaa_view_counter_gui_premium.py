# -*- coding: utf-8 -*-
"""
رابط گرافیکی مدرن شمارشگر بازدید کانال ایتا
-------------------------------------------
این فایل فقط GUI را بازطراحی می‌کند و منطق eitaa_view_counter.py را تغییر نمی‌دهد.

پیش‌نیاز:
    pip install playwright
    playwright install chromium

نکته:
    فایل eitaa_view_counter.py باید کنار این فایل باشد.
"""

import csv
import queue
import re
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import eitaa_view_counter as core


class EitaaGUI(tk.Tk):
    BG = "#f4f6f8"
    CARD = "#ffffff"
    TEXT = "#17212b"
    MUTED = "#68737d"
    BORDER = "#dfe4e8"
    ACCENT = "#2f80ed"
    ACCENT_DARK = "#2169c7"
    SUCCESS = "#1f9d68"
    WARNING = "#d98a00"
    DANGER = "#d64545"

    def __init__(self):
        super().__init__()
        self.title("شمارشگر بازدید کانال ایتا")
        self.geometry("1040x820")
        self.minsize(940, 700)
        self.configure(bg=self.BG)

        self.log_queue = queue.Queue()
        self.confirm_event = threading.Event()
        self.worker_running = False
        self.session = None

        self.total_var = tk.StringVar(value="0")
        self.views_var = tk.StringVar(value="0")
        self.avg_var = tk.StringVar(value="0")
        self.warning_var = tk.StringVar(value="0")
        self.status_var = tk.StringVar(value="آماده")
        self.status_detail_var = tk.StringVar(value="آماده")

        self._setup_style()
        self._build_ui()
        self._refresh_metrics([])
        self.after(120, self._poll_log_queue)

    # ---------------------------------------------------------------
    # ظاهر
    # ---------------------------------------------------------------
    def _setup_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TFrame", background=self.BG)
        style.configure("Card.TFrame", background=self.CARD)
        style.configure("TLabel", background=self.BG, foreground=self.TEXT,
                        font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=self.BG, foreground=self.MUTED,
                        font=("Segoe UI", 9))
        style.configure("Title.TLabel", background=self.BG, foreground=self.TEXT,
                        font=("Segoe UI", 21, "bold"))
        style.configure("Subtitle.TLabel", background=self.BG, foreground=self.MUTED,
                        font=("Segoe UI", 10))
        style.configure("CardTitle.TLabel", background=self.CARD, foreground=self.MUTED,
                        font=("Segoe UI", 9))
        style.configure("Metric.TLabel", background=self.CARD, foreground=self.TEXT,
                        font=("Segoe UI", 20, "bold"))
        style.configure("Section.TLabelframe", background=self.CARD,
                        foreground=self.TEXT, bordercolor=self.BORDER,
                        lightcolor=self.BORDER, darkcolor=self.BORDER)
        style.configure("Section.TLabelframe.Label", background=self.CARD,
                        foreground=self.TEXT, font=("Segoe UI", 10, "bold"))
        style.configure("TEntry", padding=7)
        style.configure("TButton", padding=(12, 7), font=("Segoe UI", 9, "bold"))
        style.configure("Primary.TButton", background=self.ACCENT, foreground="white",
                        borderwidth=0, padding=(16, 9))
        style.map("Primary.TButton", background=[("active", self.ACCENT_DARK)])
        style.configure("Success.TButton", background=self.SUCCESS, foreground="white",
                        borderwidth=0, padding=(14, 8))
        style.map("Success.TButton", background=[("active", "#177d53")])
        style.configure("Danger.TButton", background=self.DANGER, foreground="white",
                        borderwidth=0, padding=(14, 8))
        style.map("Danger.TButton", background=[("active", "#b93434")])
        style.configure("TCheckbutton", background=self.CARD, foreground=self.TEXT)
        style.configure("TRadiobutton", background=self.CARD, foreground=self.TEXT)
        style.configure("Horizontal.TProgressbar", troughcolor="#e7ebef",
                        background=self.ACCENT, borderwidth=0, thickness=8)

    def _card(self, parent):
        frame = tk.Frame(parent, bg=self.CARD, highlightbackground=self.BORDER,
                         highlightthickness=1, bd=0, padx=0, pady=0)
        return frame

    def _label(self, parent, text, **kw):
        return tk.Label(parent, text=text, bg=self.CARD, fg=self.TEXT,
                        font=("Segoe UI", 9), **kw)

    def _build_ui(self):
        root = tk.Frame(self, bg=self.BG)
        root.pack(fill="both", expand=True)

        # Header
        header = tk.Frame(root, bg=self.BG)
        header.pack(fill="x", padx=30, pady=(24, 12))

        left = tk.Frame(header, bg=self.BG)
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text="شمارشگر بازدید ایتا", bg=self.BG, fg=self.TEXT,
                 font=("Segoe UI", 24, "bold")).pack(anchor="w")

        status_box = tk.Frame(header, bg=self.CARD, highlightbackground=self.BORDER,
                              highlightthickness=1)
        status_box.pack(side="right")
        self.status_dot = tk.Label(status_box, text="●", bg=self.CARD, fg=self.SUCCESS,
                                    font=("Segoe UI", 13))
        self.status_dot.pack(side="left", padx=(10, 4), pady=7)
        st = tk.Frame(status_box, bg=self.CARD)
        st.pack(side="left", padx=(0, 12), pady=6)
        tk.Label(st, textvariable=self.status_var, bg=self.CARD, fg=self.TEXT,
                 font=("Segoe UI", 9, "bold")).pack(anchor="e")
        tk.Label(st, textvariable=self.status_detail_var, bg=self.CARD, fg=self.MUTED,
                 font=("Segoe UI", 8)).pack(anchor="e")

        # Metrics
        metrics = tk.Frame(root, bg=self.BG)
        metrics.pack(fill="x", padx=30, pady=(0, 14))
        self._metric_card(metrics, "پست‌های ثبت‌شده", self.total_var, "تعداد")
        self._metric_card(metrics, "مجموع بازدید", self.views_var, "بازدید")
        self._metric_card(metrics, "میانگین بازدید", self.avg_var, "برای هر پست")
        self._metric_card(metrics, "موارد نیازمند بررسی", self.warning_var, "هشدار")

        # Main content
        body = tk.Frame(root, bg=self.BG)
        body.pack(fill="both", expand=True, padx=30, pady=(0, 22))

        left_col = tk.Frame(body, bg=self.BG)
        left_col.pack(side="left", fill="both", expand=True, padx=(0, 8))

        right_col = tk.Frame(body, bg=self.BG)
        right_col.pack(side="right", fill="both", expand=True, padx=(8, 0))

        self._build_channel_card(left_col)
        self._build_manual_card(left_col)
        self._build_run_card(right_col)
        self._build_log_card(right_col)

    def _metric_card(self, parent, title, variable, footer):
        card = self._card(parent)
        card.pack(side="left", fill="x", expand=True, padx=5)
        tk.Label(card, text=title, bg=self.CARD, fg=self.MUTED,
                 font=("Segoe UI", 9)).pack(anchor="e", padx=14, pady=(11, 0))
        tk.Label(card, textvariable=variable, bg=self.CARD, fg=self.TEXT,
                 font=("Segoe UI", 20, "bold")).pack(anchor="e", padx=14, pady=(1, 0))
        tk.Label(card, text=footer, bg=self.CARD, fg=self.MUTED,
                 font=("Segoe UI", 8)).pack(anchor="e", padx=14, pady=(0, 10))

    def _build_channel_card(self, parent):
        card = self._card(parent)
        card.pack(fill="x", pady=(0, 10))
        title = tk.Frame(card, bg=self.CARD)
        title.pack(fill="x", padx=16, pady=(13, 5))
        tk.Label(title, text="کانال و تنظیمات", bg=self.CARD, fg=self.TEXT,
                 font=("Segoe UI", 11, "bold")).pack(anchor="e")

        grid = tk.Frame(card, bg=self.CARD)
        grid.pack(fill="x", padx=16, pady=(0, 12))

        self._label(grid, "نام کانال (بدون @)").grid(row=0, column=1, sticky="e", padx=5, pady=5)
        self.channel_var = tk.StringVar()
        ttk.Entry(grid, textvariable=self.channel_var, width=30).grid(
            row=0, column=0, sticky="ew", padx=5, pady=5)

        self.mode_var = tk.StringVar(value="manual")
        modes = tk.Frame(grid, bg=self.CARD)
        modes.grid(row=1, column=0, columnspan=2, sticky="e", pady=(5, 2))
        ttk.Radiobutton(modes, text="دستی / اسکرول", variable=self.mode_var,
                        value="manual", command=self._toggle_mode).pack(side="right", padx=5)
        ttk.Radiobutton(modes, text="بازه شماره پست", variable=self.mode_var,
                        value="range", command=self._toggle_mode).pack(side="right", padx=5)

        self.range_frame = tk.Frame(grid, bg=self.CARD)
        self.range_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=4)
        self._label(self.range_frame, "از").pack(side="right", padx=4)
        self.start_id_var = tk.StringVar()
        ttk.Entry(self.range_frame, textvariable=self.start_id_var, width=10).pack(side="right", padx=4)
        self._label(self.range_frame, "تا").pack(side="right", padx=4)
        self.end_id_var = tk.StringVar()
        ttk.Entry(self.range_frame, textvariable=self.end_id_var, width=10).pack(side="right", padx=4)

        self._label(grid, "تأخیر بین پست‌ها (ثانیه)").grid(row=3, column=1, sticky="e", padx=5, pady=5)
        self.delay_var = tk.StringVar(value="1.5")
        ttk.Entry(grid, textvariable=self.delay_var, width=10).grid(row=3, column=0, sticky="e", padx=5, pady=5)

        self._label(grid, "فایل خروجی CSV").grid(row=4, column=1, sticky="e", padx=5, pady=5)
        out = tk.Frame(grid, bg=self.CARD)
        out.grid(row=4, column=0, sticky="ew", padx=5, pady=5)
        self.out_var = tk.StringVar(value=str(Path.cwd() / "eitaa_views.csv"))
        ttk.Entry(out, textvariable=self.out_var).pack(side="right", fill="x", expand=True)
        ttk.Button(out, text="...", width=3, command=self.on_browse_out).pack(side="right", padx=(5, 0))

        grid.columnconfigure(0, weight=1)

        self.login_status_lbl = tk.Label(card, text="", bg=self.CARD, fg=self.MUTED,
                                         font=("Segoe UI", 8))
        self.login_status_lbl.pack(anchor="e", padx=16, pady=(0, 4))
        self.login_btn = ttk.Button(card, text="ورود / ذخیره سشن", command=self.on_login_click)
        self.login_btn.pack(side="right", padx=16, pady=(0, 13))
        self.confirm_login_btn = ttk.Button(card, text="ورود انجام شد",
                                            command=self.on_confirm_login, state="disabled")
        self.confirm_login_btn.pack(side="right", padx=5, pady=(0, 13))
        self._update_login_status()

    def _build_manual_card(self, parent):
        card = self._card(parent)
        card.pack(fill="x", pady=(0, 10))

        tk.Label(card, text="اسکرول و بازه تاریخی", bg=self.CARD, fg=self.TEXT,
                 font=("Segoe UI", 11, "bold")).pack(anchor="e", padx=16, pady=(13, 8))

        opts = tk.Frame(card, bg=self.CARD)
        opts.pack(fill="x", padx=16, pady=2)

        self.auto_scroll_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts, text="اسکرول خودکار", variable=self.auto_scroll_var,
                        command=self._toggle_auto_scroll_fields).pack(side="right", padx=5)

        self._label(opts, "گام").pack(side="right", padx=(14, 3))
        self.scroll_step_var = tk.StringVar(value="350")
        self.scroll_step_entry = ttk.Entry(opts, textvariable=self.scroll_step_var, width=7)
        self.scroll_step_entry.pack(side="right")

        self._label(opts, "توقف").pack(side="right", padx=(14, 3))
        self.idle_stop_var = tk.StringVar(value="25")
        self.idle_stop_entry = ttk.Entry(opts, textvariable=self.idle_stop_var, width=7)
        self.idle_stop_entry.pack(side="right")

        dates = tk.Frame(card, bg=self.CARD)
        dates.pack(fill="x", padx=16, pady=7)
        self._label(dates, "از تاریخ").pack(side="right", padx=4)
        self.start_date_var = tk.StringVar()
        ttk.Entry(dates, textvariable=self.start_date_var, width=13).pack(side="right", padx=4)
        self._label(dates, "تا تاریخ").pack(side="right", padx=(12, 4))
        self.end_date_var = tk.StringVar()
        ttk.Entry(dates, textvariable=self.end_date_var, width=13).pack(side="right", padx=4)

        self._label(dates, "مکث روی بازدید نامشخص").pack(side="right", padx=(12, 4))
        self.stuck_give_up_var = tk.StringVar(value="25")
        ttk.Entry(dates, textvariable=self.stuck_give_up_var, width=7).pack(side="right", padx=4)

        btns = tk.Frame(card, bg=self.CARD)
        btns.pack(fill="x", padx=16, pady=(5, 14))
        self.manual_open_btn = ttk.Button(btns, text="🌐 باز کردن مرورگر", command=self.on_manual_open)
        self.manual_open_btn.pack(side="right", padx=3)
        self.manual_capture_btn = ttk.Button(btns, text="▶ شروع ضبط", style="Success.TButton",
                                              command=self.on_manual_start_capture, state="disabled")
        self.manual_capture_btn.pack(side="right", padx=3)
        self.manual_pause_btn = ttk.Button(btns, text="⏸ توقف", command=self.on_manual_pause, state="disabled")
        self.manual_pause_btn.pack(side="right", padx=3)
        self.manual_finish_btn = ttk.Button(btns, text="⏹ پایان و ذخیره", style="Danger.TButton",
                                            command=self.on_manual_finish, state="disabled")
        self.manual_finish_btn.pack(side="right", padx=3)

    def _build_run_card(self, parent):
        card = self._card(parent)
        card.pack(fill="x", pady=(0, 10))

        tk.Label(card, text="اجرای عملیات", bg=self.CARD, fg=self.TEXT,
                 font=("Segoe UI", 11, "bold")).pack(anchor="e", padx=16, pady=(13, 8))


        self.progress = ttk.Progressbar(card, mode="indeterminate")
        self.progress.pack(fill="x", padx=16, pady=(0, 10))

        self.run_btn = ttk.Button(card, text="🚀 شروع اسکرپینگ خودکار",
                                  style="Primary.TButton", command=self.on_run_click)
        self.run_btn.pack(fill="x", padx=16, pady=(0, 14))

    def _build_log_card(self, parent):
        card = self._card(parent)
        card.pack(fill="both", expand=True)

        top = tk.Frame(card, bg=self.CARD)
        top.pack(fill="x", padx=16, pady=(13, 7))
        tk.Label(top, text="گزارش زنده", bg=self.CARD, fg=self.TEXT,
                 font=("Segoe UI", 11, "bold")).pack(side="right")
        ttk.Button(top, text="پاک کردن", command=self._clear_log).pack(side="left")

        text_frame = tk.Frame(card, bg=self.CARD)
        text_frame.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self.log_text = tk.Text(text_frame, wrap="word", bg="#f8fafc", fg=self.TEXT,
                                relief="flat", borderwidth=0, font=("Consolas", 9),
                                padx=10, pady=8)
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(text_frame, command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=scrollbar.set)

        self._set_log_tags()

    def _set_log_tags(self):
        self.log_text.tag_configure("success", foreground=self.SUCCESS)
        self.log_text.tag_configure("warning", foreground=self.WARNING)
        self.log_text.tag_configure("error", foreground=self.DANGER)

    # ---------------------------------------------------------------
    # وضعیت و متریک
    # ---------------------------------------------------------------
    def _update_status(self, text, detail="", kind="ready"):
        self.status_var.set(text)
        self.status_detail_var.set(detail)
        colors = {"ready": self.SUCCESS, "running": self.ACCENT,
                  "warning": self.WARNING, "error": self.DANGER}
        self.status_dot.config(fg=colors.get(kind, self.SUCCESS))

    def _refresh_metrics(self, results):
        results = results or []
        total = len(results)
        views = sum((r.get("views") or 0) for r in results)
        avg = round(views / total) if total else 0
        warnings = sum(1 for r in results
                       if r.get("flag") in ("stuck_at_one", "no_views_loaded",
                                            "no_views", "error", "possible_nav_fail"))
        self.total_var.set(f"{total:,}")
        self.views_var.set(f"{views:,}")
        self.avg_var.set(f"{avg:,}")
        self.warning_var.set(f"{warnings:,}")

    def _update_metrics_from_session(self):
        if self.session:
            self._refresh_metrics(self.session.results)

    # ---------------------------------------------------------------
    # mode
    # ---------------------------------------------------------------
    def _toggle_auto_scroll_fields(self):
        state = "normal" if self.auto_scroll_var.get() else "disabled"
        self.scroll_step_entry.config(state=state)
        self.idle_stop_entry.config(state=state)

    def _toggle_mode(self):
        mode = self.mode_var.get()
        if mode == "range":
            self.range_frame.grid()
        else:
            self.range_frame.grid_remove()

        if self.worker_running or self.session is not None:
            return

        manual = mode == "manual"
        self.run_btn.config(state="disabled" if manual else "normal")
        self.manual_open_btn.config(state="normal" if manual else "disabled")

    # ---------------------------------------------------------------
    # فایل‌ها و لاگین
    # ---------------------------------------------------------------
    def _update_login_status(self):
        if Path(core.STORAGE_STATE).exists():
            self.login_status_lbl.config(text="● سشن آماده", fg=self.SUCCESS)
        else:
            self.login_status_lbl.config(text="● بدون سشن", fg=self.MUTED)

    def on_browse_out(self):
        path = filedialog.asksaveasfilename(
            title="ذخیره فایل خروجی CSV",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")]
        )
        if path:
            self.out_var.set(path)

    def on_login_click(self):
        if self.worker_running:
            return
        self.worker_running = True
        self.login_btn.config(state="disabled")
        self.confirm_login_btn.config(state="normal")
        self.confirm_event.clear()
        self._update_status("در انتظار ورود", "ورود به حساب", "running")

        def worker():
            try:
                core.login_and_save_session(log_fn=self._log,
                                            confirm_fn=self.confirm_event.wait)
                self._log("لاگین با موفقیت کامل شد.")
                self.after(0, self._update_login_status)
                self.after(0, lambda: self._update_status(
                    "آماده", "سشن ذخیره شد", "ready"))
            except Exception as e:
                self._log(f"خطا در لاگین: {e}")
                self.after(0, lambda: self._update_status("خطا", "لاگین ناموفق بود.", "error"))
            finally:
                self.worker_running = False
                self.after(0, lambda: self.login_btn.config(state="normal"))
                self.after(0, lambda: self.confirm_login_btn.config(state="disabled"))

        threading.Thread(target=worker, daemon=True).start()

    def on_confirm_login(self):
        self.confirm_event.set()

    # ---------------------------------------------------------------
    # خودکار
    # ---------------------------------------------------------------
    def on_run_click(self):
        if self.mode_var.get() == "manual":
            return
        if self.worker_running:
            messagebox.showinfo("در حال اجرا", "یک عملیات دیگر در حال اجراست.")
            return

        channel = self.channel_var.get().strip().lstrip("@")
        if not channel:
            messagebox.showwarning("خطا", "نام کانال را وارد کنید.")
            return

        try:
            delay = float(self.delay_var.get())
            if delay < 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("خطا", "تأخیر باید یک عدد صفر یا بزرگ‌تر باشد.")
            return

        post_ids = []
        if self.mode_var.get() == "range":
            try:
                start_id = int(self.start_id_var.get())
                end_id = int(self.end_id_var.get())
            except ValueError:
                messagebox.showwarning("خطا", "شماره شروع و پایان باید عدد باشند.")
                return
            if end_id < start_id:
                messagebox.showwarning("خطا", "شماره پایان باید بزرگ‌تر یا مساوی شروع باشد.")
                return
            post_ids = list(range(start_id, end_id + 1))
        else:
            messagebox.showwarning("خطا", "حالت دستی فقط برای اسکرول دستی است. برای استخراج خودکار، حالت بازه شماره پست را انتخاب کنید.")
            return

        out_path = self.out_var.get().strip() or "eitaa_views.csv"
        use_login = Path(core.STORAGE_STATE).exists()

        self.worker_running = True
        self.run_btn.config(state="disabled")
        self.progress.start(10)
        self.log_text.delete("1.0", "end")
        self._refresh_metrics([])
        self._update_status("در حال اجرا", f"{len(post_ids):,} پست", "running")
        self._log(f"شروع اسکرپینگ {len(post_ids)} پست از کانال @{channel} ...")

        def worker():
            try:
                results = core.scrape_posts(
                    channel, post_ids, use_login=use_login,
                    headless=False, delay=delay, log_fn=self._log
                )
                core.save_csv(results, out_path, log_fn=self._log)
                self.after(0, lambda: self._refresh_metrics(results))
                self._log("\n✅ اسکرپینگ تمام شد.")
                self.after(0, lambda: self._update_status(
                    "تکمیل شد", f"{len(results):,} پست", "ready"))
                self.after(0, lambda: messagebox.showinfo(
                    "پایان", f"نتایج در فایل زیر ذخیره شد:\n{out_path}"))
            except Exception as e:
                self._log(f"خطای کلی: {e}")
                self.after(0, lambda: self._update_status("خطا", "عملیات با خطا متوقف شد.", "error"))
                self.after(0, lambda: messagebox.showerror("خطا", str(e)))
            finally:
                self.worker_running = False
                self.after(0, lambda: self.run_btn.config(state="normal"))
                self.after(0, self.progress.stop)

        threading.Thread(target=worker, daemon=True).start()

    # ---------------------------------------------------------------
    # دستی
    # ---------------------------------------------------------------
    def on_manual_open(self):
        if self.worker_running or self.session is not None:
            messagebox.showinfo("توجه", "یک جلسه دستی از قبل باز است.")
            return

        channel = self.channel_var.get().strip().lstrip("@")
        if not channel:
            messagebox.showwarning("خطا", "نام کانال را وارد کنید.")
            return

        try:
            scroll_step = int(self.scroll_step_var.get())
            idle_stop_seconds = float(self.idle_stop_var.get())
            stuck_give_up_seconds = float(self.stuck_give_up_var.get())
            if scroll_step < 50 or idle_stop_seconds < 0 or stuck_give_up_seconds < 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("خطا", "مقادیر اسکرول و زمان‌ها را بررسی کنید.")
            return

        start_date = self.start_date_var.get().strip() or None
        end_date = self.end_date_var.get().strip() or None
        if start_date and core.parse_display_date_key(start_date) is None:
            messagebox.showwarning("خطا", "فرمت تاریخ شروع صحیح نیست؛ مثال: 1405/2/1")
            return
        if end_date and core.parse_display_date_key(end_date) is None:
            messagebox.showwarning("خطا", "فرمت تاریخ پایان صحیح نیست؛ مثال: 1405/2/1")
            return

        use_login = Path(core.STORAGE_STATE).exists()
        self.log_text.delete("1.0", "end")
        self._refresh_metrics([])
        self._update_status("در حال آماده‌سازی", f"@{channel}", "running")

        self.session = core.InteractiveSession(
            channel, use_login=use_login, log_fn=self._log,
            auto_scroll=self.auto_scroll_var.get(),
            scroll_step=scroll_step,
            idle_stop_seconds=idle_stop_seconds,
            end_date=end_date,
            start_date=start_date,
            stuck_give_up_seconds=stuck_give_up_seconds
        )
        self.session.start()
        self.worker_running = True

        self.manual_open_btn.config(state="disabled")
        self.manual_capture_btn.config(state="normal")
        self.manual_pause_btn.config(state="normal")
        self.manual_finish_btn.config(state="normal")

        self._monitor_session()

    def _monitor_session(self):
        if self.session:
            self._update_metrics_from_session()
            self.after(500, self._monitor_session)

    def on_manual_start_capture(self):
        if self.session:
            self.session.send("start")
            self._update_status("در حال ضبط", "ثبت بازدیدها", "running")

    def on_manual_pause(self):
        if self.session:
            self.session.send("pause")
            self._update_status("مکث", "ضبط متوقف شد", "warning")

    def on_manual_finish(self):
        if not self.session:
            return
        session = self.session
        session.send("finish")
        self.manual_capture_btn.config(state="disabled")
        self.manual_pause_btn.config(state="disabled")
        self.manual_finish_btn.config(state="disabled")
        self._update_status("در حال ذخیره", "ساخت CSV", "running")
        self._log("در حال بستن مرورگر و ذخیره‌ی نتایج ...")

        def waiter():
            session.finished_event.wait()
            out_path = self.out_var.get().strip() or "eitaa_views.csv"
            try:
                core.save_csv(session.results, out_path, log_fn=self._log)
                count = len(session.results)
                self.after(0, lambda: self._refresh_metrics(session.results))
                self.after(0, lambda: self._update_status(
                    "تکمیل شد", f"{count:,} پست", "ready"))
                self.after(0, lambda: messagebox.showinfo(
                    "پایان", f"نتایج در فایل زیر ذخیره شد:\n{out_path}"))
            except Exception as e:
                self._log(f"خطا در ذخیره‌ی CSV: {e}")
                self.after(0, lambda: self._update_status("خطا", "ذخیره CSV ناموفق بود.", "error"))
                self.after(0, lambda: messagebox.showerror("خطا", str(e)))
            finally:
                self.session = None
                self.worker_running = False
                self.after(0, lambda: self.manual_open_btn.config(state="normal"))

        threading.Thread(target=waiter, daemon=True).start()

    # ---------------------------------------------------------------
    # لاگ
    # ---------------------------------------------------------------
    def _clear_log(self):
        self.log_text.delete("1.0", "end")

    def _log(self, msg):
        self.log_queue.put(str(msg))

    def _poll_log_queue(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                low = msg.lower()
                tag = "success" if ("ثبت شد" in msg or "موفق" in msg or "تمام شد" in msg) else \
                      "error" if ("خطا" in msg or "error" in low) else \
                      "warning" if ("هشدار" in msg or "⚠" in msg or "گیر" in msg) else None
                self.log_text.insert("end", msg + "\n", tag)
                self.log_text.see("end")
        except queue.Empty:
            pass
        self.after(120, self._poll_log_queue)


if __name__ == "__main__":
    app = EitaaGUI()
    app.mainloop()
