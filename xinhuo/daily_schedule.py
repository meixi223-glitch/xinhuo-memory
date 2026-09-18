#!/usr/bin/env python3
"""Queue yesterday's impression at 05:00 Shanghai; never calls a language model."""
import os
from memory_v2 import MemoryStore
s=MemoryStore(os.environ.get('MEMORY_DB','./data/memory.sqlite3'),os.environ.get('MEMORY_ARCHIVE_DIR','./data/archive'))
s.daily.schedule()
print('daily_impression_schedule_checked primary_model_calls=0',flush=True)
