"""
database.py — SQLite 数据库操作层
负责：建表、学科 CRUD、题目 CRUD
"""

import sqlite3
import os
from typing import Optional


DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "quiz_app.db")


class DatabaseManager:
    """数据库管理器，封装所有 SQLite 操作"""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    # ───────────────────────────── 连接与建表 ─────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        """获取数据库连接（每次调用创建新连接，避免跨线程问题）"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # 让查询结果支持按列名访问
        conn.execute("PRAGMA journal_mode=WAL")  # 提升并发写入性能
        return conn

    def _init_db(self):
        """建表（幂等——IF NOT EXISTS）+ 自动迁移旧数据库"""
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS subjects (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    name        TEXT    NOT NULL UNIQUE,
                    created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
                );

                CREATE TABLE IF NOT EXISTS questions (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject_id      INTEGER NOT NULL,
                    stem            TEXT    NOT NULL,          -- 题干
                    option_a        TEXT    NOT NULL DEFAULT '',
                    option_b        TEXT    NOT NULL DEFAULT '',
                    option_c        TEXT    NOT NULL DEFAULT '',
                    option_d        TEXT    NOT NULL DEFAULT '',
                    correct_answer  TEXT    NOT NULL,          -- 'A' | 'B' | 'C' | 'D'
                    wrong_count     INTEGER NOT NULL DEFAULT 0,
                    last_wrong_at   TEXT,
                    starred         INTEGER NOT NULL DEFAULT 0,
                    question_type   TEXT    NOT NULL DEFAULT 'single',
                    created_at      TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
                    FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS review_history (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_id     INTEGER NOT NULL,
                    result          TEXT    NOT NULL,       -- 'correct' | 'wrong'
                    reviewed_at     TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
                    FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_questions_subject
                    ON questions(subject_id);

                CREATE INDEX IF NOT EXISTS idx_review_question
                    ON review_history(question_id);
            """)

            # ── 迁移：为旧数据库补充可能缺失的新字段 ──
            for col_sql in [
                "ALTER TABLE questions ADD COLUMN wrong_count INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE questions ADD COLUMN last_wrong_at TEXT",
                "ALTER TABLE questions ADD COLUMN starred INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE questions ADD COLUMN question_type TEXT NOT NULL DEFAULT 'single'",
                "ALTER TABLE questions ADD COLUMN option_e TEXT NOT NULL DEFAULT ''",
            ]:
                try:
                    conn.execute(col_sql)
                except sqlite3.OperationalError:
                    pass  # 列已存在，忽略

            # ── 迁移：添加题型字段 ──
            try:
                conn.execute("ALTER TABLE questions ADD COLUMN question_type TEXT NOT NULL DEFAULT 'single'")
            except sqlite3.OperationalError:
                pass

    @staticmethod
    def ensure_images_dir() -> str:
        """确保 images/ 子目录存在，返回其绝对路径"""
        base = os.path.dirname(os.path.abspath(__file__))
        images_dir = os.path.join(base, "images")
        os.makedirs(images_dir, exist_ok=True)
        return images_dir

    # ───────────────────────────── 学科操作 ─────────────────────────────

    def add_subject(self, name: str) -> int:
        """添加学科，返回 id；若已存在则直接返回 id"""
        with self._get_conn() as conn:
            try:
                cur = conn.execute("INSERT INTO subjects (name) VALUES (?)", (name,))
                return cur.lastrowid
            except sqlite3.IntegrityError:
                # 学科名已存在
                row = conn.execute("SELECT id FROM subjects WHERE name = ?", (name,)).fetchone()
                return row["id"]

    def get_subjects(self) -> list[dict]:
        """返回所有学科列表"""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT id, name, created_at FROM subjects ORDER BY id"
            ).fetchall()
            return [dict(r) for r in rows]

    def delete_subject(self, subject_id: int) -> bool:
        """删除学科及其所有题目"""
        with self._get_conn() as conn:
            conn.execute("DELETE FROM questions WHERE subject_id = ?", (subject_id,))
            conn.execute("DELETE FROM subjects WHERE id = ?", (subject_id,))
            return conn.total_changes > 0

    def get_subject_name(self, subject_id: int) -> Optional[str]:
        """根据 id 获取学科名称"""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT name FROM subjects WHERE id = ?", (subject_id,)
            ).fetchone()
            return row["name"] if row else None

    # ───────────────────────────── 题目操作 ─────────────────────────────

    def add_question(
        self,
        subject_id: int,
        stem: str,
        option_a: str,
        option_b: str,
        option_c: str,
        option_d: str,
        correct_answer: str,
    ) -> int:
        """添加一道题目，返回其 id"""
        with self._get_conn() as conn:
            cur = conn.execute(
                """INSERT INTO questions
                   (subject_id, stem, option_a, option_b, option_c, option_d, correct_answer)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (subject_id, stem, option_a, option_b, option_c, option_d, correct_answer),
            )
            return cur.lastrowid

    def add_questions_batch(self, subject_id: int, questions: list[dict]) -> int:
        """批量添加题目（事务），返回添加数量"""
        with self._get_conn() as conn:
            conn.execute("BEGIN")
            count = 0
            for q in questions:
                conn.execute(
                    """INSERT INTO questions
                       (subject_id, stem, option_a, option_b, option_c, option_d, correct_answer)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        subject_id,
                        q["stem"],
                        q["option_a"],
                        q["option_b"],
                        q["option_c"],
                        q["option_d"],
                        q["correct_answer"],
                    ),
                )
                count += 1
            conn.execute("COMMIT")
            return count

    def get_questions(self, subject_id: int) -> list[dict]:
        """返回指定学科的全部题目（含 wrong_count, starred 等字段）"""
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT id, subject_id, stem,
                          option_a, option_b, option_c, option_d,
                          correct_answer, wrong_count, last_wrong_at, starred, question_type, created_at
                   FROM questions
                   WHERE subject_id = ?
                   ORDER BY id""",
                (subject_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def count_questions(self, subject_id: int) -> int:
        """统计某学科下题目总数"""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM questions WHERE subject_id = ?",
                (subject_id,),
            ).fetchone()
            return row["cnt"]

    def delete_question(self, question_id: int) -> bool:
        """删除单道题目"""
        with self._get_conn() as conn:
            conn.execute("DELETE FROM questions WHERE id = ?", (question_id,))
            return conn.total_changes > 0

    # ───────────────────────────── 新增：题目编辑 ─────────────────────────────

    def update_question(self, question_id: int, stem: str,
                        option_a: str, option_b: str, option_c: str, option_d: str,
                        correct_answer: str) -> bool:
        """修改一道题目的内容，返回是否成功"""
        with self._get_conn() as conn:
            cur = conn.execute(
                """UPDATE questions SET stem=?, option_a=?, option_b=?, option_c=?, option_d=?, correct_answer=?
                   WHERE id=?""",
                (stem, option_a, option_b, option_c, option_d, correct_answer, question_id),
            )
            return cur.rowcount > 0

    def search_questions(self, subject_id: int, keyword: str) -> list[dict]:
        """在指定学科的题干中搜索关键词"""
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT id, subject_id, stem, option_a, option_b, option_c, option_d,
                          correct_answer, wrong_count, last_wrong_at, starred, question_type, created_at
                   FROM questions
                   WHERE subject_id=? AND stem LIKE ?
                   ORDER BY id""",
                (subject_id, f"%{keyword}%"),
            ).fetchall()
            return [dict(r) for r in rows]

    # ───────────────────────────── 新增：统计 ─────────────────────────────

    def get_subject_stats(self, subject_id: int) -> dict:
        """返回某学科统计：总题数、答题次数、正确数、累计错误、正确率"""
        with self._get_conn() as conn:
            total = conn.execute(
                "SELECT COUNT(*) AS c FROM questions WHERE subject_id=?", (subject_id,)
            ).fetchone()["c"]
            wrong = conn.execute(
                "SELECT COALESCE(SUM(wrong_count),0) AS c FROM questions WHERE subject_id=?",
                (subject_id,),
            ).fetchone()["c"]
            reviewed = conn.execute(
                """SELECT COUNT(*) AS c FROM review_history
                   WHERE question_id IN (SELECT id FROM questions WHERE subject_id=?)""",
                (subject_id,),
            ).fetchone()["c"]
            correct = conn.execute(
                """SELECT COUNT(*) AS c FROM review_history
                   WHERE result='correct' AND question_id IN (SELECT id FROM questions WHERE subject_id=?)""",
                (subject_id,),
            ).fetchone()["c"]
            accuracy = round(correct / reviewed * 100, 1) if reviewed > 0 else 0.0
            return {"total": total, "answered": reviewed, "correct": correct,
                    "wrong_total": wrong, "accuracy": accuracy}

    def get_all_stats(self) -> list[dict]:
        """返回所有学科的统计列表"""
        result = []
        for s in self.get_subjects():
            stats = self.get_subject_stats(s["id"])
            stats["subject_id"] = s["id"]
            stats["subject_name"] = s["name"]
            result.append(stats)
        return result

    # ───────────────────────────── 新增：答题记录 ─────────────────────────────

    def record_review(self, question_id: int, is_correct: bool):
        """记录一次答题结果，更新错题计数和时间"""
        result = "correct" if is_correct else "wrong"
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO review_history (question_id, result) VALUES (?, ?)",
                (question_id, result),
            )
            if not is_correct:
                conn.execute(
                    """UPDATE questions SET wrong_count=wrong_count+1,
                            last_wrong_at=datetime('now','localtime') WHERE id=?""",
                    (question_id,),
                )

    def get_wrong_questions(self, subject_id: int, min_wrong: int = 1) -> list[dict]:
        """返回某学科中错误次数 >= min_wrong 的题目"""
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT id, subject_id, stem, option_a, option_b, option_c, option_d,
                          correct_answer, wrong_count, last_wrong_at, starred, question_type, created_at
                   FROM questions
                   WHERE subject_id=? AND wrong_count>=?
                   ORDER BY wrong_count DESC, last_wrong_at DESC""",
                (subject_id, min_wrong),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_all_wrong_questions(self, min_wrong: int = 1) -> list[dict]:
        """返回所有学科中错误次数 >= min_wrong 的题目（含 subject_name）"""
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT q.*, s.name AS subject_name
                   FROM questions q JOIN subjects s ON q.subject_id=s.id
                   WHERE q.wrong_count>=?
                   ORDER BY q.wrong_count DESC, q.last_wrong_at DESC""",
                (min_wrong,),
            ).fetchall()
            return [dict(r) for r in rows]

    def toggle_star(self, question_id: int) -> bool:
        """切换星标状态，返回新状态（True=星标）"""
        with self._get_conn() as conn:
            cur = conn.execute("SELECT starred FROM questions WHERE id=?", (question_id,))
            row = cur.fetchone()
            if row is None:
                return False
            new_val = 0 if row["starred"] else 1
            conn.execute("UPDATE questions SET starred=? WHERE id=?", (new_val, question_id))
            return bool(new_val)

    def get_starred_questions(self, subject_id: int) -> list[dict]:
        """返回某学科中星标的题目"""
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT id, subject_id, stem, option_a, option_b, option_c, option_d,
                          correct_answer, wrong_count, last_wrong_at, starred, question_type, created_at
                   FROM questions
                   WHERE subject_id=? AND starred=1
                   ORDER BY id""",
                (subject_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    # ───────────────────────────── 新增：导入导出 ─────────────────────────────

    def export_all_questions(self) -> list[dict]:
        """导出全部题目（含学科名），用于备份"""
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT q.id, s.name AS subject_name, q.stem,
                          q.option_a, q.option_b, q.option_c, q.option_d,
                          q.correct_answer, q.wrong_count, q.starred, q.question_type, q.created_at
                   FROM questions q JOIN subjects s ON q.subject_id=s.id
                   ORDER BY s.id, q.id"""
            ).fetchall()
            return [dict(r) for r in rows]

    def import_from_json(self, data: list[dict]) -> int:
        """从 JSON 数据批量导入题目，返回导入数量"""
        count = 0
        with self._get_conn() as conn:
            conn.execute("BEGIN")
            for item in data:
                sid = self.add_subject(item["subject_name"])
                conn.execute(
                    """INSERT INTO questions
                       (subject_id, stem, option_a, option_b, option_c, option_d,
                        correct_answer, wrong_count, starred)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (sid, item["stem"], item.get("option_a", ""), item.get("option_b", ""),
                     item.get("option_c", ""), item.get("option_d", ""),
                     item["correct_answer"], item.get("wrong_count", 0), item.get("starred", 0)),
                )
                count += 1
            conn.execute("COMMIT")
        return count
