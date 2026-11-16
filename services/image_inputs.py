"""Read user-uploaded Discord images without following arbitrary web URLs."""
import base64


async def read_images(attachments):
    if len(attachments) > 3:
        raise ValueError("Attach up to three images per request.")
    images = []
    total = 0
    for attachment in attachments:
        if attachment.size > 6 * 1024 * 1024:
            raise ValueError("Each image must be 6 MB or smaller.")
        data = await attachment.read()
        if len(data) > 6 * 1024 * 1024:
            raise ValueError("Each image must be 6 MB or smaller.")
        total += len(data)
        if total > 12 * 1024 * 1024:
            raise ValueError("Images together must be 12 MB or smaller.")
        if data.startswith(b'\x89PNG\r\n\x1a\n'):
            mime = "image/png"
        elif data.startswith(b'\xff\xd8\xff'):
            mime = "image/jpeg"
        elif data.startswith(b'RIFF') and data[8:12] == b'WEBP':
            mime = "image/webp"
        else:
            raise ValueError("Image analysis supports PNG, JPEG and WebP. Upload a screenshot in one of those formats.")
        images.append(f"data:{mime};base64," + base64.b64encode(data).decode("ascii"))
    return images


async def set_reaction(message, emoji, *, remove=False):
    if message is None:
        return
    import discord
    try:
        if remove:
            await message.remove_reaction(emoji, message.guild.me if message.guild else message._state.user)
        else:
            await message.add_reaction(emoji)
    except (discord.HTTPException, AttributeError):
        pass
