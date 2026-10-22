"""Interface graphique (Kivy) : mpp2mindview-gui"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

os.environ.setdefault("KIVY_NO_ARGS", "1")
os.environ.setdefault("KIVY_NO_CONSOLELOG", "1")

from kivy.config import Config  # noqa: E402

Config.set("graphics", "width", "860")
Config.set("graphics", "height", "620")
Config.set("graphics", "minimum_width", "640")
Config.set("graphics", "minimum_height", "520")
Config.set("input", "mouse", "mouse,multitouch_on_demand")  # pas de point rouge au clic droit

from kivy.app import App  # noqa: E402
from kivy.clock import mainthread  # noqa: E402
from kivy.core.window import Window  # noqa: E402
from kivy.lang import Builder  # noqa: E402
from kivy.metrics import dp  # noqa: E402
from kivy.properties import BooleanProperty, ListProperty, NumericProperty, StringProperty  # noqa: E402
from kivy.uix.boxlayout import BoxLayout  # noqa: E402
from kivy.uix.popup import Popup  # noqa: E402

# Widgets utilisés seulement dans le KV : importés ici pour que PyInstaller les embarque.
from kivy.uix import (button, checkbox, filechooser, gridlayout, label,  # noqa: E402,F401
                      progressbar, scrollview)

from . import __version__  # noqa: E402
from .converter import convert, find_mpp, target_for  # noqa: E402
from .reader import MppError  # noqa: E402

KV = """
#:import dp kivy.metrics.dp

<FlatButton@Button>:
    background_normal: ""
    background_down: ""
    background_color: (0.20, 0.42, 0.75, 1) if self.state == "normal" else (0.15, 0.32, 0.60, 1)
    disabled_color: 1, 1, 1, .6
    color: 1, 1, 1, 1
    size_hint_y: None
    height: dp(38)
    font_size: "15sp"

<GhostButton@Button>:
    background_normal: ""
    background_down: ""
    background_color: (0.90, 0.92, 0.95, 1) if self.state == "normal" else (0.80, 0.84, 0.90, 1)
    color: 0.15, 0.20, 0.30, 1
    disabled_color: 0.15, 0.20, 0.30, .4
    size_hint_y: None
    height: dp(38)
    font_size: "15sp"

<DarkLabel@Label>:
    color: 0.15, 0.18, 0.25, 1
    text_size: self.width, None
    size_hint_y: None
    height: self.texture_size[1]
    halign: "left"

<FileRow>:
    size_hint_y: None
    height: dp(34)
    padding: dp(10), 0
    spacing: dp(8)
    canvas.before:
        Color:
            rgba: (0.96, 0.97, 0.99, 1) if self.index % 2 else (1, 1, 1, 1)
        Rectangle:
            pos: self.pos
            size: self.size
    Label:
        text: root.name
        color: 0.15, 0.18, 0.25, 1
        text_size: self.size
        halign: "left"
        valign: "middle"
        shorten: True
        shorten_from: "left"
    Label:
        text: root.status
        color: root.status_color
        size_hint_x: None
        width: dp(380)
        text_size: self.size
        halign: "right"
        valign: "middle"
        shorten: True
    Button:
        text: "×"
        size_hint_x: None
        width: dp(28)
        background_normal: ""
        background_color: 0, 0, 0, 0
        color: 0.55, 0.58, 0.65, 1
        font_size: "18sp"
        disabled: app.busy
        on_release: app.remove_file(root.path)

<FileChooserPopup>:
    size_hint: .9, .9
    BoxLayout:
        orientation: "vertical"
        spacing: dp(8)
        FileChooserListView:
            id: chooser
            path: root.start_path
            filters: root.filters
            multiselect: root.multiselect
            dirselect: root.dirselect
        BoxLayout:
            size_hint_y: None
            height: dp(40)
            spacing: dp(8)
            Button:
                text: "Annuler"
                on_release: root.cancel()
            Button:
                text: root.ok_text
                on_release: root.validate(chooser.selection, chooser.path)

