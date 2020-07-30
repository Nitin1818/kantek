"""Plugin to manage the autobahn"""
import asyncio
import logging
import re
from collections import Counter

import logzero
from pyArango.document import Document
from telethon.errors import MessageIdInvalidError
from telethon.tl.custom import Message

from database.arango import ArangoDB
from utils import helpers, constants
from utils.client import Client
from utils.mdtex import *
from utils.pluginmgr import k

tlog = logging.getLogger('kantek-channel-log')
logger: logging.Logger = logzero.logger

AUTOBAHN_TYPES = {
    'bio': '0x0',
    'string': '0x1',
    'filename': '0x2',
    'channel': '0x3',
    'domain': '0x4',
    'file': '0x5',
    'mhash': '0x6',
    'tld': '0x7',
}

INVITELINK_PATTERN = re.compile(r'(?:joinchat|join)(?:/|\?invite=)(.*|)')


@k.command('autobahn', 'ab')
async def autobahn() -> MDTeXDocument:
    """Manage Autobahn blacklists.

    Each message will be checked for blacklisted items and if a match is found the user is automatically gbanned.
    """
    return MDTeXDocument(
        Section('Types',
                *[KeyValueItem(Bold(name), Code(code)) for name, code in AUTOBAHN_TYPES.items()]))


@autobahn.subcommand()
async def add(client: Client, db: ArangoDB, msg: Message, args,
              event) -> MDTeXDocument:  # pylint: disable = R1702
    """Add a item to its blacklist.

    Blacklist names are _not_ the hexadecimal short hands

    Arguments:
        `type`: One of the possible autobahn types (See {prefix}ab)
        `item`: The item to be blacklisted. Not required for the file and mhash blacklists.

    Examples:
        {cmd} domain example.com
        {cmd} string "invest with bitcoin"
        {cmd} channel @durov
    """
    item_type = args[0]
    items = args[1:]
    added_items = []
    existing_items = []
    skipped_items = []
    hex_type = AUTOBAHN_TYPES.get(item_type)
    collection = db.ab_collection_map.get(hex_type)
    warn_message = ''

    for item in items:  # pylint: disable = R1702
        if hex_type is None or collection is None:
            continue
        if hex_type == '0x3':
            _item = item
            _, chat_id, _ = await helpers.resolve_invite_link(item)
            item = chat_id
            if item is None:
                if _item.startswith('tg://resolve'):
                    # tg://resolve?domain=<username>&start=<value>
                    params = re.split(r'[?&]', _item)[1:]
                    for param in params:
                        if param.startswith('domain'):
                            _, _item = param.split('=')
                else:
                    # remove any query parameters like ?start=
                    # replace @ aswell since some spammers started using it, only Telegram X supports it
                    _item = _item.split('?')[0].replace('@', '')
                try:
                    entity = await event.client.get_entity(_item)
                except constants.GET_ENTITY_ERRORS as err:
                    logger.error(err)
                    skipped_items.append(_item)
                    continue
                if entity:
                    item = entity.id
        elif hex_type == '0x4':
            item = (await client.resolve_url(item)).lower()
            if item in constants.TELEGRAM_DOMAINS:
                skipped_items.append(item)
                continue
        elif hex_type == '0x7':
            item = item.replace('.', '')
        # avoids "null" being added to the db
        if item is None:
            skipped_items.append(item)
            continue

        existing_one = collection.fetchByExample({'string': item}, batchSize=1)

        if not existing_one:
            collection.add_item(item)
            added_items.append(Code(item))
        else:
            existing_items.append(Code(item))

    if not items and hex_type == '0x5':
        if msg.is_reply:
            reply_msg: Message = await msg.get_reply_message()
            if reply_msg.file:
                await msg.edit('Downloading file, this may take a while.')

                file = await reply_msg.download_media(
                    bytes,
                    progress_callback=lambda r, t: _sync_file_callback(r, t, msg))
                file_hash = await helpers.hash_file(file)
                await msg.delete()
                existing_one = collection.fetchByExample({'string': file_hash}, batchSize=1)

                short_hash = f'{file_hash[:15]}[...]'
                if not existing_one:
                    collection.add_item(file_hash)
                    added_items.append(Code(short_hash))
                else:
                    existing_items.append(Code(short_hash))
            else:
                return MDTeXDocument(Section('Error', 'Need to reply to a file'))
        else:
            return MDTeXDocument(Section('Error', 'Need to reply to a file'))
    if not items and hex_type == '0x6':
        if msg.is_reply:
            reply_msg: Message = await msg.get_reply_message()
            if reply_msg.photo:
                await msg.edit('Hashing photo, this may take a moment.')

                dl_photo = await reply_msg.download_media(bytes)
                photo_hash = await helpers.hash_photo(dl_photo)
                await msg.delete()
                existing_one = collection.fetchByExample({'string': photo_hash}, batchSize=1)

                if not existing_one:
                    collection.add_item(photo_hash)
                    if Counter(photo_hash).get('0', 0) > 8:
                        warn_message = ('The image seems to contain a lot of the same color.'
                                        ' This might lead to false positives.')

                    added_items.append(Code(photo_hash))
                else:
                    existing_items.append(Code(photo_hash))
            else:
                return MDTeXDocument(Section('Error', 'Need to reply to a photo'))
        else:
            return MDTeXDocument(Section('Error', 'Need to reply to a photo'))

    return MDTeXDocument(Section('Added Items:',
                                 SubSection(item_type,
                                            *added_items)) if added_items else '',
                         Section('Existing Items:',
                                 SubSection(item_type,
                                            *existing_items)) if existing_items else '',
                         Section('Skipped Items:',
                                 SubSection(item_type,
                                            *skipped_items)) if skipped_items else '',
                         Section('Warning:',
                                 warn_message) if warn_message else ''
                         )


