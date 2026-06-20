"""
web_app.py — Flask 网页版刷题服务器

启动后手机和电脑均可通过浏览器访问。
共用 quiz_app.db 数据库，数据与桌面版完全同步。

用法：
    python web_app.py
    然后打开 http://localhost:5000  （本机）
    或 http://你的IP:5000          （手机/其他设备）
"""

import random
import os
import sys
from flask import Flask, render_template, request, jsonify

# 确保能找到同目录下的模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import DatabaseManager
from parser import parse_questions

app = Flask(__name__)
db = DatabaseManager()
IMAGES_DIR = db.ensure_images_dir()


# ═══════════════════════════════════════════════════════════════════════════
#  页面路由
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    """首页：学科列表 + 总览统计"""
    subjects = db.get_subjects()
    stats = db.get_all_stats()
    # 禁止浏览器缓存 HTML，确保数据实时更新
    from flask import make_response
    resp = make_response(render_template("index.html", subjects=subjects, stats=stats,
        total_qs=sum(s["total"] for s in stats),
        total_answered=sum(s["answered"] for s in stats),
        overall_acc=round(sum(s["correct"] for s in stats) / max(sum(s["answered"] for s in stats), 1) * 100, 1),
        db=db))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp


@app.route("/review/<int:subject_id>")
def review(subject_id):
    """刷题页面"""
    subject_name = db.get_subject_name(subject_id)
    if not subject_name:
        return "学科不存在", 404

    wrong_only = request.args.get("wrong", "0") == "1"
    star_only = request.args.get("star", "0") == "1"

    if wrong_only:
        questions = db.get_wrong_questions(subject_id)
    elif star_only:
        questions = db.get_starred_questions(subject_id)
    else:
        questions = db.get_questions(subject_id)

    if not questions:
        msg = "暂无题目"
        if wrong_only:
            msg = "暂无错题记录"
        elif star_only:
            msg = "暂无星标题目"
        return render_template("review.html", subject_name=subject_name,
                               subject_id=subject_id, questions=[], msg=msg,
                               shuffle_q=True, shuffle_o=True)

    # 打乱题目顺序
    shuffle_q = request.args.get("shuffle_q", "1") == "1"
    shuffle_o = request.args.get("shuffle_o", "1") == "1"
    if shuffle_q:
        random.shuffle(questions)

    # 序列化传往前端
    serialized = []
    for q in questions:
        opts = {
            "A": q["option_a"],
            "B": q["option_b"],
            "C": q["option_c"] if q.get("option_c") else None,
            "D": q["option_d"] if q.get("option_d") else None,
        }
        # 过滤空选项
        opts = {k: v for k, v in opts.items() if v}
        serialized.append({
            "id": q["id"],
            "stem": q["stem"],
            "options": opts,
            "correct_answer": q["correct_answer"],
            "wrong_count": q.get("wrong_count", 0),
            "starred": q.get("starred", 0),
            "question_type": q.get("question_type", "single"),
        })
    # 把选项打乱信息也传给前端
    return render_template("review.html", subject_name=subject_name,
                           subject_id=subject_id,
                           questions_json=serialized,
                           questions=serialized,
                           shuffle_q=shuffle_q, shuffle_o=shuffle_o, msg="")


@app.route("/quick10")
def quick10():
    """快速刷 10 题"""
    all_qs = []
    for s in db.get_subjects():
        qs = db.get_questions(s["id"])
        for q in qs:
            q["_subject_name"] = s["name"]
        all_qs.extend(qs)
    if not all_qs:
        return render_template("review.html", subject_name="快速刷题",
                               subject_id=0, questions=[], msg="暂无题目",
                               shuffle_q=True, shuffle_o=True)
    random.shuffle(all_qs)
    picked = all_qs[: min(10, len(all_qs))]
    serialized = []
    for q in picked:
        opts = {"A": q["option_a"], "B": q["option_b"]}
        if q.get("option_c", ""): opts["C"] = q["option_c"]
        if q.get("option_d", ""): opts["D"] = q["option_d"]
        serialized.append({
            "id": q["id"],
            "stem": q["stem"],
            "options": opts,
            "correct_answer": q["correct_answer"],
            "wrong_count": q.get("wrong_count", 0),
            "starred": q.get("starred", 0),
            "question_type": q.get("question_type", "single"),
            "_subject_name": q.get("_subject_name", ""),
        })
    return render_template("review.html", subject_name="⚡ 快速刷 10 题",
                           subject_id=0, questions_json=serialized,
                           questions=serialized, shuffle_q=False,
                           shuffle_o=True, msg="")


