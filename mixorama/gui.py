import os
from os import path
from threading import Thread
from typing import Dict
import logging
logger = logging.getLogger(__name__)

from mixorama.bartender import Bartender, BartenderState, CocktailAbortedException
from mixorama.recipes import Recipe
from mixorama.statemachine import InvalidStateMachineTransition

# cmdline arguments, logger and config setup are handled by mixorama
os.environ["KIVY_NO_ARGS"] = "1"
os.environ["KIVY_NO_CONSOLELOG"] = "1"
os.environ["KIVY_NO_CONFIG"] = "1"

from kivy.lang import Builder
from kivy.properties import ObjectProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.progressbar import ProgressBar
from kivy.config import Config
from kivy.app import App
from kivy.uix.button import Button

# sudo apt-get install -y \
#     python3-pip \
#     build-essential \
#     git \
#     python3 \
#     python3-dev \
#     ffmpeg \
#     libsdl2-dev \
#     libsdl2-image-dev \
#     libsdl2-mixer-dev \
#     libsdl2-ttf-dev \
#     libportmidi-dev \
#     libswscale-dev \
#     libavformat-dev \
#     libavcodec-dev \
#     zlib1g-dev


def is_gui_available():
    try:
        from kivy.core.window import Window
        return Window is not None
    except Exception:
        return False


def config(config: Dict[str, Dict[str, str]]):
    for section, section_settings in config.items():
        for option, value in section_settings.items():
            Config.set(section, option, value)


def gui(menu, bartender):
    BartenderGuiApp(menu, bartender).run()


class BartenderGuiApp(App):
    def __init__(self, menu: Dict[str, Recipe], bartender: Bartender, **kwargs):
        super(BartenderGuiApp, self).__init__(**kwargs)
        self.menu = menu
        self.bartender = bartender

    def build(self):
        tpl_path = path.join(path.dirname(__file__), 'gui/layout.kv')
        Builder.load_file(tpl_path)
        return MainWidget(self.menu, self.bartender)


class TouchableButton(Button):
    def collide_point(self, x, y):
        parent = super(TouchableButton, self).collide_point(x, y)
        print('colliding touchable button @ ', x, y)
        return parent


class MainWidget(BoxLayout):
    menu_buttons: GridLayout = ObjectProperty(None)
    image: Image = ObjectProperty(None)
    total_progress: ProgressBar = ObjectProperty(None)
    step_progress: ProgressBar = ObjectProperty(None)
    abort_btn: Button = ObjectProperty(None)
    make_btn: Button = ObjectProperty(None)
    info_ul: Label = ObjectProperty(None)
    info_ur: Label = ObjectProperty(None)
    info_bl: Label = ObjectProperty(None)
    info_br: Label = ObjectProperty(None)

    staged_recipe: Recipe = None

    def __init__(self, menu: Dict[str, Recipe], bartender: Bartender, **kwargs):
        super(MainWidget, self).__init__(**kwargs)
        self.bartender = bartender
        self.menu = menu

        bartender.on_sm_transitions(
            enum=BartenderState,
            IDLE=self.on_idle,
            MAKING=self.on_making,
            READY=self.on_ready,
            POURING=self.on_pouring,
            POURING_PROGRESS=self.on_pouring_progress,
        )

        self.build_cocktail_buttons(menu)
        self.abort_btn.bind(on_press=self.on_abort_btn_press)
        self.make_btn.bind(on_press=self.on_make_btn_press)

        self.on_idle()

    def build_cocktail_buttons(self, menu):
        for key, recipe in menu.items():
            horiz_size = 1 / 3  # arrange in 3 columns
            vert_size = horiz_size / len(menu)  # percent of parent

            b = Button(text=recipe.name, size_hint=(horiz_size, vert_size),
                       on_press=lambda *args, r=recipe: self.stage_recipe(r))

            self.menu_buttons.add_widget(b)

    def stage_recipe(self, recipe: Recipe):
        self.staged_recipe = recipe
        self.info_ul.text = 'Volume: {} ml'.format(recipe.volume())
        self.info_bl.text = 'Strength: {:.2f}%, ABV'.format(recipe.strength())

        if recipe.image:
            self.image.source = recipe.image

    def reset_progress(self, total=0, step=0):
        self.total_progress.value = total
        self.step_progress.value = step

    def on_abort_btn_press(self, target):
        try:
            self.bartender.abort()
        except InvalidStateMachineTransition as e:
            logger.exception(e)

    def on_make_btn_press(self, target):
        if self.staged_recipe:

            def maker():
                try:
                    self.bartender.make_drink(self.staged_recipe.sequence)
                    self.bartender.serve()
                except CocktailAbortedException:
                    self.on_abort()
                    self.bartender.discard()

            Thread(daemon=True, target=maker).start()

    def on_idle(self):
        self.make_btn.disabled = False
        self.abort_btn.disabled = True
        self.info_br.text = 'Ready to make drinks!'
        self.reset_progress()

    def on_making(self):
        self.make_btn.disabled = True
        self.abort_btn.disabled = False
        self.info_br.text = 'Making your drink ...'

    def on_ready(self):
        self.info_br.text = 'Take your drink'

    def on_abort(self):
        self.info_br.text = 'Cocktail aborted. Please dump the glass contents'

    def on_pouring(self, component):
        progress = list(dict(self.staged_recipe.sequence).keys()).index(component) + 1 / len(self.menu)
        self.total_progress.value = progress * 100

    def on_pouring_progress(self, done, volume):
        self.step_progress.value = done / volume * 100