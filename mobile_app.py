"""
mobile_app.py — KivyMD 手机端刷题 APP（纯 Python 实现）

与桌面版共用 quiz_app.db，数据完全同步。

用法：
    python mobile_app.py
"""

import os
import sys
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import DatabaseManager

# ── Kivy 导入 ──
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.utils import get_color_from_hex
from kivy.clock import Clock
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.behaviors import ButtonBehavior
from kivy.properties import StringProperty, NumericProperty
from kivy.graphics import Color, RoundedRectangle, Rectangle

# ── 配色 ──
BG      = "#F2EFEA"
CARD    = "#FAF8F4"
CARD2   = "#F4F1EB"
GREEN   = "#3A7D5C"
TEAL    = "#5B7B7A"
TEXT    = "#2C3E50"
MUTED   = "#6B7B8D"
SUCCESS = "#6AAF7B"
ERR     = "#D4786A"
STAR_COL = "#D4A86A"

# ═══════════════════════════════════════════════════════════════════════════
#  自定义组件
# ═══════════════════════════════════════════════════════════════════════════

class RoundedCard(BoxLayout):
    """带圆角背景的卡片"""
    def __init__(self, bg=CARD, radius=12, **kw):
        super().__init__(**kw)
        self.padding = [dp(16), dp(12)]
        with self.canvas.before:
            Color(*get_color_from_hex(bg))
            self.rect = RoundedRectangle(pos=self.pos, size=self.size,
                                          radius=[dp(radius)])
        self.bind(pos=self._update_rect, size=self._update_rect)

    def _update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size


class OptButton(Button):
    """选项大按钮（触屏友好）"""
    def __init__(self, label, text, on_choose, **kw):
        super().__init__(**kw)
        self.display_label = label
        self.orig_key = label
        self.on_choose = on_choose
        self.text = f"  {label}. {text}"
        self.size_hint_y = None
        self.height = dp(54)
        self.font_size = dp(15)
        self.color = get_color_from_hex(TEXT)
        self.background_normal = ""
        self.background_color = get_color_from_hex(CARD)
        self.border = (dp(1), dp(1), dp(1), dp(1))
        # 边框通过 canvas 实现
        with self.canvas.before:
            Color(*get_color_from_hex("#D8D2C6"))
            self.border_rect = RoundedRectangle(pos=self.pos, size=self.size,
                                                 radius=[dp(10)])
            Color(*get_color_from_hex(CARD))
            self.bg_rect = RoundedRectangle(pos=(self.x+1, self.y+1),
                                             size=(self.width-2, self.height-2),
                                             radius=[dp(10)])
        self.bind(pos=self._update_rect, size=self._update_rect)

    def _update_rect(self, *args):
        self.border_rect.pos = self.pos
        self.border_rect.size = self.size
        self.bg_rect.pos = (self.x+1, self.y+1)
        self.bg_rect.size = (self.width-2, self.height-2)

    def on_press(self):
        self.on_choose(self)


# ═══════════════════════════════════════════════════════════════════════════
#  主页 Screen
# ═══════════════════════════════════════════════════════════════════════════

