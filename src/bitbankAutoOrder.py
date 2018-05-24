# -*- coding: utf-8 -*-

import os
import sys
import traceback
import time
import requests
import pandas
import logging
from logging import getLogger, StreamHandler, DEBUG
from datetime import datetime, timezone, timedelta

import python_bitbankcc

from datetime import datetime, timedelta, timezone


class MyUtil:
    """ 処理に依存しない自分専用のユーティリティクラス """

    def get_timestamp(self):
        """ JSTのタイムスタンプを取得する """
        JST = timezone(timedelta(hours=+9), 'JST')
        return datetime.now(JST).strftime('%Y/%m/%d %H:%M:%S')


class MyTechnicalAnalysisUtil:
    """ テクニカル分析のユーティリティクラス
    https://www.rakuten-sec.co.jp/MarketSpeed/onLineHelp/msman2_5_1_2.html

    PRAM:
        n: 対象データ数(5とか14くらいが良いとされる)
        cadle_type: "1min","5min","15min","30min","1hour"のいづれか。
    """

    def __init__(self):
        """ コンストラクタ """
        self.pubApi = python_bitbankcc.public()
        self.RSI_N = 14

    def get_candlestick(self, n: int, candle_type):
        now = time.time()
        utc = datetime.utcfromtimestamp(now)

        yyyymmdd = utc.strftime('%Y%m%d')
        candlestick = self.pubApi.get_candlestick(
            "xrp_jpy", candle_type, yyyymmdd)

        ohlcv = candlestick["candlestick"][0]["ohlcv"]
        df_ohlcv = pandas.DataFrame(ohlcv,
                                    columns=["open",   # 始値
                                             "hight",   # 高値
                                             "low",     # 安値
                                             "close",     # 終値
                                             "amount",  # 出来高
                                             "time"])   # UnixTime

        if(len(ohlcv) <= n):  # データが不足している場合
            yesterday = (datetime.now() - datetime.timedelta(days=1))
            str_yesterday = yesterday.strftime('%Y%m%d')
            yday_candlestick = self.pubApi.get_candlestick(
                "xrp_jpy", candle_type, str_yesterday)
            yday_ohlcv = yday_candlestick["candlestick"][0]["ohlcv"]
            df_yday_ohlcv = pandas.DataFrame(yday_ohlcv,
                                             columns=["open",   # 始値
                                                      "hight",   # 高値
                                                      "low",     # 安値
                                                      "close",     # 終値
                                                      "amount",  # 出来高
                                                      "time"])   # UnixTime
            df_ohlcv.append(df_yday_ohlcv, ignore_index=True)  # 前日分追加

        return df_ohlcv

    def get_ema(self, candle_type, n_short, n_long):
        """ EMA(指数平滑移動平均)を返却する
        計算式：EMA ＝ 1分前のEMA+α(現在の終値－1分前のEMA)
            *移動平均の期間をn
            *α=2÷(n+1)
        参考
        http://www.algo-fx-blog.com/ema-how-to-do-with-python-pandas/
        """
        df_ema = self.get_candlestick(n_long, candle_type)

        df_ema['ema_short'] = df_ema['close'].ewm(span=int(n_short)).mean()
        df_ema['ema_long'] = df_ema['close'].ewm(span=int(n_long)).mean()

        return df_ema  # TODO

    def get_rsi(self, n: int, candle_type):
        """ RSI：50%を中心にして上下に警戒区域を設け、70%以上を買われすぎ、30%以下を売られすぎと判断します。
        計算式：RSI＝直近N日間の上げ幅合計の絶対値/（直近N日間の上げ幅合計の絶対値＋下げ幅合計の絶対値）×100
        参考
        http://www.algo-fx-blog.com/rsi-python-ml-features/
        """
        df_ohlcv = self.get_candlestick(n, candle_type)
        df_close = df_ohlcv["close"].astype('float')
        df_diff = df_close.diff()

        # 値上がり幅、値下がり幅をシリーズへ切り分け
        up, down = df_diff.copy(), df_diff.copy()
        up[up < 0] = 0
        down[down > 0] = 0

        up_sma_n = up.rolling(window=n, center=False).mean()  # mean:平均を計算
        down_sma_n = down.abs().rolling(window=n, center=False).mean()

        df_rs = up_sma_n / down_sma_n
        df_rsi = 100.0 - (100.0 / (1.0 + df_rs))

        return df_rsi[-1:].values.tolist()[0]  # 最新のRSIを返却（最終行）


