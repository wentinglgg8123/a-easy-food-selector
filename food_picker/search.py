"""Local name lookup and conservative Mandarin pronunciation suggestions."""

from collections.abc import Sequence
from functools import lru_cache
import unicodedata

from pypinyin import Style, pinyin

from .models import Restaurant


def _normalise(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in text if character.isalnum())


def _is_han(character: str) -> bool:
    code = ord(character)
    return (
        0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0xF900 <= code <= 0xFAFF
        or 0x20000 <= code <= 0x323AF
    )


@lru_cache(maxsize=2_048)
def _sounds(text: str) -> tuple[frozenset[str], ...]:
    # Keep one syllable set per character. Joining syllables would incorrectly
    # identify "xi an" with "xian". Unknown letters remain separate characters.
    readings = pinyin(
        text, style=Style.NORMAL, heteronym=True,
        errors=lambda unknown: list(unknown),
    )
    tokens = []
    for character, phrase_readings in zip(text, readings):
        # Phrase dictionaries can suppress a valid brand-name pronunciation:
        # 呱呱 is normally "gu gu", while 頂呱呱 is pronounced "ding gua gua".
        character_readings = pinyin(character, style=Style.NORMAL, heteronym=True)[0] if _is_han(character) else ()
        tokens.append(frozenset(phrase_readings) | frozenset(character_readings))
    return tuple(tokens)


def _distance(left: str, right: str, maximum: int) -> int:
    """Bound Levenshtein work and return maximum + 1 when already too distant."""
    if abs(len(left) - len(right)) > maximum:
        return maximum + 1
    previous = list(range(len(right) + 1))
    for index, left_character in enumerate(left, start=1):
        current = [index]
        for offset, right_character in enumerate(right, start=1):
            current.append(min(
                current[-1] + 1,
                previous[offset] + 1,
                previous[offset - 1] + (left_character != right_character),
            ))
        if min(current) > maximum:
            return maximum + 1
        previous = current
    return previous[-1]


def _near_syllables(left: frozenset[str], right: frozenset[str]) -> bool:
    # A single sound spelling change covers common n/l, s/sh, an/ang, etc.
    # Two short unrelated syllables are not treated as a pronunciation typo.
    return any(
        max(len(first), len(second)) >= 3 and _distance(first, second, 1) <= 1
        for first in left for second in right
    )


def find_restaurants(restaurants: Sequence[Restaurant], query: str) -> list[Restaurant]:
    """Find literal name substrings, including closed entries, in source order."""
    needle = _normalise(query)
    if not needle:
        return []
    return [restaurant for restaurant in restaurants if needle in _normalise(restaurant.name)]


def _window_score(
    query: str,
    name: str,
    query_sounds: tuple[frozenset[str], ...],
    name_sounds: tuple[frozenset[str], ...],
) -> tuple[int, float, int] | None:
    if query in name:
        return 0, 0, len(name) - len(query)
    # One arbitrary character edit is useful for short names; longer queries
    # may contain two. Short two-character searches require a phonetic match.
    maximum_edits = 1 if len(query) < 6 else 2
    best = None
    minimum_size = max(1, len(query) - maximum_edits)
    maximum_size = min(len(name), len(query) + maximum_edits)
    for size in range(minimum_size, maximum_size + 1):
        for start in range(len(name) - size + 1):
            window = name[start:start + size]
            character_distance = _distance(query, window, maximum_edits)
            score = None
            if size == len(query):
                window_sounds = name_sounds[start:start + size]
                mismatches = [
                    index for index, (first, second) in enumerate(zip(query_sounds, window_sounds))
                    if _is_han(query[index]) != _is_han(window[index]) or first.isdisjoint(second)
                ]
                if not mismatches:
                    score = (1, 0, _distance(query, window, len(query)))
                elif len(mismatches) <= maximum_edits and all(
                    _is_han(query[index]) and _is_han(window[index])
                    and _near_syllables(query_sounds[index], window_sounds[index])
                    for index in mismatches
                ):
                    score = (2, len(mismatches), _distance(query, window, len(query)))
            if score is None and len(query) >= 3 and character_distance <= maximum_edits:
                ratio = character_distance / max(len(query), size)
                if ratio <= 1 / 3:
                    score = (3, ratio, character_distance)
            if score is not None and (best is None or score < best):
                best = score
    return best


def suggest_restaurants(
    restaurants: Sequence[Restaurant], query: str, limit: int = 5,
) -> list[Restaurant]:
    """Rank close names without inventing matches for empty or unrelated input.

    Literal matches rank before homophones, similar syllables, and character
    typos. Comparisons use contiguous name windows so a short store name can
    suggest a longer registered name. Equal scores retain source order.
    """
    needle = _normalise(query)
    if not 2 <= len(needle) <= 64 or isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        return []
    query_sounds = _sounds(needle)
    ranked = []
    seen: set[str] = set()
    for index, restaurant in enumerate(restaurants):
        if restaurant.id in seen:
            continue
        seen.add(restaurant.id)
        name = _normalise(restaurant.name)
        if not name or len(name) + 2 < len(needle):
            continue
        score = _window_score(needle, name, query_sounds, _sounds(name))
        if score is not None:
            ranked.append((score, index, restaurant))
    ranked.sort(key=lambda entry: (entry[0], entry[1]))
    return [restaurant for _, _, restaurant in ranked[:min(limit, 5)]]
