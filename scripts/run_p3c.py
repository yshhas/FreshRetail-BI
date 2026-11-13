"""运行 P3-C 商品结构分析：python scripts/run_p3c.py"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from freshretail.analysis import p3c_structure  # noqa: E402


def main() -> None:
    summary = p3c_structure.run()
    print("\n=== P3-C 完成 ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str)[:5000])
    print("\n结果表：", ROOT / "data" / "analysis" / "p3c")
    print("图表：", ROOT / "reports" / "figures" / "p3c")


if __name__ == "__main__":
    main()
