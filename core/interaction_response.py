"""Single-response handling for expired or concurrently acknowledged interactions."""

import logging

import discord

logger = logging.getLogger(__name__)
UNAVAILABLE_CODES = {40060, 10062, 10015}


def interaction_unavailable(error):
    """Unwrap command errors without hiding unrelated HTTP failures."""
    for _ in range(5):
        if isinstance(error, discord.HTTPException) and error.code in UNAVAILABLE_CODES:
            return True
        original = getattr(error, "original", None)
        if original is None or original is error:
            break
        error = original
    return False


async def defer_once(interaction, *, ephemeral=True):
    """Acknowledge before slow work; stop if Discord rejects ownership of the reply."""
    if interaction.is_expired():
        return False
    if interaction.response.is_done():
        return True
    try:
        await interaction.response.defer(ephemeral=ephemeral, thinking=True)
        return True
    except discord.InteractionResponded:
        return True
    except discord.HTTPException as error:
        if not interaction_unavailable(error):
            raise
        logger.warning("Interaction %s unavailable during acknowledgement (code %s)", interaction.id, error.code)
        return False


async def respond(interaction, content=None, **kwargs):
    """Send privately when requested, without falling back to a public channel."""
    if interaction.is_expired():
        return False
    if content is not None:
        kwargs["content"] = content
    try:
        if interaction.response.is_done():
            await interaction.followup.send(**kwargs)
        else:
            try:
                await interaction.response.send_message(**kwargs)
            except discord.InteractionResponded:
                await interaction.followup.send(**kwargs)
        return True
    except discord.HTTPException as error:
        if not interaction_unavailable(error) and not isinstance(error, discord.Forbidden):
            raise
        logger.warning("Interaction %s reply unavailable (code %s)", interaction.id, error.code)
        return False


async def report_error(interaction, error, embed):
    """Hybrid and application error handlers must not report the same error twice."""
    if interaction_unavailable(error) or interaction.extras.get("lexus_error_reported"):
        return
    interaction.extras["lexus_error_reported"] = True
    await respond(interaction, embed=embed, ephemeral=True)