class MyLogger:
    """ ログの出力表現を集中的に管理する自分専用クラス """

    def __init__(self):
        """ コンストラクタ """
        # 参考：http://joemphilips.com/post/python_logging/
        self.logger = getLogger(__name__)
        self.handler = StreamHandler()
        self.handler.setLevel(DEBUG)
        self.logger.setLevel(DEBUG)
        self.logger.addHandler(self.handler)
        formatter = logging.Formatter(
            "%(asctime)s %(name) %(levelname)s %(message)s")
        self.handler.setFormatter(formatter)

    def debug(self, msg):
        """ DEBUG	10	動作確認などデバッグの記録 """
        self.logger.debug(msg)

    def info(self, msg):
        """ INFO	20	正常動作の記録 """
        self.logger.info(msg)

    def warning(self, msg):
        """ WARNING	30	ログの定義名 """
        self.logger.warning(msg)

    def error(self, msg):
        """ ERROR	40	エラーなど重大な問題 """
        self.logger.error(msg)

    def critical(self, msg):
        """ CRITICAL	50	停止など致命的な問題 """
        self.logger.critical(msg)


class AutoOrder:
    """ 自動売買
    ■ 制御フロー
        全体処理 LOOP
            買い注文処理
                買い注文判定 LOOP
                買い注文約定待ち LOOP
                    買い注文約定判定
                        買い注文約定 BREAK
                    買い注文キャンセル判定
                        買い注文キャンセル注文
                        買い注文(成行)
                        CONTINUE(買い注文約定待ち LOOPへ)

            売り注文処理
                売り注文処理
                売り注文約定待ち LOOP
                    売り注文約定判定
                        売り注文約定 BREAK
                    損切処理判定
                        売り注文キャンセル注文
                        売り注文(成行)
                        売り注文(成行)約定待ち LOOP
    """

    def __init__(self):
        """ コンストラクタ """
        self.LOOP_COUNT_MAIN = 10
        self.AMOUNT = "1"

        self.BUY_ORDER_RANGE = 0.0
        self.SELL_ORDER_RANGE = 0.1
        self.POLLING_SEC_MAIN = 15
        self.POLLING_SEC_BUY = 0.1
        self.POLLING_SEC_SELL = 0.1

        self.myLogger = MyLogger()
        self.api_key = os.getenv("BITBANK_API_KEY")
        self.api_secret = os.getenv("BITBANK_API_SECRET")
        self.line_notify_token = os.getenv("LINE_NOTIFY_TOKEN")

        self.check_env()

        self.mu = MyUtil()
        self.mtau = MyTechnicalAnalysisUtil()

        self.pubApi = python_bitbankcc.public()
        self.prvApi = python_bitbankcc.private(self.api_key, self.api_secret)

    def check_env(self):
        """ 環境変数のチェック """
        if ((self.api_key is None) or (self.api_secret is None)):
            emsg = '''
            Please set BITBANK_API_KEY or BITBANK_API_SECRET in Environment !!
            ex) exoprt BITBANK_API_KEY=XXXXXXXXXXXXXXXXXX
            '''
            raise EnvironmentError(emsg)

        if (self.api_key is None):
            emsg = '''
            Please set LINE_NOTIFY_TOKEN in OS environment !!
            ex) exoprt LINE_NOTIFY_TOKEN=XXXXXXXXXXXXXXXXXX"
            '''
            raise EnvironmentError(emsg)

    def get_balances(self):
        """ 現在のXRP資産の取得 """
        self.myLogger.info(self.api_key)
        self.myLogger.info(self.api_secret)
        balances = self.prvApi.get_asset()
        for data in balances['assets']:
            if((data['asset'] == 'jpy') or (data['asset'] == 'xrp')):
                self.myLogger.info('●通貨：' + data['asset'])
                self.myLogger.info('保有量：' + data['onhand_amount'])

    def get_xrp_jpy_value(self):
        """ 現在のXRP価格を取得 """
        value = self.pubApi.get_ticker(
            'xrp_jpy'  # ペア
        )

        last = value['last']  # 現在値
        sell = value['sell']  # 現在の売り注文の最安値
        buy = value['buy']    # 現在の買い注文の最高値

        return last, sell, buy

    def get_active_orders(self):
        """ 現在のアクティブ注文情報を取得 """
        activeOrders = self.prvApi.get_active_orders('xrp_jpy')
        return activeOrders

    def is_fully_filled(self, orderResult, threshold_price):
        """ 注文の約定を判定 """
        last, _, _ = self.get_xrp_jpy_value()

        side = orderResult["side"]
        order_id = orderResult["order_id"]
        pair = orderResult["pair"]
        status = orderResult["status"]
        f_price = float(orderResult["price"])
        # f_start_amount = float(orderResult["remaining_amount"])    # 注文時の数量
        f_remaining_amount = float(orderResult["remaining_amount"])  # 未約定の数量
        f_executed_amount = float(orderResult["executed_amount"])    # 約定済み数量
        f_threshold_price = float(threshold_price)  # buy:買直し sell:損切 価格
        f_last = float(last)

        # self.myLogger.debug("注文時の数量：{0:.0f}".format(f_start_amount))
        result = False
        if (status == "FULLY_FILLED"):
            msg = ("{0} 注文 約定済 {7}：{1:.3f} 円 x {2:.0f}({3}) "
                   "[現在:{4:.3f}円] [閾値]：{5:.3f} ID：{6}")
            self.myLogger.info(msg.format(side,
                                          f_price,
                                          f_executed_amount,
                                          pair,
                                          f_last,
                                          f_threshold_price,
                                          order_id,
                                          status))
            result = True
        elif (status == "CANCELED_UNFILLED"):
            msg = ("{0} 注文 キャンセル済 {7}：{1:.3f} 円 x {2:.0f}({3}) "
                   "[現在:{4:.3f}円] [閾値]：{5:.3f} ID：{6}")
            self.myLogger.info(msg.format(side,
                                          f_price,
                                          f_executed_amount,
                                          pair,
                                          f_last,
                                          f_threshold_price,
                                          order_id,
                                          status))
            result = True
        else:
            msg = ("{0} 注文 約定待ち {7}：{1:.3f}円 x {2:.0f}({3}) "
                   "[現在:{4:.3f}円] [閾値]：{5:.3f} ID：{6}")
            self.myLogger.info(msg.format(side,
                                          f_price,
                                          f_remaining_amount,
                                          pair,
                                          f_last,
                                          f_threshold_price,
                                          order_id,
                                          status))
        return result

    def get_buy_order_info(self):
        """ 買い注文のリクエスト情報を取得 """
        _, _, buy = self.get_xrp_jpy_value()
        # 買い注文アルゴリズム
        buyPrice = str(float(buy) - self.BUY_ORDER_RANGE)

        buy_order_info = {"pair": "xrp_jpy",    # ペア
                          "amount": self.AMOUNT,  # 注文枚数
                          "price": buyPrice,    # 注文価格
                          "orderSide": "buy",   # buy or sell
                          "orderType": "limit"  # 指値注文の場合はlimit
                          }
        return buy_order_info

    def get_sell_order_info(self):
        """ 売り注文のリクエスト情報を取得 """
        _, sell, _ = self.get_xrp_jpy_value()
        # 売り注文アルゴリズム
        sellPrice = str(float(sell) + self.SELL_ORDER_RANGE)
        sell_order_info = {"pair": "xrp_jpy",      # ペア
                           "amount": self.AMOUNT,  # 注文枚数
                           "price": sellPrice,     # 注文価格
                           "orderSide": "sell",    # buy or sell
                           "orderType": "limit"    # 指値注文の場合はlimit
                           }
        return sell_order_info

    def get_sell_order_info_by_barket(self, amount, price):
        """ 売り注文(成行)のリクエスト情報を取得 """
        sell_order_info = {"pair": "xrp_jpy",      # ペア
                           "amount": amount,       # 注文枚数
                           "price": price,         # 注文価格
                           "orderSide": "sell",    # buy or sell
                           "orderType": "market"   # 成行注文の場合はmarket
                           }
        return sell_order_info

    def is_stop_loss(self, sell_order_result):
        """ 売り注文(損切注文)の判定 """
        last, _, _ = self.get_xrp_jpy_value()
        f_last = float(last)  # 現在値

        stop_loss_price = self.get_stop_loss_price(sell_order_result)
        if(stop_loss_price > f_last):
            msg = ("【損切判定されました 現在値：{0} 損切値：{1} 】"
                   .format(f_last, stop_loss_price))
            self.myLogger.info(msg)
            return True
        else:
            return False

    def get_stop_loss_price(self, sell_order_result):
        """ 損切価格の取得 """
        f_sell_order_price = float(sell_order_result["price"])  # 売り指定価格

        THRESHOLD = 10  # 閾値
        return f_sell_order_price - (self.SELL_ORDER_RANGE * THRESHOLD)

    def is_buy_order(self):
        """ 買い注文の判定 """
        f_rsi = float(self.mtau.get_rsi(self.mtau.RSI_N, "1min"))

        last, _, _ = self.get_xrp_jpy_value()
        f_last = float(last)  # 現在値

        RSI_THRESHOLD = 40
        msg = ("買い注文待ち 現在値：{0:.3f} RSI：{1:.3f} RSI閾値：{2}"
               .format(f_last, f_rsi, RSI_THRESHOLD))
        self.myLogger.debug(msg)

        if(f_rsi < RSI_THRESHOLD):
            return True

        return False

    def is_buy_order_cancel(self, buy_order_result):
        """ 買い注文のキャンセル判定 """
        last, _, _ = self.get_xrp_jpy_value()
        f_last = float(last)  # 現在値

        f_buy_order_price = float(buy_order_result["price"])
        f_last = float(last)
        f_buy_cancel_price = float(self.get_buy_cancel_price(buy_order_result))

        if (f_last > f_buy_cancel_price):
            msg = ("現在値：{0:.3f} 買い注文価格：{1:.3f} 再注文価格：{2:.3f}"
                   .format(f_last, f_buy_order_price, f_buy_cancel_price))
            self.myLogger.debug(msg)
            return True
        else:
            return False

    def get_buy_cancel_price(self, buy_order_result):
        """ 買い注文 キャンセル 価格 """
        f_buy_order_price = float(buy_order_result["price"])
        THRESHOLD = 0.5  # 再買い注文するための閾値
        return THRESHOLD + f_buy_order_price

    def buy_order(self):
        """ 買い注文処理 """

        # 買うタイミングを待つ
        while True:
            time.sleep(self.POLLING_SEC_BUY)

            if(self.is_buy_order()):
                break

        # 買い注文処理
        buy_order_info = self.get_buy_order_info()
        buy_value = self.prvApi.order(
            buy_order_info["pair"],  # ペア
            buy_order_info["price"],  # 価格
            buy_order_info["amount"],  # 注文枚数
            buy_order_info["orderSide"],  # 注文サイド 売 or 買(buy or sell)
            # 注文タイプ 指値 or 成行(limit or market))
            buy_order_info["orderType"]
        )

        self.notify_line(("デバッグ 買い注文処理発生！！ ID：{0}")
                         .format(buy_value["order_id"]))

        # 買い注文約定待ち
        while True:
            time.sleep(self.POLLING_SEC_BUY)

            # 買い注文結果を取得
            buy_order_result = self.prvApi.get_order(
                buy_value["pair"],     # ペア
                buy_value["order_id"]  # 注文タイプ 指値 or 成行(limit or market))
            )
            buy_cancel_price = self.get_buy_cancel_price(buy_order_result)

            # 買い注文の約定判定
            if(self.is_fully_filled(buy_order_result, buy_cancel_price)):
                break

            # 買い注文のキャンセル判定
            if (self.is_buy_order_cancel(buy_order_result)):
                # 買い注文(成行)
                buy_cancel_order_result = self.prvApi.cancel_order(
                    buy_order_result["pair"],     # ペア
                    buy_order_result["order_id"]  # 注文ID
                )

                self.notify_line(("デバッグ 買い注文キャンセル処理発生！！ ID：{0}")
                                 .format(buy_value["order_id"]))

                buy_cancel_price = self.get_buy_cancel_price(
                    buy_cancel_order_result)
                buy_order_result = buy_cancel_order_result
                continue  # 買い注文約定待ちループへ

        return buy_order_result  # 買い注文終了(売り注文へ)

    def sell_order(self, buy_order_result):
        """ 売り注文処理 """
        sell_order_info = self.get_sell_order_info()
        sell_order_result = self.prvApi.order(
            sell_order_info["pair"],       # ペア
            sell_order_info["price"],      # 価格
            sell_order_info["amount"],     # 注文枚数
            sell_order_info["orderSide"],  # 注文サイド 売 or 買(buy or sell)
            sell_order_info["orderType"]   # 注文タイプ 指値 or 成行(limit or market))
        )

        self.notify_line(("デバッグ 売り注文処理発生！！ ID：{0}")
                         .format(sell_order_result["order_id"]))

        while True:
            time.sleep(self.POLLING_SEC_SELL)

            sell_order_status = self.prvApi.get_order(
                sell_order_result["pair"],     # ペア
                sell_order_result["order_id"]  # 注文タイプ 指値 or 成行
            )

            stop_loss_price = self.get_stop_loss_price(sell_order_status)
            if (self.is_fully_filled(sell_order_status,
                                     stop_loss_price)):  # 売り注文約定判定
                order_id = sell_order_status["order_id"]
                f_amount = float(sell_order_status["executed_amount"])
                f_sell = float(sell_order_status["price"])
                f_buy = float(buy_order_result["price"])
                f_benefit = (f_sell - f_buy) * f_amount

                line_msg = "売り注文が約定！ 利益：{0:.3f}円 x {1:.0f}XRP ID：{0}"
                self.notify_line_stamp(line_msg.format(
                    f_benefit, f_amount, order_id), "1", "10")
                self.myLogger.debug(line_msg.format(
                    f_benefit, f_amount, order_id))

                break

            stop_loss_price = self.get_stop_loss_price(sell_order_status)
            if (self.is_stop_loss(sell_order_status)):  # 損切する場合
                # 約定前の売り注文キャンセル(結果のステータスはチェックしない)
                cancel_result = self.prvApi.cancel_order(
                    sell_order_status["pair"],     # ペア
                    sell_order_status["order_id"]  # 注文ID
                )

                order_id = cancel_result["order_id"]
                self.myLogger.debug("売りキャンセル注文ID：{0}".format(order_id))

                # 売り注文（成行）で損切
                amount = buy_order_result["start_amount"]
                price = buy_order_result["price"]  # 成行なので指定しても意味なし？
                sell_order_info_by_market = self.get_sell_order_info_by_barket(
                    amount, price)

                sell_market_result = self.prvApi.order(
                    sell_order_info_by_market["pair"],       # ペア
                    sell_order_info_by_market["price"],      # 価格
                    sell_order_info_by_market["amount"],     # 注文枚数
                    sell_order_info_by_market["orderSide"],
                    sell_order_info_by_market["orderType"]
                )

                order_id = sell_market_result["order_id"]
                self.myLogger.debug("売り注文（成行）ID：{0}".format(order_id))

                order_id = sell_market_result["order_id"]
                f_amount = float(sell_market_result["executed_amount"])
                f_sell = float(sell_market_result["price"])
                f_buy = float(sell_market_result["price"])
                f_benefit = (f_sell - f_buy) * f_amount

                line_msg = "売り注文(損切)！ 損失：{0:.3f}円 x {1:.0f}XRP ID：{0}"
                self.notify_line_stamp(line_msg.format(
                    f_benefit, f_amount, order_id), "1", "104")
                self.myLogger.debug(line_msg.format(
                    f_benefit, f_amount, order_id))

                sell_order_result = sell_market_result

        return buy_order_result, sell_order_result

    def order_buy_sell(self):
        """ 注文処理メイン（買い注文 → 売り注文） """
        buy_order_result = self.buy_order()
        buy_order_result, _ = self.sell_order(buy_order_result)

    def notify_line(self, message):
        """ LINE通知（messageのみ） """
        return self.notify_line_stamp(message, "", "")

    def notify_line_stamp(self, message, stickerPackageId, stickerId):
        """ LINE通知（スタンプ付き）
        LINEスタンプの種類は下記URL参照
        https://devdocs.line.me/files/sticker_list.pdf
        """
        line_notify_api = 'https://notify-api.line.me/api/notify'

        message = "{0}  {1}".format(self.mu.get_timestamp(), message)

        if(stickerPackageId == "" or stickerId == ""):
            payload = {'message': message}
        else:
            payload = {'message': message,
                       'stickerPackageId': stickerPackageId,
                       'stickerId': stickerId}

        headers = {'Authorization': 'Bearer ' +
                   self.line_notify_token}  # 発行したトークン
        return requests.post(line_notify_api, data=payload, headers=headers)


