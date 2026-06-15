"""
parser.py — 纯文本题目解析引擎（v2）

专注支持用户的标准格式：
─────────────────────────────────────────
1. (单选题, 10分).一个作业第一次执行时用了5min...
A. 并发性
B. 共享性
C. 虚拟性
D. 不确定性
我的答案:D:不确定性;正确答案:D:不确定性;
10分
答案解析：D
AI讲解
─────────────────────────────────────────

同时兼容简洁格式：
  1. 题干
  A. 选项
  B. 选项
  C. 选项
  D. 选项
  答案：A

解析结果：list[dict]，每个 dict 含：
  stem, option_a, option_b, option_c, option_d, correct_answer
"""

import os
import re
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════════
#  正则常量
# ═══════════════════════════════════════════════════════════════════════════

# ── 题号 + (单选题/判断题, N分) + 题干 ──
# 匹配如：
#   1. (单选题, 10分).一个作业...
#   2、(单选题,5分)以下关于...
#   12. (判断题)进程状态转换中...
RE_QUESTION_HEADER = re.compile(
    r"^\s*"
    r"(\d+)"                       # 题号（group 1）
    r"\s*[.、．)）]\s*"
    r"\((?:单选题|判断题)[^)]*\)"  # (单选题...) 或 (判断题...)
    r"[.．]?\s*"                    # 可选的点号
    r"(.*)"                        # 题干正文（group 2）
)

# ── 选项行：A. xxx / A、xxx / A．xxx / A) xxx ──
RE_OPTION = re.compile(
    r"^\s*([A-Da-d])\s*[.、．)）]\s*(.*)"
)

# ── 正确答案一行内提取（从任意位置）──
# 匹配：正确答案:D  正确答案：D  正确答案:对  正确答案:错  等
# 也能从复合行中提取：我的答案:D:不确定性;正确答案:D:不确定性;
# 对→A, 错→B 映射见 ANSWER_CHINESE_MAP
RE_ANSWER = re.compile(
    r"正确答案\s*[:：]\s*([A-Da-d对错])"
)

# 中文答案 → 选项字母映射（用于判断题）
ANSWER_CHINESE_MAP = {"对": "A", "错": "B"}

# ── 答案解析中提取答案（兜底）──
# 匹配：答案解析：D  答案解析:D
RE_ANSWER_ANALYSIS = re.compile(
    r"答案解析\s*[:：]\s*([A-Da-d])"
)

# ── 纯垃圾行 ──
RE_GARBAGE = re.compile(
    r"^\s*(?:"
    r"我的答案.*|"        # 我的答案:D:不确定性;...
    r"\d+\s*分|"          # 10分
    r"AI讲解|"            # AI讲解
    r"答案解析.*|"        # 答案解析：D
    r"[-=▬—~*]{5,}"      # 分隔线
    r")\s*$"
)

# ── 旧格式题号行（兜底：当新格式不匹配时使用）──
RE_QUESTION_NUM_OLD = re.compile(
    r"^\s*(\d+)\s*[.、．)）\s]\s*(.*)"
)

# ── 旧格式答案行兜底 ──
RE_ANSWER_OLD = re.compile(
    r"^\s*(?:答案|正确答案|参考答案)\s*[：:]\s*([A-Da-d])\s*$"
)


# ═══════════════════════════════════════════════════════════════════════════
#  主解析函数
# ═══════════════════════════════════════════════════════════════════════════

