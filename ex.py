import re
import sqlite3
import time
from bs4 import BeautifulSoup
import requests

# 1. SQLiteデータベースとテーブルの準備
DB_NAME = "google_repos.db"


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # 既存のテーブルがあれば削除して作り直す（再実行時の重複防止）
    cursor.execute("DROP TABLE IF EXISTS repositories")
    cursor.execute("""
        CREATE TABLE repositories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            language TEXT,
            stars INTEGER
        )
    """)
    conn.commit()
    conn.close()


# 2. スクレイピング処理
def scrape_google_repositories():
    base_url = "https://github.com/orgs/google/repositories"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    page = 1
    total_count = 0

    while True:
        url = f"{base_url}?page={page}"
        print(f"Fetching: {url}")

        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print(f"アクセス終了またはエラー: Status {response.status_code}")
            break

        soup = BeautifulSoup(response.text, "html.parser")

        # リポジトリの各行（リスト要素）を取得
        # GitHubの仕様変更に備え、リポジトリリンク(/google/xxx)を含むリストアイテムを探索
        repo_items = soup.select("li.Box-row, div[data-testid='list-view-item']")

        # フォールバック：上記セレクタで取れない場合はリポジトリ名リンクの親要素から取得
        if not repo_items:
            repo_links = soup.find_all(
                "a", href=re.compile(r"^/google/[^/]+$")
            )
            # 重複排除しつつ親要素を取得
            seen = set()
            repo_items = []
            for a in repo_links:
                # ナビゲーション等のリンクを除外するためh3やh4内のリンクに絞る
                if a.find_parent(["h3", "h4"]):
                    parent = a.find_parent("li") or a.find_parent("div")
                    if parent and parent not in seen:
                        seen.add(parent)
                        repo_items.append(parent)

        # リポジトリが1件も見つからなければ最終ページとみなして終了
        if not repo_items:
            print("全ページの取得が完了しました。")
            break

        page_count = 0
        for item in repo_items:
            # --- リポジトリ名の取得 ---
            name_tag = item.find("a", href=re.compile(r"^/google/[^/]+$"))
            if not name_tag:
                continue
            repo_name = name_tag.get_text(strip=True)

            # --- 主要な言語の取得 ---
            lang_tag = item.find(attrs={"itemprop": "programmingLanguage"})
            if not lang_tag:
                # 別のHTML構造パターンへの対応
                lang_span = item.find("span", class_=re.compile(r"repo-language-color"))
                if lang_span and lang_span.find_next_sibling("span"):
                    lang_tag = lang_span.find_next_sibling("span")
            language = lang_tag.get_text(strip=True) if lang_tag else "None"

            # --- スターの数の取得 ---
            star_tag = item.find("a", href=re.compile(r"/stargazers$"))
            if star_tag:
                star_text = star_tag.get_text(strip=True).replace(",", "")
                # "1.2k" のような表記を数値に変換する処理
                if "k" in star_text.lower():
                    stars = int(float(star_text.lower().replace("k", "")) * 1000)
                else:
                    stars = int(star_text) if star_text.isdigit() else 0
            else:
                stars = 0

            # DBへ保存
            cursor.execute(
                "INSERT INTO repositories (name, language, stars) VALUES (?, ?, ?)",
                (repo_name, language, stars),
            )
            page_count += 1
            total_count += 1

        conn.commit()
        print(f"Page {page}: {page_count}件 保存完了 (累計: {total_count}件)")

        if page_count == 0:
            break

        page += 1
        # 要件：サーバー負荷軽減のための待機
        time.sleep(1)

    conn.close()


# 3. SELECT文で保存したデータを表示する処理
def display_data():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    print("\n--- 保存されたデータ（上位20件を表示） ---")
    cursor.execute("SELECT id, name, language, stars FROM repositories LIMIT 20")
    rows = cursor.fetchall()

    for row in rows:
        print(
            f"ID: {row[0]} | リポジトリ名: {row[1]} | 言語: {row[2]} | スター数:"
            f" {row[3]}"
        )

    cursor.execute("SELECT COUNT(*) FROM repositories")
    total = cursor.fetchone()[0]
    print(f"\n合計保存件数: {total}件")

    conn.close()


if __name__ == "__main__":
    init_db()
    scrape_google_repositories()
    display_data()