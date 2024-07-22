import json
import os
import pickle
import tempfile
from datetime import timedelta, datetime
from re import match

import data
from config.auth import admin_ids
from config.logger import logger
from constants import DEPTS, CODIGO_DEPTS, CODIGO_CURSO
from data import jq, dp
from utils import save_config, try_msg
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update


def start(update, context):
    logger.info("[Command /start]")
    if context.chat_data.get("enable", False):
        try_msg(context.bot,
                chat_id=update.message.chat_id,
                text="¡Mis avisos para este chat ya están activados! El próximo chequeo será aproximadamente a las "
                     + (data.last_check_time + timedelta(seconds=300)).strftime("%H:%M") +
                     ".\nRecuerda configurar los avisos de este chat usando /suscribir_depto o /suscribir_curso"
                )
    else:
        context.chat_data["enable"] = True
        try_msg(context.bot,
                chat_id=update.message.chat_id,
                text="A partir de ahora avisaré por este chat si detecto algún cambio en el catálogo de cursos."
                     "\nRecuerda configurar los avisos de este chat usando /suscribir_depto o /suscribir_curso"
                )


def stop(update, context):
    logger.info("[Command /stop]")
    context.chat_data["enable"] = False
    try_msg(context.bot,
            chat_id=update.message.chat_id,
            text="Ok, dejaré de avisar cambios en el catálogo por este chat. "
                 "Puedes volver a activar los avisos enviándome /start nuevamente."
            )

def multicode_depto_subscription(update, context):
    if "subscribed_deptos" not in context.chat_data:
        context.chat_data["subscribed_deptos"] = []
    subscribed_deptos = context.chat_data.get("subscribed_deptos", [])

    query = update.callback_query
    query.answer()
    dpto_id = query.data.split(":")[1]

    if dpto_id not in subscribed_deptos:
        context.chat_data["subscribed_deptos"].append(dpto_id)
        data.persistence.flush()
        response = "\U0001F4A1 Te avisaré sobre los cambios en:\n<i>- " + DEPTS[dpto_id][1] + " ("+DEPTS[dpto_id][0]+")</i>"
    else:
        response = "\U0001F44D Ya te habías suscrito a:\n<i>- " + DEPTS[dpto_id][1] + " (" + DEPTS[dpto_id][0] + ")</i>"
    query.edit_message_text(text=response, parse_mode="HTML")


