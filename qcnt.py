# encoding:utf-8

import json
import os

import plugins
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from channel.wechat.wechat_channel import WechatChannel
from channel.wechatcom.wechatcomapp_channel import WechatComAppChannel
from channel.wechatmp.wechatmp_channel import WechatMPChannel
from common.log import logger
from config import conf
from plugins import *
from datetime import datetime, timedelta
from bridge.context import *


def create_comapp():
    # create channel
    channel_name = conf().get("channel_type", "wx")

    # Create a dictionary to map channel types to their corresponding classes
    channel_class_map = {
        'wechatcom_app': WechatComAppChannel,
        'wx': WechatChannel,
        'wechatmp': WechatMPChannel
    }

    # Get the class from the dictionary
    channel_class = channel_class_map.get(channel_name)

    if channel_class is None:
        print(f"Unknown channel type: {channel_name}")
        return None

    # Create a ComApp object based on the channel type
    comapp = channel_class()
    return comapp


# 先即刻回复用户一个等待信息，优化用户体验
def _reply_in_thinking(context: Context):
    reply_t = Reply()
    reply_t.type = ReplyType.TEXT
    if context.get("isgroup", False):
        if context.type == ContextType.PATPAT:
            reply_t.content = "💌 知道@" + context["msg"].actual_user_nickname + " 你很喜欢我，我是小Ai助理，有任何问题随时问我。"
        elif context.type == ContextType.IMAGE_CREATE:
            reply_t.content = "💌 已收到您的信息@" + context["msg"].actual_user_nickname + "，请求提交绘画任务🍵"
        else:
            reply_t.content = "💌 已收到您的信息@" + context["msg"].actual_user_nickname + "，让我思考一下，请耐心等待🍵"
    else:
        if context.type == ContextType.PATPAT:
            reply_t.content = "知道你很喜欢我，我是小Ai助理，有任何问题随时问我。"
        elif context.type == ContextType.IMAGE_CREATE:
            reply_t.content = "💌 已收到您的信息，请求提交绘画任务🍵"
        else:
            reply_t.content = "💌 已收到您的信息，让我思考一下，请耐心等待🍵"
    try:
        com_app = create_comapp()
        com_app.send(reply_t, context)
    except Exception as e:
        logger.error("[Qcnt] {}".format(e))


