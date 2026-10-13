"""Generation-specific Pokémon media selection."""

from ..utils import int_to_roman


def select_cries(cries: dict, target_gen: int | None) -> dict | None:
    """
    Resolves the cries object to the recording used in the target generation.

    PokéAPI splits cries into "legacy" (Gen 1-5 style) and "latest"
    (redesigned in Gen 6) recordings, so this is real per-generation data
    rather than an unversioned current value.
    """
    if not cries:
        return None
    if target_gen is None:
        return cries
    if target_gen < 6:
        return {"legacy": cries.get("legacy")} if cries.get("legacy") else None
    return {"latest": cries.get("latest")} if cries.get("latest") else None


def select_sprites(sprites: dict, target_gen: int | None, is_historical: bool) -> dict:
    """
    Refines the sprites object to only include the target generation's version data.
    """
    if not sprites:
        return {}

    processed_sprites = (
        {} if is_historical else {k: v for k, v in sprites.items() if k != "versions"}
    )

    if "versions" in sprites and target_gen is not None:
        gen_roman = int_to_roman(target_gen)
        gen_key = f"generation-{gen_roman.lower()}"
        if gen_key in sprites["versions"]:
            processed_sprites["versions"] = sprites["versions"][gen_key]

    return {k: v for k, v in processed_sprites.items() if v is not None}
