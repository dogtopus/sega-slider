# -*- mode: python ; coding: utf-8 -*-
import platform
import itertools

if platform.system() == 'Windows':
    from kivy_deps import sdl2, glew, angle
    platform_deps = tuple(Tree(p) for p in itertools.chain(sdl2.dep_bins, glew.dep_bins, angle.dep_bins))
else:
    platform_deps = tuple()

block_cipher = None


a = Analysis(['src/start.py'],
             binaries=[],
             datas=[
                 ('src/segaslider/*.kv', 'segaslider/'),
                 ('src/segaslider/*.settings.json', 'segaslider/'),
             ],
             hiddenimports=[],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          [],
          exclude_binaries=True,
          name='sega-slider',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=True )
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               *platform_deps,
               strip=False,
               upx=True,
               upx_exclude=[],
               name='sega-slider')
