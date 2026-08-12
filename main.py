# -*- coding: utf-8 -*-
"""Celebrity 启动入口：python main.py（等价于 python -m celebrity）"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from celebrity.cli import main


if __name__ == '__main__':
    sys.exit(main())
