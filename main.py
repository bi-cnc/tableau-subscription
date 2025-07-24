##### main.py

print("🚀 Starting Tableau Subscriptions component...")


import os
import pandas as pd
import sys
import tableauserverclient as TSC
import traceback
from driver import Driver
from exceptions import UserException, ApplicationException


exit_codes = [1, 2, 3]
try:
    driver = Driver('/data', '/code/')
    driver.run()
    print("skip")
except UserException as err:
    message = '%s' % err
    print(message, file=sys.stderr)
    sys.exit(exit_codes[0])
except ApplicationException as err:
    message = '%s' % err
    print(message, file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    sys.exit(exit_codes[0])
except Exception as err:
    message = '%s' % err
    print(message, file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    sys.exit(exit_codes[0])