"""The toy adapter's real job: prove the spec isn't SRD-shaped.

Same contract as the SRD adapter — citations on every path, honest exit 2,
enumerate<->validate consistency — on a game with boards instead of turns.
"""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from srdcheck.engine import Engine  # noqa: E402

BOTH = Engine([ROOT / "adapters" / "srd-5.2.1",
               ROOT / "adapters" / "toy-tictactoe"])


def move(board, player, cell):
    return BOTH.query("ttt.move", {"board": board, "player": player,
                                   "cell": cell})


def test_move_legality():
    assert move(".........", "X", 5).exit_code == 0
    assert move(".........", "O", 5).exit_code == 1      # not O's turn
    assert move("X........", "O", 1).exit_code == 1      # occupied
    assert move("X........", "O", 2).exit_code == 0
    assert move("XXX...OO.", "O", 9).exit_code == 1      # game already won
    assert move("XOXXOXOXO", "X", 1).exit_code == 1      # full board (draw)
    assert move(".........", "X", 12).exit_code == 1     # off the grid


def test_honest_edges():
    assert move("XX.......", "O", 3).exit_code == 2      # impossible board
    assert move("XO?......", "X", 3).exit_code == 2      # malformed board


def test_every_verdict_cites():
    for b, pl, c in ((".........", "X", 5), ("X........", "O", 1),
                     ("XXX...OO.", "O", 9), (".........", "O", 5)):
        vd = move(b, pl, c)
        assert vd.citations and all(x.quote for x in vd.citations), (b, pl, c)


def test_enumerate_validate_consistency():
    boards = [".........", "X........", "XO.......", "XOX.O.X..",
              "XXX...OO.", "XOXXOXOXO"]
    for board in boards:
        for player in "XO":
            opts = BOTH.query("ttt.options", {"board": board,
                                              "player": player})
            assert opts.exit_code == 0
            offered = {o["cell"] for o in opts.data["options"]}
            for cell in range(1, 10):
                ok = move(board, player, cell).exit_code == 0
                assert ok == (cell in offered), (board, player, cell)


def test_cross_adapter_jurisdiction():
    assert BOTH.jurisdiction("Fireball").exit_code == 0     # SRD adapter
    assert BOTH.jurisdiction("diagonal").exit_code == 0     # toy adapter
    assert BOTH.jurisdiction("Hexblade").exit_code == 2     # neither
    v = BOTH.jurisdiction("Hexblade")
    assert "srd-5.2.1" in v.why and "toy-tictactoe" in v.why


def test_adapters_dont_cross_answer():
    """The SRD adapter must not answer toy queries or vice versa."""
    srd_only = Engine([ROOT / "adapters" / "srd-5.2.1"])
    assert srd_only.query("ttt.move", {"board": ".........",
                                       "player": "X",
                                       "cell": 5}).exit_code == 2
    toy_only = Engine([ROOT / "adapters" / "toy-tictactoe"])
    assert toy_only.query("turn.plan",
                          {"speed": 30, "plan": []}).exit_code == 2
