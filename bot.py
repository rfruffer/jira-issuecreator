from telegram import Update
from telegram import Bot
from telegram.ext import Updater
from telegram.ext import Filters
from telegram.ext import MessageHandler
from telegram.ext import CommandHandler
from telegram.ext import CallbackContext
from telegram.utils.request import Request
from telegram import ParseMode
import re
from dateutil import parser
from datetime import datetime, timezone
import time

import os

from jira import JIRA

print ("Begining work...")

STREAM_CHAT_ID = 1111
BUGS_CHAT_ID = 2222
SUPPORT_CHAT_ID = 3333

jira = JIRA("https://jira.host.ru/", token_auth='')

def do_echo(update: Update, context: CallbackContext):
    data = update.message
    chat_id = data["chat_id"]
    title = data["chat"]["title"]

    isReply = data["reply_to_message"] is not None
    isSupport = "#support" in data["text"].lower()
    isStream = "#stream" in data["text"].lower()

    if chat_id in [STREAM_CHAT_ID,BUGS_CHAT_ID,SUPPORT_CHAT_ID] and isReply and (isSupport or isStream):
        dataUser = data["reply_to_message"]["from_user"]
        if data["reply_to_message"]["forward_from"]:
            dataUser = data["reply_to_message"]["forward_from"]
        userMain = "Name: %s %s\nLogin: %s\nMessage url: https://t.me/c/%s/%s"%(dataUser["first_name"],
                                                                                dataUser["last_name"],
                                                                                dataUser["username"],
                                                                                str(chat_id).replace("-100", ""),
                                                                                data["reply_to_message"]["message_id"])

        message = data["text"].replace("#support", "")
        message = message.replace("#stream", "")
        dateTime = None

        if isStream:
            dateTimeObj = re.search('{(.*)}', message)
            if dateTimeObj:
                dateTime = dateTimeObj.group(1)
                message = message.replace("{"+dateTime+"}", "")
                finalDate = re.match("^[\d][\d][\d][\d]-[\d][\d]-[\d][\d].[\d][\d]:[\d][\d]$",dateTime)
            else:
                context.bot.send_message(
                    chat_id=chat_id,
                    text="Нужно указать дату и время стрима. Пример: #stream {2022-07-22 14:35}",
                    parse_mode=ParseMode.HTML
                )
                return

            if finalDate:
                message += "*Трансляция начнется: %s*"%(finalDate.group(0))
            else :
                context.bot.send_message(
                    chat_id=chat_id,
                    text="Дата и время не соответствуют шаблону {гггг-мм-дд чч:мм}",
                    parse_mode=ParseMode.HTML
                )
                return

        message += "\n\n"
        replyData = data["reply_to_message"]

        caption = replyData["caption"]

        data = replyData["date"]
        text = replyData["text"]
        userId = replyData["from_user"]["id"]

        summary = ""
        summaryBody = text

        if summaryBody is None:
            summaryBody = caption

        if summaryBody is not None:
            arr = summaryBody.split("\n")
            finish = False

            if len(arr)>=1:
                textLine = arr[0]
                if (len(textLine) > 60):
                    summary = textLine[0:60].replace("\n", " ")+"..."
                    finish = True
                else :
                    summary = arr[0]

            if len(arr)>2 and finish == False:
                textLine = arr[1]
                if (len(textLine) > 60):
                    summary += " "+textLine[0:60].replace("\n", " ")+"..."
                    finish = True
                else :
                    summary += " "+arr[1]
            if len(arr)>3 and finish == False:
                textLine = arr[2]
                if (len(textLine) > 60):
                    summary += " "+textLine[0:60].replace("\n", " ")+"..."
                else :
                    summary += " "+arr[2]
        else:
            summary = "Запрос из чата (%s)"%(title)

        user = "%s %s"%(replyData["from_user"]["first_name"],replyData["from_user"]["last_name"])

        if text is not None:
            message += "%s (%s):\n%s\n\n"%(user, data, text)

        if caption is not None:
            message += "%s (%s):\n%s\n\n"%(user, data, caption)

        hasFile = len(replyData.photo)>0
        hasVideo = replyData.video is not None

        needAddAttach = hasFile or hasVideo

        # hasFile = replyData.photo[0]["file_id"]  is not None
        payload = None
        if isSupport:
            if chat_id in [STREAM_CHAT_ID]:
                payload = createStreamSuportIssue(message, user, userId, summary, userMain)
            if chat_id in [BUGS_CHAT_ID]:
                payload = createBugsSuportIssue(message, user, userId, summary, userMain)
            if chat_id in [SUPPORT_CHAT_ID]:
                payload = createSuportIssue(message, user, userId, summary, userMain)                
        if isStream:
            date_time_obj = parser.parse(dateTime)
            # dateTime = datetime.fromisoformat(date_time_obj).astimezone(timezone.utc)
            # dateTime = date_time_obj.strftime("%Y-%m-%dT%H:%M:%SZ")#
            dateTime = date_time_obj.isoformat()
            payload = createStreamIssue(message, user, userId, summary, dateTime, userMain)

        try:
            new_issue = jira.create_issue(fields=payload)
        except BaseException as error:
            print(error)
            new_issue = None
        if new_issue:
            context.bot.send_message(
                chat_id=chat_id,
                text="По Вашему обращению создана задача - <a href='https://jira.host.ru/browse/%s'>%s</a>"%(new_issue,new_issue),
                parse_mode=ParseMode.HTML
            )
            if needAddAttach:
                time.sleep(4)
                fileMassage = ""
                if hasFile:
                    fileMassage = replyData.photo[-1]["file_id"]
                if hasVideo:
                    fileMassage = replyData.video["file_id"]
                file = context.bot.get_file(fileMassage)
                files = file.download()
                jira.add_attachment(new_issue,files)
                os.remove(files)                
        else:
            context.bot.send_message(
                chat_id=chat_id,
                text="Не удалось создать запрос",
                parse_mode=ParseMode.HTML
            )

