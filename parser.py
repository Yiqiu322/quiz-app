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
  stem, option_a, option_b, option_c, option_d, correct_answer, question_type
question_type: "single" | "multi" | "judge" | "fill"
"""

import json
import os
import re
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════════
#  正则常量
# ═══════════════════════════════════════════════════════════════════════════

# 题型中文 → 内部标识
TYPE_MAP = {
    "单选": "single",
    "多选": "multi",
    "判断": "judge",
    "填空": "fill",
}

# ── 题号 + (单选题/多选题/判断题/填空题, N分) + 题干 ──
# 匹配如：
#   1. (单选题, 10分).一个作业...
#   2、(单选题,5分)以下关于...
#   12. (判断题)进程状态转换中...
#   5. (多选题, 2分)以下哪些...
#   31. (填空题, 2分).称为（  ），它包含（  ）
RE_QUESTION_HEADER = re.compile(
    r"^\s*"
    r"(\d+)"                       # 题号（group 1）
    r"\s*[.、．)）]\s*"
    r"\("                          # 开括号
    r"(单选|多选|判断|填空)"       # 题型（group 2）
    r"题[^)]*\)"                   # 题 + 其它内容 + 闭括号
    r"[.．]?\s*"                    # 可选的点号
    r"(.*)"                        # 题干正文（group 3）
)

# ── 选项行：A. xxx / A、xxx / A．xxx / A) xxx ──
# 支持 A~E（多选题可能有 E 选项）
RE_OPTION = re.compile(
    r"^\s*([A-Ea-e])\s*[.、．)）]\s*(.*)"
)

# ── 正确答案一行内提取（从任意位置）──
# 匹配：正确答案:D  正确答案：D  正确答案:BD  正确答案：BD
#       正确答案:对  正确答案:错
# 对→A, 错→B 映射见 ANSWER_CHINESE_MAP
RE_ANSWER = re.compile(
    r"正确答案\s*[:：]\s*([A-Ea-e对错]+)"
)

# 中文答案 → 选项字母映射（用于判断题）
ANSWER_CHINESE_MAP = {"对": "A", "错": "B"}

# ── 答案解析中提取答案（兜底）──
RE_ANSWER_ANALYSIS = re.compile(
    r"答案解析\s*[:：]\s*([A-Ea-e]+)"
)

# ── 纯垃圾行 ──
RE_GARBAGE = re.compile(
    r"^\s*(?:"
    r"我的答案.*|"        # 我的答案:D:不确定性;...
    r"\d+\s*分|"          # 10分
    r"AI讲解|"            # AI讲解
    r"答案解析.*|"        # 答案解析：D
    r"知识点.*|"          # 知识点：xxx
    r"[-=▬—~*]{5,}"      # 分隔线
    r")\s*$"
)

# ── 填空题答案编号行（如 (1)、(2)）──
RE_FILL_NUMBER = re.compile(
    r"^\s*\(\s*(\d+)\s*\)\s*$"
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
    pending_opt_key: Optional[str] = None

    # ── 内部：flush 当前题 ──
    def _flush():
        nonlocal current, seen_options
        if current is None:
            return

        # 填空题：将 _fill_answers 转为 correct_answer
        if current.get("question_type") == "fill":
            fill_data = current.pop("_fill_answers", [])
            if not current.get("correct_answer") and fill_data:
                fill_answers_json = []
                for blank_lines in fill_data:
                    if blank_lines:
                        # 取第一行，按 ; 分隔多个可接受值
                        answers = [a.strip() for a in blank_lines[0].split(";") if a.strip()]
                        if answers:
                            fill_answers_json.append(answers)
                if fill_answers_json:
                    current["correct_answer"] = json.dumps(fill_answers_json, ensure_ascii=False)

        for k in ("option_a", "option_b", "option_c", "option_d", "option_e"):
            current.setdefault(k, "")
        if current.get("stem") and current.get("correct_answer"):
            questions.append(current)
        current = None
        seen_options = set()

    # ── 内部：启动新题 ──
    def _new_question(stem_text: str, qtype: str = "single"):
        nonlocal current, seen_options, pending_opt_key
        _flush()
        current = {
            "stem": stem_text.strip(),
            "correct_answer": None,
            "question_type": qtype,
        }
        seen_options = set()
        pending_opt_key = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        # ────────────────────────────────────────────
        #  1. 【优先】从行中提取正确答案
        #     必须在垃圾过滤之前
        # ────────────────────────────────────────────
        if current is not None and not current.get("correct_answer"):
            m = RE_ANSWER.search(line)
            if m:
                raw = m.group(1)
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
            pending_opt_key = None
            continue

        # ────────────────────────────────────────────
        #  3. 新格式题号行
        # ────────────────────────────────────────────
        m = RE_QUESTION_HEADER.match(line)
        if m:
            qtype = TYPE_MAP.get(m.group(2), "single")
            _new_question(m.group(3), qtype)
            continue

        # ────────────────────────────────────────────
        #  4. 旧格式题号行（兜底）
        # ────────────────────────────────────────────
        m = RE_QUESTION_NUM_OLD.match(line)
        if m:
            candidate_stem = m.group(2).strip()
            if candidate_stem:
                _new_question(candidate_stem, "single")
                continue

        if current is None:
            continue

        # ────────────────────────────────────────────
        #  5. 填空题答案收集
        # ────────────────────────────────────────────
        if current.get("question_type") == "fill" and not current.get("correct_answer"):
            # 遇到 "正确答案" 时重置收集，只认正式答案
            if re.search(r"^正确答案", line):
                current["_fill_answers"] = []
                continue
            m = RE_FILL_NUMBER.match(line)
            if m:
                current.setdefault("_fill_answers", [])
                current["_fill_answers"].append([])
                continue
            # 当前在收集某一空的答案文本
            if current.get("_fill_answers"):
                current["_fill_answers"][-1].append(line)
                continue
            # _fill_answers 未初始化 → 允许继续处理题干/其他
            # （不 continue，让后续代码有机会处理）

        # ────────────────────────────────────────────
        #  6. 处理"待填选项"：上一行是"A."但文字在下一行
        # ────────────────────────────────────────────
        if pending_opt_key:
            current[pending_opt_key] = line
            pending_opt_key = None
            continue

        # ────────────────────────────────────────────
        #  7. 选项行：A. xxx / A.  (文字可空，等下一行)
        # ────────────────────────────────────────────
        m = RE_OPTION.match(line)
        if m:
            opt_letter = m.group(1).upper()
            opt_text = m.group(2).strip()
            key = f"option_{opt_letter.lower()}"
            seen_options.add(opt_letter)

            if opt_text:
                current[key] = opt_text
                pending_opt_key = None
            else:
                pending_opt_key = key
            continue

        # ────────────────────────────────────────────
        #  8. 题干续行（填空题在未开始收答案前也可续行）
        # ────────────────────────────────────────────
        is_fill_active = (current.get("question_type") == "fill" and current.get("_fill_answers"))
        if (len(seen_options) < 4
                and not current.get("correct_answer")
                and not is_fill_active):
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
    if q.get("question_type") == "fill":
        return (
            f"题干：{q['stem']}\n"
            f"答案：{q['correct_answer']}\n"
        )
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

    # ── 测试用例 5：多选题 ──
    sample_multi = """
