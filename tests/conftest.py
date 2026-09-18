"""Put the xinhuo package modules on sys.path for the flat-import test suite."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "xinhuo"))