def subscribe_depto(update, context):
    logger.info("[Command /suscribir_depto]")
    if context.args:
        added = []
        already = []
        failed = []
        for arg in context.args:
            codigo = arg.upper()
            if codigo in CODIGO_DEPTS:
                print(CODIGO_DEPTS[codigo])
                if len(CODIGO_DEPTS[codigo])==1:
                    dpto_id = CODIGO_DEPTS[codigo][0]
                else:
                    keyboard = [[InlineKeyboardButton(DEPTS[x][1], callback_data="subdepto:"+x)] for x in CODIGO_DEPTS[codigo]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    update.message.reply_text("Hay "+str(len(CODIGO_DEPTS[codigo]))+" deptos con el código "+codigo, reply_markup=reply_markup)
                    continue
                if "subscribed_deptos" not in context.chat_data:
                    context.chat_data["subscribed_deptos"] = []
                if dpto_id not in context.chat_data["subscribed_deptos"]:
                    context.chat_data["subscribed_deptos"].append(dpto_id)
                    data.persistence.flush()
                    added.append(dpto_id)
                else:
                    already.append(dpto_id)
            else:
                failed.append(arg)
        response = ""
        if added:
            response += "\U0001F4A1 Te avisaré sobre los cambios en:\n<i>{}</i>\n\n" \
                .format("\n".join(["- " + DEPTS[x][1] + " ({})".format(DEPTS[x][0]) for x in added]))
        if already:
            response += "\U0001F44D Ya te habías suscrito a:\n<i>{}</i>\n\n" \
                .format("\n".join(["- " + DEPTS[x][1] + " ({})".format(DEPTS[x][0]) for x in already]))
        if failed:
            response += "\U0001F914 No pude identificar ningún departamento asociado a:\n<i>{}</i>\n\n"\
                .format("\n".join(["- " + x for x in failed]))

        if response:
            try_msg(context.bot,
                    chat_id=update.message.chat_id,
                    parse_mode="HTML",
                    text=response)

        if added and not context.chat_data.get("enable", False):
            try_msg(context.bot,
                    chat_id=update.message.chat_id,
                    parse_mode="HTML",
                    text="He registrado tus suscripciones ¡Pero los avisos para este chat están desactivados!.\n"
                         "Actívalos enviándome /start")
    else:
        try_msg(context.bot,
                chat_id=update.message.chat_id,
                parse_mode="HTML",
                text="Debes decirme qué departamentos deseas monitorear.\n<i>Ej. /suscribir_depto CC MA EI</i>\n\n"
                     "Para ver la lista de códigos de deptos que reconozco envía /deptos")


def multicode_curso_subscription(update, context):
    if "subscribed_cursos" not in context.chat_data:
        context.chat_data["subscribed_cursos"] = []

    query = update.callback_query
    query.answer()
    curso_id = query.data.split(":")[1]
    (d_arg, c_arg) = curso_id.split("-")

    if (d_arg, c_arg) not in context.chat_data["subscribed_cursos"]:
        context.chat_data["subscribed_cursos"].append((d_arg, c_arg))
        data.persistence.flush()
        is_curso_known = c_arg in data.current_data[d_arg]
        if is_curso_known:
            response = "\U0001F4A1 Te avisaré sobre cambios en:\n<i>" \
                    "- " + c_arg + " de " + DEPTS[d_arg][1] + " (" + DEPTS[d_arg][0] + ")</i>"
        else:
            response = "\U0001F4A1 Actualmente no tengo registros de:\n<i>" \
                    "- " + c_arg + " de " + DEPTS[d_arg][1] + " (" + DEPTS[d_arg][0] + ")</i>\n" \
                    "Te avisaré si aparece algún curso con ese código en ese depto."
    else:
        response = "\U0001F44D Ya estabas suscrito a:\n<i>" \
                "- " + c_arg + " de " + DEPTS[d_arg][1] + " (" + DEPTS[d_arg][0] + ")</i>."

    query.edit_message_text(text=response, parse_mode="HTML")


def subscribe_curso(update, context):
    logger.info("[Command /suscribir_curso]")
    if context.args:
        added = []
        already = []
        unknown = []
        failed = []
        failed_depto = []
        for arg in context.args:
            regex = match(r'^([a-zA-Z]+)(.*)', arg)
            if regex and "-" not in regex.group(2):
                d_code = regex.group(1).upper()
                c_arg = regex.group(2).upper()
            else:
                failed.append(arg)
                continue

            if d_code in CODIGO_CURSO:
                if len(CODIGO_CURSO[d_code]) == 1:
                    d_arg = CODIGO_CURSO[d_code][0]
                else:
                    keyboard = [[InlineKeyboardButton(DEPTS[x][1], callback_data="subcurso:"+x+"-"+d_code+c_arg)] for x in CODIGO_CURSO[d_code]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    update.message.reply_text("Hay "+str(len(CODIGO_CURSO[d_code]))+" deptos con el código " + d_code, reply_markup=reply_markup)
                    continue
                if "subscribed_cursos" not in context.chat_data:
                    context.chat_data["subscribed_cursos"] = []
                if (d_arg, d_code+c_arg) not in context.chat_data["subscribed_cursos"]:
                    context.chat_data["subscribed_cursos"].append((d_arg, d_code+c_arg))
                    data.persistence.flush()
                    is_curso_known = d_code+c_arg in data.current_data[d_arg]
                    if is_curso_known:
                        added.append((d_arg, d_code+c_arg))
                    else:
                        unknown.append((d_arg, d_code+c_arg))
                else:
                    already.append((d_arg, d_code+c_arg))
            else:
                failed_depto.append(d_code)
        response = ""
        if added:
            response += "\U0001F4A1 Te avisaré sobre cambios en:\n<i>{}</i>\n\n" \
                .format("\n".join(["- " + x[1] + " de " + DEPTS[x[0]][1] + " (" + DEPTS[x[0]][0] + ")" for x in added]))
        if unknown:
            response += "\U0001F4A1 Actualmente no tengo registros de:\n<i>{}</i>\n" \
                .format("\n".join(["- " + x[1] + " de " + DEPTS[x[0]][1] + " (" + DEPTS[x[0]][0] + ")" for x in unknown]))
            response += "Te avisaré si aparece algún curso con ese código en ese depto.\n\n"
        if already:
            response += "\U0001F44D Ya estabas suscrito a:\n<i>{}</i>.\n\n" \
                .format("\n".join(["- " + x[1] + " de " + DEPTS[x[0]][1] + " (" + DEPTS[x[0]][0] + ")" for x in already]))
        if failed_depto:
            response += "\U0001F914 No pude identificar ningún departamento asociado a:\n<i>{}</i>\n\n" \
                .format("\n".join(["- " + x for x in failed_depto]))
            response += "Puedo recordarte la lista de /deptos que reconozco.\n"
        if failed:
            response += "\U0001F914 No pude identificar el código de curso en:\n<i>{}</i>\n\n"\
                .format("\n".join(["- " + str(x) for x in failed]))
            response += "Guíate por el formato del ejemplo:\n" \
                        "<i>Ej. /suscribir_curso CC3001 MA1002</i>\n"

        if response:
            try_msg(context.bot,
                    chat_id=update.message.chat_id,
                    parse_mode="HTML",
                    text=response)

        if (added or unknown) and not context.chat_data.get("enable", False):
            try_msg(context.bot,
                    chat_id=update.message.chat_id,
                    parse_mode="HTML",
                    text="He registrado tus suscripciones ¡Pero los avisos para este chat están desactivados!\n"
                         "Actívalos enviándome /start")
    else:
        try_msg(context.bot,
                chat_id=update.message.chat_id,
                parse_mode="HTML",
                text="Debes decirme qué cursos deseas monitorear entregándome el código del curso para registrarlo.\n"
                     "<i>Ej. /suscribir_curso CC3001 MA1002</i>")

def multicode_depto_unsubscription(update, context):
    query = update.callback_query

    query.answer()
    dpto_id = query.data.split(":")[1]
    context.chat_data["subscribed_deptos"].remove(dpto_id)
    data.persistence.flush()
    response = "\U0001F6D1 Dejaré de avisarte sobre cambios en:\n<i>- " + DEPTS[dpto_id][1] + " ("+DEPTS[dpto_id][0]+")</i>"
    query.edit_message_text(text=response, parse_mode="HTML")

def unsubscribe_depto(update, context):
    logger.info("[Command /desuscribir_depto]")
    if context.args:
        deleted = []
        notsubscribed = []
        failed = []
        for arg in context.args:
            if arg.upper() in CODIGO_DEPTS:
                codigo = arg.upper()
                if len(CODIGO_DEPTS[codigo])==1:
                    dpto_id = CODIGO_DEPTS[codigo][0]
                else:
                    intersection = [x for x in CODIGO_DEPTS[codigo] if x in context.chat_data["subscribed_deptos"]]
                    if len(intersection) == 0:
                        notsubscribed.append(codigo)
                        continue
                    elif len(intersection) == 1:
                        dpto_id = intersection[0]
                    else:
                        keyboard = [[InlineKeyboardButton(DEPTS[x][1], callback_data="unsubdepto:"+x)] \
                                for x in intersection]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        update.message.reply_text("Hay "+str(len(intersection))+" deptos suscritos con el código " \
                                                  + codigo, reply_markup=reply_markup)
                        continue
                if dpto_id in context.chat_data["subscribed_deptos"]:
                    context.chat_data["subscribed_deptos"].remove(dpto_id)
                    data.persistence.flush()
                    deleted.append(dpto_id)
                else:
                    notsubscribed.append(dpto_id)
            else:
                failed.append(arg)
        response = ""

        if deleted:
            response += "\U0001F6D1 Dejaré de avisarte sobre cambios en:\n<i>{}</i>\n\n" \
                .format("\n".join(["- " + DEPTS[x][1] + " ({})".format(DEPTS[x][0]) for x in deleted]))
        if notsubscribed:
            response += "\U0001F44D No estás suscrito a <i>{}</i>.\n" \
                .format("\n".join(["- " + DEPTS[x][1] + " ({})".format(DEPTS[x][0]) for x in notsubscribed]))
        if failed:
            response += "\U0001F914 No pude identificar ningún departamento asociado a:\n<i>{}</i>\n\n"\
                .format("\n".join(["- " + str(x) for x in failed]))
            response += "Puedo recordarte la lista de /deptos que reconozco.\n"

        response += "Recuerda que puedes apagar temporalmente todos los avisos usando /stop, " \
                    "sin perder tus suscripciones"

        try_msg(context.bot,
                chat_id=update.message.chat_id,
                parse_mode="HTML",
                text=response)
    else:
        try_msg(context.bot,
                chat_id=update.message.chat_id,
                parse_mode="HTML",
                text="Indícame qué departamentos quieres dejar de monitorear.\n"
                     "<i>Ej. /desuscribir_depto CC MA</i>\n\n"
                     "Para ver las suscripciones de este chat envía /suscripciones\n"
                     "Para ver la lista de códigos de deptos que reconozco envía /deptos\n")

def multicode_curso_unsubscription(update, context):
    query = update.callback_query

    query.answer()
    (d_arg, c_arg) = query.data.split(":")[1].split("-")
    if "subscribed_cursos" not in context.chat_data:
        context.chat_data["subscribed_cursos"] = []
    if (d_arg, c_arg) in context.chat_data["subscribed_cursos"]:
        context.chat_data["subscribed_cursos"].remove((d_arg, c_arg))
        data.persistence.flush()
        response = "\U0001F6D1 Dejaré de avisarte sobre cambios en:\n" \
                "<i>- " + c_arg + " de " + DEPTS[d_arg][1] + " (" + DEPTS[d_arg][0] + ")</i>"
    else:
        response = "\U0001F44D No estás suscrito a\n" \
                "<i>- " + c_arg + " de " + DEPTS[d_arg][1] + " (" + DEPTS[d_arg][0] + ")</i>"
    query.edit_message_text(text=response, parse_mode="HTML")

def unsubscribe_curso(update, context):
    logger.info("[Command /desuscribir_curso]")
    if context.args:
        deleted = []
        notsub = []
        failed = []
        failed_depto = []
        for arg in context.args:
            regex = match(r'^([a-zA-Z]+)(.*)', arg)
            if regex and "-" not in regex.group(2):
                d_code = regex.group(1).upper()
                c_arg = regex.group(2).upper()
            else:
                failed.append(arg)
                continue

            if d_code in CODIGO_CURSO:
                if len(CODIGO_CURSO[d_code]) == 1:
                    d_arg = CODIGO_CURSO[d_code][0]
                else:
                    keyboard = [[InlineKeyboardButton(DEPTS[x][1], callback_data="unsubcurso:"+x+"-"+d_code+c_arg)] for x in CODIGO_CURSO[d_code]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    update.message.reply_text("Hay "+str(len(CODIGO_CURSO[d_code]))+" deptos con el código " + d_code, reply_markup=reply_markup)
                    continue
                if "subscribed_cursos" not in context.chat_data:
                    context.chat_data["subscribed_cursos"] = []
                if (d_arg, d_code+c_arg) in context.chat_data["subscribed_cursos"]:
                    context.chat_data["subscribed_cursos"].remove((d_arg, d_code+c_arg))
                    data.persistence.flush()
                    deleted.append((d_arg, d_code+c_arg))
                else:
                    notsub.append((d_arg, d_code+c_arg))
            else:
                failed_depto.append(arg)
        response = ""
        if deleted:
            response += "\U0001F6D1 Dejaré de avisarte sobre cambios en:\n<i>{}</i>\n\n" \
                .format("\n".join(["- " + x[1] + " de " + DEPTS[x[0]][1] + " (" + DEPTS[x[0]][0] + ")" for x in deleted]))
        if notsub:
            response += "\U0001F44D No estás suscrito a\n<i>{}</i>\n\n" \
                .format("\n".join(["- " + x[1] + " de " + DEPTS[x[0]][1] + " (" + DEPTS[x[0]][0] + ")" for x in notsub]))
        if failed_depto:
            response += "\U0001F914 No pude identificar ningún departamento asociado a:\n<i>{}</i>\n\n" \
                .format("\n".join(["- " + x for x in failed_depto]))
        if failed:
            response += "\U0001F914 No pude identificar el código de curso en:\n<i>{}</i>\n\n"\
                .format("\n".join(["- " + x for x in failed]))
            response += "Guíate por el formato del ejemplo:\n" \
                        "<i>Ej. /desuscribir_curso CC3001 MA1002</i>\n"

        response += "\nRecuerda que puedes apagar temporalmente todos los avisos usando /stop, " \
                    "sin perder tus suscripciones"
        try_msg(context.bot,
                chat_id=update.message.chat_id,
                parse_mode="HTML",
                text=response)
    else:
        try_msg(context.bot,
                chat_id=update.message.chat_id,
                parse_mode="HTML",
                text="Indícame qué cursos quieres dejar de monitorear.\n"
                     "<i>Ej. /desuscribir_curso CC3001 MA1002</i>\n\n"
                     "Para ver las suscripciones de este chat envía /suscripciones\n")


def deptos(update, context):
    logger.info("[Command /deptos]")
    deptos_list = ["<b>{}</b> - <i>{}</i>".format(DEPTS[x][0], DEPTS[x][1]) for x in DEPTS]

    try_msg(context.bot,
            chat_id=update.message.chat_id,
            parse_mode="HTML",
            text="Estos son los códigos que representan a cada departamento o área. "
                 "Utilizaré los mismos códigos que usa U-Campus para facilitar la consistencia\n"
                 "\n{}".format("\n".join(deptos_list)))


def subscriptions(update, context):
    logger.info("[Command /suscripciones]")
    subscribed_deptos = context.chat_data.get("subscribed_deptos", [])
    subscribed_cursos = context.chat_data.get("subscribed_cursos", [])

    sub_deptos_list = ["- <b>({})</b> <i>{}</i>".format(DEPTS[x][0], DEPTS[x][1]) for x in subscribed_deptos]
    sub_cursos_list = ["- <b>({})</b> en <i>{} - {}</i>"
                           .format(x[1], DEPTS[x[0]][0], DEPTS[x[0]][1]) for x in subscribed_cursos]

    result = "<b>Avisos activados:</b> <i>{}</i>\n\n" \
        .format("Sí \U00002714 (Detener: /stop)" if context.chat_data.get("enable", False)
                             else "No \U0000274C (Activar: /start)")

    if sub_deptos_list or sub_cursos_list:
        result += "Actualmente doy los siguientes avisos para este chat:\n\n"
    else:
        result += "Actualmente no tienes suscripciones a ningún departamento o curso.\n" \
                  "Suscribe avisos con /suscribir_depto o /suscribir_curso."

    if sub_deptos_list:
        result += "<b>Avisos por departamento:</b>\n"
        result += "\n".join(sub_deptos_list)
        result += "\n\n"
    if sub_cursos_list:
        result += "<b>Avisos por curso:</b>\n"
        result += "\n".join(sub_cursos_list)
        result += "\n\n"

    if sub_deptos_list or sub_cursos_list:
        result += "<i>Puedes desuscribirte con /desuscribir_depto y /desuscribir_curso.</i>"
    try_msg(context.bot,
            chat_id=update.message.chat_id,
            parse_mode="HTML",
            text=result)


def force_check(update, context):
    if int(update.message.from_user.id) in admin_ids:
        logger.info("[Command /force_check from admin %s]", update.message.from_user.id)
        job_check = jq.get_jobs_by_name("job_check")[0]
        job_check.run(dp)


def force_check_results(update, context):
    if int(update.message.from_user.id) in admin_ids:
        logger.info("[Command /force_check_results from admin %s]", update.message.from_user.id)
        job_check = jq.get_jobs_by_name("job_results")[0]
        job_check.run(dp)


def get_log(update, context):
    if int(update.message.from_user.id) in admin_ids:
        logger.info("[Command /get_log from admin %s]", update.message.from_user.id)
        context.bot.send_document(chat_id=update.message.from_user.id,
                                  document=open(os.path.relpath('bot.log'), 'rb'),
                                  filename="catalogobot_log_{}.txt"
                                  .format(datetime.now().strftime("%d%b%Y-%H%M%S")))


def get_chats_data(update, context):
    if int(update.message.from_user.id) in admin_ids:
        logger.info("[Command /get_chats_data from admin %s]", update.message.from_user.id)
        try:
            db_path = os.path.relpath('db')
            with open(db_path, 'rb') as logfile:
                json_result = json.dumps(pickle.load(logfile), sort_keys=True, indent=4)
            with tempfile.NamedTemporaryFile(delete=False, mode="w+t") as temp_file:
                temp_filename = temp_file.name
                temp_file.write(json_result)
            with open(temp_filename, 'rb') as temp_doc:
                context.bot.send_document(chat_id=update.message.from_user.id,
                                          document=temp_doc,
                                          filename="catalogobot_chat_data_{}.txt"
                                          .format(datetime.now().strftime("%d%b%Y-%H%M%S")))
            os.remove(temp_filename)
        except Exception as e:
            logger.exception(e)


def force_notification(update, context):
    if int(update.message.from_user.id) in admin_ids:
        logger.info("[Command /force_notification from admin %s]", update.message.from_user.id)
        chats_data = dp.chat_data
        if context.args:
            message = update.message.text
            message = message[message.index(" ")+1:].replace("\\", "")
            for chat_id in chats_data:
                try_msg(context.bot,
                        chat_id=chat_id,
                        force=True,
                        text=message,
                        parse_mode="Markdown",
                        )


def notification(update, context):
    if int(update.message.from_user.id) in admin_ids:
        logger.info("[Command /notification from admin %s]", update.message.from_user.id)
        chats_data = dp.chat_data
        if context.args:
            message = update.message.text
            message = message[message.index(" ")+1:].replace("\\", "")
            for chat_id in chats_data:
                if chats_data[chat_id].get("enable", False):
                    try_msg(context.bot,
                            chat_id=chat_id,
                            text=message,
                            parse_mode="Markdown",
                            )


def enable_check_results(update, context):
    if int(update.message.from_user.id) in admin_ids:
        logger.info("[Command /enable_check_results from admin %s]", update.message.from_user.id)
        current = data.job_check_results.enabled
        data.job_check_results.enabled = not current
        data.config["is_checking_results"] = not current
        save_config()
        notif = "Check results: {}".format(str(data.config["is_checking_results"]))
        try_msg(context.bot,
                chat_id=admin_ids[0],
                text=notif
                )
        logger.info(notif)


def enable_check_changes(update, context):
    if int(update.message.from_user.id) in admin_ids:
        logger.info("[Command /enable_check_changes from admin %s]", update.message.from_user.id)
        current = data.job_check_changes.enabled
        data.job_check_changes.enabled = not current
        data.config["is_checking_changes"] = not current
        save_config()
        notif = "Check changes: {}".format(str(data.config["is_checking_changes"]))
        try_msg(context.bot,
                chat_id=admin_ids[0],
                text=notif
                )
        logger.info(notif)


def changes_check_interval(update, context):
    if int(update.message.from_user.id) in admin_ids:
        logger.info("[Command /changes_check_interval from admin %s]", update.message.from_user.id)
        if context.args:
            try:
                data.config["changes_check_interval"] = int(context.args[0])
            except ValueError:
                logger.error(f'{context.args[0]} is not a valid interval value')
                return
            save_config()
            notif = "Changes check interval: {} seconds".format(str(data.config["changes_check_interval"]))
            try_msg(context.bot,
                    chat_id=admin_ids[0],
                    text=notif
                    )
            logger.info(notif)


def results_check_interval(update, context):
    if int(update.message.from_user.id) in admin_ids:
        logger.info("[Command /results_check_interval from admin %s]", update.message.from_user.id)
        if context.args:
            try:
                data.config["results_check_interval"] = int(context.args[0])
            except ValueError:
                logger.error(f'{context.args[0]} is not a valid interval value')
                return
            save_config()
            notif = "Results check interval: {} seconds".format(str(data.config["results_check_interval"]))
            try_msg(context.bot,
                    chat_id=admin_ids[0],
                    text=notif
                    )
            logger.info(notif)


def admin_help(update, context):
    if int(update.message.from_user.id) in admin_ids:
        logger.info("[Command /help from admin %s]", update.message.from_user.id)
        try_msg(context.bot,
                chat_id=admin_ids[0],
                text=
                '/force_check\n'
                '/get_log\n'
                '/get_chats_data\n'
                '/notification\n'
                '/force_notification\n'
                '/force_check_results\n'
                '/enable_check_results\n'
                '/enable_check_changes\n'
                '/changes_check_interval\n'
                '/results_check_interval\n'
                '/help\n'
                )