@autobahn.subcommand()
async def del_(db: ArangoDB, args) -> MDTeXDocument:
    """Remove a item from its blacklist.

    Blacklist names are _not_ the hexadecimal short hands

    Arguments:
        `type`: One of the possible autobahn types (See {prefix}ab)
        `item`: The item to be blacklisted. Not required for the file and mhash blacklists.

    Examples:
        {cmd} domain example.com
        {cmd} string "invest with bitcoin"
        {cmd} channel @durov
    """
    item_type = args[0]
    items = args[1:]
    removed_items = []
    for item in items:
        hex_type = AUTOBAHN_TYPES.get(item_type)
        collection = db.ab_collection_map.get(hex_type)
        if hex_type is None or collection is None:
            continue

        if hex_type == '0x3':
            _, chat_id, _ = await helpers.resolve_invite_link(str(item))
            item = chat_id

        existing_one: Document = collection.fetchFirstExample({'string': item})
        if existing_one:
            existing_one[0].delete()
            removed_items.append(item)

    return MDTeXDocument(Section('Deleted Items:',
                                 SubSection(item_type,
                                            *removed_items)))


@autobahn.subcommand()
async def query(kwargs, db: ArangoDB) -> MDTeXDocument:
    """Query a blacklist for a specific code.

    Blacklist names are _not_ the hexadecimal short hands

    Arguments:
        `type`: One of the possible autobahn types (See {prefix}ab)
        `code`: The index of the item, can be a range

    Examples:
        {cmd} type: domain code: 3
        {cmd} type: channel code: 4..20
    """
    item_type = kwargs.get('type')
    code = kwargs.get('code')

    hex_type = None
    collection = None
    if item_type is not None:
        hex_type = AUTOBAHN_TYPES.get(item_type)
        collection = db.ab_collection_map[hex_type]
    if code is None:
        all_strings = collection.fetchAll()
        if not len(all_strings) > 100:
            items = [KeyValueItem(Bold(f'0x{doc["_key"]}'.rjust(5)),
                                  Code(doc['string'])) for doc in all_strings]
        else:
            items = [Pre(', '.join([doc['string'] for doc in all_strings]))]
        return MDTeXDocument(Section(f'Items for type: {item_type}[{hex_type}]'), *items)

    elif hex_type is not None and code is not None:
        if isinstance(code, int):
            string = collection.fetchDocument(code).getStore()['string']
            return MDTeXDocument(Section(f'Items for type: {item_type}[{hex_type}] code: {code}'), Code(string))
        elif isinstance(code, (range, list)):
            keys = [str(i) for i in code]
            documents = db.query('FOR doc IN @@collection '
                                 'FILTER doc._key in @keys '
                                 'RETURN doc',
                                 bind_vars={'@collection': collection.name,
                                            'keys': keys})
            items = [KeyValueItem(Bold(f'0x{doc["_key"]}'.rjust(5)),
                                  Code(doc['string'])) for doc in documents]
            return MDTeXDocument(
                Section(f'Items for for type: {item_type}[{hex_type}]'), *items)


def _sync_file_callback(received: int, total: int, msg: Message) -> None:
    loop = asyncio.get_event_loop()
    loop.create_task(_file_callback(received, total, msg))
    # msg.edit(args)


async def _file_callback(received: int, total: int, msg: Message) -> None:
    text = MDTeXDocument(
        Section('Downloading File',
                KeyValueItem('Progress',
                             f'{received / 1024 ** 2:.2f}/{total / 1024 ** 2:.2f}MB'
                             f' ({(received / total) * 100:.0f}%)')))
    try:
        await msg.edit(str(text))
    except MessageIdInvalidError as err:
        logger.error(err)
