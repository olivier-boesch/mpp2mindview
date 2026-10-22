# -*- mode: python ; coding: utf-8 -*-
"""Construit deux exécutables autonomes (un seul fichier chacun) :

- mpp2mindview-gui.exe : interface graphique Kivy, sans console
- mpp2mindview.exe     : ligne de commande

Usage : pyinstaller --noconfirm --clean packaging/windows/mpp2mindview.spec
Fonctionne aussi sous Linux (binaires Linux), ce qui sert à valider la configuration.
"""
import os

from kivy.tools.packaging.pyinstaller_hooks import get_deps_minimal, hookspath, runtime_hooks

ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))
ICON = os.path.join(SPECPATH, "mpp2mindview.ico")
ICON = ICON if os.path.exists(ICON) else None

# DLL SDL2 / GLEW / ANGLE fournies par les paquets kivy_deps (Windows uniquement)
dep_trees = []
try:
    from kivy_deps import glew, sdl2

    dep_bins = sdl2.dep_bins + glew.dep_bins
    try:
        from kivy_deps import angle

        dep_bins += angle.dep_bins
    except ImportError:
        pass
    dep_trees = [Tree(p) for p in dep_bins]
except ImportError:
    pass

# ---- interface graphique ----------------------------------------------------
gui = Analysis(
    [os.path.join(SPECPATH, "launcher_gui.py")],
    pathex=[ROOT],
    hookspath=hookspath(),
    runtime_hooks=runtime_hooks(),
    **get_deps_minimal(video=None, audio=None, camera=None, spelling=None),
)
gui_pyz = PYZ(gui.pure)
gui_exe = EXE(
    gui_pyz,
    gui.scripts,
    gui.binaries,
    gui.datas,
    *dep_trees,
    name="mpp2mindview-gui",
    console=False,
    upx=False,
    icon=ICON,
)

# ---- ligne de commande ------------------------------------------------------
cli = Analysis(
    [os.path.join(SPECPATH, "launcher_cli.py")],
    pathex=[ROOT],
    excludes=["kivy", "kivy_deps", "tkinter"],
)
cli_pyz = PYZ(cli.pure)
cli_exe = EXE(
    cli_pyz,
    cli.scripts,
    cli.binaries,
    cli.datas,
    name="mpp2mindview",
    console=True,
    upx=False,
    icon=ICON,
)