def parse_questions(text: str) -> list[dict]:
    """
    从纯文本中解析出所有题目。

    Args:
        text: 含有题目的纯文本（可包含多道题）

    Returns:
        解析成功的题目列表
    """
    lines = text.strip().splitlines()
    if not lines:
        return []

    questions: list[dict] = []
    current: Optional[dict] = None
    seen_options: set[str] = set()
    pending_opt_key: Optional[str] = None   # ← 新增：待填选项（字母和文字分在两行时用）

    # ── 内部：flush 当前题 ──
    def _flush():
        nonlocal current, seen_options
        if current is None:
            return
        for k in ("option_a", "option_b", "option_c", "option_d"):
            current.setdefault(k, "")
        if current.get("stem") and current.get("correct_answer"):
            questions.append(current)
        current = None
        seen_options = set()

    # ── 内部：启动新题 ──
    def _new_question(stem_text: str):
        nonlocal current, seen_options, pending_opt_key
        _flush()
        current = {
            "stem": stem_text.strip(),
            "correct_answer": None,
        }
        seen_options = set()
        pending_opt_key = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            # ── 空行不再 flush！改为跳过，选项间的空行不会打断题目 ──
            continue

        # ────────────────────────────────────────────
        #  1. 【优先】从行中提取正确答案
        #     必须在垃圾过滤之前
        # ────────────────────────────────────────────
        if current is not None and not current.get("correct_answer"):
            m = RE_ANSWER.search(line)
            if m:
                raw = m.group(1)
                # "正确答案:对/错" → 映射为 A/B
                current["correct_answer"] = ANSWER_CHINESE_MAP.get(raw, raw.upper())
            else:
                m = RE_ANSWER_OLD.match(line)
                if m:
                    current["correct_answer"] = m.group(1).upper()
                else:
                    m = RE_ANSWER_ANALYSIS.search(line)
                    if m:
                        current["correct_answer"] = m.group(1).upper()

        # ────────────────────────────────────────────
        #  2. 垃圾行 → 跳过（答案已在第 1 步提取）
        # ────────────────────────────────────────────
        if RE_GARBAGE.match(line):
            pending_opt_key = None  # 清除挂起，避免垃圾行被当成选项文本
            continue

        # ────────────────────────────────────────────
        #  3. 新格式题号行
        # ────────────────────────────────────────────
        m = RE_QUESTION_HEADER.match(line)
        if m:
            _new_question(m.group(2))
            continue

        # ────────────────────────────────────────────
        #  4. 旧格式题号行（兜底）
        # ────────────────────────────────────────────
        m = RE_QUESTION_NUM_OLD.match(line)
        if m:
            candidate_stem = m.group(2).strip()
            if candidate_stem:
                _new_question(candidate_stem)
                continue

        if current is None:
            continue

        # ────────────────────────────────────────────
        #  5. 处理"待填选项"：上一行是"A."但文字在下一行
        # ────────────────────────────────────────────
        if pending_opt_key:
            current[pending_opt_key] = line
            pending_opt_key = None
            continue

        # ────────────────────────────────────────────
        #  6. 选项行：A. xxx / A.  (文字可空，等下一行)
        # ────────────────────────────────────────────
        m = RE_OPTION.match(line)
        if m:
            opt_letter = m.group(1).upper()
            opt_text = m.group(2).strip()
            key = f"option_{opt_letter.lower()}"
            seen_options.add(opt_letter)

            if opt_text:
                # 文字和字母在同一行：直接存入
                current[key] = opt_text
                pending_opt_key = None
            else:
                # 文字在下一行：挂起，等下次循环填入
                pending_opt_key = key
            continue

        # ────────────────────────────────────────────
        #  7. 题干续行（还没收齐 4 个选项 + 尚未填答案时）
        # ────────────────────────────────────────────
        if len(seen_options) < 4 and not current.get("correct_answer"):
            if not current.get("stem"):
                current["stem"] = line
            else:
                current["stem"] += "\n" + line

    # 收尾
    _flush()

    return questions


# ═══════════════════════════════════════════════════════════════════════════
#  辅助函数
# ═══════════════════════════════════════════════════════════════════════════

def format_question_preview(q: dict) -> str:
    """格式化单道题为人类可读的预览字符串"""
    opts = "".join(
        f"  {k.upper()}. {q.get(f'option_{k}', '')}\n"
        for k in ["a", "b", "c", "d"]
    )
    return (
        f"题干：{q['stem']}\n"
        f"{opts}"
        f"答案：{q['correct_answer']}\n"
    )


# ─── 图片标记提取 ───────────────────────────────────────────────────────────

RE_IMAGE_MARKER = re.compile(r"\{img:([^}]+)\}")

def split_text_with_images(text: str) -> list[dict]:
    """
    将文本按 {img:filename} 标记拆分为可渲染片段。

    返回列表，每个元素为：
      {"type": "text",  "content": "纯文本..."}
      {"type": "image", "file": "filename.png"}

    例：
      "请看下图{img:topo.png}选答案"
      → [{"type":"text","content":"请看下图"},
         {"type":"image","file":"topo.png"},
         {"type":"text","content":"选答案"}]
    """
    segments = []
    last_end = 0
    for m in RE_IMAGE_MARKER.finditer(text):
        if m.start() > last_end:
            segments.append({"type": "text", "content": text[last_end:m.start()]})
        segments.append({"type": "image", "file": m.group(1)})
        last_end = m.end()
    if last_end < len(text):
        segments.append({"type": "text", "content": text[last_end:]})
    if not segments:
        segments.append({"type": "text", "content": text})
    return segments


