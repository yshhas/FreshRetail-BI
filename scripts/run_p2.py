"""运行 P2 分析：python scripts/run_p2.py"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from freshretail.analysis import p2  # noqa: E402


def main() -> None:
    summary = p2.run()
    print("\n=== P2 完成 ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str)[:4000])
    print("\n结果表：", ROOT / "data" / "analysis" / "p2")
    print("图表：", ROOT / "reports" / "figures" / "p2")


if __name__ == "__main__":
    main()
