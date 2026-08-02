"""Entry point de PyInstaller para tae-gui.exe (ver packaging/tae-gui.spec).

Wrapper delgado: `tae.gui.app.main()` ya hace freeze_support()/set_start_method
(P12) y la inyeccion de PATH para binarios bundleados (ver app.py:main). Este
archivo solo le da a PyInstaller un modulo __main__ real con el guard estandar.
"""

from tae.gui.app import main

if __name__ == "__main__":
    main()
