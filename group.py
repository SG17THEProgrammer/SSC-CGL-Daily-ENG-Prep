from telethon import TelegramClient
from telethon.tl.types import Chat, Channel

api_id = 30902528
api_hash = "d488fac8307d765b1b8cdb1a2334e7f9"

client = TelegramClient('session', api_id, api_hash)

async def get_all_groups():
    groups = []

    async for dialog in client.iter_dialogs():
        entity = dialog.entity

        # ✅ Small groups
        if isinstance(entity, Chat):
            groups.append({
                "id": entity.id,
                "title": entity.title
            })

        # ✅ Supergroups (Channel with megagroup=True)
        elif isinstance(entity, Channel) and entity.megagroup:
            groups.append({
                "id": entity.id,
                "title": entity.title
            })

    return groups


with client:
    result = client.loop.run_until_complete(get_all_groups())
    print(result)