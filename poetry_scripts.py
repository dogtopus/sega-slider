#!/usr/bin/env python3

# TODO can we get rid of this file completely and only use pure python scripts?
import subprocess
import os

def start():
    subprocess.run(('python', os.path.join('src', 'start.py')))

def build():
    subprocess.run(('pyinstaller', 'sega-slider.spec'))

def build_onefile():
    subprocess.run(('pyinstaller', 'sega-slider.spec'))
