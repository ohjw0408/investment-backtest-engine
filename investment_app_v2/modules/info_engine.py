import sqlite3
import pandas as pd
from rapidfuzz import process, fuzz
from config import DB_PATH


class InfoEngine:

    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)

    def search_fuzzy(self, keyword):

        if not keyword:
            return []

        df = pd.read_sql("SELECT * FROM symbols", self.conn)

        if df.empty:
            return []

        choices = df["Name"] + " (" + df["Code"] + ")"

        results = process.extract(
            keyword,
            choices,
            scorer=fuzz.WRatio,
            limit=15
        )

        return [r[0] for r in results if r[1] > 60]

    def get_symbol_info(self, code):
        df = pd.read_sql(
            "SELECT * FROM symbols WHERE Code=?",
            self.conn,
            params=(code,)
        )
        return df