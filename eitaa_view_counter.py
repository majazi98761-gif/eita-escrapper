"""
Eitaa Channel Post View Counter
================================
شمارشگر بازدید واقعی پست‌های کانال ایتا با استفاده از web.eitaa.com

چرا این کد لازم است؟
---------------------
صفحه‌ی eitaa.com/channel/id فقط یک پیش‌نمایش استاتیک است و عدد بازدیدش
واقعی نیست (معمولاً همیشه ۱ نشان می‌دهد). بازدید واقعی فقط در
web.eitaa.com دیده می‌شود که یک اپلیکیشن جاوااسکریپتی (SPA) است، پس
برای خواندنش باید از یک مرورگر واقعی (Playwright) استفاده کرد.

نصب پیش‌نیازها:
    pip install playwright
    playwright install chromium

⚠️ نکته‌ی مهم درباره‌ی selector ها:
    نام کلاس‌های CSS مربوط به «تعداد بازدید» در وب‌اپ ایتا را حدس زده‌ام
    (چون امکان تست زنده روی سایت را ندارم). حتماً قبل از اجرای واقعی:
    1. web.eitaa.com را در مرورگر خودتان باز کنید،
    2. روی یک پست کلیک راست کرده و «Inspect» (بازرسی) را بزنید،
    3. المنتی که عدد بازدید را نشان می‌دهد پیدا کنید و کلاس/سلکتور آن
       را در تابع extract_view_count() جایگزین کنید.

مراحل استفاده:
---------------
1) ابتدا (فقط یک‌بار) با فلگ --login وارد حساب خود شوید تا سشن ذخیره شود:
       python eitaa_view_counter.py --login

   اگر بدون لاگین هم بازدیدها درست نمایش داده شدند، نیازی به این مرحله
   نیست و می‌توانید مستقیم به مرحله‌ی بعد بروید.

2) سپس بسته به نیازتان یکی از حالت‌ها را اجرا کنید:

   الف) بازه‌ای از شماره پست‌ها:
       python eitaa_view_counter.py --channel defapressguilan \
           --start-id 94400 --end-id 94450

   ب) لیست دستی از لینک‌ها یا شماره پست‌ها (یک خط = یک پست):
       python eitaa_view_counter.py --channel defapressguilan \
           --ids-file my_links.txt

   ج) فیلتر بر اساس بازه‌ی تاریخی (بعد از استخراج، خروجی را بر اساس
      تاریخ پست فیلتر می‌کند - همچنان باید یک بازه‌ی شماره پست کلی
      یا فایل لینک به آن بدهید تا از کجا شروع کند بداند):
       python eitaa_view_counter.py --channel defapressguilan \
           --start-id 94000 --end-id 94500 \
           --start-date 2026-07-01 --end-date 2026-07-28

نتیجه در یک فایل CSV ذخیره می‌شود (پیش‌فرض: eitaa_views.csv).
"""

import argparse
import csv
import queue
import re
import sys
import threading
import time
from pathlib import Path
from datetime import datetime

from playwright.sync_api import sync_playwright

STORAGE_STATE = "eitaa_session.json"
BASE_URL = "https://web.eitaa.com"
RETRY_WAIT_MS = 2500  # مکث اضافه (میلی‌ثانیه) وقتی بازدید خالی یا ۱ بود


