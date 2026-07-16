"""Query handlers for the toy tic-tac-toe adapter.

Exists to prove the adapter spec on a game with nothing in common with the
SRD. Same contract: facts from atoms, citations on every verdict path,
honest exit 2 at the edges.
"""

from srdcheck import verdict as v


def _cite(atom):
    c = atom["citation"]
    return v.Citation(c["section"], c.get("page"), c.get("quote"))


def _winner(board, lines):
    for line in lines:
        a, b, c = (board[i - 1] for i in line)
        if a != "." and a == b == c:
            return a
    return None


def _gate_board(adapter, board):
    if len(board) != 9 or any(ch not in "XO." for ch in board):
        return v.cannot_adjudicate(
            "Malformed board: expected 9 characters of X, O, and '.' — "
            "cannot adjudicate.", adapter=adapter.id)
    if board.count("X") - board.count("O") not in (0, 1):
        return v.cannot_adjudicate(
            "Impossible board: mark counts violate alternating turn order, "
            "so no legal game reaches this position.",
            [_cite(adapter.atoms["ttt.turn-order"])], adapter.id,
            ["ttt.turn-order"])
    return None


def _to_move(board):
    return "X" if board.count("X") == board.count("O") else "O"


def ttt_move(adapter, p):
    a, aid = adapter.atoms, adapter.id
    board, player, cell = p["board"], p["player"], int(p["cell"])
    bad = _gate_board(adapter, board)
    if bad:
        return bad
    grid = a["ttt.grid"]
    if not 1 <= cell <= grid["params"]["cells"]:
        return v.illegal(f"Cell {cell} is not on the grid.",
                         [_cite(grid)], aid, [grid["id"]])
    end = a["ttt.no-moves-after-end"]
    lines = a["ttt.win-lines"]["params"]["lines"]
    if _winner(board, lines) or "." not in board:
        return v.illegal("The game has already ended. " +
                         end["citation"]["quote"], [_cite(end)], aid,
                         [end["id"], "ttt.win-lines"])
    turn = a["ttt.turn-order"]
    if player != _to_move(board):
        return v.illegal(f"It is not {player}'s turn. " +
                         turn["citation"]["quote"], [_cite(turn)], aid,
                         [turn["id"]])
    if board[cell - 1] != ".":
        occ = a["ttt.empty-cell-only"]
        return v.illegal(f"Cell {cell} is occupied. " +
                         occ["citation"]["quote"], [_cite(occ)], aid,
                         [occ["id"]])
    return v.legal(f"{player} may mark cell {cell}.",
                   [_cite(turn), _cite(a["ttt.empty-cell-only"])], aid,
                   [turn["id"], "ttt.empty-cell-only"])


def ttt_options(adapter, p):
    a, aid = adapter.atoms, adapter.id
    board, player = p["board"], p["player"]
    bad = _gate_board(adapter, board)
    if bad:
        return bad
    lines = a["ttt.win-lines"]["params"]["lines"]
    if _winner(board, lines) or "." not in board:
        end = a["ttt.no-moves-after-end"]
        return v.legal("The game has ended; no moves remain.",
                       [_cite(end)], aid, [end["id"]],
                       data={"options": []})
    if player != _to_move(board):
        turn = a["ttt.turn-order"]
        return v.legal(f"It is not {player}'s turn; no moves available.",
                       [_cite(turn)], aid, [turn["id"]],
                       data={"options": []})
    cells = [i + 1 for i, ch in enumerate(board) if ch == "."]
    turn = a["ttt.turn-order"]
    return v.legal(f"{player} has {len(cells)} legal move(s).",
                   [_cite(turn)], aid, [turn["id"]],
                   data={"options": [{"cell": c} for c in cells]})


HANDLERS = {"ttt.move": ttt_move, "ttt.options": ttt_options}
