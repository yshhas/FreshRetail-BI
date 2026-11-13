"""运行 P4 经营诊断与决策支持：python scripts/run_p4.py"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from freshretail.analysis import p4_diagnosis  # noqa: E402


def main() -> None:
    summary = p4_diagnosis.run()
    print("\n=== P4 完成 ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    print("\n结果表：", ROOT / "data" / "analysis" / "p4")
    print("图表：", ROOT / "reports" / "figures" / "p4")


if __name__ == "__main__":
    main()
