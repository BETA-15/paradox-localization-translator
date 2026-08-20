"""PyInstaller hook for tkinterdnd2 native TkDnD binaries."""
from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files("tkinterdnd2")
