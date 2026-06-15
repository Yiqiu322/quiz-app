"""
app.py — 基于 CustomTkinter 的图形界面主程序

包含两个标签页：
  1. 题目智能录入  — 粘贴文本 → 解析 → 预览 → 保存
  2. 沉浸式复习    — 选题 → 答题 → 即时反馈 → 下一题
"""

import os
import random
import shutil
import tkinter as tk
from tkinter import messagebox
from typing import Optional

from PIL import Image

import customtkinter as ctk

from database import DatabaseManager
from parser import parse_questions, format_question_preview

# ─── 外观设置 ──────────────────────────────────────────────────────────────
# 使用浅色 + 绿色主题作为基础，再通过组件级颜色覆盖实现护眼效果

ctk.set_appearance_mode("light")           # 浅色基底（比纯暗黑更护眼）
ctk.set_default_color_theme("green")       # 森林绿主色调

# ─── 护眼主题色板 ──────────────────────────────────────────────────────────
# 所有颜色统一在此定义，下层代码直接引用常量名

COLOR_BG          = "#F2EFEA"   # 暖白米色   — 窗口主背景
COLOR_CARD        = "#FAF8F4"   # 卡片米白   — Frame 底色
COLOR_CARD_ALT    = "#F4F1EB"   # 深一级卡片  — 选项区 / 区分用
COLOR_PRIMARY     = "#3A7D5C"   # 森林绿     — 主按钮
COLOR_PRIMARY_HV  = "#2E6649"   # 森林绿悬停
COLOR_SECONDARY   = "#5B7B7A"   # 灰蓝绿     — 次要按钮
COLOR_SECONDARY_HV= "#4A6564"   # 灰蓝绿悬停
COLOR_TEXT        = "#2C3E50"   # 深炭灰     — 正文（避免纯黑刺眼）
COLOR_TEXT_MUTED  = "#6B7B8D"   # 浅灰       — 辅助文字
COLOR_SUCCESS     = "#6AAF7B"   # 柔和草绿   — 正确反馈
COLOR_ERROR       = "#D4786A"   # 柔和朱红   — 错误反馈
COLOR_BORDER      = "#D8D2C6"   # 边框色
COLOR_HIGHLIGHT   = "#4A90D9"   # 高亮蓝     — 链接 / 强调

# ─── 字体常量 ──────────────────────────────────────────────────────────────
# 统一字号体系，便于整体调整

FONT_FAMILY  = "Microsoft YaHei"
FONT_XS      = (FONT_FAMILY, 12)
FONT_SM      = (FONT_FAMILY, 13)
FONT_MD      = (FONT_FAMILY, 15)
FONT_LG      = (FONT_FAMILY, 17, "bold")
FONT_XL      = (FONT_FAMILY, 20, "bold")


# ─── 主应用类 ──────────────────────────────────────────────────────────────