class HomeScreen(Screen):
    def __init__(self, sm, **kw):
        super().__init__(**kw)
        self.sm = sm
        self.app = QuizMobileApp.get_running_app()
        self.build_ui()

    def build_ui(self):
        root = BoxLayout(orientation="vertical", spacing=dp(8),
                         padding=[dp(12), dp(8)])
        with root.canvas.before:
            Color(*get_color_from_hex(BG))
            Rectangle(pos=root.pos, size=root.size)
        root.bind(pos=lambda i, v: setattr(root.canvas.before.children[-1], 'pos', v),
                  size=lambda i, v: setattr(root.canvas.before.children[-1], 'size', v))
        self.add_widget(root)

        # 标题
        title = Label(text="📝 刷题工具", font_size=dp(24),
                      color=get_color_from_hex(GREEN),
                      size_hint_y=None, height=dp(48))
        root.add_widget(title)

        # 总览
        self.overview = Label(text="加载中...", font_size=dp(13),
                              color=get_color_from_hex(MUTED),
                              size_hint_y=None, height=dp(24))
        root.add_widget(self.overview)

        # 快速刷题按钮
        btn_layout = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        quick = Button(text="⚡ 快速刷 10 题",
                       background_color=get_color_from_hex(GREEN),
                       color=(1,1,1,1), font_size=dp(14))
        quick.bind(on_press=lambda x: self.app.start_quick_ten(self.sm))
        btn_layout.add_widget(quick)
        root.add_widget(btn_layout)

        # 学科列表标题
        root.add_widget(Label(text="📚 选择学科", font_size=dp(16),
                              color=get_color_from_hex(TEXT),
                              size_hint_y=None, height=dp(30),
                              halign="left"))

        # 可滚动的学科列表
        scroll = ScrollView()
        self.list_layout = GridLayout(cols=1, spacing=dp(6),
                                       size_hint_y=None, padding=[0, 0])
        self.list_layout.bind(minimum_height=self.list_layout.setter("height"))
        scroll.add_widget(self.list_layout)
        root.add_widget(scroll)

    def on_enter(self):
        self.refresh()

    def refresh(self):
        self.list_layout.clear_widgets()
        subjects = self.app.db.get_subjects()
        stats = self.app.db.get_all_stats()

        tqs = sum(s["total"] for s in stats)
        ta = sum(s["answered"] for s in stats)
        tc = sum(s["correct"] for s in stats)
        acc = round(tc/ta*100, 1) if ta else 0
        self.overview.text = f"📚 {len(stats)} 学科  📝 {tqs}题  🎯 {acc}%"

        if not subjects:
            self.list_layout.add_widget(
                Label(text="暂无学科，请先在桌面版录入", color=get_color_from_hex(MUTED),
                      size_hint_y=None, height=dp(60)))
            return

        for s in subjects:
            ss = next((x for x in stats if x["subject_id"]==s["id"]), None)
            n = ss["total"] if ss else "?"
            a = f"{ss['accuracy']}%" if ss and ss["answered"] else ""
            w = f" ❌{ss['wrong_total']}" if ss and ss["wrong_total"] else ""
            info = f"  {n}题 {a}{w}"

            # 学科卡片
            card = BoxLayout(orientation="horizontal", size_hint_y=None,
                             height=dp(50), padding=[dp(12), 0])
            with card.canvas.before:
                Color(*get_color_from_hex(CARD))
                RoundedRectangle(pos=card.pos, size=card.size, radius=[dp(10)])
            card.bind(pos=lambda c, *a: self._update_bg(c),
                      size=lambda c, *a: self._update_bg(c))

            name = Label(text=s["name"], font_size=dp(16),
                         color=get_color_from_hex(TEXT),
                         halign="left", size_hint_x=0.6)
            card.add_widget(name)
            meta = Label(text=info, font_size=dp(13),
                         color=get_color_from_hex(MUTED),
                         halign="right", size_hint_x=0.4)
            card.add_widget(meta)

            # 点击进入刷题
            card.bind(on_touch_down=lambda inst, touch, sid=s["id"]:
                      self.on_subject_tap(inst, touch, sid))
            self.list_layout.add_widget(card)

    def _update_bg(self, card):
        """更新卡片背景圆角"""
        card.canvas.before.clear()
        with card.canvas.before:
            Color(*get_color_from_hex(CARD))
            RoundedRectangle(pos=card.pos, size=card.size, radius=[dp(10)])

    def on_subject_tap(self, inst, touch, sid):
        if inst.collide_point(*touch.pos):
            self.app.start_review(sid, self.sm)


# ═══════════════════════════════════════════════════════════════════════════
#  刷题 Screen
# ═══════════════════════════════════════════════════════════════════════════