# ═══════════════════════════════════════════════════════════════════════════
#  API（供前端异步调用）
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/stats")
def api_stats():
    """返回各学科统计 JSON"""
    stats = db.get_all_stats()
    total_qs = sum(s["total"] for s in stats)
    total_answered = sum(s["answered"] for s in stats)
    total_correct = sum(s["correct"] for s in stats)
    overall_acc = round(total_correct / total_answered * 100, 1) if total_answered > 0 else 0
    return jsonify({
        "subjects": stats,
        "total_questions": total_qs,
        "total_answered": total_answered,
        "total_correct": total_correct,
        "overall_accuracy": overall_acc,
    })


@app.route("/api/submit", methods=["POST"])
def api_submit():
    """提交答案，返回判定结果"""
    data = request.get_json(force=True)
    qid = data.get("question_id")
    answer = data.get("answer", "").strip().upper()

    # 查找题目
    # 从所有学科查（支持快速10题跨学科场景）
    all_qs = []
    for s in db.get_subjects():
        all_qs.extend(db.get_questions(s["id"]))
    question = next((q for q in all_qs if q["id"] == qid), None)
    if not question:
        return jsonify({"error": "题目不存在"}), 404

    if question.get("question_type") == "multi":
        # For multi-select, order doesn't matter
        user_ans = "".join(sorted(answer.strip()))
        correct_ans = "".join(sorted(question["correct_answer"].strip()))
        is_correct = user_ans == correct_ans
    elif question.get("question_type") == "fill":
        # Fill-in-blank: mark as correct (manual review)
        is_correct = True
    else:
        is_correct = answer == question["correct_answer"]
    correct_answer = question["correct_answer"]

    # 查找正确选项的文本
    correct_text = question.get(f"option_{correct_answer.lower()}", "")

    # 记录答题结果
    try:
        db.record_review(qid, is_correct)
    except Exception:
        pass

    # 重新获取题目最新状态
    try:
        updated = next((q for q in all_qs if q["id"] == qid), question)
        wrong_count = updated.get("wrong_count", 0) if not is_correct else question.get("wrong_count", 0)
    except Exception:
        wrong_count = 0

    return jsonify({
        "correct": is_correct,
        "correct_answer": correct_answer,
        "correct_text": correct_text,
        "wrong_count": wrong_count,
    })


@app.route("/api/toggle_star", methods=["POST"])
def api_toggle_star():
    """切换星标"""
    data = request.get_json(force=True)
    qid = data.get("question_id")
    new_state = db.toggle_star(qid)
    return jsonify({"starred": new_state})


@app.route("/api/image/<filename>")
def api_image(filename):
    """返回图片文件"""
    from flask import send_from_directory
    return send_from_directory(IMAGES_DIR, filename)


@app.route("/sw.js")
def service_worker():
    """PWA Service Worker（需在根路径）"""
    from flask import send_from_directory, make_response
    resp = make_response(send_from_directory(os.path.join(app.root_path, "static"), "sw.js"))
    resp.headers["Content-Type"] = "application/javascript"
    resp.headers["Service-Worker-Allowed"] = "/"
    return resp


# ═══════════════════════════════════════════════════════════════════════════
#  题目导入
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/import")
def import_page():
    """题目录入页面"""
    subjects = db.get_subjects()
    return render_template("import.html", subjects=subjects)


@app.route("/api/parse", methods=["POST"])
def api_parse():
    """解析粘贴的文本，返回结构化题目"""
    data = request.get_json(force=True)
    text = data.get("text", "")
    if not text.strip():
        return jsonify({"error": "文本为空"}), 400
    try:
        questions = parse_questions(text)
        return jsonify({"count": len(questions), "questions": questions})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/subject/new", methods=["POST"])
def api_new_subject():
    """创建新学科"""
    data = request.get_json(force=True)
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "学科名称不能为空"}), 400
    subject_id = db.add_subject(name)
    return jsonify({"id": subject_id, "name": name})


@app.route("/api/questions/save", methods=["POST"])
def api_save_questions():
    """批量保存题目到学科"""
    data = request.get_json(force=True)
    subject_id = data.get("subject_id")
    questions = data.get("questions", [])
    if not subject_id or not questions:
        return jsonify({"error": "参数不完整"}), 400
    try:
        count = db.add_questions_batch(subject_id, questions)
        return jsonify({"count": count})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════════════════
#  启动
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 50)
    print("  [Quiz App]  Web Server Started")
    print("=" * 50)
    print("  Local:   http://localhost:5000")
    # 获取局域网 IP
    import socket
    try:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        print(f"  手机访问：  http://{ip}:5000")
    except Exception:
        pass
    print(f"  按 Ctrl+C 停止服务器")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=True)