5. (多选题, 2分).以下哪些是操作系统的主要特征？
A. 并发性
B. 共享性
C. 虚拟性
D. 不确定性
我的答案:BD;正确答案:BD;
2分
答案解析：BD
AI讲解

6. (多选题, 3分)以下关于进程的描述，正确的有（ ）。
A. 进程是程序的执行过程
B. 进程是资源分配的基本单位
C. 进程是处理器调度的基本单位
D. 一个进程可以包含多个线程
我的答案:ABCD;正确答案:ABCD;
3分
答案解析：ABCD
AI讲解
"""

    # ── 测试用例 6：填空题 ──
    sample_fill = """
31. (填空题, 2分).称为（  ），它包含（  ）
正确答案：
(1)
协议;网络协议
(2)
语法

32. (填空题).进程由（  ）组成。
正确答案：
(1)
程序段;数据段;PCB
"""

    # ── 测试用例 7：多选题（选项分行）──
    sample_multi_split = """
7. (多选题, 2分)以下哪些是操作系统的功能？

A.
进程管理

B.
存储管理

C.
文件管理

D.
设备管理

我的答案:ABCD;正确答案:ABCD;
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
            print(f"  题型：{q.get('question_type', '?')}")
            print(f"  题干：{q['stem']}")
            qt = q.get("question_type")
            if qt == "fill":
                print(f"  答案：{q['correct_answer']}")
            else:
                for k in ["a", "b", "c", "d"]:
                    print(f"  {k.upper()}. {q.get(f'option_{k}', '')}")
                print(f"  答案：{q['correct_answer']}")
            try:
                assert q["stem"], "题干为空"
                assert q.get("question_type") in ("single", "multi", "judge", "fill"), \
                    f"题型无效: {q.get('question_type')}"
                if qt in ("single", "multi", "judge"):
                    assert all(c in "ABCD" for c in q["correct_answer"]), \
                        f"答案无效: {q['correct_answer']}"
                    assert q["correct_answer"], "答案为空"
                elif qt == "fill":
                    assert q["correct_answer"], "填空题答案为空"
                    parsed = json.loads(q["correct_answer"])
                    assert isinstance(parsed, list), "填空题答案不是 JSON 数组"
                    for blank in parsed:
                        assert isinstance(blank, list) and len(blank) > 0, \
                            f"填空答案项无效: {blank}"
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
    ok5 = _test_one("测试 5：多选题", sample_multi, 2)
    ok6 = _test_one("测试 6：填空题", sample_fill, 2)
    ok7 = _test_one("测试 7：多选题（选项分行）", sample_multi_split, 1)

    print(f"\n{'=' * 60}")
    if ok1 and ok2 and ok3 and ok4 and ok5 and ok6 and ok7:
        print("全部测试通过 ✅")
    else:
        print("部分测试失败 ❌")
    print(f"{'=' * 60}")