@plugins.register(
    name="QCnt",
    desire_priority=99,
    hidden=True,
    desc="To collect the usage data of questions, and fulfill the reply control with usage data",
    version="1.0",
    author="Hroid",
)
class QCnt(Plugin):
    def __init__(self):
        super().__init__()
        self.user_dict = {}  # 存放单聊用户信息和使用数据
        self.group_dict = {}  # 存放群聊用户信息和使用数据
        try:
            cur_dir = os.path.dirname(__file__)
            config_path = os.path.join(cur_dir, "config.json")
            conf = None
            if not os.path.exists(config_path):
                conf = {
                    "single_max": 10,
                    "group_member_max": 10,
                    "group_total_max": 100,
                    "limit_interval": "day"
                }
                with open(config_path, "w") as f:
                    json.dump(conf, f, indent=4)
            else:
                with open(config_path, "r") as f:
                    conf = json.load(f)
            self.single_max = conf["single_max"]
            self.group_member_max = conf["group_member_max"]
            self.group_total_max = conf["group_total_max"]
            self.limit_interval = conf["limit_interval"]

            self.init_datetime = datetime.now()

            self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
            self.handlers[Event.ON_DECORATE_REPLY] = self.on_decorate_reply
            logger.info("[qCnt] inited")
        except Exception as e:
            logger.warn("[QCnt] init failed")
            raise e

    def refresh_limit(self):
        new_datetime = datetime.now()
        if self.limit_interval == "hour":  # 按小时更新清零限制次数
            if new_datetime >= self.init_datetime + timedelta(hours=1):
                self.user_dict.clear()
                self.group_dict.clear()
                self.init_datetime = datetime.now()
                logger.info("[Qcnt] reset hour limit")
        elif self.limit_interval == "day":  # 按天更新清零限制次数
            if new_datetime >= self.init_datetime + timedelta(days=1):
                self.user_dict.clear()
                self.group_dict.clear()
                self.init_datetime = datetime.now()
                logger.info("[Qcnt] reset day limit")
        else:
            logger.warn("[QCnt] config parameters error in func-refresh_limit")

    def get_interval_str_ind(self):
        if self.limit_interval == "hour":  # 按小时更新清零限制次数
            str_ind = "小时"
        elif self.limit_interval == "day":  # 按天更新清零限制次数
            str_ind = "每日"
        else:
            str_ind = ""
        return str_ind

    def on_handle_context(self, e_context: EventContext):
        if e_context["context"].type not in [
            ContextType.TEXT,
            ContextType.IMAGE_CREATE,
            ContextType.PATPAT
        ]:
            return

        # 判断是否需要重置限制次数
        self.refresh_limit()

        # 判断是群聊消息还是单聊消息
        if e_context["context"].get("isgroup", False):
            group_id = e_context["context"]["msg"].other_user_id
            group_member_id = e_context["context"]["msg"].actual_user_id
            # 判断对应群聊是否记录过使用数据，没有的话记录并初始化数据
            if group_id not in self.group_dict:
                chat_room = {"group_total_max": 0, "group_member": {}}
                chat_room["group_member"][group_member_id] = 0
                self.group_dict[group_id] = chat_room
                logger.info("Group User List:{}".format(self.group_dict))
            elif self.group_dict[group_id]["group_total_max"] < self.group_total_max:   # 群聊是否超出次数
                if group_member_id not in self.group_dict[group_id]["group_member"]:    # 新的群聊用户，还未加入记录
                    self.group_dict[group_id]["group_member"][group_member_id] = 0      # 初始化新群聊用户
                    logger.info("Group User List:{}".format(self.group_dict))
                else:   # 已记录过的群聊用户
                    if self.group_dict[group_id]["group_member"][group_member_id] < self.group_member_max: # 用户是否超出次数
                        # 在装饰回复内容的时候才真正加一计数
                        # self.group_dict[group_id]["group_total_max"] += 1
                        # self.group_dict[group_id]["group_member"][group_member_id] += 1
                        logger.info("[Qcnt] Check whether exceed limit")
                    else:  # 群聊对应的用户已超出限定次数
                        reply = Reply(ReplyType.INFO,
                                      "🔔 用量提醒\n" +
                                      "您个人已使用{}次/可使用{}次，请联系服务方"
                                      .format(self.group_dict[group_id]["group_member"][group_member_id],
                                              self.group_member_max) + "，或等待\"" + self.get_interval_str_ind() + "额度\"更新。")
                        e_context["reply"] = reply
                        e_context.action = EventAction.BREAK_PASS
                        return
            else:  # 群聊已超出总限定次数
                reply = Reply(ReplyType.INFO,
                              "🔔 用量提醒\n" +
                              "群已使用{}次/可使用{}次，请联系服务方"
                              .format(self.group_dict[group_id]["group_total_max"],
                                      self.group_total_max) + "，或等待\"" + self.get_interval_str_ind() + "额度\"更新。")
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return
        else:  # 单聊
            user_id = e_context["context"]["msg"].from_user_id
            # 判断对应用户是否记录过使用数据，没有的话记录并初始化数据
            if user_id not in self.user_dict:
                self.user_dict[user_id] = 0
                logger.info("User List:{}".format(self.user_dict))
            # 判断使用次数是否超限
            elif self.user_dict[user_id] < self.single_max:
                # self.user_dict[user_id] += 1  # 在装饰回复内容的时候才真正加一计数
                logger.info("User List:{}".format(self.user_dict))
            else:  # 使用次数超限
                reply = Reply(ReplyType.INFO,
                              "🔔 用量提醒\n" +
                              "已使用{}次/可使用{}次，请联系服务方"
                              .format(self.user_dict[user_id],
                                      self.single_max) + "，或等待\"" + self.get_interval_str_ind() + "额度\"更新。")
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
                return

        # 给予处理的即时回应
        _reply_in_thinking(e_context["context"])

    def on_decorate_reply(self, e_context: EventContext):
        if e_context["reply"].type not in [
            ReplyType.TEXT
        ]:
            return

        # 判断是否群聊消息
        if e_context["context"].get("isgroup", False):
            group_id = e_context["context"]["msg"].other_user_id
            group_member_id = e_context["context"]["msg"].actual_user_id
            if (group_id not in self.group_dict) or (group_member_id not in self.group_dict[group_id]["group_member"]):
                # 异常，未曾记录过的用户或者群组
                logger.error("The correspond group | user wasn't record in the previous process!!")
                e_context.action = EventAction.CONTINUE
                return

            # 判断群聊是否超出总限定次数，累计加一计数
            if self.group_dict[group_id]["group_total_max"] < self.group_total_max:
                # 判断群聊对应的用户是否超出限定次数
                if self.group_dict[group_id]["group_member"][group_member_id] < self.group_member_max:
                    self.group_dict[group_id]["group_total_max"] += 1
                    self.group_dict[group_id]["group_member"][group_member_id] += 1

            reply = e_context["reply"]
            content = reply.content

            # 附加提示信息
            reply = Reply(ReplyType.TEXT, content +
                          "\n\n🔔用量提醒 - " + self.get_interval_str_ind() + "额度：\n" + "个人(已用{}/总{})次。\n群成员(已用({}/总{})次。"
                          .format(self.group_dict[group_id]["group_member"][group_member_id],
                                  self.group_member_max,
                                  self.group_dict[group_id]["group_total_max"],
                                  self.group_total_max))
        else:  # 单聊
            if e_context["context"]["msg"].from_user_id not in self.user_dict:
                logger.error("The correspond user wasn't record in the previous process!!")
                e_context.action = EventAction.CONTINUE
                return

            user_id = e_context["context"]["msg"].from_user_id
            # 判断使用次数是否超限 累计加一计数
            if self.user_dict[user_id] < self.single_max:
                self.user_dict[user_id] += 1
                logger.info("User List:{}".format(self.user_dict))

            reply = e_context["reply"]
            content = reply.content

            # 附加提示信息
            reply = Reply(ReplyType.TEXT, content +
                          "\n\n🔔用量提醒\n" + self.get_interval_str_ind() + "额度：(已用{}/总{})次。"
                          .format(self.user_dict[user_id], self.single_max))
        e_context["reply"] = reply
        e_context.action = EventAction.CONTINUE

    def get_help_text(self, **kwargs):
        help_text = "用于统计和限制一对一单聊和群聊的提问次数\n"
        return help_text
