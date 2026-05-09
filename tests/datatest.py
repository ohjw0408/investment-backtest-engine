# check_db.py
import sqlite3
conn = sqlite3.connect('data/meta/symbol_master.db')
print('005930:', conn.execute('SELECT * FROM symbols WHERE code=?', ('005930',)).fetchone())
kr_cnt = conn.execute('SELECT COUNT(*) FROM symbols WHERE country=? AND is_etf=0', ('KR',)).fetchone()
print('KR 개별종목:', kr_cnt)
conn.close()