"""允许使用 python -m concrete_inspector 运行"""
import sys
from .cli import main

if __name__ == "__main__":
    sys.exit(main())
