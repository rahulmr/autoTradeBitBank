import time
from datetime import datetime, timedelta

import pandas as pd
import pandas_datareader.data as web

import technicalAnalysis

NY_DOW_SYMBOLS = {"AAPL", "AXP", "BA", "CAT", "CSCO",
                  "CVX", "DIS", "DWDP", "GS", "HD",
                  "IBM", "INTC", "JNJ", "JPM", "KO",
                  "MCD", "MMM", "MRK", "MSFT", "NKE",
                  "PFE", "PG", "TRV", "UNH", "UTX",
                  "V", "VZ", "WBA", "WMT", "XOM"}

NASDAQ_100_SYMBOLS = {"AAL", "AAPL", "ADBE", "ADI", "ADP",
                      "ADSK", "ALGN", "ALXN", "AMAT", "AMGN",
                      "AMZN", "ASML", "ATVI", "AVGO", "BIDU",
                      "BIIB", "BKNG", "BMRN", "CA", "CDNS",
                      "CELG", "CERN", "CHKP", "CHTR", "CMCSA",
                      "COST", "CSCO", "CSX", "CTAS", "CTRP",
                      "CTSH", "CTXS", "DISH", "DLTR", "EA",
                      "EBAY", "ESRX", "EXPE", "FAST", "FB",
                      "FISV", "FOX", "FOXA", "GILD", "GOOG",
                      "GOOGL", "HAS", "HOLX", "HSIC", "IDXX",
                      "ILMN", "INCY", "INTC", "INTU", "ISRG",
                      "JBHT", "JD", "KHC", "KLAC", "LBTYA",
                      "LBTYK", "LRCX", "MAR", "MCHP", "MDLZ",
                      "MELI", "MNST", "MSFT", "MU", "MXIM",
                      "MYL", "NFLX", "NTES", "NVDA", "ORLY",
                      "PAYX", "PCAR", "PYPL", "QCOM", "QRTEA",
                      "REGN", "ROST", "SBUX", "SHPG", "SIRI",
                      "SNPS", "STX", "SWKS", "SYMC", "TMUS",
                      "TSLA", "TTWO", "TXN", "ULTA", "VOD",
                      "VRSK", "VRTX", "WBA", "WDAY", "WDC",
                      "WYNN", "XLNX", "XRAY"}

SP_100_SYMBOLS = {"AAPL", "ABBV", "ABT", "ACN", "AGN",
                  "AIG", "ALL", "AMGN", "AMZN", "AXP",
                  "BA", "BAC", "BIIB", "BK", "BKNG",
                  "BLK", "BMY", "BRK.B", "C", "CAT",
                  "CELG", "CHTR", "CL", "CMCSA", "COF",
                  "COP", "COST", "CSCO", "CVS", "CVX",
                  "DHR", "DIS", "DUK", "DWDP", "EMR",
                  "EXC", "F", "FB", "FDX", "FOX",
                  "FOXA", "GD", "GE", "GILD", "GM",
                  "GOOG", "GOOGL", "GS", "HAL", "HD",
                  "HON", "IBM", "INTC", "JNJ", "JPM",
                  "KHC", "KMI", "KO", "LLY", "LMT",
                  "LOW", "MA", "MCD", "MDLZ", "MDT",
                  "MET", "MMM", "MO", "MRK", "MS",
                  "MSFT", "NEE", "NFLX", "NKE", "NVDA",
                  "ORCL", "OXY", "PEP", "PFE", "PG",
                  "PM", "PYPL", "QCOM", "RTN", "SBUX",
                  "SLB", "SO", "SPG", "T", "TGT",
                  "TXN", "UNH", "UNP", "UPS", "USB",
                  "UTX", "V", "VZ", "WBA", "WFC",
                  "WMT", "XOM"}

# 高リターンランキング上位22 & 高成長のグロース株もおすすめ銘柄として要注目
# https://america-kabu.com/2018/01/07/watch-list-on-us-stock/
GOOD_SYMBOLS = {"PM", "MO", "ABBV", "ABT", "KO",
                      "CL", "BMY", "PEP", "MRK", "HNZ",
                      "CVS", "TR", "CR", "HSY", "PFE",
                      "EQT", "GIS", "OKE", "PG", "DE",
                      "KR", "MHP", "FB", "AMZN", "GOOG",
                      "APPL", "MSFT"}

# 結合（重複削除）
NY_DOW_SP_SYMBOLS = NY_DOW_SYMBOLS | NASDAQ_100_SYMBOLS | SP_100_SYMBOLS
# TARGET_SYMBOLS = NY_DOW_SP_SYMBOLS & GOOD_SYMBOLS
TARGET_SYMBOLS = NY_DOW_SP_SYMBOLS


class Rakuten():

    def get_rakuten_stocks(self):
        """
        楽天信託で取り扱っている株式情報（取扱が"○"）を
        今日（UTC）から３０日間分のデータを
        pandasのDataFrame形式で返却します。

        # CSVデータ 抜粋
        現地コード,銘柄名(English),銘柄名,市場,業種,取扱
        AMZN,"AMAZON.COM, INC.",アマゾン・ドット・コム,NASDAQ,小売,○
        KO,THE COCA-COLA COMPANY,コカ・コーラ,NYSE,食品・飲料,○
        MCD,MCDONALD'S CORPORATION,マクドナルド,NYSE,外食・レストラン,○
        AAPL,APPLE INC.,アップル,NASDAQ,コンピュータ関連,○
        ：
        """
        df_rakuten = pd.read_csv(self.get_rakuten_csv())
        now = datetime.utcfromtimestamp(time.time())
        days30_ago = now - timedelta(days=30)

        return df_rakuten, days30_ago, now

    def get_rakuten_csv(self):
        """
        楽天証券 米国株式 からCSVをダウンロードする。

        # 楽天証券 米国株式 CSV取得コマンド
        curl -O https://www.trkd-asia.com/rakutensec/exportcsvus?name=
        &r1=on&all=on&vall=on&forwarding=na&target=0&theme=na&returns=na&head_office=na&sector=na
        """
        CSV_FILE_PATH = "./csv/rakuten_us_stock.csv"
        # TODO CSV_FILE_FILEにCSVをダウンロードする。

        return CSV_FILE_PATH

    def notify_rsi_under_20(self, symbol, candle):
        # TODO RSI/RSCを計算する
        # RSI が 20 % 以下の場合にLINE通知する
        pass


# main
if __name__ == '__main__':
    r = Rakuten()
    df, start, end = r.get_rakuten_stocks()

    symbols = set(df["現地コード"]) & TARGET_SYMBOLS

    for symbol in TARGET_SYMBOLS:
        try:
            df_rakuten_candle = web.DataReader(
                symbol, 'morningstar', start, end)
            r.notify_rsi_under_20(symbol, df_rakuten_candle)
        except ValueError as ve:
            msg = "\[{}\] is \[{}\]".format(symbol, ve)
            print(msg)
        print(df_rakuten_candle)
