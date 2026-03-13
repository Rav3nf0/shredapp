import sqlite3
from datetime import datetime

class ShredDB:
    def __init__(self, db_name="shred_private.db"):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS daily_metrics 
            (id INTEGER PRIMARY KEY, 
             date TEXT, 
             type TEXT, 
             value REAL, 
             protein REAL, 
             note TEXT)''')
        self.conn.commit()

    def log_metric(self, entry_type, value, protein=0, note=""):
        cursor = self.conn.cursor()
        today = datetime.now().strftime("%Y-%m-%d")
        cursor.execute("INSERT INTO daily_metrics (date, type, value, protein, note) VALUES (?,?,?,?,?)",
                       (today, entry_type, value, protein, note))
        self.conn.commit()

    def get_daily_summary(self):
        cursor = self.conn.cursor()
        today = datetime.now().strftime("%Y-%m-%d")
        cursor.execute("SELECT SUM(value), SUM(protein) FROM daily_metrics WHERE date=? AND type='meal'", (today,))
        meals = cursor.fetchone()
        cursor.execute("SELECT SUM(value) FROM daily_metrics WHERE date=? AND type='workout'", (today,))
        burn = cursor.fetchone()[0] or 0
        return {
            "calories_in": meals[0] or 0,
            "protein_in": meals[1] or 0,
            "calories_out": burn
        }