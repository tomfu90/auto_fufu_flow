# locustfile.py
# coding =utf-8
# author = fufu
import os,sys
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir))
sys.path.insert(0,project_root)

#from load_test.scenarios.single_user_login import  HighRPSUser
#from load_test.scenarios.listing_single import  BurstUser
#from load_test.scenarios.buy import  TradingUser
#from load_test.scenarios.mixed_load import TradingUser
#from load_test.scenarios.multi_mixed_load import TradingUser
from  load_test.scenarios.listing import ListingUser