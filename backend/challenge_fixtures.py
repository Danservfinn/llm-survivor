from __future__ import annotations

from typing import Any


CHALLENGE_PUZZLES: list[dict[str, Any]] = [
    {
        "puzzle_id": "arc-line-crossings-6x6",
        "prompt": (
            "ARC-style grid puzzle. In each example, matching non-zero colors define straight horizontal "
            "or vertical line segments through the empty cells between them. If two completed segments cross, "
            "the crossing cell becomes 9. Return the output grid for test input "
            "[[6,0,0,0,0,6],[0,0,0,7,0,0],[0,8,0,0,0,8],[0,0,0,0,0,0],[0,0,0,0,0,0],[0,0,0,7,0,0]]."
        ),
        "examples": [
            {
                "input": [
                    [2, 0, 0, 2, 0],
                    [0, 0, 0, 0, 0],
                    [3, 0, 0, 0, 0],
                    [0, 0, 0, 0, 0],
                    [3, 0, 0, 0, 0],
                ],
                "output": [
                    [2, 2, 2, 2, 0],
                    [0, 0, 0, 0, 0],
                    [3, 0, 0, 0, 0],
                    [3, 0, 0, 0, 0],
                    [3, 0, 0, 0, 0],
                ],
            },
            {
                "input": [
                    [0, 0, 5, 0, 0],
                    [4, 0, 0, 0, 4],
                    [0, 0, 0, 0, 0],
                    [0, 0, 0, 0, 0],
                    [0, 0, 5, 0, 0],
                ],
                "output": [
                    [0, 0, 5, 0, 0],
                    [4, 4, 9, 4, 4],
                    [0, 0, 5, 0, 0],
                    [0, 0, 5, 0, 0],
                    [0, 0, 5, 0, 0],
                ],
            },
        ],
        "answer": [
            [6, 6, 6, 6, 6, 6],
            [0, 0, 0, 7, 0, 0],
            [0, 8, 8, 9, 8, 8],
            [0, 0, 0, 7, 0, 0],
            [0, 0, 0, 7, 0, 0],
            [0, 0, 0, 7, 0, 0],
        ],
        "difficulty": "hard",
        "eligibility": "both",
    },
    {
        "puzzle_id": "arc-fill-center",
        "prompt": (
            "ARC-style grid puzzle. In each example, the center 0 becomes the color used by the border. "
            "Return the output grid for test input [[3,3,3],[3,0,3],[3,3,3]]."
        ),
        "examples": [
            {
                "input": [[2, 2, 2], [2, 0, 2], [2, 2, 2]],
                "output": [[2, 2, 2], [2, 2, 2], [2, 2, 2]],
            },
            {
                "input": [[4, 4, 4], [4, 0, 4], [4, 4, 4]],
                "output": [[4, 4, 4], [4, 4, 4], [4, 4, 4]],
            },
        ],
        "answer": [[3, 3, 3], [3, 3, 3], [3, 3, 3]],
        "difficulty": "easy",
        "eligibility": "individual",
    },
    {
        "puzzle_id": "arc-team-stripes",
        "prompt": (
            "ARC-style grid puzzle. Each row is copied into the empty row below it. "
            "Return the output grid for test input [[5,6,5],[0,0,0],[7,8,7],[0,0,0]]."
        ),
        "examples": [
            {
                "input": [[1, 2, 1], [0, 0, 0], [3, 4, 3], [0, 0, 0]],
                "output": [[1, 2, 1], [1, 2, 1], [3, 4, 3], [3, 4, 3]],
            }
        ],
        "answer": [[5, 6, 5], [5, 6, 5], [7, 8, 7], [7, 8, 7]],
        "difficulty": "medium",
        "eligibility": "team",
    },
]