def strip_image_markers(text: str) -> str:
    """移除所有 {img:...} 标记，返回纯文本（用于预览等用途）"""
    return RE_IMAGE_MARKER.sub("", text)


# ═══════════════════════════════════════════════════════════════════════════
#  自测（python parser.py 直接运行）
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # ── 测试用例 1：用户标准格式 ──
    sample_user = """
1. (单选题, 10分).一个作业第一次执行时用了5min,而第二次执行时用了6min,这说明了操作系统的（ ） 特点。
A. 并发性
B. 共享性
C. 虚拟性
D. 不确定性
我的答案:D:不确定性;正确答案:D:不确定性;
10分
答案解析：D
AI讲解

2. (单选题, 2分)操作系统的主要功能是（  ）。
A. 程序设计
B. 资源管理
C. 网页浏览
D. 数据库管理
我的答案:B:资源管理;正确答案:B:资源管理;
2分
答案解析：B
AI讲解

3. (单选题, 5分)在操作系统中，进程从运行状态进入就绪状态的原因是（ ）。
A. 时间片用完
B. 等待I/O
C. 进程被创建
D. 进程终止
我的答案:A:时间片用完;正确答案:A:时间片用完;
5分
答案解析：A
AI讲解
"""

    # ── 测试用例 2：简洁格式（旧格式兼容） ──
    sample_simple = """
1. 以下关于TCP的说法正确的是？
A. 面向无连接
B. 提供可靠传输
C. 不支持全双工
D. 速度比UDP快
答案：B

2．UDP的典型应用是？
A. 文件传输
B. 电子邮件
C. 视频直播
D. 网页浏览
正确答案：C
"""

    # ── 测试用例 3：题干/选项分行的新格式 ──
    sample_split = """
1. (单选题)
在操作系统中，并发性指的是（     ）。

A.
多个程序在同一时刻发生

B.
多个程序在不同时刻发生

C.
多个程序在同一时间间隔内发生

D.
多个程序在不同时间间隔内发生

我的答案:C:多个程序在同一时间间隔内发生;正确答案:C:多个程序在同一时间间隔内发生;

2. (单选题)
以下关于进程的描述，错误的是（     ）。

A.
进程是程序的执行过程

B.
进程是资源分配的基本单位

C.
进程是处理器调度的基本单位

D.
进程与程序是一一对应的关系

我的答案:D:进程与程序是一一对应的关系;正确答案:D:进程与程序是一一对应的关系;
"""

    # ── 测试用例 4：判断题 ──
    sample_judge = """
12. (判断题)
进程状态转换中:阻塞→运行，其原因是获取了请求资源后阻塞原因解除。

A. 对
B. 错
我的答案:错正确答案:错
4.5分
AI讲解

13. (判断题)
在Linux环境下，创建子进程需要使用的函数是fork()。

A. 对
B. 错
我的答案:对正确答案:对
4.6分
AI讲解
"""

    def _test_one(label, data, expect_count):
        print(f"\n{'=' * 60}")
        print(f"【{label}】")
        print(f"{'=' * 60}")
        result = parse_questions(data)
        print(f"解析出 {len(result)} 道题（期望 {expect_count} 道）")
        all_ok = True
        for i, q in enumerate(result, 1):
            print(f"\n─── 第 {i} 题 ───")
            print(f"  题干：{q['stem']}")
            for k in ["a", "b", "c", "d"]:
                print(f"  {k.upper()}. {q.get(f'option_{k}', '')}")
            print(f"  答案：{q['correct_answer']}")
            try:
                assert q["correct_answer"] in ("A", "B", "C", "D"), f"答案无效: {q['correct_answer']}"
                assert q["stem"], "题干为空"
                print(f"  ✅")
            except AssertionError as e:
                print(f"  ❌ {e}")
                all_ok = False
        if len(result) != expect_count:
            print(f"  ❌ 数量不符: 得到 {len(result)}, 期望 {expect_count}")
            all_ok = False
        return all_ok

    ok1 = _test_one("测试 1：标准格式（含(单选题)、垃圾行）", sample_user, 3)
    ok2 = _test_one("测试 2：简洁格式（旧格式兼容）", sample_simple, 2)
    ok3 = _test_one("测试 3：题干/选项分行格式", sample_split, 2)
    ok4 = _test_one("测试 4：判断题", sample_judge, 2)

    print(f"\n{'=' * 60}")
    if ok1 and ok2 and ok3 and ok4:
        print("全部测试通过 ✅")
    else:
        print("部分测试失败 ❌")
    print(f"{'=' * 60}")
