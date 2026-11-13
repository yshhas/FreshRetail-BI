"""运行 P3-A 城市分析：python scripts/run_p3a.py"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from freshretail.analysis import p3_city  # noqa: E402


def main() -> None:
    summary = p3_city.run()
    print("\n=== P3-A 完成 ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str)[:4000])
    print("\n结果表：", ROOT / "data" / "analysis" / "p3")
    print("图表：", ROOT / "reports" / "figures" / "p3")


if __name__ == "__main__":
    main()
