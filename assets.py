"""Resolve a game's files (zip, screenshot, music, cover) on disk."""
from data_layout import DataLayout
from models import ExtraFile, Game
from repository import GameRepository


def exists(p):
    return bool(p) and p.is_file()


class GameAssets:
    def __init__(self, layout: DataLayout, repo: GameRepository):
        self.layout = layout
        self.repo = repo

    def game_file(self, game: Game):
        return self.layout.game_file(game.filename)

    def screenshot(self, game: Game):
        return self.layout.screenshot(game.screenshot_filename)

    def music(self, game: Game):
        return self.layout.music(game.sid_filename)

    def cover(self, game: Game):
        """Generated cover first, then the front boxscan extra; None if neither exists."""
        for p in (self.layout.cover(game.id),
                  self.layout.extra(self.repo.front_boxscan_path(game.id))):
            if exists(p):
                return p
        return None

    def extras(self, game: Game):
        return [ExtraFile(e, self.layout.extra(e.path)) for e in self.repo.extras(game.id)]
