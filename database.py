"""
데이터베이스 관리 모듈
SQLite를 사용한 장전 종목 데이터 저장
"""

import sqlite3
import json
from datetime import datetime
import os

class Database:
    def __init__(self, db_path='data/morning_candidates.db'):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.init_database()

    def init_database(self):
        """데이터베이스 초기화 및 테이블 생성"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # morning_candidates 테이블 생성
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS morning_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                stock_code TEXT NOT NULL,
                stock_name TEXT NOT NULL,
                current_price REAL,
                price_change_percent REAL,
                trading_value REAL,
                volume REAL,
                market_cap REAL,
                total_score REAL,
                price_score REAL,
                volume_score REAL,
                theme_score REAL,
                news_score REAL,
                matched_themes TEXT,
                news_mentions INTEGER,
                created_at TEXT NOT NULL,
                UNIQUE(date, stock_code)
            )
        ''')

        # 인덱스 생성
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_date
            ON morning_candidates(date)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_score
            ON morning_candidates(total_score DESC)
        ''')

        conn.commit()
        conn.close()

    def save_candidates(self, candidates, date=None):
        """선정된 종목들을 데이터베이스에 저장"""
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        saved_count = 0
        for candidate in candidates:
            try:
                score_detail = candidate.get('score_detail', {})

                cursor.execute('''
                    INSERT OR REPLACE INTO morning_candidates (
                        date, stock_code, stock_name,
                        current_price, price_change_percent,
                        trading_value, volume, market_cap,
                        total_score, price_score, volume_score,
                        theme_score, news_score,
                        matched_themes, news_mentions,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    date,
                    candidate.get('code', ''),
                    candidate.get('name', ''),
                    candidate.get('current_price', 0),
                    candidate.get('price_change_percent', 0),
                    candidate.get('trading_value', 0),
                    candidate.get('volume', 0),
                    candidate.get('market_cap', 0),
                    candidate.get('total_score', 0),
                    score_detail.get('disclosure', 0),
                    score_detail.get('investor', 0),
                    score_detail.get('theme_keywords', 0),
                    score_detail.get('news', 0),
                    json.dumps(candidate.get('matched_themes', []), ensure_ascii=False),
                    candidate.get('news_mentions', 0),
                    datetime.now().isoformat()
                ))
                saved_count += 1

            except Exception as e:
                print(f"⚠️  종목 저장 실패 ({candidate.get('name', 'Unknown')}): {e}")

        conn.commit()
        conn.close()

        print(f"✓ DB 저장 완료: {saved_count}개 종목")
        return saved_count

    def get_candidates_by_date(self, date):
        """특정 날짜의 선정 종목 조회"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM morning_candidates
            WHERE date = ?
            ORDER BY total_score DESC
        ''', (date,))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_recent_candidates(self, days=7):
        """최근 N일간의 선정 종목 조회"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM morning_candidates
            WHERE date >= date('now', '-' || ? || ' days')
            ORDER BY date DESC, total_score DESC
        ''', (days,))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_all_dates(self):
        """저장된 모든 날짜 목록 조회"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT DISTINCT date
            FROM morning_candidates
            ORDER BY date DESC
        ''')

        dates = [row[0] for row in cursor.fetchall()]
        conn.close()

        return dates

    def export_to_json(self, date=None, output_path=None):
        """데이터베이스 내용을 JSON으로 내보내기"""
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')

        candidates = self.get_candidates_by_date(date)

        result = {
            'generated_at': datetime.now().isoformat(),
            'date': date,
            'count': len(candidates),
            'candidates': candidates
        }

        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"✓ JSON 내보내기 완료: {output_path}")

        return result


if __name__ == '__main__':
    # 테스트
    db = Database()
    print("✓ 데이터베이스 초기화 완료")

    # 최근 데이터 조회 테스트
    dates = db.get_all_dates()
    print(f"✓ 저장된 날짜: {len(dates)}일")