<Root>:
    orientation: "vertical"
    padding: dp(18)
    spacing: dp(12)
    canvas.before:
        Color:
            rgba: 0.97, 0.98, 1, 1
        Rectangle:
            pos: self.pos
            size: self.size

    BoxLayout:
        size_hint_y: None
        height: dp(56)
        orientation: "vertical"
        DarkLabel:
            text: "[b]MPP vers MindView[/b]"
            markup: True
            font_size: "22sp"
        DarkLabel:
            text: "Convertit vos fichiers MS Project 2010 (.mpp) en XML, à ouvrir avec l'import MS Project de MindView."
            color: 0.40, 0.44, 0.52, 1
            font_size: "14sp"

    BoxLayout:
        size_hint_y: None
        height: dp(38)
        spacing: dp(8)
        FlatButton:
            text: "Ajouter des fichiers…"
            disabled: app.busy
            on_release: app.open_files()
        FlatButton:
            text: "Ajouter un dossier…"
            disabled: app.busy
            on_release: app.open_folder()
        GhostButton:
            text: "Vider la liste"
            size_hint_x: None
            width: dp(140)
            disabled: app.busy or not app.files
            on_release: app.clear_files()

    BoxLayout:
        orientation: "vertical"
        canvas.before:
            Color:
                rgba: 0.82, 0.85, 0.90, 1
            Line:
                rectangle: self.x, self.y, self.width, self.height
                dash_length: 6 if not app.files else 1
                dash_offset: 4 if not app.files else 0
        ScrollView:
            do_scroll_x: False
            GridLayout:
                id: rows
                cols: 1
                size_hint_y: None
                height: self.minimum_height
        Label:
            text: "Glissez-déposez des fichiers .mpp ou des dossiers ici"
            color: 0.55, 0.58, 0.65, 1
            size_hint_y: None
            height: 0 if app.files else dp(60)
            opacity: 0 if app.files else 1

    BoxLayout:
        size_hint_y: None
        height: dp(30)
        spacing: dp(6)
        CheckBox:
            id: beside
            group: "sortie"
            active: app.output_dir == ""
            size_hint_x: None
            width: dp(30)
            color: 0.20, 0.42, 0.75, 1
            disabled: app.busy
            on_active: if self.active: app.output_dir = ""
        DarkLabel:
            text: "Enregistrer le .xml à côté de chaque fichier .mpp"
            size_hint_y: None
            height: dp(30)
            valign: "middle"
            text_size: self.size

    BoxLayout:
        size_hint_y: None
        height: dp(30)
        spacing: dp(6)
        CheckBox:
            group: "sortie"
            active: app.output_dir != ""
            size_hint_x: None
            width: dp(30)
            color: 0.20, 0.42, 0.75, 1
            disabled: app.busy
            on_active: if self.active and not app.output_dir: app.choose_output()
        DarkLabel:
            text: "Dans le dossier :"
            size_hint: None, None
            width: dp(130)
            height: dp(30)
            valign: "middle"
            text_size: self.size
        DarkLabel:
            text: app.output_dir or "(aucun dossier choisi)"
            color: 0.40, 0.44, 0.52, 1
            size_hint_y: None
            height: dp(30)
            valign: "middle"
            text_size: self.size
            shorten: True
            shorten_from: "left"
        GhostButton:
            text: "Choisir…"
            size_hint: None, None
            width: dp(100)
            height: dp(30)
            disabled: app.busy
            on_release: app.choose_output()

    BoxLayout:
        size_hint_y: None
        height: dp(30)
        spacing: dp(6)
        CheckBox:
            active: app.overwrite
            size_hint_x: None
            width: dp(30)
            color: 0.20, 0.42, 0.75, 1
            disabled: app.busy
            on_active: app.overwrite = self.active
        DarkLabel:
            text: "Écraser les fichiers .xml existants"
            size_hint_y: None
            height: dp(30)
            valign: "middle"
            text_size: self.size

    ProgressBar:
        size_hint_y: None
        height: dp(10)
        max: max(1, len(app.files))
        value: app.progress

    BoxLayout:
        size_hint_y: None
        height: dp(42)
        spacing: dp(8)
        DarkLabel:
            text: app.message
            size_hint_y: None
            height: dp(42)
            valign: "middle"
            text_size: self.size
            shorten: True
            color: 0.30, 0.34, 0.42, 1
        GhostButton:
            text: "Ouvrir le dossier"
            size_hint: None, None
            width: dp(150)
            height: dp(42)
            disabled: app.busy or not app.last_folder
            on_release: app.open_last_folder()
        FlatButton:
            text: "Conversion…" if app.busy else "Convertir"
            size_hint: None, None
            width: dp(160)
            height: dp(42)
            bold: True
            disabled: app.busy or not app.files
            on_release: app.start()
