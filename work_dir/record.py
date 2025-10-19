import os
import csv


class TradeRecorder:
    def __init__(self, path="record.csv"):
        self.path = path
        self.unclosed_trades = {}  # 用字符串化的 id 作为 key
        self.fieldnames = ['id', 'pair', 'dir', 'amount', 'entrprice', 'closeprice', 'opentime', 'closetime', 'profit']
        self._init_csv_writer()

    def _init_csv_writer(self):
        file_exists = os.path.exists(self.path)
        self.file = open(self.path, 'a', newline='', encoding='utf-8')
        self.writer = csv.DictWriter(self.file, fieldnames=self.fieldnames)
        if not file_exists:
            self.writer.writeheader()
            print('[TradeRecorder] CSV header created.')

    def open_record(self, id, pair, dir, amount, entrprice, time):
        id = str(id)
        trade = {
            "id": id,
            "pair": pair,
            "dir": dir,
            "amount": amount,
            "entrprice": entrprice,
            "opentime": time,
            "closeprice": "",
            "closetime": "",
            "profit": ""
        }
        self.unclosed_trades[id] = trade
        print(f'[TradeRecorder] Opened trade: {trade}')

    def close_record(self, id, amount, closeprice, profit, time):
        id = str(id)
        print(f'[TradeRecorder] Attempting to close trade with id={id}')
        print(f'[TradeRecorder] Current open IDs: {list(self.unclosed_trades.keys())}')

        if id not in self.unclosed_trades:
            print(f'[TradeRecorder] ❌ No open trade found with id: {id}')
            return False

        trade = self.unclosed_trades.pop(id)
        trade["amount"] = amount
        trade["closeprice"] = closeprice
        trade["profit"] = profit
        trade["closetime"] = time

        # 写入完整字段到 CSV
        self.writer.writerow({key: trade.get(key, "") for key in self.fieldnames})
        self.file.flush()
        print(f'[TradeRecorder] ✅ Closed and recorded trade: {trade}')
        return True

    def get_unclosed(self, id=None):
        if id is not None:
            return self.unclosed_trades.get(str(id))
        return self.unclosed_trades

    def close(self):
        self.file.close()
        print('[TradeRecorder] File closed.')