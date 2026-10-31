"""Print the top functions of a .prof by cumulative time: python docs/qa/speed/top.py f [n]."""

import pstats
import sys

pstats.Stats(sys.argv[1]).sort_stats("cumulative").print_stats(int(sys.argv[2]) if len(sys.argv) > 2 else 40)