# main
if __name__ == '__main__':
    ao = AutoOrder()

    try:
        for i in range(0, ao.LOOP_COUNT_MAIN):
            ao.myLogger.info("#############################################")
            ao.myLogger.info("=== 実験[NO.{0}] ===".format(i))
            ao.order_buy_sell()
            time.sleep(ao.POLLING_SEC_MAIN)

            activeOrders = ao.get_active_orders()["orders"]
            if(len(activeOrders) != 0):
                ao.notify_line_stamp("売買数が合いません！！！ 注文数：{0}".format(
                    len(activeOrders)), "1", "422")
                ao.myLogger.debug("売買数が合いません！！！ 注文数：{0}".format(
                    len(activeOrders)))
                for i in range(len(activeOrders)):
                    ao.myLogger.debug(
                        "現在のオーダー一覧 :{0}".format(activeOrders[i]))

                break  # Mainループブレイク

        ao.get_balances()
        ao.notify_line_stamp("自動売買が終了！処理回数：{0}回".format(i + 1), "2", "516")

    except KeyboardInterrupt as ki:
        ao.notify_line_stamp("自動売買が中断されました 詳細：{0}".format(ki), "1", "3")
    except BaseException as be:
        ao.notify_line_stamp("システムエラーが発生しました！ 詳細：{0}".format(be), "1", "17")
        raise BaseException

    sys.exit()