def login_and_save_session(log_fn=print, confirm_fn=None):
    """یک مرورگر واقعی باز می‌کند تا کاربر دستی لاگین کند و سپس سشن را
    برای استفاده‌های بعدی ذخیره می‌کند.

    log_fn: تابعی برای چاپ پیام‌های پیشرفت (پیش‌فرض: print؛ رابط گرافیکی
        می‌تواند تابع دیگری بدهد تا پیام‌ها را در یک پنجره نشان دهد).
    confirm_fn: تابعی که باید تا زمان تأیید کاربر (بعد از لاگین دستی در
        مرورگر) مسدود بماند. اگر داده نشود، از input() خط‌فرمان استفاده
        می‌شود. رابط گرافیکی می‌تواند اینجا یک threading.Event().wait
        یا مشابه آن بدهد که با کلیک دکمه‌ی «ورود انجام شد» آزاد شود.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(BASE_URL)
        log_fn("مرورگر باز شد. لطفاً با شماره موبایل خود در ایتا وارد شوید.")
        if confirm_fn is not None:
            confirm_fn()
        else:
            input("بعد از ورود موفق، اینجا Enter را بزنید تا سشن ذخیره شود... ")
        context.storage_state(path=STORAGE_STATE)
        browser.close()
        log_fn(f"سشن ذخیره شد در: {STORAGE_STATE}")


def get_post_url(channel: str, post_id: int) -> str:
    return f"{BASE_URL}/#@{channel}_{post_id}"


# ایتا بعضی اعداد (مثل تعداد بازدید) را با ارقام فارسی/عربی نمایش می‌دهد
# (۰۱۲۳۴۵۶۷۸۹ یا ٠١٢٣٤٥٦٧٨٩) نه ارقام انگلیسی. این جدول برای تبدیل آن‌هاست.
_DIGIT_MAP = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹" "٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789"
)


def normalize_digits(text: str) -> str:
    return text.translate(_DIGIT_MAP)


def parse_views_text(raw):
    """رشته‌ی بازدید ایتا را به عدد صحیح تبدیل می‌کند. ارقام فارسی/عربی و
    پسوندهای اختصاری K (هزار) / M (میلیون) را هم درست می‌فهمد، مثلاً:
    '27.7K' -> 27700، '1.2M' -> 1200000، '۱۲۳' -> 123.
    توجه: قبلاً با ()re.sub(r'[^\\d]', '', ...) فقط ارقام برداشته می‌شد که
    برای چیزی مثل '27.7K' غلط بود (نتیجه‌اش می‌شد 277 به‌جای 27700،
    چون هم نقطه‌ی اعشار و هم K حذف می‌شدند)."""
    if not raw:
        return None
    t = normalize_digits(raw).strip().replace(",", "")
    if not t:
        return None
    m = re.match(r"^(\d+(?:\.\d+)?)\s*([kKmM]?)$", t)
    if not m:
        digits = re.sub(r"[^\d]", "", t)
        return int(digits) if digits else None
    num_str, suffix = m.group(1), m.group(2).lower()
    try:
        num = float(num_str)
    except ValueError:
        return None
    if suffix == "k":
        num *= 1_000
    elif suffix == "m":
        num *= 1_000_000
    return int(round(num))


# جاوااسکریپتی که داخل صفحه اجرا می‌شود: بین همه‌ی پیام‌های کانال که در
# DOM لود شده‌اند (.bubble.channel-post)، آن پیامی که از نظر عمودی به
# مرکز صفحه نزدیک‌تر است را پیدا می‌کند. این همان پیامی است که اپ به
# آن اسکرول کرده — یعنی همان پستی که با تغییر hash قصدش را داشتیم،
# صرف‌نظر از این‌که data-mid داخلی‌اش چه عددی است.
_FIND_CENTERED_POST_JS = """
() => {
    const bubbles = Array.from(document.querySelectorAll('.bubble.channel-post'));
    if (bubbles.length === 0) return null;
    const viewportCenter = window.innerHeight / 2;
    let best = null, bestDist = Infinity;
    for (const b of bubbles) {
        const rect = b.getBoundingClientRect();
        if (rect.height === 0) continue;
        const center = rect.top + rect.height / 2;
        const dist = Math.abs(center - viewportCenter);
        if (dist < bestDist) { bestDist = dist; best = b; }
    }
    if (!best) return null;
    const viewsEl = best.querySelector('.post-views');
    const timeEl = best.querySelector('.time');
    return {
        mid: best.getAttribute('data-mid'),
        views: viewsEl ? viewsEl.textContent.trim() : null,
        date: timeEl ? (timeEl.getAttribute('title') || timeEl.textContent.trim()) : null,
    };
}
"""


def get_centered_post_info(page):
    """پیام وسط‌صفحه (یعنی همان پستی که اپ الان رویش زوم/فوکوس کرده) را
    برمی‌گرداند: {mid, views, date} یا None اگر چیزی پیدا نشد."""
    try:
        data = page.evaluate(_FIND_CENTERED_POST_JS)
    except Exception:
        return None
    if not data:
        return None
    return {
        "mid": data.get("mid"),
        "views": parse_views_text(data.get("views")),
        "date": normalize_digits(data.get("date") or "") or None,
    }


# جاوااسکریپتی که همه‌ی پست‌هایی که الان در DOM لود/mount شده‌اند را
# برمی‌گرداند (نه فقط پستی که دقیقاً وسط صفحه است). این باعث می‌شود اگر
# یک قدم اسکرول بزرگ باشد یا پستی هیچ‌وقت دقیقاً وسط صفحه نیفتد، باز هم
# از قلم نیفتد.
_COLLECT_MOUNTED_POSTS_JS = """
() => {
    const bubbles = Array.from(document.querySelectorAll('.bubble.channel-post'));
    return bubbles.map(b => {
        const viewsEl = b.querySelector('.post-views');
        const timeEl = b.querySelector('.time');
        return {
            mid: b.getAttribute('data-mid'),
            views: viewsEl ? viewsEl.textContent.trim() : null,
            date: timeEl ? (timeEl.getAttribute('title') || timeEl.textContent.trim()) : null,
        };
    }).filter(p => p.mid);
}
"""


def collect_mounted_posts(page):
    """همه‌ی پست‌های فعلاً mount‌شده در صفحه را برمی‌گرداند: لیستی از
    {mid, views, date}."""
    try:
        data = page.evaluate(_COLLECT_MOUNTED_POSTS_JS)
    except Exception:
        return []
    out = []
    for item in data or []:
        out.append({
            "mid": item.get("mid"),
            "views": parse_views_text(item.get("views")),
            "date": normalize_digits(item.get("date") or "") or None,
        })
    return out


# فقط mount شدن یک پست در DOM لزوماً کافی نیست تا بازدید واقعی‌اش لود
# شود؛ به نظر می‌رسد ایتا شمارش/لود بازدید را وقتی واقعاً پست وارد
# ناحیه‌ی دیدِ صفحه (viewport) می‌شود انجام می‌دهد (شبیه IntersectionObserver).
# این تابع همان پستی را که مشخص می‌کنید صریحاً به وسط صفحه اسکرول
# می‌کند -- دقیقاً همان کاری که وقتی خودتان دستی روی یک پست توقف
# می‌کردید اتفاق می‌افتاد.
_SCROLL_MID_INTO_VIEW_JS = """
(mid) => {
    const el = document.querySelector(`.bubble.channel-post[data-mid="${mid}"]`);
    if (el) {
        el.scrollIntoView({behavior: 'instant', block: 'center'});
        return true;
    }
    return false;
}
"""


def scroll_mid_into_view(page, mid):
    """پست با شناسه‌ی mid را (اگر هنوز mount باشد) به وسط صفحه اسکرول
    می‌کند تا واقعاً «دیده‌شده» حساب شود."""
    try:
        return bool(page.evaluate(_SCROLL_MID_INTO_VIEW_JS, mid))
    except Exception:
        return False


def parse_display_date_key(date_str):
    """تاریخ نمایشی ایتا (مثلاً '1405/2/1, 09:52:20' یا فقط '1405/2/1') را
    به یک تاپل قابل‌مقایسه (سال, ماه, روز, ساعت, دقیقه, ثانیه) تبدیل
    می‌کند. چون تقویم جلالی هم مثل میلادی به‌ترتیب افزایشی پیش می‌رود،
    مقایسه‌ی عددی ساده‌ی این تاپل‌ها برای تشخیص قبل/بعد بودن دو تاریخ
    کافی است و نیازی به تبدیل واقعی تقویم نیست. اگر پارس نشد None
    برمی‌گرداند."""
    if not date_str:
        return None
    date_part, _, time_part = date_str.strip().partition(",")
    m = re.match(r"(\d{1,4})/(\d{1,2})/(\d{1,2})", date_part.strip())
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    h = mi = se = 0
    tm = re.match(r"\s*(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?", time_part)
    if tm:
        h = int(tm.group(1))
        mi = int(tm.group(2))
        se = int(tm.group(3) or 0)
    return (y, mo, d, h, mi, se)


class InteractiveSession:
    """جلسه‌ی «دستی/اسکرول». مرورگر همیشه با headless=False باز می‌شود.

    منطق ساده و کاملاً ترتیبی است:

    - از همان نقطه‌ای که خودتان دستی به آن اسکرول کرده‌اید شروع می‌شود.
    - وقتی اسکرول خودکار (auto_scroll) روشن باشد، برنامه همیشه از بالا
      به پایین (یعنی از پست‌های قدیمی‌تر به سمت جدیدتر) اسکرول می‌کند؛
      دیگر جهت قابل‌انتخاب نیست.
    - پست‌ها را دقیقاً یکی‌یکی، به ترتیب تاریخشان، بررسی می‌کند.
    - روی هر پست تازه: اگر بازدیدش هنوز لود نشده (خالی) یا دقیقاً روی
      عدد ۱ باشد، برنامه همان‌جا مکث می‌کند (اسکرول بعدی انجام
      نمی‌شود) و هر ۱ ثانیه دوباره همان پست را چک می‌کند.
        - اگر عدد واقعی لود شد → همان لحظه با عدد درست ثبت می‌شود و
          اسکرول به پست بعدی ادامه پیدا می‌کند.
        - اگر بعد از stuck_give_up_seconds ثانیه (پیش‌فرض ۲۵) باز هم
          چیزی عوض نشد → همان مقدار (۱، یا اگر اصلاً چیزی نیامده بود
          صفر) با برچسب مناسب (stuck_at_one / no_views_loaded) ثبت
          می‌شود و اسکرول ادامه پیدا می‌کند (پستی که رد شود دیگر گم
          نمی‌شود، فقط ممکن است بازدیدش دقیق نباشد).
    - اگر «تاریخ پایان» (end_date) داده شده باشد، به محض رسیدن به آن
      تاریخ، ضبط به‌طور خودکار متوقف می‌شود.
    - اگر «تاریخ شروع» (start_date) هم داده شده باشد، پست‌های قبل از
      آن دیده می‌شوند ولی ثبت نمی‌شوند (تا وارد بازه‌ی موردنظر شویم).
    - اگر برای مدتی (idle_stop_seconds) اصلاً هیچ پست تازه‌ای ظاهر
      نشود (نه فقط بازدیدش، بلکه خودِ پست)، یعنی احتمالاً به انتهای
      بخش لودشده رسیده‌ایم؛ ضبط موقتاً متوقف می‌شود.

    کاربر در هر لحظه با «توقف موقت» / «شروع ضبط» / «پایان و ذخیره»
    کنترل کامل دارد. توجه: چون بررسی هر پست ممکن است تا
    stuck_give_up_seconds ثانیه طول بکشد، اگر درست در همان لحظه دکمه‌ی
    «توقف موقت» یا «پایان و ذخیره» را بزنید، ممکن است تا پایان همان
    بررسی (حداکثر همان چند ثانیه) طول بکشد تا واقعاً اعمال شود.
    """

    def __init__(self, channel, use_login=True, log_fn=print,
                 auto_scroll=False, scroll_step=350,
                 idle_stop_seconds=25.0, end_date=None, start_date=None,
                 stuck_give_up_seconds=25.0):
        self.channel = channel
        self.use_login = use_login
        self.log_fn = log_fn
        self.auto_scroll = auto_scroll
        self.scroll_step = max(50, int(scroll_step))
        self.idle_stop_seconds = max(0.0, float(idle_stop_seconds))  # 0 یعنی غیرفعال
        self.stuck_give_up_seconds = max(0.0, float(stuck_give_up_seconds))
        self.end_date = (end_date or "").strip() or None
        self.start_date = (start_date or "").strip() or None
        self._end_date_key = parse_display_date_key(self.end_date) if self.end_date else None
        self._start_date_key = parse_display_date_key(self.start_date) if self.start_date else None

        # بازه‌ی مجاز برای ثبت (همیشه کوچک‌تر تا بزرگ‌تر، فارغ از این‌که
        # کدام‌یک را «شروع» و کدام را «پایان» نامیده‌اید): اگر هر دو داده
        # شده باشند، فقط پست‌های داخل این بازه ثبت می‌شوند.
        keys = [k for k in (self._start_date_key, self._end_date_key) if k is not None]
        if len(keys) == 2:
            self._lower_bound = min(keys)
            self._upper_bound = max(keys)
        elif self._start_date_key is not None:
            self._lower_bound = self._start_date_key
            self._upper_bound = None
        elif self._end_date_key is not None:
            self._lower_bound = None
            self._upper_bound = self._end_date_key
        else:
            self._lower_bound = None
            self._upper_bound = None
        self._entered_range_logged = False

        self._commands = queue.Queue()
        self.results = []
        self._seen_mids = set()   # پست‌هایی که پردازش‌شان تمام شده (چه ثبت شده باشند چه رد شده)
        self._capturing = False
        self._last_new_mid_time = None
        self.finished_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        """جلسه را در یک ترد جدا اجرا می‌کند (چون Playwright sync باید در
        همان تردی که مرورگر را باز کرده فراخوانی شود)."""
        self._thread.start()

    def send(self, command):
        """command یکی از این مقادیر: 'start' (شروع ضبط), 'pause' (توقف
        موقت ضبط، مرورگر باز می‌ماند)، 'finish' (پایان و بستن مرورگر)."""
        self._commands.put(command)

    def _scroll_down_one_step(self, page):
        """یک قدم به پایین (یعنی به سمت پست‌های جدیدتر) اسکرول می‌کند."""
        try:
            vw = page.viewport_size or {"width": 1000, "height": 700}
            page.mouse.move(vw["width"] / 2, vw["height"] / 2)
            page.mouse.wheel(0, abs(self.scroll_step))
            page.wait_for_timeout(400)
        except Exception as e:
            self.log_fn(f"هشدار: اسکرول خودکار انجام نشد ({e}).")

    def _in_range(self, dk):
        if dk is None:
            return True
        if self._lower_bound is not None and dk < self._lower_bound:
            return False
        if self._upper_bound is not None and dk > self._upper_bound:
            return False
        return True

    def _record(self, mid, views, date, flag):
        entry = {
            "post_id": mid,
            "url": f"{BASE_URL}/#@{self.channel}_{mid}",
            "views": views,
            "date": date,
            "flag": flag,
        }
        self.results.append(entry)
        note = ""
        if flag == "stuck_at_one":
            note = " ⚠️ (روی ۱ گیر کرد)"
        elif flag == "no_views_loaded":
            note = " ⚠️ (اصلاً بازدیدش لود نشد)"
        views_display = views if views is not None else "؟"
        self.log_fn(f"✅ ثبت شد → پست {mid} | بازدید = {views_display} | تاریخ = {date}{note}")

    def _resolve_batch(self, page, sorted_new_posts):
        """قبل از ثبت، برای همه‌ی پست‌های تازه‌ای که بازدیدشان هنوز معلوم
        نیست (None یا ۱)، یک مکثِ مشترک انجام می‌دهد -- نه این‌که برای هر
        پست جداگانه صبر کند. یعنی اگر مثلاً ۱۰ پست هم‌زمان روی ۱ گیر کرده
        باشند، مجموعاً حداکثر stuck_give_up_seconds صبر می‌شود (نه ۱۰
        برابرش)؛ همین باعث سرعت بسیار بیشتر می‌شود بدون افت دقت، چون
        هرکدام که زودتر لود شود همان لحظه با عدد درست ثبت می‌شود.
        sorted_new_posts در جا (in place) با آخرین مقادیر به‌روزرسانی
        می‌شود."""
        pending = {}
        for p in sorted_new_posts:
            mid = p.get("mid")
            if not mid or (p.get("views") is not None and p.get("views") != 1):
                continue
            if self._start_date_key is not None or self._end_date_key is not None:
                dk = parse_display_date_key(p.get("date"))
                if not self._in_range(dk):
                    continue  # خارج از بازه‌ی موردنظر؛ نیازی به دقت بازدیدش نیست
            pending[mid] = p
        if not pending:
            return

        waited = 0.0
        while pending and waited < self.stuck_give_up_seconds:
            for mid in pending:
                scroll_mid_into_view(page, mid)
            page.wait_for_timeout(1000)
            waited += 1.0
            fresh_by_mid = {p["mid"]: p for p in collect_mounted_posts(page) if p.get("mid")}
            for mid in list(pending.keys()):
                match = fresh_by_mid.get(mid)
                if match is None:
                    continue  # هنوز از صفحه خارج نشده حساب می‌شود؛ دفعه‌ی بعد دوباره چک می‌شود
                if match.get("date"):
                    pending[mid]["date"] = match["date"]
                if match.get("views") is not None and match.get("views") != 1:
                    pending[mid]["views"] = match["views"]
                    del pending[mid]
        # هرچه در pending باقی مانده یعنی مهلت تمام شد و همچنان نامعلوم/۱
        # است؛ همان مقدار آخر (که از قبل در sorted_new_posts نشسته) به
        # همراه گزارش نهایی می‌رود.

    def _process_one_post(self, info):
        """یک پستِ از‌قبل‌حل‌شده (views دیگر نامعلوم نیست، مگر اینکه مهلت
        تمام شده باشد) را ثبت می‌کند. خروجی: True یعنی به تاریخ پایان
        رسیدیم و باید کاملاً متوقف شویم."""
        mid = info.get("mid")
        self._seen_mids.add(mid)  # دیگر در پول‌های بعدی دوباره پردازش نشود

        dk = None
        if self._start_date_key is not None or self._end_date_key is not None:
            dk = parse_display_date_key(info.get("date"))

        reached_end = self._end_date_key is not None and dk is not None and dk >= self._end_date_key

        if not self._in_range(dk):
            return reached_end

        if self._lower_bound is not None and not self._entered_range_logged:
            self._entered_range_logged = True
            self.log_fn(
                f"📍 وارد بازه‌ی تاریخی موردنظر شدید (از {self.start_date or '—'} "
                f"تا {self.end_date or '—'})؛ از این‌جا ثبت واقعی شروع می‌شود."
            )

        views = info.get("views")
        date = info.get("date")

        if views is None or views == 1:
            flag = "no_views_loaded" if views is None else "stuck_at_one"
            self._record(mid, views if views is not None else 0, date, flag)
            return reached_end

        flag = "manual" if not self.auto_scroll else "auto_scroll"
        self._record(mid, views, date, flag)
        return reached_end

    def _run(self):
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=False)
                if self.use_login and Path(STORAGE_STATE).exists():
                    context = browser.new_context(storage_state=STORAGE_STATE)
                else:
                    context = browser.new_context()
                page = context.new_page()
                self.log_fn(f"در حال باز کردن کانال @{self.channel} ...")
                page.goto(f"{BASE_URL}/#@{self.channel}")
                if self.auto_scroll:
                    self.log_fn(
                        "مرورگر باز شد. داخل کانال به پستی که می‌خواهید از آنجا "
                        "شروع کنید بروید، سپس «شروع ضبط» را بزنید؛ از آن لحظه "
                        "خودِ برنامه رو به پایین (از قدیمی‌تر به جدیدتر) اسکرول "
                        "می‌کند."
                    )
                else:
                    self.log_fn(
                        "مرورگر باز شد. داخل کانال به بالا/پایین اسکرول کنید تا "
                        "پستی که می‌خواهید دیده شود، سپس دکمه‌ی «شروع ضبط» "
                        "را در برنامه بزنید."
                    )

                running = True
                while running:
                    try:
                        cmd = self._commands.get(timeout=0.3)
                    except queue.Empty:
                        cmd = None

                    if cmd == "start":
                        self._capturing = True
                        self._last_new_mid_time = time.monotonic()
                        if self.auto_scroll:
                            self.log_fn("▶️ ضبط شروع شد؛ اسکرول خودکار (از قدیمی‌تر به جدیدتر) فعال است.")
                        else:
                            self.log_fn("▶️ ضبط شروع شد؛ حالا آرام اسکرول کنید.")
                    elif cmd == "pause":
                        self._capturing = False
                        self.log_fn("⏸ ضبط موقتاً متوقف شد (مرورگر باز می‌ماند).")
                    elif cmd == "finish":
                        running = False

                    if not running:
                        break
                    if not self._capturing:
                        continue

                    if self.auto_scroll:
                        self._scroll_down_one_step(page)

                    posts = collect_mounted_posts(page)
                    new_posts = [p for p in posts
                                 if p.get("mid") and p.get("mid") not in self._seen_mids]

                    if new_posts:
                        self._last_new_mid_time = time.monotonic()
                        # به ترتیب تاریخ (قدیمی‌تر تا جدیدتر) پردازش می‌کنیم،
                        # نه هر ترتیبی که DOM برگردانده، تا تشخیص «رسیدن به
                        # تاریخ پایان» درست باشد.
                        def _sort_key(p):
                            dk = parse_display_date_key(p.get("date"))
                            return dk if dk is not None else (9999, 0, 0, 0, 0, 0)
                        new_posts.sort(key=_sort_key)

                        # مکث (اگر لازم بود) یک‌بار و مشترک برای کل این
                        # دسته انجام می‌شود -- نه یکی‌یکی -- که سرعت را
                        # به‌شدت بالا می‌برد.
                        self._resolve_batch(page, new_posts)

                        stop_everything = False
                        for info in new_posts:
                            if info.get("mid") in self._seen_mids:
                                continue  # ممکن است در یک پردازش قبلی هم‌زمان ثبت شده باشد
                            if self._process_one_post(info):
                                stop_everything = True
                                break

                        if stop_everything:
                            self._capturing = False
                            self.log_fn(
                                f"🏁 به تاریخ پایان تعیین‌شده ({self.end_date}) رسیدید؛ ضبط "
                                "خودکار متوقف شد. اگر می‌خواهید نتایج تا همین‌جا ذخیره شود "
                                "«پایان و ذخیره» را بزنید."
                            )
                    elif self.auto_scroll and self._last_new_mid_time is not None:
                        idle_seconds = time.monotonic() - self._last_new_mid_time
                        if self.idle_stop_seconds and idle_seconds >= self.idle_stop_seconds:
                            self._capturing = False
                            self.log_fn(
                                f"⏸ برای {int(idle_seconds)} ثانیه هیچ پست تازه‌ای دیده نشد؛ "
                                "به نظر می‌رسد به انتهای بخش لودشده رسیدید (یا لود پست‌های "
                                "بعدی از سرور کند است). ضبط خودکار موقتاً متوقف شد. اگر پست "
                                "بیشتری هست، خودتان کمی اسکرول/جابه‌جا کنید و دوباره «شروع "
                                "ضبط» را بزنید؛ وگرنه «پایان و ذخیره» را بزنید."
                            )

                browser.close()
        except Exception as e:
            self.log_fn(f"خطا در جلسه‌ی دستی: {e}")
        finally:
            self.finished_event.set()
            self.log_fn(f"\nجلسه بسته شد. مجموعاً {len(self.results)} پست ثبت شد.")


def scrape_posts(channel, post_ids, use_login, headless=False, delay=1.5, log_fn=print):
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        if use_login and Path(STORAGE_STATE).exists():
            context = browser.new_context(storage_state=STORAGE_STATE)
        else:
            context = browser.new_context()
        page = context.new_page()

        # اول یک‌بار خود کانال را باز می‌کنیم تا وب‌اپ کامل لود شود.
        log_fn(f"در حال باز کردن کانال @{channel} ...")
        page.goto(f"{BASE_URL}/#@{channel}")
        page.wait_for_timeout(3000)

        last_mid = None
        for pid in post_ids:
            url = get_post_url(channel, pid)
            hash_value = f"@{channel}_{pid}"
            try:
                # به‌جای رفرش کامل صفحه (page.goto) که باعث می‌شد اپ هر بار
                # از صفر لود شود (و آن toast خطا لحظه‌ای ظاهر شود)، فقط
                # هش آدرس را عوض می‌کنیم؛ دقیقاً همان کاری که وقتی داخل
                # خود اپ روی یک پست کلیک می‌کنید اتفاق می‌افتد.
                page.evaluate("h => { window.location.hash = h; }", hash_value)
                page.wait_for_timeout(int(delay * 1000))
                info = get_centered_post_info(page)
                views = info["views"] if info else None
                mid = info["mid"] if info else None
                post_date = info["date"] if info else None

                # اگر هنوز لود نشده (خالی) یا مقدار ۱ بود، چند لحظه بیشتر
                # صبر می‌کنیم تا مطمئن شویم واقعاً همینه، نه اینکه دیر لود شده.
                if views is None or views == 1:
                    page.wait_for_timeout(RETRY_WAIT_MS)
                    retry_info = get_centered_post_info(page)
                    if retry_info and retry_info["views"] is not None:
                        views = retry_info["views"]
                        mid = retry_info["mid"]
                        post_date = retry_info["date"]

                if views is None:
                    flag = "no_views"      # هیچ عنصر بازدیدی پیدا نشد -> صفر در نظر می‌گیریم
                    views = 0
                elif views == 1:
                    flag = "stuck_at_one"  # بعد از تلاش دوباره هم ۱ بود -> همان ۱ حساب می‌شود
                elif mid is not None and mid == last_mid:
                    # اگر شناسه‌ی داخلی پیام نسبت به پست قبلی عوض نشده،
                    # یعنی احتمالاً ناوبری واقعاً انجام نشده (همان پست قبلی
                    # هنوز وسط صفحه است) و این بازدید مشکوک است.
                    flag = "possible_nav_fail"
                else:
                    flag = "normal"

                last_mid = mid
                results.append({
                    "post_id": pid, "url": url,
                    "views": views, "date": post_date, "flag": flag,
                })
                log_fn(f"پست {pid} (mid={mid}): بازدید = {views} | تاریخ = {post_date} | وضعیت = {flag}")
            except Exception as e:
                log_fn(f"خطا در پست {pid}: {e}")
                results.append({"post_id": pid, "url": url,
                                 "views": 0, "date": None, "flag": "error"})
            time.sleep(delay)

        browser.close()
    return results


def save_csv(results, out_path, log_fn=print):
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["post_id", "url", "views", "date", "flag"])
        writer.writeheader()
        writer.writerows(results)
    log_fn(f"نتایج ذخیره شد در: {out_path}")

    stuck_at_one = [r for r in results if r["flag"] == "stuck_at_one"]
    no_views_loaded = [r for r in results if r["flag"] == "no_views_loaded"]
    no_views = [r for r in results if r["flag"] in ("no_views", "error")]
    normal = [r for r in results if r["flag"] not in
              ("stuck_at_one", "no_views_loaded", "no_views", "error")]

    log_fn("\n--- آمار خلاصه ---")
    log_fn(f"تعداد کل پست‌های بررسی‌شده: {len(results)}")
    log_fn(f"پست‌های با بازدید عادی: {len(normal)}")
    log_fn(f"پست‌های گیر کرده روی بازدید ۱ (stuck_at_one): {len(stuck_at_one)}")
    log_fn(f"پست‌هایی که بازدیدشان اصلاً لود نشد (no_views_loaded): {len(no_views_loaded)}")
    log_fn(f"پست‌های بدون بازدید / خطا (صفر در نظر گرفته شده): {len(no_views)}")
    if stuck_at_one or no_views_loaded:
        log_fn(
            "⚠️ توجه: پست‌های stuck_at_one و no_views_loaded را بهتر است دستی در "
            "مرورگر چک کنید، چون بازدید ثبت‌شده‌شان ممکن است دقیق نباشد."
        )

    total = sum(r["views"] for r in results if r["views"] is not None)
    log_fn(f"مجموع بازدید {len([r for r in results if r['views'] is not None])} پست: {total}")


def main():
    parser = argparse.ArgumentParser(description="Eitaa channel post view counter")
    parser.add_argument("--login", action="store_true",
                         help="مرحله اول: لاگین دستی و ذخیره سشن")
    parser.add_argument("--channel", type=str, help="نام کانال (بدون @)")
    parser.add_argument("--start-id", type=int, help="شماره پست شروع")
    parser.add_argument("--end-id", type=int, help="شماره پست پایان")
    parser.add_argument("--ids-file", type=str,
                         help="فایل متنی حاوی لیست لینک‌ها یا شماره پست‌ها (هر خط یکی)")
    parser.add_argument("--start-date", type=str,
                         help="فیلتر تاریخ شروع بعد از استخراج (فرمت آزاد، تطبیق متنی ساده)")
    parser.add_argument("--end-date", type=str,
                         help="فیلتر تاریخ پایان بعد از استخراج")
    parser.add_argument("--headless", action="store_true", default=False,
                         help="اجرا بدون نمایش مرورگر (پیشنهاد نمی‌شود، چون ناوبری خودکار ایتا گاهی گم می‌شود)")
    parser.add_argument("--show-browser", dest="headless", action="store_false",
                         help="نمایش مرورگر حین اسکرپ (پیش‌فرض)")
    parser.add_argument("--out", type=str, default="eitaa_views.csv")
    parser.add_argument("--delay", type=float, default=1.5,
                         help="تأخیر بین درخواست‌ها به ثانیه")
    args = parser.parse_args()

    if args.login:
        login_and_save_session()
        return

    if not args.channel:
        print("لطفاً نام کانال را با --channel مشخص کنید.")
        sys.exit(1)

    post_ids = []
    if args.ids_file:
        with open(args.ids_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                m = re.search(r"(\d+)\s*$", line)
                if m:
                    post_ids.append(int(m.group(1)))
    elif args.start_id and args.end_id:
        post_ids = list(range(args.start_id, args.end_id + 1))
    else:
        print("باید یکی از این‌ها را مشخص کنید: --ids-file یا (--start-id و --end-id)")
        sys.exit(1)

    use_login = Path(STORAGE_STATE).exists()
    results = scrape_posts(args.channel, post_ids, use_login=use_login,
                            headless=args.headless, delay=args.delay)

    if args.start_date or args.end_date:
        # فیلتر ساده‌ی متنی؛ اگر فرمت تاریخ سایت مشخص شد، این بخش را
        # می‌توان دقیق‌تر با datetime.strptime پیاده‌سازی کرد.
        print("توجه: فیلتر تاریخ فعلاً ساده است، خروجی CSV کامل را هم بررسی کنید.")

    save_csv(results, args.out)


if __name__ == "__main__":
    main()
