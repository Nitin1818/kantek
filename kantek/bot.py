"""Main bot module. Setup logging, register components"""
import logging
import os

import logzero

from spamwatch.client import Client as SWClient
from database.arango import ArangoDB
from utils._config import Config
from utils.client import Client
from utils.loghandler import TGChannelLogHandler
from utils.pluginmgr import PluginManager

logger = logzero.setup_logger('kantek-logger', level=logging.DEBUG)
telethon_logger = logzero.setup_logger('telethon', level=logging.INFO)
tlog = logging.getLogger('kantek-channel-log')

tlog.setLevel(logging.INFO)

__version__ = '0.3.1'


def main() -> None:
    """Register logger and components."""
    config = Config()

    handler = TGChannelLogHandler(config.log_bot_token,
                                  config.log_channel_id)
    tlog.addHandler(handler)

    client = Client(
        os.path.abspath(config.session_name),
        config.api_id,
        config.api_hash)
    # noinspection PyTypeChecker
    client.start(config.phone)

    client.config = config
    client.kantek_version = __version__

    client.plugin_mgr = PluginManager(client)
    client.plugin_mgr.register_all()

    logger.info('Connecting to Database')
    client.db = ArangoDB(config.db_host,
                         config.db_username,
                         config.db_password,
                         config.db_name)

    tlog.info('Started Kantek v%s', __version__)
    logger.info('Started Kantek v%s', __version__)

    if config.spamwatch_host and config.spamwatch_token:
        client.sw = SWClient(config.spamwatch_token, host=config.spamwatch_host)
        client.sw_url = config.spamwatch_host

    client.run_until_disconnected()


if __name__ == '__main__':
    main()
