import unittest
import pyotp
import os
import sys
import time
from logzero import logger
import credentials as wd

root_directory = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.append(root_directory)

from SmartApi.smartConnect import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2

class LiveTestCases(unittest.TestCase):
    def setUp(self):
        self.api_key = wd.api_key
        self.username = wd.username
        self.pwd = wd.pwd
        self.token = wd.token
        self.totp = pyotp.TOTP(self.token).now()
        self.smart_api = SmartConnect(self.api_key)
        self.data = self.smart_api.generateSession(self.username, self.pwd, self.totp)
        self.authToken = self.data['data']['jwtToken']
        self.feedToken = self.smart_api.getfeedToken()
        self.refreshToken = self.data['data']['refreshToken']

    def get_MarketData(self):
        mode = "FULL"
        exchangeTokens = {"NSE": ["3045"]}
        marketData = self.smart_api.getMarketData(mode, exchangeTokens)
        self.assertTrue("status" in marketData)
        self.assertTrue("message" in marketData)
        self.assertTrue("errorcode" in marketData)
        self.assertTrue("data" in marketData)
        time.sleep(1)

    def get_CandleData(self):
        candleParams = {
            "exchange": "NSE",
            "symboltoken": "3045",
            "interval": "FIVE_MINUTE",
            "fromdate": "2023-10-18 09:15",
            "todate": "2023-10-18 09:20"
        }
        candledetails = self.smart_api.getCandleData(candleParams)
        self.assertTrue("status" in candledetails)
        self.assertTrue("message" in candledetails)
        self.assertTrue("errorcode" in candledetails)
        self.assertTrue("data" in candledetails)
        time.sleep(1)


if __name__ == '__main__':
    # Create a test suite and add tests to it
    suite = unittest.TestSuite()
    suite.addTest(LiveTestCases('get_MarketData'))
    suite.addTest(LiveTestCases('get_CandleData'))
    unittest.TextTestRunner(verbosity=2).run(suite)
