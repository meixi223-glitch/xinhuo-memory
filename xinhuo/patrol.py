#!/usr/bin/env python3
import json
import os
from memory_core import MemoryStore

store = MemoryStore(os.environ.get("MEMORY_DB", "./data/memory.sqlite3"), os.environ.get("MEMORY_ARCHIVE_DIR", "./data/archive"))
print(json.dumps(store.patrol(os.environ.get("MEMORY_NAMESPACE", "default")), ensure_ascii=False))