"""

OK = (0.13, 0.55, 0.30, 1)
ERROR = (0.80, 0.20, 0.20, 1)
NEUTRAL = (0.45, 0.48, 0.55, 1)


class FileRow(BoxLayout):
    path = StringProperty("")
    name = StringProperty("")
    status = StringProperty("")
    status_color = ListProperty(NEUTRAL)
    index = NumericProperty(0)


class FileChooserPopup(Popup):
    start_path = StringProperty(str(Path.home()))
    filters = ListProperty([])
    multiselect = BooleanProperty(False)
    dirselect = BooleanProperty(False)
    ok_text = StringProperty("Ouvrir")

    def __init__(self, on_choice, **kwargs):
        super().__init__(**kwargs)
        self._on_choice = on_choice

    def cancel(self):
        self.dismiss()
        self._on_choice([])

    def validate(self, selection, current):
        self.dismiss()
        self._on_choice(list(selection) or ([current] if self.dirselect else []))


class Root(BoxLayout):
    pass


class Mpp2MindViewApp(App):
    title = f"MPP vers MindView {__version__}"
    files = ListProperty([])
    output_dir = StringProperty("")
    overwrite = BooleanProperty(False)
    busy = BooleanProperty(False)
    progress = NumericProperty(0)
    message = StringProperty("Ajoutez des fichiers .mpp pour commencer.")
    last_folder = StringProperty("")

    def build(self):
        Builder.load_string(KV)
        Window.clearcolor = (0.97, 0.98, 1, 1)
        Window.bind(on_drop_file=self._on_drop)
        self._rows: dict[str, FileRow] = {}
        self._last_dir = str(Path.home())
        return Root()

    # -- liste de fichiers -------------------------------------------------
    def add_paths(self, paths) -> None:
        added = 0
        for raw in paths:
            path = Path(raw)
            candidates = find_mpp(path, recursive=True) if path.is_dir() else [path]
            for p in candidates:
                key = str(p.resolve())
                if p.suffix.lower() != ".mpp" or key in self._rows:
                    continue
                row = FileRow(path=key, name=p.name, status="en attente", index=len(self.files))
                self._rows[key] = row
                self.root.ids.rows.add_widget(row)
                self.files.append(key)
                added += 1
        if added:
            self.progress = 0
            self.message = f"{len(self.files)} fichier(s) à convertir."
        elif paths:
            self.message = "Aucun nouveau fichier .mpp trouvé."

    def remove_file(self, key: str) -> None:
        row = self._rows.pop(key, None)
        if row is not None:
            self.root.ids.rows.remove_widget(row)
            self.files.remove(key)
            for i, r in enumerate(self.root.ids.rows.children[::-1]):
                r.index = i
            self.message = f"{len(self.files)} fichier(s) à convertir." if self.files else \
                "Ajoutez des fichiers .mpp pour commencer."

    def clear_files(self) -> None:
        self.root.ids.rows.clear_widgets()
        self._rows.clear()
        self.files = []
        self.progress = 0
        self.message = "Ajoutez des fichiers .mpp pour commencer."

    def _on_drop(self, _window, filename, *_args):
        if self.busy:
            return
        name = filename.decode("utf-8") if isinstance(filename, bytes) else filename
        self.add_paths([name])

    # -- sélecteurs --------------------------------------------------------
    def _chooser(self, title, on_choice, **kwargs):
        FileChooserPopup(on_choice, title=title, start_path=self._last_dir, **kwargs).open()

    def _remember(self, paths):
        if paths:
            first = Path(paths[0])
            self._last_dir = str(first if first.is_dir() else first.parent)

    def open_files(self):
        def done(paths):
            self._remember(paths)
            self.add_paths(paths)
        self._chooser("Choisir des fichiers .mpp", done, filters=["*.mpp", "*.MPP"],
                      multiselect=True, ok_text="Ajouter")

    def open_folder(self):
        def done(paths):
            self._remember(paths)
            self.add_paths(paths[:1])
        self._chooser("Choisir un dossier (sous-dossiers inclus)", done, dirselect=True,
                      filters=["*.mpp", "*.MPP"], ok_text="Ajouter ce dossier")

    def choose_output(self):
        def done(paths):
            if paths and Path(paths[0]).is_dir():
                self.output_dir = str(Path(paths[0]))
            if not self.output_dir:  # choix annulé : on revient à « à côté des fichiers »
                self.root.ids.beside.active = True
        self._chooser("Choisir le dossier de sortie", done, dirselect=True,
                      filters=["__aucun__"], ok_text="Choisir ce dossier")

    # -- conversion --------------------------------------------------------
    def start(self):
        if self.busy or not self.files:
            return
        self.busy = True
        self.progress = 0
        self.message = "Conversion en cours…"
        jobs = list(self.files)
        out_dir = Path(self.output_dir) if self.output_dir else None
        threading.Thread(target=self._run, args=(jobs, out_dir, self.overwrite), daemon=True).start()

    def _run(self, jobs, out_dir, overwrite):
        converted = skipped = failed = 0
        last = ""
        for i, key in enumerate(jobs, 1):
            src = Path(key)
            dst = target_for(src, out_dir)
            self._set_status(key, "conversion…", NEUTRAL)
            if dst.exists() and not overwrite:
                skipped += 1
                self._set_status(key, f"ignoré : {dst.name} existe déjà", NEUTRAL)
            else:
                try:
                    result = convert(src, dst)
                    converted += 1
                    last = str(dst.parent)
                    self._set_status(key, result.summary(), OK)
                except MppError as exc:
                    failed += 1
                    self._set_status(key, f"erreur : {exc}", ERROR)
                except Exception as exc:  # noqa: BLE001 - on continue avec les autres fichiers
                    failed += 1
                    self._set_status(key, f"erreur : lecture impossible ({type(exc).__name__})", ERROR)
            self._set_progress(i)
        self._finish(converted, skipped, failed, last)

    @mainthread
    def _set_status(self, key, text, color):
        row = self._rows.get(key)
        if row is not None:
            row.status = text
            row.status_color = color

    @mainthread
    def _set_progress(self, value):
        self.progress = value

    @mainthread
    def _finish(self, converted, skipped, failed, last):
        self.busy = False
        if last:
            self.last_folder = last
        parts = [f"{converted} converti(s)"]
        if skipped:
            parts.append(f"{skipped} ignoré(s)")
        if failed:
            parts.append(f"{failed} en erreur")
        self.message = "Terminé : " + ", ".join(parts) + "."

    def open_last_folder(self):
        folder = self.last_folder
        if not folder:
            return
        if sys.platform.startswith("win"):
            os.startfile(folder)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", folder])
        else:
            subprocess.Popen(["xdg-open", folder])


def main() -> None:
    Mpp2MindViewApp().run()


if __name__ == "__main__":
    main()
