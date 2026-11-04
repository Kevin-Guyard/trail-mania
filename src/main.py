import flet as ft

from trail_mania.app import create_app


if __name__ == "__main__":
    ft.run(create_app, assets_dir="assets")