import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rox import Rox
from server_manager import free_ram_gb
from board.queue import Queue

print("=== 1. wiring (no model) ===")
r = Rox(session_name="_boardtest", auto_start=False)
print("board:", r._board is not None,
      "| retriever:", r._board_retriever is not None,
      "| archivist:", r._archivist is not None)
r.board_enqueue("I am building an industrial robot arm with NEMA 23 motors",
                "Nice project.", thinking="the user is starting a hardware "
                "project and chose NEMA 23 steppers")
from tools.handlers_board import board_archive, board_stats, board_search
print("archive tool:", board_archive({}, r.tctx)["output"])
print("stats tool:", board_stats({}, r.tctx)["output"])

print("=== 2. run archivist live (roxn-3b) ===")
r.sm.stop()
for _ in range(60):
    if free_ram_gb() >= 5.0:
        break
    time.sleep(2)
print("free RAM:", round(free_ram_gb(), 1))
r._archivist.park = False
rep = r._archivist.run()
print("archive report:", rep)

print("=== 3. retrieve from the board ===")
card = r._board_card("what motors does the robot arm use?")
print("board card:")
print(card)
print("stats:", r._board.stats())
print("board_search tool:", board_search({"query": "robot arm"}, r.tctx)["output"][:300])

print("=== 4. forget cascade ===")
r._board_forget("robot arm")
print("after forget:", r._board.stats())

print("=== 5. reload 35B ===")
r.sm.ensure()
r.close()
print("done")
