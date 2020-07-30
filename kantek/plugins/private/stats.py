"""Plugin to get statistics of the user account"""
import logging
import time

from telethon.tl.custom import Dialog
from telethon.tl.types import Channel, Chat, User

from utils import helpers
from utils.client import Client
from utils.mdtex import *
from utils.pluginmgr import k, Command

tlog = logging.getLogger('kantek-channel-log')


@k.command('stats')
async def stats(client: Client, event: Command) -> MDTeXDocument:  # pylint: disable = R0912, R0914, R0915
    """Collect stats about the users accounts

    Examples:
        {cmd}
    """
    waiting_message = await client.respond(event, 'Collecting stats. This might take a while.')
    start_time = time.time()
    private_chats = 0
    bots = 0
    groups = 0
    broadcast_channels = 0
    admin_in_groups = 0
    creator_in_groups = 0
    admin_in_broadcast_channels = 0
    creator_in_channels = 0
    unread_mentions = 0
    unread = 0
    dialog: Dialog
    async for dialog in client.iter_dialogs():
        entity = dialog.entity

        if isinstance(entity, Channel):
            if entity.broadcast:
                broadcast_channels += 1
                if entity.creator or entity.admin_rights:
                    admin_in_broadcast_channels += 1
                if entity.creator:
                    creator_in_channels += 1

            elif entity.megagroup:
                groups += 1
                if entity.creator or entity.admin_rights:
                    admin_in_groups += 1
                if entity.creator:
                    creator_in_groups += 1

        elif isinstance(entity, User):
            private_chats += 1
            if entity.bot:
                bots += 1

        elif isinstance(entity, Chat):
            groups += 1
            if entity.creator or entity.admin_rights:
                admin_in_groups += 1
            if entity.creator:
                creator_in_groups += 1

        unread_mentions += dialog.unread_mentions_count
        unread += dialog.unread_count
    stop_time = time.time() - start_time

    full_name = await helpers.get_full_name(await client.get_me())
    response = MDTeXDocument(Section(
        Bold(f'Stats for {full_name}'),
        SubSection(
            KeyValueItem(Bold('Private Chats'), private_chats),
            KeyValueItem(Bold('Users'), private_chats - bots),
            KeyValueItem(Bold('Bots'), bots)),
        KeyValueItem(Bold('Groups'), groups),
        KeyValueItem(Bold('Channels'), broadcast_channels),
        SubSection(
            KeyValueItem(Bold('Admin in Groups'), admin_in_groups),
            KeyValueItem(Bold('Creator'), creator_in_groups),
            KeyValueItem(Bold('Admin Rights'), admin_in_groups - creator_in_groups)),
        SubSection(
            KeyValueItem(Bold('Admin in Channels'), admin_in_broadcast_channels),
            KeyValueItem(Bold('Creator'), creator_in_channels),
            KeyValueItem(Bold('Admin Rights'), admin_in_broadcast_channels - creator_in_channels)),
        KeyValueItem(Bold('Unread'), unread),
        KeyValueItem(Bold('Unread Mentions'), unread_mentions)),
        Italic(f'Took {stop_time:.02f}s'))

    await waiting_message.delete()
    return response
