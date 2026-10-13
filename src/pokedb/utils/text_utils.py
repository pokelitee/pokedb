"""Text parsing and transformation utilities."""

from typing import Any

from .constants import MAX_ROMAN_NUMERAL, ROMAN_NUMERAL_MAP


def int_to_roman(num: int) -> str:
    """
    Converts an integer to a Roman numeral using the subtractive notation.

    Args:
        num: An integer between 1 and 3999 (inclusive)

    Returns:
        The Roman numeral representation as a string

    Raises:
        ValueError: If num is not an integer or is outside the valid range

    Examples:
        >>> int_to_roman(4)
        'IV'
        >>> int_to_roman(1994)
        'MCMXCIV'
    """
    if not isinstance(num, int) or not 0 < num <= MAX_ROMAN_NUMERAL:
        raise ValueError(f"Input must be an integer between 1 and {MAX_ROMAN_NUMERAL}.")

    roman_numeral = []
    for value, numeral in ROMAN_NUMERAL_MAP:
        count, num = divmod(num, value)
        roman_numeral.append(numeral * count)

    return "".join(roman_numeral)


def _get_all_english_entries_generic(
    entries: list[dict[str, Any]],
    key_name: str,
    field_name: str,
    target_set: set,
) -> dict[str, str]:
    """
    Generic helper to find and clean all unique English entries from API data.

    This function maps entries to their field value (version_group or version),
    normalizing whitespace in the text content.

    Args:
        entries: List of entry dictionaries from the API
        key_name: The key in each entry containing the text to extract
        field_name: The field to use for categorization (e.g., 'version_group', 'version')
        target_set: Set of field values to filter for (only include these)

    Returns:
        A dictionary mapping field values to their cleaned English text
    """
    texts: dict[str, str] = {}

    for entry in entries:
        field_value = entry.get(field_name, {}).get("name")

        # Only process English entries that match our target set
        if entry.get("language", {}).get("name") == "en" and field_value in target_set:
            cleaned_text = " ".join(entry.get(key_name, "").split())

            # Store only the first occurrence for each field value
            if cleaned_text and field_value not in texts:
                texts[field_value] = cleaned_text

    return texts


def get_all_english_entries_for_gen_by_game(
    entries: list[dict[str, Any]],
    key_name: str,
    generation_version_groups: dict[int, list[str]] | None = None,
    target_gen: int | None = None,
) -> dict[str, str]:
    """
    Finds and cleans all unique English entries for a specific generation, organized by version group.

    Args:
        entries: List of entry dictionaries from the API (e.g., flavor_text_entries)
        key_name: The key containing the text to extract (e.g., 'flavor_text', 'effect')
        generation_version_groups: Mapping of generation numbers to version group lists
        target_gen: The target generation number to filter entries for

    Returns:
        A dictionary mapping version group names to their cleaned English text,
        or an empty dict if parameters are missing or no matches are found
    """
    if not entries or not generation_version_groups or target_gen is None:
        return {}

    target_version_groups = generation_version_groups.get(target_gen, [])
    if not target_version_groups:
        return {}

    return _get_all_english_entries_generic(
        entries, key_name, "version_group", set(target_version_groups)
    )


def get_all_english_entries_by_version(
    entries: list[dict[str, Any]],
    key_name: str,
    target_versions: set | None = None,
) -> dict[str, str]:
    """
    Finds and cleans all unique English entries for specific game versions.

    This function is designed for API entries that use 'version' rather than
    'version_group' (e.g., flavor_text_entries for species).

    Args:
        entries: List of entry dictionaries from the API
        key_name: The key containing the text to extract (e.g., 'flavor_text')
        target_versions: Set of version names to filter for (e.g., {'red', 'blue'})

    Returns:
        A dictionary mapping version names to their cleaned English text,
        or an empty dict if parameters are missing
    """
    if not entries or not target_versions:
        return {}

    return _get_all_english_entries_generic(
        entries, key_name, "version", target_versions
    )


def get_english_entry(
    entries: list[dict[str, Any]],
    key_name: str,
    generation_version_groups: dict[int, list[str]] | None = None,
    target_gen: int | None = None,
) -> str | None:
    """
    Finds and cleans the most appropriate English entry from multilingual API entries.

    When generation information is provided, this function prioritizes entries from
    newer version groups within the target generation, searching backwards through
    generations if needed.

    Args:
        entries: List of entry dictionaries from the API
        key_name: The key containing the text to extract
        generation_version_groups: Optional mapping of generation numbers to version groups
        target_gen: Optional target generation number for prioritization

    Returns:
        The cleaned English text, or None if no English entry is found
    """
    if not entries:
        return None

    # If we have version group information, prioritize by generation
    if (
        entries
        and "version_group" in entries[0]
        and generation_version_groups
        and target_gen
    ):
        # Build priority list: newest version groups in target gen first, then work backwards
        all_version_groups: list[str] = []
        for generation in range(target_gen, 0, -1):
            all_version_groups.extend(
                reversed(generation_version_groups.get(generation, []))
            )

        # Map version groups to their English entries
        entry_map: dict[str, dict[str, Any]] = {}
        for entry in entries:
            if entry.get("language", {}).get("name") == "en":
                version_group_name = entry.get("version_group", {}).get("name")
                if version_group_name:
                    entry_map[version_group_name] = entry

        # Return the first match in priority order
        for version_group_name in all_version_groups:
            if version_group_name in entry_map:
                cleaned = " ".join(entry_map[version_group_name][key_name].split())
                return cleaned or None

    # Fallback: return the first English entry found
    for entry in entries:
        if entry.get("language", {}).get("name") == "en":
            cleaned = " ".join(entry[key_name].split())
            return cleaned or None

    return None
