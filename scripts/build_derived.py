"""构建派生数据：python scripts/build_derived.py [--skip-hash]"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from freshretail.pipeline import run  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-hash", action="store_true", help="跳过 SHA256 校验（仅调试用）")
    args = parser.parse_args()
    report = run(skip_hash=args.skip_hash)
    print("\n=== 完成 ===")
    print("派生表：", report["derived_tables"])
    print("耗时：", report["run"]["elapsed_seconds"], "秒")
    print("质量报告：", ROOT / "data" / "derived" / "_quality_report.json")


if __name__ == "__main__":
    main()
