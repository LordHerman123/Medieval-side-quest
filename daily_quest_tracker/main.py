"""Daily Quest Tracker - entry point.

Run on desktop with ``python main.py``. Buildozer/python-for-android also
starts the app from this file.
"""

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


from kivy.config import Config  # noqa: E402
from kivy.utils import platform  # noqa: E402

if platform not in ("android", "ios"):
    # A phone-shaped window for desktop development; resize freely to test wider layouts.
    Config.set("graphics", "width", os.environ.get("DQT_WIDTH", "420"))
    Config.set("graphics", "height", os.environ.get("DQT_HEIGHT", "820"))
    Config.set("input", "mouse", "mouse,multitouch_on_demand")
Config.set("kivy", "exit_on_escape", "0")


def main() -> None:
    from ui.app import DailyQuestApp

    DailyQuestApp(db_path=os.environ.get("DQT_DB_PATH")).run()


if __name__ == "__main__":
    main()