class QuizApp(ctk.CTk):
    """本地选择题复习工具主窗口"""

    def __init__(self):
        super().__init__()

        self.db = DatabaseManager()
        self.images_dir = DatabaseManager.ensure_images_dir()

        # ── 窗口基础 ──
        self.title("📝 本地选择题复习工具")
        self.geometry("960x720")
        self.minsize(800, 600)
        # 窗口大小记忆
        self._load_window_geometry()
        self.configure(fg_color=COLOR_BG)  # 护眼暖白底色

        # ── 标签页 ──
        self.tab_view = ctk.CTkTabview(self, anchor="nw", fg_color=COLOR_BG)
        self.tab_view.pack(fill="both", expand=True, padx=12, pady=12)
        self.tab_view._segmented_button.configure(
            fg_color=COLOR_CARD_ALT,
            selected_color=COLOR_PRIMARY,
            selected_hover_color=COLOR_PRIMARY_HV,
            unselected_color=COLOR_CARD,
            unselected_hover_color=COLOR_BORDER,
            text_color=COLOR_TEXT,
            font=("Microsoft YaHei", 14),
        )

        self.tab_import = self.tab_view.add("📥 题目智能录入")
        self.tab_review = self.tab_view.add("🎯 沉浸式复习")
        self.tab_dashboard = self.tab_view.add("📊 学习统计")

        # ── 构建各标签页 ──
        self._build_import_tab()
        self._build_review_tab()
        self._build_dashboard_tab()

        # ── 窗口关闭时清理 ──
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # 键盘快捷键
        self._bind_shortcuts()

        # 标签切换时刷新统计
        self.tab_view.configure(command=self._on_tab_switch)
        # 首次加载统计
        self.after(500, self._refresh_dashboard)

        # ── 设置按钮 ──
        self.settings_btn = ctk.CTkButton(
            self.tab_view, text="⚙️", width=40,
            fg_color="transparent", hover_color=COLOR_CARD_ALT,
            text_color=COLOR_TEXT, font=("Microsoft YaHei", 18),
            command=self._open_settings,
        )
        self.settings_btn.place(relx=1.0, x=-50, y=6, anchor="ne")

        # ── 每日进度弹窗 ──
        self.after(1500, self._check_daily_progress)

    # ═════════════════════════════════════════════════════════════════════
    #  标签页一：题目智能录入
    # ═════════════════════════════════════════════════════════════════════

    def _build_import_tab(self):
        """构建「题目智能录入」标签页"""
        # ── 顶部：学科选择 / 新建 ──
        top_frame = ctk.CTkFrame(self.tab_import, fg_color=COLOR_CARD, border_color=COLOR_BORDER, border_width=1)
        top_frame.pack(fill="x", padx=10, pady=(10, 0))

        ctk.CTkLabel(top_frame, text="学科分类：", font=FONT_MD, text_color=COLOR_TEXT).pack(
            side="left", padx=(16, 8), pady=12
        )

        self.import_subject_var = ctk.StringVar()
        self.import_subject_menu = ctk.CTkOptionMenu(
            top_frame,
            variable=self.import_subject_var,
            values=self._get_subject_names(),
            width=200,
            fg_color=COLOR_CARD_ALT,
            button_color=COLOR_PRIMARY,
            button_hover_color=COLOR_PRIMARY_HV,
            text_color=COLOR_TEXT,
            dropdown_fg_color=COLOR_CARD,
            dropdown_text_color=COLOR_TEXT,
            dropdown_hover_color=COLOR_CARD_ALT,
            font=FONT_SM,
        )
        self.import_subject_menu.pack(side="left", padx=(0, 10))

        self.new_subject_entry = ctk.CTkEntry(
            top_frame, placeholder_text="新建学科名称…", width=180,
            fg_color=COLOR_CARD, text_color=COLOR_TEXT,
            placeholder_text_color=COLOR_TEXT_MUTED,
            border_color=COLOR_BORDER, font=FONT_SM,
        )
        self.new_subject_entry.pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            top_frame, text="➕ 新建", width=80,
            fg_color=COLOR_PRIMARY, hover_color=COLOR_PRIMARY_HV,
            text_color="white", font=FONT_SM,
            command=self._on_new_subject,
        ).pack(side="left", pady=12)

        # ── 中间：大文本输入区 ──
        input_frame = ctk.CTkFrame(self.tab_import, fg_color=COLOR_CARD, border_color=COLOR_BORDER, border_width=1)
        input_frame.pack(fill="both", expand=True, padx=10, pady=10)

        input_label_frame = ctk.CTkFrame(input_frame, fg_color="transparent")
        input_label_frame.pack(fill="x", pady=(6, 2), padx=8)

        ctk.CTkLabel(
            input_label_frame,
            text="📋 在此粘贴题目文本（支持批量）",
            font=FONT_MD, text_color=COLOR_TEXT,
        ).pack(side="left")

        self.char_count_label = ctk.CTkLabel(
            input_label_frame, text="字符：0", font=FONT_XS, text_color=COLOR_TEXT_MUTED,
        )
        self.char_count_label.pack(side="right")

        self.text_input = ctk.CTkTextbox(
            input_frame, height=220,
            font=("Microsoft YaHei", 14),
            fg_color=COLOR_CARD, text_color=COLOR_TEXT,
            border_color=COLOR_BORDER, border_width=1,
        )
        self.text_input.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.text_input.bind("<KeyRelease>", self._on_text_change)

        # ── 操作按钮行 ──
        btn_frame = ctk.CTkFrame(self.tab_import, fg_color="transparent")
        btn_frame.pack(fill="x", padx=10, pady=(0, 10))

        ctk.CTkButton(
            btn_frame, text="🔍 解析 & 预览", width=140,
            fg_color=COLOR_PRIMARY, hover_color=COLOR_PRIMARY_HV,
            text_color="white", font=FONT_SM,
            command=self._on_parse,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_frame, text="💾 保存入库", width=140,
            fg_color=COLOR_SECONDARY, hover_color=COLOR_SECONDARY_HV,
            text_color="white", font=FONT_SM,
            command=self._on_save,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_frame, text="🖼 添加图片", width=110,
            fg_color=COLOR_SECONDARY, hover_color=COLOR_SECONDARY_HV,
            text_color="white", font=FONT_SM,
            command=self._on_import_image,
        ).pack(side="left", padx=(0, 10))

        self.parse_status_label = ctk.CTkLabel(
            btn_frame, text="", font=FONT_SM, text_color=COLOR_PRIMARY,
        )
        self.parse_status_label.pack(side="left", padx=(10, 0))

        ctk.CTkButton(
            btn_frame, text="📤 导出", width=80,
            fg_color=COLOR_CARD_ALT, hover_color=COLOR_BORDER,
            text_color=COLOR_TEXT, font=FONT_XS,
            command=self._on_export,
        ).pack(side="right", padx=(0, 4))

        ctk.CTkButton(
            btn_frame, text="📥 导入", width=80,
            fg_color=COLOR_CARD_ALT, hover_color=COLOR_BORDER,
            text_color=COLOR_TEXT, font=FONT_XS,
            command=self._on_import_json,
        ).pack(side="right", padx=(0, 4))

        ctk.CTkButton(
            btn_frame, text="🗑 清空", width=80,
            fg_color=COLOR_CARD_ALT, hover_color=COLOR_BORDER,
            text_color=COLOR_TEXT_MUTED, font=FONT_SM,
            command=self._on_clear_input,
        ).pack(side="right")

        # ── 预览区 ──
        preview_frame = ctk.CTkFrame(self.tab_import, fg_color=COLOR_CARD, border_color=COLOR_BORDER, border_width=1)
        preview_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        ctk.CTkLabel(
            preview_frame, text="预览解析结果：", font=FONT_SM, text_color=COLOR_TEXT
        ).pack(anchor="w", pady=(6, 2), padx=12)

        self.preview_text = ctk.CTkTextbox(
            preview_frame, height=150,
            font=("Consolas", 13),
            fg_color=COLOR_CARD, text_color=COLOR_TEXT,
            border_color=COLOR_BORDER, border_width=1,
            state="disabled",
        )
        self.preview_text.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        # 暂存解析结果
        self._parsed_questions: list[dict] = []

        # ── 题目管理区 ──
        mgmt_frame = ctk.CTkFrame(self.tab_import, fg_color=COLOR_CARD, border_color=COLOR_BORDER, border_width=1)
        mgmt_frame.pack(fill="x", padx=10, pady=(0, 10))

        mgmt_label_frame = ctk.CTkFrame(mgmt_frame, fg_color="transparent")
        mgmt_label_frame.pack(fill="x", pady=(6, 2), padx=12)

        ctk.CTkLabel(
            mgmt_label_frame, text="📂 管理已入库题目", font=FONT_SM, text_color=COLOR_TEXT
        ).pack(side="left")

        self.mgmt_search_entry = ctk.CTkEntry(
            mgmt_label_frame, placeholder_text="搜索题干关键词…", width=200,
            fg_color=COLOR_CARD, text_color=COLOR_TEXT,
            placeholder_text_color=COLOR_TEXT_MUTED,
            border_color=COLOR_BORDER, font=FONT_XS,
        )
        self.mgmt_search_entry.pack(side="right", padx=(0, 6))
        self.mgmt_search_entry.bind("<KeyRelease>", lambda e: self._refresh_question_list())

        self.mgmt_listbox = tk.Listbox(
            mgmt_frame, height=5,
            font=("Microsoft YaHei", 11),
            bg=COLOR_CARD, fg=COLOR_TEXT,
            selectbackground=COLOR_PRIMARY, selectforeground="white",
            borderwidth=1, relief="solid",
        )
        self.mgmt_listbox.pack(fill="x", padx=12, pady=(0, 4))
        self.mgmt_listbox.bind("<<ListboxSelect>>", self._on_mgmt_select)

        mgmt_btn_frame = ctk.CTkFrame(mgmt_frame, fg_color="transparent")
        mgmt_btn_frame.pack(fill="x", padx=12, pady=(0, 8))

        self.mgmt_load_btn = ctk.CTkButton(
            mgmt_btn_frame, text="📝 加载到编辑区", width=130,
            fg_color=COLOR_SECONDARY, hover_color=COLOR_SECONDARY_HV,
            text_color="white", font=FONT_XS,
            command=self._on_mgmt_load,
        )
        self.mgmt_load_btn.pack(side="left", padx=(0, 8))

        self.mgmt_delete_btn = ctk.CTkButton(
            mgmt_btn_frame, text="🗑 删除选中", width=100,
            fg_color="#D4786A", hover_color="#c06050",
            text_color="white", font=FONT_XS,
            command=self._on_mgmt_delete,
        )
        self.mgmt_delete_btn.pack(side="left", padx=(0, 8))

        self.mgmt_star_btn = ctk.CTkButton(
            mgmt_btn_frame, text="⭐ 切换星标", width=100,
            fg_color=COLOR_CARD_ALT, hover_color=COLOR_BORDER,
            text_color=COLOR_TEXT, font=FONT_XS,
            command=self._on_mgmt_toggle_star,
        )
        self.mgmt_star_btn.pack(side="left")

        self.mgmt_status_label = ctk.CTkLabel(
            mgmt_btn_frame, text="", font=FONT_XS, text_color=COLOR_TEXT_MUTED,
        )
        self.mgmt_status_label.pack(side="right")

        # 数据
        self._mgmt_questions: list[dict] = []
        self._mgmt_selected_id: Optional[int] = None

    # ── 导入标签页事件 ──

    def _get_subject_names(self) -> list[str]:
        return [s["name"] for s in self.db.get_subjects()] or ["——请先新建学科——"]

    def _refresh_subject_menu(self):
        """刷新学科下拉菜单"""
        names = self._get_subject_names()
        self.import_subject_menu.configure(values=names)
        if names:
            self.import_subject_var.set(names[0])
        self._refresh_review_subject_menu()
        self._refresh_question_list()

    def _on_new_subject(self):
        name = self.new_subject_entry.get().strip()
        if not name:
            messagebox.showwarning("提示", "请输入学科名称")
            return
        self.db.add_subject(name)
        self.new_subject_entry.delete(0, "end")
        self._refresh_subject_menu()
        self.parse_status_label.configure(text=f"✅ 学科「{name}」已创建")

    def _on_text_change(self, _=None):
        text = self.text_input.get("0.0", "end-1c")
        self.char_count_label.configure(text=f"字符：{len(text)}")

    def _on_parse(self):
        """解析文本并在预览区展示"""
        text = self.text_input.get("0.0", "end-1c").strip()
        if not text:
            messagebox.showwarning("提示", "请先粘贴题目文本")
            return

        self._parsed_questions = parse_questions(text)
        n = len(self._parsed_questions)

        self.preview_text.configure(state="normal")
        self.preview_text.delete("0.0", "end")

        if n == 0:
            self.preview_text.insert("0.0", "⚠️ 未解析出任何题目，请检查格式。\n\n"
                                            "支持的格式示例：\n"
                                            "1. 题干内容\n"
                                            "A. 选项A\n"
                                            "B. 选项B\n"
                                            "C. 选项C\n"
                                            "D. 选项D\n"
                                            "答案：A\n")
            self.parse_status_label.configure(text="❌ 解析失败", text_color="#ff6b6b")
        else:
            for i, q in enumerate(self._parsed_questions, 1):
                self.preview_text.insert("end", f"──── 第 {i} 题 ────\n")
                self.preview_text.insert("end", format_question_preview(q) + "\n")
            self.preview_text.insert("end", f"共解析出 {n} 道题 ✓")
            self.parse_status_label.configure(
                text=f"✅ 解析成功：共 {n} 道题，请确认后保存",
                text_color="#69db7c",
            )

        self.preview_text.configure(state="disabled")

    def _on_save(self):
        """将解析出的题目保存到数据库"""
        if not self._parsed_questions:
            messagebox.showwarning("提示", "请先点击「解析 & 预览」")
            return

        subject_name = self.import_subject_var.get()
        if not subject_name or subject_name.startswith("——"):
            messagebox.showwarning("提示", "请先选择或新建一个学科")
            return

        # 获取 subject_id（若名称未入库则自动创建）
        subject_id = self.db.add_subject(subject_name)
        count = self.db.add_questions_batch(subject_id, self._parsed_questions)

        self.parse_status_label.configure(
            text=f"✅ 已保存 {count} 道题到「{subject_name}」",
            text_color="#69db7c",
        )
        self._parsed_questions = []
        # 清空预览
        self.preview_text.configure(state="normal")
        self.preview_text.delete("0.0", "end")
        self.preview_text.configure(state="disabled")

        messagebox.showinfo("保存成功", f"共 {count} 道题已保存到「{subject_name}」")

    def _on_clear_input(self):
        self.text_input.delete("0.0", "end")
        self._parsed_questions = []
        self.preview_text.configure(state="normal")
        self.preview_text.delete("0.0", "end")
        self.preview_text.configure(state="disabled")
        self.parse_status_label.configure(text="")

    # ── 题目管理 / 导入导出 ──────────────────────────────────────────────

    def _refresh_question_list(self):
        """刷新题目管理列表"""
        subject_name = self.import_subject_var.get()
        if not subject_name or subject_name.startswith("——"):
            return
        subjects = self.db.get_subjects()
        subject = next((s for s in subjects if s["name"] == subject_name), None)
        if not subject:
            return
        keyword = self.mgmt_search_entry.get().strip()
        if keyword:
            self._mgmt_questions = self.db.search_questions(subject["id"], keyword)
        else:
            self._mgmt_questions = self.db.get_questions(subject["id"])
        self.mgmt_listbox.delete(0, "end")
        for q in self._mgmt_questions:
            star = "⭐" if q.get("starred") else "  "
            wrong = f" [!{q.get('wrong_count',0)}]" if q.get("wrong_count", 0) > 0 else "    "
            display = q["stem"][:50].replace("\n", " ")
            self.mgmt_listbox.insert("end", f"{star}{wrong} {display}")
        self.mgmt_status_label.configure(text=f"共 {len(self._mgmt_questions)} 题")

    def _on_mgmt_select(self, event=None):
        sel = self.mgmt_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx < len(self._mgmt_questions):
            self._mgmt_selected_id = self._mgmt_questions[idx]["id"]

    def _on_mgmt_load(self):
        """将选中题目加载到文本编辑区"""
        if self._mgmt_selected_id is None:
            messagebox.showwarning("提示", "请先选择一道题目")
            return
        q = next((q for q in self._mgmt_questions if q["id"] == self._mgmt_selected_id), None)
        if not q:
            return
        text = q["stem"] + "\n"
        text += f"A. {q['option_a']}\n"
        text += f"B. {q['option_b']}\n"
        if q.get("option_c", ""): text += f"C. {q['option_c']}\n"
        if q.get("option_d", ""): text += f"D. {q['option_d']}\n"
        text += f"正确答案：{q['correct_answer']}"
        self.text_input.delete("0.0", "end")
        self.text_input.insert("0.0", text)
        self.parse_status_label.configure(
            text=f"已加载题目 #{q['id']}，修改后重新解析并保存",
            text_color=COLOR_PRIMARY,
        )

    def _on_mgmt_delete(self):
        if self._mgmt_selected_id is None:
            messagebox.showwarning("提示", "请先选择一道题目")
            return
        if not messagebox.askyesno("确认删除", "确定要删除这道题吗？"):
            return
        self.db.delete_question(self._mgmt_selected_id)
        self._mgmt_selected_id = None
        self._refresh_question_list()
        self.mgmt_status_label.configure(text="✅ 已删除")

    def _on_mgmt_toggle_star(self):
        if self._mgmt_selected_id is None:
            messagebox.showwarning("提示", "请先选择一道题目")
            return
        new_state = self.db.toggle_star(self._mgmt_selected_id)
        self._refresh_question_list()
        self.mgmt_status_label.configure(text=f"⭐ {'已星标' if new_state else '取消星标'}")

    def _on_toggle_star_review(self):
        """在复习中切换星标"""
        if not hasattr(self, '_current_question_id') or self._current_question_id is None:
            return
        new_state = self.db.toggle_star(self._current_question_id)
        self.star_btn.configure(
            text=f"{'⭐' if new_state else '☆'} {'已星标' if new_state else '标记星标'}",
            text_color=COLOR_PRIMARY if new_state else COLOR_TEXT_MUTED,
        )

    def _on_export(self):
        """导出所有题目到 JSON 文件"""
        from tkinter import filedialog
        data = self.db.export_all_questions()
        if not data:
            messagebox.showwarning("提示", "数据库中没有题目可导出")
            return
        file_path = filedialog.asksaveasfilename(
            title="导出题目", defaultextension=".json",
            filetypes=[("JSON 文件", "*.json")],
            initialfile="quiz_export.json",
        )
        if not file_path:
            return
        import json
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump({"version": 1, "questions": data}, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("导出成功", f"共导出 {len(data)} 道题到\n{file_path}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def _on_import_json(self):
        """从 JSON 文件导入题目"""
        from tkinter import filedialog
        file_path = filedialog.askopenfilename(
            title="导入题目", filetypes=[("JSON 文件", "*.json")],
        )
        if not file_path:
            return
        import json
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            questions = data.get("questions", [])
            if not questions:
                messagebox.showwarning("提示", "JSON 文件中没有题目数据")
                return
            count = self.db.import_from_json(questions)
            self._refresh_subject_menu()
            messagebox.showinfo("导入成功", f"共导入 {count} 道题")
        except Exception as e:
            messagebox.showerror("导入失败", f"文件格式错误：{e}")

    def _on_import_image(self):
        """打开文件对话框选择图片，复制到 images/ 目录，并插入标记到文本"""
        from tkinter import filedialog
        file_path = filedialog.askopenfilename(
            title="选择图片",
            filetypes=[
                ("图片文件", "*.png *.jpg *.jpeg *.gif *.bmp"),
                ("所有文件", "*.*"),
            ],
        )
        if not file_path:
            return

        # 校验文件是否存在
        if not os.path.exists(file_path):
            messagebox.showerror("错误", "文件不存在")
            return

        # 复制到 images/ 目录
        filename = os.path.basename(file_path)
        dest = os.path.join(self.images_dir, filename)
        try:
            shutil.copy2(file_path, dest)
        except Exception as e:
            messagebox.showerror("错误", f"图片复制失败：{e}")
            return

        # 在文本输入区的光标位置插入标记
        try:
            cursor_pos = self.text_input.index("insert")
            self.text_input.insert(cursor_pos, f"{{img:{filename}}}")
        except Exception:
            # 若光标获取失败，追加到末尾
            self.text_input.insert("end", f"\n{{img:{filename}}}")

        self._on_text_change()
        self.parse_status_label.configure(
            text=f"✅ 已导入图片：{filename}",
            text_color=COLOR_SUCCESS,
        )

    # ═════════════════════════════════════════════════════════════════════
    #  标签页二：沉浸式复习
    # ═════════════════════════════════════════════════════════════════════

    def _build_review_tab(self):
        """构建「沉浸式复习」标签页（护眼视觉版）"""
        # ── 顶栏：学科选择 ──
        top_frame = ctk.CTkFrame(self.tab_review, fg_color=COLOR_CARD, border_color=COLOR_BORDER, border_width=1)
        top_frame.pack(fill="x", padx=10, pady=(10, 0))

        ctk.CTkLabel(
            top_frame, text="📚 选择学科：", font=FONT_MD, text_color=COLOR_TEXT,
        ).pack(side="left", padx=(16, 8), pady=12)

        self.review_subject_var = ctk.StringVar()
        self.review_subject_menu = ctk.CTkOptionMenu(
            top_frame,
            variable=self.review_subject_var,
            values=self._get_subject_names(),
            width=200,
            fg_color=COLOR_CARD_ALT,
            button_color=COLOR_PRIMARY,
            button_hover_color=COLOR_PRIMARY_HV,
            text_color=COLOR_TEXT,
            dropdown_fg_color=COLOR_CARD,
            dropdown_text_color=COLOR_TEXT,
            dropdown_hover_color=COLOR_CARD_ALT,
            font=FONT_SM,
        )
        self.review_subject_menu.pack(side="left", padx=(0, 20))

        # ── 设置区 ──
        settings_frame = ctk.CTkFrame(self.tab_review, fg_color=COLOR_CARD, border_color=COLOR_BORDER, border_width=1)
        settings_frame.pack(fill="x", padx=10, pady=(10, 0))

        ctk.CTkLabel(
            settings_frame, text="⚙️ 复习设置", font=FONT_MD, text_color=COLOR_TEXT,
        ).pack(anchor="w", pady=(8, 4), padx=16)

        self.shuffle_questions_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            settings_frame, text="🔀 随机打乱题目顺序",
            variable=self.shuffle_questions_var,
            font=FONT_SM, text_color=COLOR_TEXT,
            fg_color=COLOR_PRIMARY, hover_color=COLOR_PRIMARY_HV,
            checkmark_color="white",
        ).pack(anchor="w", padx=(24, 0), pady=3)

        self.shuffle_options_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            settings_frame, text="🔁 随机打乱选项顺序",
            variable=self.shuffle_options_var,
            font=FONT_SM, text_color=COLOR_TEXT,
            fg_color=COLOR_PRIMARY, hover_color=COLOR_PRIMARY_HV,
            checkmark_color="white",
        ).pack(anchor="w", padx=(24, 0), pady=3)

        self.filter_wrong_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            settings_frame, text="❌ 只刷错题（wrong_count >= 1）",
            variable=self.filter_wrong_var,
            font=FONT_XS, text_color=COLOR_TEXT,
            fg_color=COLOR_PRIMARY, hover_color=COLOR_PRIMARY_HV,
            checkmark_color="white",
        ).pack(anchor="w", padx=(24, 0), pady=3)

        self.filter_star_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            settings_frame, text="⭐ 只刷星标题",
            variable=self.filter_star_var,
            font=FONT_XS, text_color=COLOR_TEXT,
            fg_color=COLOR_PRIMARY, hover_color=COLOR_PRIMARY_HV,
            checkmark_color="white",
        ).pack(anchor="w", padx=(24, 0), pady=3)

        ctk.CTkButton(
            settings_frame, text="🚀 开始复习",
            width=180, height=40,
            font=("Microsoft YaHei", 16, "bold"),
            fg_color=COLOR_PRIMARY, hover_color=COLOR_PRIMARY_HV,
            text_color="white",
            command=self._on_start_review,
        ).pack(anchor="w", padx=(24, 0), pady=(10, 12))

        ctk.CTkButton(
            settings_frame, text="⚡ 快速刷 10 题",
            width=180, height=36,
            font=("Microsoft YaHei", 14),
            fg_color=COLOR_SECONDARY, hover_color=COLOR_SECONDARY_HV,
            text_color="white",
            command=self._on_quick_ten,
        ).pack(anchor="w", padx=(24, 0), pady=(4, 12))

        # ── 答题区（可滚动卡片，图片再大也不会撑爆） ──
        self.review_card = ctk.CTkScrollableFrame(
            self.tab_review,
            fg_color=COLOR_CARD,
            border_color=COLOR_BORDER,
            border_width=1,
            scrollbar_button_color=COLOR_PRIMARY,
            scrollbar_button_hover_color=COLOR_PRIMARY_HV,
        )
        self.review_card.pack(fill="both", expand=True, padx=10, pady=10)

        # 题目编号
        self.question_header = ctk.CTkLabel(
            self.review_card, text="",
            font=("Microsoft YaHei", 18, "bold"),
            text_color=COLOR_PRIMARY,
            anchor="w", justify="left", wraplength=800,
        )
        self.question_header.pack(anchor="w", pady=(10, 2), padx=16)

        # 题干
        self.question_stem = ctk.CTkLabel(
            self.review_card, text="",
            font=("Microsoft YaHei", 16),
            text_color=COLOR_TEXT,
            anchor="w", justify="left", wraplength=820,
        )
        self.question_stem.pack(anchor="w", pady=(0, 6), padx=16)

        # 星标按钮（固定在题干下方）
        self.star_btn = ctk.CTkButton(
            self.review_card, text="☆ 标记星标", width=110, height=26,
            fg_color="transparent", hover_color=COLOR_CARD_ALT,
            text_color=COLOR_TEXT_MUTED, font=("Microsoft YaHei", 12),
            command=self._on_toggle_star_review,
        )
        self.star_btn.pack(anchor="w", padx=20, pady=(0, 4))

        # 分隔线
        ctk.CTkFrame(self.review_card, height=1, fg_color=COLOR_BORDER).pack(
            fill="x", padx=16, pady=0
        )

        # ── 题干 + 图片动态渲染区（紧凑） ──
        self.stem_display_frame = ctk.CTkFrame(self.review_card, fg_color="transparent")
        self.stem_display_frame.pack(fill="x", padx=16, pady=(4, 4))
        self._stem_image_widgets: list[ctk.CTkLabel] = []

        # ── 选项容器（紧凑） ──
        self.options_frame = ctk.CTkFrame(
            self.review_card,
            fg_color=COLOR_CARD_ALT,
            border_color=COLOR_BORDER,
            border_width=1,
        )
        self.options_frame.pack(fill="both", expand=True, padx=16, pady=6)

        # 选项 RadioButton 列表（动态重建）
        self.option_radios: list[ctk.CTkRadioButton] = []
        self.option_var = tk.StringVar(value="")

        # ── 反馈区 ──
        self.feedback_frame = ctk.CTkFrame(self.review_card, fg_color="transparent")
        self.feedback_frame.pack(fill="x", padx=20, pady=(4, 2))

        self.feedback_label = ctk.CTkLabel(
            self.feedback_frame, text="",
            font=("Microsoft YaHei", 18, "bold"),
        )
        self.feedback_label.pack(pady=(6, 2))

        self.feedback_detail = ctk.CTkLabel(
            self.feedback_frame, text="",
            font=("Microsoft YaHei", 15),
            wraplength=800, anchor="w", justify="left",
        )
        self.feedback_detail.pack(pady=(0, 4), padx=16)

        # ── 按钮行（紧凑） ──
        action_frame = ctk.CTkFrame(self.review_card, fg_color="transparent")
        action_frame.pack(fill="x", padx=16, pady=(4, 10))

        self.submit_btn = ctk.CTkButton(
            action_frame, text="✅ 提交答案", width=150, height=38,
            fg_color=COLOR_PRIMARY, hover_color=COLOR_PRIMARY_HV,
            text_color="white", font=("Microsoft YaHei", 15, "bold"),
            command=self._on_submit,
        )
        self.submit_btn.pack(side="left", padx=(0, 12))

        self.next_btn = ctk.CTkButton(
            action_frame, text="⏭ 下一题", width=130, height=38,
            fg_color=COLOR_SECONDARY, hover_color=COLOR_SECONDARY_HV,
            text_color="white", font=("Microsoft YaHei", 14),
            command=self._on_next,
        )
        self.next_btn.pack(side="left")

        self.progress_label = ctk.CTkLabel(
            action_frame, text="",
            font=FONT_SM, text_color=COLOR_TEXT_MUTED,
        )
        self.progress_label.pack(side="right", padx=(0, 4))

        self.wrong_count_label = ctk.CTkLabel(
            action_frame, text="",
            font=FONT_XS, text_color=COLOR_TEXT_MUTED,
        )
        self.wrong_count_label.pack(side="right", padx=(8, 0))

        # ── 初始状态 ──
        self._review_questions: list[dict] = []
        self._review_index = 0
        self._current_mapping: list[tuple[str, str]] = []  # (display_label, original_key)
        self._answered = False
        self._stats = {
            "subject_name": "",
            "total": 0,
            "answered": 0,
            "correct": 0,
        }
        self._set_review_ui_enabled(False)

    # ── 复习标签页事件 ──

    def _refresh_review_subject_menu(self):
        names = self._get_subject_names()
        self.review_subject_menu.configure(values=names)
        if names:
            self.review_subject_var.set(names[0])

    def _reset_review_state(self):
        """重置复习状态"""
        self._review_questions = []
        self._review_index = 0
        self._current_mapping = []
        self._stem_image_widgets = []
        self._answered = False
        self._stats = {
            "subject_name": "",
            "total": 0,
            "answered": 0,
            "correct": 0,
        }
        self._set_review_ui_enabled(False)

    def _set_review_ui_enabled(self, enabled: bool):
        """启用 / 禁用答题区控件"""
        state = "normal" if enabled else "disabled"
        self.submit_btn.configure(state=state)
        for rb in self.option_radios:
            rb.configure(state=state)

    def _clear_option_radios(self):
        """清空并销毁所有选项按钮"""
        for rb in self.option_radios:
            rb.destroy()
        self.option_radios.clear()

    def _on_start_review(self):
        """加载选定学科的题目进入复习模式"""
        subject_name = self.review_subject_var.get()
        if not subject_name or subject_name.startswith("——"):
            messagebox.showwarning("提示", "请先选择学科（可在录入页创建）")
            return

        subjects = self.db.get_subjects()
        subject = next((s for s in subjects if s["name"] == subject_name), None)
        if not subject:
            messagebox.showwarning("提示", f"学科「{subject_name}」不存在")
            return

        # 应用筛选
        if self.filter_wrong_var.get():
            questions = self.db.get_wrong_questions(subject["id"], min_wrong=1)
        elif self.filter_star_var.get():
            questions = self.db.get_starred_questions(subject["id"])
        else:
            questions = self.db.get_questions(subject["id"])
        if not questions:
            msg = f"「{subject_name}」下还没有题目"
            if self.filter_wrong_var.get():
                msg += "，或没有错题记录"
            elif self.filter_star_var.get():
                msg += "，或没有星标题目"
            messagebox.showwarning("提示", msg)
            return

        # 初始化统计数据
        self._stats = {
            "subject_name": subject_name,
            "total": len(questions),
            "answered": 0,
            "correct": 0,
        }

        # 随机打乱题目顺序
        self._review_questions = list(questions)
        if self.shuffle_questions_var.get():
            random.shuffle(self._review_questions)

        self._review_index = 0
        self._show_question(0)
        self._set_review_ui_enabled(True)
        self._update_progress()

    def _on_quick_ten(self):
        """从所有学科随机抽 10 道题快速刷"""
        subjects = self.db.get_subjects()
        if not subjects:
            messagebox.showwarning("提示", "还没有学科，请先录入题目")
            return
        all_qs = []
        for s in subjects:
            qs = self.db.get_questions(s["id"])
            for q in qs:
                q["_subject_name"] = s["name"]
            all_qs.extend(qs)
        if not all_qs:
            messagebox.showwarning("提示", "还没有题目，请先录入")
            return
        random.shuffle(all_qs)
        picked = all_qs[:min(10, len(all_qs))]
        self._review_questions = picked
        self._stats = {
            "subject_name": f"随机 {len(picked)} 题（全学科）",
            "total": len(picked),
            "answered": 0,
            "correct": 0,
        }
        self._review_index = 0
        self._show_question(0)
        self._set_review_ui_enabled(True)
        self._update_progress()

    def _show_question(self, index: int):
        """显示第 index 道题（从 0 开始）"""
        if index >= len(self._review_questions):
            self._show_completion()
            return

        q = self._review_questions[index]

        # ── 1. 销毁上一题的全部旧 RadioButton ──
        self._clear_option_radios()

        # ── 2. 复位 UI 状态 ──
        self.option_var.set("")
        self._answered = False
        self.submit_btn.configure(state="normal", text="✅ 提交答案")
        self.feedback_label.configure(text="")
        self.feedback_detail.configure(text="")

        # ── 3. 题号 + 题干 ──
        self.question_header.configure(
            text=f"第 {index + 1} 题（共 {self._stats['total']} 题）",
            text_color=COLOR_PRIMARY,
        )

        # ── 4. 渲染题干（支持纯文本 + {img:...} 图片混合） ──
        # 先销毁上一题的动态图片组件
        for w in self._stem_image_widgets:
            w.destroy()
        self._stem_image_widgets.clear()

        # 用 parser 拆分段
        from parser import split_text_with_images
        segments = split_text_with_images(q["stem"])

        # 题干文本 label 默认隐藏，后面根据是否有纯文本段决定是否显示
        self.question_stem.configure(text="")

        has_text = False
        for seg in segments:
            if seg["type"] == "text":
                txt = seg["content"].strip()
                if txt:
                    lbl = ctk.CTkLabel(
                        self.stem_display_frame,
                        text=txt,
                        font=("Microsoft YaHei", 17, "bold"),
                        text_color=COLOR_TEXT,
                        anchor="w", justify="left", wraplength=800,
                    )
                    lbl.pack(anchor="w", fill="x", pady=(0, 6))
                    self._stem_image_widgets.append(lbl)
                    has_text = True
            else:
                # 图片段
                img_path = os.path.join(self.images_dir, seg["file"])
                if os.path.exists(img_path):
                    try:
                        pil_img = Image.open(img_path)
                        # 缩小图片以适配屏幕（避免图片撑爆题目区域）
                        max_w = 360
                        max_h = 200
                        pil_img.thumbnail((max_w, max_h), Image.LANCZOS)
                        new_size = pil_img.size
                        ctk_img = ctk.CTkImage(
                            light_image=pil_img,
                            dark_image=pil_img,
                            size=new_size,
                        )
                        img_lbl = ctk.CTkLabel(
                            self.stem_display_frame,
                            image=ctk_img,
                            text="",
                        )
                        img_lbl.pack(anchor="w", pady=(4, 8))
                        self._stem_image_widgets.append(img_lbl)
                    except Exception as e:
                        # 图片加载失败，显示占位文字
                        err_lbl = ctk.CTkLabel(
                            self.stem_display_frame,
                            text=f"[图片加载失败: {seg['file']}]",
                            text_color=COLOR_ERROR,
                            font=("Microsoft YaHei", 13),
                        )
                        err_lbl.pack(anchor="w")
                        self._stem_image_widgets.append(err_lbl)
                else:
                    err_lbl = ctk.CTkLabel(
                        self.stem_display_frame,
                        text=f"[图片未找到: {seg['file']}]",
                        text_color=COLOR_ERROR,
                        font=("Microsoft YaHei", 13),
                    )
                    err_lbl.pack(anchor="w", pady=(4, 8))
                    self._stem_image_widgets.append(err_lbl)

        # 星标状态
        self._current_question_id = q["id"]
        is_starred = q.get("starred", 0)
        self.star_btn.configure(
            text=f"{'⭐' if is_starred else '☆'} {'已星标' if is_starred else '标记星标'}",
            text_color=COLOR_PRIMARY if is_starred else COLOR_TEXT_MUTED,
        )

        # 错题次数
        wc = q.get("wrong_count", 0)
        self.wrong_count_label.configure(
            text=f"❌ 已错 {wc} 次" if wc > 0 else "",
        )

        # ── 5. 构建选项列表 ──
        #    items = [("A", "并发性"), ("B", "共享性"), ...]
        items = [
            ("A", q.get("option_a", "")),
            ("B", q.get("option_b", "")),
            ("C", q.get("option_c", "")),
            ("D", q.get("option_d", "")),
        ]
        # 过滤掉空选项（判断题只有 A/B，多选题等场景也可能缺项）
        items = [(k, v) for k, v in items if v.strip()]

        # 若开启"随机打乱选项"，就打乱顺序
        if self.shuffle_options_var.get():
            random.shuffle(items)

        # ── 6. 创建映射 + 动态创建 RadioButton ──
        # 映射表：(显示用标签, 原始选项字母) — 用于提交时正确判定答案
        self._current_mapping = []
        display_letters = ["A", "B", "C", "D"]
        for display_index, (original_key, text) in enumerate(items):
            display_label = display_letters[display_index]
            self._current_mapping.append((display_label, original_key))

            rb = ctk.CTkRadioButton(
                master=self.options_frame,
                text=f"{display_label}. {text}",
                variable=self.option_var,
                value=display_label,
                font=("Microsoft YaHei", 15),
                text_color=COLOR_TEXT,
                fg_color=COLOR_PRIMARY,
                hover_color=COLOR_PRIMARY_HV,
                border_color=COLOR_BORDER,
                border_width_unchecked=2,
                border_width_checked=6,
            )
            rb.pack(anchor="w", padx=16, pady=5)
            self.option_radios.append(rb)

        # ── 6. 强制全布局刷新（关键：让新创建的 widget 进入渲染管线）──
        self.update_idletasks()

    def _on_submit(self):
        """提交当前答案，判断正误并反馈"""
        if self._answered:
            return

        selected = self.option_var.get()
        if not selected:
            messagebox.showwarning("提示", "请选择一个选项")
            return

        q = self._review_questions[self._review_index]

        # ── 通过映射找到用户所选对应的原始选项字母 ──
        selected_original = None
        for display_label, original_key in self._current_mapping:
            if display_label == selected:
                selected_original = original_key
                break

        if selected_original is None:
            # 安全兜底：映射查找失败，尝试直接用 selected 作为原始值
            selected_original = selected

        correct_original = q["correct_answer"]  # 'A' | 'B' | 'C' | 'D'

        # 消除任何格式差异（大小写、空白）
        is_correct = selected_original.strip().upper() == correct_original.strip().upper()

        # ── 记录统计数据 + 写入错题历史 ──
        self._answered = True
        self._stats["answered"] += 1
        if is_correct:
            self._stats["correct"] += 1
        try:
            self.db.record_review(q["id"], is_correct)
        except Exception:
            pass

        # 间隔重复：答错的题 3 题后再出现
        if not is_correct and len(self._review_questions) > 1:
            reinsert_pos = self._review_index + 4
            if reinsert_pos < len(self._review_questions):
                self._review_questions.insert(reinsert_pos, q)
                self._stats["total"] += 1

        # ── 即时反馈（护眼色系） ──
        if is_correct:
            self.feedback_label.configure(
                text="✅ 回答正确！",
                text_color=COLOR_SUCCESS,
            )
            self.feedback_detail.configure(text="")
        else:
            # 找出正确选项的显示标签和文本
            correct_display = "?"
            correct_text = ""
            for display_label, original_key in self._current_mapping:
                if original_key == correct_original:
                    correct_display = display_label
                    break
            if not correct_text:
                correct_text = q.get(f"option_{correct_original.lower()}", "")

            self.feedback_label.configure(
                text="❌ 回答错误",
                text_color=COLOR_ERROR,
            )
            self.feedback_detail.configure(
                text=f"正确答案是：{correct_display}. {correct_text}",
                text_color=COLOR_ERROR,
            )

        # ── 切换按钮状态 ──
        self.submit_btn.configure(state="disabled")
        self.next_btn.configure(text="⏭ 下一题")
        self._update_progress()

    def _on_next(self):
        """进入下一题 / 完成"""
        if not self._answered:
            # 用户没点"提交"就想跳题 → 拦截确认
            ok = messagebox.askyesno(
                "确认跳题",
                "你还没有提交本题的答案，确认要跳过吗？\n（跳过不计入答题统计）"
            )
            if not ok:
                return

        self._review_index += 1

        if self._review_index < self._stats["total"]:
            self._show_question(self._review_index)
            self._update_progress()
        else:
            self._show_completion()
            self._show_completion_report()

    def _update_progress(self):
        total = self._stats["total"]
        current = self._review_index + 1
        if self._stats["answered"] > 0:
            pct = int(self._stats["correct"] / self._stats["answered"] * 100)
            self.progress_label.configure(
                text=f"📊 进度：{current}/{total}  |  🎯 正确率：{self._stats['correct']}/{self._stats['answered']} ({pct}%)",
                text_color=COLOR_PRIMARY,
            )
        else:
            self.progress_label.configure(
                text=f"📊 进度：{current}/{total}",
                text_color=COLOR_TEXT_MUTED,
            )

    def _show_completion(self):
        """所有题目完成时的总结界面"""
        s = self._stats
        total = s["total"]
        pct = int(s["correct"] / s["answered"] * 100) if s["answered"] else 0
        wrong = s["answered"] - s["correct"]

        self.question_header.configure(
            text="🎉 复习完成！",
            text_color=COLOR_PRIMARY,
        )
        self.question_stem.configure(
            text=f"📚 学科：{s['subject_name']}\n"
                 f"📝 共 {total} 道题\n"
                 f"✅ 正确：{s['correct']} 道\n"
                 f"❌ 错误：{wrong} 道\n"
                 f"🎯 正确率：{pct}%\n\n"
                 f"💡 关闭当前标签再点「开始复习」即可重新刷题。",
            text_color=COLOR_TEXT,
        )
        self._clear_option_radios()
        for w in self._stem_image_widgets:
            w.destroy()
        self._stem_image_widgets.clear()
        self.feedback_label.configure(text="")
        self.feedback_detail.configure(text="")
        self.submit_btn.configure(state="disabled")
        self.next_btn.configure(text="⏭ 已结束")
        self.progress_label.configure(text="")
        self.wrong_count_label.configure(text="")

    def _show_completion_report(self):
        """弹出完整的刷题报告"""
        s = self._stats
        total = s["total"]
        answered = s["answered"]
        correct = s["correct"]
        wrong = answered - correct
        pct = int(correct / answered * 100) if answered else 0

        report = (
            f"📚 复习学科：{s['subject_name']}\n\n"
            f"📝 总共题目：{total} 道\n"
            f"✅ 答对题数：{correct} 道\n"
            f"❌ 答错题数：{wrong} 道\n"
            f"🎯 综合正确率：{pct}%\n"
        )
        messagebox.showinfo("📊 刷题报告", report)

    # ═════════════════════════════════════════════════════════════════════
    #  标签页三：学习统计
    # ═════════════════════════════════════════════════════════════════════

    def _build_dashboard_tab(self):
        """构建「学习统计」仪表盘标签页"""
        # ── 总览卡片 ──
        overview_frame = ctk.CTkFrame(self.tab_dashboard, fg_color=COLOR_CARD, border_color=COLOR_BORDER, border_width=1)
        overview_frame.pack(fill="x", padx=10, pady=(10, 0))

        ctk.CTkLabel(
            overview_frame, text="📊 学习总览",
            font=FONT_LG, text_color=COLOR_TEXT,
        ).pack(anchor="w", padx=16, pady=(8, 4))

        self.dash_overview_text = ctk.CTkLabel(
            overview_frame, text="",
            font=FONT_MD, text_color=COLOR_TEXT,
            anchor="w", justify="left",
        )
        self.dash_overview_text.pack(anchor="w", padx=16, pady=(0, 10))

        # ── 各学科统计表格 ──
        table_frame = ctk.CTkFrame(self.tab_dashboard, fg_color=COLOR_CARD, border_color=COLOR_BORDER, border_width=1)
        table_frame.pack(fill="both", expand=True, padx=10, pady=10)

        ctk.CTkLabel(
            table_frame, text="📋 各学科详情",
            font=FONT_MD, text_color=COLOR_TEXT,
        ).pack(anchor="w", padx=16, pady=(8, 4))

        # 表头
        headers = ["学科", "题目数", "累计答题", "正确数", "正确率", "累计错题"]
        col_widths = [140, 70, 80, 70, 80, 80]
        header_frame = ctk.CTkFrame(table_frame, fg_color=COLOR_CARD_ALT)
        header_frame.pack(fill="x", padx=16, pady=(0, 2))

        # 用 grid 布局表头
        for ci, hdr in enumerate(headers):
            ctk.CTkLabel(
                header_frame, text=hdr,
                font=("Microsoft YaHei", 12, "bold"), text_color=COLOR_TEXT,
                width=col_widths[ci], anchor="center",
            ).pack(side="left", padx=1, pady=4)

        # 数据行容器（可滚动）
        self.dash_rows_frame = ctk.CTkScrollableFrame(table_frame, fg_color="transparent")
        self.dash_rows_frame.pack(fill="both", expand=True, padx=16, pady=(0, 10))

        # ── 底部按钮 ──
        btn_frame = ctk.CTkFrame(self.tab_dashboard, fg_color="transparent")
        btn_frame.pack(fill="x", padx=10, pady=(0, 10))

        ctk.CTkButton(
            btn_frame, text="🔄 刷新数据", width=120,
            fg_color=COLOR_PRIMARY, hover_color=COLOR_PRIMARY_HV,
            text_color="white", font=FONT_SM,
            command=self._refresh_dashboard,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_frame, text="📤 导出报表", width=120,
            fg_color=COLOR_SECONDARY, hover_color=COLOR_SECONDARY_HV,
            text_color="white", font=FONT_SM,
            command=self._on_export_report,
        ).pack(side="left")

        ctk.CTkButton(
            btn_frame, text="🗑 清空答题记录", width=140,
            fg_color=COLOR_CARD_ALT, hover_color=COLOR_ERROR,
            text_color=COLOR_TEXT_MUTED, font=FONT_XS,
            command=self._on_clear_history,
        ).pack(side="right")

    def _refresh_dashboard(self):
        """刷新仪表盘数据"""
        try:
            stats = self.db.get_all_stats()
        except Exception:
            self.dash_overview_text.configure(text="⚠️ 读取数据失败")
            return

        # 总览
        total_qs = sum(s["total"] for s in stats)
        total_answered = sum(s["answered"] for s in stats)
        total_correct = sum(s["correct"] for s in stats)
        overall_acc = round(total_correct / total_answered * 100, 1) if total_answered > 0 else 0

        overview = (
            f"📚 学科数：{len(stats)} 个    "
            f"📝 总题数：{total_qs} 道    "
            f"📊 总答题：{total_answered} 次    "
            f"🎯 正确率：{overall_acc}%"
        )
        self.dash_overview_text.configure(text=overview)

        # 清空旧行
        for w in self.dash_rows_frame.winfo_children():
            w.destroy()

        if not stats:
            ctk.CTkLabel(
                self.dash_rows_frame, text="暂无数据，先去录入题目吧！",
                font=FONT_MD, text_color=COLOR_TEXT_MUTED,
            ).pack(pady=20)
            return

        # 填充数据行
        for si, s in enumerate(stats):
            row_bg = COLOR_CARD if si % 2 == 0 else COLOR_CARD_ALT
            row_frame = ctk.CTkFrame(self.dash_rows_frame, fg_color=row_bg)
            row_frame.pack(fill="x", pady=1)

            # 学科名
            ctk.CTkLabel(
                row_frame, text=s["subject_name"],
                font=("Microsoft YaHei", 12), text_color=COLOR_TEXT,
                width=140, anchor="w",
            ).pack(side="left", padx=(8, 0), pady=4)

            # 题目数
            ctk.CTkLabel(row_frame, text=str(s["total"]), width=70, anchor="center",
                font=("Microsoft YaHei", 12)).pack(side="left")
            # 累计答题
            ctk.CTkLabel(row_frame, text=str(s["answered"]), width=80, anchor="center",
                font=("Microsoft YaHei", 12)).pack(side="left")
            # 正确数
            ctk.CTkLabel(row_frame, text=str(s["correct"]), width=70, anchor="center",
                font=("Microsoft YaHei", 12)).pack(side="left")

            # 正确率（带颜色）
            acc = s["accuracy"]
            if acc >= 80: acc_color = COLOR_SUCCESS
            elif acc >= 50: acc_color = COLOR_PRIMARY
            else: acc_color = COLOR_ERROR
            ctk.CTkLabel(
                row_frame, text=f"{acc}%", width=80, anchor="center",
                text_color=acc_color, font=("Microsoft YaHei", 12, "bold"),
            ).pack(side="left")

            # 累计错题
            wrong = s.get("wrong_total", 0)
            ctk.CTkLabel(row_frame, text=str(wrong), width=80, anchor="center",
                text_color=COLOR_ERROR if wrong > 0 else COLOR_TEXT_MUTED,
                font=("Microsoft YaHei", 12)).pack(side="left")

    def _on_export_report(self):
        """导出统计报表为 CSV"""
        from tkinter import filedialog
        try:
            stats = self.db.get_all_stats()
        except Exception:
            messagebox.showerror("错误", "读取数据失败")
            return
        if not stats:
            messagebox.showwarning("提示", "没有数据可导出")
            return
        file_path = filedialog.asksaveasfilename(
            title="导出报表", defaultextension=".csv",
            filetypes=[("CSV 文件", "*.csv")],
            initialfile="quiz_report.csv",
        )
        if not file_path:
            return
        try:
            with open(file_path, "w", encoding="utf-8-sig") as f:
                f.write("学科,题目数,累计答题,正确数,正确率,累计错题\n")
                for s in stats:
                    f.write(f"{s['subject_name']},{s['total']},{s['answered']},{s['correct']},{s['accuracy']}%,{s['wrong_total']}\n")
            messagebox.showinfo("导出成功", f"报表已保存到\n{file_path}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def _on_clear_history(self):
        """清空所有答题记录"""
        if not messagebox.askyesno("确认", "确定要清空所有答题记录吗？\n（题目数据和错题计数将被重置）"):
            return
        try:
            with self.db._get_conn() as conn:
                conn.execute("DELETE FROM review_history")
                conn.execute("UPDATE questions SET wrong_count=0, last_wrong_at=NULL")
            self._refresh_dashboard()
            messagebox.showinfo("完成", "答题记录已清空")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _on_tab_switch(self):
        """标签切换回调"""
        try:
            if self.tab_view.get() == "📊 学习统计":
                self._refresh_dashboard()
        except Exception:
            pass

    # ═════════════════════════════════════════════════════════════════════
    #  设置 / 导出 / 每日进度
    # ═════════════════════════════════════════════════════════════════════

    def _check_daily_progress(self):
        """每天首次打开时显示进度摘要"""
        try:
            stats = self.db.get_all_stats()
            if not stats:
                return
            total_answered = sum(s["answered"] for s in stats)
            total_correct = sum(s["correct"] for s in stats)
            if total_answered == 0:
                return
            pct = round(total_correct / total_answered * 100, 1)
            messagebox.showinfo(
                "📊 学习进度",
                f"今天又见面了！目前的累计数据：\n\n"
                f"📚 学科数：{len(stats)} 个\n"
                f"📝 总答题：{total_answered} 次\n"
                f"✅ 正确率：{pct}%\n\n"
                f"💪 继续加油！"
            )
        except Exception:
            pass

    def _open_settings(self):
        """打开设置对话框"""
        dialog = ctk.CTkToplevel(self)
        dialog.title("⚙️ 设置")
        dialog.geometry("420x400")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        # 使对话框居中
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 420) // 2
        y = self.winfo_y() + (self.winfo_height() - 400) // 2
        dialog.geometry(f"+{x}+{y}")

        # ── 主题设置 ──
        theme_frame = ctk.CTkFrame(dialog, fg_color=COLOR_CARD, border_color=COLOR_BORDER, border_width=1)
        theme_frame.pack(fill="x", padx=16, pady=(16, 8))

        ctk.CTkLabel(
            theme_frame, text="🎨 主题切换",
            font=FONT_MD, text_color=COLOR_TEXT,
        ).pack(anchor="w", padx=12, pady=(8, 4))

        current_mode = ctk.get_appearance_mode()
        theme_var = ctk.StringVar(value="dark" if current_mode == "Dark" else "light")

        def on_theme_change(choice):
            nonlocal theme_var
            ctk.set_appearance_mode(choice)
            # 切换设置按钮颜色
            if choice == "dark":
                self.settings_btn.configure(text_color="white")
            else:
                self.settings_btn.configure(text_color=COLOR_TEXT)

        theme_menu = ctk.CTkOptionMenu(
            theme_frame,
            values=["light", "dark"],
            variable=theme_var,
            command=on_theme_change,
            fg_color=COLOR_CARD_ALT, button_color=COLOR_PRIMARY,
            button_hover_color=COLOR_PRIMARY_HV,
            text_color=COLOR_TEXT,
            dropdown_fg_color=COLOR_CARD,
            dropdown_text_color=COLOR_TEXT,
            font=FONT_SM,
        )
        theme_menu.pack(anchor="w", padx=12, pady=(0, 8))
        ctk.CTkLabel(
            theme_frame, text="light = 护眼浅色（默认）  |  dark = 极简深色",
            font=FONT_XS, text_color=COLOR_TEXT_MUTED,
        ).pack(anchor="w", padx=12, pady=(0, 8))

        # ── 缩放设置 ──
        scale_frame = ctk.CTkFrame(dialog, fg_color=COLOR_CARD, border_color=COLOR_BORDER, border_width=1)
        scale_frame.pack(fill="x", padx=16, pady=8)

        ctk.CTkLabel(
            scale_frame, text="🔍 界面缩放",
            font=FONT_MD, text_color=COLOR_TEXT,
        ).pack(anchor="w", padx=12, pady=(8, 4))

        scale_var = ctk.DoubleVar(value=ctk.get_widget_scaling())
        scale_slider = ctk.CTkSlider(
            scale_frame, from_=0.7, to=1.3,
            variable=scale_var,
            fg_color=COLOR_CARD_ALT,
            button_color=COLOR_PRIMARY,
            button_hover_color=COLOR_PRIMARY_HV,
            command=lambda v: (
                ctk.set_widget_scaling(round(v, 1)),
                scale_label.configure(text=f"{round(v, 1)}x")
            ),
        )
        scale_slider.pack(fill="x", padx=12, pady=(4, 0))
        scale_label = ctk.CTkLabel(
            scale_frame, text=f"{ctk.get_widget_scaling():.1f}x",
            font=FONT_SM, text_color=COLOR_TEXT_MUTED,
        )
        scale_label.pack(anchor="e", padx=12, pady=(0, 8))

        # ── 导出错题 ──
        export_frame = ctk.CTkFrame(dialog, fg_color=COLOR_CARD, border_color=COLOR_BORDER, border_width=1)
        export_frame.pack(fill="x", padx=16, pady=8)

        ctk.CTkLabel(
            export_frame, text="📤 导出错题",
            font=FONT_MD, text_color=COLOR_TEXT,
        ).pack(anchor="w", padx=12, pady=(8, 4))

        ctk.CTkLabel(
            export_frame, text="将错误次数 ≥ 1 的题目导出为文本文件，方便纸质打印。",
            font=FONT_XS, text_color=COLOR_TEXT_MUTED,
            anchor="w", justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 4))

        def on_export_wrong():
            self._on_export_wrong()
            # 导出成功后显示提示（在_export_wrong中已处理）

        ctk.CTkButton(
            export_frame, text="📥 导出错题本",
            width=160, height=32,
            fg_color=COLOR_PRIMARY, hover_color=COLOR_PRIMARY_HV,
            text_color="white", font=FONT_SM,
            command=on_export_wrong,
        ).pack(anchor="w", padx=12, pady=(0, 10))

    def _on_export_wrong(self):
        """导出错题到文本文件"""
        from tkinter import filedialog
        try:
            wrong_qs = self.db.get_all_wrong_questions(min_wrong=1)
        except Exception:
            messagebox.showerror("错误", "读取错题数据失败")
            return
        if not wrong_qs:
            messagebox.showwarning("提示", "没有错题记录，继续保持！")
            return

        file_path = filedialog.asksaveasfilename(
            title="导出错题本",
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
            initialfile="错题本.txt",
        )
        if not file_path:
            return

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("=" * 50 + "\n")
                f.write("  错题本 — 导出时间：" + __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M") + "\n")
                f.write("=" * 50 + "\n\n")
                for i, q in enumerate(wrong_qs, 1):
                    f.write(f"第 {i} 题（错 {q['wrong_count']} 次）\n")
                    f.write(f"学科：{q.get('subject_name', '')}\n")
                    f.write(f"题干：{q['stem']}\n")
                    f.write(f"A. {q['option_a']}\n")
                    if q.get('option_b', ''): f.write(f"B. {q['option_b']}\n")
                    if q.get('option_c', ''): f.write(f"C. {q['option_c']}\n")
                    if q.get('option_d', ''): f.write(f"D. {q['option_d']}\n")
                    f.write(f"正确答案：{q['correct_answer']}\n")
                    f.write("-" * 40 + "\n\n")
            messagebox.showinfo("导出成功", f"共导出 {len(wrong_qs)} 道错题到\n{file_path}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    # ═════════════════════════════════════════════════════════════════════
    #  窗口关闭
    # ═════════════════════════════════════════════════════════════════════

    def _on_close(self):
        """安全退出，保存窗口位置"""
        self._save_window_geometry()
        self.destroy()

    # ── 窗口大小记忆 ────────────────────────────────────────────────────────

    def _save_window_geometry(self):
        """保存窗口位置和大小到文件"""
        import json
        try:
            geo = self.geometry()
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".window_geometry.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"geometry": geo}, f)
        except Exception:
            pass

    def _load_window_geometry(self):
        """从文件恢复窗口位置和大小"""
        import json
        try:
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".window_geometry.json")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if "geometry" in data:
                    self.geometry(data["geometry"])
        except Exception:
            pass

    # ── 键盘快捷键 ─────────────────────────────────────────────────────────

    def _bind_shortcuts(self):
        """绑定键盘快捷键：A/B/C/D 选答案，Enter 提交，Right 下一题"""
        for ch in "ABCDabcd":
            self.bind(f"<Key-{ch}>", lambda e, c=ch.upper(): self._shortcut_select(c))
        self.bind("<Return>", lambda e: self._shortcut_submit())
        self.bind("<Right>", lambda e: self._shortcut_next())

    def _shortcut_select(self, letter: str):
        if not self._review_questions or self._answered:
            return
        for rb in self.option_radios:
            if rb.cget("value") == letter:
                self.option_var.set(letter)
                break

    def _shortcut_submit(self):
        if not self._review_questions or self._answered:
            return
        if self.option_var.get():
            self._on_submit()

    def _shortcut_next(self):
        if self._review_questions:
            self._on_next()


# ─── 启动点（直接运行时） ──────────────────────────────────────────────────

if __name__ == "__main__":
    app = QuizApp()
    app.mainloop()
