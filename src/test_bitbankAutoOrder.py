# -*- coding: utf-8 -*-

from bitbankAutoOrder import Bitbank


def test_patch_get_xrp_jpy_value(monkeypatch):
    """ [Mock Patch]
    参考：http://thinkami.hatenablog.com/entry/2017/03/07/065903
    """
    last = 50.1
    sell = 53.1
    buy = 49.2
    monkeypatch.setattr(Bitbank, 'get_xrp_jpy_value',
                        lambda x: (last, sell, buy))
    sut = Bitbank()
    last, sell, buy = sut.get_xrp_jpy_value()
    assert (last, sell, buy) == (50.1, 53.1, 49.2)


def test_get_xrp_jpy_value():
    bb = Bitbank()
    last, sell, buy = bb.get_xrp_jpy_value()
    f_last = float(last)
    f_sell = float(sell)
    f_buy = float(buy)
    assert (f_last, f_sell, f_buy) > (0.0, 0.0, 0.0)


def test_get_total_assets():
    bb = Bitbank()
    total_assets = bb.get_total_assets()
    assert total_assets > 0.0
