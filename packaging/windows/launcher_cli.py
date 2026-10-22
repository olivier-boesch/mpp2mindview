"""Point d'entrée de mpp2mindview.exe (PyInstaller)."""
import sys

from mpp2mindview.cli import main

if __name__ == "__main__":
    sys.exit(main())