class ReviewScreen(Screen):
    def __init__(self, sm, **kw):
        super().__init__(**kw)
        self.sm = sm
        self.app = QuizMobileApp.get_running_app()
        self.questions = []
        self.idx = 0
        self.answered = False
        self.correct_n = 0
        self.total_n = 0
        self.q_buttons = []
        self.mapping = []
        self._custom_qs = None
        self._custom_title = ""
        self.build_ui()

    def build_ui(self):
        root = BoxLayout(orientation="vertical", spacing=dp(6),
                         padding=[dp(8), dp(4)])
        with root.canvas.before:
            Color(*get_color_from_hex(BG))
            Rectangle(pos=root.pos, size=root.size)
        root.bind(pos=lambda i, v: setattr(root.canvas.before.children[-1], 'pos', v),
                  size=lambda i, v: setattr(root.canvas.before.children[-1], 'size', v))
        self.add_widget(root)

        # 顶栏
        top = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        back = Button(text="‹", font_size=dp(24),
                      color=get_color_from_hex(GREEN),
                      background_normal="", background_color=(0,0,0,0),
                      size_hint_x=0.12)
        back.bind(on_press=lambda x: self.go_home())
        top.add_widget(back)

        self.title_label = Label(text="刷题", font_size=dp(16),
                                  color=get_color_from_hex(TEXT),
                                  size_hint_x=0.5)
        top.add_widget(self.title_label)

        self.progress_label = Label(text="0/0", font_size=dp(13),
                                     color=get_color_from_hex(MUTED),
                                     size_hint_x=0.38, halign="right")
        top.add_widget(self.progress_label)
        root.add_widget(top)

        # 错题 + 星标
        meta = BoxLayout(size_hint_y=None, height=dp(24), spacing=dp(8))
        self.wrong_label = Label(text="", font_size=dp(12),
                                  color=get_color_from_hex(ERR),
                                  size_hint_x=0.6, halign="left")
        meta.add_widget(self.wrong_label)
        self.star_btn = Button(text="☆", font_size=dp(18),
                                color=get_color_from_hex(MUTED),
                                size_hint_x=0.4, halign="right",
                                background_normal="", background_color=(0,0,0,0))
        self.star_btn.bind(on_press=lambda x: self.toggle_star())
        meta.add_widget(self.star_btn)
        root.add_widget(meta)

        # 题干
        self.stem_label = Label(text="", font_size=dp(17),
                                 color=get_color_from_hex(TEXT),
                                 halign="left", valign="top",
                                 size_hint_y=0.25)
        self.stem_label.bind(size=self.stem_label.setter("text_size"))
        root.add_widget(self.stem_label)

        # 选项区
        scroll = ScrollView()
        self.opt_layout = GridLayout(cols=1, spacing=dp(8),
                                      size_hint_y=None, padding=[0, dp(4)])
        self.opt_layout.bind(minimum_height=self.opt_layout.setter("height"))
        scroll.add_widget(self.opt_layout)
        root.add_widget(scroll)

        # 反馈
        self.fb_label = Label(text="", font_size=dp(15),
                               size_hint_y=None, height=dp(40),
                               color=get_color_from_hex(TEXT))
        root.add_widget(self.fb_label)

        # 下一题
        self.next_btn = Button(text="", font_size=dp(16),
                                background_color=get_color_from_hex(GREEN),
                                color=(1,1,1,1),
                                size_hint_y=None, height=dp(48))
        self.next_btn.bind(on_press=lambda x: self.next_q())
        self.next_btn.opacity = 0
        self.next_btn.disabled = True
        root.add_widget(self.next_btn)

    def go_home(self):
        """返回主页"""
        self._custom_qs = None
        self.sm.current = "home"

    def load_questions(self, subject_id=0, custom=None, title=""):
        """加载题目"""
        self._custom_qs = custom
        self._custom_title = title
        self.idx = 0
        self.correct_n = 0
        self.total_n = 0

        if custom:
            self.questions = list(custom)
        elif subject_id > 0:
            self.questions = self.app.db.get_questions(subject_id)
        else:
            self.questions = []

        random.shuffle(self.questions)

        name = self.app.db.get_subject_name(subject_id) or title or "刷题"
        self.title_label.text = name
        self.show_q(0)

    def show_q(self, index):
        if index >= len(self.questions):
            self.show_done()
            return
        self.idx = index
        self.answered = False
        q = self.questions[index]

        self.progress_label.text = f"第 {index+1}/{len(self.questions)}"

        # 题干
        self.stem_label.text = q["stem"]

        # 错题
        wc = q.get("wrong_count", 0)
        self.wrong_label.text = f"❌ 已错 {wc} 次" if wc else ""

        # 星标
        starred = q.get("starred", 0)
        self.star_btn.text = "⭐" if starred else "☆"
        self.star_btn.color = get_color_from_hex(STAR_COL) if starred else get_color_from_hex(MUTED)
        self.star_btn.opacity = 1

        # 选项
        opts = {"A": q["option_a"], "B": q["option_b"]}
        if q.get("option_c", ""): opts["C"] = q["option_c"]
        if q.get("option_d", ""): opts["D"] = q["option_d"]

        items = list(opts.items())
        random.shuffle(items)

        self.mapping = []
        self.q_buttons = []
        self.opt_layout.clear_widgets()
        letters = ["A", "B", "C", "D"]

        for i, (okey, txt) in enumerate(items):
            dl = letters[i]
            self.mapping.append((dl, okey))
            btn = Button(text=f"  {dl}. {txt}",
                         font_size=dp(15),
                         color=get_color_from_hex(TEXT),
                         background_normal="",
                         background_color=get_color_from_hex(CARD),
                         size_hint_y=None, height=dp(54))
            btn.display = dl
            btn.bind(on_press=lambda x, d=dl: self.submit(d))
            self.opt_layout.add_widget(btn)
            self.q_buttons.append(btn)

        # 重置反馈
        self.fb_label.text = ""
        self.fb_label.color = get_color_from_hex(TEXT)
        self.next_btn.opacity = 0
        self.next_btn.disabled = True

    def submit(self, display):
        if self.answered:
            return
        self.answered = True
        q = self.questions[self.idx]

        # 映射
        sel_orig = display
        for d, o in self.mapping:
            if d == display:
                sel_orig = o
                break

        correct = q["correct_answer"]
        is_correct = sel_orig == correct

        # 记录
        try:
            self.app.db.record_review(q["id"], is_correct)
        except Exception:
            pass

        self.total_n += 1
        if is_correct:
            self.correct_n += 1

        # 按钮染色
        for btn in self.q_buttons:
            btn.disabled = True
        for btn, (d, o) in zip(self.q_buttons, self.mapping):
            if o == correct:
                btn.background_color = get_color_from_hex(SUCCESS)
                btn.color = (1,1,1,1)
            elif d == display and not is_correct:
                btn.background_color = get_color_from_hex(ERR)
                btn.color = (1,1,1,1)

        ctext = q.get(f"option_{correct.lower()}", "")
        if is_correct:
            self.fb_label.text = "✅ 回答正确！"
            self.fb_label.color = get_color_from_hex(GREEN)
        else:
            self.fb_label.text = f"❌ 正确答案：{correct}. {ctext}"
            self.fb_label.color = get_color_from_hex(ERR)

        # 下一题按钮
        self.next_btn.opacity = 1
        self.next_btn.disabled = False
        self.next_btn.text = "📊 成绩" if self.idx >= len(self.questions)-1 else "⏭ 下一题"

    def next_q(self):
        n = self.idx + 1
        if n >= len(self.questions):
            self.show_done()
        else:
            self.show_q(n)

    def show_done(self):
        pct = round(self.correct_n/self.total_n*100, 1) if self.total_n else 0
        w = self.total_n - self.correct_n
        self.stem_label.text = (
            f"\n🎉 刷题完成！\n\n"
            f"📝 共 {len(self.questions)} 题\n"
            f"✅ 正确：{self.correct_n}\n"
            f"❌ 错误：{w}\n"
            f"🎯 正确率：{pct}%"
        )
        self.star_btn.opacity = 0
        self.wrong_label.text = ""
        self.opt_layout.clear_widgets()
        self.fb_label.text = ""
        self.next_btn.opacity = 0
        self.next_btn.disabled = True

    def toggle_star(self):
        q = self.questions[self.idx]
        if not q: return
        ns = self.app.db.toggle_star(q["id"])
        q["starred"] = 1 if ns else 0
        self.star_btn.text = "⭐" if ns else "☆"
        self.star_btn.color = get_color_from_hex(STAR_COL) if ns else get_color_from_hex(MUTED)


# ═══════════════════════════════════════════════════════════════════════════
#  App 入口
# ═══════════════════════════════════════════════════════════════════════════

from kivy.app import App

class QuizMobileApp(App):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.db = DatabaseManager()
        self.title = "刷题工具"

    def build(self):
        Window.clearcolor = get_color_from_hex(BG)
        self.sm = ScreenManager()
        self.sm.add_widget(HomeScreen(self.sm, name="home"))
        self.sm.add_widget(ReviewScreen(self.sm, name="review"))
        return self.sm

    def start_review(self, subject_id, sm):
        scr = sm.get_screen("review")
        scr.load_questions(subject_id=subject_id)
        sm.current = "review"

    def start_quick_ten(self, sm):
        all_q = []
        for s in self.db.get_subjects():
            for q in self.db.get_questions(s["id"]):
                q["_sub"] = s["name"]
            all_q.extend(self.db.get_questions(s["id"]))
        if not all_q:
            return
        random.shuffle(all_q)
        picked = all_q[:min(10, len(all_q))]
        scr = sm.get_screen("review")
        scr.load_questions(custom=picked, title="⚡ 快速 10 题")
        sm.current = "review"


if __name__ == "__main__":
    Window.size = (400, 720)
    QuizMobileApp().run()
