# Tic-tac-toe — Rules

A deliberately small ruleset used to prove the srdcheck adapter spec is not
shaped around any one game. Released under CC0-1.0.

## §1 The grid

The game is played on a grid of nine cells, numbered 1 through 9, left to
right, top to bottom. A mark may only ever be placed in one of these nine
cells.

## §2 Turn order

X moves first. Turns alternate strictly between X and O. On a turn, the
moving player places exactly one mark of their own symbol.

## §3 Placement

A mark may be placed only in an empty cell. A cell containing any mark is
occupied and cannot be chosen.

## §4 Winning

A player wins upon having three of their marks in any straight line: a row
(1-2-3, 4-5-6, 7-8-9), a column (1-4-7, 2-5-8, 3-6-9), or a diagonal
(1-5-9, 3-5-7).

## §5 End of game

The game ends immediately when a player wins, or when all nine cells are
occupied without a winner (a draw). After the game has ended, no further
marks may be placed.
