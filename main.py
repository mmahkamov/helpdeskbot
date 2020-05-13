import os.path
import telegram
import redis
import gettext
import configparser

from functools import wraps
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

import logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Configuring bot
logging.debug("Configuring the bot")

config = configparser.ConfigParser()
config.read_file(open('config.ini'))

# Connecting to Telegram API
# Updater retrieves information and dispatcher connects commands
logging.debug("Connecting to Telegram")

updater = Updater(token=config['DEFAULT']['token'], use_context=True)
dispatcher = updater.dispatcher

# Config the translations
languages = { locale : config['LANGUAGES'][locale] for locale in config['DEFAULT']['languages'].split(",") }
logging.debug("Supported languages: {}".format(languages))

lang_map = { locale : gettext.translation(locale, localedir="locale", languages=[locale]) for locale in languages.keys() }
logging.debug("Supported languages: {}".format(lang_map))

def _(msg): return msg

# Connecting to Redis db
logging.debug("Connecting to Redis")

db = redis.StrictRedis(host=config['DB']['host'],
                       port=config['DB']['port'],
                       db=config['DB']['db'])

def user_language(func):
    @wraps(func)
    def wrapped(update, context, *args, **kwargs):
        lang = db.get(str(update.message.chat_id))

        if lang is None:
            lang = "en_US"
        else:
            lang = lang.decode('UTF-8')

        global _

        if lang in lang_map.keys():
            logging.debug("Switching to language: {}".format(lang))
            _ = lang_map[lang].gettext
        else:
            logging.debug("Language {} not found".format(lang))
            # If not, leaves as en_US
            def _(msg): return msg

        result = func(update, context, *args, **kwargs)
        return result
    return wrapped


@user_language
def start(update, context):
    logging.debug("Received Start command")

    """
        Shows an welcome message and help info about the available commands.
    """
    me = context.bot.get_me()

    # Welcome message
    msg = _("Hello!\n")
    msg += _("I'm {0} and I came here to help you.\n").format(me.first_name)
    msg += _("What would you like to do?\n\n")
    msg += _("/support - Opens a new support ticket\n")
    msg += _("/settings - Settings of your account\n\n")

    # Commands menu
    main_menu_keyboard = [[telegram.KeyboardButton('/support')],
                          [telegram.KeyboardButton('/settings')]]
    reply_kb_markup = telegram.ReplyKeyboardMarkup(main_menu_keyboard,
                                                   resize_keyboard=True,
                                                   one_time_keyboard=True)

    # Send the message with menu
    context.bot.send_message(chat_id=update.message.chat_id,
                     text=msg,
                     reply_markup=reply_kb_markup)


@user_language
def support(update, context):
    """
        Sends the support message. Some kind of "How can I help you?".
    """
    context.bot.send_message(chat_id=update.message.chat_id,
                     text=_("Please, tell me what you need support with :)"))


@user_language
def support_message(update, context):
    """
        Receives a message from the user.

        If the message is a reply to the user, the bot speaks with the user
        sending the message content. If the message is a request from the user,
        the bot forwards the message to the support group.
    """
    if update.message.reply_to_message and \
       update.message.reply_to_message.forward_from:
        # If it is a reply to the user, the bot replies the user
        context.bot.send_message(chat_id=update.message.reply_to_message
                         .forward_from.id,
                         text=update.message.text)
    else:
        # If it is a request from the user, the bot forwards the message
        # to the group
        context.bot.forward_message(chat_id=int(config['DEFAULT']['support_chat_id']),
                            from_chat_id=update.message.chat_id,
                            message_id=update.message.message_id)
        context.bot.send_message(chat_id=update.message.chat_id,
                         text=_("Give me some time to think. Soon I will return to you with an answer."))


@user_language
def settings(update, context):
    """
        Configure the messages language using a custom keyboard.
    """
    # Languages message
    msg = _("Please, choose a language:\n")

    # Languages menu
    languages_keyboard = []

    for locale in languages.keys():
        lang_str = "{} - {}".format(locale, languages[locale])

        msg += "{}\n".format(lang_str)
    
        languages_keyboard.append(
            [telegram.KeyboardButton(lang_str)]
        )
        
    reply_kb_markup = telegram.ReplyKeyboardMarkup(languages_keyboard,
                                                   resize_keyboard=True,
                                                   one_time_keyboard=True)

    # Sends message with languages menu
    context.bot.send_message(chat_id=update.message.chat_id,
                     text=msg,
                     reply_markup=reply_kb_markup)


@user_language
def kb_settings_select(update, context):
    """
        Updates the user's language based on it's choice.
    """
    logging.debug("Matches: {}".format(context.matches))

    chat_id = update.message.chat_id
    language = context.matches[0].group(1)

    logging.debug("Selected language {}".format(language))

    # If the language choice matches the expression AND is a valid choice
    if language in languages.keys():
        # Sets the user's language
        db.set(str(chat_id), language)
        context.bot.send_message(chat_id=chat_id,
                         text=_("Language updated to {0}")
                         .format(languages[language]))
    else:
        # If it is not a valid choice, sends an warning
        context.bot.send_message(chat_id=chat_id,
                         text=_("Unknown language! :("))


@user_language
def unknown(update, context):
    """
        Placeholder command when the user sends an unknown command.
    """
    msg = _("Sorry, I don't know what you're asking for.")
    context.bot.send_message(chat_id=update.message.chat_id,
                     text=msg)

# creating handlers
start_handler = CommandHandler('start', start)
support_handler = CommandHandler('support', support)
support_msg_handler = MessageHandler(Filters.text, support_message)
settings_handler = CommandHandler('settings', settings)
get_language_handler = MessageHandler(Filters.regex('^([a-z]{2}_[A-Z]{2}) - .*'),
                                    kb_settings_select)
help_handler = CommandHandler('help', start)
unknown_handler = MessageHandler(Filters.command, unknown)

# adding handlers
dispatcher.add_handler(start_handler)
dispatcher.add_handler(support_handler)
dispatcher.add_handler(settings_handler)
dispatcher.add_handler(get_language_handler)
dispatcher.add_handler(help_handler)
dispatcher.add_handler(unknown_handler)

# Message handler must be the last one
dispatcher.add_handler(support_msg_handler)

# to run this program:
logging.debug("start polling")
updater.start_polling()
# to stop it:
# updater.stop()
