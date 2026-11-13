"""运行 P1 分析：python scripts/run_p1.py"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from freshretail.analysis import p1  # noqa: E402


def main() -> None:
    summary = p1.run()
    print("\n=== P1 完成 ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str)[:3000])
    print("\n结果表：", ROOT / "data" / "analysis" / "p1")
    print("图表：", ROOT / "reports" / "figures" / "p1")


if __name__ == "__main__":
    main()