def createStreamIssue(message, user, userId, summary, dateTime, userMain):
    obj = {'project': {'key': 'HDSPSL'},
           'summary': summary,
           'description': message,
           'issuetype': {'id': '11001'},
           'reporter': {"name": "jira"},
           # 'components': [{"name": "Не знаю"}],
           'customfield_12001': { "value": "Чат" },
           'customfield_12001': str(dateTime+".000+0300") ,
           'customfield_12003': userMain,
           }
    return obj

def createSuportIssue(message, user, userId, summary, userMain):
    obj = {'project': {'key': 'HDSPSL'},
           'summary': summary,
           'description': message,
           'issuetype': {'id': '10001'},
           'reporter': {"name": "jira"},
           # 'components': [{"name": "Не знаю"}],
           'customfield_13001': { "value": "Support" },
           'customfield_13002': { "value": "Обращение" },
           'customfield_13003': userMain,
           }
    return obj

def createBugsSuportIssue(message, user, userId, summary, userMain):
    obj = {'project': {'key': 'HDSPSL'},
           'summary': summary,
           'description': message,
           'issuetype': {'id': '10001'},
           'reporter': {"name": "jira"},
           # 'components': [{"name": "Не знаю"}],
           'customfield_13001': { "value": "Bug" },
           'customfield_13002': { "value": "Обращение" },
           'customfield_13003': userMain,
           }
    return obj

def createStreamSuportIssue(message, user, userId, summary, userMain):
    obj = {'project': {'key': 'HDSPSL'},
           'summary': summary,
           'description': message,
           'issuetype': {'id': '10001'},
           'reporter': {"name": "jira"},
           # 'components': [{"name": "Не знаю"}],
           'customfield_12001': { "value": "Чат" },
           'customfield_13003': userMain,
           }
    return obj

def main():
    print ("Starting bot...")

    req = Request(
        connect_timeout=0.5,
        read_timeout=1.0,
    )
    bot = Bot(
        token='',
        request=req,
    )
    updater = Updater(
        bot=bot,
        use_context=True,
    )

    print ("---------------------------")

    # Навесить обработчики команд
    message_handler = MessageHandler(Filters.text, do_echo)

    updater.dispatcher.add_handler(message_handler)

    # Начать бесконечную обработку входящих сообщений
    updater.start_polling()
    updater.idle()

    print ("Finished work...")

if __name__ == '__main__':
    main()

