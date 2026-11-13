"""运行 P3-D 缺货与门店风险分析：python scripts/run_p3d.py"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from freshretail.analysis import p3d_risk  # noqa: E402


def main() -> None:
    summary = p3d_risk.run()
    print("\n=== P3-D 完成 ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str)[:6000])
    print("\n结果表：", ROOT / "data" / "analysis" / "p3d")
    print("图表：", ROOT / "reports" / "figures" / "p3d")


if __name__ == "__main__":
    main()
