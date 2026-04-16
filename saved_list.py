"""
保存済み企業リスト管理モジュール
SQLiteを使って企業情報を永続保存する
"""
import sqlite3
import pandas as pd
from pathlib import Path
from datetime import datetime

SAVED_DB = "saved_companies.db"

def init_db():
    """DBとテーブルを初期化する"""
    conn = sqlite3.connect(SAVED_DB)
    cur  = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS saved_companies (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            社名        TEXT NOT NULL,
            郵便番号    TEXT,
            住所        TEXT,
            TEL         TEXT,
            WebサイトURL TEXT,
            法人番号    TEXT,
            法人種別    TEXT,
            代表者名    TEXT,
            資本金      TEXT,
            従業員数    TEXT,
            設立年      TEXT,
            事業内容    TEXT,
            Web提案スコア INTEGER,
            Web提案優先度 TEXT,
            LED提案スコア INTEGER,
            LED提案優先度 TEXT,
            AI営業ポイント TEXT,
            保存日時    TEXT,
            メモ        TEXT,
            UNIQUE(社名, TEL)
        )
    """)
    conn.commit()
    conn.close()


def save_companies(df: pd.DataFrame, indices: list) -> tuple[int, int]:
    """
    選択した企業をDBに保存する。
    戻り値: (保存件数, スキップ件数（重複）)
    """
    init_db()
    conn    = sqlite3.connect(SAVED_DB)
    cur     = conn.cursor()
    saved   = 0
    skipped = 0
    now     = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for i in indices:
        row = df.loc[i]
        try:
            cur.execute("""
                INSERT INTO saved_companies
                (社名, 郵便番号, 住所, TEL, WebサイトURL, 法人番号, 法人種別,
                 代表者名, 資本金, 従業員数, 設立年, 事業内容,
                 Web提案スコア, Web提案優先度, LED提案スコア, LED提案優先度,
                 AI営業ポイント, 保存日時, メモ)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                row.get("社名", ""),
                row.get("郵便番号", ""),
                row.get("住所", ""),
                row.get("TEL", ""),
                row.get("WebサイトURL", ""),
                row.get("法人番号", ""),
                row.get("法人種別", ""),
                row.get("代表者名", ""),
                row.get("資本金", ""),
                row.get("従業員数", ""),
                row.get("設立年", ""),
                row.get("事業内容", ""),
                row.get("Web提案スコア", 0),
                row.get("Web提案優先度", ""),
                row.get("LED提案スコア", 0),
                row.get("LED提案優先度", ""),
                row.get("AI営業ポイント", ""),
                now,
                "",
            ))
            saved += 1
        except sqlite3.IntegrityError:
            skipped += 1

    conn.commit()
    conn.close()
    return saved, skipped


def load_saved_companies() -> pd.DataFrame:
    """保存済み企業一覧を取得する"""
    init_db()
    conn = sqlite3.connect(SAVED_DB)
    df   = pd.read_sql_query(
        "SELECT * FROM saved_companies ORDER BY 保存日時 DESC", conn
    )
    conn.close()
    return df


def delete_companies(ids: list):
    """指定したIDの企業を削除する"""
    if not ids:
        return
    conn = sqlite3.connect(SAVED_DB)
    cur  = conn.cursor()
    cur.executemany("DELETE FROM saved_companies WHERE id = ?", [(i,) for i in ids])
    conn.commit()
    conn.close()


def update_memo(company_id: int, memo: str):
    """メモを更新する"""
    conn = sqlite3.connect(SAVED_DB)
    cur  = conn.cursor()
    cur.execute("UPDATE saved_companies SET メモ = ? WHERE id = ?", (memo, company_id))
    conn.commit()
    conn.close()


def count_saved() -> int:
    """保存件数を返す"""
    init_db()
    conn = sqlite3.connect(SAVED_DB)
    cur  = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM saved_companies")
    count = cur.fetchone()[0]
    conn.close()
    return count
